"""Full reduced LLVM-MinGW Windows OCR build and private product acceptance.

No unreviewed runtime bytes, repro archives, build tools or private ZIP may be
uploaded. The prior MSVC and original-package evidence is not rerun. Actual
archive/member reads and complete notice bytes are preserved for the next
distribution decision; this program cannot approve its own legal evidence.
"""
import collections
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import traceback
import uuid
from pathlib import Path

ROOT=Path(__file__).absolute().parents[1]
REPORT=Path(sys.argv[1]).absolute()

def load(name,filename):
    spec=importlib.util.spec_from_file_location(name,ROOT/"tests"/filename)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module)
    return module

a=load("llvm_toolchain","check_llvm_mingw_ocr_toolchain.py")
b=a.b;m=a.m;row=m.row;save=m.save
p=load("product_helpers","check_course_ocr_product.py")
# Both helpers load the older research modules. Route all reports to this
# run's one evidence object, not the imported helper's private OUT.
p.b=b;p.m=m;p.row=row;p.save=save
PREVIOUS=json.loads((ROOT/"tests/course_ocr_product_45761867152.json").read_bytes())
assert PREVIOUS["product_job"]=="success" and PREVIOUS["product"]["product_contract_passed"]
assert PREVIOUS["product"]["link_evidence_complete"] and PREVIOUS["llvm_job"]=="failure"
assert not PREVIOUS["distribution_qualified"]
m.OUT.update(scope="LLVM-MinGW full reduced OCR build, exact linked input evidence and private product test",
    prior_run="45761867152",prior_product_and_msvc_map_retained=True,
    ocr_built=False,product_contract_passed=False,link_evidence_complete=False,
    distribution_qualified=False,customer_candidate_built=False,private_zip_not_uploaded=True,
    sources={},builds=[],limitations=[
      "Same four fixed signed-source archive identities and fixed model/config as previous MSVC build.",
      "LLVM-MinGW publisher asset digest and exact source recipe verified in prior run; unsigned tag, no independent release signature.",
      "Actual linked archive/member evidence, not a blanket claim for every file in the toolchain.",
      "No MSVC compiler or libraries selected for OCR; CMake and Ninja are build orchestrators only.",
      "Native library notices and per-object attribution must be reviewed before setting distributionQualified.",
      "No unreviewed executable/model, linker reproduction tar or private test ZIP uploaded.",
      "Product test uses the existing developer-only resolver seam; default distribution lock remains closed.",
      "Module/socket sampling is not exhaustive host/network isolation proof."])

def toolchain(base):
    prior=PREVIOUS["llvm"]
    pin=prior["release"];assert pin==m.OUT["release"]
    archive=base/pin["asset"]
    url="https://github.com/mstorsjo/llvm-mingw/releases/download/"+pin["tag"]+"/"+pin["asset"]
    assert a.fetch(url,pin["size"],archive)==(pin["size"],pin["sha256"])
    tc=a.unpack(base,archive)
    # Reuse the already verified upstream source/license identities; exact
    # archive bytes also prove the same embedded notice files are available.
    old={n["path"]:n["sha256"] for n in prior["archive_notices"]}
    assert {n["path"]:n["sha256"] for n in m.OUT["archive_notices"]}==old
    m.OUT["source_licenses"]=prior["source_licenses"]
    m.OUT["prior_toolchain_recipe"]=prior["build_recipe"]
    m.OUT["toolchain_asset_verified"]=True
    archive.unlink();save()
    return tc

