"""Seeded protocol checks and real loopback TCP stress; no external upstreams.

PySocks routing is replaced by the existing local-origin fixture, not asserted
as tested. h11 is the independently implemented HTTP parser already pinned by
the project. Vary CODEX_AUDIT_SEED to repeat with different fragmentation.
"""
from concurrent.futures import ThreadPoolExecutor
import os
import random
import socket
import threading
import time
import unittest
from unittest.mock import patch

import h11
from test_socks_http_bridge import AUTH, MemorySocket, bridge, request, run_handler
import test_socks_http_bridge_network as network_fixture
from test_socks_http_bridge_network import receive_all, receive_headers

SEED = int(os.environ.get("CODEX_AUDIT_SEED", "1660"))
OK = b"HTTP/1.1 204 No Content\r\n\r\n"


def fragments(data, rng, maximum=23):
    chunks = []
    pos = 0
    while pos < len(data):
        size = rng.randint(1, maximum)
        chunks.append(data[pos:pos + size])
        pos += size
    return chunks


class SeededProtocolTests(unittest.TestCase):
    def test_300_valid_and_300_invalid_ports(self):
        rng = random.Random(SEED)
        for i in range(300):
            port = rng.randint(1, 65535)
            target = "host%d.invalid:%d" % (i, port)
            self.assertEqual(bridge.parse_host_port(target, 80), ("host%d.invalid" % i, port))
            bad = "host.invalid:" + rng.choice(("+", "_", "\u0661")) + str(port)
            with self.assertRaises(bridge.HeaderError):
                bridge.parse_host_port(bad, 80)

    def test_100_fragmented_chunked_bodies_preserve_exact_bytes(self):
        rng = random.Random(SEED + 1)
        for case in range(100):
            body = rng.randbytes(rng.randint(0, 512))
            pieces = fragments(body, rng)
            wire = b"".join(("%x;x=1\r\n" % len(p)).encode() + p + b"\r\n" for p in pieces)
            canonical = b"".join(("%x\r\n" % len(p)).encode() + p + b"\r\n" for p in pieces)
            wire += b"0\r\n\r\nGET /pipeline HTTP/1.1\r\n\r\n"
            out = MemorySocket()
            bridge.RequestBody(MemorySocket(fragments(wire, rng)), b"").chunks(out)
            self.assertEqual(b"".join(out.sent), canonical + b"0\r\n\r\n", case)

    def test_100_fragmented_fixed_bodies_do_not_include_pipeline(self):
        rng = random.Random(SEED + 2)
        for _ in range(100):
            body = rng.randbytes(rng.randint(0, 1024))
            wire = body + b"GET /forbidden HTTP/1.1\r\n\r\n"
            out = MemorySocket()
            bridge.RequestBody(MemorySocket(fragments(wire, rng)), b"").forward(out, len(body))
            self.assertEqual(b"".join(out.sent), body)

    def test_100_method_tokens_roundtrip_through_independent_h11_parser(self):
        rng = random.Random(SEED + 3)
        alphabet = b"!#$%&'*+-.^_`|~0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        for i in range(100):
            method = bytes(rng.choice(alphabet) for _ in range(rng.randint(1, 20)))
            origin = MemorySocket([OK])
            _, response = run_handler(request(method=method), origin)
            self.assertEqual(response, OK, method)
            independent = h11.Connection(h11.SERVER)
            independent.receive_data(b"".join(origin.sent))
            event = independent.next_event()
            self.assertIsInstance(event, h11.Request)
            self.assertEqual(event.method, method)
            self.assertEqual(event.target, b"/")

    def test_500_malformed_header_inputs_do_not_dial_or_leak(self):
        rng = random.Random(SEED + 4)
        controls = tuple(range(0, 9)) + tuple(range(10, 32)) + (127,)
        for i in range(500):
            control = bytes([rng.choice(controls)])
            extra = b"X-Synthetic: prefix" + control + b"suffix\r\n"
            handler, response = run_handler(request(extra=extra))
            self.assertEqual(handler.connections, [], i)
            self.assertTrue(response.startswith(b"HTTP/1.1 400 "), response)
            self.assertNotIn(AUTH.encode(), response)
            self.assertEqual(response.count(b"HTTP/1.1 "), 1)

    def test_error_statuses_are_parseable_by_h11(self):
        cases = (
            (request(extra=b"Broken\r\n"), None, 400),
            (request().replace(AUTH.encode(), b"Basic wrong"), None, 407),
            (request(extra=b"Content-Length: 999999999\r\n"), None, 413),
            (request(), MemorySocket(), 502),
        )
        for raw, upstream, expected in cases:
            _, wire = run_handler(raw, upstream)
            client = h11.Connection(h11.CLIENT)
            client.send(h11.Request(method=b"GET", target=b"/", headers=[(b"Host", b"synthetic.invalid")]))
            client.send(h11.EndOfMessage())
            client.receive_data(wire)
            self.assertEqual(client.next_event().status_code, expected)
            client.receive_data(b"")
            self.assertIsInstance(client.next_event(), h11.EndOfMessage)


