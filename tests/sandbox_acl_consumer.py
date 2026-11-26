"""Native restricted-token probe and three repaired Office consumers; synthetic only."""
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
import zipfile
import tomllib

ROOT=Path(os.environ["CODEX_INSTALL_DIR"]).absolute()
WORK=ROOT/"work/tool-probe"
OUT=WORK/"targeted-output"
OUT.mkdir(exist_ok=False)
REPORT=WORK/"targeted-results.jsonl"
PY=ROOT/"tool/python/python.exe"
WIN=Path(os.environ["SystemRoot"])
assert Path(sys.executable).resolve()==PY.resolve() and sys.flags.isolated
assert MODE in ("normal","maintenance")
for stream in (sys.stdout,sys.stderr):
    stream.reconfigure(encoding="utf-8",errors="backslashreplace")


def row(item,status,detail=""):
    r=dict(mode=MODE,item=item,status=status,detail=detail)
    with REPORT.open("a",encoding="utf-8") as f:f.write(json.dumps(r,ensure_ascii=True)+"\n")
    print("TARGETED_ROW="+json.dumps(r,ensure_ascii=True),flush=True)


def case(item,fn):
    try:row(item,"PASS_ACTUAL",fn() or "actual assertions")
    except Exception:row(item,"FAIL",traceback.format_exc()[-6000:])


# Read-only native token/ACL evidence; no identity values, raw ACL, token
# handles or user names leave this process. No ACL changes or impersonation.
A=C.WinDLL("advapi32",use_last_error=True)
K=C.WinDLL("kernel32",use_last_error=True)
LP=C.c_void_p
DWORD=W.DWORD
BOOL=W.BOOL
HANDLE=W.HANDLE
def api(dll,name,result,args):
    f=getattr(dll,name);f.restype=result;f.argtypes=args;return f
get_current=api(K,"GetCurrentProcess",HANDLE,[])
close=api(K,"CloseHandle",BOOL,[HANDLE])
free=api(K,"LocalFree",LP,[LP])
open_token=api(A,"OpenProcessToken",BOOL,[HANDLE,DWORD,C.POINTER(HANDLE)])
get_token=api(A,"GetTokenInformation",BOOL,[HANDLE,C.c_int,LP,DWORD,C.POINTER(DWORD)])
is_restricted=api(A,"IsTokenRestricted",BOOL,[HANDLE])
is_sid=api(A,"IsValidSid",BOOL,[LP])
sid_length=api(A,"GetLengthSid",DWORD,[LP])
get_security=api(A,"GetNamedSecurityInfoW",DWORD,[W.LPCWSTR,DWORD,DWORD,LP,LP,C.POINTER(LP),LP,C.POINTER(LP)])
get_control=api(A,"GetSecurityDescriptorControl",BOOL,[LP,C.POINTER(W.WORD),C.POINTER(DWORD)])
get_acl=api(A,"GetAclInformation",BOOL,[LP,LP,DWORD,DWORD])
get_ace=api(A,"GetAce",BOOL,[LP,DWORD,C.POINTER(LP)])
class SidAndAttrs(C.Structure):_fields_=[("Sid",LP),("Attributes",DWORD)]
class TokenGroups(C.Structure):_fields_=[("Count",DWORD),("Groups",SidAndAttrs*1)]
class AclSize(C.Structure):_fields_=[("AceCount",DWORD),("AclBytesInUse",DWORD),("AclBytesFree",DWORD)]


def sid_bytes(p):
    assert p and is_sid(p)
    return C.string_at(p,sid_length(p))


def get_token_buffer(token,kind):
    n=DWORD()
    get_token(token,kind,None,0,C.byref(n))
    assert n.value>0
    b=C.create_string_buffer(n.value)
    if not get_token(token,kind,b,n,C.byref(n)):raise C.WinError(C.get_last_error())
    return b


def token_info():
    h=HANDLE()
    if not open_token(get_current(),8,C.byref(h)):raise C.WinError(C.get_last_error())
    try:
        b=get_token_buffer(h,11) # TokenRestrictedSids
        n=DWORD.from_buffer(b).value
        assert n<=1024
        if n:
            assert TokenGroups.Groups.offset+n*C.sizeof(SidAndAttrs)<=len(b)
            groups=(SidAndAttrs*n).from_buffer(b,TokenGroups.Groups.offset)
            sids={sid_bytes(x.Sid) for x in groups}
        else:sids=set()
        elevation=DWORD.from_buffer_copy(get_token_buffer(h,20)).value
        info={"restricted":bool(is_restricted(h)),"restricting_sid_count":len(sids),"elevated":bool(elevation)}
        return info,sids
    finally:close(h)


