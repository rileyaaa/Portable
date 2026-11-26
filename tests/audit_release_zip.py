"""Developer-only audit of the original published customer ZIP.

The hosted interpreter is an archive verifier, synthetic HTTP/MCP peer and
process supervisor ONLY. All tested product commands run the exact extracted
release, and no source checkout payload is copied into the tested package.
No new customer ZIP, publication, external account, device or host profile scan.
"""
from __future__ import annotations
import ast, contextlib, hashlib, importlib.util, json, os, pathlib, re
import shutil, socketserver, stat, subprocess, sys, time, traceback, urllib.parse
import urllib.request, zipfile
from collections import Counter
from pathlib import Path

REPO="rileyaaa/Portable"
TAG="v0.172.0-portable.1"
FROZEN="4fb0b50228057cd0be41fbb191e15e065e64e368"
HARNESS="fbc3b63c73cb507455f78c2315ebb5a4604d9a58"
BRANCH="refs/heads/dev/stable-tool-refresh"
ZIP="Codex-Portable-v0.172.0-portable.1-windows-x64.zip"
ASSETS={
    ZIP:(567888467,"a406e4487bde19057491b6515f7abcab74faf2e3437366b0b23f9940af5760dc"),
    "release-manifest.json":(1732194,"1c50016f81b22cb9dd6df52b41dd1686a99d90ef63da12a0ee0c71f25a829fd8"),
    "SHA256SUMS":(207,"2ea5fea72dbb968ef82498e8d2316899ad81e492753d72c84902bb6d33f4e381")}
SOURCE=Path(__file__).resolve().parents[1]
WIN=Path(os.environ["SystemRoot"])
CMD=WIN/"System32/cmd.exe"
PS=WIN/"System32/WindowsPowerShell/v1.0/powershell.exe"
ROWS=[]
META={}
core=m=stdio=None
ROOT=None
MEMBERS={}
REPORT=None
def safe_text(s):
    # Never persist the generated synthetic proxy capability in the report.
    s=re.sub(r"(?i)(codex:)[a-f0-9]{64}",r"\1<redacted>",str(s))
    s=re.sub(r"(?i)(proxy[_ -]?token[=: ]+)[a-f0-9]{64}",r"\1<redacted>",s)
    return s[:10000]
def row(mode,item,status,detail="",covers=(),env=(),packages=()):
    d=dict(mode=mode,item=item,status=status,detail=safe_text(detail),
           covers=list(covers),env=list(env),packages=list(packages))
    ROWS.append(d)
    print("RELEASE_AUDIT_ROW="+json.dumps(d,ensure_ascii=True),flush=True)
    save()
def save():
    if REPORT:
        REPORT.write_text(json.dumps({"metadata":META,"rows":ROWS},ensure_ascii=True,indent=2)+"\n",encoding="utf-8")
def check(mode,item,fn,covers=(),env=(),packages=()):
    try:
        val=fn()
        row(mode,item,"PASS_ACTUAL",val or "assertions passed",covers,env,packages)
        return True
    except Exception:
        row(mode,item,"FAIL",traceback.format_exc(),covers,env,packages)
        return False
def git(*args):
    return subprocess.check_output(["git",*args],cwd=SOURCE)
def plain(p,directory=False):
    s=p.lstat()
    assert not stat.S_ISLNK(s.st_mode) and not getattr(s,"st_file_attributes",0)&0x400,str(p)
    assert stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode) and s.st_nlink==1,str(p)
def ancestors(p):
    for a in (*reversed(p.parents),p):plain(a,True)
