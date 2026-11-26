"""Native write-flag/owner/ACL followup, SSH diagnosis and CLI path contrasts; synthetic only."""
import ctypes as C
from ctypes import wintypes as W
import json
import importlib.metadata
import importlib.util
import shutil
import sqlite3
import stat
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
OUT.mkdir(exist_ok=MODE=='host-inspect')
REPORT=WORK/"targeted-results.jsonl"
PY=ROOT/"tool/python/python.exe"
WIN=Path(os.environ["SystemRoot"])
assert Path(sys.executable).resolve()==PY.resolve() and sys.flags.isolated
assert MODE in ("normal","maintenance","host-inspect")
for stream in (sys.stdout,sys.stderr):
    stream.reconfigure(encoding="utf-8",errors="backslashreplace")


def row(item,status,detail=""):
    r=dict(mode=MODE,item=item,status=status,detail=detail)
    with REPORT.open("a",encoding="utf-8") as f:f.write(json.dumps(r,ensure_ascii=True)+"\n")
    print("TARGETED_ROW="+json.dumps({"item":item,"status":status},ensure_ascii=True),flush=True)


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
get_security=api(A,"GetNamedSecurityInfoW",DWORD,[W.LPCWSTR,DWORD,DWORD,C.POINTER(LP),LP,C.POINTER(LP),LP,C.POINTER(LP)])
get_control=api(A,"GetSecurityDescriptorControl",BOOL,[LP,C.POINTER(W.WORD),C.POINTER(DWORD)])
get_acl=api(A,"GetAclInformation",BOOL,[LP,LP,DWORD,DWORD])
get_ace=api(A,"GetAce",BOOL,[LP,DWORD,C.POINTER(LP)])
open_file=api(K,"CreateFileW",HANDLE,[W.LPCWSTR,DWORD,DWORD,LP,DWORD,DWORD,HANDLE])
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


def group_info(h,kind):
    b=get_token_buffer(h,kind)
    n=DWORD.from_buffer(b).value
    assert n<=1024
    if not n:return {}
    assert TokenGroups.Groups.offset+n*C.sizeof(SidAndAttrs)<=len(b)
    groups=(SidAndAttrs*n).from_buffer(b,TokenGroups.Groups.offset)
    return {sid_bytes(x.Sid):int(x.Attributes) for x in groups}


def token_info():
    h=HANDLE()
    if not open_token(get_current(),8,C.byref(h)):raise C.WinError(C.get_last_error())
    try:
        b=get_token_buffer(h,1)
        user=sid_bytes(SidAndAttrs.from_buffer(b).Sid)
        groups=group_info(h,2);restricted=group_info(h,11)
        enabled={sid for sid,flags in groups.items() if flags&4 and not flags&16}
        deny_only={sid for sid,flags in groups.items() if flags&16}
        elevation=DWORD.from_buffer_copy(get_token_buffer(h,20)).value
        info={"restricted":bool(is_restricted(h)),"restricting_sid_count":len(restricted),"elevated":bool(elevation),
              "enabled_group_count":len(enabled),"deny_only_group_count":len(deny_only)}
        return info,set(restricted),user,enabled,deny_only
    finally:close(h)


try:TOKEN,SIDS,USER,ENABLED,DENY_ONLY=token_info()
except Exception as exc:
    TOKEN={"error":type(exc).__name__};SIDS=set();USER=None;ENABLED=set();DENY_ONLY=set()
row("native Windows token","OBSERVED",TOKEN)


