"""Rebuild only PNG/LSTM OCR from exact previously signature-verified sources.
Native Windows research: no vendor binary, no installation, no candidate ZIP.
"""
import csv,ctypes as C,hashlib,importlib.util,json,os,re,shutil,subprocess,sys,tarfile,time,traceback,uuid
from ctypes import wintypes as W
from pathlib import Path
ROOT=Path(__file__).absolute().parents[1]
REPORT=Path(sys.argv[1]).absolute()
assert os.name=="nt" and os.environ["GITHUB_REPOSITORY"]=="rileyaaa/Portable"
PREV=json.loads((ROOT/"tests/locked_ocr_xmllite_45751623105.json").read_bytes())
assert PREV["native_recognition_passed"] and PREV["binary_archive_signatures_verified"]==49
LOCK=json.loads((ROOT/"tests/fixed_seed_f2py_ocr_45749259260.json").read_bytes())["ocr_feasibility"]
spec=importlib.util.spec_from_file_location("locked_ocr_fixture",ROOT/"tests/check_locked_ocr_xmllite.py")
w=importlib.util.module_from_spec(spec);sys.modules[spec.name]=w;spec.loader.exec_module(w)
m=w.m
m.OUT.clear()
m.OUT.update(source_commit=os.environ["GITHUB_SHA"],prior_run="45751623105",prior_candidate="15085655070",
    scope="source-built reduced Windows x64 research only",rows=[],sources={},builds=[],completed=False,
    technical_recognition_passed=False,distribution_qualified=False,integrated=False,
    limitations=["Same fixed upstream source files from prior verified official signed source archives; no MSYS2 packaging patches executed.",
       "CI toolchain is preinstalled authorized build infrastructure, not a customer runtime or distribution grant.",
       "Static CRT reduces runtime DLLs but exact VS license applicability, security servicing and rebuild obligations still need approval.",
       "No bit-for-bit reproducible toolchain claim; exact source recipe, compiler versions and actual executable digest recorded.",
       "No runtime downloads, language install, package global install, customer binary upload, or real data.",
       "Local-process module/socket sampling is not a physical network air gap or exhaustive host-write tracing."])
row=m.row;save=m.save
WIN=m.WIN;SYSTEM=m.SYSTEM
SOURCES={
 "zlib":("mingw-w64-zlib","zlib-1.4.tar.xz"),
 "png":("mingw-w64-libpng","v1.6.59.tar.gz"),
 "lept":("mingw-w64-leptonica","leptonica-1.87.0.tar.gz"),
 "tess":("mingw-w64-tesseract-ocr","tesseract-ocr-5.5.4.tar.gz")}
GROUPS={x["pkgbase"]:x for x in PREV["provenance"]["sources"]}
BINARY_LOCK={x["name"]:x for x in LOCK["package_lock"]}


def member_name(s):
    s=s.removeprefix("./").rstrip("/")
    if not s:return ""
    return m.safe_member(s)


def extract_upstream(inner,dest):
    # Fresh local tree. No links, special files or traversal. No archive
    # build scripts are executed; CMake only from the verified official release.
    dest.mkdir();seen=set();roots=set();size=0
    with tarfile.open(inner,"r:*") as tar:
        for e in tar:
            n=member_name(e.name)
            if not n:assert e.isdir();continue
            p=dest/n;roots.add(n.split("/")[0])
            assert n.casefold() not in seen,("duplicate",n)
            seen.add(n.casefold())
            if e.isdir():
                p.mkdir(parents=True,exist_ok=True);m.ancestors(p);continue
            assert e.isfile() and 0<=e.size<=128*1024*1024,("unexpected upstream entry",n,e.type)
            size+=e.size;assert size<=600*1024*1024
            p.parent.mkdir(parents=True,exist_ok=True);m.ancestors(p.parent)
            with tar.extractfile(e) as src,p.open("xb") as out:shutil.copyfileobj(src,out,1024*1024)
            m.ordinary(p);assert p.stat().st_size==e.size
    assert len(roots)==1
    root=dest/next(iter(roots));assert (root/"CMakeLists.txt").is_file()
    return root


