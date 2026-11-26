"""
Extract form structure from a non-fillable PDF.

This script analyzes the PDF to find:
- Text labels with their exact coordinates
- Horizontal lines (row boundaries)
- Checkboxes (small rectangles)

Output: A JSON file with the form structure that can be used to generate
accurate field coordinates for filling.

Usage: python extract_form_structure.py <input.pdf> <output.json>
"""

import json
import sys

# The bundled isolated Python deliberately omits the script directory.
# Use only this entrypoint's verified package-local sibling modules.
if __name__ == "__main__" and sys.flags.safe_path:
    import stat
    from pathlib import Path
    _script = Path(__file__).absolute()
    _root = _script.parents[4]
    if _script.relative_to(_root).parts != ("home", "skills", "pdf", "scripts", "extract_form_structure.py"):
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

import pdfplumber

from portable_safety import PortablePathError, prepare_output_file, resolve_inside


def extract_form_structure(pdf_path):
    structure = {
        "pages": [],
        "labels": [],
        "lines": [],
        "checkboxes": [],
        "row_boundaries": []
    }

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            structure["pages"].append({
                "page_number": page_num,
                "width": float(page.width),
                "height": float(page.height)
            })

            words = page.extract_words()
            for word in words:
                structure["labels"].append({
                    "page": page_num,
                    "text": word["text"],
                    "x0": round(float(word["x0"]), 1),
                    "top": round(float(word["top"]), 1),
                    "x1": round(float(word["x1"]), 1),
                    "bottom": round(float(word["bottom"]), 1)
                })

            for line in page.lines:
                if abs(float(line["x1"]) - float(line["x0"])) > page.width * 0.5:
                    structure["lines"].append({
                        "page": page_num,
                        "y": round(float(line["top"]), 1),
                        "x0": round(float(line["x0"]), 1),
                        "x1": round(float(line["x1"]), 1)
                    })

            for rect in page.rects:
                width = float(rect["x1"]) - float(rect["x0"])
                height = float(rect["bottom"]) - float(rect["top"])
                if 5 <= width <= 15 and 5 <= height <= 15 and abs(width - height) < 2:
                    structure["checkboxes"].append({
                        "page": page_num,
                        "x0": round(float(rect["x0"]), 1),
                        "top": round(float(rect["top"]), 1),
                        "x1": round(float(rect["x1"]), 1),
                        "bottom": round(float(rect["bottom"]), 1),
                        "center_x": round((float(rect["x0"]) + float(rect["x1"])) / 2, 1),
                        "center_y": round((float(rect["top"]) + float(rect["bottom"])) / 2, 1)
                    })

    lines_by_page = {}
    for line in structure["lines"]:
        page = line["page"]
        if page not in lines_by_page:
            lines_by_page[page] = []
        lines_by_page[page].append(line["y"])

    for page, y_coords in lines_by_page.items():
        y_coords = sorted(set(y_coords))
        for i in range(len(y_coords) - 1):
            structure["row_boundaries"].append({
                "page": page,
                "row_top": y_coords[i],
                "row_bottom": y_coords[i + 1],
                "row_height": round(y_coords[i + 1] - y_coords[i], 1)
            })

    return structure


def main():
    if len(sys.argv) != 3:
        print("Usage: extract_form_structure.py <input.pdf> <output.json>")
        sys.exit(1)

    try:
        pdf_path = resolve_inside(sys.argv[1], must_exist=True, kind="file")
        output_path = prepare_output_file(sys.argv[2])
    except (FileNotFoundError, PortablePathError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Extracting structure from {pdf_path}...")
    structure = extract_form_structure(pdf_path)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(structure, f, indent=2)

    print(f"Found:")
    print(f"  - {len(structure['pages'])} pages")
    print(f"  - {len(structure['labels'])} text labels")
    print(f"  - {len(structure['lines'])} horizontal lines")
    print(f"  - {len(structure['checkboxes'])} checkboxes")
    print(f"  - {len(structure['row_boundaries'])} row boundaries")
    print(f"Saved to {output_path}")


if __name__ == "__main__":
    main()
