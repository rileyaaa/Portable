#!/usr/bin/env python3
"""Manual Windows integration gate using the *real* full-stable staging functions.

Unlike the fast Ubuntu JSON-only preflight, this actually installs npm/Corepack,
runs Playwright npm ci, stages pinned CPython 3.15 wheels, verifies wheel and
license manifests, runs native PDF conversion, refreshes CLI shims and extracts
7-Zip. The original source checkout, installed ledger and release are untouched.
Chromium, LFS hydration, full release ZIP and ten audit rounds are not run.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

SOURCE = Path(__file__).resolve().parent.parent
PLAN = SOURCE / "tool/full-stable-upgrade-plan.json"
NODE_VERSION = "26.13.0"
# A *non-executable* scratch marker: the portable npm JS checks for Codex's
# file's presence, not its bytes. The real codex.exe remains protected by LFS
# and release SHA gates; never fetch or execute it in this quick diagnostic.
DIAGNOSTIC_CODEX_MARKER = b"NOT_A_CODEX_EXECUTABLE__NATIVE_DIAGNOSTIC_ONLY\n"
BOOTSTRAP_FILES = ("codex.exe", "env.ps1", "tool/node/node.exe",
                   "tool/node/portable-npm.js")
COPY_FILES = (
    "env.ps1",
    "tool/python-packages.in.txt",
    "tool/python-ssh-packages.in.txt",
    "tool/optional-python-manifest.json",
    "tool/refresh-python-cli-shims.py",
    "tool/bin/portable-python-cli.py",
    "tool/bin/7z.exe",
    "tool/bin/7z.dll",
    "tool/node/portable-npm.js",
    "tool/node/npm",
    "tool/node/npm.cmd",
    "tool/node/npm.ps1",
    "tool/node/npx",
    "tool/node/npx.cmd",
    "tool/node/npx.ps1",
    "tool/node/corepack",
    "tool/node/corepack.cmd",
)


def real_stager():
    target = SOURCE / "tool/full-stable-prepare.py"
    spec = importlib.util.spec_from_file_location("portable_native_diagnostic_stage", target)
    if spec is None or spec.loader is None:
        raise ValueError("Missing reviewed full tool stager")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def copy_plain(source: Path, destination: Path) -> None:
    if not source.is_file() or source.is_symlink() or (
            getattr(source.lstat(), "st_file_attributes", 0) & 0x400):
        raise ValueError("Diagnostic source file missing or linked: " + str(source))
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def verify_portable_bootstrap(root: Path) -> str:
    """Detect missing npm launcher layout *before* a slow Windows CMD attempt."""
    for name in BOOTSTRAP_FILES:
        item = root / name
        if not item.is_file() or item.is_symlink() or item.stat().st_nlink != 1:
            raise ValueError("Isolated portable npm bootstrap marker missing: " + name)
    if (root / "codex.exe").read_bytes() != DIAGNOSTIC_CODEX_MARKER:
        raise ValueError("Unexpected diagnostic Codex marker; no binary may be executed")
    for name in ("home-runtime/.npmrc", "cache/npm/global.npmrc"):
        item = root / name
        if not item.is_file() or item.stat().st_size != 0:
            raise ValueError("Isolated npm configuration file missing or non-empty: " + name)
    return "Package-local npm root markers and independent blank configs checked"


def sandbox_from_checkout(root: Path, *, node_executable: Path) -> Path:
    """Make a *minimal* disposable tool tree, excluding old Python and Chromium."""
    if root.exists() or root.is_symlink():
        raise ValueError("Diagnostic scratch root must be new")
    node_executable = node_executable.resolve(strict=True)
    if node_executable.name.lower() != "node.exe":
        raise ValueError("Expected the verified Windows x64 Node executable")
    root.mkdir(parents=True)
    for relative in COPY_FILES:
        copy_plain(SOURCE / relative, root / relative)
    copy_plain(node_executable, root / "tool/node/node.exe")
    # The actual npm.cmd -> portable-npm.js launcher's mandatory root markers
    # are codex.exe, env.ps1, node.exe and portable-npm.js. The previous
    # diagnostic omitted the first two, causing ENOENT before npm was started.
    # The synthetic Codex marker is intentionally NOT a runnable PE file.
    (root / "codex.exe").write_bytes(DIAGNOSTIC_CODEX_MARKER)
    for directory in ("tool/node/node_modules/npm", "tool/node/node_modules/corepack",
                      "tool/automation/playwright", "tool/python", "work/npm",
                      "work/python", "work/7zip", "tmp", "home-runtime",
                      "appdata", "localappdata", "localappdata/state",
                      "programdata", "cache/npm", "cache/npm-prefix", "cache/xdg"):
        (root / directory).mkdir(parents=True)
    (root / "home-runtime/.npmrc").write_bytes(b"")
    (root / "cache/npm/global.npmrc").write_bytes(b"")
    verify_portable_bootstrap(root)
    return root / "tool"


def record(records: list[dict], name: str, action, *, after: tuple[str, ...] = ()) -> bool:
    """Keep probing independent steps. Never call a dependent stage after failure."""
    status = {item["probe"]: item["status"] for item in records}
    blocked = [item for item in after if status.get(item) != "PASS"]
    if blocked:
        result = {"probe": name, "status": "BLOCKED",
                  "detail": "Upstream native stage failed: " + ", ".join(blocked),
                  "seconds": 0.0}
        records.append(result)
        print("NATIVE_DIAGNOSE_BLOCKED=" + name + ": " + result["detail"], flush=True)
        return False
    start = time.monotonic()
    try:
        detail = str(action() or "Verified original full-stable stage in isolated scratch")
        outcome = "PASS"
    except Exception as exc:
        detail = (type(exc).__name__ + ": " + str(exc))[-1700:]
        outcome = "FAIL"
    result = {"probe": name, "status": outcome, "detail": detail[:1700],
              "seconds": round(time.monotonic() - start, 2)}
    records.append(result)
    print("NATIVE_DIAGNOSE_" + outcome + "=" + name + ";seconds=" +
          str(result["seconds"]) + ": " + detail.replace("\n", " ")[:400], flush=True)
    return outcome == "PASS"


def verify_pdf_exception(stage, plan: dict, evidence: dict) -> str:
    """Use precisely the full upgrade's reviewed PDF fallback contract."""
    stage.verify_pdf_compatibility_exception(plan, evidence)
    return "Official PDF policy: " + evidence["pdf_compatibility"]["mode"]


