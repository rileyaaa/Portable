#!/usr/bin/env python3
"""Bounded API/endpoint scanner for decompiled Android sources.

Uses only the package-local Python standard library. This replaces the legacy
Bash/grep/awk/sed pipeline so the portable bundle never silently depends on
host Unix tooling.
"""
from __future__ import annotations

import argparse
from collections import Counter
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

from portable_guard import PortablePathError, ensure_tree_has_no_reparse, find_portable_root, resolve_inside

MAX_SOURCE_FILES = 250_000
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024 * 1024
MAX_MATCHES = 50_000
MAX_URLS = 20_000
MAX_PATHS = 20_000
MAX_LINE_CHARS = 1_048_576

SECTIONS: dict[str, list[tuple[str, str]]] = {
    "retrofit": [
        ("Retrofit Annotations", r"@(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS|HTTP)\s*\("),
        ("Retrofit Headers & Parameters", r"@(Headers|Header|Query|QueryMap|Path|Body|Field|FieldMap|Part|PartMap|Url)\s*\("),
        ("Retrofit Base URL", r"(baseUrl|base_url)\s*\("),
    ],
    "okhttp": [
        ("OkHttp Request Building", r"(Request\.Builder|HttpUrl|\.newCall|\.enqueue|addInterceptor|addNetworkInterceptor)"),
        ("OkHttp URL Construction", r"(\.url\s*\(|\.addQueryParameter|\.addPathSegment|\.scheme\s*\(|\.host\s*\()"),
    ],
    "ktor": [
        ("Ktor Client Calls", r"\b(client|httpClient|HttpClient)\.(get|post|put|delete|patch|head|request)\s*[<(]"),
        ("Ktor URL Construction", r"(HttpRequestBuilder|defaultRequest\s*\{|\burl\s*\(\s*\"|URLBuilder|URLProtocol)"),
        ("Ktor Auth", r"(\bbearer\s*\{|BearerTokens\s*\(|loadTokens\s*\{|refreshTokens\s*\{|\bAuth\s*\)\s*\{)"),
    ],
    "apollo": [
        ("Apollo Client", r"(ApolloClient|\.serverUrl\s*\(|\.subscriptionNetworkTransport|HttpNetworkTransport)"),
        ("Apollo Operations", r"(\.query\s*\(\s*[A-Z]|\.mutation\s*\(\s*[A-Z]|\.subscription\s*\(\s*[A-Z])"),
    ],
    "volley": [
        ("Volley Requests", r"(StringRequest|JsonObjectRequest|JsonArrayRequest|ImageRequest|RequestQueue|Volley\.newRequestQueue)"),
    ],
    "auth": [
        ("Authentication & API Keys", r"(api[_-]?key|auth[_-]?token|bearer|authorization|x-api-key|client[_-]?secret|access[_-]?token)"),
        ("Base URLs and Constants", r"(BASE_URL|API_URL|SERVER_URL|ENDPOINT|API_BASE|HOST_NAME)"),
        ("HMAC / Signing", r"(HmacSHA|Mac\.getInstance\(\s*\"Hmac|signature|signRequest)"),
    ],
}

URL_RE = re.compile(r"https?://[^\s\"'<>\\]+", re.I)
PATH_RE = re.compile(
    r"[\"'](/(?:api|v[0-9]+|auth|login|logout|token|oauth|user|users|account|accounts|profile|profiles|order|orders|payment|payments|cart|checkout|search|feed|message|messages|notification|notifications|settings|upload|download|subscription|subscriptions)(?:/[A-Za-z0-9_{}.$~!()*+,;=:@%\-]+)*/?)[\"']",
    re.I,
)


def iter_sources(src: Path):
    files_seen = total_bytes = 0
    for base, dirs, files in os.walk(src, followlinks=False):
        dirs.sort()
        files.sort()
        for name in files:
            if not name.endswith((".java", ".kt")):
                continue
            files_seen += 1
            if files_seen > MAX_SOURCE_FILES:
                raise PortablePathError("Source tree exceeds the 250,000-file safety limit.")
            path = Path(base) / name
            size = path.stat().st_size
            if size > MAX_FILE_BYTES:
                continue
            total_bytes += size
            if total_bytes > MAX_TOTAL_BYTES:
                raise PortablePathError("Source scan exceeded the 8 GiB safety limit.")
            yield path


