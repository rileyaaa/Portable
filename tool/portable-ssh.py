#!/usr/bin/env python3
"""Task-authorized SSH/SFTP with all local state under work/ssh.

No user ~/.ssh, SSH agent, inherited credential, or auto-accepted host key.
This is a CLI entrypoint, not a sandbox for untrusted remote commands.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import sys
import tempfile
import time


class SSHBoundaryError(RuntimeError):
    pass


def _paramiko():
    try:
        import paramiko
    except ImportError as exc:
        raise SSHBoundaryError(
            "Paramiko is not installed in this Python runtime. "
            "Use the verified package-local Python dependency payload."
        ) from exc
    return paramiko


def _safe_host(host: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,253}", host):
        raise SSHBoundaryError("Invalid host; specify a DNS name or IPv4 address.")
    return host


def _safe_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", name):
        raise SSHBoundaryError("Key name must be a simple file name.")
    if name.upper().split(".")[0] in {
        "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4",
        "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2",
        "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    } or name.endswith("."):
        raise SSHBoundaryError("Windows reserved key name.")
    return name


def _relative_file(value: str) -> tuple[str, ...]:
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if not parts or any(
        not part or part in (".", "..") or part.endswith((" ", "."))
        or ":" in part or re.search(r'[<>"|?*\x00-\x1f]', part)
        for part in parts
    ):
        raise SSHBoundaryError("Local file must be a safe relative path under work/ssh.")
    for part in parts:
        if part.upper().split(".")[0] in {
            "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4",
            "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2",
            "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
        }:
            raise SSHBoundaryError("Windows reserved local file name.")
    return tuple(parts)


def _is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & 0x400
    )


class Workspace:
    """Never follow symlink/junction ancestors or hardlinked local files."""

    def __init__(self, package_root: Path):
        # Validate every ancestor, not just paths below the package root.
        # Using resolve() here would silently follow a symlink before checking.
        self.root = Path(os.path.abspath(os.fspath(package_root)))
        for ancestor in (*reversed(self.root.parents), self.root):
            info = ancestor.lstat()
            if _is_link(info) or not stat.S_ISDIR(info.st_mode):
                raise SSHBoundaryError("Linked or non-directory package ancestor: " + str(ancestor))
        self.base = self.root / "work" / "ssh"
        self._inspect(self.root, directory=True, required=True)

    def _inspect(self, path: Path, *, directory: bool = False,
                 required: bool = False) -> bool:
        try:
            relative = path.relative_to(self.root)
        except ValueError as exc:
            raise SSHBoundaryError("Path escapes portable package.") from exc
        current = self.root
        chain = [current]
        for part in relative.parts:
            current = current / part
            chain.append(current)
        for i, component in enumerate(chain):
            try:
                info = component.lstat()
            except FileNotFoundError:
                if required:
                    raise SSHBoundaryError("Missing package-local path: " + str(component))
                return False
            if _is_link(info):
                raise SSHBoundaryError("Linked/junction path is forbidden: " + str(component))
            final = i == len(chain) - 1
            if not final or directory:
                if not stat.S_ISDIR(info.st_mode):
                    raise SSHBoundaryError("Expected ordinary directory: " + str(component))
            elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise SSHBoundaryError("Expected single-link regular file: " + str(component))
        return True

    def directory(self, *pieces: str) -> Path:
        directory = self.base.joinpath(*pieces)
        relative = directory.relative_to(self.root)
        current = self.root
        for part in relative.parts:
            current = current / part
            if not self._inspect(current, directory=True):
                current.mkdir(mode=0o700)
                self._inspect(current, directory=True, required=True)
        return directory

    def path(self, group: str, relative: str, *, existing: bool = False) -> Path:
        if group not in {"keys", "uploads", "downloads"}:
            raise SSHBoundaryError("Unapproved workspace group.")
        pieces = _relative_file(relative)
        parent = self.directory(group, *pieces[:-1])
        target = parent / pieces[-1]
        self._inspect(target, required=existing)
        return target

    def known_hosts(self, *, existing: bool = False) -> Path:
        self.directory()
        target = self.base / "known_hosts"
        self._inspect(target, required=existing)
        return target


def _fingerprint(key) -> str:
    return "SHA256:" + base64.b64encode(
        hashlib.sha256(key.asbytes()).digest()
    ).decode("ascii").rstrip("=")


def _host_entry(host: str, port: int) -> str:
    return host if port == 22 else f"[{host}]:{port}"


def _observed_key(pm, host: str, port: int, timeout: float):
    with socket.create_connection((host, port), timeout=timeout) as sock:
        transport = pm.Transport(sock)
        try:
            transport.start_client(timeout=timeout)
            key = transport.get_remote_server_key()
            if key is None:
                raise SSHBoundaryError("SSH peer did not present a host key.")
            return key
        finally:
            transport.close()


def _keygen(ws: Workspace, name: str, unencrypted: bool) -> int:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    name = _safe_name(name)
    private_path = ws.path("keys", name)
    public_path = ws.path("keys", name + ".pub")
    if private_path.exists() or public_path.exists():
        raise SSHBoundaryError("Key files already exist; refusing to replace them.")
    if unencrypted:
        cipher = serialization.NoEncryption()
    else:
        first = getpass.getpass("New SSH key passphrase: ")
        second = getpass.getpass("Confirm passphrase: ")
        if not first or not hmac.compare_digest(first, second):
            raise SSHBoundaryError("Nonempty passphrases did not match.")
        cipher = serialization.BestAvailableEncryption(first.encode("utf-8"))
    key = ed25519.Ed25519PrivateKey.generate()
    private = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=cipher,
    )
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    )
    # Exclusive creation: never remove an unrelated preexisting key on failure.
    created_private = False
    created_public = False
    try:
        # POSIX mode must be private at creation, not only after chmod.
        # On Windows the security ACL is inherited from the local folder.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(private_path, flags, 0o600)
        created_private = True
        with os.fdopen(fd, "wb") as handle:
            handle.write(private)
            handle.flush()
            os.fsync(handle.fileno())
        with public_path.open("xb") as handle:
            created_public = True
            handle.write(public + b"\n")
    except BaseException:
        if created_public:
            ws._inspect(public_path, required=True)
            public_path.unlink()
        if created_private:
            ws._inspect(private_path, required=True)
            private_path.unlink()
        raise
    print("SSH key created under work/ssh/keys; public key:", public_path)
    if unencrypted:
        print("WARNING: unencrypted private key; protect the package directory.")
    return 0


def _probe(pm, host: str, port: int, timeout: float) -> int:
    key = _observed_key(pm, host, port, timeout)
    print(f"{_host_entry(host, port)} {key.get_name()} {_fingerprint(key)}")
    print("Unverified observation: confirm the fingerprint out of band before trust.")
    return 0


def _trust(pm, ws: Workspace, host: str, port: int,
           timeout: float, expected: str) -> int:
    if not re.fullmatch(r"SHA256:[A-Za-z0-9+/]{43}", expected):
        raise SSHBoundaryError("Expected exact SHA256:... host-key fingerprint.")
    key = _observed_key(pm, host, port, timeout)
    found = _fingerprint(key)
    if not hmac.compare_digest(found, expected):
        raise SSHBoundaryError("Host fingerprint differs from independently verified value.")
    path = ws.known_hosts()
    hosts = pm.HostKeys()
    if path.exists():
        hosts.load(str(path))
    entry = _host_entry(host, port)
    if hosts.lookup(entry):
        raise SSHBoundaryError(
            "Host already has a pinned key; manual review required before rotation."
        )
    # No AutoAddPolicy; create the first known_hosts with restrictive mode.
    flags = os.O_WRONLY | (os.O_APPEND if path.exists() else os.O_CREAT | os.O_EXCL)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "a", encoding="ascii", newline="\n") as handle:
        handle.write(f"{entry} {key.get_name()} {key.get_base64()}\n")
    os.chmod(path, 0o600)
    print("Pinned host key in package-local work/ssh/known_hosts:", entry)
    return 0


def _connection(pm, ws: Workspace, args):
    host_keys = ws.known_hosts(existing=True)
    key = ws.path("keys", _safe_name(args.key), existing=True)
    # Paramiko 5.1.0 derives and opens both paths in _key_from_filepath,
    # even with allow_agent=False and look_for_keys=False. Check the same
    # companion before constructing the client (and before any connection).
    suffix = "-cert.pub"
    if key.name.endswith(suffix):
        ws.path("keys", _safe_name(key.name[:-len(suffix)]), existing=True)
    else:
        ws._inspect(key.with_name(key.name + suffix))
    client = pm.SSHClient()
    try:
        client.load_host_keys(str(host_keys))
        client.set_missing_host_key_policy(pm.RejectPolicy())
        passphrase = getpass.getpass("Private-key passphrase: ") if args.ask_passphrase else None
        client.connect(
            hostname=args.host, port=args.port, username=args.user,
            key_filename=str(key), passphrase=passphrase,
            allow_agent=False, look_for_keys=False,
            timeout=args.timeout, auth_timeout=args.timeout,
            banner_timeout=args.timeout,
        )
        return client
    except BaseException:
        client.close()
        raise


def _exec(client, command: str, timeout: float) -> int:
    if not command or "\x00" in command:
        raise SSHBoundaryError("An explicit remote command is required.")
    _, stdout, _ = client.exec_command(command, timeout=timeout)
    channel = stdout.channel
    deadline = time.monotonic() + timeout
    out, err = bytearray(), bytearray()
    def check_deadline():
        if time.monotonic() > deadline:
            raise SSHBoundaryError("Remote command timed out.")

    try:
        while True:
            check_deadline()
            while channel.recv_ready():
                out.extend(channel.recv(65536))
                if len(out) > 2_000_000:
                    raise SSHBoundaryError("Remote stdout exceeded the bounded limit.")
                check_deadline()
            while channel.recv_stderr_ready():
                err.extend(channel.recv_stderr(65536))
                if len(err) > 2_000_000:
                    raise SSHBoundaryError("Remote stderr exceeded the bounded limit.")
                check_deadline()
            if channel.exit_status_ready() and not (
                channel.recv_ready() or channel.recv_stderr_ready()
            ):
                break
            time.sleep(0.03)
        status = channel.recv_exit_status()
        sys.stdout.buffer.write(out)
        sys.stderr.buffer.write(err)
        return status
    finally:
        channel.close()


def _download(client, ws: Workspace, remote: str, relative: str,
              overwrite: bool) -> int:
    if not remote or "\x00" in remote or "\n" in remote:
        raise SSHBoundaryError("Invalid remote file path.")
    target = ws.path("downloads", relative)
    if target.exists() and not overwrite:
        raise SSHBoundaryError("Download exists; --overwrite required.")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".ssh-download-", dir=target.parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            os.chmod(temp_path, 0o600)
            with client.open_sftp() as sftp:
                sftp.getfo(remote, handle)
            handle.flush()
            os.fsync(handle.fileno())
        ws._inspect(temp_path, required=True)
        ws._inspect(target)
        if overwrite:
            os.replace(temp_path, target)
        else:
            # Atomic no-clobber placement; both paths are on the same volume.
            os.link(temp_path, target)
        print("Downloaded to package-local", target)
        return 0
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def _upload(client, ws: Workspace, relative: str, remote: str,
            overwrite: bool) -> int:
    if not remote or "\x00" in remote or "\n" in remote:
        raise SSHBoundaryError("Invalid remote file path.")
    source = ws.path("uploads", relative, existing=True)
    with source.open("rb") as source_file:
        with client.open_sftp() as sftp:
            created_here = False
            try:
                # SFTP v3 exclusive-create requires the read/write flag for
                # Paramiko's SFTPFile to be writable on real servers.
                # An explicit overwrite is not transactional: if interrupted,
                # the user must verify the destination before retrying.
                with sftp.open(remote, "wb" if overwrite else "x+b") as destination:
                    created_here = not overwrite
                    shutil.copyfileobj(source_file, destination, length=1024 * 1024)
                    destination.flush()
            except BaseException:
                # Never hide the original failure, but do not silently conceal
                # an incomplete remote target when cleanup is refused.
                if created_here:
                    try:
                        sftp.remove(remote)
                    except Exception:
                        print(
                            "WARNING: SFTP upload failed and cleanup of the newly "
                            "created remote file also failed. A partial remote file "
                            "may remain; inspect the destination before retrying.",
                            file=sys.stderr,
                        )
                elif overwrite:
                    # An explicitly overwritten remote file is not recoverable
                    # automatically. Report this even when the transfer failed.
                    print(
                        "WARNING: SFTP overwrite failed. Remote file contents may "
                        "be incomplete; inspect the destination before retrying.",
                        file=sys.stderr,
                    )
                raise
    print("Uploaded from package-local", source)
    return 0


def _arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    keygen = commands.add_parser("keygen", help="Create package-local Ed25519 key.")
    keygen.add_argument("--name", default="id_ed25519")
    keygen.add_argument("--unencrypted", action="store_true",
                        help="Opt in to unencrypted private key.")
    for verb in ("probe", "trust", "exec", "get", "put"):
        command = commands.add_parser(verb)
        command.add_argument("--task-authorized", action="store_true",
                             help="Explicit authorization for this host/task.")
        command.add_argument("--host", required=True)
        command.add_argument("--port", type=int, default=22)
        command.add_argument("--timeout", type=float, default=30)
        if verb == "trust":
            command.add_argument("--fingerprint", required=True,
                                 help="Host SHA256 fingerprint verified out of band.")
        if verb in ("exec", "get", "put"):
            command.add_argument("--user", required=True)
            command.add_argument("--key", default="id_ed25519")
            command.add_argument("--ask-passphrase", action="store_true")
        if verb == "exec":
            command.add_argument("--command", required=True)
        if verb in ("get", "put"):
            command.add_argument("--remote", required=True)
            command.add_argument("--local", required=True,
                                 help="Relative to work/ssh/downloads or uploads.")
            command.add_argument("--overwrite", action="store_true")
    return parser


def main(argv=None, *, package_root=None) -> int:
    args = _arguments().parse_args(argv)
    ws = Workspace(package_root or Path(__file__).absolute().parent.parent)
    if args.action == "keygen":
        return _keygen(ws, args.name, args.unencrypted)
    if not args.task_authorized:
        raise SSHBoundaryError("Explicit --task-authorized is required for network operations.")
    args.host = _safe_host(args.host)
    if not 1 <= args.port <= 65535 or not 0 < args.timeout <= 1800:
        raise SSHBoundaryError("Invalid port or timeout.")
    pm = _paramiko()
    if args.action == "probe":
        return _probe(pm, args.host, args.port, args.timeout)
    if args.action == "trust":
        return _trust(pm, ws, args.host, args.port, args.timeout,
                      args.fingerprint)
    client = _connection(pm, ws, args)
    try:
        if args.action == "exec":
            return _exec(client, args.command, args.timeout)
        if args.action == "get":
            return _download(client, ws, args.remote, args.local, args.overwrite)
        return _upload(client, ws, args.local, args.remote, args.overwrite)
    finally:
        client.close()


if __name__ == "__main__":
    # Embedded Python ignores PYTHONIOENCODING. Preserve interactive output.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and not stream.isatty() and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    try:
        raise SystemExit(main())
    except (SSHBoundaryError, OSError, ValueError) as exc:
        print("Portable SSH: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
