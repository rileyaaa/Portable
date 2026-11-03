#!/usr/bin/env python3
"""Stage full Win11 x64 stable tool updates in a read-only Windows Actions job.

This script does not publish, push, create a release or edit the user's machine.
Execute with a trusted runner Python, NOT tool/python/python.exe: Windows cannot
replace its own loaded DLLs. All downloads are confined to package tmp/.
"""
from __future__ import annotations

import base64
import csv
from email.parser import BytesParser
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tool"
# Exact repo-owned sibling import works both as a script and via unittest importlib.
_pure_spec = importlib.util.spec_from_file_location(
    "codex_portable_pure_wheels", Path(__file__).resolve().with_name("full_stable_pure_wheels.py"))
require_pure_spec = _pure_spec is not None and _pure_spec.loader is not None
if not require_pure_spec:
    raise RuntimeError("Missing trusted source-only wheel builder")
_pure_module = importlib.util.module_from_spec(_pure_spec)
_pure_spec.loader.exec_module(_pure_module)
build_pyyaml_pure_wheel = _pure_module.build_pyyaml_pure_wheel
PLAN = TOOL / "full-stable-upgrade-plan.json"
MAX_BYTES = 1100 * 1024 * 1024
MAX_FILES = 25000
WINDOWS_BAD = re.compile(r'[<>:"\\|?*\x00-\x1f]')
ALLOWED_HOSTS = {"www.python.org", "files.pythonhosted.org", "pypi.org", "registry.npmjs.org",
                 "github.com", "storage.googleapis.com", "cdn.playwright.dev"}
SSH = {"paramiko", "bcrypt", "cryptography", "invoke", "pynacl", "cffi", "pycparser"}


def require(value: bool, why: str) -> None:
    if not value:
        raise ValueError(why)


