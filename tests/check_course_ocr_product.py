"""Private Windows OCR entry validation with the exact reduced source graph.

No redistribution grant is asserted. The private ZIP stays on this runner and
is deleted, including the native bytes. Upload only synthetic result JSON/map.
"""
import collections
import hashlib
import importlib.util
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import traceback
import uuid
import zipfile
import zlib
from pathlib import Path

ROOT=Path(__file__).absolute().parents[1]
REPORT=Path(sys.argv[1]).absolute()
spec=importlib.util.spec_from_file_location("reduced",ROOT/"tests/check_minimal_ocr_build.py")
b=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=b
spec.loader.exec_module(b)
m=b.m
m.OUT.update(scope="private Windows product PNG contract and static link map only",
             product_contract_passed=False,link_evidence_complete=False,distribution_qualified=False,
             customer_candidate_built=False,private_zip_not_uploaded=True)
row=b.row
save=b.save

def collect_link(base,vs):
    dest=base/"build/tess"
    mapping=dest/"tesseract-product.map"
    m.ordinary(mapping)
    raw=mapping.read_bytes()
    assert 1000<len(raw)<50*1024*1024
    text=raw.decode("utf-8",errors="replace")
    objects=collections.Counter()
    for line in text.splitlines():
        match=re.search(r"\s([^\s:]+):([^\s]+\.obj)\s*$",line,re.I)
        if match:objects[match[1].lower()]+=1
    assert objects and any("libcmt" in x or "libucrt" in x or "libcpmt" in x for x in objects),objects
    files={}
    tlogs=[]
    roots=[base.resolve(),vs.resolve(),(Path(os.environ["ProgramFiles(x86)"])/"Windows Kits").resolve()]
    for p in dest.rglob("link.read.1.tlog"):
        data=p.read_bytes()
        decoded=data.decode("utf-16",errors="replace") if data.startswith((b"\xff\xfe",b"\xfe\xff")) else data.decode("utf-8",errors="replace")
        tlogs.append({"path":p.relative_to(dest).as_posix(),"sha256":m.digest(p)})
        for ln in decoded.splitlines():
            ln=ln.strip()
            if not ln.lower().endswith(".lib") or not re.match(r"^[A-Za-z]:[\\/]",ln):continue
            q=Path(ln)
            if not q.is_file():continue
            q=q.resolve()
            origin=next((i for i,r in enumerate(roots) if q.is_relative_to(r)),None)
            assert origin is not None,("unexpected linked library origin",q.name)
            key=["build","visual_studio","windows_sdk"][origin]+"/"+q.relative_to(roots[origin]).as_posix()
            files[key]={"size":q.stat().st_size,"sha256":m.digest(q)}
    assert tlogs and files,("missing actual link read inventory",tlogs)
    crt=[k for k in files if re.search(r"(?i)/(?:libcmt|libcpmt|libvcruntime|libucrt)\.lib$",k)]
    assert crt,("missing static CRT archive evidence",list(files))
    mapout=REPORT.with_name("course-ocr-link-map.txt")
    with mapout.open("xb") as f:f.write(raw)
    m.OUT["actual_link"]={"map_sha256":hashlib.sha256(raw).hexdigest(),"map_bytes":len(raw),"map_object_counts":dict(objects),
        "linked_library_reads":files,"static_crt_archives":crt,"link_read_logs":tlogs,
        "public_terms":["https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files",
          "https://learn.microsoft.com/cpp/windows/deployment-in-visual-cpp",
          "https://learn.microsoft.com/visualstudio/releases/2022/redistribution",
          "https://visualstudio.microsoft.com/license-terms/"],
        "license_entitlement_verified":False}
    m.OUT["link_evidence_complete"]=True
    row("actual static link map and resolved archive readback","PASS_ACTUAL",{"archive_count":len(files),"crt":crt,"map_sha256":m.OUT["actual_link"]["map_sha256"]})

def identity_tree(root):
    return {p.relative_to(root).as_posix():m.digest(p) for p in sorted(root.rglob("*")) if p.is_file()}

