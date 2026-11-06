"""Offline security/contract regression tests for the manual tool-update workflow."""
from __future__ import annotations

import importlib.util
import ast
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

# A synthetic historical Node candidate MUST carry all fields consumed by
# diff_digest(), even though production's current plan only contains CLI tools.
NODE_LFS_FIXTURE = {
    'tool': 'node',
    'version': '26.13.0',
    'destination': 'tool/node',
    'kind': 'directory',
}


def explicit_utf8_text_io(call: ast.Call) -> bool:
    """Accept explicitly declared UTF-8 or UTF-8-SIG, never host defaults."""
    choices = [kw.value for kw in call.keywords if kw.arg == 'encoding']
    index = 0 if call.func.attr == 'read_text' else 1
    if len(call.args) > index:
        choices.append(call.args[index])
    return any(isinstance(value, ast.Constant) and isinstance(value.value, str)
               and value.value.lower().replace('-', '').replace('_', '')
               in ('utf8', 'utf8sig') for value in choices)


class ToolUpdateTests(unittest.TestCase):
    def setUp(self):
        # These tests deliberately audit the fixed, reviewed legacy plan.
        # 03/auto sets TOOL_AUTO_UPDATE_PLAN=1 for candidate staging; if this
        # leaks into the legacy fixture assertions after installation, a real
        # update fails the full Windows suite despite valid candidate bytes.
        # Independently test the dynamic selector in the dedicated test below.
        pinned = patch.dict(os.environ, {'TOOL_AUTO_UPDATE_PLAN': ''})
        pinned.start()
        self.addCleanup(pinned.stop)

    def test_both_tool_writer_routes_share_full_transfer_lock(self):
        # Prevent a later refactor from shortening lock scope or introducing
        # a second incompatible lock file for one of the maintenance writers.
        updater = (ROOT / 'tool/update-tools.py').read_text(encoding='utf-8')
        stager = (ROOT / 'tool/full-stable-prepare.py').read_text(encoding='utf-8')
        entry = 'source = Path(__file__).resolve().with_name("full-stable-transfer.py")'
        for script in (updater, stager):
            self.assertIn(entry, script)
            self.assertIn('transfer.ROOT = ROOT', script)
            self.assertIn('return transfer.exclusive_transfer_lock()', script)
        updating = updater.split(
            'def prepare(group: str, *, day: str, writer: bool = False) -> None:',
            1)[1].split('\ndef diff_digest(', 1)[0]
        staging = stager.split(
            'def prepare(plan: dict) -> None:', 1)[1].split('\ndef main()', 1)[0]
        self.assertEqual(updating.count('with shared_upgrade_lock():'), 1)
        self.assertEqual(staging.count('with shared_upgrade_lock():'), 1)
        self.assertLess(updating.index('with shared_upgrade_lock():'),
                        updating.index('prepare_row(row, temp)'))
        self.assertLess(updating.index('with shared_upgrade_lock():'),
                        updating.index('ssh_module._install_under_parent_lock('))
        self.assertLess(updating.index('with shared_upgrade_lock():'),
                        updating.index('record_updates(selected, ssh=ssh, day=day)'))
        self.assertLess(staging.index('with shared_upgrade_lock():'),
                        staging.index('stage_npm(plan, temp, evidence)'))
        self.assertLess(staging.index('with shared_upgrade_lock():'),
                        staging.index('update_version_inventory(plan, evidence)'))

    def test_ssh_installer_uses_the_shared_lock_without_child_deadlock(self):
        ssh_script = (ROOT / 'tool/prepare-ssh.py').read_text(encoding='utf-8')
        updater = (ROOT / 'tool/update-tools.py').read_text(encoding='utf-8')
        self.assertIn(
            'source = Path(__file__).resolve().with_name("full-stable-transfer.py")',
            ssh_script)
        self.assertIn('return transfer.exclusive_transfer_lock()', ssh_script)
        public = ssh_script.split(
            'def install(*, new_lock: bool, runtime_test: bool) -> None:', 1)[1].split(
            '\ndef _install_under_parent_lock(', 1)[0]
        self.assertIn('with shared_upgrade_lock():', public)
        self.assertIn('_install_under_parent_lock(', public)
        self.assertIn('def _install_under_parent_lock(', ssh_script)
        self.assertNotIn('--skip-lock', ssh_script)
        updating = updater.split(
            'def prepare(group: str, *, day: str, writer: bool = False) -> None:',
            1)[1].split('\ndef diff_digest(', 1)[0]
        self.assertLess(updating.index('with shared_upgrade_lock():'),
                        updating.index('ssh_module._install_under_parent_lock('))
        self.assertIn('new_lock=True, runtime_test=not writer', updating)
        self.assertNotIn("str(TOOL / 'prepare-ssh.py'), 'install'", updating)
        # The private in-process path must preserve the sanitized pip child
        # environment and the installed CPython/ledger version checks.
        self.assertIn("env=env, timeout=360, check=False", ssh_script)
        self.assertIn("Installation requires Windows x64", ssh_script)
        self.assertIn("installed version ledger", ssh_script)

    def test_ssh_publish_rolls_back_file_lock_and_directory_rename_faults(self):
        # No Windows runtime, network, real wheels or Git credentials needed:
        # exercise exactly the sidecar publish helper with synthetic byte trees.
        original_rename = Path.rename
        original_replace = os.replace
        modes = ('old-rename-before', 'old-rename-after',
                 'candidate-rename-after', 'lock-replace-before',
                 'lock-replace-after')
        for mode in modes:
            with self.subTest(fault=mode), tempfile.TemporaryDirectory() as d:
                root = Path(d) / 'checkout'
                parent = root / 'tool/python'
                parent.mkdir(parents=True)
                dest = parent / 'ssh-packages'
                dest.mkdir()
                (dest / 'old.py').write_bytes(b'original-user-data')
                resolver = root / 'tool/python-ssh-packages.lock.txt'
                resolver.write_bytes(b'old-resolver-lock')
                temp = root / 'tmp/ssh-maintenance-fixture'
                staged = temp / 'ssh-packages'
                staged.mkdir(parents=True)
                (staged / 'new.py').write_bytes(b'verified-wheel-payload')
                staged_lock = temp / 'ssh.lock'
                staged_lock.write_bytes(b'new-resolver-lock')
                candidate = temp / 'publish.lock'

                def fault_rename(self, target):
                    if mode == 'old-rename-before' and self == dest:
                        raise OSError('synthetic SSH first rename fault')
                    result = original_rename(self, target)
                    if ((mode == 'old-rename-after' and self == dest) or
                            (mode == 'candidate-rename-after' and self == staged)):
                        raise OSError('synthetic SSH post-rename fault')
                    return result

                def fault_replace(src, target):
                    if mode == 'lock-replace-before' and Path(src) == candidate:
                        raise OSError('synthetic SSH lock replacement fault')
                    result = original_replace(src, target)
                    if mode == 'lock-replace-after' and Path(src) == candidate:
                        raise OSError('synthetic SSH post-lock replacement fault')
                    return result

                with (patch.object(ssh, 'ROOT', root),
                      patch.object(ssh, 'DEST', dest),
                      patch.object(ssh, 'LOCK', resolver),
                      patch.object(Path, 'rename', new=fault_rename),
                      patch.object(ssh.os, 'replace', side_effect=fault_replace)):
                    with self.assertRaisesRegex(OSError, 'synthetic SSH'):
                        ssh._publish_ssh_sidecar(temp, staged_lock)
                self.assertEqual((dest / 'old.py').read_bytes(), b'original-user-data')
                self.assertFalse((dest / 'new.py').exists())
                self.assertEqual(resolver.read_bytes(), b'old-resolver-lock')
                self.assertFalse((temp / 'previous-ssh').exists())
                journal = json.loads((temp / 'publish-recovery.json').read_text(
                    encoding='utf-8'))
                self.assertTrue(journal['oldSidecar'])
                self.assertEqual(journal['schema'], 1)
                self.assertEqual(journal['oldLockSHA256'],
                                 hashlib.sha256(b'old-resolver-lock').hexdigest())

    def test_ssh_publish_preserves_backup_on_foreign_edit_and_refuses_stale_map(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'checkout'
            parent = root / 'tool/python'
            parent.mkdir(parents=True)
            dest = parent / 'ssh-packages'
            dest.mkdir()
            (dest / 'old.py').write_bytes(b'preserved-old-sidecar')
            resolver = root / 'tool/python-ssh-packages.lock.txt'
            resolver.write_bytes(b'old-lock')
            temp = root / 'tmp/ssh-maintenance-fixture'
            staged = temp / 'ssh-packages'
            staged.mkdir(parents=True)
            (staged / 'new.py').write_bytes(b'new-sidecar')
            staged_lock = temp / 'ssh.lock'
            staged_lock.write_bytes(b'new-lock')
            original_rename = Path.rename
            poison = {'triggered': False}

            def concurrent_edit(self, target):
                result = original_rename(self, target)
                if self == staged and not poison['triggered']:
                    poison['triggered'] = True
                    (dest / 'new.py').write_bytes(b'FOREIGN-EDIT-DO-NOT-DELETE')
                    raise OSError('synthetic foreign edit after candidate rename')
                return result

            with (patch.object(ssh, 'ROOT', root),
                  patch.object(ssh, 'DEST', dest),
                  patch.object(ssh, 'LOCK', resolver),
                  patch.object(Path, 'rename', new=concurrent_edit)):
                with self.assertRaisesRegex(
                        ssh.SSHRollbackIncomplete, 'original backups at'):
                    ssh._publish_ssh_sidecar(temp, staged_lock)
            self.assertTrue(poison['triggered'])
            self.assertEqual((dest / 'new.py').read_bytes(),
                             b'FOREIGN-EDIT-DO-NOT-DELETE')
            self.assertEqual((temp / 'previous-ssh/old.py').read_bytes(),
                             b'preserved-old-sidecar')
            self.assertEqual(resolver.read_bytes(), b'old-lock')
            self.assertTrue((temp / 'publish-recovery.json').exists())
            # Failed SSH recovery is intentionally NOT an automatic
            # reset/hard-delete. The preserved temp blocks another install.
            implementation = (ROOT / 'tool/prepare-ssh.py').read_text(
                encoding='utf-8')
            self.assertIn("if any(scratch.glob('ssh-maintenance-*')):", implementation)
            self.assertIn('except SSHRollbackIncomplete:', implementation)
            self.assertIn('preserve = True', implementation)

    def test_ssh_publish_detects_journal_flush_errors_before_original_rename(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'checkout'
            parent = root / 'tool/python'
            parent.mkdir(parents=True)
            dest = parent / 'ssh-packages'
            dest.mkdir()
            (dest / 'old.py').write_bytes(b'keep-me')
            resolver = root / 'tool/python-ssh-packages.lock.txt'
            resolver.write_bytes(b'keep-lock')
            temp = root / 'tmp/ssh-maintenance-fixture'
            staged = temp / 'ssh-packages'
            staged.mkdir(parents=True)
            (staged / 'new.py').write_bytes(b'candidate')
            staged_lock = temp / 'ssh.lock'
            staged_lock.write_bytes(b'candidate-lock')
            with (patch.object(ssh, 'ROOT', root),
                  patch.object(ssh, 'DEST', dest),
                  patch.object(ssh, 'LOCK', resolver),
                  patch.object(ssh.os, 'fsync',
                               side_effect=OSError('synthetic journal flush fault'))):
                with self.assertRaisesRegex(OSError, 'journal flush fault'):
                    ssh._publish_ssh_sidecar(temp, staged_lock)
            self.assertEqual((dest / 'old.py').read_bytes(), b'keep-me')
            self.assertEqual(resolver.read_bytes(), b'keep-lock')
            self.assertFalse((temp / 'previous-ssh').exists())

    def test_ssh_rejects_dangling_junction_including_installed_sidecar_probe(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'checkout'
            (root / 'tmp').mkdir(parents=True)
            fake = root / 'tmp/dangling-junction'
            original_lstat = Path.lstat
            synthetic_reparse = type('WindowsReparse', (), {
                'st_mode': stat.S_IFDIR, 'st_file_attributes': 0x400,
                'st_nlink': 1,
            })()
            def controlled_lstat(path, *args, **kwargs):
                if path == fake:
                    return synthetic_reparse
                return original_lstat(path, *args, **kwargs)
            with (patch.object(ssh, 'ROOT', root),
                  patch.object(Path, 'lstat', new=controlled_lstat)):
                self.assertFalse(fake.exists())
                self.assertFalse(fake.is_symlink())
                with self.assertRaisesRegex(RuntimeError, 'Reparse/symlink path refused'):
                    ssh.inside(fake / 'payload.whl')
                with self.assertRaisesRegex(RuntimeError, 'Reparse/symlink path refused'):
                    ssh.installed(fake, {})
                self.assertEqual(ssh.inside(root / 'tmp/new-regular-path'),
                                 root / 'tmp/new-regular-path')
                self.assertFalse(ssh.installed(root / 'tmp/absent-sidecar', {}))

    def test_bounded_rejects_dangling_windows_reparse_metadata(self):
        # A target-less junction can evade exists()/is_symlink(). Prove
        # bounded() lstat's the entry itself before approving missing paths.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'checkout'
            (root / 'tmp').mkdir(parents=True)
            fake = root / 'tmp/dangling-junction'
            original_lstat = Path.lstat
            synthetic_reparse = type('WindowsReparse', (), {
                'st_mode': stat.S_IFDIR, 'st_file_attributes': 0x400,
                'st_nlink': 1,
            })()
            def controlled_lstat(path, *args, **kwargs):
                if path == fake:
                    return synthetic_reparse
                return original_lstat(path, *args, **kwargs)
            with patch.object(tools, 'ROOT', root), \
                 patch.object(Path, 'lstat', new=controlled_lstat):
                self.assertFalse(fake.exists())
                self.assertFalse(fake.is_symlink())
                with self.assertRaisesRegex(ValueError, 'Reparse/symlink refused'):
                    tools.bounded(fake / 'payload.zip')
                good = root / 'tmp/legitimate-new/payload.zip'
                self.assertEqual(tools.bounded(good), good)

    def test_update_download_redirects_are_checked_before_any_request(self):
        good = (
            ('https://github.com/owner/repo/releases/download/v1/release.zip',
             'https://release-assets.githubusercontent.com/download?token=opaque'),
            ('https://github.com/owner/repo/releases/download/v1/release.zip',
             'https://objects.githubusercontent.com/download?token=opaque'),
            ('https://nodejs.org/dist/v1/archive.zip',
             'https://nodejs.org/dist/v1/archive-2.zip'),
            ('https://7-zip.org/file.7z', 'https://www.7-zip.org/file.7z'),
        )
        for source, dest in good:
            with self.subTest(source=source, dest=dest):
                tools.validate_download_redirect(source, dest)
                original = tools.urllib.request.Request(source,
                    headers={'Authorization': 'synthetic-secret', 'Cookie': 'session'})
                forwarded = tools._ApprovedToolRedirect().redirect_request(
                    original, None, 302, 'Found', {}, dest)
                self.assertEqual(forwarded.full_url, dest)
                self.assertFalse(forwarded.has_header('Authorization'))
                self.assertFalse(forwarded.has_header('Cookie'))
        start = 'https://github.com/owner/repo/releases/download/v1/file.zip'
        for forbidden in (
            'https://evil.invalid/steal', 'http://github.com/file',
            'https://release-assets.githubusercontent.com.evil.invalid/file',
            'https://user:pass@release-assets.githubusercontent.com/file',
            'https://github.com:9443/other',
            'https://release-assets.githubusercontent.com/file#x',
            'https://127.0.0.1/host-secret',
        ):
            with self.subTest(forbidden=forbidden):
                with self.assertRaisesRegex(ValueError, 'Unapproved official download redirect'):
                    tools._ApprovedToolRedirect().redirect_request(
                        tools.urllib.request.Request(start), None,
                        302, 'Found', {}, forbidden)
        with self.assertRaisesRegex(ValueError, 'Unapproved official download redirect'):
            tools.validate_download_redirect(
                'https://api.github.com/repos/owner/repo/releases/latest',
                'https://release-assets.githubusercontent.com/file')

    def test_updater_download_uses_empty_proxy_and_audited_redirects(self):
        official = 'https://api.github.com/repos/owner/repo/releases/latest'
        payload = b'{"tag_name":"v1.2.3"}'
        calls = []
        def respond(request, timeout):
            calls.append((request.full_url, timeout))
            response = io.BytesIO(payload)
            response.url = official
            return response
        with patch.object(tools.urllib.request, 'build_opener') as factory:
            factory.return_value.open.side_effect = respond
            self.assertEqual(tools.fetch_bytes(official, 64), payload)
            factory.assert_called_once()
            self.assertEqual(factory.call_args.args[0].proxies, {})
            self.assertIsInstance(factory.call_args.args[1], tools._ApprovedToolRedirect)
            with self.assertRaisesRegex(ValueError, 'Only reviewed official download hosts'):
                tools.fetch_bytes('https://evil.invalid/file', 64)
        self.assertEqual(calls, [(official, 25)])

    def test_native_probe_child_environment_is_not_host_configuration(self):
        # The verifier runs a candidate executable, not merely reading it;
        # arbitrary host variables and a poisoned SystemRoot must not survive.
        fake_binary = ROOT / 'tool/node/node.exe'
        with patch.dict(os.environ, {
            'SystemRoot': 'Z:\\HostFake', 'COMSPEC': 'Z:\\HostFake\\cmd.exe',
            'HOME': 'Z:\\Users\\Host', 'APPDATA': 'Z:\\Users\\Host\\AppData',
            'NODE_OPTIONS': '--require=Z:\\host\\preload.js',
            'COREPACK_NPM_TOKEN': 'host-secret', 'GITHUB_TOKEN': 'host-secret',
            'AWS_ACCESS_KEY_ID': 'host-secret', 'HTTP_PROXY': 'http://host.invalid:8080',
            'NPM_CONFIG_REGISTRY': 'https://host.invalid', 'CI': 'true',
        }, clear=False):
            sanitized = tools.probe_child_environment(fake_binary)
        self.assertEqual(sanitized['HOME'], str(ROOT / 'home-runtime'))
        self.assertEqual(sanitized['TEMP'], str(ROOT / 'tmp'))
        self.assertEqual(sanitized['COREPACK_HOME'], str(ROOT / 'cache/corepack'))
        self.assertEqual(sanitized['COREPACK_ENV_FILE'], '0')
        self.assertEqual(sanitized['CI'], 'true')
        self.assertEqual(sanitized['GIT_CONFIG_NOSYSTEM'], '1')
        self.assertIn(str(fake_binary.parent), sanitized['PATH'])
        for forbidden in ('NODE_OPTIONS', 'COREPACK_NPM_TOKEN', 'GITHUB_TOKEN',
                          'AWS_ACCESS_KEY_ID', 'HTTP_PROXY', 'NPM_CONFIG_REGISTRY'):
            self.assertNotIn(forbidden, sanitized)
        if os.name == 'nt':
            self.assertNotEqual(sanitized['SystemRoot'], 'Z:\\HostFake')
            self.assertNotIn('Z:\\HostFake', sanitized['ComSpec'])
        script = (ROOT / 'tool/update-tools.py').read_text(encoding='utf-8')
        self.assertIn('env = probe_child_environment(binary)', script)
        self.assertIn('safe_env = probe_child_environment(node)', script)

    def test_auto_selector_does_not_change_reviewed_legacy_plan_contract(self):
        legacy = [row['tool'] for row in tools.plan()]
        self.assertEqual(legacy, ['ripgrep', 'fd', 'jq'])
        auto_row = dict(
            tool='jq', group='cli', version='1.9.0',
            url='https://github.com/jqlang/jq/releases/download/'
                'jq-1.9.0/jq-windows-amd64.exe',
            sha256='a' * 64, destination='tool/bin/jq.exe',
            kind='executable',
        )
        with patch.dict(os.environ, {'TOOL_AUTO_UPDATE_PLAN': '1'}), \
             patch.object(tools, 'load_json', return_value={
                 'schema': 1, 'platform': 'win32-x64',
                 'candidates': [auto_row],
             }) as load:
            self.assertEqual([r['tool'] for r in tools.selected_rows('tools')],
                             ['jq'])
            load.assert_called_once_with(
                tools.ROOT / 'tmp/auto-tool-update-plan.json')
        self.assertEqual([row['tool'] for row in tools.plan()], legacy)

    def test_separate_ssh_closure_and_pth_path(self):
        self.assertEqual(set(ssh.pins()), {
            'paramiko', 'bcrypt', 'cryptography', 'invoke', 'pynacl', 'cffi', 'pycparser'
        })
        expected_ssh = (ROOT / 'tool/python-ssh-packages.in.txt').read_text(encoding='utf-8')
        for package, version in ssh.pins().items():
            self.assertIn(package + '==' + version, expected_ssh.lower())
        self.assertEqual(ssh.pins()['paramiko'],
                         tools.load_json(tools.LEDGER)['tools']['paramiko']['version'])
        self.assertEqual((ROOT / 'tool/python/Lib/site-packages/codex_portable_ssh.pth')
                         .read_text(encoding='utf-8').strip(), '../../ssh-packages')
        self.assertNotIn('paramiko==', (ROOT / 'tool/python-packages.in.txt').read_text(encoding='utf-8'))

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
        self.assertEqual([item['tool'] for item in tools.plan()], ['ripgrep', 'fd', 'jq'])
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
        workflow = (ROOT / '.github/workflows/03-update-tools.yml').read_text(encoding='utf-8')
        self.assertIn('\non:\n  workflow_dispatch:\n', workflow)
        for forbidden in ('\n  push:', '\n  schedule:', '\n  pull_request:',
                          '\n  workflow_run:'):
            self.assertNotIn(forbidden, workflow)
        self.assertIn('default: check', workflow)
        self.assertIn('options: [diagnose, check, update]', workflow)
        self.assertNotIn('      group:', workflow)
        self.assertNotIn('      create_pr:', workflow)
        self.assertIn('needs: verify', workflow)
        self.assertIn('candidate_digest:', workflow)
        self.assertIn('sha256', (ROOT / 'tool/update-tools.py').read_text(encoding='utf-8'))
        self.assertIn('pull-requests: write', workflow)
        self.assertIn("inputs.operation == 'update' && github.ref == 'refs/heads/main'", workflow)
        self.assertIn('--writer', workflow)
        self.assertIn('release-audit.py --release', workflow)
        self.assertIn('release-audit.py --verify', workflow)
        self.assertNotIn('gh release create', workflow)
        self.assertNotIn('git push origin HEAD:refs/heads/main', workflow)

    def test_all_maintainer_text_io_is_explicit_utf8(self):
        # A Windows PS5.1 runner can use CP1252. Source test files have UTF-8
        # Chinese labels; unspecified Path.read_text/write_text is not portable.
        # Cover all first-party scripts involved in this workflow, not only
        # the test file where Windows CP1252 originally caused a failure.
        checked = ('tests/test_tool_updates.py', 'tool/update-tools.py',
                   'tool/prepare-ssh.py')
        for relative in checked:
            tree = ast.parse((ROOT / relative).read_text(encoding='utf-8'))
            calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Attribute)
                     and node.func.attr in ('read_text', 'write_text')]
            self.assertTrue(calls, relative)
            for node in calls:
                self.assertTrue(explicit_utf8_text_io(node),
                                f'Implicit {node.func.attr} encoding in {relative}:{node.lineno}')

    def test_utf8_encoding_guard_accepts_bom_and_rejects_host_defaults(self):
        # Regression for Actions run 41450908392: UTF-8-SIG is valid UTF-8.
        # Verify the checker itself before it scans this very source file.
        allowed = (
            "p.read_text(encoding='utf-8')",
            "p.read_text(encoding='utf-8-sig')",
            "p.read_text('utf-8')",
            "p.write_text('hello', encoding='utf-8')",
            "p.write_text('hello', 'utf-8-sig')",
        )
        rejected = (
            "p.read_text()",
            "p.read_text(encoding='cp1252')",
            "p.read_text(encoding=None)",
            "p.write_text('hello')",
            "p.write_text('hello', encoding='latin-1')",
        )
        for snippet in allowed:
            with self.subTest(snippet=snippet):
                self.assertTrue(explicit_utf8_text_io(ast.parse(snippet).body[0].value))
        for snippet in rejected:
            with self.subTest(snippet=snippet):
                self.assertFalse(explicit_utf8_text_io(ast.parse(snippet).body[0].value))

    def test_tool_maintenance_regressions_run_before_any_candidate_download(self):
        # Prevent repeat of AC run #41425693314: tests must fail fast before
        # downloading large Windows tool/wheel payloads. Full-suite testing
        # after installation remains mandatory.
        workflow = (ROOT / '.github/workflows/03-update-tools.yml').read_text(
            encoding='utf-8')
        legacy, full = workflow.split('\n  full_verify:', 1)
        full_verify = full.split('\n  full_propose:', 1)[0]
        needle = "-m unittest discover -s tests -p 'test_tool_updates.py' -v"
        # The old prepare path and the new full path each need exactly one
        # fail-fast maintenance pass; counting both Jobs as one is incorrect.
        self.assertEqual(legacy.count(needle), 1)
        self.assertEqual(full_verify.count(needle), 1)
        self.assertIn('Pre-download tool maintenance regression failure.', legacy)
        self.assertLess(legacy.index(needle), legacy.index('Stage checked wheel'))
        self.assertLess(full_verify.index(needle), full_verify.index('Stage full latest-stable'))
        self.assertIn("if: ${{ inputs.operation == 'update' }}", legacy)
        self.assertIn("-m unittest discover -s tests -p 'test_*.py' -v", legacy)
        self.assertIn("-m unittest discover -s tests -p 'test_*.py' -v", full_verify)

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
        # Keep the historical Node LFS fixture compatible with the actual
        # staged-digest contract. Missing destination/kind caused run #41554504292.
        self.assertEqual(set(NODE_LFS_FIXTURE), {'tool', 'version', 'destination', 'kind'})
        self.assertEqual((NODE_LFS_FIXTURE['destination'], NODE_LFS_FIXTURE['kind']),
                         ('tool/node', 'directory'))
        self.assertEqual(tools.selected_rows('ssh'), [])
        self.assertEqual([r['tool'] for r in tools.selected_rows('all')], ['ripgrep', 'fd', 'jq'])
        self.assertEqual([r['tool'] for r in tools.selected_rows('tools')], ['ripgrep', 'fd', 'jq'])
        with self.assertRaises(ValueError):
            tools.selected_rows('bogus')

    def test_node_update_requires_matching_official_shasums(self):
        # Node was delivered in the prior batch; retain its isolated trust
        # regression without making it a new production candidate.
        row = dict(tool='node', group='node', version='26.13.0',
                   url='https://nodejs.org/dist/v26.13.0/node-v26.13.0-win-x64.zip',
                   source_prefix='node-v26.13.0-win-x64/',
                   destination='tool/node', kind='directory',
                   sha256='dcc60d59a0746999f99064a01c020445d54d84228c691cdbf25b49ac3b59150a')
        shas=(row['sha256'] + '  node-v26.13.0-win-x64.zip\n').encode('ascii')
        # The official independent SHASUMS must match the reviewed ZIP pin
        # before downloading the actual release artifact.
        with tempfile.TemporaryDirectory() as d:
            with patch.object(tools,'fetch_bytes', return_value=b'0'*64), \
                    self.assertRaises(ValueError):
                tools.prepare_row(row,Path(d))
        self.assertIn('node-v26.13.0-win-x64.zip',shas.decode())

    def test_reviewed_cli_pins_are_official_x64_and_reject_wrong_arch(self):
        rows = tools.plan()
        self.assertEqual([r['tool'] for r in rows], ['ripgrep', 'fd', 'jq'])
        expected = {
            'ripgrep': ('15.2.0', '71b2fef860abe467217a538ff31de02f5258807c0129f771846f87bd029aafc5'),
            'fd': ('10.5.0', 'a227701b8551c35a9931d9f6da75503cf86d88e182d71fb849a70864c5d57cd7'),
            'jq': ('1.8.2', 'a6fc67fedaf9128a3309a1e2ebb8b986aeccf70122ee46d2cb4849e423f0c627'),
        }
        for row in rows:
            with self.subTest(tool=row['tool']):
                self.assertEqual((row['version'], row['sha256']), expected[row['tool']])
                self.assertEqual(row['group'], 'cli')
                self.assertNotIn('node', row['destination'])
                if row['tool'] != 'jq':
                    self.assertEqual(row['kind'], 'single')
                    self.assertEqual(row['source_prefix'], row['url'].split('/')[-1][:-4] + '/')
                    self.assertEqual(row['source_file'], {'ripgrep': 'rg.exe', 'fd': 'fd.exe'}[row['tool']])
                    bad = dict(row, url=row['url'].replace('x86_64', 'aarch64'))
                    with patch.object(tools, 'load_json', return_value={
                        'schema': 1, 'platform': 'win32-x64', 'candidates': [bad]
                    }), self.assertRaisesRegex(ValueError, 'Windows x64 MSVC'):
                        tools.plan()
                else:
                    self.assertEqual(row['kind'], 'executable')
                    self.assertEqual(row['destination'], 'tool/bin/jq.exe')
                    self.assertNotIn('source_prefix', row)
                    self.assertNotIn('source_file', row)
                    for change in ({'url': row['url'].replace('amd64', 'arm64')},
                                   {'source_prefix': 'unreviewed/'},
                                   {'destination': 'tool/bin/rg.exe'},
                                   {'kind': 'pair'}):
                        with self.subTest(change=change), patch.object(
                            tools, 'load_json', return_value={
                                'schema': 1, 'platform': 'win32-x64',
                                'candidates': [dict(row, **change)]
                        }), self.assertRaises(ValueError):
                            tools.plan()

    def test_direct_jq_official_pe_is_pinned_and_fails_closed(self):
        pe = bytearray(256)
        pe[:2] = b'MZ'
        pe[0x3c:0x40] = (0x80).to_bytes(4, 'little')
        pe[0x80:0x84] = b'PE\0\0'
        pe[0x84:0x86] = (0x8664).to_bytes(2, 'little')
        binary = bytes(pe)
        row = dict(next(r for r in tools.plan() if r['tool'] == 'jq'),
                   sha256=hashlib.sha256(binary).hexdigest())
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dest = root / 'tool/bin/jq.exe'
            dest.parent.mkdir(parents=True)
            dest.write_bytes(b'old-binary')
            for name, payload, pin, passes in (
                ('good', binary, row['sha256'], True),
                ('wrong-digest', binary, 'f' * 64, False),
                ('wrong-architecture', binary, None, False),
            ):
                with self.subTest(name=name):
                    scratch = root / ('tmp-' + name)
                    scratch.mkdir()
                    if name == 'wrong-architecture':
                        # Modify just the COFF machine type while keeping a valid
                        # DOS and PE signature. A matching SHA must still fail.
                        broken = bytearray(binary)
                        broken[0x84:0x86] = (0xaa64).to_bytes(2, 'little')
                        payload = bytes(broken)
                    test_row = dict(row, sha256=(hashlib.sha256(payload).hexdigest()
                                                if pin is None else pin))
                    before = dest.read_bytes()
                    with patch.object(tools, 'ROOT', root), patch.object(
                            tools, 'fetch_bytes', return_value=payload):
                        if passes:
                            tools.prepare_row(test_row, scratch)
                            self.assertEqual(dest.read_bytes(), payload)
                        else:
                            with self.assertRaises(ValueError):
                                tools.prepare_row(test_row, scratch)
                            self.assertEqual(dest.read_bytes(), before)

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
                (node / name).write_text('guarded-' + name, encoding='utf-8')
            corepack = node / 'node_modules/corepack'
            (corepack / 'dist').mkdir(parents=True)
            (corepack / 'dist/corepack.js').write_bytes(b'preserved corepack js')
            (corepack / 'package.json').write_text(
                '{"name":"corepack","version":"0.35.0","engines":{"node":">=26.0.0"}}',
                encoding='utf-8')
            npm = node / 'node_modules/npm'
            (npm / 'bin').mkdir(parents=True)
            (npm / 'package.json').write_text(
                '{"name":"npm","version":"12.2.1"}', encoding='utf-8')
            (npm / 'bin/npm-cli.js').write_text(
                'pinned portable npm', encoding='utf-8')
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
                self.assertEqual((node/name).read_text(encoding='utf-8'), 'guarded-' + name)
            self.assertEqual((node/'node_modules/corepack/dist/corepack.js').read_bytes(),
                             b'preserved corepack js')
            self.assertEqual(json.loads((node/'node_modules/corepack/package.json')
                                        .read_text(encoding='utf-8'))['version'], '0.35.0')
            self.assertFalse((node/'install_tools.bat').exists())
            self.assertTrue((node/'node.exe').is_file())
            self.assertEqual(json.loads((node/'node_modules/npm/package.json').read_text(encoding='utf-8'))['version'], '12.2.1')
            self.assertEqual((node/'node_modules/npm/bin/npm-cli.js').read_text(encoding='utf-8'),
                             'pinned portable npm')

    def test_staged_diff_scope_rejects_unrelated_tool_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            subprocess.run(['git','init','-q',str(root)], check=True)
            (root/'tool').mkdir()
            file=root/'tool/prepare-ssh.py'
            file.write_text('unexpected rewrite\n', encoding='utf-8')
            subprocess.run(['git','-C',str(root),'add','tool/prepare-ssh.py'],check=True)
            with patch.object(tools,'ROOT',root):
                with self.assertRaisesRegex(ValueError,'unrelated'):
                    tools.diff_digest('ssh')
                with self.assertRaisesRegex(ValueError,'unrelated'):
                    tools.diff_digest('tools')
            subprocess.run(['git','-C',str(root),'reset','-q'],check=True)
            (root/'tool/installed-tools.json').write_text('{}\n', encoding='utf-8')
            subprocess.run(['git','-C',str(root),'add','tool/installed-tools.json'],check=True)
            with patch.object(tools,'ROOT',root):
                self.assertRegex(tools.diff_digest('ssh'),r'^[0-9a-f]{64}$')

    def test_node_rejects_symlink_archive_before_replacing_existing_files(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); node=root/'tool/node'; node.mkdir(parents=True)
            (node/'marker.txt').write_text('keep', encoding='utf-8')
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
            self.assertEqual((node/'marker.txt').read_text(encoding='utf-8'),'keep')

    def test_official_node26_corepack_and_converter_regressions_are_preserved(self):
        # Node.js 25+ stops bundling Corepack. A whole-directory replacement
        # must retain the existing local Corepack distribution and CLI shims.
        self.assertIn('corepack', tools.NODE_PORTABLE_FILES)
        self.assertIn('corepack.cmd', tools.NODE_PORTABLE_FILES)
        self.assertIn('node_modules/corepack', tools.NODE_PORTABLE_DIRS)
        self.assertIn('node_modules/npm', tools.NODE_PORTABLE_DIRS)
        self.assertIn('NPM_RETAIN_MAX_BYTES', (ROOT / 'tool/update-tools.py').read_text(encoding='utf-8'))
        source = (ROOT / '.github/workflows/03-update-tools.yml').read_text(encoding='utf-8')
        original = (ROOT / '.github/workflows/02-verify-and-publish-portable.yml').read_text(encoding='utf-8')
        for marker in ('smoke.js', 'static-audit.js'):
            self.assertIn(marker, original)
            self.assertIn(marker, source)
        self.assertIn('COREPACK_PORTABLE=PASS',
                      (ROOT / 'tool/update-tools.py').read_text(encoding='utf-8'))
        self.assertIn('corepack', tools.load_json(tools.LEDGER)['tools'])

    def test_node26_converter_env_rejection_is_prototype_independent_and_early(self):
        # Node 26 util.parseEnv may yield a null-prototype empty mapping.
        # Check all own keys instead of depending on the mapping prototype.
        smoke = (ROOT / 'Version_History/AI account format conversion/test/smoke.js').read_text(
            encoding='utf-8-sig')
        self.assertIn('Reflect.ownKeys(parsed)', smoke)
        self.assertIn('Injected dotenv created environment variables', smoke)
        self.assertNotIn("assert.deepEqual(require('node:util').parseEnv(env),{});", smoke)
        flow = (ROOT / '.github/workflows/03-update-tools.yml').read_text(encoding='utf-8')
        self.assertLess(flow.index('Check converter compatibility on candidate Node'),
                        flow.index('Run complete Python and Node regression suites'))
        self.assertEqual(flow.count("foreach ($script in @('smoke.js', 'static-audit.js'))"), 1)
    def test_ssh_userprofile_matches_launcher_runtime_home(self):
        # On Windows run-codex.ps1 uses home-runtime; storing SSH credentials
        # in home/ would be misleading and break default ~/.ssh resolution.
        source = (ROOT / 'tool/prepare-ssh.py').read_text(encoding='utf-8')
        self.assertIn("'HOME': ROOT / 'home-runtime'", source)
        self.assertIn("'USERPROFILE': ROOT / 'home-runtime'", source)

    def test_node_corepack_retention_rejects_linked_legacy_payload(self):
        def pe():
            b = bytearray(256)
            b[:2] = b'MZ'
            b[0x3c:0x40] = (0x80).to_bytes(4,'little')
            b[0x80:0x84] = b'PE\0\0'
            b[0x84:0x86] = (0x8664).to_bytes(2,'little')
            return bytes(b)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            node=root/'tool/node'; node.mkdir(parents=True)
            for name in tools.NODE_PORTABLE_FILES:
                (node/name).write_text('guarded', encoding='utf-8')
            (node/'node.exe').write_bytes(pe())
            outside=root/'outside'; outside.mkdir()
            (outside/'corepack.js').write_bytes(b'outside')
            (node/'node_modules').mkdir()
            try:
                (node/'node_modules/corepack').symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest('This host cannot create symlinks')
            archive=io.BytesIO()
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('node-v1.2.3-win-x64/node.exe', pe())
            payload=archive.getvalue()
            row=dict(tool='node',version='1.2.3',kind='directory', destination='tool/node',
                     source_prefix='node-v1.2.3-win-x64/',
                     sha256=hashlib.sha256(payload).hexdigest(),url='https://nodejs.org/')
            checksum=(row['sha256']+'  node-v1.2.3-win-x64.zip\n').encode()
            tmp=root/'tmp'; tmp.mkdir()
            with patch.object(tools,'ROOT',root), patch.object(tools,'fetch_bytes',side_effect=[checksum,payload]):
                with self.assertRaisesRegex(ValueError, 'Reparse/symlink'):
                    tools.prepare_row(row,tmp)
            self.assertEqual((node/'node.exe').read_bytes(),pe())
            self.assertEqual((outside/'corepack.js').read_bytes(),b'outside')

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
            (tool/'python-ssh-packages.in.txt').write_text('paramiko==5.1.0\n', encoding='utf-8')
            ledger.write_text(json.dumps({'schema':1,'platform':'win32-x64','tools':{
                'paramiko':{'version':None,'status':'not-installed','path':'tool/python/ssh-packages'}},
                'lastSuccessfulToolUpdate':None}), encoding='utf-8')
            doc.write_text('before\n| Python SSH / Paramiko | 候选未安装 | 原始来源 |\n' + tools.BEGIN + '\nold\n' + tools.END + '\nafter\n', encoding='utf-8')
            with patch.object(tools, 'ROOT', root), patch.object(tools,'TOOL',tool), \
                    patch.object(tools, 'LEDGER', ledger), patch.object(tools,'DOC',doc):
                tools.record_updates([], ssh=True, day='2026-11-02')
                updated=json.loads(ledger.read_text(encoding='utf-8'))
                self.assertEqual(updated['tools']['paramiko']['version'], '5.1.0')
                self.assertEqual(updated['lastSuccessfulToolUpdate'],'2026-11-02')
                self.assertIn('paramiko | 5.1.0 | bundled',doc.read_text(encoding='utf-8'))
                self.assertEqual(doc.read_text(encoding='utf-8').count(tools.BEGIN),1)
                self.assertIn('已安装 Paramiko 5.1.0',doc.read_text(encoding='utf-8'))
                self.assertIn('home-runtime',doc.read_text(encoding='utf-8'))
                before=ledger.read_bytes()
                with self.assertRaises(ValueError):
                    tools.record_updates([], ssh=False, day='2026-11-02')
                self.assertEqual(ledger.read_bytes(),before)


    def test_node_inventory_preserves_pinned_npm_and_corepack(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); tool=root/'tool'
            pkg=tool/'node/node_modules'
            (pkg/'npm').mkdir(parents=True)
            (pkg/'corepack').mkdir(parents=True)
            (pkg/'npm/package.json').write_text('{"name":"npm","version":"11.20.0"}',
                                                encoding='utf-8')
            (pkg/'corepack/package.json').write_text(
                '{"name":"corepack","version":"0.35.0"}',encoding='utf-8')
            inventory={'schema':1,'platform':'win32-x64','lastSuccessfulToolUpdate':None,
                       'tools':{k:{'version':version,'status':'bundled','path':'tool/node'}
                                for k,version in [('node','24.16.0'),('npm','11.20.0'),
                                                  ('corepack','0.35.0')]}}
            ledger=tool/'installed-tools.json'
            ledger.write_text(json.dumps(inventory),encoding='utf-8')
            doc=tool/'工具更新说明.md'
            doc.write_text('before\n'+tools.BEGIN+'\nold\n'+tools.END+'\nafter\n',
                           encoding='utf-8')
            with patch.object(tools,'ROOT',root),patch.object(tools,'TOOL',tool),\
                 patch.object(tools,'LEDGER',ledger),patch.object(tools,'DOC',doc):
                (pkg/'npm/package.json').write_text(
                    '{"name":"npm","version":"11.19.0"}', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'changed the pinned npm'):
                    tools.record_updates([{'tool':'node','version':'26.13.0'}],
                                         ssh=False, day='2026-11-02')
                (pkg/'npm/package.json').write_text(
                    '{"name":"npm","version":"11.20.0"}', encoding='utf-8')
                (pkg/'corepack/package.json').write_text(
                    '{"name":"corepack","version":"0.34.0"}', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'changed the pinned Corepack'):
                    tools.record_updates([{'tool':'node','version':'26.13.0'}],
                                         ssh=False, day='2026-11-02')
                (pkg/'corepack/package.json').write_text(
                    '{"name":"corepack","version":"0.35.0"}', encoding='utf-8')
                tools.record_updates([{'tool':'node','version':'26.13.0'}],ssh=False,
                                     day='2026-11-02')
            result=json.loads(ledger.read_text(encoding='utf-8'))
            self.assertEqual(result['tools']['node']['version'],'26.13.0')
            self.assertEqual(result['tools']['npm']['version'],'11.20.0')
            self.assertEqual(result['tools']['corepack']['version'],'0.35.0')
            self.assertIn('corepack | 0.35.0 | bundled',doc.read_text(encoding='utf-8'))
            self.assertEqual(result['lastSuccessfulToolUpdate'],'2026-11-02')

    def test_native_corepack_probe_rejects_mismatched_runtime(self):
        # The verification Job must actually invoke retained Corepack under
        # the reviewed upgraded Node, not just trust package.json metadata.
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); node=root/'tool/node'
            dest=node/'node_modules/corepack/dist'; dest.mkdir(parents=True)
            (node/'node.exe').write_bytes(b'MZ'+b'0'*256)
            (node/'corepack').write_text('reviewed',encoding='utf-8')
            (node/'corepack.cmd').write_text('reviewed',encoding='utf-8')
            (node/'node_modules/corepack/package.json').write_text(
                '{"name":"corepack","version":"0.35.0"}',encoding='utf-8')
            (dest/'corepack.js').write_text('reviewed',encoding='utf-8')
            observed={'node':'26.13.0'}
            with patch.object(tools,'ROOT',root),\
                 patch.object(tools,'selected_rows',return_value=[NODE_LFS_FIXTURE]),\
                 patch.object(tools,'probe_versions',return_value=observed),\
                 patch.object(tools.subprocess,'run',return_value=subprocess.CompletedProcess(
                     args=[],returncode=0,stdout=b'0.35.0\n',stderr=b'')) as runner:
                tools.verify_candidates('all')
                self.assertEqual(runner.call_count,1)
                self.assertEqual(runner.call_args.args[0][0],str(node/'node.exe'))
            with patch.object(tools,'ROOT',root),\
                 patch.object(tools,'selected_rows',return_value=[NODE_LFS_FIXTURE]),\
                 patch.object(tools,'probe_versions',return_value=observed),\
                 patch.object(tools.subprocess,'run',return_value=subprocess.CompletedProcess(
                     args=[],returncode=0,stdout=b'0.34.0\n',stderr=b'')):
                with self.assertRaisesRegex(ValueError,'functional package-local Corepack'):
                    tools.verify_candidates('all')

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
            # Simulate Git-for-Windows with Git LFS clean already registered.
            # A path-based hash is then *not* guaranteed to give raw content;
            # the negative test below must bypass the filter explicitly.
            filter_script = root / 'mock-lfs-clean.py'
            filter_script.write_text(
                'import sys,hashlib\n'
                'data=sys.stdin.buffer.read()\n'
                'sys.stdout.buffer.write(("version https://git-lfs.github.com/spec/v1\\n"'
                '+"oid sha256:"+hashlib.sha256(data).hexdigest()'
                '+"\\nsize "+str(len(data))+"\\n").encode("ascii"))\n',
                encoding='utf-8')
            subprocess.run(['git', '-C', str(root), 'config', 'filter.lfs.clean',
                            f'"{sys.executable}" "{filter_script}"'], check=True)
            subprocess.run(['git', '-C', str(root), 'config', 'filter.lfs.required', 'true'],
                           check=True)
            with patch.object(tools, 'ROOT', root), patch.object(
                    tools, 'selected_rows', side_effect=lambda group: (
                        [] if group == 'ssh' else [NODE_LFS_FIXTURE])):
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
                # Prove the fixture filter would otherwise turn the path
                # into a canonical pointer, masking the negative test.
                filter_oid = subprocess.check_output(
                    ['git', '-C', str(root), 'hash-object', '-w',
                     '--path=tool/node/node.exe', 'tool/node/node.exe']).strip().decode('ascii')
                filtered = subprocess.check_output(['git', '-C', str(root),
                                                    'cat-file', 'blob', filter_oid])
                self.assertTrue(filtered.startswith(
                    b'version https://git-lfs.github.com/spec/v1\n'))
                # Supply raw bytes on stdin, bypassing ALL worktree filters.
                # Windows has Git LFS clean installed, so using hash-object's
                # worktree path can unexpectedly create another *valid pointer*
                # rather than the corrupt raw blob this negative test needs.
                raw_blob = node.read_bytes()
                raw_oid = subprocess.check_output(
                    ['git', '-C', str(root), 'hash-object', '-w', '--stdin'],
                    input=raw_blob).strip().decode('ascii')
                self.assertEqual(subprocess.check_output(
                    ['git', '-C', str(root), 'cat-file', 'blob', raw_oid]), raw_blob)
                subprocess.run(['git', '-C', str(root), 'update-index', '--add', '--cacheinfo',
                                f'100644,{raw_oid},tool/node/node.exe'], check=True)
                self.assertEqual(subprocess.check_output(
                    ['git', '-C', str(root), 'show', ':tool/node/node.exe'])[:2], b'MZ')
                with self.assertRaisesRegex(ValueError, 'canonical staged Git LFS pointer'):
                    tools.verify_node_lfs_index('all')

    def test_repeated_node_upgrade_reuses_existing_canonical_lfs_rule(self):
        # Main has already committed this rule after the first Node 26 upgrade.
        # A later official Node update must retain it and verify the new pointer.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            for key, value in (('user.name', 'fixture'),
                               ('user.email', 'fixture@example.invalid')):
                subprocess.run(['git', '-C', str(root), 'config', key, value],
                               check=True)
            attrs = root / '.gitattributes'
            original = b'other.exe -text\n' + tools.NODE_LFS_ATTRIBUTE
            attrs.write_bytes(original)
            subprocess.run(['git', '-C', str(root), 'add', '.gitattributes'],
                           check=True)
            subprocess.run(['git', '-C', str(root), 'commit', '-qm', 'pinned-lfs'],
                           check=True)
            node = root / tools.NODE_LFS_PATH
            node.parent.mkdir(parents=True)
            node.write_bytes(b'MZ' + b'\x19' * (2 * 1024 * 1024))
            digest = hashlib.sha256(node.read_bytes()).hexdigest()
            pointer = (
                b'version https://git-lfs.github.com/spec/v1\n' +
                b'oid sha256:' + digest.encode('ascii') + b'\nsize ' +
                str(node.stat().st_size).encode('ascii') + b'\n')
            oid = subprocess.check_output(
                ['git', '-C', str(root), 'hash-object', '-w', '--stdin'],
                input=pointer).strip().decode('ascii')
            subprocess.run(
                ['git', '-C', str(root), 'update-index', '--add', '--cacheinfo',
                 f'100644,{oid},{tools.NODE_LFS_PATH}'], check=True)
            with patch.object(tools, 'ROOT', root), patch.object(
                    tools, 'selected_rows', return_value=[NODE_LFS_FIXTURE]):
                tools.enable_node_lfs()
                self.assertEqual(attrs.read_bytes(), original)
                self.assertEqual(tools.verify_node_lfs_index('all'), digest)
                self.assertRegex(tools.diff_digest('all'), r'^[0-9a-f]{64}$')
                attrs.write_bytes(original + tools.NODE_LFS_ATTRIBUTE)
                with self.assertRaisesRegex(ValueError, 'Unexpected attributes'):
                    tools.enable_node_lfs()
                subprocess.run(['git', '-C', str(root), 'add', '.gitattributes'],
                               check=True)
                with self.assertRaisesRegex(ValueError, 'reviewed baseline'):
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
            encoding='utf-8').split('\n  full_verify:', 1)[0]
        verify, writer = workflow.split('\n  propose:', 1)
        self.assertEqual(verify.count('git lfs install --local'), 1)
        self.assertEqual(writer.count('git lfs install --local'), 1)
        self.assertEqual(workflow.count('git add -A -- tool .gitattributes'), 2)
        self.assertEqual(workflow.count("if ($env:TOOL_GROUP -ne 'ssh' -and $hasNodeCandidate)"), 3)
        self.assertEqual(workflow.count("Where-Object { $_.tool -ceq 'node' }"), 3)
        self.assertNotIn("if ($env:TOOL_GROUP -ne 'ssh') {", workflow)
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
            with patch.object(tools, 'ROOT', tmp), patch.object(
                    tools, 'selected_rows', return_value=[NODE_LFS_FIXTURE]):
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
        source = (ROOT / '.github/workflows/03-update-tools.yml').read_text(
            encoding='utf-8').split('\n  full_verify:', 1)[0]
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
        # Catch expensive Windows-only issues before Node and SSH downloads.
        # Retain the post-update run for full candidate coverage.
        preflight = source.index('Preflight real launcher and relocation before downloading large candidates')
        download = source.index('Stage checked wheel or SHA256-pinned archive candidates')
        self.assertLess(source.index('Run tool-maintenance tests before downloading any candidate'),
                        preflight)
        package_regression = source.index("-p 'test_release_package.py' -v")
        self.assertLess(package_regression, preflight)
        self.assertLess(preflight, download)
        self.assertEqual(tool_names[0], 'test_launcher_smoke')
        self.assertEqual(source.count('test_launcher_smoke.ps1'), 2)
        # Run #41555463345 timed out a still-progressing Windows PS 5.1 suite
        # at 25 minutes. The old success took about 22 minutes on a faster VM.
        # Keep margin for runner variance, with each test individually timed.
        ps_gate = source.split('      - name: Check Windows PowerShell 5.1 regressions', 1)[1].split(
            '\n      - name:', 1)[0]
        cap = re.search(r'(?m)^        timeout-minutes: (\d+)$', ps_gate)
        self.assertIsNotNone(cap)
        self.assertGreaterEqual(int(cap.group(1)), 45)
        self.assertLessEqual(int(cap.group(1)), 60)
        self.assertIn('WINDOWS_PS_TEST_BEGIN=', ps_gate)
        self.assertIn('WINDOWS_PS_TEST_END=', ps_gate)
        self.assertIn('$elapsed = [Diagnostics.Stopwatch]::StartNew()', ps_gate)
        self.assertIn('$exitCode = $LASTEXITCODE', ps_gate)
        self.assertIn('if ($exitCode -ne 0) { throw "Windows native regression failed: $entry" }',
                      ps_gate)
        launcher = (ROOT / 'tests/test_launcher_smoke.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('Move-OwnedFixtureAfterChildExit -Source $fixture -Destination $newRoot',
                      launcher)
        self.assertIn('ElapsedMilliseconds -ge 20000', launcher)
        self.assertIn('no relocation pass granted.', launcher)
        # Candidate ZIP manifest, hydrated LFS, native runtime and browser
        # files must be verified before the expensive ten Windows audit rounds.
        trial = source.index("Local trial commit failed.")
        package_check = source.index('package-release.py --check')
        audit = source.index('release-audit.py --release')
        full_zip = source.index('package-release.py --version')
        self.assertLess(trial, package_check)
        self.assertLess(package_check, audit)
        self.assertLess(audit, full_zip)
        self.assertEqual(source.count('package-release.py --check'), 1)
        self.assertIn('package-release.py --version', source)
        self.assertIn('git lfs push --object-id origin $newNodeOid', source)
        self.assertIn('release-audit.py --verify', source)



if __name__ == '__main__':
    unittest.main()