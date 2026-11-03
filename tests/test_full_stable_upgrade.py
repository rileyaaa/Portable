"""Offline security and contract tests for the full latest-stable Win11 upgrade.

Run BEFORE any artifact download. No internet, source wheels, new native EXE,
GitHub token or real package files are needed by these tests.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).absolute().parents[1]


def load(path: str, alias: str):
    script = ROOT / path
    spec = importlib.util.spec_from_file_location(alias, script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage = load("tool/full-stable-prepare.py", "portable_full_stage")
transfer = load("tool/full-stable-transfer.py", "portable_full_transfer")


class FullStableUpgradeTests(unittest.TestCase):
    def test_source_and_workflow_parse_without_running_downloads(self):
        for path in ("tool/full-stable-prepare.py", "tool/full-stable-transfer.py",
                     "tests/test_full_stable_upgrade.py"):
            ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)
        source = (ROOT / ".github/workflows/03-update-tools.yml").read_text(
            encoding="utf-8")
        self.assertIn("options: [check, prepare, full]", source)
        self.assertIn("    if: github.ref == 'refs/heads/main' && inputs.mode != 'full'", source)
        self.assertIn("name: Full tool stable refresh - Windows read-only verifier", source)
        self.assertIn("name: Full tool trusted writer", source)
        self.assertIn("needs: full_verify", source)
        self.assertIn("EXPECTED_ARTIFACT:", source)
        self.assertIn("EXPECTED_DIGEST:", source)
        self.assertIn("FULL_STABLE_WRITER_MATCH=PASS", source)
        self.assertIn("python-lock.py validate-runtime", source)
        self.assertIn("package-release.py --version", source)
        self.assertIn("release-audit.py --release", source)
        self.assertIn("release-audit.py --verify", source)
        self.assertIn("WINDOWS_PS_TEST_END=", source)
        self.assertNotIn("gh release create", source)
        self.assertNotIn("git push origin HEAD:refs/heads/main", source)
        full = source.split("\n  full_verify:", 1)[1]
        verifier, writer = full.split("\n  full_propose:", 1)
        self.assertIn("contents: read", verifier)
        self.assertNotIn("contents: write", verifier)
        self.assertIn("contents: write", writer)
        self.assertLess(verifier.index("Stage full latest-stable"), 
                        verifier.index("Full Python Node and converter"))
        self.assertLess(verifier.index("Full Python Node and converter"),
                        verifier.index("Bound candidate paths"))
        self.assertLess(verifier.index("Bound candidate paths"),
                        verifier.index("Fail fast on real customer ZIP inputs"))
        self.assertLess(verifier.index("Fail fast on real customer ZIP inputs"),
                        verifier.index("Check Windows PowerShell 5.1 regressions"))
        self.assertLess(verifier.index("Real package preflight"),
                        verifier.index("Upload exact verified candidate"))
        self.assertLess(writer.index("full-stable-transfer.py apply"),
                        writer.index("git push origin"))
        self.assertNotIn("full-stable-prepare.py prepare", writer)

    def test_full_major_targets_are_stable_versions_not_new_install_placeholders(self):
        plan = json.loads((ROOT / "tool/full-stable-upgrade-plan.json").read_text(
            encoding="utf-8"))
        names = [x["name"] for x in plan["targets"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(names), 14)
        entries = {x["name"]: x for x in plan["targets"]}
        for name, value in (
                ("python", "3.15.2"), ("pip", "26.2.2"),
                ("npm", "12.2.1"), ("corepack", "0.36.0"),
                ("7zip", "26.05"), ("playwright-mcp", "0.0.84"),
                ("pyinstaller", "6.22.3")):
            self.assertEqual(entries[name]["latestStable"], value)
        self.assertEqual(plan["state"], "PREPARATION_ONLY_NOT_INSTALLED")
        for name in ("python", "pip", "7zip", "corepack"):
            art = entries[name]["artifact"]
            self.assertTrue(art["url"].startswith("https://"))
            self.assertRegex(art["sha256"], r"^[a-f0-9]{64}$")
        # Same test runs before AND after Windows candidate staging. Never
        # mistake the read-only candidate's temporary ledger for a main merge.
        installed = json.loads((ROOT / "tool/installed-tools.json").read_text(
            encoding="utf-8"))["tools"]
        self.assertIn(installed["python"]["version"], ("3.14", "3.15.2"))
        self.assertIn(installed["npm"]["version"], ("11.20.0", "12.2.1"))

    def test_archive_paths_fail_closed(self):
        for text in ("", "..", "../evil", "a/../evil", "C:/thing",
                     "/absolute", "C:evil", "dir\\evil", "a//b", "foo.",
                     "CON", "AUX", "COM1.txt", "tool/name:stream", "hello?"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                stage.safe_path(text)
        self.assertEqual(stage.safe_path("chrome-win64/x64/chrome.exe"),
                         ("chrome-win64", "x64", "chrome.exe"))

    def test_unzip_rejects_traversal_symlink_and_colliding_case(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for names in (("../outside",), ("a/../x",), ("A", "a"),
                          ("C:/attack",)):
                archive = root / "case.zip"
                with zipfile.ZipFile(archive, "w") as f:
                    for name in names:
                        f.writestr(name, "sample")
                with self.subTest(names=names), self.assertRaises(ValueError):
                    stage.unzip_checked(archive, root / "out")
                archive.unlink()
            archive = root / "ok.zip"
            with zipfile.ZipFile(archive, "w") as f:
                f.writestr("root/file.txt", "safe")
            stage.unzip_checked(archive, root / "fine")
            self.assertEqual((root / "fine/root/file.txt").read_text(), "safe")

    def test_tar_rejects_symlinks_and_extra_roots(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            archive = root / "case.tgz"
            with tarfile.open(archive, "w:gz") as t:
                link = tarfile.TarInfo("package/redirect")
                link.type = tarfile.SYMTYPE
                link.linkname = "../../outside"
                t.addfile(link)
            with self.assertRaises(ValueError):
                stage.untar_checked(archive, root / "linked")
            with tarfile.open(archive, "w:gz") as t:
                file = tarfile.TarInfo("other/path")
                file.size = 4
                t.addfile(file, io.BytesIO(b"safe"))
            with self.assertRaises(ValueError):
                stage.untar_checked(archive, root / "bad")

    def test_7zip_official_full_sfx_pe_amd64_and_paired_dll_policy(self):
        plan = json.loads((ROOT / "tool/full-stable-upgrade-plan.json").read_text(
            encoding="utf-8"))
        seven = next(x for x in plan["targets"] if x["name"] == "7zip")
        self.assertEqual(seven["artifact"]["url"],
                         "https://github.com/ip7z/7zip/releases/download/26.05/7z2605-x64.exe")
        self.assertEqual(seven["artifact"]["sha256"],
                         "fd99e86f57d8f429ef5ed045bf98315af962e2309b0f1ba87a147a44c71647d0")
        code = (ROOT / "tool/full-stable-prepare.py").read_text(encoding="utf-8")
        self.assertIn("run(old_exe, \"x\",", code)
        self.assertNotIn("run(archive,", code)
        self.assertIn('chosen["7z.exe"].parent == chosen["7z.dll"].parent', code)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "candidate.exe"
            def pe(machine):
                data = bytearray(320)
                data[0:2] = b"MZ"
                data[0x3c:0x40] = (0x90).to_bytes(4, "little")
                data[0x90:0x94] = b"PE\x00\x00"
                data[0x94:0x96] = machine.to_bytes(2, "little")
                return data
            path.write_bytes(pe(0x8664))
            self.assertTrue(stage.pe_amd64(path))
            path.write_bytes(pe(0x14c))
            self.assertFalse(stage.pe_amd64(path))
            path.write_bytes(pe(0xaa64))
            self.assertFalse(stage.pe_amd64(path))
            path.write_bytes(b"MZ" + b"\x00" * 5)
            self.assertFalse(stage.pe_amd64(path))

    def test_pip_upgrade_preserves_all_local_portable_wrappers(self):
        code = (ROOT / "tool/full-stable-prepare.py").read_text(encoding="utf-8")
        for name in ("pip.exe", "pip3.exe", "pip3.15.exe"):
            self.assertIn(name, code)
        self.assertIn('pip_launcher_lock.write_text(', code)
        self.assertIn('"--require-hashes", "--no-warn-script-location"', code)
        self.assertIn('TOOL / "refresh-python-cli-shims.py"', code)
        self.assertLess(code.index('vendor = pip_launch / "bin"'),
                        code.index('replace_tree(staged_python, TOOL / "python", temp)'))

    def test_writer_filenames_allow_only_owned_tool_files(self):
        for name in (".github/workflows/02.yml", "codex.exe", "tool/python/../evil",
                     "tool/bin/evil.exe", "tool/bin/other.ps1", "tool/python/x.pyc",
                     "tool/automation/browsers/../../evil", "tool/foo.json"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                transfer.checked_name(name)
        self.assertEqual(transfer.checked_name("tool/python/python315.dll"),
                         "tool/python/python315.dll")
        self.assertEqual(transfer.checked_name("tool/bin/pip3.15.cmd"),
                         "tool/bin/pip3.15.cmd")

    def test_readonly_git_patch_and_writer_reconstruct_identical_bytes(self):
        if not shutil_which_git():
            self.skipTest("Git command missing")
        paths = [
            "tool/python/python315.dll", "tool/python/python315.zip",
            "tool/node/node_modules/npm/package.json",
            "tool/node/node_modules/corepack/package.json",
            "tool/automation/versions.json", "tool/bin/7z.exe", "tool/bin/7z.dll",
            "tool/installed-tools.json", "tool/full-stable-evidence.json",
            "tool/python-packages.in.txt", "tool/工具更新说明.md"
        ]
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            subprocess.run(["git", "init", "-q", str(tmp)], check=True)
            (tmp / ".gitignore").write_text("/tmp/\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(tmp), "add", ".gitignore"], check=True)
            subprocess.run(["git", "-C", str(tmp), "-c", "user.name=test",
                            "-c", "user.email=test@example.invalid",
                            "commit", "-qm", "base"], check=True)
            base = subprocess.check_output(
                ["git", "-C", str(tmp), "rev-parse", "HEAD"], text=True).strip()
            for i, path in enumerate(paths):
                target = tmp / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(("payload " + str(i) + "\n").encode("utf-8"))
            subprocess.run(["git", "-C", str(tmp), "add", "-A", "--", "tool"],
                           check=True)
            (tmp / "tmp").mkdir()
            archive = tmp / "tmp/candidate.zip"
            with patch.object(transfer, "ROOT", tmp):
                transfer.pack(archive, base)
                archived_sha = transfer.digest_file(archive)
                diff = transfer.diff_sha()
                subprocess.run(["git", "-C", str(tmp), "reset", "--hard", "HEAD"],
                               check=True, capture_output=True)
                transfer.apply(archive, archived_sha, diff, base)
                self.assertEqual(transfer.diff_sha(), diff)
                self.assertEqual(len(transfer.changes()), len(paths))
                archive.touch()
                with self.assertRaisesRegex(ValueError, "differs"):
                    transfer.apply(archive, "0" * 64, diff, base)

    def test_repository_contains_no_automatic_full_upgrade_trigger(self):
        source = (ROOT / ".github/workflows/03-update-tools.yml").read_text(
            encoding="utf-8")
        self.assertTrue(source.startswith('name: "03 -'))
        self.assertIn("\non:\n  workflow_dispatch:\n", source)
        for event in ("\n  push:", "\n  schedule:", "\n  pull_request:",
                      "\n  workflow_run:"):
            self.assertNotIn(event, source)


def shutil_which_git() -> bool:
    import shutil
    return shutil.which("git") is not None


if __name__ == "__main__":
    unittest.main()