def obj(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8", newline="\n")


def sha(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def safe_path(name: str) -> tuple[str, ...]:
    require(name and not name.startswith(("/", "\\")) and not WINDOWS_BAD.search(name),
            "Unsafe archive member: " + repr(name))
    require("\\" not in name and not name.endswith((" ", ".")),
            "Unsafe archive path: " + repr(name))
    parts = name.strip("/").split("/")
    require(all(p and p not in (".", "..") and not p.endswith((" ", ".")) and
                not re.match(r"(?i)^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$", p)
                for p in parts), "Archive traversal/reserved name: " + repr(name))
    return tuple(parts)


def plain_tree(path: Path) -> None:
    for p in [path, *path.rglob("*")]:
        st = p.lstat()
        require(not stat.S_ISLNK(st.st_mode) and
                not (getattr(st, "st_file_attributes", 0) & 0x400),
                "Refuse reparse/symlink: " + str(p))
        require(stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode),
                "Refuse special file: " + str(p))
        if stat.S_ISREG(st.st_mode):
            require(st.st_nlink == 1, "Refuse hard link: " + str(p))


def download(url: str, target: Path, *, expected: str | None = None,
             limit: int = MAX_BYTES, integrity: str | None = None) -> dict:
    u = urllib.parse.urlsplit(url)
    require(u.scheme == "https" and u.hostname in ALLOWED_HOSTS and
            u.username is None and u.password is None and u.port in (None, 443) and
            not u.fragment, "Unapproved artifact URL: " + url)
    target.parent.mkdir(parents=True, exist_ok=True)
    require(not target.exists(), "Download target must be new: " + str(target))
    h256, h512 = hashlib.sha256(), hashlib.sha512()
    total = 0
    with urllib.request.urlopen(urllib.request.Request(
            url, headers={"User-Agent": "Codex-Portable-full-stable/1",
                          "Accept": "application/octet-stream"}), timeout=90) as response:
        final = urllib.parse.urlsplit(response.url)
        require(final.scheme == "https", "Download redirected to insecure HTTP")
        with target.open("xb") as out:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                total += len(block)
                require(total <= limit, "Artifact exceeds permitted size: " + url)
                h256.update(block)
                h512.update(block)
                out.write(block)
    digest = h256.hexdigest()
    if expected is not None:
        require(re.fullmatch(r"[a-f0-9]{64}", expected) is not None and digest == expected,
                "Pinned upstream SHA-256 mismatch: " + url)
    if integrity is not None:
        require(integrity == "sha512-" + base64.b64encode(h512.digest()).decode("ascii"),
                "npm package registry integrity mismatch")
    return {"url": url, "sha256": digest, "size": total}


def unzip_checked(source: Path, destination: Path, *, prefix: str = "",
                  max_total: int = MAX_BYTES) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    names: set[str] = set()
    total = 0
    with zipfile.ZipFile(source) as archive:
        entries = []
        for item in archive.infolist():
            raw = item.filename.rstrip("/")
            parts = safe_path(raw)
            if prefix:
                require(raw.startswith(prefix + "/"), "Archive contains unexpected root")
                parts = safe_path(raw[len(prefix) + 1:])
            name = "/".join(parts).casefold()
            require(name not in names, "Duplicate/case-colliding ZIP member")
            names.add(name)
            mode = stat.S_IFMT((item.external_attr >> 16))
            require(mode in (0, stat.S_IFREG, stat.S_IFDIR),
                    "ZIP member is a symlink/special file")
            if item.is_dir():
                continue
            total += item.file_size
            require(item.file_size <= max_total and total <= max_total and
                    len(entries) < MAX_FILES, "Unbounded ZIP expansion")
            entries.append((item, parts))
        for item, parts in entries:
            target = destination.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as incoming, target.open("xb") as outgoing:
                shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
    plain_tree(destination)


def untar_checked(source: Path, destination: Path, *, prefix: str = "package",
                  max_total: int = 300 * 1024 * 1024) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    total = 0
    names: set[str] = set()
    with tarfile.open(source, "r:gz") as archive:
        entries = []
        for member in archive.getmembers():
            raw = member.name.rstrip("/")
            parts = safe_path(raw)
            require(parts[0] == prefix, "Unexpected npm tar root")
            if len(parts) == 1:
                require(member.isdir(), "Invalid npm package root")
                continue
            rest = parts[1:]
            name = "/".join(rest).casefold()
            require(name not in names, "Duplicate npm tar entry")
            names.add(name)
            require(member.isfile() or member.isdir(), "Refuse tar link/special member")
            if member.isdir():
                continue
            total += member.size
            require(total <= max_total and len(entries) < MAX_FILES,
                    "Unbounded npm tar expansion")
            entries.append((member, rest))
        for member, parts in entries:
            target = destination.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as incoming, target.open("xb") as out:
                require(incoming is not None, "Missing tar stream")
                shutil.copyfileobj(incoming, out, 1024 * 1024)
    plain_tree(destination)


def run(*args: str | Path, cwd: Path | None = None,
        extra_env: dict | None = None, capture: bool = False):
    env = os.environ.copy()
    for k in ("PYTHONPATH", "PYTHONHOME", "NODE_PATH", "NODE_OPTIONS", "PIP_REQUIRE_VIRTUALENV",
              "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "NPM_CONFIG_PREFIX",
              "NPM_CONFIG_USERCONFIG", "NPM_CONFIG_GLOBALCONFIG"):
        env.pop(k, None)
    env.update({"PIP_CONFIG_FILE": "NUL", "PYTHONDONTWRITEBYTECODE": "1",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1"})
    if extra_env:
        env.update({k: str(v) for k, v in extra_env.items()})
    cmd = [str(x) for x in args]
    p = subprocess.run(cmd, cwd=cwd or ROOT, env=env, check=False,
                       text=True, capture_output=capture, encoding="utf-8", errors="replace")
    require(p.returncode == 0, "Command failed (" + str(p.returncode) + "): " +
            " ".join(cmd[:6]) + "\n" + (p.stderr or "")[-2000:])
    return p


def pins(path: Path) -> list[str]:
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==[A-Za-z0-9.!+_-]+", text)
        require(match is not None, "Unexpected existing Python dependency pin")
        result.append(match.group(1))
    return result


def target(plan: dict, name: str) -> dict:
    values = [v for v in plan["targets"] if v["name"] == name]
    require(len(values) == 1, "Missing/duplicate full refresh target " + name)
    return values[0]


def register_generated_pip_launchers(site: Path) -> None:
    """Own only three standard pip Windows entrypoints in pip's wheel RECORD.

    Pip's wheel ZIP has no EXE launchers, but the official wheel installed
    into --target creates three from its console_scripts. The original wheel
    RECORD must not be silently repurposed to claim arbitrary files.
    """
    record_files = list(site.glob("pip-*.dist-info/RECORD"))
    require(len(record_files) == 1,
            "Expected exactly one official pip dist-info RECORD")
    record = record_files[0]
    with record.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    require(all(len(row) == 3 for row in rows),
            "Malformed pip wheel RECORD")
    owned = {row[0].casefold() for row in rows}
    require(len(owned) == len(rows), "Duplicate path in pip wheel RECORD")
    for name in ("pip.exe", "pip3.exe", "pip3.15.exe"):
        rel = "bin/" + name
        require(rel.casefold() not in owned,
                "Generated pip launcher unexpectedly already owned")
        binary = site / rel
        require(binary.is_file() and binary.stat().st_size > 1024,
                "Missing actual official pip Windows launcher " + name)
        digest = base64.urlsafe_b64encode(
            bytes.fromhex(sha(binary))).rstrip(b"=").decode("ascii")
        rows.append([rel, "sha256=" + digest, str(binary.stat().st_size)])
    with record.open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream, lineterminator="\n").writerows(rows)


def select_official_pip_release_wheel(data: dict, version: str,
                                      expected_sha256: str) -> str:
    """Fail closed on PyPI's wheel identity before fetching executable package."""
    require(data["info"]["name"].lower() == "pip" and
            data["info"]["version"] == version and
            re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None,
            "Official PyPI metadata does not match fixed pip release")
    filename = f"pip-{version}-py3-none-any.whl"
    candidates = [
        file for file in data["urls"]
        if file.get("filename") == filename and
           file.get("packagetype") == "bdist_wheel" and
           file.get("yanked") is not True and
           file.get("digests", {}).get("sha256") == expected_sha256
    ]
    require(len(candidates) == 1, "Official pip wheel SHA-256 or identity changed")
    remote = candidates[0]["url"]
    parsed = urllib.parse.urlsplit(remote)
    require(parsed.scheme == "https" and
            parsed.hostname == "files.pythonhosted.org" and
            parsed.path.endswith("/" + filename) and
            not parsed.query and not parsed.fragment,
            "Unexpected pip wheel upstream download URL")
    return remote


def download_pinned_pip_wheel(plan: dict, temp: Path) -> tuple[Path, dict]:
    """Select pip's official stable py3 wheel using versioned PyPI JSON + fixed SHA."""
    row = target(plan, "pip")
    version = row["latestStable"]
    url = row["artifact"]["url"]
    require(version == "26.3" and row["artifact"].get("kind") ==
            "official-PyPI-metadata-pinned-wheel" and
            url == "https://pypi.org/pypi/pip/26.3/json",
            "Review official pip versioned release metadata")
    metadata_file = temp / "official-pip-release.json"
    download(url, metadata_file, limit=4*1024*1024)
    data = obj(metadata_file)
    filename = f"pip-{version}-py3-none-any.whl"
    remote = select_official_pip_release_wheel(
        data, version, row["artifact"]["sha256"])
    wheel = temp / filename
    evidence = download(remote, wheel, expected=row["artifact"]["sha256"],
                        limit=30*1024*1024)
    evidence["metadataUrl"] = url
    return wheel, evidence


def stage_pyyaml_pure_wheel(plan: dict, temp: Path, wheels: Path,
                            evidence: dict) -> dict:
    """Audit and repackage upstream PyYAML source; never use third-party cp315."""
    entries = plan["pythonPureSourceExceptions"]
    require(len(entries) == 1 and entries[0]["name"] == "PyYAML" and
            entries[0]["version"] == "6.0.3",
            "Unreviewed CPython 3.15 source-build exception")
    item = entries[0]
    source = temp / "pyyaml-official.tar.gz"
    provenance = download(item["sourceUrl"], source,
                          expected=item["sourceSha256"], limit=2*1024*1024)
    wheel = build_pyyaml_pure_wheel(source, wheels, item["sourceSha256"])
    digest = sha(wheel)
    with zipfile.ZipFile(wheel) as pkg:
        require(pkg.testzip() is None, "Generated PyYAML wheel corrupted")
    evidence["pure_python_pyyaml"] = {
        "upstream": provenance,
        "wheel_sha256": digest,
        "wheel": wheel.name,
        "compiledExtension": False,
        "sourceBuild": "Pinned original source repackage; no setup.py invocation",
    }
    evidence.setdefault("wheels", {})["pyyaml"] = {
        "url": item["sourceUrl"], "sha256": digest,
        "source_sha256": item["sourceSha256"],
        "size": wheel.stat().st_size, "derived": True
    }
    return {"version": item["version"], "sha256": digest,
            "wheel": wheel.name, "display_name": "PyYAML"}



def official_onnx_win315_wheel(record: dict, version: str) -> bool:
    """Recognize only official SHA-256-identified CPython 3.15 Windows x64 wheels."""
    if not isinstance(record, dict) or record.get("packagetype") != "bdist_wheel" or record.get("yanked") is True:
        return False
    digests = record.get("digests", {})
    if not isinstance(digests, dict):
        return False
    filename, url, digest = record.get("filename"), record.get("url"), digests.get("sha256")
    if not all(isinstance(x, str) for x in (filename, url, digest)):
        return False
    try:
        parsed = urllib.parse.urlsplit(url)
        if not (parsed.scheme == "https" and parsed.hostname == "files.pythonhosted.org" and
                parsed.username is None and parsed.password is None and parsed.port in (None, 443) and
                parsed.path.startswith("/packages/") and not parsed.query and not parsed.fragment and
                urllib.parse.unquote(parsed.path.rsplit("/", 1)[-1]) == filename and
                re.fullmatch(r"[a-f0-9]{64}", digest)):
            return False
    except ValueError:
        return False
    if not filename.endswith(".whl"):
        return False
    try:
        stem, python_tag, abi_tag, platform_tag = filename[:-4].rsplit("-", 3)
    except ValueError:
        return False
    if stem != "onnxruntime-" + version or "win_amd64" not in platform_tag.split("."):
        return False
    abis = set(abi_tag.split("."))
    for tag in python_tag.split("."):
        if tag == "cp315" and ("cp315" in abis or "abi3" in abis):
            return True
        if re.fullmatch(r"cp3\d\d", tag) and 311 <= int(tag[2:]) <= 315 and "abi3" in abis:
            return True
    return False


def official_legacy_pdf_wheels(data: dict, name: str, version: str) -> dict:
    """Pinned-in-run official CPython 3.15 compatible PDF wheels, without Layout."""
    require((name, version) in (("pymupdf", "1.28.2"), ("pymupdf4llm", "0.3.4")),
            "Unreviewed PDF legacy compatibility candidate")
    info, rows = data.get("info", {}), data.get("urls", [])
    require(isinstance(info, dict) and isinstance(rows, list) and
            str(info.get("name", "")).lower().replace("_", "-") == name and
            str(info.get("version", "")) == version and
            all(isinstance(row, dict) for row in rows),
            "Untrusted PyPI PDF fallback metadata: " + name)
    found = {}
    for record in rows:
        filename = record.get("filename")
        if record.get("packagetype") != "bdist_wheel" or not isinstance(filename, str):
            continue
        if name == "pymupdf":
            # PyMuPDF uses the stable ABI, so its official Windows x64
            # cp310-abi3 wheel is compatible with CPython 3.15.
            match = re.fullmatch(r"pymupdf-1\.28\.2-cp3(10|11|12|13|14|15)-abi3-win_amd64\.whl",
                                 filename)
        else:
            match = filename == "pymupdf4llm-0.3.4-py3-none-any.whl"
        if not match:
            continue
        url = record.get("url")
        digests = record.get("digests", {})
        digest = digests.get("sha256") if isinstance(digests, dict) else None
        require(official_optional_url(url) and record.get("yanked") is not True and
                urllib.parse.unquote(urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1]) == filename and
                re.fullmatch(r"[a-f0-9]{64}", digest or "") is not None and
                filename not in found,
                "Untrusted official PyPI PDF fallback wheel: " + str(filename))
        found[filename] = {"url": url, "sha256": digest}
    require(1 <= len(found) <= 3, "Missing compatible official PDF wheel: " + name)
    return dict(sorted(found.items()))


def select_pdf_compatibility(onnx: dict, temp: Path, evidence: dict) -> dict:
    """Use latest 2.x with ONNX if possible; otherwise stay with official 1.x legacy PDF."""
    info, rows = onnx.get("info", {}), onnx.get("urls", [])
    require(isinstance(info, dict) and isinstance(rows, list) and
            str(info.get("name", "")).lower().replace("_", "-") == "onnxruntime" and
            isinstance(info.get("version"), str) and
            re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", info["version"]) is not None,
            "Untrusted ONNX Runtime official PyPI latest-stable metadata")
    version = info["version"]
    compatible = [x for x in rows if official_onnx_win315_wheel(x, version)]
    if compatible:
        compatible.sort(key=lambda x: x["filename"])
        evidence["onnxruntime_preflight"] = {
            "version": version,
            "wheels": {row["filename"]: {"url": row["url"],
                                         "sha256": row["digests"]["sha256"]}
                       for row in compatible}}
        policy = {"mode": "latest-with-layout", "pymupdf": ">=2.1",
                  "pymupdf4llm": ">=2.1", "onnxruntime": version}
    else:
        # The official 4LLM 0.3.4 release makes Layout an OPTIONAL extra.
        # It retains the pre-upgrade package's text/Markdown functionality.
        fallback = {}
        for name, selected_version in (("pymupdf", "1.28.2"),
                                       ("pymupdf4llm", "0.3.4")):
            file = temp / ("pypi-" + name + "-" + selected_version + ".json")
            download("https://pypi.org/pypi/" + name + "/" + selected_version + "/json",
                     file, limit=4 * 1024 * 1024)
            fallback[name] = official_legacy_pdf_wheels(obj(file), name, selected_version)
        evidence["pdf_fallback_wheels"] = fallback
        policy = {"mode": "latest-compatible-legacy-pdf", "pymupdf": "1.28.2",
                  "pymupdf4llm": "0.3.4",
                  "layout": "not installed: no official CPython 3.15 ONNX Runtime",
                  "onnxruntime_latest": version}
    evidence["pdf_compatibility"] = policy
    print("PDF_PYTHON315_COMPATIBILITY=" + policy["mode"], flush=True)
    return policy


def verify_pdf_resolver(policy: dict, resolved: dict, evidence: dict) -> None:
    """Reject downgrades, mismatched shims and changed wheels after the PyPI preflight."""
    mode = policy["mode"]
    if mode == "latest-compatible-legacy-pdf":
        for name in ("pymupdf", "pymupdf4llm"):
            item = resolved.get(name)
            require(item is not None and item["version"] == policy[name],
                    "Official CPython 3.15 legacy PDF package not selected: " + name)
            expected = evidence["pdf_fallback_wheels"][name].get(item["wheel"])
            require(expected is not None and expected["sha256"] == item["sha256"] and
                    expected["url"] == evidence["wheels"][name]["url"],
                    "PDF fallback official wheel provenance changed: " + name)
        require("pymupdf-layout" not in resolved and "onnxruntime" not in resolved,
                "Legacy PDF compatibility path must not silently install Layout/ONNX")
    else:
        version = resolved["pymupdf"]["version"]
        require(version == resolved["pymupdf4llm"]["version"] ==
                resolved["pymupdf-layout"]["version"] and
                tuple(int(x) for x in version.split(".")) >= (2, 1),
                "Modern PyMuPDF Core/Layout/4LLM versions differ")
        item = resolved.get("onnxruntime")
        require(item is not None and item["version"] == policy["onnxruntime"] and
                evidence["onnxruntime_preflight"]["wheels"].get(item["wheel"], {}).get("sha256") == item["sha256"],
                "Latest ONNX Runtime CPython 3.15 wheel provenance mismatch")


def preflight_python315_onnxruntime(temp: Path, evidence: dict) -> None:
    """Before downloads, choose verified modern Layout or official legacy PDF."""
    meta = temp / "pypi-onnxruntime-latest.json"
    download("https://pypi.org/pypi/onnxruntime/json", meta, limit=4 * 1024 * 1024)
    select_pdf_compatibility(obj(meta), temp, evidence)


def stage_python(plan: dict, temp: Path, evidence: dict) -> tuple[Path, dict]:
    row, pip = target(plan, "python"), target(plan, "pip")
    require(row["latestStable"] == "3.15.2" and pip["latestStable"] == "26.3",
            "Review latest Python and pip before preparing")
    archive = temp / "python.zip"
    evidence["python_archive"] = download(row["artifact"]["url"], archive,
                                           expected=row["artifact"]["sha256"],
                                           limit=30 * 1024 * 1024)
    stage = temp / "python-runtime"
    unzip_checked(archive, stage, max_total=80 * 1024 * 1024)
    require((stage / "python315.dll").is_file() and
            (stage / "python315.zip").is_file() and
            (stage / "python315._pth").is_file(), "Not a CPython 3.15 embedded runtime")
    (stage / "Lib/site-packages").mkdir(parents=True)
    (stage / "Scripts").mkdir()
    (stage / "python315._pth").write_bytes(
        b"python315.zip\r\n.\r\nLib\\site-packages\r\nimport site\r\n")
    pipwheel, evidence["pip_wheel"] = download_pinned_pip_wheel(plan, temp)
    unzip_checked(pipwheel, stage / "Lib/site-packages", max_total=40*1024*1024)
    python = stage / "python.exe"
    run(python, "-E", "-s", "-B", "-m", "pip", "--version")
    base_names = pins(TOOL / "python-packages.in.txt")
    ssh_names = pins(TOOL / "python-ssh-packages.in.txt")
    require(set(x.lower().replace("_", "-") for x in ssh_names) == SSH,
            "Unexpected SSH closure")
    requested = sorted(set(base_names + ssh_names), key=str.casefold)
    require(sum(x.lower().replace("_", "-") == "pyyaml" for x in requested) == 1,
            "Expected exactly one bundled PyYAML distribution")
    binary_requests = [x for x in requested if x.lower().replace("_", "-") != "pyyaml"]
    # An upstream CPython 3.15 ONNX Runtime gap must not block the entire
    # Python refresh or silently degrade already bundled PDF-to-Markdown.
    pdf = evidence["pdf_compatibility"]
    require(pdf["mode"] in ("latest-with-layout", "latest-compatible-legacy-pdf"),
            "Unreviewed PDF compatibility policy")
    binary_requests = [
        x + (">=2.1" if pdf["mode"] == "latest-with-layout"
             else "==" + pdf[x.lower().replace("_", "-")])
        if x.lower().replace("_", "-") in ("pymupdf", "pymupdf4llm") else x
        for x in binary_requests]
    spellings = {x.lower().replace('_', '-'): x for x in base_names + ssh_names}
    (temp / "requirements.in").write_text("\n".join(binary_requests) + "\n", encoding="utf-8")
    report_path = temp / "python-resolution.json"
    run(python, "-E", "-s", "-B", "-m", "pip", "install", "--dry-run",
        "--ignore-installed", "--no-input", "--disable-pip-version-check",
        "--only-binary=:all:", "--index-url", "https://pypi.org/simple",
        "--report", report_path, "-r", temp / "requirements.in",
        extra_env={"PIP_CACHE_DIR": temp / "pip-cache"})
    report = obj(report_path)
    require(report.get("version") == "1" and isinstance(report.get("install"), list),
            "Unsupported pip resolver report")
    resolved: dict[str, dict] = {}
    wheels = temp / "wheels"
    wheels.mkdir()
    for item in report["install"]:
        info, remote = item.get("metadata", {}), item.get("download_info", {})
        require(item.get("is_yanked") is not True, "Yanked PyPI distribution refused")
        name = str(info.get("name", "")).lower().replace("_", "-")
        version = str(info.get("version", ""))
        url = remote.get("url", "")
        parsed = urllib.parse.urlsplit(url)
        digest = remote.get("archive_info", {}).get("hashes", {}).get("sha256")
        require(re.fullmatch(r"[a-z0-9][a-z0-9.-]+", name) is not None and
                re.fullmatch(r"[0-9][A-Za-z0-9.!+_-]+", version) is not None and
                not re.search(r"(?:a|b|rc|dev)\d+|alpha|beta", version, re.I),
                "Non-stable Python version or invalid distribution: " + str(info))
        require(name not in resolved and parsed.scheme == "https" and
                parsed.hostname == "files.pythonhosted.org" and
                parsed.path.endswith(".whl") and not parsed.query and
                not parsed.fragment and re.fullmatch(r"[a-f0-9]{64}", digest or ""),
                "Missing verified PyPI wheel identity")
        wheelname = urllib.parse.unquote(parsed.path.split("/")[-1])
        safe_path(wheelname)
        local = wheels / wheelname
        require(not local.exists(), "Wheel filename collision")
        evidence.setdefault("wheels", {})[name] = download(
            url, local, expected=digest, limit=90*1024*1024)
        with zipfile.ZipFile(local) as wf:
            require(wf.testzip() is None, "Corrupt PyPI wheel")
        resolved[name] = {"version": version, "sha256": digest, "wheel": wheelname,
                          "display_name": spellings.get(name, str(info["name"]))}
    require("pyyaml" not in resolved, "Wheel-only resolver unexpectedly selected PyYAML")
    verify_pdf_resolver(pdf, resolved, evidence)
    resolved["pyyaml"] = stage_pyyaml_pure_wheel(plan, temp, wheels, evidence)
    for name in requested:
        norm = name.lower().replace("_", "-")
        require(norm in resolved, "Resolver omitted requested package " + norm)
    require(resolved["pip"]["version"] == pip["latestStable"] and
            resolved["pyinstaller"]["version"] == target(plan, "pyinstaller")["latestStable"] and
            resolved["paramiko"]["version"] == target(plan, "paramiko")["latestStable"],
            "Python latest-stable major or dependency target diverged")
    def generate(source_name: str, names: set[str]) -> tuple[str, str]:
        ordered = sorted(names)
        inp = "# Win11 x64 Python 3.15.2 official stable wheel closure; auto-resolved.\n"
        inp += "".join(resolved[n]["display_name"] + "==" + resolved[n]["version"] + "\n"
                       for n in ordered)
        ihash = hashlib.sha256(inp.encode("utf-8")).hexdigest()
        lock = ("# Codex Portable wheel lock v1\n# requirements-sha256: " + ihash +
                "\n# Exact selected wheel hashes; install with --require-hashes --only-binary=:all:.\n")
        lock += "".join(n + "==" + resolved[n]["version"] +
                        " --hash=sha256:" + resolved[n]["sha256"] + "\n" for n in ordered)
        (TOOL / source_name).write_text(inp, encoding="utf-8", newline="\n")
        (TOOL / source_name.replace(".in.txt", ".lock.txt")).write_text(
            lock, encoding="utf-8", newline="\n")
        return inp, lock
    base_set = set(resolved) - SSH
    ssh_set = set(resolved) & SSH
    require(ssh_set == SSH and len(base_set) >= 38, "Python dependency closure too small")
    generate("python-packages.in.txt", base_set)
    generate("python-ssh-packages.in.txt", ssh_set)
    # Build vendor pip EXE launchers in a separate isolated target. Merely
    # unzipping pip's wheel into site-packages does not generate pip.exe,
    # pip3.exe or pip3.15.exe; without these, refresh-python-cli-shims.py
    # would delete the existing portable pip CMD wrappers as obsolete.
    # Never replace pip's loaded code in its own running interpreter.
    pip_launch = temp / "pip-launchers-target"
    pip_launch.mkdir()
    pip_launcher_lock = temp / "pip-launcher-lock.txt"
    pip_launcher_lock.write_text("pip==" + resolved["pip"]["version"] +
                                " --hash=sha256:" + resolved["pip"]["sha256"] + "\n",
                                encoding="utf-8")
    run(python, "-E", "-s", "-B", "-m", "pip", "install", "--no-input",
        "--no-deps", "--no-compile", "--no-index", "--only-binary=:all:",
        "--require-hashes", "--no-warn-script-location",
        "--find-links", wheels, "--target", pip_launch,
        "-r", pip_launcher_lock,
        extra_env={"PIP_CACHE_DIR": temp / "pip-cache"})
    # pip's own invocation above is anchored to official pinned wheel bytes,
    # even though this synthetic pip launcher staging does not mutate the
    # already verified bootstrapped pip import tree.
    vendor = pip_launch / "bin"
    require(vendor.is_dir(), "pip 3.15 vendor entry points not generated")
    for name in ("pip.exe", "pip3.exe", "pip3.15.exe"):
        candidate = vendor / name
        require(candidate.is_file() and candidate.stat().st_size > 1024,
                "pip 26.3 is missing expected Windows launcher " + name)
    # Avoid creating Lib/site-packages/bin BEFORE installing other base wheels:
    # pip --target refuses to merge a new bin/ tree into an existing bin/
    # (it warned about this in the failed Windows run). That silently loses
    # new CLI entrypoints. Merge the three pinned pip launchers only after
    # all the base wheels' scripts have been installed.
    # pip was bootstrapped directly from the same officially hashed wheel.
    for label, output in (("base", stage / "Lib/site-packages"),
                          ("ssh", stage / "ssh-packages")):
        selected = base_set if label == "base" else ssh_set
        if label == "ssh":
            output.mkdir()
        wheel_lock = temp / (label + "-install.txt")
        wheel_lock.write_text("".join(n+"=="+resolved[n]["version"]+
                                     " --hash=sha256:"+resolved[n]["sha256"]+"\n"
                                     for n in sorted(selected) if n != "pip"),
                              encoding="utf-8")
        run(python, "-E", "-s", "-B", "-m", "pip", "install", "--no-input",
            "--no-deps", "--no-compile", "--no-index", "--only-binary=:all:",
            "--require-hashes", "--no-warn-script-location",
            "--find-links", wheels, "--target", output, "-r", wheel_lock,
            extra_env={"PIP_CACHE_DIR": temp / "pip-cache"})
    # Base wheel installation has now created its own bin/ launchers. Preserve
    # them exactly, then add only the three official pip 26.3 launcher templates.
    scripts = stage / "Lib/site-packages/bin"
    require(scripts.is_dir(), "Base wheels did not create required CLI launchers")
    before = {item.name.casefold() for item in scripts.iterdir() if item.is_file()}
    # These come from the newly installed, pinned PyInstaller 6.22.3 wheel.
    # Previously pip skipped the entire scripts/ tree when bin/ already existed.
    require({"pyinstaller.exe", "pyi-makespec.exe"} <= before,
            "Expected PyInstaller Windows launchers were dropped during pip --target")
    require(not any(n in before for n in ("pip.exe", "pip3.exe", "pip3.15.exe")),
            "Conflicting pip launcher in another installed distribution")
    for name in ("pip.exe", "pip3.exe", "pip3.15.exe"):
        shutil.copyfile(vendor / name, scripts / name)
    register_generated_pip_launchers(stage / "Lib/site-packages")
    require(before.issubset({p.name.casefold() for p in scripts.iterdir()}),
            "Another base package console launcher was removed")
    (stage / "Lib/site-packages/codex_portable_ssh.pth").write_text(
        "../../ssh-packages\n", encoding="ascii")
    plain_tree(stage)
    evidence["python_native_architectures"] = check_python_native_architecture(stage)
    evidence["python_packages"] = resolved
    return stage, resolved


def replace_tree(source: Path, destination: Path, scratch: Path) -> None:
    require(source.is_dir() and destination.is_dir(), "Refuse missing tool tree")
    plain_tree(source)
    backup = scratch / ("backup-" + destination.name + "-" + str(len(list(scratch.iterdir()))))
    destination.rename(backup)
    try:
        source.rename(destination)
    except Exception:
        backup.rename(destination)
        raise


def npm_metadata(name: str, version: str, temp: Path) -> tuple[str, str]:
    require(re.fullmatch(r"[a-z0-9._-]+", name) and
            re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}", version),
            "Bad npm identity")
    meta_path = temp / (name + "-metadata.json")
    download("https://registry.npmjs.org/" + name + "/" + version,
             meta_path, limit=4*1024*1024)
    row = obj(meta_path)
    require(row.get("name") == name and row.get("version") == version,
            "Registry package/version mismatch")
    dist = row["dist"]
    url = f"https://registry.npmjs.org/{name}/-/{name}-{version}.tgz"
    require(dist.get("tarball") == url and
            re.fullmatch(r"sha512-[A-Za-z0-9+/]+={0,2}", dist.get("integrity", "")),
            "Official npm tarball/integrity not present")
    return url, dist["integrity"]


