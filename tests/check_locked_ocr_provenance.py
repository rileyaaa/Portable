"""Read-only provenance research on the same 49 frozen MSYS2 archives.

Linux CI's GnuPG/tar are verification tools, not Windows OCR runtime payload.
No package installation, source execution, mutable keyserver or customer upload.
"""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import traceback
import urllib.parse
import urllib.request
import uuid

ROOT=Path(__file__).absolute().parents[1]
REPORT=Path(sys.argv[1]).absolute()
assert sys.platform=="linux" and os.environ["GITHUB_REPOSITORY"]=="rileyaaa/Portable"
assert os.environ["GITHUB_REF"]=="refs/heads/dev/stable-tool-refresh"
PRIOR=json.loads((ROOT/"tests/fixed_seed_f2py_ocr_45749259260.json").read_bytes())
LOCK=PRIOR["ocr_feasibility"]
assert len(LOCK["package_lock"])==49 and LOCK["unresolved_pe_imports"]==["xmllite.dll"]
RUNTIME={x["owner"] for x in LOCK["runtime_closure"]}
MODEL="mingw-w64-ucrt-x86_64-tesseract-data-chi_sim"
KEY_COMMIT="5d249077a0cfeec9dbf51515e5e01da413d28859"
KEY_FILES={"msys2.gpg":"7be83b5cc7bc69003ad9cc76ce65b4314c0b71a1",
    "master-keyids":"cba8db8754fb6d11c66823e897d3ab85c5f75bd8",
    "packager-keyids":"e199deef02285a445a8f600d85cbf74afdfd435b",
    "msys2-revoked":"38db966082240362b21a1cd1e66d6dc50d67f34d"}
KEY_PREFIX="https://raw.githubusercontent.com/msys2/MSYS2-keyring/"+KEY_COMMIT+"/"
REPO="https://repo.msys2.org/mingw/"
GPG=Path("/usr/bin/gpg")
TAR=Path("/usr/bin/tar")
OUT={"source_commit":os.environ["GITHUB_SHA"],"prior_run":"45749259260","prior_record":"eb7a10c6423078e3b1a8764149089685494f14b7",
     "prior_repository_snapshot_sha256":LOCK["repository_snapshot_sha256"],"scope":"Linux CI provenance only; not Windows runtime or distribution",
     "keyring":{"repository":"msys2/MSYS2-keyring","commit":KEY_COMMIT,"files":KEY_FILES},
     "packages":[],"sources":[],"rows":[],"completed":False,"distribution_qualified":False,
     "limitations":["Publisher keyring pinned to official repository commit, not an independently audited root-of-trust ceremony.",
       "Detached signatures checked only against pinned current allowlist and revocation list; no auto key retrieval.",
       "Source archive inspection is not reproducible binary build or complete legal review.",
       "Only actual runtime/model owners have source bytes downloaded where size limits permit; all 49 source endpoints checked.",
       "No archives, keys, licenses or binaries are copied into customer payload; no installation or execution of package scripts."]}
SOURCE_CAP=512*1024*1024
SINGLE_SOURCE_CAP=128*1024*1024


def save():
    REPORT.write_text(json.dumps(OUT,ensure_ascii=True,indent=2)+"\n",encoding="utf-8")


def row(item,status,detail=None):
    OUT["rows"].append({"item":item,"status":status,"detail":detail});save()
    print("OCR_PROVENANCE="+json.dumps({"item":item,"status":status},ensure_ascii=True),flush=True)


def allowed_url(url):
    q=urllib.parse.urlsplit(url)
    assert q.scheme=="https" and q.port in (None,443) and not q.username and not q.password and not q.query and not q.fragment
    assert (q.hostname=="repo.msys2.org" and q.path.startswith("/mingw/")) or (q.hostname=="raw.githubusercontent.com" and url.startswith(KEY_PREFIX))


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        allowed_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}),Redirect())


def request(url,method="GET"):
    allowed_url(url)
    return OPENER.open(urllib.request.Request(url,method=method,headers={"User-Agent":"Portable-pinned-OCR-provenance"}),timeout=40)


