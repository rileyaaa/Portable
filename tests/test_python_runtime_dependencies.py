"""Check the Windows runtime dependency closure without loading native modules."""
import email
from pathlib import Path
import unittest

from pip._vendor.packaging.markers import default_environment
from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.utils import canonicalize_name


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "tool/python/Lib/site-packages"


class PythonRuntimeDependencyTests(unittest.TestCase):
    def test_default_windows_dependencies_survive_build_tool_removal(self):
        packages = {}
        for path in SITE.glob("*.dist-info/METADATA"):
            metadata = email.message_from_string(path.read_text(encoding="utf-8"))
            packages[canonicalize_name(metadata["Name"])] = metadata
        for name in (
            "pip", "requests", "httpx", "beautifulsoup4", "lxml", "pandas",
            "numpy", "python-docx", "python-pptx", "openpyxl", "pymupdf",
            "pymupdf4llm",
        ):
            self.assertIn(name, packages)
        environment = default_environment()
        environment.update(
            python_version="3.14", python_full_version="3.14.0",
            os_name="nt", sys_platform="win32", platform_system="Windows",
            platform_machine="AMD64", extra="",
        )
        for name, metadata in packages.items():
            for text in metadata.get_all("Requires-Dist", []):
                dependency = Requirement(text)
                if dependency.marker and not dependency.marker.evaluate(environment):
                    continue
                with self.subTest(package=name, dependency=text):
                    key = canonicalize_name(dependency.name)
                    self.assertIn(key, packages)
                    self.assertTrue(dependency.specifier.contains(
                        packages[key]["Version"], prereleases=True
                    ))


if __name__ == "__main__":
    unittest.main()
