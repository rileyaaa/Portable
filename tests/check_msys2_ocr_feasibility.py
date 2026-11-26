"""MSYS2 UCRT64 OCR feasibility only. No install, release, or customer payload."""
import csv
import ctypes as C
from ctypes import wintypes as W
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import time
import traceback
import urllib.request
import urllib.parse
import uuid
import pefile
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).absolute().parents[1]
REPORT=Path(sys.argv[1]).absolute()
assert os.name=="nt" and os.environ["GITHUB_REPOSITORY"]=="rileyaaa/Portable"
assert os.environ["GITHUB_REF"]=="refs/heads/dev/stable-tool-refresh"
assert Path(sys.executable).resolve()==(ROOT/"tool/python/python.exe").resolve()
PREFIX="mingw-w64-ucrt-x86_64-"
REPO="https://repo.msys2.org/mingw/ucrt64/"
PINS={
    PREFIX+"tesseract-ocr":("5.5.4-1","a38f3f00d23ff9e05f2e6df87a65ec7f10b6735b131548e87aa15016a79538b2"),
    PREFIX+"tesseract-data-chi_sim":("4.1.0-3","a618b5e820ae86c600d68ee93295873a3b73ea2a471c8d15d2a59dc8313c45f1")
}
PROVIDERS={PREFIX+"omp":PREFIX+"libgomp"}
OUT={"source_commit":os.environ["GITHUB_SHA"],"source_repository":REPO,"pins":PINS,"scope":"isolated feasibility, not approved for redistribution",
     "rows":[],"package_lock":[],"runtime_closure":[],"qualified_for_distribution":False,"completed":False,
     "limitations":["No install or customer runtime change; only synthetic image.",
        "HTTPS publisher database SHA256 lock, not independently verified OpenPGP signatures.",
        "License metadata, extracted notice hashes and source availability are evidence, not completed redistribution legal review.",
        "Runtime module sampling is not exhaustive system write/network tracing. No runtime external OCR service.",
        "No language installation, no fallback to preinstalled MSYS2 or other third-party DLLs."]}


def save():
    REPORT.write_text(json.dumps(OUT,ensure_ascii=True,indent=2)+"\n",encoding="utf-8")


def row(item,status,detail=None):
    OUT["rows"].append({"item":item,"status":status,"detail":detail});save()
    print("OCR_FEASIBILITY="+json.dumps({"item":item,"status":status},ensure_ascii=True),flush=True)


def digest(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()


def ordinary(p,directory=False):
    import stat
    s=p.lstat()
    assert not s.st_file_attributes&0x400 and not stat.S_ISLNK(s.st_mode),str(p)
    assert stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode) and s.st_nlink==1,str(p)


def ancestors(p):
    for q in (*reversed(p.parents),p):ordinary(q,True)


class RestrictedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        safe_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def safe_url(url):
    p=urllib.parse.urlsplit(url)
    assert p.scheme=="https" and p.hostname=="repo.msys2.org" and p.port in (None,443) and not p.username and not p.password
    assert p.path.startswith("/mingw/") and not p.query and not p.fragment


OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}),RestrictedRedirect())
def download(url,target,maximum,sha=None,size=None):
    safe_url(url);ancestors(target.parent);assert not target.exists()
    request=urllib.request.Request(url,headers={"User-Agent":"Portable-OCR-isolated-feasibility"})
    h=hashlib.sha256();n=0
    with OPENER.open(request,timeout=60) as response,target.open("xb") as out:
        safe_url(response.geturl())
        while True:
            b=response.read(1024*1024)
            if not b:break
            n+=len(b);assert n<=maximum,"download limit";out.write(b);h.update(b)
    ordinary(target)
    if size is not None:assert n==size,(target.name,n,size)
    if sha is not None:assert h.hexdigest()==sha,"publisher SHA mismatch "+target.name
    return h.hexdigest()


def sections(raw):
    out={}
    for block in raw.decode("utf-8").strip().split("\n\n"):
        lines=block.splitlines()
        if not lines:continue
        assert re.fullmatch(r"%[A-Z0-9_]+%",lines[0]),lines[0]
        key=lines[0][1:-1];assert key not in out
        out[key]=lines[1:]
    return out


def one(rec,key,default=None):
    v=rec.get(key)
    if v is None:return default
    assert len(v)==1,(key,v)
    return v[0]


