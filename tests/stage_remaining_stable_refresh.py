"""Developer-only one-time Windows CI: audited remaining stable parser/text wheels.

Each group has an independent exact official artifact, RECORD, upstream source
and license gate, dependency/launcher closure, real relocated Windows consumer
checks, normal Git delivery and readback. No customer install or full-suite rerun.
"""
import base64
import configparser
import csv
import email.parser
import hashlib
import importlib.metadata as md
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.parse
import urllib.request
import zipfile
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import sys_tags
from packaging.version import Version
from packaging.utils import parse_wheel_filename

for stream in (sys.stdout,sys.stderr):
    stream.reconfigure(encoding="utf-8",errors="backslashreplace")

ROOT=Path.cwd()
PY=ROOT/"tool/python/python.exe"
SITE=ROOT/"tool/python/Lib/site-packages"
PREFIX=SITE.relative_to(ROOT).as_posix()+"/"
BRANCH="refs/heads/dev/stable-tool-refresh"
FROZEN="4fb0b50228057cd0be41fbb191e15e065e64e368"
BASE="fbc3b63c73cb507455f78c2315ebb5a4604d9a58"
BOT=["-c","user.name=github-actions[bot]","-c","user.email=41898282+github-actions[bot]@users.noreply.github.com"]
HELPER="tests/stage_remaining_stable_refresh.py"
WORKFLOW=".github/workflows/refresh-remaining-stable.yml"
TEST="tests/check_remaining_stable_refresh.py"
BUILD_MANIFEST="tool/python-build-manifest.json"
BUILD_TEST="tests/test_python_runtime_dependencies.py"
IN="tool/python-packages.in.txt"
LOCK="tool/python-packages.lock.txt"
DOC="tool/\u5de5\u5177\u66f4\u65b0\u8bf4\u660e.md"
STATE=Path(os.environ["RUNNER_TEMP"])/("portable-remaining-stable-"+os.environ["GITHUB_RUN_ID"]+".json")
SPECS=json.loads(r'''{
  "lxml": {
    "roots": [
      "lxml"
    ],
    "vendor": null,
    "pure": false,
    "license": [
      "BSD-3-Clause"
    ],
    "tag": "lxml/lxml@lxml-6.1.3",
    "source": {
      "lxml/__init__.py": "a739f86ef95ca249d84de4735312b48c611b6e0d",
      "lxml/parser.pxi": "af9bd4fc34acabaf7f5a13e5d492d847563c8fed"
    },
    "licenses": {
      "LICENSE.txt": "0bdf03913ffdfd09be5a524c9303bd54a132d450",
      "LICENSES.txt": "fa56d69c930f414ac6d01a4a65c4e20e2d8540ab"
    },
    "old": "6.1.1",
    "new": "6.1.3",
    "wheel": "lxml-6.1.3-cp314-cp314-win_amd64.whl",
    "sha": "66299564c046bc7e0cc5de5106601eae907e9fa5904cd68a323380a8502f7861",
    "url": "https://files.pythonhosted.org/packages/0f/bc/5811cc73cac05e324e05ba9b0924e1a163a317a167ede8a9c748b11db30a/lxml-6.1.3-cp314-cp314-win_amd64.whl",
    "oldsha": "b2d444f2e66624d68e9c6b211e28a76e22fff5fcabcfff4deac18b529b7d4137"
  },
  "pyyaml": {
    "roots": [
      "yaml",
      "_yaml"
    ],
    "vendor": null,
    "pure": false,
    "license": [
      "MIT"
    ],
    "tag": "yaml/pyyaml@6.0.4",
    "source": {
      "yaml/__init__.py": "7e211a83f4d1356d326bc7e3192322848a70b9f6",
      "yaml/constructor.py": "97aa7b551f24c680b785aedb80474909f1e32736"
    },
    "licenses": {
      "LICENSE": "2f1b8e15e5627d92f0521605c9870bc8e5505cb4"
    },
    "old": "6.0.3",
    "new": "6.0.4",
    "wheel": "pyyaml-6.0.4-cp314-cp314-win_amd64.whl",
    "sha": "1d2f08c122727c86f8303bb1dd45159ca1de1f2d68798e671ec46974e321008e",
    "url": "https://files.pythonhosted.org/packages/b4/b5/e5cf6ca786f8a5b9bd91e01fe8f2113300bc5628fcfdd3ca02d271970824/pyyaml-6.0.4-cp314-cp314-win_amd64.whl",
    "oldsha": "4a2e8cebe2ff6ab7d1050ecd59c25d4c8bd7e6f400f5f82b96557ac0abafd0ac"
  },
  "markdown-it-py": {
    "roots": [
      "markdown_it"
    ],
    "vendor": "bin/markdown-it.exe",
    "vendor_sha": "355a5371fdf3e307149ce11690f66cfbea1c1b7c",
    "pure": true,
    "license": [
      null,
      "MIT"
    ],
    "tag": "executablebooks/markdown-it-py@v4.3.0",
    "source": {
      "markdown_it/__init__.py": "19ed2aa99c6f0818b42aed21b1c6ee2895f4eb75",
      "markdown_it/main.py": "33088ef5ffec5ceb1774f97df1dfb4de12ca3fce"
    },
    "licenses": {
      "LICENSE": "582ddf59e08277fe6e78cee924d2c84805fe36fe",
      "LICENSE.markdown-it": "7ffa058cb78f8fb9beb974d9fd429004d2d2e585"
    },
    "old": "4.2.0",
    "new": "4.3.0",
    "wheel": "markdown_it_py-4.3.0-py3-none-any.whl",
    "sha": "7aa1511a46c39138de78d9eba92ce47e63124d8003fc98b3a351909e04239efa",
    "url": "https://files.pythonhosted.org/packages/c9/31/5f0ac2f1a1c67423c995c731a11cd4ad05d081a2be969d74f868bdb9cc70/markdown_it_py-4.3.0-py3-none-any.whl",
    "oldsha": "9f7ebbcd14fe59494226453aed97c1070d83f8d24b6fc3a3bcf9a38092641c4a"
  },
  "charset-normalizer": {
    "roots": [
      "charset_normalizer"
    ],
    "vendor": "bin/normalizer.exe",
    "vendor_sha": "f960d15224e6c1b2c4fbcba861e3eb2e23370ab6",
    "pure": false,
    "license": [
      "MIT"
    ],
    "tag": "jawah/charset_normalizer@0b45fe26ec06006533c4b038fe239a01957e9d71",
    "source": {
      "charset_normalizer/__init__.py": "d8c1cd362c891252985df57ec84597a1ab1f5408",
      "charset_normalizer/version.py": "cf3a596dafacadfcd72e89642ed31a061bff9198"
    },
    "licenses": {
      "LICENSE": "9725772c7967075d97dc78d60f3735435eccba63"
    },
    "old": "3.4.7",
    "new": "3.5.3",
    "wheel": "charset_normalizer-3.5.3-cp314-cp314-win_amd64.whl",
    "sha": "b66a0e045cf859d7418f26a554509b65f21ebb6d90a95152460781939e8264f4",
    "url": "https://files.pythonhosted.org/packages/a0/4e/0d31216be12c3146dd282b043957805d4dda8806cd7b99c90273d251f0f2/charset_normalizer-3.5.3-cp314-cp314-win_amd64.whl",
    "oldsha": "92a0a01ead5e668468e952e4238cccd7c537364eb7d851ab144ab6627dbbe12f"
  },
  "pygments": {
    "roots": [
      "pygments"
    ],
    "vendor": "bin/pygmentize.exe",
    "vendor_sha": "a22012c106e6db51b4e58bc10cc2717f07755ce4",
    "pure": true,
    "license": [
      "BSD-2-Clause"
    ],
    "tag": "pygments/pygments@2.21.0",
    "source": {
      "pygments/__init__.py": "1d41b0a400d23fa0216c17e45de2a3de0c9f8e12"
    },
    "licenses": {
      "LICENSE": "446a1a805c8a949579fb8a9799f2bec7777349dc",
      "AUTHORS": "4794e296f491b1f4b59244eaff5251c07e01a817"
    },
    "old": "2.20.0",
    "new": "2.21.0",
    "wheel": "pygments-2.21.0-py3-none-any.whl",
    "sha": "2363c69b61c4a97c838da3b130dcd6468f4848992b21a82f2a63ec34377137d9",
    "url": "https://files.pythonhosted.org/packages/71/46/17f022dd3e953bf20a04a028a21ec746d942f8d2af30fa0f124fa0e6a684/pygments-2.21.0-py3-none-any.whl",
    "oldsha": "81a9e26dd42fd28a23a2d169d86d7ac03b46e2f8b59ed4698fb4785f946d0176"
  }
}''')
GROUPS={n:(n,) for n in SPECS}
def git(*args):
    return subprocess.check_output(["git",*map(str,args)],cwd=ROOT)
