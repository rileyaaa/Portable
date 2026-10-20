"""Run the offline APK MCP in relocated fixtures; never contact Android devices."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


ROOT = Path(__file__).absolute().parents[1]
SERVER = Path("home/plugins/android-apk-lab/scripts/apk_lab_mcp.py")


class AndroidExtensionTests(unittest.TestCase):
    def setUp(self):
        for entry in (*reversed(ROOT.parents), ROOT):
            info = entry.lstat()
            self.assertFalse(stat.S_ISLNK(info.st_mode))
            self.assertFalse(getattr(info, "st_file_attributes", 0) & 0x400)
        scratch = ROOT / "tmp"
        if scratch.exists() or scratch.is_symlink():
            info = scratch.lstat()
            self.assertFalse(stat.S_ISLNK(info.st_mode))
            self.assertFalse(getattr(info, "st_file_attributes", 0) & 0x400)
        scratch.mkdir(exist_ok=True)
        fixture = tempfile.TemporaryDirectory(prefix="android-extension-", dir=scratch)
        self.addCleanup(fixture.cleanup)
        self.base = Path(fixture.name)
        self.package = self.base / "移动 Package"
        self.package.mkdir()
        for marker in ("codex.exe", "env.ps1"):
            (self.package / marker).write_bytes(b"synthetic marker")
        self.server = self.package / SERVER
        self.server.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / SERVER, self.server)
        self.outside = self.base / "old-root"
        self.outside.mkdir()
        self.env = os.environ.copy()
        for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONPYCACHEPREFIX", "APK_LAB_JOBS_DIR"):
            self.env.pop(name, None)
        self.env["CODEX_INSTALL_DIR"] = str(self.outside)
        self.env["CODEX_APK_LAB_PORTABLE"] = "1"
        self.env["CODEX_MAINTENANCE_MODE"] = "1"

    def run_mcp(self, requests=(), *, flags=("--task-authorized",), server=None, env=None):
        return subprocess.run(
            [sys.executable, "-B", str(server or self.server), *flags],
            input="".join(json.dumps(request) + "\n" for request in requests),
            capture_output=True, text=True, timeout=15, cwd=self.package,
            env=env or self.env,
        )

    def call(self, name, arguments):
        run = self.run_mcp([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                            "params": {"name": name, "arguments": arguments}}])
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout)["result"]

    def apk(self, name="sample.apk"):
        path = self.package / "work" / name
        path.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("AndroidManifest.xml", "<manifest/>")
            archive.writestr("classes.dex", b"synthetic https://example.invalid/api")
        return path

    def symlink(self, target, link, *, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Symlink creation unavailable: {exc}")

    def test_unselected_start_rejects_before_root_probing_or_state_creation(self):
        detached = self.base / "detached.py"
        shutil.copyfile(self.server, detached)
        for flags in ((), ("--task-authorized=false",), ("--maintenance",)):
            with self.subTest(flags=flags):
                run = self.run_mcp(flags=flags, server=detached)
                self.assertEqual(run.returncode, 2)
                self.assertIn("--task-authorized", run.stderr)
                self.assertNotIn("locate Codex Portable", run.stderr)
                self.assertEqual(run.stdout, "")
        self.assertFalse((self.package / "work").exists())
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_import_is_inert_even_outside_package_layout(self):
        detached = self.base / "detached.py"
        shutil.copyfile(self.server, detached)
        spec = importlib.util.spec_from_file_location("android_extension_fixture", detached)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.object(sys, "dont_write_bytecode", True), \
                mock.patch.object(Path, "lstat", side_effect=AssertionError("Unexpected filesystem probe")), \
                mock.patch.object(Path, "stat", side_effect=AssertionError("Unexpected filesystem probe")):
            spec.loader.exec_module(module)
        self.assertFalse(hasattr(module, "PKG_ROOT"))

    def test_initialization_and_tool_listing_are_read_only(self):
        run = self.run_mcp([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-03-26"}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ])
        self.assertEqual(run.returncode, 0, run.stderr)
        responses = [json.loads(line) for line in run.stdout.splitlines()]
        self.assertEqual(responses[0]["result"]["protocolVersion"], "2025-03-26")
        names = {tool["name"] for tool in responses[1]["result"]["tools"]}
        self.assertEqual(names, {"apk.inspect", "portable.resolve_path", "apk.search_strings",
                                 "apk.list_endpoints", "apk.extract_native",
                                 "network.parse_capture", "report.generate"})
        self.assertFalse((self.package / "work").exists())
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_inspection_writes_only_to_relocated_package(self):
        apk = self.apk()
        result = self.call("apk.inspect", {"path": str(apk)})
        self.assertFalse(result["isError"])
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["packageRoot"], str(self.package))
        expected = self.package / "work" / "apk-jobs" / hashlib.sha256(apk.read_bytes()).hexdigest()
        self.assertEqual(payload["jobDir"], str(expected))
        self.assertTrue((expected / "metadata" / "intake.json").is_file())
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_outside_and_private_inputs_are_denied_without_jobs(self):
        outside = self.outside / "private.apk"
        outside.write_bytes(b"must not read")
        for candidate in (outside, self.package / "env.ps1",
                          self.package / "work" / ".." / ".." / "old-root" / "private.apk"):
            with self.subTest(path=candidate):
                result = self.call("apk.inspect", {"path": str(candidate)})
                self.assertTrue(result["isError"])
        self.assertFalse((self.package / "work" / "apk-jobs").exists())
        self.assertEqual(outside.read_bytes(), b"must not read")

    def test_output_override_is_denied_before_outside_link_resolution(self):
        alias = self.package / "jobs-alias"
        self.symlink(self.outside / "missing", alias, directory=True)
        for destination in (self.outside, alias):
            env = {**self.env, "APK_LAB_JOBS_DIR": str(destination)}
            run = self.run_mcp(env=env)
            self.assertNotEqual(run.returncode, 0)
        self.assertEqual(list(self.outside.iterdir()), [])

    def test_linked_and_dangling_input_paths_are_denied(self):
        apk = self.apk()
        for name, target in (("alias.apk", apk), ("dangling.apk", self.outside / "missing")):
            alias = apk.parent / name
            self.symlink(target, alias)
            result = self.call("apk.inspect", {"path": str(alias)})
            self.assertTrue(result["isError"])
            self.assertIn("reparse/symlink", result["content"][0]["text"])
        self.assertFalse((apk.parent / "apk-jobs").exists())

    def test_hardlinked_input_is_denied(self):
        apk = self.apk()
        alias = apk.parent / "hardlink.apk"
        try:
            os.link(apk, alias)
        except OSError as exc:
            self.skipTest(f"Hard link creation unavailable: {exc}")
        result = self.call("apk.inspect", {"path": str(alias)})
        self.assertTrue(result["isError"])
        self.assertIn("hard-linked", result["content"][0]["text"])
        self.assertFalse((apk.parent / "apk-jobs").exists())

    def test_linked_package_ancestor_is_denied(self):
        alias = self.base / "alias"
        self.symlink(self.package, alias, directory=True)
        run = self.run_mcp(server=alias / SERVER)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("reparse/symlink", run.stderr)
        self.assertFalse((self.package / "work").exists())

    def test_missing_or_linked_root_marker_never_falls_back(self):
        marker = self.package / "env.ps1"
        marker.unlink()
        run = self.run_mcp()
        self.assertNotEqual(run.returncode, 0)
        outside = self.outside / "env.ps1"
        outside.write_bytes(b"old marker")
        self.symlink(outside, marker)
        run = self.run_mcp()
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("marker may not be a link", run.stderr)

    def test_plugin_discovery_does_not_register_the_optional_server(self):
        plugin = ROOT / "home" / "plugins" / "android-apk-lab"
        metadata = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text())
        self.assertNotIn("mcpServers", metadata)
        self.assertFalse((plugin / ".mcp.json").exists())
        self.assertFalse((plugin / "hooks" / "hooks.json").exists())
        manual = json.loads((plugin / ".mcp.manual.json").read_text())
        self.assertIn("-TaskAuthorized", manual["mcpServers"]["apk_lab_mcp"]["args"])


if __name__ == "__main__":
    unittest.main()
