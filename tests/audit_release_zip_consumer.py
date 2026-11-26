"""Whole released ZIP audit: executed by the RELEASED embedded interpreter,
through its real BAT/Codex/Host shell, never by the runner's Python.
MODE, HTTP_PORT and SOCKS_PORT are injected as synthetic fixture constants.
Every case is independent; DONE means the audit ran, not all tests passed.
"""
import asyncio, csv, datetime, hashlib, importlib, importlib.metadata as md
import io, json, os, pathlib, re, shutil, sqlite3, stat, subprocess, sys
import tempfile, traceback, zipfile
from pathlib import Path
from collections import Counter

ROOT=Path(os.environ["CODEX_INSTALL_DIR"]).resolve()
WORK=ROOT/"work/tool-probe"
OUT=WORK/"actual-output"
OUT.mkdir()
RESULT=WORK/"audit-results.jsonl"
PY=ROOT/"tool/python/python.exe"
WIN=Path(os.environ["SystemRoot"])
PS=WIN/"System32/WindowsPowerShell/v1.0/powershell.exe"
CMD=WIN/"System32/cmd.exe"
LABEL="Portable \u4e2d\u6587 \u7a7a\u683c 0172"
ROWS=[]
def row(item,status,detail="",covers=(),env=(),packages=()):
    data=dict(mode=MODE,item=item,status=status,detail=str(detail)[:6000],
              covers=list(covers),env=list(env),packages=list(packages))
    ROWS.append(data)
    with RESULT.open("a",encoding="utf-8",newline="\n") as f:
        f.write(json.dumps(data,ensure_ascii=True)+"\n")
def case(name,fn,covers=(),env=(),packages=()):
    try:
        detail=fn()
        row(name,"PASS_ACTUAL",detail or "ordinary consumer assertion passed",covers,env,packages)
    except Exception:
        row(name,"FAIL",traceback.format_exc(),covers,env,packages)
def ordinary(p):
    p=Path(p)
    for a in (*reversed(p.parents),p):
        s=a.lstat()
        assert not stat.S_ISLNK(s.st_mode) and not getattr(s,"st_file_attributes",0)&0x400,str(a)
    assert p.is_file() and p.stat().st_nlink==1,str(p)
    return p
def local(rel):
    p=ROOT/rel
    ordinary(p)
    assert p.resolve().is_relative_to(ROOT)
    return p
