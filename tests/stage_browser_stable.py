"""One-time, developer-only stable browser/MCP candidate. No runtime installer or release."""
import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

ROOT = Path.cwd()
PY = ROOT / "tool/python/python.exe"
NODE = ROOT / "tool/node/node.exe"
NPM = ROOT / "tool/node/node_modules/npm/bin/npm-cli.js"
AUTO = ROOT / "tool/automation"
PW = "1.65.1"
PW_TAG = "bbd948344ea9a60bf1e6f125c02ca99b2b51593b"
CHROME = "158.0.8127.88"
REV = "1727472"
URL = f"https://storage.googleapis.com/chrome-for-testing-public/{CHROME}/win64/chrome-win64.zip"
REG = "https://registry.npmjs.org/"
CFT = "https://googlechromelabs.github.io/chrome-for-testing/"
TOOL_DOC = "tool/\u5de5\u5177\u66f4\u65b0\u8bf4\u660e.md"

def git(*args):
    return subprocess.check_output(["git", *map(str,args)],cwd=ROOT)

def paths(*args):
    return set(git(*args).decode("utf-8").split("\0"))-{""}

def clean():
    assert not git("status","--porcelain=v1","--untracked-files=all"),"dirty checkout"

def plain(p, directory=False):
    s=p.lstat()
    assert not stat.S_ISLNK(s.st_mode) and not getattr(s,"st_file_attributes",0)&0x400,str(p)
    assert stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode) and s.st_nlink==1,str(p)

def inventory(folder):
    plain(folder,True)
    result={}
    for here,dirs,files in os.walk(folder,followlinks=False):
        current=Path(here)
        for name in dirs:plain(current/name,True)
        for name in files:
            p=current/name;plain(p)
            result[p.relative_to(folder).as_posix()]=digest(p)
    return result

