"""Exercise real bundled helpers using isolated package copies inside repo/tmp."""
import contextlib
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
HELPERS = tuple(
    f"home/skills/{skill}/scripts/office/{name}"
    for skill in ("docx", "pptx", "xlsx")
    for name in ("helpers/__init__.py", "soffice.py")
) + ("home/skills/pdf/scripts/portable_safety.py",)


class HelperRelocationTests(unittest.TestCase):
    def setUp(self):
        # Preserve the lexical checkout path until every ancestor is checked;
        # resolving it first would hide an alias before we create fixture files.
        for entry in (*reversed(ROOT.parents), ROOT):
            info = entry.lstat()
            self.assertFalse(stat.S_ISLNK(info.st_mode), f"Linked checkout ancestor: {entry}")
            self.assertFalse(getattr(info, "st_file_attributes", 0) & 0x400,
                             f"Reparse-point checkout ancestor: {entry}")
        scratch = ROOT / "tmp"
        self.assertFalse(scratch.is_symlink())
        if getattr(scratch, "is_junction", lambda: False)():
            self.fail("Repository tmp must not be a junction")
        scratch.mkdir(exist_ok=True)
        self.fixture = tempfile.TemporaryDirectory(prefix="helper-relocation-", dir=scratch)
        self.addCleanup(self.fixture.cleanup)
        self.base = Path(self.fixture.name)
        self.old = self.base / "旧目录 Old Package"
        self.new = self.base / "新目录 New Package"
        for package in (self.old, self.new):
            package.mkdir()
            for marker in ("codex.exe", "env.ps1"):
                (package / marker).write_bytes(b"synthetic test marker")
            for relative in HELPERS:
                target = package / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)

    def load_helper(self, relative, package=None):
        path = (package or self.new) / relative
        spec = importlib.util.spec_from_file_location("relocation_test_helper", path)
        module = importlib.util.module_from_spec(spec)
        # No bytecode or imported test helper state may escape this fixture.
        with mock.patch.object(sys, "dont_write_bytecode", True):
            spec.loader.exec_module(module)
        return module

    @staticmethod
    def root_function(module):
        return getattr(module, "portable_root", None) or module._portable_root

    @staticmethod
    def error_type(module):
        return FileNotFoundError if hasattr(module, "_portable_root") else RuntimeError

    @contextlib.contextmanager
    def forbid_path_reads(self, forbidden):
        """Catch metadata access as well as reads of an inherited/outside root."""
        with contextlib.ExitStack() as stack:
            for name in ("exists", "is_file", "is_dir", "stat", "lstat", "open"):
                original = getattr(Path, name)

                def guarded(path, *args, _original=original, **kwargs):
                    if Path(os.path.normpath(path)).is_relative_to(forbidden):
                        raise AssertionError(f"Unexpected access outside active package: {path}")
                    return _original(path, *args, **kwargs)

                stack.enter_context(mock.patch.object(Path, name, guarded))
            yield

    def symlink(self, target, link, *, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Symlink creation is unavailable: {exc}")

    def test_current_script_wins_over_old_missing_or_unset_root(self):
        for relative in HELPERS:
            module = self.load_helper(relative)
            get_root = self.root_function(module)
            for inherited in (str(self.old), str(self.base / "nonexistent"), None):
                with self.subTest(helper=relative, inherited=inherited):
                    with mock.patch.dict(os.environ):
                        if inherited is None:
                            os.environ.pop("CODEX_INSTALL_DIR", None)
                        else:
                            os.environ["CODEX_INSTALL_DIR"] = inherited
                        with self.forbid_path_reads(self.old):
                            self.assertEqual(get_root(), self.new)

    def test_real_move_uses_new_directory_without_environment_changes(self):
        moved = self.base / "再次移动 Another Location"
        self.new.rename(moved)
        with mock.patch.dict(os.environ, {"CODEX_INSTALL_DIR": str(self.new)}):
            for relative in HELPERS:
                with self.subTest(helper=relative):
                    module = self.load_helper(relative, moved)
                    self.assertEqual(self.root_function(module)(), moved)

    def test_temp_and_output_creation_stay_in_current_copy(self):
        with mock.patch.dict(os.environ, {"CODEX_INSTALL_DIR": str(self.old)}):
            for relative in HELPERS:
                module = self.load_helper(relative)
                with self.subTest(helper=relative), self.forbid_path_reads(self.old):
                    if hasattr(module, "portable_temp_dir"):
                        output = module.portable_temp_dir()
                    elif hasattr(module, "_portable_temp_dir"):
                        output = module._portable_temp_dir()
                    else:
                        output = module.prepare_output_dir(self.new / "work" / "pdf-output")
                    self.assertTrue(output.is_relative_to(self.new))
                    self.assertTrue(output.is_dir())
        self.assertFalse((self.old / "tmp").exists())
        self.assertFalse((self.old / "work").exists())

    def test_outside_and_parent_traversal_fail_before_outside_metadata(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "tool.exe").write_bytes(b"test")
        for relative in HELPERS:
            module = self.load_helper(relative)
            with self.subTest(helper=relative), self.forbid_path_reads(outside):
                if hasattr(module, "_portable_tool"):
                    resolve = module._portable_tool
                    paths = (str(outside / "tool.exe"), "../outside/tool.exe")
                else:
                    resolve = getattr(module, "resolve_portable_path", None) or module.resolve_inside
                    paths = (outside / "tool.exe", self.new / ".." / "outside" / "tool.exe")
                for path in paths:
                    with self.assertRaises(self.error_type(module)):
                        resolve(path)

    def test_missing_root_markers_fail_instead_of_falling_back(self):
        (self.new / "env.ps1").unlink()
        with mock.patch.dict(os.environ, {"CODEX_INSTALL_DIR": str(self.old)}):
            for relative in HELPERS:
                with self.subTest(helper=relative), self.forbid_path_reads(self.old):
                    module = self.load_helper(relative)
                    with self.assertRaises(self.error_type(module)):
                        self.root_function(module)()

    def test_marker_files_cannot_be_symlinks_or_hardlinks(self):
        marker = self.new / "env.ps1"
        marker.unlink()
        self.symlink(self.old / "env.ps1", marker)
        for relative in HELPERS:
            module = self.load_helper(relative)
            with self.subTest(helper=relative, kind="symlink"):
                with self.assertRaises(self.error_type(module)):
                    self.root_function(module)()
        marker.unlink()
        os.link(self.old / "env.ps1", marker)
        for relative in HELPERS:
            module = self.load_helper(relative)
            with self.subTest(helper=relative, kind="hardlink"):
                with self.assertRaises(self.error_type(module)):
                    self.root_function(module)()

    def test_package_ancestor_symlinks_are_rejected(self):
        alias = self.base / "linked-parent"
        self.symlink(self.base, alias, directory=True)
        for relative in HELPERS:
            with self.subTest(helper=relative):
                module = self.load_helper(relative, alias / self.new.name)
                with self.assertRaises(self.error_type(module)):
                    self.root_function(module)()

    def test_output_links_and_dangling_links_are_rejected(self):
        outside = self.base / "outside"
        outside.mkdir()
        for target in (outside, self.base / "missing-target"):
            link = self.new / "tmp"
            self.symlink(target, link, directory=True)
            try:
                for relative in HELPERS:
                    module = self.load_helper(relative)
                    with self.subTest(helper=relative, target=target):
                        original_stat = Path.stat

                        def no_follow_link(path, *args, **kwargs):
                            if path == link and kwargs.get("follow_symlinks", True):
                                raise AssertionError("Link target was queried before rejecting it")
                            return original_stat(path, *args, **kwargs)

                        with mock.patch.object(Path, "stat", no_follow_link), self.assertRaises(self.error_type(module)):
                            if hasattr(module, "_portable_temp_dir"):
                                module._portable_temp_dir()
                            elif hasattr(module, "resolve_portable_path"):
                                module.portable_temp_dir()
                            else:
                                module.prepare_output_file(link / "pdf" / "result.pdf")
            finally:
                link.unlink()
        self.assertEqual(list(outside.iterdir()), [])

    def test_office_temporary_category_cannot_escape_package(self):
        outside = self.base / "outside"
        for relative in HELPERS:
            module = self.load_helper(relative)
            if not hasattr(module, "portable_temp_dir"):
                continue
            for category in (str(outside), "../../outside"):
                with self.subTest(helper=relative, category=category), self.forbid_path_reads(outside):
                    with self.assertRaises(RuntimeError):
                        module.portable_temp_dir(category)
        self.assertFalse(outside.exists())

    def test_helpers_outside_known_layout_cannot_claim_a_package(self):
        for index, relative in enumerate(HELPERS):
            detached = self.base / f"detached_{index}.py"
            shutil.copyfile(ROOT / relative, detached)
            with self.subTest(helper=relative):
                module = self.load_helper(detached.name, self.base)
                with self.assertRaises(self.error_type(module)):
                    self.root_function(module)()

    def test_office_copies_stay_identical(self):
        for name in ("helpers/__init__.py", "soffice.py"):
            expected = (ROOT / "home/skills/docx/scripts/office" / name).read_bytes()
            for skill in ("pptx", "xlsx"):
                with self.subTest(file=name, skill=skill):
                    self.assertEqual(
                        (ROOT / "home/skills" / skill / "scripts/office" / name).read_bytes(),
                        expected,
                    )

    def test_office_child_state_paths_are_relocated_and_host_values_removed(self):
        state_variables = (
            "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
            "ALLUSERSPROFILE", "PUBLIC", "XDG_CACHE_HOME", "XDG_CONFIG_HOME",
            "XDG_DATA_HOME", "XDG_STATE_HOME", "TEMP", "TMP", "TMPDIR",
        )
        inherited = {key: str(self.old / key) for key in state_variables}
        inherited["CODEX_INSTALL_DIR"] = str(self.old)
        inherited["OPENAI_API_KEY"] = "synthetic-test-only"
        for relative in HELPERS:
            module = self.load_helper(relative)
            builder = getattr(module, "portable_subprocess_env", None) or \
                getattr(module, "get_soffice_env", None)
            if builder is None:
                continue
            with self.subTest(helper=relative), mock.patch.dict(os.environ, inherited), \
                    self.forbid_path_reads(self.old):
                child = builder()
                for key in state_variables:
                    self.assertTrue(Path(child[key]).is_relative_to(self.new), key)
                self.assertNotIn("OPENAI_API_KEY", child)

    def test_office_child_state_links_rejected_before_temp_creation(self):
        for relative in HELPERS:
            module = self.load_helper(relative)
            builder = getattr(module, "portable_subprocess_env", None) or \
                getattr(module, "get_soffice_env", None)
            if builder is None:
                continue
            for name in ("home-runtime", "appdata", "localappdata"):
                link = self.new / name
                self.symlink(self.old, link, directory=True)
                try:
                    with self.subTest(helper=relative, state=name):
                        with self.assertRaises(self.error_type(module)):
                            builder()
                        self.assertFalse((self.new / "tmp").exists())
                finally:
                    link.unlink()


if __name__ == "__main__":
    unittest.main()
