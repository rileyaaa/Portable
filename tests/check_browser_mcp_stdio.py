"""Native Windows stdio browser integration with synthetic local HTTP fixtures.

Run explicitly from a clean source checkout; no real account, external model,
host browser or existing profile. All writable state belongs to one tmp fixture.
"""
import contextlib
import http.server
import json
import os
from pathlib import Path
import queue
import shutil
import socketserver
import stat
import subprocess
import tempfile
import threading
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def ordinary(p):
    s = p.lstat()
    if stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
        raise RuntimeError("Linked fixture input")
    if p.is_file() and s.st_nlink != 1:
        raise RuntimeError("Multiply linked fixture input")


def copy_input(relative, dest):
    src = ROOT / relative
    for part in (*reversed(src.parents), src):
        ordinary(part)
    if src.is_dir():
        for base, dirs, files in os.walk(src, followlinks=False):
            for name in dirs + files:
                ordinary(Path(base) / name)
        shutil.copytree(src, dest / relative)
    else:
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)


HTML = b"""<!doctype html><title>Portable MCP smoke</title>
<h1>Portable MCP smoke</h1><button onclick="document.body.dataset.clicked='yes';this.textContent='Clicked'">Click me</button>
<input aria-label="Name">"""
PROXY_REQUESTS = []
SOCKS_REQUESTS = []


class Page(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(HTML)))
        self.end_headers()
        self.wfile.write(HTML)


