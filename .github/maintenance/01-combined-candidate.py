#!/usr/bin/env python3
"""Hash the exact staged combined Codex + Tool candidate, rooted at a trusted source SHA.

The first-party runtime and Tool allowlists must independently pass *before*
calling this helper. This routine never downloads, runs vendor code, commits
or pushes. It sees runtime changes already checkpointed locally plus staged
Tool changes without requiring a dirty working tree.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys

SHA40 = re.compile(r"[a-f0-9]{40}")
SHA64 = re.compile(r"[a-f0-9]{64}")


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], stderr=subprocess.PIPE
    )


def candidate_digest(repo: Path, base: str) -> tuple[str, list[str]]:
    if SHA40.fullmatch(base) is None:
        raise ValueError("Expected a pinned, full 40-character source commit SHA")
    try:
        actual_base = git(repo, "rev-parse", "--verify", base + "^{commit}").decode().strip()
    except subprocess.CalledProcessError as exc:
        raise ValueError("Pinned source commit does not exist") from exc
    if actual_base != base:
        raise ValueError("Source SHA did not resolve to the exact pinned commit")
    if subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", base, "HEAD"],
        check=False, capture_output=True, timeout=30
    ).returncode != 0:
        raise ValueError("Pinned source is not an ancestor of the local candidate")
    if git(repo, "diff", "--name-only", "-z"):
        raise ValueError("Unstaged tracked edits are not part of the verified candidate")
    names = [path.decode("utf-8") for path in
             git(repo, "-c", "core.quotepath=false", "diff", "--cached",
                 "--name-only", "-z", base).split(b"\0") if path]
    if not names or len(names) != len(set(names)):
        raise ValueError("Empty or duplicate staged combined candidate")
    if any(not name or name.startswith("/") or ".." in name.split("/")
           for name in names):
        raise ValueError("Unexpected staged path")
    patch = git(repo, "-c", "core.quotepath=false", "diff", "--cached",
                "--binary", "--no-ext-diff", base)
    if not patch:
        raise ValueError("Candidate diff is unexpectedly empty")
    return hashlib.sha256(patch).hexdigest(), names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--expected")
    args = parser.parse_args(argv)
    repo = args.repo.resolve(strict=True)
    if not (repo / ".git").exists():
        raise ValueError("A complete checked-out Git repository is required")
    value, names = candidate_digest(repo, args.base)
    if args.expected is not None:
        if SHA64.fullmatch(args.expected) is None or args.expected != value:
            raise ValueError("Writer candidate differs from Windows-verified combined diff")
    print("COMBINED_CANDIDATE_SHA256=" + value)
    print("COMBINED_CANDIDATE_FILES=" + str(len(names)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError, ValueError) as err:
        print("COMBINED_CANDIDATE_REJECTED=" + str(err), file=sys.stderr)
        raise SystemExit(2)
