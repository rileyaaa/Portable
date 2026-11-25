"""One-time CI: audited official pip/certifi wheels for GHSA-6q48-6c7w-9gw2."""
import ast, base64, configparser, csv, email.parser, hashlib, importlib.metadata as md, io, json, os
from pathlib import Path, PurePosixPath
import re, shutil, stat, subprocess, sys, tempfile, urllib.parse, urllib.request, zipfile
from packaging.specifiers import SpecifierSet
from packaging.version import Version

for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8", errors="backslashreplace")
assert os.name == "nt" and sys.flags.isolated and sys.flags.ignore_environment
assert os.environ.get("GITHUB_ACTIONS") == "true"
assert os.environ.get("GITHUB_REPOSITORY") == "rileyaaa/Portable"
assert os.environ.get("GITHUB_REF") == "refs/heads/dev/stable-tool-refresh"
assert not subprocess.check_output(["git","status","--porcelain=v1","--untracked-files=all"])
root = Path.cwd()
site = root / "tool/python/Lib/site-packages"
py = root / "tool/python/python.exe"
assert sys.version_info[:3] == (3,14,10) and Path(sys.executable).resolve() == py
specs = {
 "pip": {"old":"26.1.2","version":"26.3","license":"MIT","oldhash":"382ff9f685ee3bc25864f820aa50505825f10f5458ffff07e30a6d96e5715cab","sha256":"f3b60b20ffaadd4415ed7957212a38ac63fa4c5fa375bd0f4a797777940fad13","url":"https://files.pythonhosted.org/packages/07/25/ee8c38ae72d66b844ce8eb9711ba905dba21ca1a8a0c960057c41cd23337/pip-26.3-py3-none-any.whl"},
 "certifi":{"old":"2026.5.20","version":"2026.11.20","license":"MPL-2.0","oldhash":"3c52e209ba0a4ad7aebe60436a4ab349c39e1e602e8c134221e546902ad25897","sha256":"7422df25243767b9877031a2248cb14d09ddac9beee846f4cef3d5c9191d488f","url":"https://files.pythonhosted.org/packages/6d/39/5eec3296860b94ac20bb8ed807725b88f6adfab3f343df592afd975f5f86/certifi-2026.11.20-py3-none-any.whl"}
}
launchers = {"bin/pip.exe","bin/pip3.exe","bin/pip3.14.exe"}
def sha(data): return hashlib.sha256(data).hexdigest()
def rh(data): return "sha256="+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
def plain(p, directory=False):
    info=p.lstat()
    assert not stat.S_ISLNK(info.st_mode) and not getattr(info,"st_file_attributes",0)&0x400, "Linked maintenance path"
    assert stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink==1
def pathsafe(name):
    assert isinstance(name,str) and name and not name.startswith("/") and "\\" not in name and ":" not in name
    assert all(p not in ("",".","..") and not p.endswith((" ",".")) for p in name.split("/"))
    return name
def treefiles(parent, prefix):
    start=parent/prefix
    plain(start,True)
    result=set()
    for current, dirs, files in os.walk(start,followlinks=False):
        c=Path(current)
        for d in dirs: plain(c/d,True)
        for f in files:
            p=c/f
            plain(p)
            result.add(p.relative_to(parent).as_posix())
    return result
def rows(raw):
    result={}
    for row in csv.reader(io.StringIO(raw.decode("utf-8-sig"),newline="")):
        assert len(row)==3 and row[0] not in result, "Malformed or duplicate RECORD row"
        result[row[0]]=tuple(row[1:])
    return result
def info_at(parent,n,v):
    return parent/(n+"-"+v+".dist-info")
def distributions():
    found={}
    for d in md.distributions(path=[str(site)]):
        name=d.metadata["Name"].lower().replace("_","-")
        assert name not in found
        found[name]=d.version
    return found
def git(*a):
    return subprocess.check_output(["git",*a],cwd=root)
def listing(*a):
    return set(git(*a).decode("utf-8").split("\0"))-{""}
for p in (*reversed(site.parents),site):
    plain(p,True)
old_versions=distributions()
assert len(old_versions)==49
tracked=listing("ls-files","-z")
site_rel=site.relative_to(root).as_posix()+"/"
old_records={}
old_entry_points=None
old_launchers={}
for name,s in specs.items():
    assert old_versions[name]==s["old"]
    dist=name+"-"+s["old"]+".dist-info"
    old_set=treefiles(site,name)|treefiles(site,dist)
    if name=="pip": old_set|=launchers
    record=dist+"/RECORD"
    rr=rows((site/record).read_bytes())
    assert set(rr)==old_set, "Old RECORD and owned files differ: "+name
    for f,(digest,size) in rr.items():
        pathsafe(f)
        assert site_rel+f in tracked, "Unexpected untracked owned file"
        plain(site/f)
        if f==record:
            assert (digest,size)==("","")
        else:
            data=(site/f).read_bytes()
            assert (digest,size)==(rh(data),str(len(data))), "Old installed RECORD mismatch: "+f
    old_records[name]=old_set
    if name=="pip":
        old_entry_points=(site/dist/"entry_points.txt").read_bytes()
        old_launchers={p:(site/p).read_bytes() for p in launchers}
