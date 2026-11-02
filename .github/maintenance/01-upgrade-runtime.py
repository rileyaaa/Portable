#!/usr/bin/env python3
"""01: manually upgrade the pinned Windows x64 Codex runtime, fail closed.

No credentials are read from the portable package. This script neither pushes
commits nor creates releases. The manually dispatched GitHub Actions workflow
is responsible for validating the index and pushing a reviewed, bounded diff.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import tarfile
import urllib.request

TARGET = "x86_64-pc-windows-msvc"
ARCHIVE = "codex-package-x86_64-pc-windows-msvc.tar.gz"
UPSTREAM = {
    "codex.exe": "bin/codex.exe",
    "codex-code-mode-host.exe": "bin/codex-code-mode-host.exe",
    "codex-command-runner.exe": "codex-resources/codex-command-runner.exe",
    "codex-windows-sandbox-setup.exe": "codex-resources/codex-windows-sandbox-setup.exe",
    "codex-path/rg.exe": "codex-path/rg.exe",
}
RAW_ASSETS = {
    "codex.exe": "codex-x86_64-pc-windows-msvc.exe",
    "codex-code-mode-host.exe": "codex-code-mode-host-x86_64-pc-windows-msvc.exe",
    "codex-command-runner.exe": "codex-command-runner-x86_64-pc-windows-msvc.exe",
    "codex-windows-sandbox-setup.exe": "codex-windows-sandbox-setup-x86_64-pc-windows-msvc.exe",
}
OPTIONAL_EXEC = "bin/codex-exec-server.exe"
# The canonical archive supplies these helpers under codex-resources/.
# Our portable layout RELOCATES their bytes into the root-level names.
# This is not an upstream duplicate-copy digest comparison.
ROOT_RELOCATIONS = {
    "codex-resources/codex-command-runner.exe": "codex-command-runner.exe",
    "codex-resources/codex-windows-sandbox-setup.exe": "codex-windows-sandbox-setup.exe",
}
MODE_LAUNCHERS = (
    "run-codex.ps1", "Version_History/常用模式专用包-run-codex.ps1",
    "Version_History/YOLO mode专用包-run-codex.ps1",
)
MODE_ENVS = (
    "env.ps1", "Version_History/常用模式专用包-env.ps1",
    "Version_History/YOLO mode专用包-env.ps1",
)
ALLOWED = frozenset(
    set(UPSTREAM) | {
        "codex-package.json", "tool/runtime-manifest.json",
        "run-codex.ps1", "env.ps1", "login-json.ps1",
        "README.md", "DEVELOPMENT.md", "tool/工具更新说明.md",
        "tests/test_runtime_preflight.ps1",
        "tool/licenses/codex/LICENSE", "tool/licenses/codex/NOTICE",
    } | set(MODE_LAUNCHERS) | set(MODE_ENVS)
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def plain(path: Path) -> None:
    item = path.lstat()
    require(stat.S_ISREG(item.st_mode) and item.st_nlink == 1 and
            not (getattr(item, "st_file_attributes", 0) & 0x400),
            "Unsafe input path: " + str(path))


VERSION_PATTERN = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-(?:alpha|beta|rc)\.(?:0|[1-9][0-9]*))?"
OFFICIAL_RELEASE_URL = re.compile(
    r"https://github\.com/openai/codex/releases/tag/rust-v(?P<version>" +
    VERSION_PATTERN + r")\Z"
)


def parse_official_release_url(value: str) -> str:
    """Accept only an exact canonical OpenAI Codex release page URL."""
    match = OFFICIAL_RELEASE_URL.fullmatch(value) if isinstance(value, str) else None
    require(match is not None,
            "Enter the exact official GitHub release URL, without query, fragment or trailing slash")
    version = match.group("version")
    version_tuple(version)
    return version


def version_tuple(raw: str) -> tuple[int, int, int, int, int, int]:
    """Order alpha < beta < rc < stable for each numeric Codex version."""
    require(isinstance(raw, str) and re.fullmatch(VERSION_PATTERN, raw) is not None,
            "Use an exact Codex version, e.g. 0.167.0 or 0.167.0-alpha.3")
    base, _, suffix = raw.partition("-")
    major, minor, patch = (int(part) for part in base.split("."))
    if not suffix:
        return major, minor, patch, 1, 0, 0
    stage, sequence = suffix.split(".")
    return major, minor, patch, 0, {"alpha": 0, "beta": 1, "rc": 2}[stage], int(sequence)


def replace_once(data: bytes, old: bytes, new: bytes, label: str) -> bytes:
    require(data.count(old) == 1, "Expected exactly one anchor for " + label)
    return data.replace(old, new, 1)


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)


def read_safe(repo: Path, rel: str) -> bytes:
    require(rel in ALLOWED, "Refusing unapproved repo path " + rel)
    path = repo / rel
    plain(path)
    return path.read_bytes()


def write_safe(repo: Path, updates: dict[str, bytes]) -> None:
    require(set(updates) <= ALLOWED, "Unapproved update scope")
    for rel, data in updates.items():
        require(isinstance(data, bytes), "Invalid update bytes")
        read_safe(repo, rel)
    for rel, data in updates.items():
        (repo / rel).write_bytes(data)


def github_request(url: str) -> bytes:
    require(url.startswith(("https://api.github.com/repos/openai/codex/releases/tags/",
                            "https://raw.githubusercontent.com/openai/codex/rust-v")),
            "Unexpected upstream download origin")
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "Codex-Portable-Manual-Upgrader"}
    token = os.environ.get("GH_TOKEN", "")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=50) as response:
        require(response.status == 200, "Upstream download failed")
        content = response.read(1_000_001 if "raw.githubusercontent" in url else 5_000_001)
    require(len(content) < (1_000_001 if "raw.githubusercontent" in url else 5_000_001),
            "Upstream metadata exceeds size limit")
    return content


def official_plan(repo: Path, release_url: str) -> dict:
    target_version = parse_official_release_url(release_url)
    is_prerelease = "-" in target_version
    old = json.loads(read_safe(repo, "tool/runtime-manifest.json"))
    require(old.get("target") == TARGET, "Current runtime target differs")
    previous = old.get("version")
    require(version_tuple(target_version) > version_tuple(previous),
            "01 requires an official release newer than the pinned CLI version")
    tag = "rust-v" + target_version
    obj = json.loads(github_request(
        "https://api.github.com/repos/openai/codex/releases/tags/" + tag))
    require(obj.get("tag_name") == tag and obj.get("draft") is False and
            obj.get("prerelease") is is_prerelease,
            "Official release is unpublished or its stable/prerelease status disagrees with the tag")
    assets = {a.get("name"): a for a in obj.get("assets", [])}
    expected = [ARCHIVE] + list(RAW_ASSETS.values())
    results = {}
    for name in expected:
        item = assets.get(name)
        require(item is not None, "Missing upstream asset " + name)
        sha = item.get("digest")
        require(isinstance(sha, str) and bool(re.fullmatch(r"sha256:[0-9a-f]{64}", sha)),
                "Missing official GitHub SHA-256 for " + name)
        url = f"https://github.com/openai/codex/releases/download/{tag}/{name}"
        require(item.get("browser_download_url") == url,
                "Unapproved official release URL for " + name)
        require(isinstance(item.get("size"), int) and item["size"] > 1024,
                "Suspicious asset size for " + name)
        results[name] = {"url": url, "sha256": sha[7:], "size": item["size"]}
    plan = {"version": target_version, "old_version": previous, "tag": tag,
            "release_url": release_url, "prerelease": is_prerelease,
            "archive": results[ARCHIVE],
            "raw": {local: results[name] for local, name in RAW_ASSETS.items()}}
    print("OFFICIAL_RELEASE_APPROVED=" + tag)
    print("OFFICIAL_RELEASE_KIND=" + ("prerelease-dry-run" if is_prerelease else "stable"))
    print("OFFICIAL_ARCHIVE_SHA256=" + results[ARCHIVE]["sha256"])
    return plan


def archive_member(name: str) -> None:
    require(bool(name) and not name.startswith("/") and
            ":" not in name and "\\" not in name,
            "Unsafe upstream archive name")
    require(all(p not in ("", ".", "..") for p in name.rstrip("/").split("/")),
            "Unsafe path segment in upstream archive")


def verify_pe(name: str, data: bytes) -> None:
    require(len(data) >= 65536 and data[:2] == b"MZ",
            "Missing native Windows executable " + name)
    offset = struct.unpack_from("<I", data, 0x3C)[0]
    require(0 <= offset <= len(data) - 6 and
            data[offset:offset + 4] == b"PE\0\0" and
            struct.unpack_from("<H", data, offset + 4)[0] == 0x8664,
            "Unexpected Windows PE architecture for " + name)


def collect(archive: Path, plan: dict) -> tuple[dict[str, bytes], dict, int, str | None]:
    require(archive.is_file(), "Missing official canonical archive")
    plain(archive)
    require(archive.stat().st_size == plan["archive"]["size"],
            "Official archive byte length differs")
    require(file_digest(archive) == plan["archive"]["sha256"],
            "Official archive SHA-256 differs from published GitHub digest")
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        require(len(members) <= 512, "Unexpectedly large upstream archive")
        for member in members:
            archive_member(member.name)
            require(member.isdir() or member.isfile(),
                    "Archive links and special files are forbidden")
        metas = [m for m in members if m.isfile() and
                 m.name.endswith("codex-package.json")]
        require(len(metas) == 1, "Missing unique upstream package metadata")
        prefix = metas[0].name[:-len("codex-package.json")]
        require(prefix == "" or prefix.endswith("/"),
                "Unexpected canonical package directory")
        files: dict[str, bytes] = {}
        cases: set[str] = set()
        voice_count = 0
        allow = set(UPSTREAM.values()) | {"codex-package.json", OPTIONAL_EXEC}
        for member in members:
            require(member.name.startswith(prefix), "Archive escaped package root")
            name = member.name[len(prefix):].rstrip("/")
            if not name:
                require(member.isdir(), "Upstream root is not a directory")
                continue
            archive_member(name)
            if member.isdir():
                continue
            folded = name.casefold()
            require(folded not in cases, "Duplicate case-insensitive archive path")
            cases.add(folded)
            require(0 <= member.size <= 650_000_000, "Unexpected runtime payload size")
            if name.startswith("codex-resources/voice/"):
                voice_count += 1
                continue
            require(name in allow, "New upstream layout requires manual review: " + name)
            stream = tar.extractfile(member)
            require(stream is not None, "Upstream file missing " + name)
            with stream:
                data = stream.read(member.size + 1)
            require(len(data) == member.size, "Truncated member " + name)
            files[name] = data
    required = set(UPSTREAM.values()) | {"codex-package.json"}
    actual = set(files)
    require(actual == required or actual == required | {OPTIONAL_EXEC},
            "Missing or unexpected upstream components in canonical archive")
    original = json.loads(files["codex-package.json"].decode("utf-8"))
    known = {"layoutVersion", "version", "target", "variant", "entrypoint",
             "resourcesDir", "pathDir", "execServer"}
    require(set(original) <= known, "New package fields require compatibility review")
    expected_fields = {
        "layoutVersion": 1, "version": plan["version"], "target": TARGET,
        "variant": "codex", "entrypoint": "bin/codex.exe",
        "resourcesDir": "codex-resources", "pathDir": "codex-path"}
    for name, value in expected_fields.items():
        require(original.get(name) == value,
                "Upstream package field changed: " + name)
    if "execServer" in original:
        require(original["execServer"] == OPTIONAL_EXEC and OPTIONAL_EXEC in files,
                "Unexpected standalone execution-server metadata")
    else:
        require(OPTIONAL_EXEC not in files, "Unexpected execution server without metadata")
    for source_path, root_name in ROOT_RELOCATIONS.items():
        require(UPSTREAM.get(root_name) == source_path and source_path in files,
                "Root-level sandbox helper relocation changed: " + root_name)
    result: dict[str, bytes] = {}
    for local, upstream in UPSTREAM.items():
        data = files[upstream]
        verify_pe(local, data)
        if local in plan["raw"]:
            raw = plan["raw"][local]
            require(len(data) == raw["size"] and digest(data) == raw["sha256"],
                    "Official independent binary hash mismatch: " + local)
        result[local] = data
    server_sha = None
    if OPTIONAL_EXEC in files:
        verify_pe("codex-exec-server.exe", files[OPTIONAL_EXEC])
        server_sha = digest(files[OPTIONAL_EXEC])
    original["entrypoint"] = "codex.exe"
    original.pop("execServer", None)
    result["codex-package.json"] = (json.dumps(
        original, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    return result, original, voice_count, server_sha


def patch_launcher(data: bytes, old: str, target: str,
                   manifest_sha: str, hashes: dict[str, str]) -> bytes:
    old_bytes, new_bytes = old.encode("ascii"), target.encode("ascii")
    require(data.count(old_bytes) >= 3,
            "Launcher assumptions changed; manual compatibility review required")
    data = data.replace(old_bytes, new_bytes)
    for variable, value in (
        ("ExpectedRuntimeManifestSha256", manifest_sha),
        ("ExpectedCodexSha256", hashes["codex.exe"]),
        ("ExpectedCodeModeHostSha256", hashes["codex-code-mode-host.exe"]),
    ):
        pattern = rb'\$' + variable.encode("ascii") + rb' = "[a-fA-F0-9]{64}"'
        found = re.findall(pattern, data)
        require(len(found) == 1, "Missing unique launcher pin " + variable)
        data = data.replace(found[0], (
            "$" + variable + ' = "' + value.upper() + '"').encode("ascii"), 1)
    require(b"return @('--no-daemon') + @($LaunchArgs)" in data,
            "Interactive isolation has been removed")
    return data


def compile_updates(repo: Path, archive: Path, plan: dict) -> dict[str, bytes]:
    result, metadata, voice_count, server_sha = collect(archive, plan)
    old = json.loads(read_safe(repo, "tool/runtime-manifest.json"))
    old_version = plan["old_version"]
    require(old.get("version") == old_version and old.get("target") == TARGET,
            "Runtime baseline changed since official metadata was checked")
    manifest = dict(old)
    manifest.update({
        "version": plan["version"], "release": "https://github.com/openai/codex/releases/tag/" + plan["tag"],
        "archive": plan["archive"]["url"], "archive_sha256": plan["archive"]["sha256"]})
    manifest["files"] = {}
    for local, data in sorted(result.items()):
        row = {"upstream_path": "codex-package.json" if local == "codex-package.json"
               else UPSTREAM[local], "sha256": digest(data)}
        if local == "codex-package.json":
            row["adaptation"] = ("Package-root entrypoint; standalone exec-server executable "
                                 "and execServer metadata intentionally omitted.")
        manifest["files"][local] = row
    excluded = manifest.get("excluded_components")
    require(isinstance(excluded, dict) and
            {"voice", "duplicate_sandbox_resources", "standalone_exec_server"} <= set(excluded),
            "Missing fixed local-only exclusion policy")
    excluded["voice"]["upstream_file_count"] = voice_count
    excluded["duplicate_sandbox_resources"]["upstream_paths"] = sorted(ROOT_RELOCATIONS)
    excluded["standalone_exec_server"]["upstream_path"] = OPTIONAL_EXEC
    excluded["standalone_exec_server"].pop("sha256", None)
    if server_sha:
        excluded["standalone_exec_server"]["sha256"] = server_sha
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    result["tool/runtime-manifest.json"] = manifest_bytes
    hashes = {name: digest(contents) for name, contents in result.items()
              if name in UPSTREAM}
    original_launcher = read_safe(repo, "run-codex.ps1")
    require(all(read_safe(repo, name) == original_launcher for name in MODE_LAUNCHERS),
            "Launcher mode copies diverged before the upgrade")
    updated_launcher = patch_launcher(
        original_launcher, old_version, plan["version"], digest(manifest_bytes), hashes)
    for name in MODE_LAUNCHERS:
        result[name] = updated_launcher
    root_env = read_safe(repo, "env.ps1")
    require(read_safe(repo, MODE_ENVS[1]) == root_env, "Common env copy diverged")
    require(root_env.count(old_version.encode("ascii")) >= 2,
            "Version-sensitive env defaults require review")
    for name in MODE_ENVS:
        current = read_safe(repo, name)
        result[name] = current.replace(old_version.encode("ascii"),
                                       plan["version"].encode("ascii"))
    login = read_safe(repo, "login-json.ps1")
    old_hash = old["files"]["codex.exe"]["sha256"].encode("ascii")
    old_row = b"'" + old_hash + b"' = '" + old_version.encode("ascii") + b"'"
    new_row = (b"'" + hashes["codex.exe"].encode("ascii") + b"' = '" +
               plan["version"].encode("ascii") + b"'")
    result["login-json.ps1"] = replace_once(
        login, old_row, new_row + b"\r\n        " + old_row, "login version mapping")
    preflight = read_safe(repo, "tests/test_runtime_preflight.ps1")
    require(preflight.count(old_version.encode("ascii")) >= 3,
            "Runtime preflight fixture must be refreshed")
    result["tests/test_runtime_preflight.ps1"] = preflight.replace(
        old_version.encode("ascii"), plan["version"].encode("ascii"))
    readme = read_safe(repo, "README.md")
    readme = replace_once(
        readme,
        ("当前主客户端与 Code Mode Host 均为官方 **" + old_version + "**").encode("utf-8"),
        ("当前主客户端与 Code Mode Host 均为官方 **" + plan["version"] + "**").encode("utf-8"),
        "README current official runtime")
    # Keep the current-version sentence repeatable across consecutive upgrades.
    prior_statuses = (
        "已按 " + old_version + " 核对查找顺序",
        "当前为 " + old_version + "；运行组件的查找顺序须经 02 兼容检查确认",
    )
    matches = [x for x in prior_statuses if readme.count(x.encode("utf-8")) == 1]
    require(len(matches) == 1, "README runtime lookup status requires manual review")
    readme = replace_once(
        readme, matches[0].encode("utf-8"),
        ("当前为 " + plan["version"] + "；运行组件的查找顺序须经 02 兼容检查确认").encode("utf-8"),
        "README runtime lookup status")
    result["README.md"] = readme
    tool = read_safe(repo, "tool/工具更新说明.md")
    tool = replace_once(tool,
        ("已配套安装 " + old_version + " Windows x64").encode("utf-8"),
        ("已配套安装 " + plan["version"] + " Windows x64").encode("utf-8"),
        "tool status")
    tool = replace_once(tool,
        ("[固定 release](https://github.com/openai/codex/releases/tag/rust-v" +
         old_version + ")").encode("utf-8"),
        ("[固定 release](https://github.com/openai/codex/releases/tag/rust-v" +
         plan["version"] + ")").encode("utf-8"), "tool fixed release link")
    tool = replace_once(tool,
        ("取自官方 " + chr(96) + "rust-v" + old_version + chr(96) + " 标签的同名文件").encode("utf-8"),
        ("取自官方 " + chr(96) + "rust-v" + plan["version"] + chr(96) + " 标签的同名文件").encode("utf-8"),
        "tool license provenance")
    example_pattern = (rb"python -B tool/package-release\.py --version v" +
                       VERSION_PATTERN.encode("ascii") + rb"-portable\.\d+")
    old_example = re.search(example_pattern, tool)
    require(old_example is not None, "Missing unique package invocation")
    require(len(re.findall(example_pattern, tool)) == 1,
            "Ambiguous package version example")
    tool = tool.replace(old_example.group(), (
        "python -B tool/package-release.py --version v" + plan["version"] + "-portable.1").encode(), 1)
    result["tool/工具更新说明.md"] = tool
    development = read_safe(repo, "DEVELOPMENT.md")
    log = (
        "## " + __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%d") +
        "：Codex " + plan["version"] + " 官方运行时升级候选（01 自动更新）\n\n"
        "由手动执行的 01 更新工作流从官方 " + plan["tag"] + " 下载固定 Windows x64 工件，"
        "核对官方发布摘要与独立程序摘要，替换本地文字/Agent 所需主程序、Host、"
        "搜索和沙箱助手，并同步版本固定值、登录映射、运行清单、相关配置与模式副本。"
        "语音及独立 Exec Server 继续不打包；官方原始程序字节不修改。\n\n"
        "**状态：候选源码更新，尚不能视为正式版或已确认兼容。** 必须另外执行 02 "
        "变量与兼容性审查，处理新版 schema、请求协议与真实功能不兼容项；"
        "通过后再手动执行 03 完整 Windows 测试、10 轮回归、附件回读及发布。"
        "实际账号、联网 Agent 和用户终端显示须另行实测。\n\n"
    ).encode("utf-8")
    # Git autocrlf on Windows may convert this tracked Markdown to CRLF.
    # Preserve the checkout's newline convention when inserting the audit log.
    newline = b"\r\n" if b"\r\n" in development else b"\n"
    require(development.count(b"\n") == development.count(newline),
            "Mixed DEVELOPMENT.md line endings require manual review")
    marker = b"# " + "开发与维护记录".encode("utf-8") + newline * 2
    result["DEVELOPMENT.md"] = replace_once(
        development, marker, marker + log.replace(b"\n", newline),
        "add upgrade candidate development record")
    # Always restore the exact licenses from the same upstream source tag.
    for name in ("LICENSE", "NOTICE"):
        url = ("https://raw.githubusercontent.com/openai/codex/" +
               plan["tag"] + "/" + name)
        downloaded = github_request(url)
        require(len(downloaded) >= (1000 if name == "LICENSE" else 40) and b"\0" not in downloaded,
                "Missing/invalid upstream license text " + name)
        result["tool/licenses/codex/" + name] = downloaded
    require(set(result) <= ALLOWED, "Candidate change set exceeds approved files")
    require(set(UPSTREAM) <= set(result), "Unexpected mandatory runtime omission")
    return result


def check_index(repo: Path) -> None:
    raw = git(repo, "diff", "--cached", "--name-only", "-z")
    names = {p.decode("utf-8") for p in raw.split(b"\0") if p}
    require(names <= ALLOWED, "Unexpected staged changes: " + repr(names - ALLOWED))
    mandatory = {"codex.exe", "codex-code-mode-host.exe",
                 "tool/runtime-manifest.json", "codex-package.json",
                 "run-codex.ps1", "login-json.ps1", "DEVELOPMENT.md"}
    require(mandatory <= names, "Missing required staged runtime updates")
    attrs = git(repo, "check-attr", "-z", "filter", "--", *UPSTREAM.keys()).split(b"\0")
    records = [x.decode("utf-8") for x in attrs if x]
    require(len(records) == len(UPSTREAM) * 3, "Unexpected git attributes output")
    for i in range(0, len(records), 3):
        require(records[i + 1] == "filter" and records[i + 2] == "lfs",
                "Binary must remain managed by Git LFS: " + records[i])
    manifest = json.loads(read_safe(repo, "tool/runtime-manifest.json"))
    require(set(manifest.get("files", {})) == set(UPSTREAM) | {"codex-package.json"},
            "Staged runtime inventory no longer matches the local-only contract")
    for path in UPSTREAM:
        pointer = git(repo, "show", ":" + path)
        match = re.fullmatch(
            rb"version https://git-lfs.github.com/spec/v1\n"
            rb"oid sha256:([0-9a-f]{64})\nsize ([1-9][0-9]*)\n?", pointer)
        require(match is not None, "Staged binary is not a canonical LFS pointer: " + path)
        manifest_hash = manifest["files"][path]["sha256"]
        actual_path = repo / path
        plain(actual_path)
        require(match.group(1).decode("ascii") == manifest_hash and
                file_digest(actual_path) == manifest_hash and
                int(match.group(2)) == actual_path.stat().st_size,
                "Staged LFS oid/size differs from official verified binary: " + path)
    print("STAGED_EXACT_ALLOWLIST=PASS files=" + str(len(names)))
    print("STAGED_LFS_OID_SIZE_AND_MANIFEST_HASHES=PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--metadata", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--check-index", action="store_true")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--version")
    parser.add_argument("--release-url")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    root = args.repo.resolve(strict=True)
    require((root / ".git").exists() and (root / "codex.exe").is_file(),
            "Must use a complete checked-out portable repository")
    if not args.check_index:
        require(not git(root, "status", "--porcelain", "--untracked-files=normal").strip(),
                "Repository has uncommitted changes")
    if args.check_index:
        check_index(root)
    elif args.metadata:
        require(args.release_url and args.plan and not args.version,
                "Metadata requires --release-url and --plan, not a version argument")
        plan = official_plan(root, args.release_url)
        args.plan.parent.mkdir(parents=True, exist_ok=True)
        args.plan.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        print("UPGRADE_PLAN_CREATED=PASS")
    else:
        require(args.plan and args.archive, "Expected --plan and --archive")
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        require(args.version == plan["version"] and not args.release_url,
                "Upgrade version does not match validated plan")
        require(parse_official_release_url(plan["release_url"]) == plan["version"] and
                plan["tag"] == "rust-v" + plan["version"] and
                plan["prerelease"] is ("-" in plan["version"]),
                "Verified official release identity changed in the plan")
        require(version_tuple(plan["version"]) > version_tuple(plan["old_version"]),
                "Not an upgrade")
        require(plan["archive"]["url"] ==
                "https://github.com/openai/codex/releases/download/" +
                plan["tag"] + "/" + ARCHIVE, "Unexpected archive source")
        changed = compile_updates(root, args.archive, plan)
        write_safe(root, changed)
        print("UPGRADE_CANDIDATE=PREPARED version=" + plan["version"])
        print("RUN_02_AND_03_BEFORE_DECLARING_COMPATIBLE_OR_PUBLISHED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
