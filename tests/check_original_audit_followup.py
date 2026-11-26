"""Targeted native follow-up on the *new candidate* ZIP, never overwrite frozen audit."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import traceback
import uuid

ROOT=Path(__file__).absolute().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

course=load("candidate_zip_verifier",ROOT/"tests/check_course_assistant.py")
audit=load("original_followup_peer",ROOT/"tests/audit_release_zip.py")
audit.core=load("original_followup_core",ROOT/"tests/check_codex_tool_discovery.py")
audit.m=audit.core.m
audit.core.MAX_CELL_WAITS=20
ROWS=[]
META={"original_run":"45739266926","source_commit":os.environ["GITHUB_SHA"],"candidate_only":True,"completed":False}
REPORT=Path(sys.argv[2]).absolute()
INFO=json.loads(Path(sys.argv[1]).read_bytes())


def save():
    REPORT.write_text(json.dumps(dict(metadata=META,rows=ROWS),ensure_ascii=True,indent=2)+"\n",encoding="utf-8")


def row(mode,item,status,detail=""):
    r=dict(mode=mode,item=item,status=status,detail=str(detail)[:6000])
    ROWS.append(r);save()
    print("ORIGINAL_FOLLOWUP_ROW="+json.dumps(r,ensure_ascii=True),flush=True)


def one(mode,fixture,http_port):
    audit.ROOT=fixture
    audit.core.SKILLS={p.parent.name for p in (fixture/"home/skills").glob("*/SKILL.md") if not p.parent.name.startswith(".")}
    entry=audit.mode_files(fixture,mode)
    work=fixture/"work/tool-probe";work.mkdir(parents=True,exist_ok=False)
    (work/"documents.py").write_text("MODE="+repr(mode)+"\nHTTP_PORT="+str(http_port)+"\n"+
        (ROOT/"tests/original_audit_followup_consumer.py").read_text(encoding="utf-8"),encoding="utf-8")
    for p in (fixture/"protected-audit.txt",fixture.parent/"outside-workspace-audit.txt"):p.write_bytes(b"synthetic audit sentinel")
    model="gpt-6.2-sol";audit.m.MODEL_REQUESTS.clear();audit.m.MODEL_ERRORS.clear()
    handler=audit.handler_for(fixture)
    with audit.m.serving(audit.m.provider("",model=model,handler=handler,
          expected_headers={"X-Portable-Audit":"synthetic-package-value","X-Portable-Audit-Static":"synthetic-static"},
          forbidden_headers=("X-Portable-Host-Only",),max_requests=30)) as port:
        audit.api_config(fixture,port,model,mode,'$env:CODEX_PROXY_ENABLED = "false"\n')
        env=audit.clean_env();env["PORTABLE_TEST_HEADER"]="synthetic-parent-conflict";env["PORTABLE_TEST_MISSING_HEADER"]="synthetic-parent-only"
        status,out,err=audit.bat(fixture,entry,["--portable-auth=api","exec","--skip-git-repo-check","--json","Run targeted local candidate followup."],env,timeout=850)
    results=work/"targeted-results.jsonl"
    if results.exists():
        for line in results.read_text(encoding="utf-8").splitlines():
            r=json.loads(line);assert r["mode"]==mode
            row(mode,r["item"],r["status"],r["detail"])
    assert status==0 and not audit.m.MODEL_ERRORS and "release-full-native-audit-completed" in out,(status,audit.m.MODEL_ERRORS,out[-1500:],err[-1500:])
    assert results.exists() and handler.continuation.finished
    for p in (fixture/"protected-audit.txt",fixture.parent/"outside-workspace-audit.txt"):assert p.read_bytes()==b"synthetic audit sentinel"
    row(mode,"native BAT/Codex/Host targeted consumer finished","PASS_ACTUAL","not equivalent to every consumer passing")


def utilities(fixture):
    env=audit.clean_env()
    for k in ("HOME","USERPROFILE","APPDATA","LOCALAPPDATA","TEMP","TMP","PROGRAMDATA"):
        p=fixture/"tmp"/("followup-"+k.lower());p.mkdir(parents=True,exist_ok=True);env[k]=str(p)
    env["PSModuleAnalysisCachePath"]=str(fixture/"tmp/ps-module-analysis")
    cookie=fixture/"cache/browser/audit-cookie.txt";cookie.parent.mkdir(parents=True,exist_ok=True);cookie.write_text("synthetic cookie")
    work=fixture/"work/keep-audit.txt";work.parent.mkdir(parents=True,exist_ok=True);work.write_text("keep")
    script=fixture/"\u6e05\u7406\u7f13\u5b58.ps1"
    prefix=[str(audit.PS),"-NoLogo","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",str(script)]
    rc,out,err=audit.child(prefix+["-WhatIf"],fixture,env,timeout=120)
    assert rc==0 and cookie.exists() and work.exists(),(rc,out[-1500:],err[-1500:])
    rc,out,err=audit.child(prefix+["-Yes","-PreserveSkills","-PreserveWork","-PreservePlugins"],fixture,env,timeout=180)
    assert rc==0 and not cookie.exists() and work.read_text()=="keep",(rc,out[-1500:],err[-1500:])
    row("utilities","actual cache preview and cleanup with existing work fixture","PASS_ACTUAL")


def main():
    assert os.name=="nt" and os.environ.get("GITHUB_REPOSITORY")=="rileyaaa/Portable" and os.environ.get("GITHUB_REF")=="refs/heads/dev/stable-tool-refresh"
    assert Path(sys.executable).resolve()==(ROOT/"tool/python/python.exe").resolve()
    base=ROOT/"tmp"/("original-followup-"+uuid.uuid4().hex);base.mkdir()
    try:
        with audit.m.serving(audit.m.module.Page) as port:
            for mode in ("normal","maintenance","yolo","utilities"):
                folder=base/mode;folder.mkdir()
                try:
                    course.REPORT=folder/"integrity.json";course.ROWS.clear();course.META.clear()
                    fixture,files=course.extract(INFO,folder)
                    row(mode,"exact candidate ZIP and moved tree integrity","PASS_ACTUAL",str(len(files))+" members")
                    if mode=="utilities":utilities(fixture)
                    else:one(mode,fixture,port)
                except Exception:row(mode,"targeted harness","FAIL",traceback.format_exc())
                finally:shutil.rmtree(folder)
        META["completed"]=True
    finally:
        save();shutil.rmtree(base)
    return int(any(r["status"]=="FAIL" for r in ROWS))


if __name__=="__main__":
    for stream in (sys.stdout,sys.stderr):stream.reconfigure(encoding="utf-8",errors="backslashreplace")
    raise SystemExit(main())