def rev(ref="HEAD"):
    return git("rev-parse",ref).decode().strip()
def names(*args):
    return set(git(*args).decode("utf-8").split("\0"))-{""}
def clean():
    assert not git("status","--porcelain=v1","--untracked-files=all"),"dirty checkout"
def sha(b):return hashlib.sha256(b).hexdigest()
def rh(b):return "sha256="+base64.urlsafe_b64encode(hashlib.sha256(b).digest()).decode().rstrip("=")
def blob(b):return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
def source_blob(raw,expected,path):
    assert expected in {blob(raw),blob(raw.replace(b"\r\n",b"\n"))},("upstream source mismatch",path,expected,blob(raw))
def norm(s):return re.sub(r"[-_.]+","-",s.lower())
def dist(name,ver):return name.replace("-","_")+"-"+ver+".dist-info"
def plain(p,directory=False):
    s=p.lstat()
    assert not stat.S_ISLNK(s.st_mode) and not getattr(s,"st_file_attributes",0)&0x400,str(p)
    assert stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode) and s.st_nlink==1,str(p)
def pathsafe(p):
    assert p and all(x and x not in (".","..",".git") and not x.endswith((" ","."))
        and not re.search(r'[<>:"\\|?*\x00-\x1f]',x)
        and not re.fullmatch(r"(?i)(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?",x)
        for x in p.split("/")),p
    return p
