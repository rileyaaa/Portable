"""Loopback TCP integration for the bridge, with a synthetic origin, not SOCKS.

The socket transport and HTTP/CONNECT handling are real. Only upstream routing
is substituted to forbid external traffic. No credentials, DNS, paid API, or
Windows-specific launcher behavior is exercised.
"""
import os
import socket
import socketserver
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

from test_socks_http_bridge import AUTH, ROOT, bridge, request


def receive_all(sock):
    chunks = []
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def receive_headers(sock):
    data = bytearray()
    while b"\r\n\r\n" not in data:
        part = sock.recv(4096)
        if not part:
            raise EOFError("synthetic peer ended before headers")
        data.extend(part)
        if len(data) > 65536:
            raise ValueError("synthetic headers too large")
    return bytes(data).split(b"\r\n\r\n", 1)


class OriginServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request, client_address):
        self.errors.append(sys.exc_info()[1])


class LoopbackBridgeTests(unittest.TestCase):
    def setUp(self):
        self.origin_data = []
        self.connections = []
        self.completed = threading.Event()
        self.release_origin = threading.Event()
        self.scenario = lambda sock: None
        owner = self

        class OriginHandler(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.settimeout(3)
                try:
                    owner.scenario(self.request)
                finally:
                    owner.completed.set()

        self.origin = OriginServer(("127.0.0.1", 0), OriginHandler)
        self.origin.errors = []
        self.origin_thread = threading.Thread(target=self.origin.serve_forever,
                                              kwargs={"poll_interval": 0.01}, daemon=True)
        self.origin_thread.start()

        class Handler(bridge.ProxyHandler):
            expected_proxy_authorization = AUTH

            def connect_via_socks(self, host, port):
                if (host, port) not in (("synthetic.invalid", 80), ("synthetic.invalid", 443)):
                    raise ValueError("test forbids external destinations")
                owner.connections.append((host, port))
                return socket.create_connection(owner.origin.server_address, timeout=3)

        self.proxy = bridge.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self.proxy_thread = threading.Thread(target=self.proxy.serve_forever,
                                             kwargs={"poll_interval": 0.01}, daemon=True)
        self.proxy_thread.start()
        self.addCleanup(self.close_servers)

    def close_servers(self):
        self.release_origin.set()
        for server in (self.proxy, self.origin):
            server.shutdown()
            server.server_close()
        for thread in (self.proxy_thread, self.origin_thread):
            thread.join(3)
            self.assertFalse(thread.is_alive())
        if self.connections:
            self.assertTrue(self.completed.wait(3), "synthetic origin leaked a worker")
        self.assertEqual(self.origin.errors, [])

    def client(self):
        return socket.create_connection(self.proxy.server_address, timeout=3)

    def test_connect_client_half_close_keeps_large_response(self):
        sent = bytes(range(256)) * 1025
        reply = b"late-response:" + sent[::-1]

        def scenario(sock):
            self.origin_data.append(receive_all(sock))
            sock.sendall(reply)
            sock.shutdown(socket.SHUT_WR)

        self.scenario = scenario
        with self.client() as client:
            client.sendall(request(method=b"CONNECT", target=b"synthetic.invalid:443"))
            head, extra = receive_headers(client)
            self.assertTrue(head.startswith(b"HTTP/1.1 200 "))
            client.sendall(sent)
            client.shutdown(socket.SHUT_WR)
            self.assertEqual(extra + receive_all(client), reply)
        self.assertTrue(self.completed.wait(3))
        self.assertEqual(self.origin_data, [sent])

    def test_connect_origin_half_close_keeps_client_upload(self):
        sent = b"upload-after-origin-eof" * 10000

        def scenario(sock):
            sock.sendall(b"ready")
            sock.shutdown(socket.SHUT_WR)
            self.origin_data.append(receive_all(sock))

        self.scenario = scenario
        with self.client() as client:
            client.sendall(request(method=b"CONNECT", target=b"synthetic.invalid:443"))
            _, extra = receive_headers(client)
            self.assertEqual(extra + receive_all(client), b"ready")
            client.sendall(sent)
            client.shutdown(socket.SHUT_WR)
        self.assertTrue(self.completed.wait(3))
        self.assertEqual(self.origin_data, [sent])

    def test_connect_prefetched_data_is_preserved(self):
        def scenario(sock):
            data = receive_all(sock)
            self.origin_data.append(data)
            sock.sendall(b"ACK:" + data)

        self.scenario = scenario
        with self.client() as client:
            client.sendall(request(method=b"CONNECT", target=b"synthetic.invalid:443", body=b"prefetched"))
            _, extra = receive_headers(client)
            client.shutdown(socket.SHUT_WR)
            self.assertEqual(extra + receive_all(client), b"ACK:prefetched")
        self.assertTrue(self.completed.wait(3))
        self.assertEqual(self.origin_data, [b"prefetched"])

    def test_plain_http_strips_proxy_secret_and_blocks_pipeline(self):
        def scenario(sock):
            head, body = receive_headers(sock)
            while len(body) < 5:
                body += sock.recv(1024)
            self.origin_data.append((head, body))
            sock.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")

        self.scenario = scenario
        raw = request(method=b"POST", target=b"http://synthetic.invalid/api?q=1",
                      extra=b"Content-Length: 5\r\n", body=b"helloGET /private HTTP/1.1\r\n\r\n")
        with self.client() as client:
            client.sendall(raw)
            self.assertTrue(receive_all(client).endswith(b"\r\n\r\nOK"))
        self.assertTrue(self.completed.wait(3))
        head, body = self.origin_data[0]
        self.assertTrue(head.startswith(b"POST /api?q=1 HTTP/1.1"))
        self.assertNotIn(b"Proxy-Authorization", head)
        self.assertNotIn(AUTH.encode(), head)
        self.assertIn(b"Connection: close", head)
        self.assertEqual(body, b"hello")

    def test_chunked_body_is_framed_without_forwarding_next_request(self):
        def scenario(sock):
            head, body = receive_headers(sock)
            while not body.endswith(b"0\r\n\r\n"):
                part = sock.recv(1024)
                if not part:
                    raise EOFError("missing chunk terminator")
                body += part
            self.origin_data.append((head, body))
            sock.sendall(b"HTTP/1.1 204 No Content\r\n\r\n")

        self.scenario = scenario
        with self.client() as client:
            client.sendall(request(method=b"POST", extra=b"Transfer-Encoding: chunked\r\n",
                                   body=b"3;ext=yes\r\nabc\r\n0\r\n\r\nGET /private HTTP/1.1\r\n\r\n"))
            self.assertTrue(receive_all(client).startswith(b"HTTP/1.1 204 "))
        self.assertTrue(self.completed.wait(3))
        self.assertEqual(self.origin_data[0][1], b"3\r\nabc\r\n0\r\n\r\n")

    def test_continue_handshake_waits_for_client_body(self):
        def scenario(sock):
            _, body = receive_headers(sock)
            while len(body) < 4:
                body += sock.recv(1024)
            self.origin_data.append(body)
            sock.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")

        self.scenario = scenario
        with self.client() as client:
            client.sendall(request(method=b"POST", extra=b"Expect: 100-continue\r\nContent-Length: 4\r\n"))
            head, extra = receive_headers(client)
            self.assertEqual(head, b"HTTP/1.1 100 Continue")
            self.assertEqual(extra, b"")
            client.sendall(b"data")
            self.assertTrue(receive_all(client).startswith(b"HTTP/1.1 200 "))
        self.assertTrue(self.completed.wait(3))
        self.assertEqual(self.origin_data, [b"data"])

    def test_partial_origin_response_timeout_closes_without_appending_502(self):
        partial = b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\npartial"

        def scenario(sock):
            receive_headers(sock)
            sock.sendall(partial)
            self.release_origin.wait(3)

        self.scenario = scenario
        with patch.object(bridge, "IDLE_TIMEOUT", 0.2):
            with self.client() as client:
                client.sendall(request())
                self.assertEqual(receive_all(client), partial)
        self.release_origin.set()

    def test_invalid_credentials_never_connect_to_origin(self):
        for auth in (b"Basic wrong", b"Basic \xff", AUTH.encode() + b"\xa0"):
            with self.subTest(auth_kind=auth[-1]):
                with self.client() as client:
                    client.sendall(request().replace(AUTH.encode(), auth))
                    response = receive_all(client)
                    self.assertTrue(response.startswith(b"HTTP/1.1 407 "))
        self.assertEqual(self.connections, [])

    def test_relay_in_a_separate_process_preserves_half_close(self):
        # The child loads the real bridge file. Only SOCKS routing is replaced
        # with this test's bound loopback address; it cannot dial the Internet.
        child = r'''
import importlib.util, socket, sys, types
try:
    import socks
except ImportError:
    sys.modules['socks'] = types.SimpleNamespace(socksocket=socket.socket)
spec=importlib.util.spec_from_file_location('bridge_child',sys.argv[1])
b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
class H(b.ProxyHandler):
    expected_proxy_authorization=sys.argv[3]
    def connect_via_socks(self,host,port):
        if (host,port)!=('synthetic.invalid',443): raise ValueError('forbidden')
        return socket.create_connection(('127.0.0.1',int(sys.argv[2])),timeout=3)
s=b.ThreadingTCPServer(('127.0.0.1',0),H)
print(s.server_address[1],flush=True)
s.serve_forever(poll_interval=0.01)
'''

        def scenario(sock):
            data = receive_all(sock)
            self.origin_data.append(data)
            sock.sendall(b"child-reply:" + data)

        self.scenario = scenario
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        proc = subprocess.Popen([sys.executable, "-B", "-c", child,
                                 str(ROOT / "tool/socks-http-bridge.py"),
                                 str(self.origin.server_address[1]), AUTH],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=environment)
        line = []
        ready = threading.Event()

        def read_port():
            line.append(proc.stdout.readline())
            ready.set()

        reader = threading.Thread(target=read_port, daemon=True)
        reader.start()
        try:
            self.assertTrue(ready.wait(5), "child did not start")
            self.assertTrue(line and line[0].strip().isdigit(), "child did not report a port")
            with socket.create_connection(("127.0.0.1", int(line[0])), timeout=3) as client:
                client.sendall(request(method=b"CONNECT", target=b"synthetic.invalid:443"))
                _, extra = receive_headers(client)
                client.sendall(b"child-query")
                client.shutdown(socket.SHUT_WR)
                self.assertEqual(extra + receive_all(client), b"child-reply:child-query")
            self.assertTrue(self.completed.wait(3))
            self.assertEqual(self.origin_data, [b"child-query"])
        finally:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(5)
            reader.join(3)
            proc.stdout.close()
            proc.stderr.close()


if __name__ == "__main__":
    unittest.main()
