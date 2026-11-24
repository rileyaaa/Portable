"""Native model-visible skills and actual bundled shell/browser tools, Windows only."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import tomllib

# Embedded Python may ignore PYTHONIOENCODING. Keep the original failure visible.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")

helper = Path(__file__).absolute().with_name("check_codex_browser_mcp.py")
for p in (*reversed(helper.parents), helper):
    info = p.lstat()
    assert not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400
    if p == helper:
        assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1
spec = importlib.util.spec_from_file_location("native_tool_fixture", helper)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
ROOT = m.ROOT
SKILLS = {p.parent.name for p in (ROOT / "home/skills").glob("*/SKILL.md")
          if not p.parent.name.startswith(".")}
assert "browser-debug" in SKILLS and len(SKILLS) >= 10
TOOL_MARKER = "PORTABLE_TOOLS_EXECUTED_0172"
BROWSER_MARKER = "PORTABLE_TASK_RENDERED_0172"
DONE = "native-tool-discovery-ok"

PROBE_PY = '''
import importlib, os, pathlib, sys, tomllib
root = pathlib.Path(os.environ["CODEX_INSTALL_DIR"]).resolve()
cfg = tomllib.loads((root / "home/config.toml").read_text(encoding="utf-8-sig"))
expected = cfg["shell_environment_policy"]["set"]
different = []
for key, value in expected.items():
    actual = os.environ.get(key)
    if actual is None:
        different.append(key + ":missing")
    elif actual != value and os.path.normcase(actual) != os.path.normcase(value):
        different.append(key + ":different")
print("ENV_DIFFERENCES=" + ",".join(different) if different else
      "ENV_ALL_CONFIGURED_VALUES_CONSUMED=" + str(len(expected)), flush=True)
assert pathlib.Path(sys.executable).resolve() == root / "tool/python/python.exe"
assert os.environ["CODEX_HOME"].lower() == str(root / "home").lower()
assert os.environ["CODEX_PYTHON"].lower() == str(root / "tool/python/python.exe").lower()
assert os.environ["PIP_CONFIG_FILE"].lower() == "nul"
for name in ("pip", "requests", "httpx", "bs4", "lxml", "pandas", "numpy", "openpyxl",
             "docx", "pptx", "PIL", "xlsxwriter", "socks", "defusedxml", "fitz",
             "pymupdf4llm", "PyInstaller"):
    module = importlib.import_module(name)
    assert pathlib.Path(module.__file__).resolve().is_relative_to(root / "tool/python"), name
print("BUNDLED_PYTHON_IMPORTS_OK", flush=True)
if different:
    raise SystemExit(9)
'''
PROBE_PS = r'''
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($env:CODEX_INSTALL_DIR).TrimEnd('\')
if (-not (Test-Path -LiteralPath (Join-Path $root 'env.ps1'))) { throw 'Package root marker missing' }
$prefix = $root + '\'
foreach ($name in @('python.exe','pip.cmd','node.exe','npm.cmd','rg.exe','fd.exe','jq.exe','7z.exe')) {
    $command = Get-Command -Name $name -CommandType Application -ErrorAction Stop | Select-Object -First 1
    if (-not $command.Source.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)) { throw ('Host fallback: ' + $name) }
}
function Run-Checked([string]$name, [string[]]$argv) {
    & $name @argv
    if ($LASTEXITCODE -ne 0) { throw ('Tool failed: ' + $name + ' exit=' + $LASTEXITCODE) }
}
Run-Checked 'node.exe' @('--version')
Run-Checked 'npm.cmd' @('--version')
Run-Checked 'pip.cmd' @('--version')
Run-Checked 'rg.exe' @('--version')
Run-Checked 'fd.exe' @('--version')
Run-Checked 'jq.exe' @('--version')
Run-Checked '7z.exe' @('i')
# Version only, without discovering devices or starting the ADB daemon.
Run-Checked (Join-Path $root 'tool/android/platform-tools/adb.exe') @('version')
Run-Checked 'python.exe' @('-B', (Join-Path $root 'work/tool-probe/probe.py'))
Write-Output 'PORTABLE_TOOLS_EXECUTED_0172'
'''
# Inspect the *actual* Codex-created restricted shell before executing the
# pre-existing script. Every diagnostic is bounded to the disposable work tree.
DIAG_PS = r'''
$ErrorActionPreference = 'Stop'
Write-Output ('DIAG_CWD=' + (Get-Location).Path)
Write-Output ('DIAG_PROCESS_CWD=' + [Environment]::CurrentDirectory)
Write-Output ('DIAG_PS=' + $PSVersionTable.PSVersion + ';LANG=' + $ExecutionContext.SessionState.LanguageMode)
Write-Output ('DIAG_INSTALL_DIR=' + $env:CODEX_INSTALL_DIR)
$expectedRoot = '__EXPECTED_ROOT__'
if ($env:CODEX_INSTALL_DIR -ne $expectedRoot) { throw 'Unexpected package root; stop' }
$target = Join-Path $expectedRoot 'work/tool-probe/probe.ps1'
$relative = './tool-probe/probe.ps1'
function Observe([string]$label, [scriptblock]$operation) {
    try {
        $result = & $operation
        Write-Output ('DIAG_' + $label + '=OK ' + ($result -join '; '))
    } catch {
        Write-Output ('DIAG_' + $label + '=ERROR ' + $_.Exception.GetType().FullName + ' ' + $_.Exception.Message)
    }
}
Observe 'WORK' { Test-Path -LiteralPath (Join-Path $expectedRoot 'work') -PathType Container }
Observe 'TARGET_ABS' { Test-Path -LiteralPath $target -PathType Leaf }
Observe 'TARGET_REL' { Test-Path -LiteralPath $relative -PathType Leaf }
Observe 'ITEM' { (Get-Item -LiteralPath $target -ErrorAction Stop).FullName }
Observe 'READ' { (Get-Content -LiteralPath $target -TotalCount 1 -ErrorAction Stop) }
Observe 'SKILL_READ' { (Get-Content -LiteralPath (Join-Path $expectedRoot 'home/skills/browser-debug/SKILL.md') -TotalCount 2 -ErrorAction Stop) }
Observe 'RESOLVE_COMMAND' { (Get-Command -Name $target -ErrorAction Stop).Source }
Observe 'WORK_WRITE' {
    $own = Join-Path $expectedRoot 'work/tool-probe/native-created.txt'
    if (Test-Path -LiteralPath $own) { throw 'Unexpected existing test file' }
    Set-Content -LiteralPath $own -Value 'owned-write' -Encoding UTF8 -ErrorAction Stop
    Get-Content -LiteralPath $own -ErrorAction Stop
}
Observe 'RELATIVE_SCRIPT' { & $relative; if ($LASTEXITCODE -ne 0) { throw ('Relative script exit=' + $LASTEXITCODE) } }
Write-Output 'DIAG_BEGIN_ORIGINAL_ABSOLUTE'
& $target
if ($LASTEXITCODE -ne 0) { throw ('Absolute script exit=' + $LASTEXITCODE) }
'''

BROWSER_PS = r'''
$ErrorActionPreference = 'Stop'
$entry = Join-Path $env:CODEX_INSTALL_DIR 'tool/automation/start-browser.ps1'
$engine = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
& $engine -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $entry -TaskAuthorized -Workspace 'work/tool-probe' -TaskScript 'work/tool-probe/page.cjs'
exit $LASTEXITCODE
'''
BROWSER_JS = '''
module.exports = async ({page}) => {
  await page.setContent('<title>PORTABLE_TASK_RENDERED_0172</title><button>Local test</button>');
  await page.getByRole('button', {name: 'Local test'}).click();
  return {title: await page.title()};
};
'''


def handler_for(fixture, mode):
    expected = BROWSER_MARKER if mode == "browser" else TOOL_MARKER
    script = "browser.ps1" if mode == "browser" else "probe.ps1"

    def handler(body, _):
        if len(m.MODEL_REQUESTS) == 1:
            prompt = json.dumps({"instructions": body.get("instructions"), "input": body.get("input")},
                                ensure_ascii=False)
            absent = sorted(name for name in SKILLS if name not in prompt)
            assert not absent, "Model-visible skill catalog missing: " + ", ".join(absent)
            assert "browser-debug" in prompt, "Browser skill absent"
            print("MODEL_VISIBLE_LOCAL_SKILLS=" + ",".join(sorted(SKILLS)), flush=True)
            entries = list(m.tool_entries(body.get("tools", [])))
            assert not any("portable_browser" in (str(ns) + str(t.get("name"))) for ns, t in entries), \
                "Browser MCP should not be advertised by default"
            command = ("& (Join-Path $env:CODEX_INSTALL_DIR 'work/tool-probe/" + script + "')"
                       if mode == "browser" else DIAG_PS.replace("__EXPECTED_ROOT__", str(fixture).replace("'", "''")))
            args = {"cmd": command, "workdir": str(fixture / "work"), "login": False,
                    "yield_time_ms": 30000, "max_output_tokens": 4500}
            custom = next(((ns, t) for ns, t in entries
                           if t.get("type") == "custom" and t.get("name") == "exec"), None)
            if custom:
                ns, tool = custom
                code = (
                    'const e = ALL_TOOLS.find(x=>x.name.endsWith("exec_command")); '
                    'if (!e) throw new Error("Shell tool missing: "+JSON.stringify(ALL_TOOLS.map(x=>x.name))); '
                    'let r = await tools[e.name](' + json.dumps(args) + '); '
                    'text(JSON.stringify(r)); '
                    'for(let i=0;i<5;i++){ '
                    'const v = r.structuredContent || r; '
                    'if (!v.session_id) break; '
                    'const w = ALL_TOOLS.find(x=>x.name.endsWith("write_stdin")); '
                    'if (!w) throw new Error("Missing write_stdin"); '
                    'r=await tools[w.name]({session_id:v.session_id,chars:"",yield_time_ms:30000}); '
                    'text(JSON.stringify(r)); }'
                )
                item = {"type": "custom_tool_call", "call_id": "portable-probe",
                        "name": tool["name"], "input": code}
            else:
                direct = next(((ns, t) for ns, t in entries if t.get("type") == "function"
                               and t.get("name", "").endswith("exec_command")), None)
                assert direct, "No native shell entry"
                ns, tool = direct
                item = {"type": "function_call", "call_id": "portable-probe",
                        "name": tool["name"], "arguments": json.dumps(args)}
            if ns is not None:
                item["namespace"] = ns
            return item
        outputs = m.call_output(body, "portable-probe")
        evidence = json.dumps(outputs, ensure_ascii=False)
        print("NATIVE_TOOL_OUTPUT=" + evidence[:26000], flush=True)
        # The marker is necessary but is not sufficient when the outer shell fails.
        assert expected in evidence, "Real tool output did not contain success marker: " + expected
        assert "DIAG_BEGIN_ORIGINAL_ABSOLUTE" in evidence or mode == "browser"
        # Native direct output has an exit line; Code Mode emits JSON exit_code.
        assert 'Process exited with code 1' not in evidence
        assert '\\\"exit_code\\\":1' not in evidence and '\\\"exit_code\\\": 1' not in evidence
        assert "ENV_DIFFERENCES=" not in evidence, "Actual child environment differs from generated policy"
        return {"id": "msg_probe", "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": DONE, "annotations": []}]}
    return handler


def main():
    if os.name != "nt":
        raise SystemExit("Windows x64 required")
    mode = sys.argv[1] if len(sys.argv) == 2 else "normal"
    assert mode in {"normal", "browser", "unknown"}
    model = {"normal": "gpt-6-sol", "browser": "gpt-6.2-sol",
             "unknown": "portable-synthetic-model"}[mode]
    for p in (*reversed(ROOT.parents), ROOT):
        m.ordinary(p)
    scratch = ROOT / "tmp"
    scratch.mkdir(exist_ok=True)
    m.ordinary(scratch)
    with tempfile.TemporaryDirectory(prefix="native-tools-" + mode + "-", dir=scratch) as owned:
        fixture = Path(owned) / ("Relocated Portable" if mode != "unknown" else "Relocated \u4fbf\u643a Portable")
        fixture.mkdir()
        manifest = json.loads((ROOT / "tool/runtime-manifest.json").read_text(encoding="utf-8-sig"))
        bat = "\u542f\u52a8Codex.bat"
        for relative in ("env.ps1", "run-codex.ps1", bat, "tool/runtime-manifest.json",
                         "tool/portable-process.ps1", "tool/python", "tool/node", "tool/bin",
                         "tool/android/platform-tools", "home/skills", *manifest["files"]):
            m.copy_input(relative, fixture)
        if mode == "browser":
            m.copy_input("tool/automation", fixture)
            source = ROOT / "Version_History/YOLO mode\u4e13\u7528\u5305-env.ps1"
            m.ordinary(source)
            (fixture / "env.ps1").write_bytes(source.read_bytes())
        (fixture / "codex-resources").mkdir()
        probe = fixture / "work/tool-probe"
        probe.mkdir(parents=True)
        (probe / "probe.py").write_text(PROBE_PY, encoding="utf-8")
        (probe / "probe.ps1").write_text(PROBE_PS, encoding="utf-8-sig")
        (probe / "browser.ps1").write_text(BROWSER_PS, encoding="utf-8-sig")
        (probe / "page.cjs").write_text(BROWSER_JS, encoding="utf-8")
        (fixture / "home/portable-extensions.toml").write_text(
            '[mcp_servers.portable_browser]\ncommand = "synthetic-never-executed"\n', encoding="utf-8")
        with m.serving(m.provider("", model=model, handler=handler_for(fixture, mode))) as port:
            (fixture / "env.local.ps1").write_text(
                '$env:CODEX_AUTH_MODE = "api"\n'
                '$env:CODEX_PROXY_ENABLED = "false"\n'
                '$env:CODEX_DISABLE_WEBSOCKET = "true"\n'
                f'$env:CODEX_MODEL = "{model}"\n'
                f'$env:CODEX_BASE_URL = "http://127.0.0.1:{port}/v1"\n'
                '$env:OPENAI_API_KEY = "synthetic-offline-not-a-real-key"\n', encoding="utf-8")
            windows = Path(os.environ["SystemRoot"])
            cmd = windows / "System32/cmd.exe"
            env = {k: os.environ[k] for k in ("SystemRoot","WINDIR","SystemDrive","ComSpec",
                   "PATHEXT","OS","PROCESSOR_ARCHITECTURE","USERNAME","COMPUTERNAME") if k in os.environ}
            env["PATH"] = str(windows / "System32")
            command = (f'"{cmd}" /d /s /c ""{fixture / bat}" --portable-auth=api '
                       'exec --skip-git-repo-check --json "Inspect the authorized local test tools and page.""')
            proc = subprocess.Popen(command, executable=str(cmd), cwd=fixture, env=env,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                out, err = proc.communicate(timeout=360)
            except subprocess.TimeoutExpired:
                subprocess.run([str(windows / "System32/taskkill.exe"), "/PID", str(proc.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, check=False)
                proc.communicate(timeout=20)
                raise AssertionError("Native tool fixture timed out")
            if proc.returncode or m.MODEL_ERRORS or DONE.encode() not in out:
                print(out.decode("utf-8", "replace")[-12000:])
                print(err.decode("utf-8", "replace")[-12000:])
                raise AssertionError(f"Native fixture failed: {mode}; exit={proc.returncode}; errors={m.MODEL_ERRORS}")
            assert len(m.MODEL_REQUESTS) == 2
            cfg = tomllib.loads((fixture / "home/config.toml").read_text(encoding="utf-8-sig"))
            assert "portable_browser" not in cfg.get("mcp_servers", {})
            assert cfg["model"] == model
            assert cfg["sandbox_mode"] == ("danger-full-access" if mode == "browser" else "workspace-write")
            if mode == "browser":
                assert (fixture / "cache/browser/profile").is_dir()
            print("NATIVE_SKILL_AND_TOOL_DISCOVERY=PASS mode=" + mode + " model=" + model, flush=True)


if __name__ == "__main__":
    main()
