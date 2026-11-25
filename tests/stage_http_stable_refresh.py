import base64, csv, email.parser, hashlib, importlib.metadata as md, io, json, os, re, shutil, stat, subprocess, sys, tempfile, zipfile
from pathlib import Path
import urllib.parse, urllib.request
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
for stream in (sys.stdout,sys.stderr): stream.reconfigure(encoding="utf-8",errors="backslashreplace")
assert os.environ.get("GITHUB_ACTIONS")=="true" and os.environ.get("GITHUB_REPOSITORY")=="rileyaaa/Portable" and os.environ.get("GITHUB_REF")=="refs/heads/dev/stable-tool-refresh"
root=Path.cwd()
py=root/"tool/python/python.exe"
site=root/"tool/python/Lib/site-packages"
prefix=site.relative_to(root).as_posix()+"/"
specs={
    "urllib3":("2.7.0","2.8.0","9fb4c81ebbb1ce9531cce37674bbc6f1360472bc18ca9a553ede278ef7276897","0cf3cae568d36aa9576b28dfb35f11328f1cb974ca7647d9475ebb86c75ac6e3"),
    "anyio":("4.13.0","4.16.0","08b310f9e24a9594186fd75b4f73f4a4152069e3853f1ed8bfbf58369f4ad708","c66ae634e0b8228396b801741beb3294326d4b6102f7bba4041c0dfb58c29026"),
}
assert len(sys.argv)==2 and sys.argv[1] in specs
specs={sys.argv[1]:specs[sys.argv[1]]}
def sha(data): return hashlib.sha256(data).hexdigest()
def rh(data): return "sha256="+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
def norm(name): return re.sub(r"[-_.]+","-",name.lower())
def git(*args): return subprocess.check_output(["git",*map(str,args)],cwd=root)
def names(*args): return set(git(*args).decode("utf-8").split("\0"))-{""}
def plain(path, directory=False):
    s=path.lstat()
    assert not stat.S_ISLNK(s.st_mode) and not getattr(s,"st_file_attributes",0)&0x400,str(path)
    assert stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode) and s.st_nlink==1,str(path)
def files(parent, top):
    p=parent/top
    plain(p,True)
    result=set()
    for current,dirs,leaves in os.walk(p,followlinks=False):
        d=Path(current)
        for child in dirs: plain(d/child,True)
        for child in leaves:
            f=d/child;plain(f)
            result.add(f.relative_to(parent).as_posix())
    return result
def records(raw):
    r={}
    for row in csv.reader(io.StringIO(raw.decode("utf-8-sig"),newline="")):
        assert len(row)==3 and row[0] not in r
        r[row[0]]=tuple(row[1:])
    return r
def dist(name,v): return name+"-"+v+".dist-info"
def check_record(parent,d,owned):
    rec=d+"/RECORD"
    r=records((parent/rec).read_bytes())
    assert set(r)==owned,("record ownership differs",d,sorted(set(r)^owned))
    for path in owned:
        f=parent/path;plain(f)
        assert r[path]==(("", "") if path==rec else (rh(f.read_bytes()),str(f.stat().st_size))),path
def distributions():
    found={}
    for d in md.distributions(path=[str(site)]):
        n=norm(d.metadata["Name"]);assert n not in found
        found[n]=d.version
    return found
