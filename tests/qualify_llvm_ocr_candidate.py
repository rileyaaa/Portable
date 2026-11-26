"""Build one actual customer OCR candidate, after fixed-source notice closure.

The old private product harness is NOT executed. Staged customer bytes are
committed locally only, then the ordinary packager and real shipped product
are tested; the workflow publishes no candidate before those gates pass.
"""
import base64,concurrent.futures,contextlib,hashlib,http.server,importlib.util,json,os,re,shutil,subprocess,sys,threading,traceback,uuid
from pathlib import Path
ROOT=Path(__file__).absolute().parents[1]
REPORT=Path(sys.argv[1]).absolute()
INFO=Path(sys.argv[2]).absolute()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/"tests"/path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod)
    return mod
q=load("qualified_llvm_build","check_llvm_mingw_ocr_build.py")
b=q.b;m=q.m;row=q.row;save=q.save
c=load("candidate_course_helpers","check_course_assistant.py")
OLD=json.loads((ROOT/"tests/llvm_full_ocr_45764713894.json").read_bytes())
MAP_PATH=ROOT/"tests/llvm_ocr_45764713894_object_sources.json"
MAP_RAW=MAP_PATH.read_bytes()
MAP=json.loads(MAP_RAW)
MAP_BLOB="45c0fe7dc7265a0a2b7d78dbd2aba1b4c592e573"
assert b.git_blob(MAP_RAW)==MAP_BLOB and MAP["missing"]==[] and len(MAP["sources"])==407
assert OLD["windows_job"]=="success" and OLD["link_evidence_complete"] and OLD["product_contract_passed"]
assert OLD["runtime_module_sample_passed"] and OLD["artifact_readback"]["llvm-ocr-link-map.txt"]["matches_report"]
START=os.environ["GITHUB_SHA"]
m.OUT.update(scope="actual unreleased customer OCR candidate only; no old private harness",
    prior_run="45764713894",source_commit=START,distribution_qualified=False,customer_candidate_built=False,
    customer_candidate_accepted=False,prior_candidate_id="15085655070",
    previous_private_test_reused_not_rerun=True,source_notice_review_passed=False)
def jsave(p,d):
    p.write_text(json.dumps(d,ensure_ascii=True,indent=2)+"\n",encoding="utf-8")
def identity(p):
    return {"size":p.stat().st_size,"sha256":m.digest(p)}
def git(*args):
    return subprocess.check_output(["git","-C",str(ROOT),*args],stderr=subprocess.STDOUT)
def head():
    return git("rev-parse","HEAD").decode().strip()
def member_names(link):
    return {(a,n) for a,ns in link["archive_members"].items() for n in ns}|{(a,v["name"]) for a,v in link["direct_objects"].items()}
assert {(x["archive"],x["member"]) for x in MAP["sources"]}==member_names(OLD["actual_link"])
NOTICE_BLOCKS={}
SOURCE_ROWS={}
FLAGS=[]
# Full original comment blocks, not edited license paraphrases. Fixed source
# identity and reviewed permissive component grants are the basis; this scan
# is an additional fail-closed check for an unexpected source-specific term.
COMMENTS=re.compile(rb'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*[\s\S]*?\*/|//[^\r\n]*(?:\r?\n[ \t]*//[^\r\n]*)*')
LEGAL=re.compile(rb"copyright|SPDX-License-Identifier|licensed under|redistribution|redistribute|public domain|permission (?:is |to |hereby )|all rights reserved|without restriction of copyright",re.I)
RESTRICTIVE=re.compile(rb"SPDX-License-Identifier\s*:\s*(?:A?GPL|LGPL)[-\d]|(?:licensed|distributed|released|redistributable|redistribute)[^\r\n]{0,90}(?:GNU (?:Affero |Lesser |Library )?General Public License|under (?:the )?(?:A?GPL|LGPL))|FIXME:\s*Cephes",re.I)
def collect(family,path,raw,kind,blob=None):
    key=family+"/"+path
    h=hashlib.sha256(raw).hexdigest()
    if blob is not None:
        assert b.git_blob(raw)==blob,("source blob differs",key,blob,b.git_blob(raw))
    if key in SOURCE_ROWS:
        assert SOURCE_ROWS[key]["sha256"]==h
        return
    notices=[]
    for match in COMMENTS.finditer(raw):
        s=match.group()
        if not s.startswith((b"//",b"/*")) or not LEGAL.search(s):continue
        assert len(s)<=256*1024,("source notice too large",key)
        sid=hashlib.sha256(s).hexdigest()
        rec=NOTICE_BLOCKS.setdefault(sid,{"raw":s,"files":[]})
        rec["files"].append(key);notices.append(sid)
        if RESTRICTIVE.search(s):
            FLAGS.append({"file":key,"notice_sha256":sid,"notice":s.decode("utf-8","backslashreplace")[:6000]})
    SOURCE_ROWS[key]={"sha256":h,"git_blob":blob,"kind":kind,"notice_blocks":sorted(set(notices))}
