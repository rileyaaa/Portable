"""Static regression checks; these do not replace Windows TUI acceptance tests."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SETTING = "CODEX_TUI_FULLSCREEN_TRANSCRIPT"
NORMAL = "\u5e38\u7528\u6a21\u5f0f\u4e13\u7528\u5305"
YOLO = "YOLO mode\u4e13\u7528\u5305"


class FullscreenPreferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = (ROOT / "env.ps1").read_text(encoding="utf-8-sig")
        cls.launcher_source = (ROOT / "run-codex.ps1").read_text(encoding="utf-8-sig")

    def test_explicit_default_is_false(self):
        lines = re.findall(r'^\$env:CODEX_TUI_FULLSCREEN_TRANSCRIPT\s*=\s*"([^"]*)"\s*$', self.env, re.M)
        self.assertEqual(lines, ["false"])

    def test_local_override_is_allowlisted_not_protected(self):
        allowed = self.env.split("$supportedCodex =", 1)[1].split("$doubleAssignmentPattern =", 1)[0]
        protected = self.env.split("$protectedExact =", 1)[1].split("$supportedCodex =", 1)[0]
        self.assertEqual(allowed.count("'" + SETTING + "'"), 1)
        self.assertNotIn("'" + SETTING + "'", protected)

    def test_override_loaded_before_bool_validation(self):
        statement = "$TuiFullscreenTranscript = Convert-ToTomlBool -Value $env:" + SETTING + " -Default $false"
        self.assertEqual(self.launcher_source.count(statement), 1)
        self.assertLess(self.launcher_source.index(". $EnvFile"), self.launcher_source.index(statement))
        self.assertLess(self.launcher_source.index(statement), self.launcher_source.index("$ConfiguredAuthMode = $env:CODEX_AUTH_MODE"))

    def test_value_is_emitted_as_a_toml_bool(self):
        statement = '[void]$Builder.AppendLine("fullscreen_transcript = $TuiFullscreenTranscript")'
        self.assertEqual(self.launcher_source.count(statement), 1)
        section = self.launcher_source.split('[void]$Builder.AppendLine("[tui]")', 1)[1]
        self.assertTrue(section.lstrip().startswith(statement))
        self.assertNotIn('fullscreen_transcript = "', section.split('[tui.keymap.chat]', 1)[0])

    def test_mode_copies_preserve_existing_policy_differences(self):
        root_env = (ROOT / "env.ps1").read_bytes()
        root_run = (ROOT / "run-codex.ps1").read_bytes()
        history = ROOT / "Version_History"
        self.assertEqual((history / (NORMAL + "-env.ps1")).read_bytes(), root_env)
        for prefix in (NORMAL, YOLO):
            self.assertEqual((history / (prefix + "-run-codex.ps1")).read_bytes(), root_run)
        expected_yolo = root_env
        for old, new in (
            (b'CODEX_APPROVAL_POLICY = "on-request"', b'CODEX_APPROVAL_POLICY = "never"'),
            (b'CODEX_SANDBOX_MODE = "workspace-write"', b'CODEX_SANDBOX_MODE = "danger-full-access"'),
            (b'CODEX_SANDBOX_NETWORK_ACCESS = "false"', b'CODEX_SANDBOX_NETWORK_ACCESS = "true"'),
        ):
            self.assertEqual(expected_yolo.count(old), 1)
            expected_yolo = expected_yolo.replace(old, new, 1)
        self.assertEqual((history / (YOLO + "-env.ps1")).read_bytes(), expected_yolo)

    def test_does_not_replace_no_daemon_isolation(self):
        self.assertIn("function Get-PortableInteractiveLaunchArgs", self.launcher_source)
        self.assertIn("return @('--no-daemon') + @($LaunchArgs)", self.launcher_source)
        self.assertIn('$env:CODEX_HOME = Join-Path $Root "home"', self.launcher_source)


if __name__ == "__main__":
    unittest.main()
