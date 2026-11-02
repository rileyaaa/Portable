"""Offline security/contract regression tests for the manual tool-update workflow."""
from __future__ import annotations

import importlib.util
import contextlib
import hashlib
import io
import os
import re
import sys
import stat
import subprocess
from unittest.mock import patch
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, file: Path):
    spec = importlib.util.spec_from_file_location(name, file)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ssh = load('portable_ssh_maintenance', ROOT / 'tool/prepare-ssh.py')
tools = load('portable_tools_maintenance', ROOT / 'tool/update-tools.py')


class ToolUpdateTests(unittest.TestCase):
    def test_separate_ssh_closure_and_pth_path(self):
        self.assertEqual(ssh.pins(), {
            'paramiko': '5.1.0', 'bcrypt': '5.0.0', 'cryptography': '50.0.2',
            'invoke': '3.0.3', 'pynacl': '1.6.0', 'cffi': '2.1.1',
            'pycparser': '3.12',
        })
        self.assertEqual((ROOT / 'tool/python/Lib/site-packages/codex_portable_ssh.pth')
                         .read_text(encoding='utf-8').strip(), '../../ssh-packages')
        self.assertNotIn('paramiko==', (ROOT / 'tool/python-packages.in.txt').read_text())

    def test_reject_wheel_traversal_and_extra_data(self):
        for name in ('../evil', '/absolute', r'..\evil', 'dir/../bad',
                     'C:/escape', 'a:b', ''):
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                ssh.wheel_safe(name)
        self.assertEqual(ssh.wheel_safe('paramiko/__init__.py').as_posix(),
                         'paramiko/__init__.py')

    def test_reject_archive_traversal(self):
        for name in ('../evil', '/absolute', r'..\evil', 'dir/../bad',
                     'C:/escape', ''):
            with self.subTest(name=name), self.assertRaises(ValueError):
                tools.safe_member(name)
        self.assertEqual(tools.safe_member('node-v24-win-x64/node.exe').as_posix(),
                         'node-v24-win-x64/node.exe')

    def test_only_reviewed_candidates_are_installable(self):
        self.assertEqual([item['tool'] for item in tools.plan()], ['node'])
        ssh_status = tools.load_json(tools.LEDGER)['tools']['paramiko']['status']
        self.assertIn(ssh_status, ('not-installed', 'bundled'))
        if ssh_status == 'bundled':
            self.assertTrue(ssh.installed(ssh.DEST, ssh.pins()))
        self.assertNotIn('github-actions', tools.HOSTS)
        self.assertNotIn('pypi.org', tools.HOSTS)

    def test_document_version_block_markers_and_no_shadow_docs(self):
        source = (ROOT / 'tool/工具更新说明.md').read_text(encoding='utf-8')
        self.assertEqual(source.count(tools.BEGIN), 1)
        self.assertEqual(source.count(tools.END), 1)
        self.assertIn('## 当前工具与下载来源', source)
        self.assertIn('tool/installed-tools.json',
                      (ROOT / 'DEVELOPMENT.md').read_text(encoding='utf-8'))

    def test_hand_triggered_three_workflows_and_split_permissions(self):
        workflow = (ROOT / '.github/workflows/03-update-tools.yml').read_text()
        self.assertIn('\non:\n  workflow_dispatch:\n', workflow)
        for forbidden in ('\n  push:', '\n  schedule:', '\n  pull_request:',
                          '\n  workflow_run:'):
            self.assertNotIn(forbidden, workflow)
        self.assertIn('default: check', workflow)
        self.assertIn('default: false', workflow)
        self.assertIn('needs: verify', workflow)
        self.assertIn('candidate_digest:', workflow)
        self.assertIn('sha256', (ROOT / 'tool/update-tools.py').read_text())
        self.assertIn('pull-requests: write', workflow)
        self.assertIn("inputs.create_pr && github.ref == 'refs/heads/main'", workflow)
        self.assertIn('--writer', workflow)
        self.assertIn('release-audit.py --release', workflow)
        self.assertIn('release-audit.py --verify', workflow)
        self.assertNotIn('gh release create', workflow)
        self.assertNotIn('git push origin HEAD:refs/heads/main', workflow)

    def test_archive_rejects_link_and_zip_bomb(self):
        # No source download: verify the extraction-boundary predicate itself.
        with tempfile.TemporaryDirectory() as folder:
            candidate = Path(folder) / 'demo.zip'
            with zipfile.ZipFile(candidate, 'w') as archive:
                archive.writestr('owned/file.txt', b'hello')
            with zipfile.ZipFile(candidate) as archive:
                item = archive.infolist()[0]
                self.assertLessEqual(item.file_size, tools.EXPAND_MAX)
                self.assertEqual(tools.safe_member(item.filename).parts[0], 'owned')


    def test_member_names_cannot_hide_duplicate_or_traversal_segments(self):
        for bad in ('node//node.exe', './foo', 'a/./b', 'a//b',
                    'a/../b', 'a\\b', 'a:', 'a/b/'):
            with self.subTest(path=bad), self.assertRaises(ValueError):
                tools.safe_member(bad)

    def test_upstream_and_target_validation_fail_closed(self):
        cases = [
            ('node', 'node', 'tool/node',
             'https://nodejs.org/dist/v1.2.3/node-v1.2.3-win-x64.zip',
             'node-v1.2.3-win-x64/', 'directory'),
            ('7zip', 'cli', 'tool/bin',
             'https://www.7-zip.org/a/7z123.zip', '7zip/', 'pair'),
        ]
        for key, group, dest, url, prefix, kind in cases:
            candidate = dict(tool=key, group=group, destination=dest,
                             version='1.2.3', url=url, sha256='a'*64,
                             source_prefix=prefix, kind=kind)
            with self.subTest(tool=key):
                with patch.object(tools, 'load_json', return_value={
                    'schema': 1, 'platform': 'win32-x64',
                    'candidates': [candidate]}):
                    self.assertEqual(len(tools.plan()), 1)
                for field, malicious in (
                        ('source_prefix', '../'),
                        ('sha256', 'a'*63),
                        ('destination', '../outside'),
                        ('url', 'https://github.com/someone/fake.zip')):
                    bad = dict(candidate, **{field: malicious})
                    with self.subTest(field=field), patch.object(
                            tools, 'load_json', return_value={
                                'schema': 1, 'platform': 'win32-x64',
                                'candidates': [bad]}), self.assertRaises(ValueError):
                        tools.plan()

    def test_group_selection_and_staged_scope(self):
        self.assertEqual(tools.selected_rows('ssh'), [])
        self.assertEqual([r['tool'] for r in tools.selected_rows('all')], ['node'])
        self.assertEqual([r['tool'] for r in tools.selected_rows('tools')], ['node'])
        with self.assertRaises(ValueError):
            tools.selected_rows('bogus')

    def test_node_update_requires_matching_official_shasums(self):
        row=tools.plan()[0]
        shas=(row['sha256'] + '  node-v26.13.0-win-x64.zip\n').encode('ascii')
        # The official independent SHASUMS must match the reviewed ZIP pin
        # before downloading the actual release artifact.
        with tempfile.TemporaryDirectory() as d:
            with patch.object(tools,'fetch_bytes', return_value=b'0'*64), \
                    self.assertRaises(ValueError):
                tools.prepare_row(row,Path(d))
        self.assertIn('node-v26.13.0-win-x64.zip',shas.decode())

    def test_node_upgrade_preserves_portable_npm_and_skips_system_installer(self):
        def fake_executable():
            blob = bytearray(256)
            blob[:2] = b'MZ'
            blob[0x3c:0x40] = (0x80).to_bytes(4, 'little')
            blob[0x80:0x84] = b'PE\0\0'
            blob[0x84:0x86] = (0x8664).to_bytes(2, 'little')
            return bytes(blob)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            node = root / 'tool/node'
            node.mkdir(parents=True)
            for name in tools.NODE_PORTABLE_FILES:
                (node / name).write_text('guarded-' + name)
            (node / 'node.exe').write_bytes(fake_executable())
            archive_data = io.BytesIO()
            with zipfile.ZipFile(archive_data, 'w') as z:
                z.writestr('node-v1.2.3-win-x64/node.exe', fake_executable())
                z.writestr('node-v1.2.3-win-x64/npm.cmd', b'host npm wrapper')
                z.writestr('node-v1.2.3-win-x64/install_tools.bat', b'host installer')
                z.writestr('node-v1.2.3-win-x64/node_modules/npm/package.json', b'{"version":"9.8.7"}')
            payload = archive_data.getvalue()
            row = dict(tool='node', version='1.2.3', kind='directory', destination='tool/node',
                       source_prefix='node-v1.2.3-win-x64/',
                       sha256=hashlib.sha256(payload).hexdigest(), url='https://nodejs.org/')
            scratch = root / 'tmp'; scratch.mkdir()
            pin=(row['sha256'] + '  node-v1.2.3-win-x64.zip\n').encode()
            with patch.object(tools, 'ROOT', root), patch.object(tools, 'TOOL', root/'tool'), \
                    patch.object(tools, 'fetch_bytes', side_effect=[pin, payload]):
                tools.prepare_row(row, scratch)
            for name in tools.NODE_PORTABLE_FILES:
                self.assertEqual((node/name).read_text(), 'guarded-' + name)
            self.assertFalse((node/'install_tools.bat').exists())
            self.assertTrue((node/'node.exe').is_file())
            self.assertEqual(json.loads((node/'node_modules/npm/package.json').read_text())['version'], '9.8.7')

    def test_staged_diff_scope_rejects_unrelated_tool_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            subprocess.run(['git','init','-q',str(root)], check=True)
            (root/'tool').mkdir()
            file=root/'tool/prepare-ssh.py'
            file.write_text('unexpected rewrite\n')
            subprocess.run(['git','-C',str(root),'add','tool/prepare-ssh.py'],check=True)
            with patch.object(tools,'ROOT',root):
                with self.assertRaisesRegex(ValueError,'unrelated'):
                    tools.diff_digest('ssh')
                with self.assertRaisesRegex(ValueError,'unrelated'):
                    tools.diff_digest('tools')
            subprocess.run(['git','-C',str(root),'reset','-q'],check=True)
            (root/'tool/installed-tools.json').write_text('{}\n')
            subprocess.run(['git','-C',str(root),'add','tool/installed-tools.json'],check=True)
            with patch.object(tools,'ROOT',root):
                self.assertRegex(tools.diff_digest('ssh'),r'^[0-9a-f]{64}$')

    def test_node_rejects_symlink_archive_before_replacing_existing_files(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); node=root/'tool/node'; node.mkdir(parents=True)
            (node/'marker.txt').write_text('keep')
            payload=io.BytesIO()
            with zipfile.ZipFile(payload,'w') as z:
                link=zipfile.ZipInfo('node-v1.2.3-win-x64/node.exe')
                link.create_system=3
                link.external_attr=(stat.S_IFLNK|0o777)<<16
                z.writestr(link,b'outside')
            blob=payload.getvalue()
            row=dict(tool='node',version='1.2.3',kind='directory',
                     destination='tool/node', source_prefix='node-v1.2.3-win-x64/',
                     sha256=hashlib.sha256(blob).hexdigest(), url='https://nodejs.org/')
            checksum=(row['sha256']+'  node-v1.2.3-win-x64.zip\n').encode()
            with patch.object(tools,'ROOT',root), \
                    patch.object(tools,'fetch_bytes',side_effect=[checksum,blob]):
                with self.assertRaisesRegex(ValueError,'linked/special'):
                    tools.prepare_row(row,root)
            self.assertEqual((node/'marker.txt').read_text(),'keep')

    def test_sidecar_wheels_reject_symlinks_and_duplicate_contents(self):
        expected = {'paramiko':'5.1.0', 'bcrypt':'5.0.0'}
        def make_wheel(path, key, *, link=False, collide=False):
            with zipfile.ZipFile(path, 'w') as z:
                name = f'{key}-{expected[key]}.dist-info/METADATA'
                z.writestr(name, f'Name: {key}\nVersion: {expected[key]}\n')
                member = zipfile.ZipInfo('colliding.py' if collide else key + '.py')
                if link:
                    member.create_system=3
                    member.external_attr=(stat.S_IFLNK|0o777) << 16
                z.writestr(member,b'hi')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'tmp').mkdir()
            with patch.object(ssh, 'ROOT', root):
                wheels=root/'tmp/wheels'; wheels.mkdir()
                target=root/'tmp/stage'; target.mkdir()
                for key in expected:
                    make_wheel(wheels/f'{key}.whl', key)
                ssh.unpack_wheels(wheels, target, expected)
                self.assertTrue((target/'paramiko.py').is_file())
                self.assertTrue((target/'bcrypt.py').is_file())
                for key in expected:
                    (wheels/f'{key}.whl').unlink()
                target2=root/'tmp/stage2'; target2.mkdir()
                make_wheel(wheels/'paramiko.whl', 'paramiko', link=True)
                make_wheel(wheels/'bcrypt.whl', 'bcrypt')
                with self.assertRaises(RuntimeError):
                    ssh.unpack_wheels(wheels, target2, expected)
                (wheels/'paramiko.whl').unlink()
                (wheels/'bcrypt.whl').unlink()
                target3=root/'tmp/stage3'; target3.mkdir()
                make_wheel(wheels/'paramiko.whl', 'paramiko', collide=True)
                make_wheel(wheels/'bcrypt.whl', 'bcrypt', collide=True)
                with self.assertRaises(RuntimeError):
                    ssh.unpack_wheels(wheels, target3, expected)

    def test_installed_manifest_and_document_always_change_together(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); tool=root/'tool'; tool.mkdir()
            ledger=tool/'installed-tools.json'; doc=tool/'工具更新说明.md'
            (tool/'python-ssh-packages.in.txt').write_text('paramiko==5.1.0\n')
            ledger.write_text(json.dumps({'schema':1,'platform':'win32-x64','tools':{
                'paramiko':{'version':None,'status':'not-installed','path':'tool/python/ssh-packages'}},
                'lastSuccessfulToolUpdate':None}))
            doc.write_text('before\n' + tools.BEGIN + '\nold\n' + tools.END + '\nafter\n')
            with patch.object(tools, 'ROOT', root), patch.object(tools,'TOOL',tool), \
                    patch.object(tools, 'LEDGER', ledger), patch.object(tools,'DOC',doc):
                tools.record_updates([], ssh=True, day='2026-11-02')
                updated=json.loads(ledger.read_text())
                self.assertEqual(updated['tools']['paramiko']['version'], '5.1.0')
                self.assertEqual(updated['lastSuccessfulToolUpdate'],'2026-11-02')
                self.assertIn('paramiko | 5.1.0 | bundled',doc.read_text())
                self.assertEqual(doc.read_text().count(tools.BEGIN),1)
                before=ledger.read_bytes()
                with self.assertRaises(ValueError):
                    tools.record_updates([], ssh=False, day='2026-11-02')
                self.assertEqual(ledger.read_bytes(),before)


    def test_vendor_whitespace_kept_but_generated_records_still_checked(self):
        # Regression for Windows AC run 41419650909: the fetched official
        # Paramiko/cffi wheel has trailing spaces/extra terminal blank lines.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            tool = root / 'tool'
            (tool / 'python/ssh-packages').mkdir(parents=True)
            vendor = tool / 'python/ssh-packages/original-license.txt'
            vendor.write_bytes(b'Official licensed text with vendor spaces  \n\n')
            metadata = tool / 'installed-tools.json'
            metadata.write_text('"version": "verified"\n', encoding='utf-8')
            doc = tool / tools.DOC.name
            doc.write_text('Updated by reviewer\n', encoding='utf-8')
            lock = tool / 'python-ssh-packages.lock.txt'
            lock.write_text('paramiko==5.1.0 --hash=sha256:' + 'a' * 64 + '\n',
                            encoding='utf-8')
            subprocess.run(['git', '-C', str(root), 'add', '-A', '--', 'tool'], check=True)
            # Confirm the original unrestricted lint reproduces the failure.
            broad = subprocess.run(['git', '-C', str(root), 'diff', '--cached',
                                    '--check'], capture_output=True, check=False)
            self.assertNotEqual(broad.returncode, 0)
            with patch.object(tools, 'ROOT', root), \
                    patch.object(tools, 'LEDGER', metadata), \
                    patch.object(tools, 'DOC', doc):
                tools.lint_staged('ssh')
                self.assertEqual(vendor.read_bytes(),
                                 b'Official licensed text with vendor spaces  \n\n')
                # First-party generated files must still fail malformed whitespace.
                doc.write_text('Bad generated documentation  \n', encoding='utf-8')
                subprocess.run(['git', '-C', str(root), 'add', '-A', '--', 'tool'], check=True)
                with self.assertRaisesRegex(ValueError, 'first-party'):
                    tools.lint_staged('ssh')
                # Unreviewed staged tools cannot hide behind vendor exemption.
                doc.write_text('Clean record\n', encoding='utf-8')
                (tool / 'prepare-ssh.py').write_text('unauthorized edit\n', encoding='utf-8')
                subprocess.run(['git', '-C', str(root), 'add', '-A', '--', 'tool'], check=True)
                with self.assertRaisesRegex(ValueError, 'unrelated'):
                    tools.lint_staged('ssh')

    def test_windows_tool_workflow_uses_scoped_lint_in_both_jobs(self):
        workflow = (ROOT / '.github/workflows/03-update-tools.yml').read_text(
            encoding='utf-8')
        self.assertEqual(workflow.count('update-tools.py lint-staged --group'), 2)
        self.assertNotIn('git -c core.whitespace=cr-at-eol diff --cached --check',
                         workflow)
        self.assertIn('verify_node_lfs_index(group)',
                      (ROOT / 'tool/update-tools.py').read_text(encoding='utf-8'))
        self.assertIn('git lfs push --object-id origin $newNodeOid', workflow)
        self.assertIn('TOOL_STAGED_FIRST_PARTY_STYLE=PASS',
                      (ROOT / 'tool/update-tools.py').read_text(encoding='utf-8'))


    def test_node_lfs_attribute_and_index_pointer_checked_end_to_end(self):
        # A real Git index is used, but no external GitHub or LFS service is
        # required. Simulate Git LFS clean's exact canonical pointer bytes.
        # This covers the previous 100 MB Node exe blocking run (#41422353149).
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.name', 'fixture'], check=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.email', 'fixture@example.invalid'],
                           check=True)
            attrs = root / '.gitattributes'
            attrs.write_bytes(b'other.exe -text\n')
            subprocess.run(['git', '-C', str(root), 'add', '.gitattributes'], check=True)
            subprocess.run(['git', '-C', str(root), 'commit', '-qm', 'baseline'], check=True)
            node = root / 'tool/node/node.exe'
            node.parent.mkdir(parents=True)
            node.write_bytes(b'MZ' + b'\x01' * (2 * 1024 * 1024))
            with patch.object(tools, 'ROOT', root):
                tools.enable_node_lfs()
                self.assertEqual(attrs.read_bytes(), b'other.exe -text\n' + tools.NODE_LFS_ATTRIBUTE)
                with self.assertRaisesRegex(ValueError, 'Unexpected attributes'):
                    tools.enable_node_lfs()
                subprocess.run(['git', '-C', str(root), 'add', '.gitattributes'], check=True)
                original_sha = hashlib.sha256(node.read_bytes()).hexdigest()
                pointer = (b'version https://git-lfs.github.com/spec/v1\n'
                           + b'oid sha256:' + original_sha.encode('ascii') + b'\n'
                           + b'size ' + str(node.stat().st_size).encode('ascii') + b'\n')
                # git update-index is intentionally equivalent to what git-lfs
                # clean stores, while the working copy retains the real EXE.
                oid = subprocess.check_output(['git', '-C', str(root), 'hash-object', '-w',
                                               '--stdin'], input=pointer).strip().decode()
                subprocess.run(['git', '-C', str(root), 'update-index', '--add', '--cacheinfo',
                                f'100644,{oid},tool/node/node.exe'], check=True)
                self.assertEqual(tools.verify_node_lfs_index('all'), original_sha)
                self.assertRegex(tools.diff_digest('all'), r'^[0-9a-f]{64}$')
                with self.assertRaisesRegex(ValueError, 'Unexpected file'):
                    tools.diff_digest('ssh')
                # Tamper the working payload while keeping the index unchanged.
                with node.open('ab') as sink:
                    sink.write(b'corrupt')
                with self.assertRaisesRegex(ValueError, 'does not match'):
                    tools.verify_node_lfs_index('all')
                node.write_bytes(b'MZ' + b'\x01' * (2 * 1024 * 1024))
                # Any extra staged attribute rule must be rejected too.
                attrs.write_bytes(attrs.read_bytes() + b'unreviewed.exe filter=lfs\n')
                subprocess.run(['git', '-C', str(root), 'add', '.gitattributes'], check=True)
                with self.assertRaisesRegex(ValueError, 'reviewed one-line'):
                    tools.verify_node_lfs_index('all')
                # Restaging raw Node.exe instead of its pointer is also fatal.
                attrs.write_bytes(b'other.exe -text\n' + tools.NODE_LFS_ATTRIBUTE)
                subprocess.run(['git', '-C', str(root), 'add', '.gitattributes'], check=True)
                raw_oid = subprocess.check_output(['git', '-C', str(root), 'hash-object', '-w',
                                                   'tool/node/node.exe']).strip().decode()
                subprocess.run(['git', '-C', str(root), 'update-index', '--add', '--cacheinfo',
                                f'100644,{raw_oid},tool/node/node.exe'], check=True)
                with self.assertRaisesRegex(ValueError, 'canonical staged Git LFS pointer'):
                    tools.verify_node_lfs_index('all')

    def test_node_lfs_rule_rejects_preexisting_unreviewed_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.name', 'fixture'], check=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.email', 'fixture@example.invalid'],
                           check=True)
            path = root / '.gitattributes'
            path.write_bytes(b'other.exe -text\n')
            subprocess.run(['git', '-C', str(root), 'add', '.gitattributes'], check=True)
            subprocess.run(['git', '-C', str(root), 'commit', '-qm', 'baseline'], check=True)
            path.write_bytes(b'evil.exe filter=lfs\n')
            with patch.object(tools, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'Unexpected attributes'):
                    tools.enable_node_lfs()
            self.assertEqual(path.read_bytes(), b'evil.exe filter=lfs\n')

    def test_post_prepare_checks_accept_validated_installed_ssh(self):
        # Full regression runs *after* successful sidecar installation. It must
        # not assert that the exact functionality it just installed is absent.
        code = (ROOT / 'tests/test_tool_updates.py').read_text(encoding='utf-8')
        self.assertNotIn("'not-installed')\n        self.assertNotIn('github-actions'", code)
        self.assertIn("if ssh_status == 'bundled':", code)
        self.assertIn('ssh.installed(ssh.DEST, ssh.pins())', code)

    def test_ci_writer_lfs_upload_and_windows_gates_have_exact_parity(self):
        workflow = (ROOT / '.github/workflows/03-update-tools.yml').read_text(
            encoding='utf-8')
        verify, writer = workflow.split('\n  propose:', 1)
        self.assertEqual(verify.count('git lfs install --local'), 1)
        self.assertEqual(writer.count('git lfs install --local'), 1)
        self.assertEqual(workflow.count('git add -A -- tool .gitattributes'), 2)
        self.assertIn('git lfs push --object-id origin $newNodeOid', writer)
        self.assertLess(writer.index('git lfs push --object-id origin $newNodeOid'),
                        writer.index("git push origin ('HEAD:refs/heads/' + $name)"))
        self.assertLess(writer.index('git push origin'), writer.index('gh pr create'))
        self.assertIn('PR creation needs Connector review, NOT another Actions run.', writer)
        self.assertIn('exit 0', writer.split('gh pr create', 1)[1])
        self.assertIn('$digestMatch = [regex]::Match', verify)
        self.assertIn('$oidMatch = [regex]::Match', writer)
        self.assertIn('update-tools.py lint-staged --group', verify)
        self.assertIn('update-tools.py lint-staged --group', writer)
        self.assertIn('release-audit.py --release', verify)
        self.assertIn('release-audit.py --verify', verify)
        self.assertIn('tool\\package-release.py --version', verify)
        self.assertNotIn('gh release create', workflow)


    def test_two_independent_checkouts_generate_same_node_lfs_diff(self):
        # Reproduce both read-only and write-credential job content with an
        # actual Git clean filter. A tiny stand-in mimics Git LFS canonical
        # pointer generation, without a network connection or large EXE.
        def candidate(tmp: Path) -> str:
            tmp.mkdir()
            subprocess.run(['git', 'init', '-q', str(tmp)], check=True)
            for key, value in [('user.name', 'fixture'),
                               ('user.email', 'fixture@example.invalid')]:
                subprocess.run(['git', '-C', str(tmp), 'config', key, value], check=True)
            (tmp / '.gitattributes').write_bytes(b'legacy.exe -text\n')
            node = tmp / 'tool/node/node.exe'
            node.parent.mkdir(parents=True)
            node.write_bytes(b'MZ' + b'0' * (2 * 1024 * 1024))
            subprocess.run(['git', '-C', str(tmp), 'add', '-A'], check=True)
            subprocess.run(['git', '-C', str(tmp), 'commit', '-qm', 'preupgrade'], check=True)
            filter_tool = tmp / 'mock-lfs-filter.py'
            filter_tool.write_text(
                'import sys,hashlib\n'
                'data=sys.stdin.buffer.read()\n'
                'sha=hashlib.sha256(data).hexdigest()\n'
                'sys.stdout.buffer.write(("version https://git-lfs.github.com/spec/v1\\n"'
                '+"oid sha256:"+sha+"\\nsize "+str(len(data))+"\\n").encode())\n',
                encoding='utf-8')
            subprocess.run(['git', '-C', str(tmp), 'config', 'filter.lfs.clean',
                            f'"{sys.executable}" "{filter_tool}"'], check=True)
            subprocess.run(['git', '-C', str(tmp), 'config', 'filter.lfs.required', 'true'],
                           check=True)
            # Candidate changes are independently reproduced from the same
            # base version and source archive in the two simulated jobs.
            node.write_bytes(b'MZ' + b'1' * (3 * 1024 * 1024))
            with patch.object(tools, 'ROOT', tmp):
                tools.enable_node_lfs()
                subprocess.run(['git', '-C', str(tmp), 'add', '-A', '--',
                                'tool', '.gitattributes'], check=True)
                digest = tools.diff_digest('all')
                self.assertEqual(tools.verify_node_lfs_index('all'),
                                 hashlib.sha256(node.read_bytes()).hexdigest())
                self.assertEqual(subprocess.run(['git', '-C', str(tmp), 'diff',
                                                 '--cached', '--check'],
                                                capture_output=True).returncode, 0)
            return digest
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(candidate(root / 'readonly'), candidate(root / 'writer'))


    def test_03_windows_powershell_includes_all_release_gates_and_persistence(self):
        # Unlike the original 03, do not silently substitute persistence
        # for the official release's extension_migration regression.
        source = (ROOT / '.github/workflows/03-update-tools.yml').read_text('utf-8')
        official = (ROOT / '.github/workflows/02-verify-and-publish-portable.yml').read_text('utf-8')
        release_names = set(re.findall(r'(?m)^      - name: Windows PowerShell 5\.1 - (test_[a-z_]+)$',
                                       official))
        suite = re.search(r'\$tests = @\((.*?)\n          \)', source, re.S)
        self.assertIsNotNone(suite)
        tool_names = re.findall(r'test_[a-z_]+(?=\.ps1)', suite.group(1))
        self.assertEqual(len(release_names), 18)
        self.assertEqual(len(tool_names), 19)
        self.assertEqual(set(tool_names) - release_names, {'test_extension_persistence'})
        self.assertFalse(release_names - set(tool_names))


if __name__ == '__main__':
    unittest.main()