def download(url,path,maximum,expected=None,size=None):
    assert not path.exists() and path.parent.is_dir()
    h=hashlib.sha256();n=0
    try:
        with request(url) as resp,path.open("xb") as f:
            allowed_url(resp.geturl())
            while True:
                block=resp.read(1024*1024)
                if not block:break
                n+=len(block);assert n<=maximum,"download size cap";f.write(block);h.update(block)
        if expected is not None:assert h.hexdigest()==expected,"frozen archive SHA256 mismatch"
        if size is not None:assert n==size,"frozen archive size mismatch"
        return {"sha256":h.hexdigest(),"size":n}
    except BaseException:
        path.unlink(missing_ok=True);raise


def head(url):
    try:
        with request(url,"HEAD") as r:
            allowed_url(r.geturl())
            return {"status":r.status,"size":int(r.headers["Content-Length"]) if r.headers.get("Content-Length","").isdigit() else None}
    except Exception as e:return {"status":getattr(e,"code",None),"error":type(e).__name__}


def git_blob(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode("ascii")+b"\0"+data,usedforsecurity=False).hexdigest()


def keyring(base):
    assert GPG.is_file() and TAR.is_file()
    keydir=base/"keys";keydir.mkdir(mode=0o700)
    home=base/"gnupg";home.mkdir(mode=0o700)
    for name,sha in KEY_FILES.items():
        p=keydir/name
        download(KEY_PREFIX+name,p,256*1024)
        assert git_blob(p.read_bytes())==sha,name
    allow={line.split()[0].upper() for n in ("master-keyids","packager-keyids") for line in (keydir/n).read_text().splitlines() if line.strip()}
    revoked={line.strip().upper() for line in (keydir/"msys2-revoked").read_text().splitlines() if line.strip()}
    assert all(re.fullmatch("[0-9A-F]{40}",x) for x in allow|revoked) and not allow&revoked
    env={"PATH":"/usr/bin:/bin","LANG":"C","LC_ALL":"C","HOME":str(base),"GNUPGHOME":str(home),"TMPDIR":str(base)}
    args=[str(GPG),"--homedir",str(home),"--batch","--no-tty","--no-auto-key-retrieve","--no-auto-key-import","--status-fd","1"]
    r=subprocess.run(args+["--import",str(keydir/"msys2.gpg")],env=env,capture_output=True,timeout=60)
    assert r.returncode==0,("pinned keyring import",r.returncode,r.stderr.decode("utf-8","replace")[-500:])
    OUT["keyring"].update(allowed_primary_fingerprints=sorted(allow),revoked_primary_fingerprints=sorted(revoked),
        gpg_version=subprocess.check_output([str(GPG),"--version"],env=env,text=True).splitlines()[0])
    row("pinned official keyring bytes and allow/revoke lists","PASS_ACTUAL",len(allow))
    return args,env,allow,revoked


def verify(keys,signature,data):
    args,env,allow,revoked=keys
    r=subprocess.run(args+["--verify",str(signature),str(data)],env=env,capture_output=True,timeout=60)
    lines=[x[9:].split() for x in r.stdout.decode("utf-8","replace").splitlines() if x.startswith("[GNUPG:] ")]
    valid=[x for x in lines if x and x[0]=="VALIDSIG"]
    forbidden={"BADSIG","ERRSIG","NO_PUBKEY","EXPSIG","EXPKEYSIG","REVKEYSIG","KEYREVOKED","SIGEXPIRED","KEYEXPIRED","FAILURE"}
    flags={x[0] for x in lines if x}
    signing=valid[0][1].upper() if len(valid)==1 and len(valid[0])>=2 else None
    primary=valid[0][-1].upper() if len(valid)==1 and len(valid[0])>=11 and re.fullmatch("[0-9A-Fa-f]{40}",valid[0][-1]) else signing
    ok=r.returncode==0 and len(valid)==1 and primary in allow and primary not in revoked and signing not in revoked and not flags&forbidden
    return {"verified":bool(ok),"returncode":r.returncode,"signing_fingerprint":signing,"primary_fingerprint":primary,
        "status_flags":sorted(flags),"signature_sha256":hashlib.sha256(signature.read_bytes()).hexdigest()}


def name_safe(s):
    return bool(re.fullmatch(r"[A-Za-z0-9_.+~-]+",s))