def stage_npm(plan: dict, temp: Path, evidence: dict) -> None:
    node, npm = TOOL / "node/node.exe", target(plan, "npm")
    core = target(plan, "corepack")
    require(node.is_file() and npm["latestStable"] == "12.2.1" and
            core["latestStable"] == "0.36.0", "Unexpected Node/npm/Corepack plan")
    url, integrity = npm_metadata("npm", npm["latestStable"], temp)
    npm_tar = temp / "npm.tgz"
    evidence["npm_archive"] = download(url, npm_tar, limit=30*1024*1024,
                                       integrity=integrity)
    evidence["npm_archive"]["integrity"] = integrity
    npm_dir = temp / "npm-unpacked"
    untar_checked(npm_tar, npm_dir)
    npm_info = obj(npm_dir / "package.json")
    require(npm_info["name"] == "npm" and npm_info["version"] == npm["latestStable"] and
            (npm_dir / "bin/npm-cli.js").is_file(), "Invalid npm v12 CLI payload")
    core_tar = temp / "corepack.tgz"
    evidence["corepack_archive"] = download(core["artifact"]["url"], core_tar,
                                            expected=core["artifact"]["sha256"],
                                            limit=40*1024*1024)
    core_dir = temp / "corepack-unpacked"
    untar_checked(core_tar, core_dir)
    core_info = obj(core_dir / "package.json")
    require(core_info["name"] == "corepack" and core_info["version"] == core["latestStable"] and
            (core_dir / "dist/corepack.js").is_file(), "Invalid Corepack 0.36 payload")
    replace_tree(npm_dir, TOOL / "node/node_modules/npm", temp)
    replace_tree(core_dir, TOOL / "node/node_modules/corepack", temp)
    require((TOOL / "node/portable-npm.js").is_file() and
            all((TOOL / "node" / n).is_file()
                for n in ("npm", "npm.cmd", "npm.ps1", "npx", "npx.cmd", "npx.ps1",
                          "corepack", "corepack.cmd")),
            "Existing portable npm/npx/Corepack shims were lost")
    run(node, TOOL / "node/node_modules/npm/bin/npm-cli.js", "--version")
    run(node, TOOL / "node/node_modules/corepack/dist/corepack.js", "--version")


