"""Check the existing console_script wrapper without invoking any vendor CLI."""
import importlib.util
import io
import json
import subprocess
from pathlib import Path
import stat
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).absolute().parents[1]
SOURCE = ROOT / "tool/bin/portable-python-cli.py"


def load_wrapper():
    for p in (*reversed(SOURCE.parents), SOURCE):
        st = p.lstat()
        if stat.S_ISLNK(st.st_mode) or getattr(st, "st_file_attributes", 0) & 0x400:
            raise RuntimeError("Linked CLI test source")
        if p == SOURCE and (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1):
            raise RuntimeError("Invalid CLI test source")
    spec = importlib.util.spec_from_file_location("portable_cli_output_fixture", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PythonCliOutputTests(unittest.TestCase):
    def test_main_configures_redirected_unicode_stdout_and_stderr_before_entrypoint(self):
        module = load_wrapper()
        text = "\u4fbf\u643a \u8def\u5f84"
        data_out, data_err = io.BytesIO(), io.BytesIO()
        with io.TextIOWrapper(data_out, encoding="cp1252") as stdout, \
                io.TextIOWrapper(data_err, encoding="cp1252") as stderr:
            def console_entrypoint():
                print(text)
                print(text, file=sys.stderr)
                return 7
            ep = mock.Mock()
            ep.load.return_value = console_entrypoint
            with mock.patch.object(sys, "stdout", stdout), \
                    mock.patch.object(sys, "stderr", stderr), \
                    mock.patch.object(sys, "argv", ["portable-python-cli.py", "synthetic", "--flag"]), \
                    mock.patch.object(module, "_find_entry_point", return_value=ep):
                self.assertEqual(module.main(), 7)
                self.assertEqual(sys.argv, ["synthetic", "--flag"])
            stdout.flush()
            stderr.flush()
            self.assertEqual(data_out.getvalue().decode("utf-8").splitlines(), [text])
            self.assertEqual(data_err.getvalue().decode("utf-8").splitlines(), [text])

    def test_console_script_exit_contract_matches_vendor_launcher(self):
        # Use a synthetic registered console_script, never a vendor CLI.
        # A separate interpreter observes the real SystemExit exit code and
        # stderr, rather than only checking the wrapper's Python return value.
        harness = r"""
import importlib.metadata
import json
import runpy
import sys
import types
from unittest import mock

mode, source, value = sys.argv[1:]
result = json.loads(value)
fixture = types.ModuleType("portable_cli_exit_fixture")
fixture.entry = lambda: result
sys.modules[fixture.__name__] = fixture
entry = importlib.metadata.EntryPoint(
    name="synthetic", value=fixture.__name__ + ":entry", group="console_scripts")
if mode == "vendor":
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.exit(entry.load()())
sys.argv = [source, "synthetic"]
with mock.patch.object(importlib.metadata, "entry_points",
                       return_value=importlib.metadata.EntryPoints([entry])):
    runpy.run_path(source, run_name="__main__")
"""
        error = "\u4fbf\u643a \u8def\u5f84: synthetic failure"
        for value, code, errors in ((None, 0, []), (0, 0, []), (7, 7, []),
                                    (True, 1, []), (False, 0, []),
                                    (error, 1, [error])):
            with self.subTest(value=value):
                encoded = json.dumps(value, ensure_ascii=True)
                command = [sys.executable, "-I", "-B", "-c", harness]
                expected = subprocess.run(
                    [*command, "vendor", str(SOURCE), encoded],
                    capture_output=True, cwd=ROOT, timeout=30, check=False)
                actual = subprocess.run(
                    [*command, "portable", str(SOURCE), encoded],
                    capture_output=True, cwd=ROOT, timeout=30, check=False)
                self.assertEqual(expected.returncode, code)
                self.assertEqual(expected.stdout, b"")
                self.assertEqual(expected.stderr.decode("utf-8").splitlines(), errors)
                self.assertEqual(actual.returncode, expected.returncode)
                self.assertEqual(actual.stdout, expected.stdout)
                self.assertEqual(actual.stderr, expected.stderr)

    def test_preserves_interactive_console_and_non_reconfigurable_stream(self):
        module = load_wrapper()
        tty = mock.Mock()
        tty.isatty.return_value = True
        stream = io.StringIO()
        with mock.patch.object(sys, "stdout", tty), mock.patch.object(sys, "stderr", stream):
            module._configure_redirected_output()
        tty.reconfigure.assert_not_called()
        self.assertEqual(stream.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
