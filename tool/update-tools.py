#!/usr/bin/env python3
"""Audit and stage manually pinned Windows tools; no automatic 'latest' replacement.

Mode 'check' can query upstream public release metadata. Mode 'prepare' applies
only reviewed sha256-pinned archive mappings on an isolated CI checkout. The
writer job must reproduce exactly the verifier's Git diff digest before a PR.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).absolute().parent.parent
TOOL = ROOT / 'tool'
LEDGER = TOOL / 'installed-tools.json'
PLAN = TOOL / 'tool-update-plan.json'
DOC = TOOL / '工具更新说明.md'
BEGIN = '<!-- TOOL_VERSIONS_BEGIN -->'
END = '<!-- TOOL_VERSIONS_END -->'
SOURCES = {
    'ripgrep': 'BurntSushi/ripgrep',
    'fd': 'sharkdp/fd',
    'jq': 'jqlang/jq',
}
ALLOWED = {
    'node': ('tool/node/',),
    'adb': ('tool/android/platform-tools/',),
    'cli': ('tool/bin/7z.exe', 'tool/bin/7z.dll', 'tool/bin/rg.exe',
            'tool/bin/fd.exe', 'tool/bin/jq.exe'),
}
HOSTS = {'github.com', 'nodejs.org', 'dl.google.com', '7-zip.org', 'www.7-zip.org'}
ARCHIVE_MAX = 150 * 1024 * 1024
TOOL_GROUP = {'node': 'node', 'adb': 'adb', 'ripgrep': 'cli',
              'fd': 'cli', 'jq': 'cli', '7zip': 'cli'}
EXPAND_MAX = 450 * 1024 * 1024


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def ordinary(path: Path, *, directory: bool = False) -> None:
    info = path.lstat()
    require(not stat.S_ISLNK(info.st_mode) and not (getattr(info, 'st_file_attributes', 0) & 0x400),
            'Reparse/symlink refused: ' + str(path))
    if directory:
        require(stat.S_ISDIR(info.st_mode), 'Expected directory: ' + str(path))
    else:
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                'Expected ordinary file: ' + str(path))


def bounded(path: Path) -> Path:
    require('..' not in path.parts, 'Parent traversal refused')
    actual = Path(os.path.abspath(path))
    try:
        relative = actual.relative_to(ROOT)
    except ValueError as error:
        raise ValueError('Outside portable root') from error
    cursor = Path(ROOT.anchor)
    for segment in ROOT.parts[1:]:
        cursor /= segment
        ordinary(cursor, directory=True)
    cursor = ROOT
    for segment in relative.parts:
        cursor /= segment
        if cursor.exists() or cursor.is_symlink():
            ordinary(cursor, directory=cursor.is_dir())
    return actual


def load_json(path: Path) -> dict:
    ordinary(path)
    return json.loads(path.read_text(encoding='utf-8'))


def ledger() -> dict:
    data = load_json(LEDGER)
    require(data.get('schema') == 1 and data.get('platform') == 'win32-x64' and
            isinstance(data.get('tools'), dict), 'Invalid installed tool inventory')
    return data


def plan() -> list[dict]:
    obj = load_json(PLAN)
    require(obj.get('schema') == 1 and obj.get('platform') == 'win32-x64',
            'Invalid pinned update plan')
    rows = obj.get('candidates')
    require(isinstance(rows, list) and len(rows) <= 20, 'Invalid update count')
    names = set()
    destinations = set()
    for row in rows:
        require(isinstance(row, dict), 'Invalid candidate record')
        tool = row.get('tool')
        group = row.get('group')
        require(isinstance(tool, str) and re.fullmatch(r'[a-z0-9-]+', tool)
                and group in ALLOWED, 'Unknown tool/update group')
        require(tool not in names, 'Duplicate tool')
        require(TOOL_GROUP.get(tool) == group, 'Tool/group identity mismatch')
        names.add(tool)
        version = row.get('version')
        require(isinstance(version, str) and re.fullmatch(r'[0-9][A-Za-z0-9.+_-]{0,40}', version),
                'Invalid exact target version')
        source = row.get('url')
        require(isinstance(source, str), 'Source URL missing')
        url = urlsplit(source)
        require(url.scheme == 'https' and url.hostname in HOSTS and not url.username and
                not url.password and not url.query and not url.fragment and url.port in (None, 443),
                'Source is not an approved official HTTPS origin')
        require(re.fullmatch(r'[a-f0-9]{64}', str(row.get('sha256', ''))),
                'A reviewed real SHA256 is mandatory')
        src_prefix = row.get('source_prefix')
        require(isinstance(src_prefix, str) and bool(src_prefix) and src_prefix.endswith('/') and
                '/' not in src_prefix.rstrip('/').strip('/'),
                'Source prefix must name one archive root directory')
        dest = row.get('destination')
        require(isinstance(dest, str) and dest.startswith('tool/') and '..' not in PurePosixPath(dest).parts,
                'Invalid owned destination')
        allowed = ALLOWED[group]
        require(any((dest + '/').startswith(prefix) if prefix.endswith('/') else dest == prefix
                    for prefix in allowed), 'Destination is not in the owned tool group')
        require(dest not in destinations, 'Duplicate destination')
        if tool in ('ripgrep', 'fd', 'jq'):
            require(dest == {'ripgrep': 'tool/bin/rg.exe', 'fd': 'tool/bin/fd.exe',
                             'jq': 'tool/bin/jq.exe'}[tool], 'Mismatched CLI destination')
        if tool == '7zip':
            require(dest in ('tool/bin/7z.exe', 'tool/bin/7z.dll'), 'Invalid 7z component')
        destinations.add(dest)
        kind = row.get('kind')
        require(kind in ('single', 'directory'), 'Invalid installation kind')
        if kind == 'directory':
            require(group in ('node', 'adb') and dest in ('tool/node', 'tool/android/platform-tools'),
                    'Only reviewed complete directory replacements are allowed')
        else:
            require(group == 'cli' and isinstance(row.get('source_file'), str),
                    'Single-file candidates need a fixed member path')
    return rows


def safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    require(name and not name.startswith(('/', '\\')) and '\\' not in name and
            ':' not in name and not path.is_absolute() and '..' not in path.parts and
            all(part not in ('', '.') for part in path.parts), 'Unsafe archive name: ' + name)
    return path


def fetch_bytes(url: str, limit: int) -> bytes:
    with urlopen(Request(url, headers={'User-Agent': 'Codex-Portable-Maintenance/1'}), timeout=25) as response:
        # A pinned digest is still mandatory for binary downloads, even if redirected.
        data = response.read(limit + 1)
    require(len(data) <= limit, 'Remote data exceeds the download limit')
    return data



def validate_pe(path: Path) -> None:
    if path.suffix.lower() not in ('.exe', '.dll'):
        return
    ordinary(path)
    with path.open('rb') as file:
        header = file.read(4096)
        require(len(header) >= 64 and header[:2] == b'MZ', 'Missing Windows PE header')
        offset = int.from_bytes(header[0x3c:0x40], 'little')
        require(0x40 <= offset < 3072 and len(header) >= offset + 6, 'Invalid PE offset')
        require(header[offset:offset+4] == b'PE\0\0', 'Invalid PE signature')
        require(int.from_bytes(header[offset+4:offset+6], 'little') == 0x8664,
                'Tool is not Windows AMD64')


def probe_binary(path: str, arguments: list[str], pattern: str) -> str | None:
    binary = bounded(ROOT / path)
    if not binary.is_file() or os.name != 'nt':
        return None
    ordinary(binary)
    env = {key: os.environ[key] for key in ('SystemRoot','WINDIR','COMSPEC','PATHEXT') if key in os.environ}
    env['PATH'] = str(binary.parent) + os.pathsep + str(Path(env.get('SystemRoot', 'C:\\Windows')) / 'System32')
    # This is an explicit Windows tool-version probe; no host PATH or user config.
    data = subprocess.run([str(binary), *arguments], cwd=ROOT, env=env,
                          capture_output=True, timeout=12)
    require(data.returncode == 0, 'Version probe failed: ' + path)
    combined = (data.stdout + b'\n' + data.stderr).decode('utf-8', errors='replace')
    match = re.search(pattern, combined)
    require(match is not None, 'Unrecognized version output: ' + path)
    return match.group(1).lstrip('v')


def probe_versions() -> dict[str, str | None]:
    cases = {
        'node': ('tool/node/node.exe', ['--version'], r'v(\d+\.\d+\.\d+)'),
        'ripgrep': ('tool/bin/rg.exe', ['--version'], r'ripgrep (\d+\.\d+\.\d+)'),
        'fd': ('tool/bin/fd.exe', ['--version'], r'fd (\d+\.\d+\.\d+)'),
        'jq': ('tool/bin/jq.exe', ['--version'], r'jq-(\d+\.\d+(?:\.\d+)?)'),
        'adb': ('tool/android/platform-tools/adb.exe', ['version'], r'Version (\d+\.\d+\.\d+)'),
        '7zip': ('tool/bin/7z.exe', ['i'], r'7-Zip (\d+\.\d+)'),
    }
    values: dict[str, str | None] = {}
    for key, (path, args, match) in cases.items():
        try:
            values[key] = probe_binary(path, args, match)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            values[key] = None
    return values


def verify_candidates() -> None:
    observed = probe_versions()
    for row in plan():
        version = observed.get(row['tool'])
        if row['tool'] == 'adb':
            prop = (ROOT / 'tool/android/platform-tools/source.properties').read_text()
            metadata = re.search(r'^Pkg.Revision=(.+)$', prop, re.M)
            require(metadata is not None and metadata.group(1).strip() == row['version'],
                    'ADB package metadata differs from candidate version')
            # adb.exe reports internal version 1.0.41, not Platform Tools 37.x.
            require(version is not None, 'ADB executable probe failed')
        else:
            require(version == row['version'], 'Native installed version mismatch for ' + row['tool'])
    print('WINDOWS_TOOL_VERSION_PROBES=PASS')


def audit(online: bool = False) -> None:
    tools = ledger()['tools']
    result = {'source': 'tracked inventory; not an executable version attestation',
              'tools': tools, 'upstream': {},
              'observed_native_versions': probe_versions() if os.name == 'nt' else {}}
    if online:
        for key, repo in SOURCES.items():
            try:
                payload = json.loads(fetch_bytes('https://api.github.com/repos/' + repo + '/releases/latest',
                                                 128 * 1024))
                result['upstream'][key] = {'latest_tag': payload.get('tag_name'),
                                           'official_repo': repo}
            except (OSError, ValueError, TimeoutError, KeyError) as error:
                result['upstream'][key] = {'error': type(error).__name__}
        try:
            versions = json.loads(fetch_bytes('https://nodejs.org/dist/index.json', 400 * 1024))
            stable = next((row for row in versions if row.get('lts') and
                           not re.search(r'-(?:alpha|beta|rc)', row.get('version', ''))), None)
            result['upstream']['node-lts'] = stable.get('version') if stable else 'unavailable'
        except (OSError, ValueError, TimeoutError, KeyError) as error:
            result['upstream']['node-lts'] = {'error': type(error).__name__}
    print(json.dumps(result, ensure_ascii=False, indent=2))


def prepare_row(row: dict, temp: Path) -> None:
    binary = fetch_bytes(row['url'], ARCHIVE_MAX)
    require(hashlib.sha256(binary).hexdigest() == row['sha256'],
            'Downloaded SHA256 differs for ' + row['tool'])
    import io
    prefix = row['source_prefix']
    dest = bounded(ROOT / row['destination'])
    total = 0
    staging = temp / ('candidate-' + row['tool'])
    staging.mkdir()
    members = {}
    with zipfile.ZipFile(io.BytesIO(binary)) as archive:
        for info in archive.infolist():
            path = safe_member(info.filename.rstrip('/'))
            file = path.as_posix()
            if file == prefix.rstrip('/') or info.is_dir():
                continue
            require(info.file_size <= ARCHIVE_MAX and total + info.file_size <= EXPAND_MAX,
                    'Unbounded archive expansion')
            mode = (info.external_attr >> 16) & 0o170000
            require(mode in (0, stat.S_IFREG, stat.S_IFDIR), 'Archive contains linked/special files')
            if not file.startswith(prefix):
                continue
            rel = file[len(prefix):]
            safe_member(rel)
            lower = rel.lower()
            require(lower not in members, 'Case-colliding extracted member')
            members[lower] = (rel, info)
            total += info.file_size
        require(members, 'No matching approved archive payload')
        if row['kind'] == 'single':
            member = row['source_file']
            require(member.lower() in members and len(members) >= 1, 'Missing requested source file')
            # Only the explicitly requested file is installed; other archive entries stay ignored.
            rel, entry = members[member.lower()]
            require(dest.suffix.lower() in ('.exe', '.dll'), 'Unsupported single-file destination')
            staged = staging / dest.name
            staged.write_bytes(archive.read(entry))
            validate_pe(staged)
            bounded(dest.parent)
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged, dest)
        else:
            for rel, entry in members.values():
                require(PurePosixPath(rel).name.lower() != 'install_tools.bat', 'System installer is forbidden')
                file = staging.joinpath(*safe_member(rel).parts)
                file.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, file.open('xb') as sink:
                    shutil.copyfileobj(source, sink)
            for file in staging.rglob('*'):
                if file.is_file() and file.suffix.lower() in ('.exe', '.dll'):
                    validate_pe(file)
            require(dest.is_dir(), 'Existing tool directory is missing')
            backup = temp / ('backup-' + row['tool'])
            dest.rename(backup)
            try:
                staging.rename(dest)
            except Exception:
                backup.rename(dest)
                raise


def record_updates(rows: list[dict], *, ssh: bool, day: str) -> None:
    require(re.fullmatch(r'20[0-9]{2}-[0-9]{2}-[0-9]{2}', day) is not None,
            'Pass a fixed reviewed update date')
    doc = DOC.read_text(encoding='utf-8')
    state = ledger()
    for row in rows:
        require(row['tool'] in state['tools'], 'Unknown ledger tool')
        state['tools'][row['tool']]['version'] = row['version']
        state['tools'][row['tool']]['status'] = 'bundled'
        if row['tool'] == 'node':
            npm = json.loads((ROOT / 'tool/node/node_modules/npm/package.json').read_text(encoding='utf-8'))
            state['tools']['npm'].update(version=npm['version'], status='bundled')
        if row['tool'] == 'adb':
            doc = re.sub(r'Platform Tools \d+(?:\.\d+)+', 'Platform Tools ' + row['version'], doc)
    if ssh:
        ssh_data = (TOOL / 'python-ssh-packages.in.txt').read_text(encoding='utf-8')
        match = re.search(r'^paramiko==([^\s]+)', ssh_data, flags=re.MULTILINE)
        require(match is not None, 'Missing pinned Paramiko version')
        state['tools']['paramiko'].update(version=match.group(1), status='bundled')
    require(rows or ssh, 'No successful change to record')
    state['lastSuccessfulToolUpdate'] = day
    ledger_text = json.dumps(state, ensure_ascii=False, indent=2) + '\n'
    table = [BEGIN, '| 工具 | 随包版本 | 状态 | 路径 |', '| --- | --- | --- | --- |']
    for key, value in state['tools'].items():
        ver = value.get('version') or '待 Windows 原生核对'
        table.append(f"| {key} | {ver} | {value['status']} | `{value['path']}` |")
    table.append(END)
    updated = '\n'.join(table)
    if BEGIN in doc and END in doc:
        pattern = re.escape(BEGIN) + r'.*?' + re.escape(END)
        require(len(re.findall(pattern, doc, re.S)) == 1, 'Duplicate tool version section')
        doc = re.sub(pattern, lambda _: updated, doc, count=1, flags=re.S)
    else:
        marker = '## 当前工具与下载来源'
        require(doc.count(marker) == 1, 'Tool documentation structure changed')
        doc = doc.replace(marker, '## 已安装工具版本台账\n\n' + updated + '\n\n' + marker)
    DOC.write_text(doc, encoding='utf-8', newline='\n')
    LEDGER.write_text(ledger_text, encoding='utf-8', newline='\n')


def prepare(group: str, *, day: str, writer: bool = False) -> None:
    require(os.name == 'nt' and sys.maxsize > 2**32, 'Prepare requires Windows x64')
    require(Path(sys.executable).absolute() == (TOOL / 'python/python.exe').absolute(),
            'Must use the bundled Windows Python')
    selected = plan()
    if group == 'ssh':
        require(not selected, 'SSH-only mode refuses unrelated candidate updates')
        ssh = True
    else:
        ssh = group == 'all'
        require(selected or ssh, 'No reviewed pinned tool candidates')
    scratch = bounded(ROOT / 'tmp')
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='tool-updates-', dir=scratch) as dirname:
        temp = Path(dirname)
        for row in selected:
            prepare_row(row, temp)
    if ssh:
        # SSH installation performs its own wheel-only hash verification and import tests.
        args = [str(TOOL / 'python/python.exe'), '-E', '-s', '-B',
                str(TOOL / 'prepare-ssh.py'), 'install', '--new-lock']
        if writer:
            args.append('--skip-runtime-test')
        subprocess.run(args, cwd=ROOT, timeout=600, check=True)
    record_updates(selected, ssh=ssh, day=day)
    print('TOOL_CANDIDATE_STAGED=PASS')


def diff_digest(group: str) -> str:
    change = subprocess.check_output(['git', '-c', 'core.quotepath=false', 'diff',
                                     '--cached', '--name-only', '-z'], cwd=ROOT)
    paths = [p.decode('utf-8') for p in change.split(b'\0') if p]
    require(paths, 'No reviewed tool changes are staged')
    for path in paths:
        require(path.startswith('tool/') and not path.endswith(('.pyc', '.pyo')) and
                not path.startswith('tool/automation/browsers/'),
                'Unexpected file touched by tool update: ' + path)
        if group == 'ssh':
            require(path.startswith(('tool/python/ssh-packages/', 'tool/python-ssh-packages.lock.txt',
                                     'tool/installed-tools.json', 'tool/工具更新说明.md')),
                    'SSH-only update modified another component: ' + path)
    patch = subprocess.check_output(['git', '-c', 'core.quotepath=false', 'diff',
                                     '--cached', '--binary', '--no-ext-diff'], cwd=ROOT)
    return hashlib.sha256(patch).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['check', 'prepare', 'digest', 'verify'])
    ap.add_argument('--group', choices=['ssh', 'tools', 'all'], default='all')
    ap.add_argument('--online', action='store_true')
    ap.add_argument('--day', default=None)
    ap.add_argument('--writer', action='store_true',
                    help='No native wheel import in digest-checked writer job')
    args = ap.parse_args()
    if args.command == 'check':
        audit(args.online)
    elif args.command == 'prepare':
        prepare(args.group, day=args.day or '', writer=args.writer)
    elif args.command == 'verify':
        verify_candidates()
    else:
        print('TOOL_DIFF_SHA256=' + diff_digest(args.group))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, subprocess.CalledProcessError) as err:
        print('TOOL_UPDATE_ERROR=' + str(err), file=sys.stderr)
        raise SystemExit(2)
