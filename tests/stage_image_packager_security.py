"""One-time developer CI: fixed Pillow / PyInstaller+hooks wheels, independently.

No customer install, no network except the exact official wheel sources and
ordinary Git transport; no malicious images, elevated frozen programs, or
changes to Python's _pth, launchers, permissions, or LFS configuration.
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
BASE="1a230a507da111e9bf54b7b39c347297c333c0e0"
BOT=["-c","user.name=github-actions[bot]","-c","user.email=41898282+github-actions[bot]@users.noreply.github.com"]
HELPER="tests/stage_image_packager_security.py"
WORKFLOW=".github/workflows/refresh-image-packager-security.yml"
TEST="tests/check_image_packager_refresh.py"
BUILD_MANIFEST="tool/python-build-manifest.json"
BUILD_TEST="tests/test_python_runtime_dependencies.py"
IN="tool/python-packages.in.txt"
LOCK="tool/python-packages.lock.txt"
DOC="tool/\u5de5\u5177\u66f4\u65b0\u8bf4\u660e.md"
STATE=Path(os.environ["RUNNER_TEMP"])/("portable-image-packager-"+os.environ["GITHUB_RUN_ID"]+".json")
SPECS={
    "pillow":{
        "old":"12.2.0","new":"13.0.0","wheel":"pillow-13.0.0-cp314-cp314-win_amd64.whl",
        "oldsha":"4e6c62e9d237e9b65fac06857d511e90d8461a32adcc1b9065ea0c0fa3a28150",
        "sha":"f7cbb7a64e7ec664775195e4f81923bc8a93d9451b963f844e59118f63147a7a",
        "url":"https://files.pythonhosted.org/packages/50/e2/7ad17747517e4c813dca78257d6bb593466f8231baf1384bc98d92745edb/pillow-13.0.0-cp314-cp314-win_amd64.whl",
        "root":"PIL","license":"MIT-CMU","licensefile":"LICENSE",
        "tag":"python-pillow/Pillow@13.0.0",
        "source":{"PIL/Image.py":"40720c5d438750a21b9752c94e67259b23ddb437","PIL/_version.py":"0c358640935273e55b39c88638970c35b22a49da"},
        "licenseblob":"c011511a4ab6bd2bc901608e6b4c0fad95fc410f",
    },
    "pyinstaller":{
        "old":"6.21.0","new":"6.22.3","wheel":"pyinstaller-6.22.3-py3-none-win_amd64.whl",
        "oldsha":"7fae06c494ce0ebfe6bd3055c0e409def884f63af2e3705d06bd431ad9237fc7",
        "sha":"500bd58c7bf7e584a8435adccbd763a0b918d5c12b08d74ff50fd79b2915458b",
        "url":"https://files.pythonhosted.org/packages/24/83/c5422204772a27aef643280fdc887b7ef55679989096b21dceb1b9625fc4/pyinstaller-6.22.3-py3-none-win_amd64.whl",
        "root":"PyInstaller","license":"GPLv2-or-later with a special exception which allows to use PyInstaller to build and distribute non-free programs (including commercial ones)",
        "licensefile":"COPYING.txt","tag":"pyinstaller/pyinstaller@v6.22.3",
        "source":{"PyInstaller/__main__.py":"f36090b4b2666f558b8092a499478ea360a701a1","PyInstaller/__init__.py":"b0f7e62677dc8e7c096262370aa3aef27dd47702"},
        "licenseblob":"d6caec5ab5778c36bd7e26d8d7a48eba1ac23dee",
    },
    "pyinstaller-hooks-contrib":{
        "old":"2026.6","new":"2026.10","wheel":"pyinstaller_hooks_contrib-2026.10-py3-none-any.whl",
        "oldsha":"fd13b8ac126b35361175edacd41a0d97080b75dd5f4b594ecefefff969509dd3",
        "sha":"dfc3cde20a7ce6c92e803016e66eed4b7050467e2c5f886a3745d89b258c6d6d",
        "url":"https://files.pythonhosted.org/packages/08/10/4a6d13adaa93d0bbcfea082a78965e970cae7a8bfa82ac1557a1dc8f1cba/pyinstaller_hooks_contrib-2026.10-py3-none-any.whl",
        "root":"_pyinstaller_hooks_contrib","license":None,"licensefile":"LICENSE","tag":"pyinstaller/pyinstaller-hooks-contrib@v2026.10",
        "source":{"_pyinstaller_hooks_contrib/__init__.py":"9efdf5f7230b43e172329402433943d2759f7a09"},
        "licenseblob":"99bef9e7dc1e29e876057749037f409516eb0509",
    },
}
GROUPS={"image":("pillow",),"packager":("pyinstaller","pyinstaller-hooks-contrib")}
# The only tracked historical PyInstaller vendor EXE is never executed or
# exposed. All five other entries in the historical RECORD are absent.
VENDOR="bin/pyinstaller.exe"
MISSING_VENDOR={"bin/pyi-"+x+".exe" for x in ("archive_viewer","bindepend","grab_version","makespec","set_version")}
VENDOR_SET={VENDOR}|MISSING_VENDOR
SOURCE_TEST=ROOT/TEST

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
    allowed_roots={s["root"],di}
    if name=="pillow":allowed_roots.add("pillow.libs")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert len(z.infolist())<2500
        for info in z.infolist():
            p=pathsafe(info.filename.rstrip("/"))
            assert p.casefold() not in seen and not stat.S_ISLNK(info.external_attr>>16) and not info.flag_bits&1,p
            seen.add(p.casefold())
            assert p.split("/")[0] in allowed_roots,p
            if info.is_dir():continue
            assert not p.endswith((".pyc",".pth")) and "__pycache__" not in p,p
            assert info.file_size<32*1024*1024
            total+=info.file_size;assert total<100*1024*1024
            payload[p]=z.read(info)
    rec=di+"/RECORD";rr=records(payload[rec])
    assert set(rr)==set(payload),("wheel RECORD paths",name,sorted(set(rr)^set(payload)))
    for p,b in payload.items():
        assert rr[p]==(("","") if p==rec else (rh(b),str(len(b)))),p
    meta=email.parser.BytesParser().parsebytes(payload[di+"/METADATA"],headersonly=True)
    assert norm(meta["Name"])==name and meta["Version"]==s["new"]
    assert SpecifierSet(meta["Requires-Python"]).contains("3.14.10")
    assert (meta.get("License-Expression") or meta.get("License"))==s["license"]
    licenses=meta.get_all("License-File",[])
    assert s["licensefile"] in licenses and all(di+"/licenses/"+f in payload for f in licenses)
    lic=payload[di+"/licenses/"+s["licensefile"]]
    if name=="pillow":
        # Pillow's wheel appends bundled third-party notices to the source
        # license. Keep all notices and compare its original license prefix.
        lic=lic.replace(b"\r\n",b"\n").split(b"\n=====",1)[0].rstrip()+b"\n"
    source_blob(lic,s["licenseblob"],name+" license")
    for p,identity in s["source"].items():source_blob(payload[p],identity,p)
    wheel=email.parser.BytesParser().parsebytes(payload[di+"/WHEEL"],headersonly=True)
    assert set(wheel.get_all("Tag"))=={str(t) for t in tags}
    assert wheel["Root-Is-Purelib"].lower()==("false" if name=="pillow" else "true")
    deps=[]
    for value in meta.get_all("Requires-Dist",[]):
        d=Requirement(value)
        if d.marker and not d.marker.evaluate({"extra":""}):continue
        assert not d.url
        key=norm(d.name);assert key in expected_versions and d.specifier.contains(expected_versions[key]),("dependency closure",name,value,expected_versions.get(key))
        deps.append(value)
    if name=="pyinstaller":
        assert any(norm(Requirement(d).name)=="pyinstaller-hooks-contrib" and
                   not Requirement(d).specifier.contains("2026.6") for d in deps)
        for f in ("run.exe","run_d.exe","runw.exe","runw_d.exe"):
            p="PyInstaller/bootloader/Windows-64bit-intel/"+f
            b=payload[p]
            offset=struct.unpack_from("<I",b,60)[0]
            assert b[:2]==b"MZ" and b[offset:offset+4]==b"PE\0\0" and struct.unpack_from("<H",b,offset+4)[0]==0x8664,p
            print("OFFICIAL_AMD64_BOOTLOADER "+p+" sha256="+sha(b),flush=True)
    print("OFFICIAL_WHEEL_RECORD_SOURCE_LICENSE=PASS "+name+" "+s["new"]+" sha256="+s["sha"]+" dependencies="+json.dumps(deps),flush=True)
    return di,payload

def old_inventory(name,tracked):
    s=SPECS[name];di=dist(name,s["old"])
    owned=files(SITE,s["root"])|files(SITE,di)
    if name=="pillow":assert not (SITE/"pillow.libs").exists()
    absent=set()
    if name=="pyinstaller":
        owned.add(VENDOR);absent=MISSING_VENDOR
        assert rev("HEAD:"+PREFIX+VENDOR)=="bfbc1b2ff526ddd41c5cd2a2c019e3aafbe771b8"
    check_record(SITE,di,owned,absent)
    assert all(PREFIX+p in tracked for p in owned)
    assert all(PREFIX+p not in tracked for p in absent)
    print("OLD_TRACKED_RECORD=PASS "+name+" files="+str(len(owned))+" historical_absent="+json.dumps(sorted(absent)),flush=True)
    ep=SITE/di/"entry_points.txt"
    return owned,entries(ep.read_bytes() if ep.exists() else None)

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

def scope(group):
    prefixes=[]
    for n in GROUPS[group]:
        s=SPECS[n];prefixes.extend(PREFIX+p+"/" for p in (s["root"],dist(n,s["old"]),dist(n,s["new"])))
        if n=="pillow":prefixes.append(PREFIX+"pillow.libs/")
    exact={IN,LOCK}
    if group=="packager":exact|={BUILD_MANIFEST,BUILD_TEST}
    return tuple(prefixes),exact

def change_manifest():
    p=ROOT/BUILD_MANIFEST;manifest=json.loads(p.read_bytes())
    assert manifest["source_commit"]=="fcaf45e5dfe4c97f096475f211a423b6d882c4ae"
    assert manifest["packages"]["pyinstaller"]=="6.21.0" and manifest["packages"]["pyinstaller-hooks-contrib"]=="2026.6"
    # Commit object identities for the actual staged runtime trees; preserve
    # historical attribution and exact identities of the unchanged closure.
    old_objects=manifest["objects"]
    tree=git("write-tree").decode().strip()
    replacements={}
    for n in GROUPS["packager"]:
        s=SPECS[n];replacements[PREFIX+dist(n,s["old"])]=PREFIX+dist(n,s["new"])
    updated=[]
    for entry in old_objects:
        old=entry["path"];new=replacements.get(old,old)
        if old.startswith((PREFIX+"PyInstaller",PREFIX+"_pyinstaller_hooks_contrib",PREFIX+"pyinstaller-6.21.0",PREFIX+"pyinstaller_hooks_contrib-2026.6")):
            updated.append({**entry,"path":new,"sha":rev(tree+":"+new)})
        else:
            assert rev(tree+":"+old)==entry["sha"],old
            updated.append(entry)
    manifest["objects"]=updated
    manifest["historical_replaced_objects"]=[e for e in old_objects if e not in updated]
    manifest["packages"]["pyinstaller"]="6.22.3";manifest["packages"]["pyinstaller-hooks-contrib"]="2026.10"
    manifest["existing_dependency"]["packaging"]="26.4"
    manifest["note"]="Unchanged build closure retains historical Git objects from source_commit; PyInstaller and hooks refreshed from exact official wheels, full wheel RECORD and selected upstream tag source/license checked. No host Python or vendor EXE executed. See linked native build evidence in DEVELOPMENT.md."
    manifest["official_refresh"]={n:{"version":SPECS[n]["new"],"filename":SPECS[n]["wheel"],"sha256":SPECS[n]["sha"],"url":SPECS[n]["url"],"upstream_tag":SPECS[n]["tag"],"source_blobs":SPECS[n]["source"],"license_blob":SPECS[n]["licenseblob"]} for n in GROUPS["packager"]}
    p.write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8",newline="\n")
    q=ROOT/BUILD_TEST;raw=q.read_bytes()
    old=b"self.assertEqual(result.stdout.strip(), '6.21.0')"
    assert raw.count(old)==1
    q.write_bytes(raw.replace(old,b"self.assertEqual(result.stdout.strip(), '6.22.3')"))
    git("add","--",BUILD_MANIFEST,BUILD_TEST)

def stage(group,owned):
    old=versions();expected={**old,**{n:SPECS[n]["new"] for n in GROUPS[group]}}
    tracked=names("ls-files","-z")
    for p in (*reversed(SITE.parents),SITE):plain(p,True)
    inventory={n:old_inventory(n,tracked) for n in GROUPS[group]}
    for n in GROUPS[group]:assert old[n]==SPECS[n]["old"],(n,old[n])
    house=owned/"wheelhouse";house.mkdir()
    stage=owned/"stage";stage.mkdir()
    backup=owned/"backup";backup.mkdir()
    wheeldata={n:download(n,house,expected) for n in GROUPS[group]}
    for n,(di,content) in wheeldata.items():
        assert entries(content.get(di+"/entry_points.txt"))==inventory[n][1],("unreviewed entrypoint change",n)
    lock=owned/"group-lock.txt"
    lock.write_text("".join(n+"=="+SPECS[n]["new"]+" --hash=sha256:"+SPECS[n]["sha"]+"\n" for n in GROUPS[group]),encoding="ascii",newline="\n")
    env={k:os.environ[k] for k in ("SystemRoot","WINDIR","SystemDrive","ComSpec","PATHEXT","OS","PROCESSOR_ARCHITECTURE") if k in os.environ}
    windows=Path(env["SystemRoot"])
    env["PATH"]=os.pathsep.join((str(PY.parent),str(windows/"System32"),str(windows)))
    for k,v in (("HOME","home"),("USERPROFILE","home"),("APPDATA","appdata"),("LOCALAPPDATA","localappdata"),("PROGRAMDATA","programdata"),("ALLUSERSPROFILE","programdata"),("TEMP","temp"),("TMP","temp"),("TMPDIR","temp"),("PIP_CACHE_DIR","cache"),("PYTHONUSERBASE","userbase"),("PYTHONPYCACHEPREFIX","pycache")):
        path=owned/v;path.mkdir(exist_ok=True);env[k]=str(path)
    env.update(PIP_CONFIG_FILE="nul",PYTHONDONTWRITEBYTECODE="1",PYTHONNOUSERSITE="1")
    run(PY,"-B","-m","pip","--isolated","--disable-pip-version-check","--no-input","install","--no-index","--find-links",house,
        "--no-deps","--require-hashes","--only-binary=:all:","--no-compile","--ignore-installed","--requirement",lock,"--target",stage,env=env,timeout=240)
    expected_roots=set()
    for n,(di,payload) in wheeldata.items():
        rec=di+"/RECORD";roots={p.split("/")[0] for p in payload}
        expected_roots|=roots
        paths=set().union(*(files(stage,r) for r in roots))
        extras={di+"/INSTALLER",di+"/REQUESTED"}
        assert paths==set(payload)|extras,("staged inventory",n,sorted(paths^(set(payload)|extras)))
        assert (stage/di/"INSTALLER").read_text().strip()=="pip" and (stage/di/"REQUESTED").read_bytes()==b""
        for p,b in payload.items():
            if p!=rec:assert (stage/p).read_bytes()==b,p
        rr=records((stage/rec).read_bytes())
        # pip's Windows target scheme can record ../../bin for generated
        # console scripts. Normalize only those exact six names.
        normalized={}
        for p,pair in rr.items():
            q=p.removeprefix("../../") if p.startswith("../../bin/") else p
            assert q not in normalized
            pathsafe(q);normalized[q]=pair
        vendor=VENDOR_SET if n=="pyinstaller" else set()
        assert set(normalized)==paths|vendor,("staged installed RECORD",n,sorted(set(normalized)^(paths|vendor)))
        for p in paths|vendor:
            raw=(stage/p).read_bytes()
            assert normalized[p]==(("","") if p==rec else (rh(raw),str(len(raw)))),p
        if n=="pyinstaller":
            expected_roots.add("bin")
            assert files(stage,"bin")==VENDOR_SET
            # No generated launcher is installed into the live repo. Preserve
            # the exact one legacy unexposed EXE and its actual RECORD digest.
            (stage/VENDOR).write_bytes((SITE/VENDOR).read_bytes())
            paths.add(VENDOR)
        write_record(stage,di,paths)
        check_record(stage,di,paths)
        print("STAGED_OFFICIAL_BYTES_AND_RECORD=PASS "+n,flush=True)
    assert {p.name for p in stage.iterdir()}==expected_roots
    for n,(di,payload) in wheeldata.items():
        s=SPECS[n];old_di=dist(n,s["old"])
        roots={p.split("/")[0] for p in payload}
        for p in (s["root"],old_di):(SITE/p).rename(backup/p)
        for p in sorted(roots):
            assert not (SITE/p).exists(),p
            (stage/p).rename(SITE/p)
        rec_paths=set().union(*(files(SITE,p) for p in roots))
        if n=="pyinstaller":rec_paths.add(VENDOR)
        check_record(SITE,di,rec_paths)
    assert versions()==expected
    update_locks(group)
    run(PY,"-B","tool/python-lock.py","validate","--requirements",IN,"--lock",LOCK)
    run(PY,"-B","tool/python-lock.py","validate-runtime","--requirements",IN)
    run(PY,"-B","-m","pip","--isolated","--disable-pip-version-check","check",env=env)
    prefixes,exact=scope(group)
    payload_paths=[p.rstrip("/") for p in prefixes]
    git("add","-A","--",*[p for p in payload_paths if (ROOT/p).exists() or any(x.startswith(p+"/") for x in tracked)],IN,LOCK)
    if group=="packager":change_manifest()
    changed=names("diff","--cached","--no-renames","--name-only","-z")
    assert exact<=changed and all(p in exact or p.startswith(prefixes) for p in changed),("unexpected candidate path",sorted(p for p in changed if p not in exact and not p.startswith(prefixes)))
    assert not git("diff","--name-only","-z") and not names("ls-files","--others","--exclude-standard","-z")
    git(*BOT,"commit","-m",("Refresh official Pillow 13.0.0 security wheel" if group=="image" else "Refresh PyInstaller 6.22.3 and required hooks-contrib 2026.10"))
    clean()
    print("LOCAL_CANDIDATE="+group+" "+rev()+" files="+str(len(changed)),flush=True)

def native_tests(group):
    # Only the changed dependency/consumer paths. No browser/MCP or old
    # full-suite revalidation. Real normal and YOLO child processes.
    for pattern in ("test_python_lock.py","test_python_runtime_dependencies.py","test_mode_copies.py"):
        run(PY,"-B","-m","unittest","discover","-s","tests","-p",pattern,"-v",timeout=150)
    if group=="image":
        for pattern in ("test_pdf_library*.py","test_office_output_boundaries.py"):
            run(PY,"-B","-m","unittest","discover","-s","tests","-p",pattern,"-v",timeout=240)
        run(PY,"-B",TEST,"image","normal","version",timeout=500)
        run(PY,"-B",TEST,"image","yolo","version",timeout=500)
    else:
        run(PY,"-B",TEST,"packager","normal","version",timeout=500)
        # Common-mode onedir uses a task-owned temporary cache; YOLO
        # onefile uses the documented package cache. Both real outputs are
        # moved before normal execution, no privileged execution.
        run(PY,"-B",TEST,"packager","normal","onedir",timeout=500)
        run(PY,"-B",TEST,"packager","yolo","onefile",timeout=500)
    clean()
    run(PY,"-B","tool/package-release.py","--check",timeout=240)
    clean()

def restore(group,head):
    # This is an explicitly detached disposable CI checkout; only discard
    # candidate-owned changes, never a user directory or remote commit.
    prefixes,exact=scope(group)
    dirty=names("diff","--no-renames","--name-only","-z",head)|names("ls-files","--others","--exclude-standard","-z")
    assert all(p in exact or p.startswith(prefixes) for p in dirty),("unexpected failed candidate path",sorted(p for p in dirty if p not in exact and not p.startswith(prefixes)))
    git("reset","--hard",head)
    git("clean","-fd","--",*[p.rstrip("/") for p in prefixes])
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
    prior=state["groups"].get("image",{})
    assert head==(prior.get("commit") or state["trigger"])
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
