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
        command.write_bytes(b"Preserve existing synthetic command.")
        scratch = self.root / "tmp"
        scratch.mkdir()
        sentinel = scratch / "unrelated.txt"
        sentinel.write_bytes(b"Preserve unrelated synthetic data.")
        with mock.patch.object(self.module.os, "replace", side_effect=OSError("Synthetic failure")):
            with self.assertRaises(OSError):
                self.run_refresh()
        self.assertEqual(command.read_bytes(), b"Preserve existing synthetic command.")
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


if __name__ == "__main__":
    unittest.main()
