"""Offline security and contract tests for the full latest-stable Win11 upgrade.

Run BEFORE any artifact download. No internet, source wheels, new native EXE,
GitHub token or real package files are needed by these tests.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

ROOT = Path(__file__).absolute().parents[1]


def load(path: str, alias: str):
    script = ROOT / path
    spec = importlib.util.spec_from_file_location(alias, script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage = load("tool/full-stable-prepare.py", "portable_full_stage")
transfer = load("tool/full-stable-transfer.py", "portable_full_transfer")
fast = load("tool/full-stable-diagnose.py", "portable_fast_diagnose")
native = load("tool/full-stable-native-diagnose.py", "portable_native_diagnose")
pure = load("tool/full_stable_pure_wheels.py", "portable_pinned_pyyaml")


class FullStableUpgradeTests(unittest.TestCase):
    def test_source_and_workflow_parse_without_running_downloads(self):
        for path in ("tool/full-stable-prepare.py", "tool/full-stable-transfer.py",
                     "tool/full_stable_pure_wheels.py",
                     "tests/test_full_stable_upgrade.py"):
            ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)
        source = (ROOT / ".github/workflows/03-update-tools.yml").read_text(
            encoding="utf-8")
        self.assertIn("options: [check, diagnose, prepare, full]", source)
        self.assertIn("    if: github.ref == 'refs/heads/main' && inputs.mode != 'full'", source)
        self.assertIn("name: Full tool stable refresh - Windows read-only verifier", source)
        self.assertIn("name: Full tool trusted writer", source)
        self.assertIn("needs: full_verify", source)
        self.assertIn("EXPECTED_ARTIFACT:", source)
        self.assertIn("EXPECTED_DIGEST:", source)
        self.assertIn("FULL_STABLE_WRITER_MATCH=PASS", source)
        self.assertIn("python-lock.py validate-runtime", source)
        self.assertIn("package-release.py --version", source)
        self.assertIn("release-audit.py --release", source)
        self.assertIn("release-audit.py --verify", source)
        self.assertIn("WINDOWS_PS_TEST_END=", source)
        self.assertNotIn("gh release create", source)
        self.assertNotIn("git push origin HEAD:refs/heads/main", source)
        full = source.split("\n  full_verify:", 1)[1]
        verifier, writer = full.split("\n  full_propose:", 1)
        self.assertIn("contents: read", verifier)
        self.assertNotIn("contents: write", verifier)
        self.assertIn("contents: write", writer)
        self.assertLess(verifier.index("Stage full latest-stable"), 
                        verifier.index("Full Python Node and converter"))
        self.assertLess(verifier.index("Full Python Node and converter"),
                        verifier.index("Bound candidate paths"))
        self.assertLess(verifier.index("Bound candidate paths"),
                        verifier.index("Fail fast on real customer ZIP inputs"))
        self.assertLess(verifier.index("Fail fast on real customer ZIP inputs"),
                        verifier.index("Check Windows PowerShell 5.1 regressions"))
        self.assertLess(verifier.index("Real package preflight"),
                        verifier.index("Upload exact verified candidate"))
        self.assertLess(writer.index("full-stable-transfer.py apply"),
                        writer.index("git push origin"))
        self.assertNotIn("full-stable-prepare.py prepare", writer)

    def test_fast_batch_diagnostics_no_full_action_artifacts_and_aggregate_errors(self):
        workflow = (ROOT / ".github/workflows/03-update-tools.yml").read_text(
            encoding="utf-8")
        self.assertIn("options: [check, diagnose, prepare, full]", workflow)
        self.assertIn("inputs.mode != 'full' && inputs.mode != 'diagnose'", workflow)
        quick = workflow.split("\n  fast_diagnose:", 1)[1]
        self.assertIn("inputs.mode == 'diagnose'", quick)
        self.assertIn("inputs.create_pr == false", quick)
        self.assertIn("permissions:\n      contents: read", quick)
        self.assertNotIn("contents: write", quick)
        self.assertNotIn("actions: write", quick)
        self.assertIn("runs-on: ubuntu-latest", quick)
        self.assertIn("lfs: false", quick)
        self.assertIn("persist-credentials: false", quick)
        self.assertIn("tool/full-stable-diagnose.py --network", quick)
        for forbidden in ("upload-artifact", "download-artifact",
                          "gh release create", "git push", "stage_npm"):
            self.assertNotIn(forbidden, quick)
        program = (ROOT / "tool/full-stable-diagnose.py").read_text(encoding="utf-8")
        ast.parse(program)
        self.assertNotIn("stage.prepare(", program)
        self.assertNotIn("stage.stage_npm(", program)
        release = load("tool/package-release.py", "portable_release_diagnose_exclusion")
        included, excluded = release.customer_files(["tool/full-stable-diagnose.py",
                                                    "tool/installed-tools.json"])
        self.assertEqual(included, ["tool/installed-tools.json"])
        self.assertIn("tool/full-stable-diagnose.py", excluded)
        _, native_excluded = release.customer_files(["tool/full-stable-native-diagnose.py"])
        self.assertIn("tool/full-stable-native-diagnose.py", native_excluded)
        plan = json.loads((ROOT / "tool/full-stable-upgrade-plan.json").read_text(
            encoding="utf-8"))
        def fake_probe(name, *_):
            if name == "corepack":
                raise ValueError("mock registry error")
            return "mock official metadata OK"
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(fast, "ROOT", Path(directory)), \
             patch.object(fast, "offline_suite", return_value="mock local PASS"), \
             patch.object(fast, "network_probe", side_effect=fake_probe):
            records = fast.diagnose(include_network=True, plan=plan, stage=stage)
            self.assertEqual([r["probe"] for r in records],
                             ["plan", "contracts", "workflows", "npm",
                              "corepack", "playwright", "pip", "pdf"])
            self.assertEqual([r["probe"] for r in records if r["status"] == "FAIL"],
                             ["corepack"])
            self.assertEqual(sum(r["status"] == "PASS" for r in records), 7)
            self.assertFalse(any((Path(directory) / "tmp").iterdir()))
        with patch.object(fast, "network_probe",
                          side_effect=AssertionError("network attempted")), \
             patch.object(fast, "offline_suite", return_value="PASS"):
            no_network = fast.diagnose(include_network=False, plan=plan, stage=stage)
            self.assertEqual([r["probe"] for r in no_network],
                             ["plan", "contracts", "workflows"])
            with self.assertRaisesRegex(ValueError, "require --network"):
                fast.diagnose(include_network=False, selected={"npm"},
                              plan=plan, stage=stage)

    def test_native_diagnose_reuses_real_stagers_not_weak_registry_mocks(self):
        workflow = (ROOT / ".github/workflows/03-update-tools.yml").read_text(
            encoding="utf-8")
        nativejob = workflow.split("\n  native_diagnose:", 1)[1]
        self.assertIn("needs: fast_diagnose", nativejob)
        self.assertIn("needs.fast_diagnose.result == 'success'", nativejob)
        self.assertIn("inputs.mode == 'diagnose'", nativejob)
        self.assertIn("inputs.create_pr == false", nativejob)
        self.assertIn("runs-on: windows-latest", nativejob)
        self.assertIn("permissions:\n      contents: read", nativejob)
        self.assertIn("node-version: '26.13.0'", nativejob)
        self.assertIn("python-version: '3.14'", nativejob)
        self.assertIn("lfs: false", nativejob)
        self.assertIn("persist-credentials: false", nativejob)
        self.assertIn("full-stable-native-diagnose.py", nativejob)
        for forbidden in ("upload-artifact", "download-artifact", "git push",
                          "contents: write", "actions: write", "gh release create"):
            self.assertNotIn(forbidden, nativejob)
        self.assertIn("timeout-minutes: 15", nativejob)
        source = (ROOT / "tool/full-stable-native-diagnose.py").read_text(
            encoding="utf-8")
        ast.parse(source)
        self.assertNotIn("stage.prepare(", source)
        self.assertNotIn("stage.stage_browser(", source)
        self.assertNotIn("stage.update_version_inventory(", source)
        for real_step in ("stage.stage_npm(", "stage.stage_playwright(",
                          "stage.stage_python(", "stage.python_manifests(",
                          "stage.smoke_staged_python(", "stage.stage_7zip(",
                          "stage.replace_tree(", "refresh-python-cli-shims.py"):
            self.assertIn(real_step, source)

        # A failing independent probe must not prevent all other errors from
        # being collected, but dependent probes must be visibly BLOCKED.
        records = []
        def rejected():
            raise ValueError("synthetic npm install failure")
        native.record(records, "npm_corepack", rejected)
        probe = Mock(return_value="should not execute")
        native.record(records, "playwright_npm_ci", probe,
                      after=("npm_corepack",))
        native.record(records, "sevenzip_amd64", lambda: "real independent success")
        self.assertEqual([r["status"] for r in records],
                         ["FAIL", "BLOCKED", "PASS"])
        probe.assert_not_called()
        with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": ""}):
            self.assertEqual(native.write_report(records), 1)
            self.assertEqual(native.write_report([{"probe": "only", "status": "PASS",
                                                   "detail": "verified", "seconds": 0}]), 0)

    def test_native_full_pdf_policy_is_the_same_reviewed_exception(self):
        plan = json.loads((ROOT / "tool/full-stable-upgrade-plan.json").read_text(
            encoding="utf-8"))
        policy = {"mode": "latest-compatible-legacy-pdf",
                  "pymupdf": "1.28.2", "pymupdf4llm": "0.3.4"}
        evidence = {"pdf_compatibility": policy}
        stage.verify_pdf_compatibility_exception(plan, evidence)
        self.assertEqual(native.verify_pdf_exception(stage, plan, evidence),
                         "Official PDF policy: latest-compatible-legacy-pdf")
        wrong = {"pdf_compatibility": dict(policy, pymupdf="1.28.1")}
        with self.assertRaisesRegex(ValueError, "Unreviewed CPython"):
            stage.verify_pdf_compatibility_exception(plan, wrong)
        with self.assertRaisesRegex(ValueError, "Unreviewed PDF"):
            stage.verify_pdf_compatibility_exception(plan, {"pdf_compatibility":
                                                             {"mode": "bypass"}})
        stage.verify_pdf_compatibility_exception(plan, {"pdf_compatibility":
                                                         {"mode": "latest-with-layout"}})
        source = (ROOT / "tool/full-stable-prepare.py").read_text(encoding="utf-8")
        self.assertIn("verify_pdf_compatibility_exception(plan, evidence)", source)
        self.assertIn("stage.verify_pdf_compatibility_exception(plan, evidence)",
                      (ROOT / "tool/full-stable-native-diagnose.py").read_text(
                          encoding="utf-8"))

    def test_native_diagnostic_sandbox_uses_copied_sources_not_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            area = Path(directory)
            source = area / "source"
            node = area / "toolcache/node.exe"
            node.parent.mkdir()
            node.write_bytes(b"MZ" + bytes(64))
            for name in native.COPY_FILES:
                file = source / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(b"source-sha-preserved-" + name.encode("utf-8"))
            destination = area / "scratch"
            with patch.object(native, "SOURCE", source):
                isolated_tool = native.sandbox_from_checkout(
                    destination, node_executable=node)
                self.assertTrue((isolated_tool / "node/node.exe").is_file())
                self.assertEqual((isolated_tool / "node/node.exe").read_bytes(),
                                 node.read_bytes())
                self.assertEqual(list((isolated_tool / "automation/playwright").iterdir()), [])
                for name in native.COPY_FILES:
                    self.assertEqual((destination / name).read_bytes(),
                                     (source / name).read_bytes())
                self.assertFalse((destination / "tool/automation/browsers").exists())
                self.assertEqual(
                    (source / "tool/python-packages.in.txt").read_bytes(),
                    b"source-sha-preserved-tool/python-packages.in.txt")
                with self.assertRaisesRegex(ValueError, "must be new"):
                    native.sandbox_from_checkout(destination, node_executable=node)
                invalid = area / "bad"
                invalid.write_bytes(b"cannot be root")
                with self.assertRaisesRegex(ValueError, "must be new"):
                    native.sandbox_from_checkout(invalid, node_executable=node)

    def test_full_candidate_artifact_short_retention_and_same_run_cleanup(self):
        workflow = (ROOT / ".github/workflows/03-update-tools.yml").read_text(
            encoding="utf-8")
        self.assertEqual(workflow.count("retention-days: 1"), 1)
        verifier = workflow.split("\n  full_verify:", 1)[1].split(
            "\n  full_propose:", 1)[0]
        writer = workflow.split("\n  full_propose:", 1)[1].split(
            "\n  full_artifact_cleanup:", 1)[0]
        cleanup = workflow.split("\n  full_artifact_cleanup:", 1)[1]
        self.assertIn("full-stable-candidate-${{ github.run_id }}", verifier)
        self.assertIn("full-stable-candidate-${{ github.run_id }}", writer)
        self.assertIn("full-stable-candidate-${{ github.run_id }}", cleanup)
        self.assertIn("needs: [full_verify, full_propose]", cleanup)
        self.assertIn("always()", cleanup)
        self.assertIn("needs.full_verify.result == 'success'", cleanup)
        self.assertIn("needs.full_propose.result == 'success'", cleanup)
        self.assertIn("needs.full_propose.result == 'skipped'", cleanup)
        self.assertIn("!inputs.create_pr", cleanup)
        self.assertIn("permissions:\n      actions: write", cleanup)
        self.assertNotIn("contents: write", cleanup)
        self.assertNotIn("pull-requests: write", cleanup)
        self.assertNotIn("actions: write", verifier)
        self.assertNotIn("actions: write", writer)
        self.assertIn("actions: read", writer)
        self.assertIn("actions/runs/$GITHUB_RUN_ID/artifacts?per_page=100", cleanup)
        self.assertIn('r.get("name") == name', cleanup)
        self.assertIn('get("id") == run_id', cleanup)
        self.assertIn("len(found) > 1", cleanup)
        self.assertIn("gh api --method DELETE", cleanup)
        self.assertNotIn("gh run delete", cleanup)

    def test_full_major_targets_are_stable_versions_not_new_install_placeholders(self):
        plan = json.loads((ROOT / "tool/full-stable-upgrade-plan.json").read_text(
            encoding="utf-8"))
        names = [x["name"] for x in plan["targets"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(names), 14)
        entries = {x["name"]: x for x in plan["targets"]}
        for name, value in (
                ("python", "3.15.2"), ("pip", "26.3"),
                ("npm", "12.2.1"), ("corepack", "0.36.0"),
                ("7zip", "26.05"), ("playwright-mcp", "0.0.84"),
                ("pyinstaller", "6.22.3")):
            self.assertEqual(entries[name]["latestStable"], value)
        self.assertEqual(plan["state"], "PREPARATION_ONLY_NOT_INSTALLED")
        for name in ("python", "pip", "7zip", "corepack"):
            art = entries[name]["artifact"]
            self.assertTrue(art["url"].startswith("https://"))
            self.assertRegex(art["sha256"], r"^[a-f0-9]{64}$")
        # Same test runs before AND after Windows candidate staging. Never
        # mistake the read-only candidate's temporary ledger for a main merge.
        installed = json.loads((ROOT / "tool/installed-tools.json").read_text(
            encoding="utf-8"))["tools"]
        self.assertIn(installed["python"]["version"], ("3.14", "3.15.2"))
        self.assertIn(installed["npm"]["version"], ("11.20.0", "12.2.1"))

    def test_pip_263_and_source_only_pyyaml_are_official_and_hash_pinned(self):
        plan = json.loads((ROOT / "tool/full-stable-upgrade-plan.json").read_text(
            encoding="utf-8"))
        entries = {x["name"]: x for x in plan["targets"]}
        self.assertEqual(entries["pip"]["artifact"], {
            "url": "https://pypi.org/pypi/pip/26.3/json",
            "sha256": "f3b60b20ffaadd4415ed7957212a38ac63fa4c5fa375bd0f4a797777940fad13",
            "kind": "official-PyPI-metadata-pinned-wheel",
        })
        exceptions = plan["pythonPureSourceExceptions"]
        self.assertEqual(len(exceptions), 1)
        self.assertEqual(exceptions[0]["name"], "PyYAML")
        self.assertEqual(exceptions[0]["version"], "6.0.3")
        self.assertEqual(exceptions[0]["sourceSha256"],
                         "d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f")
        self.assertTrue(exceptions[0]["sourceUrl"].startswith(
            "https://files.pythonhosted.org/packages/"))
        code = (ROOT / "tool/full-stable-prepare.py").read_text(
            encoding="utf-8")
        self.assertIn('binary_requests = [x for x in requested', code)
        self.assertIn('resolved["pyyaml"] = stage_pyyaml_pure_wheel(', code)
        self.assertIn('build_pyyaml_pure_wheel(source, wheels, item["sourceSha256"])', code)
        self.assertIn('run(new_python, "-E", "-s", "-B", "-m", "pip", "--version")', code)
        self.assertNotIn("pyyaml-cp315", code)

    def test_pdf_policy_chooses_official_legacy_wheels_without_cp315_onnx(self):
        # Do not spend AC minutes installing other tools before checking PDF ABI.
        from unittest.mock import patch
        base = "https://files.pythonhosted.org/packages/verified/"
        def wheel(filename):
            return {"filename": filename, "url": base + filename,
                    "packagetype": "bdist_wheel",
                    "digests": {"sha256": "a" * 64}, "yanked": False}
        cp314 = wheel("onnxruntime-1.31.1-cp314-cp314-win_amd64.whl")
        cp315 = wheel("onnxruntime-1.31.1-cp315-cp315-win_amd64.whl")
        abi3 = wheel("onnxruntime-1.31.1-cp311-abi3-win_amd64.whl")
        self.assertFalse(stage.official_onnx_win315_wheel(cp314, "1.31.1"))
        self.assertTrue(stage.official_onnx_win315_wheel(cp315, "1.31.1"))
        self.assertTrue(stage.official_onnx_win315_wheel(abi3, "1.31.1"))
        modern = {"info": {"name": "onnxruntime", "version": "1.31.1"},
                  "urls": [cp314]}
        legacy = {
            "pymupdf": ("1.28.2", wheel("pymupdf-1.28.2-cp310-abi3-win_amd64.whl")),
            "pymupdf4llm": ("0.3.4", wheel("pymupdf4llm-0.3.4-py3-none-any.whl"))}
        calls = []
        def fake_download(url, file, **kwargs):
            calls.append(url)
            if url.endswith("/pypi/onnxruntime/json"):
                data = modern
            else:
                package = url.split("/")[4]
                version, record = legacy[package]
                self.assertTrue(url.endswith("/" + version + "/json"))
                data = {"info": {"name": package, "version": version}, "urls": [record]}
            Path(file).write_text(json.dumps(data), encoding="utf-8")
            return {"sha256": "a" * 64}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(stage, "download", side_effect=fake_download):
                fallback = {}
                stage.preflight_python315_onnxruntime(root, fallback)
                self.assertEqual(fallback["pdf_compatibility"]["mode"],
                                 "latest-compatible-legacy-pdf")
                self.assertEqual(fallback["pdf_compatibility"]["pymupdf"], "1.28.2")
                self.assertEqual(fallback["pdf_compatibility"]["pymupdf4llm"], "0.3.4")
                self.assertEqual(len(calls), 3)
                modern["urls"] = [cp314, cp315]
                latest = {}
                stage.select_pdf_compatibility(modern, root, latest)
                self.assertEqual(latest["pdf_compatibility"]["mode"], "latest-with-layout")
                self.assertIn(cp315["filename"],
                              latest["onnxruntime_preflight"]["wheels"])
        source = (ROOT / "tool/full-stable-prepare.py").read_text(encoding="utf-8")
        body = source.split("def prepare(plan: dict) -> None:", 1)[1]
        self.assertLess(body.index("preflight_python315_onnxruntime(temp, evidence)"),
                        body.index("stage_npm(plan, temp, evidence)"))
        self.assertIn("verify_pdf_resolver(pdf, resolved, evidence)", source)
        self.assertIn('x + (">=2.1"', source)

    def test_pdf_official_fallback_rejects_forged_wheels_and_downgraded_resolution(self):
        import copy
        base = "https://files.pythonhosted.org/packages/verified/"
        def wheel(filename):
            return {"filename": filename, "url": base + filename,
                    "packagetype": "bdist_wheel",
                    "digests": {"sha256": "a" * 64}, "yanked": False}
        file = "pymupdf-1.28.2-cp310-abi3-win_amd64.whl"
        record = wheel(file)
        release = {"info": {"name": "pymupdf", "version": "1.28.2"},
                   "urls": [record]}
        valid = stage.official_legacy_pdf_wheels(release, "pymupdf", "1.28.2")
        self.assertEqual(valid[file]["sha256"], "a" * 64)
        for item in (("wrong version", {"name": "pymupdf", "version": "1.28.0"}),
                     ("wrong name", {"name": "badpdf", "version": "1.28.2"})):
            bad = copy.deepcopy(release)
            bad["info"] = item[1]
            with self.subTest(case=item[0]), self.assertRaises(ValueError):
                stage.official_legacy_pdf_wheels(bad, "pymupdf", "1.28.2")
        for key, value in (("url", "https://bad.example/malware.whl"),
                           ("filename", "pymupdf-1.28.2-cp314-cp314-win_amd64.whl"),
                           ("digests", {"sha256": "0"}),
                           ("yanked", True)):
            bad = copy.deepcopy(release)
            bad["urls"][0][key] = value
            if key == "filename":
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, "Missing"):
                    stage.official_legacy_pdf_wheels(bad, "pymupdf", "1.28.2")
            else:
                with self.subTest(key=key), self.assertRaises(ValueError):
                    stage.official_legacy_pdf_wheels(bad, "pymupdf", "1.28.2")
        with self.assertRaises(ValueError):
            stage.official_legacy_pdf_wheels({"info": release["info"],
                                             "urls": [record, record]},
                                            "pymupdf", "1.28.2")
        policy = {"mode": "latest-compatible-legacy-pdf",
                  "pymupdf": "1.28.2", "pymupdf4llm": "0.3.4"}
        name4 = "pymupdf4llm-0.3.4-py3-none-any.whl"
        selected = {"pymupdf": {"version": "1.28.2", "wheel": file, "sha256": "a" * 64},
                    "pymupdf4llm": {"version": "0.3.4", "wheel": name4,
                                   "sha256": "a" * 64}}
        preflight = {"pdf_fallback_wheels": {
            "pymupdf": {file: {"url": base + file, "sha256": "a" * 64}},
            "pymupdf4llm": {name4: {"url": base + name4, "sha256": "a" * 64}}},
            "wheels": {"pymupdf": {"url": base + file},
                       "pymupdf4llm": {"url": base + name4}}}
        stage.verify_pdf_resolver(policy, selected, preflight)
        wrong = copy.deepcopy(selected)
        wrong["pymupdf4llm"]["sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "provenance"):
            stage.verify_pdf_resolver(policy, wrong, preflight)
        wrong = copy.deepcopy(selected)
        wrong["onnxruntime"] = {"version": "1.31.1"}
        with self.assertRaisesRegex(ValueError, "Layout/ONNX"):
            stage.verify_pdf_resolver(policy, wrong, preflight)

    def test_optional_manifest_hashes_staged_installed_wheels_before_replace(self):
        """Old 3.14 tool/python must not be used to hash the new manifest."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            temp = root / "tmp"
            tool = root / "tool"
            staged_site = temp / "python-runtime/Lib/site-packages"
            staged_site.mkdir(parents=True)
            tool.mkdir()
            initial = {"target": "old", "packages": [{"name": "defusedxml"}]}
            manifest = tool / "optional-python-manifest.json"
            manifest.write_text(json.dumps(initial), encoding="utf-8")
            wheelname = "defusedxml-0.7.1-py2.py3-none-any.whl"
            wheelurl = "https://files.pythonhosted.org/packages/verified/" + wheelname
            wheels = temp / "wheels"
            wheels.mkdir()
            entries = {
                "defusedxml/__init__.py": b"STAGED_NEW_PYTHON_WHEEL_BYTES\n",
                "defusedxml-0.7.1.dist-info/LICENSE": b"Upstream license\n",
            }
            with zipfile.ZipFile(wheels / wheelname, "w") as package:
                for name, data in entries.items():
                    package.writestr(name, data)
                    path = staged_site.joinpath(*name.split("/"))
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(data)
            checksum = "a" * 64
            resolved = {"defusedxml": {
                "version": "0.7.1", "wheel": wheelname, "sha256": checksum}}
            for name in ("pyinstaller", "pyinstaller-hooks-contrib",
                         "altgraph", "pefile", "pywin32-ctypes", "setuptools"):
                resolved[name] = {"version": "1.0", "sha256": checksum}
            evidence = {"wheels": {"defusedxml": {"url": wheelurl}}}
            metadata = {"info": {"name": "defusedxml", "version": "0.7.1"},
                        "urls": [{"packagetype": "bdist_wheel",
                                  "filename": wheelname, "url": wheelurl,
                                  "digests": {"sha256": checksum},
                                  "yanked": False}]}
            def official_json(url, output, **kwargs):
                self.assertEqual(url, "https://pypi.org/pypi/defusedxml/0.7.1/json")
                Path(output).write_text(json.dumps(metadata), encoding="utf-8")
                return {"sha256": checksum}
            with patch.object(stage, "ROOT", root), \
                 patch.object(stage, "TOOL", tool), \
                 patch.object(stage, "download", side_effect=official_json):
                stage.python_manifests(temp, resolved, evidence, staged_site=staged_site)
                after = json.loads(manifest.read_text(encoding="utf-8"))
                self.assertEqual(after["target"], "Windows x64 CPython 3.15.2")
                self.assertEqual(after["packages"][0]["source_distribution"], None)
                expected = {
                    "tool/python/Lib/site-packages/" + name: hashlib.sha256(data).hexdigest()
                    for name, data in entries.items()
                }
                self.assertEqual(after["packages"][0]["files"], expected)
                self.assertFalse((tool / "python/Lib/site-packages").exists())
                staged_site.joinpath("defusedxml-0.7.1.dist-info/LICENSE").unlink()
                with self.assertRaisesRegex(ValueError, "license"):
                    stage.python_manifests(temp, resolved, evidence,
                                           staged_site=staged_site)
                with self.assertRaisesRegex(ValueError, "staged CPython site"):
                    stage.python_manifests(temp, resolved, evidence,
                                           staged_site=root / "unrelated")
        code = (ROOT / "tool/full-stable-prepare.py").read_text(encoding="utf-8")
        body = code.split("def prepare(plan: dict) -> None:", 1)[1]
        self.assertLess(body.index("stage_python(plan, temp, evidence)"),
                        body.index("python_manifests(temp, resolved, evidence,"))
        self.assertLess(body.index("python_manifests(temp, resolved, evidence,"),
                        body.index("stage_7zip(plan, temp, evidence)"))
        self.assertLess(body.index("python_manifests(temp, resolved, evidence,"),
                        body.index("stage_browser(temp, version, revision, evidence)"))
        self.assertIn("FULL_STABLE_PHASE_END=optional_python_manifests;status=PASS",
                      body)
        self.assertEqual(body.count("python_manifests(temp, resolved, evidence,"), 1)

    def test_staged_pdf_pair_preserves_official_licenses_and_native_payload(self):
        """Verify actual 1.28.2 / 0.3.4 manifest policy before touching old Python."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tool, temp = root / "tool", root / "tmp"
            site = temp / "python-runtime/Lib/site-packages"
            site.mkdir(parents=True)
            tool.mkdir()
            (temp / "wheels").mkdir()
            rows = (
                ("PyMuPDF", "pymupdf", "1.28.2",
                 "pymupdf-1.28.2-cp310-abi3-win_amd64.whl", {
                    "pymupdf/__init__.py": b"official staged Python source",
                    "pymupdf/_mupdf.pyd": b"MZ" + bytes(50),
                    "pymupdf-1.28.2.dist-info/COPYING": b"upstream license",
                 }),
                ("pymupdf4llm", "pymupdf4llm", "0.3.4",
                 "pymupdf4llm-0.3.4-py3-none-any.whl", {
                    "pymupdf4llm/__init__.py": b"official staged Python source",
                    "pymupdf4llm-0.3.4.dist-info/licenses/LICENSE": b"upstream license",
                 }),
            )
            (tool / "optional-python-manifest.json").write_text(
                json.dumps({"packages": [{"name": row[0]} for row in rows]}),
                encoding="utf-8")
            resolved, evidence, metadata = {}, {"wheels": {}}, {}
            for label, name, version, wheelname, entries in rows:
                url = "https://files.pythonhosted.org/packages/verified/" + wheelname
                resolved[name] = {"version": version, "wheel": wheelname,
                                  "sha256": "a" * 64}
                evidence["wheels"][name] = {"url": url}
                with zipfile.ZipFile(temp / "wheels" / wheelname, "w") as wheel:
                    for item, body in entries.items():
                        wheel.writestr(item, body)
                        file = site.joinpath(*item.split("/"))
                        file.parent.mkdir(parents=True, exist_ok=True)
                        file.write_bytes(body)
                sdist = name + "-" + version + ".tar.gz"
                metadata[name] = {
                    "info": {"name": name, "version": version},
                    "urls": [
                        {"filename": wheelname, "url": url,
                         "packagetype": "bdist_wheel",
                         "digests": {"sha256": "a" * 64}},
                        {"filename": sdist, "packagetype": "sdist",
                         "url": "https://files.pythonhosted.org/packages/verified/" + sdist,
                         "digests": {"sha256": "b" * 64}},
                    ],
                }
            for name in ("pyinstaller", "pyinstaller-hooks-contrib", "altgraph",
                         "pefile", "pywin32-ctypes", "setuptools"):
                resolved[name] = {"version": "1.0", "sha256": "c" * 64}
            def mock_pypi(url, dest, **kwargs):
                name = url.split("/")[4]
                Path(dest).write_text(json.dumps(metadata[name]), encoding="utf-8")
                return {"sha256": "c" * 64}
            with patch.object(stage, "ROOT", root), \
                 patch.object(stage, "TOOL", tool), \
                 patch.object(stage, "download", side_effect=mock_pypi):
                stage.python_manifests(temp, resolved, evidence, staged_site=site)
                actual = json.loads((tool / "optional-python-manifest.json").read_text(
                    encoding="utf-8"))
                self.assertEqual([x["name"] for x in actual["packages"]],
                                 ["PyMuPDF", "pymupdf4llm"])
                self.assertTrue(all(x["source_distribution_status"] == "published"
                                    for x in actual["packages"]))
                self.assertEqual([len(x["files"]) for x in actual["packages"]], [3, 2])
                self.assertFalse((tool / "python").exists())
                (site / "pymupdf/_mupdf.pyd").unlink()
                with self.assertRaisesRegex(ValueError, "Native PyMuPDF"):
                    stage.python_manifests(temp, resolved, evidence,
                                           staged_site=site)

    def test_staged_python_native_and_pdf_smoke_precedes_7zip_chromium(self):
        """Run real native probes on Windows; prove their order offline."""
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder) / "python-runtime"
            runtime.mkdir()
            (runtime / "python.exe").write_bytes(b"MZ" + bytes(512))
            with patch.object(stage, "run") as execute:
                stage.smoke_staged_python(runtime, {
                    "mode": "latest-compatible-legacy-pdf"})
                self.assertEqual(execute.call_count, 2)
                first = execute.call_args_list[0].args
                second = execute.call_args_list[1].args
                self.assertEqual(first[1:], ("-E", "-s", "-B", "-m", "pip", "check"))
                self.assertEqual(second[1:5], ("-E", "-s", "-B", "-c"))
                self.assertIn("pymupdf4llm.to_markdown(doc)", second[5])
                self.assertIn("STAGED_PYTHON315_NATIVE_AND_PDF=PASS", second[5])
                self.assertIn("pandas,numpy,paramiko", second[5])
                self.assertIn("if True else modern", second[5])
                execute.reset_mock()
                stage.smoke_staged_python(runtime, {"mode": "latest-with-layout"})
                self.assertIn("if False else modern", execute.call_args_list[1].args[5])
                execute.reset_mock()
                with self.assertRaisesRegex(ValueError, "Unapproved staged Python PDF mode"):
                    stage.smoke_staged_python(runtime, {"mode": "unsafe"})
                self.assertEqual(execute.call_count, 0)
            (runtime / "python.exe").unlink()
            with self.assertRaisesRegex(ValueError, "Missing isolated staged CPython"):
                stage.smoke_staged_python(runtime, {"mode": "latest-with-layout"})
        script = (ROOT / "tool/full-stable-prepare.py").read_text(encoding="utf-8")
        body = script.split("def prepare(plan: dict) -> None:", 1)[1]
        self.assertLess(body.index("python_manifests(temp, resolved, evidence,"),
                        body.index("smoke_staged_python(staged_python,"))
        self.assertLess(body.index("smoke_staged_python(staged_python,"),
                        body.index("stage_7zip(plan, temp, evidence)"))
        self.assertLess(body.index("smoke_staged_python(staged_python,"),
                        body.index("stage_browser(temp, version, revision, evidence)"))
        self.assertIn("FULL_STABLE_PHASE_END=staged_python_smoke;status=PASS", body)

    def test_optional_pypi_release_metadata_wheel_only_and_rejects_forgery(self):
        import copy
        digest = "a" * 64
        base = "https://files.pythonhosted.org/packages/verified/"
        filename = "pymupdf4llm-2.1-py3-none-any.whl"
        wheelurl = base + filename
        release = {"info": {"name": "pymupdf4llm", "version": "2.1"}, "urls": [
            {"filename": filename, "packagetype": "bdist_wheel", "url": wheelurl,
             "digests": {"sha256": digest}, "yanked": False}]}
        check = stage.optional_release_provenance
        self.assertEqual(check(release, "pymupdf4llm", "2.1", filename, wheelurl, digest),
                         (None, "not_published_on_pypi"))
        src = {"filename": "pymupdf4llm-2.1.tar.gz", "packagetype": "sdist",
               "url": base + "pymupdf4llm-2.1.tar.gz",
               "digests": {"sha256": digest}, "yanked": False}
        release["urls"].append(src)
        self.assertEqual(check(release, "pymupdf4llm", "2.1", filename, wheelurl, digest),
                         ({"url": src["url"], "sha256": digest}, "published"))
        for mode in ("name", "version", "hash", "wheel_host", "wheel_yanked",
                     "missing_wheel", "source_hash", "source_host",
                     "source_yanked", "source_filename", "duplicate_source"):
            bad = copy.deepcopy(release)
            if mode == "name": bad["info"]["name"] = "attacker"
            if mode == "version": bad["info"]["version"] = "1.0"
            if mode == "hash": bad["urls"][0]["digests"]["sha256"] = "b" * 64
            if mode == "wheel_host": bad["urls"][0]["url"] = "https://invalid.example/w"
            if mode == "wheel_yanked": bad["urls"][0]["yanked"] = True
            if mode == "missing_wheel": bad["urls"].pop(0)
            if mode == "source_hash": bad["urls"][-1]["digests"]["sha256"] = "bad"
            if mode == "source_host": bad["urls"][-1]["url"] = "https://invalid.example/s"
            if mode == "source_yanked": bad["urls"][-1]["yanked"] = True
            if mode == "source_filename": bad["urls"][-1]["filename"] = "wrong.tar.gz"
            if mode == "duplicate_source": bad["urls"].append(copy.deepcopy(src))
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "optional"):
                check(bad, "pymupdf4llm", "2.1", filename, wheelurl, digest)

    def test_metadata_only_4llm_license_requires_exact_matching_core_and_layout(self):
        stub = {"tool/python/Lib/site-packages/pymupdf4llm-2.1.dist-info/METADATA":
                "a" * 64}
        parent = [{"name": "PyMuPDF", "version": "2.1",
                   "files": {"tool/python/Lib/site-packages/pymupdf4llm/__init__.py":
                             "a" * 64,
                             "tool/python/Lib/site-packages/pymupdf-2.1.dist-info/LICENSE":
                             "b" * 64}}]
        deps = {"pymupdf": {"version": "2.1"},
                "pymupdf-layout": {"version": "2.1"}}
        check = stage.optional_license_origin
        self.assertEqual(check("pymupdf4llm", "2.1", stub, parent, deps), "PyMuPDF")
        self.assertIsNone(check("defusedxml", "0.7.1",
                                {"tool/python/Lib/site-packages/d/LICENSE": "a" * 64},
                                [], {}))
        for name, version, files, pkg, closure in (
                ("tabulate", "0.10.0", stub, parent, deps),
                ("pymupdf4llm", "0.2.9", stub, parent, deps),
                ("pymupdf4llm", "2.1", dict(stub, **{"other.py": "b" * 64}), parent, deps),
                ("pymupdf4llm", "2.1", stub, [], deps),
                ("pymupdf4llm", "2.1", stub, parent,
                 {"pymupdf": {"version": "1.28.2"}, "pymupdf-layout": {"version": "2.1"}}),
                ("pymupdf4llm", "2.1", stub, parent,
                 {"pymupdf": {"version": "2.1"}, "pymupdf-layout": {"version": "1.28.2"}})):
            with self.subTest(name=name, version=version, files=files), self.assertRaises(ValueError):
                check(name, version, files, pkg, closure)

    def test_new_pymupdf_stable_floor_and_native_4llm_check(self):
        source = (ROOT / "tool/full-stable-prepare.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/03-update-tools.yml").read_text(
            encoding="utf-8")
        self.assertIn('x + (">=2.1" if pdf["mode"] == "latest-with-layout"', source)
        self.assertIn('"latest-compatible-legacy-pdf"', source)
        self.assertIn("optional_license_origin(name, version, files, packages, resolved)", source)
        self.assertIn("PYMUPDF4LLM_NATIVE=PASS", workflow)

    def test_pip_pinned_json_never_accepts_wrong_hash_or_untrusted_wheel(self):
        wheel = "pip-26.3-py3-none-any.whl"
        checksum = "f3b60b20ffaadd4415ed7957212a38ac63fa4c5fa375bd0f4a797777940fad13"
        url = "https://files.pythonhosted.org/packages/verified/" + wheel
        record = {"info": {"name": "pip", "version": "26.3"}, "urls": [
            {"filename": wheel, "packagetype": "bdist_wheel",
             "digests": {"sha256": checksum}, "url": url, "yanked": False}]}
        self.assertEqual(stage.select_official_pip_release_wheel(
            record, "26.3", checksum), url)
        import copy
        bad = copy.deepcopy(record)
        bad["urls"][0]["digests"]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            stage.select_official_pip_release_wheel(bad, "26.3", checksum)
        bad = copy.deepcopy(record)
        bad["urls"][0]["url"] = "https://attacker.example/pip-26.3-py3-none-any.whl"
        with self.assertRaises(ValueError):
            stage.select_official_pip_release_wheel(bad, "26.3", checksum)
        bad = copy.deepcopy(record)
        bad["urls"][0]["yanked"] = True
        with self.assertRaises(ValueError):
            stage.select_official_pip_release_wheel(bad, "26.3", checksum)
        bad = copy.deepcopy(record)
        bad["urls"].append(copy.deepcopy(bad["urls"][0]))
        bad["urls"][1]["yanked"] = False
        with self.assertRaises(ValueError):
            stage.select_official_pip_release_wheel(bad, "26.3", checksum)
        bad = copy.deepcopy(record)
        bad["info"]["version"] = "0.0.1"
        with self.assertRaises(ValueError):
            stage.select_official_pip_release_wheel(bad, "26.3", checksum)

    def test_offline_pyyaml_sdist_repackage_is_deterministic_and_never_runs_setup(self):
        import csv
        import base64
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "official.tar.gz"
            members = {
                "pyyaml-6.0.3/PKG-INFO": b"Metadata-Version: 2.3\nName: PyYAML\nVersion: 6.0.3\n",
                "pyyaml-6.0.3/LICENSE": b"Upstream MIT license test fixture\n",
                **{"pyyaml-6.0.3/lib/yaml/" + name:
                   (b"__version__ = '6.0.3'\n" if name == "__init__.py"
                    else b"# Verified upstream module structure test fixture\n")
                   for name in pure.PY_YAML_MODULES}
            }
            with tarfile.open(source, "w:gz") as archive:
                for name, content in sorted(members.items()):
                    entry = tarfile.TarInfo(name)
                    entry.size = len(content)
                    archive.addfile(entry, io.BytesIO(content))
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            first, second = root / "first", root / "second"
            first.mkdir()
            second.mkdir()
            built = pure.build_pyyaml_pure_wheel(source, first, digest)
            built2 = pure.build_pyyaml_pure_wheel(source, second, digest)
            self.assertEqual(hashlib.sha256(built.read_bytes()).hexdigest(),
                             hashlib.sha256(built2.read_bytes()).hexdigest())
            with zipfile.ZipFile(built) as archive:
                self.assertEqual(archive.testzip(), None)
                self.assertEqual(set(archive.namelist()),
                                 {"yaml/" + n for n in pure.PY_YAML_MODULES} |
                                 {"PyYAML-6.0.3.dist-info/METADATA",
                                  "PyYAML-6.0.3.dist-info/WHEEL",
                                  "PyYAML-6.0.3.dist-info/licenses/LICENSE",
                                  "PyYAML-6.0.3.dist-info/RECORD"})
                with archive.open("PyYAML-6.0.3.dist-info/RECORD") as f:
                    rows = list(csv.reader(io.TextIOWrapper(f, encoding="utf-8")))
                self.assertEqual(len(rows), len(pure.PY_YAML_MODULES) + 4)
                for name, record_sha, size in rows[:-1]:
                    payload = archive.read(name)
                    expected = base64.urlsafe_b64encode(
                        hashlib.sha256(payload).digest()).rstrip(b"=").decode("ascii")
                    self.assertEqual(record_sha, "sha256=" + expected)
                    self.assertEqual(int(size), len(payload))
            with self.assertRaisesRegex(ValueError, "SHA256"):
                pure.build_pyyaml_pure_wheel(source, root / "second", "0"*64)
            # The following ensures this path can never execute upstream code.
            pure_source = (ROOT / "tool/full_stable_pure_wheels.py").read_text(
                encoding="utf-8")
            self.assertNotIn("subprocess", pure_source)
            self.assertNotIn("setup.py", pure_source.split("def build_pyyaml_pure_wheel(", 1)[1])
            self.assertNotIn("compile(", pure_source)
            self.assertNotIn("eval(", pure_source)

    def test_pyyaml_source_rejects_traversal_symlink_and_unreviewed_modules(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, kind in (
                    ("pyyaml-6.0.3/../../payload.py", "file"),
                    ("pyyaml-6.0.3/lib/yaml/other.py", "file"),
                    ("pyyaml-6.0.3/link", "link")):
                source = root / "case.tar.gz"
                with tarfile.open(source, "w:gz") as archive:
                    item = tarfile.TarInfo(name)
                    if kind == "link":
                        item.type = tarfile.SYMTYPE
                        item.linkname = "../../evil"
                        archive.addfile(item)
                    else:
                        item.size = 4
                        archive.addfile(item, io.BytesIO(b"data"))
                out = root / "empty"
                out.mkdir(exist_ok=True)
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
                with self.subTest(name=name), self.assertRaises(ValueError):
                    pure.build_pyyaml_pure_wheel(source, out, digest)
                source.unlink()

    def test_official_npm_json_fail_closed_retry_and_fast_preflight(self):
        """AC18: malformed registry body is retried; forged valid JSON never is."""
        endpoint = "https://registry.npmjs.org/npm/12.2.1"
        tarball = "https://registry.npmjs.org/npm/-/npm-12.2.1.tgz"
        valid = {"name": "npm", "version": "12.2.1",
                 "dist": {"tarball": tarball, "integrity": "sha512-" + "a" * 88}}
        with tempfile.TemporaryDirectory() as folder:
            temp = Path(folder)
            calls = []
            bodies = [b"[object Object]", json.dumps(valid).encode("utf-8")]
            def fake_download(url, dest, **kwargs):
                self.assertEqual(url, endpoint)
                self.assertEqual(kwargs["accept"], "application/json")
                self.assertLessEqual(kwargs["timeout"], 20)
                calls.append(Path(dest).name)
                Path(dest).write_bytes(bodies.pop(0))
                return {"sha256": "a" * 64}
            with patch.object(stage, "download", side_effect=fake_download), \
                 patch.object(stage.time, "sleep") as delay:
                self.assertEqual(stage.npm_metadata("npm", "12.2.1", temp),
                                 (tarball, valid["dist"]["integrity"]))
                self.assertEqual(calls, ["npm-metadata-1.json",
                                         "npm-metadata-2.json"])
                delay.assert_called_once_with(1)
            for payload in (b"[object Object]", b"<html>blocked</html>", b"not json"):
                bodies = [payload] * 3
                with patch.object(stage, "download", side_effect=fake_download), \
                     patch.object(stage.time, "sleep") as delay:
                    with self.assertRaisesRegex(ValueError,
                                                "after 3 bounded attempts"):
                        stage.npm_metadata("npm", "12.2.1", temp)
                    self.assertEqual(delay.call_count, 2)
                # New paths for every call; failures leave no side-effect on
                # actual package-local installed npm or user files.
            for invalid in (
                    {"name": "not-npm", "version": "12.2.1", "dist": valid["dist"]},
                    {"name": "npm", "version": "12.2.2", "dist": valid["dist"]},
                    {"name": "npm", "version": "12.2.1",
                     "dist": {"tarball": "https://evil.invalid/file.tgz",
                              "integrity": valid["dist"]["integrity"]}},
                    {"name": "npm", "version": "12.2.1",
                     "dist": {"tarball": tarball, "integrity": "sha512-INVALID?"}}):
                bodies = [json.dumps(invalid).encode("utf-8")]
                with patch.object(stage, "download", side_effect=fake_download), \
                     patch.object(stage.time, "sleep") as delay:
                    with self.assertRaises(ValueError):
                        stage.npm_metadata("npm", "12.2.1", temp)
                    delay.assert_not_called()
            bad = temp / "npm-bad.json"
            bad.write_bytes(b"[object Object]")
            with self.assertRaisesRegex(stage.InvalidJsonPayload,
                                        "npm-bad.json.*sha256"):
                stage.obj(bad)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plan = {"targets": [{"name": "npm", "latestStable": "12.2.1"}]}
            with patch.object(stage, "ROOT", root), \
                 patch.object(stage, "npm_metadata",
                              return_value=(tarball, valid["dist"]["integrity"])) as lookup:
                stage.preflight_npm_registry(plan)
                self.assertEqual(lookup.call_count, 1)
                self.assertEqual(lookup.call_args.args[:2], ("npm", "12.2.1"))
                self.assertFalse(any((root / "tmp").iterdir()))
        workflow = (ROOT / ".github/workflows/03-update-tools.yml").read_text(
            encoding="utf-8")
        verifier = workflow.split("\n  full_verify:", 1)[1].split(
            "\n  full_propose:", 1)[0]
        self.assertLess(verifier.index("full-stable-prepare.py npm-preflight"),
                        verifier.index("Preflight real launcher and relocation"))
        self.assertLess(verifier.index("full-stable-prepare.py npm-preflight"),
                        verifier.index("full-stable-prepare.py prepare"))

    def test_official_npm_metadata_http_accept_json_is_not_archive(self):
        """Verify the real download adapter, not just a mocked metadata parser."""
        url = "https://registry.npmjs.org/npm/12.2.1"
        raw = b'{"name":"npm","version":"12.2.1"}'
        recorded = []
        def fake_urlopen(request, timeout):
            recorded.append((request.full_url, request.get_header("Accept"),
                             request.get_header("User-agent"), timeout))
            response = io.BytesIO(raw)
            response.url = url
            return response
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / "metadata.json"
            with patch.object(stage.urllib.request, "urlopen",
                              side_effect=fake_urlopen):
                item = stage.download(url, dest, limit=4*1024*1024,
                                      accept="application/json", timeout=20)
                self.assertEqual(dest.read_bytes(), raw)
                self.assertEqual(item["sha256"], hashlib.sha256(raw).hexdigest())
                with self.assertRaisesRegex(ValueError, "Unapproved artifact URL"):
                    stage.download("https://attacker.invalid/npm", Path(folder) / "bad",
                                   accept="application/json", timeout=20)
                with self.assertRaisesRegex(ValueError, "Unexpected official-download"):
                    stage.download(url, Path(folder) / "bad-accept",
                                   accept="text/html", timeout=20)
            self.assertEqual(len(recorded), 1)
            self.assertEqual(recorded[0][0], url)
            self.assertEqual(recorded[0][1], "application/json")
            self.assertEqual(recorded[0][3], 20)

    def test_npm_preflight_cli_is_metadata_only_and_cannot_stage_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = {"schema": 1, "platform": "win32-x64",
                    "state": "PREPARATION_ONLY_NOT_INSTALLED",
                    "policy": {"publish": "do not edit installed-tools.json before verification"}}
            plan_file = Path(directory) / "plan.json"
            plan_file.write_text(json.dumps(plan), encoding="utf-8")
            with patch.object(stage, "PLAN", plan_file), \
                 patch.object(stage.sys, "argv", ["full-stable-prepare.py", "npm-preflight"]), \
                 patch.object(stage, "preflight_npm_registry") as preflight, \
                 patch.object(stage, "prepare") as full_stage:
                self.assertEqual(stage.main(), 0)
                preflight.assert_called_once_with(plan)
                full_stage.assert_not_called()

    def test_npm12_user_and_global_config_are_separate_and_empty(self):
        # npm 12 rejects two config scopes pointing at one file even if empty.
        # Reproduce isolation with old bundled npm (no registry/network) before
        # spending AC minutes replacing npm or downloading Chromium.
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            project = temp / "browser-project"
            project.mkdir()
            env = stage.npm_env(temp)
            user = Path(env["NPM_CONFIG_USERCONFIG"])
            global_ = Path(env["NPM_CONFIG_GLOBALCONFIG"])
            self.assertNotEqual(user.resolve(), global_.resolve())
            self.assertTrue(user.is_relative_to(temp))
            self.assertTrue(global_.is_relative_to(temp))
            self.assertEqual(user.read_bytes(), b"")
            self.assertEqual(global_.read_bytes(), b"")
            self.assertEqual(env["NPM_CONFIG_REGISTRY"],
                             "https://registry.npmjs.org")
            self.assertEqual(env["PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"], "1")
            # An unexpected nonempty file must fail before npm or network.
            global_.write_text("registry=https://example.invalid\n",
                               encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must remain empty"):
                stage.npm_env(temp)
            global_.write_bytes(b"")
            self.assertNotEqual(
                stage.npm_env(temp)["NPM_CONFIG_USERCONFIG"],
                stage.npm_env(temp)["NPM_CONFIG_GLOBALCONFIG"])
            node = ROOT / "tool/node/node.exe"
            npm = ROOT / "tool/node/node_modules/npm/bin/npm-cli.js"
            if os.name != "nt" or not (node.is_file() and npm.is_file()):
                return
            # Existing trusted bundled npm also rejects duplicate npmrc and
            # proves the corrected paths work without contacting a registry.
            stage.verify_npm_config_isolation(node, npm, project, env)
            bad = dict(env)
            bad["NPM_CONFIG_GLOBALCONFIG"] = bad["NPM_CONFIG_USERCONFIG"]
            with self.assertRaisesRegex(ValueError, "Command failed"):
                stage.verify_npm_config_isolation(node, npm, project, bad)

    def test_npm_config_guard_happens_before_registry_package_install(self):
        source = (ROOT / "tool/full-stable-prepare.py").read_text(encoding="utf-8")
        npm = source.split("def npm_env(", 1)[1].split(
            "\ndef stage_browser(", 1)[0]
        self.assertIn('user = temp / "user.npmrc"', npm)
        self.assertIn('global_ = temp / "global.npmrc"', npm)
        self.assertIn('verify_npm_config_isolation(node, npm, project, env)', npm)
        self.assertLess(
            npm.index('verify_npm_config_isolation(node, npm, project, env)'),
            npm.index('run(node, npm, "install", "--package-lock-only"'))
        self.assertNotIn('temp / "empty.npmrc"', npm)

    def test_full_mode_attempts_small_npm_before_python_and_large_chromium(self):
        source = (ROOT / "tool/full-stable-prepare.py").read_text(encoding="utf-8")
        body = source.split("\ndef prepare(plan: dict) -> None:", 1)[1].split(
            "\ndef main() -> int:", 1)[0]
        self.assertLess(body.index("stage_npm(plan, temp, evidence)"),
                        body.index("stage_playwright(plan, temp, evidence)"))
        self.assertLess(body.index("stage_playwright(plan, temp, evidence)"),
                        body.index("stage_python(plan, temp, evidence)"))
        self.assertLess(body.index("stage_python(plan, temp, evidence)"),
                        body.index("stage_browser(temp, version, revision, evidence)"))
        for phase in ("node_npm_corepack", "playwright_mcp",
                      "python315_dependencies", "7zip", "chromium_payload"):
            self.assertIn("FULL_STABLE_PHASE_BEGIN=" + phase, body)
            self.assertIn("FULL_STABLE_PHASE_END=" + phase + ";status=PASS", body)

    def test_archive_paths_fail_closed(self):
        for text in ("", "..", "../evil", "a/../evil", "C:/thing",
                     "/absolute", "C:evil", "dir\\evil", "a//b", "foo.",
                     "CON", "AUX", "COM1.txt", "tool/name:stream", "hello?"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                stage.safe_path(text)
        self.assertEqual(stage.safe_path("chrome-win64/x64/chrome.exe"),
                         ("chrome-win64", "x64", "chrome.exe"))

    def test_unzip_rejects_traversal_symlink_and_colliding_case(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for names in (("../outside",), ("a/../x",), ("A", "a"),
                          ("C:/attack",)):
                archive = root / "case.zip"
                with zipfile.ZipFile(archive, "w") as f:
                    for name in names:
                        f.writestr(name, "sample")
                with self.subTest(names=names), self.assertRaises(ValueError):
                    stage.unzip_checked(archive, root / "out")
                archive.unlink()
            archive = root / "ok.zip"
            with zipfile.ZipFile(archive, "w") as f:
                f.writestr("root/file.txt", "safe")
            stage.unzip_checked(archive, root / "fine")
            self.assertEqual((root / "fine/root/file.txt").read_text(), "safe")

    def test_tar_rejects_symlinks_and_extra_roots(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            archive = root / "case.tgz"
            with tarfile.open(archive, "w:gz") as t:
                link = tarfile.TarInfo("package/redirect")
                link.type = tarfile.SYMTYPE
                link.linkname = "../../outside"
                t.addfile(link)
            with self.assertRaises(ValueError):
                stage.untar_checked(archive, root / "linked")
            with tarfile.open(archive, "w:gz") as t:
                file = tarfile.TarInfo("other/path")
                file.size = 4
                t.addfile(file, io.BytesIO(b"safe"))
            with self.assertRaises(ValueError):
                stage.untar_checked(archive, root / "bad")

    def test_pip_generated_console_launchers_are_owned_by_hash_record(self):
        # Reproduce pip wheel bootstrap on a synthetic target (no network, EXE
        # execution or host-site changes). python-lock.validate_runtime must
        # accept only the three hash-registered launchers.
        wheel_lock = load("tool/python-lock.py", "full_stable_lock_synthetic")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            site = root / "tool/python/Lib/site-packages"
            bin_dir = site / "bin"
            info = site / "pip-26.3.dist-info"
            bin_dir.mkdir(parents=True)
            info.mkdir()
            (info / "METADATA").write_text(
                "Metadata-Version: 2.3\nName: pip\nVersion: 26.3\n",
                encoding="utf-8")
            record = info / "RECORD"
            record.write_text(
                "pip/__init__.py,,\npip-26.3.dist-info/RECORD,,\n",
                encoding="utf-8")
            for name in ("pip.exe", "pip3.exe", "pip3.15.exe"):
                (bin_dir / name).write_bytes(b"MZ" + bytes(range(256)) * 5)
            stage.register_generated_pip_launchers(site)
            import csv
            with record.open("r", encoding="utf-8", newline="") as src:
                entries = list(csv.reader(src))
            launched = [row for row in entries if row[0].startswith("bin/")]
            self.assertEqual([row[0] for row in launched],
                             ["bin/pip.exe", "bin/pip3.exe", "bin/pip3.15.exe"])
            for name, digest, size in launched:
                path = site / name
                self.assertTrue(digest.startswith("sha256="))
                self.assertEqual(int(size), path.stat().st_size)
            wheel_lock.validate_runtime(root, b"pip==26.3\n")
            record.write_text("pip/__init__.py,,\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unowned Python bin"):
                wheel_lock.validate_runtime(root, b"pip==26.3\n")


    def test_pinned_vendor_multiarch_helpers_never_lose_active_amd64_guard(self):
        # setuptools 84.2.1 ships cli/gui.exe as byte-identical aliases
        # of cli/gui-32.exe; pip 26.3 vendored distlib ships x86 + ARM64
        # launcher templates. These are *not* the active program binaries.
        approved = stage.INERT_WHEEL_LAUNCHERS
        self.assertEqual(len(approved), 10)
        self.assertEqual(approved["setuptools/cli.exe"], 0x014c)
        self.assertEqual(approved["setuptools/gui.exe"], 0x014c)
        self.assertEqual(approved["pip/_vendor/distlib/t64-arm.exe"], 0xaa64)
        self.assertTrue(all(v in (0x014c, 0xaa64) for v in approved.values()))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "python"
            site = root / "Lib/site-packages"
            site.mkdir(parents=True)
            def write_pe(name, machine):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                binary = bytearray(320)
                binary[0:2] = b"MZ"
                binary[0x3c:0x40] = (0x90).to_bytes(4, "little")
                binary[0x90:0x94] = b"PE\x00\x00"
                binary[0x94:0x96] = machine.to_bytes(2, "little")
                path.write_bytes(binary)
                return path
            # Synthetic six active AMD64 PE files.
            for name in ("python.exe", "python315.dll", "python3.dll",
                         "Lib/site-packages/fast.pyd",
                         "Lib/site-packages/active.exe", "Lib/site-packages/more.dll"):
                write_pe(name, 0x8664)
            for name, machine in approved.items():
                self.assertEqual(stage.pe_machine(
                    write_pe("Lib/site-packages/" + name, machine)), machine)
            counts = stage.check_python_native_architecture(root)
            self.assertEqual(counts, {
                "amd64": 6,
                "inert_x86": 6,
                "inert_arm64": 4
            })
            malicious = write_pe("Lib/site-packages/other-package/cli-32.exe", 0x014c)
            with self.assertRaisesRegex(ValueError, "not Windows AMD64"):
                stage.check_python_native_architecture(root)
            malicious.unlink()
            wrong = write_pe("Lib/site-packages/setuptools/cli-32.exe", 0x8664)
            with self.assertRaisesRegex(ValueError, "PE machine mismatches"):
                stage.check_python_native_architecture(root)
            wrong.write_bytes(b"not a PE")
            with self.assertRaisesRegex(ValueError, "PE machine mismatches"):
                stage.check_python_native_architecture(root)
            write_pe("Lib/site-packages/setuptools/cli-32.exe", 0x014c)
            unexpected = write_pe("tooling/extra.exe", 0xaa64)
            with self.assertRaisesRegex(ValueError, "not Windows AMD64"):
                stage.check_python_native_architecture(root)
            unexpected.unlink()
            self.assertEqual(stage.check_python_native_architecture(root)["amd64"], 6)

    def test_pip_script_merge_occurs_only_after_all_other_base_wheel_install(self):
        script = (ROOT / "tool/full-stable-prepare.py").read_text(encoding="utf-8")
        func = script.split("def stage_python(", 1)[1].split("\ndef replace_tree(", 1)[0]
        self.assertIn("pip 26.3 is missing expected Windows launcher", func)
        install = func.index('for label, output in (("base", stage / "Lib/site-packages"),')
        merge = func.index('scripts = stage / "Lib/site-packages/bin"')
        register = func.index('register_generated_pip_launchers(stage / "Lib/site-packages")')
        self.assertLess(install, merge)
        self.assertLess(merge, register)
        self.assertNotIn('scripts.mkdir(exist_ok=True)', func)
        self.assertIn("Conflicting pip launcher in another installed distribution", func)
        self.assertIn('{"pyinstaller.exe", "pyi-makespec.exe"} <= before', func)
        self.assertIn("Another base package console launcher was removed", func)

    def test_7zip_official_full_sfx_pe_amd64_and_paired_dll_policy(self):
        plan = json.loads((ROOT / "tool/full-stable-upgrade-plan.json").read_text(
            encoding="utf-8"))
        seven = next(x for x in plan["targets"] if x["name"] == "7zip")
        self.assertEqual(seven["artifact"]["url"],
                         "https://github.com/ip7z/7zip/releases/download/26.05/7z2605-x64.exe")
        self.assertEqual(seven["artifact"]["sha256"],
                         "fd99e86f57d8f429ef5ed045bf98315af962e2309b0f1ba87a147a44c71647d0")
        code = (ROOT / "tool/full-stable-prepare.py").read_text(encoding="utf-8")
        self.assertIn("run(old_exe, \"x\",", code)
        self.assertNotIn("run(archive,", code)
        self.assertIn('chosen["7z.exe"].parent == chosen["7z.dll"].parent', code)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "candidate.exe"
            def pe(machine):
                data = bytearray(320)
                data[0:2] = b"MZ"
                data[0x3c:0x40] = (0x90).to_bytes(4, "little")
                data[0x90:0x94] = b"PE\x00\x00"
                data[0x94:0x96] = machine.to_bytes(2, "little")
                return data
            path.write_bytes(pe(0x8664))
            self.assertTrue(stage.pe_amd64(path))
            path.write_bytes(pe(0x14c))
            self.assertFalse(stage.pe_amd64(path))
            path.write_bytes(pe(0xaa64))
            self.assertFalse(stage.pe_amd64(path))
            path.write_bytes(b"MZ" + b"\x00" * 5)
            self.assertFalse(stage.pe_amd64(path))

    def test_pip_upgrade_preserves_all_local_portable_wrappers(self):
        code = (ROOT / "tool/full-stable-prepare.py").read_text(encoding="utf-8")
        for name in ("pip.exe", "pip3.exe", "pip3.15.exe"):
            self.assertIn(name, code)
        self.assertIn('pip_launcher_lock.write_text(', code)
        self.assertIn('"--require-hashes", "--no-warn-script-location"', code)
        self.assertIn('TOOL / "refresh-python-cli-shims.py"', code)
        self.assertLess(code.index('vendor = pip_launch / "bin"'),
                        code.index('replace_tree(staged_python, TOOL / "python", temp)'))

    def test_writer_filenames_allow_only_owned_tool_files(self):
        for name in (".github/workflows/02.yml", "codex.exe", "tool/python/../evil",
                     "tool/bin/evil.exe", "tool/bin/other.ps1", "tool/python/x.pyc",
                     "tool/automation/browsers/../../evil", "tool/foo.json"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                transfer.checked_name(name)
        self.assertEqual(transfer.checked_name("tool/python/python315.dll"),
                         "tool/python/python315.dll")
        self.assertEqual(transfer.checked_name("tool/bin/pip3.15.cmd"),
                         "tool/bin/pip3.15.cmd")

    def test_readonly_git_patch_and_writer_reconstruct_identical_bytes(self):
        if not shutil_which_git():
            self.skipTest("Git command missing")
        paths = [
            "tool/python/python315.dll", "tool/python/python315.zip",
            "tool/node/node_modules/npm/package.json",
            "tool/node/node_modules/corepack/package.json",
            "tool/automation/versions.json", "tool/bin/7z.exe", "tool/bin/7z.dll",
            "tool/installed-tools.json", "tool/full-stable-evidence.json",
            "tool/python-packages.in.txt", "tool/工具更新说明.md"
        ]
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            subprocess.run(["git", "init", "-q", str(tmp)], check=True)
            (tmp / ".gitignore").write_text("/tmp/\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(tmp), "add", ".gitignore"], check=True)
            subprocess.run(["git", "-C", str(tmp), "-c", "user.name=test",
                            "-c", "user.email=test@example.invalid",
                            "commit", "-qm", "base"], check=True)
            base = subprocess.check_output(
                ["git", "-C", str(tmp), "rev-parse", "HEAD"], text=True).strip()
            for i, path in enumerate(paths):
                target = tmp / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(("payload " + str(i) + "\n").encode("utf-8"))
            subprocess.run(["git", "-C", str(tmp), "add", "-A", "--", "tool"],
                           check=True)
            (tmp / "tmp").mkdir()
            archive = tmp / "tmp/candidate.zip"
            with patch.object(transfer, "ROOT", tmp):
                transfer.pack(archive, base)
                archived_sha = transfer.digest_file(archive)
                diff = transfer.diff_sha()
                subprocess.run(["git", "-C", str(tmp), "reset", "--hard", "HEAD"],
                               check=True, capture_output=True)
                transfer.apply(archive, archived_sha, diff, base)
                self.assertEqual(transfer.diff_sha(), diff)
                self.assertEqual(len(transfer.changes()), len(paths))
                archive.touch()
                with self.assertRaisesRegex(ValueError, "differs"):
                    transfer.apply(archive, "0" * 64, diff, base)

    def test_repository_contains_no_automatic_full_upgrade_trigger(self):
        source = (ROOT / ".github/workflows/03-update-tools.yml").read_text(
            encoding="utf-8")
        self.assertTrue(source.startswith('name: "03 -'))
        self.assertIn("\non:\n  workflow_dispatch:\n", source)
        for event in ("\n  push:", "\n  schedule:", "\n  pull_request:",
                      "\n  workflow_run:"):
            self.assertNotIn(event, source)


def shutil_which_git() -> bool:
    import shutil
    return shutil.which("git") is not None


if __name__ == "__main__":
    unittest.main()
