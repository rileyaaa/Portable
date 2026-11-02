"""Regression guards for two manually invoked portable maintenance Actions."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = {
    "01": ROOT / ".github/workflows/01-update-codex.yml",
    "release": ROOT / ".github/workflows/release.yml",
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

    def test_both_actions_are_strictly_manual(self):
        for name, content in self.files.items():
            with self.subTest(step=name):
                self.assertIn("\non:\n  workflow_dispatch:", content)
                self.assertNotIn("\n  push:", content)
                self.assertNotIn("\n  schedule:", content)
                self.assertNotIn("\n  pull_request:", content)
                self.assertNotIn("\n  workflow_run:", content)

    def test_existing_publisher_remains_three_asset_full_windows_gate(self):
        publisher = self.files["release"]
        for marker in (
            "release-audit.py --release",
            "release-audit.py --verify",
            "02-compatibility.py --repo . --native",
            "Assert-PublishedSourceIsLatestMain",
            "Publishing is allowed only from main.",
            "needs: verify", "source_sha:",
            "gh release create", "gh release download", "gh release edit",
            "release-manifest.json", "SHA256SUMS",
        ):
            self.assertIn(marker, publisher)
        self.assertIn("publish_release:", publisher)
        self.assertIn("default: false", publisher)
        self.assertNotIn("check_set:", publisher)
        self.assertNotIn("package_hotfix", publisher)
        self.assertNotIn("02-check-compatibility.yml/runs", publisher)
        self.assertNotIn("!cancelled()", publisher)
        self.assertIn("if: ${{ success() }}", publisher)
        self.assertIn("if: ${{ needs.verify.result == 'success' && inputs.publish_release && github.ref == 'refs/heads/main' }}", publisher)
        self.assertEqual(publisher.count("persist-credentials: false"), 2)
        self.assertEqual(publisher.count("    permissions:\n      contents: write"), 1)
        self.assertEqual(publisher.count("    permissions:\n      contents: read"), 1)
        self.assertGreaterEqual(publisher.count("Assert-PublishedSourceIsLatestMain"), 3)

    def test_upgrade_pushes_only_approved_lfs_no_release(self):
        source = self.files["01"]
        for marker in (
            "gh release download",
            "01-upgrade-runtime.py --apply",
            "02-compatibility.py --repo . --native",
            "01-upgrade-runtime.py --check-index",
            "test_upgrade_roundtrip.py",
            "git lfs push origin HEAD", "git push origin HEAD:refs/heads/main",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("gh release create", source)
        self.assertNotIn("gh workflow run", source)
        self.assertIn("release_url:", source)
        self.assertIn("default: false", source)
        self.assertIn("if ($approved.prerelease -and $env:COMMIT_CHANGES -eq 'true')", source)
        self.assertIn("UPGRADE_TAG=$($approved.tag)", source)
        self.assertIn("candidate_sha256:", source)
        self.assertIn("UPGRADE_CHANGELOG_DATE", source)
        self.assertIn("EXPECTED_CANDIDATE_SHA256", source)
        self.assertIn("gh auth setup-git", source)
        self.assertEqual(source.count("persist-credentials: false"), 2)
        self.assertEqual(source.count("    permissions:\n      contents: write"), 1)
        self.assertEqual(source.count("    permissions:\n      contents: read"), 1)

    def test_windows_powershell_does_not_strip_native_python_hash_quotes(self):
        source = self.files["01"]
        # Windows PowerShell 5.1 strips nested double quotes in single-quoted
        # Python -c arguments, corrupting the Git binary-diff hash command.
        self.assertEqual(source.count('-B -c "import hashlib,subprocess;'), 2)
        self.assertEqual(source.count("subprocess.check_output(['git','-c'"), 2)
        self.assertNotIn("-B -c 'import hashlib,subprocess", source)

    def test_inline_compatibility_is_in_both_read_only_validation_jobs(self):
        upgrade = self.files["01"]
        publisher = self.files["release"]
        self.assertIn("permissions:\n  contents: read", upgrade)
        self.assertIn("permissions:\n  contents: read", publisher)
        self.assertIn("02-compatibility.py --repo . --native", upgrade)
        self.assertIn("02-compatibility.py --repo . --native", publisher)
        self.assertIn("test_upgrade_roundtrip.py", upgrade)
        self.assertIn("-p 'test_*.py'", publisher)
        self.assertNotIn("gh release create", upgrade)
        self.assertNotIn("git push origin", publisher)

    def test_removed_workflow_entries_cannot_reappear(self):
        self.assertEqual(
            sorted(path.name for path in (ROOT / ".github/workflows").glob("*.yml")),
            ["01-update-codex.yml", "release.yml"])
        for retired in ("request-release-r2.yml", "02-check-compatibility.yml",
                        "download-browser.yml"):
            self.assertFalse((ROOT / ".github/workflows" / retired).exists())
        self.assertFalse((ROOT / ".github/scripts/prepare-release-r2.py").exists())

    def test_upgrade_script_guards_official_versions_and_archive_paths(self):
        script = import_script(
            ROOT / ".github/maintenance/01-upgrade-runtime.py",
            "portable_maintenance_upgrader")
        self.assertGreater(script.version_tuple("0.167.0"),
                           script.version_tuple("0.166.0"))
        self.assertGreater(script.version_tuple("0.167.0"),
                           script.version_tuple("0.167.0-rc.3"))
        self.assertGreater(script.version_tuple("0.167.0-rc.3"),
                           script.version_tuple("0.167.0-beta.2"))
        self.assertGreater(script.version_tuple("0.167.0-alpha.3"),
                           script.version_tuple("0.167.0-alpha.2"))
        for bad in ("0.167.0-rc", "0.167.0-foo.1", "../0.167.0", "latest", "0.167", "1.2.3/"):
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
        self.assertEqual(script.ROOT_RELOCATIONS["codex-resources/codex-command-runner.exe"],
                         "codex-command-runner.exe")
        self.assertNotIn("codex-exec-server.exe", script.ROOT_RELOCATIONS.values())

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
        self.assertEqual(len(script.NORMAL), 14)
        self.assertIn("CODEX_INSTALL_DIR", read(ROOT / "env.ps1"))
        self.assertIn("CODEX_PYTHON", read(ROOT / "env.ps1"))

    def test_release_audit_seeds_follow_pinned_version(self):
        script = import_script(
            ROOT / ".github/scripts/release-audit.py",
            "portable_release_audit")
        version = json.loads(read(ROOT / "tool/runtime-manifest.json"))["version"]
        if "-" in version:
            # 03 release seeds deliberately reject a prerelease runtime.
            with self.assertRaisesRegex(RuntimeError, "Invalid pinned release version"):
                script.version_seed_base()
        else:
            major, minor, patch = (int(part) for part in version.split("."))
            self.assertEqual(script.version_seed_base(),
                             major * 1_000_000 + minor * 1_000 + patch * 10 + 200)


if __name__ == "__main__":
    unittest.main()