def files(parent,top):
    p=parent/top;plain(p,True)
    result=set()
    for current,dirs,leaves in os.walk(p,followlinks=False):
        for d in dirs:plain(Path(current)/d,True)
        for f in leaves:
            item=Path(current)/f;plain(item)
            result.add(item.relative_to(parent).as_posix())
    return result
def records(raw):
    out={}
    for row in csv.reader(io.StringIO(raw.decode("utf-8-sig"),newline="")):
        assert len(row)==3 and row[0] not in out
        out[row[0]]=tuple(row[1:])
    return out
def write_record(target,distinfo,paths):
    rec=distinfo+"/RECORD"
    with (target/rec).open("w",encoding="utf-8",newline="") as f:
        writer=csv.writer(f,lineterminator="\n")
        for p in sorted(paths):
            raw=(target/p).read_bytes() if p!=rec else b""
            writer.writerow((p,*((rh(raw),str(len(raw))) if p!=rec else ("",""))))
def check_record(target,di,paths,absent=()):
    rec=di+"/RECORD";rr=records((target/rec).read_bytes())
    assert set(rr)==paths|set(absent),("installed RECORD paths",di,sorted(set(rr)^(paths|set(absent))))
    for p in rr:pathsafe(p)
    for p in absent:assert not (target/p).exists(),p
    for p in paths:
        plain(target/p);raw=(target/p).read_bytes()
        assert rr[p]==(("","") if p==rec else (rh(raw),str(len(raw)))),("installed RECORD digest",p)
