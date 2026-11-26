"""Targeted native Windows parser, text and existing CLI checks in moved packages.

Real BAT, Codex, shell, bundled Python and normal frozen executables. Synthetic
loopback model only; no browser/MCP execution, hostile files, elevated child,
bootloader manipulation, or changes to the embedded interpreter or sandbox.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib

for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8", errors="backslashreplace")

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("image_packager_native_core",ROOT/"tests/check_codex_tool_discovery.py")
core=importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
m=core.m

PROBE=r'''
import hashlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
from importlib.metadata import version

root=Path(os.environ["CODEX_INSTALL_DIR"]).resolve()
work=Path(__file__).resolve().parent
py=root/"tool/python/python.exe"
assert Path(sys.executable).resolve()==py
assert sys.flags.isolated and sys.flags.ignore_environment and sys.flags.safe_path
assert all(Path(p).resolve().is_relative_to(root/"tool/python") for p in sys.path if p)
assert work.is_relative_to(root/"work")
config=tomllib.loads((root/"home/config.toml").read_text(encoding="utf-8-sig"))
expected=config["shell_environment_policy"]["set"]
for k in ("CODEX_HOME","CODEX_INSTALL_DIR","CODEX_PYTHON","PIP_CONFIG_FILE","TEMP","TMP","PYTHONUSERBASE","PYTHONPYCACHEPREFIX"):
    assert k in expected and os.path.normcase(os.environ[k])==os.path.normcase(expected[k]),k
assert os.environ["PIP_CONFIG_FILE"].lower()=="nul"
for k in ("TEMP","TMP","PYTHONUSERBASE","PYTHONPYCACHEPREFIX"):
    assert Path(os.environ[k]).resolve().is_relative_to(root),k
assert (config["sandbox_mode"],config["approval_policy"],config["sandbox_workspace_write"]["network_access"])==(
    ("workspace-write","on-request",False) if MODE=="normal" else ("danger-full-access","never",True))
assert "portable_browser" not in config.get("mcp_servers",{})
if MODE=="normal":
    for sentinel in (root/"protected-audit.txt",root.parent/"outside-workspace-audit.txt"):
        try:
            with sentinel.open("wb") as out:out.write(b"unexpected")
        except PermissionError:
            pass
        else:
            raise AssertionError("Unexpected common-mode write: "+sentinel.name)
print("NATIVE_REMAINING_STABLE_POLICY=PASS "+MODE,flush=True)

# Only ordinary, benign consumer fixtures; no crafted exploit input.
import importlib
import io
module={"lxml":"lxml","pyyaml":"yaml","markdown-it-py":"markdown_it",
        "charset-normalizer":"charset_normalizer","pygments":"pygments"}[SUITE]
lib=importlib.import_module(module)
assert Path(lib.__file__).resolve().is_relative_to(root/"tool/python")
assert version(SUITE)==EXPECTED[SUITE]
assert lib.__version__==EXPECTED[SUITE],(lib.__version__,EXPECTED[SUITE])
out=work/"\u4e2d\u6587 \u517c\u5bb9 \u7ed3\u679c";out.mkdir()
label="\u4fbf\u643a \u4e2d\u6587 \u6d4b\u8bd5"
def cli(name,args):
    # Use the existing managed CMD from the inherited portable PATH,
    # not a vendor-generated executable or host Python.
    target=root/"tool/bin"/(name+".cmd")
    resolved=shutil.which(name)
    assert resolved and Path(resolved).resolve()==target.resolve(),(name,resolved)
    p=subprocess.run([str(target),*args],cwd=work,capture_output=True,timeout=60)
    assert p.returncode==0,(name,p.returncode,p.stdout[-2000:],p.stderr[-2000:])
    return p.stdout.decode("utf-8","strict")

if SUITE=="lxml":
    from lxml import etree,html
    import bs4,docx,pptx,openpyxl,pandas
    from pptx.util import Inches
    assert Path(etree.__file__).resolve().is_relative_to(root/"tool/python")
    assert etree.LXML_VERSION[:3]==(6,1,3)
    parser=etree.XMLParser(resolve_entities=False,no_network=True)
    doc=etree.fromstring(("<root><value>"+label+"</value></root>").encode(),parser)
    assert doc.xpath("string(value)")==label
    schema=etree.XMLSchema(etree.XML(b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:element name="value" type="xs:string"/></xs:schema>'))
    assert schema.validate(etree.ElementTree(doc[0]))
    h=html.fromstring("<html><body><p>"+label+"</p></body></html>")
    assert h.xpath("string(//p)")==label
    assert bs4.BeautifulSoup("<p>"+label+"</p>","lxml").p.text==label
    # Normal consumer documents and existing Office XML validators.
    d=docx.Document();d.add_paragraph(label);word=out/"\u6587\u6863.docx";d.save(word)
    assert docx.Document(word).paragraphs[0].text==label
    deck=pptx.Presentation();slide=deck.slides.add_slide(deck.slide_layouts[6])
    slide.shapes.add_textbox(Inches(1),Inches(1),Inches(3),Inches(1)).text=label
    p=out/"\u6587\u6863.pptx";deck.save(p)
    assert pptx.Presentation(p).slides[0].shapes[0].text==label
    x=out/"\u8868\u683c.xlsx";w=openpyxl.Workbook();w.active.append(["name","value"]);w.active.append([label,7]);w.save(x);w.close()
    frame=pandas.read_excel(x);assert frame.iloc[0,0]==label and int(frame.iloc[0,1])==7
    import zipfile
    for path,member in ((word,"word/document.xml"),(p,"ppt/slides/slide1.xml"),(x,"xl/worksheets/sheet1.xml")):
        with zipfile.ZipFile(path) as z:
            tree=etree.fromstring(z.read(member),etree.XMLParser(resolve_entities=False,no_network=True))
            assert label in "".join(tree.itertext())
    print("LXML_NATIVE_LIBRARIES="+repr((etree.LXML_VERSION,etree.LIBXML_VERSION,etree.LIBXSLT_VERSION)),flush=True)
elif SUITE=="pyyaml":
    import yaml
    assert yaml.__with_libyaml__
    import yaml._yaml as ext
    assert Path(ext.__file__).resolve().is_relative_to(root/"tool/python")
    ordinary={"name":label,"count":7,"enabled":True,"items":["a","b"]}
    path=out/"\u914d\u7f6e.yaml"
    for loader,dumper in ((yaml.SafeLoader,yaml.SafeDumper),(yaml.CSafeLoader,yaml.CSafeDumper)):
        path.write_text(yaml.dump(ordinary,Dumper=dumper,allow_unicode=True),encoding="utf-8")
        assert yaml.load(path.read_text(encoding="utf-8"),Loader=loader)==ordinary
        simple="base: &base\n  name: "+label+"\n  count: 7\nitem:\n  <<: *base\n  count: 8\n"
        obj=yaml.load(simple,Loader=loader)
        assert obj["item"]=={"name":label,"count":8}
elif SUITE=="markdown-it-py":
    from markdown_it import MarkdownIt
    from rich.console import Console
    from rich.markdown import Markdown
    markdown="# "+label+"\n\nA **bold** [link](https://example.invalid/) and \`code\`.\n\n- item\n"
    path=out/"\u6587\u6863.md";path.write_text(markdown,encoding="utf-8")
    renderer=MarkdownIt("commonmark",{"html":False})
    rendered=renderer.render(path.read_text(encoding="utf-8"))
    assert "<h1>"+label+"</h1>" in rendered and "<strong>bold</strong>" in rendered and "<code>code</code>" in rendered
    assert renderer.parse(markdown)[0].type=="heading_open"
    assert "&lt;span&gt;" in renderer.render("<span>ordinary text</span>")
    stream=io.StringIO()
    Console(file=stream,width=80,color_system=None).print(Markdown(markdown))
    assert label in stream.getvalue() and "bold" in stream.getvalue()
    assert EXPECTED[SUITE] in cli("markdown-it",["--version"])
elif SUITE=="charset-normalizer":
    from charset_normalizer import from_bytes,from_path
    import requests
    from requests.models import Response
    for encoding in ("utf-8","utf-8-sig","utf-16"):
        raw=(label+" ordinary text\n") .encode(encoding)
        path=out/("text-"+encoding+".txt");path.write_bytes(raw)
        for matched in (from_bytes(raw).best(),from_path(path).best()):
            assert matched is not None and str(matched)==label+" ordinary text\n",(encoding,matched)
        response=Response();response._content=raw;response.encoding=encoding
        assert response.text==label+" ordinary text\n"
        assert response.apparent_encoding is not None
    assert EXPECTED[SUITE] in cli("normalizer",["--version"])
elif SUITE=="pygments":
    from pygments import highlight,lex
    from pygments.lexers import get_lexer_by_name
    from pygments.formatters import HtmlFormatter
    from rich.console import Console
    from rich.syntax import Syntax
    for name,code in (("python","print('"+label+"')\n"),("sql","select 7 from dual;"),("json",'{"name":"'+label+'"}')):
        path=out/(name+".txt");path.write_text(code,encoding="utf-8")
        lexer=get_lexer_by_name(name)
        assert "".join(t for _,t in lex(code,lexer)).strip()==code.strip()
        assert "<pre>" in highlight(code,lexer,HtmlFormatter())
        stream=io.StringIO();Console(file=stream,width=80,color_system=None).print(Syntax(code,name))
        assert stream.getvalue().strip()
    assert EXPECTED[SUITE] in cli("pygmentize",["-V"])
else:
    raise AssertionError(SUITE)
print("NATIVE_REMAINING_STABLE_CONSUMER=PASS "+SUITE+" "+EXPECTED[SUITE]+" "+MODE,flush=True)
print("PORTABLE_TARGETED_REMAINING_STABLE_OK",flush=True)
'''

def expected_versions():
    pairs={}
    for line in (ROOT/"tool/python-packages.in.txt").read_text(encoding="utf-8").splitlines():
        if "==" in line and not line.lstrip().startswith("#"):
            k,v=line.split("==",1);pairs[k.lower().replace("_","-")]=v
    return {k:pairs[k] for k in ("lxml","pyyaml","markdown-it-py","charset-normalizer","pygments")}

def native(suite,mode,build):
    assert os.name=="nt" and sys.flags.isolated
    assert suite in {"lxml","pyyaml","markdown-it-py","charset-normalizer","pygments"} and mode in {"normal","yolo"}
    assert build=="consumer"
    for p in (*reversed(ROOT.parents),ROOT):m.ordinary(p)
    scratch=ROOT/"tmp";scratch.mkdir(exist_ok=True);m.ordinary(scratch)
    with core.extracted_package_fixture(scratch,suite+"-"+mode+"-"+build) as owned:
        fixture=owned/"Relocated \u4fbf\u643a Portable";fixture.mkdir()
        manifest=json.loads((ROOT/"tool/runtime-manifest.json").read_text(encoding="utf-8-sig"))
        bat="\u542f\u52a8Codex.bat"
        for relative in ("env.ps1","run-codex.ps1",bat,"tool/runtime-manifest.json",
                         "tool/portable-process.ps1","tool/python","tool/node","tool/bin",
                         "tool/android/platform-tools","home/skills",*manifest["files"]):
            m.copy_input(relative,fixture)
        if mode=="yolo":
            source=ROOT/"Version_History/YOLO mode\u4e13\u7528\u5305-env.ps1";m.ordinary(source)
            (fixture/"env.ps1").write_bytes(source.read_bytes())
        (fixture/"codex-resources").mkdir(exist_ok=True)
        probe=fixture/"work/tool-probe";probe.mkdir(parents=True)
        pth=fixture/"tool/python/python314._pth";original_pth=pth.read_bytes()
        assert original_pth==(ROOT/"tool/python/python314._pth").read_bytes()
        for sentinel in (fixture/"protected-audit.txt",owned/"outside-workspace-audit.txt"):
            sentinel.write_bytes(b"unchanged synthetic sentinel")
        (fixture/"home/portable-extensions.toml").write_text('[mcp_servers.portable_browser]\ncommand = "synthetic-never-executed"\n',encoding="utf-8")
        source="MODE="+repr(mode)+"\nSUITE="+repr(suite)+"\nBUILD="+repr(build)+"\nEXPECTED="+repr(expected_versions())+"\n"+PROBE
        (probe/"documents.py").write_text(source,encoding="utf-8")
        compile(source,str(probe/"documents.py"),"exec")
        core.DOCUMENT_MARKER="PORTABLE_TARGETED_REMAINING_STABLE_OK"
        # Reuse the already verified shell result/continuation protocol,
        # not the browser, MCP or prior document workloads.
        handler=core.handler_for(fixture,"documents")
        m.MODEL_REQUESTS.clear();m.MODEL_ERRORS.clear()
        model="gpt-6.2-sol"
        with m.serving(m.provider("",model=model,handler=handler,max_requests=2+core.MAX_CELL_WAITS)) as port:
            (fixture/"env.local.ps1").write_text(
                '$env:CODEX_AUTH_MODE = "api"\n'
                '$env:CODEX_PROXY_ENABLED = "false"\n'
                '$env:CODEX_DISABLE_WEBSOCKET = "true"\n'
                f'$env:CODEX_MODEL = "{model}"\n'
                f'$env:CODEX_BASE_URL = "http://127.0.0.1:{port}/v1"\n'
                '$env:OPENAI_API_KEY = "synthetic-offline-not-a-real-key"\n',encoding="utf-8")
            windows=Path(os.environ["SystemRoot"]);cmd=windows/"System32/cmd.exe"
            env={k:os.environ[k] for k in ("SystemRoot","WINDIR","SystemDrive","ComSpec","PATHEXT","OS","PROCESSOR_ARCHITECTURE","USERNAME","COMPUTERNAME") if k in os.environ}
            env["PATH"]=str(windows/"System32")
            command=(f'"{cmd}" /d /s /c ""{fixture / bat}" --portable-auth=api '
                     'exec --skip-git-repo-check --json "Run the authorized local compatibility check.""')
            proc=subprocess.Popen(command,executable=str(cmd),cwd=fixture,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                out,err=proc.communicate(timeout=450)
            except subprocess.TimeoutExpired:
                subprocess.run([str(windows/"System32/taskkill.exe"),"/PID",str(proc.pid),"/T","/F"],capture_output=True,timeout=20)
                proc.communicate(timeout=20);raise AssertionError("Native targeted fixture timed out")
            if proc.returncode or m.MODEL_ERRORS or core.DONE.encode() not in out:
                print(out.decode("utf-8","replace")[-16000:]);print(err.decode("utf-8","replace")[-16000:])
                raise AssertionError("Native targeted failure "+suite+"/"+mode+"/"+build+": "+repr(m.MODEL_ERRORS))
            assert handler.continuation.finished and len(m.MODEL_REQUESTS)==2+handler.continuation.wait_count
            exits=[]
            for line in out.decode("utf-8","replace").splitlines():
                try:event=json.loads(line)
                except ValueError:continue
                item=event.get("item",{})
                if event.get("type")=="item.completed" and item.get("type")=="command_execution":exits.append(item.get("exit_code"))
            assert exits and all(x==0 for x in exits),exits
            evidence="".join(handler.continuation.evidence)
            marker="NATIVE_REMAINING_STABLE_CONSUMER=PASS "+suite+" "+expected_versions()[suite]+" "+mode
            assert marker in evidence and "NATIVE_REMAINING_STABLE_POLICY=PASS "+mode in evidence
            assert pth.read_bytes()==original_pth
            for sentinel in (fixture/"protected-audit.txt",owned/"outside-workspace-audit.txt"):
                assert sentinel.read_bytes()==b"unchanged synthetic sentinel"
            assert not (fixture/"cache/browser").exists()
            print("TARGETED_NATIVE_ACCEPTANCE=PASS "+suite+" "+mode+" "+build,flush=True)

if __name__=="__main__":
    assert len(sys.argv)==4
    native(*sys.argv[1:])
