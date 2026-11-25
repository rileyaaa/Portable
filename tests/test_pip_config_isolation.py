"""Exercise the bundled pip config loader and CLI with synthetic files only."""
from pathlib import Path
import os
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).absolute().parents[1]


class PipConfigIsolationTests(unittest.TestCase):
    def test_devnull_suppresses_all_config_files_even_in_isolated_mode(self):
        for path in (*reversed(ROOT.parents), ROOT):
            info = path.lstat()
            self.assertTrue(stat.S_ISDIR(info.st_mode))
            self.assertFalse(getattr(info, "st_file_attributes", 0) & 0x400)
        scratch = ROOT / "tmp"
        if not scratch.exists() and not scratch.is_symlink():
            scratch.mkdir()
        info = scratch.lstat()
        self.assertTrue(stat.S_ISDIR(info.st_mode))
        self.assertFalse(getattr(info, "st_file_attributes", 0) & 0x400)
        with tempfile.TemporaryDirectory(prefix="pip-config-", dir=scratch) as fixture:
            owned = Path(fixture)
            global_config = owned / "synthetic-global-pip.ini"
            user_config = owned / "synthetic-user-pip.ini"
            site_config = owned / "synthetic-site-pip.ini"
            global_config.write_text("[install]\ntarget = synthetic-outside-target\n", encoding="utf-8")
            user_config.write_text("[portable-ci]\nuser-marker = synthetic-user-marker\n", encoding="utf-8")
            site_config.write_text("[portable-ci]\nsite-marker = synthetic-site-marker\n", encoding="utf-8")
            original = {p: p.read_bytes() for p in (global_config, user_config, site_config)}
            code = r'''
import os, runpy, sys
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

site, global_file, user_file, site_file, isolated_arg, devnull_arg = sys.argv[1:]
sys.path.insert(0, site)
import pip
from pip._internal import configuration as c
assert Path(pip.__file__).resolve().is_relative_to(Path(site).resolve())
# pip 26.1 uses kinds; 26.3 replaces it with the str-backed Kind enum.
# Only the synthetic discovery boundary needs the internal type.
kinds = c.kinds if hasattr(c, "kinds") else c.Kind
locations = {kinds.GLOBAL: [global_file], kinds.USER: [user_file], kinds.SITE: [site_file]}
isolated = isolated_arg == "1"
devnull = devnull_arg == "1"
assert (os.environ.get("PIP_CONFIG_FILE") == os.devnull) == devnull
if not devnull:
    assert "PIP_CONFIG_FILE" not in os.environ
# Replace discovery, not the config loader, CLI parser, or upstream protection.
# Never read/probe actual host or user configuration paths.
with patch.object(c, "get_configuration_files", return_value=locations):
    guard = patch.object(c.Configuration, "_load_file", side_effect=AssertionError("Config file read")) if devnull else nullcontext()
    with guard:
        config = c.Configuration(isolated=isolated)
        config.load()
        if not devnull:
            assert config.get_value("install.target") == "synthetic-outside-target"
        else:
            assert "install.target" not in dict(config.items())
        # Run the real public CLI entry point in this dedicated subprocess.
        # Only discovery is simulated; config loading/printing are real.
        sys.argv = ["pip"] + (["--isolated"] if isolated else []) + ["--disable-pip-version-check", "--no-input", "config", "list"]
        runpy.run_module("pip", run_name="__main__")
'''
            # Preserve only essential process variables; no real pip/user
            # configuration or credentials in the child environment.
            base_env = {key: os.environ[key] for key in
                        ("SystemRoot", "WINDIR", "SystemDrive", "ComSpec", "PATHEXT",
                         "OS", "PROCESSOR_ARCHITECTURE") if key in os.environ}
            for key, name in (("HOME", "home"), ("USERPROFILE", "home"),
                              ("APPDATA", "appdata"), ("LOCALAPPDATA", "localappdata"),
                              ("PROGRAMDATA", "programdata"), ("ALLUSERSPROFILE", "programdata"),
                              ("TEMP", "temp"), ("TMP", "temp"), ("TMPDIR", "temp"),
                              ("PIP_CACHE_DIR", "cache")):
                directory = owned / name
                directory.mkdir(exist_ok=True)
                base_env[key] = str(directory)
            for isolated in (False, True):
                for devnull in (False, True):
                    with self.subTest(isolated=isolated, devnull=devnull):
                        env = base_env.copy()
                        if devnull:
                            env["PIP_CONFIG_FILE"] = os.devnull
                        result = subprocess.run(
                            [sys.executable, "-B", "-c", code,
                             str(ROOT / "tool/python/Lib/site-packages"),
                             str(global_config), str(user_config), str(site_config),
                             str(int(isolated)), str(int(devnull))],
                            cwd=owned, env=env, capture_output=True,
                            encoding="utf-8", errors="replace", timeout=45,
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        # Positive controls: isolated mode alone does not
                        # suppress global/site config, but does suppress user config.
                        # Negative control: devnull suppresses all three, even isolated.
                        for marker, present in (
                            ("synthetic-outside-target", not devnull),
                            ("synthetic-site-marker", not devnull),
                            ("synthetic-user-marker", not devnull and not isolated),
                        ):
                            self.assertEqual(marker in result.stdout, present,
                                             (marker, isolated, devnull, result.stdout))
                        print("PIP_CONFIG_CLI_MATRIX=PASS isolated=%d devnull=%d" %
                              (isolated, devnull), flush=True)
            self.assertEqual({p: p.read_bytes() for p in original}, original)


if __name__ == "__main__":
    unittest.main()