def pe_amd64(path: Path) -> bool:
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            return False
        stream.seek(0, 2)
        length = stream.tell()
        if length < 0x80:
            return False
        stream.seek(0x3c)
        offset = int.from_bytes(stream.read(4), "little")
        if not (64 <= offset <= length - 6):
            return False
        stream.seek(offset)
        return stream.read(4) == b"PE\x00\x00" and stream.read(2) == b"\x64\x86"


# These are *inert vendor launcher templates* distributed as data in the
# official hash-checked Windows wheels. They are not package entry points and
# are never launched. Multi-architecture resources are required by setuptools
# and pip to construct Windows entrypoints for other targets.
INERT_WHEEL_LAUNCHERS = {
    "setuptools/cli-32.exe": 0x014c,
    "setuptools/gui-32.exe": 0x014c,
    # setuptools 84.2.1 also ships un-suffixed aliases byte-identical to x86.
    "setuptools/cli.exe": 0x014c,
    "setuptools/gui.exe": 0x014c,
    "setuptools/cli-arm64.exe": 0xaa64,
    "setuptools/gui-arm64.exe": 0xaa64,
    "pip/_vendor/distlib/t32.exe": 0x014c,
    "pip/_vendor/distlib/w32.exe": 0x014c,
    "pip/_vendor/distlib/t64-arm.exe": 0xaa64,
    "pip/_vendor/distlib/w64-arm.exe": 0xaa64,
}


