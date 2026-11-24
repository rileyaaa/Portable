"""Native core tool audit, Windows only; ADB and PSModulePath are separate known gates.

Do not execute ADB again: its pinned Windows native home API can touch the host
profile even for version. Record PSModulePath startup drift separately rather
than treating it as a lost Codex variable or claiming strict isolation.
"""
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tomllib
import uuid

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
TOOL_MARKER = "PORTABLE_CORE_TOOLS_EXECUTED_0172"
BROWSER_MARKER = "PORTABLE_TASK_RENDERED_0172"
BROWSER_CHECK_MARKER = "PORTABLE_BROWSER_CHECK_READ_ONLY_0172"
DOCUMENT_MARKER = "PORTABLE_DOCUMENT_ROUNDTRIP_0172"
DONE = "native-tool-discovery-ok"

PROBE_PY = '''
import importlib, os, pathlib, site, sys, tomllib
root = pathlib.Path(os.environ["CODEX_INSTALL_DIR"]).resolve()
cfg = tomllib.loads((root / "home/config.toml").read_text(encoding="utf-8-sig"))
expected = cfg["shell_environment_policy"]["set"]
different = []
for key, value in expected.items():
    actual = os.environ.get(key)
    if actual is None:
        different.append(key + ":missing")
    elif actual != value and os.path.normcase(actual) != os.path.normcase(value):
        if key == "PSModulePath":
            # PowerShell reconstructs this variable at startup. Preserve the
            # expected entries and print the actual extra paths as evidence;
            # this is NOT a strict module-isolation pass.
            normalize = lambda v: os.path.normcase(os.path.normpath(v))
            expected_paths = {normalize(p) for p in value.split(";") if p}
            actual_paths = {normalize(p) for p in actual.split(";") if p}
            print("PSMODULEPATH_EXPECTED=" + ascii(value), flush=True)
            print("PSMODULEPATH_ACTUAL=" + ascii(actual), flush=True)
            print("PSMODULEPATH_STARTUP_EXTRA=" + ascii(sorted(actual_paths - expected_paths)), flush=True)
            print("PSMODULEPATH_ISOLATION=UNRESOLVED", flush=True)
            if not expected_paths.issubset(actual_paths):
                different.append(key + ":missing-configured-path")
        else:
            different.append(key + ":different")
print("ENV_DIFFERENCES=" + ",".join(different) if different else
      "ENV_CORE_CONFIG_VALUES_MATCH=" + str(len(expected) - ("PSModulePath" in expected)), flush=True)
if os.environ.get("PSModulePath") == expected.get("PSModulePath"):
    print("PSMODULEPATH_ISOLATION=EXACT", flush=True)
assert pathlib.Path(sys.executable).resolve() == root / "tool/python/python.exe"
assert os.environ["CODEX_HOME"].lower() == str(root / "home").lower()
assert os.environ["CODEX_PYTHON"].lower() == str(root / "tool/python/python.exe").lower()
assert os.environ["PIP_CONFIG_FILE"].lower() == "nul"
# Variables reaching a process need not be used by the isolated interpreter.
print("PYTHON_IGNORE_ENVIRONMENT=" + str(sys.flags.ignore_environment), flush=True)
print("PYTHONUSERBASE_EFFECTIVE=" + ascii(site.getuserbase()), flush=True)
print("PYTHONPYCACHEPREFIX_EFFECTIVE=" + ascii(sys.pycache_prefix), flush=True)
assert site.getuserbase() is not None and pathlib.Path(site.getuserbase()).resolve() == pathlib.Path(os.environ["PYTHONUSERBASE"]).resolve()
# Test both a protected package file and an outside-workspace file that exist
# only in this disposable synthetic extraction. Never write real host files.
for sentinel in (root / "protected-audit.txt", root.parent / "outside-workspace-audit.txt"):
    try:
        with sentinel.open("wb") as stream:
            stream.write(b"unexpected sandbox write")
    except PermissionError:
        print("SANDBOX_WRITE_DENIED=" + sentinel.name, flush=True)
    else:
        raise AssertionError("Common-mode sandbox permitted write: " + sentinel.name)
for name in ("pip", "requests", "httpx", "bs4", "lxml", "pandas", "numpy", "openpyxl",
             "docx", "pptx", "PIL", "xlsxwriter", "socks", "defusedxml", "fitz",
             "pymupdf4llm", "PyInstaller"):
    module = importlib.import_module(name)
    assert pathlib.Path(module.__file__).resolve().is_relative_to(root / "tool/python"), name
print("BUNDLED_PYTHON_IMPORTS_OK", flush=True)
if different:
    raise SystemExit(9)
'''
# This tiny file distinguishes native .ps1 resolution from the work performed
# by a longer probe. Do not use unrestricted .NET methods under CLM.
RESOLUTION_PS = "Write-Output 'PORTABLE_SCRIPT_RESOLVED_0172'\n"
PROBE_PS = r'''
$ErrorActionPreference = 'Stop'
$root = $env:CODEX_INSTALL_DIR
$prefix = $root + '\'
$script:ToolProbeFailures = @()
function Test-BundledCommand([string]$name) {
    try {
        $entry = Get-Command -Name $name -CommandType Application -ErrorAction Stop | Select-Object -First 1
        $source = [string]$entry.Source
        if ($source.Length -lt $prefix.Length -or $source.Substring(0,$prefix.Length) -ine $prefix) {
            throw ('Host fallback: ' + $source)
        }
        Write-Output ('TOOL_RESOLVED_' + $name + '=' + $source)
    } catch {
        $script:ToolProbeFailures += $name
        Write-Output ('TOOL_RESOLUTION_ERROR_' + $name + '=' + $_.FullyQualifiedErrorId + '; ' + $_.Exception.Message)
    }
}
foreach ($name in @('python.exe','pip.cmd','node.exe','npm.cmd','rg.exe','fd.exe','jq.exe','7z.exe')) {
    Test-BundledCommand $name
}
function Run-Checked([string]$name, [string[]]$argv) {
    try {
        & $name @argv
        if ($LASTEXITCODE -ne 0) { throw ('Tool exit=' + $LASTEXITCODE) }
        Write-Output ('TOOL_RAN=' + $name)
    } catch {
        $script:ToolProbeFailures += $name
        Write-Output ('TOOL_RUN_ERROR_' + $name + '=' + $_.FullyQualifiedErrorId + '; ' + $_.Exception.Message)
    }
}
# Do not invoke a name that has failed package-local resolution.
if ($script:ToolProbeFailures.Count -eq 0) {
    Run-Checked 'node.exe' @('--version')
    Run-Checked 'npm.cmd' @('--version')
    Run-Checked 'pip.cmd' @('--version')
    Run-Checked 'rg.exe' @('--version')
    Run-Checked 'fd.exe' @('--version')
    Run-Checked 'jq.exe' @('--version')
    # Exercise 7-Zip without flooding the model's output token budget.
    (& '7z.exe' 'i') | Select-Object -First 5
    if ($LASTEXITCODE -ne 0) { throw ('7z exit=' + $LASTEXITCODE) }
    Write-Output 'TOOL_RAN=7z.exe'
    # The actual CLI must resolve the selected portable values, not merely
    # inherit environment names. These queries do not download or install.
    function Check-ToolConfig([string]$name, [string[]]$argv, [string]$expected, [string]$label) {
        try {
            $actual = (& $name @argv | Out-String).Trim()
            if ($LASTEXITCODE -ne 0) { throw ('Config query exit=' + $LASTEXITCODE) }
            if ($actual -ine $expected) { throw ('Expected ' + $expected + '; actual ' + $actual) }
            Write-Output ('TOOL_CONFIG_EFFECTIVE=' + $label)
        } catch {
            $script:ToolProbeFailures += $label
            Write-Output ('TOOL_CONFIG_ERROR=' + $label + '; ' + $_.Exception.Message)
        }
    }
    Check-ToolConfig 'pip.cmd' @('cache','dir') $env:PIP_CACHE_DIR 'PIP_CACHE_DIR'
    Check-ToolConfig 'npm.cmd' @('config','get','cache') $env:NPM_CONFIG_CACHE 'NPM_CONFIG_CACHE'
    # Existing wrapper intentionally forces local prefix to the task cwd.
    # Only an explicitly global command consumes NPM_CONFIG_PREFIX.
    Check-ToolConfig 'npm.cmd' @('config','get','prefix') (Get-Location).Path 'NPM_LOCAL_PREFIX'
    Check-ToolConfig 'npm.cmd' @('config','get','prefix','--global') $env:NPM_CONFIG_PREFIX 'NPM_CONFIG_PREFIX'
    Check-ToolConfig 'npm.cmd' @('config','get','userconfig') $env:NPM_CONFIG_USERCONFIG 'NPM_CONFIG_USERCONFIG'
    Check-ToolConfig 'npm.cmd' @('config','get','globalconfig') $env:NPM_CONFIG_GLOBALCONFIG 'NPM_CONFIG_GLOBALCONFIG'
}
# ADB is deliberately NOT invoked: previous real Windows results already
# showed that even version can try to create a real host profile directory.
# Verify its package-local file exists, not that it can run portably.
if (-not (Test-Path -LiteralPath ($root + '\tool\android\platform-tools\adb.exe') -PathType Leaf)) { throw 'Missing bundled ADB' }
Write-Output 'ADB_PORTABLE_EXECUTION=BLOCKED_KNOWN_HOST_PROFILE_BEHAVIOR'
# A stock PowerShell engine reconstructs module paths at startup. Demonstrate
# the existing command-local correction without inspecting host module folders
# or modifying a user/machine setting. Restore the original before the env audit.
$savedModulePath = $env:PSModulePath
try {
    $scopedModulePath = ($root + '\cache\powershell\modules;' + $PSHOME + '\Modules')
    $env:PSModulePath = $scopedModulePath
    & ($root + '\tool\python\python.exe') -B -c 'import os,sys; assert os.environ["PSModulePath"] == sys.argv[1]; print("PSMODULEPATH_TASK_LOCAL_RESET=PASS")' $scopedModulePath
    if ($LASTEXITCODE -ne 0) { throw ('Scoped module path probe exit=' + $LASTEXITCODE) }
} finally {
    $env:PSModulePath = $savedModulePath
}
# This absolute path is rooted in the already-verified disposable fixture.
Run-Checked ($root + '\tool\python\python.exe') @('-B', ($root + '\work\tool-probe\probe.py'))
if ($script:ToolProbeFailures.Count -ne 0) { throw ('Tool probe failures: ' + ($script:ToolProbeFailures -join ', ')) }
Write-Output 'PORTABLE_CORE_TOOLS_EXECUTED_0172'
'''
# Observe the actual restricted shell, not a different unrestricted process.
# Keep every operation independent; diagnostic failures must never mask later
# observations. Use CLM-compatible cmdlets, primitive strings and error fields.
DIAG_PS = r'''
$ErrorActionPreference = 'Stop'
Write-Output ('DIAG_CWD=' + (Get-Location).Path)
Write-Output ('DIAG_PROCESS_CWD=' + [Environment]::CurrentDirectory)
Write-Output ('DIAG_PS=' + $PSVersionTable.PSVersion + ';LANG=' + $ExecutionContext.SessionState.LanguageMode)
Write-Output ('DIAG_INSTALL_DIR=' + $env:CODEX_INSTALL_DIR)
$expectedRoot = '__EXPECTED_ROOT__'
if ($env:CODEX_INSTALL_DIR -ne $expectedRoot) { throw 'Unexpected package root; stop' }
$work = $expectedRoot + '\work'
$target = $work + '\tool-probe\probe.ps1'
$relative = '.\tool-probe\probe.ps1'
function Observe([string]$label, [scriptblock]$operation) {
    try {
        $result = & $operation
        Write-Output ('DIAG_' + $label + '=OK ' + ($result -join '; '))
    } catch {
        Write-Output ('DIAG_' + $label + '=ERROR ' + $_.FullyQualifiedErrorId + '; ' + $_.Exception.Message)
    }
}
Observe 'DRIVES' { Get-PSDrive -PSProvider FileSystem | Select-Object -ExpandProperty Root }
Observe 'WORK' { if (-not (Test-Path -LiteralPath $work -PathType Container -ErrorAction Stop)) { throw 'work missing' }; 'present' }
Observe 'TARGET_ABS' { if (-not (Test-Path -LiteralPath $target -PathType Leaf -ErrorAction Stop)) { throw 'script missing' }; 'present' }
Observe 'ITEM' { (Get-Item -LiteralPath $target -ErrorAction Stop).FullName }
Observe 'READ' { Get-Content -LiteralPath $target -TotalCount 1 -ErrorAction Stop }
Observe 'SKILL_READ' { Get-Content -LiteralPath ($expectedRoot + '\home\skills\browser-debug\SKILL.md') -TotalCount 2 -ErrorAction Stop }
Observe 'NATIVE_FILE' {
    & ($expectedRoot + '\tool\python\python.exe') -B -c 'import os,sys; print("NATIVE_FILE_EXISTS="+str(os.path.isfile(sys.argv[1]))); print("NATIVE_CWD="+ascii(os.getcwd())); sys.exit(0 if os.path.isfile(sys.argv[1]) else 2)' $target
    if ($LASTEXITCODE -ne 0) { throw ('Python native file check exit=' + $LASTEXITCODE) }
}
Observe 'SET_LOCATION' { Set-Location -LiteralPath $work -ErrorAction Stop; (Get-Location).Path }
Observe 'TARGET_REL' { if (-not (Test-Path -LiteralPath $relative -PathType Leaf -ErrorAction Stop)) { throw 'relative script missing' }; 'present' }
Observe 'RESOLVE_COMMAND' { (Get-Command -Name $target -ErrorAction Stop).Source }
Observe 'WORK_WRITE' {
    $own = $work + '\tool-probe\native-created.txt'
    if (Test-Path -LiteralPath $own) { throw 'Unexpected existing test file' }
    Set-Content -LiteralPath $own -Value 'owned-write' -Encoding UTF8 -ErrorAction Stop
    Get-Content -LiteralPath $own -ErrorAction Stop
}
Observe 'RELATIVE_SCRIPT' { & $relative; if (-not $?) { throw 'relative script failed' } }
Observe 'ABSOLUTE_SCRIPT' { & $target; if (-not $?) { throw 'absolute script failed' } }
# Run the real tool probe inline even if .ps1 resolution failed. Passing this
# probe is not allowed to hide any of the required file/script assertions.
Write-Output 'DIAG_BEGIN_INLINE_TOOL_PROBE'
'''

