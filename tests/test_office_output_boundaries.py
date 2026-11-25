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


    def rezip_source(self):
        source = self.package / "work" / "synthetic unpacked"
        source.mkdir(parents=True)
        (source / "[Content_Types].xml").write_bytes(b"<Types/>")
        (source / "doc.xml").write_bytes(b"<document>synthetic</document>")
        return source

    def test_validator_bootstrap_is_bound_to_its_own_skill_directory(self):
        relative = "home/skills/pptx/scripts/office/validate.py"
        entry = self.package / relative
        shutil.copyfile(ROOT / relative, entry)
        validators = entry.parent / "validators"
        validators.mkdir()
        (validators / "__init__.py").write_bytes(b"# synthetic marker")
        namespace = {"__file__": str(entry), "Path": Path, "stat": stat}
        bootstrap = self.source_function(relative, "_office_import_directory", namespace)
        self.assertEqual(bootstrap(), entry.parent)
        # The environment and cwd do not select the import directory.
        with mock.patch.dict(os.environ, {"CODEX_INSTALL_DIR": str(self.outside),
                                          "PYTHONPATH": str(self.outside)}):
            self.assertEqual(bootstrap(), entry.parent)
        (validators / "__init__.py").unlink()
        with self.assertRaises(FileNotFoundError):
            bootstrap()

    def test_validator_bootstrap_rejects_linked_sibling_package(self):
        relative = "home/skills/pptx/scripts/office/validate.py"
        entry = self.package / relative
        shutil.copyfile(ROOT / relative, entry)
        (self.outside / "__init__.py").write_bytes(b"# unrelated marker")
        self.directory_link(self.outside, entry.parent / "validators")
        namespace = {"__file__": str(entry), "Path": Path, "stat": stat}
        bootstrap = self.source_function(relative, "_office_import_directory", namespace)
        with self.assertRaisesRegex(RuntimeError, "link or non-directory"):
            bootstrap()

    def test_office_scratch_inherits_package_path_and_cleans_on_success_or_exit(self):
        scratch = self.package / "tmp" / "office"
        scratch.mkdir(parents=True)
        sentinel = scratch / "keep.txt"
        sentinel.write_bytes(b"keep")
        paths = []
        with mock.patch.object(self.helpers.tempfile, "TemporaryDirectory",
                               side_effect=AssertionError("private Windows ACL temp directory")):
            for failure in (False, True):
                try:
                    with self.helpers.portable_temporary_directory(prefix="audit-") as name:
                        self.assertIsInstance(name, str)
                        child = Path(name)
                        self.assertEqual(child.parent, scratch)
                        paths.append(child)
                        (child / "scratch.txt").write_bytes(b"owned")
                        if failure:
                            raise SystemExit(2)
                except SystemExit as error:
                    self.assertTrue(failure)
                    self.assertEqual(error.code, 2)
        self.assertEqual(len(paths), 2)
        self.assertNotEqual(paths[0], paths[1])
        self.assertTrue(all(not p.exists() for p in paths))
        self.assertEqual(list(scratch.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b"keep")

    def test_office_scratch_refuses_existing_link_before_creation(self):
        scratch = self.package / "tmp"
        self.directory_link(self.outside, scratch)
        with self.assertRaises(RuntimeError):
            with self.helpers.portable_temporary_directory():
                self.fail("linked scratch was accepted")
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_rezip_stages_in_package_tmp_and_preserves_archive_content(self):
        import zipfile
        source = self.rezip_source()
        output = self.package / "work" / "output" / "synthetic.docx"
        created = []
        actual = self.helpers.tempfile.mkstemp
        def capture(*args, **kwargs):
            result = actual(*args, **kwargs)
            created.append(Path(result[1]))
            return result
        with mock.patch.object(self.helpers.tempfile, "mkstemp", capture):
            self.helpers.rezip(source, output)
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].parent, self.package / "tmp" / "office")
        self.assertFalse(created[0].exists())
        with zipfile.ZipFile(output) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.namelist(), ["[Content_Types].xml", "doc.xml"])
            for name in archive.namelist():
                self.assertEqual(archive.read(name), (source / name).read_bytes())
            self.assertEqual(archive.getinfo("[Content_Types].xml").compress_type, zipfile.ZIP_STORED)
            self.assertEqual(archive.getinfo("doc.xml").compress_type, zipfile.ZIP_DEFLATED)

    def test_rezip_rejects_linked_tmp_before_output_parent_creation(self):
        source = self.rezip_source()
        scratch = self.package / "tmp"
        try:
            scratch.symlink_to(self.outside, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"Symlink creation unavailable: {error}")
        output = self.package / "work" / "output" / "synthetic.docx"
        with mock.patch.object(self.helpers.tempfile, "mkstemp",
                                       wraps=self.helpers.tempfile.mkstemp) as create_temp:
            with self.assertRaises(RuntimeError):
                self.helpers.rezip(source, output)
            create_temp.assert_not_called()
        self.assertFalse(output.parent.exists())
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_rezip_rejects_file_tmp_before_output_parent_creation(self):
        source = self.rezip_source()
        scratch = self.package / "tmp"
        scratch.write_bytes(b"keep")
        output = self.package / "work" / "output" / "synthetic.docx"
        with self.assertRaises((OSError, RuntimeError)):
            self.helpers.rezip(source, output)
        self.assertFalse(output.parent.exists())
        self.assertEqual(scratch.read_bytes(), b"keep")

    def test_rezip_replace_failure_preserves_output_and_unrelated_tmp(self):
        source = self.rezip_source()
        scratch = self.package / "tmp" / "office"
        scratch.mkdir(parents=True)
        sentinel = scratch / "keep.txt"
        sentinel.write_bytes(b"keep")
        output = self.package / "work" / "synthetic.docx"
        output.write_bytes(b"original")
        with mock.patch.object(self.helpers.os, "replace", side_effect=OSError("synthetic")):
            with self.assertRaisesRegex(OSError, "synthetic"):
                self.helpers.rezip(source, output)
        self.assertEqual(output.read_bytes(), b"original")
        self.assertEqual(list(scratch.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b"keep")
        self.assertEqual(list(output.parent.glob("*.tmp")), [])


    def extraction_archive(self, name="word/document.xml", content=b"synthetic XML"):
        import io
        import zipfile
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(name, content)
        archive = zipfile.ZipFile(io.BytesIO(buffer.getvalue()))
        self.addCleanup(archive.close)
        return archive

    def extraction_destination(self):
        destination = self.package / "work" / "synthetic unpacked"
        destination.mkdir(parents=True)
        return destination

    def directory_link(self, target, link):
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"Directory symlinks unavailable: {error}")

    def test_extract_rejects_in_tree_directory_link(self):
        destination = self.extraction_destination()
        actual = destination / "actual"
        actual.mkdir()
        sentinel = actual / "keep.txt"
        sentinel.write_bytes(b"keep")
        self.directory_link(actual, destination / "word")
        with self.assertRaisesRegex(ValueError, "symbolic link/junction/reparse"):
            self.helpers.safe_extract(self.extraction_archive(), destination)
        self.assertEqual(list(actual.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b"keep")

    def test_extract_rejects_dangling_directory_link_without_creating_target(self):
        destination = self.extraction_destination()
        actual = destination / "must-not-be-created"
        self.directory_link(actual, destination / "word")
        with self.assertRaisesRegex(ValueError, "symbolic link/junction/reparse"):
            self.helpers.safe_extract(self.extraction_archive(), destination)
        self.assertFalse(actual.exists())
        self.assertTrue((destination / "word").is_symlink())

    def test_extract_rejects_link_before_resolving_member_path(self):
        destination = self.extraction_destination()
        self.directory_link(self.outside, destination / "word")
        original_resolve = Path.resolve
        probes = []

        def capture(path, *args, **kwargs):
            if path == destination / "word" / "document.xml":
                probes.append(str(path))
            return original_resolve(path, *args, **kwargs)

        with mock.patch.object(Path, "resolve", capture):
            with self.assertRaises(ValueError):
                self.helpers.safe_extract(self.extraction_archive(), destination)
        self.assertEqual(probes, [], "Member links must be rejected before resolve follows them")
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_extract_rejects_linked_directory_archive_entry(self):
        destination = self.extraction_destination()
        actual = destination / "actual"
        actual.mkdir()
        self.directory_link(actual, destination / "word")
        with self.assertRaisesRegex(ValueError, "symbolic link/junction/reparse"):
            self.helpers.safe_extract(self.extraction_archive("word/", b""), destination)
        self.assertEqual(list(actual.iterdir()), [])

    def test_extract_source_open_failure_closes_output_before_cleanup(self):
        import zipfile
        destination = self.extraction_destination()
        archive = self.extraction_archive()
        output = destination / "word" / "document.xml"
        handles = []
        real_open = Path.open
        real_unlink = Path.unlink
        cleanup_closed = []

        def capture_open(path, *args, **kwargs):
            handle = real_open(path, *args, **kwargs)
            if path == output and args and args[0] == "xb":
                handles.append(handle)
                self.addCleanup(handle.close)
            return handle

        def windows_cleanup(path, *args, **kwargs):
            if path == output:
                closed = bool(handles) and all(handle.closed for handle in handles)
                cleanup_closed.append(closed)
                if not closed:
                    raise PermissionError("Synthetic Windows open-file sharing violation")
            return real_unlink(path, *args, **kwargs)

        with mock.patch.object(Path, "open", capture_open), \
             mock.patch.object(Path, "unlink", windows_cleanup), \
             mock.patch.object(archive, "open", side_effect=zipfile.BadZipFile("synthetic bad header")):
            with self.assertRaisesRegex(zipfile.BadZipFile, "synthetic bad header"):
                self.helpers.safe_extract(archive, destination)
        self.assertEqual(cleanup_closed, [True])
        self.assertTrue(all(handle.closed for handle in handles))
        self.assertFalse(output.exists())

    def test_extract_preserves_existing_file_and_hardlink(self):
        destination = self.extraction_destination()
        output = destination / "word" / "document.xml"
        output.parent.mkdir()
        original = b"existing user XML"
        output.write_bytes(original)
        with self.assertRaisesRegex(ValueError, "collides"):
            self.helpers.safe_extract(self.extraction_archive(), destination)
        self.assertEqual(output.read_bytes(), original)
        output.unlink()
        sentinel = self.outside / "keep.xml"
        sentinel.write_bytes(original)
        self.make_link(sentinel, output, hard=True)
        with self.assertRaisesRegex(ValueError, "collides"):
            self.helpers.safe_extract(self.extraction_archive(), destination)
        self.assertEqual(sentinel.read_bytes(), original)
        self.assertEqual(output.read_bytes(), original)

    def test_extract_regular_archive_content_is_unchanged(self):
        import io
        import zipfile
        destination = self.extraction_destination()
        data = {"[Content_Types].xml": b"<Types/>", "word/": b"",
                "word/document.xml": "synthetic \u4e2d\u6587 XML".encode("utf-8"),
                "word/media/image.bin": bytes(range(256)) * 4097}
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in data.items():
                archive.writestr(name, content)
        with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as archive:
            self.helpers.safe_extract(archive, destination)
        for name, content in data.items():
            path = destination / name
            if name.endswith("/"):
                self.assertTrue(path.is_dir())
            else:
                self.assertEqual(path.read_bytes(), content)

if __name__ == "__main__":
    unittest.main()
