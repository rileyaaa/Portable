"""Refresh shims only in owned synthetic packages; never execute vendor binaries."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).absolute().parents[1]
SOURCE = ROOT / "tool/refresh-python-cli-shims.py"


class PythonCliShimTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "tmp"
        for path in (*reversed(scratch.parents), scratch):
            if path.is_symlink() or (path.exists() and getattr(path.lstat(), "st_file_attributes", 0) & 0x400):
                raise RuntimeError("Unsafe test scratch ancestor")
        scratch.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="python-shims-", dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "synthetic package"
        self.tool = self.root / "tool"
        self.output = self.tool / "bin"
        self.vendor = self.tool / "python/Lib/site-packages/bin"
        self.output.mkdir(parents=True)
        self.vendor.mkdir(parents=True)
        shutil.copyfile(SOURCE, self.tool / SOURCE.name)
        (self.output / "portable-python-cli.py").write_text("# Synthetic helper; never executed.\n", encoding="utf-8")
        self.module = self.load(self.root)

    def load(self, root):
        spec = importlib.util.spec_from_file_location("synthetic_python_shims", root / "tool" / SOURCE.name)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def run_refresh(self, module=None):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return (module or self.module).main()

    def add_vendor(self, name="synthetic", metadata=True):
        (self.vendor / (name + ".exe")).write_bytes(b"Synthetic marker; never executed.")
        if metadata:
            info = self.vendor.parent / (name + "-1.0.dist-info")
            info.mkdir(exist_ok=True)
            (info / "entry_points.txt").write_text("[console_scripts]\n" + name + " = synthetic_module:main\n", encoding="utf-8")

    def symlink(self, target, link, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (NotImplementedError, OSError) as error:
            self.skipTest("Symlink fixture unavailable: " + type(error).__name__)

    def test_refresh_keeps_exact_generated_command_bytes(self):
        self.add_vendor()
        self.assertEqual(self.run_refresh(), 0)
        data = (self.output / "synthetic.cmd").read_bytes()
        self.assertEqual(data, self.module.render_cmd("synthetic"))
        data.decode("ascii")
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""))

    def test_user_command_mentioning_helper_is_preserved(self):
        command = self.output / "my-user-command.cmd"
        original = b"@echo off\r\nrem See portable-python-cli.py for conventions.\r\necho User command\r\n"
        command.write_bytes(original)
        self.assertEqual(self.run_refresh(), 0)
        self.assertTrue(command.exists(), "Unrelated user command was deleted")
        self.assertEqual(command.read_bytes(), original)

    def test_user_modified_generated_command_is_preserved(self):
        command = self.output / "obsolete.cmd"
        original = self.module.render_cmd("obsolete") + b"rem User custom addition\r\n"
        command.write_bytes(original)
        self.assertEqual(self.run_refresh(), 0)
        self.assertTrue(command.exists(), "User-modified command was deleted")
        self.assertEqual(command.read_bytes(), original)

    def test_exact_unmodified_obsolete_generated_command_is_removed(self):
        command = self.output / "obsolete.cmd"
        command.write_bytes(self.module.render_cmd("obsolete"))
        self.assertEqual(self.run_refresh(), 0)
        self.assertFalse(command.exists())

    def test_exact_obsolete_pip_alias_is_removed(self):
        command = self.output / "pip3.11.cmd"
        command.write_bytes(self.module.render_cmd("pip"))
        self.assertEqual(self.run_refresh(), 0)
        self.assertFalse(command.exists())

    def test_existing_unresolved_vendor_command_is_preserved(self):
        self.add_vendor(metadata=False)
        command = self.output / "synthetic.cmd"
        original = self.module.render_cmd("synthetic")
        command.write_bytes(original)
        self.assertEqual(self.run_refresh(), 3)
        self.assertTrue(command.exists(), "Current unresolved launcher was pruned")
        self.assertEqual(command.read_bytes(), original)

    def test_atomic_staging_uses_only_package_tmp(self):
        self.add_vendor()
        staged = []
        original = os.replace
        def capture(source, destination):
            staged.append(Path(source))
            self.assertEqual(Path(source).parent, self.root / "tmp")
            return original(source, destination)
        with mock.patch.object(self.module.os, "replace", side_effect=capture):
            self.assertEqual(self.run_refresh(), 0)
        self.assertEqual(len(staged), 1)
        self.assertEqual(list((self.root / "tmp").iterdir()), [])

    def test_failed_replace_preserves_destination_and_unrelated_tmp(self):
        self.add_vendor()
        command = self.output / "synthetic.cmd"
        command.write_bytes(self.module.render_cmd("synthetic"))
        scratch = self.root / "tmp"
        scratch.mkdir()
        sentinel = scratch / "unrelated.txt"
        sentinel.write_bytes(b"Preserve unrelated synthetic data.")
        with mock.patch.object(self.module.os, "replace", side_effect=OSError("Synthetic failure")):
            with self.assertRaises(OSError):
                self.run_refresh()
        self.assertEqual(command.read_bytes(), self.module.render_cmd("synthetic"))
        self.assertEqual(list(scratch.iterdir()), [sentinel])
        self.assertFalse(list(self.output.glob("*.tmp")))

    def test_linked_tmp_is_rejected_before_any_command_write(self):
        self.add_vendor()
        outside = self.base / "outside sentinel"
        outside.mkdir()
        self.symlink(outside, self.root / "tmp", directory=True)
        with self.assertRaises(RuntimeError):
            self.run_refresh()
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.output / "synthetic.cmd").exists())

    def test_hardlinked_output_is_rejected_and_alias_unchanged(self):
        self.add_vendor()
        command = self.output / "synthetic.cmd"
        command.write_bytes(b"Synthetic existing command.")
        alias = self.base / "command-alias.cmd"
        os.link(command, alias)
        with self.assertRaises(RuntimeError):
            self.run_refresh()
        self.assertEqual(command.read_bytes(), b"Synthetic existing command.")
        self.assertEqual(alias.read_bytes(), b"Synthetic existing command.")

    def assert_linked_ancestor_rejected_before_descendant_probe(self, module, alias):
        inspected = []
        original = os.lstat

        def record(path, *args, **kwargs):
            inspected.append(Path(os.path.abspath(os.fspath(path))))
            return original(path, *args, **kwargs)

        with mock.patch.object(module.os, "lstat", side_effect=record):
            with self.assertRaises(RuntimeError):
                module._require_plain_dir(module.OUT_BIN)
        self.assertIn(alias, inspected)
        self.assertFalse(any(alias in path.parents for path in inspected),
                         "Inspected a descendant through a linked package ancestor")
        self.assertFalse((self.root / "tmp").exists())
        self.assertEqual(list(self.output.glob("*.cmd")), [])

    def test_linked_package_parent_rejected_before_descendant_probe(self):
        alias = self.base / "linked parent"
        self.symlink(self.base, alias, directory=True)
        module = self.load(alias / self.root.name)
        self.assert_linked_ancestor_rejected_before_descendant_probe(module, alias)

    def test_linked_package_grandparent_rejected_before_descendant_probe(self):
        alias = self.base / "linked grandparent"
        self.symlink(self.base, alias, directory=True)
        nested = self.base / "nested" / self.root.name
        nested.parent.mkdir()
        self.root.rename(nested)
        self.root = nested
        self.output = nested / "tool/bin"
        module = self.load(alias / "nested" / nested.name)
        self.assert_linked_ancestor_rejected_before_descendant_probe(module, alias)

    def test_actual_relocation_ignores_stale_root_environment(self):
        self.add_vendor()
        old = self.root
        moved = self.base / "\u642c\u8fc1 package with spaces"
        self.root.rename(moved)
        old.mkdir()
        sentinel = old / "sentinel.txt"
        sentinel.write_bytes(b"Preserve old package.")
        with mock.patch.dict(os.environ, {"CODEX_INSTALL_DIR": str(old)}):
            module = self.load(moved)
            self.assertEqual(self.run_refresh(module), 0)
        self.assertTrue((moved / "tool/bin/synthetic.cmd").is_file())
        self.assertEqual(list(old.iterdir()), [sentinel])


    def test_refresh_preserves_same_name_user_command(self):
        self.add_vendor()
        command = self.output / "synthetic.cmd"
        original = b"@echo off\r\necho User-owned command\r\n"
        command.write_bytes(original)
        status = self.run_refresh()
        self.assertEqual(command.read_bytes(), original)
        self.assertEqual(status, 3)
        self.assertFalse((self.root / "tmp").exists())

    def test_refresh_preserves_same_name_modified_generated_command(self):
        self.add_vendor()
        command = self.output / "synthetic.cmd"
        original = self.module.render_cmd("synthetic") + b"rem User customization\r\n"
        command.write_bytes(original)
        status = self.run_refresh()
        self.assertEqual(command.read_bytes(), original)
        self.assertEqual(status, 3)

    def test_refresh_preserves_user_pip_alias(self):
        self.add_vendor("pip")
        self.add_vendor("pip3.11", metadata=False)
        command = self.output / "pip3.11.cmd"
        original = b"@echo off\r\necho Custom pip settings\r\n"
        command.write_bytes(original)
        status = self.run_refresh()
        self.assertEqual(command.read_bytes(), original)
        self.assertEqual(status, 3)
        self.assertEqual((self.output / "pip.cmd").read_bytes(), self.module.render_cmd("pip"))

    def test_owned_current_command_can_still_be_refreshed(self):
        self.add_vendor()
        command = self.output / "synthetic.cmd"
        original = self.module.render_cmd("synthetic")
        command.write_bytes(original)
        self.assertEqual(self.run_refresh(), 0)
        self.assertEqual(command.read_bytes(), original)

    def test_unowned_command_does_not_prevent_other_refreshes(self):
        self.add_vendor("alpha")
        self.add_vendor("zeta")
        command = self.output / "alpha.cmd"
        original = b"@echo off\r\nrem portable-python-cli.py is not proof of ownership\r\n"
        command.write_bytes(original)
        status = self.run_refresh()
        self.assertEqual(command.read_bytes(), original)
        self.assertEqual((self.output / "zeta.cmd").read_bytes(), self.module.render_cmd("zeta"))
        self.assertEqual(status, 3)

    def test_command_edited_during_staging_is_preserved(self):
        self.add_vendor()
        command = self.output / "synthetic.cmd"
        command.write_bytes(self.module.render_cmd("synthetic"))
        edited = b"@echo off\r\necho Concurrent synthetic customization\r\n"
        fsync = self.module.os.fsync
        def edit(fd):
            fsync(fd)
            command.write_bytes(edited)
        with mock.patch.object(self.module.os, "fsync", side_effect=edit):
            status = self.run_refresh()
        self.assertEqual(command.read_bytes(), edited)
        self.assertEqual(status, 3)
        self.assertEqual(list((self.root / "tmp").iterdir()), [])

    def test_command_created_during_staging_is_preserved(self):
        self.add_vendor()
        command = self.output / "synthetic.cmd"
        created = b"@echo off\r\necho Newly created user command\r\n"
        fsync = self.module.os.fsync
        def create(fd):
            fsync(fd)
            command.write_bytes(created)
        with mock.patch.object(self.module.os, "fsync", side_effect=create):
            status = self.run_refresh()
        self.assertEqual(command.read_bytes(), created)
        self.assertEqual(status, 3)
        self.assertEqual(list((self.root / "tmp").iterdir()), [])

    def test_unreadable_current_command_is_not_overwritten(self):
        self.add_vendor()
        command = self.output / "synthetic.cmd"
        original = self.module.render_cmd("synthetic")
        command.write_bytes(original)
        read_bytes = Path.read_bytes
        def unreadable(path):
            if path == command:
                raise PermissionError("Synthetic command read failure")
            return read_bytes(path)
        with mock.patch.object(Path, "read_bytes", autospec=True, side_effect=unreadable):
            with self.assertRaises(PermissionError):
                self.run_refresh()
        self.assertEqual(command.read_bytes(), original)
        self.assertFalse((self.root / "tmp").exists())

    def test_read_failure_after_staging_cleans_only_owned_temp(self):
        self.add_vendor()
        command = self.output / "synthetic.cmd"
        original = self.module.render_cmd("synthetic")
        command.write_bytes(original)
        scratch = self.root / "tmp"
        scratch.mkdir()
        sentinel = scratch / "unrelated.txt"
        sentinel.write_bytes(b"Keep synthetic user data.")
        read_bytes = Path.read_bytes
        reads = 0
        def unreadable(path):
            nonlocal reads
            if path == command:
                reads += 1
                if reads == 2:
                    raise PermissionError("Synthetic post-staging read failure")
            return read_bytes(path)
        with mock.patch.object(Path, "read_bytes", autospec=True, side_effect=unreadable):
            with self.assertRaises(PermissionError):
                self.run_refresh()
        self.assertEqual(command.read_bytes(), original)
        self.assertEqual(list(scratch.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b"Keep synthetic user data.")

    def test_linked_current_command_is_rejected_without_target_changes(self):
        self.add_vendor()
        outside = self.base / "outside-command.cmd"
        outside.write_bytes(b"Keep the synthetic external command.")
        command = self.output / "synthetic.cmd"
        self.symlink(outside, command)
        with self.assertRaises(RuntimeError):
            self.run_refresh()
        self.assertTrue(command.is_symlink())
        self.assertEqual(outside.read_bytes(), b"Keep the synthetic external command.")
        self.assertFalse((self.root / "tmp").exists())

    def test_owned_pip_alias_can_change_to_explicit_entrypoint(self):
        self.add_vendor("pip3.11")
        command = self.output / "pip3.11.cmd"
        command.write_bytes(self.module.render_cmd("pip"))
        self.assertEqual(self.run_refresh(), 0)
        self.assertEqual(command.read_bytes(), self.module.render_cmd("pip3.11"))

if __name__ == "__main__":
    unittest.main()
