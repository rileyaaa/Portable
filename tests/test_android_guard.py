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

    def load_script(self, filename):
        path = self.package / SCRIPTS / filename
        shutil.copyfile(ROOT / SCRIPTS / filename, path)
        spec = importlib.util.spec_from_file_location("android_read_fixture", path)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.object(sys, "dont_write_bytecode", True), \
                mock.patch.dict(sys.modules, {"portable_guard": self.guard}):
            spec.loader.exec_module(module)
        return module

    def leaf_readers(self):
        mapping_dir = self.package / "work" / "mapping"
        mapping_dir.mkdir(parents=True)
        skill_root = (self.package / SCRIPTS).parent
        (skill_root / "references").mkdir()
        mapping = self.load_script("lookup_name.py")
        scanner = self.load_script("find_api_calls.py")
        return (
            (mapping_dir / "mapping.json", lambda: mapping.load_mapping(self.package, mapping_dir)),
            (skill_root / "references" / "third_party_hosts.txt",
             lambda: scanner.load_denylist(self.package, skill_root)),
        )

    def test_lookup_regex_keeps_repetition_and_assertion_guards(self):
        # Protect the original grep safety contract on CPython 3.14 and 3.15:
        # the deprecated sre_parse shim must not be needed to load the script.
        lookup = self.load_script("lookup_name.py")
        self.assertEqual(lookup.sre_parse.__name__, "re._parser")
        self.assertTrue(lookup._safe_regex(r"Activity\\s+[A-Za-z]+").search("Activity Main"))
        for dangerous in (r"(a+)+", r"(a*+)+", r"(?=a)b", r"(?<=a)b",
                          r"(a)\\1", r"(a|b){1,3}+{1,3}"):
            with self.subTest(pattern=dangerous):
                with self.assertRaises((ValueError, lookup.re.error)):
                    lookup._safe_regex(dangerous)
        for bad in ("", "a" * 257):
            with self.assertRaises(ValueError):
                lookup._safe_regex(bad)

    def test_derived_inputs_reject_symlinks_before_content_read(self):
        outside = self.old / "synthetic-source.txt"
        outside.write_text('{"a.b": "example.Name"}')
        for path, read in self.leaf_readers():
            with self.subTest(path=path.name):
                self.symlink(outside, path)
                with mock.patch.object(Path, "read_text", side_effect=AssertionError("Input opened")):
                    with self.assertRaises(self.guard.PortablePathError):
                        read()

    def test_derived_inputs_reject_hardlinks_before_content_read(self):
        outside = self.old / "synthetic-source.txt"
        outside.write_text('{"a.b": "example.Name"}')
        for path, read in self.leaf_readers():
            with self.subTest(path=path.name):
                try:
                    os.link(outside, path)
                except OSError as error:
                    self.skipTest(f"Hard link creation unavailable: {error}")
                with mock.patch.object(Path, "read_text", side_effect=AssertionError("Input opened")):
                    with self.assertRaises(self.guard.PortablePathError):
                        read()

    def test_derived_inputs_keep_regular_reads_and_optional_denylist(self):
        mapping, denylist = self.leaf_readers()
        mapping[0].write_text('{"a.b": "example.Name"}')
        self.assertEqual(mapping[1](), {"a.b": "example.Name"})
        self.assertEqual(denylist[1](), [])
        denylist[0].write_text("# synthetic entry\nexample\\.invalid\n")
        self.assertEqual([pattern.pattern for pattern in denylist[1]()], [r"example\.invalid"])

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


    def test_atomic_writer_stages_only_in_package_tmp(self):
        output = self.package / "work" / "report.txt"
        expected = "synthetic \u4e2d\u6587\r\nreport\n"
        with self.guard.atomic_text_writer(self.package, output, newline="") as stream:
            staged = list(self.package.rglob(".codex-write-*.tmp"))
            self.assertEqual(len(staged), 1)
            self.assertEqual(staged[0].parent, self.package / "tmp")
            self.assertFalse(output.exists())
            stream.write(expected)
        self.assertEqual(output.read_bytes(), expected.encode())
        self.assertEqual(list(self.package.rglob(".codex-write-*.tmp")), [])

    def test_atomic_writer_rejects_linked_tmp_before_output_creation(self):
        scratch = self.package / "tmp"
        self.symlink(self.old, scratch, directory=True)
        output = self.package / "work" / "report.txt"
        with mock.patch.object(self.guard.tempfile, "mkstemp",
                                       wraps=self.guard.tempfile.mkstemp) as create_temp:
            with self.assertRaises(self.guard.PortablePathError):
                self.guard.atomic_write_text(self.package, output, "replacement")
            create_temp.assert_not_called()
        self.assertFalse(output.parent.exists())
        self.assertEqual(sorted(p.name for p in self.old.iterdir()), ["codex.exe", "env.ps1"])

    def test_atomic_writer_rejects_file_tmp_before_output_creation(self):
        scratch = self.package / "tmp"
        scratch.write_bytes(b"keep")
        output = self.package / "work" / "report.txt"
        with self.assertRaises((OSError, self.guard.PortablePathError)):
            self.guard.atomic_write_text(self.package, output, "replacement")
        self.assertFalse(output.parent.exists())
        self.assertEqual(scratch.read_bytes(), b"keep")

    def test_atomic_writer_failures_preserve_output_and_unrelated_tmp(self):
        scratch = self.package / "tmp"
        scratch.mkdir()
        sentinel = scratch / "keep.txt"
        sentinel.write_bytes(b"keep")
        output = self.package / "work" / "report.txt"
        output.parent.mkdir()
        output.write_bytes(b"original")
        for failure in ("body", "replace", "encoding"):
            with self.subTest(failure=failure):
                if failure == "replace":
                    with mock.patch.object(self.guard.os, "replace", side_effect=OSError("synthetic")):
                        with self.assertRaises(OSError):
                            self.guard.atomic_write_text(self.package, output, "replacement")
                elif failure == "encoding":
                    with self.assertRaises(UnicodeEncodeError):
                        self.guard.atomic_write_text(self.package, output, chr(0xD800))
                else:
                    with self.assertRaisesRegex(RuntimeError, "synthetic"):
                        with self.guard.atomic_text_writer(self.package, output) as stream:
                            stream.write("partial")
                            raise RuntimeError("synthetic")
                self.assertEqual(output.read_bytes(), b"original")
                self.assertEqual(list(scratch.iterdir()), [sentinel])
                self.assertEqual(sentinel.read_bytes(), b"keep")
                self.assertEqual(list(output.parent.iterdir()), [output])

if __name__ == "__main__":
    unittest.main()
