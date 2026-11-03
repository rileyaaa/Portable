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
    spellings = {x.lower().replace('_', '-'): x for x in base_names + ssh_names}
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
    scripts = stage / "Lib/site-packages/bin"
    scripts.mkdir(exist_ok=True)
    for name in ("pip.exe", "pip3.exe", "pip3.15.exe"):
        candidate = vendor / name
        require(candidate.is_file() and candidate.stat().st_size > 1024,
                "pip 26.2.2 is missing expected Windows launcher " + name)
        shutil.copyfile(candidate, scripts / name)
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
    for native in stage.rglob("*"):
        if native.is_file() and native.suffix.lower() in (".pyd", ".dll", ".exe"):
            require(pe_amd64(native),
                    "Staged Python/native package binary is not Windows x64: " + str(native))
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
    empty = temp / "empty.npmrc"
    if not empty.exists():
        empty.write_text("", encoding="utf-8")
    home = temp / "npm-home"
    home.mkdir(exist_ok=True)
    return {"NPM_CONFIG_CACHE": temp / "npm-cache",
            "NPM_CONFIG_USERCONFIG": empty,
            "NPM_CONFIG_GLOBALCONFIG": empty,
            "NPM_CONFIG_REGISTRY": "https://registry.npmjs.org",
            "NPM_CONFIG_UPDATE_NOTIFIER": "false",
            "NPM_CONFIG_AUDIT": "false",
            "NPM_CONFIG_FUND": "false", "HOME": home, "USERPROFILE": home,
            "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1"}


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


def python_manifests(temp: Path, resolved: dict, evidence: dict) -> None:
    """Rebuild manifests from installed bytes; never keep stale CPython 3.14 hashes."""
    optional_file = TOOL / "optional-python-manifest.json"
    old = obj(optional_file)
    packages = []
    site = TOOL / "python/Lib/site-packages"
    for record in old["packages"]:
        label = record["name"]
        name = label.lower().replace("_", "-")
        require(name in resolved, "Optional bundled package missing: " + label)
        version = resolved[name]["version"]
        meta = temp / ("pypi-" + name + ".json")
        download("https://pypi.org/pypi/" + urllib.parse.quote(name) +
                 "/" + urllib.parse.quote(version) + "/json", meta, limit=4*1024*1024)
        release = obj(meta)
        sdists = [u for u in release.get("urls", [])
                  if u.get("packagetype") == "sdist"]
        require(len(sdists) == 1 and
                sdists[0]["url"].startswith("https://files.pythonhosted.org/") and
                re.fullmatch(r"[a-f0-9]{64}", sdists[0].get("digests", {}).get("sha256", "")),
                "Official optional package source provenance missing")
        wheel = temp / "wheels" / resolved[name]["wheel"]
        files = {}
        with zipfile.ZipFile(wheel) as archive:
            for item in archive.infolist():
                if item.is_dir():
                    continue
                safe_path(item.filename)
                installed = site.joinpath(*item.filename.split("/"))
                if installed.is_file():
                    files[installed.relative_to(ROOT).as_posix()] = sha(installed)
        require(files and any(Path(f).name in ("LICENSE", "COPYING") for f in files),
                "Bundled wheel license file missing: " + label)
        if name == "pymupdf":
            require(any(p.endswith((".pyd", ".dll")) for p in files),
                    "Native PyMuPDF wheel missing")
        packages.append({
            "name": label, "version": version, "wheel": resolved[name]["wheel"],
            "source": evidence["wheels"][name]["url"],
            "sha256": resolved[name]["sha256"],
            "source_distribution": {
                "url": sdists[0]["url"],
                "sha256": sdists[0]["digests"]["sha256"]},
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
        staged_python, resolved = stage_python(plan, temp, evidence)
        stage_npm(plan, temp, evidence)
        stage_7zip(plan, temp, evidence)
        version, revision = stage_playwright(plan, temp, evidence)
        stage_browser(temp, version, revision, evidence)
        replace_tree(staged_python, TOOL / "python", temp)
        # Never load DLLs for the replaced Python from the trusted orchestrator.
        new_python = TOOL / "python/python.exe"
        run(new_python, "-E", "-s", "-B", "-m", "pip", "--version")
        run(new_python, "-E", "-s", "-B", "-m", "PyInstaller", "--version")
        run(new_python, "-E", "-s", "-B", TOOL / "refresh-python-cli-shims.py")
        python_manifests(temp, resolved, evidence)
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