def digest(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()

def sha(b):
    return hashlib.sha256(b).hexdigest()

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError("Unexpected official artifact redirect")

opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
def fetch(url,max_size):
    with opener.open(urllib.request.Request(url,headers={"User-Agent":"Portable-stable-audit/1"}),timeout=60) as res:
        assert res.url==url
        data=res.read(max_size+1)
    assert len(data)<=max_size,url
    return data

def data_json(url):
    return json.loads(fetch(url,4*1024*1024))

def safe_name(s):
    assert s and not s.startswith("/") and "\\" not in s and s==PurePosixPath(s).as_posix()
    assert all(p not in ("",".","..",".git") and not p.endswith((" ",".")) and
               not re.search(r'[<>:"|?*\x00-\x1f]',p) and
               not re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?",p)
               for p in s.split("/")),s

def registry_public_key(key):
    """npm registry keyids fingerprint the SSH wire blob, not SPKI DER."""
    assert key["keytype"]==key["scheme"]=="ecdsa-sha2-nistp256"
    der=base64.b64decode(key["key"],validate=True)
    public=serialization.load_der_public_key(der)
    assert isinstance(public,ec.EllipticCurvePublicKey) and isinstance(public.curve,ec.SECP256R1)
    kind,encoded=public.public_bytes(serialization.Encoding.OpenSSH,
                                    serialization.PublicFormat.OpenSSH).split()
    assert kind==b"ecdsa-sha2-nistp256"
    wire=base64.b64decode(encoded,validate=True)
    fingerprint="SHA256:"+base64.b64encode(hashlib.sha256(wire).digest()).decode().rstrip("=")
    assert key["keyid"]==fingerprint,("npm registry public key fingerprint mismatch",key["keyid"])
    return public

def npm_payload(name,keys):
    meta=data_json(REG+name+"/"+PW)
    assert meta["name"]==name and meta["version"]==PW and meta["license"]=="Apache-2.0"
    assert not meta.get("deprecated")
    if meta.get("gitHead"):
        assert meta["gitHead"]==PW_TAG,(name,meta["gitHead"])
    assert meta.get("dependencies",{})==({"playwright-core":PW} if name=="playwright" else {})
    assert not meta.get("optionalDependencies") and not meta.get("peerDependencies")
    dist=meta["dist"]
    url=REG+name+"/-/"+name+"-"+PW+".tgz"
    assert dist["tarball"]==url
    integrity=dist["integrity"]
    assert integrity.startswith("sha512-")
    signatures=dist.get("signatures",[])
    verified=[]
    for sig in signatures:
        for key in keys:
            if key["keyid"]!=sig["keyid"]:continue
            public=registry_public_key(key)
            # The currently published stable artifacts must use an active
            # registry signing key. Do not accept expired historical keys.
            if key.get("expires") is not None:
                from datetime import datetime,timezone
                assert datetime.fromisoformat(key["expires"].replace("Z","+00:00"))>datetime.now(timezone.utc)
            public.verify(base64.b64decode(sig["sig"],validate=True),
                          (name+"@"+PW+":"+integrity).encode(),ec.ECDSA(hashes.SHA256()))
            verified.append(key["keyid"])
    assert verified,("no verified registry signature",name)
    raw=fetch(url,40*1024*1024)
    assert "sha512-"+base64.b64encode(hashlib.sha512(raw).digest()).decode()==integrity
    assert hashlib.sha1(raw).hexdigest()==dist["shasum"]
    payload={};seen=set();total=0
    with tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz") as archive:
        for member in archive:
            assert len(seen)<1500 and member.name.startswith("package/"),member.name
            rel=member.name[len("package/"):].rstrip("/")
            safe_name(rel);assert rel.casefold() not in seen,rel;seen.add(rel.casefold())
            assert member.isdir() or member.isfile(),rel
            if member.isdir():continue
            assert 0<=member.size<=64*1024*1024,rel
            total+=member.size;assert total<=160*1024*1024
            f=archive.extractfile(member);data=f.read();assert len(data)==member.size
            payload[rel]=sha(data)
    assert {"package.json","LICENSE","NOTICE","ThirdPartyNotices.txt"}<=set(payload),name
    proof={"version":PW,"url":url,"integrity":integrity,"sha256":sha(raw),"registrySignatureKeys":verified,
           "gitHead":meta.get("gitHead"),"tagCommit":PW_TAG}
    print("NPM_OFFICIAL_SIGNED_TARBALL="+json.dumps({"name":name,**proof}),flush=True)
    return payload,proof

def run(args,env=None,cwd=ROOT,timeout=900):
    result=subprocess.run([str(x) for x in args],cwd=cwd,env=env,capture_output=True,timeout=timeout)
    print(result.stdout.decode("utf-8","backslashreplace"),end="",flush=True)
    print(result.stderr.decode("utf-8","backslashreplace"),end="",flush=True)
    assert result.returncode==0,("failed",str(args[0]),result.returncode)
    return result.stdout.decode("utf-8","backslashreplace")

def write_json(path,value):
    path.write_bytes((json.dumps(value,ensure_ascii=True,indent=2)+"\n").encode())

def isolated(own):
    keys=("SystemRoot","WINDIR","SystemDrive","ComSpec","PATHEXT","OS","PROCESSOR_ARCHITECTURE")
    env={k:os.environ[k] for k in keys if k in os.environ}
    windows=Path(env["SystemRoot"])
    env["PATH"]=os.pathsep.join((str(NODE.parent),str(PY.parent),str(windows/"System32"),str(windows)))
    for k,name in (("HOME","home"),("USERPROFILE","home"),("APPDATA","appdata"),("LOCALAPPDATA","localappdata"),
        ("PROGRAMDATA","programdata"),("ALLUSERSPROFILE","programdata"),("PUBLIC","public"),("TEMP","temp"),("TMP","temp"),
        ("TMPDIR","temp"),("XDG_CONFIG_HOME","xdg-config"),("XDG_CACHE_HOME","xdg-cache"),("XDG_DATA_HOME","xdg-data"),
        ("XDG_STATE_HOME","xdg-state"),("NPM_CONFIG_CACHE","npm-cache"),("NPM_CONFIG_PREFIX","npm-prefix"),
        ("PLAYWRIGHT_BROWSERS_PATH","browser-cache")):
        p=own/name;p.mkdir(exist_ok=True);env[k]=str(p)
    for k in ["NPM_CONFIG_USERCONFIG","NPM_CONFIG_GLOBALCONFIG"]:
        p=own/(k.lower()+".npmrc");p.write_bytes(b"");env[k]=str(p)
    env.update(PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD="1",PIP_CONFIG_FILE=os.devnull,
               PSModuleAnalysisCachePath=str(own/"ModuleAnalysisCache"),POWERSHELL_TELEMETRY_OPTOUT="1")
    return env

def stage_node(own,env):
    keys=data_json(REG+"-/npm/v1/keys")["keys"]
    payloads={};proofs={}
    for name in ("playwright","playwright-core"):
        payloads[name],proofs[name]=npm_payload(name,keys)
    target=own/"playwright";target.mkdir()
    package=json.loads((AUTO/"playwright/package.json").read_bytes())
    package["dependencies"]={"playwright":PW}
    package["description"]="Pinned Microsoft Playwright with built-in MCP for explicit portable browser tasks"
    write_json(target/"package.json",package)
    common=["--ignore-scripts","--bin-links=false","--no-audit","--no-fund","--registry="+REG,"--omit=optional"]
    run([NODE,NPM,"install","--package-lock-only",*common],env,target)
    lock=json.loads((target/"package-lock.json").read_bytes())
    assert lock["lockfileVersion"]==3 and set(lock["packages"])=={"","node_modules/playwright","node_modules/playwright-core"}
    assert lock["packages"][""]["dependencies"]=={"playwright":PW}
    for name,proof in proofs.items():
        entry=lock["packages"]["node_modules/"+name]
        assert entry["version"]==PW and entry["resolved"]==proof["url"] and entry["integrity"]==proof["integrity"],name
    lock_bytes=(target/"package-lock.json").read_bytes()
    run([NODE,NPM,"ci",*common],env,target)
    assert (target/"package-lock.json").read_bytes()==lock_bytes
    mods=target/"node_modules"
    assert {x.name for x in mods.iterdir()}=={"playwright","playwright-core",".package-lock.json"}
    for name,payload in payloads.items():
        assert inventory(mods/name)==payload,("npm installed bytes differ from official tarball",name)
    default=json.loads((mods/"playwright-core/browsers.json").read_bytes())
    chromium=next(x for x in default["browsers"] if x["name"]=="chromium")
    assert chromium["revision"]=="1255" and chromium["browserVersion"]=="159.0.8154.6"
    manifest={"source":REG+"playwright","integrity_records":"playwright/package-lock.json",
              "installation":"npm ci --ignore-scripts --bin-links=false; official package payloads unmodified",
              "officialPackages":proofs,
              "files":{"tool/automation/playwright/"+p:h for p,h in sorted(inventory(target).items())}}
    print("STABLE_NPM_INSTALLED_OFFICIAL_BYTES=PASS",flush=True)
    return target,manifest

def stage_chrome(own,installer):
    metadata=data_json(CFT+"last-known-good-versions-with-downloads.json")
    stable=metadata["channels"]["Stable"]
    assert stable["version"]==CHROME and stable["revision"]==REV
    assert {x["url"] for x in stable["downloads"]["chrome"] if x["platform"]=="win64"}=={URL}
    specific=data_json(CFT+CHROME+".json")
    assert specific["version"]==CHROME and specific["revision"]==REV
    assert {x["url"] for x in specific["downloads"]["chrome"] if x["platform"]=="win64"}=={URL}
    archive=own/"chrome-win64.zip"
    md5=hashlib.md5(usedforsecurity=False);hash256=hashlib.sha256()
    with opener.open(urllib.request.Request(URL,headers={"User-Agent":"Portable-stable-audit/1"}),timeout=120) as res:
        assert res.url==URL
        size=int(res.headers["Content-Length"]);assert 0<size<=1024**3
        google_hash=dict(p.strip().split("=",1) for p in res.headers.get("x-goog-hash","").split(",") if "=" in p)
        assert google_hash.get("md5"),"official Google Storage MD5 not available"
        generation=res.headers.get("x-goog-generation");assert generation and generation.isdigit()
        count=0
        with archive.open("xb") as out:
            while chunk:=res.read(1024*1024):
                count+=len(chunk);assert count<=size
                md5.update(chunk);hash256.update(chunk);out.write(chunk)
    assert count==size and base64.b64encode(md5.digest()).decode()==google_hash["md5"]
    prefix="tool/automation/browsers/chromium-"+REV+"/"
    manifest={"schemaVersion":1,"browserVersion":CHROME,"revision":REV,"platform":"win32-x64",
        "archive":{"sourceUrl":URL,"resolvedUrl":URL,"sha256":hash256.hexdigest(),"size":size,
                   "googleMd5":google_hash["md5"],"googleGeneration":generation,"stableMetadataTimestamp":metadata["timestamp"]},
        "files":{}}
    total=0;seen=set()
    with zipfile.ZipFile(archive) as z:
        assert 0<len(z.infolist())<1500
        for member in z.infolist():
            installer.archive_name(member.filename)
            assert member.filename.casefold() not in seen and not member.is_dir() and not stat.S_ISLNK(member.external_attr>>16)
            seen.add(member.filename.casefold());total+=member.file_size;assert total<=1024**3
            with z.open(member) as f:h=hashlib.file_digest(f,"sha256").hexdigest()
            manifest["files"][prefix+member.filename]={"size":member.file_size,"sha256":h}
    manifest["fileCount"]=len(seen);manifest["uncompressedBytes"]=total
    target=own/("chromium-"+REV)
    target.mkdir()
    installer.extract_archive(ROOT,archive,target,manifest,prefix)
    exe=target/"chrome-win64/chrome.exe"
    assert exe.is_file()
    with exe.open("rb") as f:
        assert f.read(2)==b"MZ"
        f.seek(0x3c);f.seek(int.from_bytes(f.read(4),"little"));assert f.read(6)==b"PE\0\0\x64\x86"
    print("OFFICIAL_STABLE_CFT="+json.dumps({k:v for k,v in manifest.items() if k!="files"}),flush=True)
    return target,manifest

def replace(s,a,b):
    assert s.count(a)==1,("text anchor",a[:120])
    return s.replace(a,b,1)

def edit_bytes(path,edits):
    raw=path.read_bytes();text=raw.decode("utf-8")
    for a,b in edits:text=replace(text,a,b)
    return text.encode("utf-8")

def main():
    assert os.name=="nt" and sys.version_info[:3]==(3,14,10)
    assert Path(sys.executable).resolve()==PY and sys.flags.isolated and sys.flags.ignore_environment
    assert os.environ.get("GITHUB_ACTIONS")=="true" and os.environ.get("GITHUB_REPOSITORY")=="rileyaaa/Portable"
    assert os.environ.get("GITHUB_REF")=="refs/heads/dev/stable-tool-refresh"
    clean()
    for p in (*reversed(AUTO.parents),AUTO):plain(p,True)
    spec=importlib.util.spec_from_file_location("browser_installer",AUTO/"install-browser.py")
    installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
    old_versions=json.loads((AUTO/"versions.json").read_bytes())
    assert old_versions["playwrightMcp"]=="0.0.83" and old_versions["playwright"]=="1.64.0-alpha-1790635538000"
    old_browser,old_prefix=installer.load_manifest(ROOT);installer.verify_payload(ROOT,old_browser)
    assert old_browser["browserVersion"]=="155.0.8059.12" and old_browser["revision"]=="1247"
    old_deps=json.loads((AUTO/"dependency-manifest.json").read_bytes())["files"]
    assert {"tool/automation/playwright/"+p:h for p,h in inventory(AUTO/"playwright").items()}==old_deps
    assert paths("ls-files","-z","--","tool/automation/playwright")==set(old_deps)
    assert paths("ls-files","-z","--","tool/automation/browsers")==set(old_browser["files"])
    assert set(inventory(AUTO/"browsers"))=={p.removeprefix("tool/automation/browsers/") for p in old_browser["files"]}
    for p in old_deps: assert git("cat-file","blob","HEAD:"+p)==(ROOT/p).read_bytes(),p
    tmp=ROOT/"tmp";tmp.mkdir(exist_ok=True);plain(tmp,True)
    with tempfile.TemporaryDirectory(prefix="browser-stable-",dir=tmp) as d:
        own=Path(d);plain(own,True);env=isolated(own)
        new_node,dep_manifest=stage_node(own,env)
        new_chrome,manifest=stage_chrome(own,installer)
        work=own/"migration \u4fbf\u643a";work.mkdir()
        new_exe=new_chrome/"chrome-win64/chrome.exe"
        ps=Path(env["SystemRoot"])/"System32/WindowsPowerShell/v1.0/powershell.exe"
        command="$s=Get-AuthenticodeSignature -LiteralPath $env:PORTABLE_TEST_EXE; [pscustomobject]@{status=[string]$s.Status;subject=$s.SignerCertificate.Subject}|ConvertTo-Json -Compress"
        signature_env=env|{"PORTABLE_TEST_EXE":str(new_exe)}
        signature=json.loads(run([ps,"-NoProfile","-NonInteractive","-Command",command],signature_env))
        assert signature["status"]=="NotSigned" or (signature["status"]=="Valid" and "Google" in signature["subject"]),signature
        manifest["archive"]["chromeAuthenticode"]=signature
        output=run([NODE,ROOT/"tests/check_browser_stable_pair.js",AUTO/"playwright/node_modules",
                    new_node/"node_modules",AUTO/old_versions["browser"]["executable"],new_exe,work],env,timeout=240)
        assert "MCP_REAL_FILTERED_SCHEMA_COMPATIBILITY=PASS" in output and "REAL_CHROMIUM_OLD_TO_STABLE_PROFILE_COOKIE_STORAGE_CDP=PASS" in output
        versions=old_versions
        versions.update(checkedAt="2026-11-25",playwrightMcp=PW,playwright=PW,
                        mcpImplementation="playwright-core",source="https://github.com/microsoft/playwright")
        versions["browser"].update(version=CHROME,revision=REV,revisionSource="chrome-for-testing",channel="stable",
            executable=f"browsers/chromium-{REV}/chrome-win64/chrome.exe",downloadUrl=URL,
            driverDefaultVersion="159.0.8154.6",driverDefaultRevision="1255")
        changed={
            "tool/automation/versions.json":(json.dumps(versions,indent=2)+"\n").encode(),
            "tool/automation/dependency-manifest.json":(json.dumps(dep_manifest,indent=2)+"\n").encode(),
            "tool/automation/browser-manifest.json":(json.dumps(manifest,indent=2)+"\n").encode(),
        }
        changed["tool/automation/install-browser.py"]=edit_bytes(AUTO/"install-browser.py",[
            ('    if (archive["resolvedUrl"] != official or\n            archive["sourceUrl"] != f"https://cdn.playwright.dev/builds/cft/{version}/win64/chrome-win64.zip" or',
             '    source = f"https://cdn.playwright.dev/builds/cft/{version}/win64/chrome-win64.zip"\n'
             '    if browser.get("revisionSource") == "chrome-for-testing":\n'
             '        if browser.get("channel") != "stable" or browser.get("downloadUrl") != official:\n'
             '            raise ValueError("Invalid stable Chrome for Testing identity")\n'
             '        source = official\n'
             '    elif browser.get("revisionSource") is not None or browser.get("channel") is not None:\n'
             '        raise ValueError("Unknown browser revision source")\n'
             '    if (archive["resolvedUrl"] != official or\n            archive["sourceUrl"] != source or')])
        changed["tests/test_browser_install.py"]=edit_bytes(ROOT/"tests/test_browser_install.py",[
            ('self.assertEqual(prefix, "tool/automation/browsers/chromium-1247/")',f'self.assertEqual(prefix, "tool/automation/browsers/chromium-{REV}/")'),
            ('self.assertEqual(manifest["fileCount"], 305)',f'self.assertEqual(manifest["fileCount"], {manifest["fileCount"]})\n        self.assertEqual(manifest["browserVersion"], "{CHROME}")\n        self.assertEqual(manifest["archive"]["sourceUrl"], "{URL}")\n        self.assertEqual(manifest["archive"]["sha256"], "{manifest["archive"]["sha256"]}")')])
        changed["tests/test_automation.js"]=edit_bytes(ROOT/"tests/test_automation.js",[
            ("  assert.equal(lock.packages['node_modules/@playwright/mcp'].version, versions.playwrightMcp);",
             "  assert.equal(versions.mcpImplementation, 'playwright-core');\n"
             "  assert.equal(versions.playwrightMcp, versions.playwright);\n"
             "  assert.deepEqual(Object.keys(lock.packages).sort(), ['', 'node_modules/playwright', 'node_modules/playwright-core']);\n"
             "  assert.deepEqual(lock.packages[''].dependencies, {playwright:versions.playwright});\n"
             "  assert.equal(lock.packages['node_modules/playwright'].version, versions.playwright);")])
        # Update only current documentation, not historical release descriptions.
        readme=(ROOT/"README.md").read_text(encoding="utf-8")
        rows=readme.splitlines(keepends=True)
        oldrow=next(x for x in rows if x.startswith("| \u7f51\u9875\u8c03\u8bd5 |"))
        newrow=oldrow.replace("155.0.8059.12",CHROME).replace("\u7ea6 458 MB",f"\u7ea6 {round(manifest['uncompressedBytes']/1000000)} MB")
        assert newrow!=oldrow
        changed["README.md"]=edit_bytes(ROOT/"README.md",[(oldrow.rstrip("\r\n"),newrow.rstrip("\r\n"))])
        docpath=ROOT/TOOL_DOC;doc=docpath.read_text(encoding="utf-8")
        lines=doc.splitlines()
        oldrows=[x for x in lines if x.startswith("| Playwright \u6d4f\u89c8\u5668\u5de5\u5177 |") or x.startswith("| \u914d\u5957 Chromium |")]
        assert len(oldrows)==2
        newrows=[
            f"| Playwright / MCP | 已包含 Microsoft Playwright {PW}（内置 MCP，不再单独依赖 alpha 包），\x60tool\\automation\\playwright\x60 | [官方正式版本](https://github.com/microsoft/playwright/releases/tag/v{PW})；[版本](automation/versions.json)、[文件摘要](automation/dependency-manifest.json)；同一依赖供任务脚本和可选 MCP 使用 |",
            f"| 配套 Chromium | Chrome for Testing Stable {CHROME} / r{REV}，Windows x64，约 {round(manifest['uncompressedBytes']/1000000)} MB | 官方 Stable 通道，经 Playwright {PW} 实际兼容验收；[来源与摘要](automation/browser-manifest.json)，只装一份，不装 ChromeDriver、不回退宿主 |"]
        changed[TOOL_DOC]=edit_bytes(docpath,list(zip(oldrows,newrows)))
        skill="home/skills/browser-debug/SKILL.md"
        changed[skill]=edit_bytes(ROOT/skill,[
            ("\u9ed8\u8ba4\u4f7f\u7528\u4f9d\u8d56\u6307\u5b9a\u7684\u5b8c\u6574\u6d4f\u89c8\u5668\u7248\u672c\uff0c\u5171\u540c\u66f4\u65b0\u5e76\u6d4b\u8bd5",
             "\u9ed8\u8ba4\u4f7f\u7528 versions.json \u56fa\u5b9a\u4e14\u5b9e\u9645\u9a8c\u8bc1\u7684\u6b63\u5f0f\u6d4f\u89c8\u5668\u7ec4\u5408\uff0c\u5171\u540c\u66f4\u65b0\u5e76\u6d4b\u8bd5")])
        runurl="https://github.com/rileyaaa/Portable/actions/runs/"+os.environ["GITHUB_RUN_ID"]
        note=("\n## 2026-11-25: stable browser/MCP pair\n\n"
              f"Playwright {PW} (built-in MCP) + Chrome for Testing Stable {CHROME}, r{REV}. "
              "No standalone alpha package, additional browser, driver, automatic registration or permission expansion. "
              "Official npm registry signatures, SHA-512/tarball bytes, old Git/dependency inventory, Google Stable metadata, "
              "Google object MD5/generation, pinned archive SHA-256 and extracted inventory verified. "
              f"Archive SHA-256: {manifest['archive']['sha256']}. Exact filtered tool list/compatible schema and real old-to-new synthetic profile Cookie/localStorage/CDP passed. "
              "Default Playwright Chromium 159 is not used because it is not the stable Chrome channel. "
              "Existing release workflow remains frozen; only development input validation, not a release. "
              "No real user profile/account, external website, device, Office render or recalculation tested. Run: "+runurl+"\n")
        changed["DEVELOPMENT.md"]=(ROOT/"DEVELOPMENT.md").read_bytes()+note.encode()
        backup=own/"backup";backup.mkdir()
        old_paths=[AUTO/"playwright",AUTO/"browsers/chromium-1247"]
        new_paths=[AUTO/"playwright",AUTO/("browsers/chromium-"+REV)]
        assert not new_paths[1].exists()
        originals={name:(ROOT/name).read_bytes() for name in changed}
        moved_old=[];moved_new=[]
        try:
            for i,p in enumerate(old_paths):p.rename(backup/str(i));moved_old.append((p,backup/str(i)))
            for target,source in zip(new_paths,[new_node,new_chrome]):
                source.rename(target);moved_new.append((target,source))
            for p,raw in changed.items():(ROOT/p).write_bytes(raw)
            run([PY,"-B","tool/automation/install-browser.py","--check"],timeout=120)
            run([NODE,"--test","tests/test_automation.js"],timeout=180)
            run([PY,"-B","-m","unittest","discover","-s","tests","-p","test_browser_install.py","-v"],timeout=180)
            run([PY,"-B","tests/check_browser_mcp_stdio.py"],timeout=360)
            # Run the real consumer gates before committing the browser group.
            # Failure restores only this group's files; the Python groups stay.
            run([ps,"-NoProfile","-ExecutionPolicy","Bypass","-File",ROOT/"tests/test_browser_smoke.ps1"],timeout=900)
            run([PY,"-B","tests/check_codex_tool_discovery.py","browser"],timeout=1200)
            run([PY,"-B","tests/check_codex_browser_mcp.py"],timeout=1200)
            expected=set(old_deps)|set(dep_manifest["files"])|set(old_browser["files"])|set(manifest["files"])|set(changed)
            actual=paths("diff","HEAD","--no-renames","--name-only","-z")|paths("ls-files","--others","--exclude-standard","-z")
            assert actual<=expected and (set(old_deps)^set(dep_manifest["files"])|set(old_browser["files"])|set(manifest["files"]))<=actual
            all_paths=sorted(actual)
            for i in range(0,len(all_paths),40):git("add","-A","--",*all_paths[i:i+40])
            assert paths("diff","--cached","--no-renames","--name-only","-z")==actual
            assert not git("diff","--name-only","-z") and not paths("ls-files","--others","--exclude-standard","-z")
            git("-c","user.name=github-actions[bot]","-c","user.email=41898282+github-actions[bot]@users.noreply.github.com",
                "commit","-m","Refresh verified stable Playwright and Chrome for Testing pair")
            clean()
            print("BROWSER_STABLE_STAGE_PASS="+git("rev-parse","HEAD").decode().strip(),flush=True)
        except BaseException:
            # Scope is this disposable checkout only. Restore the prior
            # tracked index and the exact directories/files moved above.
            for p,source in reversed(moved_new):p.rename(source)
            for p,source in reversed(moved_old):source.rename(p)
            for p,raw in originals.items():(ROOT/p).write_bytes(raw)
            git("restore","--staged","--source=HEAD","--","tool/automation/playwright","tool/automation/browsers",*changed)
            clean()
            raise

if __name__=="__main__":
    for stream in (sys.stdout,sys.stderr):stream.reconfigure(encoding="utf-8",errors="backslashreplace")
    main()