def database(path):
    packages={}
    with tarfile.open(path,"r:*") as tar:
        for entry in tar:
            if not entry.isfile() or not entry.name.endswith("/desc"):continue
            assert entry.size<=100000
            rec=sections(tar.extractfile(entry).read())
            name=one(rec,"NAME")
            if name and name.startswith(PREFIX):
                assert name not in packages
                packages[name]=rec
    return packages


def resolve(packages):
    selected={};todo=list(PINS);edges=[]
    for name,(version,sha) in PINS.items():
        r=packages[name]
        assert one(r,"VERSION")==version and one(r,"SHA256SUM")==sha,"root pin no longer in publisher snapshot"
    while todo:
        name=todo.pop()
        if name in selected:continue
        assert name.startswith(PREFIX) and name in packages,"unresolved UCRT64 package "+name
        rec=packages[name]
        version=one(rec,"VERSION");filename=one(rec,"FILENAME");sha=one(rec,"SHA256SUM");size=int(one(rec,"CSIZE"))
        assert re.fullmatch(r"[A-Za-z0-9_.+~-]+\.pkg\.tar\.(?:zst|xz)",filename) and filename.startswith(name+"-")
        assert re.fullmatch("[0-9a-f]{64}",sha) and 0<size<=100*1024*1024
        # Keep publisher's exact snapshot versions and digests before downloading
        # any archive. Only exact package names or a unique declared provider.
        selected[name]={"name":name,"version":version,"filename":filename,"sha256":sha,"compressed_size":size,
          "url":REPO+filename,"base":one(rec,"BASE",name),"licenses":rec.get("LICENSE",[]),
          "depends":rec.get("DEPENDS",[]),"publisher_signature_present":bool(rec.get("PGPSIG")),
          "publisher_homepage":one(rec,"URL","")}
        assert len(selected)<=70,"closure exceeds research bound"
        for dep in rec.get("DEPENDS",[]):
            match=re.fullmatch(r"([A-Za-z0-9_.+~-]+)(?:(>=|<=|=|>|<)([^\s]+))?",dep);assert match,dep
            wanted,op,version_wanted=match.groups()
            if wanted in packages:chosen=wanted
            else:
                choices=[n for n,r in packages.items() if any(p.split("=")[0]==wanted for p in r.get("PROVIDES",[]))]
                chosen=PROVIDERS.get(wanted)
                if chosen is None and len(choices)==1:chosen=choices[0]
                assert chosen in choices,("unresolved provider",wanted,choices)
            if op:
                val=one(packages[chosen],"VERSION")
                if chosen!=wanted:
                    vals=[x.split("=",1)[1] for x in packages[chosen].get("PROVIDES",[]) if x.startswith(wanted+"=")]
                    assert len(vals)==1,("versioned virtual dependency",dep)
                    val=vals[0]
                if op=="=":assert val==version_wanted,(dep,val)
                else:
                    # Conservative version check: only ordinary numeric dotted
                    # versions and numeric release. Ambiguous pacman ordering
                    # stops this probe, never silently selects a replacement.
                    assert re.fullmatch(r"\d+(?:\.\d+)*(?:-\d+)?",val) and re.fullmatch(r"\d+(?:\.\d+)*(?:-\d+)?",version_wanted),(dep,val)
                    def parts(s):
                        v,sep,rel=s.partition("-")
                        nums=tuple(map(int,v.split(".")))
                        return nums+(0,)*(8-len(nums)),int(rel or 0)
                    a,b=parts(val),parts(version_wanted)
                    if "-" not in version_wanted:a,b=a[0],b[0]
                    assert {">=":a>=b,"<=":a<=b,">":a>b,"<":a<b}[op],(dep,val)
            edges.append({"from":name,"requirement":dep,"selected":chosen})
            todo.append(chosen)
    assert sum(x["compressed_size"] for x in selected.values())<=300*1024*1024,"compressed closure over 300 MiB"
    return selected,edges


