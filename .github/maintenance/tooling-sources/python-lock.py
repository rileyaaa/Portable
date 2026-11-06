#!/usr/bin/env python3
"""Build and validate a wheel-only pip hash lock without running package code."""
from __future__ import annotations

import argparse
import csv
from email.parser import BytesParser
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib.parse import unquote, urlsplit


NAME = r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"
VERSION = r"[A-Za-z0-9][A-Za-z0-9.!+_-]*"
PIN = re.compile(rf"({NAME})==({VERSION})")
LOCK_PIN = re.compile(rf"({NAME})==({VERSION}) --hash=sha256:([a-f0-9]{{64}})")
INPUT_HEADER = "# requirements-sha256: "
FORMAT_HEADER = "# Codex Portable wheel lock v1"
MAX_INPUT_BYTES = 32 * 1024 * 1024
RUNTIME_REPAIR_SCOPE = (
    "This installer repairs only the fixed default runtime set. "
    "Use controlled maintenance for version upgrades or additional tools; "
    "existing files were left unchanged."
)


def normalized_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def requirements_pins(raw: bytes) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in raw.decode("utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN.fullmatch(line)
        if match is None:
            raise ValueError("Direct dependencies must use plain name==version pins.")
        name, version = match.groups()
        name = normalized_name(name)
        if name in pins:
            raise ValueError("Duplicate direct dependency.")
        pins[name] = version
    if not pins:
        raise ValueError("Direct dependency list is empty.")
    return pins


def _match_direct_pins(direct: dict[str, str], resolved: dict[str, str]) -> None:
    for name, version in direct.items():
        if resolved.get(name) != version:
            raise ValueError("Resolved lock does not match every direct dependency pin.")


def build_lock(report: dict, requirements: bytes) -> str:
    direct = requirements_pins(requirements)
    if not isinstance(report, dict) or report.get("version") != "1":
        raise ValueError("Unsupported pip report format.")
    installs = report.get("install")
    if not isinstance(installs, list) or not 1 <= len(installs) <= 500:
        raise ValueError("Pip report must contain a bounded nonempty install list.")
    resolved: dict[str, str] = {}
    lines: dict[str, str] = {}
    for item in installs:
        if not isinstance(item, dict) or item.get("is_direct") is not False:
            raise ValueError("Direct URLs and unsupported report records are refused.")
        if item.get("is_yanked") is not False:
            raise ValueError("Yanked or unverified distributions are refused.")
        metadata = item.get("metadata")
        download = item.get("download_info")
        if not isinstance(metadata, dict) or not isinstance(download, dict):
            raise ValueError("Missing package metadata or archive information.")
        name, version = metadata.get("name"), metadata.get("version")
        if not isinstance(name, str) or not re.fullmatch(NAME, name):
            raise ValueError("Invalid package name.")
        if not isinstance(version, str) or not re.fullmatch(VERSION, version):
            raise ValueError("Invalid package version.")
        name = normalized_name(name)
        if name in resolved:
            raise ValueError("Duplicate resolved package.")
        source = download.get("url")
        if not isinstance(source, str):
            raise ValueError("Missing archive source.")
        parsed = urlsplit(source)
        if (parsed.scheme != "https" or parsed.hostname != "files.pythonhosted.org"
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or parsed.query or parsed.fragment
                or not unquote(parsed.path).endswith(".whl")):
            raise ValueError("Only official PyPI HTTPS wheel archives are permitted.")
        archive = download.get("archive_info")
        hashes = archive.get("hashes") if isinstance(archive, dict) else None
        digest = hashes.get("sha256") if isinstance(hashes, dict) else None
        if not isinstance(digest, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
            raise ValueError("Wheel report is missing its SHA-256 digest.")
        resolved[name] = version
        lines[name] = f"{name}=={version} --hash=sha256:{digest.lower()}"
    _match_direct_pins(direct, resolved)
    return "\n".join([
        FORMAT_HEADER,
        INPUT_HEADER + hashlib.sha256(requirements).hexdigest(),
        "# Exact selected wheel hashes; install with --require-hashes --only-binary=:all:.",
        *[lines[name] for name in sorted(lines)],
        "",
    ])


def validate_lock(lock: bytes, requirements: bytes) -> None:
    direct = requirements_pins(requirements)
    lines = lock.decode("utf-8-sig").splitlines()
    if not lines or lines[0] != FORMAT_HEADER:
        raise ValueError("Lock predates wheel-only validation; regenerate it deliberately.")
    headers = [line for line in lines if line.startswith(INPUT_HEADER)]
    if headers != [INPUT_HEADER + hashlib.sha256(requirements).hexdigest()]:
        raise ValueError("Dependency input changed; regenerate the lock deliberately.")
    resolved: dict[str, str] = {}
    for line in lines:
        if not line.strip() or line.startswith("#"):
            continue
        match = LOCK_PIN.fullmatch(line)
        if match is None:
            raise ValueError("Lock contains an unsupported pin, option or archive hash.")
        name, version, _ = match.groups()
        name = normalized_name(name)
        if name in resolved:
            raise ValueError("Duplicate package in lock.")
        resolved[name] = version
    if not 1 <= len(resolved) <= 500:
        raise ValueError("Lock package count is invalid.")
    _match_direct_pins(direct, resolved)


def _ordinary(path: Path, *, directory: bool) -> os.stat_result:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("Linked paths are not permitted.")
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("Expected an ordinary directory.")
    elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Expected an ordinary single-link input file.")
    return info


def package_root() -> Path:
    script = Path(os.path.abspath(__file__))
    root = script.parent.parent
    if script.parent.name != "tool":
        raise ValueError("Lock helper must be inside the portable tool directory.")
    for ancestor in (*reversed(root.parents), root):
        _ordinary(ancestor, directory=True)
    checked_path(root, script)
    for name in ("codex.exe", "env.ps1"):
        checked_path(root, root / name, bounded=False)
    return root


def checked_path(
    root: Path, value: str | Path, *, output: bool = False, bounded: bool = True
) -> Path:
    raw = Path(value)
    if ".." in raw.parts:
        raise ValueError("Parent traversal is not permitted.")
    candidate = Path(os.path.abspath(raw))
    try:
        relative = candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("Lock operation must remain inside the portable package.") from error
    if not relative.parts:
        raise ValueError("A file path is required.")
    cursor = root
    for part in relative.parts[:-1]:
        cursor /= part
        _ordinary(cursor, directory=True)
    if output:
        try:
            candidate.lstat()
        except FileNotFoundError:
            return candidate
        raise ValueError("Refusing to overwrite an existing candidate lock.")
    info = _ordinary(candidate, directory=False)
    if bounded and info.st_size > MAX_INPUT_BYTES:
        raise ValueError("Lock input exceeds the bounded size limit.")
    return candidate


def checked_directory(root: Path, path: Path) -> Path:
    # Check the lexical boundary before examining any supplied path component.
    if ".." in path.parts:
        raise ValueError("Parent traversal is not permitted.")
    candidate = Path(os.path.abspath(path))
    try:
        relative = candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("Runtime directory must remain inside the package.") from error
    for ancestor in (*reversed(root.parents), root):
        _ordinary(ancestor, directory=True)
    cursor = root
    for part in relative.parts:
        cursor /= part
        _ordinary(cursor, directory=True)
    return candidate


def validate_runtime(root: Path, requirements: bytes) -> None:
    """Refuse destructive pip --target repairs; never import or remove packages."""
    pins = requirements_pins(requirements)
    site = checked_directory(root, root / "tool/python/Lib/site-packages")
    installed: set[str] = set()
    owned_launchers: set[str] = set()
    for entry in site.iterdir():
        lower = entry.name.lower()
        if lower.endswith((".egg-info", ".egg-link", ".egg")):
            raise ValueError("Legacy/extra distribution metadata found. " + RUNTIME_REPAIR_SCOPE)
        if not lower.endswith(".dist-info"):
            continue
        checked_directory(root, entry)
        metadata_path = checked_path(root, entry / "METADATA")
        metadata = BytesParser().parsebytes(metadata_path.read_bytes(), headersonly=True)
        if len(metadata.get_all("Name", [])) != 1 or len(metadata.get_all("Version", [])) != 1:
            raise ValueError("Ambiguous installed package metadata. " + RUNTIME_REPAIR_SCOPE)
        name, version = metadata["Name"], metadata["Version"]
        if not re.fullmatch(NAME, name) or not re.fullmatch(VERSION, version):
            raise ValueError("Invalid installed package identity. " + RUNTIME_REPAIR_SCOPE)
        name = normalized_name(name)
        if name in installed:
            raise ValueError("Duplicate installed distribution metadata. " + RUNTIME_REPAIR_SCOPE)
        installed.add(name)
        if name not in pins:
            raise ValueError("An additional distribution is installed. " + RUNTIME_REPAIR_SCOPE)
        if version != pins[name]:
            raise ValueError("Installed version differs from the fixed input. " + RUNTIME_REPAIR_SCOPE)
        record = checked_path(root, entry / "RECORD").read_bytes().decode("utf-8-sig")
        for row in csv.reader(io.StringIO(record, newline="")):
            if len(row) != 3:
                raise ValueError("Invalid installed RECORD. " + RUNTIME_REPAIR_SCOPE)
            # uv records bin/name; pip's home-scheme staging records ../../bin/name.
            # Recognize only those textual launcher names. Never resolve, read or
            # delete a filesystem path supplied by RECORD.
            match = re.fullmatch(r"(?:bin/|\.\./\.\./bin/)([A-Za-z0-9][A-Za-z0-9_.-]*)", row[0])
            if match:
                owned_launchers.add(match[1].lower())
    bin_dir = site / "bin"
    try:
        bin_dir.lstat()
    except FileNotFoundError:
        return  # Missing default files may be restored by the repair installation.
    checked_directory(root, bin_dir)
    for launcher in bin_dir.iterdir():
        checked_path(root, launcher, bounded=False)
        if launcher.name.lower() not in owned_launchers:
            raise ValueError("Unowned Python bin entry would be replaced. " + RUNTIME_REPAIR_SCOPE)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--report", required=True)
    build.add_argument("--requirements", required=True)
    build.add_argument("--output", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--lock", required=True)
    validate.add_argument("--requirements", required=True)
    validate_input = commands.add_parser("validate-input")
    validate_input.add_argument("--requirements", required=True)
    validate_installed = commands.add_parser("validate-runtime")
    validate_installed.add_argument("--requirements", required=True)
    args = parser.parse_args(argv)
    root = package_root()
    requirements = checked_path(root, args.requirements)
    if args.command == "validate-input":
        requirements_pins(requirements.read_bytes())
        print("Verified plain pinned direct dependency input.")
    elif args.command == "validate-runtime":
        validate_runtime(root, requirements.read_bytes())
        print("Verified fixed runtime repair scope and launcher ownership.")
    elif args.command == "build":
        report = checked_path(root, args.report)
        output = checked_path(root, args.output, output=True)
        body = build_lock(json.loads(report.read_bytes()), requirements.read_bytes())
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(body)
        print("Created verified wheel hash lock.")
    else:
        lock = checked_path(root, args.lock)
        validate_lock(lock.read_bytes(), requirements.read_bytes())
        print("Verified wheel hash lock and direct dependency input.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, csv.Error) as error:
        print(f"python-lock: {error}", file=sys.stderr)
        raise SystemExit(2)