def acl_info(p):
    dacl=LP();sd=LP();owner=LP()
    try:
        rc=get_security(str(p),1,5,C.byref(owner),None,C.byref(dacl),None,C.byref(sd))
        if rc:return {"winerror":int(rc)}
        control=W.WORD();revision=DWORD()
        if not get_control(sd,C.byref(control),C.byref(revision)):raise C.WinError(C.get_last_error())
        result={"protected":bool(control.value&0x1000),"auto_inherited":bool(control.value&0x400),"null_dacl":not bool(dacl),"owner_is_token_user":bool(owner and sid_bytes(owner)==USER)}
        if not dacl:return result
        info=AclSize()
        if not get_acl(dacl,C.byref(info),C.sizeof(info),2):raise C.WinError(C.get_last_error())
        result.update(ace_count=info.AceCount,inherited=0)
        masks={k:0 for k in ("normal_allow","normal_deny","user_allow","enabled_group_allow","deny_only_deny","restricted_allow","restricted_deny")}
        def add(k,mask):masks[k]|=mask
        # Only ordinary access-allowed/denied ACEs are classified. Counts
        # are diagnostic, not a substitute for an effective AccessCheck.
        for i in range(info.AceCount):
            ace=LP()
            if not get_ace(dacl,i,C.byref(ace)):raise C.WinError(C.get_last_error())
            header=C.string_at(ace,8);kind,flags=header[:2]
            if flags&0x10:result["inherited"]+=1
            if kind not in (0,1) or flags&8:continue
            mask=int.from_bytes(header[4:8],"little");sid=sid_bytes(ace.value+8)
            if kind==0:
                if sid==USER:add("user_allow",mask);add("normal_allow",mask)
                if sid in ENABLED:add("enabled_group_allow",mask);add("normal_allow",mask)
                if sid in SIDS:add("restricted_allow",mask)
            else:
                if sid==USER or sid in ENABLED or sid in DENY_ONLY:add("normal_deny",mask)
                if sid in DENY_ONLY:add("deny_only_deny",mask)
                if sid in SIDS:add("restricted_deny",mask)
        # These OR masks are explanatory ACE categories, not an AccessCheck.
        result["ace_masks"]={k:hex(v) for k,v in masks.items()}
        result["normal_write_data_ace"]=bool(masks["normal_allow"]&(0x10000000|0x40000000|2))
        result["restricted_write_data_ace"]=bool(masks["restricted_allow"]&(0x10000000|0x40000000|2))
        return result
    except Exception as exc:return {"error":type(exc).__name__,"winerror":getattr(exc,"winerror",None)}
    finally:
        if sd:free(sd)



MATRIX=[("package_root",ROOT),("work",ROOT/"work"),("tmp",ROOT/"tmp"),
        ("tool",ROOT/"tool"),("skills",ROOT/"home/skills"),("outside",ROOT.parent)]
SENTINEL=b"synthetic audit sentinel"


def attributes(p):
    info=p.lstat()
    attrs=info.st_file_attributes
    assert stat.S_ISREG(info.st_mode) and not attrs&0x400 and info.st_nlink==1
    return {"readonly":bool(attrs&1),"attributes_hex":hex(attrs),"size":info.st_size}


if MODE=="host-inspect":
    # Read only metadata of owned synthetic objects after the restricted run;
    # an elevated CI account is explicitly not ordinary-user/sandbox proof.
    for label,p in MATRIX:
        f=p/"sandbox-followup-existing.txt"
        row("host-precreated ACL after native "+label,"OBSERVED",{"attributes":attributes(f),"acl":acl_info(f)})
    for name in ("work/ssh","work/ssh/keys"):
        p=ROOT/name
        row("host read-only SSH directory ACL "+name,"OBSERVED",{"exists":p.exists(),"acl":acl_info(p)})
    raise SystemExit(0)


def configured():
    cfg=tomllib.loads((ROOT/"home/config.toml").read_text(encoding="utf-8-sig"))
    assert cfg["sandbox_mode"]=="workspace-write" and cfg["approval_policy"]=="on-request"
    assert cfg["windows"]["sandbox"]=="unelevated" and cfg["sandbox_workspace_write"]["network_access"] is False
    norm=lambda p:os.path.normcase(os.path.normpath(str(p)))
    actual={norm(x) for x in cfg["sandbox_workspace_write"]["writable_roots"]}
    assert actual==({norm(ROOT)} if MODE=="maintenance" else {norm(ROOT/"work"),norm(ROOT/"tmp")})
    assert TOKEN.get("restricted") is True and TOKEN.get("restricting_sid_count",0)>0 and not TOKEN["elevated"]
    return {"configuration_verified":True,"restricted_token":TOKEN}
case("native restricted token and unchanged launcher policy",configured)


