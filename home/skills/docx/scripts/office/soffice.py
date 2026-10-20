"""
Helper for running LibreOffice (soffice) in environments where AF_UNIX
sockets may be blocked (e.g., sandboxed VMs).  Detects the restriction
at runtime and applies an LD_PRELOAD shim if needed.

Usage:
    from office.soffice import run_soffice

    result = run_soffice(["--headless", "--convert-to", "pdf", "input.docx"])

Call soffice through run_soffice, not through subprocess with get_soffice_env():
the env dict carries the shim but names no user profile, and a non-root sandbox
cannot bootstrap the default one -- soffice aborts with "User installation could
not be completed" and converts nothing. get_soffice_env() stays public for the
callers that build their own argv (they must pass -env:UserInstallation too).
"""

import contextlib
import os
import platform
import socket
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path


def _is_reparse(path: Path, *, allow_missing: bool = False) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        return bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
    except FileNotFoundError:
        return not allow_missing
    except OSError:
        return True


def _portable_root() -> Path:
    # The script's location is authoritative even if an old package still
    # exists at an inherited CODEX_INSTALL_DIR.
    script = Path(__file__).absolute()
    expected = ("home", "skills", script.parent.parent.parent.name,
                "scripts", "office", "soffice.py")
    if len(script.parents) < 6 or expected[2] not in {"docx", "pptx", "xlsx"}:
        raise FileNotFoundError("LibreOffice helper is not in the bundled skill layout")
    root = script.parents[5]
    if script.relative_to(root).parts != expected:
        raise FileNotFoundError("LibreOffice helper is not in the bundled skill layout")
    for entry in (*reversed(script.parents), script):
        if _is_reparse(entry):
            raise FileNotFoundError(f"Portable helper path crosses a symlink/junction/reparse point: {entry}")
    for entry in (script, root / "codex.exe", root / "env.ps1"):
        if _is_reparse(entry) or not entry.is_file():
            raise FileNotFoundError(f"Portable helper requires a regular package file: {entry}")
        if getattr(entry.stat(follow_symlinks=False), "st_nlink", 1) != 1:
            raise FileNotFoundError(f"Portable helper requires a single-link package file: {entry}")
    return root


def _portable_tool(relative: str) -> Path:
    root = _portable_root()
    rel = Path(relative)
    if rel.anchor or ".." in rel.parts:
        raise FileNotFoundError(f"invalid package-local tool path: {relative}")
    raw = root / rel
    cursor = root
    for part in rel.parts:
        cursor = cursor / part
        if _is_reparse(cursor, allow_missing=True):
            raise FileNotFoundError(f"portable tool path contains a symlink/junction: {cursor}")
    candidate = raw.resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise FileNotFoundError(f"portable tool path escapes package: {relative}") from exc
    if not candidate.is_file():
        raise FileNotFoundError(f"package-local tool is missing: {candidate}")
    try:
        info = os.stat(candidate, follow_symlinks=False)
    except OSError as exc:
        raise FileNotFoundError(f"unable to inspect package-local tool safely: {candidate}") from exc
    if getattr(info, "st_nlink", 1) != 1:
        raise FileNotFoundError(f"package-local tool must be a single-link regular file: {candidate}")
    return candidate


def _portable_temp_dir() -> Path:
    root = _portable_root()
    target = root / "tmp" / "office"
    # Validate every existing component before creating anything.  Otherwise a
    # pre-existing root\tmp junction could redirect mkdir() outside the package.
    cursor = root
    for part in target.relative_to(root).parts:
        cursor = cursor / part
        if _is_reparse(cursor, allow_missing=True):
            raise FileNotFoundError(f"portable temp path contains a symlink/junction: {cursor}")
    target.mkdir(parents=True, exist_ok=True)
    if _is_reparse(target):
        raise FileNotFoundError(f"portable temp path may not be a symlink/junction: {target}")
    resolved = target.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise FileNotFoundError("portable office temp escapes package") from exc
    return resolved


def get_soffice_executable() -> str:
    return str(_portable_tool("tool/office/libreoffice/program/soffice.exe"))

