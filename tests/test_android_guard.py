"""Exercise the Android analysis helpers without devices or real APKs."""
import importlib.util
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).absolute().parents[1]
SCRIPTS = Path("home/plugins/android-apk-lab/skills/android-reverse-engineering/scripts")


class AndroidGuardTests(unittest.TestCase):
    def setUp(self):
        for ancestor in (*reversed(ROOT.parents), ROOT):
            info = ancestor.lstat()
            self.assertFalse(stat.S_ISLNK(info.st_mode))
            self.assertFalse(getattr(info, "st_file_attributes", 0) & 0x400)
        scratch = ROOT / "tmp"
        if scratch.exists() or scratch.is_symlink():
            info = scratch.lstat()
            self.assertTrue(stat.S_ISDIR(info.st_mode))
            self.assertFalse(getattr(info, "st_file_attributes", 0) & 0x400)
        scratch.mkdir(exist_ok=True)
        fixture = tempfile.TemporaryDirectory(prefix="android-guard-", dir=scratch)
        self.addCleanup(fixture.cleanup)
        self.base = Path(fixture.name)
        self.package = self.base / "当前 Package"
        self.old = self.base / "旧 Package"
        for root in (self.package, self.old):
            root.mkdir()
            for marker in ("codex.exe", "env.ps1"):
                (root / marker).write_bytes(b"synthetic marker")
        (self.package / SCRIPTS).mkdir(parents=True)
        self.guard_path = self.package / SCRIPTS / "portable_guard.py"
        shutil.copyfile(ROOT / SCRIPTS / "portable_guard.py", self.guard_path)
        self.script = self.package / SCRIPTS / "fingerprint.py"
        self.script.write_text("# synthetic caller\n")
        spec = importlib.util.spec_from_file_location("android_guard_fixture", self.guard_path)
        self.guard = importlib.util.module_from_spec(spec)
        with mock.patch.object(sys, "dont_write_bytecode", True):
            spec.loader.exec_module(self.guard)

    def symlink(self, target, link, *, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"Symlink creation unavailable: {error}")

    def test_actual_move_ignores_old_package_and_unrelated_cwd(self):
        moved = self.base / "再次移动 New Location"
        self.package.rename(moved)
        previous_cwd = Path.cwd()
        try:
            os.chdir(self.old)
            with mock.patch.dict(os.environ, {"CODEX_INSTALL_DIR": str(self.old)}):
                self.assertEqual(
                    self.guard.find_portable_root(moved / SCRIPTS / "fingerprint.py"), moved
                )
                result = self.guard.atomic_write_text(moved, moved / "work/result.txt", "result")
                self.assertEqual(result.read_text(), "result")
        finally:
            os.chdir(previous_cwd)
        self.assertFalse((self.old / "work").exists())

    def test_ancestor_link_is_rejected_before_marker_probe(self):
        alias = self.base / "alias"
        self.symlink(self.base, alias, directory=True)
        with mock.patch.object(Path, "is_file", side_effect=AssertionError("Marker queried first")):
            with self.assertRaises(self.guard.PortablePathError):
                self.guard.find_portable_root(alias / self.package.name / SCRIPTS / "fingerprint.py")

    def test_linked_markers_and_missing_package_do_not_fall_back(self):
        marker = self.package / "env.ps1"
        marker.unlink()
        with mock.patch.dict(os.environ, {"CODEX_INSTALL_DIR": str(self.old)}):
            with self.assertRaises(self.guard.PortablePathError):
                self.guard.find_portable_root(self.script)
        self.symlink(self.old / "env.ps1", marker)
        with self.assertRaises(self.guard.PortablePathError):
            self.guard.find_portable_root(self.script)
        marker.unlink()
        try:
            os.link(self.old / "env.ps1", marker)
        except OSError as error:
            self.skipTest(f"Hard link creation unavailable: {error}")
        with self.assertRaises(self.guard.PortablePathError):
            self.guard.find_portable_root(self.script)

    def test_dangling_link_is_rejected_before_resolution(self):
        link = self.package / "work"
        self.symlink(self.base / "missing", link, directory=True)
        with mock.patch.object(Path, "resolve", side_effect=AssertionError("Link target resolved")):
            with self.assertRaises(self.guard.PortablePathError):
                self.guard.resolve_inside(self.package, link / "result.txt", must_exist=False)
        self.assertFalse((self.base / "missing").exists())

    def test_outside_and_parent_traversal_rejected_before_metadata(self):
        paths = (self.old / "env.ps1", self.package / ".." / self.old.name / "env.ps1")
        for path in paths:
            with self.subTest(path=path):
                with mock.patch.object(self.guard, "is_reparse",
                                       side_effect=AssertionError("Metadata queried before boundary")):
                    with self.assertRaises(self.guard.PortablePathError):
                        self.guard.resolve_inside(self.package, path)

    def test_scanner_rejects_link_without_traversing_target(self):
        source = self.package / "work"
        source.mkdir()
        self.symlink(self.old, source / "linked", directory=True)
        with self.assertRaises(self.guard.PortablePathError):
            self.guard.ensure_tree_has_no_reparse(self.package, source)
        self.assertEqual(sorted(path.name for path in self.old.iterdir()),
                         ["codex.exe", "env.ps1"])


if __name__ == "__main__":
    unittest.main()
