"""Release mode templates must follow the current launcher and approved deltas."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ModeCopyTests(unittest.TestCase):
    def test_common_mode_is_identical_to_root(self):
        for name in ("env.ps1", "run-codex.ps1"):
            with self.subTest(file=name):
                self.assertEqual(
                    (ROOT / name).read_bytes(),
                    (ROOT / "Version_History" / ("常用模式专用包-" + name)).read_bytes(),
                )

    def test_yolo_only_changes_approved_policy_values(self):
        self.assertEqual(
            (ROOT / "run-codex.ps1").read_bytes(),
            (ROOT / "Version_History/YOLO mode专用包-run-codex.ps1").read_bytes(),
        )
        expected = (ROOT / "env.ps1").read_bytes()
        for setting, old, new in (
            ("CODEX_APPROVAL_POLICY", "on-request", "never"),
            ("CODEX_SANDBOX_MODE", "workspace-write", "danger-full-access"),
            ("CODEX_SANDBOX_NETWORK_ACCESS", "false", "true"),
        ):
            source = f'$env:{setting} = "{old}"'.encode()
            self.assertEqual(expected.count(source), 1)
            expected = expected.replace(source, f'$env:{setting} = "{new}"'.encode())
        self.assertIn(b'$env:CODEX_PORTABLE_PROFILE = "strict"', expected)
        self.assertEqual(
            expected, (ROOT / "Version_History/YOLO mode专用包-env.ps1").read_bytes()
        )


if __name__ == "__main__":
    unittest.main()
