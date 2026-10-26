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

    def assert_no_external_probe(self, operation, outside):
        inspected = []
        original = os.lstat
        def record(path, *args, **kwargs):
            inspected.append(os.path.abspath(os.fspath(path)))
            return original(path, *args, **kwargs)
        with mock.patch('os.lstat', side_effect=record):
            with self.assertRaises(SystemExit):
                operation()
        prefix = str(outside) + os.sep
        self.assertFalse(any(p == str(outside) or p.startswith(prefix) for p in inspected), inspected)

    def test_input_link_rejected_before_external_target_probe(self):
        outside = self.base / 'outside sentinel'
        outside.mkdir()
        (outside / 'input.md').write_text('Synthetic outside instructions.', encoding='utf-8')
        self.symlink(outside, self.root / 'linked input', directory=True)
        module = self.load()
        self.assert_no_external_probe(lambda: module.read_instructions('linked input/input.md', self.root), outside)

    def test_input_parent_traversal_rejected_before_external_probe(self):
        outside = self.base / 'outside sentinel'
        outside.mkdir()
        module = self.load()
        self.assert_no_external_probe(lambda: module.read_instructions('../outside sentinel/input.md', self.root), outside)

    def test_custom_home_link_rejected_before_external_target_probe(self):
        outside = self.base / 'outside sentinel'
        outside.mkdir()
        self.symlink(outside, self.root / 'linked home', directory=True)
        module = self.load()
        self.assert_no_external_probe(lambda: self.run_main(module, '--codex-dir', 'linked home'), outside)
        self.assertEqual(list(outside.iterdir()), [])

    def test_local_config_link_rejected_before_external_target_probe(self):
        outside = self.base / 'outside sentinel'
        outside.mkdir()
        target = outside / 'settings.ps1'
        target.write_text('# Synthetic settings only.', encoding='utf-8')
        local = self.root / 'env.local.ps1'
        self.symlink(target, local)
        module = self.load()
        self.assert_no_external_probe(lambda: module.read_utf8_ps1(local, self.root), outside)

    def test_normalized_source_is_the_path_actually_read(self):
        module = self.load()
        outside = self.base / 'outside sentinel'
        outside.mkdir()
        self.symlink(outside, self.root / 'linked input', directory=True)
        # abspath is lexical. Once normalized, use that SAME path for validation and IO.
        self.assertEqual(module.read_instructions('linked input/../input.md', self.root), 'Synthetic instructions only.\n')

    def test_atomic_staging_is_exclusively_in_package_tmp(self):
        module = self.load()
        directories = []
        original = module.tempfile.mkstemp
        def capture(*args, **kwargs):
            directories.append(Path(kwargs['dir']))
            return original(*args, **kwargs)
        with mock.patch.object(module.tempfile, 'mkstemp', side_effect=capture):
            self.assertEqual(self.run_main(module), 0)
        self.assertEqual(directories, [self.root / 'tmp', self.root / 'tmp'])
        self.assertEqual(list((self.root / 'tmp').iterdir()), [])

    def test_linked_tmp_cannot_receive_staged_content(self):
        outside = self.base / 'outside sentinel'
        outside.mkdir()
        self.symlink(outside, self.root / 'tmp', directory=True)
        with self.assertRaises(SystemExit):
            self.run_main(self.load())
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.root / 'home/synthetic.md').exists())
        self.assertFalse((self.root / 'env.local.ps1').exists())

    def test_failed_atomic_replace_keeps_unrelated_tmp_file(self):
        module = self.load()
        scratch = self.root / 'tmp'
        scratch.mkdir()
        sentinel = scratch / 'unrelated.txt'
        sentinel.write_text('Keep synthetic user data.', encoding='utf-8')
        with mock.patch.object(module.os, 'replace', side_effect=OSError('synthetic replace failure')):
            with self.assertRaises(OSError):
                self.run_main(module)
        self.assertEqual(list(scratch.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_text(), 'Keep synthetic user data.')
        self.assertFalse((self.root / 'env.local.ps1').exists())



    def prepare_existing_instructions(self):
        home = self.root / "home"
        home.mkdir()
        target = home / "synthetic.md"
        target.write_bytes(b"Keep the existing synthetic instructions.\n")
        return target

    def test_invalid_local_encoding_preserves_existing_instructions(self):
        target = self.prepare_existing_instructions()
        original = target.read_bytes()
        local = self.root / "env.local.ps1"
        local.write_bytes(b"\xff\xfeInvalid synthetic UTF-8")
        original_local = local.read_bytes()
        with self.assertRaises(SystemExit):
            self.run_main(self.load())
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(local.read_bytes(), original_local)
        self.assertFalse((self.root / "tmp").exists())

    def test_hardlinked_local_config_preserves_existing_instructions(self):
        target = self.prepare_existing_instructions()
        original = target.read_bytes()
        local = self.root / "env.local.ps1"
        local.write_bytes(b"# Synthetic local settings.\n")
        alias = self.base / "local-alias.ps1"
        os.link(local, alias)
        with self.assertRaises(SystemExit):
            self.run_main(self.load())
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(local.read_bytes(), b"# Synthetic local settings.\n")
        self.assertEqual(alias.read_bytes(), local.read_bytes())
        self.assertFalse((self.root / "tmp").exists())

    def test_local_read_failure_preserves_existing_instructions(self):
        target = self.prepare_existing_instructions()
        original = target.read_bytes()
        local = self.root / "env.local.ps1"
        local.write_bytes(b"# Synthetic local settings.\n")
        read_text = Path.read_text
        def unreadable(path, *args, **kwargs):
            if path == local:
                raise PermissionError("Synthetic config read failure")
            return read_text(path, *args, **kwargs)
        with mock.patch.object(Path, "read_text", autospec=True, side_effect=unreadable):
            with self.assertRaises(PermissionError):
                self.run_main(self.load())
        self.assertEqual(target.read_bytes(), original)
        self.assertFalse((self.root / "tmp").exists())

    def test_directory_local_config_preserves_existing_instructions(self):
        target = self.prepare_existing_instructions()
        original = target.read_bytes()
        (self.root / "env.local.ps1").mkdir()
        with self.assertRaises(SystemExit):
            self.run_main(self.load())
        self.assertEqual(target.read_bytes(), original)
        self.assertFalse((self.root / "tmp").exists())

    def test_hardlinked_instruction_output_is_rejected(self):
        target = self.prepare_existing_instructions()
        alias = self.base / "instruction-alias.md"
        os.link(target, alias)
        original = target.read_bytes()
        with self.assertRaises(SystemExit):
            self.run_main(self.load())
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(alias.read_bytes(), original)
        self.assertEqual(target.stat().st_nlink, 2)
        self.assertFalse((self.root / "env.local.ps1").exists())
        self.assertFalse((self.root / "tmp").exists())

    def test_dry_run_validates_local_encoding_without_writing(self):
        local = self.root / "env.local.ps1"
        local.write_bytes(b"\xffSynthetic invalid settings")
        with self.assertRaises(SystemExit):
            self.run_main(self.load(), "--dry-run")
        self.assertFalse((self.root / "home").exists())
        self.assertFalse((self.root / "tmp").exists())
        self.assertEqual(local.read_bytes(), b"\xffSynthetic invalid settings")

    def test_invalid_config_does_not_create_home_or_tmp(self):
        local = self.root / "env.local.ps1"
        local.write_bytes(b"\xffInvalid synthetic config")
        with self.assertRaises(SystemExit):
            self.run_main(self.load())
        self.assertFalse((self.root / "home").exists())
        self.assertFalse((self.root / "tmp").exists())
        self.assertEqual(local.read_bytes(), b"\xffInvalid synthetic config")

    def test_atomic_helper_rejects_existing_hardlinked_destination(self):
        target = self.prepare_existing_instructions()
        original = target.read_bytes()
        alias = self.base / "instruction-alias.md"
        os.link(target, alias)
        with self.assertRaises(SystemExit):
            self.load()._atomic_write_text(target, "New synthetic instructions", encoding="utf-8", root=self.root)
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(alias.read_bytes(), original)
        self.assertEqual(target.stat().st_nlink, 2)
        self.assertFalse((self.root / "tmp").exists())

    def test_atomic_helper_rejects_existing_linked_destination(self):
        target = self.root / "home/synthetic.md"
        target.parent.mkdir()
        outside = self.base / "outside-instructions.md"
        outside.write_bytes(b"Preserve synthetic external instructions.")
        self.symlink(outside, target)
        with self.assertRaises(SystemExit):
            self.load()._atomic_write_text(target, "New synthetic instructions", encoding="utf-8", root=self.root)
        self.assertTrue(target.is_symlink())
        self.assertEqual(outside.read_bytes(), b"Preserve synthetic external instructions.")
        self.assertFalse((self.root / "tmp").exists())

    def test_output_hardlinked_during_staging_is_rejected(self):
        target = self.prepare_existing_instructions()
        original = target.read_bytes()
        alias = self.base / "late-instruction-alias.md"
        module = self.load()
        fsync = module.os.fsync
        def hardlink(fd):
            fsync(fd)
            os.link(target, alias)
        with mock.patch.object(module.os, "fsync", side_effect=hardlink):
            with self.assertRaises(SystemExit):
                module._atomic_write_text(target, "New synthetic instructions", encoding="utf-8", root=self.root)
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(alias.read_bytes(), original)
        self.assertEqual(target.stat().st_nlink, 2)
        self.assertEqual(list((self.root / "tmp").iterdir()), [])

    def test_output_linked_during_staging_is_rejected(self):
        target = self.prepare_existing_instructions()
        outside = self.base / "outside-instructions.md"
        outside.write_bytes(b"Preserve synthetic external instructions.")
        # Verify symlink support before installing the injected filesystem event.
        probe = self.base / "link-probe"
        self.symlink(outside, probe)
        probe.unlink()
        module = self.load()
        fsync = module.os.fsync
        def link(fd):
            fsync(fd)
            target.unlink()
            target.symlink_to(outside)
        with mock.patch.object(module.os, "fsync", side_effect=link):
            with self.assertRaises(SystemExit):
                module._atomic_write_text(target, "New synthetic instructions", encoding="utf-8", root=self.root)
        self.assertTrue(target.is_symlink())
        self.assertEqual(outside.read_bytes(), b"Preserve synthetic external instructions.")
        self.assertEqual(list((self.root / "tmp").iterdir()), [])

    def test_valid_dry_run_preserves_existing_output_and_settings(self):
        target = self.prepare_existing_instructions()
        original = target.read_bytes()
        local = self.root / "env.local.ps1"
        local.write_bytes(b"# Preserve the synthetic local settings.\r\n")
        self.assertEqual(self.run_main(self.load(), "--dry-run"), 0)
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(local.read_bytes(), b"# Preserve the synthetic local settings.\r\n")
        self.assertFalse((self.root / "tmp").exists())

    def test_settings_commit_failure_restores_exact_previous_md(self):
        for existing in (False, True):
            target = self.root / 'home/synthetic.md'
            target.parent.mkdir(exist_ok=True)
            if existing: target.write_bytes(b'\xef\xbb\xbfOriginal\r\n')
            else: target.unlink(missing_ok=True)
            local = self.root / 'env.local.ps1'
            original = b"$env:CODEX_MODEL_INSTRUCTIONS_FILE = 'old.md'\n"
            local.write_bytes(original)
            module = self.load()
            replace = module.os.replace
            def fail_config(source, destination):
                if Path(destination) == local: raise PermissionError('synthetic config lock')
                return replace(source, destination)
            with mock.patch.object(module.os, 'replace', side_effect=fail_config):
                with self.assertRaises(PermissionError): self.run_main(module)
            self.assertEqual(local.read_bytes(), original)
            if existing: self.assertEqual(target.read_bytes(), b'\xef\xbb\xbfOriginal\r\n')
            else: self.assertFalse(target.exists())
            self.assertEqual(list((self.root / 'tmp').iterdir()), [])


if __name__ == "__main__":
    unittest.main()
