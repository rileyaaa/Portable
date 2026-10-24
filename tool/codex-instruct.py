#!/usr/bin/env python3
"""Install a portable Codex model-instructions file persistently.

The launcher owns ``home/config.toml`` and regenerates it on every start, so this
helper never edits that generated file. Instead it writes the instruction file
inside portable ``CODEX_HOME`` and persists the launcher-facing
``CODEX_MODEL_INSTRUCTIONS_FILE`` assignment in package-root ``env.local.ps1``.
"""
from __future__ import annotations

import argparse
import os
import re
import stat
import tempfile
from pathlib import Path

WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL", "CLOCK$", "CONIN$", "CONOUT$",
    *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10)),
}

def _is_reparse(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        return bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
    except OSError:
        # Path-inspection failure is unsafe at a security boundary.
        return True

def _reject_existing_hardlink(path: Path, label: str) -> None:
    if not path.exists():
        return
    try:
        info = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise SystemExit(f"Unable to inspect {label}: {path}: {exc}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise SystemExit(f"Expected a regular file for {label}: {path}")
    if getattr(info, "st_nlink", 1) != 1:
        raise SystemExit(f"Refusing hard-linked {label}: {path}")

def _atomic_write_text(path: Path, text: str, *, encoding: str, root: Path) -> None:
    parent = path.parent.absolute()
    if not lexical_under(parent, root) or not resolved_under(parent, root):
        raise SystemExit(f"Refusing write outside portable package: {path}")
    reject_reparse_chain(parent, root)
    parent.mkdir(parents=True, exist_ok=True)
    reject_reparse_chain(parent, root)
    fd, temp_name = tempfile.mkstemp(prefix=".codex-instruct-", suffix=".tmp", dir=parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        reject_reparse_chain(parent, root)
        os.replace(temp_path, path)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

def package_root() -> Path:
    script = Path(os.path.abspath(__file__))
    raw = script.parents[1]
    # Inspect from the filesystem root down before probing package markers.
    # Resolving first would erase a linked ancestor and silently trust its target.
    for entry in (*reversed(script.parents), script):
        if _is_reparse(entry):
            raise SystemExit(f"Refusing linked instruction-helper entry path: {entry}")
        if entry == script:
            _reject_existing_hardlink(entry, "instruction helper")
        elif not entry.is_dir():
            raise SystemExit(f"Invalid instruction-helper ancestor: {entry}")
    for name in ("codex.exe", "env.ps1"):
        marker = raw / name
        if _is_reparse(marker) or not marker.is_file():
            raise SystemExit(f"Invalid or linked portable package marker: {marker}")
        _reject_existing_hardlink(marker, "package marker")
    return raw

def lexical_under(path: Path, root: Path) -> bool:
    try:
        path.absolute().relative_to(root.absolute())
        return True
    except ValueError:
        return False

def resolved_under(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve())
        return True
    except ValueError:
        return False

def reject_reparse_chain(path: Path, root: Path) -> None:
    """Reject existing symlink/junction components from root through path."""
    root = root.resolve()
    absolute = path.absolute()
    if not lexical_under(absolute, root):
        raise SystemExit(f"Refusing path outside portable package: {absolute}")
    relative = absolute.relative_to(root)
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.exists() or cursor.is_symlink():
            if _is_reparse(cursor):
                raise SystemExit(f"Refusing reparse point in portable path: {cursor}")

def resolve_codex_home(args: argparse.Namespace) -> Path:
    root = package_root()
    if args.codex_dir:
        home = Path(args.codex_dir)
    elif os.environ.get("CODEX_HOME"):
        home = Path(os.environ["CODEX_HOME"])
    else:
        home = root / "home"
    if not home.is_absolute():
        home = root / home
    home = home.absolute()
    if not lexical_under(home, root) or not resolved_under(home, root):
        raise SystemExit(f"Refusing to write outside portable package: {home}")
    reject_reparse_chain(home, root)
    return home

def read_instructions(source_arg: str, root: Path) -> str:
    source = Path(source_arg)
    if not source.is_absolute():
        source = root / source
    source = source.absolute()
    if not lexical_under(source, root) or not resolved_under(source, root):
        raise SystemExit(f"Refusing to read instructions from outside portable package: {source}")
    reject_reparse_chain(source, root)
    if not source.is_file():
        raise SystemExit(f"Instruction file not found: {source}")
    _reject_existing_hardlink(source, "instruction source")
    return source.read_text(encoding="utf-8-sig")

def validate_output_name(requested_name: str) -> str:
    requested_name = requested_name.strip()
    if not requested_name:
        raise SystemExit("Output name must not be empty.")
    md_name = requested_name if requested_name.lower().endswith(".md") else f"{requested_name}.md"
    stem = md_name.split(".", 1)[0].upper()
    if (
        md_name in {".", ".."}
        or len(md_name) > 128
        or md_name.endswith((".", " "))
        or stem in WINDOWS_RESERVED
        or any(ord(ch) < 32 for ch in md_name)
        or any(ch in '<>:"/\\|?*' for ch in md_name)
    ):
        raise SystemExit("Output name must be one Windows-safe, non-reserved file name.")
    return md_name

def read_utf8_ps1(path: Path, root: Path) -> str:
    if not path.exists():
        return ""
    reject_reparse_chain(path, root)
    _reject_existing_hardlink(path, "env.local.ps1")
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"env.local.ps1 must be UTF-8 (BOM optional): {path}") from exc

def update_env_local(env_local: Path, md_filename: str, root: Path, *, dry_run: bool = False) -> bool:
    """Persist exactly one launcher-interface assignment without touching other secrets."""
    content = read_utf8_ps1(env_local, root)
    value = md_filename.replace("'", "''")
    target = f"$env:CODEX_MODEL_INSTRUCTIONS_FILE = '{value}'"
    lines = content.splitlines()
    output: list[str] = []
    replaced = False
    changed = False
    assignment_re = re.compile(r"^\s*\$env:CODEX_MODEL_INSTRUCTIONS_FILE\s*=", re.IGNORECASE)
    for line in lines:
        stripped = line.strip()
        if assignment_re.match(line):
            if not replaced:
                output.append(target)
                replaced = True
                if stripped != target:
                    changed = True
            else:
                changed = True
            continue
        output.append(line)
    if not replaced:
        if output and output[-1].strip():
            output.append("")
        output.append("# Managed by tool/codex-instruct.py; relative to portable CODEX_HOME.")
        output.append(target)
        changed = True
    if changed and not dry_run:
        _atomic_write_text(
            env_local,
            "\n".join(output).rstrip() + "\n",
            encoding="utf-8-sig",
            root=root,
        )
    return changed

def main() -> int:
    parser = argparse.ArgumentParser(description="Install portable Codex model instructions persistently")
    parser.add_argument("--file", "-f", required=True, help="Complete replacement instruction file inside this portable package")
    parser.add_argument("--name", "-n", default="gpt5.5-unrestricted", help="Output file name without .md")
    parser.add_argument("--codex-dir", help="Portable CODEX_HOME directory; must be inside this package")
    parser.add_argument("--dry-run", action="store_true", help="Show intended changes without writing")
    args = parser.parse_args()

    root = package_root()
    home = resolve_codex_home(args)
    md_name = validate_output_name(args.name)
    md_path = (home / md_name).absolute()
    env_local = (root / "env.local.ps1").absolute()
    for target in (md_path, env_local):
        if not lexical_under(target, root) or not resolved_under(target, root):
            raise SystemExit(f"Refusing to write outside portable package: {target}")
        reject_reparse_chain(target, root)

    content = read_instructions(args.file, root)
    persisted_path = os.path.relpath(md_path, root / "home")
    if args.dry_run:
        print(f"Package root : {root}")
        print(f"CODEX_HOME   : {home}")
        print(f"Write MD     : {md_path}")
        print(f"Persist via  : {env_local}")
        print(f"Set value    : CODEX_MODEL_INSTRUCTIONS_FILE={persisted_path}")
        return 0

    home.mkdir(parents=True, exist_ok=True)
    reject_reparse_chain(home, root)
    _atomic_write_text(md_path, content, encoding="utf-8", root=root)
    changed = update_env_local(env_local, persisted_path, root)
    print(f"Wrote {md_path}")
    print(f"env.local.ps1 {'updated' if changed else 'already current'}: {env_local}")
    print("The launcher will persist this setting across regenerated home/config.toml files.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
