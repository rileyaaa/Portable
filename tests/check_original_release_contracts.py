"""One exact original ZIP only: narrow high-risk launcher contracts.

No developer product files copied; no real credentials, external model, host
registry/policy changes, external-network sandbox test, device or GUI tests.
"""
import importlib.util,json,os,re,shutil,sys,traceback,urllib.parse,uuid,tomllib
from pathlib import Path
ROOT=Path(__file__).absolute().parents[1]
REPORT=Path(sys.argv[1]).absolute()
assert os.name=="nt" and sys.flags.isolated and os.environ["GITHUB_REPOSITORY"]=="rileyaaa/Portable"
spec=importlib.util.spec_from_file_location("original_release_audit",ROOT/"tests/audit_release_zip.py")
a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a)
a.REPORT=REPORT
a.META.update(tag=a.TAG,source_commit=a.FROZEN,source="exact original published ZIP",
    original_run="45739266926",new_harness_commit=os.environ["GITHUB_SHA"],completed=False,
    archive_sha256=a.ASSETS[a.ZIP][1],scope="selected actual launcher contracts; original release evidence only",
    static_contract_index="tests/original_release_136_env_contracts.json",
    limits=["Synthetic API loopback only; no genuine login or credentials.",
       "No actual official Apps/connector auth, plugin activation, WebSocket, or system-policy opt-in.",
       "Protected override rejection does not establish external network isolation.",
       "Native child absence/normalized values are inheritance boundary evidence only; not proof of each variable's independent tool consumption.",
       "No writes to original attachment, source payload, registry or host policy; owned extracted fixture only."])
entry="\u542f\u52a8Codex.bat"
MODEL="gpt-6.2-sol"
SYNTHETIC="synthetic-offline-not-a-real-key"
MARK="ORIGINAL_TARGETED_MODEL_INSTRUCTIONS_MARKER_45739266926"
args=["--portable-auth=api","exec","--skip-git-repo-check","--json","Run authorized local synthetic launcher contract probe."]
COVERS=[entry,"env.ps1","run-codex.ps1","codex.exe"]
selected=json.loads((ROOT/"tests/original_release_136_env_contracts.json").read_bytes())
assert selected["metadata"]["original_zip_sha256"]==a.ASSETS[a.ZIP][1] and len(selected["variables"])==136
assert selected["metadata"]["frozen_source"]==a.FROZEN

CONSUMER=r'''
import json,os,sys,tomllib
from pathlib import Path
root=Path(os.environ["CODEX_INSTALL_DIR"]).resolve()
work=root/"work/tool-probe"
assert Path(sys.executable).resolve()==root/"tool/python/python.exe" and sys.flags.isolated
assert Path(os.environ["CODEX_HOME"]).resolve()==root/"home"
names=("CODEX_API_KEY","CODEX_ACCESS_TOKEN","GH_TOKEN","GITHUB_TOKEN","NODE_OPTIONS","NODE_PATH","NODE_EXTRA_CA_CERTS")
checks={n:n not in os.environ for n in names}
assert all(checks.values()),[n for n,v in checks.items() if not v]
# Presence of host preload would create an external owned marker, which the
# supervisor independently checks. Do not execute or access any host file.
cfg=tomllib.loads((root/"home/config.toml").read_text(encoding="utf-8-sig"))
features=cfg["features"]
assert features.get("apps") is False and features.get("plugins") is False and features.get("plugin_sharing") is False
(work/"targeted-contract-results.json").write_text(json.dumps({"native_child_host_inputs_absent":checks,
    "features":{n:features[n] for n in ("apps","plugins","plugin_sharing")}}),encoding="utf-8")
print("PORTABLE_RELEASE_FULL_CONSUMER_DONE",flush=True)
'''

