"""Stage one fixed Office/data wheel in the CI checkout, not on a customer installation.

Invoke with the bundled Python -B, from a clean, disposable Windows checkout.
No installation is performed on the host. The caller must run full native gates
and commit only the exact staged paths after success. A failed candidate restores
the previous payload and never stages changed input/lock bytes.
"""
import base64
import csv
import email.parser
import hashlib
import importlib.metadata as md
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile

from packaging.specifiers import SpecifierSet

ROOT = Path.cwd()
PY = ROOT / "tool/python/python.exe"
SITE = ROOT / "tool/python/Lib/site-packages"
PREFIX = SITE.relative_to(ROOT).as_posix() + "/"
SPECS = {
    "xlsxwriter": ("3.2.9", "3.3.4", "9a5db42bc5dff014806c58a20b9eae7322a134abb6fce3c92c181bfb275ec5b3",
                   "da62fecb24fdd0f003c874c86109b9e1245ae89533052745ab85a085eb2b04d7", "py3-none-any", "BSD-2-Clause"),
    "tzdata": ("2026.2", "2026.6", "bbe9af844f658da81a5f95019480da3a89415801f6cc966806612cc7169bffe7",
               "0a10eec6e13ef16b627fabed9a5f2ba61a62b1c67f327305f4e7e412a70b4aec", "py2.py3-none-any", "Apache-2.0"),
}
# GitHub tagged runtime files (not tests/examples other than the installed script).
# PyPI wheel hashes above remain the primary byte-level identity.
XLSX_SOURCE = {
    "3.2.9": {
        "LICENSE.txt": "e1e6c8a50f5dbc0916f417a5c3605e4a980ae926",
        "examples/vba_extract.py": "f35760f4c9596d43dcd9671a04d3ed7be7ea4842",
        "xlsxwriter/__init__.py": "105c6233cdbe7121594bdf98f6081ee8d5850d7c",
        "xlsxwriter/app.py": "9519b63dcf4d9bb15b9672ff790a3f058be132e2",
        "xlsxwriter/chart.py": "fece4404e986d8691c4b1de7c7d8bd084d054df8",
        "xlsxwriter/chart_area.py": "e862ecb66c998e6955cb9fffca3d8a04a3ecfd21",
        "xlsxwriter/chart_bar.py": "4dca2c828a39aad6387a79d3fe89ddb766f333b4",
        "xlsxwriter/chart_column.py": "dc56fa89bed9a11d2971a1de1905c9a7227110ee",
        "xlsxwriter/chart_doughnut.py": "fda27edd0aa9d355f6ad2722fd27298f92480c43",
        "xlsxwriter/chart_line.py": "aa303b8fa75fd9825b6db03742cfe3620320091a",
        "xlsxwriter/chart_pie.py": "3413456b4eee204a075e825742c5793ae9cf5d14",
        "xlsxwriter/chart_radar.py": "957184d780afc1eaefcd11a99be5bc64392bd35d",
        "xlsxwriter/chart_scatter.py": "9cd81723d9be6af118e0f0977bdeb1f72360d532",
        "xlsxwriter/chart_stock.py": "fef916e80ebf96a90bdf558c243a2d1433a5d6c7",
        "xlsxwriter/chart_title.py": "e06fe6e04c85078b85aabc4b407387e70f2d2803",
        "xlsxwriter/chartsheet.py": "d1d5c55faf60c0281cf4a6eb6938f920e32177df",
        "xlsxwriter/color.py": "60b331c4fe237f8d76e17c4c57e4638844ee62e0",
        "xlsxwriter/comments.py": "3aaf0dc6dc6f60816f9f65ac3a7e2b08eb7c8aef",
        "xlsxwriter/contenttypes.py": "713e3a716235a8f68496201e48902468a85750a6",
        "xlsxwriter/core.py": "ffad7ce6c9332916562751e91976275f0d8de3b4",
        "xlsxwriter/custom.py": "3814ac7cad359acdb78493784ffb7d70494a294f",
        "xlsxwriter/drawing.py": "d05b4c795a8ff53ae21351ed70d266db11756c5d",
        "xlsxwriter/exceptions.py": "6c8198b37207bb0de07fa2798d7c66cbd727feb1",
        "xlsxwriter/feature_property_bag.py": "a9f39b30375670fc0114eb2087aee915618763d2",
        "xlsxwriter/format.py": "e146e9cacdcbf1d293bc5211bac5b500def8f497",
        "xlsxwriter/image.py": "1b7202a6acb079faa74e1cffc50bf4b6e839118a",
        "xlsxwriter/metadata.py": "2fe5269261dbba5a8f93b7f080ca02ac22633a20",
        "xlsxwriter/packager.py": "88c1aa2e69dc676367b423d72dd5ca27f787f812",
        "xlsxwriter/relationships.py": "12cbfd1dee366dfe22ed0d3d336f1c8f8abeee43",
        "xlsxwriter/rich_value.py": "6efb16abf0574f62d39e6b5b59f0358b760d4915",
        "xlsxwriter/rich_value_rel.py": "c9d0a8bcd5d5af6ae59e6f6980ffd77c8f799b02",
        "xlsxwriter/rich_value_structure.py": "8af07aeb735fdc989de9a5d2351e64e55b639969",
        "xlsxwriter/rich_value_types.py": "1f154e0b5a76a12e7a5ac3228902b60bb1e11851",
        "xlsxwriter/shape.py": "848263733f43b663157c2cac53f19f16a06eade5",
        "xlsxwriter/sharedstrings.py": "6c545ea94abe50d1c42a9fe8b3bb9f056dd60c64",
        "xlsxwriter/styles.py": "92a37e9705ffc6790b3205dcfb5629ebb458de0d",
        "xlsxwriter/table.py": "22b8a8fd65b2f345837b731d60d467a3fbcbfccb",
        "xlsxwriter/theme.py": "ac2dc6ee60c91b6e4b59af82a938af2e52d6094d",
        "xlsxwriter/url.py": "e2c3fcdf0c1c28862e0e34b396b80e9c70343b7c",
        "xlsxwriter/utility.py": "77e4713fd6391559700bcd54434e83bd21e65617",
        "xlsxwriter/vml.py": "7d6e8d50f653c8a91916a91e56d985bf49864ecc",
        "xlsxwriter/workbook.py": "608f24aefa67987971117f8ab7d9078d24c41d32",
        "xlsxwriter/worksheet.py": "cb655f4680fb84b7fa3627d817391bf6b062249c",
        "xlsxwriter/xmlwriter.py": "b0708ad5453228f96cafe24b3f2f46353487ed83"
    },
    "3.3.4": {
        "LICENSE.txt": "9c654741b8e1aeabfb4eac1430e7bf589c66ff41",
        "examples/vba_extract.py": "5e18b89e6bbe676ec6ebe4531ef89fa6014e4145",
        "xlsxwriter/__init__.py": "5bc9533ff0effcfa84cdcebb14969706e4803366",
        "xlsxwriter/app.py": "e88125287fcca7fe48eeeaaa840f51015edd3d40",
        "xlsxwriter/chart.py": "4e61f64361c0c76210ea8de0a21bb870734e1aea",
        "xlsxwriter/chart_area.py": "30dec4ead7cafad9da2b6e9ac1c88ca801d4dc8c",
        "xlsxwriter/chart_bar.py": "3f11b2abf7d75b0d5f7d217ab759d62d11895389",
        "xlsxwriter/chart_column.py": "30b5b62eb0807d2b347b08106b176bf03397315a",
        "xlsxwriter/chart_doughnut.py": "2a69cb98bf3d012cedcaf5bc5cc338b52e55fc2f",
        "xlsxwriter/chart_line.py": "c1c79d67ca1617feacaa0fb25c238c724ce19441",
        "xlsxwriter/chart_pie.py": "22c033dcc24177816ccc2d1660e73b80caa33302",
        "xlsxwriter/chart_radar.py": "c0a851a7555505daec1a11602e6cb509bfdabba4",
        "xlsxwriter/chart_scatter.py": "e64d6043e57513afb2250471b6b5cd5a29f156e0",
        "xlsxwriter/chart_stock.py": "e202bfcb8a206538aae439e271c9d7b2f110250c",
        "xlsxwriter/chart_title.py": "7ad8e63a76c686dd388ef5bfdecb034173d9d78c",
        "xlsxwriter/chartsheet.py": "310d222883df9bd2aa3e8075d38e8c4bf90fb7bc",
        "xlsxwriter/color.py": "fbbb0c7fb7113a5e2a1d7e5cfecb7eba84be5396",
        "xlsxwriter/comments.py": "52634f8e6b9a85d7e06565af85d77f1d411f444a",
        "xlsxwriter/contenttypes.py": "4e58438fb53c7eb016f51777fcaa66cce374a598",
        "xlsxwriter/core.py": "0b5e0152ef61aa49ff91b389ddce611bb44e7f71",
        "xlsxwriter/custom.py": "5faf5b240f9117756e38494c2a1aafa792c6896b",
        "xlsxwriter/drawing.py": "e0eeb426697cbaace9a634032f823276426f82d0",
        "xlsxwriter/exceptions.py": "3a73e8c1c98d44100e7f712307057ae188a9b265",
        "xlsxwriter/feature_property_bag.py": "34f51fb72e206d73adf460aa585cfe624e4d8451",
        "xlsxwriter/format.py": "b9841e976120c4e41be47ee10ccb668a6c419258",
        "xlsxwriter/image.py": "4e631d06d549c7860f88cbdf2dcfc39a8d0bf7a1",
        "xlsxwriter/metadata.py": "f6f819d9950ccea25f2927acd4fb18368f430b21",
        "xlsxwriter/packager.py": "577e132bd8bd34a51ec71c1d4c1ec3b8d996712a",
        "xlsxwriter/pivot_cache.py": "ec4e04b29dc139b0c8bd6ad7f841288c31f4b8d5",
        "xlsxwriter/pivot_table.py": "bb767527f754f5a09b29b97efde69cccf0ee8f10",
        "xlsxwriter/relationships.py": "508f541302da12cf7cca739754da7ee38729be06",
        "xlsxwriter/rich_value.py": "fe4545b10c09b8321f1be7839b1f902f7e16628f",
        "xlsxwriter/rich_value_rel.py": "8aa344732a3ab4e4d2aa017ddd59174c1b38358b",
        "xlsxwriter/rich_value_structure.py": "ea94a5d816255be0eea09bc4e7099064f0f23b2b",
        "xlsxwriter/rich_value_types.py": "2f91c598f7e316f497d08d1453180287b66c66e7",
        "xlsxwriter/shape.py": "05e8a8eadcbfcb097bd72a4c09272746f21f581c",
        "xlsxwriter/sharedstrings.py": "fbb22bc2d8c158a82108151b831145f644bcc8a9",
        "xlsxwriter/styles.py": "7358e5d605e2f8d23dc92e174e84aec36f6a07a2",
        "xlsxwriter/table.py": "0a25b27eb2fb4133c340792f409e95c055773f9d",
        "xlsxwriter/theme.py": "0b05748a3208e1285162875df686e97b12eaf264",
        "xlsxwriter/url.py": "a1d1100d0b7fec32525de53e4c54acd488527fae",
        "xlsxwriter/utility.py": "a6eb4e03820dd0eefcb9cc0787cdba73b383d04d",
        "xlsxwriter/vml.py": "8165fcad45397d70055b5a3757c7597eb2e58405",
        "xlsxwriter/workbook.py": "000d28a5a696b3d922ed15d633b6d959b41ee1d0",
        "xlsxwriter/worksheet.py": "a5c48143ff2859be3c7030e35a6a9120e56a717b",
        "xlsxwriter/xmlwriter.py": "22f39463040ccd2fcf8b159fd4069ea69978fd85"
    }
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def record_hash(data):
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *map(str, args)], cwd=ROOT)