BROWSER_PS = r'''
$ErrorActionPreference = 'Stop'
$entry = Join-Path $env:CODEX_INSTALL_DIR 'tool/automation/start-browser.ps1'
$engine = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
& $engine -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $entry -TaskAuthorized -Workspace 'work/tool-probe' -TaskScript 'work/tool-probe/page.cjs'
exit $LASTEXITCODE
'''
# Discover the installed browser from the actual normal-mode Codex shell.
# -Check must not create the persistent browser profile or its lock.
BROWSER_CHECK_PS = r'''
$ErrorActionPreference = 'Stop'
$root = $env:CODEX_INSTALL_DIR
$entry = Join-Path $root 'tool/automation/start-browser.ps1'
$engine = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
$result = & $engine -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $entry -Check -Workspace 'work/tool-probe' -TaskScript 'work/tool-probe/page.cjs'
if ($LASTEXITCODE -ne 0) { throw ('Browser read-only check exit=' + $LASTEXITCODE) }
$data = ($result -join [Environment]::NewLine) | ConvertFrom-Json
if ($data.PackageRoot -ine $root -or $data.Workspace -ine (Join-Path $root 'work\tool-probe')) { throw 'Browser check resolved wrong root/workspace' }
if (-not $data.BrowserPresent -or -not $data.PersistentProfile -or $data.AutomaticStart -or $data.Mode -ne 'task-script') { throw 'Browser check did not describe the existing task route' }
if ($data.BrowserDataDirectory -ine (Join-Path $root 'cache\browser')) { throw 'Wrong browser data directory' }
Write-Output ('BROWSER_CHECK_VERSION=' + $data.BrowserVersion)
Write-Output ('BROWSER_CHECK_EXECUTABLE=' + $data.BrowserExecutable)
Write-Output 'PORTABLE_BROWSER_CHECK_READ_ONLY_0172'
'''

