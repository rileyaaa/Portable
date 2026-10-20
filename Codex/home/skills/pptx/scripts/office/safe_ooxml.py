#!/usr/bin/env python3
"""Safely unpack or repack OOXML without raw unzip/zip extraction."""
from __future__ import annotations

import argparse
from pathlib import Path
import zipfile

from helpers import _is_reparse, _reject_reparse_chain, ensure_portable_tree_no_reparse, resolve_portable_path, rezip, safe_extract


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    u = sub.add_parser("unpack")
    u.add_argument("source")
    u.add_argument("destination")
    u.add_argument("--force", action="store_true")
    p = sub.add_parser("pack")
    p.add_argument("source_directory")
    p.add_argument("output")
    args = parser.parse_args()

    if args.command == "unpack":
        try:
            src = resolve_portable_path(args.source, must_exist=True, kind="file")
            dst = resolve_portable_path(args.destination, must_exist=False)
        except (FileNotFoundError, RuntimeError) as e:
            raise SystemExit(str(e)) from e
        _reject_reparse_chain(src)
        _reject_reparse_chain(dst)
        if _is_reparse(src) or not src.is_file():
            raise SystemExit("OOXML input must be a regular non-reparse file")
        if dst.exists():
            if not args.force:
                raise SystemExit("destination already exists; use --force only to reuse an empty directory")
            if _is_reparse(dst) or not dst.is_dir():
                raise SystemExit("refusing non-directory or reparse destination")
            if any(dst.iterdir()):
                raise SystemExit("--force refuses to delete or overwrite a non-empty destination; choose a fresh directory")
        else:
            dst.mkdir(parents=True)
        with zipfile.ZipFile(src, "r") as zf:
            safe_extract(zf, dst)
        return 0

    try:
        src_dir = ensure_portable_tree_no_reparse(args.source_directory)
        out = resolve_portable_path(args.output, must_exist=False)
    except (FileNotFoundError, RuntimeError) as e:
        raise SystemExit(str(e)) from e
    rezip(src_dir, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
