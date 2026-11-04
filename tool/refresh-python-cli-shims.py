#!/usr/bin/env python3
"""Refresh relocatable .cmd shims for bundled Python console launchers."""
from __future__ import annotations

import configparser
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

TOOL_DIR = Path(__file__).absolute().parent
ROOT = TOOL_DIR.parent
SITE = TOOL_DIR / "python" / "Lib" / "site-packages"
VENDOR_BIN = SITE / "bin"
OUT_BIN = TOOL_DIR / "bin"
HELPER = OUT_BIN / "portable-python-cli.py"
WINDOWS_REPARSE_POINT = 0x400


def _is_reparse(path: Path) -> bool:
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return False
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & WINDOWS_REPARSE_POINT) or stat.S_ISLNK(st.st_mode)


def _under_root_lexical(path: Path) -> Path:
    root = Path(os.path.abspath(ROOT))
    candidate = Path(os.path.abspath(path))
    try:
        common = os.path.commonpath((os.path.normcase(str(root)), os.path.normcase(str(candidate))))
    except ValueError as exc:
        raise RuntimeError(f"path escapes portable root: {candidate}") from exc
    if common != os.path.normcase(str(root)):
        raise RuntimeError(f"path escapes portable root: {candidate}")
    return candidate


def _require_plain_dir(path: Path) -> Path:
    candidate = _under_root_lexical(path)
    root = Path(os.path.abspath(ROOT))
    # Inspect from the filesystem root down before probing a linked target.
    for ancestor in (*reversed(root.parents), root):
        if _is_reparse(ancestor):
            raise RuntimeError("portable root has a linked parent")
    rel = candidate.relative_to(root)
    cursor = root
    for part in rel.parts:
        cursor = cursor / part
        if _is_reparse(cursor):
            raise RuntimeError(f"reparse/symlink directory refused: {cursor}")
    if not candidate.is_dir():
        raise RuntimeError(f"not a directory: {candidate}")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(ROOT.resolve(strict=True))
    except ValueError as exc:
        raise RuntimeError(f"resolved path escapes portable root: {resolved}") from exc
    return candidate


