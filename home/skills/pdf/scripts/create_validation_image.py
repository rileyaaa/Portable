import json
import sys

# The bundled isolated Python deliberately omits the script directory.
# Use only this entrypoint's verified package-local sibling modules.
if __name__ == "__main__" and sys.flags.safe_path:
    import stat
    from pathlib import Path
    _script = Path(__file__).absolute()
    _root = _script.parents[4]
    if _script.relative_to(_root).parts != ("home", "skills", "pdf", "scripts", "create_validation_image.py"):
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


from PIL import Image, ImageDraw

from portable_safety import PortablePathError, prepare_output_file, resolve_inside




def create_validation_image(page_number, fields_json_path, input_path, output_path):
    fields_json_path = resolve_inside(fields_json_path, must_exist=True, kind="file")
    input_path = resolve_inside(input_path, must_exist=True, kind="file")
    output_path = prepare_output_file(output_path)
    with open(fields_json_path, encoding="utf-8-sig") as f:
        data = json.load(f)
    with Image.open(input_path) as img:
        draw = ImageDraw.Draw(img)
        num_boxes = 0
        
        for field in data["form_fields"]:
            if field["page_number"] == page_number:
                entry_box = field['entry_bounding_box']
                label_box = field['label_bounding_box']
                draw.rectangle(entry_box, outline='red', width=2)
                draw.rectangle(label_box, outline='blue', width=2)
                num_boxes += 2
        
        img.save(output_path)
        print(f"Created validation image at {output_path} with {num_boxes} bounding boxes")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: create_validation_image.py [page number] [fields.json file] [input image path] [output image path]")
        sys.exit(1)
    page_number = int(sys.argv[1])
    fields_json_path = sys.argv[2]
    input_image_path = sys.argv[3]
    output_image_path = sys.argv[4]
    try:
        create_validation_image(page_number, fields_json_path, input_image_path, output_image_path)
    except (FileNotFoundError, PortablePathError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
