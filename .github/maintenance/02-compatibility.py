#!/usr/bin/env python3
"""02: offline, fail-closed variable and compatibility audit.

Checks project CODEX_* defaults against launcher consumers, exact runtime
identity, fixed text/Agent scope, model schema and native CLI responses.
Does not test real credentials, paid requests, devices or terminal redraw.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

REQUIRED = {
    "codex.exe", "codex-code-mode-host.exe", "codex-command-runner.exe",
    "codex-windows-sandbox-setup.exe", "codex-path/rg.exe", "codex-package.json"
}
NORMAL = {
    "CODEX_PORTABLE_PROFILE": "strict",
    "CODEX_APPROVAL_POLICY": "on-request",
    "CODEX_SANDBOX_MODE": "workspace-write",
    "CODEX_SANDBOX_NETWORK_ACCESS": "false",
    "CODEX_AUTH_MODE": "menu",
    "CODEX_FAST_MODE": "false",
    "CODEX_DISABLE_WEBSOCKET": "true",
    "CODEX_DISABLE_APPS": "true",
    "CODEX_ENABLE_PLUGINS": "false",
    "CODEX_ENABLE_PLUGIN_SHARING": "false",
    "CODEX_PORTABLE_ALLOW_USER_MCP": "false",
    "CODEX_PROXY_ENABLED": "false",
    "CODEX_TUI_FULLSCREEN_TRANSCRIPT": "false",
    "CODEX_WIRE_API": "responses",
}
YOLO = {
    "CODEX_APPROVAL_POLICY": ("on-request", "never"),
    "CODEX_SANDBOX_MODE": ("workspace-write", "danger-full-access"),
    "CODEX_SANDBOX_NETWORK_ACCESS": ("false", "true"),
}


def check(ok: bool, explanation: str) -> None:
    if not ok:
        raise RuntimeError(explanation)


def regular(path: Path) -> None:
    item = path.lstat()
    check(stat.S_ISREG(item.st_mode) and item.st_nlink == 1 and
          not (getattr(item, "st_file_attributes", 0) & 0x400),
          "Unsafe linked/non-file input: " + str(path))


def binary(root: Path, name: str) -> bytes:
    path = root / name
    regular(path)
    return path.read_bytes()


def txt(root: Path, name: str) -> str:
    path = root / name
    regular(path)
    return path.read_text(encoding="utf-8-sig")


def sha256(path: Path) -> str:
    obj = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1048576), b""):
            obj.update(part)
    return obj.hexdigest()


def pin(source: str, variable: str) -> str:
    hits = re.findall(r'\$' + variable + r'\s*=\s*"([a-fA-F0-9]{64})"', source)
    check(len(hits) == 1, "Missing unique launcher pin: " + variable)
    return hits[0].lower()


def source_check(root: Path) -> dict:
    manifest = json.loads(txt(root, "tool/runtime-manifest.json"))
    version = manifest.get("version")
    check(isinstance(version, str) and
          re.fullmatch(r"\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?", version) is not None,
          "Invalid pinned version")
    check(manifest.get("target") == "x86_64-pc-windows-msvc",
          "Runtime architecture changed")
    files = manifest.get("files")
    check(isinstance(files, dict) and set(files) == REQUIRED,
          "Exactly six local text/Agent runtime components required")
    excluded = manifest.get("excluded_components", {})
    check({"voice", "duplicate_sandbox_resources", "standalone_exec_server"} <= set(excluded),
          "Exclusion record incomplete")
    check(excluded["standalone_exec_server"].get("upstream_path") ==
          "bin/codex-exec-server.exe", "Standalone server omission policy changed")
    check(not (root / "codex-exec-server.exe").exists() and
          not (root / "codex-voice-host.exe").exists() and
          not (root / "codex-resources/voice").exists() and
          (root / "codex-resources").is_dir(),
          "Voice or standalone server returned, or resources folder missing")
    for name, record in files.items():
        regular(root / name)
        check(sha256(root / name) == record["sha256"],
              "Verified runtime SHA-256 mismatch: " + name)
    meta = json.loads(txt(root, "codex-package.json"))
    check(meta.get("version") == version and
          meta.get("target") == "x86_64-pc-windows-msvc" and
          meta.get("entrypoint") == "codex.exe" and
          meta.get("resourcesDir") == "codex-resources" and
          meta.get("pathDir") == "codex-path" and
          "execServer" not in meta, "Portable package metadata is not local-only")
    launcher, env, login = (
        txt(root, "run-codex.ps1"), txt(root, "env.ps1"),
        txt(root, "login-json.ps1"))
    check(re.findall(r'\$ExpectedCodexVersion\s*=\s*"([^"]+)"', launcher) == [version],
          "Launcher version mismatch")
    check(pin(launcher, "ExpectedRuntimeManifestSha256") ==
          sha256(root / "tool/runtime-manifest.json"),
          "Launcher manifest pin mismatch")
    for file, var in [
        ("codex.exe", "ExpectedCodexSha256"),
        ("codex-code-mode-host.exe", "ExpectedCodeModeHostSha256"),
    ]:
        check(pin(launcher, var) == files[file]["sha256"],
              "Launcher native binary pin mismatch: " + file)
    check(re.search(r"'" + files["codex.exe"]["sha256"] +
                    r"'\s*=\s*'" + re.escape(version) + r"'", login) is not None,
          "Login client version/hash mapping missing")
    run_bytes = binary(root, "run-codex.ps1")
    for name in ("Version_History/常用模式专用包-run-codex.ps1",
                 "Version_History/YOLO mode专用包-run-codex.ps1"):
        check(binary(root, name) == run_bytes, "Launcher mode copy drift: " + name)
    original_env = binary(root, "env.ps1")
    check(binary(root, "Version_History/常用模式专用包-env.ps1") == original_env,
          "Common env preset drift")
    yolo = original_env
    for var, (before, after) in YOLO.items():
        old = ('$env:' + var + ' = "' + before + '"').encode("ascii")
        new = ('$env:' + var + ' = "' + after + '"').encode("ascii")
        check(yolo.count(old) == 1, "Missing exact normal-policy delta for " + var)
        yolo = yolo.replace(old, new, 1)
    check(yolo == binary(root, "Version_History/YOLO mode专用包-env.ps1"),
          "Unexpected YOLO preset changes beyond the three allowed values")
    # Scan every environment assignment, including computed package-local paths.
    assigned = re.findall(r'^\$env:(CODEX_[A-Z0-9_]+)\s*=', env, re.M)
    check(len(assigned) >= 45 and len(assigned) == len(set(assigned)),
          "Missing or duplicate managed environment variable assignments")
    defaults = dict(re.findall(
        r'^\$env:(CODEX_[A-Z0-9_]+)\s*=\s*"([^"\r\n]*)"', env, re.M))
    expected_dynamic = {
        "CODEX_INSTALL_DIR": r'^\$env:CODEX_INSTALL_DIR\s*=\s*\$Script:CodexPortableRoot\s*$',
        "CODEX_PYTHON": r'^\$env:CODEX_PYTHON\s*=\s*Join-Path\s+\$Script:CodexPortableRoot\s+"tool\\python\\python.exe"\s*$',
    }
    dynamic = set(assigned) - set(defaults)
    check(dynamic == set(expected_dynamic),
          "New computed variables require explicit review: " + repr(sorted(dynamic)))
    for name, pattern in expected_dynamic.items():
        check(re.search(pattern, env, re.M) is not None,
              "Computed package-local path changed: " + name)
    for name, expected in NORMAL.items():
        check(defaults.get(name) == expected, "Changed protected default: " + name)
    orphans = [name for name in assigned if
               "$env:" + name not in launcher and "$env:" + name not in login]
    check(not orphans, "Unconsumed managed CODEX_* variables: " + repr(orphans))
    check('$env:CODEX_HOME = Join-Path $Root "home"' in launcher and
          "return @('--no-daemon') + @($LaunchArgs)" in launcher,
          "Shared-daemon exclusion or package-local state changed")
    check('[void]$Builder.AppendLine("fullscreen_transcript = $TuiFullscreenTranscript")'
          in launcher, "Fullscreen preference is no longer generated")
    check("Add-Member -NotePropertyName use_responses_lite -NotePropertyValue $false"
          in launcher and "supports_websockets" in launcher and "wire_api" in launcher,
          "Custom Responses API compatibility mapping changed")
    # The official codex.exe retains some built-in server/remote commands.
    # Verify the wrapper still denies those commands, and voice remains off.
    disallowed = re.search(
        r'if \(\$rootCommand -in @\(([^)]*)\)\)\s*\{\s*Stop-UnsafeCodexCliArgument',
        launcher, re.S)
    check(disallowed is not None, "Portable CLI command denylist is missing")
    blocked = set(re.findall(r"'([^']+)'", disallowed.group(1)))
    check({"exec-server", "remote-control", "app-server", "mcp-server",
           "tcp-tunnel"} <= blocked,
          "Native server/remote commands are no longer blocked by the launcher")
    check("严格便携入口不透传远程控制覆盖参数。" in launcher and
          "--remote-auth-token-env" in launcher,
          "Remote-control override flags are no longer blocked")
    for setting in ("in_app_voice = false", "in_app_dictation = false",
                    "toggle_voice = []", "toggle_voice_mute = []"):
        check('[void]$Builder.AppendLine("' + setting + '")' in launcher,
              "Voice/dictation features or hotkeys were re-enabled: " + setting)

    allowlist = env.split("$supportedCodex =", 1)
    check(len(allowlist) == 2 and
          "'CODEX_TUI_FULLSCREEN_TRANSCRIPT'" in allowlist[1],
          "Fullscreen preference is not in the local override allowlist")
    attributes = txt(root, ".gitattributes")
    for name in REQUIRED - {"codex-package.json"}:
        check(name + " filter=lfs diff=lfs merge=lfs -text" in attributes,
              "Native binary not Git LFS-tracked: " + name)
    # Only the reviewed, fail-closed one-time release workflow may return.
    # The retired automatic upgrade and tool-update workflows stay removed.
    workflow_dir = root / ".github/workflows"
    if workflow_dir.exists():
        check(workflow_dir.is_dir() and not workflow_dir.is_symlink() and
              {item.name for item in workflow_dir.iterdir()} == {"release.yml", "import-round12.yml"} and
              (workflow_dir / "release.yml").is_file(),
              "Unexpected GitHub Actions workflows on main")

    # Static checks for the existing tool/browser environment contract. The
    # native functional tests remain separate, and optional SDK/JDK must not
    # be mistaken for bundled tools merely because a path variable is set.
    tool_setup = txt(root, "tool/setup-tools.ps1")
    automation = txt(root, "tool/automation/portable-automation.ps1")
    versions = json.loads(txt(root, "tool/automation/versions.json"))
    browser = versions.get("browser", {})
    check(versions.get("platform") == "win32-x64" and
          isinstance(versions.get("playwrightMcp"), str) and
          isinstance(versions.get("playwright"), str) and
          browser.get("engine") == "chromium" and
          browser.get("payloadBundled") is True and
          browser.get("chromedriverRequired") is False and
          browser.get("payloadManifest") == "browser-manifest.json",
          "Pinned Playwright MCP/browser inventory changed")
    check(isinstance(browser.get("executable"), str) and
          browser["executable"].startswith("browsers/") and
          ".." not in browser["executable"].split("/"),
          "Unsafe Chromium executable path in pinned inventory")
    for name in ("PLAYWRIGHT_BROWSERS_PATH", "PLAYWRIGHT_SKIP_BROWSER_GC",
                 "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"):
        check("$start.EnvironmentVariables['" + name + "']" in automation,
              "Missing browser child variable: " + name)
    check("$proxyEnabled" in automation and "if ($proxyEnabled)" in automation,
          "Explicit browser/desktop proxy gate is missing")
    for name in ("PIP_CONFIG_FILE", "PSModulePath", "PATH"):
        check("$env:" + name in tool_setup,
              "Missing portable setup environment control: " + name)
    for name in ("ANDROID_HOME", "ANDROID_SDK_ROOT", "JAVA_HOME"):
        check("$env:" + name in env and "$env:" + name in launcher,
              "Missing optional Android SDK/JDK environment control: " + name)
    regular(root / "tool/python/python.exe")
    regular(root / "tool/node/node.exe")
    regular(root / "tool/automation/browser-manifest.json")
    regular(root / "tool/automation" / browser["executable"])
    print("02_TOOL_BROWSER_ENVIRONMENT_STATIC_REFERENCES=PASS "
          "mcp=" + versions["playwrightMcp"] + " browser=" + browser["version"])
    check("当前主客户端与 Code Mode Host 均为官方 **" + version + "**" in
          txt(root, "README.md"), "README current runtime version is stale")
    check("已配套安装 " + version + " Windows x64" in
          txt(root, "tool/工具更新说明.md"), "Tool runtime version is stale")
    print("02_LOCAL_ONLY_RUNTIME_IDENTITY=PASS")
    print("02_VERSION_LAUNCHER_LOGIN_AND_MODE_COPIES=PASS")
    print("02_MANAGED_VARIABLES=PASS count=" + str(len(assigned)) +
          " computed=" + str(len(dynamic)))
    print("02_OFFLINE_PROTOCOL_AND_DEFAULT_POLICY_REFERENCES=PASS")
    print("02_MANUAL_RELEASE_NO_ACTIONS=PASS")
    return {"version": version, "variables": sorted(assigned)}


def run_exe(cli: Path, argv: list[str], env: dict) -> str:
    run = subprocess.run([str(cli), *argv], env=env, cwd=cli.parent,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
    output = run.stdout.decode("utf-8-sig", errors="replace").strip()
    stderr = run.stderr.decode("utf-8-sig", errors="replace")
    check(run.returncode == 0,
          "Native CLI command " + repr(argv) + " failed: " + stderr[:700])
    return output


def native_check(root: Path, info: dict) -> None:
    check(os.name == "nt", "Native audit requires Windows x64")
    tmp = root / "tmp"
    # 01 invokes 02 before committing; clean Git checkouts need not track tmp.
    made_tmp = False
    if not tmp.exists():
        tmp.mkdir(mode=0o700)
        made_tmp = True
    try:
        item = tmp.lstat()
        check(stat.S_ISDIR(item.st_mode) and
              not (getattr(item, "st_file_attributes", 0) & 0x400),
              "Unsafe package-local temporary directory")
        with tempfile.TemporaryDirectory(prefix="compat-", dir=tmp) as directory:
            base = Path(directory)
            env = os.environ.copy()
            # Native offline diagnostics must not inherit runner credentials,
            # arbitrary CODEX_* overrides, machine proxy or logged-in account.
            for key in tuple(env):
                normalized = key.upper()
                if normalized.startswith((
                        "CODEX_", "OPENAI_", "AZURE_OPENAI_", "AWS_", "GH_TOKEN",
                        "GITHUB_TOKEN", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                        "NO_PROXY", "GIT_ASKPASS", "GIT_CONFIG_")):
                    env.pop(key, None)
            for name in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
                         "TEMP", "TMP", "TMPDIR", "CODEX_HOME",
                         "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
                path = base / name.lower()
                path.mkdir()
                env[name] = str(path)
            env["PIP_CONFIG_FILE"] = "nul"
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            cli = root / "codex.exe"
            check(run_exe(cli, ["--version"], env) == "codex-cli " + info["version"],
                  "Real binary version differs from pinned manifest")
            catalog = json.loads(run_exe(cli, ["debug", "models", "--bundled"], env))
            models = catalog.get("models")
            check(isinstance(models, list) and bool(models),
                  "Bundled model metadata shape changed; review launcher adapter")
            slugs = [m.get("slug") for m in models]
            check(all(isinstance(slug, str) and slug for slug in slugs) and
                  len(set(slugs)) == len(slugs),
                  "Bundled model identifiers invalid or duplicated")
            # Exercise the *new* native configuration parser with real fields,
            # never a user's real config or credentials.
            config = (
                'approval_policy = "on-request"\n'
                'sandbox_mode = "workspace-write"\n'
                'service_tier = "default"\n'
                '[features]\n'
                'in_app_voice = false\n'
                'in_app_dictation = false\n'
                '[tui]\n'
                'fullscreen_transcript = false\n'
            )
            (Path(env["CODEX_HOME"]) / "config.toml").write_text(
                config, encoding="utf-8")
            check(bool(run_exe(cli, ["features", "list"], env)),
                  "New native CLI rejected the offline portable config probe")
            for args, required in (
                (["--help"], "--no-daemon"),
                (["resume", "--help"], "--last"),
                (["fork", "--help"], "--last"),
            ):
                check(required in run_exe(cli, args, env),
                      "Native CLI entrypoint changed: " + repr(args))
    finally:
        if made_tmp:
            tmp.rmdir()
    print("02_NATIVE_VERSION_MODEL_SCHEMA_FEATURES_AND_CLI_FLAGS=PASS")
    print("02_REAL_ACCOUNT_ONLINE_AGENT_TUI=NOT_TESTED")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--native", action="store_true")
    args = p.parse_args()
    root = args.repo.resolve(strict=True)
    check((root / ".git").exists(), "Expected a full repository checkout")
    info = source_check(root)
    if args.native:
        native_check(root, info)
    print("COMPATIBILITY_AUDIT=PASS version=" + info["version"])
    print("Offline/static checks do not prove real provider/terminal operation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