def attempt(fn):
    try:fn();return {"ok":True}
    except OSError as exc:return {"ok":False,"errno":exc.errno,"winerror":getattr(exc,"winerror",None)}
    except Exception as exc:return {"ok":False,"error":type(exc).__name__}


def native_open_flags(p):
    outcomes={}
    for name,mask in (("read",0x80000000),("write_data",2),("generic_write",0x40000000),
                      ("generic_read_write",0xc0000000)):
        C.set_last_error(0)
        h=open_file(str(p),mask,7,None,3,0x80,None)
        if h in (None,LP(-1).value):outcomes[name]={"ok":False,"winerror":C.get_last_error()}
        else:
            assert close(h);outcomes[name]={"ok":True}
    return outcomes


def rw(p):
    with p.open("r+b") as f:
        f.seek(0)
        changed=False
        try:
            assert f.write(b"X")==1;changed=True;f.flush();f.seek(0);assert f.read(1)==b"X"
        finally:
            if changed:f.seek(0);assert f.write(SENTINEL[:1])==1;f.flush()
    assert p.read_bytes()==SENTINEL


def wo(p):
    fd=os.open(p,os.O_WRONLY|os.O_BINARY)
    try:
        changed=False
        try:assert os.write(fd,b"Y")==1;changed=True
        finally:
            if changed:os.lseek(fd,0,os.SEEK_SET);assert os.write(fd,SENTINEL[:1])==1
    finally:os.close(fd)
    assert p.read_bytes()==SENTINEL


def details(p):
    a=attributes(p)
    assert not a["readonly"] and a["size"]==len(SENTINEL),a
    result={"attributes":a,"acl":acl_info(p),"native_open":native_open_flags(p)}
    result["rplus_overwrite"]=attempt(lambda:rw(p))
    result["write_only_overwrite"]=attempt(lambda:wo(p))
    assert p.read_bytes()==SENTINEL,"sentinel content changed"
    return result


# Two independent dimensions: an existing non-readonly host-created file
# and a file actually created by the sandbox, closed and reopened. No
# permissions/ACL/owner or readonly attribute changes, no real user files.
for label,directory in MATRIX:
    allowed=label in {"work","tmp"} or MODE=="maintenance" and label!="outside"
    existing=directory/"sandbox-followup-existing.txt"
    new=directory/"sandbox-followup-new.txt"
    assert existing.read_bytes()==SENTINEL and not new.exists()
    try:
        host=details(existing)
        host["expected_write"]=allowed
        host["directory_acl"]=acl_info(directory)
        ops=[host["rplus_overwrite"],host["write_only_overwrite"],host["native_open"]["write_data"],
             host["native_open"]["generic_write"],host["native_open"]["generic_read_write"]]
        row("host-precreated non-readonly write matrix "+label,
            "PASS_ACTUAL" if all(x["ok"]==allowed for x in ops) else "FAIL",host)
    except Exception:row("host-precreated non-readonly write matrix "+label,"FAIL",traceback.format_exc()[-3000:])
    def create():
        with new.open("xb") as f:assert f.write(SENTINEL)==len(SENTINEL)
        assert new.read_bytes()==SENTINEL
    result={"expected_write":allowed,"create":attempt(create)}
    if new.exists():
        try:result["reopened"]=details(new)
        except Exception:result["reopen_error"]=traceback.format_exc()[-3000:]
        result["delete_created"]=attempt(new.unlink)
    if allowed:
        reopened=result.get("reopened",{})
        success=(result["create"]["ok"] and reopened.get("rplus_overwrite",{}).get("ok")
            and reopened.get("write_only_overwrite",{}).get("ok")
            and all(reopened.get("native_open",{}).get(k,{}).get("ok") for k in ("write_data","generic_write","generic_read_write"))
            and result.get("delete_created",{}).get("ok") and not new.exists())
    else:success=not result["create"]["ok"] and "reopened" not in result and not new.exists()
    row("sandbox-created close/reopen/overwrite/delete matrix "+label,"PASS_ACTUAL" if success else "FAIL",result)


