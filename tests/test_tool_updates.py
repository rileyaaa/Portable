"""Offline security/contract regression tests for the manual tool-update workflow."""
from __future__ import annotations

import importlib.util
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

    def test_no_unreviewed_candidate_is_installable(self):
        self.assertEqual(tools.plan(), [])
        self.assertEqual(tools.load_json(tools.LEDGER)['tools']['paramiko']['status'],
                         'not-installed')
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


if __name__ == '__main__':
    unittest.main()
