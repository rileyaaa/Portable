"""Exercise packaging argument/state routing without compiling or executing EXEs."""
import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).absolute().parents[1]
ENTRY = Path('tool/bin/portable-python-cli.py')


class Parser(argparse.ArgumentParser):
    def _forbid_options(self, args, group, errmsg):
        # Mirror the pinned parser's makespec restriction, not the build engine.
        for name in ('specpath', 'name'):
            if getattr(args, name) != self.get_default(name):
                raise SystemExit(errmsg)


class Backend:
    __version__ = '6.21.0'

    def __init__(self):
        self.calls = []
        self.error = None

    def generate_parser(self):
        parser = Parser()
        for name in ('workpath', 'distpath', 'specpath', 'name'):
            parser.add_argument('--' + name)
        parser.add_argument('--version', action='version', version=self.__version__)
        parser.add_argument('--onefile', action='store_true')
        parser.add_argument('filenames', nargs='+')
        return parser

    def run(self, args):
        self.calls.append((list(args), dict(os.environ), tempfile.gettempdir()))
        if self.error:
            raise self.error


class PyInstallerPortableTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / 'tmp'
        scratch.mkdir(exist_ok=True)
        fixture = tempfile.TemporaryDirectory(prefix='pyinstaller-routing-', dir=scratch)
        self.addCleanup(fixture.cleanup)
        self.base = Path(fixture.name)
        self.root = self.base / '\u4e2d\u6587 Package'
        self.root.mkdir()
        for name in (ENTRY, 'env.ps1', 'codex.exe', 'tool/python/python.exe'):
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if name == ENTRY:
                shutil.copyfile(ROOT / ENTRY, dest)
            else:
                dest.write_bytes(b'Synthetic marker; never executable')
        self.project = self.root / 'work/project'
        self.project.mkdir(parents=True)
        self.script = self.project / 'app.py'
        self.script.write_text('# Synthetic source; never compiled\n', encoding='utf-8')
        self.spec = self.project / 'app.spec'
        self.spec.write_text('# Synthetic spec; never executed\n', encoding='utf-8')
        spec = importlib.util.spec_from_file_location('synthetic_packaging_entry', self.root / ENTRY)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.backend = Backend()
        self.cwd = Path.cwd()
        self.addCleanup(os.chdir, self.cwd)
        os.chdir(self.project)

    def run_tool(self, args):
        with mock.patch.object(sys, 'executable', str(self.root / 'tool/python/python.exe')), \
             mock.patch.object(self.module, '_load_pyinstaller', return_value=self.backend):
            return self.module._run_pyinstaller(args)

    def parsed(self):
        argv = self.backend.calls[-1][0]
        pos = argv.index('--') if '--' in argv else len(argv)
        return self.backend.generate_parser().parse_args(argv[:pos]), argv[pos:]

    def assert_no_staging(self):
        self.assertFalse(list((self.root / 'tmp').glob('pyinstaller-*')))

    def test_defaults_and_environment_are_relocated_and_restored(self):
        inherited = {'PYTHONPATH': str(self.base / 'host'), 'PYTHONHOME': 'old-python',
                     'PYINSTALLER_CONFIG_DIR': 'old-cache', 'TMP': 'old-temp',
                     'CODEX_INSTALL_DIR': str(self.base / 'old-package')}
        with mock.patch.dict(os.environ, inherited):
            before = dict(os.environ)
            self.assertEqual(self.run_tool(['--onefile', 'app.py']), 0)
            self.assertEqual(dict(os.environ), before)
        args, tail = self.parsed()
        self.assertEqual(Path(args.distpath), self.root / 'work/dist')
        self.assertEqual(Path(args.specpath), self.root / 'work/spec')
        self.assertTrue(Path(args.workpath).is_relative_to(self.root / 'tmp'))
        self.assertEqual(tail, [])
        env = self.backend.calls[0][1]
        self.assertEqual(env['PYINSTALLER_CONFIG_DIR'], str(self.root / 'cache/pyinstaller'))
        self.assertNotIn('PYTHONPATH', env)
        self.assertNotIn('PYTHONHOME', env)
        for name in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP', 'TMPDIR'):
            self.assertTrue(Path(env[name]).is_relative_to(self.root / 'tmp'))
        self.assert_no_staging()
        self.assertFalse((self.root / 'work/dist').exists())  # Stub never compiles.

    def test_explicit_equal_abbreviated_and_repeated_paths(self):
        for form in ('separate', 'equals', 'abbreviated'):
            with self.subTest(form=form):
                path = str(self.root / 'tmp/user-build')
                option = ['--workpath', path] if form == 'separate' else [('--workp' if form == 'abbreviated' else '--workpath') + '=' + path]
                self.run_tool(['app.py', '--workpath', str(self.base / 'superseded'), *option,
                               '--distpath', str(self.root / 'work/exports')])
                args, _ = self.parsed()
                self.assertEqual(Path(args.workpath), self.root / 'tmp/user-build')
                self.assertEqual(Path(args.distpath), self.root / 'work/exports')

    def test_spec_arguments_stay_after_separator(self):
        tail = ['--', '--workpath', 'spec-owned-argument', 'value with spaces']
        self.run_tool(['app.spec', *tail])
        args, actual = self.parsed()
        self.assertEqual(actual, tail)
        self.assertIsNone(args.specpath)
        self.assertNotIn('--specpath', self.backend.calls[-1][0])

    def test_spec_preserves_upstream_makespec_restrictions(self):
        with self.assertRaises(SystemExit):
            self.run_tool(['app.spec', '--specpath', str(self.root / 'work/spec')])
        self.assertEqual(self.backend.calls, [])
        self.assert_no_staging()

    def test_external_inputs_and_outputs_fail_before_backend(self):
        external = self.base / 'outside.py'
        external.write_text('# not executed\n')
        cases = [[str(external)], ['app.py', '--distpath', str(self.base / 'out')],
                 ['app.py', '--workpath', str(self.root / 'work/build')],
                 ['app.py', '--specpath', str(self.root / 'home/spec')],
                 ['../project/app.py']]
        for args in cases:
            with self.subTest(args=args), self.assertRaises((ValueError, OSError)):
                self.run_tool(args)
        self.assertEqual(self.backend.calls, [])
        self.assertFalse((self.base / 'out').exists())
        self.assertFalse((self.root / 'cache').exists())
        self.assert_no_staging()

    def test_symlink_input_and_linked_ancestor_are_rejected(self):
        link = self.project / 'alias'
        try:
            link.symlink_to(self.project, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(str(error))
        with self.assertRaises(ValueError):
            self.run_tool([str(link / 'app.py')])
        link.unlink()
        link.symlink_to(self.script)
        with self.assertRaises(ValueError):
            self.run_tool([str(link)])
        self.assertEqual(self.backend.calls, [])

    def test_hardlinked_input_is_rejected(self):
        alias = self.project / 'hard.py'
        os.link(self.script, alias)
        with self.assertRaises(ValueError):
            self.run_tool([str(alias)])
        self.assertEqual(self.backend.calls, [])

    def test_linked_cache_is_rejected_before_tmp_creation(self):
        outside = self.base / 'external-cache'
        outside.mkdir()
        cache = self.root / 'cache'
        try:
            cache.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(str(error))
        with self.assertRaises(ValueError):
            self.run_tool(['app.py'])
        self.assertFalse((self.root / 'tmp').exists())
        self.assertEqual(list(outside.iterdir()), [])

    def test_file_or_dangling_tmp_is_rejected(self):
        scratch = self.root / 'tmp'
        scratch.write_bytes(b'preserve')
        with self.assertRaises(ValueError):
            self.run_tool(['app.py'])
        self.assertEqual(scratch.read_bytes(), b'preserve')
        scratch.unlink()
        try:
            scratch.symlink_to(self.base / 'missing', target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(str(error))
        with self.assertRaises(ValueError):
            self.run_tool(['app.py'])
        self.assertFalse((self.base / 'missing').exists())

    def test_host_python_and_outside_cwd_are_rejected(self):
        with mock.patch.object(sys, 'executable', str(self.base / 'host-python')):
            with self.assertRaises(RuntimeError):
                self.module._run_pyinstaller(['app.py'])
        os.chdir(self.base)
        with self.assertRaises(ValueError):
            self.run_tool([str(self.script)])
        self.assertEqual(self.backend.calls, [])
        self.assertFalse((self.root / 'tmp').exists())

    def test_missing_input_preserves_files(self):
        with self.assertRaises(ValueError):
            self.run_tool(['missing.py'])
        self.assertEqual(self.backend.calls, [])
        self.assert_no_staging()

    def test_help_version_and_invalid_arguments_do_not_create_persistent_output(self):
        for args, exitcode in ((['--help'], 0), (['--version'], 0), (['--unknown'], 2)):
            with self.subTest(args=args), contextlib.redirect_stdout(io.StringIO()), \
                 contextlib.redirect_stderr(io.StringIO()):
                before = dict(os.environ)
                with self.assertRaises(SystemExit) as error:
                    self.run_tool(args)
                self.assertEqual(error.exception.code, exitcode)
                self.assertEqual(dict(os.environ), before)
                self.assertFalse((self.root / 'cache').exists())
                self.assert_no_staging()
        self.assertEqual(self.backend.calls, [])

    def test_backend_failure_cleans_only_current_staging_and_restores_state(self):
        scratch = self.root / 'tmp'
        scratch.mkdir()
        sentinel = scratch / 'keep.txt'
        sentinel.write_bytes(b'keep')
        cache = self.root / 'cache/pyinstaller'
        cache.mkdir(parents=True)
        (cache / 'keep.txt').write_bytes(b'cache')
        self.backend.error = OSError('synthetic build failure; no compilation')
        before, temp, bytecode = dict(os.environ), tempfile.tempdir, sys.dont_write_bytecode
        with self.assertRaises(OSError):
            self.run_tool(['app.py'])
        self.assertEqual(dict(os.environ), before)
        self.assertEqual(tempfile.tempdir, temp)
        self.assertEqual(sys.dont_write_bytecode, bytecode)
        self.assertEqual(list(scratch.iterdir()), [sentinel])
        self.assertEqual((cache / 'keep.txt').read_bytes(), b'cache')

    def test_actual_move_ignores_stale_root(self):
        os.chdir(self.base)
        old = self.root
        self.root = self.base / '\u642c\u8fc1 New Package'
        old.rename(self.root)
        os.chdir(self.root / 'work/project')
        self.module.__file__ = str(self.root / ENTRY)
        with mock.patch.dict(os.environ, {'CODEX_INSTALL_DIR': str(old)}):
            self.run_tool(['app.py'])
        args, _ = self.parsed()
        self.assertEqual(Path(args.distpath), self.root / 'work/dist')
        self.assertFalse(old.exists())

    def test_other_console_scripts_retain_entrypoint_semantics(self):
        callback = mock.Mock(return_value=7)
        ep = mock.Mock()
        ep.load.return_value = callback
        with mock.patch.object(self.module, '_find_entry_point', return_value=ep), \
             mock.patch.object(sys, 'argv', ['portable-python-cli.py', 'pip', '--version']):
            self.assertEqual(self.module.main(), 7)
            self.assertEqual(sys.argv, ['pip', '--version'])
        callback.assert_called_once_with()

    def test_packaging_alias_uses_dedicated_path_and_reports_failure(self):
        with mock.patch.object(sys, 'argv', ['portable-python-cli.py', 'PyInstaller', 'app.py']), \
             mock.patch.object(self.module, '_run_pyinstaller', side_effect=ValueError('synthetic')), \
             mock.patch.object(self.module, '_find_entry_point', side_effect=AssertionError('Unexpected generic entry')), \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.module.main(), 2)

    def test_cmd_matches_current_generator_and_restored_pins_are_present(self):
        spec = importlib.util.spec_from_file_location('shim_generator', ROOT / 'tool/refresh-python-cli-shims.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual((ROOT / 'tool/bin/pyinstaller.cmd').read_bytes(), module.render_cmd('pyinstaller'))
        pins = (ROOT / 'tool/python-packages.in.txt').read_text()
        for requirement in ('pyinstaller==6.21.0', 'pyinstaller-hooks-contrib==2026.6',
                            'altgraph==0.17.5', 'pefile==2024.8.26',
                            'pywin32-ctypes==0.2.3', 'setuptools==82.0.1'):
            self.assertIn(requirement, pins.splitlines())


    def test_windows_aliases_and_ads_are_rejected_before_creating_outputs(self):
        for name in ('NUL', 'con.txt', 'result:stream', 'trailing.', 'space ', 'a*b'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.run_tool(['app.py', '--distpath', str(self.root / 'work' / name)])
        self.assertEqual(self.backend.calls, [])
        self.assertFalse((self.root / 'cache').exists())

    def test_manifest_only_restores_packaging_closure(self):
        manifest = json.loads((ROOT / 'tool/python-build-manifest.json').read_text())
        self.assertEqual(manifest['source_commit'], 'fcaf45e5dfe4c97f096475f211a423b6d882c4ae')
        self.assertEqual(len(manifest['objects']), 18)
        paths = [entry['path'] for entry in manifest['objects']]
        self.assertEqual(len(paths), len(set(paths)))
        for entry in manifest['objects']:
            self.assertTrue(entry['path'].startswith('tool/python/Lib/site-packages/'))
            self.assertRegex(entry['sha'], r'^[0-9a-f]{40}$')
            self.assertNotIn('__pycache__', entry['path'])
            self.assertNotIn('/packaging', entry['path'])
        pins = (ROOT / 'tool/python-packages.in.txt').read_text().splitlines()
        for name, version in manifest['packages'].items():
            self.assertIn(name + '==' + version, pins)


if __name__ == '__main__':
    unittest.main()
