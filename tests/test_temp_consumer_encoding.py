"""Isolated TEMP/TMP/TMPDIR consumer and reporting regression.

Run with the bundled Python from the checkout's tests directory, or copy
this test alone to the extracted package's work directory. No subprocess,
network, credentials, product configuration or Windows ACL changes.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).absolute().parents[1]
KEYS = ("TMPDIR", "TEMP", "TMP")
PAYLOAD = b"portable temp consumer"


def plain_directory(path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise RuntimeError("Expected ordinary test directory: " + ascii(str(path)))


@contextlib.contextmanager
def isolated_temp_environment(active):
    # Change only the three synthetic inputs in this test process; restore
    # the actual prior environment and the module's cached temp directory.
    previous = {key: os.environ.get(key) for key in KEYS}
    previous_cache = tempfile.tempdir
    original_candidates = tempfile._candidate_tempdir_list
    try:
        for key in KEYS:
            os.environ.pop(key, None)
        for key, path in active.items():
            os.environ[key] = str(path)
        tempfile.tempdir = None

        def confined_candidates():
            # Keep the standard library's actual environment-derived order.
            # Only remove fallback locations: a bad fixture must fail rather
            # than cause tempfile to try a host directory or the cwd.
            candidates = original_candidates()[:len(active)]
            if set(candidates) != {str(path) for path in active.values()}:
                raise AssertionError("Unexpected environment candidate list")
            return candidates

        with mock.patch.object(tempfile, "_candidate_tempdir_list", confined_candidates):
            yield
    finally:
        tempfile.tempdir = previous_cache
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class TempConsumerEncodingTests(unittest.TestCase):
    def setUp(self):
        for parent in (*reversed(ROOT.parents), ROOT):
            plain_directory(parent)
        if os.name == "nt":
            self.assertEqual(Path(sys.executable).resolve(), ROOT / "tool/python/python.exe")
        tmp = ROOT / "tmp"
        try:
            plain_directory(tmp)
        except FileNotFoundError:
            tmp.mkdir()
            self.addCleanup(tmp.rmdir)
            plain_directory(tmp)
        self.scratch = tmp / "temp-encoding-probe"
        self.scratch.mkdir()  # exclusive: do not reuse an existing fixture
        self.addCleanup(self.scratch.rmdir)
        plain_directory(self.scratch)
        self.unicode = self.scratch / "\u4e2d\u6587 \u7a7a\u683c"
        self.unicode.mkdir()
        self.addCleanup(self.unicode.rmdir)
        plain_directory(self.unicode)
        self.dirs = {}
        for key in KEYS:
            path = self.unicode / key.lower()
            path.mkdir()
            self.addCleanup(path.rmdir)
            plain_directory(path)
            self.dirs[key] = path

    def consume(self, key):
        # Higher-priority variables are absent; lower-priority ones point
        # to different, equally writable, package-local fixture directories.
        active = {name: self.dirs[name] for name in KEYS[KEYS.index(key):]}
        expected = self.dirs[key]
        with isolated_temp_environment(active):
            directory = Path(tempfile.gettempdir())
            self.assertEqual(directory, expected)
            with tempfile.NamedTemporaryFile() as handle:
                actual = Path(handle.name)
                self.assertEqual(actual.parent, expected)
                self.assertTrue(actual.is_file())
                self.assertEqual(handle.write(PAYLOAD), len(PAYLOAD))
                handle.flush()
                handle.seek(0)
                self.assertEqual(handle.read(), PAYLOAD)
            self.assertFalse(actual.exists())
        for path in self.dirs.values():
            self.assertEqual(list(path.iterdir()), [])
        return {"variable": key, "directory": str(directory), "file": str(actual),
                "created_read_deleted": True}

    def test_tmpdir_consumption(self):
        self.consume("TMPDIR")

    def test_temp_consumption(self):
        self.consume("TEMP")

    def test_tmp_consumption(self):
        self.consume("TMP")

    def test_unavailable_fixture_does_not_fall_back(self):
        previous = {key: os.environ.get(key) for key in KEYS}
        previous_cache = tempfile.tempdir
        with isolated_temp_environment({"TMP": self.scratch / "absent"}):
            with self.assertRaises(FileNotFoundError):
                tempfile.gettempdir()
        self.assertEqual({key: os.environ.get(key) for key in KEYS}, previous)
        self.assertIs(tempfile.tempdir, previous_cache)
        self.assertFalse((self.scratch / "absent").exists())

    def test_cp1252_reporting_fails_after_successful_consumption(self):
        evidence = self.consume("TMPDIR")
        with io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict") as output:
            with self.assertRaises(UnicodeEncodeError):
                print(evidence["directory"], file=output)
        self.assertTrue(evidence["created_read_deleted"])
        self.assertFalse(Path(evidence["file"]).exists())

    def test_ascii_json_reporting_preserves_successful_consumption(self):
        evidence = self.consume("TMPDIR")
        with io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict") as output:
            print(json.dumps(evidence, ensure_ascii=True), file=output)
            output.flush()
            encoded = output.buffer.getvalue()
        self.assertEqual(json.loads(encoded.decode("ascii")), evidence)
        self.assertFalse(Path(evidence["file"]).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
