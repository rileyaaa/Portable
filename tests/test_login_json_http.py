"""Offline regression checks for the login HTTP helper's timeout contract."""

import contextlib
import importlib.util
import io
import json
import pathlib
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "login_json_http", ROOT / "login-json-http.py"
)
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)


class LoginHttpTimeoutTests(unittest.TestCase):
    def test_file_arguments_are_rejected_before_file_or_network_access(self):
        for path in ("request.json", "../request.json", r"Z:\synthetic outside\request.json"):
            with self.subTest(path=path):
                output = io.StringIO()
                with (
                    mock.patch.object(HELPER.sys, "argv", ["login-json-http.py", path]),
                    mock.patch("builtins.open") as open_file,
                    mock.patch.object(HELPER.requests, "Session") as session,
                    contextlib.redirect_stdout(output),
                ):
                    result = HELPER.main()
                self.assertEqual(result, 2)
                self.assertEqual(json.loads(output.getvalue())["status_code"], 0)
                open_file.assert_not_called()
                session.assert_not_called()

    def run_request(self, **overrides):
        payload = {
            "method": "GET",
            "url": "https://chatgpt.com/backend-api/codex/models",
            "timeout": 60,
            **overrides,
        }
        session = mock.MagicMock()
        session.__enter__.return_value = session
        response = session.request.return_value
        response.status_code = 200
        response.iter_content.return_value = [b'{"models":[]}']
        output = io.StringIO()
        with (
            mock.patch.object(HELPER.requests, "Session", return_value=session),
            mock.patch.object(HELPER.sys, "argv", ["login-json-http.py", "-"]),
            mock.patch.object(HELPER.sys, "stdin", io.StringIO(json.dumps(payload))),
            contextlib.redirect_stdout(output),
        ):
            result = HELPER.main()
        self.assertEqual(result, 0, output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["status_code"], 200)
        self.assertFalse(session.trust_env)
        return session.request.call_args.kwargs

    def failure_result(self, error, during_body=False):
        session = mock.MagicMock()
        session.__enter__.return_value = session
        if during_body:
            response = session.request.return_value
            response.status_code = 200
            response.iter_content.side_effect = error
        else:
            session.request.side_effect = error
        payload = {
            "method": "POST", "url": "https://auth.openai.com/oauth/token",
            "body": {"grant_type": "refresh_token", "refresh_token": "synthetic"},
        }
        output = io.StringIO()
        with (
            mock.patch.object(HELPER.requests, "Session", return_value=session),
            mock.patch.object(HELPER.sys, "argv", ["login-json-http.py", "-"]),
            mock.patch.object(HELPER.sys, "stdin", io.StringIO(json.dumps(payload))),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(HELPER.main(), 1)
        session.request.assert_called_once()
        result = json.loads(output.getvalue())
        self.assertEqual(result["status_code"], 0)
        self.assertNotIn("sensitive-marker", output.getvalue())
        return result

    def test_preconnection_failure_is_distinguished_from_uncertain_delivery(self):
        exc = HELPER.requests.exceptions
        new_connection = HELPER.NewConnectionError(None, "sensitive-marker")
        wrapped = HELPER.MaxRetryError(None, "/synthetic", new_connection)
        for error in (exc.ConnectTimeout("sensitive-marker"), exc.ConnectionError(wrapped)):
            with self.subTest(error=type(error).__name__):
                self.assertIs(self.failure_result(error)["request_not_sent"], True)
        for error in (exc.ReadTimeout("sensitive-marker"),
                      exc.ConnectionError("sensitive-marker"),
                      exc.SSLError("sensitive-marker"),
                      exc.ChunkedEncodingError("sensitive-marker")):
            with self.subTest(error=type(error).__name__):
                self.assertIs(self.failure_result(error)["request_not_sent"], False)

    def test_body_failure_does_not_claim_request_was_unsent(self):
        exc = HELPER.requests.exceptions
        result = self.failure_result(exc.ConnectTimeout("sensitive-marker"), during_body=True)
        self.assertIs(result["request_not_sent"], False)

    def test_explicit_connect_timeout_reaches_requests(self):
        request = self.run_request(connect_timeout=2)
        self.assertEqual(request["timeout"], (2, 60))

    def test_omitted_connect_timeout_uses_eight_seconds(self):
        request = self.run_request()
        self.assertEqual(request["timeout"], (8, 60))

    def test_connect_timeout_is_bounded_by_thirty_seconds(self):
        request = self.run_request(connect_timeout=90)
        self.assertEqual(request["timeout"], (30, 60))

    def test_connect_timeout_cannot_exceed_overall_request_limit(self):
        request = self.run_request(connect_timeout=20, timeout=5)
        self.assertEqual(request["timeout"], (5, 5))


if __name__ == "__main__":
    unittest.main()
