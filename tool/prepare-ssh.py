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


def shared_upgrade_lock(*, recovery: bool = False):
    """Take the common OS lock, then gate new writes on unresolved journals.

    Recovery itself must be allowed to inspect its own preserved SSH journal;
    both public entrypoints still serialize through the same kernel lock.
    """
    source = Path(__file__).resolve().with_name("full-stable-transfer.py")
    spec = importlib.util.spec_from_file_location("portable_shared_transfer_lock", source)
    if spec is None or spec.loader is None:
        fail("Missing reviewed full-transfer lock implementation")
    transfer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transfer)
    transfer.ROOT = ROOT
    if recovery:
        return transfer.exclusive_transfer_lock()
    return transfer.exclusive_preparation_lock()


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


class SSHRollbackIncomplete(RuntimeError):
    """A failed SSH publish retained its original backups for manual recovery."""


def _exists_entry(path: Path) -> bool:
    """lstat the directory entry even if a Windows junction target is missing."""
    inside(path)
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _sidecar_digest(root: Path) -> str:
    """Snapshot all filenames, types and bytes before a risky rename."""
    inside(root)
    ordinary(root, True)
    result = hashlib.sha256()
    for entry in sorted(root.rglob('*'),
                        key=lambda child: child.relative_to(root).as_posix().casefold()):
        inside(entry)
        info = entry.lstat()
        name = entry.relative_to(root).as_posix()
        if stat.S_ISDIR(info.st_mode):
            ordinary(entry, True)
            record = ['D', name]
        elif stat.S_ISREG(info.st_mode):
            ordinary(entry)
            with entry.open('rb') as source:
                digest = hashlib.file_digest(source, 'sha256').hexdigest()
            record = ['F', name, digest]
        else:
            fail('Special SSH sidecar path refused: ' + str(entry))
        result.update(json.dumps(record, ensure_ascii=False,
                                 separators=(',', ':')).encode('utf-8'))
        result.update(bytes([0]))
    return result.hexdigest()


def _current_ssh_lock() -> bytes | None:
    if not _exists_entry(LOCK):
        return None
    ordinary(LOCK)
    return LOCK.read_bytes()


def _restore_failed_ssh_publish(temp: Path, *, had_old: bool,
                                old_digest: str | None, new_digest: str,
                                old_lock: bytes | None, new_lock: bytes) -> None:
    """Never delete an original sidecar or overwrite unrelated changes."""
    backup = temp / 'previous-ssh'
    backup_exists = _exists_entry(backup)
    dest_exists = _exists_entry(DEST)
    if had_old:
        if backup_exists:
            if _sidecar_digest(backup) != old_digest:
                fail('SSH original backup changed during failed publication')
            if dest_exists:
                if _sidecar_digest(DEST) != new_digest:
                    fail('SSH candidate destination changed outside publication')
                shutil.rmtree(DEST)
            backup.rename(DEST)
        elif not dest_exists or _sidecar_digest(DEST) != old_digest:
            fail('Original SSH sidecar missing or changed before backup')
    else:
        if backup_exists:
            fail('Unexpected original SSH backup for an added sidecar')
        if dest_exists:
            if _sidecar_digest(DEST) != new_digest:
                fail('SSH candidate destination changed outside publication')
            shutil.rmtree(DEST)
    current_lock = _current_ssh_lock()
    if current_lock != old_lock:
        if current_lock != new_lock:
            fail('SSH resolver lock changed outside publication')
        if old_lock is None:
            inside(LOCK)
            ordinary(LOCK)
            LOCK.unlink()
        else:
            saved_lock = temp / 'previous-ssh.lock'
            inside(saved_lock)
            ordinary(saved_lock)
            if saved_lock.read_bytes() != old_lock:
                fail('Saved original SSH resolver lock has changed')
            os.replace(saved_lock, LOCK)
    if had_old:
        if _sidecar_digest(DEST) != old_digest:
            fail('SSH sidecar failed final rollback verification')
    elif _exists_entry(DEST):
        fail('SSH added sidecar survived rollback')
    if _current_ssh_lock() != old_lock:
        fail('SSH resolver lock failed final rollback verification')


