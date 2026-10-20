"""Portable path safety for bundled PDF helper scripts.

Direct PDF helper invocations are package-local only.  A file outside the
Codex Portable root must first be copied into the package by an upper layer
after explicit user approval.
"""
from __future__ import annotations

import os
from pathlib import Path


class PortablePathError(RuntimeError):
    pass


def is_reparse(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        attrs = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(attrs & 0x400)
    except OSError:
        return True


def reject_hardlinked_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    try:
        info = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise PortablePathError(f"Unable to inspect file link count safely: {path}") from exc
    if getattr(info, "st_nlink", 1) != 1:
        raise PortablePathError(f"Hard-linked files are not allowed at this portable boundary: {path}")


def portable_root() -> Path:
    value = os.environ.get("CODEX_INSTALL_DIR")
    if not value:
        raise PortablePathError("CODEX_INSTALL_DIR is required; refusing host-directory fallback")
    raw = Path(value).expanduser().absolute()
    if not (raw / "codex.exe").is_file() or not (raw / "env.ps1").is_file():
        raise PortablePathError("CODEX_INSTALL_DIR is not a valid Codex Portable root")
    if is_reparse(raw):
        raise PortablePathError("Codex Portable root may not be a symlink/junction/reparse point")
    return raw.resolve()


def resolve_inside(value: str | os.PathLike[str], *, must_exist: bool = False, kind: str | None = None) -> Path:
    root = portable_root()
    raw = Path(value).expanduser()
    candidate = raw if raw.is_absolute() else (Path.cwd() / raw)
    candidate = candidate.absolute()
    try:
        rel = candidate.relative_to(root)
    except ValueError as exc:
        raise PortablePathError(
            f"Path is outside Codex Portable; copy it into the package after explicit approval: {value}"
        ) from exc

    cursor = root
    for part in rel.parts:
        cursor = cursor / part
        if cursor.exists() and is_reparse(cursor):
            raise PortablePathError(f"Path crosses a symbolic link/junction/reparse point: {cursor}")

    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PortablePathError(f"Path escapes Codex Portable after resolution: {value}") from exc

    if must_exist and not resolved.exists():
        raise FileNotFoundError(resolved)
    if kind == "file" and resolved.exists() and not resolved.is_file():
        raise PortablePathError(f"Expected a file: {resolved}")
    if kind == "dir" and resolved.exists() and not resolved.is_dir():
        raise PortablePathError(f"Expected a directory: {resolved}")
    reject_hardlinked_file(resolved)
    return resolved


def prepare_output_file(value: str | os.PathLike[str]) -> Path:
    out = resolve_inside(value, must_exist=False)
    parent = resolve_inside(out.parent, must_exist=False)
    parent.mkdir(parents=True, exist_ok=True)
    resolve_inside(parent, must_exist=True, kind="dir")
    return resolve_inside(out, must_exist=False)


def prepare_output_dir(value: str | os.PathLike[str]) -> Path:
    out = resolve_inside(value, must_exist=False)
    out.mkdir(parents=True, exist_ok=True)
    return resolve_inside(out, must_exist=True, kind="dir")
