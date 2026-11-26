"""Fixed upstream LLVM-MinGW static-runtime alternative preflight (no payload upload)."""
import collections,hashlib,importlib.util,json,os,re,shutil,stat,subprocess,sys,traceback,urllib.parse,urllib.request,uuid,zipfile
from pathlib import Path
ROOT=Path(__file__).absolute().parents[1]
REPORT=Path(sys.argv[1]).absolute()
assert os.name=="nt" and os.environ["GITHUB_REPOSITORY"]=="rileyaaa/Portable"
spec=importlib.util.spec_from_file_location("reduced",ROOT/"tests/check_minimal_ocr_build.py")
b=importlib.util.module_from_spec(spec);sys.modules[spec.name]=b;spec.loader.exec_module(b);m=b.m
m.OUT.clear()
m.OUT.update(source_commit=os.environ["GITHUB_SHA"],scope="fixed LLVM-MinGW compiler/runtime preflight only",rows=[],completed=False,
  distribution_qualified=False,ocr_built=False,probe_passed=False,
  release={"tag":"20261117","tag_object":"8b27e69efde155bafab54a1c6a6bb55627ec40bd","commit":"61b12e9bd8bdcc4acf15001fdb0bee1f056be50d","tag_signed":False,
   "asset":"llvm-mingw-20261117-ucrt-x86_64.zip","size":191082415,
   "sha256":"4d002e330a0f703625aa5ccbc37e96f8f824413e163bfc7336774aabd2c3a412"},
  source_licenses=[],archive_notices=[],limitations=[
    "This probes a C++ static runtime, not the four-component OCR build or its runtime closure.",
    "Publisher release SHA and Git blob checks do not prove independent signature verification or complete object-level notice mapping.",
    "No compiler/runtime DLL or executable distributed; no user data or global install."])
row=m.row;save=m.save

def safe_url(u):
    p=urllib.parse.urlsplit(u)
    assert p.scheme=="https" and not p.username and not p.password and p.port in (None,443)
    if p.hostname=="github.com":assert p.path.startswith("/mstorsjo/llvm-mingw/releases/download/20261117/")
    elif p.hostname=="raw.githubusercontent.com":
        assert p.path.startswith(("/llvm/llvm-project/llvmorg-23.1.6/","/mingw-w64/mingw-w64/41eb042358a52011b35350392130dcdc94a8ead8/","/mstorsjo/llvm-mingw/61b12e9bd8bdcc4acf15001fdb0bee1f056be50d/"))
    else:assert p.hostname in ("release-assets.githubusercontent.com","objects.githubusercontent.com")
class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        safe_url(newurl);return super().redirect_request(req,fp,code,msg,headers,newurl)
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),Redirect())
def fetch(url,limit,target=None):
    safe_url(url);h=hashlib.sha256();n=0
    with opener.open(urllib.request.Request(url,headers={"User-Agent":"Portable-OCR-fixed-toolchain-probe"}),timeout=90) as response:
        safe_url(response.geturl())
        if target is None:
            data=response.read(limit+1);assert len(data)<=limit;return data
        with target.open("xb") as out:
            while chunk:=response.read(1024*1024):
                n+=len(chunk);assert n<=limit;h.update(chunk);out.write(chunk)
    return n,h.hexdigest()