def fetch_wheel(name,v,expected,wheelhouse,installed):
    filename=name+"-"+v+"-py3-none-any.whl"
    request=urllib.request.Request("https://pypi.org/pypi/"+name+"/"+v+"/json",headers={"User-Agent":"Portable-fixed-wheel-audit/1","Accept":"application/json"})
    with urllib.request.urlopen(request,timeout=40) as res:
        assert urllib.parse.urlsplit(res.url).hostname=="pypi.org"
        release=json.load(res)
    assert norm(release["info"]["name"])==name and release["info"]["version"]==v
    items=[x for x in release["urls"] if x["filename"]==filename]
    assert len(items)==1
    item=items[0]
    assert item["packagetype"]=="bdist_wheel" and not item["yanked"] and item["digests"]["sha256"]==expected and 0<item["size"]<2*1024*1024
    u=urllib.parse.urlsplit(item["url"])
    assert u.scheme=="https" and u.hostname=="files.pythonhosted.org" and u.username is None and u.password is None and u.path.endswith("/"+filename)
    with urllib.request.urlopen(item["url"],timeout=60) as res:
        assert urllib.parse.urlsplit(res.url).hostname=="files.pythonhosted.org"
        data=res.read(item["size"]+1)
    assert len(data)==item["size"] and sha(data)==expected
    with (wheelhouse/filename).open("xb") as f: f.write(data)
    d=dist(name,v);payload={};seen=set()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert len(z.infolist())<1000
        for m in z.infolist():
            p=m.filename.rstrip("/")
            parts=p.split("/")
            assert p and parts[0] in (name,d) and all(part and part not in (".","..",".git") and not part.endswith((" ",".")) and not re.search(r'[<>:"\\|?*\x00-\x1f]',part) and not re.fullmatch(r"(?i)(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?",part) for part in parts),p
            assert p.casefold() not in seen and not stat.S_ISLNK(m.external_attr>>16) and not(m.flag_bits&1) and m.file_size<2*1024*1024,p
            seen.add(p.casefold())
            if m.is_dir(): continue
            if parts[0]==name:
                worker = name=="urllib3" and p=="urllib3/contrib/emscripten/emscripten_fetch_worker.js"
                assert (worker or p.endswith((".py",".pyi","/py.typed"))) and "__pycache__" not in parts,p
                if worker:
                    # Identical blob in both official 2.7.0/2.8.0 tags and the existing vendor tree.
                    raw=z.read(m)
                    assert hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()=="faf141e1fa4113a0c14480d1681ddecb9678ced4",p
            else:
                assert "/".join(parts[1:]) in {"METADATA","WHEEL","RECORD","entry_points.txt","top_level.txt","licenses/LICENSE","licenses/LICENSE.txt"},p
            payload[p]=z.read(m)
    rr=records(payload[d+"/RECORD"])
    assert set(rr)==set(payload)
    for p,b in payload.items(): assert rr[p]==(("", "") if p==d+"/RECORD" else (rh(b),str(len(b)))),p
    meta=email.parser.BytesParser().parsebytes(payload[d+"/METADATA"])
    assert norm(meta["Name"])==name and meta["Version"]==v and meta["License-Expression"]=="MIT"
    assert SpecifierSet(meta["Requires-Python"]).contains("3.14.10")
    active={}
    for raw in meta.get_all("Requires-Dist",[]):
        req=Requirement(raw)
        if req.marker is not None and not req.marker.evaluate({"extra":""}): continue
        n=norm(req.name)
        assert n in installed and req.specifier.contains(installed[n]),(name,raw)
        active[n]=raw
    wheel=email.parser.BytesParser().parsebytes(payload[d+"/WHEEL"])
    assert wheel["Root-Is-Purelib"].lower()=="true" and wheel.get_all("Tag")==["py3-none-any"]
    print("HTTP_OFFICIAL_WHEEL="+json.dumps({"name":name,"version":v,"sha256":expected,"url":item["url"],"files":len(payload),"active_requirements":active},ensure_ascii=True),flush=True)
    return payload,active
def run(argv,env,cwd=root,timeout=240):
    p=subprocess.run([str(x) for x in argv],cwd=cwd,env=env,capture_output=True,timeout=timeout)
    out=p.stdout.decode("utf-8","backslashreplace")
    print(out,flush=True);print(p.stderr.decode("utf-8","backslashreplace"),flush=True)
    assert p.returncode==0,"Process failed: "+str(argv[0])+" exit="+str(p.returncode)
    return out
