import sys

# The bundled isolated Python deliberately omits the script directory.
# Use only this entrypoint's verified package-local sibling modules.
if __name__ == "__main__" and sys.flags.safe_path:
    import stat
    from pathlib import Path
    _script = Path(__file__).absolute()
    _root = _script.parents[4]
    if _script.relative_to(_root).parts != ("home", "skills", "pdf", "scripts", "check_fillable_fields.py"):
        raise RuntimeError("Script is outside its bundled skill layout")
    _directory = _script.parent
    for _entry in (*reversed(_script.parents),):
        _info = _entry.lstat()
        if not stat.S_ISDIR(_info.st_mode) or getattr(_info, "st_file_attributes", 0) & 0x400:
            raise RuntimeError("Skill import path crosses a link or non-directory")
    for _entry in (_script, _root / "env.ps1", _root / "codex.exe", _directory / "portable_safety.py"):
        _info = _entry.lstat()
        if not stat.S_ISREG(_info.st_mode) or _info.st_nlink != 1 or getattr(_info, "st_file_attributes", 0) & 0x400:
            raise RuntimeError("Skill import requires ordinary single-link package files")
    sys.path.insert(0, str(_directory))
    for _stream in (sys.stdout, sys.stderr):
        if _stream is not None and not _stream.isatty() and hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")

from pypdf import PdfReader
from portable_safety import PortablePathError, resolve_inside


def main():
    if len(sys.argv) != 2:
        print("Usage: check_fillable_fields.py [input pdf]", file=sys.stderr)
        raise SystemExit(1)
    try:
        path = resolve_inside(sys.argv[1], must_exist=True, kind="file")
    except (FileNotFoundError, PortablePathError) as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)
    reader = PdfReader(str(path))
    if reader.get_fields():
        print("This PDF has fillable form fields")
    else:
        print("This PDF does not have fillable form fields; you will need to visually determine where to enter data")


if __name__ == "__main__":
    main()
