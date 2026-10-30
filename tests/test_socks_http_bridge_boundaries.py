"""Protocol and resource boundaries. All input and destinations are synthetic."""
import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import os
import sys
import types
import socket
import unittest
from unittest.mock import patch

from test_socks_http_bridge import AUTH, MemorySocket, bridge, request, run_handler

OK = b"HTTP/1.1 204 No Content\r\n\r\n"


class AuthorityTests(unittest.TestCase):
    def test_supported_authorities(self):
        for raw, expected in (
            ("example.invalid", ("example.invalid", 80)),
            ("example.invalid:443", ("example.invalid", 443)),
            ("127.0.0.1:8080", ("127.0.0.1", 8080)),
            ("[::1]:443", ("::1", 443)),
            ("[2001:db8::1]", ("2001:db8::1", 80)),
            ("service_name.invalid:00080", ("service_name.invalid", 80)),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(bridge.parse_host_port(raw, 80), expected)

    def test_python_integer_spellings_are_not_http_ports(self):
        for raw in ("host:+80", "host:1_23", "host:-80", "host:\u0668\u0660"):
            with self.subTest(raw=raw), self.assertRaises(bridge.HeaderError):
                bridge.parse_host_port(raw, 80)

    def test_authority_rejects_userinfo_delimiters_and_non_http_space(self):
        for raw in ("user@host:80", "host/path:80", "host?x:80", "host#x:80",
                    "host\\name:80", " host:80", "host:80\t", "host:80\xa0",
                    "\x00host:80", "host:80\x7f", "host%00:80"):
            with self.subTest(raw=raw), self.assertRaises(bridge.HeaderError):
                bridge.parse_host_port(raw, 80)

    def test_brackets_require_ipv6_and_ports_are_in_range(self):
        for raw in ("[localhost]:80", "[127.0.0.1]:80", "[::z]:80", "::1",
                    "[::1", "[]:80", "[::1]junk", "[::1]:", "host:",
                    "host:0", "host:65536", "host:" + "9" * 5000):
            with self.subTest(raw=raw[:50]), self.assertRaises(bridge.HeaderError):
                bridge.parse_host_port(raw, 80)

    def test_invalid_target_never_attempts_upstream_connection(self):
        for target in (b"host:1_23", b"host:+80", b"[localhost]:443", b"host/path:80"):
            handler, response = run_handler(request(method=b"CONNECT", target=target))
            self.assertEqual(handler.connections, [])
            self.assertTrue(response.startswith(b"HTTP/1.1 400 "), response)


class BasicInteroperabilityTests(unittest.TestCase):
    def test_basic_scheme_is_case_insensitive(self):
        for scheme in (b"basic", b"BASIC", b"bAsIc"):
            with self.subTest(scheme=scheme):
                raw = request().replace(b"Basic ", scheme + b" ")
                _, response = run_handler(raw, MemorySocket([OK]))
                self.assertEqual(response, OK)

    def test_basic_accepts_required_spaces_not_tabs(self):
        for separator in (b" ", b"  ", b"   "):
            raw = request().replace(b"Basic ", b"Basic" + separator)
            _, response = run_handler(raw, MemorySocket([OK]))
            self.assertEqual(response, OK)
        handler, response = run_handler(request().replace(b"Basic ", b"Basic\t"))
        self.assertEqual(handler.connections, [])
        self.assertTrue(response.startswith(b"HTTP/1.1 407 "))

    def test_case_normalization_does_not_change_credential_bytes(self):
        for replacement in (b"Bearer " + AUTH.split(" ")[1].encode(),
                            AUTH.encode().replace(b"c3lu", b"C3lu"),
                            AUTH.encode() + b"=", b"Basic", b"Basic "):
            handler, response = run_handler(request().replace(AUTH.encode(), replacement))
            self.assertEqual(handler.connections, [])
            self.assertTrue(response.startswith(b"HTTP/1.1 407 "), response)


class ProtocolBoundaryTests(unittest.TestCase):
    def test_valid_extension_method_is_not_misclassified_as_large_headers(self):
        for method in (b"M-SEARCH", b"VERSION-CONTROL", b"custom", b"X_2", b"A!#$%&'*+.^_`|~-"):
            with self.subTest(method=method):
                origin = MemorySocket([OK])
                handler, response = run_handler(request(method=method), origin)
                self.assertEqual(response, OK)
                self.assertEqual(handler.connections, [("synthetic.invalid", 80)])
                self.assertTrue(b"".join(origin.sent).startswith(method + b" / HTTP/1.1\r\n"))

    def test_bad_method_or_request_line_is_rejected_before_connect(self):
        for method in (b"bad(method)", b"bad:method", b"bad/method", b"\xff", b"", b"bad\tmethod"):
            handler, response = run_handler(request(method=method))
            self.assertEqual(handler.connections, [])
            self.assertTrue(response.startswith(b"HTTP/1.1 400 "), response)
        raw = request(method=b"CONNECT", target=b"host:443").replace(b"CONNECT ", b"CONNECT\t")
        handler, response = run_handler(raw)
        self.assertEqual(handler.connections, [])
        self.assertTrue(response.startswith(b"HTTP/1.1 400 "), response)

    def test_http10_transfer_encoding_is_rejected_before_connect(self):
        raw = request(method=b"POST", extra=b"Transfer-Encoding: chunked\r\n", body=b"0\r\n\r\n")
        handler, response = run_handler(raw.replace(b"HTTP/1.1", b"HTTP/1.0"), MemorySocket([OK]))
        self.assertEqual(handler.connections, [])
        self.assertTrue(response.startswith(b"HTTP/1.1 400 "), response)

    def test_http10_fixed_length_and_http11_chunked_still_work(self):
        fixed = request(method=b"POST", extra=b"Content-Length: 3\r\n", body=b"abc")
        chunked = request(method=b"POST", extra=b"Transfer-Encoding: chunked\r\n", body=b"3\r\nabc\r\n0\r\n\r\n")
        for raw in (fixed.replace(b"HTTP/1.1", b"HTTP/1.0"), chunked):
            origin = MemorySocket([OK])
            _, response = run_handler(raw, origin)
            self.assertEqual(response, OK)

    def test_empty_upstream_response_returns_502(self):
        origin = MemorySocket()
        _, response = run_handler(request(), origin)
        self.assertTrue(response.startswith(b"HTTP/1.1 502 "), response)
        self.assertTrue(origin.closed)

    def test_empty_upstream_after_local_continue_returns_final_502(self):
        _, response = run_handler(request(method=b"POST", extra=b"Expect: 100-continue\r\nContent-Length: 0\r\n"), MemorySocket())
        self.assertTrue(response.startswith(b"HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 502 "), response)

    def test_partial_status_does_not_get_replaced_or_appended(self):
        _, response = run_handler(request(), MemorySocket([b"HTTP/1."]))
        self.assertEqual(response, b"HTTP/1.")

    def test_invalid_absolute_ipv6_is_bad_request_not_bad_gateway(self):
        handler, response = run_handler(request(target=b"http://[::z]/"))
        self.assertEqual(handler.connections, [])
        self.assertTrue(response.startswith(b"HTTP/1.1 400 "), response)

    def test_missing_colon_or_folded_header_is_bad_request(self):
        for extra in (b"Broken\r\n", b" Folded: value\r\n", b"X\x00: value\r\n", b"X: a\x00b\r\n"):
            handler, response = run_handler(request(extra=extra))
            self.assertEqual(handler.connections, [])
            self.assertTrue(response.startswith(b"HTTP/1.1 400 "), response)

    def test_non_ascii_origin_form_host_is_bad_request(self):
        for value in (b"host\xff", b"host\xa0:80"):
            raw = request(target=b"/").replace(b"Host: synthetic.invalid", b"Host: " + value)
            handler, response = run_handler(raw)
            self.assertEqual(handler.connections, [])
            self.assertTrue(response.startswith(b"HTTP/1.1 400 "), response)

    def test_oversized_content_length_is_413(self):
        raw = request(method=b"POST", extra=("Content-Length: %d\r\n" % (bridge.MAX_BODY_BYTES + 1)).encode())
        handler, response = run_handler(raw)
        self.assertEqual(handler.connections, [])
        self.assertTrue(response.startswith(b"HTTP/1.1 413 "), response)


class DeadlineAndFramingTests(unittest.TestCase):
    def test_exact_header_limit_and_over_limit(self):
        raw = b"GET / HTTP/1.1\r\nX: a\r\n\r\n"
        self.assertEqual(bridge.recv_until_headers(MemorySocket([raw]), len(raw)), raw)
        with self.assertRaises(bridge.HeaderError) as cm:
            bridge.recv_until_headers(MemorySocket([raw]), len(raw)-1)
        self.assertEqual(cm.exception.status, b"431 Request Header Fields Too Large")

    def test_header_socket_timeout_is_request_timeout(self):
        with self.assertRaises(bridge.HeaderError) as cm:
            bridge.recv_until_headers(MemorySocket([socket.timeout("synthetic")]))
        self.assertEqual(cm.exception.status, b"408 Request Timeout")

    def test_header_absolute_deadline_is_not_reset_by_trickle(self):
        with patch.object(bridge.time, "monotonic", side_effect=[0.0, 0.1, 11.0]):
            with self.assertRaises(bridge.HeaderError) as cm:
                bridge.recv_until_headers(MemorySocket([b"G", b"E"]))
        self.assertEqual(cm.exception.status, b"408 Request Timeout")

    def test_truncated_header_is_bad_request(self):
        with self.assertRaises(bridge.HeaderError) as cm:
            bridge.recv_until_headers(MemorySocket([b"GET / HTTP/1.1\r\n"]))
        self.assertEqual(cm.exception.status, b"400 Bad Request")

    def test_body_socket_timeout_and_deadline_are_request_timeouts(self):
        with self.assertRaises(bridge.HeaderError) as cm:
            bridge.RequestBody(MemorySocket([socket.timeout("synthetic")]), b"").exact(1)
        self.assertEqual(cm.exception.status, b"408 Request Timeout")
        with patch.object(bridge.time, "monotonic", side_effect=[0.0, bridge.BODY_TIMEOUT + 1]):
            with self.assertRaises(bridge.HeaderError) as cm:
                bridge.RequestBody(MemorySocket(), b"").exact(1)
        self.assertEqual(cm.exception.status, b"408 Request Timeout")

    def test_truncated_or_malformed_chunks_fail_without_forwarding_pipeline(self):
        for wire in (b"z\r\n", b"-1\r\n", b"1\r\nxXX", b"0\r\nTrailer: x\r\n\r\n",
                     b"10000000000000000\r\n"):
            with self.subTest(wire=wire):
                origin = MemorySocket()
                with self.assertRaises(bridge.HeaderError):
                    bridge.RequestBody(MemorySocket(), wire).chunks(origin)
                self.assertNotIn(b"Trailer", b"".join(origin.sent))

    def test_body_size_limit_applies_cumulatively(self):
        with patch.object(bridge, "MAX_BODY_BYTES", 5):
            origin = MemorySocket()
            with self.assertRaises(bridge.HeaderError) as cm:
                bridge.RequestBody(MemorySocket(), b"3\r\nabc\r\n3\r\ndef\r\n0\r\n\r\n").chunks(origin)
            self.assertEqual(cm.exception.status, b"413 Content Too Large")
            self.assertNotIn(b"def", b"".join(origin.sent))

    def test_chunk_line_length_is_bounded(self):
        with self.assertRaises(bridge.HeaderError):
            bridge.RequestBody(MemorySocket(), b"a" * 8193 + b"\r\n").line()

    def test_every_split_of_headers_is_reassembled(self):
        raw = request(extra=b"X-Test: value\r\n")
        for i in range(1, len(raw)):
            with self.subTest(split=i):
                self.assertEqual(bridge.recv_until_headers(MemorySocket([raw[:i], raw[i:]])), raw)

    def test_every_split_of_chunked_request_preserves_data(self):
        wire = b"3;ext=yes\r\nabc\r\n2\r\nde\r\n0\r\n\r\nGET /never HTTP/1.1\r\n\r\n"
        for i in range(len(wire)):
            with self.subTest(split=i):
                origin = MemorySocket()
                bridge.RequestBody(MemorySocket([wire[i:]]), wire[:i]).chunks(origin)
                self.assertEqual(b"".join(origin.sent), b"3\r\nabc\r\n2\r\nde\r\n0\r\n\r\n")


class ExistingGuardTests(unittest.TestCase):
    def test_loopback_only_listener_policy_is_unchanged(self):
        for host in ("127.0.0.1", "::1", "localhost"):
            self.assertEqual(bridge.validate_loopback_host(host), host)
        for host in ("0.0.0.0", "::", "192.0.2.1", "127.0.0.2", "example.invalid"):
            with self.assertRaises(argparse.ArgumentTypeError):
                bridge.validate_loopback_host(host)

    def test_port_validation_and_upstream_host_controls(self):
        for value in ("1", "80", "65535"):
            self.assertEqual(bridge.valid_port(value), int(value))
        for value in ("0", "65536", "no"):
            with self.assertRaises(argparse.ArgumentTypeError):
                bridge.valid_port(value)
        for host in ("", "a b", "a\x00b", "x" * 254):
            with self.assertRaises(argparse.ArgumentTypeError):
                bridge.validate_upstream_host(host)

    def test_named_hop_headers_and_credentials_are_removed(self):
        origin = MemorySocket([OK])
        run_handler(request(extra=b"Connection: X-Internal\r\nX-Internal: private\r\nX-End: public\r\nProxy-Connection: keep-alive\r\n"), origin)
        wire = b"".join(origin.sent)
        self.assertNotIn(b"private", wire)
        self.assertNotIn(AUTH.encode(), wire)
        self.assertIn(b"X-End: public", wire)

    def test_thread_start_failure_releases_worker_slot(self):
        with bridge.ThreadingTCPServer(("127.0.0.1", 0), bridge.ProxyHandler) as server:
            before = server.worker_slots._value
            with patch.object(bridge.socketserver.ThreadingTCPServer, "process_request", side_effect=RuntimeError("synthetic")):
                with self.assertRaises(RuntimeError):
                    server.process_request(MemorySocket(), ("127.0.0.1", 0))
            self.assertEqual(server.worker_slots._value, before)

    def test_saturation_rejects_without_starting_another_worker(self):
        with bridge.ThreadingTCPServer(("127.0.0.1", 0), bridge.ProxyHandler) as server:
            for _ in range(bridge.MAX_WORKERS):
                self.assertTrue(server.worker_slots.acquire(blocking=False))
            try:
                incoming = MemorySocket()
                server.process_request(incoming, ("127.0.0.1", 0))
                self.assertTrue(incoming.closed)
            finally:
                for _ in range(bridge.MAX_WORKERS):
                    server.worker_slots.release()


class EntryPointAndSocketLifecycleTests(unittest.TestCase):
    def test_socks_connect_parameters_and_failure_cleanup(self):
        # Exercises our call into PySocks; the library handshake is not mocked
        # into a success claim. A real SOCKS service is outside this fixture.
        for fail in (False, True):
            class ProxySocket(MemorySocket):
                def set_proxy(self, *args, **kwargs):
                    self.proxy_args = (args, kwargs)
                def connect(self, target):
                    self.target = target
                    if fail:
                        raise OSError("synthetic connect failure")
            upstream = ProxySocket()
            library = types.SimpleNamespace(SOCKS5=2, socksocket=lambda: upstream)
            handler = object.__new__(bridge.ProxyHandler)
            handler.socks_rdns = False
            with patch.object(bridge, "socks", library):
                if fail:
                    with self.assertRaises(OSError):
                        handler.connect_via_socks("synthetic.invalid", 443)
                    self.assertTrue(upstream.closed)
                else:
                    self.assertIs(handler.connect_via_socks("synthetic.invalid", 443), upstream)
                    self.assertFalse(upstream.closed)
            self.assertEqual(upstream.proxy_args, ((2, "127.0.0.1", 10808), {"rdns": False}))
            self.assertEqual(upstream.target, ("synthetic.invalid", 443))
            self.assertEqual(upstream.timeouts, [bridge.IO_TIMEOUT])

    def test_proxy_header_stripping_preserves_unrelated_body_bytes(self):
        body = b"Proxy-Authorization: body-not-a-header\x00\xff"
        raw = request(extra=b"Proxy-Connection: keep-alive\r\nX-End: yes\r\n", body=body)
        out = bridge.strip_proxy_headers(raw)
        header, actual_body = out.split(b"\r\n\r\n", 1)
        self.assertNotIn(AUTH.encode(), header)
        self.assertNotIn(b"Proxy-Connection", header)
        self.assertIn(b"X-End: yes", header)
        self.assertEqual(actual_body, body)

    def test_main_invalid_listener_or_token_stops_before_server_creation(self):
        base = ["bridge", "--auth-token-env", "SYNTHETIC_BRIDGE_TOKEN"]
        cases = ((["--listen-host", "0.0.0.0"], "a" * 64),
                 (["--listen-port", "0"], "a" * 64),
                 (["--socks-port", "65536"], "a" * 64),
                 (["--socks-host", "bad host"], "a" * 64),
                 ([], ""), ([], "not-hex"), ([], "a" * 63))
        for extra, token in cases:
            with self.subTest(extra=extra, token_length=len(token)):
                err = io.StringIO()
                with patch.object(sys, "argv", base + extra), patch.dict(os.environ, {"SYNTHETIC_BRIDGE_TOKEN": token}):
                    with patch.object(bridge, "ThreadingTCPServer") as factory, redirect_stderr(err):
                        with self.assertRaises(SystemExit) as cm:
                            bridge.main()
                        self.assertEqual(cm.exception.code, 2)
                        factory.assert_not_called()
                self.assertNotIn("a" * 63, err.getvalue())
        with patch.object(sys, "argv", ["bridge", "--auth-token-env", "bad-name"]), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                bridge.main()
            self.assertEqual(cm.exception.code, 2)

    def test_main_propagates_settings_and_closes_server_without_printing_token(self):
        token = "a" * 64
        for host, server_name, no_rdns in (("127.0.0.1", "ThreadingTCPServer", False),
                                          ("::1", "ThreadingTCPServerV6", True)):
            argv = ["bridge", "--auth-token-env", "SYNTHETIC_BRIDGE_TOKEN", "--listen-host", host,
                    "--listen-port", "18088", "--socks-host", "127.0.0.1", "--socks-port", "10808"]
            if no_rdns:
                argv.append("--no-rdns")
            saved = {name: getattr(bridge.ProxyHandler, name) for name in
                     ("expected_proxy_authorization", "socks_host", "socks_port", "socks_rdns")}
            stream = io.StringIO()
            try:
                with patch.object(sys, "argv", argv), patch.dict(os.environ, {"SYNTHETIC_BRIDGE_TOKEN": token}):
                    with patch.object(bridge, server_name) as factory, redirect_stdout(stream):
                        factory.return_value.serve_forever.side_effect = KeyboardInterrupt
                        self.assertEqual(bridge.main(), 0)
                        factory.assert_called_once_with((host, 18088), bridge.ProxyHandler)
                        factory.return_value.server_close.assert_called_once()
                        self.assertEqual(bridge.ProxyHandler.socks_rdns, not no_rdns)
                        self.assertEqual(bridge.ProxyHandler.expected_proxy_authorization,
                                         "Basic " + bridge.base64.b64encode(("codex:" + token).encode()).decode())
                self.assertNotIn(token, stream.getvalue())
                self.assertNotIn("Proxy-Authorization", stream.getvalue())
            finally:
                for name, value in saved.items():
                    setattr(bridge.ProxyHandler, name, value)


if __name__ == "__main__":
    unittest.main()
