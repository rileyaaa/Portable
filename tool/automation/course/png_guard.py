"""Bounded local PNG validation before either course OCR engine (no image output)."""
import importlib.util
import json
import os
import struct
import sys
import warnings
import zlib
from pathlib import Path

MAX_BYTES = 20 * 1024 * 1024
MAX_SIDE = 4096
MAX_PIXELS = 16 * 1024 * 1024
PNG = b"\x89PNG\r\n\x1a\n"

class Refused(Exception):
    pass

def check(path):
    if path.stat().st_size > MAX_BYTES:
        raise Refused("PNG_LIMIT")
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise Refused("PNG_LIMIT")
    if not data.startswith(PNG):
        raise Refused("PNG_FORMAT")
    offset = 8
    width = height = None
    seen_idat = ended = False
    count = 0
    while offset < len(data):
        count += 1
        if count > 4096:
            raise Refused("PNG_LIMIT")
        if len(data) - offset < 12:
            raise Refused("PNG_CORRUPT")
        size, tag = struct.unpack_from(">I4s", data, offset)
        end = offset + 12 + size
        if end > len(data):
            raise Refused("PNG_CORRUPT")
        block = memoryview(data)[offset+4:end-4]
        if zlib.crc32(block) != struct.unpack_from(">I", data, end-4)[0]:
            raise Refused("PNG_CORRUPT")
        if count == 1:
            if tag != b"IHDR" or size != 13:
                raise Refused("PNG_CORRUPT")
            width, height = struct.unpack_from(">II", data, offset+8)
            if not width or not height:
                raise Refused("PNG_CORRUPT")
            if max(width, height) > MAX_SIDE or width * height > MAX_PIXELS:
                raise Refused("PNG_LIMIT")
        elif tag == b"IHDR":
            raise Refused("PNG_CORRUPT")
        if tag in (b"acTL", b"fcTL", b"fdAT"):
            raise Refused("PNG_FORMAT")
        if tag == b"IDAT":
            seen_idat = True
        if tag == b"IEND":
            if size or not seen_idat or end != len(data):
                raise Refused("PNG_CORRUPT")
            ended = True
            break
        offset = end
    if not ended:
        raise Refused("PNG_CORRUPT")
    # Use the already bundled Pillow decoder. Never sniff or decode any other
    # format, and never accept partially decoded or animated data.
    from PIL import Image, ImageFile
    import io
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with Image.open(io.BytesIO(data), formats=["PNG"]) as image:
                if image.format != "PNG" or image.size != (width, height) or image.n_frames != 1:
                    raise Refused("PNG_FORMAT")
                image.verify()
            with Image.open(io.BytesIO(data), formats=["PNG"]) as image:
                image.load()
    except Refused:
        raise
    except Exception:
        raise Refused("PNG_CORRUPT") from None
    return {"width": width, "height": height}

def main():
    if os.name != "nt" or len(sys.argv) != 3:
        raise Refused("PNG_PATH")
    spec = importlib.util.spec_from_file_location("course_path_guard", Path(__file__).with_name("path_guard.py"))
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    state = guard.validate(sys.argv[1])
    image = guard.validate(sys.argv[2])
    import re
    work = guard.ROOT / "work"
    parts = state.relative_to(work).parts
    if (len(parts) != 2 or not re.fullmatch(r"course-[a-z0-9][a-z0-9_-]{0,47}", parts[0])
            or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", parts[1])
            or image.parent != state / "tmp"
            or not re.fullmatch(r"ocr-[0-9a-f]{32}\.png", image.name) or not image.is_file()):
        raise Refused("PNG_PATH")
    print(json.dumps(check(image), separators=(",", ":")))

if __name__ == "__main__":
    try:
        main()
    except Refused as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("PNG_PATH_OR_DECODER", file=sys.stderr)
        sys.exit(1)
