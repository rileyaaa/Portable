"""Regression guards for the three manually invoked portable maintenance Actions."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = {
    "01": ROOT / ".github/workflows/01-update-codex.yml",
    "02": ROOT / ".github/workflows/02-check-compatibility.yml",
    "03": ROOT / ".github/workflows/release.yml",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def import_script(file: Path, module: str):
    spec = importlib.util.spec_from_file_location(module, file)
    if spec is None or spec.loader is None:
        raise AssertionError("Cannot import the maintenance script")
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


class ManualMaintenanceWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = {key: read(path) for key, path in WORKFLOWS.items()}

    def test_all_three_actions_are_strictly_manual(self):
        for name, content in self.files.items():
            with self.subTest(step=name):
                self.assertIn("\non:\n  workflow_dispatch:", content)
                self.assertNotIn("\n  push:", content)
                self.assertNotIn("\n  schedule:", content)
                self.assertNotIn("\n  pull_request:", content)
                self.assertNotIn("\n  workflow_run:", content)

    def test_existing_publisher_remains_three_asset_full_windows_gate(self):
        publisher = self.files["03"]
        for marker in (
            "release-audit.py --release",
            "release-audit.py --verify",
            "02-compatibility.py --repo . --native",
            "02-check-compatibility.yml/runs?event=workflow_dispatch",
            "gh release create", "gh release download", "gh release edit",
            "release-manifest.json", "SHA256SUMS",
        ):
            self.assertIn(marker, publisher)
        self.assertIn("check_set:", publisher)
        self.assertIn("actions: read", publisher)
        self.assertIn("publish_release:", publisher)

    def test_upgrade_pushes_only_approved_lfs_no_release(self):
        source = self.files["01"]
        for marker in (
            "gh release download",
            "01-upgrade-runtime.py --apply",
            "02-compatibility.py --repo . --native",
            "01-upgrade-runtime.py --check-index",
            "git lfs push origin HEAD", "git push origin HEAD:refs/heads/main",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("gh release create", source)
        self.assertNotIn("gh workflow run", source)

    def test_compatibility_action_has_no_write_permissions(self):
        source = self.files["02"]
        self.assertIn("permissions:\n  contents: read", source)
        self.assertIn("02-compatibility.py --repo . --native", source)
        self.assertNotIn("git push ", source)

    def test_obsolete_push_dispatcher_is_absent(self):
        self.assertFalse((ROOT / ".github/workflows/request-release-r2.yml").exists())
        self.assertFalse((ROOT / ".github/scripts/prepare-release-r2.py").exists())

    def test_upgrade_script_guards_stable_semver_and_archive_paths(self):
        script = import_script(
            ROOT / ".github/maintenance/01-upgrade-runtime.py",
            "portable_maintenance_upgrader")
        self.assertGreater(script.version_tuple("0.167.0"),
                           script.version_tuple("0.166.0"))
        for bad in ("0.167.0-rc.1", "../0.167.0", "latest", "0.167", "1.2.3/"):
            with self.subTest(input=bad), self.assertRaises(RuntimeError):
                script.version_tuple(bad)
        for bad in ("../secret", "/abs/file", "dir/../evil", "dir\\evil", "a//b"):
            with self.subTest(path=bad), self.assertRaises(RuntimeError):
                script.archive_member(bad)
        self.assertEqual(
            script.replace_once(b"a--b", b"--", b"-", "sample"), b"a-b")
        with self.assertRaises(RuntimeError):
            script.replace_once(b"a--b--c", b"--", b"-", "duplicate")
        self.assertNotIn("codex-exec-server.exe", script.UPSTREAM)
        self.assertNotIn("codex-resources/voice", script.ALLOWED)

    def test_compatibility_audit_has_fixed_local_policy(self):
        script = import_script(
            ROOT / ".github/maintenance/02-compatibility.py",
            "portable_maintenance_audit")
        current = json.loads(read(ROOT / "tool/runtime-manifest.json"))
        self.assertEqual(set(current["files"]), script.REQUIRED)
        self.assertEqual(script.NORMAL["CODEX_TUI_FULLSCREEN_TRANSCRIPT"], "false")
        self.assertEqual(script.NORMAL["CODEX_FAST_MODE"], "false")
        self.assertEqual(script.NORMAL["CODEX_PORTABLE_ALLOW_USER_MCP"], "false")
        self.assertEqual(script.YOLO["CODEX_SANDBOX_MODE"][1],
                         "danger-full-access")

    def test_release_audit_seeds_follow_pinned_version(self):
        script = import_script(
            ROOT / ".github/scripts/release-audit.py",
            "portable_release_audit")
        version = json.loads(read(ROOT / "tool/runtime-manifest.json"))["version"]
        major, minor, patch = (int(part) for part in version.split("."))
        self.assertEqual(script.version_seed_base(),
                         major * 1_000_000 + minor * 1_000 + patch * 10 + 200)


if __name__ == "__main__":
    unittest.main()
