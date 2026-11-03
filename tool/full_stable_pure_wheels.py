#!/usr/bin/env python3
"""Build a pure-Python PyYAML wheel from the reviewed official source sdist.

Never execute upstream setup.py or another package build backend. Copy only
audited upstream Python module bytes plus upstream metadata and license.
The wheel is reproducible and works on CPython 3.15 without a C compiler.
"""
from __future__ import annotations

import base64
import csv
from email.parser import BytesParser
import hashlib
import io
from pathlib import Path
import re
import tarfile
import zipfile

PY_YAML_MODULES = frozenset({
    '__init__.py', 'composer.py', 'constructor.py', 'cyaml.py', 'dumper.py',
    'emitter.py', 'error.py', 'events.py', 'loader.py', 'nodes.py', 'parser.py',
    'reader.py', 'representer.py', 'resolver.py', 'scanner.py',
    'serializer.py', 'tokens.py',
})
VERSION = '6.0.3'
WHEEL_NAME = 'PyYAML-6.0.3-py3-none-any.whl'
DIST_INFO = 'PyYAML-6.0.3.dist-info'
SOURCE_ROOT = 'pyyaml-6.0.3'
MAX_SOURCE_BYTES = 8 * 1024 * 1024


def _ensure(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def _source_member_name(name: str) -> str:
    _ensure(isinstance(name, str) and name and '\\' not in name and
            not name.startswith('/') and not re.search(r'[<>:"|?*\x00-\x1f]', name),
            'Unsafe official source path ' + repr(name))
    parts = name.rstrip('/').split('/')
    _ensure(all(p and p not in ('.', '..') and not p.endswith((' ', '.'))
                for p in parts) and parts[0] == SOURCE_ROOT,
            'Unexpected official source root or traversal: ' + repr(name))
    return '/'.join(parts)


def _record_hash(payload: bytes) -> str:
    return 'sha256=' + base64.urlsafe_b64encode(
        hashlib.sha256(payload).digest()).rstrip(b'=').decode('ascii')


def build_pyyaml_pure_wheel(source: Path, output_dir: Path,
                            expected_sha256: str) -> Path:
    _ensure(re.fullmatch(r'[0-9a-f]{64}', expected_sha256) is not None,
            'Missing fixed source SHA256')
    _ensure(source.is_file() and source.stat().st_size <= MAX_SOURCE_BYTES,
            'Invalid PyYAML official source size')
    _ensure(hashlib.sha256(source.read_bytes()).hexdigest() == expected_sha256,
            'Official PyYAML sdist SHA256 does not match reviewed pin')
    _ensure(output_dir.is_dir() and not (output_dir / WHEEL_NAME).exists(),
            'Derived wheel output must be a new target')
    necessary = {f'{SOURCE_ROOT}/lib/yaml/{n}' for n in PY_YAML_MODULES}
    necessary.update({f'{SOURCE_ROOT}/LICENSE', f'{SOURCE_ROOT}/PKG-INFO'})
    selected: dict[str, bytes] = {}
    names: set[str] = set()
    expanded = 0
    with tarfile.open(source, 'r:gz') as tar:
        for member in tar:
            name = _source_member_name(member.name)
            _ensure(name.casefold() not in names,
                    'Duplicate/case-colliding PyYAML member')
            names.add(name.casefold())
            _ensure(member.isfile() or member.isdir(),
                    'Refuse symlink, hardlink or special source member')
            if not member.isfile():
                continue
            expanded += member.size
            _ensure(0 <= member.size <= MAX_SOURCE_BYTES and
                    expanded <= MAX_SOURCE_BYTES,
                    'Unbounded PyYAML source expansion')
            if name in necessary:
                stream = tar.extractfile(member)
                _ensure(stream is not None, 'Missing PyYAML source stream')
                with stream:
                    payload = stream.read(MAX_SOURCE_BYTES + 1)
                _ensure(len(payload) == member.size,
                        'Truncated PyYAML source member')
                selected[name] = payload
            elif name.startswith(f'{SOURCE_ROOT}/lib/yaml/') and name.endswith('.py'):
                _ensure(False, 'Additional unreviewed PyYAML module')
    _ensure(set(selected) == necessary,
            'Official PyYAML source layout/metadata differs: ' +
            str(sorted(necessary - set(selected))))
    header = BytesParser().parsebytes(
        selected[f'{SOURCE_ROOT}/PKG-INFO'], headersonly=True)
    _ensure(header.get('Name') == 'PyYAML' and
            header.get('Version') == VERSION,
            'Unreviewed PyYAML package identity')
    _ensure(b"__version__ = '6.0.3'" in
            selected[f'{SOURCE_ROOT}/lib/yaml/__init__.py'],
            'Upstream pure Python implementation version mismatch')
    items: dict[str, bytes] = {
        f'yaml/{mod}': selected[f'{SOURCE_ROOT}/lib/yaml/{mod}']
        for mod in sorted(PY_YAML_MODULES)
    }
    items[f'{DIST_INFO}/METADATA'] = selected[f'{SOURCE_ROOT}/PKG-INFO']
    items[f'{DIST_INFO}/WHEEL'] = (
        'Wheel-Version: 1.0\n'
        'Generator: Codex-Portable audited official PyYAML pure-Python source\n'
        'Root-Is-Purelib: true\n'
        'Tag: py3-none-any\n'
    ).encode('ascii')
    items[f'{DIST_INFO}/licenses/LICENSE'] = selected[f'{SOURCE_ROOT}/LICENSE']
    rows = [[name, _record_hash(payload), str(len(payload))]
            for name, payload in sorted(items.items())]
    record_name = f'{DIST_INFO}/RECORD'
    rows.append([record_name, '', ''])
    buffer = io.StringIO(newline='')
    csv.writer(buffer, lineterminator='\n').writerows(rows)
    items[record_name] = buffer.getvalue().encode('utf-8')
    wheel = output_dir / WHEEL_NAME
    with zipfile.ZipFile(wheel, 'x', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as z:
        for filename, payload in sorted(items.items()):
            info = zipfile.ZipInfo(filename, date_time=(2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, payload)
    with zipfile.ZipFile(wheel) as z:
        _ensure(z.testzip() is None,
                'Derived PyYAML wheel failed ZIP CRC')
    return wheel
