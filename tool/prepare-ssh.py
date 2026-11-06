#!/usr/bin/env python3
"""Build a pinned Windows SSH wheel add-on inside Codex Portable; never use host pip.

This maintenance utility operates on a *checkout*, not a user's active session.
The independent sidecar keeps the fixed base 42-distribution repair scope intact.
"""
from __future__ import annotations

import argparse
from email.parser import Parser
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).absolute().parent.parent
TOOL = ROOT / 'tool'
SITE = TOOL / 'python' / 'Lib' / 'site-packages'
DEST = TOOL / 'python' / 'ssh-packages'
INPUT = TOOL / 'python-ssh-packages.in.txt'
LOCK = TOOL / 'python-ssh-packages.lock.txt'
PYTHON = TOOL / 'python' / 'python.exe'
PTH = SITE / 'codex_portable_ssh.pth'
MAX_WHEEL = 30 * 1024 * 1024
MAX_PAYLOAD = 90 * 1024 * 1024


def fail(message: str) -> None:
    raise RuntimeError(message)


def shared_upgrade_lock():
    """Use the same kernel lock as full-stable-transfer and update-tools.

    Only standalone SSH installation takes this lock. update-tools.prepare
    already holds it when invoking _install_under_parent_lock in-process.
    """
    source = Path(__file__).resolve().with_name("full-stable-transfer.py")
    spec = importlib.util.spec_from_file_location("portable_shared_transfer_lock", source)
    if spec is None or spec.loader is None:
        fail("Missing reviewed full-transfer lock implementation")
    transfer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transfer)
    transfer.ROOT = ROOT
    return transfer.exclusive_transfer_lock()


def ordinary(path: Path, directory: bool = False) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        fail('Reparse/symlink path refused: ' + str(path))
    if directory and not stat.S_ISDIR(info.st_mode):
        fail('Not a directory: ' + str(path))
    if not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
        fail('Not an ordinary single-link file: ' + str(path))


def inside(path: Path) -> Path:
    if '..' in path.parts:
        fail('Parent traversal refused')
    full = Path(os.path.abspath(path))
    try:
        full.relative_to(ROOT)
    except ValueError:
        fail('Outside portable package: ' + str(path))
    current = Path(ROOT.anchor)
    for part in ROOT.parts[1:]:
        current /= part
        ordinary(current, True)
    current = ROOT
    for part in full.relative_to(ROOT).parts:
        current /= part
        # A dangling Windows junction can report exists()/is_symlink()
        # as false while lstat() still exposes its reparse directory entry.
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        ordinary(current, stat.S_ISDIR(info.st_mode))
    return full


def pins() -> dict[str, str]:
    ordinary(INPUT)
    obj = {}
    for line in INPUT.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r'([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9.!+_-]+)', line)
        if not match:
            fail('Every SSH distribution must have an exact version pin')
        name, version = match.groups()
        name = re.sub('[-_.]+', '-', name).lower()
        if name in obj:
            fail('Duplicate SSH dependency: ' + name)
        obj[name] = version
    if set(obj) != {'paramiko', 'bcrypt', 'cryptography', 'invoke', 'pynacl', 'cffi', 'pycparser'}:
        fail('Unexpected SSH dependency closure; review before changing the allowlist')
    return obj


def installed(site: Path, expected: dict[str, str]) -> bool:
    # Do not mistake a dangling reparse point for an absent sidecar.
    try:
        site.lstat()
    except FileNotFoundError:
        return False
    inside(site)
    for member in site.rglob('*'):
        # A committed sidecar may not contain junctions, symlinks or hardlinks.
        ordinary(member, directory=member.is_dir())
    observed = {}
    for meta in site.glob('*.dist-info/METADATA'):
        ordinary(meta)
        doc = Parser().parsestr(meta.read_text(encoding='utf-8'), headersonly=True)
        name = re.sub('[-_.]+', '-', doc.get('Name', '')).lower()
        if name in observed:
            fail('Duplicate distribution metadata')
        observed[name] = doc.get('Version')
    if observed != expected:
        fail('SSH sidecar is incomplete or altered: ' + str(observed))
    return True


