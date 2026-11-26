"""One narrow Windows batch: exact candidate copies, native sandbox, OCR and marker."""
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
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
course=load("targeted_course_verifier",ROOT/"tests/check_course_assistant.py")
audit=load("targeted_audit_peer",ROOT/"tests/audit_release_zip.py")
audit.core=load("targeted_audit_core",ROOT/"tests/check_codex_tool_discovery.py")
audit.m=audit.core.m
audit.core.MAX_CELL_WAITS=20
REPORT=Path(sys.argv[3]).absolute()
INFO=json.loads(Path(sys.argv[2]).read_bytes())
MODE=sys.argv[1]
ROWS=[]
META={"prior_run":"45741929384","prior_source":"5b8d3dae6d2d6f8966ce39eb48c32072c2b4c04b",
    "source_commit":os.environ["GITHUB_SHA"],"scope":MODE,"runner_image":os.environ.get("ImageOS"),
    "runner_image_version":os.environ.get("ImageVersion"),"completed":False}


def save():
    REPORT.write_text(json.dumps(dict(metadata=META,rows=ROWS),ensure_ascii=True,indent=2)+"\n",encoding="utf-8")


def row(mode,item,status,detail=""):
    r=dict(mode=mode,item=item,status=status,detail=detail)
    ROWS.append(r);save();print("TARGETED_BATCH_ROW="+json.dumps(r,ensure_ascii=True),flush=True)


def extract(folder):
    course.REPORT=folder/"integrity.json";course.ROWS.clear();course.META.clear()
    fixture,files=course.extract(INFO,folder)
    META["archive_sha256"]=course.META["archive_sha256"]
    META["manifest_sha256"]=course.META["manifest_sha256"]
    META["file_count"]=len(files)
    return fixture,files


MARKER="home/skills/.system/.codex-system-skills.marker"
def system_marker(fixture,files,mode):
    # Exact pristine ZIP was verified before runtime. This compares every
    # shipped .system member, never a blanket skip for a mutable subtree.
    assert MARKER in files
    system=fixture/"home/skills/.system"
    actual={p.relative_to(fixture).as_posix() for p in system.rglob("*") if p.is_file()}
    expected={n for n in files if n.startswith("home/skills/.system/")}
    bad=[]
    for n in sorted(actual&expected):
        p=fixture/n;course.ancestors(p.parent);course.plain(p)
        if n!=MARKER and (p.stat().st_size!=files[n]["size"] or course.digest(p)!=files[n]["sha256"]):bad.append(n)
    marker=(fixture/MARKER).read_bytes()
    assert re.fullmatch(rb"[0-9a-f]{1,16}\n",marker)
    # Native launcher also owns ordinary runtime state, but original tracked
    # payload members other than the exact marker must still match.
    other=[]
    for n,rec in files.items():
        if n.startswith("home/skills/.system/"):continue
        p=fixture/n
        try:
            course.ancestors(p.parent);course.plain(p)
            if p.stat().st_size!=rec["size"] or course.digest(p)!=rec["sha256"]:other.append(n)
        except (OSError,AssertionError):other.append(n)
    result={"marker":marker.decode("ascii").strip(),"original_marker_sha256":files[MARKER]["sha256"],
        "runtime_marker_sha256":course.digest(fixture/MARKER),"missing":sorted(expected-actual),"new":sorted(actual-expected),
        "changed_system_non_marker":bad,"changed_other_shipped_members":other}
    row(mode,"actual system cache marker and all shipped member byte check",
        "PASS_ACTUAL" if not (expected-actual or actual-expected or bad or other) else "FAIL",result)
    return result


