#!/usr/bin/env python3
"""Stage full Win11 x64 stable tool updates in a read-only Windows Actions job.

This script does not publish, push, create a release or edit the user's machine.
Execute with a trusted runner Python, NOT tool/python/python.exe: Windows cannot
replace its own loaded DLLs. All downloads are confined to package tmp/.
"""
from __future__ import annotations

import base64
from email.parser import BytesParser
import hashlib
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
PLAN = TOOL / "full-stable-upgrade-plan.json"
MAX_BYTES = 1100 * 1024 * 1024
MAX_FILES = 25000
WINDOWS_BAD = re.compile(r'[<>:"\\|?*\x00-\x1f]')
ALLOWED_HOSTS = {"www.python.org", "files.pythonhosted.org", "registry.npmjs.org",
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


def stage_python(plan: dict, temp: Path, evidence: dict) -> tuple[Path, dict]:
    row, pip = target(plan, "python"), target(plan, "pip")
    require(row["latestStable"] == "3.15.2" and pip["latestStable"] == "26.2.2",
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
    pipwheel = temp / "pip.whl"
    evidence["pip_wheel"] = download(pip["artifact"]["url"], pipwheel,
                                     expected=pip["artifact"]["sha256"], limit=30*1024*1024)
    unzip_checked(pipwheel, stage / "Lib/site-packages", max_total=40*1024*1024)
    python = stage / "python.exe"
    run(python, "-E", "-s", "-B", "-m", "pip", "--version")
    base_names = pins(TOOL / "python-packages.in.txt")
    ssh_names = pins(TOOL / "python-ssh-packages.in.txt")
    require(set(x.lower().replace("_", "-") for x in ssh_names) == SSH,
            "Unexpected SSH closure")
    requested = sorted(set(base_names + ssh_names), key=str.casefold)
    (temp / "requirements.in").write_text("\n".join(requested) + "\n", encoding="utf-8")
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
        resolved[name] = {"version": version, "sha256": digest, "wheel": wheelname}
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
        inp += "".join(n + "==" + resolved[n]["version"] + "\n" for n in ordered)
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
    (stage / "Lib/site-packages/codex_portable_ssh.pth").write_text(
        "../../ssh-packages\n", encoding="ascii")
    plain_tree(stage)
    evidence["python_packages"] = resolved
    return stage, resolved
