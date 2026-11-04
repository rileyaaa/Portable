"""Synthetic browser archives exercise the production installer without networking."""
import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
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

    def test_browser_downloader_rejects_redirect_before_network_followup(self):
        official = "https://storage.googleapis.com/chrome-for-testing-public/test/win64/chrome-win64.zip"
        for redirected in (
            "https://evil.invalid/collect", "https://storage.googleapis.com/elsewhere",
            "http://storage.googleapis.com/unsafe", "https://127.0.0.1/private",
        ):
            with self.subTest(redirected=redirected):
                with self.assertRaisesRegex(ValueError, "must not redirect"):
                    browser._RejectBrowserDownloadRedirect().redirect_request(
                        browser.urllib.request.Request(official), None,
                        302, "Found", {}, redirected)

    def test_browser_downloader_locks_url_before_creating_package_file(self):
        official = "https://storage.googleapis.com/chrome-for-testing-public/test/win64/chrome-win64.zip"
        manifest = {"archive": {"resolvedUrl": official, "size": 20}}
        payload = b"synthetic-archive"
        def response(url):
            result = io.BytesIO(payload)
            result.url = url
            return result
        with patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:10808"}, clear=True), \
             patch.object(browser.urllib.request, "build_opener") as factory:
            factory.return_value.open.side_effect = lambda url, timeout: response(official)
            target = browser.download_archive(self.root, self.root, manifest)
            self.assertEqual(target.read_bytes(), payload)
            self.assertEqual(factory.call_args.args[0].proxies,
                             {"http": "http://127.0.0.1:10808"})
            self.assertIsInstance(factory.call_args.args[1],
                                  browser._RejectBrowserDownloadRedirect)
            self.assertEqual(factory.return_value.open.call_args.kwargs["timeout"], 60)
        # Even a deliberately misbehaving mocked opener must not create an
        # output file for a foreign URL; a real opener rejects earlier.
        separate = self.root / "bad-response"
        separate.mkdir()
        with patch.object(browser.urllib.request, "build_opener") as factory:
            factory.return_value.open.side_effect = lambda url, timeout: response("https://evil.invalid/asset")
            with self.assertRaisesRegex(ValueError, "Unexpected browser download redirect"):
                browser.download_archive(self.root, separate, manifest)
        self.assertFalse((separate / "chrome-win64.zip").exists())

    def test_pinned_browser_inventory_matches_installed_official_bytes(self):
        manifest, prefix = browser.load_manifest(ROOT)
        versions = json.loads((ROOT / 'tool/automation/versions.json').read_text(encoding='utf-8'))
        self.assertEqual(prefix, 'tool/automation/browsers/chromium-' + versions['browser']['revision'] + '/')
        self.assertEqual(manifest['browserVersion'], versions['browser']['version'])
        self.assertGreaterEqual(manifest['fileCount'], 150)
        browser.verify_payload(ROOT, manifest)


if __name__ == "__main__":
    unittest.main()
