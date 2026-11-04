#!/usr/bin/env python3
"""Official stable Windows Node/CLI discovery for manual 03/auto.

No global installs, local executables, Git writes, branches, releases or
Actions dispatches. Only official version metadata and immutable SHA-256
references may produce a candidate. The existing Windows read-only verifier
and digest-checked writer remain mandatory.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "tool/installed-tools.json"
OUT = ROOT / "tmp/auto-tool-update-plan.json"
OFFICIAL = {"ripgrep": "BurntSushi/ripgrep",
            "fd": "sharkdp/fd", "jq": "jqlang/jq"}
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
DIGEST = re.compile(r"[a-f0-9]{64}")
HOSTS = {"api.github.com", "nodejs.org"}
MAX_METADATA = 3 * 1024 * 1024


class _RejectRedirect(urllib.request.HTTPRedirectHandler):
    # urllib's stock redirect handler can forward custom request headers.
    # Reject redirects before a metadata bearer token could reach another host.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Official metadata redirected; no credentials forwarded")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def version(value: str) -> tuple[int, int, int]:
    require(isinstance(value, str) and VERSION.fullmatch(value) is not None,
            "Not an official stable numeric version: " + str(value))
    return tuple(int(x) for x in value.split("."))


def request_bytes(url: str, *, limit: int = MAX_METADATA) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    require(parsed.scheme == "https" and parsed.hostname in HOSTS and
            not parsed.username and not parsed.password and
            parsed.port in (None, 443) and not parsed.query and not parsed.fragment,
            "Unapproved official metadata endpoint")
    headers = {"User-Agent": "Codex-Portable-auto-check/1",
               "Accept": "application/vnd.github+json, application/json, text/plain"}
    if parsed.hostname == "api.github.com":
        # Only the official GitHub metadata API receives the Actions token.
        # Never forward it to nodejs.org, release asset URLs or redirect hosts.
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token:
            require("\r" not in token and "\n" not in token and len(token) < 8192,
                    "Invalid GitHub metadata token")
            headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    # Explicitly suppress ambient HTTP(S)_PROXY / Windows Internet Settings
    # for bearer-bearing metadata requests. The redirect guard is separate.
    with urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _RejectRedirect()).open(
            request, timeout=20) as response:
        final = urllib.parse.urlsplit(response.url)
        require(final.scheme == "https" and final.hostname in HOSTS and
                final.hostname == parsed.hostname,
                "Official metadata redirected to an unapproved host")
        content = response.read(limit + 1)
    require(0 < len(content) <= limit, "Official metadata exceeds limit or is empty")
    return content


def request_json(url: str):
    return json.loads(request_bytes(url).decode("utf-8"))


def ledger_versions() -> dict[str, str]:
    item = LEDGER.lstat()
    require(stat.S_ISREG(item.st_mode) and item.st_nlink == 1 and
            not (getattr(item, "st_file_attributes", 0) & 0x400),
            "Installed tool ledger must be an ordinary file")
    raw = json.loads(LEDGER.read_text(encoding="utf-8"))
    require(raw.get("schema") == 1 and raw.get("platform") == "win32-x64" and
            isinstance(raw.get("tools"), dict), "Unsupported installed tool ledger")
    result = {}
    for name in ("node", *OFFICIAL):
        selected = raw["tools"].get(name)
        require(isinstance(selected, dict) and isinstance(selected.get("version"), str),
                "Missing installed version for " + name)
        version(selected["version"])
        result[name] = selected["version"]
    return result


def github_release(tool: str) -> tuple[str, dict]:
    require(tool in OFFICIAL, "Unapproved GitHub release repository")
    response = request_json(
        "https://api.github.com/repos/" + OFFICIAL[tool] + "/releases/latest")
    require(isinstance(response, dict) and response.get("draft") is False and
            response.get("prerelease") is False and
            isinstance(response.get("assets"), list),
            "Latest GitHub release is not published stable")
    tag = response.get("tag_name")
    prefix = {"ripgrep": "", "fd": "v", "jq": "jq-"}[tool]
    require(isinstance(tag, str) and tag.startswith(prefix),
            "Unexpected stable release tag for " + tool)
    stable = tag[len(prefix):]
    version(stable)
    return stable, response


def verified_asset(tool: str, stable: str, release: dict,
                   filename: str) -> tuple[str, str]:
    repo = OFFICIAL[tool]
    tag = {"ripgrep": stable, "fd": "v" + stable,
           "jq": "jq-" + stable}[tool]
    url = ("https://github.com/" + repo + "/releases/download/" +
           tag + "/" + filename)
    assets = [asset for asset in release["assets"]
              if isinstance(asset, dict) and asset.get("name") == filename]
    require(len(assets) == 1, "Missing unique official Windows AMD64 asset: " + filename)
    asset = assets[0]
    digest = asset.get("digest")
    require(asset.get("browser_download_url") == url and
            asset.get("state") == "uploaded" and
            isinstance(asset.get("size"), int) and
            1024 < asset["size"] <= 150 * 1024 * 1024 and
            isinstance(digest, str) and digest.startswith("sha256:") and
            DIGEST.fullmatch(digest[7:]) is not None,
            "Official GitHub asset SHA-256 or URL is unavailable: " + filename)
    return url, digest[7:]


def official_node_latest(*, supported_major: int | None = None) -> str:
    rows = request_json("https://nodejs.org/dist/index.json")
    require(isinstance(rows, list) and 1 <= len(rows) <= 5000,
            "Unexpected official Node distribution index")
    versions = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        tag = item.get("version")
        if not isinstance(tag, str) or not tag.startswith("v") or not VERSION.fullmatch(tag[1:]):
            continue
        files = item.get("files")
        if isinstance(files, list) and "win-x64-zip" in files:
            versions.append(tag[1:])
    require(versions, "No official stable Node Windows x64 ZIP release")
    if supported_major is not None:
        require(type(supported_major) is int and 1 <= supported_major <= 99,
                "Unexpected pinned Node major")
        versions = [candidate for candidate in versions
                    if version(candidate)[0] == supported_major]
        require(versions, "No stable official Node ZIP for the verified current major")
    return max(versions, key=version)


def node_candidate(stable: str) -> dict:
    # Official SHASUMS are independently published alongside the Node ZIP.
    filename = "node-v" + stable + "-win-x64.zip"
    raw = request_bytes(
        "https://nodejs.org/dist/v" + stable + "/SHASUMS256.txt", limit=100 * 1024)
    sums = raw.decode("ascii", errors="strict").splitlines()
    matches = [m.group(1) for line in sums
               if (m := re.fullmatch(r"([a-f0-9]{64})\s+\*?" +
                                      re.escape(filename), line.strip())) is not None]
    require(len(matches) == 1, "Missing unique official Node ZIP SHA-256")
    return {
        "tool": "node", "group": "node", "version": stable,
        "url": "https://nodejs.org/dist/v" + stable + "/" + filename,
        "sha256": matches[0],
        "source_prefix": filename[:-4] + "/",
        "destination": "tool/node", "kind": "directory",
    }


def cli_candidate(tool: str, stable: str, release: dict) -> dict:
    if tool == "jq":
        url, digest = verified_asset(tool, stable, release, "jq-windows-amd64.exe")
        return {"tool": tool, "group": "cli", "version": stable,
                "url": url, "sha256": digest,
                "destination": "tool/bin/jq.exe", "kind": "executable"}
    filename = ("ripgrep-" + stable + "-x86_64-pc-windows-msvc.zip"
                if tool == "ripgrep" else
                "fd-v" + stable + "-x86_64-pc-windows-msvc.zip")
    url, digest = verified_asset(tool, stable, release, filename)
    return {"tool": tool, "group": "cli", "version": stable,
            "url": url, "sha256": digest,
            "source_prefix": filename[:-4] + "/",
            "source_file": "rg.exe" if tool == "ripgrep" else "fd.exe",
            "destination": "tool/bin/rg.exe" if tool == "ripgrep" else "tool/bin/fd.exe",
            "kind": "single"}


def discover() -> tuple[list[dict], dict[str, dict]]:
    installed = ledger_versions()
    candidates = []
    status = {}
    # A new Node major changes npm/ABI/launcher contracts; it is intentionally
    # not silently treated as a compatible patch/minor update.
    latest_node = official_node_latest(supported_major=version(installed["node"])[0])
    require(version(latest_node) >= version(installed["node"]),
            "Official Node latest release is older than installed version")
    status["node"] = {"installed": installed["node"], "latest": latest_node,
                      "policy": "same_verified_major_only"}
    if version(latest_node) > version(installed["node"]):
        candidates.append(node_candidate(latest_node))
    for tool in OFFICIAL:
        stable, release = github_release(tool)
        require(version(stable) >= version(installed[tool]),
                "Official " + tool + " stable release is older than installed")
        status[tool] = {"installed": installed[tool], "latest": stable}
        if version(stable) > version(installed[tool]):
            candidates.append(cli_candidate(tool, stable, release))
    require(len(candidates) == len(set(c["tool"] for c in candidates)),
            "Duplicate generated update candidate")
    return candidates, status


def owned_output() -> None:
    require(not OUT.parent.is_symlink(), "Linked auto-update scratch is forbidden")
    OUT.parent.mkdir(exist_ok=True)
    cursor = ROOT
    for part in OUT.relative_to(ROOT).parts[:-1]:
        cursor = cursor / part
        require(cursor.is_dir() and not cursor.is_symlink(),
                "Unsafe generated plan directory")
    if OUT.exists() or OUT.is_symlink():
        st = OUT.lstat()
        require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and
                not (getattr(st, "st_file_attributes", 0) & 0x400),
                "Unsafe existing generated plan")


def write_plan(candidates: list[dict]) -> None:
    require(candidates, "No upgrades needed; refusing an empty candidate branch")
    owned_output()
    plan = {
        "schema": 1, "platform": "win32-x64",
        "note": "Automatically selected latest stable official Node and CLI SHA-256 assets. "
                "Revalidate on the Windows verifier and independently in the byte-only writer.",
        "candidates": candidates,
    }
    OUT.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=("check", "plan"))
    args = ap.parse_args(argv)
    candidates, status = discover()
    changed = sorted(x["tool"] for x in candidates)
    print("AUTO_TOOL_UPSTREAM=" + json.dumps(status, sort_keys=True), flush=True)
    print("AUTO_TOOL_UPDATES=" + ",".join(changed) if changed else
          "AUTO_TOOL_UPDATES=NONE", flush=True)
    print("AUTO_TOOL_SCOPE=node(same-verified-major),ripgrep,fd,jq; "
          "other tool runtimes retain separate pinned full-mode verification", flush=True)
    if args.command == "plan":
        write_plan(candidates)
        print("AUTO_TOOL_PLAN=PASS;count=" + str(len(candidates)), flush=True)
    elif os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
            out.write("updates=" + ("true" if changed else "false") + "\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and args.command == "check":
        # Make it impossible to mistake an up-to-date CLI subset for a full
        # Python/npm/Playwright/browser upgrade or stable-major audit.
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("\n### Official Node / CLI auto-update scope\n\n")
            stream.write("Only Node.js within its verified major, ripgrep, fd, and jq are auto-managed. "
                         "Python, pip, npm, Corepack, Playwright, Chromium, 7-Zip, ADB, "
                         "and SSH remain under a separately reviewed full upgrade plan.\n\n")
            for name, row in sorted(status.items()):
                stream.write("- " + name + ": " + row["installed"] +
                             " → " + row["latest"] + "\n")
            stream.write("\nResult: " + ("Candidate(s): " + ", ".join(changed)
                                         if changed else "No supported updates needed") + "\n")
    print("AUTO_TOOL_RESULT=" + ("CANDIDATES_READY" if changed else
                                 "SUPPORTED_TOOLS_UP_TO_DATE"), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, TimeoutError, UnicodeError, KeyError,
            urllib.error.URLError, json.JSONDecodeError) as exc:
        print("AUTO_TOOL_FAILED=" + type(exc).__name__ + ": " + str(exc),
              file=sys.stderr, flush=True)
        raise SystemExit(2)
