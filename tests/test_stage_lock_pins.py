"""Offline tests for the retained fixed-wheel staging lock edit; no installation."""
import hashlib
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).absolute().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "stage_lock_pins", ROOT / "tests/stage_office_data_stable_refresh.py")
stage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage)
OLD = "81a9e26dd42fd28a23a2d169d86d7ac03b46e2f8b59ed4698fb4785f946d0176"
SYNTHETIC = "b" * 64


def lock_bytes(raw, lines):
    return (b"# Codex Portable wheel lock v1\r\n# requirements-sha256: " +
            hashlib.sha256(raw).hexdigest().encode("ascii") + b"\r\n" + lines)


class StageLockPinsTests(unittest.TestCase):
    def test_current_pygments_pin_and_hash_noop(self):
        raw = (ROOT / "tool/python-packages.in.txt").read_bytes()
        locked = (ROOT / "tool/python-packages.lock.txt").read_bytes()
        self.assertEqual(stage.update_locks(raw, locked, "pygments", "2.20.0", "2.20.0", OLD, OLD),
                         (raw, locked))
        with self.assertRaises(ValueError):
            stage.update_locks(raw, locked, "Pygments", "2.20.0", "2.20.0", SYNTHETIC, OLD)

    def test_canonical_unique_match_preserves_other_bytes(self):
        raw = b"# Demo_Pkg==1.0\r\nDemo_Pkg==1.0\r\nDemo-Pkg-extra==1.0\r\n"
        lines = (b"demo.pkg==1.0 --hash=sha256:" + b"a" * 64 + b"\r\n" +
                 b"demo-pkg-extra==1.0 --hash=sha256:" + b"c" * 64 + b"\r\n")
        locked = lock_bytes(raw, lines)
        updated = stage.update_locks(raw, locked, "DEMO--PKG", "1.0", "2.0", "a" * 64, SYNTHETIC)
        expected_input = raw.replace(b"\r\nDemo_Pkg==1.0\r\n", b"\r\nDemo_Pkg==2.0\r\n")
        expected_lock = lock_bytes(expected_input, lines.replace(
            b"demo.pkg==1.0 --hash=sha256:" + b"a" * 64,
            b"demo.pkg==2.0 --hash=sha256:" + SYNTHETIC.encode("ascii")))
        self.assertEqual(updated, (expected_input, expected_lock))

    def test_missing_duplicate_wrong_version_and_stale_digest_fail_closed(self):
        raw = b"Pygments==2.20.0\n"
        line = b"pygments==2.20.0 --hash=sha256:" + OLD.encode("ascii") + b"\r\n"
        locked = lock_bytes(raw, line)
        for candidate, candidate_lock, name, old in (
            (raw, locked, "missing", "2.20.0"),
            (raw, locked, "pygments", "2.19.0"),
            (raw + b"PYGMENTS==2.20.0\n", lock_bytes(raw + b"PYGMENTS==2.20.0\n", line), "pygments", "2.20.0"),
            (raw, lock_bytes(raw, line + line.replace(b"pygments", b"PYGMENTS")), "pygments", "2.20.0"),
            (raw + b"# changed\n", locked, "pygments", "2.20.0"),
        ):
            with self.subTest(candidate=candidate, name=name, old=old):
                with self.assertRaises(ValueError):
                    stage.update_locks(candidate, candidate_lock, name, old, "2.20.0", OLD, OLD)


if __name__ == "__main__":
    unittest.main()