def child_env(base: Path) -> dict[str, str]:
    # Never propagate credential, proxy, pip, Python, Git or user-profile settings.
    allowed = ('SystemRoot', 'WINDIR', 'COMSPEC', 'PATHEXT', 'PROCESSOR_ARCHITECTURE')
    result = {key: os.environ[key] for key in allowed if key in os.environ}
    dirs = {
        'TEMP': base / 'tmp', 'TMP': base / 'tmp', 'TMPDIR': base / 'tmp',
        'HOME': ROOT / 'home-runtime', 'USERPROFILE': ROOT / 'home-runtime',
        'APPDATA': ROOT / 'appdata', 'LOCALAPPDATA': ROOT / 'localappdata',
        'XDG_CACHE_HOME': ROOT / 'cache' / 'xdg',
        'PIP_CACHE_DIR': ROOT / 'cache' / 'pip',
        'PYTHONUSERBASE': ROOT / 'cache' / 'python-userbase',
    }
    for name, path in dirs.items():
        inside(path)
        path.mkdir(parents=True, exist_ok=True)
        result[name] = str(path)
    result.update(PIP_CONFIG_FILE='nul', PYTHONDONTWRITEBYTECODE='1',
                  PYTHONNOUSERSITE='1', PYTHONPYCACHEPREFIX=str(ROOT / 'cache' / 'pycache'))
    result['PATH'] = str(TOOL / 'python') + os.pathsep + str(Path(result.get('SystemRoot', 'C:\\Windows')) / 'System32')
    return result


def run(args: list[str], env: dict[str, str]) -> None:
    outcome = subprocess.run([str(PYTHON), '-E', '-s', '-B', *args], cwd=ROOT,
                             env=env, timeout=360, check=False)
    if outcome.returncode:
        fail('Bundled Python maintenance command failed: exit ' + str(outcome.returncode))