try:TOKEN,SIDS=token_info()
except Exception as exc:
    TOKEN={"error":type(exc).__name__};SIDS=set()
row("native Windows token","OBSERVED",TOKEN)


def acl_info(p):
    dacl=LP();sd=LP()
    try:
        rc=get_security(str(p),1,4,None,None,C.byref(dacl),None,C.byref(sd))
        if rc:return {"winerror":int(rc)}
        control=W.WORD();revision=DWORD()
        if not get_control(sd,C.byref(control),C.byref(revision)):raise C.WinError(C.get_last_error())
        result={"protected":bool(control.value&0x1000),"auto_inherited":bool(control.value&0x400),"null_dacl":not bool(dacl)}
        if not dacl:return result
        info=AclSize()
        if not get_acl(dacl,C.byref(info),C.sizeof(info),2):raise C.WinError(C.get_last_error())
        result.update(ace_count=info.AceCount,inherited=0,restricted_allow_write=0,restricted_deny_write=0)
        # Only ordinary access-allowed/denied ACEs are classified. Counts
        # are diagnostic, not a substitute for an effective AccessCheck.
        for i in range(info.AceCount):
            ace=LP()
            if not get_ace(dacl,i,C.byref(ace)):raise C.WinError(C.get_last_error())
            header=C.string_at(ace,8);kind,flags=header[:2]
            if flags&0x10:result["inherited"]+=1
            if kind not in (0,1):continue
            mask=int.from_bytes(header[4:8],"little")
            if mask&(0x40000000|0x10000000|0x2|0x4|0x40|0x10000) and sid_bytes(ace.value+8) in SIDS:
                result["restricted_allow_write" if kind==0 else "restricted_deny_write"]+=1
        return result
    except Exception as exc:return {"error":type(exc).__name__,"winerror":getattr(exc,"winerror",None)}
    finally:
        if sd:free(sd)


def configured():
    cfg=tomllib.loads((ROOT/"home/config.toml").read_text(encoding="utf-8-sig"))
    assert cfg["sandbox_mode"]=="workspace-write" and cfg["approval_policy"]=="on-request"
    assert cfg["windows"]["sandbox"]=="unelevated" and cfg["sandbox_workspace_write"]["network_access"] is False
    norm=lambda p:os.path.normcase(os.path.normpath(str(p)))
    actual={norm(x) for x in cfg["sandbox_workspace_write"]["writable_roots"]}
    assert actual==({norm(ROOT)} if MODE=="maintenance" else {norm(ROOT/"work"),norm(ROOT/"tmp")})
    assert TOKEN.get("restricted") is True and TOKEN.get("restricting_sid_count",0)>0
    return {"configuration_verified":True,"restricted_token":TOKEN}
case("actual native configuration and restricted token",configured)


def attempt(fn):
    try:fn();return {"ok":True}
    except OSError as exc:return {"ok":False,"errno":exc.errno,"winerror":getattr(exc,"winerror",None)}
    except Exception as exc:return {"ok":False,"error":type(exc).__name__}


# Each sentinel is prepared and verified by the host orchestrator. Never touch
# actual code, configuration, security state or user files.
matrix=[("package_root",ROOT),("work",ROOT/"work"),("tmp",ROOT/"tmp"),
        ("tool",ROOT/"tool"),("skills",ROOT/"home/skills"),("outside",ROOT.parent)]
for label,directory in matrix:
    allowed=label in {"work","tmp"} or MODE=="maintenance" and label!="outside"
    existing=directory/"sandbox-followup-existing.txt";new=directory/"sandbox-followup-new.txt"
    assert existing.read_bytes()==b"synthetic audit sentinel" and not new.exists()
    meta={"expected_write":allowed,"directory_acl":acl_info(directory),"existing_acl":acl_info(existing)}
    def overwrite():
        with existing.open("r+b") as f:
            f.seek(0);f.write(b"X");f.flush();f.seek(0);assert f.read(1)==b"X"
            f.seek(0);f.write(b"s");f.flush()
        assert existing.read_bytes()==b"synthetic audit sentinel"
    def create():
        with new.open("xb") as f:f.write(b"synthetic new sentinel")
        assert new.read_bytes()==b"synthetic new sentinel"
    meta["overwrite_restore"]=attempt(overwrite)
    meta["create"]=attempt(create)
    if new.exists():meta["new_acl"]=acl_info(new);meta["delete_created"]=attempt(new.unlink)
    expected_ok=all(meta[k]["ok"]==allowed for k in ("overwrite_restore","create"))
    if meta["create"]["ok"]:expected_ok=expected_ok and meta.get("delete_created",{}).get("ok") is True
    row("actual write matrix "+label,"PASS_ACTUAL" if expected_ok else "FAIL",meta)


