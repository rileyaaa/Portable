"""Exercise actual BAT -> pinned Codex -> native MCP client -> Chromium.

The Responses service and browser page are loopback-only synthetic fixtures.
No real model, account, device, host profile or external site is required.
Run explicitly on Windows with the fully hydrated source checkout.
"""
import hashlib
import importlib.util
import gzip
import http.server
import json
import os
from pathlib import Path
import subprocess
import tempfile
import stat
import tomllib

# Embedded Windows Python uses python314._pth and intentionally does not
# import sibling scripts via the usual sys.path. Load this exact test helper.
helper = Path(__file__).absolute().with_name("check_browser_mcp_stdio.py")
for p in (*reversed(helper.parents), helper):
    info = p.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise RuntimeError("Linked test helper")
    if p == helper and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
        raise RuntimeError("Invalid test helper")
spec = importlib.util.spec_from_file_location("portable_browser_test_helper", helper)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ROOT, ordinary, copy_input, serving = module.ROOT, module.ordinary, module.copy_input, module.serving

MARKER = "PORTABLE_NATIVE_MCP_PAGE_74f9b2"
PAGE_HITS = []
MODEL_REQUESTS = []
MODEL_ERRORS = []


class NativePage(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        PAGE_HITS.append(self.path)
        html = f"<!doctype html><title>{MARKER}</title><h1>{MARKER}</h1>".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)


def tool_entries(tools, namespace=None):
    for tool in tools:
        if tool.get("type") == "namespace":
            yield from tool_entries(tool.get("tools", []), tool["name"])
        else:
            yield namespace, tool


def call_output(body, ident):
    return [item for item in body.get("input", [])
            if item.get("call_id") == ident and str(item.get("type", "")).endswith("_call_output")]


def response_item(body, url):
    if len(MODEL_REQUESTS) == 1:
        entries = list(tool_entries(body.get("tools", [])))
        custom = next(((ns, t) for ns, t in entries
                       if t.get("type") == "custom" and t.get("name") == "exec"), None)
        if custom is not None:
            ns, tool = custom
            code = (
                'const find = suffix => { const t = ALL_TOOLS.find(x => '
                'x.name.includes("portable_browser") && x.name.endsWith(suffix)); '
                'if (!t) throw new Error("Browser tool missing: " + suffix); return tools[t.name]; };'
                'const nav = await find("browser_navigate")({url:' + json.dumps(url) + '});'
                'if (nav.isError) throw new Error(JSON.stringify(nav));'
                'const result = await find("browser_evaluate")({function:"() => document.title"});'
                'if (result.isError) throw new Error(JSON.stringify(result));'
                'text(JSON.stringify(result)); await find("browser_close")({});'
            )
            item = {"type": "custom_tool_call", "call_id": "portable-browser-call",
                    "name": tool["name"], "input": code}
            if ns is not None:
                item["namespace"] = ns
            return item
        # If the selected model uses standard direct tools rather than Code
        # Mode, use the exact advertised function name and namespace.
        direct = next(((ns, t) for ns, t in entries
                       if t.get("type") == "function"
                       and "portable_browser" in (str(ns) + str(t.get("name")))
                       and t.get("name", "").endswith("browser_navigate")), None)
        if direct is None:
            raise AssertionError("Native model request exposed neither Code Mode nor direct browser navigation")
        ns, tool = direct
        item = {"type": "function_call", "call_id": "portable-browser-call",
                "name": tool["name"], "arguments": json.dumps({"url": url})}
        if ns is not None:
            item["namespace"] = ns
        return item

    outputs = call_output(body, "portable-browser-call")
    assert outputs, "No actual native browser tool output returned to the synthetic model"
    assert MARKER in json.dumps(outputs), "Browser tool did not return the served page marker"
    assert "/" in PAGE_HITS, "No Chromium request reached the loopback page server"
    return {"id": "msg_synthetic", "type": "message", "role": "assistant",
            "status": "completed", "content": [
                {"type": "output_text", "text": "native-browser-mcp-ok", "annotations": []}]}


