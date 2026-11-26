"""Narrow provenance completion and actual license text inventory.
Reuses prior signed archive results, downloads only exact bytes needed for notices,
and verifies the one previously size-blocked source group. No build or distribution.
"""
import base64,hashlib,importlib.util,json,os,re,shutil,subprocess,sys,tarfile,traceback,uuid
from pathlib import Path
ROOT=Path(__file__).absolute().parents[1]
REPORT=Path(sys.argv[1]).absolute()
assert sys.platform=="linux" and os.environ["GITHUB_REPOSITORY"]=="rileyaaa/Portable"
PREV=json.loads((ROOT/"tests/locked_ocr_xmllite_45751623105.json").read_bytes())
OLD=json.loads((ROOT/"tests/fixed_seed_f2py_ocr_45749259260.json").read_bytes())["ocr_feasibility"]
P=PREV["provenance"];N=PREV["native"]
assert PREV["binary_archive_signatures_verified"]==49 and PREV["runtime_source_groups_inspected"]==32
assert PREV["native_recognition_passed"] and PREV["prior_candidate_id"]=="15085655070"
MISSING=[x for x in P["sources"] if x["runtime_required"] and x["status"]!="SOURCE_SIGNED_ARCHIVE_INSPECTED"]
assert len(MISSING)==1 and MISSING[0]["pkgbase"]=="mingw-w64-tesseract-data" and MISSING[0]["version"]=="4.1.0-3"
assert MISSING[0]["head"]["size"]==351069719 and MISSING[0]["status"]=="SOURCE_SIZE_OR_BUDGET_BLOCKED"
spec=importlib.util.spec_from_file_location("old_provenance",ROOT/"tests/check_locked_ocr_provenance.py")
p=importlib.util.module_from_spec(spec);sys.modules[spec.name]=p;spec.loader.exec_module(p)
OUT={"source_commit":os.environ["GITHUB_SHA"],"prior_run":"45751623105","prior_record":"da1c777ab04b2bbd0dd7c1e13ae6c2396b832931",
 "rows":[],"license_documents":{},"runtime_files":[],"source_evidence":{},"completed":False,"distribution_qualified":False,
 "limitations":["Full text is from exact signed prior archive bytes, or corresponding upstream source archive, with path/hash. Package notice alone does not prove every linked source-file obligation.",
 "No old technical OCR or 49 signature rerun. Full 41-PE graph remains not selected for distribution; no binary or source archive published.",
 "Model source is upstream released traineddata, not independent reproduction of training corpus.",
 "Mixed copyleft/exception/custom terms need actual file/linking review; old graph not cleared."]}
SRC={pkg:x for x in P["sources"] for pkg in x["packages"]}
SIG={x["name"]:x for x in P["packages"]}
LOCK={x["name"]:x for x in OLD["package_lock"]}
PE=N["runtime_closure"]
LOADED=set(n for r in N["rows"] if r["item"].startswith("actual local OCR process") for n in r["detail"]["bundled_modules"])
assert LOADED=={x["file"] for x in PE} and len(LOADED)==41
MODEL="mingw-w64-ucrt-x86_64-tesseract-data-chi_sim"
OWNERS={x["owner"] for x in PE}|{MODEL}
assert len(OWNERS)==35
def save():
    REPORT.write_text(json.dumps(OUT,ensure_ascii=True,indent=2)+"\n",encoding="utf-8")
def row(item,status,detail):
    OUT["rows"].append(dict(item=item,status=status,detail=detail));save()
    print("SOURCE_DECISION="+json.dumps({"item":item,"status":status},ensure_ascii=True),flush=True)
def hashbytes(b):return hashlib.sha256(b).hexdigest()
def document(data,origin):
    assert len(data)<=1024*1024
    key=hashbytes(data)
    if key not in OUT["license_documents"]:
        try:body={"text":data.decode("utf-8")}
        except UnicodeError:body={"base64":base64.b64encode(data).decode("ascii")}
        OUT["license_documents"][key]={"sha256":key,"size":len(data),"origins":[],**body}
    if origin not in OUT["license_documents"][key]["origins"]:OUT["license_documents"][key]["origins"].append(origin)
    return key
def tar_names(path,env):
    r=subprocess.run([str(p.TAR),"--zstd","-tf",str(path)],env=env,capture_output=True,check=True,timeout=180)
    assert len(r.stdout)<32*1024*1024
    ns=r.stdout.decode("utf-8","strict").splitlines();assert len(ns)<200000
    normalized={}
    for n in ns:
        k=n.removeprefix("./")
        if k.endswith("/"):continue
        assert k not in normalized
        normalized[k]=n
    return normalized
def readmember(path,names,name,env,cap=1024*1024):
    assert name in names and not name.startswith("/") and ".." not in name.split("/")
    r=subprocess.run([str(p.TAR),"--zstd","-xOf",str(path),"--",names[name]],env=env,capture_output=True,check=True,timeout=180)
    assert len(r.stdout)<=cap
    return r.stdout
