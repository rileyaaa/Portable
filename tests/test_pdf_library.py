"""Behavior tests for the portable PDF library, using synthetic PDFs only."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid
import zipfile


ROOT = Path(__file__).absolute().parents[1]
SCRIPT = Path("home/skills/pdf-library/scripts/pdf_library.py")
SAFETY = Path("home/skills/pdf/scripts/portable_safety.py")
PDF_AVAILABLE = (
    importlib.util.find_spec("pymupdf") is not None
    and importlib.util.find_spec("pymupdf4llm") is not None
)


@unittest.skipUnless(
    PDF_AVAILABLE,
    "PDF behavior tests require PyMuPDF and pymupdf4llm; no installation is automatic.",
)
class PdfLibraryTests(unittest.TestCase):
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
        self.fixture = tempfile.TemporaryDirectory(prefix="pdf-library-test-", dir=scratch)
        self.addCleanup(self.fixture.cleanup)
        self.base = Path(self.fixture.name)
        self.package = self.base / "便携 Package"
        self.package.mkdir()
        for marker in ("env.ps1", "codex.exe"):
            (self.package / marker).write_bytes(b"synthetic marker; never executable")
        for relative in (SCRIPT, SAFETY):
            destination = self.package / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        self.input = self.package / "work" / "PDF 输入"
        self.input.mkdir(parents=True)
        self.library = self.package / "work" / "library"
        module_name = "portable_pdf_test_" + uuid.uuid4().hex
        spec = importlib.util.spec_from_file_location(module_name, self.package / SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = self.module
        self.addCleanup(sys.modules.pop, module_name, None)
        with mock.patch.object(sys, "dont_write_bytecode", True):
            spec.loader.exec_module(self.module)
        import pymupdf

        self.pdf = pymupdf

    def create_pdf(self, relative, page_texts):
        path = self.input / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.pdf.open() as document:
            for text in page_texts:
                page = document.new_page()
                page.insert_text((50, 60), text, fontname="cour", fontsize=10)
            document.save(path)
        return path

    def create_scanned_pdf(self):
        path = self.input / "scanned.pdf"
        with self.pdf.open() as document:
            page = document.new_page()
            image = self.pdf.Pixmap(self.pdf.csRGB, (0, 0, 40, 40), False)
            image.clear_with(255)
            page.insert_image(self.pdf.Rect(10, 10, 300, 300), stream=image.tobytes("png"))
            document.save(path)
        return path

    def ordinary_pdf(self):
        return self.create_pdf(
            Path("nested") / "manual.pdf",
            [
                "Database manual\n"
                "AUTO_RECONNECT\n"
                "SELECT * FROM V$DATABASE;\n"
                "#define S24 20\n"
                "/dm8/bin/dmserver\n"
                '<parameter name="PORT_NUM">5236</parameter>',
                "UNIQUE_SECOND_PAGE_SYMBOL\n"
                + "\n".join(f"Parameter_{i:03d} value_{i:03d}" for i in range(25)),
            ],
        )

    def markdown_path(self, relative=Path("nested") / "manual.pdf"):
        return self.library / "manuals" / relative.with_suffix(".md")

    @staticmethod
    def assert_page_markers_outside_fences(test, text):
        fence = None
        markers = []
        for line in text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith(("```", "~~~")):
                char = stripped[0]
                length = len(stripped) - len(stripped.lstrip(char))
                if fence is None:
                    fence = (char, length)
                elif char == fence[0] and length >= fence[1]:
                    fence = None
            if line.startswith("## PDF 第 "):
                test.assertIsNone(fence, "PDF page marker appeared inside a code fence")
                markers.append(line)
        test.assertIsNone(fence, "Unclosed Markdown fence")
        return markers

    @contextlib.contextmanager
    def unchanged_file(self, path):
        before = path.read_bytes()
        yield
        self.assertEqual(path.read_bytes(), before)

    def symlink(self, target, destination, directory=False):
        try:
            destination.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"Symlink creation unavailable: {error}")

    def test_cli_read_and_search_on_redirected_legacy_code_page(self):
        self.create_pdf("manual.pdf", ["PORTABLE_UNICODE_PAGE\nSELECT * FROM V$DATABASE;"])
        self.module.build_library(self.input, self.library)
        for args in (
            ["read", "--library", str(self.library), "--document", "manual.pdf", "--pages", "1"],
            ["search", "--library", str(self.library), "--query", "PORTABLE_UNICODE_PAGE"],
        ):
            with self.subTest(command=args[0]):
                buffer = io.BytesIO()
                errors = io.BytesIO()
                with io.TextIOWrapper(buffer, encoding="cp1252", errors="strict") as stdout, \
                        io.TextIOWrapper(errors, encoding="cp1252", errors="strict") as stderr:
                    with mock.patch.object(sys, "stdout", stdout), mock.patch.object(sys, "stderr", stderr):
                        self.assertEqual(self.module.main(args), 0)
                    stdout.flush()
                    self.assertEqual(stdout.encoding, "utf-8")
                    value = buffer.getvalue().decode("utf-8")
                    self.assertIn("PORTABLE_UNICODE_PAGE", value)
                    self.assertIn("\u7b2c", value)
                    if args[0] == "search":
                        self.assertEqual(json.loads(value)[0]["page"], 1)

    def test_text_symbols_and_page_boundaries_survive_conversion(self):
        self.ordinary_pdf()
        result = self.module.build_library(self.input, self.library)
        self.assertEqual(result["documents"], 1)
        self.assertEqual(result["pages"], 2)
        self.assertTrue(result["strict_ok"])
        text = self.markdown_path().read_text(encoding="utf-8")
        for literal in (
            "AUTO_RECONNECT",
            "SELECT * FROM V$DATABASE;",
            "#define S24 20",
            "/dm8/bin/dmserver",
            '<parameter name="PORT_NUM">5236</parameter>',
            "UNIQUE_SECOND_PAGE_SYMBOL",
        ):
            self.assertIn(literal, text)
        self.assertNotIn("#define S24 20}", text)
        markers = self.assert_page_markers_outside_fences(self, text)
        self.assertEqual(markers, ["## PDF 第 1 页", "## PDF 第 2 页"])

    def test_original_text_recovers_lines_dropped_by_structured_extractor(self):
        self.ordinary_pdf()
        # Exercise the documented recovery boundary using a real PDF, with
        # deliberately incomplete output from the upstream formatter.
        with mock.patch("pymupdf4llm.to_markdown", return_value="Database manual"):
            result = self.module.build_library(self.input, self.library)
        text = self.markdown_path().read_text(encoding="utf-8")
        for literal in (
            "SELECT * FROM V$DATABASE;",
            "#define S24 20",
            '<parameter name="PORT_NUM">5236</parameter>',
            "Parameter_024 value_024",
        ):
            self.assertIn(literal, text)
        self.assertEqual(result["text_coverage"], 1.0)
        self.assertEqual(result["code_coverage"], 1.0)
        self.assert_page_markers_outside_fences(self, text)

    def test_search_returns_target_page_and_limits_excerpts(self):
        self.ordinary_pdf()
        self.module.build_library(self.input, self.library)
        hits = self.module.search_library(
            self.library, "UNIQUE_SECOND_PAGE_SYMBOL", limit=1, max_chars=160
        )
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["document"], "nested/manual.pdf")
        self.assertEqual(hits[0]["page"], 2)
        self.assertIn("UNIQUE_SECOND_PAGE_SYMBOL", hits[0]["text"])
        self.assertLessEqual(len(hits[0]["text"]), 160)
        page = self.module.read_pages(
            self.library, "nested/manual.pdf", [2], max_chars=300
        )
        self.assertIn("UNIQUE_SECOND_PAGE_SYMBOL", page)
        self.assertNotIn("AUTO_RECONNECT", page)
        self.assertLessEqual(len(page), 300)

    def test_incremental_hashes_reuse_change_and_remove_owned_manuals(self):
        first = self.create_pdf("first.pdf", ["FIRST_DOCUMENT immutable text"])
        second = self.create_pdf(Path("sub") / "second.pdf", ["SECOND_DOCUMENT initial text"])
        self.module.build_library(self.input, self.library)
        original_first = self.markdown_path(Path("first.pdf")).read_bytes()
        result = self.module.build_library(self.input, self.library)
        self.assertEqual(result["reused"], 2)
        second.unlink()
        self.create_pdf(Path("sub") / "second.pdf", ["SECOND_DOCUMENT REPLACED_VALUE"])
        result = self.module.build_library(self.input, self.library)
        self.assertEqual(result["reused"], 1)
        self.assertIn(
            "REPLACED_VALUE",
            self.markdown_path(Path("sub") / "second.pdf").read_text(encoding="utf-8"),
        )
        self.assertEqual(self.markdown_path(Path("first.pdf")).read_bytes(), original_first)
        first.unlink()
        result = self.module.build_library(self.input, self.library)
        self.assertEqual(result["removed"], 1)
        self.assertEqual(result["documents"], 1)
        self.assertFalse(self.markdown_path(Path("first.pdf")).exists())

    def test_same_name_in_distinct_subdirectories_keeps_both_manuals(self):
        self.create_pdf(Path("one") / "manual.pdf", ["FIRST_FOLDER_DOCUMENT text"])
        self.create_pdf(Path("two") / "manual.pdf", ["SECOND_FOLDER_DOCUMENT text"])
        result = self.module.build_library(self.input, self.library)
        self.assertEqual(result["documents"], 2)
        self.assertIn(
            "FIRST_FOLDER_DOCUMENT",
            self.markdown_path(Path("one") / "manual.pdf").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "SECOND_FOLDER_DOCUMENT",
            self.markdown_path(Path("two") / "manual.pdf").read_text(encoding="utf-8"),
        )

    def test_incremental_build_retries_missing_or_failed_ocr(self):
        self.create_scanned_pdf()
        for status in ("missing", "failed"):
            library = self.library.with_name("retry-" + status)
            with self.subTest(status=status):
                with mock.patch.object(self.module, "_ocr",
                                       return_value=("", status, "synthetic OCR unavailable")):
                    first = self.module.build_library(self.input, library, ocr="auto")
                self.assertEqual(first["incomplete_ocr_pages"], 1)
                # Only the OCR boundary is simulated; the PDF renderer, SQLite
                # cache, output hashes and incremental decision are real.
                with mock.patch.object(self.module, "_ocr",
                                       return_value=("RECOVERED_TEXT", "processed", "synthetic OCR")) as ocr:
                    recovered = self.module.build_library(self.input, library, ocr="auto")
                self.assertEqual(recovered["reused"], 0)
                self.assertEqual(recovered["incomplete_ocr_pages"], 0)
                ocr.assert_called_once()
                with mock.patch.object(self.module, "_ocr",
                                       side_effect=AssertionError("Successful OCR should be reused")):
                    cached = self.module.build_library(self.input, library, ocr="auto")
                self.assertEqual(cached["reused"], 1)
                text = (library / "manuals/scanned.md").read_text(encoding="utf-8")
                self.assertIn("RECOVERED_TEXT", text)

    def test_scan_without_ocr_is_incomplete_in_strict_mode(self):
        self.create_scanned_pdf()
        result = self.module.build_library(
            self.input, self.library, ocr="none", strict=True
        )
        self.assertFalse(result["strict_ok"])
        self.assertTrue(result["incomplete_ocr_pages"])
        self.assertTrue((self.library / "OCR.md").is_file())
        self.assertTrue((self.library / "VALIDATION.md").is_file())

    def test_strict_cli_reports_missing_ocr_and_refuses_strict_export(self):
        self.create_scanned_pdf()
        command = [sys.executable, "-B", str(self.package / SCRIPT)]
        result = subprocess.run(
            command + [
                "build", "--input", str(self.input), "--library", str(self.library),
                "--ocr", "auto", "--strict",
            ],
            cwd=self.package, capture_output=True, text=True, encoding="utf-8",
            timeout=60,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        summary = json.loads(result.stdout)
        self.assertFalse(summary["strict_ok"])
        self.assertEqual(summary["incomplete_ocr_pages"], 1)
        self.assertIn("missing", (self.library / "OCR.md").read_text(encoding="utf-8"))
        destination = self.package / "work" / "strict-export.zip"
        result = subprocess.run(
            command + [
                "export", "--library", str(self.library),
                "--output", str(destination), "--strict",
            ],
            cwd=self.package, capture_output=True, text=True, encoding="utf-8",
            timeout=60,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(destination.exists())

    def test_export_contains_only_utf8_markdown_and_matches_digest(self):
        self.ordinary_pdf()
        self.module.build_library(self.input, self.library)
        destination = self.package / "work" / "export.zip"
        result = self.module.export_library(self.library, destination)
        with zipfile.ZipFile(destination) as archive:
            self.assertIsNone(archive.testzip())
            names = archive.namelist()
            self.assertTrue(names)
            self.assertTrue(all(Path(name).suffix.lower() == ".md" for name in names))
            self.assertIn("manuals/nested/manual.md", names)
            self.assertEqual(len(names), len(set(names)))
            for name in names:
                archive.read(name).decode("utf-8")
        self.assertEqual(
            hashlib.sha256(destination.read_bytes()).hexdigest(), result["sha256"]
        )
        receipt = (self.library / "SHA256.md").read_text(encoding="utf-8")
        self.assertIn(result["sha256"], receipt)
        self.assertIn("work/export.zip", receipt)
        second = self.package / "work" / "export-second.zip"
        updated = self.module.export_library(self.library, second)
        receipt = (self.library / "SHA256.md").read_text(encoding="utf-8")
        self.assertIn(updated["sha256"], receipt)
        self.assertNotIn("  work/export.zip", receipt)
        with zipfile.ZipFile(second) as archive:
            self.assertNotIn("最近导出的 ZIP", archive.read("SHA256.md").decode("utf-8"))

    def test_outside_input_and_output_are_rejected(self):
        source = self.ordinary_pdf()
        outside = self.base / "outside"
        outside.mkdir()
        outside_pdf = outside / "manual.pdf"
        shutil.copyfile(source, outside_pdf)
        with self.unchanged_file(outside_pdf):
            with self.assertRaises((RuntimeError, ValueError, OSError)):
                self.module.build_library(outside, self.library)
        with self.assertRaises((RuntimeError, ValueError, OSError)):
            self.module.build_library(self.input, outside / "library")
        self.assertEqual(list(outside.iterdir()), [outside_pdf])

    def test_linked_input_and_output_cannot_escape_package(self):
        source = self.ordinary_pdf()
        outside = self.base / "outside"
        outside.mkdir()
        outside_pdf = outside / "manual.pdf"
        shutil.copyfile(source, outside_pdf)
        linked_input = self.input / "linked.pdf"
        self.symlink(outside_pdf, linked_input)
        with self.assertRaises((RuntimeError, ValueError, OSError)):
            self.module.build_library(self.input, self.library)
        linked_input.unlink()
        # Any directory created before the rejected input was found belongs to
        # this synthetic test. Remove it so the next case is a real alias.
        if self.library.exists():
            shutil.rmtree(self.library)
        self.symlink(outside, self.library, directory=True)
        self.addCleanup(self.library.unlink, missing_ok=True)
        with self.assertRaises((RuntimeError, ValueError, OSError)):
            self.module.build_library(self.input, self.library)
        self.assertEqual(list(outside.iterdir()), [outside_pdf])

    def test_hardlinked_pdf_input_is_rejected(self):
        source = self.ordinary_pdf()
        linked = self.input / "hardlinked.pdf"
        os.link(source, linked)
        with self.assertRaises((RuntimeError, ValueError, OSError)):
            self.module.build_library(self.input, self.library)

    def test_existing_nonempty_unmanaged_library_is_preserved(self):
        self.ordinary_pdf()
        self.library.mkdir()
        user_file = self.library / "user-notes.md"
        user_file.write_text("Existing user material", encoding="utf-8")
        with self.unchanged_file(user_file):
            with self.assertRaises((RuntimeError, ValueError, OSError)):
                self.module.build_library(self.input, self.library)
        self.assertEqual(list(self.library.iterdir()), [user_file])

    def test_manual_changes_to_generated_output_are_not_overwritten(self):
        self.ordinary_pdf()
        self.module.build_library(self.input, self.library)
        generated = self.markdown_path()
        generated.write_text("Manually edited synthetic content", encoding="utf-8")
        with self.unchanged_file(generated):
            with self.assertRaises((RuntimeError, ValueError, OSError)):
                self.module.build_library(self.input, self.library)


if __name__ == "__main__":
    unittest.main()