def pe_machine(path: Path) -> int | None:
    """Read PE COFF Machine without loading or running an untrusted binary."""
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            return None
        stream.seek(0, 2)
        length = stream.tell()
        if length < 0x80:
            return None
        stream.seek(0x3c)
        offset = int.from_bytes(stream.read(4), "little")
        if not (64 <= offset <= length - 6):
            return None
        stream.seek(offset)
        if stream.read(4) != b"PE\x00\x00":
            return None
        return int.from_bytes(stream.read(2), "little")


def check_python_native_architecture(root: Path) -> dict:
    """Verify ALL staged native payloads, with ten exact data-only exceptions.

    Each exception remains backed by its own upstream SHA-256-pinned wheel
    and must have precisely the named PE machine architecture. Unexpected x86,
    ARM64, malformed PE, DLL or PYD payloads are always rejected.
    """
    require(root.is_dir(), "Missing staged Python directory")
    counts = {"amd64": 0, "inert_x86": 0, "inert_arm64": 0}
    allowed_base = root / "Lib/site-packages"
    actual_inert: set[str] = set()
    for native in root.rglob("*"):
        if not native.is_file() or native.suffix.lower() not in (".pyd", ".dll", ".exe"):
            continue
        machine = pe_machine(native)
        approved = None
        if native.is_relative_to(allowed_base):
            name = native.relative_to(allowed_base).as_posix().casefold()
            approved = INERT_WHEEL_LAUNCHERS.get(name)
        if approved is None:
            require(machine == 0x8664,
                    "Active/nonexception Python native file is not Windows AMD64 PE: " +
                    str(native) + " (machine=" + hex(machine or 0) + ")")
            counts["amd64"] += 1
        else:
            require(native.suffix.lower() == ".exe" and machine == approved,
                    "Vendor data-only launcher PE machine mismatches reviewed identity: " +
                    str(native) + " (machine=" + hex(machine or 0) + ")")
            require(name not in actual_inert, "Duplicate inert upstream launcher")
            actual_inert.add(name)
            counts["inert_x86" if approved == 0x014c else "inert_arm64"] += 1
    require(counts["amd64"] >= 5,
            "Staged CPython 3.15 and Windows native wheel payloads are incomplete")
    return counts


def stage_7zip(plan: dict, temp: Path, evidence: dict) -> None:
    row = target(plan, "7zip")
    require(row["latestStable"] == "26.05" and
            row["artifact"]["url"].endswith("/7z2605-x64.exe"),
            "Require approved x64 7-Zip SFX artifact, not standalone reduced Extra")
    archive = temp / "7zip-installer-as-data.exe"
    evidence["7zip_archive"] = download(row["artifact"]["url"], archive,
                                        expected=row["artifact"]["sha256"],
                                        limit=20*1024*1024)
    old_exe = TOOL / "bin/7z.exe"
    require(pe_amd64(old_exe), "Existing trusted 7z.exe must be Windows AMD64")
    stage = temp / "seven-extracted"
    stage.mkdir()
    # Crucially, execute only the OLD bundled 7z.exe, NEVER the SFX installer.
    # Official Win64 SFX is treated as a read-only archive inside package tmp.
    run(old_exe, "x", "-y", "-bd", "-o" + str(stage), archive)
    plain_tree(stage)
    chosen = {}
    for name in ("7z.exe", "7z.dll"):
        candidates = [p for p in stage.rglob(name) if p.is_file() and pe_amd64(p)]
        require(len(candidates) == 1,
                "Official x64 7-Zip SFX lacks one unique AMD64 " + name)
        chosen[name] = candidates[0]
    require(chosen["7z.exe"].parent == chosen["7z.dll"].parent,
            "7z.exe and 7z.dll must come from the same official x64 package root")
    for name in ("7z.exe", "7z.dll"):
        shutil.copyfile(chosen[name], TOOL / "bin" / name)
    version = run(TOOL / "bin/7z.exe", "i", capture=True).stdout
    require(re.search(r"(?i)7-Zip\s+26\.05\b", version) is not None,
            "Extracted full 7-Zip native version differs from official 26.05")

def npm_env(temp: Path) -> dict:
    """Provide distinct, empty user/global npmrc files inside owned scratch.

    npm 12 (and npm 10/11) refuses loading the *same* npmrc twice: 'double-
    loading config as global, previously loaded as user'. Never point both
    configuration scopes at one path even if the file contains zero bytes.
    """
    require(temp.is_dir() and not temp.is_symlink(),
            "Npm scratch must be an owned ordinary directory")
    user = temp / "user.npmrc"
    global_ = temp / "global.npmrc"
    require(user != global_ and user.resolve() != global_.resolve(),
            "npm userconfig and globalconfig must be independent paths")
    for item in (user, global_):
        require(not item.is_symlink(), "Refuse linked npmrc")
        if item.exists():
            require(item.is_file() and item.stat().st_size == 0,
                    "Isolated npmrc must remain empty: " + str(item))
        else:
            item.write_text("", encoding="utf-8")
    home = temp / "npm-home"
    home.mkdir(exist_ok=True)
    return {"NPM_CONFIG_CACHE": temp / "npm-cache",
            "NPM_CONFIG_USERCONFIG": user,
            "NPM_CONFIG_GLOBALCONFIG": global_,
            "NPM_CONFIG_REGISTRY": "https://registry.npmjs.org",
            "NPM_CONFIG_UPDATE_NOTIFIER": "false",
            "NPM_CONFIG_AUDIT": "false",
            "NPM_CONFIG_FUND": "false", "HOME": home, "USERPROFILE": home,
            "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1"}