def licenses():
    base="https://raw.githubusercontent.com/"
    rows=[("mstorsjo/llvm-mingw","61b12e9bd8bdcc4acf15001fdb0bee1f056be50d","LICENSE.txt","fa1b4228555bd14fe7a63c3a22e18c477f1df000"),
          ("mingw-w64/mingw-w64","41eb042358a52011b35350392130dcdc94a8ead8","COPYING","28fa9514c036c2ae6a545fc9fe75c37baecf596d")]
    rows += [("llvm/llvm-project","llvmorg-23.1.6",k+"/LICENSE.TXT",v) for k,v in {
        "llvm":"fa6ac540007032cbd0ec772a1c72e6cb5527a4fe","libcxx":"e159d283443f92ac78b964d2bccebe8f95d5d445",
        "libcxxabi":"b75c0441bcd5be32b5a07e2a1ffc7e67b6d99f16","libunwind":"1e3120621caeb62648745a42f7a9a25d1e2731ab",
        "compiler-rt":"5a79a1b9d5cb0af9a779751f07033e44ca3b14d8"}.items()]
    for repo,ref,path,blob in rows:
        url=base+repo+"/"+ref+"/"+path
        raw=fetch(url,1024*1024);assert b.git_blob(raw)==blob,(path,"source Git blob mismatch")
        m.OUT["source_licenses"].append({"url":url,"git_blob_sha1":blob,"sha256":hashlib.sha256(raw).hexdigest(),"text":raw.decode("utf-8")})
    for name,blob in [("build-llvm.sh","ef6a3ff057043e18f6f606db443957401b6d325e"),("build-mingw-w64.sh","85345cd1a396afb196ad503da7f274774c589f5a"),
            ("build-libcxx.sh","f37cc9dea406dd5ffa54b1f3a8c0dfd306d562f4"),("build-compiler-rt.sh","b56aa489c8c6f6a2ef21b3290612ac48e9457f53")]:
        raw=fetch(base+"mstorsjo/llvm-mingw/61b12e9bd8bdcc4acf15001fdb0bee1f056be50d/"+name,1024*1024)
        assert b.git_blob(raw)==blob
        m.OUT.setdefault("build_recipe",{})[name]={"git_blob_sha1":blob,"sha256":hashlib.sha256(raw).hexdigest()}
    row("exact upstream toolchain recipe and source license blobs","PASS_ACTUAL",len(m.OUT["source_licenses"]))
def unpack(base,archive):
    dest=base/"toolchain";dest.mkdir();seen=set();roots=set();total=0
    with zipfile.ZipFile(archive) as z:
        for e in z.infolist():
            n=e.filename.rstrip("/")
            assert n and not n.startswith("/") and "\\" not in n and ":" not in n and all(x not in ("",".","..") and not x.endswith((" ",".")) for x in n.split("/"))
            assert n.casefold() not in seen and not stat.S_ISLNK(e.external_attr>>16)
            seen.add(n.casefold());roots.add(n.split("/")[0])
            p=dest/n
            if e.is_dir():p.mkdir(parents=True,exist_ok=True);continue
            total+=e.file_size;assert total<=1500*1024*1024 and e.file_size<=300*1024*1024
            p.parent.mkdir(parents=True,exist_ok=True);m.ancestors(p.parent)
            with z.open(e) as i,p.open("xb") as o:shutil.copyfileobj(i,o)
            assert p.stat().st_size==e.file_size;m.ordinary(p)
            if re.search(r"(?i)(?:^|/)(?:license|copying|notice|copyright)(?:[._-][^/]*)?$",n) and e.file_size<1024*1024:
                m.OUT["archive_notices"].append({"path":n,"sha256":m.digest(p),"size":e.file_size,"text":p.read_text(encoding="utf-8",errors="backslashreplace")})
    assert len(roots)==1
    row("fixed upstream archive safe extraction and notice inventory","PASS_ACTUAL",{"files":len(seen),"notice_count":len(m.OUT["archive_notices"])})
    return dest/next(iter(roots))