def _require_plain_file(path: Path) -> Path:
    candidate = _under_root_lexical(path)
    _require_plain_dir(candidate.parent)
    if _is_reparse(candidate):
        raise RuntimeError(f"reparse/symlink file refused: {candidate}")
    try:
        st = os.stat(candidate, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise RuntimeError(f"file missing: {candidate}") from exc
    if not stat.S_ISREG(st.st_mode):
        raise RuntimeError(f"not a regular file: {candidate}")
    if getattr(st, "st_nlink", 1) != 1:
        raise RuntimeError(f"hardlinked file refused: {candidate}")
    return candidate


def _safe_command_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
        raise RuntimeError(f"unsafe console launcher name: {name!r}")
    stem = name.rstrip(" .").split(".", 1)[0].upper()
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if stem in reserved:
        raise RuntimeError(f"reserved Windows console launcher name: {name!r}")
    return name


def _console_scripts() -> dict[str, str]:
    found: dict[str, str] = {}
    _require_plain_dir(SITE)
    for info in SITE.glob("*.dist-info"):
        _require_plain_dir(info)
        ep_file = info / "entry_points.txt"
        try:
            ep_file.lstat()
        except FileNotFoundError:
            continue
        ep_file = _require_plain_file(ep_file)
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        try:
            parser.read(ep_file, encoding="utf-8")
        except Exception as exc:
            raise RuntimeError(f"cannot parse {ep_file}: {exc}") from exc
        if not parser.has_section("console_scripts"):
            continue
        for name, value in parser.items("console_scripts"):
            name = _safe_command_name(name.strip())
            key = name.lower()
            if key in found and found[key] != value.strip():
                raise RuntimeError(f"ambiguous console_script {name!r}")
            found[key] = value.strip()
    return found


def _canonical_launcher(name: str, console: dict[str, str]) -> str | None:
    lower = name.lower()
    if lower in console:
        return lower
    if re.fullmatch(r"pip\d+(?:\.\d+)?", lower) and "pip" in console:
        return "pip"
    return None


def _atomic_write_cmd(path: Path, content: bytes) -> bool:
    path = _under_root_lexical(path)
    _require_plain_dir(path.parent)
    if _is_reparse(path):
        raise RuntimeError("linked shim destination refused")
    if path.exists():
        _require_plain_file(path)
        # Refreshing is destructive too: an existing name is not ownership.
        if not _is_owned_generated_cmd(path, path.read_bytes()):
            return False
    scratch = ROOT / "tmp"
    if _is_reparse(scratch):
        raise RuntimeError("linked shim temporary directory refused")
    scratch.mkdir(exist_ok=True)
    _require_plain_dir(scratch)
    fd, name = tempfile.mkstemp(prefix=".python-cli-", suffix=".tmp", dir=scratch)
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb", closefd=True) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        _require_plain_dir(path.parent)
        if _is_reparse(path):
            raise RuntimeError("linked shim destination refused")
        if path.exists():
            _require_plain_file(path)
            # Recheck after staging so a newly created/edited user file survives.
            if not _is_owned_generated_cmd(path, path.read_bytes()):
                return False
        os.replace(temp, path)
        return True
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def render_cmd(canonical: str) -> bytes:
    canonical = _safe_command_name(canonical)
    return (
        "@echo off\r\nsetlocal DisableDelayedExpansion\r\n"
        + 'set "POWERSHELL_TELEMETRY_OPTOUT=1"\r\nset "PSModuleAnalysisCachePath=NUL"\r\n'
        + 'rem R19 preflight: executable and code file are independently checked.\r\nset "_CODEX_BOOTSTRAP_ROOT=%~dp0..\\.."\r\nset "_CODEX_BOOTSTRAP_ENTRYDIR=%~dp0."\r\nset "_CODEX_BOOTSTRAP_CODE1=%~dp0..\\python\\python.exe"\r\nset "_CODEX_BOOTSTRAP_CODE2=%~dp0portable-python-cli.py"\r\n"%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$ErrorActionPreference=\'Stop\'; try { function Check([string]$p,[bool]$file) { $p=[IO.Path]::GetFullPath($p); if($p -notmatch \'^[A-Za-z]:\\\\\' -or $p.Substring(2).Contains(\':\')){throw \'path\'}; $leaf=$true; $c=$p; while($c){$i=Get-Item -LiteralPath $c -Force -ErrorAction Stop; if(($i.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw \'reparse\'}; if($leaf -and $file){if($i.PSIsContainer -or $null -eq $i.PSObject.Properties[\'LinkType\'] -or [string]$i.LinkType -eq \'HardLink\' -or ([string]$i.Mode).Contains(\'l\')){throw \'file\'}}elseif(-not $i.PSIsContainer){throw \'parent\'}; $leaf=$false; $c=[IO.Path]::GetDirectoryName($c.TrimEnd(\'\\\'))}; return $p }; $r=Check $env:_CODEX_BOOTSTRAP_ROOT $false; $r=$r.TrimEnd(\'\\\'); $e=Check $env:_CODEX_BOOTSTRAP_ENTRYDIR $false; $cwd=Check ([Environment]::CurrentDirectory) $false; if(-not ($cwd.Equals($r,[StringComparison]::OrdinalIgnoreCase) -or $cwd.StartsWith($r+\'\\\',[StringComparison]::OrdinalIgnoreCase))){throw \'cwd\'}; foreach($raw in @($env:_CODEX_BOOTSTRAP_CODE1,$env:_CODEX_BOOTSTRAP_CODE2)){if($raw){$p=Check $raw $true; if(-not $p.StartsWith($r+\'\\\',[StringComparison]::OrdinalIgnoreCase)){throw \'boundary\'}}}; exit 0 } catch { [Console]::Error.WriteLine(\'Safety stop: unsafe package/code/cwd; target NOT EXECUTED.\'); exit 3 }"\r\nif errorlevel 1 exit /b 3\r\n'
        + f'"%~dp0..\\python\\python.exe" -E -s -B "%~dp0portable-python-cli.py" "{canonical}" %*\r\n'
        + "exit /b %errorlevel%\r\n"
    ).encode("ascii")


def _is_owned_generated_cmd(path: Path, content: bytes) -> bool:
    # A mention of our helper is not proof of ownership. Preserve user-edited,
    # unrelated and unrecognized legacy commands; delete only exact output.
    try:
        canonical = _safe_command_name(path.stem).lower()
    except RuntimeError:
        return False
    candidates = [canonical]
    if re.fullmatch(r"pip\d+(?:\.\d+)?", canonical):
        candidates.append("pip")
    return any(content == render_cmd(name) for name in candidates)


def main() -> int:
    _require_plain_file(Path(__file__).absolute())
    for d in (SITE, VENDOR_BIN, OUT_BIN):
        _require_plain_dir(d)
    _require_plain_file(HELPER)

    console = _console_scripts()
    vendor = sorted(VENDOR_BIN.glob("*.exe"), key=lambda p: p.name.lower())
    created: list[str] = []
    unresolved: list[str] = []
    expected_names: set[str] = set()

    for exe in vendor:
        _require_plain_file(exe)
        base = _safe_command_name(exe.stem)
        # Missing console metadata is not evidence that a current shim is obsolete.
        expected_names.add((base + ".cmd").lower())
        canonical = _canonical_launcher(base, console)
        if canonical is None:
            unresolved.append(base)
            continue
        target = OUT_BIN / f"{base}.cmd"
        body = render_cmd(canonical)
        if not _atomic_write_cmd(target, body):
            unresolved.append(base + " (existing command preserved)")
            continue
        created.append(target.name)

    # Remove only unmodified generated shims without a current vendor launcher.
    # In particular, a user comment mentioning our helper never grants ownership.
    for cmd in OUT_BIN.glob("*.cmd"):
        _require_plain_file(cmd)
        if cmd.name.lower() in expected_names:
            continue
        try:
            data = cmd.read_bytes()
        except OSError:
            continue
        if _is_owned_generated_cmd(cmd, data):
            cmd.unlink()

    if unresolved:
        print("Unresolved vendor launchers: " + ", ".join(unresolved), file=sys.stderr)
        return 3
    print(f"Refreshed {len(created)} portable Python CLI shims: " + ", ".join(created))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"refresh-python-cli-shims: {exc}", file=sys.stderr)
        raise SystemExit(2)