def names(*args):
    return set(git(*args).decode("utf-8").split("\0")) - {""}


def plain(path, directory=False):
    info = path.lstat()
    assert not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400, str(path)
    assert stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1, str(path)


def files(parent, top):
    result = set()
    plain(parent / top, True)
    for current, dirs, leaves in os.walk(parent / top, followlinks=False):
        folder = Path(current)
        for child in dirs:
            plain(folder / child, True)
        for child in leaves:
            path = folder / child
            plain(path)
            result.add(path.relative_to(parent).as_posix())
    return result


def records(raw):
    result = {}
    for row in csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline="")):
        assert len(row) == 3 and row[0] not in result
        result[row[0]] = tuple(row[1:])
    return result


def record_bytes(entries):
    text = io.StringIO(newline="")
    writer = csv.writer(text, lineterminator="\n")
    for path, pair in sorted(entries.items()):
        writer.writerow((path, *pair))
    return text.getvalue().encode("utf-8")


def check_record(parent, dist, owned):
    key = dist + "/RECORD"
    entries = records((parent / key).read_bytes())
    assert set(entries) == owned, ("RECORD inventory", sorted(set(entries) ^ owned))
    for path, pair in entries.items():
        plain(parent / path)
        data = (parent / path).read_bytes()
        assert pair == (("", "") if path == key else (record_hash(data), str(len(data)))), path


