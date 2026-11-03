#!/usr/bin/env python3
"""Cheap, batch, read-only full-tool diagnostics. No GitHub Actions dispatch.

Default: local offline repository regression suites (zero Actions minutes).
--network: add small official registry/PyPI JSON checks; no wheel, npm tarball,
Chromium or other large payloads are downloaded or executed. Results from
independent probes are collected before choosing a final exit status.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.parse

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT / "tool/full-stable-prepare.py"
PLAN = ROOT / "tool/full-stable-upgrade-plan.json"
SUITES = {
    "contracts": "test_full_stable_upgrade.py",
    "workflows": "test_maintenance_workflows.py",
    # PR #26's maintainer-only file exclusion exposed a source ZIP regression
    # not covered by the old 8-item metadata gate. Run real synthetic ZIP tests.
    "release": "test_release_package.py",
}
NETWORK_PROBES = ("npm", "corepack", "playwright", "pip", "pdf")


def stage_module():
    spec = importlib.util.spec_from_file_location("portable_fast_diagnose_stage", STAGE)
    if spec is None or spec.loader is None:
        raise RuntimeError("Missing reviewed full-stable-prepare.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def official_json(stage, url: str, destination: Path) -> dict:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {"pypi.org", "registry.npmjs.org"}:
        raise ValueError("Official metadata endpoint not allowed")
    stage.download(url, destination, limit=4*1024*1024,
                   accept="application/json", timeout=15)
    result = stage.obj(destination)
    if not isinstance(result, dict):
        raise ValueError("Official metadata must be a JSON object: " + destination.name)
    return result


def check_plan(stage, plan: dict) -> str:
    if plan.get("schema") != 1 or plan.get("platform") != "win32-x64" or \
            plan.get("state") != "PREPARATION_ONLY_NOT_INSTALLED":
        raise ValueError("Full tool upgrade plan schema/state changed")
    names = [r.get("name") for r in plan.get("targets", [])]
    if len(names) != len(set(names)) or len(names) < 14:
        raise ValueError("Full upgrade plan contains missing/duplicate target")
    for row in plan["targets"]:
        art = row.get("artifact")
        if art is not None and (not isinstance(art, dict) or
                                not re.fullmatch(r"[0-9a-f]{64}", art.get("sha256", "")) or
                                not art.get("url", "").startswith("https://")):
            raise ValueError("Missing official artifact SHA-256: " + row["name"])
    for name, expected in (("python", "3.15.2"), ("npm", "12.2.1"),
                           ("corepack", "0.36.0"), ("pip", "26.3"),
                           ("playwright-mcp", "0.0.84")):
        if stage.target(plan, name)["latestStable"] != expected:
            raise ValueError("Full upgrade target must be re-reviewed: " + name)
    return "14 targets and official SHA-256 pins checked; no payload downloaded"


def offline_suite(pattern: str) -> str:
    command = [sys.executable, "-E", "-s", "-B", "-m", "unittest", "discover",
               "-s", "tests", "-p", pattern, "-q"]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True,
                               timeout=90, check=False, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        raise ValueError(("offline regression failed: " + pattern + "\n" +
                          completed.stdout + "\n" + completed.stderr)[-2400:])
    return pattern + " PASS"


def network_probe(name: str, stage, plan: dict, folder: Path) -> str:
    if name == "npm":
        url, integrity = stage.npm_metadata("npm", stage.target(plan, "npm")["latestStable"], folder)
        return url + " " + integrity[:15] + "… (metadata only)"
    if name == "corepack":
        url, integrity = stage.npm_metadata("corepack", stage.target(plan, "corepack")["latestStable"], folder)
        return url + " " + integrity[:15] + "… (registry metadata only)"
    if name == "playwright":
        version = stage.target(plan, "playwright-mcp")["latestStable"]
        url = "https://registry.npmjs.org/@playwright%2Fmcp/" + version
        row = official_json(stage, url, folder / "playwright-metadata.json")
        dist = row.get("dist", {})
        tarball = dist.get("tarball", "") if isinstance(dist, dict) else ""
        integrity = dist.get("integrity", "") if isinstance(dist, dict) else ""
        if row.get("name") != "@playwright/mcp" or row.get("version") != version or \
                tarball != "https://registry.npmjs.org/@playwright/mcp/-/mcp-" + version + ".tgz" or \
                not isinstance(integrity, str) or \
                not re.fullmatch(r"sha512-[A-Za-z0-9+/]+={0,2}", integrity):
            raise ValueError("Official Playwright MCP registry identity/integrity mismatch")
        return "Playwright MCP " + version + " official metadata/integrity present"
    if name == "pip":
        row = stage.target(plan, "pip")
        version = row["latestStable"]
        url = row["artifact"]["url"]
        metadata = official_json(stage, url, folder / "pip-metadata.json")
        wheel_url = stage.select_official_pip_release_wheel(metadata, version,
                                                           row["artifact"]["sha256"])
        return "pip " + version + " official wheel SHA-256 identified: " + wheel_url.rsplit("/", 1)[-1]
    if name == "pdf":
        onnx = official_json(stage, "https://pypi.org/pypi/onnxruntime/json",
                             folder / "onnx-metadata.json")
        info = onnx.get("info", {})
        rows = onnx.get("urls", [])
        version = info.get("version") if isinstance(info, dict) else None
        if not isinstance(info, dict) or not isinstance(info.get("name"), str) or \
                info["name"].lower().replace("_", "-") != "onnxruntime" or \
                not isinstance(version, str) or not isinstance(rows, list):
            raise ValueError("Official ONNX Runtime PyPI metadata identity invalid")
        modern = any(stage.official_onnx_win315_wheel(r, version) for r in rows)
        if modern:
            return "Official ONNX Runtime " + version + " CPython 3.15 wheel available; modern path eligible"
        fallback = plan.get("pythonPdfCompatibilityException", {})
        for package, pinned in (("pymupdf", "1.28.2"), ("pymupdf4llm", "0.3.4")):
            if fallback.get(package) != pinned:
                raise ValueError("Unreviewed legacy PDF compatibility exception")
            metadata = official_json(stage, "https://pypi.org/pypi/" + package +
                                    "/" + pinned + "/json", folder / (package + "-metadata.json"))
            stage.official_legacy_pdf_wheels(metadata, package, pinned)
        return "ONNX " + version + " lacks cp315; official PyMuPDF 1.28.2 + 4LLM 0.3.4 fallback verified"
    raise ValueError("Unknown diagnostic probe: " + name)


def run_probe(label: str, fn) -> dict:
    try:
        detail = str(fn())
        return {"probe": label, "status": "PASS", "detail": detail[:500]}
    except Exception as error:
        return {"probe": label, "status": "FAIL", "detail":
                (type(error).__name__ + ": " + str(error))[-2000:]}


def diagnose(*, include_network: bool, selected: set[str] | None = None,
             stage=None, plan=None) -> list[dict]:
    if stage is None:
        stage = stage_module()
    if plan is None:
        plan = stage.obj(PLAN)
    enabled = {"plan", *SUITES, *NETWORK_PROBES} if selected is None else selected
    valid = {"plan", *SUITES, *NETWORK_PROBES}
    if not enabled.issubset(valid):
        raise ValueError("Unrecognized fast diagnostics: " + ",".join(sorted(enabled - valid)))
    if not include_network and enabled.intersection(NETWORK_PROBES):
        if selected is not None:
            raise ValueError("Selected upstream probes require --network")
        enabled = enabled - set(NETWORK_PROBES)
    result = []
    if "plan" in enabled:
        result.append(run_probe("plan", lambda: check_plan(stage, plan)))
    for label, pattern in SUITES.items():
        if label in enabled:
            result.append(run_probe(label, lambda pattern=pattern: offline_suite(pattern)))
    names = [name for name in NETWORK_PROBES if name in enabled]
    if names:
        scratch = ROOT / "tmp"
        if scratch.is_symlink():
            raise ValueError("Refuse symlinked diagnostic scratch")
        scratch.mkdir(exist_ok=True)
        def execute(name):
            def scoped():
                with tempfile.TemporaryDirectory(prefix="full-diagnose-" + name + "-", dir=scratch) as folder:
                    return network_probe(name, stage, plan, Path(folder))
            return run_probe(name, scoped)
        with ThreadPoolExecutor(max_workers=min(5, len(names))) as workers:
            future = {name: workers.submit(execute, name) for name in names}
            result.extend(future[name].result() for name in names)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Batch small failure checks before costly 03/full")
    parser.add_argument("--network", action="store_true", help="Also query official upstream JSON only")
    parser.add_argument("--only", help="Comma-separated probes: plan,contracts,workflows,npm,corepack,playwright,pip,pdf")
    args = parser.parse_args(argv)
    selected = set(args.only.split(",")) if args.only else None
    records = diagnose(include_network=args.network, selected=selected)
    for record in records:
        print("FAST_DIAGNOSE_" + record["status"] + "=" + record["probe"] + ": " +
              record["detail"].replace("\n", " ")[:450], flush=True)
    failed = [r for r in records if r["status"] == "FAIL"]
    print("FAST_DIAGNOSE_RESULT=" + ("FAIL" if failed else "PASS") +
          ";checked=" + str(len(records)) + ";failures=" + str(len(failed)))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as output:
            output.write("\n### Lightweight full-tool diagnostics (no payloads / no artifacts)\n\n")
            for record in records:
                detail = record["detail"].replace("|", "\\|").replace("\n", " ")[:320]
                output.write("- " + record["status"] + " **" + record["probe"] +
                             "**: " + detail + "\n")
            output.write("\nNot a replacement for real Windows native and release gates.\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
