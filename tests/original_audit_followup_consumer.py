"""Only the previously failed original-ZIP consumer groups; candidate, not old ZIP."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import traceback
import zipfile
import tomllib

ROOT=Path(os.environ["CODEX_INSTALL_DIR"]).absolute()
WORK=ROOT/"work/tool-probe"
OUT=WORK/"targeted-output"
OUT.mkdir(exist_ok=False)
PY=ROOT/"tool/python/python.exe"
WIN=Path(os.environ["SystemRoot"])
CMD=WIN/"System32/cmd.exe"
PS=WIN/"System32/WindowsPowerShell/v1.0/powershell.exe"
REPORT=WORK/"targeted-results.jsonl"
LABEL="TARGETED_SYNTHETIC_MARKER"
assert Path(sys.executable).resolve()==PY.resolve() and sys.flags.isolated
for stream in (sys.stdout,sys.stderr):
    stream.reconfigure(encoding="utf-8",errors="backslashreplace")


def row(item,status,detail=""):
    r=dict(mode=MODE,item=item,status=status,detail=str(detail)[:5000])
    with REPORT.open("a",encoding="utf-8") as f:f.write(json.dumps(r,ensure_ascii=True)+"\n")
    print("TARGETED_ROW="+json.dumps(r,ensure_ascii=True),flush=True)


def case(item,fn):
    try:row(item,"PASS_ACTUAL",fn() or "actual consumer assertions")
    except Exception:row(item,"FAIL",traceback.format_exc())


def run(rel,*args,cwd=OUT,expect=0):
    p=ROOT/rel
    assert p.is_file() and p.resolve().is_relative_to(ROOT)
    args=[str(a) for a in args]
    if p.suffix.lower() in (".cmd",".bat"):
        argv=str(CMD)+' /d /s /c "'+subprocess.list2cmdline([str(p),*args])+'"';exe=str(CMD)
    elif p.suffix.lower()==".ps1":
        argv=[str(PS),"-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",str(p),*args];exe=str(PS)
    else:argv=[str(p),*args];exe=str(p)
    child=subprocess.run(argv,executable=exe,cwd=cwd,stdin=subprocess.DEVNULL,capture_output=True,timeout=180)
    out=child.stdout.decode("utf-8","backslashreplace");err=child.stderr.decode("utf-8","backslashreplace")
    if expect is not None:assert child.returncode==expect,(rel,child.returncode,out[-2000:],err[-2000:])
    return child.returncode,out,err


def py(rel,*args):
    return run("tool/python/python.exe","-B",ROOT/rel,*args)[1]


def policy():
    c=tomllib.loads((ROOT/"home/config.toml").read_text(encoding="utf-8-sig"))
    want=("danger-full-access","never",True) if MODE=="yolo" else ("workspace-write","on-request",False)
    assert (c["sandbox_mode"],c["approval_policy"],c["sandbox_workspace_write"]["network_access"])==want
    norm=lambda p:os.path.normcase(os.path.normpath(str(p)))
    roots={norm(p) for p in c["sandbox_workspace_write"]["writable_roots"]}
    assert roots==({norm(ROOT)} if MODE=="maintenance" else {norm(ROOT/"work"),norm(ROOT/"tmp")})
    return "generated native policy, not actual writes"
case("mode policy configuration",policy)


def protected():
    for p,allowed in ((ROOT/"protected-audit.txt",MODE in ("maintenance","yolo")),(ROOT.parent/"outside-workspace-audit.txt",MODE=="yolo")):
        original=p.read_bytes();assert original==b"synthetic audit sentinel"
        try:p.write_bytes(b"targeted test write")
        except PermissionError:assert not allowed,"actual expected write denied: "+p.name
        else:
            try:assert allowed,"unexpected write allowed: "+p.name
            finally:p.write_bytes(original)
case("actual mode protected/outside writes",protected)


def rg():
    p=OUT/"search.txt";p.write_text(LABEL+"\n",encoding="utf-8")
    resolved=shutil.which("rg.exe")
    assert resolved and Path(resolved).resolve()==(ROOT/"codex-path/rg.exe").resolve(),resolved
    for rel in ("codex-path/rg.exe","tool/bin/rg.exe"):
        assert LABEL in run(rel,"--fixed-strings","--no-config",LABEL,p)[1]
case("fixed rg PATH order plus independent rg actual content",rg)


def f2py():
    (OUT/"sample.f90").write_text("subroutine addone(x)\nreal :: x\nx=x+1\nend subroutine addone\n")
    run("tool/bin/f2py.cmd","-m","sample","-h","sample.pyf","sample.f90")
    assert "addone" in (OUT/"sample.pyf").read_text().lower()
    return "relative names in relocated package; upstream absolute space-splitting limitation retained"
case("f2py relative-name signature generation",f2py)


def make_docs():
    import docx,pptx
    word=OUT/"source.docx";d=docx.Document();p=d.add_paragraph();p.add_run("first");p.add_run("second");d.save(word)
    deck=OUT/"source.pptx";d=pptx.Presentation();d.slides.add_slide(d.slide_layouts[6]);d.save(deck)
    return word,deck
word,deck=make_docs()


def merge():
    import docx
    p=OUT/"merged.docx";py("home/skills/docx/scripts/merge_runs.py",word,"-o",p)
    para=docx.Document(p).paragraphs[0]
    assert para.text=="firstsecond" and len(para.runs)==1
case("docx merge_runs real file",merge)


def comment():
    p=OUT/"commented.docx";py("home/skills/docx/scripts/comment.py",word,"synthetic comment","-o",p)
    with zipfile.ZipFile(p) as z:assert b"synthetic comment" in z.read("word/comments.xml")
case("docx comment real file",comment)


def slide():
    import pptx
    p=OUT/"added.pptx";py("home/skills/pptx/scripts/add_slide.py",deck,"slide1.xml","-o",p)
    assert len(pptx.Presentation(p).slides)==2
case("pptx add_slide real file",slide)


def clean():
    d=OUT/"unpacked";d.mkdir()
    with zipfile.ZipFile(deck) as z:
        assert all(not n.startswith("/") and ".." not in n.split("/") for n in z.namelist());z.extractall(d)
    p=d/"ppt/slides/slide999.xml";p.write_text("<unused/>")
    py("home/skills/pptx/scripts/clean.py",d)
    assert not p.exists() and (d/"ppt/slides/slide1.xml").exists()
case("pptx clean actual unpacked tree",clean)


def ssh():
    import paramiko
    name="synthetic-"+MODE
    py("tool/portable-ssh.py","keygen","--name",name,"--unencrypted")
    key=ROOT/"work/ssh/keys"/name;pub=key.with_suffix(".pub")
    assert paramiko.Ed25519Key.from_private_key_file(str(key)).get_name()=="ssh-ed25519"
    assert pub.read_text().startswith("ssh-ed25519 ")
    key.unlink();pub.unlink()
    return "only disposable key; no ACL relaxation or remote connection"
case("SSH keygen and readback actual mode",ssh)


def android_sqlite():
    assert run("tool/android/platform-tools/sqlite3.exe","native.sqlite","create table t(v); insert into t values(7); select v*3 from t;")[1].strip()=="21"
    with sqlite3.connect(OUT/"native.sqlite") as c:assert c.execute("select v from t").fetchone()==(7,)
    return "relative name in Chinese-space cwd; old Unicode absolute argument failure remains"
case("Android sqlite3 relative path actual database",android_sqlite)


def etc():
    from PIL import Image
    Image.new("RGB",(8,8),(10,30,50)).save(OUT/"etc-source.png")
    run("tool/android/platform-tools/etc1tool.exe","etc-source.png","-o","etc.pkm")
    assert (OUT/"etc.pkm").is_file()
    run("tool/android/platform-tools/etc1tool.exe","etc.pkm","--decode","-o","etc-decoded.png")
    with Image.open(OUT/"etc-decoded.png") as image:
        assert image.size==(8,8)
        pix=image.convert("RGB").getpixel((0,0))
        assert all(abs(a-b)<=35 for a,b in zip(pix,(10,30,50))),pix
    return "relative names; lossy ETC pixel tolerance; no host fallback"
case("Android etc1tool relative path actual encode/decode",etc)


def instructions():
    p=OUT/"instructions.md";p.write_text("Synthetic instructions\n")
    before=(ROOT/"env.local.ps1").read_bytes()
    home=ROOT/"home/targeted-instructions.md";assert not home.exists()
    output=py("tool/codex-instruct.py","--file",p,"--name","targeted-instructions","--dry-run")
    assert "Package root" in output and str(ROOT) in output
    assert not home.exists() and (ROOT/"env.local.ps1").read_bytes()==before
case("instruction installer Unicode redirected dry-run",instructions)


def browser_check():
    result=json.loads(run("tool/automation/start-browser.ps1","-Check","-Workspace","work/tool-probe")[1])
    assert result["BrowserPresent"] and not result["AutomaticStart"] and Path(result["PackageRoot"]).resolve()==ROOT.resolve()
    assert not (ROOT/"cache/browser").exists()
case("original browser-debug native read-only check",browser_check)

if MODE=="yolo":
    def httpx_cli():
        url="http://127.0.0.1:"+str(HTTP_PORT)+"/"
        rc,out,err=run("tool/bin/httpx.cmd",url,expect=None)
        if rc==0:
            assert "Portable MCP smoke" in out
            row("HTTPX CLI","PASS_ACTUAL","actual loopback")
        else:
            assert "httpx[cli]" in out+err
            row("HTTPX CLI","KNOWN_LIMIT","fixed optional CLI dependencies absent; no install")
    try:httpx_cli()
    except Exception:row("HTTPX CLI","FAIL",traceback.format_exc())

print("PORTABLE_RELEASE_FULL_CONSUMER_DONE",flush=True)