def versions():
    found={}
    for d in md.distributions(path=[str(SITE)]):
        k=norm(d.metadata["Name"]);assert k not in found
        found[k]=d.version
    assert len(found)==49
    return found
def entries(raw):
    if raw is None:return {}
    p=configparser.ConfigParser(interpolation=None,strict=True)
    p.optionxform=str;p.read_string(raw.decode("utf-8-sig"));assert not p.defaults()
    return {section:dict(p[section]) for section in p.sections()}
def fetch(url,host,maxlen):
    u=urllib.parse.urlsplit(url)
    assert u.scheme=="https" and u.hostname==host and not u.username and not u.password
    req=urllib.request.Request(url,headers={"User-Agent":"Portable-fixed-image-build-audit/1"})
    with urllib.request.urlopen(req,timeout=90) as resp:
        assert urllib.parse.urlsplit(resp.url).hostname==host
        body=resp.read(maxlen+1)
    assert len(body)<=maxlen
    return body

def native_top(name,path):
    # The prior mypyc wheel may use a top-level named native extension.
    # Accept only the reviewed exact naming class, only from this pinned wheel.
    return name=="charset-normalizer" and bool(re.fullmatch(r"[0-9a-f]{20}__mypyc\.cp314-win_amd64\.pyd",path))
def root_allowed(name,path,ver):
    s=SPECS[name]
    return path in set(s["roots"])|{dist(name,ver)} or native_top(name,path)
def root_paths(parent,root):
    p=parent/root
    if p.is_dir():return files(parent,root)
    plain(p);return {root}
def all_roots(parent,name,ver):
    return {p.name for p in parent.iterdir() if root_allowed(name,p.name,ver)}
def download(name,house,expected_versions):
    s=SPECS[name];di=dist(name,s["new"])
    release=json.loads(fetch("https://pypi.org/pypi/"+name+"/"+s["new"]+"/json","pypi.org",4*1024*1024))
    assert norm(release["info"]["name"])==name and release["info"]["version"]==s["new"]
    candidates=[x for x in release["urls"] if x["filename"]==s["wheel"]]
    assert len(candidates)==1
    item=candidates[0]
    assert not item["yanked"] and item["packagetype"]=="bdist_wheel"
    assert item["url"]==s["url"] and item["digests"]["sha256"]==s["sha"]
    wn,wv,_,tags=parse_wheel_filename(s["wheel"])
    assert wn==name and str(wv)==s["new"] and not wv.is_prerelease and set(sys_tags())&tags
    assert SpecifierSet(item["requires_python"] or release["info"]["requires_python"]).contains("3.14.10")
    assert 0<item["size"]<32*1024*1024
    raw=fetch(s["url"],"files.pythonhosted.org",item["size"])
    assert len(raw)==item["size"] and sha(raw)==s["sha"]
    (house/s["wheel"]).write_bytes(raw)
    payload={};seen=set();total=0
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert len(z.infolist())<2500
        for info in z.infolist():
            p=pathsafe(info.filename.rstrip("/"))
            assert p.casefold() not in seen and not stat.S_ISLNK(info.external_attr>>16) and not info.flag_bits&1,p
            seen.add(p.casefold())
            assert root_allowed(name,p.split("/")[0],s["new"]),p
            if info.is_dir():continue
            assert not p.endswith((".pyc",".pth")) and "__pycache__" not in p,p
            assert info.file_size<32*1024*1024
            total+=info.file_size;assert total<100*1024*1024
            payload[p]=z.read(info)
    roots={p.split("/")[0] for p in payload}
    assert set(s["roots"])|{di}<=roots
    rec=di+"/RECORD";rr=records(payload[rec])
    assert set(rr)==set(payload),("wheel RECORD paths",name,sorted(set(rr)^set(payload)))
    for p,b in payload.items():
        assert rr[p]==(("","") if p==rec else (rh(b),str(len(b)))),p
    meta=email.parser.BytesParser().parsebytes(payload[di+"/METADATA"],headersonly=True)
    assert norm(meta["Name"])==name and meta["Version"]==s["new"]
    assert SpecifierSet(meta["Requires-Python"]).contains("3.14.10")
    assert (meta.get("License-Expression") or meta.get("License")) in s["license"],("license metadata",name,meta.get("License-Expression"),meta.get("License"))
    license_names=meta.get_all("License-File",[])
    assert set(license_names)==set(s["licenses"]),("license inventory",name,license_names)
    for p,digest in s["licenses"].items():source_blob(payload[di+"/licenses/"+p],digest,name+" license "+p)
    for p,digest in s["source"].items():source_blob(payload[p],digest,p)
    wheel=email.parser.BytesParser().parsebytes(payload[di+"/WHEEL"],headersonly=True)
    assert set(wheel.get_all("Tag"))=={str(t) for t in tags}
    assert wheel["Root-Is-Purelib"].lower()==str(s["pure"]).lower()
    deps=[]
    for value in meta.get_all("Requires-Dist",[]):
        d=Requirement(value)
        if d.marker and not d.marker.evaluate({"extra":""}):continue
        assert not d.url
        key=norm(d.name);assert key in expected_versions and d.specifier.contains(expected_versions[key]),("dependency closure",name,value,expected_versions.get(key))
        deps.append(value)
    natives={p:b for p,b in payload.items() if p.endswith((".pyd",".dll"))}
    assert bool(natives)!=s["pure"],("native wheel payload",name)
    for p,b in natives.items():
        offset=struct.unpack_from("<I",b,60)[0]
        assert b[:2]==b"MZ" and b[offset:offset+4]==b"PE\0\0" and struct.unpack_from("<H",b,offset+4)[0]==0x8664,p
    print("OFFICIAL_WHEEL_RECORD_SOURCE_LICENSE=PASS "+name+" "+s["new"]+" sha256="+s["sha"]+" natives="+str(len(natives))+" dependencies="+json.dumps(deps),flush=True)
    return di,payload
