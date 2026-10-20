#!/usr/bin/env python3
"""Recover Kotlin class names without requiring Bash/grep on Windows."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import re
import sys

from portable_guard import PortablePathError, atomic_text_writer, atomic_write_text, ensure_tree_has_no_reparse, find_portable_root, resolve_inside

MAX_SOURCE_FILES = 250_000
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024 * 1024

RE_DEBUG = re.compile(r'@DebugMetadata\([^)]*?c\s*=\s*"([^"]+)"', re.S)
RE_DTWO = re.compile(r'@Metadata\([^)]*?d2\s*=\s*\{([^}]*)\}', re.S)
RE_LCLASS = re.compile(r'L([A-Za-z][\w/$]+);')
RE_RENAMED = re.compile(r'/\*\s*renamed from:\s*([\w.$]+)\s*\*/')
SKIP_PREFIXES = (
    "kotlin.", "kotlinx.", "androidx.", "android.", "java.", "javax.",
    "com.google.", "com.facebook.", "com.appsflyer.", "com.datadog.",
    "io.ktor.", "io.sentry.", "io.realm.", "okhttp3.", "okio.",
    "com.squareup.", "com.bumptech.", "com.airbnb.", "com.payu.",
    "com.storyteller.", "zendesk.", "io.intercom.", "com.microsoft.",
    "com.tinder.", "com.hotjar.", "com.amplitude.", "com.segment.",
    "com.mixpanel.", "com.onesignal.", "com.stripe.", "com.braintreepayments.",
    "retrofit2.", "dagger.", "javax.inject.", "org.jetbrains.",
)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sources")
    parser.add_argument("output", nargs="?")
    args = parser.parse_args(argv)
    try:
        root = find_portable_root(__file__)
        src = resolve_inside(root, args.sources, kind="dir")
        out_raw = args.output or os.fspath(src.parent / "mapping")
        out = resolve_inside(root, out_raw, must_exist=False)
        ensure_tree_has_no_reparse(root, src, max_entries=MAX_SOURCE_FILES * 2)
        out.mkdir(parents=True, exist_ok=True)
        by_package_dir = out / "by_package"
        by_package_dir.mkdir(parents=True, exist_ok=True)

        mapping: dict[str, str] = {}
        file_real: dict[str, str] = {}
        counts: defaultdict[str, int] = defaultdict(int)
        files_seen = 0
        total_bytes = 0

        for dp, dirs, files in os.walk(src, followlinks=False):
            dirs.sort()
            files.sort()
            for filename in files:
                if not filename.endswith(".java"):
                    continue
                files_seen += 1
                if files_seen > MAX_SOURCE_FILES:
                    raise PortablePathError("Too many Java source files for a bounded recovery scan.")
                path = Path(dp) / filename
                size = path.stat().st_size
                if size > MAX_FILE_BYTES:
                    continue
                total_bytes += size
                if total_bytes > MAX_TOTAL_BYTES:
                    raise PortablePathError("Java source scan exceeded the 8 GiB safety limit.")
                rel = path.relative_to(src)
                obf = ".".join(rel.with_suffix("").parts)
                if obf.startswith(SKIP_PREFIXES):
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                real = None
                match = RE_DEBUG.search(text)
                if match:
                    real = match.group(1).split("$", 1)[0]
                    counts["debug_meta"] += 1
                if not real:
                    match = RE_DTWO.search(text)
                    if match:
                        for lm in RE_LCLASS.finditer(match.group(1)):
                            candidate = lm.group(1).replace("/", ".").split("$", 1)[0]
                            if "." in candidate and not candidate.startswith(("kotlin.", "java.", "android")):
                                real = candidate
                                counts["d2"] += 1
                                break
                if not real:
                    match = RE_RENAMED.search(text)
                    if match:
                        real = match.group(1)
                        counts["renamed"] += 1
                if real:
                    mapping[obf] = real
                    file_real[obf] = os.fspath(path)

        with atomic_text_writer(root, out / "mapping.tsv", encoding="utf-8", newline="\n") as fh:
            fh.write("obf_fqn\treal_fqn\tfile\n")
            for key in sorted(mapping):
                fh.write(f"{key}\t{mapping[key]}\t{file_real[key]}\n")
        atomic_write_text(
            root,
            out / "mapping.json",
            json.dumps(mapping, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        by_pkg: defaultdict[str, list[tuple[str, str, str]]] = defaultdict(list)
        for obf, real in mapping.items():
            package = real.rsplit(".", 1)[0] if "." in real else "(default)"
            by_pkg[package].append((real, obf, file_real[obf]))
        used_names: set[str] = set()
        for index, (package, rows) in enumerate(sorted(by_pkg.items()), start=1):
            base = re.sub(r"[^A-Za-z0-9_.-]+", "_", package).replace(".", "_").strip("._") or "default"
            filename = f"{base}.txt"
            if filename.casefold() in used_names:
                filename = f"{base}-{index}.txt"
            used_names.add(filename.casefold())
            with atomic_text_writer(root, by_package_dir / filename, encoding="utf-8", newline="\n") as fh:
                for real, obf, source in sorted(rows):
                    fh.write(f"{real}\t{obf}\t{source}\n")

        print(f"Recovered {len(mapping)} class names")
        for key, value in sorted(counts.items()):
            print(f"  via {key}: {value}")
        print(f"Real packages: {len(by_pkg)}")
        print(f"Wrote {out / 'mapping.tsv'}, mapping.json, by_package/")
        return 0
    except (PortablePathError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