def source(base,key,group,leaf):
    g=GROUPS[group];assert g["status"]=="SOURCE_SIGNED_ARCHIVE_INSPECTED" and g["signature_verification"]["verified"]
    archive=base/(group+".src.tar.zst")
    m.download(g["url"],archive,g["archive"]["size"],g["archive"]["sha256"],g["archive"]["size"])
    nested=base/leaf;recipe=None;entry=None;docs=[]
    with tarfile.open(archive,"r:*") as tar:
        for e in tar:
            n=member_name(e.name)
            if not n or e.isdir():continue
            if n.endswith("/PKGBUILD"):
                assert recipe is None and e.isfile() and e.size<1024*1024
                recipe=tar.extractfile(e).read()
            elif n==group+"/"+leaf:
                assert entry is None and e.isfile() and e.size<=128*1024*1024
                entry=n
                with tar.extractfile(e) as src,nested.open("xb") as out:shutil.copyfileobj(src,out,1024*1024)
    assert recipe and hashlib.sha256(recipe).hexdigest()==g["recipes"][0]["sha256"] and entry
    nested_hash=m.digest(nested)
    assert nested_hash.encode("ascii") in recipe,("upstream nested source not pinned in signed recipe",key,nested_hash)
    root=extract_upstream(nested,base/(key+"-src"))
    for p in root.rglob("*"):
        if p.is_file() and re.fullmatch(r"(?i)(license|licence|copying|copyright|notice|authors|patents)(?:[._-].*)?",p.name):
            assert p.stat().st_size<=1024*1024 and len(docs)<200
            raw=p.read_bytes()
            docs.append({"path":p.relative_to(root).as_posix(),"sha256":hashlib.sha256(raw).hexdigest(),
                         "text":raw.decode("utf-8","backslashreplace")})
    assert docs,("upstream license missing",key)
    m.OUT["sources"][key]={"group":group,"version":g["version"],"signed_archive":g["archive"],"source_url":g["url"],
       "prior_signature":g["signature_verification"],"recipe_sha256":g["recipes"][0]["sha256"],
       "nested_member":entry,"nested_sha256":nested_hash,"source_file_count":sum(x.is_file() for x in root.rglob("*")),
       "license_notice_documents":docs,"cmake_sha256":m.digest(root/"CMakeLists.txt"),"applied_packager_patches":[]}
    save()
    archive.unlink();nested.unlink()
    return root


def tools():
    pf=Path(os.environ["ProgramFiles(x86)"])
    vswhere=pf/"Microsoft Visual Studio/Installer/vswhere.exe"
    assert vswhere.is_file()
    r=subprocess.run([str(vswhere),"-latest","-version","[17.0,18.0)","-products","*",
        "-requires","Microsoft.VisualStudio.Component.VC.Tools.x86.x64","-format","json","-utf8"],capture_output=True,check=True,timeout=30)
    v=json.loads(r.stdout.decode("utf-8-sig"));assert len(v)==1
    vs=Path(v[0]["installationPath"]).resolve()
    assert vs.is_relative_to(Path(os.environ["ProgramFiles"]).resolve()/"Microsoft Visual Studio")
    cmake=vs/"Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe"
    msbuild=vs/"MSBuild/Current/Bin/amd64/MSBuild.exe"
    version=(vs/"VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt").read_text().strip()
    assert re.fullmatch(r"14\.\d+\.\d+",version)
    cl=vs/"VC/Tools/MSVC"/version/"bin/Hostx64/x64/cl.exe"
    link=cl.with_name("link.exe")
    for p in (cmake,msbuild,cl,link):assert p.is_file() and p.resolve().is_relative_to(vs)
    m.OUT["toolchain"]={"vs_instance_version":v[0]["installationVersion"],"vs_product":v[0].get("productId"),
        "msvc_tools_version":version,"cmake_version":subprocess.check_output([str(cmake),"--version"],timeout=30,text=True).splitlines()[0],
        "build_tools_sha256":{p.name:m.digest(p) for p in (cmake,msbuild,cl,link)},
        "redist_terms":"https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files",
        "static_crt_requested":True,"runner_image":os.environ.get("ImageOS"),"runner_image_version":os.environ.get("ImageVersion")}
    save()
    return vs,cmake