def digest(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def guard():
    assert os.name=="nt" and sys.flags.isolated
    assert os.environ.get("GITHUB_ACTIONS")=="true" and os.environ.get("GITHUB_REPOSITORY")==REPO
    assert os.environ.get("GITHUB_REF")==BRANCH
    assert git("rev-parse","HEAD").decode().strip()==os.environ["GITHUB_SHA"]
    assert not git("diff","--name-only",HARNESS,"HEAD","--","tests/check_codex_tool_discovery.py","tests/check_codex_browser_mcp.py","tests/check_browser_mcp_stdio.py"),"Accepted orchestration helper changed"
    # These checkout files are test infrastructure only, never product files.
    assert not Path(sys.executable).resolve().is_relative_to(SOURCE)
    print("ORCHESTRATOR_ONLY="+str(sys.executable),flush=True)
class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        u=urllib.parse.urlsplit(newurl)
        assert u.scheme=="https" and u.hostname in {"github.com","release-assets.githubusercontent.com","objects.githubusercontent.com","github-releases.githubusercontent.com"},"Unexpected release asset redirect"
        assert not u.username and not u.password
        return super().redirect_request(req,fp,code,msg,headers,newurl)
def download(owned):
    opener=urllib.request.build_opener(OfficialRedirect)
    for name,(size,expected) in ASSETS.items():
        url="https://github.com/"+REPO+"/releases/download/"+TAG+"/"+name
        p=owned/name
        h=hashlib.sha256();total=0
        req=urllib.request.Request(url,headers={"User-Agent":"Portable-original-release-audit/1","Accept-Encoding":"identity"})
        with opener.open(req,timeout=180) as resp,p.open("xb") as dest:
            for part in iter(lambda:resp.read(1024*1024),b""):
                total+=len(part);assert total<=size
                h.update(part);dest.write(part)
        assert total==size and h.hexdigest()==expected,(name,total,h.hexdigest())
        assert digest(p)==expected
        print("OFFICIAL_RELEASE_ASSET_VERIFIED="+name+" "+expected+" size="+str(total),flush=True)
    sums={}
    for line in (owned/"SHA256SUMS").read_text(encoding="ascii").splitlines():
        v,name=line.split(None,1)
        assert name not in sums
        sums[name]=v
    assert sums=={k:ASSETS[k][1] for k in (ZIP,"release-manifest.json")},sums
    manifest=json.loads((owned/"release-manifest.json").read_bytes())
    assert manifest["source_commit"]==FROZEN and manifest["release_version"]==TAG
    assert manifest["archive"]==ZIP and manifest["package_kind"]=="customer"
    assert manifest["codex_version"]=="0.172.0" and manifest["browser_version"]=="155.0.8059.12"
    assert manifest["file_count"]==len(manifest["files"])==9076
    return manifest
def safe_path(name):
    assert isinstance(name,str) and name and "\\" not in name and not name.startswith("/")
    for p in name.split("/"):
        assert p and p not in {".","..",".git"} and not p.endswith((" ","."))
        assert not re.search(r'[<>:"|?*\x00-\x1f]',p)
        assert not re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?",p)
    return name
def verify_tree(root,files):
    ancestors(root);actual={}
    for base,dirs,names in os.walk(root,followlinks=False):
        for d in dirs:plain(Path(base)/d,True)
        for n in names:
            p=Path(base)/n;plain(p)
            rel=p.relative_to(root).as_posix()
            assert rel in files,("unexpected extracted member",rel)
            record=files[rel]
            assert p.stat().st_size==record["size"] and digest(p)==record["sha256"],rel
            actual[rel]=True
    assert set(actual)==set(files),("missing extracted members",list(set(files)-set(actual))[:20])
def extract(owned,manifest):
    files=manifest["files"]
    assert len({safe_path(n).casefold() for n in files})==len(files)
    assert sum(v["size"] for v in files.values())==manifest["uncompressed_bytes"]
    initial=owned/"initial-original";initial.mkdir()
    with zipfile.ZipFile(owned/ZIP) as z:
        infos=z.infolist()
        # Frozen producer tool/package-release.py: verify_zip() and build_release()
        # write exactly Codex/<manifest relative name>, never explicit directories.
        # This is a single literal prefix, not a generic path normalization.
        expected=["Codex/"+n for n in files]
        names=[i.filename for i in infos]
        raw=set(names);want=set(expected);manifest_names=set(files)
        duplicates=sorted(n for n,c in Counter(names).items() if c!=1)
        missing=sorted(want-raw);extra=sorted(raw-want)
        directories=[i.filename for i in infos if i.is_dir()]
        # Record actual archive differences before rejecting any mismatch.
        diagnostic=dict(manifest_count=len(files),zip_entry_count=len(infos),
            zip_unique_name_count=len(raw),raw_intersection_count=len(raw&manifest_names),
            raw_manifest_only_count=len(manifest_names-raw),raw_zip_only_count=len(raw-manifest_names),
            raw_manifest_only_sample=sorted(manifest_names-raw)[:12],
            raw_zip_only_sample=sorted(raw-manifest_names)[:12],
            expected_prefix="Codex/",prefix_match_count=sum(n.startswith("Codex/") for n in names),
            expected_missing=missing,unexpected_zip_names=extra,duplicates=duplicates,
            explicit_directory_entries=directories,producer_order_matches=names==expected)
        META["archive_name_diagnostic"]=diagnostic;save()
        print("ORIGINAL_ZIP_NAME_DIAGNOSTIC="+json.dumps(diagnostic,ensure_ascii=True),flush=True)
        assert len(infos)==len(files) and not duplicates and not missing and not extra and not directories, "Archive differs from exact frozen Codex/ member contract"
        assert names==expected,"Archive ordering differs from frozen producer/manifest"
        for info in infos:
            assert info.orig_filename==info.filename and info.filename.startswith("Codex/")
            rel=safe_path(info.filename[len("Codex/"):]);record=files[rel]
            assert not info.is_dir() and not info.flag_bits&1
            assert stat.S_IFMT(info.external_attr>>16) in (0,stat.S_IFREG),rel
            assert info.file_size==record["size"] and re.fullmatch("[0-9a-f]{64}",record["sha256"])
            dest=initial/rel;dest.parent.mkdir(parents=True,exist_ok=True)
            h=hashlib.sha256();size=0
            with z.open(info) as src,dest.open("xb") as out:
                for b in iter(lambda:src.read(1024*1024),b""):
                    size+=len(b);assert size<=record["size"];out.write(b);h.update(b)
            assert size==record["size"] and h.hexdigest()==record["sha256"],rel
    verify_tree(initial,files)
    moved=owned/"Original \u4e2d\u6587 \u7a7a\u683c";initial.rename(moved)
    assert not initial.exists()
    verify_tree(moved,files)
    print("ORIGINAL_ZIP_ALL_MEMBERS_AND_REAL_MOVE=PASS "+str(len(files)),flush=True)
    return moved
def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec);sys.modules[name]=obj;spec.loader.exec_module(obj)
    return obj
