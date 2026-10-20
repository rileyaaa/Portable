import os
import sys
from pathlib import Path

from pdf2image import convert_from_path



from portable_safety import PortablePathError, portable_root, prepare_output_dir, resolve_inside


def _portable_poppler_bin() -> str:
    root = portable_root()
    for rel in ("tool/pdf/poppler/Library/bin", "tool/pdf/poppler/bin"):
        candidate = root / rel
        cursor = root
        for part in Path(rel).parts:
            cursor = cursor / part
            from portable_safety import is_reparse
            if cursor.exists() and is_reparse(cursor):
                raise RuntimeError(f"Poppler path contains a reparse point: {cursor}")
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise RuntimeError("Poppler path escapes portable package") from exc
        if (resolved / "pdftoppm.exe").is_file() and (resolved / "pdfinfo.exe").is_file():
            return str(resolved)
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
