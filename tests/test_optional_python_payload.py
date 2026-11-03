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
                source = package["source_distribution"]
                if source is None:
                    self.assertEqual(package["source_distribution_status"],
                                     "not_published_on_pypi")
                else:
                    self.assertTrue(source["url"].startswith("https://files.pythonhosted.org/"))
                    self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")
                    if "source_distribution_status" in package:
                        self.assertEqual(package["source_distribution_status"], "published")
                self.assertRegex(package["sha256"], r"^[0-9a-f]{64}$")
                origin = package.get("license_provided_by")
                if origin is None:
                    self.assertTrue(any(Path(n).name in {"LICENSE", "COPYING"}
                                        for n in package["files"]))
                else:
                    self.assertEqual(origin, "PyMuPDF")
                    self.assertEqual(package["name"].lower(), "pymupdf4llm")
                    parent = next(p for p in self.packages
                                  if p["name"].lower() == "pymupdf")
                    self.assertEqual(parent["version"], package["version"])
                    self.assertTrue(any("/pymupdf4llm/" in n for n in parent["files"]))
                    self.assertTrue(any(Path(n).name in {"LICENSE", "COPYING"}
                                        for n in parent["files"]))
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