def fetch_code(rec,srcs):
    f,p,blob=rec["family"],rec["path"],rec["git_blob"]
    if f in srcs:
        path=srcs[f]/p;m.ordinary(path);raw=path.read_bytes()
    else:
        # Source paths in the immutable map were resolved at the exact source
        # tree. The already pinned LLVM tag is also checked against each blob.
        r=MAP["refs"][f]
        tag="llvmorg-23.1.6" if f=="llvm" else r["ref"]
        raw=q.a.fetch("https://raw.githubusercontent.com/"+r["repo"]+"/"+tag+"/"+p,8*1024*1024)
    assert b.git_blob(raw)==blob,("exact linked source mismatch",f,p,blob,b.git_blob(raw))
    return f,p,raw,blob
RUNTIME_HEADERS=[{"family":"mingw","path":"mingw-w64-crt/crt/seh_signal_dispatcher.h","git_blob":"7eb58b91096b02f2ebcf8f9fdcc741539a961c66"},{"family":"mingw","path":"mingw-w64-crt/gdtoa/gd_arith.h","git_blob":"f86e633b374334ca54dffac8a0ccb4bb577da16a"},{"family":"mingw","path":"mingw-w64-crt/gdtoa/gd_qnan.h","git_blob":"bd324f0f6f0878c3a81ce0b83e9481c03b86ac89"},{"family":"mingw","path":"mingw-w64-crt/gdtoa/gdtoa.h","git_blob":"b2b4c54151a0da327338210940e5470cbca33f11"},{"family":"mingw","path":"mingw-w64-crt/gdtoa/gdtoa_fltrnds.h","git_blob":"28c474e2c29f4b934a3e2b11d4fabfc10bfea3e2"},{"family":"mingw","path":"mingw-w64-crt/gdtoa/gdtoaimp.h","git_blob":"cc2007cd5fa3f0654b14acee99db363d515c44ad"},{"family":"mingw","path":"mingw-w64-crt/include/filetime_to_time64.h","git_blob":"afaa2b925f27795e1f9b24b9c3dc3d4a2e0836b2"},{"family":"mingw","path":"mingw-w64-crt/include/internal.h","git_blob":"78896eb89f06b1220b1825bda23c522fcb3a853d"},{"family":"mingw","path":"mingw-w64-crt/include/mingw-wchar.h","git_blob":"e372a74eac826b3ecda1610e616240ba1a0947e0"},{"family":"mingw","path":"mingw-w64-crt/include/msvcrt.h","git_blob":"9e48bf0694b3547f449e38109f9531f5d16bf3d2"},{"family":"mingw","path":"mingw-w64-crt/include/msvcrt_or_emu_glue.h","git_blob":"da470ce0891117c0df737a154b2ec67dad6680fa"},{"family":"mingw","path":"mingw-w64-crt/include/sect_attribs.h","git_blob":"7621e0494d1b744da0b1dc0e8b053a6bc85a8ab5"},{"family":"mingw","path":"mingw-w64-crt/include/thread_local.h","git_blob":"9da58bd5bf6bfe827912b848a5673df67eca28b4"},{"family":"mingw","path":"mingw-w64-crt/stdio/__mingw_fix_stat.h","git_blob":"438182913f73dbbc7cd54724a779b64feadf9963"},{"family":"mingw","path":"mingw-w64-crt/stdio/_findX.h","git_blob":"d95d9f8c383e852962a37444c36b71a7c27e71fc"},{"family":"mingw","path":"mingw-w64-crt/stdio/mingw_pformat.h","git_blob":"3381ff8ba9088f317dcf437729942d577c0a9126"},{"family":"mingw","path":"mingw-w64-crt/stdio/mingw_sformat.h","git_blob":"7d133dd7f29ba26c08aafbd4aeed5dc75e4808d0"},{"family":"mingw","path":"mingw-w64-crt/stdio/mingw_swformat.h","git_blob":"aea4c53fb6b0881d5374acd1db36c9024e93df43"}]
def put(folder,name,data):
    assert not name.startswith("/") and "\\" not in name and all(x not in ("",".","..") for x in name.split("/"))
    p=folder/name;p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():assert p.read_bytes()==data,("notice collision",name)
    else:
        with p.open("xb") as f:f.write(data)
    return p