print("BASELINE_49_DISTRIBUTIONS_AND_OLD_RECORD_OWNERSHIP=PASS",flush=True)
# Audit tracked project Python/PowerShell/CMD/BAT sources before
# changing the fixture. Vendor payloads are excluded; no credential
# content or matching source text is printed.
source_paths=("*.py","*.ps1","*.cmd","*.bat",":(exclude)tool/python/**",":(exclude)tool/node/**",":(exclude)tool/automation/playwright/node_modules/**",":(exclude)tool/automation/browsers/**",":(exclude)tool/android/platform-tools/**",":(exclude)tool/7zip/**",":(exclude)tests/**")
scan=subprocess.run(["git","grep","-l","-I","-E",r"pip\._internal\.configuration|from pip\._internal import .*configuration|\.kinds\.(GLOBAL|USER|SITE|ENV|ENV_VAR)","--",*source_paths],cwd=root,capture_output=True)
assert scan.returncode in (0,1), "Project source dependency scan failed"
assert not scan.stdout.strip(), "Production source depends on pip's internal config API: "+scan.stdout.decode("utf-8","replace")
print("PROJECT_PRODUCTION_PIP_CONFIG_INTERNAL_API_SCAN=PASS",flush=True)
fixture_path=root/"tests/test_pip_config_isolation.py"
# Git blob identity, not an unchecked overwrite.
assert git("hash-object",str(fixture_path)).decode().strip()=="f4e8ebc0aa3c4a65abc6a6bf129683c7f868dc1c"
fixture_path.write_text("\"\"\"Exercise the bundled pip config loader and CLI with synthetic files only.\"\"\"\nfrom pathlib import Path\nimport os\nimport stat\nimport subprocess\nimport sys\nimport tempfile\nimport unittest\n\n\nROOT = Path(__file__).absolute().parents[1]\n\n\nclass PipConfigIsolationTests(unittest.TestCase):\n    def test_devnull_suppresses_all_config_files_even_in_isolated_mode(self):\n        for path in (*reversed(ROOT.parents), ROOT):\n            info = path.lstat()\n            self.assertTrue(stat.S_ISDIR(info.st_mode))\n            self.assertFalse(getattr(info, \"st_file_attributes\", 0) & 0x400)\n        scratch = ROOT / \"tmp\"\n        if not scratch.exists() and not scratch.is_symlink():\n            scratch.mkdir()\n        info = scratch.lstat()\n        self.assertTrue(stat.S_ISDIR(info.st_mode))\n        self.assertFalse(getattr(info, \"st_file_attributes\", 0) & 0x400)\n        with tempfile.TemporaryDirectory(prefix=\"pip-config-\", dir=scratch) as fixture:\n            owned = Path(fixture)\n            global_config = owned / \"synthetic-global-pip.ini\"\n            user_config = owned / \"synthetic-user-pip.ini\"\n            site_config = owned / \"synthetic-site-pip.ini\"\n            global_config.write_text(\"[install]\\ntarget = synthetic-outside-target\\n\", encoding=\"utf-8\")\n            user_config.write_text(\"[portable-ci]\\nuser-marker = synthetic-user-marker\\n\", encoding=\"utf-8\")\n            site_config.write_text(\"[portable-ci]\\nsite-marker = synthetic-site-marker\\n\", encoding=\"utf-8\")\n            original = {p: p.read_bytes() for p in (global_config, user_config, site_config)}\n            code = r'''\nimport os, runpy, sys\nfrom contextlib import nullcontext\nfrom pathlib import Path\nfrom unittest.mock import patch\n\nsite, global_file, user_file, site_file, isolated_arg, devnull_arg = sys.argv[1:]\nsys.path.insert(0, site)\nimport pip\nfrom pip._internal import configuration as c\nassert Path(pip.__file__).resolve().is_relative_to(Path(site).resolve())\n# pip 26.1 uses kinds; 26.3 replaces it with the str-backed Kind enum.\n# Only the synthetic discovery boundary needs the internal type.\nkinds = c.kinds if hasattr(c, \"kinds\") else c.Kind\nlocations = {kinds.GLOBAL: [global_file], kinds.USER: [user_file], kinds.SITE: [site_file]}\nisolated = isolated_arg == \"1\"\ndevnull = devnull_arg == \"1\"\nassert (os.environ.get(\"PIP_CONFIG_FILE\") == os.devnull) == devnull\nif not devnull:\n    assert \"PIP_CONFIG_FILE\" not in os.environ\n# Replace discovery, not the config loader, CLI parser, or upstream protection.\n# Never read/probe actual host or user configuration paths.\nwith patch.object(c, \"get_configuration_files\", return_value=locations):\n    guard = patch.object(c.Configuration, \"_load_file\", side_effect=AssertionError(\"Config file read\")) if devnull else nullcontext()\n    with guard:\n        config = c.Configuration(isolated=isolated)\n        config.load()\n        if not devnull:\n            assert config.get_value(\"install.target\") == \"synthetic-outside-target\"\n        else:\n            assert \"install.target\" not in dict(config.items())\n        # Run the real public CLI entry point in this dedicated subprocess.\n        # Only discovery is simulated; config loading/printing are real.\n        sys.argv = [\"pip\"] + ([\"--isolated\"] if isolated else []) + [\"--disable-pip-version-check\", \"--no-input\", \"config\", \"list\"]\n        runpy.run_module(\"pip\", run_name=\"__main__\")\n'''\n            # Preserve only essential process variables; no real pip/user\n            # configuration or credentials in the child environment.\n            base_env = {key: os.environ[key] for key in\n                        (\"SystemRoot\", \"WINDIR\", \"SystemDrive\", \"ComSpec\", \"PATHEXT\",\n                         \"OS\", \"PROCESSOR_ARCHITECTURE\") if key in os.environ}\n            for key, name in ((\"HOME\", \"home\"), (\"USERPROFILE\", \"home\"),\n                              (\"APPDATA\", \"appdata\"), (\"LOCALAPPDATA\", \"localappdata\"),\n                              (\"PROGRAMDATA\", \"programdata\"), (\"ALLUSERSPROFILE\", \"programdata\"),\n                              (\"TEMP\", \"temp\"), (\"TMP\", \"temp\"), (\"TMPDIR\", \"temp\"),\n                              (\"PIP_CACHE_DIR\", \"cache\")):\n                directory = owned / name\n                directory.mkdir(exist_ok=True)\n                base_env[key] = str(directory)\n            for isolated in (False, True):\n                for devnull in (False, True):\n                    with self.subTest(isolated=isolated, devnull=devnull):\n                        env = base_env.copy()\n                        if devnull:\n                            env[\"PIP_CONFIG_FILE\"] = os.devnull\n                        result = subprocess.run(\n                            [sys.executable, \"-B\", \"-c\", code,\n                             str(ROOT / \"tool/python/Lib/site-packages\"),\n                             str(global_config), str(user_config), str(site_config),\n                             str(int(isolated)), str(int(devnull))],\n                            cwd=owned, env=env, capture_output=True,\n                            encoding=\"utf-8\", errors=\"replace\", timeout=45,\n                        )\n                        self.assertEqual(result.returncode, 0, result.stderr)\n                        # Positive controls: isolated mode alone does not\n                        # suppress global/site config, but does suppress user config.\n                        # Negative control: devnull suppresses all three, even isolated.\n                        for marker, present in (\n                            (\"synthetic-outside-target\", not devnull),\n                            (\"synthetic-site-marker\", not devnull),\n                            (\"synthetic-user-marker\", not devnull and not isolated),\n                        ):\n                            self.assertEqual(marker in result.stdout, present,\n                                             (marker, isolated, devnull, result.stdout))\n                        print(\"PIP_CONFIG_CLI_MATRIX=PASS isolated=%d devnull=%d\" %\n                              (isolated, devnull), flush=True)\n            self.assertEqual({p: p.read_bytes() for p in original}, original)\n\n\nif __name__ == \"__main__\":\n    unittest.main()\n",encoding="utf-8",newline="\n")
def check_config_cli(version):
    installed=subprocess.check_output([str(py),"-B","-c","import pip; print(pip.__version__)"],cwd=root,text=True).strip()
    assert installed==version
    result=subprocess.run([str(py),"-B","-m","unittest","discover","-s","tests","-p","test_pip_config_isolation.py","-v"],cwd=root,capture_output=True,encoding="utf-8",errors="replace",timeout=240)
    print(result.stdout,flush=True)
    print(result.stderr,flush=True)
    assert result.returncode==0 and result.stdout.count("PIP_CONFIG_CLI_MATRIX=PASS")==4, "Pip configuration CLI contract failed: "+version
    print("SAME_WINDOWS_PIP_CONFIG_CLI_ISOLATION=PASS "+version,flush=True)
# Run old-version control before downloading/staging replacements.
check_config_cli("26.1.2")

