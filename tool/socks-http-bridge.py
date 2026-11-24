import argparse
import base64
import hmac
import ipaddress
import os
import re
import select
import socket
import socketserver
import threading
import time
from urllib.parse import urlsplit

import socks


BUFFER_SIZE = 65536
MAX_HEADER_BYTES = 65536
HEADER_TIMEOUT = 10.0
IO_TIMEOUT = 30.0
IDLE_TIMEOUT = 60.0
BODY_TIMEOUT = 180.0
MAX_BODY_BYTES = 128 * 1024 * 1024
MAX_WORKERS = 64
HEADER_NAME = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+")


class HeaderError(ValueError):
    def __init__(self, message: str, status: bytes = b"400 Bad Request"):
        super().__init__(message)
        self.status = status


def parse_host_port(target: str, default_port: int) -> tuple[str, int]:
    # Parse HTTP authority, not Python's more permissive integer/whitespace
    # syntax. Reject malformed targets before any upstream DNS or connection.
    if (not target or not target.isascii()
            or any(ord(ch) <= 32 or ord(ch) == 127 for ch in target)
            or any(ch in target for ch in "/\\?#@%")):
        raise HeaderError("invalid target")

    port_text = None
    if target.startswith("["):
        closing = target.find("]")
        if closing < 0:
            raise HeaderError("invalid bracketed IPv6 target")
        host = target[1:closing]
        try:
            ipaddress.IPv6Address(host)
        except ValueError as exc:
            raise HeaderError("invalid bracketed IPv6 target") from exc
        suffix = target[closing + 1:]
        if suffix:
            if not suffix.startswith(":") or not suffix[1:]:
                raise HeaderError("invalid bracketed IPv6 port")
            port_text = suffix[1:]
    else:
        if target.count(":") > 1:
            raise HeaderError("IPv6 authority requires brackets")
        host, separator, candidate_port = target.partition(":")
        if separator:
            port_text = candidate_port
        if not re.fullmatch(r"[A-Za-z0-9._~!$&'()*+,;=-]+", host):
            raise HeaderError("invalid target host")

    port = default_port
    if port_text is not None:
        if not re.fullmatch(r"[0-9]+", port_text):
            raise HeaderError("invalid target port")
        significant = port_text.lstrip("0") or "0"
        if len(significant) > 5:
            raise HeaderError("invalid target port")
        port = int(significant)
    if not host or len(host) > 253 or not 1 <= port <= 65535:
        raise HeaderError("invalid target host or port")
    return host, port


def validate_loopback_host(host: str) -> str:
    host = host.strip()
    if host.lower() == "localhost":
        return "localhost"
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("listen host must be localhost or a loopback IP") from exc
    if not address.is_loopback:
        raise argparse.ArgumentTypeError("listen host must be loopback-only")
    # Keep the listener surface intentionally narrow even though 127/8 is loopback.
    if str(address) not in {"127.0.0.1", "::1"}:
        raise argparse.ArgumentTypeError("listen host must be 127.0.0.1, ::1, or localhost")
    return str(address)


def valid_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def validate_upstream_host(host: str) -> str:
    host = host.strip()
    if not host or len(host) > 253 or any(ch.isspace() for ch in host):
        raise argparse.ArgumentTypeError("invalid SOCKS host")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in host):
        raise argparse.ArgumentTypeError("invalid SOCKS host")
    # The launcher accepts IPv6 URI spelling as well as a bare address.
    # PySocks passes the upstream host to a socket, not to a URI parser.
    if ":" in host or "[" in host or "]" in host:
        candidate = host[1:-1] if host.startswith("[") and host.endswith("]") else host
        try:
            ipaddress.IPv6Address(candidate)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("invalid SOCKS IPv6 host") from exc
        return candidate
    return host


def get_header_value(header_blob: bytes, name: str) -> str:
    wanted = name.lower()
    head = header_blob.split(b"\r\n\r\n", 1)[0]
    for raw_line in head.split(b"\r\n")[1:]:
        line = raw_line.decode("latin-1", "replace")
        key, sep, value = line.partition(":")
        if sep and key.strip().lower() == wanted:
            return value.strip(" \t")
    return ""


def recv_until_headers(sock: socket.socket, limit: int = MAX_HEADER_BYTES) -> bytes:
    data = bytearray()
    deadline = time.monotonic() + HEADER_TIMEOUT
    while b"\r\n\r\n" not in data:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise HeaderError("request headers timed out", b"408 Request Timeout")
        if len(data) >= limit:
            raise HeaderError("request headers too large", b"431 Request Header Fields Too Large")
        sock.settimeout(min(IO_TIMEOUT, remaining))
        try:
            chunk = sock.recv(min(4096, limit - len(data)))
        except socket.timeout as exc:
            raise HeaderError("request headers timed out", b"408 Request Timeout") from exc
        if not chunk:
            raise HeaderError("incomplete request headers")
        data.extend(chunk)
    return bytes(data)


