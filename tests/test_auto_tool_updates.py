"""Offline security regression tests for manual official tool discovery."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "portable_auto_tools", ROOT / "tool/auto-tool-updates.py")
assert spec and spec.loader
auto = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auto)


def official_release(name, stable, digest="a" * 64):
    tag = {"ripgrep": stable, "fd": "v" + stable, "jq": "jq-" + stable}[name]
    filename = {
        "ripgrep": "ripgrep-" + stable + "-x86_64-pc-windows-msvc.zip",
        "fd": "fd-v" + stable + "-x86_64-pc-windows-msvc.zip",
        "jq": "jq-windows-amd64.exe",
    }[name]
    return {"draft": False, "prerelease": False, "tag_name": tag, "assets": [{
        "name": filename, "state": "uploaded", "size": 8192,
        "digest": "sha256:" + digest,
        "browser_download_url":
            "https://github.com/" + auto.OFFICIAL[name] +
            "/releases/download/" + tag + "/" + filename,
    }]}


class AutoToolTests(unittest.TestCase):
    def test_strict_stable_semver(self):
        self.assertEqual(auto.version("26.14.0"), (26, 14, 0))
        for bad in ("v26.14.0", "26.14", "26.14.0-rc.1",
                    "26.14.0.1", "latest", "../26.14.0"):
            with self.subTest(version=bad), self.assertRaises(ValueError):
                auto.version(bad)

    def test_official_github_assets_fail_closed(self):
        for tool, candidate in (("ripgrep", "15.3.0"), ("fd", "10.6.0"),
                                ("jq", "1.9.0")):
            with self.subTest(tool=tool):
                release = official_release(tool, candidate)
                with patch.object(auto, "request_json", return_value=release):
                    self.assertEqual(auto.github_release(tool)[0], candidate)
                selected = auto.cli_candidate(tool, candidate, release)
                self.assertEqual(selected["sha256"], "a" * 64)
                self.assertEqual(selected["tool"], tool)
                for key, value in (("digest", None),
                                   ("browser_download_url", "https://evil.invalid/z"),
                                   ("state", "deleted"), ("size", 0)):
                    forged = official_release(tool, candidate)
                    forged["assets"][0][key] = value
                    with self.assertRaises(ValueError):
                        auto.cli_candidate(tool, candidate, forged)
                for key in ("draft", "prerelease"):
                    forged = official_release(tool, candidate)
                    forged[key] = True
                    with patch.object(auto, "request_json", return_value=forged):
                        with self.assertRaises(ValueError):
                            auto.github_release(tool)

    def test_metadata_bearer_only_to_github_api_and_no_redirects(self):
        # Authorization is never sent to nodejs.org or GitHub asset URLs.
        seen = []
        class Response:
            def __init__(self, url):
                self.url = url
            def read(self, limit):
                return b"{}"
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        class Opener:
            def open(self, request, timeout):
                seen.append((request.full_url,
                             request.get_header("Authorization")))
                return Response(request.full_url)
        opener = Opener()
        with patch.dict(os.environ, {"GITHUB_TOKEN": "safe-test-token",
                                    "GH_TOKEN": ""}), \
             patch.object(auto.urllib.request, "build_opener",
                          return_value=opener):
            github = "https://api.github.com/repos/jqlang/jq/releases/latest"
            node = "https://nodejs.org/dist/index.json"
            self.assertEqual(auto.request_bytes(github), b"{}")
            self.assertEqual(auto.request_bytes(node), b"{}")
        self.assertEqual(seen, [(github, "Bearer safe-test-token"),
                                (node, None)])
        with self.assertRaisesRegex(ValueError, "no credentials forwarded"):
            auto._RejectRedirect().redirect_request(
                None, None, 302, "Moved", {},
                "https://attacker.invalid/token")
        with patch.dict(os.environ, {"GITHUB_TOKEN": "bad\r\nheader"}):
            with self.assertRaisesRegex(ValueError, "Invalid GitHub"):
                auto.request_bytes(github)

    def test_node_official_shasums_and_release_index(self):
        index = [{"version": "v26.14.0", "files": ["win-x64-zip"]},
                 {"version": "v26.15.0-rc.1", "files": ["win-x64-zip"]},
                 {"version": "v27.0.0", "files": ["linux-x64"]}]
        # A newer major may exist but is not yet approved by our
        # Windows launcher/npm/ABI regression policy.
        index.insert(1, {"version": "v27.1.0", "files": ["win-x64-zip"]})
        with patch.object(auto, "request_json", return_value=index):
            self.assertEqual(auto.official_node_latest(), "27.1.0")
            self.assertEqual(auto.official_node_latest(supported_major=26), "26.14.0")
        entry = ("b" * 64 + "  node-v26.14.0-win-x64.zip\n").encode("ascii")
        with patch.object(auto, "request_bytes", return_value=entry):
            node = auto.node_candidate("26.14.0")
        self.assertEqual(node["source_prefix"], "node-v26.14.0-win-x64/")
        self.assertEqual(node["sha256"], "b" * 64)
        with patch.object(auto, "request_bytes", return_value=b"wrong"):
            with self.assertRaises(ValueError):
                auto.node_candidate("26.14.0")

    def test_version_comparison_and_no_downgrade(self):
        installed = {"node": "26.13.0", "ripgrep": "15.2.0",
                     "fd": "10.5.0", "jq": "1.8.2"}
        releases = {"ripgrep": ("15.3.0", official_release("ripgrep", "15.3.0")),
                    "fd": ("10.5.0", official_release("fd", "10.5.0")),
                    "jq": ("1.8.2", official_release("jq", "1.8.2"))}
        with patch.object(auto, "ledger_versions", return_value=installed), \
             patch.object(auto, "official_node_latest", return_value="26.13.0"), \
             patch.object(auto, "github_release", side_effect=releases.get):
            selected, states = auto.discover()
        self.assertEqual([x["tool"] for x in selected], ["ripgrep"])
        self.assertEqual(states["node"]["latest"], "26.13.0")
        with patch.object(auto, "ledger_versions", return_value=installed), \
             patch.object(auto, "official_node_latest", return_value="26.12.0"):
            with self.assertRaisesRegex(ValueError, "older than installed"):
                auto.discover()

    def test_owned_scratch_plan_and_empty_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            out = root / "tmp/auto-tool-update-plan.json"
            cand = auto.cli_candidate("jq", "1.9.0",
                                      official_release("jq", "1.9.0"))
            with patch.object(auto, "ROOT", root), patch.object(auto, "OUT", out):
                with self.assertRaisesRegex(ValueError, "No upgrades needed"):
                    auto.write_plan([])
                auto.write_plan([cand])
                saved = json.loads(out.read_text(encoding="utf-8"))
                self.assertEqual(saved["candidates"], [cand])

    def test_node_only_candidate_generates_independent_official_digest(self):
        installed = {"node": "26.13.0", "ripgrep": "15.2.0",
                     "fd": "10.5.0", "jq": "1.8.2"}
        checksum = ("c" * 64 + "  node-v26.14.0-win-x64.zip\n").encode("ascii")
        def unchanged(tool):
            stable = installed[tool]
            return stable, official_release(tool, stable)
        with patch.object(auto, "ledger_versions", return_value=installed), \
             patch.object(auto, "official_node_latest", return_value="26.14.0"), \
             patch.object(auto, "github_release", side_effect=unchanged), \
             patch.object(auto, "request_bytes", return_value=checksum):
            candidates, status = auto.discover()
        self.assertEqual([row["tool"] for row in candidates], ["node"])
        self.assertEqual(candidates[0]["sha256"], "c" * 64)
        self.assertEqual(candidates[0]["destination"], "tool/node")
        self.assertEqual(status["node"]["policy"], "same_verified_major_only")

    def test_jq_only_candidate_has_exact_verified_executable(self):
        installed = {"node": "26.13.0", "ripgrep": "15.2.0",
                     "fd": "10.5.0", "jq": "1.8.2"}
        def release(tool):
            stable = "1.9.0" if tool == "jq" else installed[tool]
            return stable, official_release(tool, stable)
        with patch.object(auto, "ledger_versions", return_value=installed), \
             patch.object(auto, "official_node_latest", return_value="26.13.0"), \
             patch.object(auto, "github_release", side_effect=release):
            candidates, _ = auto.discover()
        self.assertEqual([row["tool"] for row in candidates], ["jq"])
        self.assertEqual(candidates[0]["kind"], "executable")
        self.assertEqual(candidates[0]["destination"], "tool/bin/jq.exe")
        self.assertEqual(candidates[0]["sha256"], "a" * 64)

    def test_unchanged_auto_check_outputs_false_without_plan(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "output"
            scratch = Path(folder) / "auto-tool-update-plan.json"
            with patch.object(auto, "discover", return_value=([], {})), \
                 patch.object(auto, "OUT", scratch), \
                 patch.dict(os.environ, {"GITHUB_OUTPUT": str(output),
                                      "GITHUB_STEP_SUMMARY": ""}):
                self.assertEqual(auto.main(["check"]), 0)
            self.assertEqual(output.read_text(encoding="utf-8"), "updates=false\n")
            self.assertFalse(scratch.exists())

    def test_auto_metadata_rejects_unapproved_origins(self):
        for url in ("http://api.github.com/repos/jqlang/jq/releases/latest",
                    "https://evil.invalid/", "https://api.github.com:444/repos/a",
                    "https://user@api.github.com/repos/a",
                    "https://nodejs.org/dist/index.json?unreviewed=true"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "Unapproved"):
                auto.request_bytes(url)

    def test_node_only_auto_preserves_separately_pinned_npm_and_corepack(self):
        # Official Node 26 currently bundles npm 11.x, but our package has
        # separately audited npm 12.x. Auto must not silently downgrade npm.
        source = (ROOT / "tool/update-tools.py").read_text(encoding="utf-8")
        for contract in (
            "NODE_PORTABLE_DIRS = ('node_modules/corepack', 'node_modules/npm')",
            "NPM_RETAIN_MAX_BYTES",
            "shutil.rmtree(target_dir)",
            "shutil.copytree(original_dir, target_dir)",
            "Node-only upgrade changed the pinned npm version",
            "Node-only upgrade changed the pinned Corepack version",
        ):
            self.assertIn(contract, source)
        test_source = (ROOT / "tests/test_tool_updates.py").read_text(
            encoding="utf-8")
        self.assertIn("def test_node_upgrade_preserves_portable_npm", test_source)
        self.assertIn("def test_node_inventory_preserves_pinned_npm", test_source)
        self.assertIn("def test_auto_selector_does_not_change_reviewed", test_source)

    def test_workflow_auto_is_manual_and_preserves_release_gates(self):
        workflow = (ROOT / ".github/workflows/03-update-tools.yml").read_text(
            encoding="utf-8")
        self.assertIn("options: [check, diagnose, prepare, full, auto]", workflow)
        self.assertIn("tool/auto-tool-updates.py check", workflow)
        # Ubuntu uses POSIX paths; the Windows verifier and writer use native
        # PowerShell paths. Check each job, not just a global string occurrence.
        windows_plan = r".\tool\auto-tool-updates.py plan"
        verify = workflow.split("\n  verify:", 1)[1].split("\n  propose:", 1)[0]
        writer = workflow.split("\n  propose:", 1)[1].split("\n  full_verify:", 1)[0]
        self.assertEqual(verify.count(windows_plan), 1)
        self.assertEqual(writer.count(windows_plan), 1)
        self.assertIn("!cancelled()", workflow)
        self.assertEqual(workflow.count("-p 'test_auto_tool_updates.py' -v"), 2)
        self.assertLess(workflow.index("-p 'test_auto_tool_updates.py' -v"),
                        workflow.index("tool/auto-tool-updates.py check"))
        windows = workflow.split("\n  verify:", 1)[1].split("\n  propose:", 1)[0]
        self.assertLess(windows.index("-p 'test_auto_tool_updates.py' -v"),
                        windows.index("Stage checked wheel or SHA256-pinned"))
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", workflow)
        self.assertIn("needs.auto_check.outputs.updates == 'true'", workflow)
        self.assertIn("TOOL_AUTO_UPDATE_PLAN=1", workflow)
        self.assertIn("TOOL_AUTO_UPDATE_PLAN = '1'", workflow)
        self.assertIn("inputs.mode == 'prepare' || inputs.mode == 'auto'", workflow)
        self.assertIn("WINDOWS_PS_TEST_END=", workflow)
        self.assertIn("release-audit.py --release", workflow)
        self.assertIn("release-audit.py --verify", workflow)
        self.assertNotIn("gh release create", workflow)


if __name__ == "__main__":
    unittest.main()
