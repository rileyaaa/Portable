"""Real loopback SOCKS5 negotiation with the pinned PySocks dependency.

No external DNS, proxy credentials or model requests. The synthetic server
verifies that the original destination and remote-DNS policy are unchanged.
"""
import argparse
import importlib.util
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "tool/socks-http-bridge.py"
try:
    import socks
except ImportError:
    socks = None


def load_bridge(baseline=None):
    if baseline:
        if not re.fullmatch(r"[a-f0-9]{40}", baseline):
            raise ValueError("invalid baseline commit")
        raw = subprocess.check_output(
            ["git", "-C", str(ROOT), "show", baseline + ":tool/socks-http-bridge.py"]
        )
        module = types.ModuleType("previous_bridge")
        exec(compile(raw, str(PATH), "exec"), module.__dict__)
        return module
    spec = importlib.util.spec_from_file_location("current_bridge", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def exact(sock, count):
    data = bytearray()
    while len(data) < count:
        part = sock.recv(count - len(data))
        if not part:
            raise EOFError("synthetic SOCKS peer closed")
        data.extend(part)
    return bytes(data)


def listener_for(family):
    listener = socket.socket(family, socket.SOCK_STREAM)
    try:
        listener.bind(("::1" if family == socket.AF_INET6 else "127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(3)
        return listener
    except BaseException:
        listener.close()
        raise


def handler_for(module, host, port):
    handler = object.__new__(module.ProxyHandler)
    handler.socks_host = module.validate_upstream_host(host)
    handler.socks_port = port
    handler.socks_rdns = True
    return handler


def negotiate(module, listener, host):
    errors = []
    observed = []

    def synthetic_proxy():
        try:
            with listener.accept()[0] as peer:
                peer.settimeout(3)
                assert exact(peer, 3) == b"\x05\x01\x00"
                peer.sendall(b"\x05\x00")
                assert exact(peer, 4) == b"\x05\x01\x00\x03"
                size = exact(peer, 1)[0]
                observed.append((exact(peer, size), exact(peer, 2)))
                peer.sendall(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00")
                assert exact(peer, 5) == b"probe"
                peer.sendall(b"reply")
        except BaseException as error:
            errors.append(error)

    worker = threading.Thread(target=synthetic_proxy, daemon=True)
    worker.start()
    old_timeout = module.IO_TIMEOUT
    module.IO_TIMEOUT = 3
    try:
        handler = handler_for(module, host, listener.getsockname()[1])
        with handler.connect_via_socks("synthetic.invalid", 443) as upstream:
            upstream.sendall(b"probe")
            assert exact(upstream, 5) == b"reply"
    finally:
        module.IO_TIMEOUT = old_timeout
        worker.join(4)
    assert not worker.is_alive(), "synthetic SOCKS worker did not exit"
    if errors:
        raise errors[0]
    assert observed == [(b"synthetic.invalid", b"\x01\xbb")]


@unittest.skipIf(socks is None, "PySocks is not installed")
class UpstreamLiteralTests(unittest.TestCase):
    def setUp(self):
        self.bridge = load_bridge()

    def loopback(self, family):
        try:
            return listener_for(family)
        except OSError:
            if family == socket.AF_INET6:
                self.skipTest("IPv6 loopback is unavailable on this host")
            raise

    def test_ipv4_negotiation_is_unchanged(self):
        with self.loopback(socket.AF_INET) as listener:
            negotiate(self.bridge, listener, "127.0.0.1")

    def test_ipv6_bare_and_bracketed_literals(self):
        for host in ("::1", "[::1]"):
            with self.subTest(host=host), self.loopback(socket.AF_INET6) as listener:
                negotiate(self.bridge, listener, host)

    def test_host_normalization_preserves_existing_dns_and_ipv4(self):
        for host in ("localhost", "synthetic.invalid", "127.0.0.1"):
            self.assertEqual(self.bridge.validate_upstream_host(host), host)
        self.assertEqual(self.bridge.validate_upstream_host("[::1]"), "::1")
        self.assertEqual(self.bridge.validate_upstream_host("::1"), "::1")
        for bad in ("[localhost]", "[127.0.0.1]", "[::1", "::invalid", "example:1080"):
            with self.subTest(host=bad), self.assertRaises(argparse.ArgumentTypeError):
                self.bridge.validate_upstream_host(bad)


def reproduce(baseline):
    if socks is None:
        raise RuntimeError("Pinned PySocks is required for baseline reproduction")
    old = load_bridge(baseline)
    old.IO_TIMEOUT = 1
    for host in ("::1", "[::1]"):
        with listener_for(socket.AF_INET6) as listener:
            handler = handler_for(old, host, listener.getsockname()[1])
            try:
                with handler.connect_via_socks("synthetic.invalid", 443):
                    raise AssertionError("previous IPv4-only socket unexpectedly connected")
            except OSError:
                pass
            listener.settimeout(0.2)
            try:
                peer, _ = listener.accept()
            except socket.timeout:
                pass
            else:
                peer.close()
                raise AssertionError("baseline reached upstream instead of failing before SOCKS negotiation")
    print("REPRODUCED old IPv4 socket cannot connect to configured bare/bracketed IPv6 SOCKS endpoint")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--baseline-commit":
        reproduce(sys.argv[2])
    elif sys.argv[1:] == ["--require-native"]:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(UpstreamLiteralTests)
        )
        if not result.wasSuccessful() or result.skipped:
            raise SystemExit(1)
    else:
        unittest.main()
