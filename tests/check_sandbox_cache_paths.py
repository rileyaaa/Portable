"""Exact candidate, one narrow native Windows batch, verified system seed only."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import traceback
import uuid

ROOT=Path(__file__).absolute().parents[1]
REFERENCE=json.loads((ROOT/"tests/system_skills_0172_upstream.json").read_bytes())
EXPECTED=REFERENCE["files"]
PREFIX="home/skills/.system/"
MARKER=".codex-system-skills.marker"
SENTINEL=b"synthetic audit sentinel"
assert REFERENCE["commit"]=="3d86e43b075adeba2193ec5c22ac92f55afd82e6"
assert REFERENCE["tag"]=="rust-v0.172.0" and len(EXPECTED)==REFERENCE["source_file_count"]==52
assert all(re.fullmatch("[0-9a-f]{40}",r["git_blob_sha1"]) for r in EXPECTED.values())


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
course=load("cache_path_course_verifier",ROOT/"tests/check_course_assistant.py")
audit=load("cache_path_audit_peer",ROOT/"tests/audit_release_zip.py")
audit.core=load("cache_path_audit_core",ROOT/"tests/check_codex_tool_discovery.py")
audit.m=audit.core.m
audit.core.MAX_CELL_WAITS=20
PHASE=sys.argv[1]
INFO=Path(sys.argv[2]).absolute()
REPORT=Path(sys.argv[3]).absolute()
STAGE=Path(sys.argv[4]).absolute()
ROWS=[]
META={"prior_run":"45744922536","prior_record":"a96e0c70494de030da297f574e3d048977c8d1f3",
    "source_commit":os.environ["GITHUB_SHA"],"phase":PHASE,"completed":False,
    "runner_image":os.environ.get("ImageOS"),"runner_image_version":os.environ.get("ImageVersion"),
    "upstream_system_source":REFERENCE["commit"],"chinese_ocr":"BLOCKED_PREVIOUS_BOTH_RUNNERS_NO_NEW_AUTHORIZED_ENVIRONMENT"}


def save():
    REPORT.write_text(json.dumps(dict(metadata=META,rows=ROWS),ensure_ascii=True,indent=2)+"\n",encoding="utf-8")


def row(mode,item,status,detail=""):
    r=dict(mode=mode,item=item,status=status,detail=detail)
    ROWS.append(r);save();print("CACHE_PATH_ROW="+json.dumps(r,ensure_ascii=True),flush=True)


def git(*args):
    return subprocess.check_output(["git","-C",str(ROOT),*args])


def blob_id(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode("ascii")+b"\0"+data,usedforsecurity=False).hexdigest()


def checked_tree(root):
    course.ancestors(root);course.plain(root,True)
    names={}
    for p in root.rglob("*"):
        if p.is_dir():course.plain(p,True);continue
        course.ancestors(p.parent);course.plain(p)
        n=p.relative_to(root).as_posix()
        assert n not in names
        names[n]=p
    assert len({n.casefold() for n in names})==len(names)
    return names


def verify_source_system(system):
    """All fixed source blobs + actual native marker, no whole-directory skip."""
    actual=checked_tree(system)
    missing=set(EXPECTED)|{MARKER};missing-=set(actual)
    extra=set(actual)-(set(EXPECTED)|{MARKER})
    failures=[];details={}
    for name,record in EXPECTED.items():
        if name not in actual:continue
        data=actual[name].read_bytes()
        match="none"
        if len(data)==record["size"] and blob_id(data)==record["git_blob_sha1"]:match="exact-source-blob"
        elif record["text"] and b"\r\n" in data:
            # Only exact Windows checkout newline conversion is accepted;
            # no arbitrary text cleanup, Unicode normalization or mixed endings.
            try:
                data.decode("utf-8")
                lf=data.replace(b"\r\n",b"\n")
                if b"\r" not in lf and lf.replace(b"\n",b"\r\n")==data and len(lf)==record["size"] and blob_id(lf)==record["git_blob_sha1"]:
                    match="source-blob-via-crlf-checkout"
            except UnicodeError:pass
        if match=="none":failures.append(name)
        details[name]={"source_git_blob_sha1":record["git_blob_sha1"],"variant":match,"actual_sha256":course.digest(actual[name]),"size":len(data)}
    marker=actual[MARKER].read_bytes() if MARKER in actual else b""
    expected_marker=(REFERENCE["observed_windows_marker"]+"\n").encode("ascii")
    marker_ok=marker==expected_marker
    if MARKER in actual:
        details[MARKER]={"actual_sha256":course.digest(actual[MARKER]),"size":len(marker),"variant":"native-fingerprint-observed-in-two-prior-launches"}
    return {"verified":not missing and not extra and not failures and marker_ok,
        "missing":sorted(missing),"extra":sorted(extra),"source_blob_mismatches":failures,
        "marker_matches_prior_native":marker_ok,
        "marker":marker.decode("ascii","backslashreplace")[:80],"files":details}


def extract(folder):
    course.REPORT=folder/"integrity.json";course.ROWS.clear();course.META.clear()
    fixture,files=course.extract(json.loads(INFO.read_bytes()),folder)
    assert course.digest(fixture/"codex.exe")==REFERENCE["runtime_binary_sha256"]
    META["archive_sha256"]=course.META["archive_sha256"];META["manifest_sha256"]=course.META["manifest_sha256"]
    META["file_count"]=len(files);META["zip_verified"]=True;save()
    return fixture,files


def check_non_system(fixture,files):
    changed=[]
    for name,rec in files.items():
        if name.startswith(PREFIX):continue
        p=fixture/name
        try:
            course.ancestors(p.parent);course.plain(p)
            if p.stat().st_size!=rec["size"] or course.digest(p)!=rec["sha256"]:changed.append(name)
        except (OSError,AssertionError):changed.append(name)
    root=fixture/"home/skills"
    actual={"home/skills/"+n for n in checked_tree(root) if not n.startswith(".system/")}
    expected={n for n in files if n.startswith("home/skills/") and not n.startswith(PREFIX)}
    return {"verified":not changed and actual==expected,"changed_non_system_shipped":changed,
        "missing_custom_skill_members":sorted(expected-actual),"unexpected_custom_skill_members":sorted(actual-expected)}


def system_diff(fixture,files):
    actual=checked_tree(fixture/"home/skills/.system")
    shipped={n[len(PREFIX):]:r for n,r in files.items() if n.startswith(PREFIX)}
    changed=sorted(n for n in actual.keys()&shipped.keys() if course.digest(actual[n])!=shipped[n]["sha256"])
    return {"removed":sorted(shipped.keys()-actual.keys()),"added":sorted(actual.keys()-shipped.keys()),"changed":changed}


def native(mode,fixture,files,minimal=False):
    audit.ROOT=fixture
    audit.core.SKILLS={p.parent.name for p in (fixture/"home/skills").glob("*/SKILL.md") if not p.parent.name.startswith(".")}
    entry=audit.mode_files(fixture,mode)
    work=fixture/"work/tool-probe";work.mkdir(parents=True,exist_ok=False)
    consumer=ROOT/"tests/sandbox_cache_path_consumer.py"
    dirs=(fixture,fixture/"work",fixture/"tmp",fixture/"tool",fixture/"home/skills",fixture.parent)
    if minimal:
        (work/"documents.py").write_text('print("PORTABLE_RELEASE_FULL_CONSUMER_DONE",flush=True)\n',encoding="utf-8")
    else:
        (work/"documents.py").write_text("MODE="+repr(mode)+"\n"+consumer.read_text(encoding="utf-8"),encoding="utf-8")
        for p in dirs:
            p.mkdir(parents=True,exist_ok=True)
            sentinel=p/"sandbox-followup-existing.txt";assert not sentinel.exists()
            sentinel.write_bytes(SENTINEL)
            a=sentinel.lstat();assert not a.st_file_attributes&1 and a.st_nlink==1
    model="gpt-6.2-sol";audit.m.MODEL_REQUESTS.clear();audit.m.MODEL_ERRORS.clear()
    handler=audit.handler_for(fixture)
    with audit.m.serving(audit.m.provider("",model=model,handler=handler,
          expected_headers={"X-Portable-Audit":"synthetic-package-value","X-Portable-Audit-Static":"synthetic-static"},
          forbidden_headers=("X-Portable-Host-Only",),max_requests=30)) as port:
        audit.api_config(fixture,port,model,mode,'$env:CODEX_PROXY_ENABLED = "false"\n')
        env=audit.clean_env();env["PORTABLE_TEST_HEADER"]="synthetic-parent-conflict";env["PORTABLE_TEST_MISSING_HEADER"]="synthetic-parent-only"
        rc,out,err=audit.bat(fixture,entry,["--portable-auth=api","exec","--skip-git-repo-check","--json","Run targeted synthetic Windows cache and sandbox audit."],env,timeout=850)
    results=work/"targeted-results.jsonl"
    if results.exists():
        for line in results.read_text(encoding="utf-8").splitlines():
            r=json.loads(line);assert r["mode"]==mode;row(mode,r["item"],r["status"],r["detail"])
    assert rc==0 and not audit.m.MODEL_ERRORS and "release-full-native-audit-completed" in out,(rc,audit.m.MODEL_ERRORS,out[-1500:],err[-1500:])
    assert handler.continuation.finished
    if not minimal:
        assert results.exists()
        for p in dirs:assert (p/"sandbox-followup-existing.txt").read_bytes()==SENTINEL
        row(mode,"synthetic precreated sentinel bytes retained","PASS_ACTUAL")
        # Host diagnostic is limited to read-only ACL/attributes of those
        # sentinels and failed private SSH directory. Not an elevated retry.
        host=work/"host-inspect.py"
        host.write_text("MODE='host-inspect'\n"+consumer.read_text(encoding="utf-8"),encoding="utf-8")
        before=len(results.read_text(encoding="utf-8").splitlines())
        env=audit.clean_env();env["CODEX_INSTALL_DIR"]=str(fixture)
        scratch=fixture/"tmp/host-metadata";scratch.mkdir()
        for key in ("HOME","USERPROFILE","APPDATA","LOCALAPPDATA","TEMP","TMP","TMPDIR","PROGRAMDATA"):
            env[key]=str(scratch)
        env["PSModuleAnalysisCachePath"]=str(scratch/"ps-module-analysis")
        r=subprocess.run([str(fixture/"tool/python/python.exe"),"-I","-B",str(host)],cwd=work,env=env,capture_output=True,timeout=100)
        lines=results.read_text(encoding="utf-8").splitlines()
        for line in lines[before:]:
            x=json.loads(line);assert x["mode"]=="host-inspect";row(mode+"-host-metadata",x["item"],x["status"],x["detail"])
        row(mode,"host read-only metadata diagnostic","PASS_ACTUAL" if r.returncode==0 and len(lines)>before else "FAIL",{"returncode":r.returncode,"stderr":r.stderr.decode("utf-8","backslashreplace")[-500:]})
    row(mode,"actual native launcher/Host completed","PASS_ACTUAL","not equivalent to all consumer assertions")
    source=verify_source_system(fixture/"home/skills/.system")
    diff=system_diff(fixture,files)
    non=check_non_system(fixture,files)
    row(mode,"fixed embedded system cache source membership and all bytes","PASS_ACTUAL" if source["verified"] else "FAIL",{**source,"runtime_delta_against_pristine":diff})
    row(mode,"all non-system shipped bytes and custom skill membership","PASS_ACTUAL" if non["verified"] else "FAIL",non)
    if minimal:
        # Corrected seed must remain byte-identical on the actual native start.
        course.verify(fixture,files,exact=False)
        assert not any(diff.values()) and source["verified"] and non["verified"]
        row(mode,"corrected pristine system seed remains identical after actual start","PASS_ACTUAL")
    return source,non


def run_probe():
    base=ROOT/"tmp"/("cache-path-followup-"+uuid.uuid4().hex);base.mkdir()
    witnesses=[];first_stage=base/"verified-first-system"
    try:
        for mode in ("normal","maintenance"):
            folder=base/mode;folder.mkdir()
            try:
                fixture,files=extract(folder)
                row(mode,"exact pristine candidate ZIP and moved tree","PASS_ACTUAL",len(files))
                source,non=native(mode,fixture,files)
                if source["verified"] and non["verified"]:
                    witnesses.append(source["files"])
                    if len(witnesses)==1:
                        shutil.copytree(fixture/"home/skills/.system",first_stage)
                        assert verify_source_system(first_stage)["verified"]
            except Exception:row(mode,"targeted native harness","FAIL",traceback.format_exc()[-6500:])
            finally:shutil.rmtree(folder)
        ok=len(witnesses)==2 and witnesses[0]==witnesses[1]
        row("system","two independent fixed native cache byte manifests agree","PASS_ACTUAL" if ok else "FAIL",{"witness_count":len(witnesses),"all_53_match":ok})
        if ok:
            assert not STAGE.exists()
            shutil.copytree(first_stage,STAGE)
            recheck=verify_source_system(STAGE)
            assert recheck["verified"] and recheck["files"]==witnesses[0]
            META["verified_system_files"]=witnesses[0]
            META["system_stage_verified"]=True
        META["completed"]=True;save()
    finally:shutil.rmtree(base)
    return int(any(r["status"]=="FAIL" for r in ROWS))


def apply_seed():
    # This runs only on a disposable Windows checkout after TWO actual source-
    # matched native launches, not on a user's live installation.
    result=json.loads(REPORT.read_bytes())
    assert result["metadata"]["completed"] and result["metadata"]["system_stage_verified"]
    assert result["metadata"]["source_commit"]==os.environ["GITHUB_SHA"]==git("rev-parse","HEAD").decode().strip()
    assert not git("status","--porcelain=v1","--untracked-files=all")
    verified=verify_source_system(STAGE)
    assert verified["verified"] and verified["files"]==result["metadata"]["verified_system_files"]
    target=ROOT/"home/skills/.system"
    old=checked_tree(target);new=checked_tree(STAGE)
    tracked={n.decode("utf-8")[len(PREFIX):] for n in git("ls-files","-z","--",PREFIX).split(b"\0") if n}
    assert tracked==set(old)
    changed=set(old)^set(new)
    changed.update(n for n in old.keys()&new.keys() if course.digest(old[n])!=course.digest(new[n]))
    assert changed,"No stale seed correction required"
    assert all(n in EXPECTED or n==MARKER or n in old for n in changed)
    # All destination parents and source files have been validated as ordinary.
    # No deletion beyond precisely the tracked stale files; no ACL changes.
    for n in sorted(set(old)-set(new)):old[n].unlink()
    for n in sorted(set(new)&changed):
        p=target/n;p.parent.mkdir(parents=True,exist_ok=True);course.ancestors(p.parent)
        if p.exists():course.plain(p)
        p.write_bytes(new[n].read_bytes());course.plain(p)
    check=verify_source_system(target);assert check["verified"] and check["files"]==verified["files"]
    git("add","-A","--",PREFIX)
    paths={n.decode("utf-8") for n in git("diff","--cached","--name-only","-z").split(b"\0") if n}
    assert paths=={PREFIX+n for n in changed}
    # Core.autocrlf is false in workflow; verify exact staged bytes, not just
    # working-tree digests. Git blobs are source data, not shell code.
    for n in new:
        assert git("show",":"+PREFIX+n)==new[n].read_bytes(),n
    git("-c","user.name=github-actions[bot]","-c","user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit","-m","Synchronize stale system skill seed to verified pinned Windows Codex payload")
    assert not git("status","--porcelain=v1","--untracked-files=all")
    print("VERIFIED_SYSTEM_SEED_COMMIT="+git("rev-parse","HEAD").decode().strip(),flush=True)
    return 0


def verify_candidate():
    base=ROOT/"tmp"/("cache-seed-candidate-"+uuid.uuid4().hex);base.mkdir()
    try:
        fixture,files=extract(base)
        row("candidate","exact corrected customer ZIP and moved tree","PASS_ACTUAL",len(files))
        before=verify_source_system(fixture/"home/skills/.system")
        assert before["verified"]
        stage=verify_source_system(STAGE)
        assert stage["verified"] and stage["files"]==before["files"]
        row("candidate","corrected shipped seed matches verified actual fixed Windows cache","PASS_ACTUAL",{"count":len(before["files"])})
        native("normal",fixture,files,minimal=True)
        META["completed"]=True;save()
    except Exception:
        row("candidate","corrected candidate verification","FAIL",traceback.format_exc()[-6500:]);return 1
    finally:shutil.rmtree(base)
    return 0


def main():
    assert os.name=="nt" and os.environ["GITHUB_REPOSITORY"]=="rileyaaa/Portable" and os.environ["GITHUB_REF"]=="refs/heads/dev/stable-tool-refresh"
    assert Path(sys.executable).resolve()==(ROOT/"tool/python/python.exe").resolve()
    assert STAGE.is_relative_to(ROOT/"tmp") and STAGE.parent==ROOT/"tmp"
    course.ancestors(STAGE.parent)
    if PHASE=="probe":return run_probe()
    if PHASE=="apply-seed":return apply_seed()
    if PHASE=="verify-candidate":return verify_candidate()
    raise ValueError("unknown targeted phase")


if __name__=="__main__":
    for stream in (sys.stdout,sys.stderr):stream.reconfigure(encoding="utf-8",errors="backslashreplace")
    raise SystemExit(main())