def build_env(base):
    keep=("SystemRoot","WINDIR","SystemDrive","ComSpec","OS","PROCESSOR_ARCHITECTURE","ProgramFiles","ProgramFiles(x86)","ProgramW6432","NUMBER_OF_PROCESSORS")
    env={k:os.environ[k] for k in keep if k in os.environ}
    scratch=base/"build-env";scratch.mkdir()
    for k in ("HOME","USERPROFILE","APPDATA","LOCALAPPDATA","TEMP","TMP","TMPDIR","PROGRAMDATA","ALLUSERSPROFILE","PUBLIC","VCPKG_DEFAULT_BINARY_CACHE"):
        env[k]=str(scratch)
    env.update(PATH=str(SYSTEM)+os.pathsep+str(WIN),VcpkgEnabled="false",VCPKG_FEATURE_FLAGS="-manifests",
        CMAKE_BUILD_PARALLEL_LEVEL="2",CL="/Brepro",LINK="/Brepro")
    return env


def run(args,cwd,env,label,timeout=900):
    log=cwd/(label+".log")
    with log.open("xb") as out:
        r=subprocess.run([str(x) for x in args],cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,timeout=timeout)
    content=log.read_text(encoding="utf-8",errors="replace")
    result={"step":label,"returncode":r.returncode,"log_sha256":m.digest(log),"log_bytes":log.stat().st_size}
    if r.returncode:result["tail"]=content[-10000:]
    m.OUT["builds"].append(result);save()
    print("MINIMAL_BUILD="+json.dumps(result,ensure_ascii=True),flush=True)
    assert r.returncode==0,(label,r.returncode,content[-2000:])


def cache(path):
    result={}
    for line in (path/"CMakeCache.txt").read_text(encoding="utf-8",errors="replace").splitlines():
        if line.startswith(("#","//")):continue
        q=re.match(r"([^:=]+):[^=]+=(.*)",line)
        if q:result[q[1]]=q[2]
    return result


