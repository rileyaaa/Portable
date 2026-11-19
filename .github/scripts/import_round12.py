#!/usr/bin/env python3
"""One-time, fail-closed import of the audited round-12 Git bundle and LFS payloads.

Runs only on an authenticated GitHub Actions Windows runner. The transfer branch
contains the exact original Git bundle (split into Git blobs) and an independent
9066-file SHA-256 inventory. New LFS objects are obtained from the pinned
upstream Codex and Node releases, not from a personal workstation or user data.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = "7fa8e0712ef4b65bc46ce3ed6eafe9636417a04a"
SOURCE_BRANCH = "automation/r12-source-transfer"
TRANSFER_COMMIT = "bf4471039d5a56f9a8e4d5d5c4453aa09feec753"
BUNDLE_SHA = "c25f543c8784c3213addd48a7e3d37a74c82d3124194409529a5845b2a82956b"
REFERENCE_SHA = "de4b48e7646943d981a768aa037df2a9ab82b13dce1f146cf3a8165599b33b8b"
GITHUB_REF = "refs/heads/main"
ASSETS = {
    "codex.exe": "bin/codex.exe",
    "codex-code-mode-host.exe": "bin/codex-code-mode-host.exe",
    "codex-command-runner.exe": "codex-resources/codex-command-runner.exe",
    "codex-windows-sandbox-setup.exe": "codex-resources/codex-windows-sandbox-setup.exe",
    "codex-path/rg.exe": "codex-path/rg.exe",
}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def run(*args: str, env=None, capture=False, check=True, cwd=None):
    command = [str(x) for x in args]
    print("CMD:", " ".join(command[:6]), flush=True)
    result = subprocess.run(command, cwd=cwd or ROOT, env=env, check=False,
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None)
    if check and result.returncode != 0:
        detail = (result.stderr or b"").decode(errors="replace")[-1500:]
        raise RuntimeError(f"Command exited {result.returncode}: {command[:5]} {detail}")
    return result.stdout if capture else result.returncode


def digest(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def git_show(rev: str, path: str, dest: Path):
    with dest.open("wb") as f:
        process = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT,
                                 stdout=f, stderr=subprocess.PIPE)
    require(process.returncode == 0,
            f"Missing stage object: {path} {process.stderr.decode(errors='replace')[:200]}")


def load_transfer(temp: Path):
    ref = "refs/remotes/origin/" + SOURCE_BRANCH
    run("git", "fetch", "--no-tags", "origin", f"refs/heads/{SOURCE_BRANCH}:{ref}")
    commit = run("git", "rev-parse", ref, capture=True).decode().strip()
    require(commit == TRANSFER_COMMIT, "Unexpected transfer branch commit")
    manifest_path = temp / "transfer.json"
    prefix = ".github/release-transfer/round12/"
    git_show(commit, prefix + "manifest.json", manifest_path)
    transfer = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(transfer["source_commit"] == CANDIDATE and transfer["bundle_sha256"] == BUNDLE_SHA,
            "Transfer manifest identity changed")
    require(len(transfer["parts"]) == 9 and transfer["bundle_bytes"] == 17095128,
            "Unexpected source bundle chunk inventory")
    bundle = temp / "round12-candidate.bundle"
    with bundle.open("wb") as out:
        for part in transfer["parts"]:
            name = part["name"]
            require(re.fullmatch(r"part0[1-9]\.bin", name) is not None,
                    "Unapproved bundle chunk path")
            piece = temp / name
            git_show(commit, prefix + name, piece)
            require(piece.stat().st_size == part["bytes"] and
                    digest(piece) == part["sha256"], "Bundle transfer part damaged: " + name)
            with piece.open("rb") as source:
                shutil.copyfileobj(source, out, length=1024 * 1024)
    require(bundle.stat().st_size == transfer["bundle_bytes"] and digest(bundle) == BUNDLE_SHA,
            "Reassembled source bundle does not match independent SHA-256")
    reference_gz = temp / "release-manifest.json.gz"
    git_show(commit, prefix + "release-manifest.json.gz", reference_gz)
    require(digest(reference_gz) == REFERENCE_SHA, "Original file inventory archive changed")
    reference = json.loads(gzip.decompress(reference_gz.read_bytes()))
    require(reference["source_commit"] == CANDIDATE and reference["file_count"] == 9066 and
            len(reference["files"]) == 9066 and
            reference["target"] == "x86_64-pc-windows-msvc", "Reference file identity invalid")
    print("SOURCE_BUNDLE_TRANSFER=PASS sha256=" + BUNDLE_SHA, flush=True)
    run("git", "bundle", "verify", str(bundle))
    run("git", "fetch", "--no-tags", str(bundle), "HEAD")
    local = run("git", "rev-parse", "FETCH_HEAD", capture=True).decode().strip()
    require(local == CANDIDATE, "Git bundle refers to the wrong candidate")
    return reference


def expected(reference, path):
    record = reference["files"].get(path)
    require(record and re.fullmatch(r"[0-9a-f]{64}", record["sha256"]),
            "Missing expected file identity: " + path)
    return record


def verify_one(reference, rel):
    record = expected(reference, rel)
    path = ROOT / rel
    require(path.is_file() and not path.is_symlink() and
            path.stat().st_size == record["size"] and digest(path) == record["sha256"],
            "Candidate payload differs: " + rel)


def verify_all(reference):
    errors = []
    for i, (name, record) in enumerate(reference["files"].items(), 1):
        path = ROOT / name
        try:
            require(path.is_file() and not path.is_symlink(), "Not a regular file")
            require(path.stat().st_size == record["size"] and
                    digest(path) == record["sha256"], "Digest mismatch")
        except Exception as exc:
            if len(errors) < 20:
                errors.append(f"{name}: {exc}")
        if i % 1500 == 0:
            print(f"VERIFIED_FILES={i}/9066", flush=True)
    require(not errors, "Candidate files differ from verified round-12 ZIP: " + repr(errors))
    print("CUSTOMER_FILES=PASS count=9066", flush=True)


def safe_download(url: str, dest: Path, limit: int):
    require(url.startswith("https://nodejs.org/dist/v26.13.1/") or
            url.startswith("https://nodejs.org/download/release/v26.13.1/"),
            "Only fixed official Node download URLs allowed")
    req = urllib.request.Request(url, headers={"User-Agent": "Codex-Portable-verified-release"})
    with urllib.request.urlopen(req, timeout=180) as response:
        require(response.status == 200 and response.url == url,
                "Unapproved Node download redirect")
        with dest.open("xb") as out:
            n = 0
            while True:
                part = response.read(1024 * 1024)
                if not part:
                    break
                n += len(part)
                require(n < limit, "Node download exceeds bound")
                out.write(part)


def store_lfs(reference, rel, source: Path):
    verify_one(reference, rel)
    # Worktree bytes must be exactly what the independent release manifest records.
    pointer = run("git", "show", f"{CANDIDATE}:{rel}", capture=True)
    require(pointer.startswith(b"version https://git-lfs.github.com/spec/v1\n"),
            "Expected Git LFS pointer is missing: " + rel)
    with source.open("rb") as f:
        process = subprocess.run(["git", "lfs", "clean"], cwd=ROOT,
                                 stdin=f, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    require(process.returncode == 0 and process.stdout == pointer,
            "Official bytes do not match the committed Git LFS OID: " + rel)
    print("NEW_LFS=PASS " + rel, flush=True)


def download_codex(reference, runtime, temp):
    version = runtime["version"]
    require(version == "0.170.0" and runtime["target"] == "x86_64-pc-windows-msvc",
            "Unexpected Codex runtime")
    sha = runtime["archive_sha256"]
    require(re.fullmatch(r"[0-9a-f]{64}", sha) is not None,
            "Missing upstream archive SHA-256")
    archive_name = "codex-package-x86_64-pc-windows-msvc.tar.gz"
    upstream = temp / archive_name
    run("gh", "release", "download", "rust-v0.170.0", "--repo", "openai/codex",
        "--pattern", archive_name, "--dir", str(temp))
    require(upstream.is_file() and digest(upstream) == sha,
            "Official Codex 0.170.0 release archive SHA-256 differs from pinned source")
    with tarfile.open(upstream, "r:gz") as tar:
        members = {m.name.removeprefix("./"):m for m in tar.getmembers()
                   if m.isfile()}
        for rel, upstream_name in ASSETS.items():
            record = expected(reference, rel)
            require(upstream_name in members, "Official Codex package member absent: " + upstream_name)
            member = members[upstream_name]
            require(member.size == record["size"], "Official Codex member size mismatch: " + rel)
            src = tar.extractfile(member)
            require(src is not None, "Cannot extract official member: " + rel)
            target = ROOT / rel
            with target.open("wb") as out:
                shutil.copyfileobj(src, out, length=1024 * 1024)
            verify_one(reference, rel)
            if tar.name:
                print("OFFICIAL_CODEX_MEMBER=PASS " + rel, flush=True)
            if run("git", "check-attr", "filter", "--", rel, capture=True).decode().strip().endswith(": lfs"):
                store_lfs(reference, rel, target)
    print("OFFICIAL_CODEX_ARCHIVE=PASS sha256=" + sha, flush=True)


def download_node(reference, temp):
    name = "node-v26.13.1-win-x64.zip"
    zip_path = temp / name
    sums_path = temp / "SHASUMS256.txt"
    root = "https://nodejs.org/dist/v26.13.1/"
    safe_download(root + "SHASUMS256.txt", sums_path, 1_000_000)
    sums = sums_path.read_text(encoding="utf-8").splitlines()
    candidates = [line.split() for line in sums if line.strip().endswith(" " + name)]
    require(len(candidates) == 1 and len(candidates[0]) == 2 and
            re.fullmatch(r"[0-9a-f]{64}", candidates[0][0]),
            "Official Node SHA256SUMS lacks expected ZIP")
    safe_download(root + name, zip_path, 120_000_000)
    require(digest(zip_path) == candidates[0][0],
            "Official Node ZIP mismatches official SHA256SUMS")
    with zipfile.ZipFile(zip_path) as z:
        member = "node-v26.13.1-win-x64/node.exe"
        require(z.testzip() is None and member in z.namelist(),
                "Official Node ZIP is corrupt or lacks node.exe")
        with z.open(member) as source, (ROOT / "tool/node/node.exe").open("wb") as out:
            shutil.copyfileobj(source, out, length=1024 * 1024)
    verify_one(reference, "tool/node/node.exe")
    store_lfs(reference, "tool/node/node.exe", ROOT / "tool/node/node.exe")
    print("OFFICIAL_NODE_ZIP=PASS sha256=" + candidates[0][0], flush=True)


def main():
    require(os.name == "nt" and os.environ.get("GITHUB_ACTIONS") == "true",
            "Only native GitHub Actions Windows runner may import a release candidate")
    require(os.environ.get("GITHUB_REF") == GITHUB_REF,
            "Import only from the protected main source context")
    initial = os.environ.get("GITHUB_SHA", "")
    require(re.fullmatch(r"[0-9a-f]{40}", initial) is not None,
            "Missing original GitHub source SHA")
    require(run("git", "rev-parse", "HEAD", capture=True).decode().strip() == initial,
            "Source checkout differs from the triggering commit")
    require(run("git", "status", "--porcelain", capture=True).strip() == b"",
            "Import requires a clean source checkout")
    # Git for Windows often defaults to core.autocrlf=true. The verified ZIP
    # hashes the original Git blob bytes, not a CRLF-transcoded checkout.
    # Keep exact tracked bytes, then independently re-check all 9066 hashes.
    run("git", "config", "--local", "core.autocrlf", "false")
    with tempfile.TemporaryDirectory(prefix="codex-r12-", dir=os.environ.get("RUNNER_TEMP")) as scratch:
        temp = Path(scratch)
        reference = load_transfer(temp)
        runtime = json.loads(run("git", "show", f"{CANDIDATE}:tool/runtime-manifest.json",
                                 capture=True).decode("utf-8"))
        # Fetch already-published Chromium and search-tool objects from the
        # old main, without re-downloading the old Codex/Node LFS payloads.
        run("git", "lfs", "fetch", "--include=tool/automation/browsers/**,codex-path/rg.exe",
            "--exclude=", "origin", initial)
        isolated = dict(os.environ, GIT_LFS_SKIP_SMUDGE="1")
        run("git", "checkout", "--detach", CANDIDATE, env=isolated)
        # Force materialization of Git blobs as-is. Existing unchanged files
        # can otherwise retain CRLF left by the initial Windows checkout.
        # Keep LFS smudge disabled until verified LFS objects are hydrated.
        run("git", "checkout-index", "--all", "--force", env=isolated)
        run("git", "lfs", "checkout")
        download_codex(reference, runtime, temp)
        download_node(reference, temp)
        run("git", "lfs", "checkout")
        verify_all(reference)
        run("git", "lfs", "fsck")
        # Merge candidate with the three allowlisted release-automation changes.
        run("git", "checkout", "-B", "automation/import-r12", initial, env=isolated)
        run("git", "merge", "--no-ff", "--no-commit", CANDIDATE, env=isolated)
        # Check the final merged source with the same literal-byte policy.
        run("git", "checkout-index", "--all", "--force", env=isolated)
        run("git", "lfs", "checkout")
        verify_all(reference)
        run("git", "config", "user.name", "github-actions[bot]")
        run("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
        run("git", "commit", "-m", "release: integrate audited 0.170.0 portable.2 source and pinned LFS")
        latest = run("git", "rev-parse", "HEAD", capture=True).decode().strip()
        run("git", "lfs", "fsck")
        # Ensure final manifest and all source payload files match this commit.
        run("python", "-B", "tool/package-release.py", "--check")
        # Confirm no concurrent main update before either remote write.
        remote = run("git", "ls-remote", "origin", "refs/heads/main", capture=True).decode().strip()
        require(remote.split()[0] == initial,
                "Main changed during import. No upload or push permitted")
        run("git", "lfs", "push", "origin", "HEAD")
        run("git", "push", "origin", "HEAD:refs/heads/main")
        after = run("git", "ls-remote", "origin", "refs/heads/main", capture=True).decode().strip()
        require(after.split()[0] == latest, "Remote main did not reach verified source commit")
        print("VERIFIED_REMOTE_MAIN=" + latest, flush=True)
        # GITHUB_TOKEN pushes do not trigger push workflows. workflow_dispatch
        # is the explicitly supported authenticated Actions continuation.
        run("gh", "workflow", "run", "release.yml", "--repo", os.environ["GITHUB_REPOSITORY"],
            "--ref", "main")
        print("RELEASE_DISPATCH=PASS", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ROUND12_IMPORT_BLOCKED: " + str(exc), file=sys.stderr, flush=True)
        raise SystemExit(1)