def native(mode,fixture,files):
    audit.ROOT=fixture
    audit.core.SKILLS={p.parent.name for p in (fixture/"home/skills").glob("*/SKILL.md") if not p.parent.name.startswith(".")}
    entry=audit.mode_files(fixture,mode)
    work=fixture/"work/tool-probe";work.mkdir(parents=True,exist_ok=False)
    (work/"documents.py").write_text("MODE="+repr(mode)+"\n"+(ROOT/"tests/sandbox_acl_consumer.py").read_text(encoding="utf-8"),encoding="utf-8")
    dirs=(fixture,fixture/"work",fixture/"tmp",fixture/"tool",fixture/"home/skills",fixture.parent)
    for p in dirs:
        p.mkdir(parents=True,exist_ok=True)
        sentinel=p/"sandbox-followup-existing.txt";assert not sentinel.exists()
        sentinel.write_bytes(b"synthetic audit sentinel")
    # Direct control: use bundled Python in this same extracted package
    # outside Codex's command sandbox, never as proof of sandbox success.
    # Run after the native probe so its ACL observations are not preseeded.
    model="gpt-6.2-sol";audit.m.MODEL_REQUESTS.clear();audit.m.MODEL_ERRORS.clear()
    handler=audit.handler_for(fixture)
    with audit.m.serving(audit.m.provider("",model=model,handler=handler,
          expected_headers={"X-Portable-Audit":"synthetic-package-value","X-Portable-Audit-Static":"synthetic-static"},
          forbidden_headers=("X-Portable-Host-Only",),max_requests=30)) as port:
        audit.api_config(fixture,port,model,mode,'$env:CODEX_PROXY_ENABLED = "false"\n')
        env=audit.clean_env();env["PORTABLE_TEST_HEADER"]="synthetic-parent-conflict";env["PORTABLE_TEST_MISSING_HEADER"]="synthetic-parent-only"
        rc,out,err=audit.bat(fixture,entry,["--portable-auth=api","exec","--skip-git-repo-check","--json","Run targeted synthetic sandbox audit."],env,timeout=750)
    results=work/"targeted-results.jsonl"
    if results.exists():
        for line in results.read_text(encoding="utf-8").splitlines():
            r=json.loads(line);assert r["mode"]==mode;row(mode,r["item"],r["status"],r["detail"])
    assert rc==0 and not audit.m.MODEL_ERRORS and "release-full-native-audit-completed" in out,(rc,audit.m.MODEL_ERRORS,out[-1300:],err[-1300:])
    assert results.exists() and handler.continuation.finished
    for p in dirs:
        sentinel=p/"sandbox-followup-existing.txt"
        assert sentinel.read_bytes()==b"synthetic audit sentinel"
    row(mode,"actual native Codex BAT/Host consumer completed","PASS_ACTUAL","independent of failed consumer assertions")
    marker=system_marker(fixture,files,mode)
    if mode=="normal":
        p=fixture/"work/tool-probe/direct-key-control.py"
        p.write_text("""import ctypes as C,json,sys,subprocess
from ctypes import wintypes as W
from pathlib import Path
root=Path(__file__).resolve().parents[2]
k=C.WinDLL('kernel32');a=C.WinDLL('advapi32')
k.GetCurrentProcess.restype=W.HANDLE
a.OpenProcessToken.argtypes=[W.HANDLE,W.DWORD,C.POINTER(W.HANDLE)]
a.IsTokenRestricted.argtypes=[W.HANDLE];a.IsTokenRestricted.restype=W.BOOL
a.GetTokenInformation.argtypes=[W.HANDLE,C.c_int,C.c_void_p,W.DWORD,C.POINTER(W.DWORD)]
k.CloseHandle.argtypes=[W.HANDLE]
h=W.HANDLE()
assert a.OpenProcessToken(k.GetCurrentProcess(),8,C.byref(h))
try:
 e=W.DWORD();n=W.DWORD()
 assert a.GetTokenInformation(h,20,C.byref(e),C.sizeof(e),C.byref(n))
 info={'restricted':bool(a.IsTokenRestricted(h)),'elevated':bool(e.value)}
finally:k.CloseHandle(h)
py=root/'tool/python/python.exe'
r=subprocess.run([str(py),'-B',str(root/'tool/portable-ssh.py'),'keygen','--name','synthetic-direct-control','--unencrypted'],cwd=root/'work',capture_output=True,timeout=90)
info['keygen_returncode']=r.returncode
if r.returncode==0:
 import paramiko
 key=root/'work/ssh/keys/synthetic-direct-control';pub=key.with_suffix('.pub')
 info['readback']=paramiko.Ed25519Key.from_private_key_file(str(key)).get_name()=='ssh-ed25519' and pub.read_text().startswith('ssh-ed25519 ')
 key.unlink();pub.unlink()
print(json.dumps(info))
""",encoding="utf-8")
        env=course.env(fixture,"a")
        r=subprocess.run([str(fixture/"tool/python/python.exe"),"-I","-B",str(p)],cwd=fixture/"work",env=env,capture_output=True,timeout=120)
        if r.returncode==0:
            info=json.loads(r.stdout);row("direct-control","same extracted package SSH ordinary process (not sandbox evidence)","OBSERVED",info)
        else:row("direct-control","same extracted package SSH ordinary process","OBSERVED",{"returncode":r.returncode,"detail":"direct control failed; no substitute"})
    return marker["marker"]