BROWSER_JS = '''
module.exports = async ({page}) => {
  await page.setContent('<title>PORTABLE_TASK_RENDERED_0172</title><button>Local test</button>');
  await page.getByRole('button', {name: 'Local test'}).click();
  return {title: await page.title()};
};
'''


# Real bundled authoring and reading libraries, in the restricted native shell.
# This does not exercise optional Office renderers, OCR, or formula calculation.
DOCUMENTS_PY = r'''
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import docx
import openpyxl
import pandas
import pptx
import pymupdf
from pptx.util import Inches

root = Path(os.environ["CODEX_INSTALL_DIR"]).resolve()
assert Path(sys.executable).resolve() == root / "tool/python/python.exe"
for module in (docx, openpyxl, pandas, pptx, pymupdf):
    assert Path(module.__file__).resolve().is_relative_to(root / "tool/python"), module.__name__
work = root / "work/tool-probe"
output = work / "document-results"
output.mkdir()
label = "Portable \u4fbf\u643a 0172"

# Word: write/reopen, Unicode text and path.
word = output / "\u4fbf\u643a.docx"
document = docx.Document()
document.add_paragraph(label)
table = document.add_table(rows=1, cols=2)
table.cell(0, 0).text = "value"
table.cell(0, 1).text = "172"
document.save(word)
reopened = docx.Document(word)
assert reopened.paragraphs[0].text == label
assert reopened.tables[0].cell(0, 1).text == "172"
print("NATIVE_DOCX_WRITE_READ=PASS", flush=True)

# Excel: preserve formulas; read ordinary tabular data with pandas.
book = output / "\u4fbf\u643a.xlsx"
workbook = openpyxl.Workbook()
sheet = workbook.active
sheet.title = "Data"
sheet.append(["Name", "Amount"])
sheet.append([label, 172])
sheet.append(["Second", 3])
sheet["D2"] = "=SUM(B2:B3)"
workbook.save(book)
with_formula = openpyxl.load_workbook(book, data_only=False)
assert with_formula["Data"]["D2"].value == "=SUM(B2:B3)"
with_formula.close()
frame = pandas.read_excel(book, sheet_name="Data", usecols="A:B")
assert frame["Name"].iloc[0] == label and int(frame["Amount"].sum()) == 175
print("NATIVE_XLSX_WRITE_READ_FORMULA_PRESERVED=PASS (not recalculated)", flush=True)

# PowerPoint: write and reopen without launching any desktop application.
deck = output / "\u4fbf\u643a.pptx"
presentation = pptx.Presentation()
slide = presentation.slides.add_slide(presentation.slide_layouts[6])
box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1))
box.text_frame.text = label
presentation.save(deck)
assert pptx.Presentation(deck).slides[0].shapes[0].text_frame.text == label
print("NATIVE_PPTX_WRITE_READ=PASS", flush=True)

# PDF: create a synthetic manual with actual selectable text.
manuals = output / "manuals"
manuals.mkdir()
filename = "\u4fbf\u643a-manual.pdf"
manual = manuals / filename
marker = "PORTABLE_MANUAL_SYMBOL_0172"
with pymupdf.open() as pdf:
    page = pdf.new_page()
    page.insert_text((50, 70), marker + "\nSELECT * FROM V$DATABASE;", fontname="cour", fontsize=11)
    pdf.save(manual)
with pymupdf.open(manual) as pdf:
    assert len(pdf) == 1 and marker in pdf[0].get_text()
    assert pdf[0].get_pixmap(matrix=pymupdf.Matrix(0.5, 0.5)).width > 0
print("NATIVE_PDF_WRITE_READ_RENDER=PASS", flush=True)

# Actual skill entrypoint in a separate process, from the default work cwd.
# No -X utf8 or PYTHONIOENCODING workaround: test the shipped CLI behavior.
tool = root / "home/skills/pdf-library/scripts/pdf_library.py"
library = output / "library"
archive = output / "manuals.zip"
def invoke(*args):
    p = subprocess.run([sys.executable, "-B", str(tool), *map(str, args)],
                       cwd=root / "work", capture_output=True, timeout=90, check=False)
    if p.returncode:
        raise AssertionError("PDF library " + str(args[0]) + " exit=" + str(p.returncode)
                             + "; " + ascii(p.stderr.decode("utf-8", "replace")[-2500:]))
    return p.stdout.decode("utf-8", "strict")

summary = json.loads(invoke("build", "--input", manuals, "--library", library, "--strict"))
assert summary["strict_ok"], summary
hits = json.loads(invoke("search", "--library", library, "--query", marker))
assert len(hits) == 1 and hits[0]["document"] == filename and hits[0]["page"] == 1
text = invoke("read", "--library", library, "--document", filename, "--pages", "1")
assert marker in text and "## PDF \u7b2c 1 \u9875" in text
assert json.loads(invoke("verify", "--library", library, "--strict"))["strict_ok"]
receipt = json.loads(invoke("export", "--library", library, "--output", archive, "--strict"))
assert receipt["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None and all(n.endswith(".md") for n in z.namelist())
    assert marker in z.read("manuals/" + Path(filename).stem + ".md").decode("utf-8")
print("NATIVE_PDF_LIBRARY_BUILD_SEARCH_READ_VERIFY_EXPORT=PASS", flush=True)

for path in (word, book, deck):
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
print("PORTABLE_DOCUMENT_ROUNDTRIP_0172", flush=True)
'''

