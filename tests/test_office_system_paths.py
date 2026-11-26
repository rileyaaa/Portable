"""Office system-path regression: synthetic files only, no Office execution."""
import contextlib
import ctypes
from ctypes import wintypes
import importlib
import importlib.util
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest import mock
import uuid

ROOT = Path(__file__).absolute().parents[1]
SKILLS = ("docx", "pptx", "xlsx")
LEAVES = ("helpers/__init__.py", "soffice.py")
SYSTEM_KEYS = {"SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "PATHEXT"}
STATE = {"HOME": "home-runtime", "USERPROFILE": "home-runtime",
         "APPDATA": "appdata", "LOCALAPPDATA": "localappdata",
         "PROGRAMDATA": "programdata", "ALLUSERSPROFILE": "programdata",
         "PUBLIC": "public", "XDG_CACHE_HOME": "home-runtime/.cache",
         "XDG_CONFIG_HOME": "home-runtime/.config",
         "XDG_DATA_HOME": "home-runtime/.local/share",
         "XDG_STATE_HOME": "home-runtime/.local/state"}
OFFICE_PATH = ("tool/office/libreoffice/program", "tool/bin", "tool/python")
HELPER_PATH = ("tool/git/cmd", "tool/git/bin", "tool/git/usr/bin", OFFICE_PATH[0],
               "tool/pdf/poppler/Library/bin", "tool/pdf/poppler/bin", *OFFICE_PATH[1:])


def plain(path, directory):
    info = path.lstat()
    if getattr(info, "st_file_attributes", 0) & 0x400 or not (
        stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1
    ):
        raise RuntimeError("Unsafe synthetic test path")


def expected_windows():
    # Independent OS query, never an inherited system path.
    if os.name != "nt":
        return None
    query = ctypes.windll.kernel32.GetSystemWindowsDirectoryW
    query.argtypes = [wintypes.LPWSTR, wintypes.UINT]
    query.restype = wintypes.UINT
    buf = ctypes.create_unicode_buffer(32768)
    if not 0 < query(buf, len(buf)) < len(buf):
        raise RuntimeError("Cannot obtain Windows expectation")
    return Path(buf.value)


class OfficeSystemPathTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(sys.dont_write_bytecode)
        if os.name == "nt":
            self.assertEqual(Path(sys.executable).resolve(), ROOT / "tool/python/python.exe")
        for p in (*reversed(ROOT.parents), ROOT):
            plain(p, True)
        tmp = ROOT / "tmp"
        try:
            plain(tmp, True)
        except FileNotFoundError:
            tmp.mkdir()
            plain(tmp, True)
        self.base = tmp / ("office-system-" + uuid.uuid4().hex)
        self.base.mkdir()
        self.addCleanup(shutil.rmtree, self.base)
        self.package = self.base / "portable package"
        self.package.mkdir()
        self.outside = self.base / "outside synthetic package"
        self.outside.mkdir()
        (self.outside / "sentinel").write_bytes(b"keep")
        for marker in ("codex.exe", "env.ps1"):
            (self.package / marker).write_bytes(b"synthetic marker; never execute")
        for leaf in LEAVES:
            sources = []
            for skill in SKILLS:
                rel = f"home/skills/{skill}/scripts/office/{leaf}"
                source = ROOT / rel
                for p in reversed(source.parents):
                    plain(p, True)
                plain(source, False)
                sources.append(source.read_bytes())
                target = self.package / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as f:
                    f.write(sources[-1])
            self.assertTrue(all(data == sources[0] for data in sources))
        self.windows = expected_windows()
        self.bogus = {"SystemRoot": str(self.outside), "WINDIR": str(self.outside),
                      "SystemDrive": "X:", "ComSpec": "synthetic.exe", "PATHEXT": ".FAKE",
                      "PATH": str(self.outside), "TEMP": str(self.outside), "LANG": "C"}

    @contextlib.contextmanager
    def modules(self, skill):
        scripts = self.package / f"home/skills/{skill}/scripts"
        # The product uses an office namespace package, not a fabricated module.
        def office_name(name):
            return name == "office" or name.startswith("office.")
        saved = {k: v for k, v in sys.modules.items() if office_name(k)}
        try:
            for k in saved:
                sys.modules.pop(k)
            with mock.patch.object(sys, "path", [str(scripts), *sys.path]):
                spec = importlib.util.find_spec("office")
                self.assertIsNone(spec.origin)
                self.assertEqual(list(spec.submodule_search_locations), [str(scripts / "office")])
                helpers = importlib.import_module("office.helpers")
                soffice = importlib.import_module("office.soffice")
                self.assertEqual(Path(helpers.__file__), scripts / "office" / LEAVES[0])
                self.assertEqual(Path(soffice.__file__), scripts / "office" / LEAVES[1])
                yield helpers, soffice
        finally:
            for k in tuple(sys.modules):
                if office_name(k):
                    sys.modules.pop(k)
            sys.modules.update(saved)

    def check_env(self, env, entries):
        expected = [self.package / rel for rel in entries]
        system = {}
        if self.windows is not None:
            win = self.windows
            expected += [win / "System32", win, win / "System32/Wbem"]
            system = {"SYSTEMROOT": str(win), "WINDIR": str(win), "SYSTEMDRIVE": win.drive,
                      "COMSPEC": str(win / "System32/cmd.exe"), "PATHEXT": ".COM;.EXE;.BAT;.CMD"}
        self.assertEqual([Path(p) for p in env["PATH"].split(os.pathsep)], expected)
        aliases = [(key.upper(), value) for key, value in env.items() if key.upper() in SYSTEM_KEYS]
        self.assertEqual(len(aliases), len(system))
        self.assertEqual(dict(aliases), system)
        for key, rel in STATE.items():
            self.assertEqual(Path(env[key]), self.package / rel)
        for key in ("TEMP", "TMP", "TMPDIR"):
            self.assertEqual(Path(env[key]), self.package / "tmp/office")
        self.assertEqual(env["LANG"], "C")
        self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(list(self.outside.iterdir()), [self.outside / "sentinel"])
        self.assertEqual((self.outside / "sentinel").read_bytes(), b"keep")

    def test_package_import_and_environment(self):
        for skill in SKILLS:
            with self.modules(skill) as (helpers, soffice), \
                 mock.patch.dict(os.environ, self.bogus, clear=True), \
                 mock.patch.object(soffice, "_needs_shim", return_value=False):
                for name, build, entries in (("helpers", helpers.portable_subprocess_env, HELPER_PATH),
                                             ("soffice", soffice.get_soffice_env, OFFICE_PATH)):
                    with self.subTest(skill=skill, entry=name):
                        env = build()
                        self.check_env(env, entries)
                        if name == "helpers":
                            self.assertEqual(env["GIT_CONFIG_GLOBAL"], os.devnull)
                            self.assertEqual(env["GIT_CONFIG_SYSTEM"], os.devnull)
                        else:
                            self.assertEqual(env["SAL_USE_VCLPLUGIN"], "svp")

    def test_api_failure_rejects_without_fallback(self):
        for skill in SKILLS:
            with self.modules(skill) as (helpers, _):
                for value, length in (("", 0), ("", 32768), ("relative", 8)):
                    with self.subTest(skill=skill, length=length):
                        def reply(buf, size):
                            self.assertEqual(size, 32768)
                            buf.value = value
                            return length
                        query = mock.Mock(side_effect=reply)
                        dll = mock.Mock(GetSystemWindowsDirectoryW=query)
                        env = {"sYsTeMrOoT": "synthetic", "COMSPEC": "synthetic", "KEEP": "unchanged"}
                        # Only the helper's platform dispatch/API are simulated.
                        with mock.patch.object(helpers, "os", SimpleNamespace(name="nt")), \
                             mock.patch.object(ctypes, "WinDLL", return_value=dll, create=True):
                            with self.assertRaisesRegex(RuntimeError, "Windows system directory"):
                                helpers._trusted_windows_environment(env)
                        self.assertEqual(env, {"KEEP": "unchanged"})
                        self.assertEqual(query.argtypes, [wintypes.LPWSTR, wintypes.UINT])
                        self.assertEqual(query.restype, wintypes.UINT)
                        query.assert_called_once()

    def test_soffice_profile_contract(self):
        exe = self.package / OFFICE_PATH[0] / "soffice.exe"
        exe.parent.mkdir(parents=True)
        for skill in SKILLS:
            with self.subTest(skill=skill), self.modules(skill) as (_, soffice), \
                 mock.patch.dict(os.environ, self.bogus, clear=True), \
                 mock.patch.object(soffice, "_needs_shim", return_value=False):
                with self.assertRaises(FileNotFoundError):
                    soffice.get_soffice_executable()
                exe.write_bytes(b"synthetic marker; never execute")
                scratch = self.package / "tmp/office"
                def launch(argv, *, env, **kwargs):
                    self.check_env(env, OFFICE_PATH)
                    self.assertEqual(Path(argv[0]), exe)
                    children = list(scratch.iterdir())
                    self.assertEqual(len(children), 1)
                    profile = children[0]
                    self.assertEqual(argv[1:], [f"-env:UserInstallation={profile.as_uri()}", "--headless"])
                    (profile / "owned").write_bytes(b"profile")
                    return subprocess.CompletedProcess(argv, 0)
                try:
                    # Validate argv/env and actual owned profile cleanup, no fake EXE launch.
                    with mock.patch.object(soffice.subprocess, "run", side_effect=launch) as run:
                        self.assertEqual(soffice.run_soffice(["--headless"]).returncode, 0)
                        run.assert_called_once()
                    self.assertEqual(list(scratch.iterdir()), [])
                    explicit = self.package / "explicit profile"
                    explicit.mkdir(exist_ok=True)
                    sentinel = explicit / "keep"
                    sentinel.write_bytes(b"explicit")
                    args = [f"-env:UserInstallation={explicit.as_uri()}", "--headless"]
                    def explicit_launch(argv, *, env, **kwargs):
                        self.check_env(env, OFFICE_PATH)
                        self.assertEqual(argv, [str(exe), *args])
                        self.assertEqual(list(scratch.iterdir()), [])
                        return subprocess.CompletedProcess(argv, 7)
                    with mock.patch.object(soffice.subprocess, "run", side_effect=explicit_launch) as run:
                        self.assertEqual(soffice.run_soffice(args).returncode, 7)
                        run.assert_called_once()
                    self.assertEqual(sentinel.read_bytes(), b"explicit")
                    self.assertEqual(list(explicit.iterdir()), [sentinel])
                finally:
                    exe.unlink()

    def test_direct_entry_still_refuses(self):
        tmp = self.package / "tmp"
        tmp.mkdir(exist_ok=True)
        env = {key: str(tmp) for key in ("HOME", "USERPROFILE", "TEMP", "TMP", "TMPDIR")}
        if self.windows is not None:
            env.update(SystemRoot=str(self.windows), WINDIR=str(self.windows))
        for skill in SKILLS:
            with self.subTest(skill=skill):
                entry = self.package / f"home/skills/{skill}/scripts/office/soffice.py"
                result = subprocess.run([sys.executable, "-I", "-B", str(entry)], cwd=self.package,
                                        env=env, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, b"")
                self.assertEqual(result.stderr.strip(), b"office.soffice is an internal portable helper; "
                                 b"use the guarded document skill entrypoints instead")
        self.assertEqual(list(tmp.iterdir()), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
