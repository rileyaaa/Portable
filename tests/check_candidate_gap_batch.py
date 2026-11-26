"""Intermediate candidate gap matrix, not an all-package final acceptance.
Build one exact ordinary customer ZIP and use existing real BAT/Codex/Host
synthetic peer for three modes. Preserve old original-release index unchanged.
"""
import collections,hashlib,importlib.util,json,os,re,shutil,subprocess,sys,traceback,uuid
from pathlib import Path
ROOT=Path(__file__).absolute().parents[1]
REPORT=Path(sys.argv[1]).absolute()
INDEX=Path(sys.argv[2]).absolute()
START=os.environ["GITHUB_SHA"]
assert os.name=="nt" and os.environ["GITHUB_REPOSITORY"]=="rileyaaa/Portable"
assert os.environ["GITHUB_REF"]=="refs/heads/dev/stable-tool-refresh"
assert Path(sys.executable).resolve()==ROOT/"tool/python/python.exe"
def load(n,p):
    spec=importlib.util.spec_from_file_location(n,ROOT/"tests"/p)
    mod=importlib.util.module_from_spec(spec);sys.modules[n]=mod;spec.loader.exec_module(mod);return mod
a=load("candidate_targeted_audit","audit_release_zip.py")
c=load("candidate_targeted_extract","check_course_assistant.py")
a.core=load("candidate_targeted_peer","check_codex_tool_discovery.py");a.m=a.core.m
a.core.MAX_CELL_WAITS=25
a.REPORT=REPORT
OLD=ROOT/"tests/original_release_45739266926_coverage.json"
old_raw=OLD.read_bytes();old=json.loads(old_raw)
missing={x["name"] for x in old["environment"] if x["classification"]=="\u672a\u9a8c"}
assert len(missing)==122 and len(old["environment"])==171
a.META.update(source_commit=START,run_id=os.environ["GITHUB_RUN_ID"],scope="intermediate defect validation, exact candidate only",completed=False,
    original_index_sha256=hashlib.sha256(old_raw).hexdigest(),old_env_missing_count=122,
    final_regression=False,known_limits_not_overridden=True,
    limitations=["Synthetic loopback Responses; actual client/Host execution, not live model autonomy.",
      "Known SSH restricted ACL and Android Unicode failures are retained as FAIL if reproduced.",
      "No actual remote/device, Office renderer, install, host profile probe or elevation.",
      "YOLO deliberately disables the sandbox; path routing does not establish write isolation.",
      "Only selected consumers in this batch; prior original/other candidate rows are not promoted."])
def row(mode,item,status,detail="",covers=(),env=(),packages=()):
    a.row(mode,item,status,detail,covers,env,packages)