# Verify the actual affected DER trust anchor, not only a version or PEM label.
def root_audit(profile):
    probe = r"""
import hashlib, pathlib, ssl, sys, certifi
from pip._vendor import certifi as vendored
root = pathlib.Path(sys.argv[1]).resolve()
profile = sys.argv[2]
affected = "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"
for name, mod, rel in (("standalone",certifi,"certifi/cacert.pem"),
                       ("vendored",vendored,"pip/_vendor/certifi/cacert.pem")):
    expected = root / rel
    assert pathlib.Path(mod.where()).resolve()==expected
    ctx=ssl.create_default_context(cafile=str(expected))
    assert ctx.verify_mode==ssl.CERT_REQUIRED and ctx.check_hostname
    roots={hashlib.sha256(der).hexdigest() for der in ctx.get_ca_certs(binary_form=True)}
    assert roots and ((affected in roots)==(profile=="baseline"))
    print("CA_TRUST_ANCHOR_"+profile.upper()+"=PASS "+name+" roots="+str(len(roots)),flush=True)
"""
    result=subprocess.run([str(py),"-B","-c",probe,str(site),profile],cwd=root,capture_output=True,encoding="utf-8",errors="replace",timeout=60)
    print(result.stdout,flush=True)
    print(result.stderr,flush=True)
    assert result.returncode==0 and result.stdout.count("CA_TRUST_ANCHOR_"+profile.upper()+"=PASS")==2
root_audit("baseline")
scratch=root/"tmp"
scratch.mkdir(exist_ok=True)
plain(scratch,True)
runner_temp=Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
plain(runner_temp,True)
assert runner_temp.is_absolute() and not runner_temp.is_relative_to(root)
checkout_cache=root/"Microsoft/Windows/PowerShell/ModuleAnalysisCache"
def assert_no_checkout_cache(label):
    assert not os.path.lexists(checkout_cache), "Unexpected PowerShell cache at checkout: "+label
