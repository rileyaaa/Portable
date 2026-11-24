"""Check the existing console_script wrapper without invoking any vendor CLI."""
import importlib.util
import io
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