def obligation(rec,files,used):
    labels=" ".join(rec["archive_pkginfo_license"]+rec["licenses"]).lower()
    hints=[]
    if not used:return ["Not in the frozen PE/model runtime set; no customer distribution proposed. If later included, review its exact license/source independently."]
    if "gpl" in labels:
        hints.append("Copyleft/GCC exception/mixed-license components require file-level terms and corresponding-source, notices and applicable linking/relinking obligations; package label alone does not establish compatibility.")
    if any(x in labels for x in ("apache","bsd","mit","zlib","icu","cc0","public domain")):
        hints.append("Retain applicable copyright/license text, NOTICE and attribution; verify actual selected-file license, modifications and exceptions.")
    if "custom" in labels or not labels.strip():hints.append("Custom/ambiguous metadata: read actual upstream license and selected-file headers.")
    if not rec["notice_files"]:hints.append("No selected archive notice found; recover exact notices from corresponding source/upstream before distribution.")
    if rec["name"].endswith("-jbigkit"):
        hints.append("JBIG-KIT is GPL-licensed and author states linking combined-work terms; exact 2.1 file terms and compatibility must be reviewed; remove this unneeded image-format dependency in a reduced local PNG build rather than assuming permission.")
    if rec["name"]==MODEL:
        hints.append("Model is distinct Apache-2.0 asset; retain matching model license and notices from pinned tessdata_fast upstream.")
    return hints or ["Review exact source and selected-file terms; no blanket approval."]


def package(base,keys,rec):
    name=rec["name"];filename=rec["filename"]
    assert name_safe(name) and name_safe(filename) and rec["url"]==REPO+"ucrt64/"+filename
    p=base/filename;s=base/(filename+".sig")
    files=[x["file"] for x in LOCK["runtime_closure"] if x["owner"]==name]
    used=name in RUNTIME or name==MODEL
    result={"name":name,"version":rec["version"],"url":rec["url"],"locked_sha256":rec["sha256"],
       "runtime_pe_files":files,"model_asset":name==MODEL,"in_static_runtime_or_model":used,
       "license_metadata":rec["licenses"],"archive_pkginfo_license":rec["archive_pkginfo_license"],
       "prior_verified_notice_files":rec["notice_files"],"pkgbase":rec["pkgbase"],
       "obligation_review":obligation(rec,files,used),"redistribution_approved":False}
    try:
        result["archive"]=download(rec["url"],p,100*1024*1024,rec["sha256"],rec["compressed_size"])
        result["detached_signature"]=download(rec["url"]+".sig",s,128*1024)
        result["signature_verification"]=verify(keys,s,p)
        result["status"]="PASS_SIGNATURE" if result["signature_verification"]["verified"] else "BLOCKED_SIGNATURE"
    except Exception as e:result.update(status="BLOCKED_ARCHIVE_OR_SIGNATURE",error=type(e).__name__+":"+str(e)[:300])
    finally:p.unlink(missing_ok=True);s.unlink(missing_ok=True)
    return result


def source_groups():
    groups={}
    for rec in LOCK["package_lock"]:
        base=rec["pkgbase"];version=rec["version"].split(":")[-1]
        assert name_safe(base) and name_safe(version)
        key=base+"-"+version
        g=groups.setdefault(key,{"pkgbase":base,"version":version,"packages":[],"runtime_required":False})
        g["packages"].append(rec["name"]);g["runtime_required"]|=rec["name"] in RUNTIME or rec["name"]==MODEL
    return sorted(groups.items(),key=lambda x:(not x[1]["runtime_required"],x[0]))