assert_no_checkout_cache("before maintenance subprocesses")
with tempfile.TemporaryDirectory(prefix="pip-certifi-refresh-",dir=scratch) as own, tempfile.TemporaryDirectory(prefix="portable-ci-pscache-",dir=runner_temp) as cache_temp:
    owned=Path(own)
    ci_cache_dir=Path(cache_temp).resolve(strict=True)
    plain(ci_cache_dir,True)
    assert ci_cache_dir.is_relative_to(runner_temp) and not ci_cache_dir.is_relative_to(root)
    ci_cache=ci_cache_dir/"ModuleAnalysisCache"
    assert not os.path.lexists(ci_cache)
    wheelhouse=owned/"wheelhouse"
    stage=owned/"stage"
    verified=owned/"online-recheck"
    reinstall=owned/"offline-reinstall"
    backup=owned/"original"
    for d in (wheelhouse,stage,verified,reinstall,backup): d.mkdir()
    # No runner credentials, host Python or user config in pip subprocesses.
    env={k:os.environ[k] for k in ("SystemRoot","WINDIR","SystemDrive","ComSpec","PATHEXT","OS","PROCESSOR_ARCHITECTURE") if k in os.environ}
    windows=Path(env["SystemRoot"])
    env["PATH"]=os.pathsep.join((str(root/"tool/bin"),str(py.parent),str(windows/"System32"),str(windows)))
    for k,d in {"HOME":"home","USERPROFILE":"home","APPDATA":"appdata","LOCALAPPDATA":"localappdata","PROGRAMDATA":"programdata","ALLUSERSPROFILE":"programdata","TEMP":"temp","TMP":"temp","TMPDIR":"temp","PIP_CACHE_DIR":"cache","PYTHONUSERBASE":"userbase","PYTHONPYCACHEPREFIX":"pycache"}.items():
        p=owned/d
        p.mkdir(exist_ok=True)
        env[k]=str(p)
    env.update(PIP_CONFIG_FILE="nul",PYTHONNOUSERSITE="1",PYTHONDONTWRITEBYTECODE="1",CODEX_INSTALL_DIR=str(root))
    def piprun(*args, expected=None):
        proc=subprocess.run([str(py),"-E","-s","-B","-m","pip","--isolated","--disable-pip-version-check","--no-input","--cache-dir",env["PIP_CACHE_DIR"],*map(str,args)],
            cwd=root,env=env,capture_output=True,timeout=300)
        assert_no_checkout_cache("python -m pip "+str(args[0]))
        if proc.returncode:
            raise RuntimeError("pip command failed: "+str(args[0])+"; "+proc.stdout.decode("utf-8","replace")[-3000:]+"; "+proc.stderr.decode("utf-8","replace")[-3000:])
        if expected is not None: assert expected in proc.stdout.decode("utf-8","replace")
        return proc.stdout
    # The direct module call is the control for the subsequent
    # Windows PowerShell shim diagnosis.
    piprun("check",expected="No broken requirements found.")
    print("PIP_MODULE_CALL_NO_CHECKOUT_PS_CACHE=PASS",flush=True)
    aliases=("pip.cmd","pip3.cmd","pip3.14.cmd")
    cli_helper=root/"tool/bin/portable-python-cli.py"
    cmd=windows/"System32/cmd.exe"
    alias_bytes={name:(root/"tool/bin"/name).read_bytes() for name in aliases}
    def alias_run(name,argv,cwd=root,code=0,expected_error=None,child_env=None):
        assert name in aliases and (root/"tool/bin"/name).read_bytes()==alias_bytes[name]
        shim=root/"tool/bin"/name
        # A fixed CMD executable and owned paths; no shell-supplied user text.
        command=f'"{cmd}" /d /s /c ""{shim}" '+subprocess.list2cmdline(list(map(str,argv)))+'"'
        p=subprocess.run(command,executable=str(cmd),cwd=cwd,env=env if child_env is None else child_env,capture_output=True,timeout=300)
        assert_no_checkout_cache("CMD preflight "+name)
        assert p.returncode==code, (name,argv[0],p.returncode,p.stdout.decode("utf-8","replace")[-1000:],p.stderr.decode("utf-8","replace")[-1000:])
        if expected_error is not None:
            err=p.stderr.decode("utf-8","strict")
            assert code!=0 and expected_error in err, "Unexpected failure reason: "+name
            assert str(py)+" -m pip" in err, "Missing official module invocation guidance"
        return p.stdout.decode("utf-8","strict").strip()
    flags=("--isolated","--disable-pip-version-check","--no-input")
    # Reproduce the old environment only within an owned diagnostic cwd,
    # never in the checkout root. Inspect only the two synthetic candidate
    # cache paths, not the host profile. The real CMD is unchanged.
    legacy_env=env.copy()
    assert "PSModuleAnalysisCachePath" not in legacy_env
    repro=owned/"default-cache-repro"
    repro.mkdir()
    relative_cache=repro/"Microsoft/Windows/PowerShell/ModuleAnalysisCache"
    appdata_cache=Path(legacy_env["LOCALAPPDATA"])/"Microsoft/Windows/PowerShell/ModuleAnalysisCache"
    assert not os.path.lexists(relative_cache) and not os.path.lexists(appdata_cache)
    assert alias_run("pip.cmd",(*flags,"--version"),cwd=repro,child_env=legacy_env).startswith("pip 26.1.2 from ")
    print("DEFAULT_CACHE_PRODUCER_PROBE="+json.dumps({"entry":"pip.cmd Windows PowerShell preflight","relative_cwd_cache":relative_cache.is_file(),"synthetic_localappdata_cache":appdata_cache.is_file(),"checkout_cache":os.path.lexists(checkout_cache)},ensure_ascii=True),flush=True)
    # Use Microsoft's supported process-only cache path, not NUL, not a
    # persistent user setting and not a change to the product launcher.
    env["PSModuleAnalysisCachePath"]=str(ci_cache)
    assert alias_run("pip.cmd",(*flags,"--version")).startswith("pip 26.1.2 from ")
    print("EXPLICIT_CACHE_CMD_PREFLIGHT="+json.dumps({"cache_created":ci_cache.is_file(),"checkout_cache":os.path.lexists(checkout_cache)}),flush=True)

    # Force a fresh, deterministic module discovery in the same 5.1 engine.
    # The synthetic module search path is used only in this proof subprocess;
    # all actual CMD contracts keep their original module search behavior.
    ps=windows/"System32/WindowsPowerShell/v1.0/powershell.exe"
    modules=ci_cache_dir/"modules"
    synthetic=modules/"PortableCiCacheProbe"
    synthetic.mkdir(parents=True)
    (synthetic/"PortableCiCacheProbe.psm1").write_text("function Get-PortableCiCacheProbe { 'portable-ci-cache-probe' }\nExport-ModuleMember -Function Get-PortableCiCacheProbe\n",encoding="ascii",newline="\n")
    probe_env=env.copy()
    probe_env["PSModulePath"]=os.pathsep.join((str(modules),str(ps.parent/"Modules")))
    discovery=r"""
    $ErrorActionPreference='Stop'
    if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'Unexpected PowerShell engine' }
    $found=@(Get-Module -ListAvailable -Name PortableCiCacheProbe)
    if ($found.Count -ne 1) { throw 'Synthetic module discovery failed' }
    Import-Module $found[0].Path -Force
    if ((Get-PortableCiCacheProbe) -cne 'portable-ci-cache-probe') { throw 'Synthetic command failed' }
    $deadline=[DateTime]::UtcNow.AddSeconds(75)
    while (-not [IO.File]::Exists($env:PSModuleAnalysisCachePath) -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 250 }
    if (-not [IO.File]::Exists($env:PSModuleAnalysisCachePath)) { throw 'PowerShell did not create explicit module cache' }
    [Console]::WriteLine('POWERSHELL_51_MODULE_DISCOVERY=PASS')
    """
    for phase in ("create","reuse"):
        probe=subprocess.run([str(ps),"-NoLogo","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-Command",discovery],cwd=owned,env=probe_env,capture_output=True,timeout=120)
        assert probe.returncode==0 and b"POWERSHELL_51_MODULE_DISCOVERY=PASS" in probe.stdout, (phase,probe.returncode,probe.stderr.decode("utf-8","replace")[-2000:])
        plain(ci_cache)
        # Real PowerShell creates the cache. Opening it r+b and reading
        # proves the test account can both read and open for writing;
        # do not alter the engine's serialized bytes.
        with ci_cache.open("r+b") as stream:
            assert stream.read(1), "Empty module cache"
        assert_no_checkout_cache("explicit cache "+phase)
        print("CI_POWERSHELL_MODULE_CACHE_READ_WRITE=PASS "+phase+" bytes="+str(ci_cache.stat().st_size),flush=True)
    print("CI_POWERSHELL_CACHE_OUTSIDE_CHECKOUT=PASS",flush=True)
    def check_entry_contract(version):
        # All three supported CMD aliases must execute the same official
        # installed distribution as python -m pip, not the old vendor EXEs.
        expected=piprun("--version").decode("utf-8","strict").strip()
        assert expected.startswith("pip "+version+" from ") and str(site/"pip") in expected
        module_packages={x["name"].lower():x["version"] for x in json.loads(piprun("list","--format=json"))}
        assert len(module_packages)==49 and module_packages["pip"]==version
        for name in aliases:
            assert alias_run(name,(*flags,"--version"))==expected
            assert alias_run(name,(*flags,"check"))=="No broken requirements found."
            assert Path(alias_run(name,(*flags,"cache","dir","--cache-dir",env["PIP_CACHE_DIR"]))).resolve()==Path(env["PIP_CACHE_DIR"]).resolve()
            package_list={x["name"].lower():x["version"] for x in json.loads(alias_run(name,(*flags,"list","--format=json")))}
            assert package_list==module_packages
            alias_run(name,(*flags,"portable-invalid-command"),code=1)
            print("WINDOWS_CMD_ALIAS_CONTRACT=PASS "+version+" "+name,flush=True)
    check_entry_contract("26.1.2")

    def read_entry_map(raw):
        if raw is None: return {}
        cp=configparser.ConfigParser(interpolation=None,strict=True)
        cp.optionxform=str
        cp.read_string(raw.decode("utf-8-sig"))
        assert not cp.defaults() and cp.sections()==["console_scripts"], "Unexpected entry point group/default"
        return {key:value.strip() for key,value in cp["console_scripts"].items()}
    old_wheel_entries={}
    for name,s in specs.items():
        version=s["old"]
        dist=name+"-"+version+".dist-info"
        filename=name+"-"+version+"-py3-none-any.whl"
        request=urllib.request.Request("https://pypi.org/pypi/"+name+"/"+version+"/json",headers={"User-Agent":"Portable-entry-review/1","Accept":"application/json"})
        with urllib.request.urlopen(request,timeout=30) as response:
            assert urllib.parse.urlsplit(response.url).hostname=="pypi.org"
            release=json.load(response)
        assert release["info"]["version"]==version
        items=[x for x in release["urls"] if x["filename"]==filename]
        assert len(items)==1
        item=items[0]
        assert not item["yanked"] and item["packagetype"]=="bdist_wheel" and item["digests"]["sha256"]==s["oldhash"]
        u=urllib.parse.urlsplit(item["url"])
        assert u.scheme=="https" and u.hostname=="files.pythonhosted.org" and u.username is None and u.password is None
        with urllib.request.urlopen(item["url"],timeout=90) as response:
            assert urllib.parse.urlsplit(response.url).hostname=="files.pythonhosted.org"
            body=response.read(item["size"]+1)
        assert len(body)==item["size"] and sha(body)==s["oldhash"]
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            entry=dist+"/entry_points.txt"
            rec=rows(z.read(dist+"/RECORD"))
            assert z.namelist().count(entry)<=1
            raw=z.read(entry) if entry in z.namelist() else None
            if raw is not None: assert rec[entry]==(rh(raw),str(len(raw)))
            else: assert entry not in rec
            old_wheel_entries[name]=raw
            ca="pip/_vendor/certifi/cacert.pem" if name=="pip" else "certifi/cacert.pem"
            assert z.namelist().count(ca)==1
            ca_bytes=z.read(ca)
            assert rec[ca]==(rh(ca_bytes),str(len(ca_bytes)))
            assert (site/ca).read_bytes()==ca_bytes, "Old official CA bytes differ: "+name
            if name=="pip":
                # The running old version must use the guard and entry
                # code from the same hash-verified official wheel.
                for relative in ("pip/_internal/utils/misc.py","pip/_internal/commands/install.py","pip/_internal/cli/main.py","pip/__main__.py"):
                    assert z.namelist().count(relative)==1
                    original=z.read(relative)
                    assert rec[relative]==(rh(original),str(len(original)))
                    assert (site/relative).read_bytes()==original, "Old installed guard/entry code differs: "+relative
                print("OLD_PIP_GUARD_AND_ENTRY_OFFICIAL_BYTES=PASS",flush=True)
        installed=site/dist/"entry_points.txt"
        installed_raw=installed.read_bytes() if installed.exists() else None
        assert read_entry_map(installed_raw)==read_entry_map(raw), "Installed old metadata differs from official wheel"
        print("PINNED_OLD_WHEEL_ENTRY_POINTS="+json.dumps({"name":name,"version":version,"wheel_sha256":s["oldhash"],"raw":None if raw is None else raw.decode("utf-8-sig"),"installed_raw_equal":installed_raw==raw,"semantic":read_entry_map(raw)},ensure_ascii=True),flush=True)
    upstream={}
    for name,s in specs.items():
        version=s["version"]
        assert not (Version(version).is_prerelease or Version(version).is_devrelease)
        wheel=name+"-"+version+"-py3-none-any.whl"
        # Official exact release and digest; fail closed on changed/yanked metadata.
        url="https://pypi.org/pypi/"+name+"/"+version+"/json"
        req=urllib.request.Request(url,headers={"User-Agent":"Portable-maintenance/1","Accept":"application/json"})
        with urllib.request.urlopen(req,timeout=30) as response:
            assert urllib.parse.urlsplit(response.url).hostname=="pypi.org"
            data=json.load(response)
        assert data["info"]["version"]==version
        item=[x for x in data["urls"] if x["filename"]==wheel]
        assert len(item)==1
        item=item[0]
        assert not item["yanked"] and item["packagetype"]=="bdist_wheel"
        assert item["url"]==s["url"] and item["digests"]["sha256"]==s["sha256"]
        assert SpecifierSet(item["requires_python"] or data["info"]["requires_python"]).contains("3.14.10",prereleases=False)
        with urllib.request.urlopen(s["url"],timeout=90) as response:
            assert urllib.parse.urlsplit(response.url).hostname=="files.pythonhosted.org"
            body=response.read(item["size"]+1)
        assert len(body)==item["size"] and sha(body)==s["sha256"]
        dest=wheelhouse/wheel
        dest.write_bytes(body)
        dist=name+"-"+version+".dist-info"
        rec=dist+"/RECORD"
        with zipfile.ZipFile(dest) as z:
            files={}
            for entry in z.infolist():
                if entry.is_dir(): continue
                f=pathsafe(entry.filename)
                assert f.startswith((name+"/",dist+"/"))
                assert not stat.S_ISLNK(entry.external_attr>>16) and not entry.flag_bits&1
                assert entry.file_size<30_000_000 and f not in files
                assert "__pycache__" not in f and not f.endswith((".pyc",".pth"))
                files[f]=z.read(entry)
            assert len({f.casefold() for f in files})==len(files)
        rr=rows(files[rec])
        assert set(rr)==set(files)
        for f,content in files.items():
            assert rr[f]==(("","") if f==rec else (rh(content),str(len(content)))), "Wheel RECORD mismatch: "+f
        metadata=email.parser.BytesParser().parsebytes(files[dist+"/METADATA"],headersonly=True)
        assert metadata["Name"].lower()==name and metadata["Version"]==version
        assert (metadata.get("License-Expression") or metadata.get("License"))==s["license"]
        assert SpecifierSet(metadata["Requires-Python"]).contains("3.14.10",prereleases=False)
        licensefiles=metadata.get_all("License-File",[])
        assert licensefiles and all(dist+"/licenses/"+f in files for f in licensefiles)
        new_raw=files.get(dist+"/entry_points.txt")
        old_raw=old_wheel_entries[name]
        old_map=read_entry_map(old_raw)
        new_map=read_entry_map(new_raw)
        print("PINNED_WHEEL_ENTRY_POINT_COMPARISON="+json.dumps({"name":name,"old":s["old"],"new":version,"old_wheel_sha256":s["oldhash"],"new_wheel_sha256":s["sha256"],"old_raw":None if old_raw is None else old_raw.decode("utf-8-sig"),"new_raw":None if new_raw is None else new_raw.decode("utf-8-sig"),"old_semantic":old_map,"new_semantic":new_map,"raw_equal":old_raw==new_raw,"semantic_equal":old_map==new_map},ensure_ascii=True),flush=True)
        if name=="pip":
            # Only this reviewed, version-pinned upstream change is allowed.
            # Never accept a new arbitrary target just because a wrapper loads it.
            expected_old={key:"pip._internal.cli.main:main" for key in ("pip","pip3")}
            expected_new={key:"pip._internal.cli.main:cli" for key in ("pip","pip3")}
            assert old_map==expected_old and read_entry_map(old_entry_points)==expected_old
            assert new_map==expected_new, "Unreviewed console entry point change"
            assert old_map!=new_map, "Expected real official entry-point change not reproduced"
            # Check the pinned wheel source, not just its declared metadata:
            # cli delegates with cli=True; main remains a non-CLI compatibility path.
            syntax=ast.parse(files["pip/_internal/cli/main.py"])
            funcs={f.name:f for f in syntax.body if isinstance(f,ast.FunctionDef)}
            for key,wanted in (("cli",True),("main",False)):
                node=funcs[key]
                body=list(node.body)
                if isinstance(body[0],ast.Expr) and isinstance(body[0].value,ast.Constant) and isinstance(body[0].value.value,str): body=body[1:]
                assert len(body)==1 and isinstance(body[0],ast.Return)
                call=body[0].value
                assert isinstance(call,ast.Call) and isinstance(call.func,ast.Name) and call.func.id=="_main"
                assert len(call.args)==1 and isinstance(call.args[0],ast.Name) and call.args[0].id=="args"
                assert len(call.keywords)==1 and call.keywords[0].arg=="cli" and isinstance(call.keywords[0].value,ast.Constant) and call.keywords[0].value.value is wanted
            module_main=ast.parse(files["pip/__main__.py"])
            assert any(isinstance(node,ast.ImportFrom) and node.module=="pip._internal.cli.main" and any(a.name=="cli" and a.asname=="_main" for a in node.names) for node in ast.walk(module_main))
            print("REVIEWED_PIP_MAIN_TO_CLI_SECURITY_ENTRY=PASS",flush=True)
        else:
            assert old_raw is None and new_raw is None and not old_map and not new_map, "Unexpected certifi console entry"
            print("CERTIFI_NO_CONSOLE_ENTRY_CHANGE=PASS",flush=True)
        upstream[name]=(dist,rec,files)
        print("OFFICIAL_WHEEL_VERIFIED="+json.dumps({"name":name,"version":version,"sha256":s["sha256"],"bytes":dest.stat().st_size,"requires_python":metadata["Requires-Python"],"license":s["license"],"license_files":len(licensefiles)},ensure_ascii=True),flush=True)
    reqfile=owned/"two-wheel-lock.txt"
    reqfile.write_text("".join(n+"=="+s["version"]+" --hash=sha256:"+s["sha256"]+"\n" for n,s in specs.items()),encoding="ascii",newline="\n")
    args=("--no-index","--find-links",wheelhouse,"--no-deps","--require-hashes","--only-binary=:all:","--no-compile","--ignore-installed","--requirement",reqfile)
    piprun("install",*args,"--target",stage)
    def verify_install(target, preserve_launchers=False, selected=("pip","certifi")):
        chosen=set(selected)
        assert chosen and chosen.issubset(upstream)
        assert not preserve_launchers or chosen=={"pip","certifi"}
        expected_roots=chosen|{upstream[n][0] for n in chosen}
        if "pip" in chosen: expected_roots.add("bin")
        assert {p.name for p in target.iterdir()}==expected_roots, "Unexpected installed top-level path"
        if "pip" in chosen: assert treefiles(target,"bin")==launchers
        for name in selected:
            dist,rec,files=upstream[name]
            actual=treefiles(target,name)|treefiles(target,dist)
            extra={dist+"/INSTALLER",dist+"/REQUESTED"}
            assert actual==set(files)|extra, ("Installed extra/missing files",name,sorted(actual-(set(files)|extra)),sorted((set(files)|extra)-actual))
            assert (target/dist/"INSTALLER").read_text().strip()=="pip" and (target/dist/"REQUESTED").read_bytes()==b""
            for f,content in files.items():
                if f!=rec: assert (target/f).read_bytes()==content, "Installed official bytes differ: "+f
            # RECORD may refer to the staging home scheme's ../../bin paths.
            # Normalize only the three exact generated names, never a supplied
            # arbitrary path. Preserve old unexposed vendor EXEs in final repo.
            if preserve_launchers and name=="pip":
                for f,data in old_launchers.items():
                    (target/f).write_bytes(data)
            owned_files=actual|(launchers if name=="pip" else set())
            if name=="certifi":
                # An ordinary wheel has no generated launcher paths.
                # Verify pip's real installed RECORD before rewriting it.
                installed_rows=rows((target/rec).read_bytes())
                assert set(installed_rows)==owned_files, "Installed certifi RECORD inventory differs"
                for f in owned_files:
                    if f==rec: assert installed_rows[f]==("","")
                    else:
                        data=(target/f).read_bytes()
                        assert installed_rows[f]==(rh(data),str(len(data))), "Installed certifi RECORD digest differs: "+f
            with (target/rec).open("w",encoding="utf-8",newline="") as handle:
                writer=csv.writer(handle,lineterminator="\n")
                for f in sorted(owned_files):
                    if f==rec: writer.writerow((f,"",""))
                    else:
                        content=(target/f).read_bytes()
                        writer.writerow((f,rh(content),str(len(content))))
            print("STAGED_WHEEL_PAYLOAD_AND_RECORD=PASS "+name,flush=True)
    # Use the exact same two verified wheels, command flags and owned
    # destinations for the old/new guard test. The supported module
    # path above is the only path used to install pip itself.
    ordinary_lock=owned/"ordinary-certifi-lock.txt"
    ordinary=specs["certifi"]
    ordinary_lock.write_text("certifi=="+ordinary["version"]+" --hash=sha256:"+ordinary["sha256"]+"\n",encoding="ascii",newline="\n")
    assert args[-2]=="--requirement" and args[-1]==reqfile
    ordinary_args=(*args[:-1],ordinary_lock)
    def runtime_snapshot():
        data={}
        for name in specs:
            version=distributions()[name]
            dist=name+"-"+version+".dist-info"
            for f in treefiles(site,name)|treefiles(site,dist):
                data[f]=sha((site/f).read_bytes())
        for f in launchers: data[f]=sha((site/f).read_bytes())
        return data
    def check_install_contract(version):
        baseline=runtime_snapshot()
        before=distributions()
        assert before["pip"]==version
        assert env["PIP_CONFIG_FILE"]=="nul" and all(Path(env[k]).is_relative_to(owned) for k in ("HOME","USERPROFILE","APPDATA","LOCALAPPDATA","PROGRAMDATA","TEMP","TMP","PIP_CACHE_DIR","PYTHONUSERBASE","PYTHONPYCACHEPREFIX"))
        assert Path(env["PSModuleAnalysisCachePath"])==ci_cache and ci_cache.is_relative_to(ci_cache_dir)
        assert not ci_cache.is_relative_to(root) and ci_cache.is_file()
        assert_no_checkout_cache("before install contract "+version)
        assert not any(k in env for k in ("PIP_INDEX_URL","PIP_EXTRA_INDEX_URL","PIP_TRUSTED_HOST","PIP_CERT","PIP_CLIENT_CERT","SSL_CERT_FILE","SSL_CERT_DIR","REQUESTS_CA_BUNDLE","CURL_CA_BUNDLE","PYTHONPATH","PYTHONHOME"))
        # Put both test types in fresh package-owned directories, also
        # exercising CMD argument quoting with Unicode and spaces.
        area=owned/("Windows \u4fbf\u643a pip "+version)
        area.mkdir()
        for name in aliases:
            rejected=area/(name+" protected pip")
            rejected.mkdir()
            alias_run(name,(*flags,"--cache-dir",env["PIP_CACHE_DIR"],"install",*args,"--target",rejected),code=1,expected_error="To modify pip, please run the following command:")
            assert not list(rejected.iterdir()), "Rejected self-modification wrote target files"
            print("WINDOWS_PIP_SELF_MODIFICATION_GUARD=PASS "+version+" "+name+" exit=1 target_empty=true",flush=True)
            target=area/(name+" ordinary certifi")
            target.mkdir()
            alias_run(name,(*flags,"--cache-dir",env["PIP_CACHE_DIR"],"install",*ordinary_args,"--target",target))
            verify_install(target,selected=("certifi",))
            assert distributions()==before, "Ordinary wheel install modified current runtime versions"
            print("WINDOWS_CMD_ORDINARY_WHEEL_INSTALL=PASS "+version+" "+name+" exit=0 sha256="+ordinary["sha256"],flush=True)
        assert runtime_snapshot()==baseline and distributions()==before, "Staging/guard probes changed live runtime"
        assert all((root/"tool/bin"/name).read_bytes()==data for name,data in alias_bytes.items())
        print("WINDOWS_PIP_INSTALL_CONTRACT_ISOLATION=PASS "+version,flush=True)
    verify_install(stage,preserve_launchers=True)
    print("SUPPORTED_MODULE_PIP_INSTALL=PASS runner=26.1.2 target_pip=26.3",flush=True)
    check_install_contract("26.1.2")
    # All old roots were proven fully owned above; move only those exact
    # directories into our private backup, never remove unrelated files.
    for name,s in specs.items():
        old_dist=name+"-"+s["old"]+".dist-info"
        new_dist,_,_=upstream[name]
        assert not (site/new_dist).exists()
        for part in (name,old_dist): (site/part).rename(backup/part)
        for part in (name,new_dist): (stage/part).rename(site/part)
    assert all((site/p).read_bytes()==data for p,data in old_launchers.items())
    new_versions=distributions()
    expected=old_versions|{n:s["version"] for n,s in specs.items()}
    assert new_versions==expected
    assert set(new_versions)==set(old_versions)
    print("INSTALLED_VERSION_DELTA=PASS "+json.dumps({n:[old_versions[n],new_versions[n]] for n in specs}),flush=True)
    check_config_cli("26.3")
    root_audit("candidate")
    assert_no_checkout_cache("after new pip configuration CLI contract")
    print("OLD_NEW_PIP_CONFIG_DEVNULL_ISOLATION_PARITY=PASS",flush=True)
    # The new pip itself must handle public verified HTTPS downloads and local
    # offline installation, without relying on cached data or source builds.
    piprun("--version",expected="pip 26.3 from ")
    piprun("check",expected="No broken requirements found.")
    check_entry_contract("26.3")
    piprun("download","--index-url","https://pypi.org/simple","--no-cache-dir","--no-deps","--only-binary=:all:","--require-hashes","--requirement",reqfile,"--dest",verified)
    assert {p.name for p in verified.iterdir()}=={p.name for p in wheelhouse.iterdir()}
    assert all(sha(p.read_bytes())==sha((wheelhouse/p.name).read_bytes()) for p in verified.iterdir())
    piprun("install",*args,"--target",reinstall)
    verify_install(reinstall)
    print("SUPPORTED_MODULE_PIP_INSTALL=PASS runner=26.3 target_pip=26.3",flush=True)
    check_install_contract("26.3")
    print("OLD_NEW_WINDOWS_SELF_GUARD_AND_ORDINARY_CMD_INSTALL_PARITY=PASS",flush=True)
    print("NEW_PIP_OFFICIAL_HTTPS_AND_OFFLINE_REINSTALL=PASS",flush=True)
    print("VENDOR_LAUNCHERS_UNEXPOSED_ORIGINAL_BYTES_RETAINED=PASS",flush=True)
    assert_no_checkout_cache("after all wheel and CMD tests")
    plain(ci_cache)
    with ci_cache.open("r+b") as stream:
        assert stream.read(1)
    print("CI_POWERSHELL_CACHE_CONTAINED_AFTER_ALL_INSTALL_TESTS=PASS",flush=True)
