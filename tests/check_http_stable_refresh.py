"""Real package-local HTTP consumer probe; loopback and synthetic inputs only."""
import asyncio
import base64
import gzip
import importlib.metadata as md
import os
from pathlib import Path
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import anyio
import httpx
import requests
import urllib3

DATA = b"portable-http-stream-" * 41
AUTH = "Basic " + base64.b64encode(b"portable:synthetic").decode("ascii")

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/data")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path not in ("/data", "http://portable.invalid/data"):
            self.send_error(404)
            return
        if self.path.startswith("http://") and self.headers.get("Proxy-Authorization") != AUTH:
            self.send_error(407)
            return
        compressed = gzip.compress(DATA)
        self.send_response(200)
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for offset in range(0, len(compressed), 9):
            part = compressed[offset:offset + 9]
            self.wfile.write(("%x\r\n" % len(part)).encode("ascii") + part + b"\r\n")
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def log_message(self, *_):
        pass

def main():
    root = Path(__file__).absolute().parents[1]
    runtime = root / "tool/python"
    assert os.name == "nt" and sys.version_info[:3] == (3, 14, 10)
    assert Path(sys.executable).resolve() == runtime / "python.exe"
    assert sys.flags.isolated and sys.flags.ignore_environment and sys.flags.safe_path
    assert set(map(Path, sys.path)) == {runtime / "python314.zip", runtime, runtime / "Lib/site-packages"}
    assert os.environ.get("PIP_CONFIG_FILE") == os.devnull
    assert (md.version("urllib3"), md.version("anyio")) == tuple(sys.argv[1:])
    for mod in (urllib3, anyio, requests, httpx):
        assert Path(mod.__file__).resolve().is_relative_to(runtime / "Lib/site-packages")
    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = "http://127.0.0.1:" + str(server.server_port)
        pool = urllib3.PoolManager()
        try:
            response = pool.request("GET", url + "/data", preload_content=False, timeout=5)
            try:
                assert response.status == 200 and b"".join(response.stream(11, decode_content=True)) == DATA
            finally:
                response.release_conn()
            raw = pool.request("GET", url + "/data", preload_content=False, timeout=5)
            try:
                assert raw.status == 200
                encoded = b"".join(raw.stream(11, decode_content=False))
                assert encoded.startswith(b"\x1f\x8b") and gzip.decompress(encoded) == DATA
            finally:
                raw.release_conn()
            with requests.Session() as session:
                session.trust_env = False
                with session.get(url + "/redirect", stream=True, timeout=5) as response:
                    assert response.status_code == 200 and len(response.history) == 1
                    assert b"".join(response.iter_content(13)) == DATA
                proxy = "http://portable:synthetic@127.0.0.1:" + str(server.server_port)
                with session.get("http://portable.invalid/data", proxies={"http": proxy}, stream=True, timeout=5) as response:
                    response.raise_for_status()
                    assert b"".join(response.iter_content(17)) == DATA
            with httpx.Client(trust_env=False, timeout=5) as client:
                assert client.get(url + "/data").raise_for_status().content == DATA
            async def fetch():
                with anyio.move_on_after(0) as scope:
                    await anyio.sleep_forever()
                assert scope.cancel_called
                async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
                    with anyio.fail_after(10):
                        async with client.stream("GET", url + "/data") as response:
                            response.raise_for_status()
                            chunks = [part async for part in response.aiter_bytes(19)]
                            assert b"".join(chunks) == DATA
            anyio.run(fetch, backend="asyncio")
        finally:
            pool.clear()
            server.shutdown()
            worker.join(10)
            assert not worker.is_alive()
    print("HTTP_STABLE_LOOPBACK_PROXY_STREAM_ASYNC=PASS", *sys.argv[1:], flush=True)

if __name__ == "__main__":
    main()
