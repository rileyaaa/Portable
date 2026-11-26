"""Exact prior locked UCRT64 research; Windows XmlLite and actual local OCR only."""
import base64
import copy
import csv
import ctypes as C
from ctypes import wintypes as W
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import traceback
import uuid
import zlib

ROOT=Path(__file__).absolute().parents[1]
PRIOR=json.loads((ROOT/"tests/fixed_seed_f2py_ocr_45749259260.json").read_bytes())
LOCK=PRIOR["ocr_feasibility"]
assert PRIOR["artifact"]["id"]=="15085655070" and PRIOR["artifact"]["verified_downloadable"]
assert LOCK["unresolved_pe_imports"]==["xmllite.dll"] and len(LOCK["package_lock"])==49
assert len(LOCK["runtime_closure"])==41 and LOCK["completed"]
assert any(r["item"]=="all locked archives SHA256 and PKGINFO checked; no install scripts run" and r["status"]=="PASS_ACTUAL" for r in LOCK["rows"])
# Reuse the previous checked archive extractor/PE parser. Never invoke its
# repository database resolver or main(). Preserve the previous source.
spec=importlib.util.spec_from_file_location("frozen_ocr_helpers",ROOT/"tests/check_msys2_ocr_feasibility.py")
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
m.OUT.update(prior_run="45749259260",prior_record="eb7a10c6423078e3b1a8764149089685494f14b7",
    repository_snapshot_sha256=LOCK["repository_snapshot_sha256"],scope="same frozen archive graph, no distribution",
    limitations=["No current package database lookup or version replacement.",
      "Only local image/model input; process module/socket sampling is not an enforced air gap or exhaustive host tracing.",
      "Windows XmlLite is verified OS-only, never copied. Other static/system module boundaries unchanged.",
      "Separate signature/source report; no distribution or product integration.",
      "Synthetic raster fixture uses no Windows language pack or font installation."])
row=m.row
save=m.save
WIN=m.WIN
SYSTEM=m.SYSTEM
EXPECTED={x["file"]:x for x in LOCK["runtime_closure"]}
assert sum(x["compressed_size"] for x in LOCK["package_lock"])==64644179


def xmllite():
    k=C.WinDLL("kernel32",use_last_error=True)
    assert C.sizeof(C.c_void_p)==8
    k.GetSystemDirectoryW.argtypes=[W.LPWSTR,W.UINT];k.GetSystemDirectoryW.restype=W.UINT
    b=C.create_unicode_buffer(32768);n=k.GetSystemDirectoryW(b,len(b))
    assert 0<n<len(b) and Path(b.value).resolve()==SYSTEM.resolve()
    p=SYSTEM/"xmllite.dll";st=p.lstat()
    assert p.is_file() and not st.st_file_attributes&0x400 and p.resolve()==SYSTEM.resolve()/"xmllite.dll"
    pe=m.pefile.PE(str(p),fast_load=True)
    try:assert pe.FILE_HEADER.Machine==0x8664 and pe.FILE_HEADER.Characteristics&0x2000
    finally:pe.close()
    ps=SYSTEM/"WindowsPowerShell/v1.0/powershell.exe"
    code="""$ErrorActionPreference='Stop';$p=Join-Path ([Environment]::SystemDirectory) 'xmllite.dll';$s=Get-AuthenticodeSignature -LiteralPath $p;$v=(Get-Item -LiteralPath $p).VersionInfo;[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false);[ordered]@{status=[string]$s.Status;signer=[string]$s.SignerCertificate.Subject;thumbprint=[string]$s.SignerCertificate.Thumbprint;company=$v.CompanyName;product=$v.ProductName;original=$v.OriginalFilename;fileVersion=$v.FileVersion;signatureType=[string]$s.SignatureType}|ConvertTo-Json -Compress"""
    r=subprocess.run([str(ps),"-NoProfile","-NonInteractive","-Command",code],capture_output=True,timeout=90,check=True)
    info=json.loads(r.stdout.decode("utf-8-sig"))
    assert info["status"]=="Valid" and re.search(r"(?:^|,\s*)O=Microsoft Corporation(?:,|$)",info["signer"],re.I),info
    assert info["company"]=="Microsoft Corporation" and "windows" in info["product"].lower() and info["original"].lower()=="xmllite.dll",info
    # Explicit System32-only load verifies the actual native platform path.
    k.LoadLibraryExW.argtypes=[W.LPCWSTR,W.HANDLE,W.DWORD];k.LoadLibraryExW.restype=W.HMODULE
    k.GetModuleFileNameW.argtypes=[W.HMODULE,W.LPWSTR,W.DWORD];k.GetModuleFileNameW.restype=W.DWORD
    k.FreeLibrary.argtypes=[W.HMODULE];k.FreeLibrary.restype=W.BOOL
    h=k.LoadLibraryExW(str(p),None,0x800)
    if not h:raise C.WinError(C.get_last_error())
    try:
        n=k.GetModuleFileNameW(h,b,len(b));assert 0<n<len(b) and Path(b.value).resolve()==p.resolve()
    finally:assert k.FreeLibrary(h)
    info.update(path="Windows/System32/xmllite.dll",machine="AMD64",sha256=m.digest(p),native_load_verified=True,
        redistributable=False,source="https://learn.microsoft.com/en-us/previous-versions/windows/desktop/ee388577(v=vs.85)")
    row("actual Microsoft-signed AMD64 Windows System32 XmlLite, native load","PASS_ACTUAL",info)
    return p.resolve(),info


