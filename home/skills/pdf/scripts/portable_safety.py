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


def is_reparse(path: Path, *, allow_missing: bool = False) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        attrs = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(attrs & 0x400)
    except FileNotFoundError:
        return not allow_missing
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
    # Resolve only the known bundled layout, without consulting an inherited
    # CODEX_INSTALL_DIR or searching unrelated ancestor directories for markers.
    script = Path(__file__).absolute()
    if len(script.parents) < 5:
        raise PortablePathError("PDF helper is not in the bundled skill layout")
    root = script.parents[4]
    if script.relative_to(root).parts != ("home", "skills", "pdf", "scripts", "portable_safety.py"):
        raise PortablePathError("PDF helper is not in the bundled skill layout")
    for entry in (*reversed(script.parents), script):
        if is_reparse(entry):
            raise PortablePathError(f"Portable helper path crosses a symlink/junction/reparse point: {entry}")
    for entry in (script, root / "codex.exe", root / "env.ps1"):
        if is_reparse(entry) or not entry.is_file():
            raise PortablePathError(f"Portable helper requires a regular package file: {entry}")
        reject_hardlinked_file(entry)
    return root


def resolve_inside(value: str | os.PathLike[str], *, must_exist: bool = False, kind: str | None = None) -> Path:
    root = portable_root()
    raw = Path(value).expanduser()
    candidate = raw if raw.is_absolute() else (Path.cwd() / raw)
    candidate = candidate.absolute()
    if ".." in candidate.parts:
        raise PortablePathError(f"Parent traversal is not allowed at the portable boundary: {value}")
    try:
        rel = candidate.relative_to(root)
    except ValueError as exc:
        raise PortablePathError(
            f"Path is outside Codex Portable; copy it into the package after explicit approval: {value}"
        ) from exc

    cursor = root
    for part in rel.parts:
        cursor = cursor / part
        if is_reparse(cursor, allow_missing=True):
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
