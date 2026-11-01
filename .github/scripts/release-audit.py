#!/usr/bin/env python3
"""Ten fresh, fail-closed seeded checks of the exact release checkout.

Run --release with bundled Python on Windows. --local-bridge is an explicitly
narrower Linux/local preflight, never accepted as a release report. No network
outside test loopback fixtures and no user credentials are used.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import gc
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import re
import stat
import subprocess
import sys
import threading
import time
import unittest
import warnings

ROOT = Path(__file__).resolve().parents[2]
BRIDGE_FILES = ["tool/socks-http-bridge.py", "README.md", ".github/scripts/release-audit.py"]
GROUPS = {
    "unit": (["test_socks_http_bridge", "test_socks_http_bridge_boundaries"], 64),
    "tcp": (["test_socks_http_bridge_network", "test_socks_http_bridge_stress.LiveBoundaryTests"], 19),
    "property": (["test_socks_http_bridge_stress.SeededProtocolTests"], 6),
    "runtime": (["test_runtime_package", "test_mode_copies", "test_tui_fullscreen", "test_release_package"], 20),
}
REPORT = ROOT / "tmp/windows-release-state/release-audit/report.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def ordinary(path: Path) -> None:
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            and not getattr(info, "st_file_attributes", 0) & 0x400,
            "Non-regular audit input: " + str(path.relative_to(ROOT)))


def source_files(release: bool) -> list[Path]:
    names = set(BRIDGE_FILES)
    names.update(str(p.relative_to(ROOT)).replace(os.sep, "/")
                 for p in (ROOT / "tests").glob("test_socks_http_bridge*.py"))
    if release:
        names.update(["run-codex.ps1", "env.ps1", "login-json.ps1", "codex-package.json",
                      "tool/runtime-manifest.json", "tool/package-release.py",
                      "tool/python-packages.in.txt", ".github/workflows/release.yml",
                      ".github/maintenance/02-compatibility.py"])
        names.update(str(p.relative_to(ROOT)).replace(os.sep, "/")
                     for p in (ROOT / "Version_History").glob("*-*.ps1"))
        names.update(str(p.relative_to(ROOT)).replace(os.sep, "/")
                     for p in (ROOT / "tests").glob("test_*.py"))
    return [ROOT / name for name in sorted(names)]


def snapshot(release: bool) -> dict[str, str]:
    result = {}
    for path in source_files(release):
        ordinary(path)
        result[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], stderr=subprocess.PIPE,
                                   timeout=30).decode("utf-8").strip()


def numeric(node):
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        return numeric(node.left) * numeric(node.right)
    raise RuntimeError("Unsupported constant expression")


def static_checks(release: bool) -> dict:
    checks = []
    for path in source_files(release):
        if path.suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            checks.append("syntax:" + path.relative_to(ROOT).as_posix())
    source = (ROOT / "tool/socks-http-bridge.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    limits = {n.targets[0].id: numeric(n.value) for n in tree.body
              if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
              and n.targets[0].id in {"MAX_WORKERS", "MAX_HEADER_BYTES", "MAX_BODY_BYTES",
                                     "HEADER_TIMEOUT", "BODY_TIMEOUT", "IO_TIMEOUT", "IDLE_TIMEOUT"}}
    require(limits == {"MAX_WORKERS": 64, "MAX_HEADER_BYTES": 65536,
                       "MAX_BODY_BYTES": 128 * 1024 * 1024, "HEADER_TIMEOUT": 10.0,
                       "BODY_TIMEOUT": 180.0, "IO_TIMEOUT": 30.0, "IDLE_TIMEOUT": 60.0},
            "Unreviewed bridge limit change")
    require("hmac.compare_digest" in source, "Missing constant-time credential check")
    require("validate_loopback_host" in source and "address.is_loopback" in source,
            "Missing loopback-only listener check")
    checks.extend(["bridge limits", "credential comparison", "loopback listener"])
    if release:
        require(os.name == "nt", "Release audit requires native Windows")
        expected_python = ROOT / "tool/python/python.exe"
        require(Path(sys.executable).resolve() == expected_python.resolve(), "Not bundled Python")
        import socks
        import h11
        require(socks.__version__ == "1.7.1" and h11.__version__ == "0.16.0", "Dependency pin mismatch")
        require(Path(socks.__file__).resolve().is_relative_to(ROOT / "tool/python"),
                "PySocks was imported outside the package")
        require(Path(h11.__file__).resolve().is_relative_to(ROOT / "tool/python"),
                "h11 was imported outside the package")
        require(not git("status", "--porcelain=v1", "--untracked-files=no"), "Dirty release source")
        checks.extend(["native Windows", "bundled Python", "pinned local dependencies", "clean source"])
    return {"passed": len(checks), "checks": checks}


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def child(group: str, seed: int) -> int:
    sys.path.insert(0, str(ROOT / "tests"))
    os.environ["CODEX_AUDIT_SEED"] = str(seed)
    names, expected = GROUPS[group]
    items = list(flatten(unittest.defaultTestLoader.loadTestsFromNames(names)))
    require(len(items) == expected, f"Unexpected {group} test count: {len(items)} != {expected}")
    require(len({t.id() for t in items}) == expected, "Duplicate test IDs")
    random.Random(seed).shuffle(items)
    before = set(threading.enumerate())
    warnings.simplefilter("error", ResourceWarning)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(items))
    gc.collect()
    for thread in set(threading.enumerate()) - before:
        thread.join(timeout=3)
    leaked = [t.name for t in set(threading.enumerate()) - before if t.is_alive()]
    record = {"group": group, "seed": seed, "tests": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors),
              "skipped": len(result.skipped), "threads_leaked": leaked}
    print("RESULT_JSON=" + json.dumps(record), flush=True)
    return 0 if result.wasSuccessful() and not result.skipped and not leaked else 1


def prepare_directory() -> Path:
    cursor = ROOT
    for part in ("tmp", "windows-release-state", "release-audit"):
        cursor /= part
        if cursor.exists() or cursor.is_symlink():
            info = cursor.lstat()
            require(stat.S_ISDIR(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                    "Unsafe audit output directory")
        else:
            cursor.mkdir()
    return cursor


def version_seed_base() -> int:
    """Bind all ten deterministic audit seeds to the pinned CLI version."""
    version = json.loads((ROOT / "tool/runtime-manifest.json").read_text(encoding="utf-8"))["version"]
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    require(match is not None, "Invalid pinned release version")
    major, minor, patch = (int(part) for part in match.groups())
    return major * 1_000_000 + minor * 1_000 + patch * 10 + 200


def run(release: bool) -> None:
    if release:
        require(os.name == "nt", "Release audit cannot be fulfilled by local/Linux checks")
    directory = prepare_directory()
    frozen = snapshot(release)
    head = git("rev-parse", "HEAD") if release else None
    record = {"format": 1, "scope": "windows-release" if release else "local-bridge-only",
              "started_utc": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
              "python": sys.version, "source_commit": head, "source_sha256": frozen, "rounds": []}
    groups = ["unit", "tcp", "property"] + (["runtime"] if release else [])
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for number in range(1, 11):
        require(snapshot(release) == frozen, "Source changed; restart all ten rounds")
        seed = version_seed_base() + number
        row = {"round": number, "seed": seed, "static": static_checks(release), "groups": {}}
        for group in groups:
            started = time.monotonic()
            command = [sys.executable, "-B", str(Path(__file__).resolve()), "--child", group,
                       "--seed", str(seed)]
            completed = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, timeout=180)
            path = directory / f"round-{number:02d}-{group}.log"
            path.write_bytes(completed.stdout)
            output = completed.stdout.decode("utf-8", errors="replace")
            print(output, end="", flush=True)
            require(completed.returncode == 0, f"Round {number} {group} failed; no release permitted")
            require("ResourceWarning" not in output, "Resource warning detected")
            require("RESULT_JSON=" in output, "Missing dynamic result")
            detail = json.loads(output.rsplit("RESULT_JSON=", 1)[1])
            require(detail["failures"] == detail["errors"] == detail["skipped"] == 0
                    and not detail["threads_leaked"], "Non-passing group result")
            detail["seconds"] = round(time.monotonic() - started, 3)
            row["groups"][group] = detail
        require(snapshot(release) == frozen, "Source changed during tests; restart all ten rounds")
        record["rounds"].append(row)
        REPORT.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(f"RELEASE_AUDIT_ROUND={number:02d} SEED={seed} STATUS=PASS", flush=True)
    record["all_passed"] = True
    record["completed_utc"] = datetime.now(timezone.utc).isoformat()
    record["dynamic_executions"] = sum(g["tests"] for r in record["rounds"] for g in r["groups"].values())
    REPORT.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("TEN_CONSECUTIVE_ROUNDS=PASS scope=" + record["scope"]
          + " tests=" + str(record["dynamic_executions"]), flush=True)


def verify() -> None:
    ordinary(REPORT)
    record = json.loads(REPORT.read_text(encoding="utf-8"))
    require(record.get("scope") == "windows-release" and record.get("all_passed") is True,
            "Not a successful Windows release audit")
    require(record.get("source_commit") == git("rev-parse", "HEAD"), "Audit commit differs")
    require(record.get("source_sha256") == snapshot(True), "Audited source bytes differ")
    require(len(record.get("rounds", [])) == 10, "Exactly ten rounds are required")
    for i, row in enumerate(record["rounds"], 1):
        require(row["round"] == i and row["seed"] == version_seed_base() + i, "Incorrect round sequence")
        require(set(row["groups"]) == set(GROUPS), "Incomplete round")
        for name, detail in row["groups"].items():
            require(detail["tests"] == GROUPS[name][1] and detail["errors"] == detail["failures"]
                    == detail["skipped"] == 0 and not detail["threads_leaked"], "Invalid audit result")
    static_checks(True)
    print("AUDITED_SOURCE_REVERIFIED=PASS commit=" + record["source_commit"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--release", action="store_true")
    group.add_argument("--local-bridge", action="store_true")
    group.add_argument("--verify", action="store_true")
    group.add_argument("--child", choices=GROUPS)
    parser.add_argument("--seed", type=int, default=version_seed_base() + 1)
    args = parser.parse_args()
    if args.child:
        return child(args.child, args.seed)
    if args.verify:
        verify()
    else:
        run(args.release)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
