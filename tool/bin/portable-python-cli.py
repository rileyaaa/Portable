#!/usr/bin/env python3
"""Relocatable console_script entrypoint for the bundled Windows Python.

The owning CMD validates the package, executable, helper and working directory.
This helper rebuilds the child's environment before importing any third-party
console_script; it does not sandbox arbitrary code or the Python startup itself.
"""
from __future__ import annotations

import importlib.metadata
import os
import re
import runpy
import stat
import sys


def _inherited(inherited: dict[str, str], name: str) -> str:
    for key, value in inherited.items():
        if key.upper() == name.upper() and isinstance(value, str):
            return value
    return ""


def portable_cli_environment(
    inherited: dict[str, str], package_root: str | os.PathLike[str] | None = None
) -> dict[str, str]:
    """Rebuild a minimal portable environment for all 19 CLI console shims."""
    if package_root is None:
        package_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    root = os.path.abspath(os.fspath(package_root))
    join = lambda *parts: os.path.join(root, *parts)
    env: dict[str, str] = {}
    for name in (
        "PATHEXT", "OS", "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER",
        "NUMBER_OF_PROCESSORS", "USERNAME", "USERDOMAIN", "COMPUTERNAME",
        "CI", "TERM", "COLORTERM", "NO_COLOR", "FORCE_COLOR",
        "LANG", "LC_ALL", "LC_CTYPE", "TZ",
    ):
        value = _inherited(inherited, name)
        if value:
            env[name] = value

    values = {
        "HOME": join("home-runtime"), "USERPROFILE": join("home-runtime"),
        "APPDATA": join("appdata"), "LOCALAPPDATA": join("localappdata"),
        "PROGRAMDATA": join("programdata"), "ALLUSERSPROFILE": join("programdata"),
        "PUBLIC": join("home-runtime"),
        "TEMP": join("tmp"), "TMP": join("tmp"), "TMPDIR": join("tmp"),
        "XDG_CONFIG_HOME": join("appdata"), "XDG_DATA_HOME": join("localappdata"),
        "XDG_STATE_HOME": join("localappdata", "state"),
        "XDG_CACHE_HOME": join("cache", "xdg"),
        "PIP_CONFIG_FILE": os.devnull, "PIP_NO_CACHE_DIR": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
        "PYTHONUSERBASE": join("cache", "python-userbase"),
        "PYTHONPYCACHEPREFIX": join("cache", "pycache"),
        "NPM_CONFIG_CACHE": join("cache", "npm"),
        "NPM_CONFIG_PREFIX": join("cache", "npm-prefix"),
        "NPM_CONFIG_GLOBALCONFIG": join("cache", "npm", "global.npmrc"),
        "NPM_CONFIG_USERCONFIG": join("home-runtime", ".npmrc"),
        "NODE_REPL_HISTORY": join("home-runtime", ".node_repl_history"),
        "YARN_CACHE_FOLDER": join("cache", "yarn"),
        "PNPM_HOME": join("cache", "pnpm"),
        "PNPM_STORE_DIR": join("cache", "pnpm-store"),
        "GRADLE_USER_HOME": join("cache", "gradle"),
        "MAVEN_OPTS": '-Dmaven.repo.local="' + join("cache", "maven") + '"',
        "ANDROID_HOME": join("tool", "android", "sdk"),
        "ANDROID_SDK_ROOT": join("tool", "android", "sdk"),
        "ANDROID_USER_HOME": join("home-runtime", ".android"),
        "ANDROID_SDK_HOME": join("home-runtime"),
        "ADB_VENDOR_KEYS": join("home-runtime", ".android", "adbkey"),
        "JAVA_HOME": join("tool", "android", "jdk"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "POWERSHELL_TELEMETRY_OPTOUT": "1",
        "PSModuleAnalysisCachePath": "NUL" if os.name == "nt" else os.devnull,
    }
    env.update(values)

    # A direct CLI must not inherit host credentials/proxy. Preserve only a
    # proxy that the relocated package launcher explicitly chose for local
    # commands. These anchors prevent accidental leakage, not env spoofing.
    def same_path(candidate: str, expected: str) -> bool:
        return bool(candidate) and os.path.normcase(os.path.abspath(candidate)) == os.path.normcase(expected)

    def enabled(name: str) -> bool:
        return _inherited(inherited, name).strip().lower() in {"1", "true", "yes", "on"}

    approved_proxy = (
        same_path(_inherited(inherited, "CODEX_INSTALL_DIR"), root)
        and same_path(_inherited(inherited, "CODEX_HOME"), join("home"))
        and enabled("CODEX_PROXY_ENABLED")
        and enabled("CODEX_PROXY_FOR_SUBPROCESS")
        and enabled("CODEX_SANDBOX_NETWORK_ACCESS")
    )
    if approved_proxy:
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
                     "http_proxy", "https_proxy", "all_proxy", "no_proxy"):
            value = _inherited(inherited, name)
            if value:
                env[name] = value

    if os.name == "nt":
        # GetWindowsDirectoryW reads the real OS location, not the caller's
        # potentially poisoned SystemRoot/ComSpec/PATH environment variables.
        import ctypes

        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer))
        if not 0 < length < len(buffer):
            raise RuntimeError("Cannot determine the real Windows directory")
        windows = os.path.normpath(buffer.value)
        drive, _ = os.path.splitdrive(windows)
        if not re.match(r"^[A-Za-z]:$", drive) or ":" in windows[2:]:
            raise RuntimeError("Only an ordinary local Windows system root is supported")
        env["SystemRoot"] = windows
        env["WINDIR"] = windows
        env["SystemDrive"] = drive
        env["ComSpec"] = os.path.join(windows, "System32", "cmd.exe")
        env["PATHEXT"] = ".COM;.EXE;.BAT;.CMD"
        env["HOMEDRIVE"], env["HOMEPATH"] = os.path.splitdrive(env["HOME"])
        dirs = [
            join("tool", "bin"), join("tool", "python"),
            join("tool", "node"), join("tool", "android", "platform-tools"),
            os.path.join(windows, "System32"), windows,
            os.path.join(windows, "System32", "WindowsPowerShell", "v1.0"),
            os.path.join(windows, "System32", "Wbem"),
        ]
        env["PATH"] = os.pathsep.join(dirs)
        env["PSModulePath"] = os.pathsep.join((
            join("cache", "powershell", "modules"),
            os.path.join(windows, "System32", "WindowsPowerShell", "v1.0", "Modules"),
        ))
    else:
        # Synthetic POSIX tests only; the shipped package targets Windows x64.
        env["PATH"] = os.pathsep.join((
            join("tool", "bin"), join("tool", "python"),
            join("tool", "node"), "/usr/bin", "/bin",
        ))
    return env