# Actual isolated SSH keygen with the unchanged private-directory policy.
# The host orchestrator will inspect the failed synthetic directory DACL,
# not change it. Never bypass to generate a user's key.
def keygen():
    name="synthetic-native-"+MODE
    p=ROOT/"tool/portable-ssh.py"
    r=subprocess.run([str(PY),"-B",str(p),"keygen","--name",name,"--unencrypted"],cwd=OUT,
                     stdin=subprocess.DEVNULL,capture_output=True,timeout=90)
    result={"returncode":r.returncode,"stderr":r.stderr.decode("utf-8","backslashreplace")[-600:]}
    for d in ("work/ssh","work/ssh/keys"):
        path=ROOT/d;result[d]={"exists":path.exists(),"acl":acl_info(path)}
    if r.returncode==0:
        import paramiko
        key=ROOT/"work/ssh/keys"/name;pub=key.with_suffix(".pub")
        assert paramiko.Ed25519Key.from_private_key_file(str(key)).get_name()=="ssh-ed25519"
        assert pub.read_text().startswith("ssh-ed25519 ")
        key.unlink();pub.unlink();result["actual_readback"]=True
    row("SSH actual unchanged private-directory keygen","PASS_ACTUAL" if result.get("actual_readback") else "FAIL",result)
try:keygen()
except Exception:row("SSH actual unchanged private-directory keygen","FAIL",traceback.format_exc()[-3000:])


# Same fixed native tools; only one normal-mode contrast, no repeat of
# prior three-mode relative successes / network / Office / course cases.
def run(rel,*args,cwd=OUT):
    p=ROOT/rel;assert p.is_file() and p.resolve().is_relative_to(ROOT)
    a=[str(x) for x in args]
    if p.suffix.lower()==".cmd":
        cmd=WIN/"System32/cmd.exe"
        argv=str(cmd)+' /d /s /c "'+subprocess.list2cmdline([str(p),*a])+'"';exe=str(cmd)
    else:argv=[str(p),*a];exe=str(p)
    r=subprocess.run(argv,executable=exe,cwd=cwd,stdin=subprocess.DEVNULL,capture_output=True,timeout=120)
    return {"returncode":r.returncode,"stdout":r.stdout.decode("utf-8","backslashreplace")[-700:],
            "stderr":r.stderr.decode("utf-8","backslashreplace")[-700:]}


def inputs(group,extension):
    # Separate fresh directories: all paths under the owned moved package.
    for name,filename,absolute in (("ascii-relative","sample"+extension,False),
          ("chinese-relative","\u4e2d\u6587"+extension,False),
          ("space-relative","two words"+extension,False),
          ("absolute-chinese-space","sample"+extension,True)):
        d=OUT/group/name;d.mkdir(parents=True)
        p=d/filename
        yield name,d,p,str(p) if absolute else p.name


def f2py():
    from numpy.f2py.f2py2e import get_newer_options
    proof=get_newer_options(["-m","sample","with space.f90"])[2]
    assert "with space.f90" not in proof and "with" in proof and "space.f90" in proof
    row("fixed NumPy actual argument parser split","OBSERVED",{"space_argument_split":True})
    control=False
    for name,d,src,arg in inputs("f2py",".f90"):
        src.write_text("subroutine addone(x)\nreal :: x\nx=x+1\nend subroutine addone\n",encoding="ascii")
        results={}
        for entry in ("direct-module","portable-cmd"):
            out=d/(entry+".pyf")
            args=["-m","sample","-h",out.name,arg]
            if entry=="direct-module":r=run("tool/python/python.exe","-B","-m","numpy.f2py",*args,cwd=d)
            else:r=run("tool/bin/f2py.cmd",*args,cwd=d)
            r["signature_verified"]=bool(r["returncode"]==0 and out.is_file() and "addone" in out.read_text(encoding="utf-8",errors="replace").lower())
            results[entry]=r
        actual=[r["signature_verified"] for r in results.values()]
        if name=="ascii-relative":control=all(actual)
        status="PASS_ACTUAL" if all(actual) else "KNOWN_LIMIT" if control and not any(actual) and name in ("space-relative","absolute-chinese-space") else "FAIL"
        row("f2py direct versus wrapper "+name,status,results)