class LiveBoundaryTests(unittest.TestCase):
    # Reuse only lifecycle helpers, not inherited test methods/counts.
    setUp = network_fixture.LoopbackBridgeTests.setUp
    close_servers = network_fixture.LoopbackBridgeTests.close_servers
    client = network_fixture.LoopbackBridgeTests.client

    def test_concurrent_requests_do_not_mix_response_or_credentials(self):
        count = 24
        completed = []
        lock = threading.Lock()

        def scenario(sock):
            head, body = receive_headers(sock)
            self.assertEqual(body, b"")
            self.assertNotIn(AUTH.encode(), head)
            path = head.split(b" ")[1]
            payload = b"echo:" + path
            wire = b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(payload)).encode() + b"\r\n\r\n" + payload
            for part in fragments(wire, random.Random(SEED + len(path)), 7):
                sock.sendall(part)
            with lock:
                completed.append(path)

        self.scenario = scenario

        def exchange(i):
            raw = request(target=("http://synthetic.invalid/request-%d" % i).encode())
            raw = raw.replace(b"Basic ", b"bAsIc   ")
            with self.client() as client:
                for piece in fragments(raw, random.Random(SEED + i), 13):
                    client.sendall(piece)
                response = receive_all(client)
            self.assertEqual(response.split(b"\r\n\r\n", 1)[1], ("echo:/request-%d" % i).encode())

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(exchange, range(count)))
        self.assertEqual(len(completed), count)
        self.assertEqual(len(set(completed)), count)
        self.assertEqual(len(self.connections), count)

    def test_independent_h11_client_and_server(self):
        payload = b"synthetic-response"

        def scenario(sock):
            head, body = receive_headers(sock)
            parser = h11.Connection(h11.SERVER)
            parser.receive_data(head + b"\r\n\r\n" + body)
            event = parser.next_event()
            self.assertEqual(event.method, b"M-SEARCH")
            self.assertEqual(event.target, b"/protocol?q=1")
            self.assertIsInstance(parser.next_event(), h11.EndOfMessage)
            wire = parser.send(h11.Response(status_code=200, headers=[(b"Content-Length", str(len(payload)).encode())]))
            wire += parser.send(h11.Data(data=payload)) + parser.send(h11.EndOfMessage())
            sock.sendall(wire)

        self.scenario = scenario
        peer = h11.Connection(h11.CLIENT)
        wire = peer.send(h11.Request(method=b"M-SEARCH", target=b"http://synthetic.invalid/protocol?q=1",
                                    headers=[(b"Host", b"synthetic.invalid"), (b"Proxy-Authorization", AUTH.encode())]))
        wire += peer.send(h11.EndOfMessage())
        with self.client() as client:
            client.sendall(wire)
            peer.receive_data(receive_all(client))
        self.assertEqual(peer.next_event().status_code, 200)
        self.assertEqual(peer.next_event().data, payload)
        self.assertIsInstance(peer.next_event(), h11.EndOfMessage)

    def test_origin_eof_before_response_gets_502(self):
        self.scenario = lambda sock: receive_headers(sock)
        with self.client() as client:
            client.sendall(request())
            self.assertTrue(receive_all(client).startswith(b"HTTP/1.1 502 "))

    def test_client_header_timeout_is_408_without_upstream(self):
        with patch.object(bridge, "HEADER_TIMEOUT", 0.12):
            with self.client() as client:
                client.sendall(b"GET / HTTP/1.1\r\n")
                self.assertTrue(receive_all(client).startswith(b"HTTP/1.1 408 "))
        self.assertEqual(self.connections, [])

    def test_full_header_limit_without_terminator_is_431(self):
        prefix = b"GET / HTTP/1.1\r\nX: "
        wire = prefix + b"x" * (bridge.MAX_HEADER_BYTES - len(prefix))
        with self.client() as client:
            client.sendall(wire)
            self.assertTrue(receive_all(client).startswith(b"HTTP/1.1 431 "))
        self.assertEqual(self.connections, [])

    def test_incomplete_body_timeout_closes_origin_and_returns_408(self):
        def scenario(sock):
            head, body = receive_headers(sock)
            self.origin_data.append(body + receive_all(sock))
        self.scenario = scenario
        with patch.object(bridge, "BODY_TIMEOUT", 0.12):
            with self.client() as client:
                client.sendall(request(method=b"POST", extra=b"Content-Length: 6\r\n", body=b"abc"))
                self.assertTrue(receive_all(client).startswith(b"HTTP/1.1 408 "))
        self.assertTrue(self.completed.wait(3))
        self.assertEqual(self.origin_data, [b""])  # Incomplete exact-sized block is not forwarded.

    def test_http10_chunked_is_rejected_without_upstream(self):
        with self.client() as client:
            wire = request(method=b"POST", extra=b"Transfer-Encoding: chunked\r\n", body=b"0\r\n\r\n")
            client.sendall(wire.replace(b"HTTP/1.1", b"HTTP/1.0"))
            self.assertTrue(receive_all(client).startswith(b"HTTP/1.1 400 "))
        self.assertEqual(self.connections, [])

    def test_malformed_connect_target_never_creates_upstream(self):
        for target in (b"host:+80", b"host:1_23", b"[localhost]:443", b"user@host:443"):
            with self.client() as client:
                client.sendall(request(method=b"CONNECT", target=target))
                self.assertTrue(receive_all(client).startswith(b"HTTP/1.1 400 "))
        self.assertEqual(self.connections, [])

    def test_invalid_auth_under_load_does_not_use_upstream(self):
        def exchange(i):
            with self.client() as client:
                client.sendall(request().replace(AUTH.encode(), b"Basic deliberately-wrong"))
                self.assertTrue(receive_all(client).startswith(b"HTTP/1.1 407 "))
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(exchange, range(18)))
        self.assertEqual(self.connections, [])

    def test_binary_connect_fragmentation_keeps_both_directions(self):
        rng = random.Random(SEED + 7)
        payload = rng.randbytes(100000 + rng.randint(0, 20000))

        def scenario(sock):
            got = receive_all(sock)
            self.origin_data.append(got)
            for piece in fragments(got[::-1], random.Random(SEED + 8), 4096):
                sock.sendall(piece)
        self.scenario = scenario
        with self.client() as client:
            client.sendall(request(method=b"CONNECT", target=b"synthetic.invalid:443"))
            _, extra = receive_headers(client)
            for piece in fragments(payload, random.Random(SEED + 9), 4096):
                client.sendall(piece)
            client.shutdown(socket.SHUT_WR)
            self.assertEqual(extra + receive_all(client), payload[::-1])
        self.assertTrue(self.completed.wait(3))
        self.assertEqual(self.origin_data, [payload])


if __name__ == "__main__":
    unittest.main()
