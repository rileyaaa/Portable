"""Release tests use tiny synthetic repositories; never package user state."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).absolute().parents[1]
spec = importlib.util.spec_from_file_location("portable_release", ROOT / "tool/package-release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
CONVERTER = "Version_History/AI account format conversion/"
PROJECT_DOCS = {
    "README.md", "DEVELOPMENT.md", "tool/工具更新说明.md", CONVERTER + "README.md",
}
MODE_COPIES = {
    f"Version_History/{mode}专用包-{script}.ps1"
    for mode in ("YOLO mode", "常用模式") for script in ("env", "run-codex")
}
CONVERTER_RUNTIME = {CONVERTER + name for name in (
    "index.html", "app/app.js", "app/converter.js", "app/style.css",
)}


def native_exe():
    body = bytearray(128)
    body[:2] = b"MZ"
    struct.pack_into("<I", body, 0x3C, 64)
    body[64:70] = b"PE\0\0\x64\x86"
    return bytes(body)


class ReleasePackageTests(unittest.TestCase):
    def setUp(self):
        release.check_root(ROOT)
        scratch = ROOT / "tmp"
        if not scratch.exists() and not scratch.is_symlink():
            scratch.mkdir()
        release.ordinary(scratch, directory=True)
        self.temp = tempfile.TemporaryDirectory(prefix="release-test-", dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "便携 package"
        self.root.mkdir()
        self.git("init", "--quiet")
        self.git("config", "user.name", "Synthetic release test")
        self.git("config", "user.email", "release-test@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.write(".gitignore", b"/tmp/\nenv.local.ps1\n/home/auth.json\n")
        self.write("env.ps1", b"# synthetic default configuration\n")
        self.write("README.md", "synthetic 便携\n".encode())
        for name in (PROJECT_DOCS - {"README.md"}) | MODE_COPIES | CONVERTER_RUNTIME:
            self.write(name, b"synthetic customer content\n")
        self.development_files = {
            ".gitignore", ".gitattributes", ".github/workflows/release.yml",
            "tests/test_synthetic.py", "tests/fixtures/synthetic.json",
            CONVERTER + "test/smoke.js", CONVERTER + "test/static-audit.js",
            CONVERTER + "test/multi-array-sample.json",
        }
        for name in self.development_files - {".gitignore"}:
            self.write(name, b"synthetic development content\n")
        # A third-party file with a test-like name must remain byte-for-byte intact.
        self.write("tool/vendor/runtime/test.js", b"synthetic vendor runtime\n")
        self.write("codex-resources/.gitkeep", b"")
        self.write("home/.keep", b"")
        self.write("home/.agents/plugins/marketplace.json", b'{"synthetic":true}\n')
        self.write("home/rules/default.rules", b"# synthetic committed policy\n")
        self.write("login_json/.gitkeep", b"")
        for name in release.RUNTIME_FILES - {"codex-package.json"}:
            self.write(name, native_exe())
        self.write("codex-package.json", json.dumps({
            "version": "0.163.0", "target": "x86_64-pc-windows-msvc", "entrypoint": "codex.exe",
            "resourcesDir": "codex-resources", "pathDir": "codex-path",
        }).encode())
        manifest = json.dumps({"version": "0.163.0", "target": "x86_64-pc-windows-msvc", "files": {
            name: {"sha256": hashlib.sha256((self.root / name).read_bytes()).hexdigest()}
            for name in sorted(release.RUNTIME_FILES)
        }}, indent=2).encode()
        self.write("tool/runtime-manifest.json", manifest)
        self.write("run-codex.ps1", ('$ExpectedRuntimeManifestSha256 = "' + hashlib.sha256(manifest).hexdigest() + '"\n').encode())
        self.browser_executable = "tool/automation/browsers/chromium-1247/chrome-win64/chrome.exe"
        self.write(self.browser_executable, native_exe())
        self.write("tool/automation/install-browser.py", (ROOT / "tool/automation/install-browser.py").read_bytes())
        self.write("tool/automation/versions.json", json.dumps({"browser": {
            "version": "155.0.8059.12", "revision": "1247", "payloadBundled": True,
            "payloadManifest": "browser-manifest.json",
            "executable": "browsers/chromium-1247/chrome-win64/chrome.exe",
        }}).encode())
        self.write("tool/automation/browser-manifest.json", json.dumps({
            "schemaVersion": 1, "browserVersion": "155.0.8059.12", "revision": "1247", "platform": "win32-x64",
            "archive": {
                "sourceUrl": "https://cdn.playwright.dev/builds/cft/155.0.8059.12/win64/chrome-win64.zip",
                "resolvedUrl": "https://storage.googleapis.com/chrome-for-testing-public/155.0.8059.12/win64/chrome-win64.zip",
                "sha256": "0" * 64, "size": 128,
            },
            "fileCount": 1, "uncompressedBytes": len(native_exe()), "files": {
                self.browser_executable: {"sha256": hashlib.sha256(native_exe()).hexdigest(), "size": len(native_exe())},
            },
        }).encode())
        self.commit()

    def write(self, name, contents):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)

    def git(self, *arguments):
        return subprocess.check_output(["git", "-C", str(self.root), *arguments], stderr=subprocess.PIPE)

    def commit(self):
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "Synthetic fixture")

    def test_archive_is_reproducible_and_excludes_untracked_private_state(self):
        script = self.root / "tool/package-release.py"
        script.write_bytes(Path(release.__file__).read_bytes())
        self.commit()
        self.write("env.local.ps1", b"synthetic private value")
        self.write("home/auth.json", b"synthetic credential fixture")
        first = release.build_release(self.root, "v0.163.0-portable.1")
        second = release.build_release(self.root, "v0.163.0-portable.1")
        self.assertEqual(first["archive_sha256"], second["archive_sha256"])
        self.assertEqual(Path(first["archive"]).name, "Codex-Portable-v0.163.0-portable.1-windows-x64.zip")
        metadata = json.loads(Path(first["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(metadata["source_commit"], self.git("rev-parse", "HEAD").decode().strip())
        self.assertNotIn("env.local.ps1", metadata["files"])
        self.assertNotIn("home/auth.json", metadata["files"])
        self.assertEqual(metadata["file_count"], len(metadata["files"]))
        self.assertEqual(metadata["package_kind"], "customer")
        self.assertEqual(metadata["browser_version"], "155.0.8059.12")
        self.assertIn(self.browser_executable, metadata["files"])
        self.assertNotIn("codex-exec-server.exe", metadata["files"])
        excluded = self.development_files | {"tool/package-release.py"}
        self.assertEqual(set(metadata["excluded_files"]), excluded)
        self.assertTrue(all(metadata["excluded_files"].values()))
        self.assertEqual(metadata["excluded_file_count"], len(excluded))
        self.assertEqual(metadata["source_file_count"], metadata["file_count"] + len(excluded))
        self.assertTrue(excluded.isdisjoint(metadata["files"]))
        self.assertTrue((PROJECT_DOCS | MODE_COPIES | CONVERTER_RUNTIME | release.RUNTIME_FILES)
                        .issubset(metadata["files"]))
        with zipfile.ZipFile(first["archive"]) as archive:
            self.assertEqual(set(archive.namelist()), {"Codex/" + name for name in metadata["files"]})
            self.assertEqual(archive.read("Codex/README.md"), "synthetic 便携\n".encode())
            self.assertEqual(archive.read("Codex/codex.exe"), native_exe())
            self.assertEqual(archive.read("Codex/home/.agents/plugins/marketplace.json"), b'{"synthetic":true}\n')
            self.assertEqual(archive.read("Codex/home/rules/default.rules"), b"# synthetic committed policy\n")
            self.assertEqual(archive.read("Codex/tool/vendor/runtime/test.js"), b"synthetic vendor runtime\n")
        self.assertTrue(Path(first["checksums"]).read_text(encoding="ascii").startswith(first["archive_sha256"]))
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "ascii"
        # Embedded Windows Python ignores PYTHON* variables under ._pth isolation;
        # configure the same ASCII pipe explicitly so both platforms exercise it.
        result = subprocess.run([
            sys.executable, "-B", "-c",
            "import runpy,sys; sys.stdout.reconfigure(encoding='ascii'); "
            "sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')",
            str(script), "--version", "v0.163.0-portable.1",
        ], env=environment, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout.decode("ascii"))
        self.assertTrue(Path(output["archive"]).is_file())
        self.assertEqual(Path(output["output_dir"]).parent, self.root / "tmp")

    def test_release_label_cannot_claim_a_different_codex_version(self):
        with self.assertRaisesRegex(ValueError, "Release tag must match bundled Codex version"):
            release.build_release(self.root, "v0.169.0-portable.1")
        with self.assertRaisesRegex(ValueError, "Release tag must match bundled Codex version"):
            release.build_release(self.root, "freeform-build")

    def test_dirty_checkout_and_lfs_pointer_are_refused(self):
        self.write("README.md", b"uncommitted update\n")
        with self.assertRaisesRegex(ValueError, "Commit tracked changes"):
            release.build_release(self.root)
        self.commit()
        self.write("extra.bin", release.LFS_HEADER + b"\noid sha256:synthetic\nsize 1\n")
        self.commit()
        with self.assertRaisesRegex(ValueError, "Unhydrated Git LFS pointer"):
            release.build_release(self.root)
        self.assertFalse((self.root / "tmp").exists())

    def test_private_paths_collisions_and_links_are_rejected_before_content_read(self):
        for name in ("env.local.ps1", "home/auth.json", "home/.agents/local.json", "home/rules/private.rules",
                     "work/user.sql", "../outside", "C:/outside", "NUL.txt", "foo/../outside"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                release.safe_name(name)
        with self.assertRaisesRegex(ValueError, "Case-colliding"):
            release.unique_windows_names(["README.md", "README.MD"])
        target = self.root / "README.md"
        other = self.root.parent / "synthetic-outside.txt"
        other.write_bytes(b"synthetic outside")
        target.unlink()
        try:
            os.link(other, target)
        except OSError as error:
            self.skipTest(f"Hard links unavailable: {error}")
        with self.assertRaisesRegex(ValueError, "single-link"):
            release.build_release(self.root)

    def test_runtime_identity_and_archive_integrity_are_checked(self):
        self.write("codex-code-mode-host.exe", native_exe() + b"modified")
        self.commit()
        with self.assertRaisesRegex(ValueError, "Runtime file is missing, altered"):
            release.build_release(self.root)
        self.write("codex-code-mode-host.exe", native_exe())
        self.commit()
        built = release.build_release(self.root)
        metadata = json.loads(Path(built["manifest"]).read_text(encoding="utf-8"))
        metadata["files"]["README.md"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Archive member digest differs"):
            release.verify_zip(Path(built["archive"]), metadata["files"])

    def test_excluded_inputs_are_still_validated_before_filtering(self):
        name = "tests/test_synthetic.py"
        self.write(name, release.LFS_HEADER + b"\noid sha256:synthetic\nsize 1\n")
        self.commit()
        with self.assertRaisesRegex(ValueError, "Unhydrated Git LFS pointer"):
            release.build_release(self.root)
        self.write(name, b"synthetic development content\n")
        self.commit()
        other = self.root.parent / "synthetic-excluded-source.txt"
        other.write_bytes((self.root / name).read_bytes())
        (self.root / name).unlink()
        try:
            os.link(other, self.root / name)
        except OSError as error:
            self.skipTest(f"Hard links unavailable: {error}")
        with self.assertRaisesRegex(ValueError, "single-link"):
            release.build_release(self.root)
        self.assertFalse((self.root / "tmp").exists())

    def test_browser_inventory_and_payload_are_required(self):
        self.write(self.browser_executable, native_exe() + b"modified")
        self.commit()
        with self.assertRaisesRegex(ValueError, "Pinned browser payload has changed"):
            release.build_release(self.root)
        self.write(self.browser_executable, native_exe())
        extra = "tool/automation/browsers/unpinned/extra.bin"
        self.write(extra, b"synthetic extra browser")
        self.commit()
        with self.assertRaisesRegex(ValueError, "browser inventory differs"):
            release.build_release(self.root)
        (self.root / extra).unlink()
        (self.root / self.browser_executable).unlink()
        self.commit()
        with self.assertRaisesRegex(ValueError, "browser inventory differs"):
            release.build_release(self.root)

    def test_customer_selection_keeps_actual_runtime_and_documentation(self):
        # Read names only from Git, never recurse through local user state.
        names = [name.decode("utf-8") for name in release.git(ROOT, "ls-files", "-z").split(b"\0") if name]
        included, excluded = release.customer_files(names)
        self.assertEqual(set(included) | set(excluded), set(names))
        self.assertTrue(set(included).isdisjoint(excluded))
        self.assertNotIn("codex-exec-server.exe", included)
        self.assertTrue((PROJECT_DOCS | MODE_COPIES | CONVERTER_RUNTIME | release.RUNTIME_FILES
                         | {"env.ps1", "run-codex.ps1", "tool/setup-tools.ps1", "tool/runtime-manifest.json"})
                        .issubset(included))
        self.assertTrue({name for name in names if name.endswith(".bat")}.issubset(included))
        self.assertTrue({".gitignore", ".gitattributes", "tool/package-release.py",
                         "tests/test_release_package.py",
                         CONVERTER + "test/smoke.js", CONVERTER + "test/static-audit.js",
                         CONVERTER + "test/multi-array-sample.json"}.issubset(excluded))
        self.assertFalse(any(name.startswith(("tests/", ".github/", CONVERTER + "test/"))
                             for name in included))
        # Preserve all pinned tool payloads, functional skills and their licenses.
        self.assertEqual({name for name in names if name.startswith(("home/skills/", "home/plugins/"))},
                         {name for name in included if name.startswith(("home/skills/", "home/plugins/"))})
        self.assertEqual({name for name in names if name.startswith("tool/")}
                         - {"tool/package-release.py"},
                         {name for name in included if name.startswith("tool/")})
        for name in ("env.local.ps1", "home/auth.json", "tests/../home/auth.json"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                release.customer_files([name])


if __name__ == "__main__":
    unittest.main()
