"""Actual relocated Windows pip entry point and CA-consumer audit (synthetic environment)."""
import hashlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys

import certifi
import httpx
import pip
import requests
from pip._vendor import certifi as pip_certifi
from pip._vendor import requests as pip_requests

def main():
    profile = sys.argv[1] if len(sys.argv) == 2 else "candidate"
    assert len(sys.argv) <= 2 and profile in {"baseline", "candidate"}
    pip_version, certifi_version, vendor_version, entry_name = {
        "baseline": ("26.1.2", "2026.5.20", "2026.02.25", "main"),
        "candidate": ("26.3", "2026.11.20", "2026.10.23", "cli"),
    }[profile]
    root = Path(os.environ["CODEX_INSTALL_DIR"]).resolve()
    site = root / "tool/python/Lib/site-packages"
    py = root / "tool/python/python.exe"
    assert sys.version_info[:3] == (3, 14, 10)
    assert Path(sys.executable).resolve() == py
    assert sys.flags.isolated and sys.flags.ignore_environment
    assert all(Path(p).resolve().is_relative_to(root / "tool/python") for p in sys.path)
    assert os.environ["PIP_CONFIG_FILE"].lower() == "nul"
    assert Path(os.environ["PIP_CACHE_DIR"]).resolve().is_relative_to(root)
    assert Path(os.environ["PYTHONUSERBASE"]).resolve().is_relative_to(root)
    assert Path(os.environ["PYTHONPYCACHEPREFIX"]).resolve().is_relative_to(root)
    for key in ("PIP_INDEX_URL","PIP_EXTRA_INDEX_URL","PIP_TRUSTED_HOST","PIP_CERT","PIP_CLIENT_CERT",
                "SSL_CERT_FILE","SSL_CERT_DIR","REQUESTS_CA_BUNDLE","CURL_CA_BUNDLE","PYTHONHOME","PYTHONPATH"):
        assert not os.environ.get(key), "Unexpected inherited config: " + key
    assert pip.__version__ == md.version("pip") == pip_version
    from pip._internal.cli import main as cli_module
    entry_points = {e.name:e for e in md.distribution("pip").entry_points if e.group=="console_scripts"}
    assert set(entry_points)=={"pip","pip3"}
    assert all(e.value=="pip._internal.cli.main:"+entry_name and e.load() is getattr(cli_module, entry_name) for e in entry_points.values())
    assert certifi.__version__ == md.version("certifi") == certifi_version
    assert pip_certifi.__version__ == vendor_version
    for name in ("pip", "certifi"):
        found = [d for d in md.distributions() if d.metadata["Name"].lower() == name]
        assert len(found) == 1 and Path(found[0].locate_file("")).resolve() == site
    for module in (pip, certifi, requests, httpx, pip_certifi, pip_requests):
        assert Path(module.__file__).resolve().is_relative_to(site)
    standalone = site / "certifi/cacert.pem"
    vendored = site / "pip/_vendor/certifi/cacert.pem"
    assert Path(certifi.where()).resolve() == standalone
    assert Path(requests.certs.where()).resolve() == standalone
    assert Path(requests.utils.DEFAULT_CA_BUNDLE_PATH).resolve() == standalone
    assert Path(pip_certifi.where()).resolve() == vendored
    assert Path(pip_requests.certs.where()).resolve() == vendored
    assert Path(pip_requests.utils.DEFAULT_CA_BUNDLE_PATH).resolve() == vendored
    def certs(ctx):
        assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
        values = set(ctx.get_ca_certs(binary_form=True))
        assert values
        return values
    expected = certs(ssl.create_default_context(cafile=str(standalone)))
    assert certs(httpx.create_ssl_context(verify=True, trust_env=True)) == expected
    pip_roots = certs(ssl.create_default_context(cafile=str(vendored)))
    affected = "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"
    for roots in (expected, pip_roots):
        assert (affected in {hashlib.sha256(der).hexdigest() for der in roots}) == (profile == "baseline")
    print("NATIVE_AFFECTED_CA_TRUST_REMOVED=PASS" if profile == "candidate" else "NATIVE_AFFECTED_CA_PRESENT=CONFIRMED", flush=True)
    print("NATIVE_CA_BUNDLES=PASS standalone=%s roots=%d vendored=%s roots=%d" % (certifi_version, len(expected), vendor_version, len(pip_roots)), flush=True)
    # Execute through the same relocatable console entry-point helper used by
    # the existing .cmd shims (the shell additionally exercises those shims).
    helper = root / "tool/bin/portable-python-cli.py"
    def run(*args):
        p = subprocess.run([str(py), "-E", "-s", "-B", str(helper), "pip",
            "--isolated", "--disable-pip-version-check", "--no-input", *args],
            cwd=Path(__file__).parent, capture_output=True, timeout=90)
        assert p.returncode == 0, ("pip", args, p.returncode, p.stderr.decode("utf-8","replace"))
        return p.stdout.decode("utf-8","strict").strip()
    version = run("--version")
    assert version.startswith("pip "+pip_version+" from ") and str(site / "pip") in version
    debug = run("debug")
    line = next(s for s in debug.splitlines() if s.startswith("pip._vendor.certifi.where(): "))
    assert Path(line.split(": ",1)[1]).resolve() == vendored
    assert Path(run("cache","dir","--cache-dir",os.environ["PIP_CACHE_DIR"])).resolve() == Path(os.environ["PIP_CACHE_DIR"]).resolve()
    packages = {x["name"].lower():x["version"] for x in json.loads(run("list","--format=json"))}
    assert len(packages) == 49
    assert packages["pip"] == pip_version and packages["certifi"] == certifi_version
    assert run("check") == "No broken requirements found."
    # Exercise the actual relocated CMD aliases in the native Codex child
    # with the existing sandbox policy. Do not execute vendor EXEs.
    cmd = Path(os.environ["SystemRoot"]) / "System32/cmd.exe"
    for name in ("pip.cmd","pip3.cmd","pip3.14.cmd"):
        shim = root / "tool/bin" / name
        assert Path(shutil.which(name)).resolve() == shim
        def alias(*args, code=0):
            argv = ["--isolated","--disable-pip-version-check","--no-input",*args]
            command = f'"{cmd}" /d /s /c ""{shim}" '+subprocess.list2cmdline(argv)+'"'
            p = subprocess.run(command,executable=str(cmd),cwd=Path(__file__).parent,capture_output=True,timeout=90)
            assert p.returncode == code, (name,args,p.returncode,p.stderr.decode("utf-8","replace")[-1000:])
            return p.stdout.decode("utf-8","strict").strip()
        assert alias("--version")==version
        assert alias("check")=="No broken requirements found."
        assert Path(alias("cache","dir","--cache-dir",os.environ["PIP_CACHE_DIR"])).resolve()==Path(os.environ["PIP_CACHE_DIR"]).resolve()
        assert {x["name"].lower():x["version"] for x in json.loads(alias("list","--format=json"))}==packages
        alias("portable-invalid-command",code=1)
        print("NATIVE_PIP_CMD_ALIAS=PASS "+name,flush=True)
    print("NATIVE_PIP_OFFICIAL_CLI_ENTRY_AND_ALIASES=PASS",flush=True)
    print("NATIVE_PIP_ENTRYPOINT_CONFIG_AND_CLOSURE=PASS",flush=True)
    print("NATIVE_PIP_PINNED_PROFILE=PASS "+profile+" pip="+pip_version+" certifi="+certifi_version,flush=True)

if __name__ == "__main__":
    main()
