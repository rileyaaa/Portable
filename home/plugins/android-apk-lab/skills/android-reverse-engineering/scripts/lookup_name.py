#!/usr/bin/env python3
"""Query Kotlin recovery mappings without host grep/Bash dependencies."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sre_parse
import sys

from portable_guard import PortablePathError, ensure_tree_has_no_reparse, find_portable_root, resolve_inside

MAX_MAPPING_BYTES = 64 * 1024 * 1024
MAX_SOURCE_FILES = 250_000
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024 * 1024
MAX_MATCHES = 10_000
MAX_PATTERN_CHARS = 256


def _safe_regex(pattern: str) -> re.Pattern[str]:
    if not pattern or len(pattern) > MAX_PATTERN_CHARS:
        raise ValueError("grep regex must contain 1-256 characters")
    parsed = sre_parse.parse(pattern)
    repeats = {sre_parse.MAX_REPEAT, sre_parse.MIN_REPEAT}
    possessive = getattr(sre_parse, "POSSESSIVE_REPEAT", None)
    if possessive is not None:
        repeats.add(possessive)

    def walk(items, in_repeat=False):
        for op, arg in items:
            if op in repeats:
                if in_repeat:
                    raise ValueError("nested regex repetition is not allowed")
                walk(arg[2], True)
            elif op is sre_parse.SUBPATTERN:
                walk(arg[-1], in_repeat)
            elif op is sre_parse.BRANCH:
                for branch in arg[1]:
                    walk(branch, in_repeat)
            elif op in {sre_parse.ASSERT, sre_parse.ASSERT_NOT, sre_parse.GROUPREF}:
                raise ValueError("lookarounds/backreferences are not allowed in grep regex")
    walk(parsed)
    return re.compile(pattern)


def load_mapping(root: Path, mapping_dir: Path) -> dict[str, str]:
    # Validating the directory does not validate the derived file entry.
    path = resolve_inside(root, mapping_dir / "mapping.json", kind="file")
    if not path.is_file():
        raise PortablePathError(f"mapping.json not found in {mapping_dir}")
    if path.stat().st_size > MAX_MAPPING_BYTES:
        raise PortablePathError("mapping.json exceeds the 64 MiB safety limit")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise ValueError("mapping.json must be a string-to-string object")
    return data


def grep_annot(pattern: str, sources: Path, mapping: dict[str, str]) -> None:
    regex = _safe_regex(pattern)
    files_seen = total_bytes = matches = 0
    for dp, dirs, files in os.walk(sources, followlinks=False):
        dirs.sort(); files.sort()
        for filename in files:
            if not filename.endswith(".java"):
                continue
            files_seen += 1
            if files_seen > MAX_SOURCE_FILES:
                raise PortablePathError("source scan exceeded file-count limit")
            path = Path(dp) / filename
            size = path.stat().st_size
            if size > MAX_FILE_BYTES:
                continue
            total_bytes += size
            if total_bytes > MAX_TOTAL_BYTES:
                raise PortablePathError("source scan exceeded 8 GiB limit")
            rel = path.relative_to(sources)
            obf = ".".join(rel.with_suffix("").parts)
            suffix = f"  // {mapping[obf]}" if obf in mapping else ""
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, start=1):
                    if len(line) > 1_048_576:
                        continue
                    if regex.search(line):
                        print(f"{rel}:{lineno}:{line.rstrip()}{suffix}")
                        matches += 1
                        if matches >= MAX_MATCHES:
                            print(f"[truncated after {MAX_MATCHES} matches]", file=sys.stderr)
                            return


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mapping_dir")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-o", "--obfuscated")
    group.add_argument("-p", "--package")
    group.add_argument("--grep", dest="grep_pattern")
    parser.add_argument("query", nargs="*")
    parser.add_argument("--sources")
    args = parser.parse_args(argv)
    try:
        root = find_portable_root(__file__)
        mapping_dir = resolve_inside(root, args.mapping_dir, kind="dir")
        mapping = load_mapping(root, mapping_dir)
        reverse: dict[str, list[str]] = {}
        for obf, real in mapping.items():
            reverse.setdefault(real, []).append(obf)

        if args.obfuscated:
            real = mapping.get(args.obfuscated)
            if real is None:
                raise ValueError(f"no mapping for {args.obfuscated}")
            print(f"{args.obfuscated}  ->  {real}")
            for sibling in sorted(s for s in reverse[real] if s != args.obfuscated):
                print(f"    sibling: {sibling}")
            return 0
        if args.package:
            needle = args.package.lower()
            for real in sorted(reverse):
                if needle in real.rsplit(".", 1)[0].lower():
                    print(real)
                    for obf in sorted(reverse[real]): print(f"    {obf}")
            return 0
        if args.grep_pattern is not None:
            if not args.sources:
                raise ValueError("--grep requires --sources <decompiled-sources-dir>")
            sources = resolve_inside(root, args.sources, kind="dir")
            ensure_tree_has_no_reparse(root, sources, max_entries=MAX_SOURCE_FILES * 2)
            grep_annot(args.grep_pattern, sources, mapping)
            return 0
        query = " ".join(args.query).strip().lower()
        if not query:
            raise ValueError("provide a query, -o, -p, or --grep")
        for real in sorted(reverse):
            if query in real.lower():
                print(real)
                for obf in sorted(reverse[real]): print(f"    {obf}")
        return 0
    except (PortablePathError, OSError, ValueError, re.error, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
