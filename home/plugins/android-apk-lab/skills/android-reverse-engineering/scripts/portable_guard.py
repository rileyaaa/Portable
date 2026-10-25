"""Shared package-boundary helpers for APK Lab skill scripts."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
from contextlib import contextmanager

WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL", "CLOCK$", "CONIN$", "CONOUT$",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class PortablePathError(RuntimeError):
    pass


def is_reparse(path: os.PathLike[str] | str, *, allow_missing: bool = False) -> bool:
    try:
        info = os.lstat(path)
        attrs = getattr(info, "st_file_attributes", 0)
        flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        return stat.S_ISLNK(info.st_mode) or bool(attrs & flag)
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


def _inside(root: Path, candidate: Path) -> bool:
    try:
        return os.path.commonpath([os.fspath(root), os.fspath(candidate)]) == os.fspath(root)
    except ValueError:
        return False


def find_portable_root(script_path: os.PathLike[str] | str) -> Path:
    script = Path(script_path).absolute()
    if len(script.parents) < 7:
        raise PortablePathError("APK Lab script is outside the bundled layout")
    root = script.parents[6]
    if script.relative_to(root).parts[:-1] != (
        "home", "plugins", "android-apk-lab", "skills",
        "android-reverse-engineering", "scripts",
    ):
        raise PortablePathError("APK Lab script is outside the bundled layout")
    # Do not search markers through a redirected ancestor, or fall back to a
    # different package when this copy is incomplete.
    for entry in (*reversed(script.parents), script):
        if is_reparse(entry):
            raise PortablePathError(f"Reparse point in APK Lab script path: {entry}")
    for entry in (script, root / "codex.exe", root / "env.ps1"):
        if is_reparse(entry) or not entry.is_file():
            raise PortablePathError(f"APK Lab requires a regular package file: {entry}")
        reject_hardlinked_file(entry)
    return root


def resolve_inside(
    root: Path,
    value: os.PathLike[str] | str,
    *,
    must_exist: bool = True,
    kind: str | None = None,
    allow_root: bool = False,
) -> Path:
    raw = Path(value)
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    lexical = raw.absolute()
    if ".." in lexical.parts:
        raise PortablePathError(f"Parent traversal is not allowed in APK Lab paths: {value}")
    if not _inside(root, lexical) or (lexical == root and not allow_root):
        raise PortablePathError(f"Path escapes Codex Portable package: {value}")

    for ancestor in (*reversed(root.parents), root):
        if is_reparse(ancestor):
            raise PortablePathError(f"Reparse point in APK Lab package path: {ancestor}")
    walk = root
    try:
        relative = lexical.relative_to(root)
    except ValueError as exc:
        raise PortablePathError(f"Path escapes Codex Portable package: {value}") from exc
    for part in relative.parts:
        walk = walk / part
        if is_reparse(walk, allow_missing=True):
            raise PortablePathError(f"Reparse point is not allowed in APK Lab path: {walk}")

    resolved = lexical.resolve(strict=False)
    if not _inside(root, resolved) or (resolved == root and not allow_root):
        raise PortablePathError(f"Resolved path escapes Codex Portable package: {value}")
    if must_exist and not resolved.exists():
        raise PortablePathError(f"Path does not exist: {value}")
    if kind == "file" and must_exist and not resolved.is_file():
        raise PortablePathError(f"Expected a file: {value}")
    if kind == "dir" and must_exist and not resolved.is_dir():
        raise PortablePathError(f"Expected a directory: {value}")
    reject_hardlinked_file(resolved)
    return resolved


def ensure_tree_has_no_reparse(root: Path, tree: Path, *, max_entries: int = 500_000) -> None:
    """Reject any reparse entry before a recursive scanner traverses the tree."""
    tree = resolve_inside(root, tree, kind="dir")
    seen = 0
    for base, dirs, files in os.walk(tree, followlinks=False):
        for name in [*dirs, *files]:
            seen += 1
            if seen > max_entries:
                raise PortablePathError("Source tree has too many entries for a safe scan.")
            entry = Path(base) / name
            if is_reparse(entry):
                raise PortablePathError(f"Reparse point is not allowed in scanned source tree: {entry}")
            if entry.is_file():
                reject_hardlinked_file(entry)

@contextmanager
def atomic_text_writer(root: Path, path: os.PathLike[str] | str, *, encoding: str = "utf-8", newline: str | None = "\n"):
    """Safely replace a package-local text file without following a hard-link target.

    The final path is never opened for writing.  Data is written to a newly-created
    file in the validated package tmp directory and then installed with ``os.replace``.
    """
    dest = resolve_inside(root, path, must_exist=False)
    parent = resolve_inside(root, dest.parent, must_exist=False, allow_root=True)
    scratch = resolve_inside(root, root / "tmp", must_exist=False)
    scratch.mkdir(parents=True, exist_ok=True)
    scratch = resolve_inside(root, scratch, kind="dir")
    parent.mkdir(parents=True, exist_ok=True)
    parent = resolve_inside(root, parent, kind="dir", allow_root=True)
    fd, temp_name = tempfile.mkstemp(prefix=".codex-write-", suffix=".tmp", dir=scratch)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline=newline) as handle:
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
        resolve_inside(root, parent, kind="dir", allow_root=True)
        os.replace(temp, dest)
    except Exception:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def atomic_write_text(root: Path, path: os.PathLike[str] | str, text: str, *, encoding: str = "utf-8") -> Path:
    with atomic_text_writer(root, path, encoding=encoding, newline="") as handle:
        handle.write(text)
    return resolve_inside(root, path, kind="file")