assert_no_checkout_cache("after owned temporary contexts exited")
print("CI_POWERSHELL_CACHE_TEMPORARY_SCOPE=PASS",flush=True)

# Only the two exact direct pins and corresponding wheel hashes change.
input_path=root/"tool/python-packages.in.txt"
lock_path=root/"tool/python-packages.lock.txt"
old_input=input_path.read_bytes()
new_input=old_input
lock=lock_path.read_bytes()
old_header=b"# requirements-sha256: "+sha(old_input).encode()
assert lock.count(old_header)==1
for name,s in specs.items():
    a=(name+"=="+s["old"]).encode()
    b=(name+"=="+s["version"]).encode()
    assert new_input.count(a)==1
    new_input=new_input.replace(a,b,1)
    a+=(" --hash=sha256:"+s["oldhash"]).encode()
    b+=(" --hash=sha256:"+s["sha256"]).encode()
    assert lock.count(a)==1
    lock=lock.replace(a,b,1)
lock=lock.replace(old_header,b"# requirements-sha256: "+sha(new_input).encode(),1)
input_path.write_bytes(new_input); lock_path.write_bytes(lock)

# Keep the native consumer regression on the accepted candidate.
probe=root/"tests/check_pip_certifi_security.py"
assert not probe.exists()
probe.write_text("\"\"\"Actual relocated Windows pip entry point and CA-consumer audit (synthetic environment).\"\"\"\nimport hashlib\nimport importlib.metadata as md\nimport json\nimport os\nfrom pathlib import Path\nimport shutil\nimport ssl\nimport subprocess\nimport sys\n\nimport certifi\nimport httpx\nimport pip\nimport requests\nfrom pip._vendor import certifi as pip_certifi\nfrom pip._vendor import requests as pip_requests\n\ndef main():\n    profile = sys.argv[1] if len(sys.argv) == 2 else \"candidate\"\n    assert len(sys.argv) <= 2 and profile in {\"baseline\", \"candidate\"}\n    pip_version, certifi_version, vendor_version, entry_name = {\n        \"baseline\": (\"26.1.2\", \"2026.5.20\", \"2026.02.25\", \"main\"),\n        \"candidate\": (\"26.3\", \"2026.11.20\", \"2026.10.23\", \"cli\"),\n    }[profile]\n    root = Path(os.environ[\"CODEX_INSTALL_DIR\"]).resolve()\n    site = root / \"tool/python/Lib/site-packages\"\n    py = root / \"tool/python/python.exe\"\n    assert sys.version_info[:3] == (3, 14, 10)\n    assert Path(sys.executable).resolve() == py\n    assert sys.flags.isolated and sys.flags.ignore_environment\n    assert all(Path(p).resolve().is_relative_to(root / \"tool/python\") for p in sys.path)\n    assert os.environ[\"PIP_CONFIG_FILE\"].lower() == \"nul\"\n    assert Path(os.environ[\"PIP_CACHE_DIR\"]).resolve().is_relative_to(root)\n    assert Path(os.environ[\"PYTHONUSERBASE\"]).resolve().is_relative_to(root)\n    assert Path(os.environ[\"PYTHONPYCACHEPREFIX\"]).resolve().is_relative_to(root)\n    for key in (\"PIP_INDEX_URL\",\"PIP_EXTRA_INDEX_URL\",\"PIP_TRUSTED_HOST\",\"PIP_CERT\",\"PIP_CLIENT_CERT\",\n                \"SSL_CERT_FILE\",\"SSL_CERT_DIR\",\"REQUESTS_CA_BUNDLE\",\"CURL_CA_BUNDLE\",\"PYTHONHOME\",\"PYTHONPATH\"):\n        assert not os.environ.get(key), \"Unexpected inherited config: \" + key\n    assert pip.__version__ == md.version(\"pip\") == pip_version\n    from pip._internal.cli import main as cli_module\n    entry_points = {e.name:e for e in md.distribution(\"pip\").entry_points if e.group==\"console_scripts\"}\n    assert set(entry_points)=={\"pip\",\"pip3\"}\n    assert all(e.value==\"pip._internal.cli.main:\"+entry_name and e.load() is getattr(cli_module, entry_name) for e in entry_points.values())\n    assert certifi.__version__ == md.version(\"certifi\") == certifi_version\n    assert pip_certifi.__version__ == vendor_version\n    for name in (\"pip\", \"certifi\"):\n        found = [d for d in md.distributions() if d.metadata[\"Name\"].lower() == name]\n        assert len(found) == 1 and Path(found[0].locate_file(\"\")).resolve() == site\n    for module in (pip, certifi, requests, httpx, pip_certifi, pip_requests):\n        assert Path(module.__file__).resolve().is_relative_to(site)\n    standalone = site / \"certifi/cacert.pem\"\n    vendored = site / \"pip/_vendor/certifi/cacert.pem\"\n    assert Path(certifi.where()).resolve() == standalone\n    assert Path(requests.certs.where()).resolve() == standalone\n    assert Path(requests.utils.DEFAULT_CA_BUNDLE_PATH).resolve() == standalone\n    assert Path(pip_certifi.where()).resolve() == vendored\n    assert Path(pip_requests.certs.where()).resolve() == vendored\n    assert Path(pip_requests.utils.DEFAULT_CA_BUNDLE_PATH).resolve() == vendored\n    def certs(ctx):\n        assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname\n        values = set(ctx.get_ca_certs(binary_form=True))\n        assert values\n        return values\n    expected = certs(ssl.create_default_context(cafile=str(standalone)))\n    assert certs(httpx.create_ssl_context(verify=True, trust_env=True)) == expected\n    pip_roots = certs(ssl.create_default_context(cafile=str(vendored)))\n    affected = \"86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b\"\n    for roots in (expected, pip_roots):\n        assert (affected in {hashlib.sha256(der).hexdigest() for der in roots}) == (profile == \"baseline\")\n    print(\"NATIVE_AFFECTED_CA_TRUST_REMOVED=PASS\" if profile == \"candidate\" else \"NATIVE_AFFECTED_CA_PRESENT=CONFIRMED\", flush=True)\n    print(\"NATIVE_CA_BUNDLES=PASS standalone=%s roots=%d vendored=%s roots=%d\" % (certifi_version, len(expected), vendor_version, len(pip_roots)), flush=True)\n    # Execute through the same relocatable console entry-point helper used by\n    # the existing .cmd shims (the shell additionally exercises those shims).\n    helper = root / \"tool/bin/portable-python-cli.py\"\n    def run(*args):\n        p = subprocess.run([str(py), \"-E\", \"-s\", \"-B\", str(helper), \"pip\",\n            \"--isolated\", \"--disable-pip-version-check\", \"--no-input\", *args],\n            cwd=Path(__file__).parent, capture_output=True, timeout=90)\n        assert p.returncode == 0, (\"pip\", args, p.returncode, p.stderr.decode(\"utf-8\",\"replace\"))\n        return p.stdout.decode(\"utf-8\",\"strict\").strip()\n    version = run(\"--version\")\n    assert version.startswith(\"pip \"+pip_version+\" from \") and str(site / \"pip\") in version\n    debug = run(\"debug\")\n    line = next(s for s in debug.splitlines() if s.startswith(\"pip._vendor.certifi.where(): \"))\n    assert Path(line.split(\": \",1)[1]).resolve() == vendored\n    assert Path(run(\"cache\",\"dir\",\"--cache-dir\",os.environ[\"PIP_CACHE_DIR\"])).resolve() == Path(os.environ[\"PIP_CACHE_DIR\"]).resolve()\n    packages = {x[\"name\"].lower():x[\"version\"] for x in json.loads(run(\"list\",\"--format=json\"))}\n    assert len(packages) == 49\n    assert packages[\"pip\"] == pip_version and packages[\"certifi\"] == certifi_version\n    assert run(\"check\") == \"No broken requirements found.\"\n    # Exercise the actual relocated CMD aliases in the native Codex child\n    # with the existing sandbox policy. Do not execute vendor EXEs.\n    cmd = Path(os.environ[\"SystemRoot\"]) / \"System32/cmd.exe\"\n    for name in (\"pip.cmd\",\"pip3.cmd\",\"pip3.14.cmd\"):\n        shim = root / \"tool/bin\" / name\n        assert Path(shutil.which(name)).resolve() == shim\n        def alias(*args, code=0):\n            argv = [\"--isolated\",\"--disable-pip-version-check\",\"--no-input\",*args]\n            command = f'\"{cmd}\" /d /s /c \"\"{shim}\" '+subprocess.list2cmdline(argv)+'\"'\n            p = subprocess.run(command,executable=str(cmd),cwd=Path(__file__).parent,capture_output=True,timeout=90)\n            assert p.returncode == code, (name,args,p.returncode,p.stderr.decode(\"utf-8\",\"replace\")[-1000:])\n            return p.stdout.decode(\"utf-8\",\"strict\").strip()\n        assert alias(\"--version\")==version\n        assert alias(\"check\")==\"No broken requirements found.\"\n        assert Path(alias(\"cache\",\"dir\",\"--cache-dir\",os.environ[\"PIP_CACHE_DIR\"])).resolve()==Path(os.environ[\"PIP_CACHE_DIR\"]).resolve()\n        assert {x[\"name\"].lower():x[\"version\"] for x in json.loads(alias(\"list\",\"--format=json\"))}==packages\n        alias(\"portable-invalid-command\",code=1)\n        print(\"NATIVE_PIP_CMD_ALIAS=PASS \"+name,flush=True)\n    print(\"NATIVE_PIP_OFFICIAL_CLI_ENTRY_AND_ALIASES=PASS\",flush=True)\n    print(\"NATIVE_PIP_ENTRYPOINT_CONFIG_AND_CLOSURE=PASS\",flush=True)\n    print(\"NATIVE_PIP_PINNED_PROFILE=PASS \"+profile+\" pip=\"+pip_version+\" certifi=\"+certifi_version,flush=True)\n\nif __name__ == \"__main__\":\n    main()\n",encoding="utf-8",newline="\n")

