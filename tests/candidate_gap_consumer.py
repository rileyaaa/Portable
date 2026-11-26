"""Targeted existing-function consumer; run by real extracted BAT/Codex/Host.
MODE is injected by the test supervisor, not an application setting.
All inputs are synthetic, no host profile scan, optional installs or ACL changes.
"""
import hashlib,importlib.util,json,os,re,shutil,sqlite3,subprocess,sys,tempfile,tomllib,traceback,zipfile
from pathlib import Path
from unittest import mock
ROOT=Path(os.environ["CODEX_INSTALL_DIR"]).resolve()
WORK=ROOT/"work/tool-probe"
OUT=WORK/"closeout-inputs";OUT.mkdir()
RESULT=WORK/"targeted-results.jsonl"
PY=ROOT/"tool/python/python.exe";NODE=ROOT/"tool/node/node.exe"
WIN=Path(os.environ["SystemRoot"]);CMD=WIN/"System32/cmd.exe"
def digest(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def row(item,status,detail="",covers=(),env=(),packages=()):
    r=dict(mode=MODE,item=item,status=status,detail=str(detail)[:5000],covers=list(covers),env=list(env),packages=list(packages))
    with RESULT.open("a",encoding="utf-8",newline="\n") as f:f.write(json.dumps(r,ensure_ascii=True)+"\n")
def case(item,fn,covers=(),env=(),packages=(),status="PASS_ACTUAL"):
    try:row(item,status,fn(),covers,env,packages)
    except Exception:row(item,"FAIL",traceback.format_exc(),covers,env,packages)
def run(exe,args,cwd=OUT,extra=None,remove=(),timeout=120):
    exe=Path(exe).absolute()
    assert exe.is_relative_to(ROOT) or exe==CMD
    assert exe.is_file() and exe.stat().st_nlink==1
    env=dict(os.environ)
    for k in remove:env.pop(k,None)
    if extra:env.update(extra)
    assert cwd.is_relative_to(ROOT)
    argv=[str(exe),*map(str,args)]
    if exe.suffix.lower() in (".bat",".cmd"):
        argv='"'+str(CMD)+'" /d /s /c "'+subprocess.list2cmdline(argv)+'"';exe=CMD
    p=subprocess.run(argv,executable=str(exe),cwd=cwd,env=env,stdin=subprocess.DEVNULL,capture_output=True,timeout=timeout)
    return p.returncode,p.stdout.decode("utf-8","replace"),p.stderr.decode("utf-8","replace")
def script(rel,*args):
    return run(PY,["-I","-B",ROOT/rel,*args])
def failed(r,marker):
    assert r[0]!=0 and marker.casefold() in (r[1]+r[2]).casefold(),r
    assert "No module named 'office'" not in r[2] and "No module named 'portable_safety'" not in r[2],r
def ok(r):
    assert r[0]==0,r
    return r[1]
def package_modules(*mods):
    for mod in mods:assert Path(mod.__file__).resolve().is_relative_to(ROOT/"tool/python"),mod.__name__
def native_identity():
    assert Path(sys.executable).resolve()==PY and sys.flags.isolated and sys.flags.safe_path and sys.flags.ignore_environment
    assert all(Path(x).resolve().is_relative_to(ROOT/"tool/python") for x in sys.path if x)
    cfg=tomllib.loads((ROOT/"home/config.toml").read_text(encoding="utf-8-sig"))
    expected=("danger-full-access","never",True) if MODE=="yolo" else ("workspace-write","on-request",False)
    assert (cfg["sandbox_mode"],cfg["approval_policy"],cfg["sandbox_workspace_write"]["network_access"])==expected
    for executable in ("python.exe","node.exe","pip.cmd"):
        got=shutil.which(executable);assert got and Path(got).resolve().is_relative_to(ROOT),(executable,got)
    return {"actual_binary":str(PY.relative_to(ROOT)),"mode":expected,"isolated":True}
case("native interpreter and generated mode policy",native_identity,["tool/python/python.exe","run-codex.ps1"],
     ["CODEX_SANDBOX_MODE","CODEX_APPROVAL_POLICY","CODEX_SANDBOX_NETWORK_ACCESS"],status="PASS_CONFIG_GATE")
PATH_PY_CODE="""import json,pathlib,sys
identity=json.dumps(sys.executable,ensure_ascii=True)
with pathlib.Path(sys.argv[1]).open('x',encoding='ascii') as f:
    f.write(identity)
try:
    print(identity,flush=True)
except Exception:
    print('PORTABLE_PATH_REPORT_ERROR',file=sys.stderr,flush=True)
    raise
"""
PATH_NODE_CODE="""const fs=require('node:fs');
const identity=JSON.stringify(process.execPath);
fs.writeFileSync(process.argv[1],identity,{flag:'wx',encoding:'utf8'});
try { fs.writeSync(1,identity+'\\n'); }
catch (e) { fs.writeSync(2,'PORTABLE_PATH_REPORT_ERROR\\n'); throw e; }
"""
def path_resolution(name,expected,args,proof):
    detail={"expected":str(expected),"resolved":None,"execution_verified":False,
            "stage":"PROBE_CONTEXT_INVALID"}
    try:
        assert Path(sys.executable).resolve()==PY and sys.flags.isolated
        detail["stage"]="PATH_RESOLUTION_FAILED"
        search=os.environ.get("PATH")
        got=shutil.which(name,path=search) if search else None
        detail["resolved"]=got
        if not got or Path(got).absolute()!=expected or Path(got).resolve()!=expected:
            detail["reason"]="name did not resolve to expected package binary"
            return "FAIL",detail
        if not any(Path(part.strip('"')).absolute()==expected.parent
                   for part in search.split(os.pathsep) if part):
            detail["reason"]="expected directory absent from explicit PATH"
            return "FAIL",detail
        # Execute only the verified result of name lookup. Do not let Windows
        # search again (the parent application's directory can precede PATH).
        # This proves PATH lookup + actual bundled binary, not OS search order.
        detail["stage"]="EXECUTION_FAILED"
        assert not proof.exists() and not proof.is_symlink()
        rc,out,err=run(Path(got),[*args,proof.name])
        detail.update(exit=rc,stdout=out[-1200:],stderr=err[-1600:])
        if not proof.is_file() or proof.is_symlink() or proof.stat().st_nlink!=1:
            return "FAIL",detail
        actual=json.loads(proof.read_text(encoding="utf-8"))
        detail["actual_binary"]=actual
        detail["execution_verified"]=Path(actual).absolute()==expected and Path(actual).resolve()==expected
        if not detail["execution_verified"]:
            return "FAIL",detail
        # Only a verified identity plus an explicit output-stage failure can
        # classify a nonzero process exit as reporting-only.
        if rc!=0 and "PORTABLE_PATH_REPORT_ERROR" not in err.splitlines():
            return "FAIL",detail
        detail["stage"]="REPORTING_FAILED"
        if rc!=0 or json.loads(out)!=actual:
            return "FAIL",detail
        detail["stage"]="COMPLETE"
        return "PASS_ACTUAL",detail
    except Exception:
        detail["error"]=traceback.format_exc()[-1600:]
        return "FAIL",detail
for name,expected,args in (("node.exe",NODE,["-e",PATH_NODE_CODE]),
                           ("python.exe",PY,["-I","-B","-c",PATH_PY_CODE])):
    status,detail=path_resolution(name,expected,args,OUT/("path-"+name+".json"))
    row("actual PATH-resolved "+name+" invocation",status,detail,
        [expected.relative_to(ROOT).as_posix()],["PATH"])
def python_tmp():
    p=Path(tempfile.gettempdir()).resolve()
    assert p.is_relative_to(ROOT)
    with tempfile.NamedTemporaryFile() as f:
        actual=Path(f.name)
        assert actual.parent.resolve()==p
        f.write(b"owned");f.flush();f.seek(0);assert f.read()==b"owned"
    assert not actual.exists()
    return {"actual_default_directory":p.relative_to(ROOT).as_posix(),"create_read_delete":True}
# Default path behavior is observed but not credited to every variable.
case("Python actual default temp file lifecycle",python_tmp,["tool/python/python.exe"])
PY_TMP_CODE="""import json,pathlib,sys,tempfile
expected=pathlib.Path(sys.argv[1]).resolve()
# Check actual environment precedence and selected owned directory first.
assert pathlib.Path(tempfile._candidate_tempdir_list()[0]).resolve()==expected
check=expected/'preflight'
with check.open('xb') as handle:
    handle.write(b'x')
check.unlink()
d=pathlib.Path(tempfile.gettempdir()).resolve()
assert d==expected,(d,expected)
with tempfile.NamedTemporaryFile() as f:
    p=pathlib.Path(f.name)
    assert p.parent.resolve()==d and p.is_file()
    assert f.write(b'owned')==5
    f.flush();f.seek(0);assert f.read()==b'owned'
assert not p.exists()
print(json.dumps({'directory':str(d),'file':str(p)},ensure_ascii=True),flush=True)
"""
NODE_TMP_CODE="""const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const d=path.resolve(os.tmpdir()),expected=path.resolve(process.argv[1]);
if(d!==expected)throw Error('Unexpected temp directory');
const sub=fs.mkdtempSync(path.join(d,'portable-probe-')),p=path.join(sub,'owned');
try {
    fs.writeFileSync(p,'owned',{flag:'wx'});
    if(fs.readFileSync(p,'utf8')!=='owned')throw Error('Temp readback failed');
} finally {
    if(fs.existsSync(p))fs.unlinkSync(p);
    fs.rmdirSync(sub);
}
if(fs.existsSync(sub))throw Error('Temp cleanup failed');
console.log(JSON.stringify({directory:d,file:p}));
"""
def tmp_contrast(engine,key,removed):
    parent=OUT/("actual-"+engine+"-"+key.lower());parent.mkdir()
    paths={k:parent/k.lower() for k in ("TMPDIR","TEMP","TMP")}
    for p in paths.values():p.mkdir()
    env={k:str(v) for k,v in paths.items() if k not in removed}
    expected=paths[key]
    if engine=="python":
        r=run(PY,["-I","-B","-c",PY_TMP_CODE,expected],extra=env,remove=removed)
    else:
        r=run(NODE,["-e",NODE_TMP_CODE,expected],extra=env,remove=removed)
    data=json.loads(ok(r))
    actual=Path(data["directory"]).resolve();file=Path(data["file"])
    assert actual==expected and file.is_relative_to(expected) and not file.exists(),data
    assert all(not list(p.iterdir()) for p in paths.values())
    for p in paths.values():p.rmdir()
    parent.rmdir()
    return {"consumer":engine,"selected_variable":key,"removed":removed,
            "directory":actual.relative_to(ROOT).as_posix(),"create_read_delete":True}
for engine,key,removed in (("python","TMPDIR",()),("python","TEMP",("TMPDIR",)),
                           ("python","TMP",("TMPDIR","TEMP")),("node","TEMP",()),
                           ("node","TMP",("TEMP",))):
    binary=PY if engine=="python" else NODE
    case("actual "+engine+" "+key+" independent temp lifecycle",
         lambda e=engine,k=key,r=removed:tmp_contrast(e,k,r),
         [binary.relative_to(ROOT).as_posix()],[key])
def home_actual():
    want=Path(os.environ["USERPROFILE"]).resolve();assert want.is_relative_to(ROOT)
    assert Path(os.path.expanduser("~")).resolve()==want
    r=json.loads(ok(run(NODE,["-e","console.log(JSON.stringify({exe:process.execPath,home:require('node:os').homedir()}))"])))
    assert Path(r["exe"]).resolve()==NODE and Path(r["home"]).resolve()==want
    return {"home":want.relative_to(ROOT).as_posix(),"actual_python_expanduser_and_node_homedir":True}
case("actual Windows USERPROFILE consumer",home_actual,["tool/python/python.exe","tool/node/node.exe"],["USERPROFILE"])
def pip_actual():
    assert os.environ["PIP_CONFIG_FILE"].lower()=="nul"
    fixture=OUT/"synthetic-pip.ini";fixture.write_text("[global]\ntimeout=17\n",encoding="ascii")
    shim=ROOT/"tool/bin/pip.cmd"
    denied=run(shim,["config","get","global.timeout"])
    assert denied[0]!=0 and "global.timeout" in denied[1]+denied[2],denied
    contrast=ok(run(shim,["config","get","global.timeout"],extra={"PIP_CONFIG_FILE":str(fixture)})).strip()
    assert contrast=="17",contrast
    again=run(shim,["config","get","global.timeout"]);assert again[0]!=0
    return {"default_config_disabled":True,"owned_explicit_child_config_value":17,"default_restored":True}
case("actual pip config-file disabled/explicit child contrast",pip_actual,["tool/bin/pip.cmd","tool/bin/portable-python-cli.py"],["PIP_CONFIG_FILE"],["pip"])

PDF="home/skills/pdf/scripts/"
DOC="home/skills/docx/scripts/accept_changes.py"
PPT="home/skills/pptx/scripts/thumbnail.py"
XLS="home/skills/xlsx/scripts/recalc.py"
def pdf_boxes():
    fields={"form_fields":[{"page_number":1,"description":"\u6d4b\u8bd5\u5b57\u6bb5","label_bounding_box":[1,1,20,10],"entry_bounding_box":[30,1,60,20],"entry_text":{"font_size":12}}]}
    good=OUT/"\u4e2d\u6587 \u5b57\u6bb5.json";good.write_text(json.dumps(fields,ensure_ascii=False),encoding="utf-8")
    assert "SUCCESS: All bounding boxes are valid" in ok(script(PDF+"check_bounding_boxes.py",good))
    fields["form_fields"][0]["entry_bounding_box"]=[2,2,8,8]
    bad=OUT/"\u9519\u8bef \u5b57\u6bb5.json";bad.write_text(json.dumps(fields,ensure_ascii=False),encoding="utf-8")
    r=script(PDF+"check_bounding_boxes.py",bad)
    assert r[0]==1 and "FAILURE:" in r[1] and "\u6d4b\u8bd5\u5b57\u6bb5" in r[1] and "SUCCESS:" not in r[1],r
    return {"valid_exit":0,"overlap_exit":r[0],"utf8_description":True}
case("actual PDF bounding-box success and failure exit",pdf_boxes,[PDF+"check_bounding_boxes.py",PDF+"portable_safety.py"])
def pdf_image():
    from PIL import Image
    source=OUT/"\u539f\u9875.png";dest=OUT/"\u6807\u6ce8 \u9875.png"
    Image.new("RGB",(100,100),"white").save(source);before=digest(source)
    data={"form_fields":[{"page_number":1,"description":"\u4e2d\u6587","label_bounding_box":[5,5,20,20],"entry_bounding_box":[30,30,60,60]}]}
    f=OUT/"\u6807\u6ce8.json";f.write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8")
    assert "2 bounding boxes" in ok(script(PDF+"create_validation_image.py",1,f,source,dest))
    with Image.open(dest) as im:
        assert im.size==(100,100) and im.getpixel((5,5))==(0,0,255) and im.getpixel((30,30))==(255,0,0)
    assert digest(source)==before
    outside=ROOT.parent/"owned-outside.pdf.png";assert not outside.exists()
    r=script(PDF+"create_validation_image.py",1,f,source,outside)
    failed(r,"outside");assert not outside.exists()
    return {"pixels_checked":2,"original_unchanged":True,"outside_output_refused":True}
case("actual PDF validation image and outside-output refusal",pdf_image,[PDF+"create_validation_image.py",PDF+"portable_safety.py"],packages=["pillow"])
def optional_pdf(rel,dep,args):
    # These modules are deliberately not installed by this project.
    if importlib.util.find_spec(dep) is not None:
        row("optional PDF "+rel,"NOT_RUN","dependency present; this missing-dependency probe is not applicable",[PDF+rel]);return
    r=script(PDF+rel,*args)
    failed(r,"No module named '"+dep+"'")
    row("optional PDF "+rel,"KNOWN_LIMIT","actual bundled entry stops on missing "+dep+"; no install or host fallback",[PDF+rel])
for rel,dep,n in [("check_fillable_fields.py","pypdf",1),("extract_form_field_info.py","pypdf",2),
 ("fill_fillable_fields.py","pypdf",3),("fill_pdf_form_with_annotations.py","pypdf",3),
 ("extract_form_structure.py","pdfplumber",2),("convert_pdf_to_images.py","pdf2image",2)]:
    try:optional_pdf(rel,dep,[OUT/("absent"+str(i)) for i in range(n)])
    except Exception:row("optional PDF "+rel,"FAIL",traceback.format_exc(),[PDF+rel])
def office():
    import docx,pptx,openpyxl
    package_modules(docx,pptx,openpyxl)
    d=docx.Document();d.add_paragraph("\u4e2d\u6587 \u6d4b\u8bd5")
    src=OUT/"\u539f\u6587.docx";d.save(src);before=digest(src)
    dst=OUT/"\u5df2\u6709.docx";other=docx.Document();other.add_paragraph("preserve");other.save(dst);old=digest(dst)
    absent=OUT/"must-not-create"/"result.docx"
    assert not (ROOT/"tool/office/libreoffice/program/soffice.exe").exists()
    for p in (dst,src,absent):
        failed(script(DOC,src,p),"package-local tool is missing")
    assert digest(src)==before and digest(dst)==old and not absent.parent.exists()
    row("actual DOCX missing LibreOffice refuses before output modification","PASS_ACTUAL",{"existing":True,"same_input":True,"new_parent":False},[DOC],packages=["python-docx"])
    wb=openpyxl.Workbook();wb.active["A1"]="=1+2";book=OUT/"\u516c\u5f0f.xlsx";wb.save(book);wb.close()
    before=digest(book);r=script(XLS,book)
    assert r[0]==1 and "package-local LibreOffice is missing" in json.loads(r[1])["error"],r
    assert digest(book)==before
    row("actual XLSX missing LibreOffice returns structured error without rewriting","PASS_ACTUAL","formula file identical",[XLS],packages=["openpyxl"])
    deck=pptx.Presentation();deck.slides.add_slide(deck.slide_layouts[6]);presentation=OUT/"\u6295\u5f71.pptx";deck.save(presentation)
    before=digest(presentation);prefix=OUT/"thumb"
    failed(script(PPT,presentation,prefix,"--cols","0"),"--cols must be positive")
    failed(script(PPT,presentation,prefix),"package-local tool is missing")
    assert digest(presentation)==before and not list(OUT.glob("thumb*.jpg"))
    row("actual PPTX invalid grid option and missing renderer refusal","PASS_ACTUAL","input identical; no output",[PPT],packages=["python-pptx"])
    for rel,detail in ((DOC,"LibreOffice accept macro"),(XLS,"LibreOffice formula calculation"),(PPT,"LibreOffice/Poppler thumbnail rendering")):
        row("optional actual "+detail,"KNOWN_LIMIT","renderer not shipped; no installation or simulated result counted as render",[rel])
    # Staging regression: only the optional subprocess is mocked; actual
    # product code and package-local output/cleanup are exercised.
    directory=ROOT/"home/skills/docx/scripts"
    sys.path.insert(0,str(directory))
    spec=importlib.util.spec_from_file_location("document_acceptance_probe",ROOT/DOC)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    try:
        existing=OUT/"\u5df2\u6709.docx";old=digest(existing)
        scratch_before=set((ROOT/"tmp/office").iterdir()) if (ROOT/"tmp/office").exists() else set()
        def simulated_failure(argv,**kwargs):
            staged=Path(argv[-1]);assert staged!=existing and staged.is_relative_to(ROOT/"tmp/office")
            staged.write_bytes(b"partial");return subprocess.CompletedProcess(argv,1,"","synthetic renderer failure")
        with mock.patch.object(mod,"get_soffice_executable",return_value="synthetic-not-executed"),mock.patch.object(mod,"get_soffice_env",return_value={}),mock.patch.object(mod,"_setup_libreoffice_macro",return_value=True),mock.patch.object(mod.subprocess,"run",side_effect=simulated_failure):
            _,msg=mod.accept_changes(str(src),str(existing))
            assert msg.startswith("Error:") and digest(existing)==old
        assert set((ROOT/"tmp/office").iterdir())==scratch_before
        row("DOCX staged partial renderer failure leaves existing output","PASS_MOCK","real staging and cleanup; renderer simulated",[DOC])
    finally:sys.path.remove(str(directory))
try:office()
except Exception:row("targeted Office consumer","FAIL",traceback.format_exc(),[DOC,XLS,PPT])

def ssh():
    rel="tool/portable-ssh.py"
    r=script(rel,"keygen","--name","synthetic-closeout","--unencrypted")
    if r[0]:
        row("actual SSH private-directory keygen","FAIL",{"returncode":r[0],"error":r[2][-1400:],"key_exists":(ROOT/"work/ssh/keys/synthetic-closeout").exists(),"policy_unchanged":True},[rel],packages=["paramiko","cryptography"])
        return
    import paramiko
    package_modules(paramiko)
    path=ROOT/"work/ssh/keys/synthetic-closeout"
    key=paramiko.Ed25519Key.from_private_key_file(str(path));assert key.get_name()=="ssh-ed25519"
    pub=path.with_name(path.name+".pub");assert pub.read_text().strip()==key.get_name()+" "+key.get_base64()
    before=digest(path);failed(script(rel,"keygen","--name",path.name,"--unencrypted"),"already exist")
    assert digest(path)==before
    row("actual SSH private-directory keygen","PASS_ACTUAL","local synthetic key and public readback; no real remote, no ACL change",[rel],packages=["paramiko","cryptography"])
try:ssh()
except Exception:row("actual SSH private-directory keygen","FAIL",traceback.format_exc(),["tool/portable-ssh.py"])
row("actual SSH remote login/SFTP","NOT_RUN","no remote credential or authorized external host; local keygen does not establish remote protocol behavior",["tool/portable-ssh.py"])
def android(kind):
    binary=ROOT/"tool/android/platform-tools"/("sqlite3.exe" if kind=="sqlite" else "etc1tool.exe")
    for variant in ("ascii-relative","chinese-relative","absolute-chinese-space"):
        d=OUT/(kind+"-"+variant);d.mkdir()
        stem="\u4e2d\u6587" if variant=="chinese-relative" else "sample"
        def arg(p):return str(p) if variant=="absolute-chinese-space" else p.name
        if kind=="sqlite":
            db=d/(stem+".sqlite")
            r=run(binary,[arg(db),"create table t(v); insert into t values(7); select v*3 from t;"],cwd=d)
            good=r[0]==0 and db.is_file() and r[1].strip()=="21"
            if good:
                with sqlite3.connect(db) as conn:good=conn.execute("select v from t").fetchone()==(7,)
        else:
            from PIL import Image
            src=d/(stem+".png");encoded=d/(stem+".pkm");dst=d/"decoded.png"
            Image.new("RGB",(8,8),(10,30,50)).save(src)
            r=run(binary,[arg(src),"-o",arg(encoded)],cwd=d)
            good=r[0]==0 and encoded.is_file()
            if good:
                r=run(binary,[arg(encoded),"--decode","-o",arg(dst)],cwd=d)
                good=r[0]==0 and dst.is_file()
                if good:
                    with Image.open(dst) as im:good=im.size==(8,8) and all(abs(x-y)<=35 for x,y in zip(im.convert("RGB").getpixel((0,0)),(10,30,50)))
        row("actual Android "+binary.name+" "+variant,"PASS_ACTUAL" if good else "FAIL",
            {"exit":r[0],"verified_output":bool(good),"stderr":r[2][-500:],"owned_files":sorted(x.name for x in d.iterdir()),"cwd_inside_moved_package":True},
            [binary.relative_to(ROOT).as_posix()])
for kind in ("sqlite","etc"):
    try:android(kind)
    except Exception:row("Android "+kind,"FAIL",traceback.format_exc())
row("ADB native Windows home API","KNOWN_LIMIT","prior fixed 37.0.1 host profile access; deliberately not executed again; requires independent safe resolution",["tool/android/platform-tools/adb.exe"],["ADB_VENDOR_KEYS","ANDROID_USER_HOME","ANDROID_SDK_HOME"])
print("PORTABLE_RELEASE_FULL_CONSUMER_DONE",flush=True)
