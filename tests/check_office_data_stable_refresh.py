"""Real Office and timezone probes for a fixed stable wheel refresh (synthetic data only)."""
import importlib.metadata as md
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "tool/python/python.exe"
SITE = ROOT / "tool/python/Lib/site-packages"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def office(version, work):
    import openpyxl
    import pandas as pd
    import xlsxwriter

    assert xlsxwriter.__version__ == md.version("xlsxwriter") == version
    assert Path(xlsxwriter.__file__).resolve().is_relative_to(SITE)
    book = work / "\u4e2d\u6587 formulas.xlsx"
    wb = xlsxwriter.Workbook(book, {"strings_to_formulas": False, "use_future_functions": True})
    ws = wb.add_worksheet("\u4e2d\u6587")
    fmt = wb.add_format({"num_format": "yyyy-mm-dd hh:mm:ss"})
    ws.write_datetime("A1", datetime(1900, 2, 28, 12), fmt)
    ws.write("A2", "{=SUM(B1:B2)}")
    ws.write_formula("A3", '="SINGLE()"')
    ws.write_formula("A4", "=MYSINGLE()")
    ws.write("B1", 5)
    ws.write("B2", 7)
    ws.write_formula("B3", "=SUM(B1:B2)", None, 12)
    ws.write("C1", "\u53f0\u7063\u6578\u64da")
    wb.close()
    with zipfile.ZipFile(book) as z:
        assert z.testzip() is None
        root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        cells = {c.attrib["r"]: c for c in root.findall(".//m:c", NS)}
        if version == "3.2.9":
            # Require actual old defects to be reproduced; do not treat them as success.
            assert cells["A1"].findtext("m:v", namespaces=NS) == "60.5"
            assert cells["A2"].find("m:f", NS) is not None
            assert cells["A3"].findtext("m:f", namespaces=NS) == '"_xlfn.SINGLE()"'
            assert cells["A4"].findtext("m:f", namespaces=NS) == "MY_xlfn.SINGLE()"
        else:
            assert version == "3.3.4"
            assert cells["A1"].findtext("m:v", namespaces=NS) == "59.5"
            assert cells["A2"].find("m:f", NS) is None
            assert cells["A3"].findtext("m:f", namespaces=NS) == '"SINGLE()"'
            assert cells["A4"].findtext("m:f", namespaces=NS) == "MYSINGLE()"
    with _read(openpyxl, book) as actual:
        assert actual.active["C1"].value == "\u53f0\u7063\u6578\u64da"
        assert actual.active["B3"].value == "=SUM(B1:B2)"
        if version == "3.3.4":
            assert actual.active["A2"].value == "{=SUM(B1:B2)}"
    with _read(openpyxl, book, data_only=True) as actual:
        assert actual.active["B3"].value == 12
    table = work / "\u6578\u64da frame.xlsx"
    frame = pd.DataFrame({"\u6b04\u4f4d": [1, 2], "text": ["\u5317", "\u5357"]})
    frame.to_excel(table, engine="xlsxwriter", index=False)
    assert pd.read_excel(table, engine="openpyxl").equals(frame)
    # Exercise the historical data script with an explicit embedded interpreter.
    # These are inert bytes in a synthetic ZIP, never executable VBA.
    script = SITE / "bin/vba_extract.py"
    source = work / "synthetic.xlsm"
    with zipfile.ZipFile(source, "w") as z:
        z.writestr("xl/vbaProject.bin", b"synthetic-project")
        z.writestr("xl/vbaProjectSignature.bin", b"synthetic-signature")
    result = subprocess.run([str(PY), "-B", str(script), str(source)], cwd=work,
                            capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert (work / "vbaProject.bin").read_bytes() == b"synthetic-project"
    assert (work / "vbaProjectSignature.bin").read_bytes() == b"synthetic-signature"
    if version == "3.3.4":
        assert script.read_bytes().splitlines()[0] == b"#!python"
    print("XLSX_STABLE_REGRESSION=PASS " + version, flush=True)


from contextlib import contextmanager


@contextmanager
def _read(openpyxl, file, data_only=False):
    book = openpyxl.load_workbook(file, read_only=True, data_only=data_only)
    try:
        yield book
    finally:
        book.close()


def timezone_data(version):
    import pandas as pd
    import tzdata
    from zoneinfo import ZoneInfo, reset_tzpath, TZPATH

    assert md.version("tzdata") == tzdata.__version__ == version
    assert Path(tzdata.__file__).resolve().is_relative_to(SITE)
    # Disable every system time-zone path, including any inherited PYTHONTZPATH.
    reset_tzpath(())
    ZoneInfo.clear_cache()
    from zoneinfo import TZPATH as effective
    assert effective == ()
    assert tzdata.IANA_VERSION == {"2026.2": "2026b", "2026.6": "2026f"}[version]
    instant = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)
    expected = {
        "America/Havana": (-5, -4), "America/Winnipeg": (-6, -5),
        "America/Edmonton": (-7, -6), "America/Yellowknife": (-7, -6),
        "Africa/Casablanca": (1, 0), "Asia/Taipei": (8, 8),
        "Asia/Shanghai": (8, 8), "America/Los_Angeles": (-8, -8),
    }
    for name, pair in expected.items():
        zone = ZoneInfo(name)
        hours = pair[version == "2026.6"]
        result = instant.astimezone(zone)
        assert result.utcoffset().total_seconds() == hours * 3600, (name, result)
        converted = pd.Timestamp(instant).tz_convert(zone)
        assert converted.utcoffset() == result.utcoffset(), name
    print("TZDATA_PACKAGE_ONLY_OFFSETS=PASS " + version, flush=True)


def main():
    assert os.name == "nt" and sys.version_info[:3] == (3, 14, 10)
    assert Path(sys.executable).resolve() == PY.resolve()
    assert sys.flags.isolated and sys.flags.ignore_environment and sys.flags.safe_path
    assert set(map(Path, sys.path)) == {PY.parent / "python314.zip", PY.parent, SITE}
    assert os.environ.get("PIP_CONFIG_FILE") == os.devnull
    kind, version = sys.argv[1:]
    if kind == "tzdata":
        timezone_data(version)
    elif kind == "xlsxwriter":
        with tempfile.TemporaryDirectory(prefix="office \u4e2d\u6587 ", dir=os.environ["TMP"]) as d:
            office(version, Path(d))
    else:
        raise ValueError(kind)


if __name__ == "__main__":
    main()
