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
        pinned_manifest = re.search(
            r'\$ExpectedRuntimeManifestSha256 = "([A-Fa-f0-9]+)"', launcher
        )[1].lower()
        self.assertEqual(
            pinned_manifest,
            hashlib.sha256((ROOT / "tool/runtime-manifest.json").read_bytes()).hexdigest(),
        )
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

    def test_text_agent_package_retains_active_runtime_dependencies(self):
        self.assertIn("voice", self.manifest["excluded_components"])
        self.assertIn("duplicate_sandbox_resources", self.manifest["excluded_components"])
        self.assertFalse((ROOT / "codex-resources/voice").exists())
        # Keep one complete root-level helper set. Upstream resolves these before
        # the duplicate resources copies; a missing helper may search host PATH.
        self.assertEqual(set(self.manifest["files"]), {
            "codex.exe", "codex-code-mode-host.exe", "codex-package.json",
            "codex-path/rg.exe", "codex-command-runner.exe",
            "codex-windows-sandbox-setup.exe",
        })
        self.assertTrue((ROOT / "codex-resources").is_dir())
        for name in ("codex-command-runner.exe", "codex-windows-sandbox-setup.exe"):
            self.assertFalse((ROOT / "codex-resources" / name).exists())

    def test_all_native_helpers_are_windows_x64(self):
        # Search and sandbox helpers must match the main client's platform.
        for name in self.manifest["files"]:
            if not name.endswith((".exe", ".dll")):
                continue
            with self.subTest(file=name), (ROOT / name).open("rb") as stream:
                self.assertEqual(stream.read(2), b"MZ")
                stream.seek(0x3C)
                pe_offset = struct.unpack("<I", stream.read(4))[0]
                stream.seek(pe_offset)
                self.assertEqual(stream.read(4), b"PE\0\0")
                self.assertEqual(struct.unpack("<H", stream.read(2))[0], 0x8664)


if __name__ == "__main__":
    unittest.main()