def mode(base,fixture,files,name):
    a.ROOT=fixture
    a.core.SKILLS={p.parent.name for p in (fixture/"home/skills").glob("*/SKILL.md") if not p.parent.name.startswith(".")}
    entry=a.mode_files(fixture,name)
    work=fixture/"work/tool-probe";work.mkdir(parents=True,exist_ok=False)
    (work/"documents.py").write_text("MODE="+repr(name)+"\n"+(ROOT/"tests/candidate_gap_consumer.py").read_text(encoding="utf-8"),encoding="utf-8")
    a.m.MODEL_REQUESTS.clear();a.m.MODEL_ERRORS.clear();handler=a.handler_for(fixture);model="gpt-6.2-sol"
    with a.m.serving(a.m.provider("",model=model,handler=handler,
        expected_headers={"X-Portable-Audit":"synthetic-package-value","X-Portable-Audit-Static":"synthetic-static"},
        forbidden_headers=("X-Portable-Host-Only",),max_requests=35)) as port:
        extra=('$env:CODEX_REASONING_EFFORT = "low"\n'+
               ('$env:CODEX_PROXY_ENABLED = "false"\n' if name=="yolo" else ""))
        a.api_config(fixture,port,model,name,extra)
        env=a.clean_env();env["PORTABLE_TEST_HEADER"]="synthetic-parent-conflict";env["PORTABLE_TEST_MISSING_HEADER"]="synthetic-parent-only"
        outside=base/("synthetic-parent-"+name);outside.mkdir()
        for k in ("HOME","USERPROFILE","TEMP","TMP","APPDATA","LOCALAPPDATA"):
            env[k]=str(outside)
        env["PIP_CONFIG_FILE"]=str(outside/"pip.ini")
        (outside/"pip.ini").write_text("[global]\ntimeout=23\n",encoding="ascii")
        before={p.name:c.digest(p) for p in outside.iterdir()}
        rc,out,err=a.bat(fixture,entry,["--portable-auth=api","exec","--skip-git-repo-check","--json","Run targeted owned synthetic candidate tests."],env,timeout=850)
    result=work/"targeted-results.jsonl"
    if result.is_file():
        for line in result.read_text(encoding="utf-8").splitlines():
            r=json.loads(line);assert r["mode"]==name
            row(name,r["item"],r["status"],r["detail"],r["covers"],r["env"],r["packages"])
    assert rc==0 and not a.m.MODEL_ERRORS and "release-full-native-audit-completed" in out and handler.continuation.finished,(rc,a.m.MODEL_ERRORS,out[-2000:],err[-1800:])
    row(name,"actual BAT/Codex/Host targeted consumer completed","PASS_ACTUAL","real synthetic Responses, child terminal status; not all rows pass",[entry,"codex.exe","codex-code-mode-host.exe"])
    efforts=[(b.get("reasoning") or {}).get("effort") for b in a.m.MODEL_REQUESTS]
    row(name,"actual configured reasoning effort in Responses","PASS_ACTUAL" if efforts and all(x=="low" for x in efforts) else "FAIL",
        {"expected":"low","observed":efforts},["run-codex.ps1","codex.exe"],["CODEX_REASONING_EFFORT"])
    assert before=={p.name:c.digest(p) for p in outside.iterdir() if p.is_file()} and len(list(outside.iterdir()))==1
    row(name,"synthetic parent profile/config sentinel unchanged","PASS_ACTUAL","only owned fixture observed; not full OS audit")
    changed=[]
    for n,r in files.items():
        p=fixture/n
        if name=="yolo" and n=="env.ps1":
            assert p.read_bytes()==(fixture/"Version_History/YOLO mode\u4e13\u7528\u5305-env.ps1").read_bytes()
            continue
        try:c.plain(p);assert p.stat().st_size==r["size"] and c.digest(p)==r["sha256"]
        except (AssertionError,OSError):changed.append(n)
    row(name,"all other shipped member bytes after native use","PASS_ACTUAL" if not changed else "FAIL",
        {"changed":changed,"intentional_yolo_env_selection":name=="yolo"})
def index(fixture,files):
    a.ROOT=fixture;a.MEMBERS=files
    a.inventory()
    vars={v["name"]:v for v in a.META["environment_inventory"]}
    old_vars={v["name"]:v for v in old["environment"]}
    def evidence(key,field):
        return [{"row":i+1,"mode":r["mode"],"item":r["item"],"status":r["status"]} for i,r in enumerate(a.ROWS) if key in r[field]]
    def classify(ev):
        statuses={x["status"] for x in ev}
        if "FAIL" in statuses:return "FAIL"
        if "PASS_ACTUAL" in statuses and "KNOWN_LIMIT" in statuses:return "PASS_ACTUAL_WITH_LIMIT"
        if "PASS_ACTUAL" in statuses:return "PASS_ACTUAL"
        if statuses:return "LIMIT_OR_OTHER_EVIDENCE"
        return "UNTESTED"
    environments=[]
    for n in sorted(set(vars)|set(old_vars)):
        v=vars.get(n,{})
        ev=evidence(n,"env")
        environments.append({"name":n,"original_classification":old_vars.get(n,{}).get("classification"),
            "original_missing_actual":n in missing,"current_source_references":v.get("source_references",[]),
            "original_source_references":old_vars.get(n,{}).get("source_references",[]),
            "current_scan":"REFERENCED_OR_PROBED" if n in vars else "NOT_REFERENCED_IN_STATIC_SCAN",
            "status":classify(ev),"evidence":ev})
    assert sum(x["original_missing_actual"] for x in environments)==122
    old_entries={x["path"]:x for x in old["entries"]}
    current_entries={x["path"]:x for x in a.META["entry_inventory"]}
    entries=[]
    for p,v in sorted(current_entries.items()):
        ev=evidence(p,"covers")
        entries.append({"path":p,"sha256":files[p]["sha256"],"original_classification":old_entries.get(p,{}).get("classification"),
            "inventory_status":v["status"],"status":classify(ev),"evidence":ev})
    packages=[]
    for v in a.META["python_distribution_inventory"]:
        ev=evidence(v["name"],"packages")
        packages.append({**v,"status":classify(ev),"evidence":ev})
    browser=(fixture/"tool/automation/browser-bridge.js").read_text(encoding="utf-8")
    course=(fixture/"tool/automation/course/course.js").read_text(encoding="utf-8")
    allow=re.search(r"const allowedTools = new Set\(\[([\s\S]*?)\]\);",browser)
    defs=re.search(r"const tools = \{([\s\S]*?)\n\};",course)
    assert allow and defs
    browser_names=set(re.findall(r"'(browser_[a-z_]+)'",allow[1]))
    course_names=set(re.findall(r"(?m)^\s*(course_[a-z_]+):spec\(",defs[1]))
    assert browser_names and course_names
    old_mcp={x["name"]:x for x in old["mcp_tools"]}
    mcp=[{"name":n,"family":"course" if n in course_names else "browser",
          "declared_current":n in browser_names|course_names,"original_classification":old_mcp.get(n,{}).get("classification"),
          "status":"UNTESTED","evidence":[],"scope":"source declaration/allowlist only, actual negotiated list and tool calls not tested in this batch"}
          for n in sorted(browser_names|course_names|set(old_mcp))]
    result={"format":1,"source_commit":START,"archive_sha256":a.META["archive_sha256"],"manifest_sha256":a.META["manifest_sha256"],
      "run_id":os.environ["GITHUB_RUN_ID"],"file_count":len(files),"final_regression":False,
      "scope":"exact candidate only; per-row evidence, no old status promoted; PASS_ACTUAL is scoped, not every option or mode",
      "original_index_sha256":a.META["original_index_sha256"],"environment":environments,"entries":entries,
      "original_entries_absent_from_candidate":sorted(set(old_entries)-set(current_entries)),
      "python_distributions":packages,"npm_packages":a.META["npm_package_inventory"],"mcp_tools":mcp,
      "raw_rows":a.ROWS,"limitations":a.META["limitations"],
      "counts":{"env":dict(collections.Counter(x["status"] for x in environments)),
                "previous_122":dict(collections.Counter(x["status"] for x in environments if x["original_missing_actual"])),
                "entries":dict(collections.Counter(x["status"] for x in entries))}}
    INDEX.write_text(json.dumps(result,ensure_ascii=True,indent=2)+"\n",encoding="utf-8")
    a.META["candidate_coverage_counts"]=result["counts"];a.save()