def parse_headers(header_blob: bytes) -> list[tuple[bytes, bytes]]:
    result = []
    seen = set()
    head = header_blob.split(b"\r\n\r\n", 1)[0]
    for line in head.split(b"\r\n")[1:]:
        key, separator, value = line.partition(b":")
        if not separator or not HEADER_NAME.fullmatch(key):
            raise HeaderError("invalid header name")
        value = value.strip(b" \t")
        if any(c < 32 and c != 9 or c == 127 for c in value):
            raise HeaderError("invalid header value")
        name = key.lower()
        if name in {b"host", b"content-length", b"transfer-encoding", b"proxy-authorization", b"expect"}:
            if name in seen:
                raise HeaderError("duplicate framing or authentication header")
            seen.add(name)
        result.append((key, value))
    return result


class RequestBody:
    """Consume only this request's body, never a pipelined next request."""
    def __init__(self, sock: socket.socket, prefetched: bytes):
        self.sock = sock
        self.pending = bytearray(prefetched)
        self.deadline = time.monotonic() + BODY_TIMEOUT

    def remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise HeaderError("request body timed out", b"408 Request Timeout")
        return remaining

    def send(self, upstream: socket.socket, data: bytes) -> None:
        upstream.settimeout(min(IO_TIMEOUT, self.remaining()))
        upstream.sendall(data)
        self.remaining()

    def receive(self) -> None:
        self.sock.settimeout(min(IO_TIMEOUT, self.remaining()))
        try:
            part = self.sock.recv(BUFFER_SIZE)
        except socket.timeout as exc:
            raise HeaderError("request body timed out", b"408 Request Timeout") from exc
        if not part:
            raise HeaderError("incomplete request body")
        self.pending.extend(part)

    def exact(self, count: int) -> bytes:
        self.remaining()
        while len(self.pending) < count:
            self.receive()
        result = bytes(self.pending[:count])
        del self.pending[:count]
        return result

    def line(self, limit: int = 8192) -> bytes:
        while b"\r\n" not in self.pending:
            if len(self.pending) > limit:
                raise HeaderError("body line too large")
            self.receive()
        end = self.pending.index(b"\r\n")
        if end > limit:
            raise HeaderError("body line too large")
        return self.exact(end + 2)[:-2]

    def forward(self, upstream: socket.socket, count: int) -> None:
        if count < 0 or count > MAX_BODY_BYTES:
            raise HeaderError("request body too large", b"413 Content Too Large")
        while count:
            chunk = self.exact(min(count, BUFFER_SIZE))
            self.send(upstream, chunk)
            count -= len(chunk)

    def chunks(self, upstream: socket.socket) -> None:
        total = 0
        while True:
            line = self.line()
            size_text = line.split(b";", 1)[0]
            if not re.fullmatch(rb"[0-9A-Fa-f]{1,16}", size_text):
                raise HeaderError("invalid chunk length")
            size = int(size_text, 16)
            total += size
            if total > MAX_BODY_BYTES:
                raise HeaderError("request body too large", b"413 Content Too Large")
            if size == 0:
                # Do not allow a trailer to reintroduce a stripped credential or
                # framing header. Non-empty trailers are explicitly unsupported.
                if self.line():
                    raise HeaderError("request trailers are not supported")
                self.send(upstream, b"0\r\n\r\n")
                return
            self.send(upstream, f"{size:x}\r\n".encode("ascii"))
            self.forward(upstream, size)
            if self.exact(2) != b"\r\n":
                raise HeaderError("invalid chunk terminator")
            self.send(upstream, b"\r\n")


def strip_proxy_headers(header_blob: bytes) -> bytes:
    head, body = header_blob.split(b"\r\n\r\n", 1)
    lines = head.split(b"\r\n")
    kept = [lines[0]]
    for raw_line in lines[1:]:
        key, sep, _ = raw_line.partition(b":")
        if sep and key.strip().lower() in {b"proxy-authorization", b"proxy-connection"}:
            continue
        kept.append(raw_line)
    return b"\r\n".join(kept) + b"\r\n\r\n" + body


def tunnel(left: socket.socket, right: socket.socket) -> None:
    sockets = [left, right]
    receiving = list(sockets)
    try:
        while receiving:
            readable, _, errored = select.select(receiving, [], sockets, IDLE_TIMEOUT)
            if errored:
                return
            if not readable:
                return
            for src in readable:
                dst = right if src is left else left
                data = src.recv(BUFFER_SIZE)
                if not data:
                    # EOF closes one direction only. The other peer may still
                    # owe a response after receiving this request's final byte.
                    receiving.remove(src)
                    dst.shutdown(socket.SHUT_WR)
                else:
                    dst.sendall(data)
    finally:
        for sock in sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                sock.close()
            except Exception:
                pass


class ThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 32

    def __init__(self, *args, **kwargs):
        self.worker_slots = threading.BoundedSemaphore(MAX_WORKERS)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self.worker_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.worker_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.worker_slots.release()


class ThreadingTCPServerV6(ThreadingTCPServer):
    address_family = socket.AF_INET6


class ProxyHandler(socketserver.BaseRequestHandler):
    socks_host: str = "127.0.0.1"
    socks_port: int = 10808
    socks_rdns: bool = True
    expected_proxy_authorization: str = ""

    @classmethod
    def is_authorized(cls, header_blob: bytes) -> bool:
        actual = get_header_value(header_blob, "Proxy-Authorization")
        expected = cls.expected_proxy_authorization
        # HTTP field values may contain obs-text; Basic credentials may not.
        # Reject them as authentication failures rather than raising TypeError.
        if not expected or not actual.isascii():
            return False
        scheme, separator, credentials = actual.partition(" ")
        expected_scheme, expected_separator, expected_credentials = expected.partition(" ")
        # Only the scheme is case-insensitive. Base64 credential bytes are not.
        return (scheme.lower() == expected_scheme.lower() == "basic"
                and bool(separator) and bool(expected_separator)
                and hmac.compare_digest(credentials.lstrip(" "), expected_credentials))

    def connect_via_socks(self, host: str, port: int) -> socks.socksocket:
        # The bundled PySocks socket defaults to AF_INET. Explicit IPv6
        # proxy literals need AF_INET6; keep the existing IPv4/DNS behavior
        # and single connection attempt (no new retry or timeout policy).
        upstream = (socks.socksocket(socket.AF_INET6)
                    if ":" in self.socks_host else socks.socksocket())
        upstream.set_proxy(
            socks.SOCKS5,
            self.socks_host,
            self.socks_port,
            rdns=self.socks_rdns,
        )
        upstream.settimeout(IO_TIMEOUT)
        try:
            upstream.connect((host, port))
            return upstream
        except BaseException:
            upstream.close()
            raise

    def handle_connect(self, target: str, prefetched: bytes = b"") -> None:
        host, port = parse_host_port(target, 443)
        upstream = self.connect_via_socks(host, port)
        try:
            self.response_started = True
            self.request.sendall(
                b"HTTP/1.1 200 Connection Established\r\n"
                b"Proxy-Agent: codex-socks-http-bridge\r\n\r\n"
            )
            if prefetched:
                upstream.sendall(prefetched)
            tunnel(self.request, upstream)
        finally:
            upstream.close()

    def handle_plain_http(self, first_line: str, header_blob: bytes) -> None:
        parts = first_line.split(" ")
        if (len(parts) != 3 or not parts[0].isascii()
                or not HEADER_NAME.fullmatch(parts[0].encode("ascii"))
                or parts[2] not in {"HTTP/1.0", "HTTP/1.1"}):
            raise HeaderError("invalid request line")
        method, raw_url, version = parts
        if any(ord(c) <= 32 or ord(c) == 127 for c in raw_url):
            raise HeaderError("invalid request target")
        headers = parse_headers(header_blob)
        fields = {key.lower(): value for key, value in headers}
        try:
            parsed = urlsplit(raw_url)
        except ValueError as exc:
            raise HeaderError("invalid request URL") from exc
        if parsed.fragment or parsed.username is not None or parsed.password is not None:
            raise HeaderError("invalid request URL")
        if parsed.hostname:
            # TLS must use CONNECT; never send plaintext to an https URL.
            if parsed.scheme.lower() != "http":
                raise HeaderError("plain requests require http")
            host, port = parse_host_port(parsed.netloc, 80)
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
        elif raw_url.startswith("/") and not raw_url.startswith("//"):
            try:
                host, port = parse_host_port(fields.get(b"host", b"").decode("ascii"), 80)
            except UnicodeDecodeError as exc:
                raise HeaderError("invalid Host header") from exc
            path = raw_url
        else:
            raise HeaderError("invalid request target")

        length = fields.get(b"content-length")
        transfer = fields.get(b"transfer-encoding")
        if length is not None:
            if not re.fullmatch(rb"[0-9]{1,12}", length):
                raise HeaderError("invalid content length")
            if int(length) > MAX_BODY_BYTES:
                raise HeaderError("request body too large", b"413 Content Too Large")
        if transfer is not None and (version != "HTTP/1.1" or transfer.lower() != b"chunked" or length is not None):
            raise HeaderError("ambiguous transfer framing")
        expectation = fields.get(b"expect")
        if expectation is not None and expectation.lower() != b"100-continue":
            raise HeaderError("unsupported expectation")
        connection = set()
        for key, value in headers:
            if key.lower() == b"connection":
                connection.update(item.strip().lower() for item in value.split(b","))
        if connection & {b"host", b"content-length", b"transfer-encoding"}:
            raise HeaderError("connection header conflicts with framing")
        excluded = connection | {b"proxy-authorization", b"proxy-connection", b"connection", b"keep-alive", b"upgrade", b"te", b"trailer", b"host", b"expect"}
        host_text = f"[{host}]" if ":" in host else host
        authority = host_text if port == 80 else f"{host_text}:{port}"
        output = [f"{method} {path} {version}".encode("latin-1"), f"Host: {authority}".encode("ascii"), b"Connection: close"]
        output.extend(key + b": " + value for key, value in headers if key.lower() not in excluded)
        upstream = self.connect_via_socks(host, port)
        upstream.settimeout(IO_TIMEOUT)
        try:
            upstream.sendall(b"\r\n".join(output) + b"\r\n\r\n")
            if expectation is not None:
                self.request.sendall(b"HTTP/1.1 100 Continue\r\n\r\n")
            body = RequestBody(self.request, header_blob.split(b"\r\n\r\n", 1)[1])
            if transfer is not None:
                body.chunks(upstream)
            elif length is not None:
                body.forward(upstream, int(length))
            # Deliberately one-way: another client request must not reach the
            # origin without a new authentication/sanitization pass.
            upstream.settimeout(IDLE_TIMEOUT)
            self.request.settimeout(IO_TIMEOUT)
            while True:
                data = upstream.recv(BUFFER_SIZE)
                if not data:
                    if not self.response_started:
                        raise OSError("upstream closed before sending a response")
                    return
                self.response_started = True
                self.request.sendall(data)
        finally:
            upstream.close()

    def handle(self) -> None:
        self.response_started = False
        try:
            # Do not let an unauthenticated local process hold a worker forever by
            # connecting and never finishing its proxy headers.
            self.request.settimeout(10)
            header_blob = recv_until_headers(self.request)
            parse_headers(header_blob)
            if not self.is_authorized(header_blob):
                self.request.sendall(
                    b"HTTP/1.1 407 Proxy Authentication Required\r\n"
                    b"Proxy-Authenticate: Basic realm=\"codex-portable\"\r\n"
                    b"Connection: close\r\n\r\n"
                )
                return
            self.request.settimeout(IO_TIMEOUT)
            first_line = header_blob.split(b"\r\n", 1)[0].decode("latin-1", "replace")
            parts = first_line.split(" ")
            if len(parts) == 3 and parts[0] == "CONNECT" and parts[2] in {"HTTP/1.0", "HTTP/1.1"}:
                self.handle_connect(parts[1], header_blob.split(b"\r\n\r\n", 1)[1])
            else:
                self.handle_plain_http(first_line, header_blob)
        except HeaderError as exc:
            if self.response_started:
                return
            try:
                self.request.sendall(
                    b"HTTP/1.1 " + exc.status + b"\r\nConnection: close\r\n\r\n"
                )
            except Exception:
                pass
        except Exception:
            # Once response bytes (or CONNECT's 200) were sent, another HTTP
            # status would corrupt the body/tunnel. Closing signals truncation.
            if self.response_started:
                return
            # The bridge is local-only; do not leak upstream exception details/tokens to proxy clients.
            try:
                self.request.sendall(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Local HTTP CONNECT proxy backed by a SOCKS5 proxy.")
    parser.add_argument("--listen-host", type=validate_loopback_host, default="127.0.0.1")
    parser.add_argument("--listen-port", type=valid_port, default=18088)
    parser.add_argument("--socks-host", type=validate_upstream_host, default="127.0.0.1")
    parser.add_argument("--socks-port", type=valid_port, default=10808)
    parser.add_argument("--auth-token-env", required=True, help="Environment variable containing a per-launch 64-hex proxy token")
    parser.add_argument("--no-rdns", action="store_true")
    args = parser.parse_args()

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.auth_token_env):
        parser.error("--auth-token-env must name a conventional environment variable")
    token = os.environ.get(args.auth_token_env, "")
    if not re.fullmatch(r"[0-9A-Fa-f]{64}", token):
        parser.error("proxy authentication token is missing or invalid")
    basic = base64.b64encode(f"codex:{token}".encode("ascii")).decode("ascii")

    ProxyHandler.expected_proxy_authorization = "Basic " + basic
    ProxyHandler.socks_host = args.socks_host
    ProxyHandler.socks_port = args.socks_port
    ProxyHandler.socks_rdns = not args.no_rdns

    server_class = ThreadingTCPServerV6 if ":" in args.listen_host else ThreadingTCPServer
    server = server_class((args.listen_host, args.listen_port), ProxyHandler)
    print(
        f"codex socks-http bridge listening on {args.listen_host}:{args.listen_port}, "
        f"upstream socks5://{args.socks_host}:{args.socks_port}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
