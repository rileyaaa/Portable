"""Protect synthetic non-library SQLite files before persistent configuration."""
import importlib.util
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).absolute().parents[1]
SCRIPT = Path('home/skills/pdf-library/scripts/pdf_library.py')
SAFETY = Path('home/skills/pdf/scripts/portable_safety.py')


class PdfLibraryDatabaseTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / 'tmp'
        for entry in (*reversed(scratch.parents), scratch):
            try:
                info = entry.lstat()
            except FileNotFoundError:
                continue
            self.assertFalse(stat.S_ISLNK(info.st_mode))
            self.assertFalse(getattr(info, 'st_file_attributes', 0) & 0x400)
        scratch.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix='pdf-database-', dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.package = Path(temporary.name) / 'synthetic package'
        self.package.mkdir()
        for name in ('codex.exe', 'env.ps1'):
            (self.package / name).write_bytes(b'synthetic marker, never executed')
        for relative in (SCRIPT, SAFETY):
            destination = self.package / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        spec = importlib.util.spec_from_file_location('synthetic_pdf_database', self.package / SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        with mock.patch.object(sys, 'dont_write_bytecode', True):
            spec.loader.exec_module(self.module)
        self.library = self.package / 'work/library'
        self.database = self.library / '_index.sqlite3'

    def prepare_database(self, statements, *, wal=False, application_id=0):
        self.library.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database)
        try:
            if wal:
                self.assertEqual(connection.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
            connection.execute('PRAGMA application_id=' + str(application_id))
            for statement in statements:
                connection.execute(statement)
            connection.commit()
        finally:
            connection.close()

    def assert_rejected_unchanged(self):
        before = self.database.read_bytes()
        with self.assertRaisesRegex(ValueError, 'unrelated SQLite|Not a PDF library'):
            connection = self.module._database(self.library, create=True)
            connection.close()  # Also close the unexpected successful baseline result.
        self.assertEqual(self.database.read_bytes(), before)

    def test_unowned_wal_table_is_rejected_before_journal_mode_change(self):
        self.prepare_database([
            'CREATE TABLE synthetic_user_data(value TEXT)',
            "INSERT INTO synthetic_user_data VALUES('preserve')",
            'PRAGMA user_version=27',
        ], wal=True)
        self.assert_rejected_unchanged()
        connection = sqlite3.connect(self.database.as_uri() + '?mode=ro', uri=True)
        try:
            self.assertEqual(connection.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
            self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], 27)
            self.assertEqual(connection.execute('SELECT value FROM synthetic_user_data').fetchall(), [('preserve',)])
        finally:
            connection.close()

    def test_unowned_view_only_database_is_not_adopted(self):
        self.prepare_database(['CREATE VIEW synthetic_user_view AS SELECT 42 AS value'])
        self.assert_rejected_unchanged()

    def test_foreign_application_id_is_rejected_without_mutation(self):
        self.prepare_database(['CREATE TABLE synthetic_user_data(value TEXT)'], wal=True, application_id=77)
        self.assert_rejected_unchanged()

    def test_fresh_database_receives_owned_schema(self):
        connection = self.module._database(self.library, create=True)
        try:
            self.assertEqual(connection.execute('PRAGMA application_id').fetchone()[0], self.module.APPLICATION_ID)
            self.assertEqual(connection.execute('PRAGMA journal_mode').fetchone()[0], 'delete')
            names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertEqual(names, {'documents', 'pages'})
        finally:
            connection.close()

    def test_existing_empty_database_can_complete_initialization(self):
        self.prepare_database([])
        connection = self.module._database(self.library, create=True)
        try:
            self.assertEqual(connection.execute('PRAGMA application_id').fetchone()[0], self.module.APPLICATION_ID)
        finally:
            connection.close()

    def test_owned_wal_library_keeps_records_when_reopened(self):
        connection = self.module._database(self.library, create=True)
        try:
            connection.execute('INSERT INTO documents VALUES(?,?,?,?,?)', ('synthetic.pdf', 'a', 'b', 'signature', 1))
            connection.commit()
        finally:
            connection.close()
        self.prepare_database([], wal=True, application_id=self.module.APPLICATION_ID)
        connection = self.module._database(self.library, create=True)
        try:
            self.assertEqual(connection.execute('PRAGMA journal_mode').fetchone()[0], 'delete')
            self.assertEqual(connection.execute('SELECT document FROM documents').fetchone()[0], 'synthetic.pdf')
        finally:
            connection.close()

    def test_read_only_library_does_not_change_persistent_journal_mode(self):
        connection = self.module._database(self.library, create=True)
        connection.close()
        self.prepare_database([], wal=True, application_id=self.module.APPLICATION_ID)
        before = self.database.read_bytes()
        connection = self.module._database(self.library)
        try:
            self.assertEqual(connection.execute('PRAGMA query_only').fetchone()[0], 1)
            self.assertEqual(connection.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
        finally:
            connection.close()
        self.assertEqual(self.database.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