assert sys.version_info[:3]==(3,14,10) and Path(sys.executable).resolve()==py
assert sys.flags.isolated and sys.flags.ignore_environment and sys.flags.safe_path
assert not git("status","--porcelain=v1","--untracked-files=all")
for p in (*reversed(site.parents),site):plain(p,True)
old_versions=distributions()
assert len(old_versions)==49 and old_versions["pip"]=="26.1.2" and old_versions["certifi"]=="2026.5.20" and old_versions["typing-extensions"]=="4.16.0"
assert all(old_versions[n]==v[0] for n,v in specs.items())
new_versions=old_versions|{n:v[1] for n,v in specs.items()}
scratch=root/"tmp";scratch.mkdir(exist_ok=True);plain(scratch,True)
test=root/"tests/check_http_stable_refresh.py"
assert test.is_file()
allowed=set();required=set();all_old=set();all_new=set()
with tempfile.TemporaryDirectory(prefix="http-refresh-",dir=scratch) as tmp:
    own=Path(tmp);plain(own,True)
    env={k:os.environ[k] for k in ("SystemRoot","WINDIR","SystemDrive","ComSpec","PATHEXT","OS","PROCESSOR_ARCHITECTURE") if k in os.environ}
    windows=Path(env["SystemRoot"])
    env["PATH"]=os.pathsep.join((str(py.parent),str(root/"tool/bin"),str(windows/"System32"),str(windows)))
    for key,rel in (("HOME","home"),("USERPROFILE","home"),("APPDATA","appdata"),("LOCALAPPDATA","localappdata"),("PROGRAMDATA","programdata"),("ALLUSERSPROFILE","programdata"),("TEMP","temp"),("TMP","temp"),("TMPDIR","temp"),("PIP_CACHE_DIR","pip-cache"),("PYTHONUSERBASE","python-user"),("PYTHONPYCACHEPREFIX","pycache")):
        p=own/rel;p.mkdir(exist_ok=True);env[key]=str(p)
    env.update(PIP_CONFIG_FILE=os.devnull,PSModuleAnalysisCachePath=str(own/"ModuleAnalysisCache"),POWERSHELL_TELEMETRY_OPTOUT="1")
    def pip(*args):
        return run([py,"-B","-m","pip","--isolated","--disable-pip-version-check","--no-input","--cache-dir",env["PIP_CACHE_DIR"],*args],env)
    def consumer(uv,av):
        assert "HTTP_STABLE_LOOPBACK_PROXY_STREAM_ASYNC=PASS" in run([py,"-B",test,uv,av],env)
        out=run([py,"-B",root/"tests/check_typing_extensions_refresh.py","4.16.0"],env)
        assert "EXISTING_HTTP_SYNC_ASYNC_LOOPBACK=PASS" in out and "EXISTING_OFFICE_ROUNDTRIP=PASS" in out
    assert "No broken requirements found." in pip("check")
    consumer(old_versions["urllib3"],old_versions["anyio"])
    wheelhouse=own/"wheelhouse";wheelhouse.mkdir()
    plans=[]
    for n,(old,new,oldsha,newsha) in specs.items():
        od,nd=dist(n,old),dist(n,new)
        assert not os.path.lexists(site/nd)
        old_payload,old_deps=fetch_wheel(n,old,oldsha,wheelhouse,old_versions)
        new_payload,new_deps=fetch_wheel(n,new,newsha,wheelhouse,new_versions)
        if n=="anyio":
            assert old_deps=={"idna":"idna>=2.8"}
            assert new_deps=={"idna":"idna>=2.8","typing-extensions":'typing_extensions>=4.16.0; python_version < "3.15"'}
            assert old_versions["typing-extensions"]==new_versions["typing-extensions"]=="4.16.0"
        else:
            assert old_deps==new_deps=={},("default dependency change",n,old_deps,new_deps)
        old_meta={p.split("/",1)[1]:b for p,b in old_payload.items() if p.startswith(od+"/")}
        new_meta={p.split("/",1)[1]:b for p,b in new_payload.items() if p.startswith(nd+"/")}
        assert {p:b for p,b in old_meta.items() if p.startswith("licenses/")}=={p:b for p,b in new_meta.items() if p.startswith("licenses/")},("license change needs review",n)
        assert old_meta.get("entry_points.txt")==new_meta.get("entry_points.txt"),("entry point change needs review",n)
        owned_old=files(site,n)|files(site,od)
        expected_old=set(old_payload)|{od+"/INSTALLER",od+"/REQUESTED"}
        assert owned_old==expected_old,("old wheel inventory differs",n,sorted(owned_old^expected_old))
        assert names("ls-files","-z","--",prefix+n,prefix+od)=={prefix+p for p in owned_old}
        check_record(site,od,owned_old)
        for p in owned_old:
            assert git("cat-file","blob","HEAD:"+prefix+p)==(site/p).read_bytes(),p
        for p,b in old_payload.items():
            if p!=od+"/RECORD": assert (site/p).read_bytes()==b,("old vendor byte mismatch",p)
        for p in site.glob("*.dist-info/RECORD"):
            plain(p.parent,True);plain(p)
            if p.parent.name!=od: assert not(set(records(p.read_bytes()))&owned_old),("shared ownership",p.name)
        assert (site/od/"INSTALLER").read_bytes()==b"uv" and (site/od/"REQUESTED").read_bytes()==b""
        print("HTTP_OLD_WHEEL_GIT_RECORD=PASS "+n+" files="+str(len(owned_old)),flush=True)
        target=own/("stage-"+n);target.mkdir()
        req=own/(n+".lock");req.write_text(n+"=="+new+" --hash=sha256:"+newsha+"\n",encoding="ascii",newline="\n")
        pip("install","--no-index","--find-links",wheelhouse,"--no-deps","--require-hashes","--only-binary=:all:","--no-compile","--ignore-installed","--requirement",req,"--target",target)
        assert {p.name for p in target.iterdir()}=={n,nd}
        owned_new=files(target,n)|files(target,nd)
        assert owned_new==set(new_payload)|{nd+"/INSTALLER",nd+"/REQUESTED"}
        check_record(target,nd,owned_new)
        for p,b in new_payload.items():
            if p!=nd+"/RECORD": assert (target/p).read_bytes()==b,p
        assert (target/nd/"INSTALLER").read_bytes().strip()==b"pip" and (target/nd/"REQUESTED").read_bytes()==b""
        all_old.update(prefix+p for p in owned_old);all_new.update(prefix+p for p in owned_new)
        plans.append((n,od,nd,target,owned_new))
        print("HTTP_NEW_STAGED_WHEEL_RECORD=PASS "+n+" files="+str(len(owned_new)),flush=True)
    # All candidates are verified before either replaces its owned tree.
    backup=own/"old";backup.mkdir()
    for n,od,nd,target,owned_new in plans:
        for p in (n,od):(site/p).rename(backup/p)
        for p in (n,nd):(target/p).rename(site/p)
        check_record(site,nd,owned_new)
    assert distributions()==new_versions
    assert "No broken requirements found." in pip("check")
    consumer(new_versions["urllib3"],new_versions["anyio"])
    print("ONLY_ONE_OF_49_DISTRIBUTIONS_CHANGED=PASS",flush=True)