def frozen_archives(base):
    archives=base/"archives";archives.mkdir();pool=base/"pool";pool.mkdir()
    inventory={};locations={};records=[]
    for previous in LOCK["package_lock"]:
        rec=copy.deepcopy(previous)
        assert rec["url"]==m.REPO+rec["filename"]
        archive=archives/rec["filename"]
        m.download(rec["url"],archive,100*1024*1024,rec["sha256"],rec["compressed_size"])
        d=pool/rec["name"];d.mkdir()
        locations[rec["name"]]=m.extract_package(archive,rec,d,inventory)
        for key in ("selected_archive_members","notice_files","archive_pkginfo_license","pkgbase"):
            assert rec[key]==previous[key],(rec["name"],key)
        records.append({"name":rec["name"],"version":rec["version"],"sha256":rec["sha256"],
            "notice_files":rec["notice_files"],"archive_pkginfo_license":rec["archive_pkginfo_license"]})
        m.OUT["locked_archive_readback"]=records;save()
    row("all 49 original pinned archives and selected members/notice hashes match","PASS_ACTUAL",len(records))
    return inventory,locations


def fixture(runtime):
    # Deterministic test-only glyph raster (no font package or OS language).
    from PIL import Image
    a=json.loads((ROOT/"tests/ocr_synthetic_glyphs.json").read_bytes())
    raw=zlib.decompress(base64.b64decode(a["zlib_base64"],validate=True))
    assert hashlib.sha256(raw).hexdigest()==a["raw_sha256"] and len(raw)==4566
    images={};offset=0
    for char,l,t,w,h,advance,size in a["glyphs"]:
        assert char not in images and size==((w+7)//8)*h
        images[char]=(Image.frombytes("1",(w,h),raw[offset:offset+size]),l,t,advance)
        offset+=size
    assert offset==len(raw)
    cells=[("title","\u4e2d\u6587\u8bfe\u4ef6",80,50),
        ("rowlabel","\u6570\u91cf",80,200),("countlabel","\u91d1\u989d",650,200),
        ("1208","1208",80,340),("0.05","0.05",650,340),
        ("70301","70301",80,480),("9007","9007",650,480),
        ("watermark","\u6c34\u5370",80,690),("personal","\u7f16\u53f7314159",650,690)]
    im=Image.new("1",(1200,850),1)
    for _,text,x,y in cells:
        pos=float(x)
        for c in text:
            glyph,l,t,advance=images[c];im.paste(glyph,(round(pos)+l,y+t));pos+=advance
    p=runtime/"course-table.png";im.save(p);m.ordinary(p)
    row("local synthetic Chinese numeric page, no installed font or language dependency","PASS_ACTUAL",
        {"fixture_font":a["font"],"page":"1/1","size":im.size,"image_sha256":m.digest(p)})
    return cells


def socket_count(pid):
    # Read OS connection metadata; retain only the owned child PID's count.
    # No port scanning, connections, addresses, host firewall or privilege changes.
    dll=C.WinDLL("iphlpapi",use_last_error=True)
    total=0
    for name,af,kind,stride,offset in (("GetExtendedTcpTable",2,5,24,20),
      ("GetExtendedTcpTable",23,5,56,52),("GetExtendedUdpTable",2,1,12,8),
      ("GetExtendedUdpTable",23,1,28,24)):
        f=getattr(dll,name);f.argtypes=[C.c_void_p,C.POINTER(W.DWORD),W.BOOL,W.ULONG,C.c_int,W.ULONG];f.restype=W.DWORD
        size=W.DWORD(0);rc=f(None,C.byref(size),False,af,kind,0)
        assert rc in (0,122) and 4<=size.value<=16*1024*1024,(name,af,rc,size.value)
        for _ in range(3):
            b=C.create_string_buffer(size.value);rc=f(b,C.byref(size),False,af,kind,0)
            if rc==0:break
            assert rc==122 and size.value<=16*1024*1024
        assert rc==0,(name,af,rc)
        n=W.DWORD.from_buffer(b).value;assert 4+n*stride<=size.value
        total+=sum(W.DWORD.from_buffer(b,4+i*stride+offset).value==pid for i in range(n))
    return total


def local_run(runtime,image,psm,name,xml_path,xml_info):
    # One explicit executable, local PNG + local locked model only. Keep the
    # existing static import allowlist and actual system-directory boundary.
    assert re.fullmatch(r"[a-z0-9-]+\.png",image) and psm in (6,7)
    bindir=runtime/"bin";exe=bindir/"tesseract.exe"
    scratch=runtime/"temp";scratch.mkdir(exist_ok=True)
    env={k:os.environ[k] for k in ("SystemRoot","WINDIR","SystemDrive","ComSpec","OS","PROCESSOR_ARCHITECTURE") if k in os.environ}
    for key in ("HOME","USERPROFILE","APPDATA","LOCALAPPDATA","TEMP","TMP","TMPDIR","PROGRAMDATA","ALLUSERSPROFILE","PUBLIC"):env[key]=str(scratch)
    env["PATH"]=str(bindir)+os.pathsep+str(SYSTEM);env["TESSDATA_PREFIX"]="tessdata";env["OMP_THREAD_LIMIT"]="2"
    psapi=C.WinDLL("psapi",use_last_error=True)
    enum=psapi.EnumProcessModulesEx;enum.argtypes=[W.HANDLE,C.POINTER(W.HMODULE),W.DWORD,C.POINTER(W.DWORD),W.DWORD];enum.restype=W.BOOL
    filename=psapi.GetModuleFileNameExW;filename.argtypes=[W.HANDLE,W.HMODULE,W.LPWSTR,W.DWORD];filename.restype=W.DWORD
    output=runtime/(name+".tsv");errfile=runtime/(name+".stderr")
    loaded=set();system=set();outside=set();samples=0;network_samples=0;socket_max=0;xml_seen=False
    with output.open("xb") as out,errfile.open("xb") as err:
        p=subprocess.Popen([str(exe),image,"stdout","--tessdata-dir","tessdata","-l","chi_sim","--psm",str(psm),"tsv"],
            cwd=runtime,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err)
        try:
            deadline=time.monotonic()+120
            while p.poll() is None:
                if time.monotonic()>deadline:raise TimeoutError("local OCR")
                arr=(W.HMODULE*1024)();need=W.DWORD()
                if enum(W.HANDLE(int(p._handle)),arr,C.sizeof(arr),C.byref(need),3) and need.value<=C.sizeof(arr):
                    samples+=1
                    for module in arr[:need.value//C.sizeof(W.HMODULE)]:
                        buf=C.create_unicode_buffer(32768)
                        if not filename(W.HANDLE(int(p._handle)),module,buf,len(buf)):continue
                        q=Path(buf.value).resolve();key=q.name.casefold()
                        if key=="xmllite.dll":
                            assert q==xml_path and m.digest(q)==xml_info["sha256"]
                            xml_seen=True;system.add(key)
                        elif q.is_relative_to(bindir):
                            assert q==bindir/key and key in EXPECTED
                            loaded.add(key)
                        elif q.is_relative_to(SYSTEM) or q.is_relative_to(WIN/"WinSxS"):
                            system.add(key)
                        else:outside.add(q.name)
                socket_max=max(socket_max,socket_count(p.pid));network_samples+=1
                time.sleep(.025)
            rc=p.returncode
        finally:
            if p.poll() is None:p.kill();p.wait(timeout=15)
    info={"case":name,"returncode":rc,"module_samples":samples,"network_samples":network_samples,
        "owned_socket_max":socket_max,"bundled_modules":sorted(loaded),"system_module_names":sorted(system),
        "unexpected_module_basenames":sorted(outside),"xmllite_system32_loaded":xml_seen,
        "stderr":errfile.read_text(encoding="utf-8",errors="backslashreplace")[-500:]}
    ok=rc==0 and samples and network_samples and not socket_max and not outside and xml_seen and "tesseract.exe" in loaded
    row("actual local OCR process "+name,"PASS_ACTUAL" if ok else "FAIL",info)
    assert ok,info
    words=[]
    with output.open(encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f,delimiter="\t"):
            if r.get("level")=="5" and r.get("text","").strip():
                words.append({"text":r["text"].strip(),"x":int(r["left"]),"y":int(r["top"]),"w":int(r["width"]),"h":int(r["height"])})
    return words


def recognize(runtime,cells,xml_path,xml_info):
    from PIL import Image
    words=local_run(runtime,"course-table.png",6,"full-page",xml_path,xml_info)
    matches={};source=runtime/"course-table.png"
    for index,(key,expected,x,y) in enumerate(cells):
        # All boxes retain original page coordinates, including a normal
        # per-region OCR fallback for a missed table cell. Never substitute oracle text.
        box=[w for w in words if x-15<=w["x"]<x+500 and y-10<=w["y"]<y+90]
        box.sort(key=lambda w:w["x"])
        got="".join(w["text"] for w in box);method="full-page"
        if got!=expected:
            left=x-10;top=y-5;right=min(x+500,1200);bottom=y+90
            name="cell-"+str(index)
            with Image.open(source) as im:im.crop((left,top,right,bottom)).save(runtime/(name+".png"))
            box=local_run(runtime,name+".png",7,name,xml_path,xml_info)
            for w in box:w["x"]+=left;w["y"]+=top
            box.sort(key=lambda w:w["x"]);got="".join(w["text"] for w in box);method="actual source region"
        matches[key]={"expected":expected,"actual":got,"matched":got==expected,"method":method,
            "word_boxes":box,"source_page":"1/1","source_region":[x-10,y-5,min(x+500,1200),y+90]}
        m.OUT["synthetic_recognition"]=matches;save()
    assert all(x["matched"] and x["word_boxes"] for x in matches.values()),"unrecognized source cells"
    md="# "+matches["title"]["actual"]+"\n\nSource page 1/1\n\n"
    md+="| "+matches["rowlabel"]["actual"]+" | "+matches["countlabel"]["actual"]+" |\n|---:|---:|\n"
    md+="| "+matches["1208"]["actual"]+" | "+matches["0.05"]["actual"]+" |\n| "+matches["70301"]["actual"]+" | "+matches["9007"]["actual"]+" |\n\n## Source index\n"
    for n in ("1208","0.05","70301","9007"):
        w=matches[n]["word_boxes"][0];md+=f"- {matches[n]['actual']}: page 1, x={w['x']}, y={w['y']}\n"
    assert matches["watermark"]["actual"] not in md and matches["personal"]["actual"] not in md and "314159" not in md
    p=runtime/"reviewed-synthetic.md";p.write_text(md,encoding="utf-8")
    row("actual Chinese text, numeric table, source coordinates and reviewed redaction","PASS_ACTUAL",
        {"exact_cells":len(matches),"source_page":"1/1","markdown_sha256":m.digest(p),
         "full_page_cells":sum(x["method"]=="full-page" for x in matches.values()),"raw_image_sha256":m.digest(source)})


def main():
    m.ancestors(ROOT);base=ROOT/"tmp"/("ocr-locked-"+uuid.uuid4().hex);base.mkdir()
    try:
        xml_path,xml_info=xmllite()
        old=m.is_system
        m.is_system=lambda name:(name=="xmllite.dll" and xml_path.is_file() and m.digest(xml_path)==xml_info["sha256"]) or old(name)
        inventory,locations=frozen_archives(base)
        runtime=base/"Portable \u4e2d\u6587 \u7a7a\u683c";runtime.mkdir();bin_dir=runtime/"bin";bin_dir.mkdir()
        dlls=m.closure(inventory,bin_dir)
        assert dlls==EXPECTED and set(m.OUT["system_imports"])==set(LOCK["system_imports"])|{"xmllite.dll"}
        assert not (bin_dir/"xmllite.dll").exists()
        sizes={n:(bin_dir/n).stat().st_size for n in dlls}
        m.OUT["runtime_pe_bytes"]=sum(sizes.values());m.OUT["runtime_pe_sizes"]=sizes
        row("same 41 locked PE files; only verified OS XmlLite classification changed","PASS_ACTUAL",
            {"exe":1,"dll":40,"source_packages":len({x["owner"] for x in dlls.values()}),"pe_bytes":sum(sizes.values())})
        tess=runtime/"tessdata";tess.mkdir();(tess/"configs").mkdir()
        for pkg,rel in ((m.PREFIX+"tesseract-data-chi_sim","chi_sim.traineddata"),(m.PREFIX+"tesseract-ocr","configs/tsv")):
            src=locations[pkg]/"ucrt64/share/tessdata"/rel;m.ordinary(src);dst=tess/rel
            shutil.copyfile(src,dst);assert m.digest(src)==m.digest(dst)
        m.OUT["runtime_model_and_config"]=[{"path":p.relative_to(runtime).as_posix(),"size":p.stat().st_size,"sha256":m.digest(p)} for p in tess.rglob("*") if p.is_file()]
        save()
        cells=fixture(runtime);recognize(runtime,cells,xml_path,xml_info)
        for n,r in dlls.items():assert m.digest(bin_dir/n)==r["sha256"]
        assert not (bin_dir/"xmllite.dll").exists()
        m.OUT["technical_recognition_passed"]=True
        row("distribution and integration","BLOCKED_REVIEW","No new customer payload; signature/source/license review separate.")
    except Exception:row("locked OCR followup","FAIL_OR_BLOCKED",traceback.format_exc()[-7000:])
    finally:
        # Only this owned research subtree, never host/system DLLs or old candidate.
        shutil.rmtree(base);m.OUT["scratch_removed"]=not base.exists();m.OUT["completed"]=True;save()
    return int(not m.OUT.get("technical_recognition_passed",False))


if __name__=="__main__":
    for stream in (sys.stdout,sys.stderr):stream.reconfigure(encoding="utf-8",errors="backslashreplace")
    raise SystemExit(main())
