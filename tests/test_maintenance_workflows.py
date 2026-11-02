"""Regression guards for two manually invoked portable maintenance Actions."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = {
    "01": ROOT / ".github/workflows/01-upgrade-codex-runtime.yml",
    "release": ROOT / ".github/workflows/02-verify-and-publish-portable.yml",
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

    def test_pinned_actionlint_is_a_required_read_only_gate(self):
        verifier = read(ROOT / ".github/maintenance/check-actionlint.ps1")
        self.assertIn("rhysd/actionlint", verifier)
        self.assertIn("actionlint_", verifier)
        self.assertIn("_windows_amd64.zip", verifier)
        self.assertIn(
            "6e7241b51e6817ea6a047693d8e6fed13b31819c9a0dd6c5a726e1592d22f6e9",
            verifier)
        self.assertIn("Get-FileHash -LiteralPath $archive -Algorithm SHA256", verifier)
        for workflow_path in WORKFLOWS.values():
            self.assertIn("'" + workflow_path.relative_to(ROOT).as_posix() + "'", verifier)
        for key, source in self.files.items():
            with self.subTest(workflow=key):
                self.assertIn("check-actionlint.ps1", source)
                self.assertIn("if ($LASTEXITCODE -ne 0) { throw 'actionlint failed.' }", source)

    def test_stable_precommit_windows_matrix_matches_release_verification(self):
        import re
        upgrade = self.files["01"]
        release = self.files["release"]
        pattern = r"^      - name: Windows PowerShell 5\.1 - (test_[a-z_]+)$"
        standard = re.findall(pattern, release, re.M)
        stable = re.findall(pattern, upgrade, re.M)
        self.assertEqual(len(standard), 18)
        self.assertEqual(stable, standard)
        self.assertIn("Prepare isolated environment for stable-only precommit Windows tests", upgrade)
        self.assertIn("Copy-Item -LiteralPath $env:UPGRADE_MODELS", upgrade)
        before_write = upgrade.split("\n  commit:", 1)[0]
        for step in before_write.split("      - name: Windows PowerShell 5.1 - ")[1:]:
            self.assertIn("if: ${{ success() && inputs.commit_changes }}", step.split("\n      - name:", 1)[0])
        self.assertLess(
            upgrade.index("Make an unpushed local stable candidate checkpoint"),
            upgrade.index("      - name: Windows PowerShell 5.1 - test_portable_config"))
        self.assertIn("CANDIDATE_LOCAL_SHA=", upgrade)
        self.assertIn("Converter regression failed", before_write)
        self.assertIn("tool\\python-lock.py validate-runtime", before_write)
        self.assertLess(
            upgrade.index("      - name: Windows PowerShell 5.1 - test_browser_smoke"),
            upgrade.index("      - name: Pre-commit complete Windows audit"))
        self.assertIn("    timeout-minutes: 125", before_write)

    def test_pinned_checkout_uses_reviewed_node24_commit(self):
        for source in self.files.values():
            self.assertEqual(
                source.count("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"), 2)
            self.assertNotIn("11bd71901bbe5b1630ceea73d27597364c9af683", source)

    def test_trial_customer_zip_runs_before_optional_publication(self):
        release = self.files["release"]
        verify, publish = release.split("\n  publish:", 1)
        self.assertIn("id: trial_package", verify)
        self.assertIn("tool\\package-release.py --version $env:RELEASE_VERSION", verify)
        self.assertIn("TRIAL_RELEASE_ZIP=PASS", verify)
        self.assertIn("archive_sha256: ${{ steps.trial_package.outputs.archive_sha256 }}", verify)
        self.assertIn("EXPECTED_TRIAL_ARCHIVE_SHA256: ${{ needs.verify.outputs.archive_sha256 }}", publish)
        self.assertIn("Publisher ZIP bytes differ", publish)
        self.assertNotIn("gh release create", verify)
        self.assertIn("if: ${{ needs.verify.result == 'success' && inputs.publish_release", publish)
        self.assertIn("Report incomplete draft recovery", publish)

    def test_stable_candidate_requires_release_audit_before_remote_commit(self):
        upgrade = self.files["01"]
        read_only, writer = upgrade.split("\n  commit:", 1)
        self.assertIn("Pre-commit complete Windows audit", read_only)
        self.assertIn("if: ${{ success() && inputs.commit_changes }}", read_only)
        self.assertIn("release-audit.py --release", read_only)
        self.assertIn("release-audit.py --verify", read_only)
        self.assertIn("tool\\package-release.py --version $tag", read_only)
        self.assertIn("safe recovery", writer.lower())
        self.assertNotIn("gh release create", writer)

    def test_lfs_growth_estimates_and_new_upstream_fields_are_reported(self):
        source = read(ROOT / ".github/maintenance/01-upgrade-runtime.py")
        self.assertIn("NEW_VERSION_LFS_BYTES=", source)
        self.assertIn("LFS_CAPACITY_WARNING=", source)
        self.assertIn("Missing=", source)
        self.assertIn("New package fields require compatibility review:", source)

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
            ["01-upgrade-codex-runtime.yml", "02-verify-and-publish-portable.yml"])
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
        self.assertEqual(script.GROUPS["runtime"][1], 21)
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