# Keep the already validated native Code Mode continuation intact.
fixture=root/"tests/check_codex_tool_discovery.py"
original=fixture.read_bytes()
source=original.decode("utf-8")
newline="\r\n" if b"\r\n" in original else "\n"
def edit(a,b):
    global source
    a,b=a.replace("\n",newline),b.replace("\n",newline)
    assert source.count(a)==1, "Unexpected native fixture anchor: "+repr(a[:120])
    source=source.replace(a,b,1)
edit("PROBE_PY = '''","PIP_CERTIFI_SECURITY_PY = Path(__file__).with_name('check_pip_certifi_security.py').read_text(encoding='utf-8')\n\nPROBE_PY = '''")
edit('if different:\n    raise SystemExit(9)\n'+"'''",
     'if different:\n    raise SystemExit(9)\nimport subprocess\nsubprocess.run([sys.executable,"-B",str(pathlib.Path(__file__).with_name("pip-certifi-security.py"))],check=True)\n'+"'''")
edit("if ($LASTEXITCODE -ne 0) { throw 'Native YOLO rg regression failed' }",
     "if ($LASTEXITCODE -ne 0) { throw 'Native YOLO rg regression failed' }\n& (Join-Path $env:CODEX_INSTALL_DIR 'tool/python/python.exe') -B (Join-Path $env:CODEX_INSTALL_DIR 'work/tool-probe/pip-certifi-security.py')\nif ($LASTEXITCODE -ne 0) { throw 'Native YOLO CA/pip regression failed' }")