def language_preflight():
    # Native Windows API only, no installation, no administrator command.
    code="""$ErrorActionPreference='Stop';[void][Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime];[void][Windows.Globalization.Language,Windows.Globalization,ContentType=WindowsRuntime];$l=[Windows.Globalization.Language]::new('zh-Hans-CN');[ordered]@{available=@([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages|ForEach-Object{$_.LanguageTag});supported=[Windows.Media.Ocr.OcrEngine]::IsLanguageSupported($l)}|ConvertTo-Json -Compress"""
    r=subprocess.run([str(course.PS),"-NoProfile","-NonInteractive","-Command",code],capture_output=True,timeout=40)
    assert r.returncode==0,("Windows OCR API preflight",r.returncode)
    return json.loads(r.stdout.decode("utf-8-sig"))


def chinese(folder):
    check=language_preflight()
    row("ocr","actual OS language inventory","OBSERVED",check)
    if not check["supported"]:
        row("ocr","Chinese OCR","BLOCKED_LANGUAGE_MISSING","no zh-Hans-CN; no installation or substitute")
        return
    fixture,files=extract(folder)
    row("ocr","exact candidate ZIP and moved tree","PASS_ACTUAL",len(files))
    with course.serve() as origin:
        owner=course.Owner(fixture,"a",origin,False)
        client=course.Client(fixture,"a",owner.session)
        client.call("course_bind",confirmed=True)
        result=client.call("course_ocr_check",language="zh-Hans-CN")
        assert result["supported"] and result["zhHansSupported"]
        r=client.call("course_ocr",selector="#ocrZh",pageSelector="#page-label",language="zh-Hans-CN")
        assert r["supported"] and r["actualLanguage"].lower().startswith("zh")
        t=re.sub(r"\s+","",r["text"])
        assert "\u4e2d\u6587\u8bfe\u4ef6" in t and "123" in t
        assert r["source"]["pageLabel"]=="Page 2 of 2" and r["source"]["imageSelector"]=="#ocrZh" and r["lines"]
        words=[w for line in r["lines"] for w in line["words"]];assert words and all(w["width"]>0 and w["height"]>0 for w in words)
        assert not list((fixture/"work/course-fixture/a/tmp").glob("ocr-*.png"))
        client.call("course_close",confirmed=True);client.end();assert owner.p.wait(timeout=60)==0
        assert not course.Page.submitted
    course.verify(fixture,files,exact=False)
    row("ocr","actual bundled Chinese course OCR","PASS_ACTUAL",{"actualLanguage":r["actualLanguage"],"source":r["source"]["pageLabel"],"verified_text":"Chinese fixture and 123","word_boxes":len(words)})


def main():
    assert os.name=="nt" and os.environ["GITHUB_REPOSITORY"]=="rileyaaa/Portable" and os.environ["GITHUB_REF"]=="refs/heads/dev/stable-tool-refresh"
    assert Path(sys.executable).resolve()==(ROOT/"tool/python/python.exe").resolve()
    assert MODE in {"main","ocr-only"}
    base=ROOT/"tmp"/("sandbox-ocr-followup-"+uuid.uuid4().hex);base.mkdir()
    try:
        if MODE=="main":
            markers=[]
            for mode in ("normal","maintenance"):
                folder=base/mode;folder.mkdir()
                try:
                    fixture,files=extract(folder);row(mode,"exact new candidate ZIP and moved tree","PASS_ACTUAL",len(files))
                    markers.append(native(mode,fixture,files))
                except Exception:row(mode,"native sandbox targeted harness","FAIL",traceback.format_exc()[-6500:])
                finally:shutil.rmtree(folder)
            row("marker","independent native launch marker repeatability",
                "PASS_ACTUAL" if len(markers)==2 and markers[0]==markers[1] else "FAIL",markers)
        folder=base/"ocr";folder.mkdir()
        try:chinese(folder)
        except Exception:row("ocr","targeted OCR harness","FAIL",traceback.format_exc()[-6500:])
        META["completed"]=True
    finally:
        for p in reversed(course.PROCS):
            if p.poll() is None:
                subprocess.run([str(course.WIN/"System32/taskkill.exe"),"/PID",str(p.pid),"/T","/F"],capture_output=True,timeout=20,check=False)
                p.wait(timeout=30)
        save();shutil.rmtree(base)
    return int(any(x["status"] in ("FAIL","BLOCKED_LANGUAGE_MISSING") for x in ROWS))


if __name__=="__main__":
    for stream in (sys.stdout,sys.stderr):stream.reconfigure(encoding="utf-8",errors="backslashreplace")
    raise SystemExit(main())