def exact_text(doc):
    raw=doc["text"].encode("utf-8")
    assert hashlib.sha256(raw).hexdigest()==doc["sha256"],("lossy prior notice",doc.get("path",doc.get("url")))
    return raw
def audit_sources(srcs,folder):
    tasks=[x for x in MAP["sources"] if x["family"]!="mingw-import"]+MAP["embedded"]+RUNTIME_HEADERS
    unique={(x["family"],x["path"]):x for x in tasks}
    errors=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures={ex.submit(fetch_code,x,srcs):x for x in unique.values()}
        for future in concurrent.futures.as_completed(futures):
            rec=futures[future]
            try:
                f,p,raw,blob=future.result()
                collect(f,p,raw,"mapped-source-or-local-runtime-header",blob)
            except Exception as e:
                errors.append({"family":rec["family"],"file":rec["path"],"expected_blob":rec["git_blob"],"error":str(e)[:1000]})
    m.OUT["source_notice_audit"]={"mapped_sources":len(unique),"verified_sources":len(SOURCE_ROWS),
        "source_notice_blocks":len(NOTICE_BLOCKS),"source_errors":errors,"source_specific_terms_requiring_review":FLAGS.copy()}
    save()
    assert not errors,("actual source blobs unresolved",len(errors))
    assert not FLAGS,("additional source terms require review",len(FLAGS))
    # Exact signed nested sources, preserving all discovered upstream notices.
    for family,s in m.OUT["sources"].items():
        for doc in s["license_notice_documents"]:
            f=srcs[family]/doc["path"];m.ordinary(f)
            raw=f.read_bytes();assert hashlib.sha256(raw).hexdigest()==doc["sha256"]
            put(folder,"upstream/"+family+"/"+doc["path"],raw)
    for doc in OLD["source_licenses"]+OLD["supplemental_notice_documents"]:
        u=doc["url"].split("/")
        # https://raw.githubusercontent.com/owner/repo/ref/relative/path
        group={"llvm-project":"llvm","mingw-w64":"mingw","llvm-mingw":"llvm-mingw"}[u[4]]
        put(folder,"upstream/"+group+"/"+"/".join(u[6:]),exact_text(doc))
    for doc in MAP["additional_documents"]+[{"family":"mingw","path":"DISCLAIMER","git_blob":"51261a8ec4b5c5b6b074317fab1d7f506eb30425"}]:
        f,p,raw,blob=fetch_code(doc,srcs)
        put(folder,"upstream/"+f+"/"+p,raw)
    put(folder,"upstream/model/LICENSE",exact_text(OLD["model"]["source_license"]))
    # Source recipe evidence distinguishes the gdtoa strtof from the unrelated
    # stdio strtof, and the three direct CRT startup object origins.
    raw=q.a.fetch("https://raw.githubusercontent.com/mingw-w64/mingw-w64/41eb042358a52011b35350392130dcdc94a8ead8/mingw-w64-crt/Makefile.am",2*1024*1024)
    assert b.git_blob(raw)=="e6aad17d17b9a426381db733d6b4fa33b00d3c3a"
    assert b"gdtoa/strtof.c" in raw and b"lib64/crt1.o: crt/crtexe.c" in raw and b"lib64/crt2.o: lib64/crt1.o" in raw
    m.OUT["mingw_source_rules_blob"]=b.git_blob(raw)
    row("all fixed linked source identities and original source-level notice blocks","PASS_ACTUAL",m.OUT["source_notice_audit"])