def get_soffice_env() -> dict:
    # LibreOffice receives a minimal host environment plus package-local paths.
    # Unknown variables are intentionally not inherited.
    allowed_host = {
        "SystemRoot", "SYSTEMROOT", "WINDIR", "SystemDrive", "ComSpec", "PATHEXT", "OS",
        "PROCESSOR_ARCHITECTURE", "PROCESSOR_ARCHITEW6432", "PROCESSOR_IDENTIFIER",
        "NUMBER_OF_PROCESSORS", "COMPUTERNAME", "USERNAME", "USERDOMAIN",
        "LANG", "LC_ALL", "LC_CTYPE",
    }
    env = {name: value for name, value in os.environ.items() if name in allowed_host}
    root = _portable_root()
    portable_home = root / "home-runtime"
    portable_tmp = _portable_temp_dir()
    exact_scrub = {
        "OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_API_KEY", "ANTHROPIC_API_KEY", "AZURE_OPENAI_API_KEY",
        "GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS",
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN", "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID", "AZURE_FEDERATED_TOKEN_FILE",
        "GH_TOKEN", "GITHUB_TOKEN", "NPM_TOKEN", "NODE_AUTH_TOKEN", "PYPI_TOKEN", "TWINE_PASSWORD",
        "HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN", "CLOUDFLARE_API_TOKEN",
        "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "NODE_OPTIONS", "NODE_PATH", "NODE_EXTRA_CA_CERTS",
        "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS", "CLASSPATH",
        "GIT_SSH", "GIT_SSH_COMMAND", "GIT_ASKPASS", "SSH_ASKPASS", "SSH_AUTH_SOCK",
        "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_COUNT",
        "BASH_ENV", "ENV", "CDPATH", "RUBYOPT", "RUBYLIB", "PERL5OPT", "PERL5LIB",
        "LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH",
        "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    }
    for name in list(env):
        upper = name.upper()
        secret_like = any(marker in upper for marker in ("API_KEY", "ACCESS_TOKEN", "AUTH_TOKEN", "_SECRET", "_PASSWORD", "_CREDENTIAL"))
        git_injection = upper.startswith("GIT_CONFIG_KEY_") or upper.startswith("GIT_CONFIG_VALUE_")
        if upper in exact_scrub or secret_like or git_injection or upper.startswith("GIT_"):
            env.pop(name, None)
    env["HOME"] = str(portable_home)
    env["USERPROFILE"] = str(portable_home)
    env["TEMP"] = str(portable_tmp)
    env["TMP"] = str(portable_tmp)
    env["TMPDIR"] = str(portable_tmp)
    # Do not let a direct invocation rediscover arbitrary host executables.
    system_root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT")
    path_parts = [
        root / "tool" / "office" / "libreoffice" / "program",
        root / "tool" / "bin",
        root / "tool" / "python",
    ]
    if system_root:
        win = Path(system_root)
        path_parts.extend([win / "System32", win, win / "System32" / "Wbem"])
    env["PATH"] = os.pathsep.join(str(part) for part in path_parts)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["SAL_USE_VCLPLUGIN"] = "svp"

    if platform.system() == "Linux" and _needs_shim():
        shim = _ensure_shim()
        env["LD_PRELOAD"] = str(shim)

    return env


def run_soffice(args: Iterable[str], **kwargs) -> subprocess.CompletedProcess:
    args = list(args)
    with contextlib.ExitStack() as stack:
        if not any(str(a).startswith("-env:UserInstallation") for a in args):
            profile = stack.enter_context(
                tempfile.TemporaryDirectory(prefix="lo_profile_", dir=_portable_temp_dir(), ignore_cleanup_errors=True)
            )
            args = [f"-env:UserInstallation={Path(profile).as_uri()}"] + args
        return subprocess.run([get_soffice_executable()] + args, env=get_soffice_env(), **kwargs)



def _shim_paths() -> tuple[Path, Path]:
    base = _portable_temp_dir()
    return base / "lo_socket_shim.so", base / "lo_socket_shim.c"


def _needs_shim() -> bool:
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.close()
        return False
    except OSError:
        return True


def _ensure_shim() -> Path:
    shim_so, src = _shim_paths()
    if shim_so.exists():
        return shim_so

    # Linux-only compatibility path. Do not search an arbitrary host PATH for gcc.
    gcc = _portable_tool("tool/build/gcc/bin/gcc.exe") if platform.system() == "Windows" else None
    if platform.system() != "Windows":
        raise FileNotFoundError("AF_UNIX shim requires an explicitly packaged compiler; host gcc fallback is disabled")
    src.write_text(_SHIM_SOURCE, encoding="utf-8")
    subprocess.run(
        [str(gcc), "-shared", "-fPIC", "-o", str(shim_so), str(src), "-ldl"],
        check=True,
        capture_output=True,
        env=get_soffice_env(),
    )
    src.unlink(missing_ok=True)
    return shim_so



_SHIM_SOURCE = r"""
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <unistd.h>

static int (*real_socket)(int, int, int);
static int (*real_socketpair)(int, int, int, int[2]);
static int (*real_listen)(int, int);
static int (*real_accept)(int, struct sockaddr *, socklen_t *);
static int (*real_close)(int);
static int (*real_read)(int, void *, size_t);

/* Per-FD bookkeeping (FDs >= 1024 are passed through unshimmed). */
static int is_shimmed[1024];
static int peer_of[1024];
static int wake_r[1024];            /* accept() blocks reading this */
static int wake_w[1024];            /* close()  writes to this      */
static int listener_fd = -1;        /* FD that received listen()    */

__attribute__((constructor))
static void init(void) {
    real_socket     = dlsym(RTLD_NEXT, "socket");
    real_socketpair = dlsym(RTLD_NEXT, "socketpair");
    real_listen     = dlsym(RTLD_NEXT, "listen");
    real_accept     = dlsym(RTLD_NEXT, "accept");
    real_close      = dlsym(RTLD_NEXT, "close");
    real_read       = dlsym(RTLD_NEXT, "read");
    for (int i = 0; i < 1024; i++) {
        peer_of[i] = -1;
        wake_r[i]  = -1;
        wake_w[i]  = -1;
    }
}

/* ---- socket ---------------------------------------------------------- */
int socket(int domain, int type, int protocol) {
    if (domain == AF_UNIX) {
        int fd = real_socket(domain, type, protocol);
        if (fd >= 0) return fd;
        /* socket(AF_UNIX) blocked – fall back to socketpair(). */
        int sv[2];
        if (real_socketpair(domain, type, protocol, sv) == 0) {
            if (sv[0] >= 0 && sv[0] < 1024) {
                is_shimmed[sv[0]] = 1;
                peer_of[sv[0]]    = sv[1];
                int wp[2];
                if (pipe(wp) == 0) {
                    wake_r[sv[0]] = wp[0];
                    wake_w[sv[0]] = wp[1];
                }
            }
            return sv[0];
        }
        errno = EPERM;
        return -1;
    }
    return real_socket(domain, type, protocol);
}

/* ---- listen ---------------------------------------------------------- */
int listen(int sockfd, int backlog) {
    if (sockfd >= 0 && sockfd < 1024 && is_shimmed[sockfd]) {
        listener_fd = sockfd;
        return 0;
    }
    return real_listen(sockfd, backlog);
}

/* ---- accept ---------------------------------------------------------- */
int accept(int sockfd, struct sockaddr *addr, socklen_t *addrlen) {
    if (sockfd >= 0 && sockfd < 1024 && is_shimmed[sockfd]) {
        /* Block until close() writes to the wake pipe. */
        if (wake_r[sockfd] >= 0) {
            char buf;
            real_read(wake_r[sockfd], &buf, 1);
        }
        errno = ECONNABORTED;
        return -1;
    }
    return real_accept(sockfd, addr, addrlen);
}

/* ---- close ----------------------------------------------------------- */
int close(int fd) {
    if (fd >= 0 && fd < 1024 && is_shimmed[fd]) {
        int was_listener = (fd == listener_fd);
        is_shimmed[fd] = 0;

        if (wake_w[fd] >= 0) {              /* unblock accept() */
            char c = 0;
            write(wake_w[fd], &c, 1);
            real_close(wake_w[fd]);
            wake_w[fd] = -1;
        }
        if (wake_r[fd] >= 0) { real_close(wake_r[fd]); wake_r[fd]  = -1; }
        if (peer_of[fd] >= 0) { real_close(peer_of[fd]); peer_of[fd] = -1; }

        if (was_listener)
            _exit(0);                        /* conversion done – exit */
    }
    return real_close(fd);
}
"""



if __name__ == "__main__":
    raise SystemExit(
        "office.soffice is an internal portable helper; use the guarded document skill entrypoints instead"
    )