def _publish_ssh_sidecar(temp: Path, staged_lock: Path) -> None:
    """Move the original only after writing a verifiable recovery map.

    Any unsuccessful rollback leaves the transaction outside automatic
    TemporaryDirectory cleanup so the last surviving original is not lost.
    """
    staged = temp / 'ssh-packages'
    inside(staged)
    new_digest = _sidecar_digest(staged)
    had_old = _exists_entry(DEST)
    old_digest = _sidecar_digest(DEST) if had_old else None
    old_lock = _current_ssh_lock()
    inside(staged_lock)
    ordinary(staged_lock)
    new_lock = staged_lock.read_bytes()
    candidate = temp / 'publish.lock'
    candidate.write_bytes(new_lock)
    if old_lock is not None:
        (temp / 'previous-ssh.lock').write_bytes(old_lock)
    # Both the original tree and old lock are recoverable even if the
    # process terminates just after its first successful rename.
    mapping = temp / 'publish-recovery.json'
    with mapping.open('x', encoding='utf-8') as journal:
        json.dump({'schema': 1, 'oldSidecar': had_old,
                   'oldTreeSHA256': old_digest, 'newTreeSHA256': new_digest,
                   'oldLockSHA256': (hashlib.sha256(old_lock).hexdigest()
                                    if old_lock is not None else None),
                   'newLockSHA256': hashlib.sha256(new_lock).hexdigest()},
                  journal, sort_keys=True)
        journal.write('\n')
        journal.flush()
        os.fsync(journal.fileno())
    backup = temp / 'previous-ssh'
    try:
        if had_old:
            DEST.rename(backup)
        staged.rename(DEST)
        os.replace(candidate, LOCK)
        # A successful rename is not itself proof that the final path still
        # refers to the candidate. Reject late changes before discarding the
        # original sidecar and resolver lock backup.
        if (_sidecar_digest(DEST) != new_digest or
                _current_ssh_lock() != new_lock):
            fail('SSH final publication digest changed')
    except BaseException as error:
        try:
            _restore_failed_ssh_publish(
                temp, had_old=had_old, old_digest=old_digest,
                new_digest=new_digest, old_lock=old_lock, new_lock=new_lock)
        except BaseException as rollback_error:
            raise SSHRollbackIncomplete(
                'SSH publish failed and rollback is incomplete; preserve '
                'original backups at ' + str(temp) + ': ' +
                str(rollback_error)) from error
        raise