def private_zip(base,exe,runtime):
    initial=base/"private-ocr-source";initial.mkdir()
    for p in ("tool/python","tool/automation/course"):
        shutil.copytree(ROOT/p,initial/p)
    for p in ("tool/node/node.exe","tool/automation/browser-bridge.js"):
        dest=initial/p;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/p,dest)
    assert (initial/"tool/node/node.exe").read_bytes()[:2]==b"MZ"
    target=initial/"tool/automation/course/ocr-native"
    shutil.copytree(runtime,target)
    expected=identity_tree(initial)
    archive=base/"PRIVATE-NOT-FOR-DISTRIBUTION.zip"
    with zipfile.ZipFile(archive,"x",compression=zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for name in expected:z.write(initial/name,name)
    source_digest=m.digest(archive)
    unpack=base/"private-unpack";unpack.mkdir()
    with zipfile.ZipFile(archive) as z:
        assert sorted(z.namelist())==sorted(expected) and z.testzip() is None
        for name in expected:
            p=unpack/name;p.parent.mkdir(parents=True,exist_ok=True)
            with z.open(name) as i,p.open("xb") as o:shutil.copyfileobj(i,o)
    assert identity_tree(unpack)==expected
    moved=base/"Portable \u4e2d\u6587 \u7a7a\u683c";unpack.rename(moved)
    assert not unpack.exists() and identity_tree(moved)==expected
    row("private technical ZIP integrity, unpack and Chinese-space relocation","PASS_ACTUAL",
        {"members":len(expected),"sha256":source_digest,"not_customer_zip":True,"uploaded":False})
    return moved

def pngs(base,moved):
    from PIL import Image
    state=moved/"work/course-ocrfixture/a"
    for p in ("runtime","tmp","notes"): (state/p).mkdir(parents=True)
    fixture=base/"test-glyphs";fixture.mkdir()
    b.w.fixture(fixture)
    source=(fixture/"course-table.png").read_bytes()
    files={}
    def make(key,data=None):
        p=state/"tmp"/("ocr-"+uuid.uuid4().hex+".png")
        if data is not None:p.write_bytes(data)
        files[key]=str(p)
        return p
    make("normal",source)
    bad=bytearray(source);bad[29]^=1
    make("badcrc",bad)
    make("truncated",source[:-12])
    make("nonpng",b"\xff\xd8synthetic-not-png")
    wide=bytearray(source);wide[16:20]=struct.pack(">I",4097);wide[29:33]=struct.pack(">I",zlib.crc32(wide[12:29]))
    make("oversized",wide)
    with make("bytes").open("xb") as f:f.truncate(20*1024*1024+1)
    Image.new("1",(1200,850),1).save(make("blank"))
    outside=moved/"work"/("ocr-"+uuid.uuid4().hex+".png");outside.write_bytes(source);files["outside"]=str(outside)
    return state,files

def main():
    base=None
    try:
        parent=ROOT/"tmp";parent.mkdir(exist_ok=True);m.ancestors(parent);save()
        base=parent/("ocr-product-"+uuid.uuid4().hex[:8]);base.mkdir()
        vs,cmake=b.tools()
        srcs={k:b.source(base,k,*v) for k,v in b.SOURCES.items()}
        exe,prefix=b.build(base,srcs,vs,cmake,capture_link=True)
        b.pe_check(exe)
        try:collect_link(base,vs)
        except Exception:row("static link map evidence","FAIL",traceback.format_exc()[-4000:])
        runtime=base/"runtime";(runtime/"bin").mkdir(parents=True)
        shutil.copyfile(exe,runtime/"bin/tesseract.exe")
        b.model(base,runtime)
        cfg=srcs["tess"]/ "tessdata/configs/tsv"
        shutil.copyfile(cfg,runtime/"tessdata/configs/tsv")
        assert m.digest(cfg)=="59d079bb75d8b3d7c839a3564580cb559e362c93a9d70f234e421c0c3e767e04"
        moved=private_zip(base,exe,runtime)
        state,files=pngs(base,moved)
        input_file=base/"synthetic-input-paths.json";input_file.write_text(json.dumps(files),encoding="utf-8")
        output=base/"product-result.json";save()
        env={k:os.environ[k] for k in ("SystemRoot","WINDIR","SystemDrive","ComSpec","OS","PROCESSOR_ARCHITECTURE") if k in os.environ}
        for k in ("HOME","USERPROFILE","APPDATA","LOCALAPPDATA","TEMP","TMP","TMPDIR","PROGRAMDATA","ALLUSERSPROFILE","PUBLIC",
                  "XDG_CONFIG_HOME","XDG_CACHE_HOME","XDG_DATA_HOME","XDG_STATE_HOME"):
            env[k]=str(state/"runtime")
        env["PATH"]=str(m.SYSTEM)
        env["PSModuleAnalysisCachePath"]=str(state/"runtime/ps-module-cache")
        p=subprocess.run([str(moved/"tool/node/node.exe"),str(ROOT/"tests/check_course_ocr_product.js"),str(moved),str(REPORT),str(input_file),str(output)],
            cwd=state,env=env,capture_output=True,timeout=600)
        rows=[]
        for line in p.stdout.decode("utf-8",errors="replace").splitlines():
            try:rows.append(json.loads(line))
            except ValueError:pass
        m.OUT["product_rows"]=rows
        m.OUT["product_exit"]=p.returncode
        if p.returncode:row("actual product harness","FAIL",p.stderr.decode("utf-8",errors="replace")[-4000:])
        assert p.returncode==0 and output.is_file()
        result=json.loads(output.read_bytes())
        m.OUT["product_result"]=result
        m.OUT["product_contract_passed"]=bool(result["completed"] and result["missingLanguage"])
        assert m.OUT["product_contract_passed"],"actual missing-language path unavailable on this runner"
    except Exception:row("product native validation","FAIL_OR_BLOCKED",traceback.format_exc()[-6000:])
    finally:
        try:
            if base is not None and base.exists():m.ancestors(base);shutil.rmtree(base)
            m.OUT["scratch_removed"]=base is None or not base.exists()
        except Exception:row("scratch removal","FAIL",traceback.format_exc()[-2000:])
        m.OUT["completed"]=True;save()
    return int(not (m.OUT["product_contract_passed"] and m.OUT["link_evidence_complete"] and m.OUT.get("scratch_removed")))
if __name__=="__main__":
    for s in (sys.stdout,sys.stderr):s.reconfigure(encoding="utf-8",errors="backslashreplace")
    raise SystemExit(main())