def handler_for(fixture, mode):
    expected = {"browser": BROWSER_MARKER, "browser-check": BROWSER_CHECK_MARKER,
                "documents": DOCUMENT_MARKER}.get(mode, TOOL_MARKER)
    script = {"browser": "browser.ps1", "browser-check": "browser-check.ps1"}.get(mode, "probe.ps1")

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
                       if mode in {"browser", "browser-check"} else DIAG_PS.replace("__EXPECTED_ROOT__", str(fixture).replace("'", "''")) + "\n" + PROBE_PS)
            if mode == "documents":
                command = ("& (Join-Path $env:CODEX_INSTALL_DIR 'tool/python/python.exe') -B "
                           "(Join-Path $env:CODEX_INSTALL_DIR 'work/tool-probe/documents.py'); exit $LASTEXITCODE")
            args = {"cmd": command, "workdir": str(fixture / "work"), "login": False,
                    "yield_time_ms": 30000, "max_output_tokens": 7000}
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
        assert expected in evidence, "Real tool output did not contain success marker: " + expected
        assert "ENV_DIFFERENCES=" not in evidence, "Actual child environment differs from generated policy"
        if mode in {"normal", "unknown"}:
            required = (
                "DIAG_WORK=OK present", "DIAG_TARGET_ABS=OK present",
                "DIAG_SKILL_READ=OK", "name: browser-debug",
                "NATIVE_FILE_EXISTS=True", "DIAG_SET_LOCATION=OK",
                "DIAG_TARGET_REL=OK present", "DIAG_WORK_WRITE=OK owned-write",
                "DIAG_RELATIVE_SCRIPT=OK PORTABLE_SCRIPT_RESOLVED_0172",
                "DIAG_ABSOLUTE_SCRIPT=OK PORTABLE_SCRIPT_RESOLVED_0172",
                "SANDBOX_WRITE_DENIED=protected-audit.txt",
                "SANDBOX_WRITE_DENIED=outside-workspace-audit.txt",
                "TOOL_CONFIG_EFFECTIVE=PIP_CACHE_DIR",
                "TOOL_CONFIG_EFFECTIVE=NPM_CONFIG_CACHE",
                "TOOL_CONFIG_EFFECTIVE=NPM_LOCAL_PREFIX",
                "TOOL_CONFIG_EFFECTIVE=NPM_CONFIG_PREFIX",
                "TOOL_CONFIG_EFFECTIVE=NPM_CONFIG_USERCONFIG",
                "TOOL_CONFIG_EFFECTIVE=NPM_CONFIG_GLOBALCONFIG",
                "PSMODULEPATH_ISOLATION=", "PSMODULEPATH_TASK_LOCAL_RESET=PASS",
                "ADB_PORTABLE_EXECUTION=BLOCKED_",
            )
            missing = [marker for marker in required if marker not in evidence]
            assert not missing, "Required native diagnostics failed: " + ", ".join(missing)
        return {"id": "msg_probe", "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": DONE, "annotations": []}]}
    return handler