edit('(probe / "rg-refresh.py").write_text(RG_REFRESH_PY, encoding="utf-8")',
     '(probe / "rg-refresh.py").write_text(RG_REFRESH_PY, encoding="utf-8")\n        (probe / "pip-certifi-security.py").write_text(PIP_CERTIFI_SECURITY_PY, encoding="utf-8")')
edit('        assert "ENV_DIFFERENCES=" not in evidence, "Actual child environment differs from generated policy"',
     '        if mode in {"normal", "unknown", "browser"}:\n            for marker in ("NATIVE_AFFECTED_CA_TRUST_REMOVED=PASS", "NATIVE_PIP_OFFICIAL_CLI_ENTRY_AND_ALIASES=PASS", "NATIVE_PIP_ENTRYPOINT_CONFIG_AND_CLOSURE=PASS"):\n                assert marker in evidence, "Missing native CA/pip evidence: " + marker\n        assert "ENV_DIFFERENCES=" not in evidence, "Actual child environment differs from generated policy"')
edit('            env["PATH"] = str(windows / "System32")',
     '            env["PATH"] = str(windows / "System32")\n            env.update({k:"synthetic-host-value-not-for-child" for k in ("PIP_INDEX_URL","PIP_EXTRA_INDEX_URL","PIP_TRUSTED_HOST","PIP_CERT","PIP_CLIENT_CERT","SSL_CERT_FILE","SSL_CERT_DIR","REQUESTS_CA_BUNDLE","CURL_CA_BUNDLE","PYTHONHOME","PYTHONPATH")})')
fixture.write_bytes(source.encode("utf-8"))
for p in (fixture,probe,fixture_path):
    compile(p.read_bytes(),str(p),"exec")
print("PIP_CERTIFI_SECURITY_WHEELS_AND_TARGETED_NATIVE_FIXTURE_READY=PASS",flush=True)