def verify_npm_config_isolation(node: Path, npm: Path,
                                project: Path, env: dict) -> None:
    """Read-only npm config probe, before any dependency registry request."""
    require(project.is_dir(), "Missing isolated npm workspace")
    files = {}
    for key in ("USERCONFIG", "GLOBALCONFIG"):
        expected = Path(env["NPM_CONFIG_" + key])
        require(expected.is_file() and expected.stat().st_size == 0,
                "Npm config file is missing or not blank")
        result = run(node, npm, "config", "get", key.lower(),
                     cwd=project, extra_env=env, capture=True)
        actual = Path(result.stdout.strip())
        require(actual.resolve() == expected.resolve(),
                "npm config scope escaped isolated workspace: " + key)
        files[key] = actual.resolve()
    require(files["USERCONFIG"] != files["GLOBALCONFIG"],
            "npm user and global configs unexpectedly alias")


def stage_playwright(plan: dict, temp: Path, evidence: dict) -> tuple[str, str]:
    mcp = target(plan, "playwright-mcp")
    require(mcp["latestStable"] == "0.0.84", "Review newer Playwright MCP release")
    project = temp / "browser-project"
    project.mkdir()
    write_json(project / "package.json", {
        "name": "codex-portable-browser-tools", "version": "1.0.0", "private": True,
        "description": "Pinned latest stable Playwright MCP with package-local Chromium",
        "dependencies": {"@playwright/mcp": mcp["latestStable"]}})
    node = TOOL / "node/node.exe"
    npm = TOOL / "node/node_modules/npm/bin/npm-cli.js"
    env = npm_env(temp)
    verify_npm_config_isolation(node, npm, project, env)
    run(node, npm, "install", "--package-lock-only", "--ignore-scripts",
        "--no-audit", "--no-fund", "--no-update-notifier", cwd=project, extra_env=env)
    run(node, npm, "ci", "--ignore-scripts", "--bin-links=false",
        "--no-audit", "--no-fund", "--no-update-notifier", cwd=project, extra_env=env)
    lock = obj(project / "package-lock.json")
    packages = lock["packages"]
    require(packages["node_modules/@playwright/mcp"]["version"] == mcp["latestStable"],
            "Wrong Playwright MCP dependency")
    playwright_version = packages["node_modules/playwright"]["version"]
    require(playwright_version == packages["node_modules/playwright-core"]["version"],
            "Playwright / playwright-core must match exactly")
    require(playwright_version == "1.65.0-alpha-2026-10-30",
            "Upstream Playwright MCP pinned browser framework changed; review required")
    for name, item in packages.items():
        if not name:
            continue
        require(item.get("resolved", "").startswith("https://registry.npmjs.org/") and
                item.get("integrity", "").startswith("sha512-"),
                "npm lock contains unsigned/non-official dependency")
    browsers = obj(project / "node_modules/playwright-core/browsers.json")["browsers"]
    matching = [b for b in browsers if b.get("name") == "chromium"]
    require(len(matching) == 1, "Missing unique pinned Chromium")
    info = matching[0]
    version, revision = str(info["browserVersion"]), str(info["revision"])
    require(re.fullmatch(r"\d+\.\d+\.\d+\.\d+", version) and
            re.fullmatch(r"\d+", revision), "Invalid Chromium identity")
    replace_tree(project, TOOL / "automation/playwright", temp)
    manifest_files = {}
    for f in (TOOL / "automation/playwright/node_modules").rglob("*"):
        if f.is_file():
            manifest_files[f.relative_to(ROOT).as_posix()] = sha(f)
    require(len(manifest_files) > 100, "Playwright dependencies are incomplete")
    write_json(TOOL / "automation/dependency-manifest.json", {
        "source": "https://registry.npmjs.org/@playwright/mcp",
        "integrity_records": "playwright/package-lock.json",
        "installation": "npm ci --ignore-scripts --bin-links=false; official archive payloads",
        "files": dict(sorted(manifest_files.items()))})
    evidence["playwright"] = {"mcp": mcp["latestStable"],
                              "playwright": playwright_version,
                              "chromiumVersion": version, "revision": revision}
    return version, revision


def stage_browser(temp: Path, version: str, revision: str, evidence: dict) -> None:
    url = ("https://storage.googleapis.com/chrome-for-testing-public/" + version +
           "/win64/chrome-win64.zip")
    archive = temp / "chrome-win64.zip"
    evidence["browser_archive"] = download(url, archive, limit=500*1024*1024)
    stage = temp / "browser-unpacked"
    unzip_checked(archive, stage, max_total=800*1024*1024)
    require((stage / "chrome-win64/chrome.exe").is_file(),
            "Browser ZIP lacks Chrome for Testing executable")
    browser_dir = TOOL / "automation/browsers"
    require(browser_dir.is_dir(), "Original Chromium package is missing")
    for old in browser_dir.iterdir():
        require(old.is_dir() and old.name.startswith("chromium-"),
                "Unreviewed item in browsers root")
        plain_tree(old)
        shutil.rmtree(old)
    (stage).rename(browser_dir / ("chromium-" + revision))
    payload = browser_dir / ("chromium-" + revision)
    paths: dict[str, dict] = {}
    for file in payload.rglob("*"):
        if file.is_file():
            paths[file.relative_to(ROOT).as_posix()] = {
                "sha256": sha(file), "size": file.stat().st_size}
    require(150 <= len(paths) <= 800, "Unexpected browser file count")
    write_json(TOOL / "automation/browser-manifest.json", {
        "schemaVersion": 1, "browserVersion": version, "revision": revision,
        "platform": "win32-x64",
        "archive": {
            "sourceUrl": f"https://cdn.playwright.dev/builds/cft/{version}/win64/chrome-win64.zip",
            "resolvedUrl": url,
            "sha256": evidence["browser_archive"]["sha256"],
            "size": evidence["browser_archive"]["size"]
        },
        "fileCount": len(paths),
        "uncompressedBytes": sum(item["size"] for item in paths.values()),
        "files": dict(sorted(paths.items()))
    })
    versions_file = TOOL / "automation/versions.json"
    versions = obj(versions_file)
    versions["checkedAt"] = "2026-11-03"
    versions["playwrightMcp"] = evidence["playwright"]["mcp"]
    versions["playwright"] = evidence["playwright"]["playwright"]
    versions["browser"].update({
        "version": version, "revision": revision,
        "executable": f"browsers/chromium-{revision}/chrome-win64/chrome.exe",
        "downloadUrl": f"https://cdn.playwright.dev/builds/cft/{version}/win64/chrome-win64.zip",
        "payloadManifest": "browser-manifest.json", "payloadBundled": True})
    write_json(versions_file, versions)



def official_optional_url(value: str) -> bool:
    """Accept only canonical PyPI-hosted HTTPS archives."""
    if not isinstance(value, str):
        return False
    try:
        url = urllib.parse.urlsplit(value)
        return (url.scheme == "https" and url.hostname == "files.pythonhosted.org" and
                url.username is None and url.password is None and url.port in (None, 443) and
                url.path.startswith("/packages/") and not url.query and not url.fragment)
    except ValueError:
        return False