def cases(owned,fixture):
    a.ROOT=fixture
    a.setup_helpers(owned)
    a.core.MAX_CELL_WAITS=15
    work=fixture/"work/tool-probe";work.mkdir(parents=True,exist_ok=False)
    (work/"documents.py").write_text(CONSUMER,encoding="utf-8")
    home=fixture/"home";instructions=home/"synthetic-contract-instructions.md"
    instructions.write_text(MARK+"\n",encoding="utf-8")
    outside=owned/"synthetic-outside-instructions.md";outside.write_text("owned outside marker",encoding="ascii")
    outside_catalog=owned/"must-not-create-catalog.json";assert not outside_catalog.exists()
    # Harmless synthetic host Node preload, which must not run. No payload
    # reads, external writes, network or access to actual user files.
    host_marker=owned/"synthetic-host-preload-executed.txt"
    preload=owned/"synthetic-host-preload.cjs"
    preload.write_text("require('node:fs').writeFileSync("+json.dumps(str(host_marker))+",'synthetic')",encoding="utf-8")
    env=a.clean_env()
    env.update(PORTABLE_TEST_HEADER="synthetic-parent-conflict",PORTABLE_TEST_MISSING_HEADER="synthetic-parent-only",
      CODEX_API_KEY="synthetic-parent-codex-key",CODEX_ACCESS_TOKEN="synthetic-parent-access-token",
      OPENAI_API_KEY="synthetic-parent-openai-key",OPENAI_BASE_URL="http://127.0.0.1:1/v1",
      GH_TOKEN="synthetic-parent-gh",GITHUB_TOKEN="synthetic-parent-github",
      NODE_OPTIONS="--require="+str(preload),NODE_PATH=str(owned/"not-a-package"),NODE_EXTRA_CA_CERTS=str(owned/"not-a-certificate.pem"))
    a.m.MODEL_REQUESTS.clear();a.m.MODEL_ERRORS.clear()
    handler=a.handler_for(fixture)
    assertions={"auth":0,"query":0,"instruction":0}
    def checked_handler(body,url):
        if not assertions["instruction"]:
            # First actual Responses request, not just generated TOML.
            content=json.dumps({"instructions":body.get("instructions"),"input":body.get("input")},ensure_ascii=False)
            assert MARK in content,"local model instructions did not reach actual model request"
            assertions["instruction"]+=1
        return handler(body,url)
    Parent=a.m.provider("",model=MODEL,handler=checked_handler,
       expected_headers={"X-Portable-Audit":"synthetic-package-value","X-Portable-Audit-Static":"synthetic-static"},
       forbidden_headers=("X-Portable-Host-Only",),max_requests=30)
    class Peer(Parent):
        def do_POST(self):
            try:
                u=urllib.parse.urlsplit(self.path)
                assert u.path=="/v1/responses"
                assert urllib.parse.parse_qs(u.query)=={"portable_contract":["synthetic-query"]},"configured query absent/different"
                assert self.headers.get("Authorization")=="Bearer "+SYNTHETIC,"synthetic authentication conflict"
                assertions["query"]+=1;assertions["auth"]+=1
                self.path=u.path
            except Exception as exc:
                a.m.MODEL_ERRORS.append(str(exc));self.send_error(400,"Synthetic contract mismatch");return
            return super().do_POST()
    with a.m.serving(Peer) as port:
        extra=('$env:CODEX_MODEL_INSTRUCTIONS_FILE = "synthetic-contract-instructions.md"\n'
               '$env:CODEX_QUERY_PARAMS_TOML = \'{ portable_contract = "synthetic-query" }\'\n'
               '$env:CODEX_ENABLE_PLUGINS = "true"\n'
               '$env:CODEX_ENABLE_PLUGIN_SHARING = "true"\n'
               '$env:CODEX_DISABLE_APPS = "true"\n')
        a.api_config(fixture,port,MODEL,"normal",extra)
        local=fixture/"env.local.ps1";good=local.read_bytes()
        # Separate early stop cases; each preserves original launcher bytes.
        invalid=[("CODEX_API_KEY","synthetic-invalid-local-key"),
                 ("CODEX_ACCESS_TOKEN","synthetic-invalid-local-access"),
                 ("CODEX_PORTABLE_ALLOW_HOST_PATH","true"),
                 ("CODEX_SANDBOX_NETWORK_ACCESS","true"),
                 ("NODE_OPTIONS","--require=synthetic-not-executed")]
        for name,value in invalid:
            before=len(a.m.MODEL_REQUESTS)
            local.write_bytes(good+('\n$env:'+name+' = "'+value+'"\n').encode("utf-8"))
            try:
                rc,out,err=a.bat(fixture,entry,args,env,timeout=120)
                ok=rc!=0 and name.lower() in (out+err).lower() and len(a.m.MODEL_REQUESTS)==before and not host_marker.exists()
                a.row("normal","protected/unapproved local override rejected "+name,"PASS_ACTUAL" if ok else "FAIL",
                    "launcher early rejection; no synthetic model request; rc="+str(rc),COVERS,[name])
            except Exception:a.row("normal","protected/unapproved local override rejected "+name,"FAIL",traceback.format_exc()[-1800:],COVERS,[name])
            finally:local.write_bytes(good)
        for name,path in (("CODEX_MODEL_INSTRUCTIONS_FILE",outside),("CODEX_MODEL_CATALOG_JSON",outside_catalog)):
            before=len(a.m.MODEL_REQUESTS);outside_bytes=outside.read_bytes()
            # Remove original instructions assignment before the negative
            # replacement; catalog setting has no existing assignment here.
            lines=[x for x in good.decode("utf-8").splitlines() if not x.startswith("$env:"+name+" =")]
            local.write_text("\n".join(lines)+'\n$env:'+name+' = "'+str(path)+'"\n',encoding="utf-8")
            try:
                rc,out,err=a.bat(fixture,entry,args,env,timeout=160)
                ok=(rc!=0 and (name.lower() in (out+err).lower() or str(path).lower() in (out+err).lower())
                    and len(a.m.MODEL_REQUESTS)==before and outside.read_bytes()==outside_bytes and not outside_catalog.exists())
                a.row("normal","package-boundary rejection "+name,"PASS_ACTUAL" if ok else "FAIL",
                    "actual launcher stopped; owned outside input unchanged/no output; rc="+str(rc),COVERS,[name])
            except Exception:a.row("normal","package-boundary rejection "+name,"FAIL",traceback.format_exc()[-1800:],COVERS,[name])
            finally:local.write_bytes(good)
        # One actual native session; not another all-tool or ACL matrix.
        a.m.MODEL_REQUESTS.clear();a.m.MODEL_ERRORS.clear()
        rc,out,err=a.bat(fixture,entry,args,env,timeout=550)
        q=work/"targeted-contract-results.json"
        actual=json.loads(q.read_bytes()) if q.exists() else {}
        if assertions["auth"] and assertions["query"]:
            a.row("normal","actual configured query on local Responses","PASS_ACTUAL",str(assertions["query"])+" matching local requests",COVERS,["CODEX_QUERY_PARAMS_TOML"])
            a.row("normal","actual local synthetic Authorization despite host auth/base conflicts","PASS_ACTUAL","matched expected package key and configured local peer; no values stored",COVERS,["OPENAI_API_KEY","CODEX_API_KEY","CODEX_ACCESS_TOKEN","OPENAI_BASE_URL"])
        else:a.row("normal","actual synthetic request authentication/query","FAIL","no matching actual local request",COVERS,["OPENAI_API_KEY","CODEX_QUERY_PARAMS_TOML"])
        if assertions["instruction"]:
            a.row("normal","actual package-local model instruction marker in Responses","PASS_ACTUAL","marker in actual request",COVERS,["CODEX_MODEL_INSTRUCTIONS_FILE"])
        else:a.row("normal","actual package-local model instruction marker in Responses","FAIL","no matching request marker",COVERS,["CODEX_MODEL_INSTRUCTIONS_FILE"])
        checks=actual.get("native_child_host_inputs_absent",{})
        for n in ("CODEX_API_KEY","CODEX_ACCESS_TOKEN","GH_TOKEN","GITHUB_TOKEN","NODE_OPTIONS","NODE_PATH","NODE_EXTRA_CA_CERTS"):
            a.row("normal","actual native child inherited-host rejection "+n,"PASS_ACTUAL" if checks.get(n) is True else "FAIL",
                "negative inheritance boundary only; not independent tool activation",COVERS,[n])
        a.row("normal","host Node preload marker absent","PASS_ACTUAL" if not host_marker.exists() and checks.get("NODE_OPTIONS") else "FAIL",
            "owned synthetic preload did not execute; no arbitrary user script",COVERS,["NODE_OPTIONS"])
        if actual.get("features")=={"apps":False,"plugins":False,"plugin_sharing":False}:
            a.row("normal","feature config gate without explicit extension opt-in","PASS_CONFIG_GATE",
              "actual launched child read apps/plugins/plugin_sharing=false; real plugin execution and official connector authorization NOT tested",
              COVERS,["CODEX_DISABLE_APPS","CODEX_ENABLE_PLUGINS","CODEX_ENABLE_PLUGIN_SHARING"])
        else:a.row("normal","feature config gate without explicit extension opt-in","FAIL","feature values not verified",COVERS,["CODEX_DISABLE_APPS","CODEX_ENABLE_PLUGINS","CODEX_ENABLE_PLUGIN_SHARING"])
        completed=(rc==0 and not a.m.MODEL_ERRORS and "release-full-native-audit-completed" in out and handler.continuation and handler.continuation.finished)
        a.row("normal","actual original native session completion","PASS_ACTUAL" if completed else "FAIL",
            "local synthetic Responses session; rc="+str(rc)+"; model_errors="+str(len(a.m.MODEL_ERRORS)),COVERS)
    assert outside.read_text()=="owned outside marker" and not outside_catalog.exists()
    for n in ("env.ps1","run-codex.ps1",entry,"codex.exe","codex-code-mode-host.exe"):
        assert a.digest(fixture/n)==a.MEMBERS[n]["sha256"],n
    a.row("integrity","original launcher/binary members unchanged after targeted cases","PASS_ACTUAL","no developer payload copied")
def main():
    a.guard()
    owned=ROOT/"tmp"/("original-contract-"+uuid.uuid4().hex[:8]);owned.mkdir()
    try:
        manifest=a.download(owned);a.MEMBERS=manifest["files"];a.ROOT=a.extract(owned,manifest)
        a.row("integrity","exact original ZIP and all 9076 members, real Chinese-space move","PASS_ACTUAL",len(a.MEMBERS))
        cases(owned,a.ROOT);a.META["completed"]=True
    except Exception:a.row("harness","targeted original contract probe","FAIL",traceback.format_exc()[-6000:])
    finally:a.save();a.ancestors(owned);shutil.rmtree(owned)
    return int(not a.META["completed"] or any(x["status"]=="FAIL" for x in a.ROWS))
if __name__=="__main__":
    for stream in (sys.stdout,sys.stderr):stream.reconfigure(encoding="utf-8",errors="backslashreplace")
    raise SystemExit(main())
