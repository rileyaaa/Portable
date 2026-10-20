"""Verify shipped optional wheels without executing Windows extensions on Linux."""
import hashlib
import json
from pathlib import Path
import struct
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OptionalPythonPayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packages = json.loads(
            (ROOT / "tool/optional-python-manifest.json").read_text(encoding="utf-8")
        )["packages"]

    def test_official_wheel_payloads_and_source_records(self):
        requirements = (ROOT / "tool/python-packages.in.txt").read_text(encoding="utf-8")
        for package in self.packages:
            with self.subTest(package=package["name"]):
                self.assertIn(f'{package["name"]}=={package["version"]}', requirements)
                self.assertTrue(package["source"].startswith("https://files.pythonhosted.org/"))
                self.assertTrue(
                    package["source_distribution"]["url"].startswith(
                        "https://files.pythonhosted.org/"
                    )
                )
                self.assertRegex(package["sha256"], r"^[0-9a-f]{64}$")
                self.assertRegex(package["source_distribution"]["sha256"], r"^[0-9a-f]{64}$")
                self.assertTrue(
                    any(Path(name).name in {"LICENSE", "COPYING"} for name in package["files"])
                )
                for name, expected in package["files"].items():
                    target = ROOT / name
                    self.assertFalse(target.is_symlink(), name)
                    self.assertTrue(
                        target.resolve().is_relative_to(ROOT / "tool/python/Lib/site-packages"),
                        name,
                    )
                    with target.open("rb") as stream:
                        actual = hashlib.file_digest(stream, "sha256").hexdigest()
                    self.assertEqual(actual, expected, name)

    def test_native_pdf_extensions_are_windows_x64(self):
        native = [
            ROOT / name
            for package in self.packages
            for name in package["files"]
            if Path(name).suffix.lower() in {".pyd", ".dll"}
        ]
        self.assertTrue(native, "PyMuPDF must contain its actual Windows native payload")
        for path in native:
            with self.subTest(file=path.name), path.open("rb") as stream:
                self.assertEqual(stream.read(2), b"MZ")
                stream.seek(0x3C)
                stream.seek(struct.unpack("<I", stream.read(4))[0])
                self.assertEqual(stream.read(4), b"PE\0\0")
                self.assertEqual(struct.unpack("<H", stream.read(2))[0], 0x8664)


if __name__ == "__main__":
    unittest.main()
