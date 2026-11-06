#!/usr/bin/env python3
"""Read-only routing for 03 Tool maintenance.

Determine whether the previously reviewed full-tool plan contains versions
different from the installed inventory. This does NOT discover every upstream
release; only the separate official Node/CLI discovery can do that today.
Never silently claim that all installed tools are the latest available.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "tool/full-stable-upgrade-plan.json"
LEDGER = ROOT / "tool/installed-tools.json"
BUILD = ROOT / "tool/python-build-manifest.json"
DEPENDENCIES = ROOT / "tool/automation/versions.json"

REVIEWED_TOOLS = frozenset({
    "python", "pip", "paramiko", "node", "npm", "corepack",
    "playwright-mcp", "adb", "7zip", "ripgrep", "fd", "jq",
})
FULL_TARGETS = REVIEWED_TOOLS | {"chromium", "pyinstaller"}


def stable(value: str) -> tuple[int, ...]:
    if not isinstance(value, str) or re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", value) is None:
        raise ValueError("Unreviewed stable version: " + repr(value))
    return tuple(int(part) for part in value.split("."))


def route(plan: dict, ledger: dict, build: dict, dependencies: dict) -> tuple[bool, list[str]]:
    if plan.get("schema") != 1 or plan.get("platform") != "win32-x64" or \
            plan.get("state") != "PREPARATION_ONLY_NOT_INSTALLED" or \
            ledger.get("schema") != 1 or ledger.get("platform") != "win32-x64":
        raise ValueError("Unreviewed full-tool plan or inventory")
    rows = plan.get("targets")
    if not isinstance(rows, list) or len(rows) != len(FULL_TARGETS) or \
            {row.get("name") for row in rows if isinstance(row, dict)} != FULL_TARGETS:
        raise ValueError("Missing, duplicate or unknown full-tool target")
    installed = ledger.get("tools")
    if not isinstance(installed, dict) or set(installed) != REVIEWED_TOOLS | {"chromium", "git"}:
        raise ValueError("Unexpected installed tool inventory")
    versions = {row["name"]: row["latestStable"] for row in rows}
    if versions["chromium"] is not None:
        raise ValueError("Chromium must track the reviewed Playwright browser lock")
    if dependencies.get("playwrightMcp") != installed["playwright-mcp"]["version"] or \
            dependencies.get("browser", {}).get("version") != installed["chromium"]["version"]:
        raise ValueError("Unreviewed browser dependency/inventory mismatch")
    changes = []
    for name in sorted(REVIEWED_TOOLS):
        expected = versions[name]
        actual = installed[name].get("version")
        if installed[name].get("status") != "bundled":
            changes.append(name + ":not-installed")
            continue
        if stable(expected) < stable(actual):
            raise ValueError("Full-tool plan would downgrade " + name)
        if stable(expected) > stable(actual):
            changes.append(name + ":" + actual + "->" + expected)
    current_builder = build.get("packages", {}).get("pyinstaller")
    expected_builder = versions["pyinstaller"]
    if stable(expected_builder) < stable(current_builder):
        raise ValueError("Full-tool plan would downgrade pyinstaller")
    if stable(expected_builder) > stable(current_builder):
        changes.append("pyinstaller:" + current_builder + "->" + expected_builder)
    return bool(changes), changes


def main() -> int:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    build = json.loads(BUILD.read_text(encoding="utf-8"))
    dependencies = json.loads(DEPENDENCIES.read_text(encoding="utf-8"))
    needs_full, changes = route(plan, ledger, build, dependencies)
    print("FULL_TOOL_REVIEWED_PLAN=" + ("CANDIDATE" if needs_full else "UP_TO_DATE"))
    print("FULL_TOOL_APPROVED_CHANGES=" + json.dumps(changes, ensure_ascii=False))
    print("FULL_TOOL_UPSTREAM_SCOPE=Node/CLI official auto; other tools only approved reviewed plan")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write("full_plan_changes=" + str(needs_full).lower() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
