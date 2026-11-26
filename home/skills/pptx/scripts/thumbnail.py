"""Create thumbnail grids from PowerPoint presentation slides.

Creates a grid layout of slide thumbnails for quick visual analysis.
Labels each thumbnail with its XML filename (e.g., slide1.xml).
Hidden slides are shown with a placeholder pattern.

Usage:
    python thumbnail.py input.pptx [output_prefix] [--cols N]

Examples:
    python thumbnail.py presentation.pptx
    # Creates: thumbnails.jpg

    python thumbnail.py template.pptx grid --cols 4
    # Creates: grid.jpg (or grid-1.jpg, grid-2.jpg for large decks)
"""

import argparse
import posixpath
import subprocess
import sys
import zipfile
from pathlib import Path

import defusedxml.minidom
from defusedxml import ElementTree

# The bundled isolated Python deliberately omits the script directory.
# Use only this entrypoint's verified package-local sibling modules.
if __name__ == "__main__" and sys.flags.safe_path:
    import stat
    from pathlib import Path
    _script = Path(__file__).absolute()
    _root = _script.parents[4]
    if _script.relative_to(_root).parts != ("home", "skills", "pptx", "scripts", "thumbnail.py"):
        raise RuntimeError("Script is outside its bundled skill layout")
    _directory = _script.parent
    for _entry in (*reversed(_script.parents), _directory / "office", _directory / "office/helpers"):
        _info = _entry.lstat()
        if not stat.S_ISDIR(_info.st_mode) or getattr(_info, "st_file_attributes", 0) & 0x400:
            raise RuntimeError("Skill import path crosses a link or non-directory")
    for _entry in (_script, _root / "env.ps1", _root / "codex.exe", _directory / "office/helpers/__init__.py", _directory / "office/soffice.py"):
        _info = _entry.lstat()
        if not stat.S_ISREG(_info.st_mode) or _info.st_nlink != 1 or getattr(_info, "st_file_attributes", 0) & 0x400:
            raise RuntimeError("Skill import requires ordinary single-link package files")
    sys.path.insert(0, str(_directory))
    for _stream in (sys.stdout, sys.stderr):
        if _stream is not None and not _stream.isatty() and hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")

from office.helpers import SLIDE_REL_TYPE, opc_target, portable_file, portable_subprocess_env, portable_temporary_directory, resolve_portable_path, safe_extract
from office.soffice import run_soffice
from PIL import Image, ImageDraw, ImageFont


THUMBNAIL_WIDTH = 300
CONVERSION_DPI = 100
MAX_COLS = 6
DEFAULT_COLS = 3
JPEG_QUALITY = 95
GRID_PADDING = 20
BORDER_WIDTH = 2
FONT_SIZE_RATIO = 0.10
LABEL_PADDING_RATIO = 0.4


