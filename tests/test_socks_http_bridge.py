"""Offline bridge regressions. SOCKS negotiation is outside these test doubles.

Only the import-time annotation is supplied when PySocks is unavailable. The
production relay/parser/handler methods are executed; no real proxy or account
is used. Native packaged-Python/SOCKS validation remains a separate check.
"""
from collections import deque
import importlib.util
from pathlib import Path
import socket
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("portable_bridge_test", ROOT / "tool/socks-http-bridge.py")
bridge = importlib.util.module_from_spec(SPEC)
try:
    import socks  # noqa: F401 - use the installed dependency when present
except ImportError:
    with patch.dict(sys.modules, {"socks": types.SimpleNamespace(socksocket=socket.socket)}):
        SPEC.loader.exec_module(bridge)
else:
    SPEC.loader.exec_module(bridge)

AUTH = "Basic c3ludGhldGljOm5vdC1hLXJlYWwtdG9rZW4="


class MemorySocket:
    def __init__(self, incoming=()):
        self.incoming = deque(incoming)
        self.sent = []
        self.shutdowns = []
        self.closed = False
        self.timeouts = []

    def recv(self, size):
        item = self.incoming.popleft() if self.incoming else b""
        if isinstance(item, Exception):
            raise item
        if len(item) > size:
            self.incoming.appendleft(item[size:])
        return item[:size]

    def sendall(self, data):
        self.sent.append(data)

    def settimeout(self, value):
        self.timeouts.append(value)

    def shutdown(self, how):
        self.shutdowns.append(how)

    def close(self):
        self.closed = True


def request(method=b"GET", extra=b"", target=b"http://synthetic.invalid/", body=b""):
    return (method + b" " + target + b" HTTP/1.1\r\nHost: synthetic.invalid\r\n"
            + b"Proxy-Authorization: " + AUTH.encode() + b"\r\n" + extra + b"\r\n" + body)


def run_handler(raw, upstream=None, connect_error=None):
    class Handler(bridge.ProxyHandler):
        expected_proxy_authorization = AUTH

    handler = object.__new__(Handler)
    handler.request = MemorySocket([raw])
    handler.connections = []

    def connect(host, port):
        handler.connections.append((host, port))
        if connect_error:
            raise connect_error
        return upstream

    handler.connect_via_socks = connect
    handler.handle()
    return handler, b"".join(handler.request.sent)


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.old = bridge.ProxyHandler.expected_proxy_authorization
        bridge.ProxyHandler.expected_proxy_authorization = AUTH
        self.addCleanup(setattr, bridge.ProxyHandler, "expected_proxy_authorization", self.old)

    def test_matching_ascii_credentials(self):
        self.assertTrue(bridge.ProxyHandler.is_authorized(request()))

    def test_missing_or_wrong_credentials(self):
        for raw in (b"GET / HTTP/1.1\r\n\r\n", request().replace(AUTH.encode(), b"Basic wrong")):
            self.assertFalse(bridge.ProxyHandler.is_authorized(raw))

    def test_empty_expected_credentials_do_not_disable_authentication(self):
        bridge.ProxyHandler.expected_proxy_authorization = ""
        self.assertFalse(bridge.ProxyHandler.is_authorized(request()))

    def test_all_obs_text_bytes_are_denied_without_type_errors(self):
        for value in range(128, 256):
            with self.subTest(value=value):
                raw = request().replace(AUTH.encode(), b"Basic " + bytes([value]))
                self.assertFalse(bridge.ProxyHandler.is_authorized(raw))

    def test_obs_text_is_not_trimmed_into_valid_credentials(self):
        for value in range(128, 256):
            for raw_value in (bytes([value]) + AUTH.encode(), AUTH.encode() + bytes([value])):
                with self.subTest(value=value, prefix=raw_value[0] == value):
                    raw = request().replace(AUTH.encode(), raw_value)
                    self.assertFalse(bridge.ProxyHandler.is_authorized(raw))

    def test_non_ascii_authentication_returns_407_without_connecting(self):
        handler, response = run_handler(request().replace(AUTH.encode(), b"Basic \xff"))
        self.assertTrue(response.startswith(b"HTTP/1.1 407 "))
        self.assertEqual(handler.connections, [])

    def test_duplicate_credentials_are_rejected_before_connecting(self):
        handler, response = run_handler(request(extra=b"Proxy-Authorization: Basic duplicate\r\n"))
        self.assertTrue(response.startswith(b"HTTP/1.1 400 "))
        self.assertEqual(handler.connections, [])