def audit_headers(base,tc,srcs):
    # Actual compiler dependency database of the new customer build. No host
    # header or alternate SDK is silently accepted. Prebuilt runtime producer
    # header dependencies are not independently rebuilt by this test.
    ninja=Path(m.OUT["build_recipe"]["common"][2].split("=",1)[1])
    m.ordinary(ninja)
    deps=set()
    for key in ("zlib","png","lept","tess"):
        dest=base/"build"/key
        data=subprocess.check_output([str(ninja),"-t","deps"],cwd=dest,timeout=120).decode("utf-8","strict")
        for line in data.splitlines():
            if not line.startswith("    "):continue
            p=Path(line.strip())
            p=(dest/p).resolve() if not p.is_absolute() else p.resolve()
            assert p.is_relative_to(base.resolve()),("actual compiler dependency outside fixed build root",str(p))
            if p.is_file():deps.add(p)
    assert len(deps)>100,("compiler dependency evidence missing",len(deps))
    for p in sorted(deps):
        m.ordinary(p)
        if p.stat().st_size>8*1024*1024:raise ValueError("Unexpected compiler input size: "+p.name)
        family=next((k for k,v in srcs.items() if p.is_relative_to(v.resolve())),None)
        if family:
            rel=p.relative_to(srcs[family]).as_posix()
        elif p.is_relative_to(tc.resolve()):
            family="llvm-toolchain-header";rel=p.relative_to(tc).as_posix()
        else:
            family="generated-build-input";rel=p.relative_to(base).as_posix()
        collect(family,rel,p.read_bytes(),"actual-compiler-dependency")
    m.OUT["compiler_dependency_audit"]={"dependency_count":len(deps),"source_and_header_records":len(SOURCE_ROWS),
        "additional_terms_requiring_review":FLAGS.copy()}
    save()
    assert not FLAGS,("compiler input notices require further review",len(FLAGS))
    row("actual compiler dependency paths and source/header notice capture","PASS_ACTUAL",m.OUT["compiler_dependency_audit"])
def compare_link():
    new=m.OUT["actual_link"];old=OLD["actual_link"]
    assert m.OUT["link_evidence_complete"] and not new["unresolved_members"]
    expected=member_names(old);actual=member_names(new)
    m.OUT["linked_member_delta"]={"missing":sorted(expected-actual),"new":sorted(actual-expected)}
    assert actual==expected and set(new["input_files"])==set(old["input_files"]),m.OUT["linked_member_delta"]
    assert set(new["archives_without_member_reads"])==set(old["archives_without_member_reads"])
    for k,v in new["input_files"].items():
        if k.startswith("llvm-toolchain/"):assert v==old["input_files"][k],("toolchain link input changed",k)
    assert m.OUT["runtime_pe"]["imports_and_delay_imports"]==OLD["runtime_pe"]["imports_and_delay_imports"]
    assert m.OUT["source_patches"]==OLD["source_patches"]
    assert m.OUT["build_recipe"]["components"]==OLD["build_recipe"]["components"]
    m.OUT["actual_link_matches_review"]=True
    m.OUT["rebuild_byte_identical"]=m.OUT["runtime_pe"]==OLD["runtime_pe"]
    m.OUT["built_source_archive_digest_changes"]=[k for k,v in new["input_files"].items() if k.startswith("built-source/") and v!=old["input_files"][k]]
    row("new actual linker inputs match reviewed member inventory and fixed toolchain bytes","PASS_ACTUAL",
        {"linked_names":len(actual),"identical_exe":m.OUT["rebuild_byte_identical"],"source_digest_changes":m.OUT["built_source_archive_digest_changes"]})
