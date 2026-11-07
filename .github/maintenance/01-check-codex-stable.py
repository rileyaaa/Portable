#!/usr/bin/env python3
"""Metadata-only official Codex stable check, before requesting a Windows Runner."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/maintenance/01-upgrade-runtime.py"


def upstream():
    source = importlib.util.spec_from_file_location("trusted_codex_upstream_metadata", SCRIPT)
    if source is None or source.loader is None:
        raise RuntimeError("Missing pinned official Codex metadata verifier")
    module = importlib.util.module_from_spec(source)
    source.loader.exec_module(module)
    return module


def discover(output: Path, repo: Path = ROOT) -> bool:
    if not output.is_file():
        raise RuntimeError("GitHub Actions output file must already exist")
    module = upstream()
    latest = module.latest_stable_release_url(repo)
    if latest is not None:
        version = module.parse_official_release_url(latest)
        if "-" in version:
            raise RuntimeError("Only published official stable Codex can be selected automatically")
    needed = latest is not None
    with output.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write("codex_updates=" + str(needed).lower() + "\n")
    print("OFFICIAL_CODEX_METADATA_ONLY=" + ("UPDATE_REQUIRED" if needed else "ALREADY_CURRENT"))
    return needed


def main() -> int:
    target = os.environ.get("GITHUB_OUTPUT")
    if not target:
        raise RuntimeError("Only metadata-only GitHub Actions discovery is supported")
    discover(Path(target))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print("CODEX_DISCOVERY_FAILED=" + type(exc).__name__ + ": " + str(exc),
              file=sys.stderr)
        raise SystemExit(2)