def main():
    parser = argparse.ArgumentParser(
        description="Create thumbnail grids from PowerPoint slides."
    )
    parser.add_argument("input", help="Input PowerPoint file (.pptx)")
    parser.add_argument(
        "output_prefix",
        nargs="?",
        default="thumbnails",
        help="Output prefix for image files (default: thumbnails)",
    )
    parser.add_argument(
        "--cols",
        type=int,
        default=DEFAULT_COLS,
        help=f"Number of columns (default: {DEFAULT_COLS}, max: {MAX_COLS})",
    )

    args = parser.parse_args()

    if args.cols <= 0:
        parser.error("--cols must be positive")
    cols = min(args.cols, MAX_COLS)
    if args.cols > MAX_COLS:
        print(f"Warning: Columns limited to {MAX_COLS}")

    try:
        input_path = resolve_portable_path(args.input, must_exist=True, kind="file")
    except (FileNotFoundError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    if not input_path.exists() or input_path.suffix.lower() != ".pptx":
        print(f"Error: Invalid PowerPoint file: {args.input}", file=sys.stderr)
        sys.exit(1)

    try:
        output_path = resolve_portable_path(f"{args.output_prefix}.jpg", must_exist=False)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        with portable_temporary_directory() as temp_dir:
            temp_path = Path(temp_dir)
            # Validate archive structure/limits before handing the document to LibreOffice.
            validate_dir = temp_path / "archive-validation"
            validate_dir.mkdir()
            with zipfile.ZipFile(input_path, "r") as zf:
                safe_extract(zf, validate_dir)
            slide_info = get_slide_info(input_path)
            visible_images = convert_to_images(input_path, temp_path)

            if not visible_images and not any(s["hidden"] for s in slide_info):
                print("Error: No slides found", file=sys.stderr)
                sys.exit(1)

            slides = build_slide_list(slide_info, visible_images, temp_path)

            grid_files = create_grids(slides, cols, THUMBNAIL_WIDTH, output_path)

            print(f"Created {len(grid_files)} grid(s):")
            for grid_file in grid_files:
                print(f"  {grid_file}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _is_hidden(zf: zipfile.ZipFile, part: str) -> bool:
    try:
        with zf.open(part) as f:
            for _, root in ElementTree.iterparse(f, events=("start",)):
                return root.get("show") in ("0", "false")  
    except (KeyError, ElementTree.ParseError):
        return False
    return False


def get_slide_info(pptx_path: Path) -> list[dict]:
    with zipfile.ZipFile(pptx_path, "r") as zf:
        rels_content = zf.read("ppt/_rels/presentation.xml.rels").decode("utf-8")
        rels_dom = defusedxml.minidom.parseString(rels_content)

        rid_to_part = {}
        for rel in rels_dom.getElementsByTagName("Relationship"):
            if rel.getAttribute("Type") != SLIDE_REL_TYPE:
                continue
            part = opc_target(
                rel.getAttribute("Target"),
                "ppt/presentation.xml",
                rel.getAttribute("TargetMode"),
            )
            if part is not None:
                rid_to_part[rel.getAttribute("Id")] = part

        pres_content = zf.read("ppt/presentation.xml").decode("utf-8")
        pres_dom = defusedxml.minidom.parseString(pres_content)

        present = set(zf.namelist())

        slides = []
        for sld_id in pres_dom.getElementsByTagName("p:sldId"):
            part = rid_to_part.get(sld_id.getAttribute("r:id"))
            if part is not None and part in present:
                slides.append(
                    {"name": posixpath.basename(part), "hidden": _is_hidden(zf, part)}
                )

        return slides


def build_slide_list(
    slide_info: list[dict],
    visible_images: list[Path],
    temp_dir: Path,
) -> list[tuple[Path, str]]:
    visible_count = sum(1 for info in slide_info if not info["hidden"])
    rendered_hidden = len(visible_images) == len(slide_info) != visible_count

    if not rendered_hidden and visible_count != len(visible_images):
        raise ValueError(
            f"LibreOffice rendered {len(visible_images)} page(s) for {visible_count} "
            f"visible slide(s) of {len(slide_info)}; thumbnails would be mislabeled"
        )

    if visible_images:
        with Image.open(visible_images[0]) as img:
            placeholder_size = img.size
    else:
        placeholder_size = (1920, 1080)

    slides = []
    visible_idx = 0

    for info in slide_info:
        if info["hidden"] and not rendered_hidden:
            placeholder_path = temp_dir / f"hidden-{info['name']}.jpg"
            placeholder_img = create_hidden_placeholder(placeholder_size)
            placeholder_img.save(placeholder_path, "JPEG")
            slides.append((placeholder_path, f"{info['name']} (hidden)"))
        else:
            label = f"{info['name']} (hidden)" if info["hidden"] else info["name"]
            slides.append((visible_images[visible_idx], label))
            visible_idx += 1

    return slides


def create_hidden_placeholder(size: tuple[int, int]) -> Image.Image:
    img = Image.new("RGB", size, color="#F0F0F0")
    draw = ImageDraw.Draw(img)
    line_width = max(5, min(size) // 100)
    draw.line([(0, 0), size], fill="#CCCCCC", width=line_width)
    draw.line([(size[0], 0), (0, size[1])], fill="#CCCCCC", width=line_width)
    return img


def _portable_pdftoppm() -> str:
    for rel in (
        "tool/pdf/poppler/Library/bin/pdftoppm.exe",
        "tool/pdf/poppler/bin/pdftoppm.exe",
    ):
        try:
            return str(portable_file(rel))
        except FileNotFoundError:
            continue
    raise RuntimeError("package-local pdftoppm is missing under tool/pdf/poppler")

def convert_to_images(pptx_path: Path, temp_dir: Path) -> list[Path]:
    pdf_path = temp_dir / f"{pptx_path.stem}.pdf"

    result = run_soffice(
        ["--headless", "--convert-to", "pdf", "--outdir", str(temp_dir), str(pptx_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not pdf_path.exists():
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"PDF conversion failed: {detail}" if detail else "PDF conversion failed")

    result = subprocess.run(
        [
            _portable_pdftoppm(),
            "-jpeg",
            "-r",
            str(CONVERSION_DPI),
            str(pdf_path),
            str(temp_dir / "slide"),
        ],
        capture_output=True,
        text=True,
        env=portable_subprocess_env(),
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError("Image conversion failed")

    return sorted(temp_dir.glob("slide-*.jpg"))


def create_grids(
    slides: list[tuple[Path, str]],
    cols: int,
    width: int,
    output_path: Path,
) -> list[str]:
    max_per_grid = cols * (cols + 1)
    grid_files = []

    for chunk_idx, start_idx in enumerate(range(0, len(slides), max_per_grid)):
        end_idx = min(start_idx + max_per_grid, len(slides))
        chunk_slides = slides[start_idx:end_idx]

        grid = create_grid(chunk_slides, cols, width)

        if len(slides) <= max_per_grid:
            grid_filename = output_path
        else:
            stem = output_path.stem
            suffix = output_path.suffix
            grid_filename = output_path.parent / f"{stem}-{chunk_idx + 1}{suffix}"

        # Multi-grid names differ from the prefix checked by main(). A
        # pre-existing numbered output must pass the same link/path checks.
        grid_filename = resolve_portable_path(grid_filename, must_exist=False, kind="file")
        grid_filename.parent.mkdir(parents=True, exist_ok=True)
        grid.save(str(grid_filename), quality=JPEG_QUALITY)
        grid_files.append(str(grid_filename))

    return grid_files


def create_grid(
    slides: list[tuple[Path, str]],
    cols: int,
    width: int,
) -> Image.Image:
    font_size = int(width * FONT_SIZE_RATIO)
    label_padding = int(font_size * LABEL_PADDING_RATIO)

    with Image.open(slides[0][0]) as img:
        aspect = img.height / img.width
    height = int(width * aspect)

    rows = (len(slides) + cols - 1) // cols
    grid_w = cols * width + (cols + 1) * GRID_PADDING
    grid_h = rows * (height + font_size + label_padding * 2) + (rows + 1) * GRID_PADDING

    grid = Image.new("RGB", (grid_w, grid_h), "white")
    draw = ImageDraw.Draw(grid)

    try:
        font = ImageFont.load_default(size=font_size)
    except Exception:
        font = ImageFont.load_default()

    for i, (img_path, slide_name) in enumerate(slides):
        row, col = i // cols, i % cols
        x = col * width + (col + 1) * GRID_PADDING
        y_base = (
            row * (height + font_size + label_padding * 2) + (row + 1) * GRID_PADDING
        )

        label = slide_name
        bbox = draw.textbbox((0, 0), label, font=font)
        text_w = bbox[2] - bbox[0]
        draw.text(
            (x + (width - text_w) // 2, y_base + label_padding),
            label,
            fill="black",
            font=font,
        )

        y_thumbnail = y_base + label_padding + font_size + label_padding

        with Image.open(img_path) as img:
            img.thumbnail((width, height), Image.Resampling.LANCZOS)
            w, h = img.size
            tx = x + (width - w) // 2
            ty = y_thumbnail + (height - h) // 2
            grid.paste(img, (tx, ty))

            if BORDER_WIDTH > 0:
                draw.rectangle(
                    [
                        (tx - BORDER_WIDTH, ty - BORDER_WIDTH),
                        (tx + w + BORDER_WIDTH - 1, ty + h + BORDER_WIDTH - 1),
                    ],
                    outline="gray",
                    width=BORDER_WIDTH,
                )

    return grid


if __name__ == "__main__":
    main()