def supplement_notices():
    # Source-tree inventories at the exact compiler-reported LLVM commit
    # contained only LICENSE and the following credits in the four runtime
    # subtrees. MinGW's full runtime notice is explicitly intended for
    # statically linked output; retain every notice, including its caveats.
    rows=[
      ("llvm/llvm-project","llvmorg-23.1.6","compiler-rt/CREDITS.TXT","6964eba020b8aa7a08629b249e3b9aea3ce3e448"),
      ("llvm/llvm-project","llvmorg-23.1.6","libcxx/CREDITS.TXT","6ed18072de9a56d97d8446b2b7be9d3178d9334d"),
      ("llvm/llvm-project","llvmorg-23.1.6","libcxxabi/CREDITS.TXT","fbb6cbf38baf60a05dcca9025e50f3a25c961b73"),
      ("mingw-w64/mingw-w64","41eb042358a52011b35350392130dcdc94a8ead8","AUTHORS","4b40f2beb3cac255a09ff12616c22aa89aa9d80f"),
      ("mingw-w64/mingw-w64","41eb042358a52011b35350392130dcdc94a8ead8","COPYING.MinGW-w64-runtime/COPYING.MinGW-w64-runtime.txt","776d5f1034240f6dae0ce59d592f9c6f4ad29e7d"),
      ("mingw-w64/mingw-w64","41eb042358a52011b35350392130dcdc94a8ead8","COPYING.MinGW-w64/COPYING.MinGW-w64.txt","decbf46bde9d87a0c2250fe33ece1b7e0724ee6e"),
      ("mingw-w64/mingw-w64","41eb042358a52011b35350392130dcdc94a8ead8","mingw-w64-libraries/winpthreads/COPYING","3507701238b798b1ddbf4d5ffe16f285f4458963")]
    out=[]
    for repo,ref,path,blob in rows:
        url="https://raw.githubusercontent.com/"+repo+"/"+ref+"/"+path
        raw=a.fetch(url,1024*1024)
        assert b.git_blob(raw)==blob,(path,"source Git blob mismatch")
        out.append({"url":url,"git_blob_sha1":blob,"sha256":hashlib.sha256(raw).hexdigest(),"text":raw.decode("utf-8")})
    m.OUT["supplemental_notice_documents"]=out
    by_name={Path(n["url"]).name:n["sha256"] for n in out}
    for name in ("COPYING.MinGW-w64-runtime.txt","COPYING.MinGW-w64.txt"):
        embedded=[n["sha256"] for n in m.OUT["archive_notices"] if "/x86_64-w64-mingw32/share/" in n["path"] and n["path"].endswith("/"+name)]
        assert embedded==[by_name[name]],("embedded runtime notice differs from fixed source",name)
    m.OUT["llvm_source_tag"]={"tag_object":"c5edffe4a336b626aa4803127a5724b677d37a3a",
        "commit":"5b10d2d74929eae78912771222c9855af97496f4","tag_signature_verified_by_github":True,
        "runtime_subtrees":{"compiler-rt":"14d3b43691dfcdffcf11833a33ab0a18dfb66996",
            "libcxx":"792c10839ae4a65e96479055e0493a9ee5379849","libcxxabi":"d902c06646c4421a491e021f383b0328c5bdc6df","libunwind":"1a50034df91361e1ada2fd28589061bdd1a3d044"}}
    row("fixed LLVM credits and MinGW full runtime source notice readback", "PASS_ACTUAL",len(out))

