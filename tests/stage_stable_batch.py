"""Batch independent, fixed stable-wheel candidates in a disposable Windows CI checkout.

Failures stay local; restore only the failing group's audited paths. No consumer
installation, host fallback, resolver updates, release, or reference writes.
"""
import importlib.metadata as md
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

ROOT = Path.cwd()
PY = ROOT / "tool/python/python.exe"
SITE = "tool/python/Lib/site-packages/"
SHARED = {"tool/python-packages.in.txt", "tool/python-packages.lock.txt",
          "DEVELOPMENT.md", "tool/\u5de5\u5177\u66f4\u65b0\u8bf4\u660e.md"}
GROUPS = [
    ("urllib3", "tests/stage_http_stable_refresh.py", ["urllib3"], {"urllib3": ("2.7.0","2.8.0")}),
    ("anyio", "tests/stage_http_stable_refresh.py", ["anyio"], {"anyio": ("4.13.0","4.16.0")}),
    ("tzdata", "tests/stage_office_data_stable_refresh.py", ["tzdata"], {"tzdata": ("2026.2","2026.6")}),
]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def names(*args):
    return set(git(*args).decode("utf-8").split("\0")) - {""}


def tracked_changes():
    return names("diff", "HEAD", "--no-renames", "--name-only", "-z")


def untracked():
    return names("ls-files", "--others", "--exclude-standard", "-z")


def clean():
    assert not git("status", "--porcelain=v1", "--untracked-files=all"), "dirty CI checkout"


def run(*args):
    result = subprocess.run([str(a) for a in args], cwd=ROOT, capture_output=True)
    print(result.stdout.decode("utf-8", "backslashreplace"), end="", flush=True)
    print(result.stderr.decode("utf-8", "backslashreplace"), end="", flush=True)
    return result


def allowed(paths, pins):
    roots = [SITE + n + "/" for n in pins]
    roots += [SITE + n + "-" + v + ".dist-info/" for n, pair in pins.items() for v in pair]
    exact = SHARED | ({SITE + "bin/vba_extract.py"} if "xlsxwriter" in pins else set())
    assert all(p in exact or any(p.startswith(r) for r in roots) for p in paths), ("unexpected candidate paths", sorted(paths))


def validate():
    for args in [
        ["validate", "--requirements", "tool/python-packages.in.txt", "--lock", "tool/python-packages.lock.txt"],
        ["validate-runtime", "--requirements", "tool/python-packages.in.txt"],
    ]:
        assert run(PY, "-B", "tool/python-lock.py", *args).returncode == 0


def restore(pins):
    tracked, extra = tracked_changes(), untracked()
    allowed(tracked | extra, pins)
    if tracked:
        # Batch paths to fit Windows CreateProcess limits. Restore only candidate paths.
        paths = sorted(tracked)
        for i in range(0, len(paths), 60):
            git("restore", "--source=HEAD", "--staged", "--worktree", "--", *paths[i:i+60])
    for p in sorted(untracked()):
        allowed({p}, pins)
        target = ROOT / p
        for a in (target, *target.parents):
            s = a.lstat()
            assert not stat.S_ISLNK(s.st_mode) and not getattr(s, "st_file_attributes", 0) & 0x400, p
        assert target.is_file() and target.stat().st_nlink == 1, p
        target.unlink()
    clean()
    validate()


def append_record(path, content):
    raw = path.read_bytes()
    nl = b"\r\n" if b"\r\n" in raw else b"\n"
    if not raw.endswith(nl):
        raw += nl
    path.write_bytes(raw + nl + content.encode("utf-8").replace(b"\n", nl) + nl)


def commit(message, paths):
    paths = sorted(paths)
    for i in range(0, len(paths), 60):
        git("add", "-A", "--", *paths[i:i+60])
    assert names("diff", "--cached", "--no-renames", "--name-only", "-z") == set(paths)
    git("-c","user.name=github-actions[bot]","-c","user.email=41898282+github-actions[bot]@users.noreply.github.com","commit","-m",message)
    clean()
    print("LOCAL_CANDIDATE="+git("rev-parse","HEAD").decode().strip(), flush=True)


def versions():
    return {d.metadata["Name"].lower().replace("_","-"): d.version
            for d in md.distributions(path=[str(ROOT / SITE)])}


def main():
    assert os.name == "nt" and sys.version_info[:3] == (3,14,10)
    assert Path(sys.executable).resolve() == PY
    assert sys.flags.isolated and sys.flags.ignore_environment and sys.flags.safe_path
    assert os.environ.get("GITHUB_ACTIONS") == "true"
    assert os.environ.get("GITHUB_REPOSITORY") == "rileyaaa/Portable"
    assert os.environ.get("GITHUB_REF") == "refs/heads/dev/stable-tool-refresh"
    clean()
    validate()
    results = {}
    for label, script, args, pins in GROUPS:
        clean()
        before = versions()
        assert len(before) == 49 and all(before[n] == old for n,(old,new) in pins.items())
        print("BEGIN_INDEPENDENT_GROUP="+label, flush=True)
        r = run(PY, "-B", script, *args)
        if r.returncode:
            restore(pins)
            assert versions() == before
            results[label] = "RETAINED: stage failed; exact reason in preceding traceback"
            print("GROUP_RETAINED="+label, flush=True)
            continue
        try:
            validate()
            assert versions() == before | {n:new for n,(old,new) in pins.items()}
            changed = tracked_changes() | untracked()
            allowed(changed, pins)
            assert {"tool/python-packages.in.txt","tool/python-packages.lock.txt"} <= changed
        except (AssertionError, subprocess.CalledProcessError):
            restore(pins)
            assert versions() == before
            results[label] = "RETAINED: lock, closure, or scope validation failed"
            print("GROUP_RETAINED="+label, flush=True)
            continue
        runurl = "https://github.com/rileyaaa/Portable/actions/runs/" + os.environ["GITHUB_RUN_ID"]
        summary = ", ".join(f"{n} {old} -> {new}" for n,(old,new) in pins.items())
        note = ("## 2026-11-25: " + summary +
                "\n\nOfficial fixed wheel hashes, RECORD, prior Git payload, licenses, dependency closure and actual old/new Windows consumer checks passed. "
                "No extra distribution or feature enabled. AnyIO's exact added dependency is already satisfied by the fixed typing_extensions 4.16.0. "
                "Full native regression required before push. No real accounts, devices, remote SSH, Office rendering or recalculation tested. Run: " + runurl)
        append_record(ROOT / "DEVELOPMENT.md", note)
        append_record(ROOT / "tool/\u5de5\u5177\u66f4\u65b0\u8bf4\u660e.md", summary + " (Windows validation: " + runurl + ")")
        changed = tracked_changes() | untracked()
        allowed(changed, pins)
        commit("Refresh verified stable " + label + " payload", changed)
        results[label] = "PASSED stage and lock/closure checks; awaiting full native gate"
        print("GROUP_STAGE_PASS="+label, flush=True)
    clean()
    print("INDEPENDENT_GROUP_RESULTS="+json.dumps(results,ensure_ascii=True),flush=True)


if __name__ == "__main__":
    for stream in (sys.stdout,sys.stderr):
        stream.reconfigure(encoding="utf-8",errors="backslashreplace")
    main()
