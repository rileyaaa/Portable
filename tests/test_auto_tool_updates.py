"""Offline security regression tests for manual official tool discovery."""
from __future__ import annotations

import importlib.util
import json
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

    def test_workflow_auto_is_manual_and_preserves_release_gates(self):
        workflow = (ROOT / ".github/workflows/03-update-tools.yml").read_text(
            encoding="utf-8")
        self.assertIn("options: [check, diagnose, prepare, full, auto]", workflow)
        self.assertIn("tool/auto-tool-updates.py check", workflow)
        self.assertIn("tool/auto-tool-updates.py plan", workflow)
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
