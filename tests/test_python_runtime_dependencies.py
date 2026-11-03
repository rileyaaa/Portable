"""Check the Windows runtime dependency closure without loading native modules."""
import email
import json
import os
import subprocess
import sys
from pathlib import Path
import unittest

from pip._vendor.packaging.markers import default_environment
from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.utils import canonicalize_name


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "tool/python/Lib/site-packages"


class PythonRuntimeDependencyTests(unittest.TestCase):
    def test_vendor_launchers_are_not_exposed_by_default_path(self):
        launcher = (ROOT/'run-codex.ps1').read_text(encoding='utf-8-sig')
        self.assertNotIn('(Join-Path $PortableTool "python\\Lib\\site-packages\\bin")', launcher)
        for script in (ROOT/'home/plugins/android-apk-lab').rglob('*.ps1'):
            self.assertNotIn('site-packages\\bin', script.read_text(encoding='utf-8-sig'))
        for bat in ROOT.glob('*.bat'):
            self.assertNotIn('%~dp0tool\\python\\Lib\\site-packages\\bin', bat.read_text(encoding='ascii'))

    def test_default_windows_dependencies_and_restored_packager(self):
        packages = {}
        for path in SITE.glob("*.dist-info/METADATA"):
            metadata = email.message_from_string(path.read_text(encoding="utf-8"))
            packages[canonicalize_name(metadata["Name"])] = metadata
        for name in (
            "pip", "requests", "httpx", "beautifulsoup4", "lxml", "pandas",
            "numpy", "python-docx", "python-pptx", "openpyxl", "pymupdf",
            "pymupdf4llm", "pyinstaller", "pyinstaller-hooks-contrib",
            "altgraph", "pefile", "pywin32-ctypes", "setuptools",
        ):
            self.assertIn(name, packages)
        environment = default_environment()
        active = json.loads((ROOT / 'tool/installed-tools.json').read_text(encoding='utf-8'))['tools']['python']['version']
        parts = active.split('.')
        python_minor = '.'.join(parts[:2])
        environment.update(
            python_version=python_minor, python_full_version=(active if len(parts) == 3 else active + '.0'),
            os_name="nt", sys_platform="win32", platform_system="Windows",
            platform_machine="AMD64", extra="",
        )
        for name, metadata in packages.items():
            for text in metadata.get_all("Requires-Dist", []):
                dependency = Requirement(text)
                if dependency.marker and not dependency.marker.evaluate(environment):
                    continue
                with self.subTest(package=name, dependency=text):
                    key = canonicalize_name(dependency.name)
                    self.assertIn(key, packages)
                    self.assertTrue(dependency.specifier.contains(
                        packages[key]["Version"], prereleases=True
                    ))


    def test_restored_build_payload_matches_recorded_git_objects(self):
        manifest = json.loads((ROOT / 'tool/python-build-manifest.json').read_text())
        for entry in manifest['objects']:
            with self.subTest(path=entry['path']):
                actual = subprocess.check_output(
                    ['git', 'rev-parse', 'HEAD:' + entry['path']], cwd=ROOT,
                    text=True, timeout=15).strip()
                self.assertEqual(actual, entry['sha'])

    @unittest.skipUnless(os.name == 'nt', 'The restored CLI targets bundled Windows Python.')
    def test_bundled_pyinstaller_version_without_compilation(self):
        result = subprocess.run(
            [str(ROOT / 'tool/python/python.exe'), '-E', '-s', '-B',
             '-m', 'PyInstaller', '--version'],
            cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((ROOT / 'tool/python-build-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(result.stdout.strip(), manifest['packages']['pyinstaller'])


if __name__ == "__main__":
    unittest.main()