def optional_release_provenance(release: dict, name: str, version: str,
                                wheelname: str, wheelurl: str,
                                wheeldigest: str) -> tuple[dict | None, str]:
    """A wheel-only release is valid, but its official wheel identity is mandatory."""
    label = name + "==" + version
    info = release.get("info", {})
    require(isinstance(info, dict) and
            str(info.get("name", "")).lower().replace("_", "-") == name and
            str(info.get("version", "")) == version,
            "Official optional package identity mismatch: " + label)
    rows = release.get("urls", [])
    require(isinstance(rows, list) and all(isinstance(x, dict) for x in rows),
            "Invalid official PyPI release file list: " + label)
    wheels = [x for x in rows if x.get("packagetype") == "bdist_wheel" and
              x.get("filename") == wheelname]
    require(len(wheels) == 1 and official_optional_url(wheelurl) and
            wheels[0].get("url") == wheelurl and
            re.fullmatch(r"[a-f0-9]{64}", wheeldigest or "") is not None and
            wheels[0].get("digests", {}).get("sha256") == wheeldigest and
            wheels[0].get("yanked") is not True,
            "Official optional wheel provenance mismatch: " + label)
    sdists = [x for x in rows if x.get("packagetype") == "sdist"]
    require(len(sdists) <= 1, "Ambiguous official optional source distributions: " + label)
    if not sdists:
        return None, "not_published_on_pypi"
    source = sdists[0]
    source_url = source.get("url")
    digest = source.get("digests", {}).get("sha256", "")
    filename = source.get("filename")
    require(official_optional_url(source_url) and
            isinstance(filename, str) and
            urllib.parse.unquote(urllib.parse.urlsplit(source_url).path.rsplit("/", 1)[-1]) == filename and
            filename.endswith((".tar.gz", ".zip")) and
            re.fullmatch(r"[a-f0-9]{64}", digest or "") is not None and
            source.get("yanked") is not True,
            "Official optional source distribution provenance invalid: " + label)
    return {"url": source_url, "sha256": digest}, "published"


def optional_license_origin(name: str, version: str, files: dict,
                            packages: list, resolved: dict) -> str | None:
    """Verify the licensed real code behind PyMuPDF 2.x's metadata-only 4LLM shim."""
    require(bool(files), "Bundled optional wheel has no installed files: " + name)
    if any(Path(f).name in ("LICENSE", "COPYING") for f in files):
        return None
    label = name + "==" + version
    require(name == "pymupdf4llm" and
            re.fullmatch(r"2\.[0-9]+(?:\.[0-9]+)*", version) is not None and
            all("/pymupdf4llm-" in f and ".dist-info/" in f for f in files) and
            any(f.endswith("/METADATA") for f in files),
            "Bundled wheel license file missing: " + label)
    parent = next((p for p in packages if p["name"].lower() == "pymupdf"), None)
    require(parent is not None and parent["version"] == version and
            resolved.get("pymupdf", {}).get("version") == version and
            resolved.get("pymupdf-layout", {}).get("version") == version and
            any("/pymupdf4llm/" in p for p in parent["files"]) and
            any(Path(p).name in ("LICENSE", "COPYING") for p in parent["files"]),
            "PyMuPDF 4LLM metadata-only wheel lacks matching licensed core/layout: " + label)
    return "PyMuPDF"


def smoke_staged_python(runtime: Path, pdf_policy: dict) -> None:
    """Fail fast on real Windows package imports and PDF-to-Markdown BEFORE Chromium."""
    require(runtime.name == "python-runtime" and runtime.is_dir() and
            (runtime / "python.exe").is_file(),
            "Missing isolated staged CPython native runtime for smoke")
    mode = pdf_policy.get("mode")
    require(mode in ("latest-compatible-legacy-pdf", "latest-with-layout"),
            "Unapproved staged Python PDF mode")
    python = runtime / "python.exe"
    run(python, "-E", "-s", "-B", "-m", "pip", "check")
    # This is a real CPython 3.15 interpreter and bundled native wheel smoke,
    # not an AST-only check. Synthetic PDF input never touches user files.
    code = (
        "import sys,importlib.metadata as md,pandas,numpy,paramiko,"
        "cryptography,pymupdf,pymupdf4llm\n"
        "assert sys.version_info[:3] == (3,15,2)\n"
        "p=md.version('pymupdf'); q=md.version('pymupdf4llm')\n"
        "legacy=(p=='1.28.2' and q=='0.3.4')\n"
        "modern=(p==q and p.startswith('2.') and md.version('pymupdf-layout')==p) "
        "if not legacy else False\n"
        "assert (legacy if "
        + ("True" if mode == "latest-compatible-legacy-pdf" else "False")
        + " else modern), 'Selected PDF distribution closure differs'\n"
        "assert callable(pymupdf4llm.to_markdown)\n"
        "doc=pymupdf.open(); page=doc.new_page()\n"
        "page.insert_text((72,72),'Codex Portable staged PDF smoke')\n"
        "assert 'Codex Portable staged PDF smoke' in pymupdf4llm.to_markdown(doc)\n"
        "doc.close()\n"
        "print('STAGED_PYTHON315_NATIVE_AND_PDF=PASS',p,q)\n"
    )
    run(python, "-E", "-s", "-B", "-c", code)


def python_manifests(temp: Path, resolved: dict, evidence: dict,
                     *, staged_site: Path) -> None:
    """Audit staged installed wheel bytes BEFORE overwriting the trusted runtime.

    Record final tool/python paths, but hash the freshly pip-installed CPython
    3.15 files under the isolated Windows candidate instead of the old 3.14
    checkout. Optional provenance/license failures now stop before Chromium.
    """
    require(staged_site == temp / "python-runtime/Lib/site-packages" and
            staged_site.is_dir(), "Optional manifests require the staged CPython site")
    optional_file = TOOL / "optional-python-manifest.json"
    old = obj(optional_file)
    packages = []
    final_site = TOOL / "python/Lib/site-packages"
    for record in old["packages"]:
        label = record["name"]
        name = label.lower().replace("_", "-")
        require(name in resolved, "Optional bundled package missing: " + label)
        version = resolved[name]["version"]
        meta = temp / ("pypi-" + name + ".json")
        download("https://pypi.org/pypi/" + urllib.parse.quote(name) +
                 "/" + urllib.parse.quote(version) + "/json", meta, limit=4*1024*1024)
        release = obj(meta)
        source_distribution, source_status = optional_release_provenance(
            release, name, version, resolved[name]["wheel"],
            evidence["wheels"][name]["url"], resolved[name]["sha256"])
        wheel = temp / "wheels" / resolved[name]["wheel"]
        files = {}
        with zipfile.ZipFile(wheel) as archive:
            for item in archive.infolist():
                if item.is_dir():
                    continue
                safe_path(item.filename)
                staged = staged_site.joinpath(*item.filename.split("/"))
                if staged.is_file():
                    final = final_site.joinpath(*item.filename.split("/"))
                    files[final.relative_to(ROOT).as_posix()] = sha(staged)
        license_origin = optional_license_origin(name, version, files, packages, resolved)
        if name == "pymupdf":
            require(any(p.endswith((".pyd", ".dll")) for p in files),
                    "Native PyMuPDF wheel missing")
        packages.append({
            "name": label, "version": version, "wheel": resolved[name]["wheel"],
            "source": evidence["wheels"][name]["url"],
            "sha256": resolved[name]["sha256"],
            "source_distribution": source_distribution,
            "source_distribution_status": source_status,
            "license_provided_by": license_origin,
            "files": dict(sorted(files.items()))})
    write_json(optional_file, {
        "target": "Windows x64 CPython 3.15.2",
        "purpose": "Office, PDF and document helpers bundled as official hash-pinned wheels",
        "packages": packages,
        "file_hash_policy": {"algorithm": "sha256",
                             "scope": "Every named installed optional-wheel file"}})
    build_keys = ("pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "pefile",
                  "pywin32-ctypes", "setuptools")
    require(all(k in resolved for k in build_keys), "PyInstaller closure incomplete")
    write_json(TOOL / "python-build-manifest.json", {
        "schema": 2, "target": "Windows x64 CPython 3.15.2",
        "note": ("Fresh official SHA256-pinned PyPI wheels, not historical Git objects. "
                 "PyInstaller is invoked via package-local python -m PyInstaller."),
        "packages": {name: resolved[name]["version"] for name in build_keys},
        "wheel_sha256": {name: resolved[name]["sha256"] for name in build_keys},
        "objects": []})