def print_section(title: str, matches: list[tuple[Path, int, str]], src: Path) -> int:
    print(f"\n==== {title} ====\n")
    for path, lineno, line in matches:
        print(f"{path.relative_to(src)}:{lineno}:{line.strip()}")
    return len(matches)


def collect_pattern(files: list[Path], pattern: str, *, flags: int, remaining: int) -> list[tuple[Path, int, str]]:
    rx = re.compile(pattern, flags)
    out: list[tuple[Path, int, str]] = []
    for path in files:
        if len(out) >= remaining:
            break
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, 1):
                    if len(line) > MAX_LINE_CHARS:
                        continue
                    if rx.search(line):
                        out.append((path, lineno, line.rstrip("\r\n")))
                        if len(out) >= remaining:
                            break
        except OSError:
            continue
    return out


def load_denylist(root: Path, skill_root: Path) -> list[re.Pattern[str]]:
    path = resolve_inside(
        root, skill_root / "references" / "third_party_hosts.txt",
        must_exist=False, kind="file",
    )
    out: list[re.Pattern[str]] = []
    if not path.is_file() or path.stat().st_size > 1_048_576:
        return out
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or len(line) > 512:
            continue
        try:
            out.append(re.compile(line, re.I))
        except re.error:
            continue
    return out


def scan_urls(files: list[Path], deny: list[re.Pattern[str]]) -> int:
    found: set[str] = set()
    for path in files:
        if len(found) >= MAX_URLS:
            break
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if len(line) > MAX_LINE_CHARS:
                        continue
                    for match in URL_RE.finditer(line):
                        url = match.group(0).rstrip(".,);]}>")
                        if len(url) <= 4096:
                            found.add(url)
                        if len(found) >= MAX_URLS:
                            break
        except OSError:
            continue
    first: list[str] = []
    third: list[str] = []
    for url in sorted(found):
        try:
            host = (urlsplit(url).hostname or "").lower()
        except ValueError:
            continue
        if not host:
            continue
        (third if any(rx.search(host) for rx in deny) else first).append(url)
    print("\n==== Hardcoded URLs — first-party candidates ====\n")
    for url in first:
        print(url)
    print("\n==== Hardcoded URLs — known third-party/noise ====\n")
    for url in third:
        print(url)
    if len(found) >= MAX_URLS:
        print(f"[truncated after {MAX_URLS} unique URLs]", file=sys.stderr)
    return len(found)


def scan_paths(files: list[Path]) -> int:
    paths: Counter[str] = Counter()
    for path in files:
        if len(paths) >= MAX_PATHS:
            break
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in PATH_RE.finditer(text):
            paths[match.group(1)] += 1
            if len(paths) >= MAX_PATHS:
                break
    print("\n==== Endpoint-shaped path literals ====\n")
    for value, count in sorted(paths.items()):
        print(f"{count:5d}  {value}")
    if len(paths) >= MAX_PATHS:
        print(f"[truncated after {MAX_PATHS} unique paths]", file=sys.stderr)
    return len(paths)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir")
    for flag in ("retrofit", "okhttp", "ktor", "apollo", "volley", "urls", "paths", "auth", "all"):
        parser.add_argument(f"--{flag}", action="store_true")
    args = parser.parse_args(argv)
    try:
        root = find_portable_root(__file__)
        src = resolve_inside(root, args.source_dir, kind="dir")
        ensure_tree_has_no_reparse(root, src, max_entries=MAX_SOURCE_FILES * 2)
        files = list(iter_sources(src))
        selected = [name for name in SECTIONS if getattr(args, name)]
        specials = args.urls or args.paths
        if args.all or (not selected and not specials):
            selected = list(SECTIONS)
            args.urls = True
            args.paths = True
        total_matches = 0
        for name in selected:
            flags = re.I if name == "auth" else 0
            for title, pattern in SECTIONS[name]:
                remaining = MAX_MATCHES - total_matches
                if remaining <= 0:
                    print(f"[truncated after {MAX_MATCHES} text matches]", file=sys.stderr)
                    return 0
                matches = collect_pattern(files, pattern, flags=flags, remaining=remaining)
                total_matches += print_section(title, matches, src)
        skill_root = Path(__file__).absolute().parent.parent
        if args.urls:
            scan_urls(files, load_denylist(root, skill_root))
        if args.paths:
            scan_paths(files)
        print("\n=== Search complete ===")
        return 0
    except (PortablePathError, OSError, ValueError, re.error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
