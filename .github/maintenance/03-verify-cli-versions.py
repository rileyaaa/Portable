#!/usr/bin/env python3
"""Identify existing Windows CLI binaries by byte equality with official releases.

Requires *downloaded* official archives; no network activity or package mutation.
Release metadata SHA-256 values were recorded from official GitHub release APIs.
A size match alone never establishes a version.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

OFFICIAL = {
    "fd": {
        "version": "10.5.2",
        "tag": "v10.5.2",
        "asset": "fd-v10.5.2-x86_64-pc-windows-msvc.zip",
        "size": 1564536,
        "sha256": "7edac75ef96b7e9a01ebb251a21ee86ea365a09adcfb865f1ec3346a906153b6",
        "binary": "fd.exe"
    },
    "rg": {
        "version": "15.2.0",
        "tag": "15.2.0",
        "asset": "ripgrep-15.2.0-x86_64-pc-windows-msvc.zip",
        "size": 1789611,
        "sha256": "71b2fef860abe467217a538ff31de02f5258807c0129f771846f87bd029aafc5",
        "binary": "rg.exe"
    },
    "jq": {
        "version": "1.8.2",
        "tag": "jq-1.8.2",
        "asset": "jq-windows-amd64.exe",
        "size": 1035264,
        "sha256": "a6fc67fedaf9128a3309a1e2ebb8b986aeccf70122ee46d2cb4849e423f0c627",
        "binary": "jq.exe"
    }
}


def sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def match(repo: Path, packages: dict[str, Path]) -> list[dict]:
    results = []
    for name in ("fd", "rg", "jq"):
        spec = OFFICIAL[name]
        official = packages[name].absolute()
        embedded = repo / "tool" / "bin" / spec["binary"]
        row = {"name": name, "candidate_version": spec["version"],
               "github_release_tag": spec["tag"], "official_asset": spec["asset"]}
        if not official.is_file() or not embedded.is_file():
            raise ValueError(f"Missing local file for {name}")
        if official.name != spec["asset"]:
            raise ValueError(f"Incorrect official asset filename: {official.name}")
        row["official_asset_sha256"] = sha256(official)
        if official.stat().st_size != spec["size"] or row["official_asset_sha256"] != spec["sha256"]:
            raise ValueError(f"Official {name} asset size or SHA-256 mismatch")
        if name == "jq":
            row["official_exe_sha256"] = row["official_asset_sha256"]
        else:
            with zipfile.ZipFile(official) as archive:
                candidates = [entry for entry in archive.infolist()
                              if PurePosixPath(entry.filename).name == spec["binary"]
                              and entry.is_dir() is False]
                if len(candidates) != 1:
                    raise ValueError(f"Official {name} archive has unexpected binary layout")
                member = candidates[0]
                if member.file_size > 100_000_000:
                    raise ValueError(f"Official {name} binary unreasonably large")
                hasher = hashlib.sha256()
                with archive.open(member) as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        hasher.update(chunk)
                row["official_exe_sha256"] = hasher.hexdigest()
        row["bundled_exe_sha256"] = sha256(embedded)
        row["bundled_bytes"] = embedded.stat().st_size
        row["byte_identical"] = row["official_exe_sha256"] == row["bundled_exe_sha256"]
        row["status"] = "VERIFIED" if row["byte_identical"] else "MISMATCH"
        results.append(row)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--fd-archive", type=Path, required=True)
    parser.add_argument("--rg-archive", type=Path, required=True)
    parser.add_argument("--jq-exe", type=Path, required=True)
    args = parser.parse_args()
    try:
        rows = match(args.repo.absolute(),
                     {"fd": args.fd_archive, "rg": args.rg_archive, "jq": args.jq_exe})
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0 if all(r["byte_identical"] for r in rows) else 2
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        print(f"CLI identity verifier: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
