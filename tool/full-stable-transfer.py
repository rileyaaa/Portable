#!/usr/bin/env python3
"""Verified candidate transport for manual, read-only -> write-token Windows Jobs.

The writer never executes downloaded Python/Node/7-Zip/Chromium binaries. It
accepts only same-run SHA-256 checked files plus an identical staged Git diff.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
MAX_FILES = 40000
MAX_FILE = 900 * 1024 * 1024
MAX_TOTAL = 2200 * 1024 * 1024
SINGLES = {
    "tool/installed-tools.json", "tool/工具更新说明.md",
    "tool/python-packages.in.txt", "tool/python-packages.lock.txt",
    "tool/python-ssh-packages.in.txt", "tool/python-ssh-packages.lock.txt",
    "tool/optional-python-manifest.json", "tool/python-build-manifest.json",
    "tool/full-stable-evidence.json", "tool/automation/browser-manifest.json",
    "tool/automation/dependency-manifest.json", "tool/automation/versions.json",
    "tool/bin/7z.exe", "tool/bin/7z.dll"
}
PREFIXES = (
    "tool/python/", "tool/node/node_modules/npm/",
    "tool/node/node_modules/corepack/", "tool/automation/playwright/",
    "tool/automation/browsers/"
)
BAD = re.compile(r'[<>:"\\|?*\x00-\x1f]')


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def checked_name(path: str) -> str:
    require(isinstance(path, str) and path.startswith("tool/") and
            not BAD.search(path) and "\\" not in path and
            all(x and x not in (".", "..") and not x.endswith((" ", "."))
                for x in path.split("/")),
            "Unsafe candidate path " + repr(path))
    require(path in SINGLES or any(path.startswith(p) for p in PREFIXES) or
            (path.startswith("tool/bin/") and
             path.endswith(".cmd") and path.count("/") == 2 and
             re.fullmatch(r"[A-Za-z0-9_.-]+", path.rsplit("/", 1)[-1])),
            "Unexpected tool change scope: " + path)
    require(not path.endswith((".pyc", ".pyo")) and
            "__pycache__/" not in path, "Generated Python cache must not be tracked")
    # The producer can stage on a different OS, but the writer checks out on
    # Windows. Reserved DOS device basenames can address device streams, and
    # an embedded .git component can change Git's meaning of a candidate tree.
    # Validate each component, not only the complete slash-delimited filename.
    for part in path.split("/"):
        require(part.casefold() != ".git" and
                re.fullmatch(
                    r"(?i)(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|CLOCK\$|"
                    r"COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?", part) is None,
                "Windows reserved candidate component: " + part)
    return path


def digest_file(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def checked_disk(path: Path, *, missing: bool = False) -> None:
    require(path.is_relative_to(ROOT), "Candidate escaped repository")
    cursor = ROOT
    for component in path.relative_to(ROOT).parts:
        cursor /= component
        if not cursor.exists() and not cursor.is_symlink():
            require(missing, "Missing candidate payload: " + str(cursor))
            continue
        st = cursor.lstat()
        require(not stat.S_ISLNK(st.st_mode) and
                not (getattr(st, "st_file_attributes", 0) & 0x400),
                "Refuse linked input/output: " + str(cursor))
        if stat.S_ISREG(st.st_mode):
            require(st.st_nlink == 1, "Refuse hard-linked payload")
        else:
            require(stat.S_ISDIR(st.st_mode), "Refuse special file")


def git(*args: str, binary: bool = False):
    result = subprocess.run(["git", *args], cwd=ROOT, check=True,
                            capture_output=True)
    return result.stdout if binary else result.stdout.decode("utf-8", "strict").strip()


def changes() -> list[dict]:
    raw = git("-c", "core.quotepath=false", "diff", "--cached",
              "--name-status", "--no-renames", "-z", binary=True)
    tokens = raw.split(b"\0")
    require(tokens and not tokens[-1], "Malformed git index diff")
    tokens.pop()
    require(len(tokens) % 2 == 0, "Unexpected git name-status token count")
    found = []
    for status, filename in zip(tokens[0::2], tokens[1::2]):
        require(status in (b"A", b"M", b"D"), "Unreviewed Git status")
        name = checked_name(filename.decode("utf-8", "strict"))
        full = ROOT / name
        if status != b"D":
            checked_disk(full)
            require(full.is_file() and full.stat().st_size <= MAX_FILE,
                    "Non-regular/oversized tool payload " + name)
            found.append({"status": status.decode("ascii"), "path": name,
                          "sha256": digest_file(full), "size": full.stat().st_size})
        else:
            found.append({"status": "D", "path": name})
    require(10 <= len(found) <= MAX_FILES, "Unexpected changed file count")
    require(len({x["path"].casefold() for x in found}) == len(found),
            "Case-colliding changed path")
    for required in ("tool/python/python315.dll", "tool/python/python315.zip",
                     "tool/node/node_modules/npm/package.json",
                     "tool/node/node_modules/corepack/package.json",
                     "tool/automation/versions.json", "tool/bin/7z.exe",
                     "tool/bin/7z.dll", "tool/installed-tools.json",
                     "tool/full-stable-evidence.json"):
        require(any(x["path"] == required and x["status"] != "D" for x in found),
                "Essential full refresh file not updated: " + required)
    return found


def indexed_base_paths() -> tuple[set[str], set[str]]:
    """Read Git's base index once without changing the working tree.

    Candidate A/M/D statuses must reflect the real Git index. Checking only
    the final Git diff is too late when an invalid status overwrites a file.
    """
    raw = git("-c", "core.quotepath=false", "ls-files",
              "-z", "--", "tool", binary=True)
    fields = raw.split(b"\0")
    require(bool(fields) and fields[-1] == b"", "Malformed tracked Git index")
    fields.pop()
    names = [field.decode("utf-8", "strict") for field in fields]
    folded = {name.casefold() for name in names}
    require(len(folded) == len(names), "Case-colliding tracked Git paths")
    return set(names), folded


def check_candidate_base_status(name: str, status: str, dest: Path,
                                tracked: set[str], folded: set[str]) -> None:
    """Refuse forged A/M/D statuses before writing or deleting anything."""
    if status == "A":
        require(name.casefold() not in folded,
                "Added candidate path already exists in Git base")
        try:
            dest.lstat()
        except FileNotFoundError:
            pass
        else:
            raise ValueError("Added candidate destination already exists")
    else:
        require(name in tracked and dest.is_file(),
                "Modified/deleted candidate must be an existing base file")


def diff_sha() -> str:
    value = git("-c", "core.quotepath=false", "diff", "--cached",
                "--binary", "--no-ext-diff", binary=True)
    require(value, "Expected a nonempty staged candidate diff")
    return hashlib.sha256(value).hexdigest()


def checked_candidate_archive(path: Path, *, output: bool = False) -> Path:
    """Accept verified candidate ZIPs only beneath this checkout's owned tmp.

    Neither pack nor apply may read/write a host path by selecting a different
    CLI --archive; reject linked parents, linked files and pre-existing output.
    """
    candidate = Path(path).absolute()
    scratch = ROOT / "tmp"
    require(candidate != scratch and candidate.is_relative_to(scratch),
            "Candidate archive must remain below package tmp")
    checked_disk(candidate.parent)
    require(candidate.parent.is_dir(), "Candidate archive parent is not a directory")
    if output:
        try:
            candidate.lstat()
        except FileNotFoundError:
            pass
        else:
            raise ValueError("Candidate archive output must be new and unlinked")
    else:
        checked_disk(candidate)
        require(candidate.is_file(), "Candidate archive input must be an ordinary file")
    return candidate


def pack(output: Path, expected_base: str) -> None:
    require(re.fullmatch(r"[0-9a-f]{40}", expected_base) is not None and
            git("rev-parse", "HEAD") == expected_base, "Unexpected source commit")
    output = checked_candidate_archive(output, output=True)
    payload = changes()
    manifest = {
        "schema": 1, "sourceCommit": expected_base,
        "diffSHA256": diff_sha(), "files": payload
    }
    encoded = (json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False) + "\n").encode("utf-8")
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=1, allowZip64=True) as archive:
        archive.writestr("manifest.json", encoded)
        for item in payload:
            if item["status"] != "D":
                archive.write(ROOT / item["path"], arcname="payload/" + item["path"])
    print("FULL_STABLE_ARTIFACT_SHA256=" + digest_file(output))
    print("FULL_STABLE_DIFF_SHA256=" + manifest["diffSHA256"])
    print("FULL_STABLE_CHANGED_FILES=" + str(len(payload)))


def apply(archive: Path, expected_sha: str, expected_diff: str,
          expected_base: str) -> None:
    require(re.fullmatch(r"[a-f0-9]{64}", expected_sha) is not None and
            re.fullmatch(r"[a-f0-9]{64}", expected_diff) is not None and
            re.fullmatch(r"[a-f0-9]{40}", expected_base) is not None,
            "Missing signed-run candidate identity")
    archive = checked_candidate_archive(archive)
    require(digest_file(archive) == expected_sha,
            "Candidate artifact differs from validated read-only Job")
    require(git("rev-parse", "HEAD") == expected_base,
            "Main moved since validated source; fail closed")
    require(not git("status", "--porcelain"), "Writer checkout must be unchanged")
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        require(entries and entries[0].filename == "manifest.json" and
                len(entries) <= MAX_FILES + 1, "Unexpected artifact structure")
        manifest = json.loads(source.read("manifest.json"))
        require(manifest.get("schema") == 1 and
                manifest.get("sourceCommit") == expected_base and
                manifest.get("diffSHA256") == expected_diff and
                isinstance(manifest.get("files"), list), "Candidate identity mismatch")
        planned = manifest["files"]
        require(10 <= len(planned) <= MAX_FILES and
                len({x["path"].casefold() for x in planned}) == len(planned),
                "Invalid candidate file count")
        expected_entries = {"manifest.json"} | {
            "payload/" + checked_name(x["path"]) for x in planned
            if x.get("status") in ("A", "M")}
        require(len(entries) == len(expected_entries) and
                {x.filename for x in entries} == expected_entries and
                all(not x.is_dir() for x in entries), "Unexpected archive file scope")
        # Phase 1: validate *all* payload digests, Git base statuses and
        # deletions without touching any tracked working-tree files.
        tracked, tracked_folded = indexed_base_paths()
        verified_total = 0
        for item in planned:
            name = checked_name(item["path"])
            status = item.get("status")
            require(status in ("A", "M", "D"), "Unknown candidate file status")
            dest = ROOT / name
            checked_disk(dest, missing=True)
            check_candidate_base_status(name, status, dest, tracked, tracked_folded)
            if status == "D":
                require(dest.is_file(), "Deleted path missing from base")
                continue
            require(type(item.get("size")) is int and
                    0 <= item["size"] <= MAX_FILE and
                    re.fullmatch(r"[a-f0-9]{64}", item.get("sha256", "")),
                    "Invalid payload digest/length")
            verified_total += item["size"]
            require(verified_total <= MAX_TOTAL, "Candidate archive exceeds bounded scope")
            member = source.getinfo("payload/" + name)
            require(member.file_size == item["size"] and
                    stat.S_IFMT(member.external_attr >> 16) != stat.S_IFLNK,
                    "Payload size/link status mismatch")
            verified_sha = hashlib.sha256()
            with source.open(member) as verified_stream:
                while chunk := verified_stream.read(1024 * 1024):
                    verified_sha.update(chunk)
            require(verified_sha.hexdigest() == item["sha256"],
                    "Payload failed pre-apply SHA-256 verification: " + name)

        # Phase 2a: stage ALL replacements in the package's ignored tmp
        # before moving a single base file. The archive is read and hashed
        # again, so a late decompression/disk failure leaves the base intact.
        scratch = ROOT / "tmp"
        checked_disk(scratch)
        require(scratch.is_dir(), "Owned candidate transaction tmp is missing")
        # A failed rollback intentionally preserves original bytes in tmp.
        # Never start a new write while that unresolved journal still exists.
        require(not any(scratch.glob("full-writer-journal-*")),
                "Unresolved full-writer transaction: recover preserved originals first")
        transaction = Path(tempfile.mkdtemp(prefix="full-writer-journal-", dir=scratch))
        preserve_transaction = False
        try:
            checked_disk(transaction)
            staged: dict[str, Path] = {}
            total = 0
            for index, item in enumerate(planned):
                if item["status"] == "D":
                    continue
                name = item["path"]
                source_info = source.getinfo("payload/" + name)
                total += item["size"]
                require(total <= MAX_TOTAL, "Candidate archive exceeds bounded scope")
                pending = transaction / ("payload-" + str(index))
                check = hashlib.sha256()
                with pending.open("xb") as output, source.open(source_info) as payload:
                    while block := payload.read(1024 * 1024):
                        check.update(block)
                        output.write(block)
                require(check.hexdigest() == item["sha256"] and
                        pending.stat().st_size == item["size"],
                        "Prepared candidate payload changed since validation")
                staged[name] = pending

            # Store exact names for manual recovery after process death or a
            # failed rollback. The journal lives in ignored package tmp and is
            # removed after success or a complete rollback.
            with (transaction / "recovery-map.json").open("x", encoding="utf-8") as recovery:
                json.dump({"sourceCommit": expected_base, "files": [
                    {"index": i, "path": item["path"], "status": item["status"]}
                    for i, item in enumerate(planned)
                ]}, recovery, ensure_ascii=False, sort_keys=True)
                recovery.write("\n")
                recovery.flush()
                # Fail before any original-file rename if the recovery map
                # cannot be flushed. A process crash is still not an atomic
                # multi-file transaction or a power-loss-safe journal.
                os.fsync(recovery.fileno())

            # Phase 2b: original file bytes are moved to same-volume private
            # backup names before replacing/deleting them. A failed later
            # replace, staged Git comparison or LFS pointer check rolls back
            # earlier changes. This is not power-loss/kill-safe or TOCTOU-free.
            journal: list[tuple[str, Path, Path | None]] = []
            created_dirs: set[Path] = set()
            try:
                for index, item in enumerate(planned):
                    name = checked_name(item["path"])
                    status = item["status"]
                    dest = ROOT / name
                    checked_disk(dest, missing=True)
                    check_candidate_base_status(name, status, dest,
                                                tracked, tracked_folded)
                    if status != "D":
                        checked_disk(dest.parent, missing=True)
                        missing_dirs = []
                        cursor = dest.parent
                        while not cursor.exists():
                            missing_dirs.append(cursor)
                            cursor = cursor.parent
                        for directory in reversed(missing_dirs):
                            checked_disk(directory, missing=True)
                            directory.mkdir()
                            created_dirs.add(directory)
                        checked_disk(dest.parent)

                    if status != "A":
                        # Moving the original (rather than copying it) retains
                        # exact binary bytes and is an atomic rename on the
                        # normal package volume. Keep it until all Git gates
                        # have succeeded.
                        saved = transaction / ("original-" + str(index))
                        os.replace(dest, saved)
                        journal.append((status, dest, saved))
                    else:
                        # Record a potential addition BEFORE replace: an
                        # exception immediately after the rename must also
                        # remove its untracked result during rollback.
                        journal.append((status, dest, None))
                    if status != "D":
                        os.replace(staged[name], dest)

                git("add", "-A", "--", "tool")
                actual = changes()
                require(actual == planned,
                        "Candidate file identities differ from read-only Job")
                require(diff_sha() == expected_diff,
                        "Trusted writer Git patch differs")
                # Existing .gitattributes creates Git LFS pointer objects for
                # Chromium binaries; verify those before discarding backups.
                for item in planned:
                    name = item["path"]
                    if name.startswith("tool/automation/browsers/") and item["status"] != "D":
                        blob = git("show", ":" + name)
                        match = re.search(r"(?m)^oid sha256:([0-9a-f]{64})$", blob)
                        require("version https://git-lfs.github.com/spec/v1" in blob and
                                match and match.group(1) == item["sha256"],
                                "Chromium LFS pointer missing or mismatched")
            except BaseException as failure:
                errors: list[str] = []
                for status, dest, original in reversed(journal):
                    try:
                        checked_disk(dest.parent)
                        if original is not None:
                            checked_disk(original)
                            os.replace(original, dest)
                        else:
                            # A path was absent in the clean checkout. Never
                            # follow a link or delete unexpected host data.
                            checked_disk(dest, missing=True)
                            if dest.exists():
                                dest.unlink()
                    except BaseException as rollback_error:
                        errors.append(str(dest) + ": " + str(rollback_error))
                for directory in sorted(created_dirs, key=lambda p: len(p.parts),
                                        reverse=True):
                    try:
                        checked_disk(directory)
                        directory.rmdir()  # Only our own empty new directories
                    except BaseException as rollback_error:
                        errors.append(str(directory) + ": " + str(rollback_error))
                try:
                    # git add may have staged part of the tree before failing;
                    # restore the clean base index, not the candidate index.
                    git("reset", "--quiet", "HEAD", "--", "tool")
                except BaseException as rollback_error:
                    errors.append("Git index: " + str(rollback_error))
                if errors:
                    # On a failed restore, NEVER destroy the only surviving
                    # originals in the transaction journal. Keep an auditable
                    # path in tmp so a maintainer can recover them manually.
                    preserve_transaction = True
                    raise RuntimeError(
                        "Candidate apply failed and rollback was incomplete; " +
                        "originals preserved at " + str(transaction) + ": " +
                        "; ".join(errors)) from failure
                raise
        finally:
            if not preserve_transaction:
                checked_disk(transaction)
                shutil.rmtree(transaction)
    print("FULL_STABLE_WRITER_MATCH=PASS")
    print("FULL_STABLE_DIFF_SHA256=" + expected_diff)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("pack")
    p.add_argument("--archive", required=True, type=Path)
    p.add_argument("--base", required=True)
    a = sub.add_parser("apply")
    a.add_argument("--archive", required=True, type=Path)
    a.add_argument("--base", required=True)
    a.add_argument("--sha256", required=True)
    a.add_argument("--diff", required=True)
    args = parser.parse_args()
    if args.command == "pack":
        pack(args.archive, args.base)
    else:
        apply(args.archive, args.sha256, args.diff, args.base)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, RuntimeError, zipfile.BadZipFile,
            subprocess.CalledProcessError) as error:
        raise SystemExit("FULL_STABLE_TRANSFER_FAILED: " + str(error))