def complete_notice_bundle(folder,runtime):
    put(folder,"source-map.json",MAP_RAW)
    blocks=[]
    for sid,v in sorted(NOTICE_BLOCKS.items()):
        blocks.append(("----- SHA256 "+sid+"; source files: "+", ".join(sorted(v["files"]))+" -----\n").encode("utf-8")+v["raw"]+b"\n\n")
    put(folder,"source-notices.txt",b"".join(blocks))
    exe=identity(runtime/"bin/tesseract.exe")
    model=identity(runtime/"tessdata/chi_sim.traineddata");config=identity(runtime/"tessdata/configs/tsv")
    assert model=={"size":2469156,"sha256":"a5fcb6f0db1e1d6d8522f39db4e848f05984669172e584e8d76b6b3141e1f730"}
    assert config=={"size":22,"sha256":"59d079bb75d8b3d7c839a3564580cb559e362c93a9d70f234e421c0c3e767e04"}
    readme="""Course OCR: third-party notices and exact source provenance
Tesseract 5.5.4 and tessdata_fast chi_sim 4.1.0: Apache 2.0.
Leptonica 1.87.0: its permissive BSD-style binary redistribution terms.
libpng 1.6.59 and zlib 1.4: their upstream permissive grants and notices.
LLVM-MinGW 20261117 x64 UCRT: libc++, libc++abi, libunwind, compiler-rt,
Apache 2.0 with LLVM exception and legacy notices; MinGW runtime ZPL,
public-domain and file-specific permissive terms including David M. Gay /
Lucent gdtoa and Keith Marshall formatting notices. Full original notices
and source-specific attributions are in this directory. The static member
inventory contains gdtoa, not an identified Cephes or profiling object.
The full MinGW runtime notice (including its own caveats) is retained.
Windows import records call the OS UCRT and Kernel32; no Windows DLL,
Microsoft SDK/CRT archive, compiler, original outline font, or build tool
is distributed by this OCR addition. No MSVC hosted license inferred.
Tesseract's embedded GlyphLessFont header is explicitly Apache-licensed;
Leptonica's embedded raster font data carries its binary redistribution
grant; bmf.c identifies rendered Palatino-Roman bitmaps, not a shipped font
program. Historical source outline font identity was not independently
reconstructed. The source-level notices include both embedded data headers.
Leptonica build-only modification: apply the MinGW DLL suffix only when
BUILD_SHARED_LIBS is true; exact original/modified hash and diff in
source-proof.json. No recognition source or codec changes.
Fixed publisher toolchain asset is SHA-256 pinned, not independently
signature verified or independently rebuilt. The linked source families
and actual compiler dependencies are checked; this is not a legal
guarantee about all unlinked components of upstream distributions.
"""
    put(folder,"README.txt",readme.encode("utf-8"))
    proof={"source_map_git_blob":MAP_BLOB,"linked_names":407,"unresolved":[],
        "exe":exe,"source_notice_review_passed":True,"actual_link_matches_review":True,
        "fixed_toolchain":m.OUT["release"],"actual_link_input_files":m.OUT["actual_link"]["input_files"],
        "map_sha256":m.OUT["actual_link"]["map_sha256"],"reading_sha256":m.OUT["actual_link"]["reading_sha256"],
        "source_rows":SOURCE_ROWS,"source_patches":m.OUT["source_patches"],
        "sources":{k:{n:v for n,v in d.items() if n!="license_notice_documents"} for k,d in m.OUT["sources"].items()},
        "model_source":{k:v for k,v in OLD["model"].items() if k!="source_license"},
        "prior_exe_identical":m.OUT["rebuild_byte_identical"],"compiler_dependencies":m.OUT["compiler_dependency_audit"],
        "limitations":["Named import-library records are not unique COFF import symbols; OS DLL closure verified from PE.",
          "No independent toolchain rebuild or exhaustive OS privacy tracing.",
          "Historic underlying outline font binary not independently identified; only explicitly licensed raster data shipped."]}
    put(folder,"source-proof.json",(json.dumps(proof,ensure_ascii=True,indent=2)+"\n").encode("utf-8"))
    docs={p.relative_to(folder).as_posix():identity(p) for p in sorted(folder.rglob("*")) if p.is_file()}
    manifest={"format":1,"distributionQualified":True,"reviewedSourceRun":45764713894,
        "linkedNameCount":407,"sourceMapGitBlob":MAP_BLOB,"unresolved":[],"runtime":exe,
        "model":model,"config":config,"noticeFiles":docs}
    mp=put(folder,"manifest.json",(json.dumps(manifest,ensure_ascii=True,indent=2)+"\n").encode("utf-8"))
    lock={"format":1,"engine":"tesseract-5.5.4","modelLanguage":"chi_sim","distributionQualified":True,
        "exe":exe,"noticeManifest":identity(mp),"evidence":"tool/licenses/course-ocr/manifest.json"}
    m.OUT["source_notice_review_passed"]=True;m.OUT["distribution_qualified"]=True
    m.OUT["notice_manifest"]=manifest;m.OUT["notice_manifest_identity"]=identity(mp);save()
    return lock
def replace_text(path,old,new):
    p=ROOT/path;s=p.read_text(encoding="utf-8");assert s.count(old)==1,(path,old)
    p.write_text(s.replace(old,new),encoding="utf-8",newline="\n")