def setup_helpers(owned):
    global core,m,stdio
    core=load_module("release_audit_core",SOURCE/"tests/check_codex_tool_discovery.py")
    m=core.m
    # The accepted continuation mechanism is runner test infrastructure.
    # The whole-package probe has a finite longer deadline than small probes.
    core.MAX_CELL_WAITS=50
    core.SKILLS={p.parent.name for p in (ROOT/"home/skills").glob("*/SKILL.md") if not p.parent.name.startswith(".")}
    old=owned/"frozen_browser_stdio.py"
    old.write_bytes(git("show",FROZEN+":tests/check_browser_mcp_stdio.py"))
    stdio=load_module("release_frozen_stdio",old)
def frozen_documents():
    parsed=ast.parse(git("show",FROZEN+":tests/check_codex_tool_discovery.py").decode("utf-8-sig"))
    nodes=[x for x in parsed.body if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="DOCUMENTS_PY" for t in x.targets)]
    assert len(nodes)==1
    return ast.literal_eval(nodes[0].value)
@contextlib.contextmanager
def copy_for(owned,label):
    # Each test starts from every byte of the verified release. No test
    # overlays developer payload or invokes source checkout executables.
    base=owned/("case-"+label);base.mkdir()
    initial=base/"Portable initial"
    shutil.copytree(ROOT,initial)
    verify_tree(initial,MEMBERS)
    fixture=base/"Portable \u4e2d\u6587 \u7a7a\u683c"
    initial.rename(fixture);assert not initial.exists()
    verify_tree(fixture,MEMBERS)
    print("EXACT_RELEASE_COPY_MOVED="+label,flush=True)
    try:yield fixture
    finally:
        # Only this unique synthetic case is removed. Never real user state.
        ancestors(base);shutil.rmtree(base)
def clean_env():
    env={k:os.environ[k] for k in ("SystemRoot","WINDIR","SystemDrive","ComSpec","PATHEXT","OS","PROCESSOR_ARCHITECTURE","USERNAME","COMPUTERNAME") if k in os.environ}
    env["PATH"]=str(WIN/"System32")
    return env