def old_inventory(name,tracked):
    s=SPECS[name];di=dist(name,s["old"])
    roots=all_roots(SITE,name,s["old"])
    assert set(s["roots"])|{di}<=roots
    owned=set().union(*(root_paths(SITE,p) for p in roots))
    vendor=s["vendor"]
    if vendor:
        owned.add(vendor)
        assert rev("HEAD:"+PREFIX+vendor)==s["vendor_sha"]
    check_record(SITE,di,owned)
    assert all(PREFIX+p in tracked for p in owned)
    # Confirm no other distribution claims any selected path. Existing
    # top-level mypyc ownership must be proven by the actual old RECORD.
    for record in SITE.glob("*.dist-info/RECORD"):
        if record.parent.name==di:continue
        other=records(record.read_bytes())
        assert not (set(other)&owned),("cross-distribution ownership",record.parent.name,sorted(set(other)&owned))
    print("OLD_TRACKED_RECORD=PASS "+name+" files="+str(len(owned)),flush=True)
    ep=SITE/di/"entry_points.txt"
    return roots,owned,entries(ep.read_bytes() if ep.exists() else None)
def run(*argv,env=None,timeout=240):
    p=subprocess.run([str(x) for x in argv],cwd=ROOT,env=env,capture_output=True,timeout=timeout)
    print(p.stdout.decode("utf-8","backslashreplace"),end="",flush=True)
    print(p.stderr.decode("utf-8","backslashreplace"),end="",flush=True)
    assert p.returncode==0,("failed command",str(argv[0]),[str(x) for x in argv[1:4]],p.returncode)
    return p.stdout