def check_node_version(node: Path) -> str:
    if os.name != "nt" or sys.maxsize < 2**32:
        raise ValueError("Native diagnosis requires Windows x64")
    result = subprocess.run([str(node), "--version"], check=True,
                            capture_output=True, text=True, timeout=20,
                            encoding="utf-8", errors="replace")
    if result.stdout.strip() != "v" + NODE_VERSION:
        raise ValueError("Expected Node " + NODE_VERSION + ", got " + result.stdout.strip())
    return "Windows Node " + NODE_VERSION + " (setup-node, not bundled LFS node)"


def check_python_shims(stage, root: Path, runtime: Path, folder: Path) -> str:
    """Exercise the same post-replacement CLI refresh, but only in scratch."""
    stage.replace_tree(runtime, root / "tool/python", folder)
    python = root / "tool/python/python.exe"
    stage.run(python, "-E", "-s", "-B", "-m", "pip", "--version")
    stage.run(python, "-E", "-s", "-B", "-m", "PyInstaller", "--version")
    stage.run(python, "-E", "-s", "-B", root / "tool/refresh-python-cli-shims.py")
    scripts = {item.name.casefold() for item in (root / "tool/bin").glob("*.cmd")}
    if not {"pip.cmd", "pyinstaller.cmd"} <= scripts:
        raise ValueError("Staged Python CMD wrappers missing pip or PyInstaller")
    # Exercise *actual* Windows launchers, including their PowerShell path
    # guard, rather than checking only that the generated files exist.
    stage.run(root / "tool/bin/pip.cmd", "--version", cwd=root)
    stage.run(root / "tool/bin/pyinstaller.cmd", "--version", cwd=root)
    return "Pinned pip/PyInstaller native imports and real Windows CMD wrappers passed"


def native_node_shims(stage, root: Path) -> str:
    """Execute package-local npm/npx/Corepack CMD, not just npm-cli.js."""
    for label in ("npm.cmd", "npx.cmd", "corepack.cmd"):
        launcher = root / "tool/node" / label
        if not launcher.is_file():
            raise ValueError("Missing portable Windows Node launcher: " + label)
        stage.run(launcher, "--version", cwd=root)
    return "Portable npm.cmd, npx.cmd and corepack.cmd native launchers passed"


