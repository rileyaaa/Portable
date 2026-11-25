"""Protect synthetic non-library SQLite files before persistent configuration."""
from contextlib import closing
import importlib.util
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import subprocess
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
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

    def test_search_snippet_uses_original_offsets_and_sqlite_case_rules(self):
        text = "\u00df" * 300 + " NEEDLE SS \u4e2d\u6587 _literal% \\path"
        connection = self.module._database(self.library, create=True)
        try:
            connection.execute(
                "INSERT INTO documents VALUES(?,?,?,?,?)",
                ("synthetic.pdf", "a", "b", "signature", 1),
            )
            connection.execute(
                "INSERT INTO pages(document,page,markdown) VALUES(?,?,?)",
                ("synthetic.pdf", 1, text),
            )
            connection.commit()
        finally:
            connection.close()
        for query, expected in (
            ("needle", "NEEDLE"), ("ss", "SS"), ("\u4e2d\u6587", "\u4e2d\u6587"),
            ("_literal%", "_literal%"), ("\\path", "\\path"), ("needle ss", "NEEDLE"),
        ):
            with self.subTest(query=query):
                hits = self.module.search_library(self.library, query, max_chars=80)
                self.assertEqual(len(hits), 1)
                self.assertEqual(hits[0]["page"], 1)
                self.assertIn(expected, hits[0]["text"])
                self.assertLessEqual(len(hits[0]["text"]), 80)
                self.assertTrue(hits[0]["truncated"])
        self.assertEqual(self.module.search_library(self.library, "SSS"), [])
        with self.assertRaises(ValueError):
            self.module.search_library(self.library, "needle\x00suffix")

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


    def test_database_snapshot_uses_owned_inherited_scratch_and_cleans_up(self):
        self.prepare_database([], application_id=self.module.APPLICATION_ID)
        scratch = self.package / 'tmp'
        scratch.mkdir()
        sentinel = scratch / 'unrelated.txt'
        sentinel.write_bytes(b'keep')
        before = self.database.read_bytes()
        owned = []
        real_copy = self.module.shutil.copyfile

        def copy(source, target, *args, **kwargs):
            target = Path(target)
            self.assertEqual(target.parent.parent, scratch)
            self.assertTrue(target.parent.name.startswith('pdf-ownership-'))
            owned.append(target.parent)
            return real_copy(source, target, *args, **kwargs)

        with mock.patch.object(self.module.tempfile, 'TemporaryDirectory',
                               side_effect=AssertionError('legacy private ACL directory')), \
                mock.patch.object(self.module.shutil, 'copyfile', side_effect=copy):
            with closing(self.module._database(self.library)) as connection:
                self.assertEqual(connection.execute('PRAGMA query_only').fetchone()[0], 1)
        self.assertEqual(len(owned), 1)
        self.assertFalse(owned[0].exists())
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(list(scratch.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b'keep')

    def test_scratch_failure_cleans_only_owned_directory(self):
        scratch = self.package / 'tmp'
        scratch.mkdir()
        sentinel = scratch / 'unrelated.txt'
        sentinel.write_bytes(b'keep')
        with self.assertRaisesRegex(OSError, 'synthetic task failure'):
            with self.module._scratch_directory(scratch, 'pdf-ownership-') as staging:
                self.assertEqual(staging.parent, scratch)
                (staging / 'snapshot').write_bytes(b'temporary')
                raise OSError('synthetic task failure')
        self.assertEqual(list(scratch.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b'keep')

    def test_atomic_write_stages_only_in_package_tmp(self):
        output = self.library / 'manuals' / 'synthetic.md'
        created = []
        actual = self.module.tempfile.mkstemp

        def capture(*args, **kwargs):
            result = actual(*args, **kwargs)
            created.append(Path(result[1]))
            return result

        with mock.patch.object(self.module.tempfile, 'mkstemp', capture):
            self.module._write(output, 'synthetic \u4e2d\u6587 markdown\n')
        self.assertEqual(output.read_bytes(), 'synthetic \u4e2d\u6587 markdown\n'.encode())
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].parent, self.package / 'tmp')
        self.assertFalse(created[0].exists())

    def test_linked_write_tmp_is_rejected_before_output_creation(self):
        elsewhere = self.package.parent / 'synthetic unrelated directory'
        elsewhere.mkdir()
        sentinel = elsewhere / 'keep.txt'
        sentinel.write_bytes(b'keep')
        scratch = self.package / 'tmp'
        try:
            scratch.symlink_to(elsewhere, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f'Symlinks unavailable: {error}')
        output = self.library / 'manuals' / 'synthetic.md'
        with mock.patch.object(self.module.tempfile, 'mkstemp',
                               wraps=self.module.tempfile.mkstemp) as create_temp:
            with self.assertRaises(self.module._safety.PortablePathError):
                self.module._write(output, 'synthetic replacement')
            create_temp.assert_not_called()
        self.assertFalse(self.library.exists())
        self.assertEqual(sentinel.read_bytes(), b'keep')
        self.assertEqual(list(elsewhere.iterdir()), [sentinel])

    def test_file_write_tmp_is_rejected_and_original_is_preserved(self):
        scratch = self.package / 'tmp'
        scratch.write_bytes(b'not a directory')
        output = self.library / 'synthetic.md'
        output.parent.mkdir(parents=True)
        output.write_bytes(b'original')
        with mock.patch.object(self.module.tempfile, 'mkstemp',
                               wraps=self.module.tempfile.mkstemp) as create_temp:
            with self.assertRaises((OSError, self.module._safety.PortablePathError)):
                self.module._write(output, 'synthetic replacement')
            create_temp.assert_not_called()
        self.assertEqual(output.read_bytes(), b'original')
        self.assertEqual(scratch.read_bytes(), b'not a directory')

    def test_write_replace_failure_preserves_output_and_unrelated_tmp(self):
        scratch = self.package / 'tmp'
        scratch.mkdir()
        sentinel = scratch / 'unrelated.txt'
        sentinel.write_bytes(b'keep')
        output = self.library / 'synthetic.md'
        output.parent.mkdir(parents=True)
        output.write_bytes(b'original')
        with mock.patch.object(self.module.os, 'replace', side_effect=OSError('synthetic failure')):
            with self.assertRaisesRegex(OSError, 'synthetic failure'):
                self.module._write(output, 'synthetic replacement')
        self.assertEqual(output.read_bytes(), b'original')
        self.assertEqual(sentinel.read_bytes(), b'keep')
        self.assertEqual(list(scratch.iterdir()), [sentinel])
        self.assertEqual(list(output.parent.iterdir()), [output])

    def test_write_encoding_failure_preserves_output_and_unrelated_tmp(self):
        scratch = self.package / 'tmp'
        scratch.mkdir()
        sentinel = scratch / 'unrelated.txt'
        sentinel.write_bytes(b'keep')
        output = self.library / 'synthetic.md'
        output.parent.mkdir(parents=True)
        output.write_bytes(b'original')
        with self.assertRaises(UnicodeEncodeError):
            self.module._write(output, 'invalid surrogate ' + chr(0xD800))
        self.assertEqual(output.read_bytes(), b'original')
        self.assertEqual(sentinel.read_bytes(), b'keep')
        self.assertEqual(list(scratch.iterdir()), [sentinel])
        self.assertEqual(list(output.parent.iterdir()), [output])


    def _synthetic_pdf(self):
        source = self.package / 'work/source'
        source.mkdir(parents=True, exist_ok=True)
        pdf = source / 'synthetic.pdf'
        pdf.write_bytes(b'synthetic PDF fixture; not parsed or executed')
        return source, pdf

    def _build_with_stub_renderer(self, source, callback=None):
        page = dict(page=1, markdown='## PDF 第 1 页\n\nSynthetic text\n',
                    text_total=14, text_matched=14, code_total=0, code_matched=0,
                    ocr_status='not-flagged', ocr_reason='synthetic', images=0,
                    supplement_lines=0)

        def render(_file, **_kwargs):
            if callback is not None:
                callback()
            return [page]

        fake_pdf = SimpleNamespace(VersionBind='fixture')
        fake_formatter = SimpleNamespace(__version__='fixture')
        with mock.patch.object(self.module, '_dependencies', return_value=(fake_pdf, fake_formatter)), \
             mock.patch.object(self.module, '_render_document', side_effect=render):
            return self.module.build_library(source, self.library)

    def test_new_markdown_arriving_during_render_is_preserved(self):
        source, _ = self._synthetic_pdf()
        output = self.library / 'manuals/synthetic.md'
        original = b'User-created Markdown during conversion'

        def user_create():
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(original)

        with self.assertRaisesRegex(ValueError, 'unowned Markdown'):
            self._build_with_stub_renderer(source, user_create)
        self.assertEqual(output.read_bytes(), original)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM documents').fetchone()[0], 0)

    def test_owned_markdown_modified_during_render_is_preserved(self):
        source, pdf = self._synthetic_pdf()
        self._build_with_stub_renderer(source)
        output = self.library / 'manuals/synthetic.md'
        old = output.read_bytes()
        pdf.write_bytes(b'changed synthetic source to request regeneration')
        manual_edit = b'User-edited Markdown while conversion ran'
        with self.assertRaisesRegex(ValueError, 'removed/edited'):
            self._build_with_stub_renderer(source, lambda: output.write_bytes(manual_edit))
        self.assertNotEqual(old, manual_edit)
        self.assertEqual(output.read_bytes(), manual_edit)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute('SELECT output_sha FROM documents').fetchone()[0],
                             self.module.hashlib.sha256(old).hexdigest())

    def test_owned_markdown_modified_after_staging_is_preserved(self):
        source, pdf = self._synthetic_pdf()
        self._build_with_stub_renderer(source)
        output = self.library / 'manuals/synthetic.md'
        pdf.write_bytes(b'changed synthetic source to request regeneration')
        manual_edit = b'Last-moment user Markdown edit'
        original_mkstemp = self.module.tempfile.mkstemp
        called = False

        def mutate_during_stage(*args, **kwargs):
            nonlocal called
            if not called and kwargs.get('prefix') == '.pdf-library-':
                called = True
                output.write_bytes(manual_edit)
            return original_mkstemp(*args, **kwargs)

        with mock.patch.object(self.module.tempfile, 'mkstemp', side_effect=mutate_during_stage):
            with self.assertRaisesRegex(ValueError, 'removed/edited'):
                self._build_with_stub_renderer(source)
        self.assertTrue(called)
        self.assertEqual(output.read_bytes(), manual_edit)
        self.assertFalse(list((self.package / 'tmp').glob('.pdf-library-*')))

    def test_new_unowned_markdown_created_during_staging_is_preserved(self):
        source, _ = self._synthetic_pdf()
        output = self.library / 'manuals/synthetic.md'
        user_content = b'Unowned Markdown added at staging time'
        real_mkstemp = self.module.tempfile.mkstemp
        changed = False

        def create_during_stage(*args, **kwargs):
            nonlocal changed
            if not changed and kwargs.get('prefix') == '.pdf-library-':
                changed = True
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(user_content)
            return real_mkstemp(*args, **kwargs)

        with mock.patch.object(self.module.tempfile, 'mkstemp', side_effect=create_during_stage):
            with self.assertRaisesRegex(ValueError, 'unowned Markdown'):
                self._build_with_stub_renderer(source)
        self.assertTrue(changed)
        self.assertEqual(output.read_bytes(), user_content)
        self.assertFalse(list((self.package / 'tmp').glob('.pdf-library-*')))

    def test_owned_markdown_removed_during_staging_is_not_recreated(self):
        source, pdf = self._synthetic_pdf()
        self._build_with_stub_renderer(source)
        output = self.library / 'manuals/synthetic.md'
        pdf.write_bytes(b'changed PDF fixture')
        real_mkstemp = self.module.tempfile.mkstemp
        changed = False

        def remove_during_stage(*args, **kwargs):
            nonlocal changed
            if not changed and kwargs.get('prefix') == '.pdf-library-':
                changed = True
                output.unlink()
            return real_mkstemp(*args, **kwargs)

        with mock.patch.object(self.module.tempfile, 'mkstemp', side_effect=remove_during_stage):
            with self.assertRaisesRegex(ValueError, 'removed/edited'):
                self._build_with_stub_renderer(source)
        self.assertTrue(changed)
        self.assertFalse(output.exists())
        self.assertFalse(list((self.package / 'tmp').glob('.pdf-library-*')))
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM documents').fetchone()[0], 1)

    def test_removed_source_does_not_delete_later_user_edits(self):
        source, pdf = self._synthetic_pdf()
        self._build_with_stub_renderer(source)
        output = self.library / 'manuals/synthetic.md'
        pdf.unlink()
        manual_edit = b'User-edited removed-source Markdown'
        original_check = self.module._check_owned_output
        checks = 0

        def edit_after_first_check(*args, **kwargs):
            nonlocal checks
            checks += 1
            original_check(*args, **kwargs)
            if checks == 1:
                output.write_bytes(manual_edit)

        with mock.patch.object(self.module, '_check_owned_output', side_effect=edit_after_first_check):
            with self.assertRaisesRegex(ValueError, 'removed/edited'):
                self._build_with_stub_renderer(source)
        self.assertGreaterEqual(checks, 2)
        self.assertEqual(output.read_bytes(), manual_edit)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM documents').fetchone()[0], 1)

    def test_normal_synthetic_incremental_update_and_removal_still_work(self):
        source, pdf = self._synthetic_pdf()
        self.assertEqual(self._build_with_stub_renderer(source)['documents'], 1)
        self.assertEqual(self._build_with_stub_renderer(source)['reused'], 1)
        pdf.write_bytes(b'changed synthetic source')
        self.assertEqual(self._build_with_stub_renderer(source)['reused'], 0)
        pdf.unlink()
        summary = self._build_with_stub_renderer(source)
        self.assertEqual(summary['removed'], 1)
        self.assertEqual(summary['documents'], 0)
        self.assertFalse((self.library / 'manuals/synthetic.md').exists())



    def test_verify_export_and_reuse_reject_inconsistent_index_pages(self):
        source, _ = self._synthetic_pdf()
        (source / 'another.pdf').write_bytes(b'second synthetic PDF fixture')
        self.assertEqual(self._build_with_stub_renderer(source)['documents'], 2)
        self.assertTrue(self.module.verify_library(self.library)['strict_ok'])
        self.assertEqual(self._build_with_stub_renderer(source)['reused'], 2)
        original = self.database.read_bytes()
        outputs = {path: path.read_bytes() for path in (self.library / 'manuals').glob('*.md')}
        self.assertEqual(len(outputs), 2)
        cases = (
            ("DELETE FROM pages WHERE document='synthetic.pdf'", 'Indexed page mapping'),
            ("UPDATE pages SET markdown='unrelated text' WHERE document='synthetic.pdf'",
             'Indexed page content'),
            ("UPDATE pages SET page=2 WHERE document='synthetic.pdf'", 'Indexed page mapping'),
            ("UPDATE pages SET document='unmanaged.pdf' WHERE document='synthetic.pdf'",
             'orphan pages'),
        )
        for number, (sql, message) in enumerate(cases):
            with self.subTest(sql=sql):
                self.database.write_bytes(original)
                with closing(sqlite3.connect(self.database)) as connection:
                    connection.execute(sql)
                    connection.commit()
                before = self.database.read_bytes()
                # All four invalid index states used to leave the Markdown
                # hashes/headings intact and pass the old strict summary.
                with closing(self.module._database(self.library)) as connection:
                    self.assertTrue(self.module._summary(connection)['strict_ok'])
                with self.assertRaisesRegex(ValueError, message):
                    self.module.verify_library(self.library)
                destination = self.package / 'work' / f'invalid-{number}.zip'
                with self.assertRaisesRegex(ValueError, message):
                    self.module.export_library(self.library, destination)
                self.assertFalse(destination.exists())
                self.assertEqual(self.database.read_bytes(), before)
                with self.assertRaisesRegex(ValueError, message):
                    self._build_with_stub_renderer(source)
                for path, content in outputs.items():
                    self.assertEqual(path.read_bytes(), content)
        self.database.write_bytes(original)
        self.assertTrue(self.module.verify_library(self.library)['strict_ok'])
        self.assertEqual(self._build_with_stub_renderer(source)['reused'], 2)

    def test_rejected_crashed_wal_database_keeps_all_original_files(self):
        self.library.mkdir(parents=True)
        code = "import sqlite3,os,sys; c=sqlite3.connect(sys.argv[1]); c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA wal_autocheckpoint=0'); c.execute('CREATE TABLE user_data(x)'); c.execute('INSERT INTO user_data VALUES(7)'); c.commit(); os._exit(0)"
        subprocess.run([sys.executable, '-B', '-c', code, str(self.database)], check=True)
        before = {p.name:p.read_bytes() for p in self.library.iterdir()}
        for create in (True, False):
            with self.assertRaises(ValueError): self.module._database(self.library, create=create)
            self.assertEqual({p.name:p.read_bytes() for p in self.library.iterdir()}, before)


if __name__ == '__main__':
    unittest.main()