def proc(path,args=(),cwd=OUT,timeout=120,expect=0,extra_env=None):
    p=Path(path)
    assert p.is_absolute()
    ordinary(p)
    assert p.resolve().is_relative_to(ROOT) or p in {CMD,PS},str(p)
    args=[str(a) for a in args]
    e=dict(os.environ)
    if extra_env:e.update(extra_env)
    # No shell lookup. A BAT/CMD must execute in the Windows command
    # interpreter, not through a runner installation or unquoted shell text.
    if p.suffix.lower() in {".bat",".cmd"}:
        command=str(CMD)+' /d /s /c "'+subprocess.list2cmdline([str(p),*args])+'"'
        argv=command;exe=str(CMD)
    elif p.suffix.lower()==".ps1":
        argv=[str(PS),"-NoLogo","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",str(p),*args];exe=str(PS)
    else:
        argv=[str(p),*args];exe=str(p)
    child=subprocess.Popen(argv,executable=exe,cwd=cwd,env=e,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:out,err=child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run([str(WIN/"System32/taskkill.exe"),"/PID",str(child.pid),"/T","/F"],capture_output=True,timeout=20,check=False)
        child.communicate(timeout=20)
        raise AssertionError("deadline: "+str(p))
    text=out.decode("utf-8","backslashreplace")
    errors=err.decode("utf-8","backslashreplace")
    if expect is not None:assert child.returncode==expect,(str(p),child.returncode,text[-2000:],errors[-2000:])
    return child.returncode,text,errors
def cmd(rel,*args,**kw):
    return proc(local(rel),args,**kw)[1]
def py(rel,*args,**kw):
    return proc(PY,["-B",str(local(rel)),*args],**kw)[1]
def which(rel):
    p=local(rel)
    got=shutil.which(p.name)
    assert got and Path(got).resolve()==p.resolve(),(rel,got)
def module(n):
    m=importlib.import_module(n)
    assert Path(m.__file__).resolve().is_relative_to(ROOT/"tool/python"),n
    return m
def put(name,data):
    p=OUT/name
    p.parent.mkdir(parents=True,exist_ok=True)
    if isinstance(data,str):p.write_text(data,encoding="utf-8",newline="\n")
    else:p.write_bytes(data)
    return p
def cfg():
    import tomllib
    return tomllib.loads((ROOT/"home/config.toml").read_text(encoding="utf-8-sig"))
def norm(p):return os.path.normcase(os.path.normpath(str(p)))

def policy():
    c=cfg()
    assert Path(sys.executable).resolve()==PY
    assert sys.flags.isolated and sys.flags.ignore_environment and sys.flags.safe_path
    assert all(Path(p).resolve().is_relative_to(ROOT/"tool/python") for p in sys.path if p)
    assert not any("portable_browser" in k for k in c.get("mcp_servers",{}))
    want=("danger-full-access","never",True) if MODE=="yolo" else ("workspace-write","on-request",False)
    assert (c["sandbox_mode"],c["approval_policy"],c["sandbox_workspace_write"]["network_access"])==want
    roots={norm(p) for p in c["sandbox_workspace_write"]["writable_roots"]}
    assert roots==({norm(ROOT)} if MODE=="maintenance" else {norm(ROOT/"work"),norm(ROOT/"tmp")}),roots
    for p,allowed in ((ROOT/"protected-audit.txt",MODE in {"maintenance","yolo"}),
                      (ROOT.parent/"outside-workspace-audit.txt",MODE=="yolo")):
        assert p.read_bytes()==b"synthetic audit sentinel"
        try:p.write_bytes(b"owned test write")
        except PermissionError:assert not allowed,str(p)
        else:
            assert allowed,str(p)
            assert p.read_bytes()==b"owned test write"
            p.write_bytes(b"synthetic audit sentinel")
    return "actual work write; package/outside sentinels matched mode; embedded sys.path and expansion-off"
case("native mode policy",policy,["run-codex.ps1","env.ps1","codex.exe","codex-code-mode-host.exe"],
     ["CODEX_PORTABLE_PROFILE","CODEX_APPROVAL_POLICY","CODEX_SANDBOX_MODE","CODEX_INSTALL_DIR","CODEX_PYTHON","CODEX_HOME"])
c=cfg()
expected=c["shell_environment_policy"]["set"]
for name,value in sorted(expected.items()):
    actual=os.environ.get(name)
    if name.lower()=="psmodulepath":
        a={norm(p) for p in (actual or "").split(";") if p}
        e={norm(p) for p in value.split(";") if p}
        row("env:"+name,"KNOWN_LIMIT" if e<=a else "FAIL","actual extra module paths: "+repr(sorted(a-e)),env=[name])
    elif actual is not None and os.path.normcase(actual)==os.path.normcase(value):
        row("env:"+name,"PROPAGATION_ONLY","actual native child matches generated policy",env=[name])
    else:
        row("env:"+name,"FAIL","actual native child differs or absent",env=[name])
def effective_paths():
    import site
    assert Path(os.environ["CODEX_HOME"]).resolve()==ROOT/"home"
    assert (ROOT/"home/config.toml").is_file()
    assert Path(os.environ["CODEX_SQLITE_HOME"]).resolve()==ROOT/"sqlite"
    for n in ("TEMP","TMP","TMPDIR","USERPROFILE","HOME","APPDATA","LOCALAPPDATA","PYTHONUSERBASE","PYTHONPYCACHEPREFIX"):
        assert Path(os.environ[n]).resolve().is_relative_to(ROOT),n
    assert Path(tempfile.gettempdir()).resolve().is_relative_to(ROOT)
    # Create only a task-owned file in the actual default temporary directory.
    with tempfile.NamedTemporaryFile(delete=True) as f:
        assert Path(f.name).resolve().is_relative_to(ROOT)
        f.write(b"portable temporary data");f.flush()
    assert Path(site.getuserbase()).resolve()==Path(os.environ["PYTHONUSERBASE"]).resolve()
    assert sys.pycache_prefix and norm(sys.pycache_prefix)==norm(os.environ["PYTHONPYCACHEPREFIX"])
    assert Path(os.path.expanduser("~")).resolve()==Path(os.environ["USERPROFILE"]).resolve()
    result=json.loads(cmd("tool/node/node.exe","-e","console.log(JSON.stringify({exe:process.execPath,home:require('os').homedir(),tmp:require('os').tmpdir()}))"))
    assert Path(result["exe"]).resolve()==ROOT/"tool/node/node.exe"
    assert Path(result["home"]).resolve()==Path(os.environ["USERPROFILE"]).resolve()
    assert Path(result["tmp"]).resolve()==Path(os.environ["TEMP"]).resolve()
    return "real Python tempfile/userbase/pycache and Node home/temp; no host installation"
case("effective Python and Node paths",effective_paths,["tool/python/python.exe","tool/node/node.exe"],
     ["TEMP","TMP","TMPDIR","USERPROFILE","HOME","PYTHONUSERBASE","PYTHONPYCACHEPREFIX","CODEX_HOME","CODEX_INSTALL_DIR","CODEX_PYTHON"])
def pythonw():
    marker=OUT/"pythonw-result.txt"
    script=put("pythonw-probe.py","from pathlib import Path\nPath("+repr(str(marker))+").write_text('portable-pythonw',encoding='ascii')\n")
    cmd("tool/python/pythonw.exe","-B",script)
    assert marker.read_text()=="portable-pythonw"
case("pythonw GUI interpreter noninteractive file consumer",pythonw,["tool/python/pythonw.exe"])

# Every public command is resolved explicitly; actual content, not version only.
data=put("search input \u4e2d\u6587.txt",LABEL+"\nsecond line\n")
def rg(rel,resolve):
    if resolve:which(rel)
    assert LABEL in cmd(rel,"--fixed-strings","--no-config",LABEL,data)
case("standalone rg actual search",lambda:rg("tool/bin/rg.exe",True),["tool/bin/rg.exe"],["PATH"])
case("Codex fixed rg actual search",lambda:rg("codex-path/rg.exe",False),["codex-path/rg.exe"])
def fd():
    which("tool/bin/fd.exe")
    # fd outputs relative to supplied root; exact file must be found.
    out=cmd("tool/bin/fd.exe","--type","f","--fixed-strings","search input",str(OUT))
    assert data.name in out
case("fd actual file discovery",fd,["tool/bin/fd.exe"],["PATH"])
def jq():
    which("tool/bin/jq.exe")
    p=put("query.json",json.dumps({"name":LABEL,"amount":7},ensure_ascii=False))
    assert cmd("tool/bin/jq.exe","-r",".amount + 5",p).strip()=="12"
    assert cmd("tool/bin/jq.exe","-r",".name",p).strip()==LABEL
case("jq actual JSON transformation",jq,["tool/bin/jq.exe"],["PATH"])
def sevenzip():
    which("tool/bin/7z.exe")
    archive=OUT/"synthetic archive.7z";dest=OUT/"extracted archive";dest.mkdir()
    cmd("tool/bin/7z.exe","a","-t7z",archive,data)
    cmd("tool/bin/7z.exe","t",archive)
    cmd("tool/bin/7z.exe","x","-y","-o"+str(dest),archive)
    assert (dest/data.name).read_bytes()==data.read_bytes()
case("7-Zip actual create/test/extract",sevenzip,["tool/bin/7z.exe","tool/bin/7z.dll"],["PATH"])

def pip_alias(rel):
    which(rel)
    assert norm(cmd(rel,"cache","dir").strip())==norm(os.environ["PIP_CACHE_DIR"])
    assert "No broken requirements found" in cmd(rel,"check")
    # The managed shim resolves the portable interpreter; config is consumed.
    assert os.environ["PIP_CONFIG_FILE"].lower()=="nul"
    out=cmd(rel,"--version");assert str(ROOT/"tool/python").lower() in out.lower()
for rel in ("tool/bin/pip.cmd","tool/bin/pip3.cmd","tool/bin/pip3.14.cmd"):
    case(rel+" real cache and dependency consumer",lambda p=rel:pip_alias(p),[rel,"tool/bin/portable-python-cli.py"],["PATH","PIP_CACHE_DIR","PIP_CONFIG_FILE"],["pip"])
def lock():
    py("tool/python-lock.py","validate","--requirements",ROOT/"tool/python-packages.in.txt","--lock",ROOT/"tool/python-packages.lock.txt")
    py("tool/python-lock.py","validate-runtime","--requirements",ROOT/"tool/python-packages.in.txt")
    pins={n.lower().replace("_","-"):v for n,v in (s.split("==") for s in (ROOT/"tool/python-packages.in.txt").read_text().splitlines() if "==" in s and not s.startswith("#"))}
    found={d.metadata["Name"].lower().replace("_","-"):d.version for d in md.distributions(path=[str(ROOT/"tool/python/Lib/site-packages")])}
    assert found==pins and len(found)==49
    for n,v in sorted(found.items()):row("distribution:"+n,"IDENTITY_ONLY",v)
    return "49 exact installed distributions and wheel hash lock"
case("Python lock and installed closure",lock,["tool/python-lock.py","tool/python-packages.in.txt","tool/python-packages.lock.txt"])

npm_dir=OUT/"npm local \u4e2d\u6587";npm_dir.mkdir()
(npm_dir/"package.json").write_text('{"name":"portable-audit","version":"1.0.0","scripts":{"audit":"node fixture.cjs"}}',encoding="utf-8")
(npm_dir/"fixture.cjs").write_text("const assert=require('node:assert'); assert(process.execPath.toLowerCase()===process.env.CODEX_INSTALL_DIR.toLowerCase()+'\\\\tool\\\\node\\\\node.exe'); console.log('PORTABLE_NPM_LOCAL_SCRIPT_OK')",encoding="utf-8")
def npm_entry(rel):
    if rel.endswith(".cmd"):which(rel)
    for key,variable in (("cache","NPM_CONFIG_CACHE"),("prefix","NPM_CONFIG_PREFIX"),("userconfig","NPM_CONFIG_USERCONFIG"),("globalconfig","NPM_CONFIG_GLOBALCONFIG")):
        args=["config","get",key]+(["--global"] if key=="prefix" else [])
        assert norm(cmd(rel,*args,cwd=npm_dir).strip())==norm(os.environ[variable]),(rel,key)
    assert norm(cmd(rel,"config","get","prefix",cwd=npm_dir).strip())==norm(npm_dir)
    assert "PORTABLE_NPM_LOCAL_SCRIPT_OK" in cmd(rel,"run","--silent","audit","--offline",cwd=npm_dir)
for rel in ("tool/node/npm.cmd","tool/node/npm.ps1"):
    case(rel+" actual local npm script and config",lambda p=rel:npm_entry(p),[rel,"tool/node/portable-npm.js"],
         ["PATH","NPM_CONFIG_CACHE","NPM_CONFIG_PREFIX","NPM_CONFIG_USERCONFIG","NPM_CONFIG_GLOBALCONFIG"])
def npx_entry(rel):
    if rel.endswith(".cmd"):which(rel)
    out=cmd(rel,"--offline","--no","--call","node fixture.cjs",cwd=npm_dir)
    assert "PORTABLE_NPM_LOCAL_SCRIPT_OK" in out
for rel in ("tool/node/npx.cmd","tool/node/npx.ps1"):
    case(rel+" actual offline local command",lambda p=rel:npx_entry(p),[rel,"tool/node/portable-npm.js"],["PATH"])
def node_repl():
    # Actual package-local JS execution and Node's module resolution.
    assert cmd("tool/node/node.exe",str(npm_dir/"fixture.cjs")).strip()=="PORTABLE_NPM_LOCAL_SCRIPT_OK"
case("Node native script",node_repl,["tool/node/node.exe"],["PATH"])
def corepack():
    out=cmd("tool/node/corepack.cmd","--version",cwd=npm_dir,extra_env={"COREPACK_ENABLE_NETWORK":"0"})
    assert out.strip()=="0.35.0"
    # No pnpm/Yarn payload in this distribution. Do not download a manager
    # just to convert a version probe into a claimed application pass.
    row("corepack managed package execution","NOT_APPLICABLE","No package-local pnpm/Yarn manager; only dispatcher identity checked")
try:
    corepack()
    row("Corepack dispatcher","IDENTITY_ONLY","actual package-local version command; no manager execution",["tool/node/corepack.cmd"])
except Exception:row("Corepack dispatcher","FAIL",traceback.format_exc(),["tool/node/corepack.cmd"])

def math_yaml_text():
    np=module("numpy");pd=module("pandas");yaml=module("yaml")
    assert np.array([[1,2],[3,4]])@np.array([2,3]) is not None
    assert (np.array([[1,2],[3,4]])@np.array([2,3])).tolist()==[8,18]
    f=pd.DataFrame({"name":[LABEL,LABEL],"value":[2,5]});assert int(f.groupby("name").value.sum().iloc[0])==7
    p=put("data.csv",f.to_csv(index=False));assert pd.read_csv(p).equals(f)
    val={"name":LABEL,"enabled":True,"items":[1,2]}
    for loader,dumper in [(yaml.SafeLoader,yaml.SafeDumper),(yaml.CSafeLoader,yaml.CSafeDumper)]:
        assert yaml.load(yaml.dump(val,Dumper=dumper,allow_unicode=True),Loader=loader)==val
case("NumPy pandas YAML native data operations",math_yaml_text,packages=["numpy","pandas","pyyaml"])
def xml_html():
    from lxml import etree,html
    module("lxml");bs=module("bs4");module("soupsieve");module("defusedxml")
    from defusedxml import ElementTree as safe
    xml=("<root><value>"+LABEL+"</value></root>").encode()
    assert etree.fromstring(xml,etree.XMLParser(resolve_entities=False,no_network=True)).xpath("string(value)")==LABEL
    assert safe.fromstring(xml)[0].text==LABEL
    assert html.fromstring("<p>"+LABEL+"</p>").text==LABEL
    assert bs.BeautifulSoup("<div><p class='audit'>"+LABEL+"</p></div>","lxml").select_one("div > p.audit").text==LABEL
case("XML HTML CSS selector actual parsing",xml_html,packages=["lxml","beautifulsoup4","soupsieve","defusedxml"])
def dates_and_types():
    from dateutil.parser import isoparse
    from zoneinfo import ZoneInfo
    import six,typing_extensions,packaging.version,packaging.requirements
    for n in ("dateutil","tzdata","six","typing_extensions","packaging"):module(n)
    assert isoparse("2026-11-26T08:30:00+08:00").hour==8
    d=datetime.datetime(2026,11,26,8,tzinfo=ZoneInfo("Asia/Taipei"))
    assert d.utcoffset()==datetime.timedelta(hours=8)
    assert six.text_type(7)=="7"
    class T(typing_extensions.TypedDict):
        x:int
    assert T(x=3)=={"x":3}
    assert packaging.version.Version("2.0")>packaging.version.Version("1.9")
    assert packaging.requirements.Requirement("numpy>=2").specifier.contains("2.4.6")
case("dates/timezone/types/version consumers",dates_and_types,packages=["python-dateutil","tzdata","six","typing-extensions","packaging"])
def rich_text():
    from markdown_it import MarkdownIt
    from rich.console import Console
    from rich.markdown import Markdown
    from pygments import highlight,lex
    from pygments.lexers import get_lexer_by_name
    from pygments.formatters import HtmlFormatter
    import mdurl,tabulate
    for n in ("markdown_it","rich","pygments","mdurl","tabulate"):module(n)
    mark="# "+LABEL+"\n\n**bold** [link](https://example.invalid/)\n"
    assert "<strong>bold</strong>" in MarkdownIt().render(mark)
    stream=io.StringIO();Console(file=stream,color_system=None,width=80).print(Markdown(mark))
    assert LABEL in stream.getvalue()
    code="select 7 from dual;\n";lexer=get_lexer_by_name("sql")
    assert "".join(t for _,t in lex(code,lexer))==code
    assert "<pre>" in highlight(code,lexer,HtmlFormatter())
    assert mdurl.parse("https://example.invalid/").hostname=="example.invalid"
    assert "7" in tabulate.tabulate([[LABEL,7]],headers=["name","count"],tablefmt="github")
case("Markdown/Rich/Pygments/tabulate actual formatting",rich_text,packages=["markdown-it-py","rich","pygments","mdurl","tabulate"])
def encoding():
    from charset_normalizer import from_bytes
    import idna
    module("charset_normalizer");module("idna")
    text=LABEL+" sample text\n"
    for enc in ("utf-8","utf-8-sig","utf-16"):
        assert str(from_bytes(text.encode(enc)).best())==text
    domain="\u4f8b\u5b50.example"
    assert idna.decode(idna.encode(domain))==domain
case("encoding and IDNA actual conversion",encoding,packages=["charset-normalizer","idna"])

def cli_markdown():
    which("tool/bin/markdown-it.cmd")
    file=put("ordinary.md","# Heading\n\n**bold**\n")
    assert "<strong>bold</strong>" in cmd("tool/bin/markdown-it.cmd",file)
case("markdown-it CMD",cli_markdown,["tool/bin/markdown-it.cmd"],["PATH"],["markdown-it-py"])
def cli_pygments():
    which("tool/bin/pygmentize.cmd")
    file=put("query.sql","select 7 from dual;\n")
    target=OUT/"query.html"
    cmd("tool/bin/pygmentize.cmd","-l","sql","-f","html","-o",target,file)
    assert "<pre>" in target.read_text(encoding="utf-8")
case("pygmentize CMD",cli_pygments,["tool/bin/pygmentize.cmd"],["PATH"],["pygments"])
def cli_idna():
    which("tool/bin/idna.cmd")
    import idna
    domain="\u4f8b\u5b50.example"
    assert idna.encode(domain).decode() in cmd("tool/bin/idna.cmd",domain)
case("idna CMD",cli_idna,["tool/bin/idna.cmd"],["PATH"],["idna"])
def cli_normalizer():
    which("tool/bin/normalizer.cmd")
    file=put("encoded.txt",(LABEL+" normal Unicode text\n").encode("utf-8-sig"))
    out=cmd("tool/bin/normalizer.cmd",file)
    assert "utf" in out.lower(),out
case("normalizer CMD",cli_normalizer,["tool/bin/normalizer.cmd"],["PATH"],["charset-normalizer"])
def cli_numpy_config():
    which("tool/bin/numpy-config.cmd")
    out=cmd("tool/bin/numpy-config.cmd","--cflags")
    assert "numpy" in out.lower() and str(ROOT).replace("\\","/").lower() in out.replace("\\","/").lower(),out
case("numpy-config actual header discovery",cli_numpy_config,["tool/bin/numpy-config.cmd"],["PATH"],["numpy"])
def cli_f2py():
    which("tool/bin/f2py.cmd")
    source=put("sample.f90","subroutine addone(x)\nreal :: x\nx=x+1\nend subroutine addone\n")
    signature=OUT/"sample.pyf"
    cmd("tool/bin/f2py.cmd","-m","sample","-h",signature,source)
    assert "addone" in signature.read_text().lower()
case("f2py actual signature generation (no compiler)",cli_f2py,["tool/bin/f2py.cmd"],["PATH"],["numpy"])
def cli_vba():
    which("tool/bin/vba_extract.cmd")
    # Inert byte sentinel in an ordinary synthetic ZIP; no macro execution.
    src=OUT/"vba-fixture.xlsm"
    with zipfile.ZipFile(src,"w") as z:z.writestr("xl/vbaProject.bin",b"synthetic not executable VBA")
    cmd("tool/bin/vba_extract.cmd",src)
    assert (OUT/"vbaProject.bin").read_bytes()==b"synthetic not executable VBA"
case("vba_extract actual inert ZIP member readback",cli_vba,["tool/bin/vba_extract.cmd"],["PATH"],["xlsxwriter"])

def office_pdf():
    status,out,err=proc(PY,["-B",WORK/"office_pdf_probe.py"],cwd=ROOT/"work",timeout=240,expect=None)
    markers={
      "DOCX write/read":"NATIVE_DOCX_WRITE_READ=PASS",
      "XLSX write/read":"NATIVE_XLSX_WRITE_READ_FORMULA_PRESERVED=PASS",
      "PPTX write/read":"NATIVE_PPTX_WRITE_READ=PASS",
      "PDF library":"NATIVE_PDF_LIBRARY_BUILD_SEARCH_READ_VERIFY_EXPORT=PASS",
      "Office and PDF complete":"PORTABLE_DOCUMENT_ROUNDTRIP_0172"}
    for name,marker in markers.items():
        row("released native "+name,"PASS_ACTUAL" if marker in out else "NOT_REACHED",marker if marker in out else (err[-2500:] or out[-2500:]))
    assert status==0 and markers["Office and PDF complete"] in out,(status,out[-3500:],err[-3500:])
    return out[-4000:]
case("original Office validators and PDF library actual consumer",office_pdf,
     ["home/skills/docx/scripts/office/validate.py","home/skills/pptx/scripts/office/validate.py","home/skills/xlsx/scripts/office/validate.py","home/skills/pdf-library/scripts/pdf_library.py"],
     ["CODEX_PYTHON","CODEX_INSTALL_DIR","TEMP","TMP"],
     ["python-docx","python-pptx","openpyxl","pandas","lxml","pymupdf","pymupdf4llm","tabulate","defusedxml","et-xmlfile"])
def office_subtools():
    import docx,pptx
    base=WORK/"document-results"
    word=base/"\u4fbf\u643a.docx";deck=base/"\u4fbf\u643a.pptx"
    if not (word.exists() and deck.exists()):
        # Independent fixtures if the larger original Office probe stopped early.
        word=OUT/"ordinary.docx";d=docx.Document();d.add_paragraph(LABEL);d.save(word)
        deck=OUT/"ordinary.pptx";d=pptx.Presentation();d.slides.add_slide(d.slide_layouts[6]);d.save(deck)
    def merge():
        target=OUT/"merged.docx"
        py("home/skills/docx/scripts/merge_runs.py",word,"-o",target)
        assert docx.Document(target).paragraphs[0].text
    def comment():
        target=OUT/"commented.docx"
        py("home/skills/docx/scripts/comment.py",word,"synthetic comment","-o",target)
        with zipfile.ZipFile(target) as z:assert b"synthetic comment" in z.read("word/comments.xml")
    def slide():
        target=OUT/"added.pptx"
        py("home/skills/pptx/scripts/add_slide.py",deck,"slide1.xml","-o",target)
        assert len(pptx.Presentation(target).slides)==2
    def clean_deck():
        target=OUT/"unpacked-pptx";target.mkdir()
        # Own generated fixture only, not arbitrary ZIP.
        with zipfile.ZipFile(deck) as z:
            assert all(not n.startswith("/") and ".." not in n.split("/") for n in z.namelist())
            z.extractall(target)
        orphan=target/"ppt/slides/slide999.xml";orphan.write_text("<unused/>")
        py("home/skills/pptx/scripts/clean.py",target)
        assert not orphan.exists() and (target/"ppt/slides/slide1.xml").exists()
    for name,fn in (("docx/scripts/merge_runs.py",merge),("docx/scripts/comment.py",comment),("pptx/scripts/add_slide.py",slide),("pptx/scripts/clean.py",clean_deck)):
        case("skill "+name,fn,["home/skills/"+name])
office_subtools()
for name,reason in [
 ("docx/scripts/accept_changes.py","requires optional LibreOffice"),
 ("pptx/scripts/thumbnail.py","requires optional renderers"),
 ("xlsx/scripts/recalc.py","requires optional LibreOffice"),
 ("pdf/scripts/check_fillable_fields.py","pypdf not installed"),
 ("pdf/scripts/extract_form_field_info.py","pypdf not installed"),
 ("pdf/scripts/fill_fillable_fields.py","pypdf not installed"),
 ("pdf/scripts/extract_form_structure.py","pdfplumber not installed"),
 ("pdf/scripts/convert_pdf_to_images.py","pdf2image/Poppler not installed"),
 ("pdf/scripts/create_validation_image.py","optional rendering dependencies"),
 ("pdf/scripts/fill_pdf_form_with_annotations.py","optional PDF authoring dependencies"),
 ("pdf/scripts/check_bounding_boxes.py","optional PDF form dependencies")]:
    row("skill "+name,"NOT_APPLICABLE",reason,["home/skills/"+name])

def image_xlsx():
    from PIL import Image
    import xlsxwriter,openpyxl
    p=OUT/"image.png"
    Image.new("RGB",(12,8),(10,30,50)).save(p)
    with Image.open(p) as image:assert image.size==(12,8) and image.getpixel((0,0))==(10,30,50)
    book=OUT/"xlsxwriter.xlsx"
    with xlsxwriter.Workbook(book) as w:
        sh=w.add_worksheet();sh.write(0,0,LABEL);sh.write_formula(0,1,"=1+2");sh.insert_image("C2",str(p))
    with zipfile.ZipFile(book) as z:assert "xl/media/image1.png" in z.namelist()
    wb=openpyxl.load_workbook(book);assert wb.active["A1"].value==LABEL and wb.active["B1"].value=="=1+2";wb.close()
case("Pillow and XlsxWriter actual image/workbook",image_xlsx,packages=["pillow","xlsxwriter","openpyxl"])
def freeze():
    style="onefile" if MODE=="yolo" else "onedir"
    area=OUT/"freeze";area.mkdir()
    source=area/"ordinary.py";source.write_text("print('PORTABLE_RELEASE_FROZEN_OK')\n")
    # Explicit task-owned build cache is the documented safe packaging path,
    # not an alteration of the original env.ps1 or Python isolation.
    e={"PYINSTALLER_CONFIG_DIR":str(area/"cache")}
    proc(PY,["-B","-m","PyInstaller","--noconfirm","--"+style,"--name","ordinary","--distpath",area/"dist","--workpath",area/"build","--specpath",area,source],cwd=area,timeout=240,extra_env=e)
    moved=area/"Moved \u4e2d\u6587 EXE";(area/"dist").rename(moved)
    exe=moved/"ordinary.exe" if style=="onefile" else moved/"ordinary/ordinary.exe"
    assert proc(exe,[],cwd=area)[1].strip()=="PORTABLE_RELEASE_FROZEN_OK"
    return style+" actual build, move, execute; explicit task cache"
if MODE!="maintenance":
    case("PyInstaller real frozen executable",freeze,packages=["pyinstaller","pyinstaller-hooks-contrib"])
else:row("PyInstaller build maintenance","NOT_REPEATED","same payload is built in normal and YOLO; maintenance scope tested independently")

def crypto():
    import bcrypt,nacl.secret,nacl.utils,cffi,pycparser,cryptography
    from cryptography.hazmat.primitives.asymmetric import ed25519
    for n in ("bcrypt","nacl","cffi","pycparser","cryptography"):module(n)
    key=ed25519.Ed25519PrivateKey.generate();sig=key.sign(b"ordinary");key.public_key().verify(sig,b"ordinary")
    assert bcrypt.checkpw(b"audit",bcrypt.hashpw(b"audit",bcrypt.gensalt(rounds=4)))
    box=nacl.secret.SecretBox(nacl.utils.random(nacl.secret.SecretBox.KEY_SIZE));assert box.decrypt(box.encrypt(b"audit"))==b"audit"
    ffi=cffi.FFI();assert ffi.sizeof("int")>=4
    assert pycparser.CParser().parse("int ordinary(int a) { return a; }")
case("crypto/native SSH dependency consumers",crypto,packages=["bcrypt","pynacl","cffi","pycparser","cryptography"])
def ssh_key():
    py("tool/portable-ssh.py","keygen","--name","synthetic-audit","--unencrypted")
    key=ROOT/"work/ssh/keys/synthetic-audit"
    import paramiko
    module("paramiko");module("invoke")
    k=paramiko.Ed25519Key.from_private_key_file(str(key))
    assert k.get_name()=="ssh-ed25519"
    assert (key.with_suffix(".pub")).read_text().startswith("ssh-ed25519 ")
    # No actual user or real remote host. The only keys are disposable.
    key.unlink();key.with_suffix(".pub").unlink()
case("SSH actual package-local synthetic key creation/readback",ssh_key,["tool/portable-ssh.py"],packages=["cryptography","paramiko"])
row("SSH/SFTP real host","NOT_APPLICABLE","No real remote host or account; key consumer is separate")
def http_protocol():
    import h11,certifi,ssl
    for n in ("h11","certifi"):module(n)
    server=h11.Connection(h11.SERVER);server.receive_data(b"GET / HTTP/1.1\r\nHost: example.invalid\r\n\r\n")
    assert isinstance(server.next_event(),h11.Request)
    path=Path(certifi.where()).resolve();assert path.is_relative_to(ROOT/"tool/python")
    context=ssl.create_default_context(cafile=str(path));assert context.cert_store_stats()["x509_ca"]>0
case("HTTP parser and package CA consumer",http_protocol,packages=["h11","certifi"])
def http_actual():
    import requests,httpx,urllib3,anyio,httpcore,socks
    for n in ("requests","httpx","urllib3","anyio","httpcore","socks"):module(n)
    url="http://127.0.0.1:"+str(HTTP_PORT)+"/"
    marker="Portable MCP smoke"
    with requests.Session() as s:
        s.trust_env=False;assert marker in s.get(url,timeout=10).text
        assert marker in s.get("http://portable-socks.invalid/",proxies={"http":"socks5h://127.0.0.1:"+str(SOCKS_PORT)},timeout=10).text
    with httpx.Client(trust_env=False) as c:assert marker in c.get(url,timeout=10).text
    pool=urllib3.PoolManager();assert marker.encode() in pool.request("GET",url,timeout=10).data;pool.clear()
    async def go():
        async with httpx.AsyncClient(trust_env=False) as c:assert marker in (await c.get(url,timeout=10)).text
    anyio.run(go)
if MODE=="yolo":
    case("HTTP and SOCKS actual loopback clients",http_actual,packages=["requests","httpx","urllib3","anyio","httpcore","pysocks"])
    def inherited_bridge():
        import requests
        from urllib.parse import urlsplit
        proxy=requests.utils.get_environ_proxies("http://portable-socks.invalid/")
        parsed=urlsplit(proxy.get("http",""))
        assert parsed.hostname=="127.0.0.1" and parsed.port
        with requests.Session() as s:
            assert "Portable MCP smoke" in s.get("http://portable-socks.invalid/",timeout=12).text
            assert "Portable MCP smoke" in s.get("http://127.0.0.1:"+str(HTTP_PORT)+"/",timeout=12).text
        return "actual inherited HTTP bridge to synthetic SOCKS and loopback bypass (auth token omitted)"
    case("launcher-generated proxy bridge consumer",inherited_bridge,["tool/socks-http-bridge.py"],
         ["CODEX_PROXY_ENABLED","CODEX_PROXY_PROTOCOL","CODEX_PROXY_HOST","CODEX_PROXY_PORT","CODEX_PROXY_HTTP_BRIDGE","CODEX_PROXY_BRIDGE_HOST","CODEX_PROXY_BRIDGE_PORT","CODEX_PROXY_FOR_SUBPROCESS","HTTP_PROXY","NO_PROXY"],["requests","pysocks"])
else:
    import socket
    try:
        with socket.create_connection(("127.0.0.1",HTTP_PORT),timeout=3):
            row("command network loopback","OBSERVED","loopback accessible with generated network_access=false; external network not probed",env=["CODEX_SANDBOX_NETWORK_ACCESS"])
    except OSError as e:
        row("command network loopback","OBSERVED","loopback refused under normal/maintenance policy: "+type(e).__name__,env=["CODEX_SANDBOX_NETWORK_ACCESS"])
    row("HTTP clients external network","NOT_APPLICABLE","No external network use; YOLO synthetic HTTP/SOCKS tested separately")
if MODE=="yolo":
    def httpx_cli():
        which("tool/bin/httpx.cmd")
        url="http://127.0.0.1:"+str(HTTP_PORT)+"/"
        assert "Portable MCP smoke" in cmd("tool/bin/httpx.cmd",url)
    case("httpx CMD real loopback",httpx_cli,["tool/bin/httpx.cmd"],["PATH"],["httpx"])
else:row("httpx CMD network","NOT_APPLICABLE","Command-network disabled in this mode; actual YOLO HTTP tested separately",["tool/bin/httpx.cmd"])

# Android platform-tools are not on the generic PATH by design.
android="tool/android/platform-tools/"
def sqlite_cli():
    db=OUT/"native.sqlite"
    assert cmd(android+"sqlite3.exe",db,"create table t(v); insert into t values(7); select v*3 from t;").strip()=="21"
    with sqlite3.connect(db) as db:assert db.execute("select v from t").fetchone()==(7,)
case("Android sqlite3 actual database consumer",sqlite_cli,[android+"sqlite3.exe"])
def etc():
    from PIL import Image
    src=OUT/"etc-source.png";encoded=OUT/"etc.pkm";decoded=OUT/"etc-decoded.png"
    Image.new("RGB",(8,8),(10,30,50)).save(src)
    cmd(android+"etc1tool.exe",src,"-o",encoded)
    cmd(android+"etc1tool.exe",encoded,"--decode","-o",decoded)
    with Image.open(decoded) as im:assert im.size==(8,8)
case("Android etc1tool ordinary image encode/decode",etc,[android+"etc1tool.exe"])
# The prior real ADB version probe already touched a host-profile API.
# Do not invoke it again or create a real .android in the runner's profile.
for name,reason in [
 ("adb.exe","known native Windows host-profile API limitation; no repeat unsafe probe"),
 ("fastboot.exe","requires a real/authorized target for actual device operations"),
 ("hprof-conv.exe","no valid synthetic Android HPROF fixture in this gate"),
 ("make_f2fs.exe","internal filesystem/device formatting helper, no authorized device"),
 ("make_f2fs_casefold.exe","internal filesystem/device formatting helper, no authorized device"),
 ("mke2fs.exe","internal filesystem/device formatting helper, no authorized device")]:
    row("Android "+name,"KNOWN_LIMIT" if name=="adb.exe" else "NOT_APPLICABLE",reason,[android+name])

def browser_check():
    entry=local("tool/automation/start-browser.ps1")
    data=json.loads(proc(entry,["-Check","-Workspace","work/tool-probe"])[1])
    assert data["BrowserPresent"] and not data["AutomaticStart"]
    assert Path(data["PackageRoot"]).resolve()==ROOT
    assert not (ROOT/"cache/browser").exists()
    return str(data.get("BrowserVersion"))
case("browser read-only discovery",browser_check,["tool/automation/start-browser.ps1","tool/automation/portable-automation.ps1"])
if MODE=="yolo":
    def browser_task():
        p=WORK/"ordinary-page.cjs"
        p.write_text("module.exports=async({page})=>{await page.setContent('<title>PORTABLE_RELEASE_BROWSER_OK</title><button>Click</button>');await page.getByRole('button',{name:'Click'}).click();return {title:await page.title()};};",encoding="utf-8")
        out=cmd("tool/automation/start-browser.ps1","-TaskAuthorized","-Workspace","work/tool-probe","-TaskScript",p,timeout=150)
        assert "PORTABLE_RELEASE_BROWSER_OK" in out
        assert (ROOT/"cache/browser/profile").is_dir()
    case("real released browser task and persistent profile",browser_task,["tool/automation/start-browser.ps1","tool/automation/browser-task.js"])
else:row("browser task write/start","NOT_APPLICABLE","normal/maintenance read-only discovery; explicit browser task/approval route tested in YOLO")
def instruction():
    p=put("ordinary-instructions.md","Synthetic audit instructions\n")
    py("tool/codex-instruct.py","--file",p,"--name","portable-audit-instructions","--dry-run")
case("instruction installer dry-run only",instruction,["tool/codex-instruct.py"])
row("optional dependency repair/setup","NOT_APPLICABLE","No network reinstall/changed package for original ZIP; lock and actual installed consumers separately validated",["tool/setup-tools.ps1","tool/refresh-python-cli-shims.py","tool/automation/install-browser.py","tool/automation/install-browser.ps1"])
row("optional tools not installed","NOT_APPLICABLE","Go, uv, git, SDK/JDK, Appium/Maestro, optional PDF/OCR/LibreOffice, host Python/Node")
print("PORTABLE_RELEASE_FULL_CONSUMER_DONE",flush=True)
print("AUDIT_ROW_COUNTS="+json.dumps(Counter(x["status"] for x in ROWS),sort_keys=True),flush=True)