inp=root/"tool/python-packages.in.txt";lockpath=root/"tool/python-packages.lock.txt"
raw=inp.read_bytes();new_input=raw;lock=lockpath.read_bytes()
def once(data,a,b):
    assert data.count(a)==1,a
    return data.replace(a,b,1)
for n,(old,new,oldsha,newsha) in specs.items():
    new_input=once(new_input,(n+"=="+old).encode(),(n+"=="+new).encode())
    lock=once(lock,(n+"=="+old+" --hash=sha256:"+oldsha).encode(),(n+"=="+new+" --hash=sha256:"+newsha).encode())
lock=once(lock,b"# requirements-sha256: "+sha(raw).encode(),b"# requirements-sha256: "+sha(new_input).encode())
inp.write_bytes(new_input);lockpath.write_bytes(lock)
fixed={"tool/python-packages.in.txt","tool/python-packages.lock.txt"}
allowed=all_old|all_new|fixed
required=(all_old^all_new)|fixed
changed=names("diff","--no-renames","--name-only","-z")|names("ls-files","--others","--exclude-standard","-z")
assert required<=changed<=allowed,("candidate scope",sorted(required-changed),sorted(changed-allowed))
print("HTTP_STABLE_SCOPE_READY=PASS files="+str(len(changed)),flush=True)