def _journal_sha(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def ssh_recovery_plan(directory: Path) -> tuple[Path, dict, bytes | None, bytes]:
    """Read-only validation of an interrupted SSH directory publication.

    The journal is locally supplied evidence, not a signed authenticity
    proof. Validate all original, candidate and resolver-lock identities
    before any restoration or cleanup. This does not defend OS path races.
    """
    scratch = ROOT / 'tmp'
    inside(scratch)
    ordinary(scratch, True)
    journal = Path(directory).absolute()
    if ('..' in journal.parts or journal.parent != scratch or
            re.fullmatch(r'ssh-maintenance-[A-Za-z0-9_-]+', journal.name) is None):
        fail('SSH recovery journal must be a direct package tmp child')
    inside(journal)
    ordinary(journal, True)
    others = [p for p in scratch.glob('ssh-maintenance-*') if p != journal]
    if others:
        fail('Multiple unresolved SSH maintenance journals; inspect manually')

    mapping = journal / 'publish-recovery.json'
    inside(mapping)
    ordinary(mapping)
    if mapping.stat().st_size > 4096:
        fail('Oversized SSH recovery mapping')
    data = json.loads(mapping.read_text(encoding='utf-8'))
    required = {'schema', 'oldSidecar', 'oldTreeSHA256', 'newTreeSHA256',
                'oldLockSHA256', 'newLockSHA256'}
    if (not isinstance(data, dict) or set(data) != required or
            type(data.get('schema')) is not int or data['schema'] != 1 or
            type(data.get('oldSidecar')) is not bool or
            not _journal_sha(data.get('newTreeSHA256')) or
            not _journal_sha(data.get('newLockSHA256')) or
            (not _journal_sha(data.get('oldTreeSHA256'))
             if data['oldSidecar'] else data.get('oldTreeSHA256') is not None) or
            (data.get('oldLockSHA256') is not None and
             not _journal_sha(data.get('oldLockSHA256')))):
        fail('Invalid SSH recovery journal schema or hashes')

    old_tree = data['oldTreeSHA256']
    new_tree = data['newTreeSHA256']
    backup = journal / 'previous-ssh'
    saved = _exists_entry(backup)
    destination = _exists_entry(DEST)
    if data['oldSidecar']:
        if saved:
            if _sidecar_digest(backup) != old_tree:
                fail('SSH recovery original backup digest mismatch')
            if destination and _sidecar_digest(DEST) != new_tree:
                fail('SSH recovery destination changed outside candidate')
        elif not destination or _sidecar_digest(DEST) != old_tree:
            fail('SSH recovery original is missing or modified')
    elif saved:
        fail('SSH recovery contains an unexpected original sidecar')
    elif destination and _sidecar_digest(DEST) != new_tree:
        fail('SSH recovery destination changed outside candidate')

    staged = journal / 'ssh-packages'
    if _exists_entry(staged) and _sidecar_digest(staged) != new_tree:
        fail('SSH recovery staged candidate digest mismatch')

    current = _current_ssh_lock()
    current_hash = hashlib.sha256(current).hexdigest() if current is not None else None
    old_hash = data['oldLockSHA256']
    new_hash = data['newLockSHA256']
    old_copy = journal / 'previous-ssh.lock'
    if old_hash is None:
        if _exists_entry(old_copy):
            fail('SSH recovery unexpected old resolver lock backup')
        old_bytes = None
    elif _exists_entry(old_copy):
        ordinary(old_copy)
        old_bytes = old_copy.read_bytes()
        if hashlib.sha256(old_bytes).hexdigest() != old_hash:
            fail('SSH recovery original resolver lock backup digest mismatch')
    elif current_hash == old_hash:
        # Earlier recovery may already have restored this lock.
        old_bytes = current
    else:
        fail('SSH recovery original resolver lock cannot be reconstructed')

    for relative in ('ssh.lock', 'publish.lock'):
        entry = journal / relative
        if _exists_entry(entry):
            ordinary(entry)
            if hashlib.sha256(entry.read_bytes()).hexdigest() != new_hash:
                fail('SSH recovery staged resolver lock digest mismatch')
    new_copy = journal / 'ssh.lock'
    if not _exists_entry(new_copy):
        fail('SSH recovery staged resolver lock missing')
    ordinary(new_copy)
    new_bytes = new_copy.read_bytes()
    if current_hash not in (old_hash, new_hash):
        fail('SSH recovery resolver lock changed outside publication')
    return journal, data, old_bytes, new_bytes


def _safe_ssh_recovery_cleanup(directory: Path) -> None:
    """Refuse linked, special, hard-linked or unbounded journal contents."""
    inside(directory)
    ordinary(directory, True)
    # Cleanup must not silently erase arbitrary files dropped into a
    # leftover journal. Only the SSH staging files generated by this
    # installer are eligible for deletion.
    allowed = {'publish-recovery.json', 'report.json', 'ssh.lock',
               'publish.lock', 'previous-ssh.lock', 'previous-ssh',
               'ssh-packages', 'wheels', 'tmp'}
    for child in directory.iterdir():
        if child.name not in allowed:
            fail('Unexpected SSH recovery entry; refuse cleanup: ' + child.name)
    scanned = 0
    for entry in directory.rglob('*'):
        scanned += 1
        if scanned > 120000:
            fail('SSH recovery directory contains too many entries for cleanup')
        inside(entry)
        mode = entry.lstat().st_mode
        ordinary(entry, stat.S_ISDIR(mode))


def recover_ssh(directory: Path, *, restore: bool = False) -> None:
    """Default to audit only; explicit --restore is required to change files."""
    with shared_upgrade_lock(recovery=True):
        scratch = ROOT / 'tmp'
        inside(scratch)
        if any(scratch.glob('full-writer-journal-*')):
            fail('Unresolved full-writer transaction; recover full writer first')
        journal, record, old_lock, new_lock = ssh_recovery_plan(directory)
        _safe_ssh_recovery_cleanup(journal)
        print('SSH_RECOVERY_AUDIT=PASS')
        if not restore:
            return
        try:
            _restore_failed_ssh_publish(
                journal, had_old=record['oldSidecar'],
                old_digest=record['oldTreeSHA256'],
                new_digest=record['newTreeSHA256'],
                old_lock=old_lock, new_lock=new_lock)
            ssh_recovery_plan(journal)
            _safe_ssh_recovery_cleanup(journal)
            shutil.rmtree(journal)
        except BaseException as error:
            raise SSHRollbackIncomplete(
                'SSH recovery incomplete; journal retained for review at ' +
                str(journal) + ': ' + str(error)) from error
        print('SSH_RECOVERY_RESTORED=PASS')


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
    # A stale transaction can contain the only surviving old SSH sidecar.
    # Never overwrite it with a second update; require manual recovery.
    if any(scratch.glob('ssh-maintenance-*')):
        fail('Unresolved SSH maintenance transaction; inspect preserved backup first')
    temp = Path(tempfile.mkdtemp(prefix='ssh-maintenance-', dir=scratch))
    preserve = False
    try:
        env = child_env(temp)
        staged_lock = stage_install(temp, expected, env, new_lock=new_lock,
                                    runtime_test=runtime_test)
        if _exists_entry(DEST):
            installed(DEST, expected) if not new_lock else inside(DEST)
        _publish_ssh_sidecar(temp, staged_lock)
    except SSHRollbackIncomplete:
        preserve = True
        raise
    finally:
        if not preserve:
            inside(temp)
            shutil.rmtree(temp)
    print('SSH_INSTALLED=PASS paramiko=' + expected['paramiko'])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['check', 'install', 'recover'])
    ap.add_argument('--journal', type=Path, help='Preserved SSH transaction in tmp')
    ap.add_argument('--restore', action='store_true',
                    help='Restore exact SSH originals only after read-only audit')
    ap.add_argument('--new-lock', action='store_true')
    ap.add_argument('--skip-runtime-test', action='store_true',
                    help='Only for the separate no-execution writer job after matching a verified digest')
    args = ap.parse_args()
    if args.action == 'recover':
        if args.journal is None or args.new_lock or args.skip_runtime_test:
            ap.error('recover requires --journal, and excludes install-only options')
        recover_ssh(args.journal, restore=args.restore)
        return
    if args.journal is not None or args.restore:
        ap.error('--journal and --restore apply only to recover')
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