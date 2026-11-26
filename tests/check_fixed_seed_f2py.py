"""Native acceptance of the exact corrected customer ZIP only; no old matrix."""
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import traceback
import uuid

ROOT=Path(__file__).absolute().parents[1]
assert os.name=="nt" and os.environ["GITHUB_REPOSITORY"]=="rileyaaa/Portable"
assert os.environ["GITHUB_REF"]=="refs/heads/dev/stable-tool-refresh"
assert Path(sys.executable).resolve()==(ROOT/"tool/python/python.exe").resolve()
LOCK=json.loads((ROOT/"tests/system_skills_0172_windows_seed.json").read_bytes())
PRIOR=json.loads((ROOT/"tests/sandbox_cache_paths_45747282942.json").read_bytes())
witnesses=[r["detail"] for r in PRIOR["probe"]["rows"] if r["item"]=="fixed embedded system cache source membership and all bytes"]
assert len(witnesses)==2 and all(x["verified"] for x in witnesses)
assert witnesses[0]["files"]==witnesses[1]["files"]==LOCK["files"] and len(LOCK["files"])==53
false_rows=[r["detail"] for r in PRIOR["probe"]["rows"] if r["item"]=="all non-system shipped bytes and custom skill membership"]
assert len(false_rows)==2 and all(not x["changed_non_system_shipped"] and not x["missing_custom_skill_members"] and x["unexpected_custom_skill_members"]==["home/skills/sandbox-followup-existing.txt"] for x in false_rows)
INFO=Path(sys.argv[1]).absolute()
REPORT=Path(sys.argv[2]).absolute()
# Reuse previous verified ZIP and native mock Responses peer. Import with its
# documented argv contract; never invoke its matrix or apply-seed phases.
sys.argv=[sys.argv[0],"verify-candidate",str(INFO),str(REPORT),str(ROOT/"tmp"/"unused-system-stage")]
spec=importlib.util.spec_from_file_location("cache_verified_helpers",ROOT/"tests/check_sandbox_cache_paths.py")
h=importlib.util.module_from_spec(spec);sys.modules[spec.name]=h;spec.loader.exec_module(h)
h.META.update(phase="fixed-seed-and-f2py",prior_run="45747282942",prior_record=LOCK["prior_commit"],completed=False)

CONSUMER=r'''
import json,os,re,subprocess,sys
from pathlib import Path
from numpy.f2py.f2py2e import get_newer_options
ROOT=Path(os.environ["CODEX_INSTALL_DIR"]).absolute()
assert Path(sys.executable).resolve()==(ROOT/"tool/python/python.exe").resolve()
assert sys.flags.isolated
work=ROOT/"work/tool-probe"
out=work/"f2py-actual";out.mkdir()
source_text="subroutine addone(x)\nreal :: x\nx=x+1\nend subroutine addone\n"
results=[]
cmd=Path(os.environ["SystemRoot"])/"System32/cmd.exe"
shim=ROOT/"tool/bin/f2py.cmd"
env_before={k:os.environ.get(k) for k in ("PYTHONUTF8","PYTHONIOENCODING","PATH")}
default_before=sys.flags.utf8_mode
for name,src_name in (("ascii","source.f90"),("chinese","\u4e2d\u6587.f90")):
    d=out/name;d.mkdir()
    src=d/src_name;src.write_text(source_text,encoding="ascii")
    target=d/"result.pyf"
    args=[str(shim),"-m","sample","-h",target.name,src.name]
    argv=str(cmd)+' /d /s /c "'+subprocess.list2cmdline(args)+'"'
    p=subprocess.run(argv,executable=str(cmd),cwd=d,stdin=subprocess.DEVNULL,capture_output=True,timeout=120)
    sig=target.read_text(encoding="utf-8") if target.is_file() else ""
    verified=bool(p.returncode==0 and re.search(r"(?im)^\s*python module sample\b",sig) and
        re.search(r"(?im)^\s*subroutine addone\(x\)",sig) and re.search(r"(?im)^\s*real\b.*\bx\b",sig) and src_name in sig)
    results.append({"name":name,"status":"PASS_ACTUAL" if verified else "FAIL","returncode":p.returncode,
        "verified_signature":verified,"stdout":p.stdout.decode("utf-8","backslashreplace")[-500:],
        "stderr":p.stderr.decode("utf-8","backslashreplace")[-500:]})
# Do not rerun the prior known-space failure: show fixed parser still splits it.
remain=get_newer_options(["-m","sample","two words.f90"])[2]
assert "two" in remain and "words.f90" in remain and "two words.f90" not in remain
assert sys.flags.utf8_mode==default_before and env_before=={k:os.environ.get(k) for k in env_before}
results.append({"name":"scope and unchanged fixed NumPy whitespace parser","status":"PASS_ACTUAL","utf8_mode_parent":default_before,"space_split_unchanged":True})
(work/"f2py-results.json").write_text(json.dumps(results,ensure_ascii=True),encoding="utf-8")
print("PORTABLE_RELEASE_FULL_CONSUMER_DONE",flush=True)
'''