def safe_member(name):
    while name.startswith("./"):name=name[2:]
    name=name.rstrip("/")
    parts=name.split("/")
    assert name and all(x and x not in (".","..") and not x.endswith((" ",".")) and not re.search(r'[<>:"\\|?*\x00-\x1f]',x) for x in parts),name
    assert all(not re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?",x) for x in parts),name
    return name


def extract_package(archive,rec,destination,inventory):
    licenses=[];pkginfo=None;files={}
    ancestors(destination);seen=set()
    with tarfile.open(archive,"r:*") as tar:
        for e in tar:
            if e.isdir() and e.name.rstrip('/') in ('','.'):continue
            name=safe_member(e.name);low=name.casefold()
            if e.isdir():continue
            select=(name==".PKGINFO" or
                name.startswith("ucrt64/bin/") and name.count("/")==2 and (low.endswith(".dll") or low=="ucrt64/bin/tesseract.exe") or
                name=="ucrt64/share/tessdata/chi_sim.traineddata" or
                name=="ucrt64/share/tessdata/configs/tsv" or
                name.startswith("ucrt64/share/licenses/"))
            if not select:continue
            assert e.isfile() and low not in seen and 0<=e.size<=150*1024*1024,("unsafe selected member",name)
            seen.add(low)
            raw=tar.extractfile(e).read()
            assert len(raw)==e.size
            if name==".PKGINFO":
                pkginfo={}
                for line in raw.decode("utf-8").splitlines():
                    if " = " in line:
                        k,v=line.split(" = ",1);pkginfo.setdefault(k,[]).append(v)
                continue
            p=destination/name;p.parent.mkdir(parents=True,exist_ok=True);ancestors(p.parent)
            with p.open("xb") as out:out.write(raw)
            ordinary(p);sha=digest(p);files[name]=sha
            if name.startswith("ucrt64/share/licenses/"):
                licenses.append({"path":name,"sha256":sha,"size":len(raw)})
            elif name.startswith("ucrt64/bin/"):
                key=p.name.casefold()
                assert key not in inventory,("duplicate PE filename",key)
                inventory[key]=(p,rec["name"],sha)
    assert pkginfo and pkginfo.get("pkgname")==[rec["name"]] and pkginfo.get("pkgver")==[rec["version"]],("archive PKGINFO mismatch",rec["name"])
    assert sorted(pkginfo.get("depend",[]))==sorted(rec["depends"]),("archive dependency metadata mismatch",rec["name"])
    rec["archive_pkginfo_license"]=pkginfo.get("license",[])
    rec["notice_files"]=licenses
    rec["selected_archive_members"]=files
    rec["pkgbase"]=pkginfo.get("pkgbase",[rec["base"]])[0]
    # Source-only URL is checked separately for owners of actual loaded PEs.
    return destination


SYSTEM_NAMES=set("""kernel32.dll kernelbase.dll ntdll.dll advapi32.dll bcrypt.dll bcryptprimitives.dll
crypt32.dll cryptbase.dll user32.dll gdi32.dll gdi32full.dll shell32.dll ole32.dll oleaut32.dll
ws2_32.dll secur32.dll rpcrt4.dll shlwapi.dll iphlpapi.dll normaliz.dll version.dll winmm.dll
msvcrt.dll ucrtbase.dll dnsapi.dll psapi.dll setupapi.dll cfgmgr32.dll wintrust.dll mswsock.dll
powrprof.dll dbghelp.dll imm32.dll winhttp.dll netapi32.dll wldap32.dll comdlg32.dll
comctl32.dll mpr.dll dwrite.dll dwmapi.dll userenv.dll winspool.drv ncrypt.dll
cryptnet.dll propsys.dll shcore.dll cabinet.dll wininet.dll api-ms-win-crt-runtime-l1-1-0.dll""".split())
WIN=Path(os.environ["SystemRoot"]).resolve()
SYSTEM=WIN/"System32"


def is_system(name):
    if name.startswith(("api-ms-win-","ext-ms-win-")):return bool(re.fullmatch(r"(?:api|ext)-ms-win-[a-z0-9-]+\.dll",name))
    return name in SYSTEM_NAMES and (SYSTEM/name).is_file()


def closure(inventory,bin_dir):
    todo=["tesseract.exe"];done={};missing=[];system=set()
    while todo:
        name=todo.pop().casefold()
        if name in done or name in system:continue
        if name not in inventory:
            if is_system(name):system.add(name);continue
            missing.append(name);continue
        path,owner,sha=inventory[name]
        pe=pefile.PE(str(path),fast_load=True)
        try:
            assert pe.FILE_HEADER.Machine==0x8664,("not x64",name)
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"]])
            imports=sorted({x.dll.decode("ascii").casefold() for k in ("DIRECTORY_ENTRY_IMPORT","DIRECTORY_ENTRY_DELAY_IMPORT") for x in getattr(pe,k,[])})
            assert all(re.fullmatch(r"[a-z0-9_.+-]+\.(?:dll|drv)",x) for x in imports)
        finally:pe.close()
        done[name]={"file":name,"owner":owner,"sha256":sha,"imports_and_delay_imports":imports}
        todo.extend(imports)
    OUT["runtime_closure"]=list(done.values());OUT["system_imports"]=sorted(system);OUT["unresolved_pe_imports"]=sorted(set(missing));save()
    assert not missing,("unresolved PE imports",sorted(set(missing)))
    for name,rec in done.items():
        path,_,sha=inventory[name];p=bin_dir/name
        assert not p.exists();shutil.copyfile(path,p);ordinary(p);assert digest(p)==sha
    row("native x64 static import and delay-import DLL closure","PASS_ACTUAL",{"files":len(done),"system_contracts":len(system)})
    return done


def source_inventory(selected,owners):
    # The package label alone is not a license grant for every linked object.
    # Retain actual notice hashes and source URLs; do not declare redistribution.
    evidence=[]
    for name in sorted(owners|set(PINS)):
        r=selected[name]
        base=r["pkgbase"];version=r["version"].split(":")[-1]
        assert re.fullmatch(r"[A-Za-z0-9_.+~-]+",base) and re.fullmatch(r"[A-Za-z0-9_.+~-]+",version)
        url="https://repo.msys2.org/mingw/sources/"+base+"-"+version+".src.tar.zst"
        status="not_checked"
        try:
            safe_url(url)
            with OPENER.open(urllib.request.Request(url,method="HEAD"),timeout=20) as resp:
                safe_url(resp.geturl());status="available" if resp.status==200 else str(resp.status)
        except Exception as e:status=type(e).__name__+":"+str(getattr(e,"code",""))
        evidence.append({"owner":name,"version":r["version"],"license_metadata":r["licenses"],"archive_license":r["archive_pkginfo_license"],
            "notice_files":r["notice_files"],"source_archive_url":url,"source_availability":status,
            "source_bytes_independently_verified":False})
    OUT["license_source_inventory"]=evidence
    OUT["upstream_model_license"]={"tag":"4.1.0","repository":"https://github.com/tesseract-ocr/tessdata_fast",
        "license_git_blob_sha1":"d645695673349e3947e8e5ae42332d0ac3164cd7","license":"Apache-2.0",
        "note":"Publisher model subpackage has traineddata only; license and notices must accompany any future distribution."}
    row("license and corresponding source inventory of actual runtime owners","OBSERVED",{"owners":len(evidence),"without_archive_notice":[x["owner"] for x in evidence if not x["notice_files"]],
        "source_url_not_confirmed":[x["owner"] for x in evidence if x["source_availability"]!="available"],
        "distribution_qualified":False})


def fixture(runtime):
    font=None
    for name in ("msyh.ttc","msyhbd.ttc","simhei.ttf","simsun.ttc","Deng.ttf"):
        p=WIN/"Fonts"/name
        if p.is_file():
            try:
                f=ImageFont.truetype(str(p),64)
                if bytes(f.getmask("\u4e2d"))!=bytes(f.getmask("\u0378")):font=p;break
            except OSError:continue
    assert font,"no installed Chinese fixture font (no install permitted)"
    im=Image.new("RGB",(1800,1000),"white");d=ImageDraw.Draw(im)
    f=ImageFont.truetype(str(font),64)
    # Native Chinese text and numeric cells. Watermark and identifier occupy
    # separate known source regions, not prefilled in the recognized note.
    cells=[("title","\u4e2d\u6587\u8bfe\u4ef6",80,50),
        ("rowlabel","\u6570\u91cf",80,200),("countlabel","\u91d1\u989d",650,200),
        ("1208","1208",80,340),("0.05","0.05",650,340),
        ("70301","70301",80,480),("9007","9007",650,480),
        ("watermark","\u6c34\u5370",80,690),("personal","\u7f16\u53f7314159",650,690)]
    for _,value,x,y in cells:d.text((x,y),value,font=f,fill="black")
    path=runtime/"course-table.png";im.save(path);ordinary(path)
    row("synthetic Chinese table and watermark source page","PASS_ACTUAL",{"font":font.name,"page":"1/1","size":im.size,"image_sha256":digest(path)})
    return cells


def sampled_run(runtime):
    bin_dir=runtime/"bin";exe=bin_dir/"tesseract.exe"
    env={k:os.environ[k] for k in ("SystemRoot","WINDIR","SystemDrive","ComSpec","OS","PROCESSOR_ARCHITECTURE") if k in os.environ}
    scratch=runtime/"temp";scratch.mkdir()
    for key in ("HOME","USERPROFILE","APPDATA","LOCALAPPDATA","TEMP","TMP","TMPDIR","PROGRAMDATA","ALLUSERSPROFILE","PUBLIC"):env[key]=str(scratch)
    env["PATH"]=str(bin_dir)+os.pathsep+str(SYSTEM)
    env["TESSDATA_PREFIX"]="tessdata";env["OMP_THREAD_LIMIT"]="2"
    psapi=C.WinDLL("psapi",use_last_error=True)
    enum=psapi.EnumProcessModulesEx;enum.argtypes=[W.HANDLE,C.POINTER(W.HMODULE),W.DWORD,C.POINTER(W.DWORD),W.DWORD];enum.restype=W.BOOL
    filename=psapi.GetModuleFileNameExW;filename.argtypes=[W.HANDLE,W.HMODULE,W.LPWSTR,W.DWORD];filename.restype=W.DWORD
    args=[str(exe),"course-table.png","stdout","--tessdata-dir","tessdata","-l","chi_sim","--psm","6","tsv"]
    stdout=runtime/"ocr.tsv";stderr=runtime/"ocr.stderr"
    loaded=set();outside=set();samples=0
    with stdout.open("xb") as out,stderr.open("xb") as err:
        p=subprocess.Popen(args,cwd=runtime,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err)
        try:
            deadline=time.monotonic()+120
            while p.poll() is None:
                if time.monotonic()>deadline:raise TimeoutError("local OCR process")
                arr=(W.HMODULE*1024)();need=W.DWORD()
                if enum(W.HANDLE(int(p._handle)),arr,C.sizeof(arr),C.byref(need),3) and need.value<=C.sizeof(arr):
                    samples+=1
                    for module in arr[:need.value//C.sizeof(W.HMODULE)]:
                        buf=C.create_unicode_buffer(32768)
                        if filename(W.HANDLE(int(p._handle)),module,buf,len(buf)):
                            q=Path(buf.value).resolve()
                            if q.is_relative_to(bin_dir):loaded.add(q.name.casefold())
                            elif not(q.is_relative_to(SYSTEM) or q.is_relative_to(WIN/"WinSxS")):outside.add(q.name)
                time.sleep(.015)
            rc=p.returncode
        finally:
            if p.poll() is None:p.kill();p.wait(timeout=15)
    info={"returncode":rc,"module_samples":samples,"loaded_bundled_modules":sorted(loaded),"unexpected_module_basenames":sorted(outside),
        "stderr":stderr.read_text(encoding="utf-8",errors="backslashreplace")[-500:]}
    row("local native OCR execution and actual module observations","PASS_ACTUAL" if rc==0 and samples and not outside and "tesseract.exe" in loaded else "FAIL",info)
    assert rc==0 and samples and not outside and "tesseract.exe" in loaded
    assert loaded<=set(x["file"] for x in OUT["runtime_closure"]),("unaccounted loaded DLLs",loaded)
    return stdout


def recognize(tsv,cells,runtime):
    words=[]
    with tsv.open(encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f,delimiter="\t"):
            if r.get("level")=="5" and r.get("text","").strip():
                words.append({"text":r["text"].strip(),"x":int(r["left"]),"y":int(r["top"]),"w":int(r["width"]),"h":int(r["height"])})
    matches={}
    for key,expected,x,y in cells:
        box=[w for w in words if x-25<=w["x"]<x+550 and y-25<=w["y"]<y+105]
        box.sort(key=lambda w:w["x"])
        got="".join(w["text"] for w in box)
        matches[key]={"expected":expected,"actual":got,"word_boxes":box,"source_page":"1/1","matched":got==expected}
    OUT["synthetic_recognition"]=matches;save()
    assert all(x["matched"] for x in matches.values()),"Chinese or numeric source cell not exactly recognized"
    # Actual recognized words from the selected source cells, never copied
    # oracle text as OCR output. Do not retain watermark/identifier.
    title=matches["title"]["actual"]
    md="# "+title+"\n\nSource page 1/1, local course-table.png\n\n"
    md+="| "+matches["rowlabel"]["actual"]+" | "+matches["countlabel"]["actual"]+" |\n|---:|---:|\n"
    md+="| "+matches["1208"]["actual"]+" | "+matches["0.05"]["actual"]+" |\n| "+matches["70301"]["actual"]+" | "+matches["9007"]["actual"]+" |\n\n## Source index\n"
    for n in ("1208","0.05","70301","9007"):
        w=matches[n]["word_boxes"][0];md+=f"- {matches[n]['actual']}: page 1, x={w['x']}, y={w['y']}\n"
    assert matches["watermark"]["actual"] not in md and matches["personal"]["actual"] not in md and "314159" not in md
    (runtime/"reviewed-synthetic.md").write_text(md,encoding="utf-8")
    row("actual Chinese numeric table, source coordinates and watermark/identifier exclusion","PASS_ACTUAL",
        {"exact_cells":len(matches),"source_page":"1/1","markdown_sha256":digest(runtime/"reviewed-synthetic.md")})


def main():
    ancestors(ROOT);tmp=ROOT/"tmp";tmp.mkdir(exist_ok=True);ancestors(tmp)
    base=tmp/("ocr-feasibility-"+uuid.uuid4().hex);base.mkdir()
    # Research and all extracted files are excluded from customer packaging.
    try:
        archives=base/"archives";archives.mkdir();pool=base/"pool";pool.mkdir()
        db=archives/"ucrt64.db";db_sha=download(REPO+"ucrt64.db",db,20*1024*1024)
        OUT["repository_snapshot_sha256"]=db_sha
        packages=database(db);selected,edges=resolve(packages)
        OUT["package_lock"]=list(selected.values());OUT["dependency_edges"]=edges
        row("exact publisher repository snapshot and locked dependency graph","PASS_ACTUAL",{"packages":len(selected),"download_bytes":sum(x["compressed_size"] for x in selected.values())})
        inventory={};locations={}
        for name,rec in selected.items():
            archive=archives/rec["filename"]
            download(rec["url"],archive,100*1024*1024,rec["sha256"],rec["compressed_size"])
            d=pool/name;d.mkdir()
            locations[name]=extract_package(archive,rec,d,inventory)
            save()
        row("all locked archives SHA256 and PKGINFO checked; no install scripts run","PASS_ACTUAL",len(selected))
        runtime=base/"Portable \u4e2d\u6587 \u7a7a\u683c";runtime.mkdir();bin_dir=runtime/"bin";bin_dir.mkdir()
        dlls=closure(inventory,bin_dir)
        tess=runtime/"tessdata";tess.mkdir();(tess/"configs").mkdir()
        for pkg,rel in ((PREFIX+"tesseract-data-chi_sim","chi_sim.traineddata"),(PREFIX+"tesseract-ocr","configs/tsv")):
            src=locations[pkg]/"ucrt64/share/tessdata"/rel;ordinary(src);dst=tess/rel
            shutil.copyfile(src,dst);assert digest(src)==digest(dst)
        source_inventory(selected,{r["owner"] for r in dlls.values()})
        cells=fixture(runtime);tsv=sampled_run(runtime);recognize(tsv,cells,runtime)
        OUT["technical_recognition_passed"]=True
        row("redistribution qualification","BLOCKED_REVIEW","Full independent source/signature and license obligation review still required; no binary included or uploaded.")
    except Exception:
        row("isolated offline feasibility","FAIL_OR_BLOCKED",traceback.format_exc()[-7000:])
    finally:
        OUT["completed"]=True;save()
        shutil.rmtree(base)
    return int(not OUT.get("technical_recognition_passed",False))


if __name__=="__main__":
    for stream in (sys.stdout,sys.stderr):stream.reconfigure(encoding="utf-8",errors="backslashreplace")
    raise SystemExit(main())
