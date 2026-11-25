"""Offline tests of package-local SSH state and sensitive-path boundaries."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
from pathlib import Path
import os
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).absolute().parents[1]
SOURCE = ROOT / "tool" / "portable-ssh.py"
SPEC = importlib.util.spec_from_file_location("portable_ssh_under_test", SOURCE)
SSH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SSH)


class FakeKey:
    def asbytes(self):
        return b"ssh-key-wire-bytes"

    def get_name(self):
        return "ssh-ed25519"

    def get_base64(self):
        return base64.b64encode(self.asbytes()).decode("ascii")


class FakeClient:
    def __init__(self):
        self.loaded = None
        self.policy = None
        self.options = None
        self.closed = False

    def load_host_keys(self, path):
        self.loaded = path

    def set_missing_host_key_policy(self, policy):
        self.policy = policy

    def connect(self, *, hostname, port, username, key_filename, passphrase,
                allow_agent, look_for_keys, timeout, auth_timeout,
                banner_timeout, gss_kex=False):
        # Deliberately emulate real Paramiko 5.1.0 signature; a catch-all
        # **kwargs masked a real production TypeError in the original tests.
        self.options = dict(hostname=hostname, port=port, username=username,
                            key_filename=key_filename, passphrase=passphrase,
                            allow_agent=allow_agent, look_for_keys=look_for_keys,
                            timeout=timeout, auth_timeout=auth_timeout,
                            banner_timeout=banner_timeout, gss_kex=gss_kex)

    def close(self):
        self.closed = True


class FakeParamiko:
    class RejectPolicy:
        pass

    def __init__(self):
        self.client = FakeClient()

    def SSHClient(self):
        return self.client


class RetainedBuffer(io.BytesIO):
    def close(self):
        pass


class FakeSFTP:
    def __init__(self):
        self.data = RetainedBuffer()
        self.mode = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def getfo(self, remote, handle):
        assert remote == "/var/log/demo.log"
        handle.write(b"synthetic downloaded content\n")

    def open(self, remote, mode):
        assert remote == "/tmp/demo.log"
        if mode == "xb":
            raise OSError("File not open for writing")
        self.mode = mode
        return self.data

    def remove(self, remote):
        assert remote == "/tmp/demo.log"


class FakeTransferClient:
    def __init__(self):
        self.sftp = FakeSFTP()

    def open_sftp(self):
        return self.sftp


class PortableSSHTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="portable-ssh-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "portable"
        self.root.mkdir()
        self.ws = SSH.Workspace(self.root)

    def test_local_workspace_and_windows_name_checks(self):
        self.assertEqual(
            self.ws.path("downloads", "logs/中文 文本.txt"),
            self.root / "work/ssh/downloads/logs/中文 文本.txt",
        )
        self.assertTrue((self.root / "work/ssh/downloads/logs").is_dir())
        for name in (
            "../escape", "logs/../escape", "/etc/passwd", "C:\\secret",
            "folder//test", "folder/./test", "NUL.txt", "data/file.",
            "a\x00b", "bad:name",
        ):
            with self.subTest(name=name):
                with self.assertRaises(SSH.SSHBoundaryError):
                    self.ws.path("downloads", name)

    def test_linked_ancestors_and_files_are_rejected(self):
        target = self.ws.path("uploads", "source.dat")
        target.write_bytes(b"synthetic")
        duplicate = target.with_name("hard.dat")
        os.link(target, duplicate)
        with self.assertRaises(SSH.SSHBoundaryError):
            self.ws.path("uploads", "hard.dat", existing=True)
        self.assertTrue(target.exists())
        if hasattr(os, "symlink"):
            folder = self.root / "work/ssh/downloads"
            try:
                (folder / "link").symlink_to(self.root, target_is_directory=True)
            except (OSError, NotImplementedError):
                return
            with self.assertRaises(SSH.SSHBoundaryError):
                self.ws.path("downloads", "link/escaped")

    def test_network_requires_explicit_authorization(self):
        with self.assertRaisesRegex(SSH.SSHBoundaryError, "task-authorized"):
            SSH.main(["probe", "--host", "example.test"], package_root=self.root)
        self.assertFalse((self.root / "work/ssh/known_hosts").exists())

    def test_host_observation_is_not_implicit_trust(self):
        with mock.patch.object(SSH, "_observed_key", return_value=FakeKey()):
            expected = SSH._fingerprint(FakeKey())
            with self.assertRaisesRegex(SSH.SSHBoundaryError, "differs"):
                SSH._trust(None, self.ws, "server.example", 22, 1, "SHA256:" + "A" * 43)
            self.assertFalse(self.ws.known_hosts().exists())

            class FakeHosts:
                def __init__(self):
                    self.loaded = False

                def load(self, path):
                    self.loaded = True

                def lookup(self, entry):
                    return {"ssh-ed25519": FakeKey()} if self.loaded else None

            pm = mock.Mock(HostKeys=FakeHosts)
            SSH._trust(pm, self.ws, "server.example", 2222, 1, expected)
            self.assertIn(
                "[server.example]:2222 ssh-ed25519 ",
                self.ws.known_hosts(existing=True).read_text(),
            )
            with self.assertRaises(SSH.SSHBoundaryError):
                SSH._trust(pm, self.ws, "server.example", 2222, 1, expected)

    def test_paramiko_connection_disables_agent_and_host_keys(self):
        self.ws.known_hosts().write_text(
            "server.example ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIE==\n"
        )
        self.ws.path("keys", "id_ed25519").write_bytes(b"synthetic")
        args = mock.Mock(host="server.example", port=22, user="dbuser",
                         key="id_ed25519", timeout=9, ask_passphrase=False)
        pm = FakeParamiko()
        client = SSH._connection(pm, self.ws, args)
        self.assertIs(client, pm.client)
        self.assertIsInstance(client.policy, FakeParamiko.RejectPolicy)
        self.assertEqual(client.options["allow_agent"], False)
        self.assertEqual(client.options["look_for_keys"], False)
        self.assertEqual(client.options["gss_kex"], False)
        self.assertEqual(client.options["timeout"], 9)
        # Assert the exact package-local paths on both Windows and POSIX.
        # Forward-slash suffix checks fail on native Windows despite a
        # correctly isolated host-key file and explicitly selected key.
        self.assertEqual(Path(client.loaded), self.ws.known_hosts(existing=True))
        self.assertEqual(
            Path(client.options["key_filename"]),
            self.ws.path("keys", "id_ed25519", existing=True),
        )

    def test_paramiko_implicit_certificate_and_private_key_paths_checked(self):
        self.ws.known_hosts().write_text("synthetic host keys")
        key = self.ws.path("keys", "id_ed25519")
        cert = self.ws.path("keys", "id_ed25519-cert.pub")
        key.write_bytes(b"synthetic private")
        args = mock.Mock(host="server.example", port=22, user="dbuser",
                         key=key.name, timeout=9, ask_passphrase=False)
        unrelated = self.root / "unrelated"
        unrelated.write_bytes(b"preserve")
        os.link(unrelated, cert)
        pm = FakeParamiko()
        with self.assertRaisesRegex(SSH.SSHBoundaryError, "single-link"):
            SSH._connection(pm, self.ws, args)
        self.assertIsNone(pm.client.options)
        cert.unlink()
        # Preserve the established Paramiko companion behavior for normal files.
        cert.write_bytes(b"synthetic certificate")
        self.assertIs(SSH._connection(pm, self.ws, args), pm.client)
        self.assertEqual(Path(pm.client.options["key_filename"]), key)
        args.key = cert.name
        self.assertIs(SSH._connection(pm, self.ws, args), pm.client)
        self.assertEqual(Path(pm.client.options["key_filename"]), cert)
        key.unlink()
        os.link(unrelated, key)
        pm = FakeParamiko()
        with self.assertRaisesRegex(SSH.SSHBoundaryError, "single-link"):
            SSH._connection(pm, self.ws, args)
        self.assertIsNone(pm.client.options)
        self.assertEqual(unrelated.read_bytes(), b"preserve")

    def test_exec_checks_deadline_during_continuous_output(self):
        for stderr in (False, True):
            with self.subTest(stderr=stderr):
                channel = mock.Mock()
                channel.recv_ready.side_effect = [not stderr] * 3 + [False]
                channel.recv_stderr_ready.side_effect = [stderr] * 3 + [False]
                channel.recv.return_value = b"x"
                channel.recv_stderr.return_value = b"x"
                channel.exit_status_ready.return_value = True
                client = mock.Mock()
                client.exec_command.return_value = (None, mock.Mock(channel=channel), None)
                # Deadline is 1.0. At the first read it has already passed,
                # although a finite burst is still queued and below the cap.
                with mock.patch.object(SSH.time, "monotonic", side_effect=[0.0, 0.5, 1.1]):
                    with self.assertRaisesRegex(SSH.SSHBoundaryError, "timed out"):
                        SSH._exec(client, "synthetic", 1)
                self.assertEqual(channel.recv.call_count + channel.recv_stderr.call_count, 1)
                channel.recv_exit_status.assert_not_called()
                channel.close.assert_called_once_with()

    def test_exec_preserves_successful_binary_output_and_exit_status(self):
        channel = mock.Mock()
        channel.recv_ready.side_effect = [True, False, False]
        channel.recv_stderr_ready.side_effect = [True, False, False]
        channel.recv.return_value = b"\x00\xffout"
        channel.recv_stderr.return_value = b"\xfeerr"
        channel.exit_status_ready.return_value = True
        channel.recv_exit_status.return_value = 7
        client = mock.Mock()
        client.exec_command.return_value = (None, mock.Mock(channel=channel), None)
        output, errors = io.BytesIO(), io.BytesIO()
        with mock.patch.object(SSH.sys, "stdout", mock.Mock(buffer=output)), \
                mock.patch.object(SSH.sys, "stderr", mock.Mock(buffer=errors)):
            self.assertEqual(SSH._exec(client, "synthetic", 5), 7)
        self.assertEqual(output.getvalue(), b"\x00\xffout")
        self.assertEqual(errors.getvalue(), b"\xfeerr")
        channel.close.assert_called_once_with()

    def test_sftp_download_no_clobber_and_upload_exclusive(self):
        client = FakeTransferClient()
        SSH._download(client, self.ws, "/var/log/demo.log", "demo.log", False)
        destination = self.ws.path("downloads", "demo.log", existing=True)
        self.assertEqual(destination.read_bytes(), b"synthetic downloaded content\n")
        with self.assertRaisesRegex(SSH.SSHBoundaryError, "exists"):
            SSH._download(client, self.ws, "/var/log/demo.log", "demo.log", False)
        self.assertEqual(destination.read_bytes(), b"synthetic downloaded content\n")
        SSH._download(client, self.ws, "/var/log/demo.log", "demo.log", True)
        source = self.ws.path("uploads", "file.dat")
        source.write_bytes(b"new synthetic data")
        SSH._upload(client, self.ws, "file.dat", "/tmp/demo.log", False)
        self.assertEqual(client.sftp.mode, "x+b")
        self.assertEqual(client.sftp.data.getvalue(), b"new synthetic data")

    def test_generated_key_remains_work_local_and_is_never_replaced(self):
        try:
            import cryptography  # noqa: F401
        except ImportError:
            self.skipTest("cryptography not yet installed in test environment")
        SSH._keygen(self.ws, "id_ed25519", unencrypted=True)
        private = self.ws.path("keys", "id_ed25519", existing=True)
        public = self.ws.path("keys", "id_ed25519.pub", existing=True)
        before = private.read_bytes()
        self.assertIn(b"OPENSSH PRIVATE KEY", before)
        self.assertTrue(public.read_bytes().startswith(b"ssh-ed25519 "))
        with self.assertRaisesRegex(SSH.SSHBoundaryError, "already exist"):
            SSH._keygen(self.ws, "id_ed25519", unencrypted=True)
        self.assertEqual(private.read_bytes(), before)

    def test_linked_ancestor_of_package_root_is_rejected(self):
        outer = self.root.parent / "alias"
        try:
            outer.symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable")
        with self.assertRaisesRegex(SSH.SSHBoundaryError, "ancestor"):
            SSH.Workspace(outer)

    def test_non_overwrite_upload_cleans_partial_on_write_failure(self):
        source = self.ws.path("uploads", "partial.dat")
        source.write_bytes(b"data")
        class FailingFile:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def write(self, _): raise IOError("synthetic network interruption")
            def flush(self): pass
        class FailingSFTP(FakeSFTP):
            def __init__(self):
                super().__init__()
                self.removed = False
            def open(self, remote, mode):
                assert mode == "x+b"
                return FailingFile()
            def remove(self, remote):
                self.removed = True
        sftp = FailingSFTP()
        client = mock.Mock(open_sftp=lambda: sftp)
        with self.assertRaisesRegex(OSError, "synthetic network interruption"):
            SSH._upload(client, self.ws, "partial.dat", "/tmp/demo.log", False)
        self.assertTrue(sftp.removed)

    def test_failed_upload_warns_when_remote_cleanup_is_denied(self):
        source = self.ws.path("uploads", "partial.dat")
        source.write_bytes(b"data")

        class FailingFile:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def write(self, _): raise OSError("synthetic upload interrupted")
            def flush(self): pass

        class DeniedCleanupSFTP(FakeSFTP):
            def __init__(self):
                super().__init__()
                self.removed = False

            def open(self, remote, mode):
                self.mode = mode
                return FailingFile()

            def remove(self, remote):
                self.removed = True
                raise PermissionError("synthetic cleanup refused")

        sftp = DeniedCleanupSFTP()
        client = mock.Mock(open_sftp=lambda: sftp)
        captured = io.StringIO()
        with mock.patch.object(SSH.sys, "stderr", captured):
            with self.assertRaisesRegex(OSError, "synthetic upload interrupted"):
                SSH._upload(client, self.ws, "partial.dat", "/tmp/demo.log", False)
        self.assertEqual(sftp.mode, "x+b")
        self.assertTrue(sftp.removed)
        self.assertIn("A partial remote file may remain", captured.getvalue())

    def test_failed_overwrite_warns_without_deleting_remote_target(self):
        source = self.ws.path("uploads", "overwrite.dat")
        source.write_bytes(b"data")

        class FailingFile:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def write(self, _): raise OSError("synthetic overwrite interrupted")
            def flush(self): pass

        class FailingOverwriteSFTP(FakeSFTP):
            def __init__(self):
                super().__init__()
                self.remove_called = False

            def open(self, remote, mode):
                self.mode = mode
                return FailingFile()

            def remove(self, remote):
                self.remove_called = True

        sftp = FailingOverwriteSFTP()
        client = mock.Mock(open_sftp=lambda: sftp)
        captured = io.StringIO()
        with mock.patch.object(SSH.sys, "stderr", captured):
            with self.assertRaisesRegex(OSError, "synthetic overwrite interrupted"):
                SSH._upload(client, self.ws, "overwrite.dat", "/tmp/demo.log", True)
        self.assertEqual(sftp.mode, "wb")
        self.assertFalse(sftp.remove_called)
        self.assertIn("Remote file contents may be incomplete", captured.getvalue())

    def test_private_key_is_private_at_creation(self):
        try:
            import cryptography  # noqa: F401
        except ImportError:
            self.skipTest("cryptography not installed")
        if os.name != "posix":
            self.skipTest("POSIX mode test")
        original_open = SSH.os.open
        calls = []
        def capture_open(path, flags, mode=0o777, *args, **kwargs):
            if Path(path).name == "mode-test":
                calls.append(mode)
            return original_open(path, flags, mode, *args, **kwargs)
        with mock.patch.object(SSH.os, "open", side_effect=capture_open):
            old_umask = os.umask(0)
            try:
                SSH._keygen(self.ws, "mode-test", unencrypted=True)
            finally:
                os.umask(old_umask)
        self.assertEqual(calls, [0o600])
        path = self.ws.path("keys", "mode-test", existing=True)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_reserved_and_disallowed_key_names(self):
        for name in ("../key", "NUL", "COM1.pem", "-bad", ".hidden", "bad/key"):
            with self.subTest(name=name):
                with self.assertRaises(SSH.SSHBoundaryError):
                    SSH._safe_name(name)

    def test_work_state_excluded_from_git_and_releases(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        packager = (ROOT / "tool/package-release.py").read_text(encoding="utf-8")
        self.assertIn("/work/", gitignore)
        self.assertIn('"work"', packager)


if __name__ == "__main__":
    unittest.main()
