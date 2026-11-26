"""Validate package paths without reading website or browser credentials."""
import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).absolute().parents[3]


def validate(path, missing=False):
    raw = os.fspath(path)
    p = Path(raw)
    if not p.is_absolute() or ".." in p.parts or raw.startswith(("\\\\", "//")) or ":" in raw[2:]:
        raise ValueError("invalid local path")
    if os.path.commonpath([os.path.normcase(ROOT), os.path.normcase(p)]) != os.path.normcase(ROOT):
        raise ValueError("outside package")
    for q in (*reversed(p.parents), p):
        try:
            s = q.lstat()
        except FileNotFoundError:
            if q == p and missing:
                return p
            raise
        if stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
            raise ValueError("reparse path")
        if q != p and not stat.S_ISDIR(s.st_mode):
            raise ValueError("ancestor is not directory")
        if q == p and not (stat.S_ISDIR(s.st_mode) or stat.S_ISREG(s.st_mode) and s.st_nlink == 1):
            raise ValueError("unexpected file or link")
    if os.path.normcase(os.path.realpath(p)) != os.path.normcase(p):
        raise ValueError("resolved path mismatch")
    return p


def tree(p):
    validate(p)
    if p.is_dir():
        for child in p.iterdir():
            tree(child)


if __name__ == "__main__":
    try:
        if os.name != "nt" or len(sys.argv) != 3 or sys.argv[1] not in ("file", "missing", "tree", "directory"):
            raise ValueError("invalid guard invocation")
        p = validate(sys.argv[2], missing=sys.argv[1] == "missing")
        if sys.argv[1] == "tree":
            tree(p)
        if sys.argv[1] == "file" and not p.is_file():
            raise ValueError("not a regular file")
        if sys.argv[1] == "directory" and not p.is_dir():
            raise ValueError("not a directory")
    except (ValueError, OSError):
        sys.exit("COURSE_PATH_REFUSED")