def update_version_inventory(plan: dict, evidence: dict) -> None:
    file = TOOL / "installed-tools.json"
    state = obj(file)
    require(state["schema"] == 1 and state["platform"] == "win32-x64",
            "Untrusted installed-tools inventory")
    updated = {
        "python": "3.15.2",
        "pip": evidence["python_packages"]["pip"]["version"],
        "paramiko": evidence["python_packages"]["paramiko"]["version"],
        "node": target(plan, "node")["latestStable"],
        "npm": target(plan, "npm")["latestStable"],
        "corepack": target(plan, "corepack")["latestStable"],
        "playwright-mcp": evidence["playwright"]["mcp"],
        "chromium": evidence["playwright"]["chromiumVersion"],
        "adb": target(plan, "adb")["latestStable"],
        "7zip": target(plan, "7zip")["latestStable"],
        "ripgrep": target(plan, "ripgrep")["latestStable"],
        "fd": target(plan, "fd")["latestStable"],
        "jq": target(plan, "jq")["latestStable"]
    }
    require(set(updated) == set(state["tools"]) - {"git"},
            "Tool inventory changed unexpectedly")
    for key, version in updated.items():
        require(re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", version) is not None,
                "Invalid newly installed version")
        state["tools"][key].update(version=version, status="bundled")
    state["lastSuccessfulToolUpdate"] = "2026-11-03"
    write_json(file, state)
    doc_file = TOOL / "工具更新说明.md"
    doc = doc_file.read_text(encoding="utf-8")
    begin, end = "<!-- TOOL_VERSIONS_BEGIN -->", "<!-- TOOL_VERSIONS_END -->"
    require(doc.count(begin) == 1 and doc.count(end) == 1,
            "Tool documentation version section must be unique")
    lines = [begin, "| 工具 | 随包版本 | 状态 | 路径 |",
             "| --- | --- | --- | --- |"]
    for name, row in state["tools"].items():
        lines.append("| " + name + " | " +
                     (row["version"] or "待 Windows 原生核对") + " | " +
                     row["status"] + " | " + chr(96) + row["path"] + chr(96) + " |")
    lines.append(end)
    block = "\n".join(lines)
    doc = re.sub(re.escape(begin) + ".*?" + re.escape(end), lambda _: block, doc,
                 count=1, flags=re.S)
    current = (
        "**全目录最新稳定版候选（2026-11-03 Windows 验证后方可合入）：** "
        "Python 3.15.2（嵌入式 Windows x64）、最新兼容版官方 PyPI wheels（含 pip、SSH、"
        "PyInstaller）、npm 12.2.1、Corepack 0.36.0、Playwright MCP 0.0.84 与其官方"
        "锁定 Playwright 版本/唯一 Chromium、7-Zip 26.05 已重建并逐项核查；"
        "Node、ADB、rg、fd、jq 保留已有最新稳定版。只有完整 Windows 验证及可信差异"
        "核对成功、候选 PR 合并后，这些版本才代表 main 已安装事实。"
        "当前旧正式 Release ZIP 不会自动更新。\n\n")
    marker = "## 实际安装版本台账（随更新同步）"
    require(doc.count(marker) == 1, "Cannot locate tool inventory header")
    doc = doc.replace(marker, current + marker)
    doc_file.write_text(doc, encoding="utf-8", newline="\n")


def prepare(plan: dict) -> None:
    require(os.name == "nt" and sys.maxsize > 2**32,
            "Full stable preparation requires Windows x64")
    require(Path(sys.executable).resolve() != (TOOL / "python/python.exe").resolve(),
            "The host-owned Python must drive replacement, not loaded bundled CPython")
    require((ROOT / "codex.exe").is_file() and
            (ROOT / "env.ps1").is_file(), "Not the complete Codex portable source")
    state = obj(TOOL / "installed-tools.json")["tools"]
    for name in ("node", "adb", "ripgrep", "fd", "jq", "paramiko"):
        require(state[name]["version"] == target(plan, name)["latestStable"],
                "The retained component is not yet latest-stable: " + name)
    scratch = ROOT / "tmp"
    require(not scratch.is_symlink(), "Refuse linked update scratch")
    scratch.mkdir(exist_ok=True)
    evidence: dict = {
        "schema": 1,
        "platform": "win32-x64",
        "source": "trusted official HTTPS release and package archives",
        "candidatePolicy": "latest stable across supported major versions",
        "plan_sha256": sha(PLAN)
    }
    with tempfile.TemporaryDirectory(prefix="full-stable-", dir=scratch) as name:
        temp = Path(name)
        # PyMuPDF 2.x requires ONNX Runtime: check CPython 3.15 official wheel
        # compatibility before downloading npm, browsers or Python archives.
        preflight_python315_onnxruntime(temp, evidence)
        if evidence["pdf_compatibility"]["mode"] == "latest-compatible-legacy-pdf":
            approved = plan.get("pythonPdfCompatibilityException", {})
            require(isinstance(approved, dict) and
                    approved.get("pymupdf") == evidence["pdf_compatibility"]["pymupdf"] and
                    approved.get("pymupdf4llm") == evidence["pdf_compatibility"]["pymupdf4llm"] and
                    approved.get("layout", "").startswith("not installed"),
                    "Unreviewed CPython 3.15 PDF legacy compatibility exception")
        # Detect npm/Playwright configuration and lock errors before redoing
        # three minutes of already native-verified CPython 3.15 wheel work.
        # Defer the large Chromium ZIP until all smaller candidates pass.
        print("FULL_STABLE_PHASE_BEGIN=node_npm_corepack", flush=True)
        stage_npm(plan, temp, evidence)
        print("FULL_STABLE_PHASE_END=node_npm_corepack;status=PASS", flush=True)
        print("FULL_STABLE_PHASE_BEGIN=playwright_mcp", flush=True)
        version, revision = stage_playwright(plan, temp, evidence)
        print("FULL_STABLE_PHASE_END=playwright_mcp;status=PASS", flush=True)
        print("FULL_STABLE_PHASE_BEGIN=python315_dependencies", flush=True)
        staged_python, resolved = stage_python(plan, temp, evidence)
        print("FULL_STABLE_PHASE_END=python315_dependencies;status=PASS", flush=True)
        print("FULL_STABLE_PHASE_BEGIN=optional_python_manifests", flush=True)
        python_manifests(temp, resolved, evidence,
                         staged_site=staged_python / "Lib/site-packages")
        print("FULL_STABLE_PHASE_END=optional_python_manifests;status=PASS", flush=True)
        print("FULL_STABLE_PHASE_BEGIN=staged_python_smoke", flush=True)
        smoke_staged_python(staged_python, evidence["pdf_compatibility"])
        print("FULL_STABLE_PHASE_END=staged_python_smoke;status=PASS", flush=True)
        print("FULL_STABLE_PHASE_BEGIN=7zip", flush=True)
        stage_7zip(plan, temp, evidence)
        print("FULL_STABLE_PHASE_END=7zip;status=PASS", flush=True)
        print("FULL_STABLE_PHASE_BEGIN=chromium_payload", flush=True)
        stage_browser(temp, version, revision, evidence)
        print("FULL_STABLE_PHASE_END=chromium_payload;status=PASS", flush=True)
        replace_tree(staged_python, TOOL / "python", temp)
        # Never load DLLs for the replaced Python from the trusted orchestrator.
        new_python = TOOL / "python/python.exe"
        run(new_python, "-E", "-s", "-B", "-m", "pip", "--version")
        run(new_python, "-E", "-s", "-B", "-m", "PyInstaller", "--version")
        run(new_python, "-E", "-s", "-B", TOOL / "refresh-python-cli-shims.py")
    update_version_inventory(plan, evidence)
    write_json(TOOL / "full-stable-evidence.json", evidence)
    print("FULL_STABLE_CANDIDATE_STAGED=PASS")
    print("FULL_STABLE_PYTHON=3.15.2")
    print("FULL_STABLE_NODE=" + target(plan, "node")["latestStable"])
    print("FULL_STABLE_BROWSER=" + evidence["playwright"]["chromiumVersion"])


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] != "prepare":
        print("Usage: host-python tool/full-stable-prepare.py prepare",
              file=sys.stderr)
        return 2
    plan = obj(PLAN)
    require(plan["schema"] == 1 and plan["platform"] == "win32-x64" and
            plan["state"] == "PREPARATION_ONLY_NOT_INSTALLED" and
            plan["policy"]["publish"].startswith("do not edit installed-tools.json"),
            "Unreviewed full upgrade plan")
    prepare(plan)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, subprocess.SubprocessError,
            zipfile.BadZipFile, tarfile.TarError, urllib.error.URLError) as error:
        print("FULL_STABLE_PREPARE_FAILED: " + str(error), file=sys.stderr)
        raise SystemExit(2)
