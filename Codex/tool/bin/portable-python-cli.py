#!/usr/bin/env python3
"""Run an installed console_script through the bundled portable Python.

The Windows distlib .exe launchers under Lib/site-packages/bin embed the Python
absolute path present at installation time.  The .cmd shims in tool/bin call this
helper instead, so moving the whole Codex Portable directory keeps CLI entry
points working.
"""
from __future__ import annotations

import importlib.metadata
import re
import sys


def _canonical_name(name: str) -> str:
    lower = name.lower()
    if re.fullmatch(r"pip\d+(?:\.\d+)?", lower):
        return "pip"
    return lower


def _find_entry_point(name: str):
    wanted = _canonical_name(name)
    eps = importlib.metadata.entry_points()
    if hasattr(eps, "select"):
        candidates = eps.select(group="console_scripts")
    else:  # pragma: no cover - compatibility with older Python only
        candidates = eps.get("console_scripts", ())
    matches = [ep for ep in candidates if ep.name.lower() == wanted]
    if len(matches) != 1:
        raise SystemExit(f"portable-python-cli: expected exactly one console_script for {wanted!r}, found {len(matches)}")
    return matches[0]


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: portable-python-cli.py <console-script-name> [args...]", file=sys.stderr)
        return 2
    requested = sys.argv[1]
    ep = _find_entry_point(requested)
    sys.argv = [requested, *sys.argv[2:]]
    result = ep.load()()
    return int(result) if isinstance(result, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
