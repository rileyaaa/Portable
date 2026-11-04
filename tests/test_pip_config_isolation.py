"""Exercise the bundled pip config loader using only synthetic package files."""
from pathlib import Path
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
            config = Path(fixture) / "synthetic-host-pip.ini"
            config.write_text("[install]\ntarget = synthetic-outside-target\n", encoding="utf-8")
            code = r'''
import os, sys
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from pip._internal import configuration as c
# pip 26.3 uses the Kind enumeration; older pip exposed the
# kinds namespace even when Kind was a NewType without GLOBAL/USER/SITE.
# Resolve the real identifiers without changing configuration assertions.
kinds = getattr(c, "kinds", None)
if kinds is None:
    kinds = c.Kind
locations = {kinds.GLOBAL: [sys.argv[2]], kinds.USER: [], kinds.SITE: []}
# Replace discovery, so no real host/user configuration path is read or probed.
with patch.object(c, "get_configuration_files", return_value=locations):
    for isolated in (False, True):
        with patch.dict(os.environ, {}, clear=True):
            config = c.Configuration(isolated=isolated)
            config.load()
            assert config.get_value("install.target") == "synthetic-outside-target"
        with patch.dict(os.environ, {"PIP_CONFIG_FILE": os.devnull}, clear=True):
            config = c.Configuration(isolated=isolated)
            with patch.object(config, "_load_file", side_effect=AssertionError("Config file read")):
                config.load()
            assert "install.target" not in dict(config.items())
'''
            # The native Windows diagnostic runs these tests using the staged
            # python-runtime, while full runs them from the replaced tool/python.
            # Both must test the pip actually selected for the test process.
            runtime = Path(sys.executable).resolve().parent
            site = (runtime / "Lib/site-packages"
                    if (runtime / "python315._pth").is_file()
                    else ROOT / "tool/python/Lib/site-packages")
            self.assertTrue(site.is_dir(), "Bundled or staged pip site-packages missing")
            result = subprocess.run(
                [sys.executable, "-B", "-c", code,
                 str(site), str(config)],
                cwd=fixture, capture_output=True, text=True, timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
