"""Exercise Office/PDF executable and derived-output paths in synthetic packages."""
import ast
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
SAFETY = "home/skills/pdf/scripts/portable_safety.py"
HELPERS = "home/skills/pptx/scripts/office/helpers/__init__.py"


class OfficeOutputBoundaryTests(unittest.TestCase):
    def setUp(self):
        for entry in (*reversed(ROOT.parents), ROOT):
            info = entry.lstat()
            self.assertFalse(stat.S_ISLNK(info.st_mode))
            self.assertFalse(getattr(info, "st_file_attributes", 0) & 0x400)
        scratch = ROOT / "tmp"
        if scratch.exists() or scratch.is_symlink():
            info = scratch.lstat()
            self.assertFalse(stat.S_ISLNK(info.st_mode))
            self.assertFalse(getattr(info, "st_file_attributes", 0) & 0x400)
        scratch.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="office-boundaries-", dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.package = self.base / "portable package"
        self.outside = self.base / "outside synthetic package"
        self.package.mkdir()
        self.outside.mkdir()
        for name in ("codex.exe", "env.ps1"):
            (self.package / name).write_bytes(b"synthetic package marker")
        for relative in (SAFETY, HELPERS):
            destination = self.package / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        self.safety = self.load_helper(SAFETY)
        self.helpers = self.load_helper(HELPERS)

    def load_helper(self, relative):
        spec = importlib.util.spec_from_file_location("office_boundary_helper", self.package / relative)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.object(sys, "dont_write_bytecode", True):
            spec.loader.exec_module(module)
        return module

    @staticmethod
    def source_function(relative, name, namespace):
        # Isolate rendering dependencies, while executing the actual production
        # function and the actual relocated path validators without modification.
        source = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        function = next(node for node in source.body
                        if isinstance(node, ast.FunctionDef) and node.name == name)
        exec(compile(ast.Module(body=[function], type_ignores=[]), relative, "exec"), namespace)
        return namespace[name]

    def poppler_function(self):
        return self.source_function(
            "home/skills/pdf/scripts/convert_pdf_to_images.py", "_portable_poppler_bin",
            {"portable_root": self.safety.portable_root,
             "resolve_inside": self.safety.resolve_inside},
        )

    def make_poppler(self, relative="tool/pdf/poppler/Library/bin"):
        directory = self.package / relative
        directory.mkdir(parents=True, exist_ok=True)
        for executable in ("pdftoppm.exe", "pdfinfo.exe"):
            (directory / executable).write_bytes(b"synthetic executable; never run")
        return directory

    def make_link(self, target, destination, hard):
        try:
            if hard:
                os.link(target, destination)
            else:
                destination.symlink_to(target)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"Link creation unavailable: {error}")

    def test_poppler_accepts_regular_binaries_and_supported_fallback(self):
        directory = self.make_poppler()
        self.assertEqual(self.poppler_function()(), str(directory))
        (directory / "pdfinfo.exe").unlink()
        fallback = self.make_poppler("tool/pdf/poppler/bin")
        self.assertEqual(self.poppler_function()(), str(fallback))

    def check_poppler_links(self, hard):
        directory = self.make_poppler()
        target = self.outside / "fake.exe"
        target.write_bytes(b"outside executable must not run")
        for name in ("pdftoppm.exe", "pdfinfo.exe"):
            with self.subTest(executable=name):
                executable = directory / name
                executable.unlink()
                self.make_link(target, executable, hard)
                try:
                    with self.assertRaises(RuntimeError):
                        self.poppler_function()()
                finally:
                    executable.unlink()
                    executable.write_bytes(b"synthetic executable; never run")

    def test_poppler_rejects_symlink_executables(self):
        self.check_poppler_links(hard=False)

    def test_poppler_rejects_hardlinked_executables(self):
        self.check_poppler_links(hard=True)

    def render_grids(self):
        class Grid:
            def save(self, filename, **kwargs):
                # Pillow.save opens output names with w+b; a fake renderer keeps
                # this storage-boundary test independent of native image codecs.
                with open(filename, "w+b") as stream:
                    stream.write(b"rendered synthetic grid")

        render = self.source_function(
            "home/skills/pptx/scripts/thumbnail.py", "create_grids",
            {"Path": Path, "JPEG_QUALITY": 95, "create_grid": lambda *args: Grid(),
             "resolve_portable_path": self.helpers.resolve_portable_path},
        )
        return render([(self.package / f"slide{i}.jpg", str(i)) for i in range(3)],
                      1, 300, self.package / "thumbnails.jpg")

    def check_grid_link(self, hard):
        target = self.outside / "sentinel.jpg"
        target.write_bytes(b"unchanged sentinel")
        self.make_link(target, self.package / "thumbnails-1.jpg", hard)
        with self.assertRaises(RuntimeError):
            self.render_grids()
        self.assertEqual(target.read_bytes(), b"unchanged sentinel")
        self.assertFalse((self.package / "thumbnails-2.jpg").exists())

    def test_numbered_grid_rejects_symlink_output(self):
        self.check_grid_link(hard=False)

    def test_numbered_grid_rejects_hardlinked_output(self):
        self.check_grid_link(hard=True)

    def test_numbered_grid_keeps_regular_output_working(self):
        outputs = self.render_grids()
        self.assertEqual([Path(path).name for path in outputs],
                         ["thumbnails-1.jpg", "thumbnails-2.jpg"])
        for output in outputs:
            self.assertEqual(Path(output).read_bytes(), b"rendered synthetic grid")


if __name__ == "__main__":
    unittest.main()