@contextlib.contextmanager
def extracted_package_fixture(parent, label):
    """Model a normal extracted Windows directory, not a private Python temp.

    CPython 3.13+ creates 0o700 directories with protected SYSTEM/admin/owner
    ACLs. tempfile.TemporaryDirectory uses that mode, unlike a normal ZIP
    extraction. An elevated CI token may own it as Administrators, and the
    unelevated Codex token cannot necessarily read it. Never change the ACL of
    the parent, checkout, or a user's package to make this test pass.
    """
    m.ordinary(parent)
    owned = parent / ("native-tools-" + label + "-" + uuid.uuid4().hex)
    owned.mkdir()  # Default 0o777 on Windows: inherit the existing parent ACL.
    try:
        m.ordinary(owned)
        yield owned
    finally:
        m.ordinary(owned)
        shutil.rmtree(owned)


def fixture_acl_evidence(owned, fixture):
    # Only inspect this disposable synthetic fixture, using trusted Windows
    # system executables. No ACL change, and no user profile/host scan.
    icacls = Path(os.environ["SystemRoot"]) / "System32/icacls.exe"
    for p in (owned, fixture, fixture / "work", fixture / "tool/python/python.exe"):
        result = subprocess.run([str(icacls), str(p)], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=20, check=False)
        print("FIXTURE_ACL=" + ascii(str(p)) + " exit=" + str(result.returncode)
              + " " + result.stdout.decode("utf-8", "backslashreplace"), flush=True)
        assert result.returncode == 0, "Cannot inspect synthetic extraction ACL"