def build(base,srcs,vs,cmake):
    env=build_env(base)
    prefix=base/"prefix";prefix.mkdir()
    builds=base/"build";builds.mkdir()
    common=["-G","Visual Studio 17 2022","-A","x64",f"-DCMAKE_GENERATOR_INSTANCE={vs}",
        f"-DCMAKE_INSTALL_PREFIX={prefix}",f"-DCMAKE_PREFIX_PATH={prefix}",
        "-DCMAKE_INSTALL_LIBDIR=lib","-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded","-DCMAKE_POLICY_DEFAULT_CMP0091=NEW",
        "-DBUILD_SHARED_LIBS=OFF","-DCMAKE_FIND_USE_PACKAGE_REGISTRY=FALSE","-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=FALSE",
        "-DCMAKE_FIND_PACKAGE_NO_PACKAGE_REGISTRY=TRUE","-DCMAKE_FIND_PACKAGE_NO_SYSTEM_PACKAGE_REGISTRY=TRUE",
        "-DCMAKE_DISABLE_FIND_PACKAGE_PkgConfig=TRUE","-DCMAKE_DISABLE_FIND_PACKAGE_SW=TRUE","-DCMAKE_DISABLE_FIND_PACKAGE_Git=TRUE",
        "-DCMAKE_DISABLE_FIND_PACKAGE_CURL=TRUE","-DCMAKE_DISABLE_FIND_PACKAGE_LibArchive=TRUE",
        "-DCMAKE_DISABLE_FIND_PACKAGE_TIFF=TRUE","-DCMAKE_DISABLE_FIND_PACKAGE_JPEG=TRUE","-DCMAKE_DISABLE_FIND_PACKAGE_GIF=TRUE",
        "-DCMAKE_DISABLE_FIND_PACKAGE_OpenJPEG=TRUE","-DCMAKE_DISABLE_FIND_PACKAGE_WebP=TRUE","-DCMAKE_DISABLE_FIND_PACKAGE_OpenMP=TRUE",
        "-DCMAKE_DISABLE_FIND_PACKAGE_ICU=TRUE","-DCMAKE_DISABLE_FIND_PACKAGE_GTest=TRUE"]
    opts={"zlib":["-DZLIB_BUILD_TESTING=OFF","-DZLIB_BUILD_SHARED=OFF","-DZLIB_BUILD_STATIC=ON","-DZLIB_INSTALL=ON"],
          "png":["-DPNG_SHARED=OFF","-DPNG_STATIC=ON","-DPNG_TESTS=OFF","-DPNG_TOOLS=OFF","-DPNG_HARDWARE_OPTIMIZATIONS=OFF"],
          "lept":["-DSW_BUILD=OFF","-DSTRICT_CONF=ON","-DBUILD_PROG=OFF","-DENABLE_ZLIB=ON","-DENABLE_PNG=ON",
                   "-DENABLE_GIF=OFF","-DENABLE_JPEG=OFF","-DENABLE_TIFF=OFF","-DENABLE_WEBP=OFF","-DENABLE_OPENJPEG=OFF"],
          "tess":["-DWIN32_MT_BUILD=ON","-DDISABLE_CURL=ON","-DDISABLE_ARCHIVE=ON","-DDISABLE_TIFF=ON","-DOPENMP_BUILD=OFF",
                  "-DBUILD_TRAINING_TOOLS=OFF","-DBUILD_TESTS=OFF","-DGRAPHICS_DISABLED=ON","-DDISABLED_LEGACY_ENGINE=ON",
                  "-DENABLE_NATIVE=OFF","-DUSE_SYSTEM_ICU=OFF","-DENABLE_CCACHE=OFF","-DENABLE_PRECOMPILED_HEADERS=OFF",
                  "-DENABLE_LTO=OFF","-DINSTALL_CONFIGS=ON"]}
    m.OUT["build_recipe"]={"common":common,"components":opts,"configuration":"Release","parallel":2,"source_patches":[]};save()
    dep=[]
    for key in ("zlib","png","lept","tess"):
        dest=builds/key;dest.mkdir()
        extras=opts[key]+dep
        if key=="tess":extras=extras+[f"-DLeptonica_DIR={prefix/'lib/cmake/leptonica'}"]
        run([cmake,"-S",srcs[key],"-B",dest,*common,*extras],dest,env,"configure",timeout=240)
        c=cache(dest)
        assert c["CMAKE_GENERATOR"]=="Visual Studio 17 2022" and c["CMAKE_GENERATOR_PLATFORM"]=="x64"
        assert c["CMAKE_MSVC_RUNTIME_LIBRARY"]=="MultiThreaded"
        selected={k:v for k,v in c.items() if re.match(r"(?i)(ZLIB|PNG|Leptonica|CURL|LibArchive|TIFF|JPEG|GIF|OpenJPEG|WebP|ICU|OpenMP)_",k)}
        for name,val in selected.items():
            if re.search(r"(?:LIBRARY|LIBRARIES|INCLUDE_DIR|_DIR)(?:_(?:RELEASE|DEBUG))?$",name,re.I):
                if val.endswith("-NOTFOUND") or not val or val in ("optimized","debug","general"):continue
                for part in val.split(";"):
                    if re.match(r"^[A-Za-z]:[/\\]",part):
                        assert Path(part).resolve().is_relative_to(prefix.resolve()),("unexpected host dependency",name,part)
        m.OUT["builds"].append({"component":key,"cache_dependency_selections":selected,
            "cache_sha256":m.digest(dest/"CMakeCache.txt"),"sdk_version":c.get("CMAKE_VS_WINDOWS_TARGET_PLATFORM_VERSION")});save()
        run([cmake,"--build",dest,"--config","Release","--parallel","2"],dest,env,"build",timeout=1500)
        run([cmake,"--install",dest,"--config","Release"],dest,env,"install",timeout=180)
        if key=="zlib":
            libs=list((prefix/"lib").glob("*.lib"));assert len(libs)==1
            dep=[f"-DZLIB_ROOT={prefix}","-DZLIB_USE_STATIC_LIBS=ON",f"-DZLIB_LIBRARY_RELEASE={libs[0]}",f"-DZLIB_INCLUDE_DIR={prefix/'include'}"]
        elif key=="png":
            libs=[p for p in (prefix/"lib").glob("*.lib") if "png" in p.name.lower()];assert len(libs)==1
            dep=dep+[f"-DPNG_LIBRARY_RELEASE={libs[0]}",f"-DPNG_PNG_INCLUDE_DIR={prefix/'include'}"]
        elif key=="lept":
            config=(dest/"src/config_auto.h").read_text(encoding="utf-8")
            assert re.search(r"(?m)^#define HAVE_LIBPNG(?:\s+1)?\s*$",config) and re.search(r"(?m)^#define HAVE_LIBZ(?:\s+1)?\s*$",config),config
            assert not re.search(r"(?m)^#define HAVE_LIB(?:JPEG|TIFF|GIF|WEBP|JP2K)\s+1",config)
            row("Leptonica actual generated PNG/zlib-only codec config","PASS_ACTUAL",m.digest(dest/"src/config_auto.h"))
        else:
            config=(dest/"config_auto.h").read_text(encoding="utf-8")
            assert not re.search(r"(?m)^#define (?:HAVE_LIBARCHIVE|HAVE_CURL|HAVE_TIFFIO_H|HAVE_LIBCURL)\s+1",config)
            row("Tesseract actual generated reduced feature config","PASS_ACTUAL",m.digest(dest/"config_auto.h"))
        assert not list(prefix.rglob("*.dll")),("unexpected installed DLL",key)
    exe=prefix/"bin/tesseract.exe";assert exe.is_file()
    return exe,prefix


