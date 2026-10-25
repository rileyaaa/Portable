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

    def test_utf8_mcp_wire_survives_ascii_and_windows_legacy_stdio_encodings(self):
        apk = self.apk("中文输入.apk")
        outside = self.outside / "中文私密.apk"
        outside.write_bytes(b"must not read")
        requests = [
            {"jsonrpc": "2.0", "id": "中文成功", "method": "tools/call",
             "params": {"name": "apk.inspect", "arguments": {"path": str(apk)}}},
            {"jsonrpc": "2.0", "id": "中文错误", "method": "tools/call",
             "params": {"name": "未知工具", "arguments": {}}},
            {"jsonrpc": "2.0", "id": "中文拒绝", "method": "tools/call",
             "params": {"name": "apk.inspect", "arguments": {"path": str(outside)}}},
        ]
        # Send real UTF-8 Chinese bytes, not JSON \u escapes. Locale decoding
        # would corrupt the path or stop the stream before the successful reply.
        wire = "".join(json.dumps(request, ensure_ascii=False) + "\n" for request in requests).encode("utf-8")
        wire += b"\xff\n"  # Invalid UTF-8 is a parse error, not locale text.
        wire += (json.dumps({"jsonrpc": "2.0", "id": "继续消息", "method": "ping"},
                            ensure_ascii=False) + "\n").encode("utf-8")
        for encoding in ("ascii", "cp1252"):
            with self.subTest(stdio_encoding=encoding):
                env = {**self.env, "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0",
                       "PYTHONIOENCODING": encoding + ":strict"}
                run = subprocess.run(
                    [sys.executable, "-B", str(self.server), "--task-authorized"],
                    input=wire, capture_output=True, timeout=15, cwd=self.package, env=env,
                )
                self.assertEqual(run.returncode, 0, run.stderr.decode("ascii", "backslashreplace"))
                self.assertTrue(run.stdout.isascii(), "MCP output must not depend on a Windows code page")
                responses = [json.loads(line) for line in run.stdout.decode("utf-8").splitlines()]
                self.assertEqual(len(responses), 5)
                self.assertEqual(responses[0]["id"], "中文成功")
                self.assertFalse(responses[0]["result"]["isError"])
                payload = json.loads(responses[0]["result"]["content"][0]["text"])
                self.assertEqual(payload["path"], str(apk))
                self.assertEqual(payload["packageRoot"], str(self.package))
                self.assertEqual(responses[1]["id"], "中文错误")
                self.assertIn("未知工具", responses[1]["error"]["message"])
                self.assertEqual(responses[2]["id"], "中文拒绝")
                self.assertTrue(responses[2]["result"]["isError"])
                self.assertIn("中文私密.apk", responses[2]["result"]["content"][0]["text"])
                self.assertEqual(responses[3]["error"]["code"], -32700)
                self.assertEqual(responses[4], {"jsonrpc": "2.0", "id": "继续消息", "result": {}})
        self.assertEqual(outside.read_bytes(), b"must not read")

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


    def atomic_fixture(self):
        spec = importlib.util.spec_from_file_location("apk_atomic_fixture", self.server)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.object(sys, "dont_write_bytecode", True):
            spec.loader.exec_module(module)
        module.PKG_ROOT = module.find_package_root()
        module.JOBS_ROOT = self.package / "work" / "apk-jobs"
        source = self.package / "work" / "synthetic-source.bin"
        source.parent.mkdir(exist_ok=True)
        source.write_bytes(b"synthetic\x00payload\r\n")
        return module, source

    def atomic_operation(self, module, source, kind, output):
        if kind == "text":
            return module._atomic_write_text(output, "synthetic \u4e2d\u6587\r\n", jobs_only=True)
        if kind == "copy":
            return module._atomic_copy_file(source, output, jobs_only=True)
        with source.open("rb") as stream:
            return module._atomic_copy_limited(stream, output, source.stat().st_size, jobs_only=True)

    def test_atomic_outputs_stage_only_in_package_tmp(self):
        module, source = self.atomic_fixture()
        for kind in ("text", "copy", "extract"):
            with self.subTest(kind=kind):
                output = module.JOBS_ROOT / kind / "result.bin"
                paths = []
                actual = module.tempfile.mkstemp
                def capture(*args, **kwargs):
                    result = actual(*args, **kwargs)
                    paths.append(Path(result[1]))
                    return result
                with mock.patch.object(module.tempfile, "mkstemp", capture):
                    self.atomic_operation(module, source, kind, output)
                expected = "synthetic \u4e2d\u6587\r\n".encode() if kind == "text" else source.read_bytes()
                self.assertEqual(output.read_bytes(), expected)
                self.assertEqual(len(paths), 1)
                self.assertEqual(paths[0].parent, self.package / "tmp")
                self.assertFalse(paths[0].exists())

    def test_atomic_outputs_reject_linked_tmp_before_job_creation(self):
        module, source = self.atomic_fixture()
        self.symlink(self.outside, self.package / "tmp", directory=True)
        for kind in ("text", "copy", "extract"):
            with self.subTest(kind=kind):
                output = module.JOBS_ROOT / kind / "result.bin"
                with mock.patch.object(module.tempfile, "mkstemp",
                                       wraps=module.tempfile.mkstemp) as create_temp:
                    with self.assertRaises(ValueError):
                        self.atomic_operation(module, source, kind, output)
                    create_temp.assert_not_called()
                self.assertFalse(output.parent.exists())
                self.assertEqual(list(self.outside.iterdir()), [])

    def test_atomic_outputs_reject_file_tmp_before_job_creation(self):
        module, source = self.atomic_fixture()
        scratch = self.package / "tmp"
        scratch.write_bytes(b"keep")
        for kind in ("text", "copy", "extract"):
            with self.subTest(kind=kind):
                with self.assertRaises((OSError, ValueError)):
                    self.atomic_operation(module, source, kind, module.JOBS_ROOT / kind / "result.bin")
                self.assertFalse(module.JOBS_ROOT.exists())
                self.assertEqual(scratch.read_bytes(), b"keep")

    def test_atomic_replace_failures_preserve_outputs_and_unrelated_tmp(self):
        module, source = self.atomic_fixture()
        scratch = self.package / "tmp"
        scratch.mkdir()
        sentinel = scratch / "keep.txt"
        sentinel.write_bytes(b"keep")
        for kind in ("text", "copy", "extract"):
            with self.subTest(kind=kind):
                output = module.JOBS_ROOT / kind / "result.bin"
                output.parent.mkdir(parents=True)
                output.write_bytes(b"original")
                with mock.patch.object(module.os, "replace", side_effect=OSError("synthetic")):
                    with self.assertRaisesRegex(OSError, "synthetic"):
                        self.atomic_operation(module, source, kind, output)
                self.assertEqual(output.read_bytes(), b"original")
                self.assertEqual(list(output.parent.iterdir()), [output])
                self.assertEqual(list(scratch.iterdir()), [sentinel])
                self.assertEqual(sentinel.read_bytes(), b"keep")

    def test_atomic_copy_open_failure_closes_staging_descriptor(self):
        module, source = self.atomic_fixture()
        output = module.JOBS_ROOT / "result.bin"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"original")
        created = []
        actual_mkstemp = module.tempfile.mkstemp
        actual_open = Path.open
        def capture(*args, **kwargs):
            result = actual_mkstemp(*args, **kwargs)
            created.append(result)
            return result
        def deny_source(path, *args, **kwargs):
            if path == source:
                raise PermissionError("synthetic read failure")
            return actual_open(path, *args, **kwargs)
        try:
            with mock.patch.object(module.tempfile, "mkstemp", capture), \
                    mock.patch.object(Path, "open", deny_source):
                with self.assertRaises(PermissionError):
                    module._atomic_copy_file(source, output, jobs_only=True)
            self.assertEqual(len(created), 1)
            with self.assertRaises(OSError):
                os.fstat(created[0][0])
            self.assertFalse(Path(created[0][1]).exists())
            self.assertEqual(output.read_bytes(), b"original")
        finally:
            # The unpatched implementation leaks this descriptor. The negative
            # control must close it so the test itself leaves no handle behind.
            for descriptor, name in created:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                Path(name).unlink(missing_ok=True)

if __name__ == "__main__":
    unittest.main()