def stage_candidate(runtime,folder,lock):
    assert head()==START and not git("status","--porcelain=v1","--untracked-files=all")
    native=ROOT/"tool/automation/course/ocr-native";notices=ROOT/"tool/licenses/course-ocr"
    assert not native.exists() and not notices.exists()
    shutil.copytree(runtime,native);shutil.copytree(folder,notices)
    jsave(ROOT/"tool/automation/course/ocr-native-lock.json",lock)
    attr=ROOT/".gitattributes"
    attr.write_bytes(attr.read_bytes()+b"\n# Exact qualified course OCR payload and lock bytes.\ntool/automation/course/ocr-native/** -text\ntool/automation/course/ocr-native-lock.json -text\n")
    replace_text("home/skills/course-assistant/references/usage.md","\u76ee\u524d\u5f00\u53d1\u9501\u5173\u95ed\uff0c\u65e0\u4e8c\u8fdb\u5236\u5206\u53d1\u3002",
        "\u672c\u5019\u9009\u5305\u7684\u5907\u63f4\u8f7d\u8377\u5df2\u5b8c\u6210\u56fa\u5b9a\u6765\u6e90\u53ca notice \u6821\u9a8c\uff1b\u4e0d\u4f5c\u5168\u5c40 OCR \u5f15\u64ce\uff0c\u4e0d\u6269\u5c55\u5176\u4ed6\u8bed\u8a00\u6216\u683c\u5f0f\u3002")
    replace_text("home/skills/course-assistant/SKILL.md","\u5f53\u524d\u5f00\u53d1\u9501\u5173\u95ed\uff0c\u4e0d\u80fd\u58f0\u79f0\u5df2\u5185\u7f6e\u3002",
        "\u672c\u5019\u9009\u5185\u7f6e\u56fa\u5b9a chi_sim \u539f\u751f\u5907\u63f4\uff0c\u4f7f\u7528\u524d\u4ecd\u6821\u9a8c\u5305\u5185\u8f7d\u8377\u3002")
    replace_text("README.md","Windows \u672c\u673a OCR\uff08\u4f9d\u8d56\u7cfb\u7edf\u8bed\u8a00\uff09","Windows \u672c\u673a OCR\uff08\u4f9d\u8d56\u7cfb\u7edf\u8bed\u8a00\uff0c\u4ec5 zh-Hans-CN \u7f3a\u5931\u65f6\u4f7f\u7528\u7ecf\u5ba1\u6838\u7684\u5305\u5185 chi_sim PNG \u5907\u63f4\uff09")
    paths=[".gitattributes","README.md","home/skills/course-assistant/references/usage.md","home/skills/course-assistant/SKILL.md",
           "tool/automation/course/ocr-native-lock.json","tool/automation/course/ocr-native","tool/licenses/course-ocr"]
    git("add","--",*paths)
    changed=git("diff","--cached","--name-only","-z").decode("utf-8").rstrip("\0").split("\0")
    assert changed and all(x in paths[:5] or x.startswith(("tool/automation/course/ocr-native/","tool/licenses/course-ocr/")) for x in changed)
    git("-c","user.name=github-actions[bot]","-c","user.email=41898282+github-actions[bot]@users.noreply.github.com","commit","-m","Stage qualified LLVM course OCR payload and complete notices")
    candidate=head()
    assert git("rev-parse","HEAD^").decode().strip()==START and not git("status","--porcelain=v1","--untracked-files=all")
    m.OUT["candidate_commit"]=candidate;save()
    return candidate
def pack(candidate):
    result=subprocess.check_output([str(ROOT/"tool/python/python.exe"),"-B",str(ROOT/"tool/package-release.py"),"--version","v0.172.0-portable.2"],cwd=ROOT,timeout=2400)
    info=json.loads(result)
    assert info["source_commit"]==candidate
    m.OUT["customer_candidate_built"]=True;m.OUT["candidate_build"]=info;save()
    jsave(INFO,info)
    return info
def product_direct(base,fixture):
    state,files=q.p.pngs(base,fixture)
    normal=Path(files["normal"]).read_bytes()
    ip=base/"customer-png-paths.json";jsave(ip,files)
    out=base/"customer-direct-result.json";save()
    env={k:os.environ[k] for k in ("SystemRoot","WINDIR","SystemDrive","ComSpec","OS","PROCESSOR_ARCHITECTURE") if k in os.environ}
    for k in ("HOME","USERPROFILE","APPDATA","LOCALAPPDATA","TEMP","TMP","TMPDIR","PROGRAMDATA","ALLUSERSPROFILE","PUBLIC","XDG_CONFIG_HOME","XDG_CACHE_HOME","XDG_DATA_HOME","XDG_STATE_HOME"):
        env[k]=str(state/"runtime")
    env["PATH"]=str(m.SYSTEM);env["PSModuleAnalysisCachePath"]=str(state/"runtime/ps-module-cache")
    p=subprocess.run([str(fixture/"tool/node/node.exe"),str(ROOT/"tests/check_course_ocr_candidate.js"),str(fixture),str(REPORT),str(ip),str(out)],
        cwd=state,env=env,capture_output=True,timeout=600)
    rows=[]
    for line in p.stdout.decode("utf-8","replace").splitlines():
        try:rows.append(json.loads(line))
        except ValueError:pass
    m.OUT["customer_direct_rows"]=rows;m.OUT["customer_direct_exit"]=p.returncode;save()
    if p.returncode:raise RuntimeError(p.stderr.decode("utf-8","replace")[-4000:])
    assert out.is_file() and json.loads(out.read_bytes())["missingLanguage"]
    Path(files["outside"]).unlink()
    shutil.rmtree(fixture/"work/course-ocrfixture")
    return normal