def wheel_safe(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (not name or name.startswith(('/', '\\')) or '\\' in name or
            path.is_absolute() or ':' in name or
            not all(part not in ('', '.', '..') for part in name.split('/'))):
        fail('Unsafe wheel member: ' + name)
    return path


def unpack_wheels(wheel_dir: Path, site: Path, expected: dict[str, str]) -> None:
    files = sorted(wheel_dir.glob('*.whl'))
    if len(files) != len(expected):
        fail('Wheel count differs from pinned closure')
    seen: set[str] = set()
    total = 0
    for wheel in files:
        ordinary(wheel)
        if wheel.stat().st_size > MAX_WHEEL:
            fail('Oversize wheel: ' + wheel.name)
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            metas = [n for n in names if n.endswith('.dist-info/METADATA')]
            if len(metas) != 1:
                fail('Ambiguous wheel METADATA')
            metadata = Parser().parsestr(archive.read(metas[0]).decode('utf-8'), headersonly=True)
            key = re.sub('[-_.]+', '-', metadata.get('Name', '')).lower()
            if key not in expected or expected[key] != metadata.get('Version'):
                fail('Unexpected wheel identity: ' + wheel.name)
            seen.add(key)
            for entry in archive.infolist():
                path = wheel_safe(entry.filename.rstrip('/'))
                # Do not allow wheel .data scripts or external installation targets.
                if any(part.endswith('.data') for part in path.parts):
                    fail('Wheel layout needs manual review: ' + entry.filename)
                mode = (entry.external_attr >> 16) & 0o170000
                if mode not in (0, stat.S_IFREG, stat.S_IFDIR):
                    fail('Linked/special wheel entry: ' + entry.filename)
                if entry.is_dir():
                    continue
                if entry.file_size > MAX_WHEEL or total + entry.file_size > MAX_PAYLOAD:
                    fail('SSH wheel expansion exceeds limit')
                target = site.joinpath(*path.parts)
                inside(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    fail('Colliding wheel members: ' + entry.filename)
                with archive.open(entry) as source, target.open('xb') as dest:
                    shutil.copyfileobj(source, dest)
                total += entry.file_size
    if seen != set(expected):
        fail('Missing/duplicated SSH wheel distributions')
    installed(site, expected)


def stage_install(temp: Path, expected: dict[str, str], env: dict[str, str], *, new_lock: bool,
                  runtime_test: bool) -> Path:
    report = temp / 'report.json'
    wheels = temp / 'wheels'
    wheels.mkdir()
    staged = temp / 'ssh-packages'
    staged.mkdir()
    helper_spec = importlib.util.spec_from_file_location('portable_python_lock', TOOL / 'python-lock.py')
    if helper_spec is None or helper_spec.loader is None:
        fail('Missing fixed runtime lock helper')
    helper = importlib.util.module_from_spec(helper_spec)
    helper_spec.loader.exec_module(helper)
    source = INPUT.read_bytes()
    inside(LOCK)  # Reject dangling junctions and links before lock read/write.
    if LOCK.exists():
        ordinary(LOCK)
        lock_bytes = LOCK.read_bytes()
        try:
            helper.validate_lock(lock_bytes, source)
        except ValueError:
            if not new_lock:
                fail('SSH lock stale: explicit --new-lock required')
            lock_bytes = b''
    else:
        lock_bytes = b''
    if not lock_bytes:
        run(['-m', 'pip', '--isolated', '--disable-pip-version-check', '--no-input',
             'install', '--dry-run', '--ignore-installed', '--only-binary=:all:',
             '--index-url', 'https://pypi.org/simple', '--report', str(report),
             '-r', str(INPUT)], env)
        lock_bytes = helper.build_lock(json.loads(report.read_text(encoding='utf-8')), source).encode()
    staged_lock = temp / 'ssh.lock'
    staged_lock.write_bytes(lock_bytes)
    helper.validate_lock(lock_bytes, source)
    run(['-m', 'pip', '--isolated', '--disable-pip-version-check', '--no-input',
         'download', '--only-binary=:all:', '--require-hashes',
         '--index-url', 'https://pypi.org/simple', '-d', str(wheels),
         '-r', str(staged_lock)], env)
    unpack_wheels(wheels, staged, expected)
    if runtime_test:
        probe = ('import sys,importlib.metadata as md;sys.path.insert(0,sys.argv[1]);'
                 'import paramiko,bcrypt,cryptography,invoke,nacl,cffi,pycparser;'
                 'assert paramiko.__version__==sys.argv[2];'
                 'assert all(md.distribution(n).version==v for n,v in '
                 '[p.split("==") for p in sys.argv[3:]]);'
                 'print("SSH_IMPORT_NATIVE=PASS")')
        # -c is a normal Python argument, not a shell fragment.
        run(['-c', probe, str(staged), expected['paramiko'],
             *[f'{name}=={version}' for name, version in expected.items()]], env)
    return staged_lock


def install(*, new_lock: bool, runtime_test: bool) -> None:
    """Standalone public installation always takes the shared OS lock."""
    with shared_upgrade_lock():
        _install_under_parent_lock(new_lock=new_lock, runtime_test=runtime_test)


def _install_under_parent_lock(*, new_lock: bool, runtime_test: bool) -> None:
    """Internal only: update-tools.prepare MUST hold shared_upgrade_lock.

    Keeping the actual SSH wheel staging in the already-running bundled
    Python process prevents a child from trying to acquire its parent's lock.
    This private helper is not exposed as a command-line escape hatch.
    """
    if os.name != 'nt' or sys.platform != 'win32' or sys.maxsize <= 2**32:
        fail('Installation requires Windows x64')
    installed_python = json.loads((TOOL / 'installed-tools.json').read_text(encoding='utf-8'))['tools']['python']['version']
    expected_minor = tuple(int(part) for part in installed_python.split('.')[:2])
    if (Path(sys.executable).absolute() != PYTHON.absolute() or
            sys.version_info[:2] != expected_minor):
        fail('Must use the bundled CPython runtime matching the installed version ledger')
    expected = pins()
    for name in ('codex.exe', 'env.ps1'):
        ordinary(ROOT / name)
    inside(DEST)
    inside(SITE)
    ordinary(PTH)
    if PTH.read_text(encoding='utf-8').strip() != '../../ssh-packages':
        fail('Portable .pth has an unexpected path')
    scratch = ROOT / 'tmp'
    inside(scratch)
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ssh-maintenance-', dir=scratch) as folder:
        temp = Path(folder)
        env = child_env(temp)
        staged_lock = stage_install(temp, expected, env, new_lock=new_lock,
                                    runtime_test=runtime_test)
        if DEST.exists():
            installed(DEST, expected) if not new_lock else inside(DEST)
        backup = temp / 'previous-ssh'
        had_old = DEST.exists()
        try:
            if had_old:
                DEST.rename(backup)
            (temp / 'ssh-packages').rename(DEST)
            # Never publish an unverified resolver lock before the sidecar is installed.
            candidate = temp / 'publish.lock'
            candidate.write_bytes(staged_lock.read_bytes())
            os.replace(candidate, LOCK)
        except Exception:
            if DEST.exists():
                # Only remove the freshly staged path; never delete user SSH state.
                shutil.rmtree(DEST)
            if had_old and backup.exists():
                backup.rename(DEST)
            raise
    print('SSH_INSTALLED=PASS paramiko=' + expected['paramiko'])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['check', 'install'])
    ap.add_argument('--new-lock', action='store_true')
    ap.add_argument('--skip-runtime-test', action='store_true',
                    help='Only for the separate no-execution writer job after matching a verified digest')
    args = ap.parse_args()
    expected = pins()
    if args.action == 'check':
        print('SSH_STATUS=' + ('installed' if installed(DEST, expected) else 'missing'))
        return
    install(new_lock=args.new_lock, runtime_test=not args.skip_runtime_test)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as error:
        print('SSH_MAINTENANCE_ERROR=' + str(error), file=sys.stderr)
        raise SystemExit(2)