def update_locks(group):
    input=ROOT/IN;lock=ROOT/LOCK
    old=input.read_bytes();new=old;raw=lock.read_bytes()
    header=b"# requirements-sha256: "+sha(old).encode()
    assert raw.count(header)==1
    for name in GROUPS[group]:
        s=SPECS[name];a=(name+"=="+s["old"]).encode();b=(name+"=="+s["new"]).encode()
        assert new.count(a)==1;new=new.replace(a,b,1)
        a+=(" --hash=sha256:"+s["oldsha"]).encode();b+=(" --hash=sha256:"+s["sha"]).encode()
        assert raw.count(a)==1;raw=raw.replace(a,b,1)
    raw=raw.replace(header,b"# requirements-sha256: "+sha(new).encode(),1)
    input.write_bytes(new);lock.write_bytes(raw)


def allowed(group,path):
    if path in {IN,LOCK}:return True
    if not path.startswith(PREFIX):return False
    s=SPECS[group]
    relative=path[len(PREFIX):]
    if relative==s["vendor"]:return False # legacy launcher bytes must not change
    root=relative.split("/")[0]
    return root_allowed(group,root,s["old"]) or root_allowed(group,root,s["new"])
def stage(group,owned):
    name=group;s=SPECS[name]
    old=versions();expected={**old,name:s["new"]}
    tracked=names("ls-files","-z")
    for p in (*reversed(SITE.parents),SITE):plain(p,True)
    old_roots,old_paths,old_entries=old_inventory(name,tracked)
    assert old[name]==s["old"]
    house=owned/"wheelhouse";house.mkdir()
    stage=owned/"stage";stage.mkdir()
    backup=owned/"backup";backup.mkdir()
    di,payload=download(name,house,expected)
    assert entries(payload.get(di+"/entry_points.txt"))==old_entries,("unreviewed entrypoint change",name)
    lock=owned/"group-lock.txt"
    lock.write_text(name+"=="+s["new"]+" --hash=sha256:"+s["sha"]+"\n",encoding="ascii",newline="\n")
    env={k:os.environ[k] for k in ("SystemRoot","WINDIR","SystemDrive","ComSpec","PATHEXT","OS","PROCESSOR_ARCHITECTURE") if k in os.environ}
    windows=Path(env["SystemRoot"])
    env["PATH"]=os.pathsep.join((str(PY.parent),str(windows/"System32"),str(windows)))
    for k,v in (("HOME","home"),("USERPROFILE","home"),("APPDATA","appdata"),("LOCALAPPDATA","localappdata"),("PROGRAMDATA","programdata"),("ALLUSERSPROFILE","programdata"),("TEMP","temp"),("TMP","temp"),("TMPDIR","temp"),("PIP_CACHE_DIR","cache"),("PYTHONUSERBASE","userbase"),("PYTHONPYCACHEPREFIX","pycache")):
        path=owned/v;path.mkdir(exist_ok=True);env[k]=str(path)
    env.update(PIP_CONFIG_FILE="nul",PYTHONDONTWRITEBYTECODE="1",PYTHONNOUSERSITE="1")
    run(PY,"-B","-m","pip","--isolated","--disable-pip-version-check","--no-input","install","--no-index","--find-links",house,
        "--no-deps","--require-hashes","--only-binary=:all:","--no-compile","--ignore-installed","--requirement",lock,"--target",stage,env=env,timeout=240)
    rec=di+"/RECORD";roots={p.split("/")[0] for p in payload}
    paths=set().union(*(root_paths(stage,p) for p in roots))
    assert paths==set(payload)|{di+"/INSTALLER",di+"/REQUESTED"},("staged inventory",name,sorted(paths^(set(payload)|{di+"/INSTALLER",di+"/REQUESTED"})))
    assert (stage/di/"INSTALLER").read_text().strip()=="pip" and (stage/di/"REQUESTED").read_bytes()==b""
    for p,b in payload.items():
        if p!=rec:assert (stage/p).read_bytes()==b,p
    normalized={}
    for p,pair in records((stage/rec).read_bytes()).items():
        q=p.removeprefix("../../") if p.startswith("../../bin/") else p
        assert q not in normalized
        pathsafe(q);normalized[q]=pair
    vendor=s["vendor"];scripts={vendor} if vendor else set()
    assert set(normalized)==paths|scripts,("staged RECORD",name,sorted(set(normalized)^(paths|scripts)))
    for p in paths|scripts:
        raw=(stage/p).read_bytes()
        assert normalized[p]==(("","") if p==rec else (rh(raw),str(len(raw)))),p
    assert {p.name for p in stage.iterdir()}==roots|({"bin"} if vendor else set())
    if vendor:
        assert files(stage,"bin")==scripts
        # Keep the exact legacy vendor EXE, never its transient absolute
        # target path. Managed CMD and metadata entrypoints are unchanged.
        (stage/vendor).write_bytes((SITE/vendor).read_bytes());paths.add(vendor)
    write_record(stage,di,paths)
    check_record(stage,di,paths)
    for p in old_roots:(SITE/p).rename(backup/p)
    for p in roots:
        assert not (SITE/p).exists(),p
        (stage/p).rename(SITE/p)
    check_record(SITE,di,paths)
    assert versions()==expected
    update_locks(group)
    run(PY,"-B","tool/python-lock.py","validate","--requirements",IN,"--lock",LOCK)
    run(PY,"-B","tool/python-lock.py","validate-runtime","--requirements",IN)
    run(PY,"-B","-m","pip","--isolated","--disable-pip-version-check","check",env=env)
    changed=names("diff","--no-renames","--name-only","-z")|names("ls-files","--others","--exclude-standard","-z")
    assert {IN,LOCK}<=changed and all(allowed(group,p) for p in changed),("out of scope",sorted(p for p in changed if not allowed(group,p)))
    paths=sorted(changed)
    for i in range(0,len(paths),50):git("add","-A","--",*paths[i:i+50])
    assert names("diff","--cached","--no-renames","--name-only","-z")==changed
    assert not git("diff","--name-only","-z") and not names("ls-files","--others","--exclude-standard","-z")
    git(*BOT,"commit","-m","Refresh audited stable "+name+" "+s["new"]+" wheel")
    clean();print("LOCAL_CANDIDATE="+group+" "+rev()+" files="+str(len(changed)),flush=True)
