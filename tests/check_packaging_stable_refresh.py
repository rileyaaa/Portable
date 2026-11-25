"""Check actual consumers and existing packaging contracts with the fixed Windows runtime."""
import importlib.metadata as md
from pathlib import Path
import sys

import packaging
from packaging.markers import Marker
from packaging.metadata import Metadata
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename
from packaging.version import Version

name, expected = sys.argv[1:]
assert name == "packaging" and expected in {"26.2", "26.4"}
root = Path.cwd()
assert sys.flags.isolated and sys.flags.safe_path and sys.flags.ignore_environment
assert Path(packaging.__file__).resolve().is_relative_to(root / "tool/python/Lib/site-packages/packaging")
assert packaging.__version__ == md.version("packaging") == expected
assert Version("3.14.10") in SpecifierSet(">=3.10,<4")
assert Version("1.0rc1") < Version("1.0") < Version("1.0.post1")
assert Marker('python_version >= "3.10" and sys_platform == "win32"').evaluate()
wheel = parse_wheel_filename("packaging-" + expected + "-py3-none-any.whl")
assert wheel[0] == "packaging" and str(wheel[1]) == expected
assert wheel[3].intersection(sys_tags())
assert Requirement("typing-extensions>=4.16.0").specifier.contains(md.version("typing-extensions"))
meta = Metadata.from_email(md.distribution("packaging").read_text("METADATA"))
assert meta.name == "packaging" and str(meta.version) == expected
# Check all active requirements in the existing installed closure, without
# resolution, downloading extra dependencies or introducing new APIs.
installed = {d.metadata["Name"].lower().replace("_", "-"): d.version
             for d in md.distributions(path=[str(root / "tool/python/Lib/site-packages")])}
assert len(installed) == 49
for dist in md.distributions(path=[str(root / "tool/python/Lib/site-packages")]):
    for raw in dist.requires or []:
        req = Requirement(raw)
        if req.marker is None or req.marker.evaluate({"extra": ""}):
            key = req.name.lower().replace("_", "-")
            assert key in installed and req.specifier.contains(installed[key], prereleases=True), (dist.name, raw)
import pandas
import PyInstaller
assert pandas.DataFrame({"a": [1, 2]})["a"].sum() == 3
assert Version(PyInstaller.__version__) == Version(md.version("pyinstaller"))
print("PACKAGING_STABLE_REGRESSION=PASS " + expected + "; Windows tags, metadata, closure, pandas and PyInstaller imports")