def child(argv,cwd,env=None,timeout=240,stdin=None,exe=None):
    p=subprocess.Popen(argv,executable=exe,cwd=cwd,env=env or clean_env(),
                       stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                       stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:out,err=p.communicate(stdin,timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run([str(WIN/"System32/taskkill.exe"),"/PID",str(p.pid),"/T","/F"],capture_output=True,timeout=20,check=False)
        out,err=p.communicate(timeout=20)
        raise RuntimeError("Owned child deadline; "+safe_text(out.decode("utf-8","replace")[-2000:]))
    return p.returncode,out.decode("utf-8","backslashreplace"),err.decode("utf-8","backslashreplace")
def bat(fixture,entry,args,env=None,timeout=240,stdin=None):
    target=fixture/entry;plain(target)
    command='"'+str(CMD)+'" /d /s /c "'+subprocess.list2cmdline([str(target),*args])+'"'
    return child(command,fixture,env,timeout,stdin,exe=str(CMD))
def mode_files(fixture,mode):
    if mode=="yolo":
        for name in ("env.ps1","run-codex.ps1"):
            template=fixture/("Version_History/YOLO mode\u4e13\u7528\u5305-"+name)
            plain(template);(fixture/name).write_bytes(template.read_bytes())
        assert (fixture/"run-codex.ps1").read_bytes()==(ROOT/"run-codex.ps1").read_bytes()
    return "\u542f\u52a8Codex-\u7ef4\u62a4\u6a21\u5f0f.bat" if mode=="maintenance" else "\u542f\u52a8Codex.bat"
def api_config(fixture,port,model,mode,extra=""):
    text=('$env:CODEX_AUTH_MODE = "api"\n'
          '$env:CODEX_DISABLE_WEBSOCKET = "true"\n'
          f'$env:CODEX_MODEL = "{model}"\n'
          f'$env:CODEX_BASE_URL = "http://127.0.0.1:{port}/v1"\n'
          '$env:OPENAI_API_KEY = "synthetic-offline-not-a-real-key"\n'
          '$env:CODEX_HTTP_HEADERS_TOML = \'{ "X-Portable-Audit-Static" = "synthetic-static" }\'\n'
          '$env:CODEX_ENV_HTTP_HEADERS_TOML = \'{ "X-Portable-Audit" = "PORTABLE_TEST_HEADER", "X-Portable-Host-Only" = "PORTABLE_TEST_MISSING_HEADER" }\'\n'
          '$env:PORTABLE_TEST_HEADER = "synthetic-package-value"\n')
    if mode!="yolo":text+='$env:CODEX_PROXY_ENABLED = "false"\n'
    text+=extra
    (fixture/"env.local.ps1").write_text(text,encoding="utf-8")
def handler_for(fixture):
    continuation=None
    marker="PORTABLE_RELEASE_FULL_CONSUMER_DONE"
    def handler(body,_):
        nonlocal continuation
        if continuation is None:
            prompt=json.dumps({"instructions":body.get("instructions"),"input":body.get("input")},ensure_ascii=False)
            assert all(n in prompt for n in core.SKILLS),"Released local skill catalog absent"
            entries=list(m.tool_entries(body.get("tools",[])))
            assert not any("portable_browser" in str(ns)+str(t.get("name")) for ns,t in entries)
            command=("& (Join-Path $env:CODEX_INSTALL_DIR 'tool/python/python.exe') -B "
                     "(Join-Path $env:CODEX_INSTALL_DIR 'work/tool-probe/documents.py'); exit $LASTEXITCODE")
            args={"cmd":command,"workdir":str(fixture/"work"),"login":False,"yield_time_ms":30000,"max_output_tokens":7000}
            custom=next(((ns,t) for ns,t in entries if t.get("type")=="custom" and t.get("name")=="exec"),None)
            if custom:
                ns,t=custom
                code=('const e=ALL_TOOLS.find(x=>x.name.endsWith("exec_command")); if(!e)throw new Error("missing shell"); '
                      'let r=await tools[e.name]('+json.dumps(args)+'); '
                      'for(let i=0;;i++){const v=r.structuredContent||r; if(r.isError||v.isError)throw new Error(JSON.stringify(r)); '
                      'text(JSON.stringify(v)); if(v.exit_code!==undefined&&v.exit_code!==null){if(v.exit_code!==0||v.session_id!=null)throw new Error("shell exit");break;} '
                      'if(!Number.isSafeInteger(v.session_id)||i>=39)throw new Error("finite whole-package shell deadline"); '
                      'const w=ALL_TOOLS.find(x=>x.name.endsWith("write_stdin")); if(!w)throw new Error("missing wait"); '
                      'r=await tools[w.name]({session_id:v.session_id,chars:"",yield_time_ms:30000});}')
                item={"type":"custom_tool_call","call_id":"portable-probe","name":t["name"],"input":code}
            else:
                ns,t=next((ns,t) for ns,t in entries if t.get("type")=="function" and t.get("name","").endswith("exec_command"))
                item={"type":"function_call","call_id":"portable-probe","name":t["name"],"arguments":json.dumps(args)}
            if ns is not None:item["namespace"]=ns
            continuation=core.NativeProbeContinuation(custom is not None)
            handler.continuation=continuation
            return item
        follow=continuation.receive(body)
        if follow is not None:return follow
        assert marker in "".join(continuation.evidence),"Full consumer did not reach completion marker"
        return {"id":"msg_release_audit","type":"message","role":"assistant","status":"completed",
                "content":[{"type":"output_text","text":"release-full-native-audit-completed","annotations":[]}]}
    return handler
def native(fixture,mode,http_port,socks_port):
    entry=mode_files(fixture,mode)
    work=fixture/"work/tool-probe";work.mkdir(parents=True,exist_ok=True)
    (work/"office_pdf_probe.py").write_text(frozen_documents(),encoding="utf-8")
    source="MODE="+repr(mode)+"\nHTTP_PORT="+str(http_port)+"\nSOCKS_PORT="+str(socks_port)+"\n"+(SOURCE/"tests/audit_release_zip_consumer.py").read_text(encoding="utf-8")
    compile(source,str(work/"documents.py"),"exec")
    (work/"documents.py").write_text(source,encoding="utf-8")
    for sentinel in (fixture/"protected-audit.txt",fixture.parent/"outside-workspace-audit.txt"):
        sentinel.write_bytes(b"synthetic audit sentinel")
    store=fixture/"home/portable-extensions.toml"
    assert not store.exists()
    store.write_text('[mcp_servers.portable_browser]\ncommand = "synthetic-never-executed"\n',encoding="utf-8")
    original_store=store.read_bytes()
    model="gpt-6.2-sol"
    m.MODEL_REQUESTS.clear();m.MODEL_ERRORS.clear()
    handler=handler_for(fixture)
    with m.serving(m.provider("",model=model,handler=handler,
          expected_headers={"X-Portable-Audit":"synthetic-package-value","X-Portable-Audit-Static":"synthetic-static"},
          forbidden_headers=("X-Portable-Host-Only",),max_requests=52)) as port:
        extra=""
        if mode=="yolo":
            extra=('$env:CODEX_PROXY_ENABLED = "true"\n$env:CODEX_PROXY_PROTOCOL = "socks5"\n'
                   '$env:CODEX_PROXY_HOST = "127.0.0.1"\n'
                   f'$env:CODEX_PROXY_PORT = "{socks_port}"\n'
                   '$env:CODEX_PROXY_HTTP_BRIDGE = "true"\n$env:CODEX_PROXY_BRIDGE_HOST = "127.0.0.1"\n'
                   '$env:CODEX_PROXY_BRIDGE_PORT = ""\n$env:CODEX_PROXY_FOR_SUBPROCESS = "true"\n'
                   '$env:CODEX_PROXY_BYPASS_MODEL = "true"\n')
        api_config(fixture,port,model,mode,extra)
        env=clean_env();env["PORTABLE_TEST_HEADER"]="synthetic-parent-conflict";env["PORTABLE_TEST_MISSING_HEADER"]="synthetic-parent-only"
        env["CODEX_HOME"]=str(fixture.parent/"never-used-parent-home")
        status,out,err=bat(fixture,entry,["--portable-auth=api","exec","--skip-git-repo-check","--json","Run the authorized local original release audit."],env,timeout=1500)
    # Read each case result even if a later shell/continuation failed.
    results=work/"audit-results.jsonl"
    if results.exists():
        for line in results.read_text(encoding="utf-8").splitlines():
            x=json.loads(line);assert x["mode"]==mode
            row(mode,x["item"],x["status"],x.get("detail",""),x.get("covers",()),x.get("env",()),x.get("packages",()))
    if status or m.MODEL_ERRORS or "release-full-native-audit-completed" not in out:
        raise AssertionError(("actual BAT/Host session",status,m.MODEL_ERRORS,safe_text(out[-4500:]),safe_text(err[-4500:])))
    assert handler.continuation.finished
    assert len(m.MODEL_REQUESTS)==2+handler.continuation.wait_count
    assert results.exists() and "PORTABLE_RELEASE_FULL_CONSUMER_DONE" in "".join(handler.continuation.evidence)
    assert store.read_bytes()==original_store
    for sentinel in (fixture/"protected-audit.txt",fixture.parent/"outside-workspace-audit.txt"):
        assert sentinel.read_bytes()==b"synthetic audit sentinel"
    row(mode,"actual BAT/Codex/Host synthetic Responses and extension-off","PASS_ACTUAL",
        "real configured request, actual shell output, durable user MCP retained but inactive",
        [entry,"codex.exe","codex-code-mode-host.exe","run-codex.ps1"],
        ["CODEX_AUTH_MODE","CODEX_BASE_URL","CODEX_MODEL","CODEX_DISABLE_WEBSOCKET","CODEX_HTTP_HEADERS_TOML","CODEX_ENV_HTTP_HEADERS_TOML","CODEX_PORTABLE_ALLOW_USER_MCP","CODEX_PROXY_BYPASS_MODEL"] if mode=="yolo" else
        ["CODEX_AUTH_MODE","CODEX_BASE_URL","CODEX_MODEL","CODEX_DISABLE_WEBSOCKET","CODEX_HTTP_HEADERS_TOML","CODEX_ENV_HTTP_HEADERS_TOML","CODEX_PORTABLE_ALLOW_USER_MCP"])
    sqlite=fixture/"sqlite"
    actual=[p.name for p in sqlite.glob("*.sqlite*") if p.is_file()] if sqlite.exists() else []
    if actual:row(mode,"actual Codex SQLite state","PASS_ACTUAL",repr(actual),env=["CODEX_SQLITE_HOME"])
    else:row(mode,"actual Codex SQLite state","NOT_REACHED","no state file produced by this synthetic session",env=["CODEX_SQLITE_HOME"])
def mcp_stdio(fixture,http_port,proxy_port,socks_port):
    workspace=fixture/"work/browser-debug";workspace.mkdir(parents=True,exist_ok=True)
    sentinel=workspace/"keep.txt";sentinel.write_text("keep")
    seen=set()
    def call(client,name,**args):
        result=client.call(name,**args)
        seen.add(name);row("mcp-stdio",name,"PASS_ACTUAL","actual original browser bridge JSON-RPC call",["tool/automation/browser-bridge.js"])
        return result
    with stdio.Client(fixture,workspace) as client:
        client.initialize()
        tools=client.request("tools/list")["result"]["tools"]
        advertised={t["name"]:t.get("inputSchema",{}) for t in tools}
        META["mcp_advertised"]=advertised;save()
        assert not any("run_code" in n or "upload" in n for n in advertised)
        rejected=client.request("tools/call",{"name":"browser_navigate","arguments":{"url":"file:///C:/refused"}})
        assert "error" in rejected
        row("mcp-stdio","file URL and code/upload boundary","PASS_ACTUAL","rejected file URL; no unrestricted run_code/upload exposed")
        url=f"http://127.0.0.1:{http_port}/"
        call(client,"browser_navigate",url=url)
        assert "Portable MCP smoke" in json.dumps(call(client,"browser_snapshot"))
        call(client,"browser_click",target="button",element="Click me")
        assert "yes" in json.dumps(call(client,"browser_evaluate",function="() => document.body.dataset.clicked"))
        call(client,"browser_take_screenshot",filename="proof.png")
        assert (workspace/"proof.png").stat().st_size>0
        for name,args in (("browser_console_messages",{}),("browser_network_requests",{}),("browser_tabs",{"action":"list"})):
            if name in advertised:
                schema=advertised[name];required=set(schema.get("required",[]))
                if required<=set(args) and set(args)<=set(schema.get("properties",{})):
                    check("mcp-stdio",name,lambda n=name,a=args:call(client,n,**a))
        assert "portable_mcp=persisted" in json.dumps(call(client,"browser_evaluate",function="() => { document.cookie='portable_mcp=persisted; Max-Age=3600; Path=/'; return document.cookie; }"))
        call(client,"browser_close")
        call(client,"browser_navigate",url=url)
        assert "portable_mcp=persisted" in json.dumps(call(client,"browser_evaluate",function="() => document.cookie"))
        call(client,"browser_close")
        row("mcp-stdio","persistent cookie close/reopen","PASS_ACTUAL","real original profile survives close/reopen")
    for name in sorted(set(advertised)-seen):
        row("mcp-stdio",name,"NOT_RUN","advertised schema inventoried; no individual consumer assertion yet")
    stdio.PROXY_REQUESTS.clear();stdio.SOCKS_REQUESTS.clear()
    with stdio.Client(fixture,workspace,proxy_port) as client:
        client.initialize();client.call("browser_navigate",url="http://portable-browser.invalid/")
        assert "Portable MCP smoke" in json.dumps(client.call("browser_snapshot"))
        assert stdio.PROXY_REQUESTS
        client.call("browser_navigate",url=f"http://127.0.0.1:{http_port}/")
        assert "Portable MCP smoke" in json.dumps(client.call("browser_snapshot"));client.call("browser_close")
    row("mcp-stdio","authenticated HTTP proxy and loopback bypass","PASS_ACTUAL","synthetic upstream saw actual request",["tool/automation/start-browser.ps1"],["HTTP_PROXY","NO_PROXY","CODEX_PROXY_ENABLED","CODEX_PROXY_FOR_SUBPROCESS"])
    with stdio.Client(fixture,workspace,socks_port=socks_port) as client:
        client.initialize();client.call("browser_navigate",url="http://portable-socks.invalid/")
        assert "Portable MCP smoke" in json.dumps(client.call("browser_snapshot"))
        assert stdio.SOCKS_REQUESTS;client.call("browser_close")
    assert sentinel.read_text()=="keep"
    row("mcp-stdio","SOCKS5 proxy","PASS_ACTUAL","actual original Chromium and bridge; owned output retained",["tool/automation/start-browser.ps1","tool/automation/browser-bridge.js"],["ALL_PROXY","NO_PROXY","CODEX_PROXY_ENABLED","CODEX_PROXY_FOR_SUBPROCESS"])
def mcp_native(fixture):
    m.MODEL_REQUESTS.clear();m.MODEL_ERRORS.clear();m.PAGE_HITS.clear()
    model="gpt-6-sol"
    with m.serving(m.NativePage) as page_port,m.serving(m.provider(
         f"http://127.0.0.1:{page_port}/",model=model,
         expected_headers={"X-Portable-Audit":"synthetic-package-value","X-Portable-Audit-Static":"synthetic-static"},
         forbidden_headers=("X-Portable-Host-Only",))) as api_port:
        api_config(fixture,api_port,model,"normal",'$env:CODEX_PORTABLE_ALLOW_USER_MCP = "true"\n')
        workspace=fixture/"work/browser-debug"
        store=fixture/"home/portable-extensions.toml"
        args=["-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",str(fixture/"tool/automation/start-browser.ps1"),"-TaskAuthorized","-Workspace",str(workspace)]
        lines=["[mcp_servers.portable_browser]","command = "+json.dumps(str(PS)),
               "args = "+json.dumps(args),"cwd = "+json.dumps(str(fixture/"work")),
               'env_vars = ["CODEX_INSTALL_DIR","CODEX_HOME","CODEX_PROXY_ENABLED","CODEX_PROXY_FOR_SUBPROCESS","CODEX_SANDBOX_NETWORK_ACCESS","HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","NO_PROXY"]',
               "startup_timeout_sec = 120","tool_timeout_sec = 120","supports_parallel_tool_calls = false","required = true",'default_tools_approval_mode = "approve"']
        store.write_text("\n".join(lines)+"\n",encoding="utf-8");before=store.read_bytes()
        env=clean_env();env.update(PORTABLE_TEST_HEADER="synthetic-parent-conflict",PORTABLE_TEST_MISSING_HEADER="synthetic-parent-only")
        code,out,err=bat(fixture,"\u542f\u52a8Codex.bat",["--portable-auth=api","--portable-extensions","exec","--skip-git-repo-check","--json","Run authorized synthetic original MCP audit."],env,timeout=360)
        assert code==0 and not m.MODEL_ERRORS and "native-browser-mcp-ok" in out,(code,m.MODEL_ERRORS,safe_text(out[-4000:]),safe_text(err[-4000:]))
        assert len(m.MODEL_REQUESTS)==2 and m.PAGE_HITS
        assert store.read_bytes()==before and (fixture/"cache/browser/profile").is_dir()
        import tomllib
        cfg=tomllib.loads((fixture/"home/config.toml").read_text(encoding="utf-8-sig"))
        assert "portable_browser" in cfg["mcp_servers"]
    return "real original BAT, Codex/Host, opt-in MCP client, original Playwright/Chromium and returned page marker"
def maintenance_entries(fixture):
    # Direct utility launch only in an owned release copy. Do not run an
    # external account request, destructive device tool or host residue scan.
    env=clean_env()
    for k in ("HOME","USERPROFILE","APPDATA","LOCALAPPDATA","TEMP","TMP","PROGRAMDATA"):
        path=fixture/"tmp"/("audit-"+k.lower());path.mkdir(parents=True,exist_ok=True);env[k]=str(path)
    def isolate():
        path=fixture/"\u68c0\u67e5\u9694\u79bb.ps1"
        rc,out,err=child([str(PS),"-NoLogo","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",str(path)],fixture,env,timeout=100)
        assert rc==0,(rc,safe_text(out[-3000:]),safe_text(err[-2000:]))
        return "real package-only isolation script completed; no -ScanHostResidue"
    check("utilities","package-only isolation check",isolate,["\u68c0\u67e5\u9694\u79bb.ps1"])
    def cleanup():
        cookie=fixture/"cache/browser/audit-cookie.txt";cookie.parent.mkdir(parents=True,exist_ok=True);cookie.write_text("synthetic cookie")
        work=fixture/"work/keep-audit.txt";work.write_text("keep")
        script=fixture/"\u6e05\u7406\u7f13\u5b58.ps1"
        rc,out,err=child([str(PS),"-NoLogo","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",str(script),"-WhatIf"],fixture,env,timeout=100)
        assert rc==0 and cookie.exists() and work.exists(),(rc,out[-2500:],err[-2500:])
        rc,out,err=child([str(PS),"-NoLogo","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",str(script),"-Yes","-PreserveSkills","-PreserveWork","-PreservePlugins"],fixture,env,timeout=150)
        assert rc==0 and not cookie.exists() and work.read_text()=="keep",(rc,out[-2500:],err[-2500:])
        return "real preview preserves fixture; real cleanup removes owned cookie and preserves work"
    check("utilities","cache cleanup real preview and cleanup",cleanup,["\u6e05\u7406\u7f13\u5b58.ps1"])
    row("utilities","login JSON real online checks","NOT_APPLICABLE","No real account/authentication request or credential export; local malformed-input regression still separate",["login-json.ps1","login-json-http.py","\u68c0\u67e5login_json.bat"])
    row("utilities","Windows desktop UIAutomation","BLOCKED_UNVERIFIED","Requires actual interactive desktop/owned GUI target; not counted as passed from a service runner",["tool/automation/desktop.ps1","tool/automation/desktop-worker.ps1"])
def inventory():
    # Every executable/library is accounted for; first-party entry points
    # receive per-path evidence, never infer that every vendor helper ran.
    files=MEMBERS
    covered={}
    for x in ROWS:
        for p in x["covers"]:covered.setdefault(p,[]).append((x["mode"],x["item"],x["status"]))
    def firstparty(p):
        return ("/" not in p or p.startswith(("home/skills/","home/plugins/","Version_History/")) or
                (p.startswith("tool/") and not p.startswith(("tool/python/","tool/node/node_modules/","tool/automation/playwright/","tool/automation/browsers/","tool/android/platform-tools/"))))
    items=[]
    for p in sorted(files):
        suffix=Path(p).suffix.lower()
        if suffix in {".exe",".dll",".pyd",".cmd",".bat",".ps1",".sh"} or (firstparty(p) and suffix in {".py",".js",".cjs",".mjs"}):
            ev=covered.get(p,[])
            if ev:status="EVIDENCE_LISTED"
            elif firstparty(p) or p.startswith(("tool/android/platform-tools/","tool/node/")) and len(p.split("/"))<=4:
                status="NOT_RUN_ENTRY_OR_HELPER"
            else:status="INTEGRITY_ONLY_VENDOR_COMPONENT"
            items.append({"path":p,"status":status,"evidence":ev})
    # Include non-extension managed npm/corepack shims and all package metadata.
    for p in ("tool/node/npm","tool/node/npx","tool/node/corepack"):
        if p in files:items.append({"path":p,"status":"NOT_RUN_POSIX_SHIM_ON_WINDOWS","evidence":[]})
    package_names={}
    for x in ROWS:
        for p in x["packages"]:package_names.setdefault(p.lower().replace("_","-"),[]).append((x["mode"],x["item"],x["status"]))
    pins={}
    for line in (ROOT/"tool/python-packages.in.txt").read_text(encoding="utf-8").splitlines():
        if "==" in line and not line.startswith("#"):
            k,v=line.split("==",1);pins[k.lower().replace("_","-")]=v
    assert len(pins)==49
    python=[{"name":k,"version":v,"evidence":package_names.get(k,[]),"status":"EVIDENCE_LISTED" if k in package_names else "IDENTITY_OR_TRANSITIVE_ONLY"} for k,v in sorted(pins.items())]
    npm=[]
    for p in sorted(files):
        if p.startswith(("tool/node/node_modules/","tool/automation/playwright/")) and p.endswith("/package.json"):
            try:
                q=json.loads((ROOT/p).read_bytes())
                if isinstance(q.get("name"),str) and isinstance(q.get("version"),str):
                    npm.append({"path":p,"name":q["name"],"version":q["version"],"status":"BUNDLED_METADATA; PARENT CONSUMER OR INTEGRITY ONLY"})
            except (ValueError,UnicodeError):pass
    # Enumerate all declared/referenced names in project-owned code (not
    # third-party internals); reconcile actual native policy and use evidence.
    refs={}
    patterns=[
        r'(?i)\$env:([A-Za-z_][A-Za-z0-9_]*)',
        r'(?i)(?:GetEnvironmentVariable|SetEnvironmentVariable|os\.getenv|os\.environ\.get)\s*\(\s*["\']([A-Za-z_][A-Za-z0-9_]*)',
        r'(?i)(?:os\.environ|process\.env)\[\s*["\']([A-Za-z_][A-Za-z0-9_]*)',
        r'\bprocess\.env\.([A-Za-z_][A-Za-z0-9_]*)',
        r'(?im)^\s*(?:@?set\s+)["]?([A-Za-z_][A-Za-z0-9_]*)=',
        r'%([A-Za-z_][A-Za-z0-9_]*)%',
        r'\b(CODEX_[A-Z][A-Z0-9_]+)\b']
    for p in files:
        if not firstparty(p) or Path(p).suffix.lower() not in {".ps1",".bat",".cmd",".py",".js",".cjs",".mjs"}:continue
        if files[p]["size"]>2*1024*1024:continue
        try:s=(ROOT/p).read_text(encoding="utf-8-sig")
        except UnicodeError:continue
        for pattern in patterns:
            for key in re.findall(pattern,s):refs.setdefault(key.upper(),set()).add(p)
    env_evidence={}
    for x in ROWS:
        for name in x["env"]:env_evidence.setdefault(name.upper(),[]).append((x["mode"],x["item"],x["status"]))
    for k in env_evidence:refs.setdefault(k,set())
    variables=[]
    for name,paths in sorted(refs.items()):
        evidence=env_evidence.get(name,[])
        status="EFFECT_EVIDENCE_LISTED" if any(v[2]=="PASS_ACTUAL" for v in evidence) else ("PROPAGATION_OR_OBSERVATION_ONLY" if evidence else "NO_CONSUMER_EVIDENCE")
        variables.append({"name":name,"status":status,"source_references":sorted(paths),"evidence":evidence})
    META["entry_inventory"]=items;META["python_distribution_inventory"]=python
    META["npm_package_inventory"]=npm;META["environment_inventory"]=variables
    META["inventory_note"]="Individual vendor helpers and optional paths are not claimed functional. CODEX names include referenced/guarded/internal names, not just enabled settings. An evidence-listed row may fail; inspect status and actual assertion."
    print("RELEASE_AUDIT_INVENTORY_COUNTS="+json.dumps({"entries":len(items),"python":len(python),"npm":len(npm),"env":len(variables)},sort_keys=True),flush=True)
    save()
def main():
    global ROOT,MEMBERS,REPORT
    guard()
    assert len(sys.argv)==2
    REPORT=Path(sys.argv[1]).absolute()
    owned=REPORT.parent
    ancestors(owned)
    META.update(tag=TAG,source_commit=FROZEN,run_id=os.environ["GITHUB_RUN_ID"],source="original GitHub release assets; no reconstruction",assets=ASSETS,completed=False)
    save()
    try:
        manifest=download(owned);MEMBERS=manifest["files"]
        META["manifest_file_count"]=len(MEMBERS)
        ROOT=extract(owned,manifest)
        row("integrity","exact original ZIP, SHA256SUMS, manifest and all members","PASS_ACTUAL",str(len(MEMBERS))+" files verified before and after real Chinese-space relocation")
        setup_helpers(owned)
        with (stdio.serving(stdio.Page) as http_port,stdio.serving(stdio.Proxy) as proxy_port,
              stdio.serving(stdio.SocksProxy,socketserver.ThreadingTCPServer) as socks_port):
            for mode in ("normal","yolo","maintenance"):
                def one(mode=mode):
                    with copy_for(owned,mode) as fixture:native(fixture,mode,http_port,socks_port)
                check(mode,"complete original native mode harness",one)
            def stdio_one():
                with copy_for(owned,"mcp-stdio") as fixture:mcp_stdio(fixture,http_port,proxy_port,socks_port)
            check("mcp-stdio","complete original MCP stdio workflow",stdio_one)
        def mcp_one():
            with copy_for(owned,"mcp-native") as fixture:return mcp_native(fixture)
        check("mcp-native","actual opt-in Codex/MCP Responses",mcp_one,
              ["\u542f\u52a8Codex.bat","tool/automation/start-browser.ps1","tool/automation/browser-bridge.js","codex-code-mode-host.exe"],
              ["CODEX_PORTABLE_ALLOW_USER_MCP","CODEX_AUTH_MODE","CODEX_MODEL","CODEX_BASE_URL","CODEX_HTTP_HEADERS_TOML","CODEX_ENV_HTTP_HEADERS_TOML"])
        def utilities():
            with copy_for(owned,"utilities") as fixture:maintenance_entries(fixture)
        check("utilities","original maintenance utility harness",utilities)
        verify_tree(ROOT,MEMBERS)
        row("integrity","pristine extracted release unchanged after all cases","PASS_ACTUAL","all source bytes rehashed")
        inventory()
        META["completed"]=True
    except Exception:
        row("orchestrator","whole-package harness stopped","FAIL",traceback.format_exc())
    finally:
        META["status_counts"]=dict(Counter(x["status"] for x in ROWS));save()
        print("RELEASE_AUDIT_STATUS_COUNTS="+json.dumps(META["status_counts"],sort_keys=True),flush=True)
    # Partial success or documented limitations never become an all-pass claim.
    if not META["completed"] or any(x["status"]=="FAIL" for x in ROWS):return 1
    return 0
if __name__=="__main__":
    for stream in (sys.stdout,sys.stderr):stream.reconfigure(encoding="utf-8",errors="backslashreplace")
    raise SystemExit(main())