class Proxy(Page):
    def do_CONNECT(self):
        self.send_error(403)

    def do_GET(self):
        if urlsplit(self.path).hostname != "portable-browser.invalid":
            self.send_error(403)
            return
        if self.headers.get("Proxy-Authorization") != "Basic Y29kZXg6c3ludGhldGlj":
            self.send_response(407)
            self.send_header("Proxy-Authenticate", 'Basic realm="portable-test"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        PROXY_REQUESTS.append(self.path)
        super().do_GET()


class SocksProxy(socketserver.StreamRequestHandler):
    """Loopback-only synthetic SOCKS5 endpoint; never connect to an upstream host."""
    def handle(self):
        self.request.settimeout(10)
        try:
            greeting = self.rfile.read(2)
            if len(greeting) != 2 or greeting[0] != 5:
                return
            methods = self.rfile.read(greeting[1])
            if 0 not in methods:
                self.wfile.write(b"\x05\xff")
                return
            self.wfile.write(b"\x05\x00")
            if self.rfile.read(4) != b"\x05\x01\x00\x03":
                return
            size = self.rfile.read(1)
            if not size:
                return
            host = self.rfile.read(size[0])
            port = int.from_bytes(self.rfile.read(2), "big")
            if host != b"portable-socks.invalid" or port != 80:
                self.wfile.write(b"\x05\x02\x00\x01\x00\x00\x00\x00\x00\x00")
                return
            self.wfile.write(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x50")
            request = self.rfile.readline(4096)
            if not request.startswith(b"GET "):
                return
            for _ in range(64):
                header = self.rfile.readline(4096)
                if header == b"\r\n":
                    break
                if not header or len(header) >= 4096:
                    return
            else:
                return
            SOCKS_REQUESTS.append(host)
            self.wfile.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\nContent-Length: "
                             + str(len(HTML)).encode("ascii") + b"\r\n\r\n" + HTML)
        except (OSError, ValueError):
            return


@contextlib.contextmanager
def serving(handler, server_type=http.server.ThreadingHTTPServer):
    server = server_type(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class Client:
    def __init__(self, root, workspace, proxy_port=None, socks_port=None):
        windows = Path(os.environ["SystemRoot"])
        engine = windows / "System32/WindowsPowerShell/v1.0/powershell.exe"
        self.taskkill = windows / "System32/taskkill.exe"
        env = {k: os.environ[k] for k in ("SystemRoot", "WINDIR", "SystemDrive",
                                         "ComSpec", "PATHEXT", "OS", "PROCESSOR_ARCHITECTURE")
               if k in os.environ}
        env.update(PATH=str(windows / "System32"), CODEX_INSTALL_DIR=str(root),
                   CODEX_HOME=str(root / "home"), CODEX_PROXY_ENABLED="false",
                   CODEX_PROXY_FOR_SUBPROCESS="false", CODEX_SANDBOX_NETWORK_ACCESS="true")
        scratch = root / "tmp"
        scratch.mkdir(exist_ok=True)
        for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
            env[key] = str(scratch)
        if proxy_port:
            env.update(CODEX_PROXY_ENABLED="true", CODEX_PROXY_FOR_SUBPROCESS="true",
                       HTTP_PROXY=f"http://codex:synthetic@127.0.0.1:{proxy_port}",
                       NO_PROXY="localhost,127.0.0.1,::1")
        elif socks_port:
            env.update(CODEX_PROXY_ENABLED="true", CODEX_PROXY_FOR_SUBPROCESS="true",
                       ALL_PROXY=f"socks5h://127.0.0.1:{socks_port}",
                       NO_PROXY="localhost,127.0.0.1,::1")
        self.proc = subprocess.Popen(
            [str(engine), "-NoLogo", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-File",
             str(root / "tool/automation/start-browser.ps1"), "-TaskAuthorized",
             "-Workspace", str(workspace)],
            cwd=root, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        self.responses = queue.Queue()
        self.errors = []
        self.counter = 0
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._stderr, daemon=True).start()

    def _read(self):
        try:
            for line in self.proc.stdout:
                self.responses.put(json.loads(line.decode("utf-8")))
        except Exception as exc:
            self.responses.put(exc)
        finally:
            self.responses.put(EOFError("MCP pipe closed"))

    def _stderr(self):
        # Synthetic fixture only; keep diagnostic memory bounded.
        for line in self.proc.stderr:
            if len(self.errors) < 30:
                self.errors.append(line.decode("utf-8", errors="replace")[:1000])

    def send(self, message):
        self.proc.stdin.write((json.dumps({"jsonrpc": "2.0", **message}) + "\n").encode())
        self.proc.stdin.flush()

    def request(self, method, params=None):
        self.counter += 1
        ident = self.counter
        self.send({"id": ident, "method": method, "params": params or {}})
        while True:
            response = self.responses.get(timeout=150)
            if isinstance(response, Exception):
                raise response
            if response.get("id") == ident:
                return response

    def initialize(self):
        r = self.request("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "portable-native-test", "version": "1"}})
        assert "result" in r, r
        self.send({"method": "notifications/initialized"})
        r = self.request("tools/list")
        names = {t["name"] for t in r["result"]["tools"]}
        assert {"browser_navigate", "browser_snapshot", "browser_click",
                "browser_evaluate", "browser_close"}.issubset(names), names
        assert not any("run_code" in n or "upload" in n for n in names)

    def call(self, name, **args):
        r = self.request("tools/call", {"name": name, "arguments": args})
        assert "error" not in r and not r["result"].get("isError"), (name, r)
        return r["result"]

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=30)
            assert self.proc.returncode == 0, self.errors
        except BaseException:
            if self.proc.poll() is None:
                subprocess.run([str(self.taskkill), "/PID", str(self.proc.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=15, check=False)
                self.proc.wait(timeout=15)
            raise
        finally:
            self.proc.stdout.close()
            self.proc.stderr.close()

    def __enter__(self):
        return self

    def __exit__(self, typ, exc, tb):
        if typ is not None and self.errors:
            print("Synthetic MCP stderr:", "".join(self.errors), flush=True)
        self.close()


def main():
    if os.name != "nt":
        raise SystemExit("Windows x64 is required")
    for p in (*reversed(ROOT.parents), ROOT):
        ordinary(p)
    scratch = ROOT / "tmp"
    scratch.mkdir(exist_ok=True)
    ordinary(scratch)
    with tempfile.TemporaryDirectory(prefix="mcp-native-", dir=scratch) as owned:
        fixture = Path(owned) / "Portable relocated with spaces"
        fixture.mkdir()
        for relative in ("env.ps1", "tool/portable-process.ps1",
                         "tool/node/node.exe", "tool/automation"):
            copy_input(relative, fixture)
        workspace = fixture / "work/browser-debug"
        workspace.mkdir(parents=True)
        sentinel = workspace / "user-result.txt"
        sentinel.write_text("keep", encoding="utf-8")
        with (serving(Page) as port, serving(Proxy) as proxy_port,
              serving(SocksProxy, socketserver.ThreadingTCPServer) as socks_port):
            url = f"http://127.0.0.1:{port}/"
            with Client(fixture, workspace) as client:
                client.initialize()
                rejected = client.request("tools/call", {
                    "name": "browser_navigate", "arguments": {"url": "file:///C:/refused"}})
                assert "error" in rejected
                for name,args in (
                    ("browser_find", {"text":"Click me","maxResults":1}),
                    ("browser_network_requests", {"static":True,"all":True}),
                    ("browser_tabs", {"action":"new","isolatedContext":"unowned"}),
                ):
                    refused=client.request("tools/call",{"name":name,"arguments":args})
                    assert "error" in refused, (name,refused)
                client.call("browser_navigate", url=url)
                snap = client.call("browser_snapshot")
                assert "Portable MCP smoke" in json.dumps(snap)
                assert "Click me" in json.dumps(client.call("browser_find",text="Click me"))
                client.call("browser_click", target="button", element="Click me")
                clicked = client.call("browser_evaluate", function="() => document.body.dataset.clicked")
                assert "yes" in json.dumps(clicked)
                client.call("browser_take_screenshot", filename="proof.png")
                assert (workspace / "proof.png").stat().st_size > 0
                # The fixture page never writes cookies. Seed exactly once and
                # verify after reopening without any second write.
                seeded = client.call("browser_evaluate", function=(
                    "() => { document.cookie = 'portable_mcp=persisted; Max-Age=3600; Path=/'; "
                    "return document.cookie; }"))
                assert "portable_mcp=persisted" in json.dumps(seeded)
                client.call("browser_tabs",action="new",url=url)
                assert "portable_mcp=persisted" in json.dumps(client.call("browser_evaluate",function="() => document.cookie"))
                client.call("browser_tabs",action="close")
                client.call("browser_close")
                client.call("browser_navigate", url=url)
                cookies = client.call("browser_evaluate", function="() => document.cookie")
                assert "portable_mcp=persisted" in json.dumps(cookies)
                client.call("browser_close")
            print("PASS actual Windows stdio MCP initialize/list/navigate/click/evaluate/screenshot/close/reopen", flush=True)
            with Client(fixture, workspace, proxy_port) as client:
                client.initialize()
                client.call("browser_navigate", url="http://portable-browser.invalid/")
                assert "Portable MCP smoke" in json.dumps(client.call("browser_snapshot"))
                assert PROXY_REQUESTS, "Chromium did not reach the authenticated synthetic proxy"
                client.call("browser_navigate", url=url)
                assert "Portable MCP smoke" in json.dumps(client.call("browser_snapshot"))
                client.call("browser_close")
            print("PASS explicit authenticated HTTP proxy and loopback bypass", flush=True)
            with Client(fixture, workspace, socks_port=socks_port) as client:
                client.initialize()
                client.call("browser_navigate", url="http://portable-socks.invalid/")
                assert "Portable MCP smoke" in json.dumps(client.call("browser_snapshot"))
                assert SOCKS_REQUESTS, "Chromium did not reach the synthetic SOCKS5 endpoint"
                client.call("browser_close")
            assert sentinel.read_text(encoding="utf-8") == "keep"
            assert len(list(workspace.glob("mcp-output-*"))) == 3
            print("PASS actual SOCKS5 fallback and separate MCP output directories", flush=True)


if __name__ == "__main__":
    main()
