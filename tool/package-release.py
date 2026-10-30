#!/usr/bin/env python3
"""Build and verify a customer release ZIP from a clean, hydrated checkout."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import subprocess
import tempfile
import time
import zipfile


CHUNK = 1024 * 1024
LFS_HEADER = b"version https://git-lfs.github.com/spec/v1"
RUNTIME_FILES = {
    "codex.exe", "codex-code-mode-host.exe", "codex-command-runner.exe",
    "codex-windows-sandbox-setup.exe", "codex-package.json", "codex-path/rg.exe",
}
STATE_ROOTS = {
    "tmp", "cache", "logs", "sqlite", "appdata", "localappdata", "programdata",
    "home-runtime", "work", "login_json", ".codex", ".agents",
}
PLACEHOLDERS = {".keep", ".gitkeep"}
HOME_SOURCE_FILES = {
    "home/.agents/plugins/marketplace.json",
    "home/rules/default.rules",
}
# Match only audited first-party development paths. In particular, do not
# remove files named "test" or "docs" from pinned third-party runtime packages:
# those can be imported by tools or covered by their integrity manifests.
DEVELOPMENT_DIRECTORIES = {
    "tests/": "Project regression tests; run from the source checkout.",
    ".github/": "Repository automation and CI configuration.",
    "Version_History/AI account format conversion/test/":
        "Converter development audits, regression tests and synthetic fixtures.",
}
DEVELOPMENT_FILES = {
    ".gitignore": "Git checkout configuration.",
    ".gitattributes": "Git checkout and LFS configuration.",
    "tool/package-release.py": "Release builder; run from the source checkout.",
}


def ordinary(path: Path, directory: bool = False) -> os.stat_result:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("Linked/reparse path refused: " + str(path))
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("Expected an ordinary directory: " + str(path))
    elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Expected a single-link ordinary file: " + str(path))
    return info


def check_root(root: Path) -> None:
    for ancestor in (*reversed(root.parents), root):
        ordinary(ancestor, directory=True)


def safe_name(name: str) -> None:
    parts = name.split("/")
    if not name or "\\" in name or PurePosixPath(name).is_absolute():
        raise ValueError("Invalid archive path.")
    for part in parts:
        if (not part or part in (".", "..") or part.lower() == ".git"
                or part.endswith((" ", ".")) or re.search(r'[<>:"|?*\x00-\x1f]', part)
                or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part)):
            raise ValueError("Path is not portable to Windows: " + name)
    lowered = [part.lower() for part in parts]
    if lowered[0] in {"env.local.ps1", ".codex-portable.instance.lock", ".codex-browser.instance.lock"}:
        raise ValueError("Private runtime state cannot be released: " + name)
    if lowered[0] in STATE_ROOTS and lowered[-1] not in PLACEHOLDERS:
        raise ValueError("Private runtime state cannot be released: " + name)
    if lowered[0] == "home" and not (
        len(parts) > 2 and lowered[1] in {"skills", "plugins"}
        or len(parts) == 2 and lowered[1] in PLACEHOLDERS
        or name in HOME_SOURCE_FILES
    ):
        raise ValueError("Private home state cannot be released: " + name)


def package_file(root: Path, name: str) -> Path:
    safe_name(name)  # Reject sensitive names before any filesystem access.
    cursor = root
    for part in name.split("/")[:-1]:
        cursor /= part
        ordinary(cursor, directory=True)
    path = root / name
    info = ordinary(path)
    if name.split("/")[0].lower() in STATE_ROOTS and info.st_size:
        raise ValueError("Runtime directory placeholders must be empty: " + name)
    return path


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)


def unique_windows_names(names: list[str]) -> None:
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError("Case-colliding archive paths are not supported on Windows.")


def clean_checkout(root: Path) -> tuple[str, int, list[str]]:
    check_root(root)
    ordinary(root / ".git", directory=True)
    commit = git(root, "rev-parse", "HEAD").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
        raise ValueError("Cannot determine the source commit.")
    names = []
    for record in git(root, "ls-tree", "-rz", "--full-tree", "HEAD").split(b"\0"):
        if not record:
            continue
        header, raw_name = record.split(b"\t", 1)
        mode, kind, _ = header.split()
        name = raw_name.decode("utf-8")
        safe_name(name)
        if kind != b"blob" or mode not in (b"100644", b"100755"):
            raise ValueError("Links and submodules cannot be released: " + name)
        names.append(name)
    unique_windows_names(names)
    # Validate index names before asking Git to inspect working files. Never scan
    # untracked files, including local credentials and user work directories.
    for record in git(root, "ls-files", "-v", "-z").split(b"\0"):
        if record:
            flag, name = record[:1], record[2:].decode("utf-8")
            safe_name(name)
            if flag != b"H":
                raise ValueError("Release requires a normal, fully checked-out Git index.")
    for name in names:
        with package_file(root, name).open("rb") as stream:
            if stream.read(128).startswith(LFS_HEADER):
                raise ValueError("Unhydrated Git LFS pointer: " + name)
    if git(root, "status", "--porcelain=v1", "--untracked-files=no"):
        raise ValueError("Commit tracked changes before building a release.")
    timestamp = int(git(root, "show", "-s", "--format=%ct", "HEAD"))
    return commit, timestamp, sorted(names)


def customer_files(names: list[str]) -> tuple[list[str], dict[str, str]]:
    """Select customer files without weakening validation of the source tree."""
    unique_windows_names(names)
    included = []
    excluded = {}
    for name in sorted(names):
        safe_name(name)
        reason = DEVELOPMENT_FILES.get(name)
        if reason is None:
            reason = next((reason for prefix, reason in DEVELOPMENT_DIRECTORIES.items()
                           if name.startswith(prefix)), None)
        if reason is None:
            included.append(name)
        else:
            excluded[name] = reason
    return included, excluded


def digest_stream(stream) -> str:
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(CHUNK), b""):
        digest.update(block)
    return digest.hexdigest()


def runtime_identity(root: Path, names: list[str]) -> dict:
    manifest_path = package_file(root, "tool/runtime-manifest.json")
    if manifest_path.stat().st_size > CHUNK:
        raise ValueError("Runtime manifest is unexpectedly large.")
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    if (manifest.get("target") != "x86_64-pc-windows-msvc"
            or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}", manifest.get("version", ""))
            or set(manifest.get("files", {})) != RUNTIME_FILES):
        raise ValueError("Unexpected portable runtime layout or identity.")
    launcher = package_file(root, "run-codex.ps1").read_text(encoding="utf-8-sig")
    pinned = re.search(r'\$ExpectedRuntimeManifestSha256\s*=\s*"([0-9a-fA-F]{64})"', launcher)
    if not pinned or pinned[1].lower() != hashlib.sha256(raw).hexdigest():
        raise ValueError("Launcher and runtime manifest identities differ.")
    for name, record in manifest["files"].items():
        if name not in names:
            raise ValueError("Runtime file is not committed: " + name)
        path = package_file(root, name)
        with path.open("rb") as stream:
            if digest_stream(stream) != record.get("sha256"):
                raise ValueError("Runtime file is missing, altered or an LFS pointer: " + name)
            if name.endswith((".exe", ".dll")):
                stream.seek(0)
                if stream.read(2) != b"MZ":
                    raise ValueError("Runtime file is not a native Windows binary: " + name)
                stream.seek(0x3C)
                offset = struct.unpack("<I", stream.read(4))[0]
                stream.seek(offset)
                if stream.read(6) != b"PE\0\0\x64\x86":
                    raise ValueError("Runtime file is not Windows x64: " + name)
    metadata = json.loads(package_file(root, "codex-package.json").read_bytes())
    if any(metadata.get(key) != value for key, value in {
        "version": manifest["version"], "target": manifest["target"],
        "entrypoint": "codex.exe", "resourcesDir": "codex-resources", "pathDir": "codex-path",
    }.items()):
        raise ValueError("Codex package metadata does not match the release layout.")
    if "execServer" in metadata or "codex-exec-server.exe" in names:
        raise ValueError("Standalone exec server is not part of this local-only portable package.")
    ordinary(root / "codex-resources", directory=True)
    return manifest


def browser_identity(root: Path, names: list[str]) -> dict:
    required = {"tool/automation/install-browser.py", "tool/automation/browser-manifest.json",
                "tool/automation/versions.json"}
    if not required.issubset(names):
        raise ValueError("Browser identity and verifier must be committed.")
    versions = json.loads(package_file(root, "tool/automation/versions.json").read_bytes())
    if (versions["browser"].get("payloadBundled") is not True or
            versions["browser"].get("payloadManifest") != "browser-manifest.json"):
        raise ValueError("Customer releases require the pinned browser payload.")
    # Share the installer's strict official-source, inventory and PE checks.
    verifier = package_file(root, "tool/automation/install-browser.py")
    spec = importlib.util.spec_from_file_location("portable_browser_verifier", verifier)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest, _ = module.load_manifest(root)
    for name in manifest["files"]:
        safe_name(name)
    tracked_payload = {name for name in names if name.startswith("tool/automation/browsers/")}
    if tracked_payload != set(manifest["files"]):
        raise ValueError("Committed browser inventory differs from the pinned manifest.")
    module.verify_payload(root, manifest)
    return manifest


def verify_zip(archive: Path, files: dict) -> None:
    ordinary(archive)
    with zipfile.ZipFile(archive) as zipped:
        if zipped.namelist() != ["Codex/" + name for name in files]:
            raise ValueError("Archive member list differs from the release input.")
        for name, expected in files.items():
            info = zipped.getinfo("Codex/" + name)
            if info.file_size != expected["size"]:
                raise ValueError("Archive member size differs: " + name)
            with zipped.open(info) as stream:
                if digest_stream(stream) != expected["sha256"]:
                    raise ValueError("Archive member digest differs: " + name)
            # Reading through EOF also checks zipfile's CRC validation.


def build_release(root: Path, version: str | None = None) -> dict:
    # Validate every tracked input, including excluded development files, before
    # filtering. Exclusion must not hide linked paths, private state or LFS stubs.
    commit, timestamp, source_names = clean_checkout(root)
    names, excluded = customer_files(source_names)
    manifest = runtime_identity(root, names)
    browser = browser_identity(root, names)
    version = version or manifest["version"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", version):
        raise ValueError("Invalid release version/tag.")
    scratch = root / "tmp"
    try:
        ordinary(scratch, directory=True)
    except FileNotFoundError:
        scratch.mkdir()
    output = Path(tempfile.mkdtemp(prefix="release-", dir=scratch))
    try:
        stem = f"Codex-Portable-{version}-windows-x64"
        archive = output / (stem + ".zip")
        files = {}
        stamp = time.gmtime(max(315532800, min(timestamp, 4354819199)))[:6]
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
            for name in names:
                path = package_file(root, name)
                before = path.stat()
                digest = hashlib.sha256()
                info = zipfile.ZipInfo("Codex/" + name, date_time=stamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                with path.open("rb") as source:
                    first = source.read(CHUNK)
                    if first.startswith(LFS_HEADER):
                        raise ValueError("Unhydrated Git LFS pointer: " + name)
                    with zipped.open(info, "w", force_zip64=True) as destination:
                        block = first
                        while block:
                            destination.write(block)
                            digest.update(block)
                            block = source.read(CHUNK)
                after = ordinary(path)
                if (before.st_ino, before.st_size, before.st_mtime_ns) != (
                        after.st_ino, after.st_size, after.st_mtime_ns):
                    raise ValueError("Source file changed while packaging: " + name)
                files[name] = {"size": before.st_size, "sha256": digest.hexdigest()}
        if clean_checkout(root)[0] != commit:
            raise ValueError("Source checkout changed while packaging.")
        verify_zip(archive, files)
        metadata = {
            "format": 1, "source_commit": commit, "release_version": version,
            "package_kind": "customer", "source_file_count": len(source_names),
            "excluded_file_count": len(excluded), "excluded_files": excluded,
            "codex_version": manifest["version"],
            "browser_version": browser["browserVersion"], "browser_revision": browser["revision"],
            "browser_archive_sha256": browser["archive"]["sha256"],
            "target": manifest["target"], "archive": archive.name, "file_count": len(files),
            "uncompressed_bytes": sum(record["size"] for record in files.values()),
            "files": files,
        }
        metadata_path = output / "release-manifest.json"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        hashes = {}
        for path in (archive, metadata_path):
            with path.open("rb") as stream:
                hashes[path.name] = digest_stream(stream)
        checksum = output / "SHA256SUMS"
        checksum.write_text("".join(f"{digest}  {name}\n" for name, digest in hashes.items()), encoding="ascii")
        return {"output_dir": str(output), "archive": str(archive), "manifest": str(metadata_path),
                "checksums": str(checksum), "source_commit": commit, "file_count": len(files),
                "source_file_count": len(source_names), "excluded_file_count": len(excluded),
                "uncompressed_bytes": metadata["uncompressed_bytes"], "archive_bytes": archive.stat().st_size,
                "archive_sha256": hashes[archive.name]}
    except BaseException:
        # This private directory was created above; never clean shared tmp/user data.
        shutil.rmtree(output)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check committed inputs without creating an archive")
    parser.add_argument("--version", help="release tag, for example v0.164.0-portable.1 (specify for official releases)")
    args = parser.parse_args()
    root = Path(os.path.abspath(__file__)).parent.parent
    if args.check:
        commit, _, source_names = clean_checkout(root)
        names, excluded = customer_files(source_names)
        manifest = runtime_identity(root, names)
        browser = browser_identity(root, names)
        print(json.dumps({"source_commit": commit, "codex_version": manifest["version"],
                          "browser_version": browser["browserVersion"],
                          "file_count": len(names), "source_file_count": len(source_names),
                          "excluded_file_count": len(excluded)}))
    else:
        # ASCII JSON remains parseable through Windows legacy-codepage pipes;
        # JSON readers recover the original Unicode path from escaped strings.
        print(json.dumps(build_release(root, args.version), ensure_ascii=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, struct.error, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        raise SystemExit("Release packaging failed: " + str(error))