def android_sqlite():
    control=False
    for name,d,db,arg in inputs("android-sqlite",".sqlite"):
        r=run("tool/android/platform-tools/sqlite3.exe",arg,
              "create table t(v); insert into t values(7); select v*3 from t;",cwd=d)
        r["database_verified"]=False
        if r["returncode"]==0 and db.is_file():
            try:
                with sqlite3.connect(db) as c:r["database_verified"]=c.execute("select v from t").fetchone()==(7,) and r["stdout"].strip()=="21"
            except sqlite3.Error:pass
        r["actual_files"]=sorted(x.name for x in d.iterdir())
        if name=="ascii-relative":control=r["database_verified"]
        status="PASS_ACTUAL" if r["database_verified"] else "OBSERVED_PATH_FAILURE" if control and name in ("chinese-relative","absolute-chinese-space") else "FAIL"
        row("direct bundled Android sqlite3 "+name,status,r)


def android_etc():
    from PIL import Image
    control=False
    for name,d,src,arg in inputs("android-etc",".png"):
        Image.new("RGB",(8,8),(10,30,50)).save(src)
        if name=="chinese-relative":pkm=d/"\u4e2d\u6587.pkm";decoded=d/"\u89e3\u7801.png"
        elif name=="space-relative":pkm=d/"two words.pkm";decoded=d/"decode words.png"
        else:pkm=d/"sample.pkm";decoded=d/"decoded.png"
        absolute=name=="absolute-chinese-space"
        pkmarg=str(pkm) if absolute else pkm.name;decarg=str(decoded) if absolute else decoded.name
        enc=run("tool/android/platform-tools/etc1tool.exe",arg,"-o",pkmarg,cwd=d)
        result={"encode":enc,"encoded_exact_path":pkm.is_file(),"image_verified":False}
        if enc["returncode"]==0 and pkm.is_file():
            dec=run("tool/android/platform-tools/etc1tool.exe",pkmarg,"--decode","-o",decarg,cwd=d);result["decode"]=dec
            if dec["returncode"]==0 and decoded.is_file():
                try:
                    with Image.open(decoded) as im:
                        pix=im.convert("RGB").getpixel((0,0))
                        result["image_verified"]=im.size==(8,8) and all(abs(a-b)<=35 for a,b in zip(pix,(10,30,50)))
                except OSError:pass
        result["actual_files"]=sorted(x.name for x in d.iterdir())
        if name=="ascii-relative":control=result["image_verified"]
        status="PASS_ACTUAL" if result["image_verified"] else "OBSERVED_PATH_FAILURE" if control and name in ("chinese-relative","absolute-chinese-space") else "FAIL"
        row("direct bundled Android etc1tool "+name,status,result)


def httpx_cli():
    md=importlib.metadata.metadata("httpx")
    requirements=[s for s in md.get_all("Requires-Dist") if "extra == 'cli'" in s or 'extra == "cli"' in s]
    versions={}
    for name in ("httpx","rich","click","pygments"):
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]=None
    r=run("tool/bin/httpx.cmd","--help")
    expected=versions["httpx"]=="0.28.1" and versions["rich"]=="15.0.0" and versions["click"] is None and any("rich" in x and "<14" in x for x in requirements)
    result={"versions":versions,"cli_requires":requirements,"actual_help":r}
    if r["returncode"]!=0 and "httpx[cli]" in r["stdout"]+r["stderr"] and expected:status="KNOWN_LIMIT"
    elif r["returncode"]==0 and "Usage" in r["stdout"]:status="OBSERVED"
    else:status="FAIL"
    row("fixed HTTPX CLI optional dependency refusal",status,result)


def path_priority():
    p=shutil.which("rg.exe")
    assert p and Path(p).resolve()==(ROOT/"codex-path/rg.exe").resolve()
    assert (ROOT/"tool/bin/rg.exe").is_file()
    return "PATH identity only in this batch; actual two rg content probes already passed 45741929384"
if MODE=="normal":
    for fn in (f2py,android_sqlite,android_etc,httpx_cli):
        try:fn()
        except Exception:row(fn.__name__+" targeted harness","FAIL",traceback.format_exc()[-3000:])
    case("fixed rg PATH priority identity",path_priority)
print("PORTABLE_RELEASE_FULL_CONSUMER_DONE",flush=True)
