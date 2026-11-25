"""Offline regression tests for deterministic CLI archive/exe identity checks."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest import mock

SRC = Path(__file__).absolute().parents[1] / '.github/maintenance/03-verify-cli-versions.py'
spec = importlib.util.spec_from_file_location('cli_version_verifier', SRC)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class CliVersionTests(unittest.TestCase):
    def test_official_zip_members_and_identical_repo_exes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bin_dir = root / 'tool/bin'
            bin_dir.mkdir(parents=True)
            candidates = {}
            expected = {}
            for name, filename in [('fd', 'fd.exe'), ('rg', 'rg.exe'), ('jq', 'jq.exe')]:
                binary = b'MZ' + name.encode() + b'synthetic exe'
                (bin_dir / filename).write_bytes(binary)
                if name == 'jq':
                    asset = root / 'jq-windows-amd64.exe'
                    asset.write_bytes(binary)
                else:
                    asset = root / (f'{name}-pinned.zip')
                    with zipfile.ZipFile(asset, 'w') as z:
                        z.writestr(f'tool-v1/{filename}', binary)
                candidates[name] = asset
                expected[name] = {'version': '1.0.0', 'tag': 'v1.0.0',
                                  'asset': asset.name, 'size': asset.stat().st_size,
                                  'sha256': hashlib.sha256(asset.read_bytes()).hexdigest(),
                                  'binary': filename}
            with mock.patch.dict(verifier.OFFICIAL, expected, clear=True):
                result = verifier.match(root, candidates)
                self.assertTrue(all(x['status'] == 'VERIFIED' for x in result))
                (bin_dir / 'fd.exe').write_bytes(b'MZmodified')
                result = verifier.match(root, candidates)
                self.assertEqual(result[0]['status'], 'MISMATCH')
                (candidates['rg']).write_bytes(b'broken archive')
                with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                    verifier.match(root, candidates)


    def test_bundled_cli_manifest_digests(self):
        import json
        root = SRC.parents[2]
        manifest = json.loads((root / 'tool/cli-versions.json').read_bytes())
        for item in manifest['tools']:
            with self.subTest(name=item['name']):
                self.assertEqual(verifier.sha256(root / item['windows_path']), item['windows_sha256'])


if __name__ == '__main__':
    unittest.main()
