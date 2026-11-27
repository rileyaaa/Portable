"""Exercise urllib's actual routing to a local synthetic CONNECT endpoint."""
import base64
import contextlib
import http.server
import importlib.util
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error

ROOT = Path(__file__).absolute().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "browser_install", ROOT / "tool/automation/install-browser.py")
browser = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(browser)
URL = "https://storage.googleapis.com/chrome-for-testing-public/158.0.8127.88/win64/chrome-win64.zip"


class BrowserProxyRouteTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "tmp"
        scratch.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="browser-route-", dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.session = Path(temporary.name)
        self.manifest = {"archive": {"resolvedUrl": URL, "size": 16}}

    @contextlib.contextmanager
    def proxies(self, **values):
        # No inherited machine proxy; restore the environment after each case.
        env = {k: v for k, v in os.environ.items() if not k.lower().endswith("_proxy")}
        with mock.patch.dict(os.environ, {**env, **values}, clear=True):
            yield

    def download(self):
        return browser.download_archive(self.session, self.session, self.manifest)

    def test_direct_route_without_host_proxy_lookup_or_external_connection(self):
        with self.proxies(), \
                mock.patch("urllib.request.getproxies", side_effect=AssertionError("host proxy lookup")), \
                mock.patch("socket.create_connection", side_effect=OSError("synthetic stop before DNS")) as dial:
            with self.assertRaises(urllib.error.URLError):
                self.download()
        self.assertEqual(dial.call_count, 1)
        self.assertEqual(dial.call_args.args[0], ("storage.googleapis.com", 443))
        self.assertEqual(list(self.session.iterdir()), [])

    def test_configured_http_bridge_receives_connect_without_direct_fallback(self):
        requests = []

        class Bridge(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_CONNECT(self):
                requests.append((self.path, self.headers.get("Proxy-Authorization")))
                # Deliberately stop at the synthetic bridge. Never tunnel outward.
                self.send_error(502, "synthetic tunnel refusal")

        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Bridge) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            endpoint = server.server_address
            proxy = f"http://codex:synthetic@127.0.0.1:{endpoint[1]}"
            real_dial = socket.create_connection
            attempts = []

            def local_only(address, *args, **kwargs):
                attempts.append(address)
                if address != endpoint:
                    raise AssertionError("unexpected nonlocal connection")
                return real_dial(address, *args, **kwargs)

            try:
                with self.proxies(HTTP_PROXY=proxy, HTTPS_PROXY=proxy, ALL_PROXY=proxy,
                                  NO_PROXY="localhost,127.0.0.1"), \
                        mock.patch("socket.create_connection", side_effect=local_only):
                    with self.assertRaises(urllib.error.URLError):
                        self.download()
            finally:
                server.shutdown()
                thread.join(timeout=5)
        auth = "Basic " + base64.b64encode(b"codex:synthetic").decode("ascii")
        self.assertEqual(attempts, [endpoint])
        self.assertEqual(requests, [("storage.googleapis.com:443", auth)])
        self.assertEqual(list(self.session.iterdir()), [])

    def test_missing_or_unsupported_https_route_fails_before_opener(self):
        for env in (
            {"ALL_PROXY": "socks5h://127.0.0.1:10808"},
            {"all_proxy": "socks5h://127.0.0.1:10808"},
            {"ALL_PROXY": "http://127.0.0.1:10808"},
            {"ALL_PROXY": "socks5h://127.0.0.1:10808", "NO_PROXY": "*"},
            {"HTTP_PROXY": "http://127.0.0.1:10808"},
            {"HTTPS_PROXY": "socks5h://127.0.0.1:10808"},
        ):
            with self.subTest(env=env), self.proxies(**env), \
                    mock.patch("urllib.request.build_opener") as opener, \
                    mock.patch("socket.create_connection") as dial:
                with self.assertRaisesRegex(ValueError, "configured HTTP proxy/bridge"):
                    self.download()
                opener.assert_not_called()
                dial.assert_not_called()
                self.assertEqual(list(self.session.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
