"""Shared URL contract exercised through the real HTTP helper; transport is fake."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).absolute().parents[1]
SPEC = importlib.util.spec_from_file_location('login_url_helper', ROOT / 'login-json-http.py')
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)
VECTORS = json.loads((ROOT / 'tests/fixtures/login-url-contract.json').read_text(encoding='utf-8'))


class LoginUrlContractTests(unittest.TestCase):
    def request(self, url, method='GET', **extra):
        payload = {'url': url, 'method': method, 'timeout': 10, **extra}
        session = mock.MagicMock()
        session.__enter__.return_value = session
        response = session.request.return_value
        response.status_code = 200
        response.iter_content.return_value = [b'{"synthetic":true}']
        output = io.StringIO()
        with mock.patch.object(HELPER.requests, 'Session', return_value=session) as factory, \
                mock.patch.object(HELPER.sys, 'argv', ['login-json-http.py', '-']), \
                mock.patch.object(HELPER.sys, 'stdin', io.StringIO(json.dumps(payload))), \
                contextlib.redirect_stdout(output):
            code = HELPER.main()
        return code, json.loads(output.getvalue()), session, factory

    def test_exact_supported_urls_reach_only_the_fake_transport(self):
        for entry in VECTORS['allow']:
            with self.subTest(url=entry['url']):
                code, result, session, factory = self.request(**entry)
                self.assertEqual(code, 0, result)
                self.assertEqual(result['status_code'], 200)
                factory.assert_called_once()
                self.assertFalse(session.trust_env)
                session.request.assert_called_once()
                self.assertEqual(session.request.call_args.kwargs['url'], entry['url'])
                self.assertFalse(session.request.call_args.kwargs['allow_redirects'])

    def test_other_urls_and_queries_fail_before_transport_creation(self):
        for url in VECTORS['deny']:
            with self.subTest(url=url):
                code, result, session, factory = self.request(url)
                self.assertEqual(code, 1)
                self.assertEqual(result['status_code'], 0)
                factory.assert_not_called()
                session.request.assert_not_called()

    def test_version_query_does_not_relax_method_body_or_header_rules(self):
        url = 'https://chatgpt.com/backend-api/codex/models?client_version=0.164.0'
        for extra in ({'method': 'POST'}, {'body': {'synthetic': True}},
                      {'headers': {'Host': 'example.invalid'}},
                      {'headers': {'X-Synthetic': 'value\r\nInjected: value'}}):
            with self.subTest(extra=extra):
                code, result, session, factory = self.request(url, **extra)
                self.assertEqual(code, 1)
                factory.assert_not_called()
                session.request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
