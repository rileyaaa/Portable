"""Synthetic browser archives exercise the production installer without networking."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).absolute().parents[1]
SPEC = importlib.util.spec_from_file_location("browser_install", ROOT / "tool/automation/install-browser.py")
browser = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(browser)


class BrowserInstallTests(unittest.TestCase):
    def setUp(self):
        scratch = browser.checked(ROOT, ROOT / "tmp", directory=True, missing=True)
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="browser-install-test-", dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / "browser.zip"
        self.stage = self.root / "stage"
        self.stage.mkdir()
        self.prefix = "tool/automation/browsers/chromium-1247/"

    def make_archive(self, files):
        with zipfile.ZipFile(self.archive, "w") as output:
            for name, value in files.items():
                output.writestr(name, value)
        return {"archive": {"size": self.archive.stat().st_size, "sha256": browser.digest(self.archive)},
                "files": {self.prefix + name: {"size": len(value), "sha256": hashlib.sha256(value).hexdigest()}
                          for name, value in files.items()}}

    def test_archive_inventory_and_content_are_verified_before_use(self):
        manifest = self.make_archive({"chrome-win64/chrome.exe": b"synthetic", "chrome-win64/locales/en.pak": b"locale"})
        browser.extract_archive(self.root, self.archive, self.stage, manifest, self.prefix)
        self.assertEqual((self.stage / "chrome-win64/chrome.exe").read_bytes(), b"synthetic")
        self.assertEqual((self.stage / "chrome-win64/locales/en.pak").read_bytes(), b"locale")
        bad_stage = self.root / "bad-stage"
        bad_stage.mkdir()
        manifest["files"][self.prefix + "chrome-win64/chrome.exe"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "digest differs"):
            browser.extract_archive(self.root, self.archive, bad_stage, manifest, self.prefix)

    def test_archive_traversal_and_linked_output_are_rejected(self):
        manifest = self.make_archive({"chrome-win64/../../escaped": b"escape"})
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            browser.extract_archive(self.root, self.archive, self.stage, manifest, self.prefix)
        self.assertEqual(list(self.stage.iterdir()), [])
        manifest = self.make_archive({"chrome-win64/chrome.exe": b"synthetic"})
        outside = self.root / "outside"
        outside.mkdir()
        try:
            os.symlink(outside, self.stage / "chrome-win64", target_is_directory=True)
        except OSError as error:
            self.skipTest("Directory symlinks unavailable: " + str(error))
        with self.assertRaisesRegex(ValueError, "links"):
            browser.extract_archive(self.root, self.archive, self.stage, manifest, self.prefix)
        self.assertEqual(list(outside.iterdir()), [])

    def test_browser_download_rejects_redirect_before_following_it(self):
        url = "https://storage.googleapis.com/chrome-for-testing-public/155.0.8059.12/win64/chrome-win64.zip"
        request = browser.urllib.request.Request(url)
        with self.assertRaisesRegex(ValueError, "Pinned browser download must not redirect"):
            browser._RejectBrowserDownloadRedirect().redirect_request(
                request, None, 302, "Found", {}, "https://example.invalid/browser.zip")

    def test_missing_revision_and_incomplete_payload_are_distinct(self):
        executable = bytearray(128)
        executable[:2] = b"MZ"
        executable[60:64] = (64).to_bytes(4, "little")
        executable[64:70] = b"PE\0\0\x64\x86"
        files = {"chrome-win64/chrome.exe": bytes(executable),
                 "chrome-win64/chrome.dll": b"synthetic dll"}
        manifest = self.make_archive(files)
        manifest["revision"] = "1247"
        profile = self.root / "cache/browser/profile"
        profile.mkdir(parents=True)
        sentinel = profile / "sentinel"
        sentinel.write_bytes(b"preserve")
        self.assertEqual(browser.payload_state(self.root, manifest, self.prefix), "missing")
        self.assertFalse((self.root / self.prefix).exists())
        for name, content in files.items():
            path = self.root / self.prefix / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.assertEqual(browser.payload_state(self.root, manifest, self.prefix), "verified")
        for name, content in files.items():
            path = self.root / self.prefix / name
            path.unlink()
            self.assertEqual(browser.payload_state(self.root, manifest, self.prefix), "incomplete")
            self.assertFalse(path.exists())
            path.write_bytes(content)
        dll = self.root / self.prefix / "chrome-win64/chrome.dll"
        corrupt = b"X" * len(files["chrome-win64/chrome.dll"])
        dll.write_bytes(corrupt)
        self.assertEqual(browser.payload_state(self.root, manifest, self.prefix), "incomplete")
        self.assertEqual(dll.read_bytes(), corrupt)
        self.assertEqual(sentinel.read_bytes(), b"preserve")

    def test_pinned_browser_inventory_matches_installed_official_bytes(self):
        manifest, prefix = browser.load_manifest(ROOT)
        self.assertEqual(prefix, "tool/automation/browsers/chromium-1727472/")
        self.assertEqual(manifest["fileCount"], 305)
        self.assertEqual(manifest["browserVersion"], "158.0.8127.88")
        self.assertEqual(manifest["archive"]["sourceUrl"], "https://storage.googleapis.com/chrome-for-testing-public/158.0.8127.88/win64/chrome-win64.zip")
        self.assertEqual(manifest["archive"]["sha256"], "fda73ca9ffc7f02c5c85165cb472152540a76a7cecd8ec11314ea781e4454109")
        browser.verify_payload(ROOT, manifest)


if __name__ == "__main__":
    unittest.main()