def pe_check(exe):
    pe=m.pefile.PE(str(exe),fast_load=True)
    try:
        assert pe.FILE_HEADER.Machine==0x8664
        pe.parse_data_directories(directories=[m.pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],m.pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"]])
        imports=sorted({x.dll.decode("ascii").casefold() for k in ("DIRECTORY_ENTRY_IMPORT","DIRECTORY_ENTRY_DELAY_IMPORT") for x in getattr(pe,k,[])})
    finally:pe.close()
    # Do not accept VC++ redistributable DLLs or any package DLL from runner.
    # Original known OS allowlist, no xmllite/host fallback expansion.
    bad=[n for n in imports if not m.is_system(n) or re.search(r"(?:vcruntime|msvcp[0-9]|libcurl|libarchive|xmllite)",n,re.I)]
    m.OUT["runtime_pe"]={"name":"tesseract.exe","sha256":m.digest(exe),"size":exe.stat().st_size,
        "imports_and_delay_imports":imports,"non_os_imports":bad}
    save()
    assert not bad,bad
    row("single native x64 executable; only verified existing Windows OS imports","PASS_ACTUAL",m.OUT["runtime_pe"])


def model(base,runtime):
    name=m.PREFIX+"tesseract-data-chi_sim";rec=BINARY_LOCK[name]
    archive=base/rec["filename"];m.download(rec["url"],archive,rec["compressed_size"],rec["sha256"],rec["compressed_size"])
    d=base/"model";d.mkdir();m.extract_package(archive,rec,d,{})
    src=d/"ucrt64/share/tessdata/chi_sim.traineddata";m.ordinary(src)
    want=next(x for x in PREV["native"]["runtime_model_and_config"] if x["path"]=="tessdata/chi_sim.traineddata")
    assert m.digest(src)==want["sha256"] and src.stat().st_size==want["size"]
    t=runtime/"tessdata";t.mkdir();(t/"configs").mkdir()
    shutil.copyfile(src,t/"chi_sim.traineddata")
    m.OUT["model"]=want;save()
    archive.unlink()


def reduced_run(runtime,image,psm,name,_unused1,_unused2):
    assert re.fullmatch(r"[a-z0-9-]+\.png",image) and psm in (6,7)
    bin_dir=runtime/"bin";exe=bin_dir/"tesseract.exe"
    scratch=runtime/"temp";scratch.mkdir(exist_ok=True)
    env={k:os.environ[k] for k in ("SystemRoot","WINDIR","SystemDrive","ComSpec","OS","PROCESSOR_ARCHITECTURE") if k in os.environ}
    for k in ("HOME","USERPROFILE","APPDATA","LOCALAPPDATA","TEMP","TMP","TMPDIR","PROGRAMDATA","ALLUSERSPROFILE","PUBLIC"):env[k]=str(scratch)
    env["PATH"]=str(bin_dir)+os.pathsep+str(SYSTEM);env["TESSDATA_PREFIX"]="tessdata"
    psapi=C.WinDLL("psapi",use_last_error=True)
    enum=psapi.EnumProcessModulesEx;enum.argtypes=[W.HANDLE,C.POINTER(W.HMODULE),W.DWORD,C.POINTER(W.DWORD),W.DWORD];enum.restype=W.BOOL
    filename=psapi.GetModuleFileNameExW;filename.argtypes=[W.HANDLE,W.HMODULE,W.LPWSTR,W.DWORD];filename.restype=W.DWORD
    loaded=set();outside=set();sockets=0;samples=0;exe_seen=False
    output=runtime/(name+".tsv");err=runtime/(name+".stderr")
    with output.open("xb") as out,err.open("xb") as er:
        p=subprocess.Popen([str(exe),image,"stdout","--tessdata-dir","tessdata","-l","chi_sim","--psm",str(psm),"tsv"],
           cwd=runtime,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=er)
        try:
            end=time.monotonic()+120
            while p.poll() is None:
                assert time.monotonic()<end,"OCR deadline"
                arr=(W.HMODULE*1024)();need=W.DWORD()
                if enum(W.HANDLE(int(p._handle)),arr,C.sizeof(arr),C.byref(need),3) and need.value<=C.sizeof(arr):
                    samples+=1
                    for h in arr[:need.value//C.sizeof(W.HMODULE)]:
                        b=C.create_unicode_buffer(32768)
                        if filename(W.HANDLE(int(p._handle)),h,b,len(b)):
                            q=Path(b.value).resolve()
                            if q==exe.resolve():exe_seen=True
                            elif q.is_relative_to(SYSTEM) or q.is_relative_to(WIN/"WinSxS"):
                                if re.search(r"(?i)(vcruntime|msvcp[0-9]|xmllite|libcurl|libarchive)",q.name):outside.add(q.name)
                                else:loaded.add(q.name.casefold())
                            else:outside.add(q.name)
                sockets=max(sockets,w.socket_count(p.pid));time.sleep(.025)
            rc=p.returncode
        finally:
            if p.poll() is None:p.kill();p.wait(timeout=15)
    result={"returncode":rc,"actual_executable_seen":exe_seen,"module_samples":samples,"os_modules":sorted(loaded),
        "unexpected_modules":sorted(outside),"owned_socket_max":sockets,"stderr":err.read_text(encoding="utf-8",errors="replace")[-500:]}
    ok=rc==0 and exe_seen and samples and not outside and not sockets
    row("reduced native local OCR "+name,"PASS_ACTUAL" if ok else "FAIL",result)
    assert ok,result
    with output.open(encoding="utf-8-sig",newline="") as f:
        return [{"text":r["text"].strip(),"x":int(r["left"]),"y":int(r["top"]),"w":int(r["width"]),"h":int(r["height"])}
          for r in csv.DictReader(f,delimiter="\t") if r.get("level")=="5" and r.get("text","").strip()]


def main():
    m.ancestors(ROOT);base=ROOT/"tmp"/("ocr-min-"+uuid.uuid4().hex[:8]);base.mkdir()
    try:
        srcs={k:source(base,k,*v) for k,v in SOURCES.items()}
        row("four exact signed-source recipe and actual upstream source/license inventories","PASS_ACTUAL",list(srcs))
        vs,cmake=tools();exe,prefix=build(base,srcs,vs,cmake);pe_check(exe)
        runtime=base/"Portable \u4e2d\u6587 \u7a7a\u683c";runtime.mkdir();bd=runtime/"bin";bd.mkdir()
        shutil.copyfile(exe,bd/"tesseract.exe");assert m.digest(bd/"tesseract.exe")==m.digest(exe)
        model(base,runtime)
        cfg=srcs["tess"]/"tessdata/configs/tsv";assert cfg.is_file()
        shutil.copyfile(cfg,runtime/"tessdata/configs/tsv")
        m.OUT["tsv_config"]={"sha256":m.digest(cfg),"size":cfg.stat().st_size};save()
        cells=w.fixture(runtime);w.local_run=reduced_run
        w.recognize(runtime,cells,None,None)
        assert len(list(bd.iterdir()))==1 and m.digest(bd/"tesseract.exe")==m.OUT["runtime_pe"]["sha256"]
        m.OUT["technical_recognition_passed"]=True
        row("reduced build technical acceptance, not redistribution/integration","PASS_ACTUAL",{"one_exe":True,"third_party_dlls":0,"model_bytes":m.OUT["model"]["size"]})
    except Exception:row("reduced source-built OCR","FAIL_OR_BLOCKED",traceback.format_exc()[-8000:])
    finally:
        shutil.rmtree(base);m.OUT["scratch_removed"]=not base.exists();m.OUT["completed"]=True;save()
    return int(not m.OUT["technical_recognition_passed"])
if __name__=="__main__":
    for stream in (sys.stdout,sys.stderr):stream.reconfigure(encoding="utf-8",errors="backslashreplace")
    raise SystemExit(main())