def pip_environment(inherited: dict[str, str]) -> dict[str, str]:
    """Compatibility helper: pip uses the same strict environment as other CLIs."""
    return portable_cli_environment(inherited)



def _run_legacy_vba_extract(package_root: str | os.PathLike[str],
                            arguments: list[str]) -> int:
    """Run XlsxWriter's non-console_script entry after environment scrubbing.

    This is a single exact bundled filename. No caller-provided script path,
    PYTHONPATH, environment-selected entrypoint or host fallback is allowed.
    """
    root = os.path.abspath(os.fspath(package_root))
    script = os.path.join(root, "tool", "python", "Lib",
                          "site-packages", "bin", "vba_extract.py")
    ancestors: list[str] = []
    cursor = script
    while cursor:
        ancestors.append(cursor)
        parent = os.path.dirname(cursor)
        if parent == cursor:
            break
        cursor = parent
    for candidate in reversed(ancestors):
        info = os.lstat(candidate)
        if (stat.S_ISLNK(info.st_mode) or
                getattr(info, "st_file_attributes", 0) & 0x400):
            raise RuntimeError("Portable VBA entry must not contain links or reparse points")
        if candidate == script:
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise RuntimeError("Portable VBA entry requires one ordinary script file")
        elif not stat.S_ISDIR(info.st_mode):
            raise RuntimeError("Portable VBA entry must have ordinary directory ancestors")
    # Match the original 'python.exe vba_extract.py <args>' argv contract.
    sys.argv = [script, *arguments]
    runpy.run_path(script, run_name="__main__")
    return 0


def _canonical_name(name: str) -> str:
    lower = name.lower()
    if re.fullmatch(r"pip\d+(?:\.\d+)?", lower):
        return "pip"
    return lower


def _find_entry_point(name: str):
    wanted = _canonical_name(name)
    eps = importlib.metadata.entry_points()
    if hasattr(eps, "select"):
        candidates = eps.select(group="console_scripts")
    else:  # pragma: no cover - compatibility with older Python only
        candidates = eps.get("console_scripts", ())
    matches = [ep for ep in candidates if ep.name.lower() == wanted]
    if len(matches) != 1:
        raise SystemExit(f"portable-python-cli: expected exactly one console_script for {wanted!r}, found {len(matches)}")
    return matches[0]


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: portable-python-cli.py <console-script-name> [args...]", file=sys.stderr)
        return 2
    requested = sys.argv[1]
    # Sanitize before importlib.metadata resolves and loads third-party script
    # entrypoints; CMD and Python -E -s -B cover interpreter bootstrap separately.
    clean = portable_cli_environment(dict(os.environ))
    os.environ.clear()
    os.environ.update(clean)
    if requested == "vba_extract":
        package_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
        return _run_legacy_vba_extract(package_root, sys.argv[2:])
    ep = _find_entry_point(requested)
    sys.argv = [requested, *sys.argv[2:]]
    result = ep.load()()
    return int(result) if isinstance(result, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