def windows_tool_contracts() -> str:
    """Use the same real maintenance unit suite invoked before full staging."""
    command = [sys.executable, "-E", "-s", "-B", "-m", "unittest", "discover",
               "-s", "tests", "-p", "test_tool_updates.py", "-q"]
    completed = subprocess.run(command, cwd=SOURCE, capture_output=True,
                               text=True, timeout=120, check=False,
                               encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        raise ValueError("Windows maintenance regressions failed: " +
                         (completed.stdout + "\n" + completed.stderr)[-2300:])
    return "Existing real Windows tool-maintenance regression suite passed"


def execute(root: Path, stage, plan: dict, node: Path) -> list[dict]:
    """Batch independent Windows checks; never run full prepare or publish."""
    work = root / "work"
    evidence: dict = {}
    records: list[dict] = []
    record(records, "npm_bootstrap_layout", lambda: verify_portable_bootstrap(root))
    record(records, "windows_tool_contracts", windows_tool_contracts)
    record(records, "node26", lambda: check_node_version(node))
    record(records, "npm_corepack", lambda: stage.stage_npm(plan, work / "npm", evidence),
           after=("node26",))
    record(records, "portable_node_shims", lambda: native_node_shims(stage, root),
           after=("npm_corepack", "npm_bootstrap_layout"))
    record(records, "playwright_npm_ci",
           lambda: stage.stage_playwright(plan, work / "npm", evidence),
           after=("npm_corepack",))
    record(records, "pdf_policy",
           lambda: (stage.preflight_python315_onnxruntime(work / "python", evidence),
                    verify_pdf_exception(stage, plan, evidence))[1])
    built: dict = {}
    def build_python():
        runtime, resolved = stage.stage_python(plan, work / "python", evidence)
        built.update(runtime=runtime, resolved=resolved)
        return "Real official CPython 3.15 embedded runtime, pip wheel and full pinned closure"
    record(records, "python315_install", build_python, after=("pdf_policy",))
    record(records, "python_optional_manifest",
           lambda: stage.python_manifests(work / "python", built["resolved"], evidence,
                                          staged_site=built["runtime"] / "Lib/site-packages"),
           after=("python315_install",))
    record(records, "python_native_pdf",
           lambda: stage.smoke_staged_python(built["runtime"], evidence["pdf_compatibility"]),
           after=("python315_install",))
    record(records, "python_cli_shims",
           lambda: check_python_shims(stage, root, built["runtime"], work / "python"),
           after=("python315_install",))
    record(records, "sevenzip_amd64",
           lambda: stage.stage_7zip(plan, work / "7zip", evidence))
    return records


def write_report(records: list[dict]) -> int:
    bad = [item for item in records if item["status"] != "PASS"]
    print("NATIVE_DIAGNOSE_RESULT=" + ("FAIL" if bad else "PASS") + ";checked=" +
          str(len(records)) + ";failed_or_blocked=" + str(len(bad)), flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("\n### Windows native preflight (original staging functions)\n\n")
            for item in records:
                detail = item["detail"].replace("\n", " ").replace("|", "\\|")[:300]
                stream.write("- **" + item["status"] + "** " + item["probe"] +
                             " (" + str(item["seconds"]) + "s): " + detail + "\n")
            stream.write("\nSource checkout untouched. Browser payload, 19 PowerShell suites, "
                         "ten release audits and customer ZIP still require full verification. "
                         "Node comes from pinned setup-node 26.13.0, not Git LFS.\n")
    return 1 if bad else 0


def main() -> int:
    if os.name != "nt" or sys.maxsize <= 2**32:
        raise ValueError("This deep diagnostic must run in a Windows x64 job")
    stage = real_stager()
    plan = stage.obj(PLAN)
    if plan.get("schema") != 1 or plan.get("platform") != "win32-x64" or \
            plan.get("state") != "PREPARATION_ONLY_NOT_INSTALLED" or \
            stage.target(plan, "node")["latestStable"] != NODE_VERSION:
        raise ValueError("Unreviewed official full tool upgrade plan / Node identity")
    node = shutil.which("node")
    if not node:
        raise ValueError("Windows Node setup-node missing")
    with tempfile.TemporaryDirectory(prefix="portable-native-preflight-",
                                     dir=os.environ.get("RUNNER_TEMP")) as parent:
        root = Path(parent) / "isolated-candidate"
        tool = sandbox_from_checkout(root, node_executable=Path(node))
        # The original stage module now only writes under the ephemeral root.
        stage.ROOT, stage.TOOL = root, tool
        stage.plain_tree(tool)
        records = execute(root, stage, plan, tool / "node/node.exe")
        return write_report(records)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print("NATIVE_DIAGNOSE_BOOTSTRAP_FAIL=" + type(error).__name__ +
              ": " + str(error), file=sys.stderr)
        raise SystemExit(2)