def build(base,tc,srcs):
    vs,cmake=b.tools()
    m.OUT["build_orchestrator"]=m.OUT.pop("toolchain")
    ninja=vs/"Common7/IDE/CommonExtensions/Microsoft/CMake/Ninja/ninja.exe"
    tools={k:tc/"bin"/v for k,v in {
       "cc":"x86_64-w64-mingw32-clang.exe","cxx":"x86_64-w64-mingw32-clang++.exe",
       "ar":"llvm-ar.exe","ranlib":"llvm-ranlib.exe","rc":"x86_64-w64-mingw32-windres.exe",
       "linker":"ld.lld.exe","readobj":"llvm-readobj.exe"}.items()}
    for x in [ninja,*tools.values()]:m.ordinary(x)
    env=b.build_env(base)
    env.pop("CL",None);env.pop("LINK",None)
    env["PATH"]=str(tc/"bin")+os.pathsep+str(m.SYSTEM)+os.pathsep+str(m.WIN)
    env["CMAKE_BUILD_PARALLEL_LEVEL"]="2"
    version=subprocess.check_output([str(tools["cxx"]),"--version"],env=env,timeout=30,text=True)
    assert "clang version 23.1.6" in version and "5b10d2d74929eae78912771222c9855af97496f4" in version and "x86_64-w64-windows-gnu" in version
    assert m.digest(tools["cxx"])==PREVIOUS["llvm"]["compiler"]["sha256"]
    m.OUT["llvm_compiler"]={"version":version,"tools":{k:{"path":v.relative_to(tc).as_posix(),"sha256":m.digest(v)} for k,v in tools.items()},
        "ninja_sha256":m.digest(ninja),"ninja_version":subprocess.check_output([str(ninja),"--version"],env=env,timeout=30,text=True).strip()}
    save()
    prefix=base/"prefix";prefix.mkdir()
    builds=base/"build";builds.mkdir()
    # Explicit fixed compiler, sysroot, linker and archiver. CMake can only
    # find dependency packages/libraries/includes in the private prefix or
    # the verified toolchain; no compiler SDK or host package registries.
    sysroot=tc/"x86_64-w64-mingw32"
    common=["-G","Ninja",f"-DCMAKE_MAKE_PROGRAM:FILEPATH={ninja.as_posix()}",
        "-DCMAKE_SYSTEM_NAME=Windows","-DCMAKE_SYSTEM_PROCESSOR=x86_64",
        f"-DCMAKE_C_COMPILER:FILEPATH={tools['cc'].as_posix()}",f"-DCMAKE_CXX_COMPILER:FILEPATH={tools['cxx'].as_posix()}",
        f"-DCMAKE_AR:FILEPATH={tools['ar'].as_posix()}",f"-DCMAKE_RANLIB:FILEPATH={tools['ranlib'].as_posix()}",
        f"-DCMAKE_RC_COMPILER:FILEPATH={tools['rc'].as_posix()}",f"-DCMAKE_LINKER:FILEPATH={tools['linker'].as_posix()}",
        f"-DCMAKE_FIND_ROOT_PATH={prefix.as_posix()};{sysroot.as_posix()}",
        "-DCMAKE_FIND_ROOT_PATH_MODE_LIBRARY=ONLY","-DCMAKE_FIND_ROOT_PATH_MODE_INCLUDE=ONLY",
        "-DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=ONLY","-DCMAKE_FIND_ROOT_PATH_MODE_PROGRAM=NEVER",
        f"-DCMAKE_INSTALL_PREFIX:PATH={prefix.as_posix()}",f"-DCMAKE_PREFIX_PATH={prefix.as_posix()}",
        "-DCMAKE_BUILD_TYPE=Release","-DCMAKE_INSTALL_LIBDIR=lib",
        "-DCMAKE_C_FLAGS_RELEASE=-O2 -DNDEBUG","-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG",
        "-DCMAKE_EXE_LINKER_FLAGS=-static","-DBUILD_SHARED_LIBS=OFF",
        "-DCMAKE_FIND_USE_CMAKE_ENVIRONMENT_PATH=FALSE",
        "-DCMAKE_FIND_USE_PACKAGE_REGISTRY=FALSE","-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=FALSE",
        "-DCMAKE_FIND_PACKAGE_NO_PACKAGE_REGISTRY=TRUE","-DCMAKE_FIND_PACKAGE_NO_SYSTEM_PACKAGE_REGISTRY=TRUE"]
    old=PREVIOUS["product"]["build_recipe"]
    common+= [x for x in old["common"] if x.startswith("-DCMAKE_DISABLE_FIND_PACKAGE_")]
    opts={k:[x for x in v if not x.startswith("-DWIN32_MT_BUILD=")] for k,v in old["components"].items()}
    m.OUT["build_recipe"]={"common":common,"components":opts,"source_patches":[],"config":"Release","parallel":2}
    dep=[]
    for key in ("zlib","png","lept","tess"):
        dest=builds/key;dest.mkdir()
        extras=opts[key]+dep
        mp=dest/"tesseract-llvm.map";rp=dest/"tesseract-link-repro.tar"
        if key=="tess":
            extras += [f"-DLeptonica_DIR:PATH={(prefix/'lib/cmake/leptonica').as_posix()}",
                f"-DCMAKE_EXE_LINKER_FLAGS=-static -Wl,-Map={mp.as_posix()} -Wl,--verbose -Wl,--reproduce={rp.as_posix()}"]
        assert all("\\" not in x for x in common+extras), "CMake cache paths must use forward slash"
        b.run([cmake,"-S",srcs[key].as_posix(),"-B",dest.as_posix(),*common,*extras],dest,env,"configure",timeout=300)
        cache=b.cache(dest)
        assert cache["CMAKE_GENERATOR"]=="Ninja" and cache["CMAKE_BUILD_TYPE"]=="Release"
        for lang,k in (("C","cc"),("CXX","cxx")):
            if "CMAKE_"+lang+"_COMPILER" in cache:
                assert Path(cache["CMAKE_"+lang+"_COMPILER"]).resolve()==tools[k].resolve()
        for flag in opts[key]:
            n,v=flag[2:].split("=",1)
            assert cache.get(n)==v,("effective CMake option",key,n,cache.get(n),v)
        selected={k:v for k,v in cache.items() if re.match(r"(?i)(ZLIB|PNG|Leptonica|CURL|LibArchive|TIFF|JPEG|GIF|OpenJPEG|WebP|ICU|OpenMP)_",k)}
        for n,v in selected.items():
            if n.upper().endswith(("_SOURCE_DIR","_BINARY_DIR")):
                if re.match(r"^[A-Za-z]:[/\\]",v):assert Path(v).resolve().is_relative_to(base.resolve()),(n,v)
                continue
            if not re.search(r"(?:LIBRARY|LIBRARIES|INCLUDE_DIR|_DIR)(?:_(?:RELEASE|DEBUG))?$",n,re.I):continue
            if not v or v.endswith("-NOTFOUND"):continue
            for part in v.split(";"):
                if re.match(r"^[A-Za-z]:[/\\]",part):
                    assert Path(part).resolve().is_relative_to(prefix.resolve()),("unexpected host dependency",n,part)
        m.OUT["builds"].append({"component":key,"cache_sha256":m.digest(dest/"CMakeCache.txt"),
            "cache_dependency_selections":selected});save()
        for f in (mp,rp):
            if f.exists():f.unlink()
        b.run([cmake,"--build",dest,"--config","Release","--parallel","2"],dest,env,"build",timeout=1800)
        b.run([cmake,"--install",dest,"--config","Release"],dest,env,"install",timeout=180)
        assert not list(prefix.rglob("*.dll")),("unexpected installed DLL",key)
        if key=="zlib":
            libs=list((prefix/"lib").glob("*.a"));assert len(libs)==1,libs
            dep=[f"-DZLIB_ROOT:PATH={prefix.as_posix()}","-DZLIB_USE_STATIC_LIBS=ON",f"-DZLIB_LIBRARY_RELEASE:FILEPATH={libs[0].as_posix()}",f"-DZLIB_INCLUDE_DIR:PATH={(prefix/'include').as_posix()}"]
        elif key=="png":
            # libpng's GNU Windows branch deliberately installs libpng16.a
            # plus a byte-for-byte libpng.a compatibility copy. Verify both
            # actual ordinary files, then pin the ABI-specific archive.
            libs={f.name:f for f in (prefix/"lib").glob("*.a") if "png" in f.name.lower()}
            assert set(libs)=={"libpng.a","libpng16.a"},libs
            for f in libs.values():m.ordinary(f)
            assert m.digest(libs["libpng.a"])==m.digest(libs["libpng16.a"]),"libpng alias bytes differ"
            row("actual GNU Windows libpng16 archive and exact compatibility alias","PASS_ACTUAL",
                {"canonical":"libpng16.a","alias":"libpng.a","sha256":m.digest(libs["libpng16.a"]),"upstream_cmake":"v1.6.59 create_symlink copies target on Windows"})
            dep += [f"-DPNG_LIBRARY_RELEASE:FILEPATH={libs['libpng16.a'].as_posix()}",f"-DPNG_PNG_INCLUDE_DIR:PATH={(prefix/'include').as_posix()}"]
        elif key=="lept":
            cfg=(dest/"src/config_auto.h").read_text(encoding="utf-8")
            assert re.search(r"(?m)^#define HAVE_LIBPNG(?:\s+1)?\s*$",cfg) and re.search(r"(?m)^#define HAVE_LIBZ(?:\s+1)?\s*$",cfg)
            assert not re.search(r"(?m)^#define HAVE_LIB(?:JPEG|TIFF|GIF|WEBP|JP2K)\s+1",cfg)
            row("LLVM actual generated Leptonica PNG/zlib-only codec config","PASS_ACTUAL",m.digest(dest/"src/config_auto.h"))
        else:
            cfg=(dest/"config_auto.h").read_text(encoding="utf-8")
            assert not re.search(r"(?m)^#define (?:HAVE_LIBARCHIVE|HAVE_CURL|HAVE_TIFFIO_H|HAVE_LIBCURL)\s+1",cfg)
            row("LLVM actual generated reduced Tesseract feature config","PASS_ACTUAL",m.digest(dest/"config_auto.h"))
    exe=prefix/"bin/tesseract.exe";m.ordinary(exe)
    m.OUT["ocr_built"]=True;save()
    return exe,tools,env

