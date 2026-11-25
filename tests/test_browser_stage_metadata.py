"""Offline probes for the one-time official browser artifact staging code."""
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT=Path(__file__).absolute().parents[1]

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

stage=module("browser_stable_stage","tests/stage_browser_stable.py")
installer=module("browser_stable_install","tool/automation/install-browser.py")

# Public registry test vectors, not installation inputs:
# https://registry.npmjs.org/-/npm/v1/keys
KEYS=(
    ("SHA256:jl3bwswu80PjjokCgh0o2w5c2U4LhQAE57gj9cz1kzA",
     "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE1Olb3zMAFFxXKHiIkQO5cJ3Yhl5i6UPp+IhuteBJbuHcA5UogKo0EWtlWwW6KSaKoTNEYL7JlCQiVnkhBktUgg=="),
    ("SHA256:DhQ8wR5APBvFHLF/+Tc+AYvPOdTpcIDqOhxsBHRwC7U",
     "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEY6Ya7W++7aUPzvMTrezH6Ycx3c+HOKYCcNGybJZSCJq/fd7Qa8uuAKtdIkUQtQiEKERhAmE5lMMJhP8OkDOa2g=="),
)

class BrowserStageMetadataTests(unittest.TestCase):
    def test_official_ssh_fingerprints_and_invalid_key_binding(self):
        for keyid,encoded in KEYS:
            with self.subTest(keyid=keyid):
                key=dict(keyid=keyid,key=encoded,keytype="ecdsa-sha2-nistp256",
                         scheme="ecdsa-sha2-nistp256")
                der=base64.b64decode(encoded,validate=True)
                wrong="SHA256:"+base64.b64encode(hashlib.sha256(der).digest()).decode().rstrip("=")
                self.assertNotEqual(wrong,keyid)
                self.assertIsNotNone(stage.registry_public_key(key))
                with self.assertRaises(AssertionError):
                    stage.registry_public_key(key|{"keyid":wrong})
                with self.assertRaises(AssertionError):
                    stage.registry_public_key(key|{"scheme":"unknown"})

    def test_cft_archive_staging_preserves_exact_inventory(self):
        # No real downloads or executables run. Exercise the actual staging
        # path and production extractor with an owned synthetic PE header.
        exe=bytearray(128);exe[:2]=b"MZ";exe[0x3c:0x40]=(64).to_bytes(4,"little")
        exe[64:70]=b"PE\0\0\x64\x86"
        output=io.BytesIO()
        with zipfile.ZipFile(output,"w") as z:
            z.writestr("chrome-win64/chrome.exe",bytes(exe))
            z.writestr("chrome-win64/locales/en.pak",b"synthetic locale")
        archive=output.getvalue()
        entry={"version":stage.CHROME,"revision":stage.REV,
               "downloads":{"chrome":[{"platform":"win64","url":stage.URL}]}}
        metadata={"timestamp":"synthetic","channels":{"Stable":entry}}
        def response():
            result=io.BytesIO(archive);result.url=stage.URL
            result.headers={"Content-Length":str(len(archive)),"x-goog-generation":"1",
                            "x-goog-hash":"md5="+base64.b64encode(hashlib.md5(archive,usedforsecurity=False).digest()).decode()}
            return result
        scratch=ROOT/"tmp";scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="browser-stage-test-",dir=scratch) as d:
            own=Path(d)
            with mock.patch.object(stage,"ROOT",own), \
                 mock.patch.object(stage,"data_json",side_effect=[metadata,entry]), \
                 mock.patch.object(stage.opener,"open",side_effect=lambda *args,**kwargs:response()):
                folder,manifest=stage.stage_chrome(own,installer)
            self.assertEqual(folder,own/("chromium-"+stage.REV))
            self.assertEqual(manifest["archive"]["sha256"],hashlib.sha256(archive).hexdigest())
            self.assertEqual(manifest["fileCount"],2)
            self.assertEqual((folder/"chrome-win64/chrome.exe").read_bytes(),exe)
            self.assertEqual((folder/"chrome-win64/locales/en.pak").read_bytes(),b"synthetic locale")

if __name__=="__main__":
    unittest.main()