def native_tests(group):
    for pattern in ("test_python_lock.py","test_python_runtime_dependencies.py","test_mode_copies.py"):
        run(PY,"-B","-m","unittest","discover","-s","tests","-p",pattern,"-v",timeout=150)
    if group=="lxml":
        run(PY,"-B","-m","unittest","discover","-s","tests","-p","test_office_output_boundaries.py","-v",timeout=150)
    if SPECS[group]["vendor"]:
        run(PY,"-B","-m","unittest","discover","-s","tests","-p","test_python_cli*.py","-v",timeout=150)
    for mode in ("normal","yolo"):
        run(PY,"-B",TEST,group,mode,"consumer",timeout=500)
    clean()
    run(PY,"-B","tool/package-release.py","--check",timeout=240);clean()
def restore(group,head):
    dirty=names("diff","--no-renames","--name-only","-z",head)|names("ls-files","--others","--exclude-standard","-z")
    assert all(allowed(group,p) for p in dirty),("unexpected failed candidate path",sorted(p for p in dirty if not allowed(group,p)))
    git("reset","--hard",head)
    extra=sorted(names("ls-files","--others","--exclude-standard","-z"))
    for i in range(0,len(extra),50):git("clean","-fd","--",*extra[i:i+50])
    clean()
def guard():
    assert os.name=="nt" and sys.version_info[:3]==(3,14,10)
    assert sys.flags.isolated and Path(sys.executable).resolve()==PY
    assert os.environ.get("GITHUB_ACTIONS")=="true" and os.environ.get("GITHUB_REPOSITORY")=="rileyaaa/Portable"
    assert os.environ.get("GITHUB_REF")==BRANCH
    assert subprocess.run(["git","symbolic-ref","-q","HEAD"],cwd=ROOT,capture_output=True).returncode!=0,"not a detached CI checkout"

