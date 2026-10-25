#!/usr/bin/env python3
"""Run an installed console_script through the bundled portable Python.

The Windows distlib .exe launchers under Lib/site-packages/bin embed the Python
absolute path present at installation time.  The .cmd shims in tool/bin call this
helper instead, so moving the whole Codex Portable directory keeps CLI entry
points working.
"""
from __future__ import annotations

import importlib.metadata
import re
import sys


def _canonical_name(name: str) -> str:
    lower = name.lower()
    if re.fullmatch(r"pip\d+(?:\.\d+)?", lower):
        return "pip"
    return lower


def _find_entry_point(name: str):
    wanted = _canonical_name(name)
    eps = importlib.metadata.entry_points()
    if hasattr(eps, "select"):
        candidates = eps.select(group="console_scripts")
    else:  # pragma: no cover - compatibility with older Python only
        candidates = eps.get("console_scripts", ())
    matches = [ep for ep in candidates if ep.name.lower() == wanted]
    if len(matches) != 1:
        raise SystemExit(f"portable-python-cli: expected exactly one console_script for {wanted!r}, found {len(matches)}")
    return matches[0]


def _package_path(root, value, *, file=False, within=None):
    """Validate lexically, then lstat ancestors before touching their targets."""
    from pathlib import Path
    import os
    import stat

    raw = Path(os.path.expandvars(os.path.expanduser(str(value))))
    if '..' in raw.parts:
        raise ValueError('Parent traversal is not permitted for packaging paths.')
    path = Path(os.path.abspath(raw))
    boundary = within or root
    if not path.is_relative_to(boundary):
        raise ValueError('Packaging path must remain inside ' + str(boundary))
    for name in path.relative_to(root).parts:
        if (name.endswith((' ', '.')) or re.search(r'[<>:"\\|?*\x00-\x1f]', name) or
                re.fullmatch(r'(?i)(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', name)):
            raise ValueError('Packaging path cannot be preserved safely on Windows.')
    for part in (*reversed(path.parents), path):
        try:
            info = part.lstat()
        except FileNotFoundError:
            if file:
                raise ValueError('Packaging input is missing: ' + str(path))
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Linked packaging path is not permitted.')
        if part == path and file:
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('Packaging input must be an ordinary single-link file.')
        elif not stat.S_ISDIR(info.st_mode):
            raise ValueError('Packaging directory is not an ordinary directory.')
    return path


def _pyinstaller_arguments(root, argv, backend, job):
    """Use the pinned upstream parser, including its spec argument separator."""
    split = argv.index('--') if '--' in argv else len(argv)
    cli, spec_args = argv[:split], argv[split:]
    parser = backend.generate_parser()
    parser.set_defaults(workpath=None, distpath=None, specpath=None)
    args = parser.parse_args(cli)
    is_spec = args.filenames[0].endswith('.spec')
    if is_spec:
        parser._forbid_options(args, group='makespec',
                               errmsg='makespec options not valid when a .spec file is given')
    for name in args.filenames:
        _package_path(root, name, file=True)
    work = _package_path(root, args.workpath or job / 'build', within=root / 'tmp')
    output = _package_path(root, args.distpath or root / 'work' / 'dist', within=root / 'work')
    additions = ['--workpath', str(work), '--distpath', str(output)]
    if not is_spec:
        spec = _package_path(root, args.specpath or root / 'work' / 'spec', within=root / 'work')
        additions += ['--specpath', str(spec)]
    # Last canonical options win over abbreviations, repeated options or values
    # containing environment variables. Keep the spec's own arguments untouched.
    return [*cli, *additions, *spec_args]


def _load_pyinstaller(root):
    import importlib

    site = root / 'tool' / 'python' / 'Lib' / 'site-packages'
    for name in ('PyInstaller/__init__.py', 'PyInstaller/__main__.py'):
        _package_path(root, site / name, file=True)
    module = importlib.import_module('PyInstaller.__main__')
    if _package_path(root, module.__file__, file=True) != site / 'PyInstaller' / '__main__.py':
        raise RuntimeError('Refusing a PyInstaller module outside the bundled runtime.')
    if module.__version__ != '6.21.0':
        raise RuntimeError('Unexpected PyInstaller version; review the runtime before upgrading.')
    return module


def _run_pyinstaller(argv):
    """Restore build support without reviving old absolute-path EXE launchers.

    This is path/state routing, NOT a sandbox. A spec or hook is executable code
    and must be trusted. It may override settings inside its own Python code.
    """
    from pathlib import Path
    import os
    import tempfile

    root = Path(__file__).absolute().parents[2]
    _package_path(root, root)
    _package_path(root, Path(__file__).absolute(), file=True)
    for name in ('env.ps1', 'codex.exe', 'tool/python/python.exe'):
        _package_path(root, root / name, file=True)
    if os.path.normcase(os.path.abspath(sys.executable)) != os.path.normcase(str(root / 'tool/python/python.exe')):
        raise RuntimeError('PyInstaller must use the bundled Windows Python interpreter.')
    _package_path(root, Path.cwd())
    scratch = _package_path(root, root / 'tmp')
    cache = _package_path(root, root / 'cache' / 'pyinstaller')
    scratch.mkdir(exist_ok=True)
    _package_path(root, scratch)
    saved_env, saved_temp = dict(os.environ), tempfile.tempdir
    saved_bytecode = sys.dont_write_bytecode
    try:
        with tempfile.TemporaryDirectory(prefix='pyinstaller-', dir=scratch) as temporary:
            job = Path(temporary)
            temp = job / 'temp'
            temp.mkdir()
            for name in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', '__PYVENV_LAUNCHER__'):
                os.environ.pop(name, None)
            for name in ('TEMP', 'TMP', 'TMPDIR'):
                os.environ[name] = str(temp)
            for name in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME'):
                os.environ[name] = str(job / 'home')
            os.environ['XDG_CACHE_HOME'] = str(cache)
            os.environ['PYINSTALLER_CONFIG_DIR'] = str(cache)
            os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
            os.environ['PYTHONNOUSERSITE'] = '1'
            tempfile.tempdir = str(temp)
            sys.dont_write_bytecode = True
            backend = _load_pyinstaller(root)
            arguments = _pyinstaller_arguments(root, list(argv), backend, job)
            # Invalid arguments/help/version cannot create persistent output.
            _package_path(root, cache)
            cache.mkdir(parents=True, exist_ok=True)
            _package_path(root, cache)
            backend.run(arguments)
            return 0
    finally:
        tempfile.tempdir = saved_temp
        sys.dont_write_bytecode = saved_bytecode
        os.environ.clear()
        os.environ.update(saved_env)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: portable-python-cli.py <console-script-name> [args...]", file=sys.stderr)
        return 2
    requested = sys.argv[1]
    if _canonical_name(requested) == "pyinstaller":
        try:
            return _run_pyinstaller(sys.argv[2:])
        except (OSError, ValueError, RuntimeError) as error:
            print(f"portable-python-cli: {error}", file=sys.stderr)
            return 2
    ep = _find_entry_point(requested)
    sys.argv = [requested, *sys.argv[2:]]
    result = ep.load()()
    return int(result) if isinstance(result, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