def link_evidence(base,tc,tools,env):
    dest=base/"build/tess"
    mp=dest/"tesseract-llvm.map";rp=dest/"tesseract-link-repro.tar";log=dest/"build.log"
    for f in (mp,rp,log):m.ordinary(f)
    assert 1000<mp.stat().st_size<64*1024*1024
    assert 1000<rp.stat().st_size<1500*1024*1024
    raw=mp.read_bytes();trace=log.read_text(encoding="utf-8",errors="replace")
    # Upstream LLD 23 COFF verbose driver emits Reading <input> for actual
    # inputs, including archive members; reproduce tar stores absolute
    # input names converted to drive/path form (not just -l search names).
    # Never upload the repro tar: it contains static library/object bytes.
    inputs={};metadata={};archives={};direct={}
    with tarfile.open(rp,"r:*") as tar:
        for e in tar:
            assert e.isfile() or e.isdir(),("nonregular repro member",e.name)
            if e.isdir():continue
            parts=e.name.replace("\\","/").split("/")
            assert len(parts)>=2 and all(x not in ("",".","..") for x in parts)
            rel="/".join(parts[1:])
            with tar.extractfile(e) as f:sha=hashlib.file_digest(f,"sha256").hexdigest()
            if rel in ("response.txt","version.txt"):
                assert e.size<1024*1024
                metadata[rel]={"sha256":sha,"text":tar.extractfile(e).read().decode("utf-8",errors="replace")}
                continue
            assert re.match(r"^[A-Za-z]/",rel),("unexpected LLD reproduction path",rel)
            actual=Path(rel[0]+":/"+rel[2:]).resolve()
            assert actual.is_file() and actual.is_relative_to(base.resolve()),("input from outside fixed build root",rel)
            assert m.digest(actual)==sha,("actual linked file mismatch",rel)
            origin="llvm-toolchain" if actual.is_relative_to(tc.resolve()) else "built-source"
            name=actual.relative_to(tc if origin=="llvm-toolchain" else base).as_posix()
            key=origin+"/"+name
            assert key not in inputs
            inputs[key]={"sha256":sha,"size":e.size,"origin":origin}
            if actual.suffix.lower() in (".a",".lib"):
                listing=subprocess.check_output([str(tools["ar"]),"t",str(actual)],env=env,cwd=dest,timeout=60).decode("utf-8",errors="replace").splitlines()
                assert listing and len(listing)<100000
                archives[key]={"path":actual,"members":listing}
            elif actual.suffix.lower() in (".o",".obj",".res"):
                direct[key]={"origin":origin,"name":actual.name}
    assert "response.txt" in metadata and archives and direct
    reads=[]
    for line in trace.splitlines():
        mat=re.search(r"(?:^|\s)Reading (.+?)\s*$",line)
        if mat:reads.append(mat.group(1))
    assert reads, "No actual LLD Reading entries"
    members={};unresolved=[]
    for item in reads:
        mm=re.fullmatch(r"(.+\.(?:a|lib))\((.+)\)",item,re.I)
        if not mm:continue
        arch,member=mm.groups()
        candidates=[k for k,v in archives.items() if v["path"].name.casefold()==Path(arch).name.casefold()]
        if len(candidates)!=1:
            unresolved.append({"archive":arch,"member":member,"reason":"archive basename not unique in actual reproduction inputs"});continue
        k=candidates[0];matching=[s for s in archives[k]["members"] if Path(s).name.casefold()==Path(member).name.casefold()]
        if not matching:
            unresolved.append({"archive":arch,"member":member,"reason":"member not found in actual archive inventory"});continue
        r=members.setdefault(k,{})
        r[member]={"archive_member_matches":matching,"read_count":r.get(member,{}).get("read_count",0)+1}
    # Conservative: actual "Reading" members, not all archive candidates,
    # and original map/trace readback preserved. No guessed license for an
    # unknown archive or an unresolvable object. Distinct source-level
    # attribution review is still required after these mechanical checks.
    assert members,"No resolved actual LLD archive members"
    m.OUT["actual_link"]={"map_sha256":hashlib.sha256(raw).hexdigest(),"map_bytes":len(raw),
        "verbose_sha256":m.digest(log),"reproducer_sha256":m.digest(rp),
        "response":metadata,"input_files":inputs,"direct_objects":direct,
        "archive_members":members,"unresolved_members":unresolved,
        "archives_without_member_reads":sorted(set(archives)-set(members))}
    REPORT.with_name("llvm-ocr-link-map.txt").write_bytes(raw)
    REPORT.with_name("llvm-ocr-link-reading.txt").write_text("\n".join(reads)+"\n",encoding="utf-8")
    m.OUT["actual_link"]["reading_sha256"]=m.digest(REPORT.with_name("llvm-ocr-link-reading.txt"))
    m.OUT["link_evidence_complete"]=not unresolved
    row("actual LLVM OCR linker map, reproduction input digests and resolved member reads",
        "PASS_ACTUAL" if not unresolved else "FAIL",{"archives":len(archives),"members":sum(len(x) for x in members.values()),"unresolved":len(unresolved)})
    # Associate candidate full license sets with exact input families. This is
    # intentionally an evidence index, not an approval of unknown object terms.
    notices={}
    for k,s in m.OUT["sources"].items():
        notices[k]=[{x:y for x,y in n.items() if x in ("path","sha256")} for n in s["license_notice_documents"]]
    notices["llvm"]=[{x:y for x,y in n.items() if x in ("url","sha256","git_blob_sha1")} for n in m.OUT["source_licenses"]]
    notices["mingw_x64"]=[{x:y for x,y in n.items() if x in ("path","sha256")} for n in m.OUT["archive_notices"] if "/x86_64-w64-mingw32/share/" in n["path"]]
    m.OUT["notice_index"]=notices;save()

