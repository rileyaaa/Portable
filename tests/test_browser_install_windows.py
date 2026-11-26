"""Local P3 only; native mode requires an already offline Windows x64 VM.

Run explicitly with bundled Python -I -B; --helper-only tests pure Python.
No install, browser launch, network, policy change, or customer archive.
"""
import ctypes
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import uuid

ROOT = Path(__file__).absolute().parents[1]
VERSION, REVISION = "0.0.0.1", "1247"
PREFIX = f"tool/automation/browsers/chromium-{REVISION}/"
URL = ("https://storage.googleapis.com/chrome-for-testing-public/"
       f"{VERSION}/win64/chrome-win64.zip")
CASES = (("complete", "verified", True, True),
         ("missing-revision", "missing", False, False),
         ("missing-exe", "incomplete", False, False),
         ("missing-dll", "incomplete", True, False))


def load_browser():
    spec = importlib.util.spec_from_file_location(
        "browser_install", ROOT / "tool/automation/install-browser.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(root, case):
    exe = bytearray(128)
    exe[:2] = b"MZ"
    exe[60:64] = (64).to_bytes(4, "little")
    exe[64:70] = b"PE\0\0\x64\x86"
    files = {"chrome-win64/chrome.exe": bytes(exe),
             "chrome-win64/chrome.dll": b"synthetic dll"}
    auto = root / "tool/automation"
    root.mkdir()
    auto.mkdir(parents=True)
    (auto / "browsers").mkdir()
    (root / "tmp").mkdir()
    (root / "env.ps1").write_bytes(b"# synthetic marker\n")
    profile = root / "cache/browser/profile"
    profile.mkdir(parents=True)
    (profile / "sentinel").write_bytes(b"preserve")
    versions = {"playwrightMcp": "synthetic", "browser": {
        "version": VERSION, "revision": REVISION,
        "executable": f"browsers/chromium-{REVISION}/chrome-win64/chrome.exe",
        "revisionSource": "chrome-for-testing", "channel": "stable",
        "downloadUrl": URL}}
    manifest = {"schemaVersion": 1, "platform": "win32-x64",
        "browserVersion": VERSION, "revision": REVISION,
        "fileCount": 2, "uncompressedBytes": sum(map(len, files.values())),
        "archive": {"size": 1, "sha256": "0" * 64,
                    "sourceUrl": URL, "resolvedUrl": URL},
        "files": {PREFIX + k: {"size": len(v),
                  "sha256": hashlib.sha256(v).hexdigest()}
                  for k, v in files.items()}}
    for name, data in (("versions.json", versions),
                       ("browser-manifest.json", manifest)):
        (auto / name).write_text(json.dumps(data), encoding="ascii")
    if case != "missing-revision":
        (root / PREFIX / "chrome-win64").mkdir(parents=True)
        for name, data in files.items():
            if (case, name) not in (("missing-exe", "chrome-win64/chrome.exe"),
                                    ("missing-dll", "chrome-win64/chrome.dll")):
                (root / PREFIX / name).write_bytes(data)


def snapshot(browser, root, ignore=()):
    result = {}
    pending = [browser.checked(root, root, directory=True)]
    while pending:
        folder = pending.pop()
        for p in folder.iterdir():
            name = p.relative_to(root).as_posix()
            directory = stat.S_ISDIR(p.lstat().st_mode)
            browser.checked(root, p, directory=directory)
            if name in ignore:
                continue
            result[name] = "dir" if directory else browser.digest(p)
            if directory:
                pending.append(p)
    return result


def assert_action(action, state):
    assert PREFIX.rstrip("/") in action
    assert ("-Install" in action) == (state == "missing")
    if state == "incomplete":
        assert "same version" in action and "profile" in action
    if state == "verified":
        assert "verified" in action


def prepare_native(browser, root):
    def copy(source, dest):
        browser.checked(ROOT, source)
        browser.checked(root, dest, missing=True)
        assert not dest.exists()
        shutil.copyfile(source, dest)
        assert browser.digest(source) == browser.digest(dest)

    for name in ("tool/automation/install-browser.ps1",
                 "tool/automation/install-browser.py",
                 "tool/automation/portable-automation.ps1",
                 "tool/portable-process.ps1"):
        copy(ROOT / name, root / name)
    source = browser.checked(ROOT, ROOT / "tool/python", directory=True)
    runtime = root / "tool/python"
    (runtime / "Lib/site-packages").mkdir(parents=True)
    required = {"python.exe", "python314.dll", "python314.zip", "python314._pth"}
    for p in source.iterdir():
        if p.name in required or p.suffix.lower() in (".dll", ".pyd"):
            copy(p, runtime / p.name)
    assert all((runtime / name).is_file() for name in required)
    assert (runtime / "python314._pth").read_text(encoding="ascii").splitlines() == [
        "python314.zip", ".", "Lib\\site-packages", "",
        "# Uncomment to run site.main() automatically", "import site"]
    (root / "tool/node").mkdir()
    (root / "runner-state").mkdir()


def native_check(root):
    buf = ctypes.create_unicode_buffer(32768)
    assert 0 < ctypes.windll.kernel32.GetSystemWindowsDirectoryW(buf, len(buf)) < len(buf)
    win = Path(buf.value)
    assert win.is_absolute() and len(win.drive) == 2
    ps = win / "System32/WindowsPowerShell/v1.0/powershell.exe"
    assert ps.is_file()
    state = root / "runner-state"
    env = {"SystemRoot": str(win), "WINDIR": str(win),
           "SystemDrive": win.drive, "COMSPEC": str(win / "System32/cmd.exe"),
           "PATH": str(win / "System32"), "PATHEXT": ".COM;.EXE;.BAT;.CMD",
           "PSModulePath": str(ps.parent / "Modules"),
           "PSModuleAnalysisCachePath": str(state / "module-cache")}
    for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP",
                "TMPDIR", "PROGRAMDATA", "ALLUSERSPROFILE", "PUBLIC"):
        env[key] = str(state)
    env.update(HOMEDRIVE=state.drive, HOMEPATH=str(state)[len(state.drive):])
    prefix = [str(ps), "-NoProfile", "-NonInteractive"]
    options = dict(cwd=root, env=env, stdin=subprocess.DEVNULL, capture_output=True)
    version = subprocess.run(prefix + ["-Command", "$PSVersionTable.PSVersion.ToString()"],
                             timeout=30, **options)
    assert version.returncode == 0 and version.stdout.strip().startswith(b"5.1.")
    result = subprocess.run(prefix + ["-File", str(root / "tool/automation/install-browser.ps1"),
                                     "-Check"], timeout=1000, **options)
    assert result.returncode == 0 and not result.stderr, "PowerShell check failed"
    return json.loads(result.stdout.decode("utf-8-sig"))


