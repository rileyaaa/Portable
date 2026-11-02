"""Synthetic, network-free regression tests for repeated manual Codex upgrades.

Use the checked-out source/configuration but never rewrite the real checkout,
download upstream binaries or use actual user credentials.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
from unittest import TestCase, mock

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise AssertionError("Missing manual maintenance module: " + relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


UPGRADE = load_module("testable_portable_upgrade", ".github/maintenance/01-upgrade-runtime.py")
AUDIT = load_module("testable_portable_compat", ".github/maintenance/02-compatibility.py")


def synthetic_pe() -> bytes:
    contents = bytearray(65540)
    contents[:2] = b"MZ"
    contents[0x3c:0x40] = (0x80).to_bytes(4, "little")
    contents[0x80:0x86] = b"PE\0\0\x64\x86"
    return bytes(contents)


def upstream_metadata(version: str, with_server: bool = True) -> dict:
    info = {
        "layoutVersion": 1,
        "version": version,
        "target": UPGRADE.TARGET,
        "variant": "codex",
        "entrypoint": "bin/codex.exe",
        "resourcesDir": "codex-resources",
        "pathDir": "codex-path",
    }
    if with_server:
        info["execServer"] = UPGRADE.OPTIONAL_EXEC
    return info


def canonical_fixture(directory: Path, version: str, *, extra: bool = False):
    exe = synthetic_pe()
    metadata = upstream_metadata(version)
    members = {path: exe for path in UPGRADE.UPSTREAM.values()}
    members["codex-package.json"] = json.dumps(metadata).encode("utf-8")
    members[UPGRADE.OPTIONAL_EXEC] = exe
    members["codex-resources/voice/voice-model.bin"] = b"not shipped"
    if extra:
        members["codex-resources/extra-new-service.exe"] = exe
    archive = directory / "canonical.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name, data in sorted(members.items()):
            info = tarfile.TarInfo("package/" + name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    plan = {
        "old_version": "0.166.0",
        "version": version,
        "tag": "rust-v" + version,
        "archive": {
            "url": "https://github.com/openai/codex/releases/download/rust-v" + version +
                   "/" + UPGRADE.ARCHIVE,
            "sha256": UPGRADE.file_digest(archive),
            "size": archive.stat().st_size,
        },
        "raw": {
            name: {"sha256": hashlib.sha256(exe).hexdigest(), "size": len(exe)}
            for name in UPGRADE.RAW_ASSETS
        },
    }
    return archive, plan


def next_version(raw: str, increment: int) -> str:
    major, minor, patch = UPGRADE.version_tuple(raw)[:3]
    return f"{major}.{minor}.{patch + increment}"


def fake_components(version: str):
    exe = {
        name: ("synthetic " + version + " " + name).encode("utf-8")
        for name in UPGRADE.UPSTREAM
    }
    metadata = upstream_metadata(version, with_server=False)
    metadata["entrypoint"] = "codex.exe"
    exe["codex-package.json"] = (json.dumps(metadata, indent=2) + "\n").encode()
    return exe, metadata, 0, None



class OfficialReleaseUrlTests(TestCase):
    def test_accepts_canonical_stable_and_alpha_links(self):
        self.assertEqual(
            UPGRADE.parse_official_release_url(
                "https://github.com/openai/codex/releases/tag/rust-v0.167.0-alpha.3"),
            "0.167.0-alpha.3")
        self.assertEqual(
            UPGRADE.parse_official_release_url(
                "https://github.com/openai/codex/releases/tag/rust-v0.167.0"),
            "0.167.0")
        self.assertGreater(UPGRADE.version_tuple("0.167.0"),
                           UPGRADE.version_tuple("0.167.0-alpha.3"))
        self.assertGreater(UPGRADE.version_tuple("0.167.0-alpha.3"),
                           UPGRADE.version_tuple("0.167.0-alpha.2"))

    def test_rejects_unofficial_or_ambiguous_urls(self):
        invalid = (
            "http://github.com/openai/codex/releases/tag/rust-v0.167.0-alpha.3",
            "https://github.com/evil/codex/releases/tag/rust-v0.167.0-alpha.3",
            "https://github.com/openai/codex/releases/download/rust-v0.167.0-alpha.3/file",
            "https://github.com/openai/codex/releases/tag/rust-v0.167.0-alpha.3/",
            "https://github.com/openai/codex/releases/tag/rust-v0.167.0-alpha.3?download=1",
            "https://github.com/openai/codex/releases/tag/rust-v0.167.0-alpha.3#frag",
            "https://github.com@evil.example/openai/codex/releases/tag/rust-v0.167.0-alpha.3",
            "https://github.com/openai/codex/releases/tag/rust-v0.167.0-rc",
            "https://github.com/openai/codex/releases/tag/rust-v0.167.0-alpha.03",
            "https://github.com/openai/codex/releases/tag/rust-v0.167.0-alpha.٣",
            "https://github.com/openai/codex/releases/tag/rust-v0.167.0-alpha.3\nX",
            "0.167.0-alpha.3",
        )
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(RuntimeError):
                UPGRADE.parse_official_release_url(url)

    def test_official_published_channel_must_match_url_tag(self):
        current = json.loads((ROOT / "tool/runtime-manifest.json").read_text())["version"]
        major, minor, patch = UPGRADE.version_tuple(current)[:3]
        version = f"{major}.{minor}.{patch + 1}-alpha.3"
        tag = "rust-v" + version
        names = [UPGRADE.ARCHIVE] + list(UPGRADE.RAW_ASSETS.values())
        assets = [{"name": name, "size": 65540, "digest": "sha256:" + "a" * 64,
                   "browser_download_url":
                       "https://github.com/openai/codex/releases/download/" + tag + "/" + name}
                  for name in names]
        release = {"tag_name": tag, "draft": False, "prerelease": True, "assets": assets}
        url = "https://github.com/openai/codex/releases/tag/" + tag
        with mock.patch.object(UPGRADE, "github_request",
                               return_value=json.dumps(release).encode("utf-8")):
            plan = UPGRADE.official_plan(ROOT, url)
        self.assertEqual(plan["version"], version)
        self.assertTrue(plan["prerelease"])
        self.assertEqual(plan["release_url"], url)
        release["prerelease"] = False
        with mock.patch.object(UPGRADE, "github_request",
                               return_value=json.dumps(release).encode("utf-8")):
            with self.assertRaisesRegex(RuntimeError, "status disagrees"):
                UPGRADE.official_plan(ROOT, url)


class OfficialArchiveContractTests(TestCase):
    def test_canonical_archive_excludes_voice_and_remote_server(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, plan = canonical_fixture(Path(directory), "0.167.0")
            output, metadata, voice_count, removed_server_sha = UPGRADE.collect(archive, plan)
            self.assertEqual(set(output), set(UPGRADE.UPSTREAM) | {"codex-package.json"})
            self.assertEqual(voice_count, 1)
            self.assertEqual(removed_server_sha, hashlib.sha256(synthetic_pe()).hexdigest())
            self.assertNotIn("execServer", metadata)
            self.assertEqual(metadata["entrypoint"], "codex.exe")
            self.assertEqual(output["codex.exe"], synthetic_pe())

    def test_unreviewed_archive_file_blocks_upgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, plan = canonical_fixture(Path(directory), "0.167.0", extra=True)
            with self.assertRaisesRegex(RuntimeError, "New upstream layout"):
                UPGRADE.collect(archive, plan)

    def test_official_archive_digest_mismatch_blocks_upgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, plan = canonical_fixture(Path(directory), "0.167.0")
            plan["archive"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(RuntimeError, "SHA-256 differs"):
                UPGRADE.collect(archive, plan)

    def test_bad_independent_executable_digest_blocks_upgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, plan = canonical_fixture(Path(directory), "0.167.0")
            plan["raw"]["codex.exe"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(RuntimeError, "independent binary hash"):
                UPGRADE.collect(archive, plan)


class RepeatedUpgradeAndCompatibilityTests(TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.repo = Path(self.work.name)
        # Copy only the small, tracked configuration/test inputs. Real 500 MB
        # EXEs and package caches must never be copied or modified by this test.
        text_sources = set(UPGRADE.ALLOWED) - set(UPGRADE.UPSTREAM)
        text_sources |= {".gitattributes", ".github/workflows/02-verify-and-publish-portable.yml"}
        for relative in sorted(text_sources):
            original = ROOT / relative
            if not original.is_file():
                continue
            destination = self.repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, destination)
        for relative in UPGRADE.UPSTREAM:
            path = self.repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"old synthetic native fixture")
        (self.repo / "codex-resources").mkdir(exist_ok=True)
        self.start_version = json.loads(
            (self.repo / "tool/runtime-manifest.json").read_text(encoding="utf-8"))["version"]

    def apply_mock_upgrade(self, version: str) -> None:
        previous = json.loads(
            (self.repo / "tool/runtime-manifest.json").read_text(encoding="utf-8"))["version"]
        plan = {"version": version, "old_version": previous,
                "tag": "rust-v" + version,
                "archive": {"url": "https://github.com/openai/codex/releases/download/"
                            "rust-v" + version + "/" + UPGRADE.ARCHIVE,
                            "sha256": "a" * 64}}
        self.assertGreater(UPGRADE.version_tuple(version), UPGRADE.version_tuple(previous))
        with (mock.patch.object(UPGRADE, "collect", return_value=fake_components(version)),
              mock.patch.object(UPGRADE, "github_request", return_value=b"license text\n" * 200)):
            updates = UPGRADE.compile_updates(self.repo, self.repo / "not-used.tar.gz", plan)
        self.assertNotIn("codex-exec-server.exe", updates)
        self.assertFalse(any("voice" in filename for filename in updates))
        UPGRADE.write_safe(self.repo, updates)
        result = AUDIT.source_check(self.repo)
        self.assertEqual(result["version"], version)
        self.assertEqual(len(result["variables"]), 45)
        manifest = json.loads((self.repo / "tool/runtime-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(set(manifest["files"]), set(UPGRADE.UPSTREAM) |
                         {"codex-package.json"})
        self.assertEqual(
            (self.repo / "codex.exe").read_bytes(), updates["codex.exe"])

    def test_two_consecutive_upgrades_keep_all_identity_and_mode_pins(self):
        self.apply_mock_upgrade(next_version(self.start_version, 1))
        self.apply_mock_upgrade(next_version(self.start_version, 2))
        readme = (self.repo / "README.md").read_text(encoding="utf-8")
        self.assertIn("当前为 " + next_version(self.start_version, 2) +
                      "；运行组件的查找顺序须经发布前兼容检查确认", readme)

    def test_changelog_date_is_reproducible_across_jobs(self):
        with mock.patch.dict(os.environ, {"UPGRADE_CHANGELOG_DATE": "2026-11-02"}):
            self.apply_mock_upgrade(next_version(self.start_version, 1))
        self.assertIn("## 2026-11-02：Codex ".encode("utf-8"),
                      (self.repo / "DEVELOPMENT.md").read_bytes())

    def test_bad_calendar_date_cannot_write_changelog(self):
        with mock.patch.dict(os.environ, {"UPGRADE_CHANGELOG_DATE": "2026-02-30"}):
            with self.assertRaisesRegex(RuntimeError, "Invalid calendar changelog date"):
                self.apply_mock_upgrade(next_version(self.start_version, 1))

    def test_windows_crlf_development_log_insert_remains_consistent(self):
        changelog = self.repo / "DEVELOPMENT.md"
        plain = changelog.read_bytes().replace(b"\r\n", b"\n")
        changelog.write_bytes(plain.replace(b"\n", b"\r\n"))
        self.apply_mock_upgrade(next_version(self.start_version, 1))
        updated = changelog.read_bytes()
        self.assertEqual(updated.count(b"\n"), updated.count(b"\r\n"))
        self.assertNotIn(b"\r\r\n", updated)
        self.assertIn(("## " + "20").encode("utf-8"), updated)

    def test_alpha_upgrade_then_stable_promotion_is_repeatable(self):
        stable = next_version(self.start_version, 1)
        self.apply_mock_upgrade(stable + "-alpha.3")
        self.apply_mock_upgrade(stable)

    def test_computed_package_local_variable_removal_is_not_silently_skipped(self):
        self.apply_mock_upgrade(next_version(self.start_version, 1))
        for relative in UPGRADE.MODE_ENVS:
            path = self.repo / relative
            text = path.read_bytes()
            line = b'$env:CODEX_PYTHON = Join-Path $Script:CodexPortableRoot "tool\\python\\python.exe"'
            self.assertEqual(text.count(line), 1)
            path.write_bytes(text.replace(line, b"# removed for negative regression"))
        with self.assertRaisesRegex(RuntimeError, "Missing or duplicate managed"):
            AUDIT.source_check(self.repo)


if __name__ == "__main__":
    import unittest
    unittest.main()
