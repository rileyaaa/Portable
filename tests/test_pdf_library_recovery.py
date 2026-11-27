"""Real build/SQLite recovery tests; only PDF layout formatting is synthetic."""
import contextlib
import hashlib
import json
import importlib.util
from pathlib import Path
import shutil
import sqlite3
import tempfile
import types
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).absolute().parents[1]
SCRIPT = Path("home/skills/pdf-library/scripts/pdf_library.py")
SAFETY = Path("home/skills/pdf/scripts/portable_safety.py")


@unittest.skipUnless(importlib.util.find_spec("pymupdf"), "PyMuPDF required")
class PdfOutputRecoveryTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "tmp"
        scratch.mkdir(exist_ok=True)
        temp = tempfile.TemporaryDirectory(prefix="pdf-output-recovery-", dir=scratch)
        self.addCleanup(temp.cleanup)
        self.package = Path(temp.name) / "\u4fbf\u643a Package"
        self.package.mkdir()
        for name in ("codex.exe", "env.ps1"):
            (self.package / name).write_bytes(b"synthetic marker; never executable")
        for name in (SCRIPT, SAFETY):
            target = self.package / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        spec = importlib.util.spec_from_file_location("pdf_recovery", self.package / SCRIPT)
        self.library = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.library)
        import pymupdf
        self.pdf = pymupdf
        formatter = types.SimpleNamespace(
            __version__="synthetic-layout",
            to_markdown=lambda doc, pages, **kwargs: doc[pages[0]].get_text("text", sort=True),
        )
        # Real PDFs/text extraction; fault injection is about index publication,
        # not the optional upstream formatter or visual layout quality.
        self.enterContext(mock.patch.object(self.library, "_dependencies", return_value=(pymupdf, formatter)))

    def pdf_file(self, path, text):
        with self.pdf.open() as doc:
            doc.new_page().insert_text((50, 60), text)
            doc.save(path)

    def prepare(self, case, operation):
        source = self.package / "work" / case / "input"
        source.mkdir(parents=True)
        library = source.parent / "library"
        self.pdf_file(source / "anchor.pdf", "ANCHOR_CONTENT must stay unchanged")
        target = source / "target.pdf"
        if operation != "add":
            self.pdf_file(target, "ORIGINAL_TARGET initial document")
        self.library.build_library(source, library)
        output = library / "manuals/target.md"
        old = output.read_bytes() if output.exists() else None
        anchor = (library / "manuals/anchor.md").read_bytes()
        if target.exists():
            target.unlink()
        if operation != "delete":
            self.pdf_file(target, "UPDATED_TARGET committed document")
        return source, library, output, old, anchor

    def sql(self, library, statement):
        with contextlib.closing(sqlite3.connect(library / "_index.sqlite3")) as db, db:
            return db.execute(statement).fetchall()

    def indexed(self, library):
        return [self.sql(library, "SELECT * FROM " + table + " ORDER BY 1,2")
                for table in ("documents", "pages")]

    def pending(self, library):
        return self.sql(library, "SELECT document,previous_sha,desired_sha FROM pending_output")

    def complete(self, source, library, output, operation, anchor):
        result = self.library.build_library(source, library)
        self.assertEqual(result["documents"], 1 if operation == "delete" else 2)
        self.assertEqual(self.pending(library), [])
        self.assertEqual((library / "manuals/anchor.md").read_bytes(), anchor)
        self.assertEqual(self.library.verify_library(library)["documents"], result["documents"])
        destination = library.with_suffix(".zip")
        self.library.export_library(library, destination)
        with zipfile.ZipFile(destination) as exported:
            self.assertIsNone(exported.testzip())
            self.assertEqual("manuals/target.md" in exported.namelist(), operation != "delete")
        if operation == "delete":
            self.assertFalse(output.exists())
            self.assertEqual(self.library.search_library(library, "ORIGINAL_TARGET"), [])
        else:
            self.assertIn(b"UPDATED_TARGET", output.read_bytes())
            self.assertIn("UPDATED_TARGET", self.library.read_pages(library, "target.pdf", [1]))

    def test_real_sql_failure_before_publication(self):
        for operation in ("add", "replace", "delete"):
            with self.subTest(operation=operation):
                src, lib, output, old, anchor = self.prepare("sql-" + operation, operation)
                before = self.indexed(lib)
                event, record = ("DELETE", "OLD") if operation == "delete" else ("INSERT", "NEW")
                self.sql(lib, f"""CREATE TRIGGER injected BEFORE {event} ON documents
                    WHEN {record}.document='target.pdf'
                    BEGIN SELECT RAISE(ABORT,'synthetic index failure'); END""")
                with self.assertRaisesRegex(sqlite3.IntegrityError, "synthetic index failure"):
                    self.library.build_library(src, lib)
                self.assertEqual(self.indexed(lib), before)
                self.assertEqual(output.read_bytes() if output.exists() else None, old)
                self.assertEqual(self.pending(lib), [])
                self.sql(lib, "DROP TRIGGER injected")
                self.complete(src, lib, output, operation, anchor)

    def test_real_commit_denial_rolls_back_before_publication(self):
        for operation in ("add", "replace", "delete"):
            with self.subTest(operation=operation):
                src, lib, output, old, anchor = self.prepare("commit-" + operation, operation)
                before = self.indexed(lib)
                connect, database = sqlite3.connect, self.library._database
                denials = []

                def uncached(*args, **kwargs):
                    return connect(*args, **kwargs, cached_statements=0)

                def with_authorizer(*args, **kwargs):
                    db = database(*args, **kwargs)
                    armed = False

                    def authorize(action, arg1, arg2, schema, trigger):
                        nonlocal armed
                        if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_DELETE) and arg1 == "documents":
                            armed = True
                        if armed and action == sqlite3.SQLITE_TRANSACTION and arg1 == "COMMIT":
                            denials.append(arg1)
                            armed = False
                            return sqlite3.SQLITE_DENY
                        return sqlite3.SQLITE_OK

                    db.set_authorizer(authorize)
                    return db

                # SQLite itself denies COMMIT, rather than a fake connection
                # raising before executing the index mutation.
                with mock.patch.object(sqlite3, "connect", uncached), \
                        mock.patch.object(self.library, "_database", with_authorizer):
                    with self.assertRaises(sqlite3.DatabaseError):
                        self.library.build_library(src, lib)
                self.assertEqual(denials, ["COMMIT"])
                self.assertEqual(self.indexed(lib), before)
                self.assertEqual(self.pending(lib), [])
                self.assertEqual(output.read_bytes() if output.exists() else None, old)
                self.complete(src, lib, output, operation, anchor)

    def test_real_sql_failure_after_file_publication(self):
        for operation in ("add", "replace", "delete"):
            with self.subTest(operation=operation):
                src, lib, output, old, anchor = self.prepare("finish-" + operation, operation)
                self.sql(lib, """CREATE TRIGGER injected BEFORE DELETE ON pending_output
                    BEGIN SELECT RAISE(ABORT,'synthetic intent clear failure'); END""")
                with self.assertRaisesRegex(sqlite3.IntegrityError, "synthetic intent clear failure"):
                    self.library.build_library(src, lib)
                self.assertEqual(len(self.pending(lib)), 1)
                if operation == "delete":
                    self.assertFalse(output.exists())
                else:
                    self.assertIn(b"UPDATED_TARGET", output.read_bytes())
                for read in (
                    lambda: self.library.search_library(lib, "TARGET"),
                    lambda: self.library.read_pages(lib, "anchor.pdf", [1]),
                    lambda: self.library.verify_library(lib),
                    lambda: self.library.export_library(lib, lib.with_suffix(".zip")),
                ):
                    with self.assertRaisesRegex(ValueError, "Unfinished Markdown/index update"):
                        read()
                self.assertFalse(lib.with_suffix(".zip").exists())
                self.sql(lib, "DROP TRIGGER injected")
                published = output.read_bytes() if output.exists() else None
                output.write_bytes(b"user edit after publication")
                with self.assertRaisesRegex(ValueError, "refusing to overwrite user changes"):
                    self.library.build_library(src, lib)
                self.assertEqual(output.read_bytes(), b"user edit after publication")
                self.assertEqual(len(self.pending(lib)), 1)
                if published is None:
                    output.unlink()
                else:
                    output.write_bytes(published)
                self.complete(src, lib, output, operation, anchor)

    def test_pending_file_failure_and_manual_edit_protection(self):
        for operation in ("add", "replace", "delete"):
            with self.subTest(operation=operation):
                src, lib, output, old, anchor = self.prepare("file-" + operation, operation)
                unlink, write = Path.unlink, self.library._write

                def interrupted_unlink(path, *args, **kwargs):
                    if path == output:
                        raise OSError("synthetic file interruption")
                    return unlink(path, *args, **kwargs)

                def interrupted_write(path, *args, **kwargs):
                    if path == output:
                        raise OSError("synthetic file interruption")
                    return write(path, *args, **kwargs)

                with mock.patch.object(Path, "unlink", interrupted_unlink), \
                        mock.patch.object(self.library, "_write", interrupted_write):
                    with self.assertRaisesRegex(OSError, "synthetic file interruption"):
                        self.library.build_library(src, lib)
                self.assertEqual(len(self.pending(lib)), 1)
                self.assertEqual(output.read_bytes() if output.exists() else None, old)
                if operation == "replace":
                    output.unlink()
                    with self.assertRaisesRegex(ValueError, "refusing to overwrite user changes"):
                        self.library.build_library(src, lib)
                    self.assertFalse(output.exists())
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"user notes")
                with self.assertRaisesRegex(ValueError, "refusing to overwrite user changes"):
                    self.library.build_library(src, lib)
                self.assertEqual(output.read_bytes(), b"user notes")
                self.assertEqual(len(self.pending(lib)), 1)
                if old is None:
                    output.unlink()
                else:
                    output.write_bytes(old)
                # A failed file operation may have changed the output before
                # raising. Reentry must not infer ownership from old bytes.
                self.assert_blocked_previous(lib, output, old, anchor, src)
                self.reconcile_fixture(lib, output, operation)
                self.complete(src, lib, output, operation, anchor)

    def pending_token(self, lib):
        return self.sql(lib, "SELECT publication_token FROM pending_output")[0][0]

    def assert_blocked_previous(self, lib, output, old, anchor, src):
        pending, token, index = self.pending(lib), self.pending_token(lib), self.indexed(lib)
        reports = {name: (lib / name).read_bytes() for name in self.library.REPORTS}
        self.assertIsNotNone(token)
        def identity():
            if not output.exists():
                return None
            info = output.stat()
            return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        before = identity()
        with self.assertRaisesRegex(ValueError, "Pending Markdown publication is uncertain"):
            self.library.build_library(src, lib)
        self.assertEqual(output.read_bytes() if output.exists() else None, old)
        self.assertEqual(identity(), before)
        self.assertEqual(self.pending(lib), pending)
        self.assertEqual(self.pending_token(lib), token)
        self.assertEqual(self.indexed(lib), index)
        self.assertEqual(self.sql(lib, "PRAGMA quick_check"), [("ok",)])
        self.assertEqual(self.sql(lib, "SELECT count(*) FROM pages p LEFT JOIN documents d "
                                  "ON p.document=d.document WHERE d.document IS NULL"), [(0,)])
        self.assertEqual((lib / "manuals/anchor.md").read_bytes(), anchor)
        self.assertEqual({name: (lib / name).read_bytes() for name in self.library.REPORTS}, reports)
        for read in (
            lambda: self.library.search_library(lib, "TARGET"),
            lambda: self.library.read_pages(lib, "anchor.pdf", [1]),
            lambda: self.library.verify_library(lib),
            lambda: self.library.export_library(lib, lib.with_suffix(".zip")),
        ):
            with self.assertRaisesRegex(ValueError, "Unfinished Markdown/index update"):
                read()
        self.assertFalse(lib.with_suffix(".zip").exists())

    def reconcile_fixture(self, lib, output, operation):
        # Explicit synthetic user action, not a repair command in the product.
        if operation == "delete":
            output.unlink()
        else:
            pages = self.sql(lib, "SELECT markdown FROM pages WHERE document='target.pdf' ORDER BY page")
            output.write_bytes(("# target\n\n" + "\n".join(p[0] for p in pages)).encode("utf-8"))

    def test_publication_claim_failure_retries_only_unattempted_output(self):
        for fault in ("update", "commit"):
            for operation in ("add", "replace", "delete"):
                with self.subTest(fault=fault, operation=operation):
                    src, lib, output, old, anchor = self.prepare(fault + "-claim-" + operation, operation)
                    if fault == "update":
                        self.sql(lib, """CREATE TRIGGER injected BEFORE UPDATE OF publication_token ON pending_output
                            BEGIN SELECT RAISE(ABORT,'synthetic publication claim failure'); END""")
                        with self.assertRaisesRegex(sqlite3.IntegrityError, "synthetic publication claim failure"):
                            self.library.build_library(src, lib)
                        self.sql(lib, "DROP TRIGGER injected")
                    else:
                        connect, database = sqlite3.connect, self.library._database
                        denials = []

                        def uncached(*args, **kwargs):
                            return connect(*args, **kwargs, cached_statements=0)

                        def with_authorizer(*args, **kwargs):
                            db = database(*args, **kwargs)
                            armed = False

                            def authorize(action, arg1, arg2, schema, trigger):
                                nonlocal armed
                                if action == sqlite3.SQLITE_UPDATE and arg1 == "pending_output" and arg2 == "publication_token":
                                    armed = True
                                if armed and action == sqlite3.SQLITE_TRANSACTION and arg1 == "COMMIT":
                                    denials.append(arg1)
                                    armed = False
                                    return sqlite3.SQLITE_DENY
                                return sqlite3.SQLITE_OK

                            db.set_authorizer(authorize)
                            return db

                        with mock.patch.object(sqlite3, "connect", uncached), \
                                mock.patch.object(self.library, "_database", with_authorizer):
                            with self.assertRaises(sqlite3.DatabaseError):
                                self.library.build_library(src, lib)
                        self.assertEqual(denials, ["COMMIT"])
                    self.assertEqual(output.read_bytes() if output.exists() else None, old)
                    self.assertEqual(len(self.pending(lib)), 1)
                    self.assertIsNone(self.pending_token(lib))
                    self.assertEqual(self.sql(lib, "PRAGMA quick_check"), [("ok",)])
                    self.complete(src, lib, output, operation, anchor)
                    print(f"UNATTEMPTED_RETRY {fault} {operation} PASS", flush=True)

    def test_post_publication_exact_previous_restore_is_preserved(self):
        def digest(data):
            return hashlib.sha256(data).hexdigest() if data is not None else None

        for operation in ("add", "replace", "delete"):
            with self.subTest(operation=operation):
                src, lib, output, old, anchor = self.prepare("restore-" + operation, operation)

                def report(stage):
                    print(json.dumps(dict(operation=operation, stage=stage,
                        actual=digest(output.read_bytes() if output.exists() else None),
                        indexed=self.sql(lib, "SELECT output_sha FROM documents WHERE document='target.pdf'"),
                        pending=self.pending(lib), quick_check=self.sql(lib, "PRAGMA quick_check")),
                        sort_keys=True), flush=True)

                report("initial")
                self.sql(lib, """CREATE TRIGGER injected BEFORE DELETE ON pending_output
                    BEGIN SELECT RAISE(ABORT,'synthetic intent clear failure'); END""")
                with self.assertRaisesRegex(sqlite3.IntegrityError, "synthetic intent clear failure"):
                    self.library.build_library(src, lib)
                published = output.read_bytes() if output.exists() else None
                self.assertNotEqual(old, published)
                self.assertEqual(self.pending(lib), [("target.pdf", digest(old), digest(published))])
                self.assertIsNotNone(self.pending_token(lib))
                report("after_real_sql_failure")
                self.sql(lib, "DROP TRIGGER injected")
                if old is None:
                    output.unlink()
                else:
                    output.write_bytes(old)
                report("manual_restore_previous")
                self.assert_blocked_previous(lib, output, old, anchor, src)
                report("reentry_blocked")
                # The user (test fixture) independently reconciles to desired.
                self.reconcile_fixture(lib, output, operation)
                self.complete(src, lib, output, operation, anchor)
                report("after_explicit_reconciliation")

    def test_legacy_pending_publication_is_unknown(self):
        for restore in (False, True):
            with self.subTest(restore=restore):
                src, lib, output, old, anchor = self.prepare("old-pending-" + str(restore), "replace")
                self.sql(lib, """CREATE TRIGGER injected BEFORE DELETE ON pending_output
                    BEGIN SELECT RAISE(ABORT,'synthetic intent clear failure'); END""")
                with self.assertRaises(sqlite3.IntegrityError):
                    self.library.build_library(src, lib)
                published = output.read_bytes()
                self.sql(lib, "DROP TRIGGER injected")
                # Recreate exactly the previous candidate's four-column schema.
                self.sql(lib, "ALTER TABLE pending_output DROP COLUMN publication_token")
                if restore:
                    output.write_bytes(old)
                    with self.assertRaisesRegex(ValueError, "Pending Markdown publication is uncertain"):
                        self.library.build_library(src, lib)
                    self.assertEqual(self.pending_token(lib), "unknown")
                    self.assertEqual(output.read_bytes(), old)
                    self.assertEqual(len(self.pending(lib)), 1)
                    output.write_bytes(published)
                self.complete(src, lib, output, "replace", anchor)

    def test_legacy_index_is_readable_and_old_orphan_is_not_adopted(self):
        src, lib, output, old, anchor = self.prepare("legacy", "add")
        self.sql(lib, "DROP TABLE pending_output")
        self.assertEqual(self.library.verify_library(lib)["documents"], 1)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"unowned manual")
        with self.assertRaisesRegex(ValueError, "unowned Markdown"):
            self.library.build_library(src, lib)
        self.assertEqual(output.read_bytes(), b"unowned manual")
        output.unlink()
        self.complete(src, lib, output, "add", anchor)


if __name__ == "__main__":
    unittest.main()