def actual_page(fixture,png):
    page_instance=uuid.uuid4().hex
    html=('<!doctype html><meta charset="utf-8"><title>Synthetic OCR page</title>'
          '<style>body{margin:0}img{display:block}</style><p id="page-label">Page 2 of 2</p>'
          '<p id="page-instance">'+page_instance+'</p><p id="not-image">Synthetic text</p>'
          '<img id="table" width="1200" height="850" src="data:image/png;base64,'+base64.b64encode(png).decode("ascii")+'">'
          '<img id="hidden" style="display:none" src="data:image/png;base64,'+base64.b64encode(png).decode("ascii")+'">').encode("utf-8")
    hits=[]
    class Page(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path!="/course/lesson":self.send_error(404);return
            hits.append(self.path);self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length",str(len(html)));self.end_headers();self.wfile.write(html)
        def do_POST(self):raise AssertionError("unexpected synthetic page POST")
    before=c.package_nonaccount(fixture)
    with http.server.ThreadingHTTPServer(("127.0.0.1",0),Page) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            origin="http://127.0.0.1:"+str(server.server_port)
            owner=c.Owner(fixture,"a",origin);client=c.Client(fixture,"a",owner.session)
            binding=client.call("course_bind",confirmed=True)["bindingId"]
            assert client.call("course_read",selector="#page-instance")["text"]==page_instance
            pre=client.call("course_ocr_check",language="zh-Hans-CN")
            assert pre["windowsSupported"] is False and pre["supported"] and pre["engine"]=="native" and pre["actualLanguage"]=="chi_sim"
            result=client.call("course_ocr",selector="#table",pageSelector="#page-label",language="zh-Hans-CN")
            assert result["engine"]=="native" and result["status"]=="ok" and result["source"]=={"pageLabel":"Page 2 of 2","imageSelector":"#table","bindingId":binding}
            expected=[("\u4e2d\u6587\u8bfe\u4ef6",80,50,650,150),("\u6570\u91cf",80,200,550,300),("\u91d1\u989d",650,200,1100,300),
                ("1208",80,340,550,440),("0.05",650,340,1100,440),("70301",80,480,550,580),("9007",650,480,1100,580),
                ("\u6c34\u5370",80,690,550,810),("\u7f16\u53f7314159",650,690,1150,810)]
            words=[w for l in result["lines"] for w in l["words"]]
            boxes=[]
            for want,x,y,x2,y2 in expected:
                found=sorted((w for w in words if w["x"]>=x-20 and w["x"]+w["width"]<=x2+20 and w["y"]>=y-20 and w["y"]+w["height"]<=y2+20),key=lambda w:w["x"])
                assert re.sub(r"\s+","","".join(w["text"] for w in found))==want,(want,[w["text"] for w in found])
                boxes.append([{"x":w["x"],"y":w["y"],"width":w["width"],"height":w["height"]} for w in found])
            row("actual customer course MCP missing-language fallback, nine Chinese/numeric cells and original page binding","PASS_ACTUAL",
                {"cells":9,"boxes":boxes,"pageLabel":"Page 2 of 2","engine":"native"})
            for sel,label in (("#not-image","#page-label"),("#hidden","#page-label"),("#table","#missing-label")):
                client.call("course_ocr",error=True,selector=sel,pageSelector=label,language="zh-Hans-CN")
            compact=lambda s:re.sub(r"[\W_]+","",s)
            marker="\u7f16\u53f7314159"
            assert marker in compact(result["text"]) and "\u6c34\u5370" in compact(result["text"])
            client.call("course_save_notes",error=True,slug="raw",markdown="# "+result["text"],excludedText=[marker],confirmed=True)
            md="# Reviewed synthetic table\n\nPage 2 of 2\n\n| Count | Amount |\n|---:|---:|\n| 1208 | 0.05 |\n| 70301 | 9007 |\n"
            saved=client.call("course_save_notes",slug="lesson",markdown=md,excludedText=[marker],confirmed=True)
            state=fixture/"work/course-fixture/a"
            note=state/saved["saved"]
            assert note.read_text(encoding="utf-8")==md and marker not in compact(md) and "\u6c34\u5370" not in md
            client.call("course_save_notes",error=True,slug="lesson",markdown="# replacement",excludedText=[],confirmed=True)
            client.call("course_save_notes",error=True,slug="signed",markdown="# Link https://example.invalid/a?signature=synthetic",excludedText=[],confirmed=True)
            assert client.call("course_read",selector="#page-instance")["text"]==page_instance
            assert client.call("course_status")["bindingId"]==binding and hits==["/course/lesson"]
            assert not list((state/"tmp").glob("ocr-*.png")) and list((state/"notes").iterdir())==[note]
            client.call("course_unbind",confirmed=True)
            client.call("course_ocr",error=True,selector="#table",pageSelector="#page-label",language="zh-Hans-CN")
            client.call("course_close",confirmed=True);assert client.end()==0;assert owner.p.wait(timeout=60)==0
            row("actual customer original page unchanged, image/label/unbound refusals, excluded marker and signed URL refusal, reviewed note and OCR temp cleanup","PASS_ACTUAL",
                {"raw_ocr_saved":False,"original_page_requests":len(hits),"notes":1,"owned_temp_pngs":0})
        finally:
            server.shutdown();thread.join(10)
    outside=c.differences(before,c.package_nonaccount(fixture))["package_outside_course_accounts"]
    assert not outside["new_or_changed"] and not outside["removed"] and not outside["incomplete"],outside
    row("actual candidate outside account package metadata unchanged","PASS_ACTUAL",outside)
def validate(base,info,candidate):
    c.REPORT=base/"customer-extract.json"
    previous=os.environ["GITHUB_SHA"];os.environ["GITHUB_SHA"]=candidate
    owned=base/"customer-extract";owned.mkdir()
    try:
        fixture,files=c.extract(info,owned)
        m.OUT["customer_zip_verified"]=True;m.OUT["customer_extract"]=c.META;save()
        normal=product_direct(base,fixture)
        actual_page(fixture,normal)
        c.verify(fixture,files,exact=False)
        row("all shipped customer ZIP member bytes unchanged after actual runtime","PASS_ACTUAL",len(files))
        m.OUT["customer_candidate_accepted"]=True;save()
    finally:
        os.environ["GITHUB_SHA"]=previous
        for process in reversed(c.PROCS):
            if process.poll() is None:
                subprocess.run([str(c.WIN/"System32/taskkill.exe"),"/PID",str(process.pid),"/T","/F"],capture_output=True,timeout=20,check=False)
                process.wait(timeout=30)
def main():
    base=None
    try:
        assert head()==START
        parent=ROOT/"tmp";m.ancestors(parent)
        # Reuse the previous actual build path on a fresh runner to avoid
        # unnecessary path variation in the newly generated executable.
        base=parent/"llvm-full-f4b14c0b";base.mkdir()
        tc=q.toolchain(base)
        m.OUT["supplemental_notice_documents"]=OLD["supplemental_notice_documents"]
        m.OUT["llvm_source_tag"]=OLD["llvm_source_tag"]
        srcs={k:b.source(base,k,*v) for k,v in b.SOURCES.items()}
        folder=base/"customer-notices";folder.mkdir()
        audit_sources(srcs,folder)
        q.patch_leptonica_mingw_static(srcs["lept"])
        exe,tools,env=q.build(base,tc,srcs)
        b.pe_check(exe);q.link_evidence(base,tc,tools,env);compare_link()
        audit_headers(base,tc,srcs)
        runtime=base/"customer-runtime";(runtime/"bin").mkdir(parents=True)
        shutil.copyfile(exe,runtime/"bin/tesseract.exe");b.model(base,runtime)
        shutil.copyfile(srcs["tess"]/"tessdata/configs/tsv",runtime/"tessdata/configs/tsv")
        lock=complete_notice_bundle(folder,runtime)
        candidate=stage_candidate(runtime,folder,lock)
        info=pack(candidate);validate(base,info,candidate)
    except Exception:
        row("customer OCR candidate","FAIL_OR_BLOCKED",traceback.format_exc()[-8000:])
    finally:
        try:
            if base and base.exists():m.ancestors(base);shutil.rmtree(base)
            m.OUT["scratch_removed"]=base is None or not base.exists()
        except Exception:row("scratch cleanup","FAIL",traceback.format_exc()[-2000:])
        m.OUT["completed"]=True;save()
    return int(not (m.OUT["distribution_qualified"] and m.OUT["customer_candidate_accepted"] and m.OUT.get("scratch_removed")))
if __name__=="__main__":
    for s in (sys.stdout,sys.stderr):s.reconfigure(encoding="utf-8",errors="backslashreplace")
    raise SystemExit(main())