class TunnelTests(unittest.TestCase):
    def test_client_half_close_preserves_late_origin_response(self):
        left = MemorySocket([b"request", b""])
        right = MemorySocket([b"late response", b""])
        events = [([left], [], []), ([left], [], []), ([right], [], []), ([right], [], [])]
        with patch.object(bridge.select, "select", side_effect=events):
            bridge.tunnel(left, right)
        self.assertEqual(right.sent, [b"request"])
        self.assertEqual(left.sent, [b"late response"])
        self.assertEqual(right.shutdowns, [socket.SHUT_WR, socket.SHUT_RDWR])
        self.assertTrue(left.closed and right.closed)

    def test_origin_half_close_preserves_reverse_direction(self):
        left = MemorySocket([b"final client bytes", b""])
        right = MemorySocket([b"response", b""])
        events = [([right], [], []), ([right], [], []), ([left], [], []), ([left], [], [])]
        with patch.object(bridge.select, "select", side_effect=events):
            bridge.tunnel(left, right)
        self.assertEqual(left.sent, [b"response"])
        self.assertEqual(right.sent, [b"final client bytes"])
        self.assertIn(socket.SHUT_WR, left.shutdowns)
        self.assertTrue(left.closed and right.closed)

    def test_closed_read_direction_is_not_polled_again(self):
        left, right = MemorySocket([b""]), MemorySocket([b"last", b""])
        snapshots = []
        events = deque([([left], [], []), ([right], [], []), ([right], [], [])])

        def poll(readers, writers, errors, timeout):
            snapshots.append(tuple(readers))
            return events.popleft()

        with patch.object(bridge.select, "select", side_effect=poll):
            bridge.tunnel(left, right)
        self.assertEqual(snapshots, [(left, right), (right,), (right,)])

    def test_simultaneous_eof_closes_both_sockets(self):
        left, right = MemorySocket([b""]), MemorySocket([b""])
        with patch.object(bridge.select, "select", return_value=([left, right], [], [])):
            bridge.tunnel(left, right)
        self.assertTrue(left.closed and right.closed)

    def test_idle_and_select_error_cleanup(self):
        for errored in (False, True):
            with self.subTest(errored=errored):
                left, right = MemorySocket(), MemorySocket()
                with patch.object(bridge.select, "select", return_value=([], [], [right] if errored else [])):
                    bridge.tunnel(left, right)
                self.assertTrue(left.closed and right.closed)

    def test_receive_failure_still_closes_both_sockets(self):
        left, right = MemorySocket([ConnectionResetError("synthetic")]), MemorySocket()
        with patch.object(bridge.select, "select", return_value=([left], [], [])):
            with self.assertRaises(ConnectionResetError):
                bridge.tunnel(left, right)
        self.assertTrue(left.closed and right.closed)