def nested(path,names,name,env,dest,cap):
    assert name in names and not name.startswith("/") and ".." not in name.split("/")
    with dest.open("xb") as out:
        proc=subprocess.Popen([str(p.TAR),"--zstd","-xOf",str(path),"--",names[name]],env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        total=0
        try:
            while True:
                b=proc.stdout.read(1024*1024)
                if not b:break
                total+=len(b);assert total<=cap;out.write(b)
            assert proc.wait(timeout=180)==0
        finally:
            if proc.poll() is None:proc.kill();proc.wait(timeout=20)
    return {"size":total,"sha256":hashlib.file_digest(dest.open("rb"),"sha256").hexdigest()}
def source_licenses(nested_archive,origin):
    """Full license/NOTICE from actual upstream release files, no extraction."""
    docs=[];models=[];tops=set()
    with tarfile.open(nested_archive,"r:*") as tar:
        for x in tar:
            if not x.isfile():continue
            n=x.name.removeprefix("./");tops.add(n.split("/")[0])
            if n.endswith("/chi_sim.traineddata"):
                h=hashlib.sha256()
                with tar.extractfile(x) as f:
                    for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
                models.append({"path":n,"size":x.size,"sha256":h.hexdigest()})
            leaf=n.rsplit("/",1)[-1]
            if re.fullmatch(r"(?i)(license|licence|copying|copyright|notice|authors|patents)(?:[._-].*)?",leaf) and x.size<=1024*1024:
                if len(docs)>=200:raise AssertionError("license inventory cap")
                b=tar.extractfile(x).read()
                docs.append({"path":n,"sha256":document(b,{**origin,"source_member":n})})
    return docs,models,sorted(tops)
def inspect_source(base,keys,g,missing=False):
    path=base/(g["pkgbase"]+"-"+g["version"]+".src.tar.zst")
    info={"pkgbase":g["pkgbase"],"version":g["version"],"url":g["url"],"source_group_status":g["status"],"documents":[]}
    try:
        if missing:
            info["archive"]=p.download(g["url"],path,370*1024*1024,size=g["head"]["size"])
            sig=path.with_suffix(path.suffix+".sig")
            info["detached_signature"]=p.download(g["url"]+".sig",sig,128*1024,size=g["signature_head"]["size"])
            info["signature_verification"]=p.verify(keys,sig,path)
            assert info["signature_verification"]["verified"]
            sig.unlink()
        else:
            info["archive"]=p.download(g["url"],path,g["archive"]["size"],g["archive"]["sha256"],g["archive"]["size"])
            info["signature_verification"]=g["signature_verification"]
            assert info["signature_verification"]["verified"]
        names=tar_names(path,keys[1])
        recipes=[n for n in names if n.endswith("/PKGBUILD")]
        assert len(recipes)==1
        recipe=readmember(path,names,recipes[0],keys[1]);rh=hashbytes(recipe)
        if not missing:assert rh==g["recipes"][0]["sha256"]
        info["recipe"]={"path":recipes[0],"sha256":rh,"text":recipe.decode("utf-8")}
        nested_names=[n for n in names if re.search(r"\.(?:tar\.(?:gz|xz|bz2)|tgz)$",n,re.I)]
        assert nested_names and len(nested_names)<=8
        info["nested_archives"]=[]
        for i,n in enumerate(nested_names):
            q=base/("nested-"+str(i)+".tar");record=nested(path,names,n,keys[1],q,370*1024*1024 if missing else 128*1024*1024)
            if missing:
                assert record["sha256"]=="d0e3bb6f3b4e75748680524a1d116f2bfb145618f8ceed55b279d15098a530f9"
                assert record["sha256"] in info["recipe"]["text"] and "tessdata_fast" in info["recipe"]["text"]
            docs,models,tops=source_licenses(q,{"archive_url":g["url"],"nested_member":n,"nested_sha256":record["sha256"]})
            info["nested_archives"].append({"path":n,**record,"roots":tops,"models":models})
            info["documents"].extend(docs);q.unlink()
            if missing:
                assert len(models)==1
                want=next(x for x in N["runtime_model_and_config"] if x["path"]=="tessdata/chi_sim.traineddata")
                assert models[0]["sha256"]==want["sha256"] and models[0]["size"]==want["size"]
                assert any(x["path"].endswith("/LICENSE") for x in docs)
                info["model_exact_source_match"]=True
        assert info["documents"]
        info["status"]="SIGNED_SOURCE_AND_LICENSE_TEXT_INSPECTED"
    except Exception:info.update(status="BLOCKED_SOURCE_LICENSE",error=traceback.format_exc()[-4000:])
    finally:path.unlink(missing_ok=True);path.with_suffix(path.suffix+".sig").unlink(missing_ok=True)
    OUT["source_evidence"][g["pkgbase"]]=info;save()
    row("source "+g["pkgbase"],info["status"],{"documents":len(info["documents"]),"model_exact_source_match":info.get("model_exact_source_match",False)})
    return info
def notices(base,keys,name):
    rec=LOCK[name];prev=SIG[name]
    assert prev["status"]=="PASS_SIGNATURE" and prev["locked_sha256"]==rec["sha256"]
    g=SRC[name];docs=[]
    if rec["notice_files"]:
        q=base/rec["filename"]
        try:
            p.download(rec["url"],q,rec["compressed_size"],rec["sha256"],rec["compressed_size"])
            names=tar_names(q,keys[1])
            for n in rec["notice_files"]:
                raw=readmember(q,names,n["path"],keys[1]);assert hashbytes(raw)==n["sha256"] and len(raw)==n["size"]
                docs.append({"path":n["path"],"sha256":document(raw,{"archive_url":rec["url"],"archive_sha256":rec["sha256"],"package_member":n["path"]})})
        finally:q.unlink(missing_ok=True)
    source_docs=OUT["source_evidence"].get(g["pkgbase"],{}).get("documents",[])
    labels=" ".join(rec["licenses"]+rec["archive_pkginfo_license"]).lower()
    obligations=["Retain actual applicable copyright, license, attribution and NOTICE; review exact selected source file and build/link terms."]
    if "gpl" in labels or "custom" in labels or not labels:
        obligations.append("Mixed/copyleft/custom terms: exact selected-file source, applicable linking exceptions/combined-work and corresponding-source/build/relinking obligations remain uncleared.")
    if name.endswith("-jbigkit"):obligations.append("JBIG-KIT linked through TIFF: not selected for new PNG-only build; exact GPL terms not cleared for old graph.")
    if name==MODEL:obligations.append("Released chi_sim model bytes match signed source; retain Apache-2.0 license and any applicable model notice; training reproducibility not claimed.")
    return {"package":name,"version":rec["version"],"binary_archive_url":rec["url"],"binary_archive_sha256":rec["sha256"],
        "prior_verified_signature":prev["signature_verification"],"source_group":g["pkgbase"],"source_version":g["version"],"source_url":g["url"],
        "source_archive":OUT["source_evidence"].get(g["pkgbase"],{}).get("archive",g.get("archive")),
        "source_signature":OUT["source_evidence"].get(g["pkgbase"],{}).get("signature_verification",g.get("signature_verification")),
        "source_recipe":OUT["source_evidence"].get(g["pkgbase"],{}).get("recipe",g.get("recipes")),
        "full_package_notice_documents":docs,"full_source_license_documents":source_docs,"obligations":obligations,
        "exact_linked_source_file_legal_clearance":False,"selected_for_distribution":False}
def main():
    base=ROOT/"tmp"/("ocr-source-decision-"+uuid.uuid4().hex);base.parent.mkdir(exist_ok=True);base.mkdir()
    try:
        keys=p.keyring(base);archive=base/"archives";archive.mkdir()
        inspect_source(archive,keys,MISSING[0],True)
        # New purpose: complete actual license text missing from binary notices.
        # Also inspect the four selected upstream sources for the smaller build.
        wanted={"mingw-w64-lz4","mingw-w64-giflib","mingw-w64-libidn2","mingw-w64-zlib","mingw-w64-libpng","mingw-w64-leptonica","mingw-w64-tesseract-ocr"}
        for g in P["sources"]:
            if g["pkgbase"] in wanted:inspect_source(archive,keys,g)
        inventory={}
        for name in sorted(OWNERS):
            try:inventory[name]=notices(archive,keys,name)
            except Exception:inventory[name]={"package":name,"status":"BLOCKED_NOTICE","error":traceback.format_exc()[-2500:],"selected_for_distribution":False}
            OUT["package_license_inventory"]=inventory;save()
        for r in PE:
            OUT["runtime_files"].append({"path":r["file"],"sha256":r["sha256"],"actually_loaded":True,
                "source_and_full_license_refs":inventory[r["owner"]]})
        model=next(x for x in N["runtime_model_and_config"] if x["path"]=="tessdata/chi_sim.traineddata")
        OUT["runtime_files"].append({"path":model["path"],"sha256":model["sha256"],"actually_consumed":True,"source_and_full_license_refs":inventory[MODEL]})
        # TSV config is also explicitly mapped, distinct from the PE closure.
        tsv=next(x for x in N["runtime_model_and_config"] if x["path"]=="tessdata/configs/tsv")
        OUT["runtime_files"].append({"path":tsv["path"],"sha256":tsv["sha256"],"actually_consumed":True,"source_and_full_license_refs":inventory["mingw-w64-ucrt-x86_64-tesseract-ocr"]})
        row("actual loaded PE/model/config inventory with full notice references","OBSERVED",{"files":len(OUT["runtime_files"]),"owners":len(inventory),
          "without_full_text":[n for n,r in inventory.items() if not(r.get("full_package_notice_documents") or r.get("full_source_license_documents"))],
          "old_graph_selected":False})
        row("old 41-PE redistribution decision","NOT_SELECTED","Full dependency/maintenance and mixed linking obligations are excessive for local PNG OCR; no distribution clearance from notices alone.")
    except Exception:row("source decision","FAIL_OR_BLOCKED",traceback.format_exc()[-6000:])
    finally:shutil.rmtree(base);OUT["scratch_removed"]=not base.exists();OUT["completed"]=True;save()
    return int(not OUT["source_evidence"].get(MISSING[0]["pkgbase"],{}).get("model_exact_source_match",False))
if __name__=="__main__":raise SystemExit(main())
