#!/usr/bin/env python3
"""Losslessly normalize a classic split ZIP without recompressing any payload."""
from pathlib import Path
import shutil
import struct
import sys
import zipfile

EOCD = b"PK\x05\x06"
CD = b"PK\x01\x02"
LOCAL = b"PK\x03\x04"


def main(parts, target):
    prefixes = []
    size = 0
    target = Path(target)
    with target.open("wb") as out:
        for part in parts:
            part = Path(part)
            prefixes.append(size)
            with part.open("rb") as source:
                shutil.copyfileobj(source, out, 4 * 1024 * 1024)
            size += part.stat().st_size
    with target.open("r+b") as out:
        out.seek(max(0, size - 65557))
        tail = out.read()
        candidate = len(tail)
        while True:
            candidate = tail.rfind(EOCD, 0, candidate)
            if candidate < 0:
                raise RuntimeError("ZIP end-of-central-directory not found")
            if candidate + 22 > len(tail):
                continue
            fields = struct.unpack_from("<4s4H2LH", tail, candidate)
            if candidate + 22 + fields[-1] == len(tail):
                break
        end = size - len(tail) + candidate
        _, disk, cd_disk, on_disk, total, cd_size, cd_offset, comment_len = fields
        print("Split ZIP:", len(parts), "volumes;", total, "file/directory records; ZIP disk", disk)
        if disk != len(parts) - 1 or cd_disk >= len(parts):
            raise RuntimeError("Split ZIP disk indexes are inconsistent")
        if any(n >= 0xFFFF for n in (disk, cd_disk, total)):
            raise RuntimeError("ZIP64 indexing requires a different converter")
        if cd_offset == 0xFFFFFFFF or cd_size == 0xFFFFFFFF:
            raise RuntimeError("ZIP64 central directory requires a different converter")
        cd_start = prefixes[cd_disk] + cd_offset
        out.seek(cd_start)
        if out.read(4) != CD:
            raise RuntimeError("Central directory signature missing at claimed offset")
        fixes = []
        cursor = cd_start
        for index in range(total):
            out.seek(cursor)
            header = out.read(46)
            if len(header) != 46 or header[:4] != CD:
                raise RuntimeError(f"Invalid central directory record {index} at {cursor}")
            name_len, extra_len, note_len = struct.unpack_from("<3H", header, 28)
            start_disk = struct.unpack_from("<H", header, 34)[0]
            local_offset = struct.unpack_from("<L", header, 42)[0]
            if start_disk >= len(parts) or local_offset == 0xFFFFFFFF:
                raise RuntimeError(f"Unsupported local ZIP offset in record {index}")
            local_absolute = prefixes[start_disk] + local_offset
            out.seek(local_absolute)
            if out.read(4) != LOCAL:
                raise RuntimeError(f"Local header mismatch at record {index}, disk={start_disk}, offset={local_offset}")
            fixes.append((cursor, local_absolute))
            cursor += 46 + name_len + extra_len + note_len
        if cursor > end:
            raise RuntimeError("Central directory exceeds end record")
        for cursor, absolute in fixes:
            out.seek(cursor + 34)
            out.write(struct.pack("<H", 0))
            out.seek(cursor + 42)
            out.write(struct.pack("<L", absolute))
        out.seek(end + 4)
        out.write(struct.pack("<4H2L", 0, 0, total, total, cd_size, cd_start))
    with zipfile.ZipFile(target) as archive:
        print("Normalized entries:", len(archive.infolist()), "archive size:", target.stat().st_size)
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"CRC mismatch in restored split ZIP: {bad}")
        print("All restored ZIP entries passed CRC.")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise SystemExit("Usage: restore_split_zip.py part1 part2 ... last.zip output.zip")
    main(sys.argv[1:-1], sys.argv[-1])