def startup(mode,fixture,files):
    a=h.audit
    a.ROOT=fixture
    a.core.SKILLS={p.parent.name for p in (fixture/"home/skills").glob("*/SKILL.md") if not p.parent.name.startswith(".")}
    entry=a.mode_files(fixture,mode)
    work=fixture/"work/tool-probe";work.mkdir(parents=True,exist_ok=False)
    (work/"documents.py").write_text(CONSUMER if mode=="normal" else 'print("PORTABLE_RELEASE_FULL_CONSUMER_DONE",flush=True)\n',encoding="utf-8")
    model="gpt-6.2-sol";a.m.MODEL_REQUESTS.clear();a.m.MODEL_ERRORS.clear()
    handler=a.handler_for(fixture)
    with a.m.serving(a.m.provider("",model=model,handler=handler,
          expected_headers={"X-Portable-Audit":"synthetic-package-value","X-Portable-Audit-Static":"synthetic-static"},
          forbidden_headers=("X-Portable-Host-Only",),max_requests=30)) as port:
        a.api_config(fixture,port,model,mode,'$env:CODEX_PROXY_ENABLED = "false"\n')
        env=a.clean_env();env["PORTABLE_TEST_HEADER"]="synthetic-parent-conflict";env["PORTABLE_TEST_MISSING_HEADER"]="synthetic-parent-only"
        rc,out,err=a.bat(fixture,entry,["--portable-auth=api","exec","--skip-git-repo-check","--json","Run the synthetic seed and f2py probe."],env,timeout=600)
    assert rc==0 and not a.m.MODEL_ERRORS and "release-full-native-audit-completed" in out,(rc,a.m.MODEL_ERRORS,out[-1200:],err[-1200:])
    assert handler.continuation.finished
    if mode=="normal":
        for result in json.loads((work/"f2py-results.json").read_bytes()):
            h.row(mode,"f2py "+result["name"],result["status"],result)
    seed=h.verify_source_system(fixture/"home/skills/.system")
    non=h.check_non_system(fixture,files)
    delta=h.system_diff(fixture,files)
    assert seed["verified"] and seed["files"]==LOCK["files"] and not any(delta.values())
    assert non["verified"],non
    h.course.verify(fixture,files,exact=False)
    h.row(mode,"actual native start preserved all shipped bytes and custom skills","PASS_ACTUAL",{"system_members":53,"custom_membership":True,"delta":delta})


def main():
    source=h.verify_source_system(ROOT/"home/skills/.system")
    assert source["verified"] and source["files"]==LOCK["files"]
    h.row("source","all reconstructed fixed Windows seed bytes match both prior native manifests","PASS_ACTUAL",53)
    base=ROOT/"tmp"/("fixed-seed-native-"+uuid.uuid4().hex);base.mkdir()
    try:
        for mode in ("normal","maintenance"):
            folder=base/mode;folder.mkdir()
            try:
                fixture,files=h.extract(folder)
                assert h.verify_source_system(fixture/"home/skills/.system")["files"]==LOCK["files"]
                h.row(mode,"exact candidate ZIP and Chinese-space moved tree","PASS_ACTUAL",len(files))
                startup(mode,fixture,files)
            except Exception:h.row(mode,"targeted native harness","FAIL",traceback.format_exc()[-6000:])
            finally:shutil.rmtree(folder)
        h.META["completed"]=True;h.save()
    finally:shutil.rmtree(base)
    return int(any(x["status"]=="FAIL" for x in h.ROWS))


if __name__=="__main__":
    for stream in (sys.stdout,sys.stderr):stream.reconfigure(encoding="utf-8",errors="backslashreplace")
    raise SystemExit(main())