def main():
    assert __debug__ and sys.dont_write_bytecode
    if sys.argv[1:] not in ([], ["--helper-only"]):
        raise SystemExit("Expected no arguments or --helper-only")
    pure = sys.argv[1:] == ["--helper-only"]
    if not pure and os.name != "nt":
        raise SystemExit("NOT_RUN: native Windows required")
    if not pure:
        assert sys.flags.isolated and struct.calcsize("P") == 8
        assert str(ROOT).isascii(), "Use an ASCII checkout path for this P3-only test"
        assert Path(sys.executable).resolve() == ROOT / "tool/python/python.exe"
    browser = load_browser()
    scratch = browser.checked(ROOT, ROOT / "tmp", directory=True, missing=True)
    scratch.mkdir(exist_ok=True)
    owned = scratch / ("p3-native-" + uuid.uuid4().hex)
    owned.mkdir()
    timed_out = False
    try:
        for case, expected, present, verified in CASES:
            root = owned / case
            fixture(root, case)
            if not pure:
                prepare_native(browser, root)
            before = snapshot(browser, root, ignore=("tmp", "runner-state"))
            if pure:
                manifest, prefix = browser.load_manifest(root)
                assert prefix == PREFIX
                state = browser.payload_state(root, manifest, prefix)
                assert state == expected
                output = io.StringIO()
                with redirect_stdout(output):
                    rc = browser.report_payload_state(manifest, state)
                report = json.loads(output.getvalue())
                assert rc == (0 if verified else 1)
                assert report["state"] == expected and report["verified"] is verified
                assert report["version"] == VERSION and report["files"] == 2
                assert_action(report["action"], state)
            else:
                report = native_check(root)
                assert report["BrowserState"] == expected
                assert report["BrowserPresent"] is present
                assert report["BrowserVerified"] is verified
                assert report["BrowserVersion"] == VERSION
                assert Path(report["Destination"]) == root / "tool/automation/browsers"
                assert Path(report["RevisionDestination"]) == root / PREFIX
                assert_action(report["Action"], expected)
            assert snapshot(browser, root, ignore=("tmp", "runner-state")) == before
            assert not list(browser.checked(root, root / "tmp", directory=True).iterdir())
            print(case + (": PASS_HELPER_ONLY" if pure else ": PASS_NATIVE_PS"), flush=True)
    except subprocess.TimeoutExpired:
        timed_out = True
        raise SystemExit("FAIL: native timeout; owned fixture retained for safe inspection")
    finally:
        if not timed_out:
            snapshot(browser, owned)  # Refuse linked trees before recursive cleanup.
            shutil.rmtree(owned)
    print("WINDOWS=NOT_RUN" if pure else "P3_LOCAL_WINDOWS_ONLY=PASS")


if __name__ == "__main__":
    main()