def normalized(name):
    return re.sub(r"[-_.]+", "-", name.lower())


def versions():
    found = {}
    for dist in md.distributions(path=[str(SITE)]):
        name = normalized(dist.metadata["Name"])
        assert name not in found
        found[name] = dist.version
    return found


def get(url, host, limit):
    u = urllib.parse.urlsplit(url)
    assert u.scheme == "https" and u.hostname == host and not u.username and not u.password
    req = urllib.request.Request(url, headers={"User-Agent": "Portable-fixed-wheel-audit/1"})
    with urllib.request.urlopen(req, timeout=60) as response:
        assert urllib.parse.urlsplit(response.url).hostname == host
        data = response.read(limit + 1)
    assert len(data) <= limit
    return data


def wheel_payload(name, version, sha, tag, license_id, wheelhouse):
    fn = name + "-" + version + "-" + tag + ".whl"
    release = json.loads(get("https://pypi.org/pypi/" + name + "/" + version + "/json", "pypi.org", 2 * 1024 * 1024))
    assert normalized(release["info"]["name"]) == name and release["info"]["version"] == version
    candidates = [x for x in release["urls"] if x["filename"] == fn]
    assert len(candidates) == 1
    item = candidates[0]
    assert item["packagetype"] == "bdist_wheel" and not item["yanked"]
    assert item["digests"]["sha256"] == sha and 0 < item["size"] < 2 * 1024 * 1024
    assert urllib.parse.urlsplit(item["url"]).path.endswith("/" + fn)
    data = get(item["url"], "files.pythonhosted.org", item["size"])
    assert len(data) == item["size"] and digest(data) == sha
    (wheelhouse / fn).write_bytes(data)
    dist = name + "-" + version + ".dist-info"
    data_script = name + "-" + version + ".data/scripts/vba_extract.py"
    payload = {}
    seen = set()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert len(z.infolist()) < 1500
        for info in z.infolist():
            p = info.filename.rstrip("/")
            parts = p.split("/")
            assert p and all(part and part not in (".", "..", ".git") and not part.endswith((" ", ".")) and not re.search(r'[<>:"\\|?*\x00-\x1f]', part) and not re.fullmatch(r"(?i)(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part) for part in parts), p
            assert p.casefold() not in seen and not stat.S_ISLNK(info.external_attr >> 16) and not (info.flag_bits & 1)
            assert info.file_size < 2 * 1024 * 1024
            seen.add(p.casefold())
            if info.is_dir():
                assert parts[0] in (name, dist, name + "-" + version + ".data")
                continue
            raw = z.read(info)
            if parts[0] == name:
                if name == "xlsxwriter":
                    assert len(parts) == 2 and p.endswith(".py"), p
                else:
                    assert (p == "tzdata/__init__.py" or p == "tzdata/zones" or
                            p.startswith("tzdata/zoneinfo/")), p
                    assert (raw.startswith(b"TZif") or p.endswith("/__init__.py") or
                            p in {"tzdata/zones", "tzdata/zoneinfo/tzdata.zi", "tzdata/zoneinfo/iso3166.tab",
                                  "tzdata/zoneinfo/zone.tab", "tzdata/zoneinfo/zone1970.tab",
                                  "tzdata/zoneinfo/zonenow.tab", "tzdata/zoneinfo/leapseconds"}), p
                    if p.endswith("/__init__.py") and p != "tzdata/__init__.py":
                        assert not raw.strip(), p
            elif parts[0] == dist:
                assert "/".join(parts[1:]) in {"METADATA", "WHEEL", "RECORD", "top_level.txt", "LICENSE.txt",
                    "licenses/LICENSE.txt", "licenses/LICENSE", "licenses/licenses/LICENSE_APACHE"}, p
            else:
                assert name == "xlsxwriter" and p == data_script, p
            payload[p] = raw
    rec = records(payload[dist + "/RECORD"])
    assert set(rec) == set(payload)
    for path, raw in payload.items():
        assert rec[path] == (("", "") if path == dist + "/RECORD" else (record_hash(raw), str(len(raw)))), path
    meta = email.parser.BytesParser().parsebytes(payload[dist + "/METADATA"])
    assert normalized(meta["Name"]) == name and meta["Version"] == version
    assert (meta["License-Expression"] or meta["License"]) == license_id
    assert SpecifierSet(meta["Requires-Python"]).contains("3.14.10")
    assert not meta.get_all("Requires-Dist", [])
    wheel = email.parser.BytesParser().parsebytes(payload[dist + "/WHEEL"])
    assert wheel["Root-Is-Purelib"].lower() == "true"
    assert set(wheel.get_all("Tag")) == ({"py3-none-any"} if name == "xlsxwriter" else {"py2-none-any", "py3-none-any"})
    if name == "xlsxwriter":
        source = XLSX_SOURCE[version]
        mapped = {p: git_blob(b) for p, b in payload.items() if p.startswith("xlsxwriter/")}
        mapped["examples/vba_extract.py"] = git_blob(payload[data_script])
        licenses = [p for p in payload if p.startswith(dist + "/") and p.endswith("/LICENSE.txt")]
        assert len(licenses) == 1
        mapped["LICENSE.txt"] = git_blob(payload[licenses[0]])
        assert mapped == source, ("tag-to-wheel source mismatch", sorted(set(mapped) ^ set(source)),
                                  sorted(p for p in mapped.keys() & source.keys() if mapped[p] != source[p]))
        payload["bin/vba_extract.py"] = payload.pop(data_script)
    print("OFFICIAL_WHEEL_AND_SOURCE=PASS " + name + " " + version + " " + sha, flush=True)
    return dist, payload


def run(argv, env, timeout=240):
    result = subprocess.run([str(x) for x in argv], cwd=ROOT, env=env, capture_output=True, timeout=timeout)
    print(result.stdout.decode("utf-8", "backslashreplace"), flush=True)
    print(result.stderr.decode("utf-8", "backslashreplace"), flush=True)
    assert result.returncode == 0, ("process failed", str(argv[0]), result.returncode)
    return result.stdout.decode("utf-8", "backslashreplace")


def replace_once(data, old, new):
    assert data.count(old) == 1, old
    return data.replace(old, new, 1)


def main(name):
    assert os.name == "nt" and sys.version_info[:3] == (3, 14, 10)
    assert Path(sys.executable).resolve() == PY and sys.flags.isolated and sys.flags.ignore_environment
    assert not git("status", "--porcelain=v1", "--untracked-files=all")
    assert os.environ.get("GITHUB_ACTIONS") == "true"
    assert os.environ.get("GITHUB_REPOSITORY") == "rileyaaa/Portable"
    assert os.environ.get("GITHUB_REF") == "refs/heads/dev/stable-tool-refresh"
    for path in (*reversed(SITE.parents), SITE):
        plain(path, True)
    old, new, old_sha, new_sha, tag, license_id = SPECS[name]
    before = versions()
    assert len(before) == 49 and before[name] == old and before["pip"] == "26.1.2"
    probe = ROOT / "tests/check_office_data_stable_refresh.py"
    assert probe.is_file()
    tmp = ROOT / "tmp"
    tmp.mkdir(exist_ok=True)
    plain(tmp, True)
    with tempfile.TemporaryDirectory(prefix="office-data-refresh-", dir=tmp) as d:
        own = Path(d)
        plain(own, True)
        env = {k: os.environ[k] for k in ("SystemRoot", "WINDIR", "SystemDrive", "ComSpec", "PATHEXT", "OS", "PROCESSOR_ARCHITECTURE") if k in os.environ}
        windows = Path(env["SystemRoot"])
        env["PATH"] = os.pathsep.join((str(PY.parent), str(ROOT / "tool/bin"), str(windows / "System32"), str(windows)))
        for key, rel in (("HOME", "home"), ("USERPROFILE", "home"), ("APPDATA", "appdata"),
                         ("LOCALAPPDATA", "localappdata"), ("PROGRAMDATA", "programdata"), ("ALLUSERSPROFILE", "programdata"),
                         ("TEMP", "temp"), ("TMP", "temp"), ("TMPDIR", "temp"), ("PIP_CACHE_DIR", "pip-cache"),
                         ("PYTHONUSERBASE", "python-user"), ("PYTHONPYCACHEPREFIX", "pycache")):
            folder = own / rel
            folder.mkdir(exist_ok=True)
            env[key] = str(folder)
        env.update(PIP_CONFIG_FILE=os.devnull, PSModuleAnalysisCachePath=str(own / "ModuleAnalysisCache"))
        def pip(*args):
            return run([PY, "-B", "-m", "pip", "--isolated", "--disable-pip-version-check",
                        "--no-input", "--cache-dir", env["PIP_CACHE_DIR"], *args], env)
        def consumer(version):
            marker = "XLSX_STABLE_REGRESSION=PASS" if name == "xlsxwriter" else "TZDATA_PACKAGE_ONLY_OFFSETS=PASS"
            assert marker in run([PY, "-B", probe, name, version], env)
        assert "No broken requirements found." in pip("check")
        consumer(old)
        wheelhouse = own / "wheelhouse"
        wheelhouse.mkdir()
        od, op = wheel_payload(name, old, old_sha, tag, license_id, wheelhouse)
        nd, np = wheel_payload(name, new, new_sha, tag, license_id, wheelhouse)
        assert not os.path.lexists(SITE / nd)
        if name == "tzdata":
            old_licenses = {p.split("/", 1)[1]: b for p, b in op.items() if p.startswith(od + "/licenses/")}
            new_licenses = {p.split("/", 1)[1]: b for p, b in np.items() if p.startswith(nd + "/licenses/")}
            # Exact tagged license files; the only change is an added copyright
            # notice in LICENSE. The full Apache-2.0 text is unchanged.
            assert {p: git_blob(b) for p,b in old_licenses.items()} == {
                "licenses/LICENSE": "c2f84aeb06f7a520b7cf17bdd9c9c3854dc4c469",
                "licenses/licenses/LICENSE_APACHE": "261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64"}
            assert {p: git_blob(b) for p,b in new_licenses.items()} == {
                "licenses/LICENSE": "a62e827c2862dda1a509f3998a42dbe48ddd0251",
                "licenses/licenses/LICENSE_APACHE": "261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64"}
            assert new_licenses["licenses/LICENSE"] == old_licenses["licenses/LICENSE"].replace(
                b"Copyright (c) 2020, Paul Ganssle (Google)\n",
                b"Copyright (c) 2020, Paul Ganssle (Google)\nCopyright (c) 2026, Stan Ulbrych\n",1)
            print("TZDATA_OFFICIAL_LICENSE_NOTICE=PASS",flush=True)
        old_owned = files(SITE, name) | files(SITE, od)
        if name == "xlsxwriter":
            plain(SITE / "bin", True)
            old_owned.add("bin/vba_extract.py")
        assert old_owned == set(op) | {od + "/INSTALLER", od + "/REQUESTED"}
        check_record(SITE, od, old_owned)
        for p in old_owned:
            assert git("cat-file", "blob", "HEAD:" + PREFIX + p) == (SITE / p).read_bytes(), p
        assert names("ls-files", "-z", "--", PREFIX + name, PREFIX + od,
                     *([PREFIX + "bin/vba_extract.py"] if name == "xlsxwriter" else [])) == {PREFIX + p for p in old_owned}
        for p, raw in op.items():
            actual = (SITE / p).read_bytes()
            if p == od + "/RECORD":
                continue
            if p == "bin/vba_extract.py":
                # Historical uv installation: only its rewritten first line is allowed.
                first, rest = actual.split(b"\n", 1)
                assert first.rstrip(b"\r") == b"#!D:\\Codex\\tool\\python\\python.exe"
                assert raw.split(b"\n", 1)[0] == b"#!python" and rest == raw.split(b"\n", 1)[1]
            else:
                assert actual == raw, ("old vendor mismatch", p)
        for rec in SITE.glob("*.dist-info/RECORD"):
            plain(rec.parent, True)
            plain(rec)
            if rec.parent.name != od:
                assert not (set(records(rec.read_bytes())) & old_owned), ("shared ownership", rec.parent.name)
        assert (SITE / od / "INSTALLER").read_bytes() == b"uv" and (SITE / od / "REQUESTED").read_bytes() == b""
        target = own / "stage"
        target.mkdir()
        requirement = own / "fixed.lock"
        requirement.write_text(name + "==" + new + " --hash=sha256:" + new_sha + "\n", encoding="ascii", newline="\n")
        pip("install", "--no-index", "--find-links", wheelhouse, "--no-deps", "--require-hashes",
            "--only-binary=:all:", "--no-compile", "--ignore-installed", "--requirement", requirement, "--target", target)
        expected_top = {name, nd} | ({"bin"} if name == "xlsxwriter" else set())
        assert {x.name for x in target.iterdir()} == expected_top
        new_owned = files(target, name) | files(target, nd)
        if name == "xlsxwriter":
            assert files(target, "bin") == {"bin/vba_extract.py"}
            new_owned.add("bin/vba_extract.py")
            script = target / "bin/vba_extract.py"
            actual = script.read_bytes()
            first, rest = actual.split(b"\n", 1)
            raw = np["bin/vba_extract.py"]
            assert first.rstrip(b"\r") == b"#!" + str(PY).encode("utf-8") and rest == raw.split(b"\n", 1)[1]
            assert raw.split(b"\n", 1)[0] == b"#!python"
            recpath = target / nd / "RECORD"
            entries = records(recpath.read_bytes())
            # pip --target's home scheme may record only this exact script
            # relative to the temporary purelib directory. Never traverse it.
            script_keys = set(entries) & {"bin/vba_extract.py", "../../bin/vba_extract.py"}
            assert len(script_keys) == 1
            key = script_keys.pop()
            assert entries.pop(key) == (record_hash(actual), str(len(actual)))
            script.write_bytes(raw)
            entries["bin/vba_extract.py"] = (record_hash(raw), str(len(raw)))
            recpath.write_bytes(record_bytes(entries))
        assert new_owned == set(np) | {nd + "/INSTALLER", nd + "/REQUESTED"}
        check_record(target, nd, new_owned)
        for p, raw in np.items():
            if p != nd + "/RECORD":
                assert (target / p).read_bytes() == raw, p
        assert (target / nd / "INSTALLER").read_bytes().strip() == b"pip"
        assert (target / nd / "REQUESTED").read_bytes() == b""
        backup = own / "backup"
        backup.mkdir()
        old_roots = [name, od] + (["bin/vba_extract.py"] if name == "xlsxwriter" else [])
        new_roots = [name, nd] + (["bin/vba_extract.py"] if name == "xlsxwriter" else [])
        moved_old = []
        moved_new = []
        inp = ROOT / "tool/python-packages.in.txt"
        lock = ROOT / "tool/python-packages.lock.txt"
        raw_input, raw_lock = inp.read_bytes(), lock.read_bytes()
        try:
            for p in old_roots:
                dest = backup / p
                dest.parent.mkdir(parents=True, exist_ok=True)
                (SITE / p).rename(dest)
                moved_old.append(p)
            for p in new_roots:
                (target / p).rename(SITE / p)
                moved_new.append(p)
            check_record(SITE, nd, new_owned)
            assert versions() == before | {name: new}
            assert "No broken requirements found." in pip("check")
            consumer(new)
            old_pin = ("XlsxWriter" if name == "xlsxwriter" else name) + "==" + old
            new_pin = old_pin.split("==")[0] + "==" + new
            new_input = replace_once(raw_input, old_pin.encode(), new_pin.encode())
            new_lock = replace_once(raw_lock, (name + "==" + old + " --hash=sha256:" + old_sha).encode(),
                                     (name + "==" + new + " --hash=sha256:" + new_sha).encode())
            new_lock = replace_once(new_lock, b"# requirements-sha256: " + digest(raw_input).encode(),
                                    b"# requirements-sha256: " + digest(new_input).encode())
            inp.write_bytes(new_input)
            lock.write_bytes(new_lock)
            allowed = {PREFIX + p for p in old_owned | new_owned} | {"tool/python-packages.in.txt", "tool/python-packages.lock.txt"}
            required = {PREFIX + p for p in old_owned ^ new_owned} | {"tool/python-packages.in.txt", "tool/python-packages.lock.txt"}
            changed = names("diff", "--no-renames", "--name-only", "-z") | names("ls-files", "--others", "--exclude-standard", "-z")
            assert required <= changed <= allowed, ("scope", sorted(required - changed), sorted(changed - allowed))
            print("OFFICE_DATA_CANDIDATE_READY=PASS " + name + " files=" + str(len(changed)), flush=True)
        except BaseException:
            # Only the paths moved by this invocation are rolled back.
            inp.write_bytes(raw_input)
            lock.write_bytes(raw_lock)
            for p in reversed(moved_new):
                source = SITE / p
                (target / p).parent.mkdir(parents=True, exist_ok=True)
                source.rename(target / p)
            for p in reversed(moved_old):
                (backup / p).rename(SITE / p)
            assert not git("status", "--porcelain=v1", "--untracked-files=all")
            raise


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    main(sys.argv[1])
