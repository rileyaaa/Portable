"""Read-only release identity checks; works with standard Python on Windows/Linux."""
import hashlib
import json
from pathlib import Path
import re
import struct
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RuntimePackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / "tool/runtime-manifest.json").read_text())

    def test_installed_files_match_verified_release(self):
        for name, record in self.manifest["files"].items():
            with self.subTest(file=name):
                target = ROOT / name
                self.assertFalse(target.is_symlink())
                self.assertTrue(target.resolve().is_relative_to(ROOT.resolve()))
                with target.open("rb") as stream:
                    actual = hashlib.file_digest(stream, "sha256").hexdigest()
                self.assertEqual(actual, record["sha256"])

    def test_pinned_pair_and_login_version_agree(self):
        launcher = (ROOT / "run-codex.ps1").read_text(encoding="utf-8-sig")
        login = (ROOT / "login-json.ps1").read_text(encoding="utf-8-sig")
        version = self.manifest["version"]
        self.assertEqual(
            re.search(r'\$ExpectedCodexVersion = "([^"]+)"', launcher)[1], version
        )
        for name, variable in (
            ("codex.exe", "ExpectedCodexSha256"),
            ("codex-code-mode-host.exe", "ExpectedCodeModeHostSha256"),
        ):
            digest = self.manifest["files"][name]["sha256"]
            pinned = re.search(rf'\${variable} = "([A-Fa-f0-9]+)"', launcher)[1]
            self.assertEqual(pinned.lower(), digest)
            if name == "codex.exe":
                self.assertRegex(login, rf"'{digest}'\s*=\s*'{re.escape(version)}'")
            with (ROOT / name).open("rb") as stream:
                self.assertEqual(stream.read(2), b"MZ")
                stream.seek(0x3C)
                pe_offset = struct.unpack("<I", stream.read(4))[0]
                stream.seek(pe_offset)
                self.assertEqual(stream.read(4), b"PE\0\0")
                self.assertEqual(struct.unpack("<H", stream.read(2))[0], 0x8664)

    def test_portable_package_layout(self):
        metadata = json.loads((ROOT / "codex-package.json").read_text())
        self.assertEqual(metadata["version"], self.manifest["version"])
        self.assertEqual(metadata["target"], "x86_64-pc-windows-msvc")
        self.assertEqual(metadata["entrypoint"], "codex.exe")
        self.assertEqual(metadata["resourcesDir"], "codex-resources")
        self.assertEqual(metadata["pathDir"], "codex-path")
        # An unrecorded resources host would shadow the pinned sibling host.
        shadow = "codex-resources/codex-code-mode-host.exe"
        if (ROOT / shadow).exists():
            self.assertIn(shadow, self.manifest["files"])
            self.assertEqual(
                self.manifest["files"][shadow]["sha256"],
                self.manifest["files"]["codex-code-mode-host.exe"]["sha256"],
            )


if __name__ == "__main__":
    unittest.main()