def probe(base,tc):
    scratch=base/"scratch";scratch.mkdir()
    compiler=tc/"bin/x86_64-w64-mingw32-clang++.exe";m.ordinary(compiler)
    env={k:os.environ[k] for k in ("SystemRoot","WINDIR","SystemDrive","ComSpec","OS","PROCESSOR_ARCHITECTURE") if k in os.environ}
    for k in ("HOME","USERPROFILE","APPDATA","LOCALAPPDATA","TEMP","TMP","TMPDIR","PROGRAMDATA","ALLUSERSPROFILE","PUBLIC"):env[k]=str(scratch)
    env["PATH"]=str(tc/"bin")+os.pathsep+str(m.SYSTEM)
    src=scratch/"probe.cpp"
    src.write_text('#include <iostream>\n#include <string>\n#include <stdexcept>\n#include <thread>\n#include <chrono>\nint main(){std::string s;std::thread t([&]{try{throw std::runtime_error("PORTABLE_LLVM_STATIC");}catch(const std::exception& e){s=e.what();}});t.join();std::cout<<s;return s=="PORTABLE_LLVM_STATIC"?0:1;}\n',encoding="ascii")
    version=subprocess.check_output([str(compiler),"--version"],env=env,cwd=scratch,timeout=30,text=True)
    exe=scratch/"probe.exe";mp=scratch/"probe.map"
    cmd=[str(compiler),"-O2","-static",str(src),"-o",str(exe),"-Wl,-Map,"+str(mp),"-Wl,--trace"]
    p=subprocess.run(cmd,env=env,cwd=scratch,capture_output=True,timeout=180)
    m.OUT["compiler"]={"version":version,"sha256":m.digest(compiler),"argv":cmd[1:],"returncode":p.returncode,
        "link_trace":(p.stdout+p.stderr).decode("utf-8",errors="replace")[-20000:]};save()
    assert p.returncode==0
    m.ordinary(mp);m.ordinary(exe)
    raw=mp.read_bytes();assert 100<len(raw)<20*1024*1024
    mapping=raw.decode("utf-8",errors="replace")
    archives={}
    for name in set(re.findall(r"(?i)([A-Za-z0-9_+.-]+\.a)\(",mapping)):
        candidates=list(tc.rglob(name))
        matches=[q for q in candidates if q.is_file() and ("x86_64" in q.as_posix().lower() or "clang" in q.as_posix().lower())]
        if len(matches)==1:
            archives[name]={"path":matches[0].relative_to(tc).as_posix(),"sha256":m.digest(matches[0])}
        else:archives[name]={"candidates":[q.relative_to(tc).as_posix() for q in matches],"unresolved":True}
    pe=m.pefile.PE(str(exe),fast_load=True)
    try:
        assert pe.FILE_HEADER.Machine==0x8664
        pe.parse_data_directories(directories=[m.pefile.DIRECTORY_ENTRY[k] for k in ("IMAGE_DIRECTORY_ENTRY_IMPORT","IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT")])
        imports=sorted({x.dll.decode("ascii").casefold() for k in ("DIRECTORY_ENTRY_IMPORT","DIRECTORY_ENTRY_DELAY_IMPORT") for x in getattr(pe,k,[])})
    finally:pe.close()
    bad=[x for x in imports if not m.is_system(x)]
    m.OUT["actual_probe_link"]={"map_sha256":hashlib.sha256(raw).hexdigest(),"map_bytes":len(raw),"archives":archives,"imports":imports,"non_os_imports":bad}
    REPORT.with_name("llvm-mingw-static-probe-map.txt").write_bytes(raw);save()
    assert not bad,bad
    moved=base/"LLVM \u4e2d\u6587 \u7a7a\u683c";moved.mkdir();shutil.copyfile(exe,moved/"probe.exe")
    runenv=env.copy();runenv["PATH"]=str(m.SYSTEM)
    r=subprocess.run([str(moved/"probe.exe")],cwd=moved,env=runenv,capture_output=True,timeout=30)
    assert r.returncode==0 and r.stdout==b"PORTABLE_LLVM_STATIC" and not r.stderr
    row("actual static C++ probe with OS-only imports and moved path","PASS_ACTUAL",{"imports":imports,"sha256":m.digest(exe),"archives":len(archives)})
    m.OUT["probe_passed"]=True
def main():
    base=None
    try:
        parent=ROOT/"tmp";parent.mkdir(exist_ok=True);m.ancestors(parent);save()
        base=parent/("llvm-ocr-"+uuid.uuid4().hex[:8]);base.mkdir()
        licenses()
        pin=m.OUT["release"];archive=base/pin["asset"]
        url="https://github.com/mstorsjo/llvm-mingw/releases/download/"+pin["tag"]+"/"+pin["asset"]
        assert fetch(url,pin["size"],archive)==(pin["size"],pin["sha256"])
        row("fixed upstream native x64 LLVM-MinGW asset SHA and size","PASS_ACTUAL",pin)
        tc=unpack(base,archive)
        probe(base,tc)
    except Exception:row("LLVM-MinGW preflight","FAIL_OR_BLOCKED",traceback.format_exc()[-6000:])
    finally:
        try:
            if base and base.exists():m.ancestors(base);shutil.rmtree(base)
            m.OUT["scratch_removed"]=base is None or not base.exists()
        except Exception:row("scratch cleanup","FAIL",traceback.format_exc()[-2000:])
        m.OUT["completed"]=True;save()
    return int(not (m.OUT["probe_passed"] and m.OUT.get("scratch_removed")))
if __name__=="__main__":
    for s in (sys.stdout,sys.stderr):s.reconfigure(encoding="utf-8",errors="backslashreplace")
    raise SystemExit(main())
