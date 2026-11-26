import sys

# The bundled isolated Python deliberately omits the script directory.
# Use only this entrypoint's verified package-local sibling modules.
if __name__ == "__main__" and sys.flags.safe_path:
    import stat
    from pathlib import Path
    _script = Path(__file__).absolute()
    _root = _script.parents[4]
    if _script.relative_to(_root).parts != ("home", "skills", "pdf", "scripts", "convert_pdf_to_images.py"):
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


from pdf2image import convert_from_path



from portable_safety import PortablePathError, portable_root, prepare_output_dir, resolve_inside


def _portable_poppler_bin() -> str:
    root = portable_root()
    for rel in ("tool/pdf/poppler/Library/bin", "tool/pdf/poppler/bin"):
        candidate = resolve_inside(root / rel, kind="dir")
        try:
            # pdf2image starts both binaries. Validate their leaf entries as
            # well as the directory before allowing executable discovery.
            for executable in ("pdftoppm.exe", "pdfinfo.exe"):
                resolve_inside(candidate / executable, must_exist=True, kind="file")
        except FileNotFoundError:
            continue
        return str(candidate)
    raise RuntimeError("package-local Poppler is missing under tool/pdf/poppler")

def convert(pdf_path, output_dir, max_dim=1000):
    pdf_path = resolve_inside(pdf_path, must_exist=True, kind="file")
    output_dir = prepare_output_dir(output_dir)
    images = convert_from_path(str(pdf_path), dpi=200, poppler_path=_portable_poppler_bin())

    for i, image in enumerate(images):
        width, height = image.size
        if width > max_dim or height > max_dim:
            scale_factor = min(max_dim / width, max_dim / height)
            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            image = image.resize((new_width, new_height))
        
        image_path = resolve_inside(output_dir / f"page_{i+1}.png", must_exist=False)
        image.save(str(image_path))
        print(f"Saved page {i+1} as {image_path} (size: {image.size})")

    print(f"Converted {len(images)} pages to PNG images")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: convert_pdf_to_images.py [input pdf] [output directory]")
        sys.exit(1)
    pdf_path = sys.argv[1]
    output_directory = sys.argv[2]
    try:
        convert(pdf_path, output_directory)
    except (FileNotFoundError, PortablePathError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