def directory_probe(parent,mode):
    target=parent/("sandbox-followup-mode-"+oct(mode)[2:])
    assert not target.exists()
    result={"parent_acl":acl_info(parent),"mkdir":attempt(lambda:target.mkdir(mode=mode))}
    if target.exists():
        result["child_acl"]=acl_info(target)
        marker=target/"public-synthetic.txt"
        def rw():
            with marker.open("xb") as f:f.write(b"not secret")
            assert marker.read_bytes()==b"not secret"
            marker.unlink()
        result["child_write_read_delete"]=attempt(rw)
        result["directory_cleanup"]=attempt(target.rmdir)
    return result
for name,parent in (("work",WORK),("tmp",ROOT/"tmp")):
    for perm in (0o700,0o777):
        d=directory_probe(parent,perm)
        row("directory ACL diagnostic "+name+" "+oct(perm),"OBSERVED",d)
        if perm==0o777:
            row("existing writable parent inherited scratch control "+name,
                "PASS_ACTUAL" if all(d.get(k,{}).get("ok") for k in ("mkdir","child_write_read_delete","directory_cleanup")) else "FAIL",d)


def py(rel,*args,expect=0):
    p=ROOT/rel
    assert p.is_file() and p.resolve().is_relative_to(ROOT)
    r=subprocess.run([str(PY),"-B",str(p),*map(str,args)],cwd=OUT,stdin=subprocess.DEVNULL,capture_output=True,timeout=180)
    out=r.stdout.decode("utf-8","backslashreplace");err=r.stderr.decode("utf-8","backslashreplace")
    if expect is not None:assert r.returncode==expect,(rel,r.returncode,out[-1800:],err[-1800:])
    return r.returncode,out,err


import docx,pptx
word=OUT/"source.docx";d=docx.Document();p=d.add_paragraph();p.add_run("first");p.add_run("second");d.save(word)
deck=OUT/"source.pptx";d=pptx.Presentation();d.slides.add_slide(d.slide_layouts[6]);d.save(deck)
scratch=ROOT/"tmp/office"
def scratch_empty():
    assert not scratch.exists() or not list(scratch.iterdir()),"Office scratch not cleaned"
def merge():
    p=OUT/"merged.docx";py("home/skills/docx/scripts/merge_runs.py",word,"-o",p)
    para=docx.Document(p).paragraphs[0];assert para.text=="firstsecond" and len(para.runs)==1
    scratch_empty()
case("fixed merge_runs native file roundtrip and scratch cleanup",merge)
def comment():
    p=OUT/"commented.docx";py("home/skills/docx/scripts/comment.py",word,"synthetic comment","-o",p)
    with zipfile.ZipFile(p) as z:assert b"synthetic comment" in z.read("word/comments.xml")
    scratch_empty()
case("fixed comment native file roundtrip and scratch cleanup",comment)
def slide():
    p=OUT/"added.pptx";py("home/skills/pptx/scripts/add_slide.py",deck,"slide1.xml","-o",p)
    assert len(pptx.Presentation(p).slides)==2
    scratch_empty()
case("fixed add_slide native file roundtrip and scratch cleanup",slide)
def malformed():
    p=OUT/"bad.docx";p.write_bytes(b"not a ZIP")
    target=OUT/"must-not-create.docx"
    r,_,_=py("home/skills/docx/scripts/merge_runs.py",p,"-o",target,expect=None)
    assert r!=0 and not target.exists()
    scratch_empty()
case("malformed packed document fails without scratch residue",malformed)


# Keep original private-directory policy; only disposable synthetic keypair,
# no network, no ACL edits. A failure is not silently replaced by host work.
def ssh():
    import paramiko
    name="synthetic-native-"+MODE
    py("tool/portable-ssh.py","keygen","--name",name,"--unencrypted")
    key=ROOT/"work/ssh/keys"/name;pub=key.with_suffix(".pub")
    assert paramiko.Ed25519Key.from_private_key_file(str(key)).get_name()=="ssh-ed25519"
    assert pub.read_text().startswith("ssh-ed25519 ")
    key.unlink();pub.unlink()
    return "disposable synthetic key only; original ACL behavior unchanged"
case("SSH actual sandbox keygen/readback",ssh)
for name in ("work","work/ssh","work/ssh/keys"):
    p=ROOT/name
    row("SSH ACL diagnostic "+name,"OBSERVED",{"exists":p.exists(),"acl":acl_info(p)})
print("PORTABLE_RELEASE_FULL_CONSUMER_DONE",flush=True)
