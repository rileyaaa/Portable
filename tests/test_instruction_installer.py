"""Exercise the instruction helper with owned, synthetic package fixtures only."""
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
HELPER = ROOT / "tool/codex-instruct.py"


class InstructionInstallerTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "tmp"
        for entry in (*reversed(scratch.parents), scratch):
            if entry.is_symlink() or (entry.exists() and getattr(entry.lstat(), "st_file_attributes", 0) & 0x400):
                raise RuntimeError("Unsafe test scratch ancestor")
        scratch.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="instruction-install-", dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "original package"
        (self.root / "tool").mkdir(parents=True)
        shutil.copyfile(HELPER, self.root / "tool/codex-instruct.py")
        (self.root / "codex.exe").write_bytes(b"synthetic marker, never executed")
        (self.root / "env.ps1").write_text("# synthetic marker\n", encoding="utf-8")
        (self.root / "input.md").write_text("Synthetic instructions only.\n", encoding="utf-8")

    def load(self, root=None, script=None):
        script = script or (root or self.root) / "tool/codex-instruct.py"
        spec = importlib.util.spec_from_file_location("synthetic_instruction_installer", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def run_main(self, module, *arguments):
        with mock.patch("sys.argv", [str(HELPER), "--file", "input.md", "--name", "synthetic", *arguments]), \
                mock.patch.dict(os.environ, {"CODEX_HOME": str(Path(module.__file__).parents[1] / "home")}), \
                contextlib.redirect_stdout(io.StringIO()):
            return module.main()

    def symlink(self, source, destination, directory=False):
        try:
            destination.symlink_to(source, target_is_directory=directory)
        except (NotImplementedError, OSError) as error:
            self.skipTest("Symlink fixture unavailable: " + type(error).__name__)

    def test_ordinary_dry_run_creates_no_state(self):
        module = self.load()
        self.assertEqual(module.package_root(), self.root)
        self.assertEqual(self.run_main(module, "--dry-run"), 0)
        self.assertFalse((self.root / "home").exists())
        self.assertFalse((self.root / "env.local.ps1").exists())

    def test_install_preserves_other_synthetic_settings(self):
        local = self.root / "env.local.ps1"
        local.write_text("$env:SYNTHETIC_SETTING = 'preserved'\n", encoding="utf-8")
        self.assertEqual(self.run_main(self.load()), 0)
        self.assertEqual((self.root / "home/synthetic.md").read_text(), "Synthetic instructions only.\n")
        saved = local.read_text(encoding="utf-8-sig")
        self.assertIn("$env:SYNTHETIC_SETTING = 'preserved'", saved)
        self.assertIn("$env:CODEX_MODEL_INSTRUCTIONS_FILE = 'synthetic.md'", saved)
        self.assertFalse(list(self.root.rglob(".codex-instruct-*.tmp")))

    def test_actual_relocation_uses_current_entry_not_old_root_or_cwd(self):
        old = self.root
        moved = self.base / "\u642c\u8fc1 renamed package"
        self.root.rename(moved)
        old.mkdir()
        sentinel = old / "env.local.ps1"
        sentinel.write_text("SENTINEL - do not read or overwrite", encoding="utf-8")
        with mock.patch.dict(os.environ, {"CODEX_INSTALL_DIR": str(old)}):
            module = self.load(root=moved)
            self.assertEqual(module.package_root(), moved)
            self.assertEqual(self.run_main(module), 0)
        self.assertTrue((moved / "home/synthetic.md").is_file())
        self.assertEqual(sentinel.read_text(), "SENTINEL - do not read or overwrite")
        self.assertFalse((old / "home").exists())

    def test_linked_ancestor_rejected_before_marker_probe(self):
        alias = self.base / "linked parent"
        self.symlink(self.base, alias, directory=True)
        module = self.load(root=alias / self.root.name)
        inspected = []
        original = module._is_reparse
        def record(path):
            inspected.append(path)
            return original(path)
        with mock.patch.object(module, "_is_reparse", side_effect=record):
            with self.assertRaises(SystemExit):
                module.package_root()
        self.assertIn(alias, inspected)
        self.assertFalse(any(path.name in ("codex.exe", "env.ps1") for path in inspected))
        self.assertFalse((self.root / "env.local.ps1").exists())

    def test_linked_root_and_tool_directory_are_rejected(self):
        alias = self.base / "linked package"
        self.symlink(self.root, alias, directory=True)
        with self.assertRaises(SystemExit):
            self.load(root=alias).package_root()
        real_tool = self.root / "real-tool"
        (self.root / "tool").rename(real_tool)
        self.symlink(real_tool, self.root / "tool", directory=True)
        with self.assertRaises(SystemExit):
            self.load().package_root()

    def test_linked_helper_is_rejected(self):
        actual = self.root / "tool/original.py"
        (self.root / "tool/codex-instruct.py").rename(actual)
        self.symlink(actual, self.root / "tool/codex-instruct.py")
        with self.assertRaises(SystemExit):
            self.load().package_root()

    def test_hardlinked_helper_is_rejected(self):
        os.link(self.root / "tool/codex-instruct.py", self.base / "helper-copy.py")
        with self.assertRaises(SystemExit):
            self.load().package_root()

    def test_linked_and_hardlinked_markers_are_rejected(self):
        for name in ("codex.exe", "env.ps1"):
            with self.subTest(name=name):
                marker = self.root / name
                backup = self.base / (name + ".original")
                marker.rename(backup)
                self.symlink(backup, marker)
                with self.assertRaises(SystemExit):
                    self.load().package_root()
                marker.unlink()
                os.link(backup, marker)
                with self.assertRaises(SystemExit):
                    self.load().package_root()
                marker.unlink()
                backup.rename(marker)

    def test_missing_marker_is_rejected_without_state(self):
        (self.root / "codex.exe").unlink()
        with self.assertRaises(SystemExit):
            self.run_main(self.load())
        self.assertFalse((self.root / "home").exists())

    def test_custom_package_home_persists_correct_relative_path(self):
        self.assertEqual(self.run_main(self.load(), "--codex-dir", "alternate home"), 0)
        self.assertTrue((self.root / "alternate home/synthetic.md").is_file())
        saved = (self.root / "env.local.ps1").read_text(encoding="utf-8-sig")
        expected = os.path.relpath(self.root / "alternate home/synthetic.md", self.root / "home")
        self.assertIn("$env:CODEX_MODEL_INSTRUCTIONS_FILE = '" + expected + "'", saved)

    def test_existing_input_hardlink_rejection_is_preserved(self):
        os.link(self.root / "input.md", self.base / "input-copy.md")
        with self.assertRaises(SystemExit):
            self.run_main(self.load())
        self.assertFalse((self.root / "home").exists())


if __name__ == "__main__":
    unittest.main()