def product(base,exe,srcs):
    runtime=base/"runtime";(runtime/"bin").mkdir(parents=True)
    shutil.copyfile(exe,runtime/"bin/tesseract.exe")
    b.model(base,runtime)
    cfg=srcs["tess"]/"tessdata/configs/tsv"
    assert m.digest(cfg)=="59d079bb75d8b3d7c839a3564580cb559e362c93a9d70f234e421c0c3e767e04"
    shutil.copyfile(cfg,runtime/"tessdata/configs/tsv")
    moved=p.private_zip(base,exe,runtime)
    state,files=p.pngs(base,moved)
    input_file=base/"synthetic-input-paths.json";input_file.write_text(json.dumps(files),encoding="utf-8")
    output=base/"product-result.json";save()
    env={k:os.environ[k] for k in ("SystemRoot","WINDIR","SystemDrive","ComSpec","OS","PROCESSOR_ARCHITECTURE") if k in os.environ}
    for k in ("HOME","USERPROFILE","APPDATA","LOCALAPPDATA","TEMP","TMP","TMPDIR","PROGRAMDATA","ALLUSERSPROFILE","PUBLIC",
              "XDG_CONFIG_HOME","XDG_CACHE_HOME","XDG_DATA_HOME","XDG_STATE_HOME"):env[k]=str(state/"runtime")
    env["PATH"]=str(m.SYSTEM);env["PSModuleAnalysisCachePath"]=str(state/"runtime/ps-module-cache")
    r=subprocess.run([str(moved/"tool/node/node.exe"),str(ROOT/"tests/check_course_ocr_product.js"),str(moved),str(REPORT),str(input_file),str(output)],
        cwd=state,env=env,capture_output=True,timeout=600)
    rows=[]
    for line in r.stdout.decode("utf-8",errors="replace").splitlines():
        try:rows.append(json.loads(line))
        except ValueError:pass
    m.OUT["product_rows"]=rows;m.OUT["product_exit"]=r.returncode;save()
    if r.returncode:row("LLVM actual product harness","FAIL",r.stderr.decode("utf-8",errors="replace")[-4000:])
    assert r.returncode==0 and output.is_file()
    result=json.loads(output.read_bytes());m.OUT["product_result"]=result
    m.OUT["product_contract_passed"]=bool(result["completed"] and result["missingLanguage"])
    assert m.OUT["product_contract_passed"],"actual missing-language product path not proven"
    # New binary only: sample actual loaded modules and sockets on the same
    # fixed local PNG; does not repeat previous MSVC or browser matrix.
    cells=b.w.fixture(runtime)
    words=b.reduced_run(runtime,"course-table.png",6,"llvm-module-sample",None,None)
    assert words
    m.OUT["runtime_module_sample_passed"]=True
    row("LLVM native product PNG and separate actual process closure","PASS_ACTUAL",{"product_rows":len(rows),"cells":len(cells)})
    save()

