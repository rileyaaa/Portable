"""Exercise wheel-lock generation with synthetic pip reports; never install packages."""
import importlib.util
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).absolute().parents[1]
SCRIPT = ROOT / "tool/python-lock.py"
spec = importlib.util.spec_from_file_location("portable_python_lock", SCRIPT)
lock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lock)


def report_item(name="demo", version="1.2.3"):
    return {
        "is_direct": False, "is_yanked": False,
        "metadata": {"name": name, "version": version},
        "download_info": {
            "url": f"https://files.pythonhosted.org/packages/{name}-{version}-py3-none-any.whl",
            "archive_info": {"hashes": {"sha256": "a" * 64}},
        },
    }


class PythonLockTests(unittest.TestCase):
    requirements = b"# synthetic input\ndemo==1.2.3\n"

    def report(self):
        return {"version": "1", "install": [report_item(), report_item("dependency", "2.0")]}

    @contextmanager
    def runtime_fixture(self):
        scratch = ROOT / "tmp"
        lock.checked_directory(ROOT, ROOT)
        if not scratch.exists() and not scratch.is_symlink():
            scratch.mkdir()
        lock.checked_directory(ROOT, scratch)
        with tempfile.TemporaryDirectory(prefix="runtime-repair-", dir=scratch) as temp:
            package = Path(temp) / "portable"
            site = package / "tool/python/Lib/site-packages"
            site.mkdir(parents=True)
            self.write_distribution(site)
            (site / "bin").mkdir()
            (site / "bin/demo.exe").write_bytes(b"synthetic launcher")
            yield package, site

    @staticmethod
    def write_distribution(site, name="demo", version="1.2.3", folder=None):
        metadata = site / (folder or f"{name}-{version}.dist-info")
        metadata.mkdir()
        (metadata / "METADATA").write_text(f"Name: {name}\nVersion: {version}\n", encoding="utf-8")
        (metadata / "RECORD").write_text("bin/demo.exe,,\n", encoding="utf-8")
        return metadata

    def test_runtime_repair_accepts_current_defaults_and_missing_packages(self):
        lock.validate_runtime(ROOT, (ROOT / "tool/python-packages.in.txt").read_bytes())
        with self.runtime_fixture() as (package, site):
            lock.validate_runtime(package, self.requirements + b"missing==9.0\n")
            # pip and uv use different relative RECORD names for target/bin.
            (site / "demo-1.2.3.dist-info/RECORD").write_text("../../bin/demo.exe,,\n", encoding="utf-8")
            lock.validate_runtime(package, self.requirements)
            (site / "bin/demo.exe").unlink()
            (site / "bin").rmdir()
            lock.validate_runtime(package, self.requirements)

    def test_runtime_repair_refuses_ambiguous_or_extended_installations(self):
        for problem in ("duplicate", "extra", "version", "custom-launcher"):
            with self.subTest(problem=problem), self.runtime_fixture() as (package, site):
                if problem == "duplicate":
                    self.write_distribution(site, folder="duplicate.dist-info")
                elif problem == "extra":
                    self.write_distribution(site, name="additional")
                elif problem == "version":
                    (site / "demo-1.2.3.dist-info/METADATA").write_text("Name: demo\nVersion: 2.0\n", encoding="utf-8")
                else:
                    (site / "bin/custom.cmd").write_bytes(b"user launcher")
                before = {str(path.relative_to(site)): path.read_bytes() for path in site.rglob("*") if path.is_file()}
                with self.assertRaisesRegex(ValueError, "repairs only the fixed default runtime set"):
                    lock.validate_runtime(package, self.requirements)
                after = {str(path.relative_to(site)): path.read_bytes() for path in site.rglob("*") if path.is_file()}
                self.assertEqual(before, after)

    def test_runtime_repair_rejects_linked_and_oversized_metadata(self):
        for target in ("demo-1.2.3.dist-info/METADATA", "demo-1.2.3.dist-info/RECORD", "bin/demo.exe"):
            with self.subTest(target=target), self.runtime_fixture() as (package, site):
                path = site / target
                outside = package.parent / "outside.txt"
                outside.write_bytes(path.read_bytes())
                path.unlink()
                try:
                    os.link(outside, path)
                except OSError as error:
                    self.skipTest(f"Hard links unavailable: {error}")
                with self.assertRaisesRegex(ValueError, "single-link"):
                    lock.validate_runtime(package, self.requirements)
        with self.runtime_fixture() as (package, site):
            metadata = site / "demo-1.2.3.dist-info/METADATA"
            with metadata.open("r+b") as stream:
                stream.truncate(lock.MAX_INPUT_BYTES + 1)
            with self.assertRaisesRegex(ValueError, "bounded size"):
                lock.validate_runtime(package, self.requirements)

    def test_report_records_direct_and_transitive_hashes(self):
        body = lock.build_lock(self.report(), self.requirements)
        self.assertIn("dependency==2.0 --hash=sha256:" + "a" * 64, body)
        lock.validate_lock(body.encode(), self.requirements)

    def test_changed_input_cannot_reuse_existing_lock(self):
        body = lock.build_lock(self.report(), self.requirements).encode()
        for changed in (b"demo==2.0\n", self.requirements + b"# changed\n"):
            with self.assertRaisesRegex(ValueError, "input changed"):
                lock.validate_lock(body, changed)

    def test_non_wheels_untrusted_sources_and_direct_urls_are_refused(self):
        for url in (
            "https://files.pythonhosted.org/source.tar.gz",
            "https://example.com/demo.whl",
            "http://files.pythonhosted.org/demo.whl",
            "https://user:password@files.pythonhosted.org/demo.whl",
            "file:///local/demo.whl",
        ):
            report = self.report()
            report["install"][0]["download_info"]["url"] = url
            with self.subTest(url=url), self.assertRaises(ValueError):
                lock.build_lock(report, self.requirements)
        for key in ("is_direct", "is_yanked"):
            report = self.report()
            report["install"][0][key] = True
            with self.subTest(key=key), self.assertRaises(ValueError):
                lock.build_lock(report, self.requirements)

    def test_missing_hash_conflicts_and_missing_direct_pin_are_refused(self):
        reports = []
        report = self.report()
        del report["install"][0]["download_info"]["archive_info"]["hashes"]
        reports.append(report)
        report = self.report()
        report["install"].append(report_item("demo", "9.0"))
        reports.append(report)
        report = self.report()
        report["install"][0]["metadata"]["version"] = "9.0"
        reports.append(report)
        reports.append({"version": "1", "install": []})
        for report in reports:
            with self.subTest(report=report), self.assertRaises(ValueError):
                lock.build_lock(report, self.requirements)

    def test_lock_options_and_unpinned_direct_inputs_are_refused(self):
        body = lock.build_lock(self.report(), self.requirements)
        for extra in ("--index-url https://example.com", "demo", "other @ https://example.com/pkg.whl"):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                lock.validate_lock((body + extra + "\n").encode(), self.requirements)
            with self.assertRaises(ValueError):
                lock.requirements_pins((extra + "\n").encode())

    def test_cli_is_relocatable_and_rejects_external_or_linked_inputs(self):
        for ancestor in (*reversed(ROOT.parents), ROOT):
            info = ancestor.lstat()
            self.assertTrue(stat.S_ISDIR(info.st_mode))
            self.assertFalse(getattr(info, "st_file_attributes", 0) & 0x400)
        scratch = ROOT / "tmp"
        if scratch.exists() or scratch.is_symlink():
            lock._ordinary(scratch, directory=True)
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="python-lock-", dir=scratch) as temp:
            base = Path(temp)
            package = base / "便携 New Package"
            (package / "tool").mkdir(parents=True)
            for marker in ("codex.exe", "env.ps1"):
                (package / marker).write_bytes(b"synthetic marker")
            # Runtime markers are only inspected, never parsed as lock inputs.
            with (package / "codex.exe").open("r+b") as marker:
                marker.truncate(lock.MAX_INPUT_BYTES + 1)
            script = package / "tool/python-lock.py"
            shutil.copyfile(SCRIPT, script)
            requirements = package / "tool/input.txt"
            requirements.write_bytes(self.requirements)
            report = package / "report.json"
            report.write_text(json.dumps(self.report()), encoding="utf-8")
            target = package / "candidate.txt"
            env = os.environ.copy()
            env["CODEX_INSTALL_DIR"] = str(base / "old location")

            def invoke(*extra):
                return subprocess.run(
                    [sys.executable, "-B", str(script), *extra],
                    cwd=base, env=env, capture_output=True, text=True, timeout=15,
                )

            result = invoke("validate-input", "--requirements", str(requirements))
            self.assertEqual(result.returncode, 0, result.stderr)
            requirements.write_text("--index-url https://example.com\n", encoding="utf-8")
            result = invoke("validate-input", "--requirements", str(requirements))
            self.assertEqual(result.returncode, 2)
            self.assertFalse(target.exists())
            requirements.write_bytes(self.requirements)
            args = ("build", "--report", str(report), "--requirements", str(requirements), "--output", str(target))
            result = invoke(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = invoke("validate", "--lock", str(target), "--requirements", str(requirements))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(invoke(*args).returncode, 2)  # never overwrite a candidate
            with report.open("r+b") as oversized:
                oversized.truncate(lock.MAX_INPUT_BYTES + 1)
            target.unlink()
            self.assertEqual(invoke(*args).returncode, 2)
            self.assertFalse(target.exists())
            report.write_text(json.dumps(self.report()), encoding="utf-8")
            self.assertEqual(invoke(*args).returncode, 0)
            external = base / "outside.txt"
            external.write_bytes(self.requirements)
            denied = invoke("validate", "--lock", str(target), "--requirements", str(external))
            self.assertEqual(denied.returncode, 2)
            requirements.unlink()
            try:
                os.link(external, requirements)
            except OSError as error:
                self.skipTest(f"Hard links unavailable: {error}")
            self.assertEqual(invoke("validate", "--lock", str(target), "--requirements", str(requirements)).returncode, 2)
            requirements.unlink()
            try:
                requirements.symlink_to(external)
            except OSError as error:
                self.skipTest(f"Symbolic links unavailable: {error}")
            self.assertEqual(invoke("validate", "--lock", str(target), "--requirements", str(requirements)).returncode, 2)


if __name__ == "__main__":
    unittest.main()