def main():
    if os.name != "nt":
        raise SystemExit("Windows x64 required")
    mode = sys.argv[1] if len(sys.argv) == 2 else "normal"
    assert mode in {"normal", "browser", "browser-check", "unknown", "documents"}
    model = {"normal": "gpt-6-sol", "browser": "gpt-6.2-sol", "browser-check": "gpt-6.2-sol",
             "unknown": "portable-synthetic-model", "documents": "gpt-6.2-sol"}[mode]
    for p in (*reversed(ROOT.parents), ROOT):
        m.ordinary(p)
    scratch = ROOT / "tmp"
    scratch.mkdir(exist_ok=True)
    m.ordinary(scratch)
    with extracted_package_fixture(scratch, mode) as owned:
        fixture = owned / ("Relocated \u4fbf\u643a Portable" if mode in {"unknown", "documents"} else "Relocated Portable")
        fixture.mkdir()
        manifest = json.loads((ROOT / "tool/runtime-manifest.json").read_text(encoding="utf-8-sig"))
        bat = "\u542f\u52a8Codex.bat"
        for relative in ("env.ps1", "run-codex.ps1", bat, "tool/runtime-manifest.json",
                         "tool/portable-process.ps1", "tool/python", "tool/node", "tool/bin",
                         "tool/android/platform-tools", "home/skills", *manifest["files"]):
            m.copy_input(relative, fixture)
        if mode in {"browser", "browser-check"}:
            m.copy_input("tool/automation", fixture)
        if mode == "browser":
            source = ROOT / "Version_History/YOLO mode\u4e13\u7528\u5305-env.ps1"
            m.ordinary(source)
            (fixture / "env.ps1").write_bytes(source.read_bytes())
        (fixture / "codex-resources").mkdir()
        probe = fixture / "work/tool-probe"
        probe.mkdir(parents=True)
        (probe / "probe.py").write_text(PROBE_PY, encoding="utf-8")
        (probe / "probe.ps1").write_text(RESOLUTION_PS, encoding="utf-8-sig")
        (probe / "browser.ps1").write_text(BROWSER_PS, encoding="utf-8-sig")
        (probe / "browser-check.ps1").write_text(BROWSER_CHECK_PS, encoding="utf-8-sig")
        if mode == "documents":
            (probe / "documents.py").write_text(DOCUMENTS_PY, encoding="utf-8")
        (probe / "page.cjs").write_text(BROWSER_JS, encoding="utf-8")
        for sentinel in (fixture / "protected-audit.txt", owned / "outside-workspace-audit.txt"):
            sentinel.write_bytes(b"unchanged synthetic sentinel")
        fixture_acl_evidence(owned, fixture)
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
            # CLI --json events record the actual native command exit status,
            # rather than guessing it from marker text or escaped JSON.
            exits = []
            for line in out.decode("utf-8", "replace").splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                item = event.get("item", {}) if isinstance(event, dict) else {}
                if event.get("type") == "item.completed" and item.get("type") == "command_execution":
                    exits.append(item.get("exit_code"))
            assert exits and all(code == 0 for code in exits), "Native command exits: " + repr(exits)
            if mode in {"normal", "unknown"}:
                assert (probe / "native-created.txt").read_text(encoding="utf-8-sig").strip() == "owned-write"
                for sentinel in (fixture / "protected-audit.txt", owned / "outside-workspace-audit.txt"):
                    assert sentinel.read_bytes() == b"unchanged synthetic sentinel", "Sandbox changed " + sentinel.name
            cfg = tomllib.loads((fixture / "home/config.toml").read_text(encoding="utf-8-sig"))
            assert "portable_browser" not in cfg.get("mcp_servers", {})
            assert cfg["model"] == model
            assert cfg["sandbox_mode"] == ("danger-full-access" if mode == "browser" else "workspace-write")
            assert cfg["approval_policy"] == ("never" if mode == "browser" else "on-request")
            assert cfg["sandbox_workspace_write"]["network_access"] == (mode == "browser")
            if mode == "browser":
                assert (fixture / "cache/browser/profile").is_dir()
            if mode == "documents":
                outputs = probe / "document-results"
                for filename in ("\u4fbf\u643a.docx", "\u4fbf\u643a.xlsx", "\u4fbf\u643a.pptx", "manuals.zip"):
                    assert (outputs / filename).is_file(), "Missing native document output: " + filename
                assert (outputs / "manuals/\u4fbf\u643a-manual.pdf").is_file()
                print("NORMAL_MODE_DOCUMENT_ROUNDTRIP=PASS; optional renderers/OCR and formula calculation not tested", flush=True)
            if mode == "browser-check":
                assert not (fixture / "cache/browser").exists(), "Read-only check created persistent browser state"
                assert not (fixture / ".codex-browser.instance.lock").exists(), "Read-only check created browser lock"
                print("NORMAL_MODE_BROWSER_DISCOVERY_READ_ONLY=PASS; interactive task approval still separate", flush=True)
            print("NATIVE_CORE_SKILL_AND_TOOL_DISCOVERY=PASS mode=" + mode + " model=" + model, flush=True)
            if mode in {"normal", "unknown"}:
                print("CORE_PASS_NOT_FULL_PORTABILITY: ADB and PSModulePath require separate resolution", flush=True)


if __name__ == "__main__":
    main()