def main():
    base=None
    try:
        parent=ROOT/"tmp";parent.mkdir(exist_ok=True);m.ancestors(parent);save()
        base=parent/("llvm-full-"+uuid.uuid4().hex[:8]);base.mkdir()
        tc=toolchain(base)
        supplement_notices()
        srcs={k:b.source(base,k,*v) for k,v in b.SOURCES.items()}
        exe,tools,env=build(base,tc,srcs)
        b.pe_check(exe)
        try:link_evidence(base,tc,tools,env)
        except Exception:row("LLVM actual linker evidence","FAIL",traceback.format_exc()[-6000:])
        product(base,exe,srcs)
    except Exception:row("LLVM reduced full OCR","FAIL_OR_BLOCKED",traceback.format_exc()[-6000:])
    finally:
        try:
            if base and base.exists():m.ancestors(base);shutil.rmtree(base)
            m.OUT["scratch_removed"]=base is None or not base.exists()
        except Exception:row("owned scratch cleanup","FAIL",traceback.format_exc()[-2000:])
        m.OUT["completed"]=True;save()
    return int(not (m.OUT.get("ocr_built") and m.OUT.get("product_contract_passed") and m.OUT.get("runtime_module_sample_passed") and m.OUT.get("link_evidence_complete") and m.OUT.get("scratch_removed")))
if __name__=="__main__":
    for s in (sys.stdout,sys.stderr):s.reconfigure(encoding="utf-8",errors="backslashreplace")
    raise SystemExit(main())
