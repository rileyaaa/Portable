import json
import base64
import sys
import re
import time
from urllib.parse import urlsplit

import requests
from urllib3.exceptions import MaxRetryError, NewConnectionError


MAX_REQUEST_CHARS = 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


def read_request(stream):
    text = stream.read(MAX_REQUEST_CHARS + 1)
    if len(text) > MAX_REQUEST_CHARS:
        raise ValueError("request exceeds the size limit")
    return json.loads(text)


def request_not_sent(error):
    # The bundled requests adapter has retries disabled. ConnectTimeout and
    # urllib3's NewConnectionError (including DNS failure) prove that no HTTP
    # request reached the endpoint. Generic ConnectionError, read timeouts,
    # TLS/response errors and supervisor failures do not prove this.
    if isinstance(error, requests.exceptions.ConnectTimeout):
        return True
    if isinstance(error, requests.exceptions.ConnectionError) and error.args:
        wrapped = error.args[0]
        return isinstance(wrapped, MaxRetryError) and isinstance(
            wrapped.reason, NewConnectionError
        )
    return False


def main() -> int:
    # The PowerShell caller sends credentials through stdin.  Keeping the old
    # filename mode would allow direct helper calls to read outside the package.
    if len(sys.argv) != 2 or sys.argv[1] != "-":
        print(json.dumps({"status_code": 0, "body": "", "error": "stdin marker '-' is required"}))
        return 2

    not_sent = False
    try:
        req = read_request(sys.stdin)
        if not isinstance(req, dict):
            raise ValueError("request payload must be a JSON object")

        method = str(req.get("method") or "GET").upper()
        url = str(req.get("url") or "")
        headers = req.get("headers") or {}
        body = req.get("body", None)
        timeout = max(1, min(int(req.get("timeout") or 45), 300))
        connect_timeout = max(1, min(int(req.get("connect_timeout") or 8), 30, timeout))
        proxy_url = str(req.get("proxy_url") or "")
        if any(ord(ch) <= 32 or ord(ch) == 127 for ch in url + proxy_url):
            raise ValueError("URL contains forbidden characters")
        if not url:
            raise ValueError("request URL is required")
        if not isinstance(headers, dict):
            raise ValueError("headers must be a JSON object")

        parsed = urlsplit(url)
        if (
            parsed.scheme.lower() != "https"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
            or "#" in url
        ):
            raise ValueError("request URL must be credential-free HTTPS on the default port without a fragment")
        host = (parsed.hostname or "").lower().rstrip(".")
        if host == "auth.openai.com" and parsed.path == "/oauth/token":
            expected_method = "POST"
        elif host == "chatgpt.com" and parsed.path in {"/backend-api/codex/models", "/backend-api/wham/usage"}:
            expected_method = "GET"
        else:
            raise ValueError("request URL is outside the fixed Codex login API allowlist")
        # Match the caller's exact endpoint contract. The models request alone
        # may carry one numeric release version; never accept arbitrary queries.
        raw_allowed = re.fullmatch(
            r"(?i:https://auth\.openai\.com\.?)(?::443)?/oauth/token"
            r"|(?i:https://chatgpt\.com\.?)(?::443)?/backend-api/wham/usage"
            r"|(?i:https://chatgpt\.com\.?)(?::443)?/backend-api/codex/models"
            r"(?:\?client_version=[0-9]+\.[0-9]+\.[0-9]+)?", url
        )
        if raw_allowed is None:
            raise ValueError("request URL or query is outside the fixed login contract")
        if method != expected_method:
            raise ValueError(f"{parsed.path} only permits {expected_method}")
        if expected_method == "GET" and body is not None:
            raise ValueError("GET login API requests must not carry a JSON body")

        forbidden_headers = {
            "host", "proxy-authorization", "proxy-connection", "connection",
            "content-length", "transfer-encoding", "te", "trailer", "upgrade",
        }
        clean_headers: dict[str, str] = {}
        for key, value in headers.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError("header names and values must be strings")
            if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", key) or key.lower() in forbidden_headers:
                raise ValueError("request header is invalid or controlled by the HTTP helper")
            if any(ord(ch) < 32 and ch != "\t" or ord(ch) == 127 for ch in value):
                raise ValueError("request headers may not contain CR/LF or ':' in a header name")
            clean_headers[key] = value

        if proxy_url:
            proxy = urlsplit(proxy_url)
            if (
                proxy.scheme.lower() not in {"http", "https", "socks5", "socks5h"}
                or not proxy.hostname
                or proxy.path not in {"", "/"}
                or proxy.query
                or proxy.fragment
            ):
                raise ValueError("proxy_url must be a simple http/https/socks5/socks5h proxy URL")
            if proxy.port is not None and not 1 <= proxy.port <= 65535:
                raise ValueError("proxy_url port is invalid")
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
        deadline = time.monotonic() + timeout
        with requests.Session() as session:
            session.trust_env = False
            try:
                response = session.request(
                    method=method,
                    url=url,
                    headers=clean_headers,
                    json=body if body is not None else None,
                    timeout=(connect_timeout, timeout),
                    proxies=proxies,
                    allow_redirects=False,
                    stream=True,
                )
            except requests.exceptions.RequestException as error:
                not_sent = request_not_sent(error)
                raise
            content = bytearray()
            with response:
                for chunk in response.iter_content(chunk_size=65536):
                    if time.monotonic() > deadline or len(content) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise ValueError("HTTP response exceeded its resource limit")
                    content.extend(chunk)
        print(json.dumps({
            "status_code": response.status_code,
            "body_b64": base64.b64encode(content).decode("ascii"),
            "error": "",
        }))
        return 0
    except Exception:
        print(json.dumps({
            "status_code": 0,
            "body_b64": "",
            "error": "HTTP request rejected or failed (details suppressed to protect credentials)",
            "request_not_sent": not_sent,
        }))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