def main():
    owned=None
    try:
        parent=ROOT/"tmp";parent.mkdir(exist_ok=True);c.ancestors(parent)
        a.save()
        raw=subprocess.check_output([str(ROOT/"tool/python/python.exe"),"-I","-B",str(ROOT/"tool/package-release.py"),"--version","v0.172.0-portable.2"],cwd=ROOT,timeout=1200)
        info=json.loads(raw);assert info["source_commit"]==START
        a.META.update(archive_sha256=info["archive_sha256"],file_count=info["file_count"],archive_size=info["archive_bytes"])
        a.META["manifest_sha256"]=c.digest(Path(info["manifest"]));a.save()
        owned=parent/("candidate-gap-"+uuid.uuid4().hex[:8]);owned.mkdir()
        # Retain one pristine inventory witness. All three mode runs extract
        # independently from the SAME exact ZIP, never from a modified tree.
        for name in ("normal","yolo","maintenance"):
            folder=owned/name;folder.mkdir()
            try:
                c.REPORT=folder/"extract.json";c.ROWS.clear();c.META.clear()
                fixture,files=c.extract(info,folder)
                assert c.META["archive_sha256"]==a.META["archive_sha256"]
                row(name,"same exact intermediate ZIP, member hash and Chinese-space move","PASS_ACTUAL",len(files))
                if name=="normal":
                    witness=owned/"inventory-witness";shutil.copytree(fixture,witness);c.verify(witness,files)
                mode(folder,fixture,files,name)
            except Exception:row(name,"targeted native harness","FAIL",traceback.format_exc())
            finally:
                c.ancestors(folder);shutil.rmtree(folder)
        index(witness,files)
        assert OLD.read_bytes()==old_raw
        a.META["completed"]=True
    except Exception:row("harness","candidate gap batch","FAIL",traceback.format_exc())
    finally:
        if owned and owned.exists():
            try:c.ancestors(owned);shutil.rmtree(owned);a.META["scratch_removed"]=True
            except Exception:row("harness","scratch removal","FAIL",traceback.format_exc())
        a.META["failure_rows"]=sum(r["status"]=="FAIL" for r in a.ROWS);a.save()
    return int(not (a.META["completed"] and a.META.get("scratch_removed") and INDEX.is_file()))
if __name__=="__main__":
    for s in (sys.stdout,sys.stderr):s.reconfigure(encoding="utf-8",errors="backslashreplace")
    raise SystemExit(main())