class ResponseFailureTests(unittest.TestCase):
    RESPONSE = b"HTTP/1.1 200 OK\r\nContent-Length: 20\r\n\r\npartial"

    def test_partial_response_reset_does_not_append_a_second_status(self):
        origin = MemorySocket([self.RESPONSE, ConnectionResetError("synthetic")])
        _, response = run_handler(request(), origin)
        self.assertEqual(response, self.RESPONSE)
        self.assertTrue(origin.closed)

    def test_partial_response_timeout_does_not_append_a_second_status(self):
        origin = MemorySocket([self.RESPONSE, socket.timeout("synthetic")])
        _, response = run_handler(request(), origin)
        self.assertEqual(response, self.RESPONSE)
        self.assertTrue(origin.closed)

    def test_started_response_never_appends_header_error(self):
        origin = MemorySocket([self.RESPONSE, bridge.HeaderError("synthetic")])
        _, response = run_handler(request(), origin)
        self.assertEqual(response, self.RESPONSE)

    def test_failure_before_any_response_still_returns_502(self):
        for error in (socket.timeout("synthetic"), ConnectionResetError("synthetic")):
            with self.subTest(error=type(error).__name__):
                _, response = run_handler(request(), MemorySocket([error]))
                self.assertTrue(response.startswith(b"HTTP/1.1 502 "))

    def test_connection_failure_still_returns_502(self):
        _, response = run_handler(request(), connect_error=OSError("synthetic private text"))
        self.assertTrue(response.startswith(b"HTTP/1.1 502 "))
        self.assertNotIn(b"private text", response)

    def test_connect_tunnel_error_does_not_append_http_error(self):
        origin = MemorySocket()
        with patch.object(bridge, "tunnel", side_effect=ConnectionResetError("synthetic")):
            _, response = run_handler(request(method=b"CONNECT", target=b"synthetic.invalid:443"), origin)
        self.assertTrue(response.startswith(b"HTTP/1.1 200 Connection Established"))
        self.assertEqual(response.count(b"HTTP/1.1"), 1)
        self.assertTrue(origin.closed)

    def test_continue_is_not_a_final_response(self):
        origin = MemorySocket([ConnectionResetError("synthetic")])
        _, response = run_handler(request(method=b"POST", extra=b"Expect: 100-continue\r\nContent-Length: 0\r\n"), origin)
        self.assertTrue(response.startswith(b"HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 502 "))

    def test_origin_response_body_is_byte_preserving(self):
        body = bytes(range(256)) * 3
        wire = b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n" + body
        origin = MemorySocket([wire[:7], wire[7:70], wire[70:], b""])
        _, response = run_handler(request(), origin)
        self.assertEqual(response, wire)


class FramingTests(unittest.TestCase):
    def test_content_length_does_not_forward_pipelined_request(self):
        origin = MemorySocket([b"HTTP/1.1 204 No Content\r\n\r\n", b""])
        raw = request(method=b"POST", extra=b"Content-Length: 3\r\n", body=b"abcGET /secret HTTP/1.1\r\n\r\n")
        _, response = run_handler(raw, origin)
        wire = b"".join(origin.sent)
        self.assertTrue(wire.endswith(b"\r\n\r\nabc"))
        self.assertNotIn(b"/secret", wire)
        self.assertNotIn(AUTH.encode(), wire)
        self.assertTrue(response.startswith(b"HTTP/1.1 204 "))

    def test_chunked_body_stops_at_terminator(self):
        origin = MemorySocket([b"HTTP/1.1 204 No Content\r\n\r\n", b""])
        body = b"3;ignored=yes\r\nabc\r\n0\r\n\r\nGET /secret HTTP/1.1\r\n\r\n"
        run_handler(request(method=b"POST", extra=b"Transfer-Encoding: chunked\r\n", body=body), origin)
        wire = b"".join(origin.sent)
        self.assertTrue(wire.endswith(b"3\r\nabc\r\n0\r\n\r\n"))
        self.assertNotIn(b"/secret", wire)

    def test_ambiguous_framing_is_rejected_without_connecting(self):
        handler, response = run_handler(request(extra=b"Content-Length: 0\r\nTransfer-Encoding: chunked\r\n"))
        self.assertEqual(handler.connections, [])
        self.assertTrue(response.startswith(b"HTTP/1.1 400 "))

    def test_connection_header_cannot_hide_framing(self):
        handler, _ = run_handler(request(extra=b"Content-Length: 0\r\nConnection: Content-Length\r\n"))
        self.assertEqual(handler.connections, [])

    def test_tls_absolute_url_is_not_sent_as_plaintext(self):
        handler, _ = run_handler(request(target=b"https://synthetic.invalid/"))
        self.assertEqual(handler.connections, [])


if __name__ == "__main__":
    unittest.main()