def state_read():
    return json.loads(STATE.read_bytes()) if STATE.exists() else {"trigger":os.environ["GITHUB_SHA"],"groups":{}}
def state_write(s):
    STATE.write_text(json.dumps(s,ensure_ascii=True,indent=2)+"\n",encoding="utf-8",newline="\n")

def remote_functions():
    auth=base64.b64encode(("x-access-token:"+os.environ.pop("GH_TOKEN")).encode()).decode()
    print("::add-mask::"+auth,flush=True)
    cfg=["-c","http.https://github.com/.extraheader=AUTHORIZATION: basic "+auth]
    def ref(name):
        value,actual=git(*cfg,"ls-remote","origin",name).decode().strip().split("\t")
        assert actual==name
        return value
    def frozen():
        assert ref("refs/heads/main")==ref("refs/tags/v0.172.0-portable.1")==FROZEN
    def publish(old,new):
        frozen();assert ref(BRANCH)==old and rev()==new and rev("HEAD^")==old
        for delay in (0,10,30):
            if delay:time.sleep(delay)
            p=subprocess.run(["git",*cfg,"push","origin","HEAD:"+BRANCH],cwd=ROOT)
            if ref(BRANCH)==new:break
            assert ref(BRANCH)==old
            if p.returncode==0:break
        assert ref(BRANCH)==new
        run("git",*cfg,"fetch","--no-tags","origin",BRANCH)
        assert rev("FETCH_HEAD")==new and rev("FETCH_HEAD^{tree}")==rev("HEAD^{tree}")
        frozen()
    return ref,frozen,publish

def group_main(group):
    guard();clean();assert group in GROUPS
    ref,frozen,publish=remote_functions()
    frozen();head=rev();assert ref(BRANCH)==head
    state=state_read();assert state["trigger"]==os.environ["GITHUB_SHA"] and group not in state["groups"]
    known=state["trigger"]
    for n,data in state["groups"].items():
        assert data["status"] in {"delivered","retained"},data
        assert data["base"]==known
        if data["status"]=="delivered":known=data["commit"]
    assert head==known
    state["groups"][group]={"status":"started","base":head}
    state_write(state)
    candidate=None
    try:
        scratch=ROOT/"tmp";scratch.mkdir(exist_ok=True);plain(scratch,True)
        # All installation work is in a disposable package-owned temporary
        # directory; no changes to the runner host interpreter.
        with tempfile.TemporaryDirectory(prefix=group+"-fixed-wheel-",dir=scratch) as d:
            stage(group,Path(d))
        candidate=rev();assert rev("HEAD^")==head
        native_tests(group)
        assert not git("diff","--name-only",BASE,"HEAD","--","env.ps1","run-codex.ps1","Version_History","tool/automation","tool/node","tool/bin","tool/python/python314._pth","tool/runtime-manifest.json",".gitattributes","codex.exe","codex-path")
        run("git","lfs","fsck",timeout=240)
        clean()
        publish(head,candidate)
        state["groups"][group]={"status":"delivered","commit":candidate,"base":head,"tree":rev("HEAD^{tree}")}
        state_write(state)
        print("DELIVERED_"+group.upper()+"="+candidate,flush=True)
    except Exception as exc:
        traceback.print_exc()
        actual=ref(BRANCH)
        if actual!=head:
            # Never rewind a remote commit, or falsely claim retained old
            # version if an accepted push occurred but readback failed.
            state["groups"][group]={"status":"remote-unconfirmed","base":head,"remote":actual,"error":str(exc)[:700]}
            state_write(state)
            raise
        restore(group,head)
        state["groups"][group]={"status":"retained","base":head,"error":str(exc)[:700]}
        state_write(state)
        print("RETAINED_"+group.upper()+"="+str(exc)[:700],flush=True)
        # Exact failure is visible; the independent other step may proceed.
        raise SystemExit(1)

if __name__=="__main__":
    assert len(sys.argv)==2
    group_main(sys.argv[1])