def source(base,keys,key,g,remaining):
    url=REPO+"sources/"+key+".src.tar.zst"
    result={**g,"url":url,"head":head(url),"signature_head":head(url+".sig"),"corresponding_source_complete":False}
    n=result["head"].get("size")
    if result["head"].get("status")!=200:result["status"]="SOURCE_ENDPOINT_UNAVAILABLE";return result,0
    if not g["runtime_required"]:result["status"]="SOURCE_ENDPOINT_ONLY_NOT_RUNTIME";return result,0
    if not n or n>min(remaining,SINGLE_SOURCE_CAP):result["status"]="SOURCE_SIZE_OR_BUDGET_BLOCKED";return result,0
    p=base/(key+".src.tar.zst");sig=base/(key+".src.tar.zst.sig")
    used=0
    try:
        result["archive"]=download(url,p,min(remaining,SINGLE_SOURCE_CAP),size=n);used=result["archive"]["size"]
        result["detached_signature"]=download(url+".sig",sig,128*1024)
        result["signature_verification"]=verify(keys,sig,p)
        if not result["signature_verification"]["verified"]:
            result["status"]="SOURCE_SIGNATURE_BLOCKED";return result,used
        # Do not extract or execute sources. Inspect signed archive member
        # names and exact build-recipe bytes with independent Linux CI tar.
        r=subprocess.run([str(TAR),"--zstd","-tf",str(p)],env=keys[1],capture_output=True,timeout=100,check=True)
        assert len(r.stdout)<=16*1024*1024,"source member list cap"
        names=r.stdout.decode("utf-8","strict").splitlines()
        assert len(names)<=100000
        recipes=[x for x in names if x.rsplit("/",1)[-1]=="PKGBUILD"]
        assert all(not x.startswith("/") and ".." not in x.split("/") and "\x00" not in x for x in recipes)
        recipe_hash=[]
        for name in recipes[:8]:
            data=subprocess.check_output([str(TAR),"--zstd","-xOf",str(p),"--",name],env=keys[1],timeout=100)
            assert len(data)<=2*1024*1024
            recipe_hash.append({"path":name,"sha256":hashlib.sha256(data).hexdigest()})
        result["source_archive_member_count"]=len(names)
        result["recipes"]=recipe_hash
        result["source_payload_names"]=[x for x in names if re.search(r"\.(?:tar\.(?:gz|xz|bz2|zst)|tgz|zip|patch|diff)$",x,re.I)][:80]
        result["license_notice_names"]=[x for x in names if re.search(r"(?:^|/)(?:COPYING|LICENSE|NOTICE)(?:[._-][^/]*)?$",x,re.I)][:40]
        result["status"]="SOURCE_SIGNED_ARCHIVE_INSPECTED" if recipe_hash else "SOURCE_SIGNED_NO_RECIPE_IDENTIFIED"
    except Exception as e:result.update(status="SOURCE_CHECK_BLOCKED",error=type(e).__name__+":"+str(e)[:400])
    finally:p.unlink(missing_ok=True);sig.unlink(missing_ok=True)
    return result,used


def main():
    base=ROOT/"tmp"/("ocr-provenance-"+uuid.uuid4().hex)
    base.parent.mkdir(exist_ok=True);base.mkdir(mode=0o700)
    try:
        keys=keyring(base);archives=base/"archives";archives.mkdir()
        # Sequential GnuPG access to the same isolated homedir avoids locks.
        for rec in LOCK["package_lock"]:
            result=package(archives,keys,rec);OUT["packages"].append(result);save()
            print("PACKAGE "+rec["name"]+" "+result["status"],flush=True)
        verified=sum(x["status"]=="PASS_SIGNATURE" for x in OUT["packages"])
        row("49 fixed binary archive signatures against official pinned allowlist",
            "PASS_ACTUAL" if verified==49 else "BLOCKED_SIGNATURE",{"verified":verified,"total":49})
        budget=SOURCE_CAP
        for key,g in source_groups():
            result,used=source(archives,keys,key,g,budget);budget-=used
            OUT["sources"].append(result);save()
            print("SOURCE "+key+" "+result["status"],flush=True)
        actual=[x for x in OUT["sources"] if x["runtime_required"]]
        inspected=sum(x["status"]=="SOURCE_SIGNED_ARCHIVE_INSPECTED" for x in actual)
        row("corresponding source archive availability and actual signed archive inspection",
            "OBSERVED",{"all_source_groups":len(OUT["sources"]),"runtime_source_groups":len(actual),
                "runtime_signed_inspected":inspected,"downloaded_source_bytes":SOURCE_CAP-budget})
        row("redistribution qualification","BLOCKED_REVIEW",
            "Need exact selected-file license/NOTICE coverage, complete corresponding sources and license compatibility, no distribution from research.")
    except Exception:row("provenance research","FAIL_OR_BLOCKED",traceback.format_exc()[-6000:])
    finally:shutil.rmtree(base);OUT["completed"]=True;OUT["scratch_removed"]=not base.exists();save()
    return int(not (len(OUT["packages"])==49 and all(x["status"]=="PASS_SIGNATURE" for x in OUT["packages"])))


if __name__=="__main__":
    raise SystemExit(main())