def provider(url, model="gpt-6-sol", handler=response_item, expected_headers=None, forbidden_headers=(), max_requests=2):
    class Provider(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_GET(self):
            payload = json.dumps({"data": [{"id": model, "object": "model"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            try:
                assert self.path == "/v1/responses", self.path
                for name, value in (expected_headers or {}).items():
                    assert self.headers.get(name) == value, "Wrong synthetic configured header: " + name
                for name in forbidden_headers:
                    assert self.headers.get(name) is None, "Unexpected inherited synthetic header: " + name
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                if self.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                body = json.loads(raw)
                assert body.get("model") == model
                MODEL_REQUESTS.append(body)
                assert len(MODEL_REQUESTS) <= max_requests, "Unexpected additional model turn"
                item = handler(body, url)
                ident = "resp_synthetic_" + str(len(MODEL_REQUESTS))
                response = {"id": ident, "object": "response", "status": "completed",
                            "model": model, "output": [item],
                            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}
                events = [{"type": "response.created", "response": {
                    **response, "status": "in_progress", "output": []}},
                    {"type": "response.output_item.done", "output_index": 0, "item": item},
                    {"type": "response.completed", "response": response}]
                payload = "".join("event: " + e["type"] + "\ndata: " + json.dumps(e) + "\n\n"
                                  for e in events).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                self.wfile.flush()
            except Exception as exc:
                MODEL_ERRORS.append(str(exc))
                self.send_error(400, "Synthetic model contract failed")

    return Provider


def main():
    if os.name != "nt":
        raise SystemExit("Windows x64 required")
    for p in (*reversed(ROOT.parents), ROOT):
        ordinary(p)
    scratch = ROOT / "tmp"
    scratch.mkdir(exist_ok=True)
    ordinary(scratch)
    with tempfile.TemporaryDirectory(prefix="codex-browser-native-", dir=scratch) as owned:
        fixture = Path(owned) / "Relocated Portable"
        fixture.mkdir()
        manifest = json.loads((ROOT / "tool/runtime-manifest.json").read_text(encoding="utf-8-sig"))
        bat_name = "\u542f\u52a8Codex.bat"
        for relative in ("env.ps1", "run-codex.ps1", bat_name, "tool/runtime-manifest.json",
                         "tool/portable-process.ps1", "tool/node/node.exe",
                         "tool/automation", *manifest["files"]):
            copy_input(relative, fixture)
        (fixture / "codex-resources").mkdir()
        with serving(NativePage) as page_port, serving(provider(
                f"http://127.0.0.1:{page_port}/",
                expected_headers={"X-Portable-Audit": "synthetic-package-value"},
                forbidden_headers=("X-Portable-Host-Only",))) as api_port:
            (fixture / "env.local.ps1").write_text(
                '$env:CODEX_AUTH_MODE = "api"\n'
                '$env:CODEX_PORTABLE_ALLOW_USER_MCP = "true"\n'
                '$env:CODEX_PROXY_ENABLED = "false"\n'
                '$env:CODEX_DISABLE_WEBSOCKET = "true"\n'
                '$env:CODEX_MODEL = "gpt-6-sol"\n'
                f'$env:CODEX_BASE_URL = "http://127.0.0.1:{api_port}/v1"\n'
                '$env:OPENAI_API_KEY = "synthetic-offline-not-a-real-key"\n'
                '$env:CODEX_ENV_HTTP_HEADERS_TOML = \'{ "X-Portable-Audit" = "PORTABLE_TEST_HEADER", "X-Portable-Host-Only" = "PORTABLE_TEST_MISSING_HEADER" }\'\n'
                '$env:PORTABLE_TEST_HEADER = "synthetic-package-value"\n',
                encoding="utf-8")
            windows = Path(os.environ["SystemRoot"])
            # Configure exactly one synthetic MCP via the original durable user
            # sidecar and original double opt-in. No new launcher switch.
            (fixture / "home").mkdir()
            store = fixture / "home/portable-extensions.toml"
            engine = windows / "System32/WindowsPowerShell/v1.0/powershell.exe"
            entry = fixture / "tool/automation/start-browser.ps1"
            workspace = fixture / "work/browser-debug"
            lines = [
                "[mcp_servers.portable_browser]",
                "command = " + json.dumps(str(engine)),
                "args = " + json.dumps(["-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                                        "Bypass", "-File", str(entry), "-TaskAuthorized",
                                        "-Workspace", str(workspace)]),
                "cwd = " + json.dumps(str(fixture / "work")),
                'env_vars = ["CODEX_INSTALL_DIR","CODEX_HOME","CODEX_PROXY_ENABLED","CODEX_PROXY_FOR_SUBPROCESS","CODEX_SANDBOX_NETWORK_ACCESS","HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","NO_PROXY"]',
                "startup_timeout_sec = 120",
                "tool_timeout_sec = 120",
                "supports_parallel_tool_calls = false",
                "required = true",
                # The synthetic model is trusted test code; this approval
                # setting is restricted to the disposable fixture only.
                'default_tools_approval_mode = "approve"',
            ]
            store.write_text("\n".join(lines) + "\n", encoding="utf-8")
            expected_store = hashlib.sha256(store.read_bytes()).digest()
            cmd = windows / "System32/cmd.exe"
            env = {k: os.environ[k] for k in ("SystemRoot", "WINDIR", "SystemDrive",
                                             "ComSpec", "PATHEXT", "OS", "PROCESSOR_ARCHITECTURE",
                                             "USERNAME", "COMPUTERNAME") if k in os.environ}
            env["PATH"] = str(windows / "System32")
            # Both names originate in the synthetic parent. Only the explicit
            # package assignment may reach the model request.
            env["PORTABLE_TEST_HEADER"] = "synthetic-parent-conflict"
            env["PORTABLE_TEST_MISSING_HEADER"] = "synthetic-parent-only"
            command = (f'"{cmd}" /d /s /c ""{fixture / bat_name}" '
                       '--portable-auth=api --portable-extensions '
                       'exec --skip-git-repo-check --json "Run the synthetic browser check.""')
            proc = subprocess.Popen(command, executable=str(cmd), cwd=fixture, env=env,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            try:
                out, err = proc.communicate(timeout=300)
            except subprocess.TimeoutExpired:
                subprocess.run([str(windows / "System32/taskkill.exe"), "/PID", str(proc.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, check=False)
                out, err = proc.communicate(timeout=20)
                raise AssertionError("Native Codex browser session exceeded the test deadline")
            if proc.returncode or MODEL_ERRORS or b"native-browser-mcp-ok" not in out:
                # This entire fixture contains only synthetic data.
                print(out.decode("utf-8", "replace")[-8000:])
                print(err.decode("utf-8", "replace")[-8000:])
                raise AssertionError(f"Native integration failed (exit={proc.returncode}, errors={MODEL_ERRORS})")
            assert len(MODEL_REQUESTS) == 2
            cfg = tomllib.loads((fixture / "home/config.toml").read_text(encoding="utf-8-sig"))
            assert "portable_browser" in cfg["mcp_servers"]
            assert hashlib.sha256(store.read_bytes()).digest() == expected_store
            assert (fixture / "cache/browser/profile").is_dir()
            print("PASS real BAT, pinned native Codex and MCP client, real Chromium, tool output returned to Responses API")
            print("PASS original user MCP config retained unchanged")
        print("PASS actual Responses header uses package value and omits inherited host-only value")


if __name__ == "__main__":
    main()
