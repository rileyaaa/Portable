import contextlib
import os
import posixpath
import re
import shutil
import stat
import tempfile
import urllib.parse
import unicodedata
import uuid
import zipfile
from pathlib import Path

OOXML_FAMILY = {
    ".docx": "docx",
    ".dotx": "docx",
    ".pptx": "pptx",
    ".potx": "pptx",
    ".xlsx": "xlsx",
    ".xltx": "xlsx",
}

_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")

SLIDE_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"


def _is_reparse(path: Path, *, allow_missing: bool = False) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        attrs = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(attrs & 0x400)
    except FileNotFoundError:
        return not allow_missing
    except OSError:
        return True


def _reject_hardlinked_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    try:
        info = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise RuntimeError(f"Unable to inspect file link count safely: {path}") from exc
    if getattr(info, "st_nlink", 1) != 1:
        raise RuntimeError(f"Hard-linked files are not allowed at this portable boundary: {path}")


def portable_root() -> Path:
    # Bind to this copy of the helper.  An inherited CODEX_INSTALL_DIR can still
    # name a different, valid package after a move or copy.
    script = Path(__file__).absolute()
    expected = ("home", "skills", script.parent.parent.parent.parent.name,
                "scripts", "office", "helpers", "__init__.py")
    if len(script.parents) < 7 or expected[2] not in {"docx", "pptx", "xlsx"}:
        raise RuntimeError("Office helper is not in the bundled skill layout")
    root = script.parents[6]
    if script.relative_to(root).parts != expected:
        raise RuntimeError("Office helper is not in the bundled skill layout")
    # Check ancestors before inspecting markers: a redirected package path
    # must not make us inspect or create files in its target.
    for entry in (*reversed(script.parents), script):
        if _is_reparse(entry):
            raise RuntimeError(f"Portable helper path crosses a symlink/junction/reparse point: {entry}")
    for entry in (script, root / "codex.exe", root / "env.ps1"):
        if _is_reparse(entry) or not entry.is_file():
            raise RuntimeError(f"Portable helper requires a regular package file: {entry}")
        _reject_hardlinked_file(entry)
    return root



def resolve_portable_path(value: str | os.PathLike[str], *, must_exist: bool = False, kind: str | None = None) -> Path:
    """Resolve a caller-supplied path inside the portable package without crossing reparse points."""
    root = portable_root()
    raw = Path(value).expanduser()
    candidate = raw if raw.is_absolute() else (Path.cwd() / raw)
    candidate = candidate.absolute()
    if ".." in candidate.parts:
        raise RuntimeError(f"Parent traversal is not allowed at the portable boundary: {value}")
    try:
        rel = candidate.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(
            f"Path is outside Codex Portable; copy it into the package after explicit approval: {value}"
        ) from exc

    cursor = root
    for part in rel.parts:
        cursor = cursor / part
        if _is_reparse(cursor, allow_missing=True):
            raise RuntimeError(f"Path crosses a symbolic link/junction/reparse point: {cursor}")

    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"Path escapes Codex Portable after resolution: {value}") from exc

    if must_exist and not resolved.exists():
        raise FileNotFoundError(resolved)
    if kind == "file" and resolved.exists() and not resolved.is_file():
        raise RuntimeError(f"Expected a file: {resolved}")
    if kind == "dir" and resolved.exists() and not resolved.is_dir():
        raise RuntimeError(f"Expected a directory: {resolved}")
    _reject_hardlinked_file(resolved)
    return resolved


def ensure_portable_tree_no_reparse(value: str | os.PathLike[str], *, max_entries: int = 100_000) -> Path:
    """Reject reparse points without recursively traversing through an unchecked entry."""
    tree = resolve_portable_path(value, must_exist=True, kind="dir")
    count = 0
    stack = [tree]
    while stack:
        directory = stack.pop()
        if _is_reparse(directory):
            raise RuntimeError(f"Editable tree contains a symbolic link/junction/reparse point: {directory}")
        with os.scandir(directory) as entries:
            for entry in entries:
                count += 1
                if count > max_entries:
                    raise RuntimeError(f"Refusing oversized editable tree (> {max_entries} entries): {tree}")
                item = Path(entry.path)
                if entry.is_symlink() or _is_reparse(item):
                    raise RuntimeError(f"Editable tree contains a symbolic link/junction/reparse point: {item}")
                if entry.is_file(follow_symlinks=False):
                    _reject_hardlinked_file(item)
                if entry.is_dir(follow_symlinks=False):
                    stack.append(item)
    return tree

def portable_file(relative: str) -> Path:
    root = portable_root()
    rel = Path(relative)
    if rel.anchor or ".." in rel.parts:
        raise RuntimeError(f"invalid package-local tool path: {relative}")
    candidate = root / rel
    cursor = root
    for part in rel.parts:
        cursor = cursor / part
        if _is_reparse(cursor, allow_missing=True):
            raise RuntimeError(f"package-local tool path contains a reparse point: {cursor}")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"package-local tool path escapes package: {relative}") from exc
    if not resolved.is_file():
        raise FileNotFoundError(f"package-local tool is missing: {resolved}")
    _reject_hardlinked_file(resolved)
    return resolved


def portable_temp_dir(category: str = "office") -> Path:
    root = portable_root()
    rel = Path(category)
    if rel.anchor or ".." in rel.parts:
        raise RuntimeError(f"invalid package-local temporary category: {category}")
    target = root / "tmp" / rel
    cursor = root
    for part in target.relative_to(root).parts:
        cursor = cursor / part
        if _is_reparse(cursor, allow_missing=True):
            raise RuntimeError(f"portable temp path contains a reparse point: {cursor}")
    target.mkdir(parents=True, exist_ok=True)
    resolved = target.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("portable temp path escapes package") from exc
    return resolved



@contextlib.contextmanager
def portable_temporary_directory(prefix: str = "office-", *, ignore_cleanup_errors: bool = False):
    """Own one temporary child under the existing package-local office scratch.

    CPython 3.13+ mkdir(0700) on Windows creates a protected DACL, which
    tempfile.TemporaryDirectory uses. A restricted Codex token can be denied
    access despite the parent being writable. Inherit the parent's existing
    Windows ACL instead; retain 0700 on POSIX. No ACL is modified and this
    directory layout does not guarantee confidentiality from other users.
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]+", prefix):
        raise ValueError("Invalid portable Office scratch prefix")
    parent = resolve_portable_path(portable_temp_dir(), must_exist=True, kind="dir")
    child = resolve_portable_path(parent / (prefix + uuid.uuid4().hex), kind="dir")
    child.mkdir(mode=0o777 if os.name == "nt" else 0o700)
    identity = child.lstat()
    try:
        resolve_portable_path(child, must_exist=True, kind="dir")
        # Preserve the string interface of tempfile.TemporaryDirectory.
        yield str(child)
    finally:
        resolve_portable_path(child, kind="dir")
        try:
            current = child.lstat()
        except FileNotFoundError:
            current = None
        if current is not None:
            if (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
                raise RuntimeError("Office scratch directory identity changed; refusing cleanup")
            shutil.rmtree(child, ignore_errors=ignore_cleanup_errors)


def portable_subprocess_env() -> dict[str, str]:
    """Build a package-local environment for non-LibreOffice helper subprocesses."""
    root = portable_root()
    # Start from an explicit allow-list instead of inheriting the host process
    # wholesale.  This prevents unknown credentials/injection knobs from leaking
    # into helper subprocesses while retaining the minimum Windows runtime context.
    allowed_host = {
        "SystemRoot", "SYSTEMROOT", "WINDIR", "SystemDrive", "ComSpec", "PATHEXT", "OS",
        "PROCESSOR_ARCHITECTURE", "PROCESSOR_ARCHITEW6432", "PROCESSOR_IDENTIFIER",
        "NUMBER_OF_PROCESSORS", "COMPUTERNAME", "USERNAME", "USERDOMAIN",
        "LANG", "LC_ALL", "LC_CTYPE",
    }
    env = {name: value for name, value in os.environ.items() if name in allowed_host}
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
    state_paths = {
        "HOME": "home-runtime", "USERPROFILE": "home-runtime",
        "APPDATA": "appdata", "LOCALAPPDATA": "localappdata",
        "PROGRAMDATA": "programdata", "ALLUSERSPROFILE": "programdata",
        "PUBLIC": "public", "XDG_CACHE_HOME": "home-runtime/.cache",
        "XDG_CONFIG_HOME": "home-runtime/.config",
        "XDG_DATA_HOME": "home-runtime/.local/share",
        "XDG_STATE_HOME": "home-runtime/.local/state",
    }
    # Direct helper calls cannot rely on the launcher checking these paths.
    env.update({key: str(resolve_portable_path(root / relative, kind="dir"))
                for key, relative in state_paths.items()})
    tmp = portable_temp_dir("office")
    env["TEMP"] = str(tmp)
    env["TMP"] = str(tmp)
    env["TMPDIR"] = str(tmp)
    path_parts = [
        root / "tool" / "git" / "cmd", root / "tool" / "git" / "bin", root / "tool" / "git" / "usr" / "bin",
        root / "tool" / "office" / "libreoffice" / "program", root / "tool" / "pdf" / "poppler" / "Library" / "bin",
        root / "tool" / "pdf" / "poppler" / "bin", root / "tool" / "bin", root / "tool" / "python",
    ]
    system_root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT")
    if system_root:
        win = Path(system_root)
        path_parts.extend([win / "System32", win, win / "System32" / "Wbem"])
    env["PATH"] = os.pathsep.join(str(part) for part in path_parts)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    return env

def opc_target(target: str, source_part: str, target_mode: str = "") -> str | None:
    if not target:
        return None
    if target_mode.lower() == "external":
        return None
    if _SCHEME_RE.match(target):
        return None

    target = urllib.parse.unquote(target)

    if "\\" in target:
        raise ValueError(f"relationship target is not a POSIX part name: {target!r}")

    if target.startswith("/"):
        joined = target.lstrip("/")
    else:
        joined = posixpath.join(posixpath.dirname(source_part), target)

    parts: list[str] = []
    for segment in posixpath.normpath(joined).split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if not parts:
                raise ValueError(f"relationship target escapes the package: {target!r}")
            parts.pop()
        else:
            parts.append(segment)

    if not parts:
        raise ValueError(f"relationship target resolves to nothing: {target!r}")
    return "/".join(parts)


def rels_source_part(rels_file: Path, unpacked_dir: Path) -> str:
    owner_dir = rels_file.parent.parent.relative_to(unpacked_dir)
    return posixpath.join(owner_dir.as_posix(), rels_file.name[: -len(".rels")]).lstrip("./")


def part_text(data: bytes) -> str:
    return data.decode("utf-8", "surrogateescape")


XML_SPACE = " \t\r\n"


def rendered_text(text: str, preserve: bool) -> str:
    return text if preserve else text.strip(XML_SPACE)


_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", "CLOCK$", "CONIN$", "CONOUT$", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_MAX_ARCHIVE_ENTRIES = 20_000
_MAX_ARCHIVE_ENTRY_BYTES = 128 * 1024 * 1024
_MAX_ARCHIVE_TOTAL_BYTES = 512 * 1024 * 1024
_MAX_ARCHIVE_NAME_CHARS = 4096
_MAX_COMPRESSION_RATIO = 250


def _validate_archive_name(name: str) -> list[str]:
    if len(name) > _MAX_ARCHIVE_NAME_CHARS:
        raise ValueError("archive entry name is too long")
    if not name or "\\" in name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise ValueError(f"unsafe archive entry: {name!r}")
    parts = name.split("/")
    clean: list[str] = []
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError(f"unsafe archive entry: {name!r}")
        if ":" in part or any(ord(ch) < 32 for ch in part):
            raise ValueError(f"Windows-unsafe archive entry: {name!r}")
        if part.endswith((".", " ")):
            raise ValueError(f"Windows-unsafe archive entry: {name!r}")
        stem = part.split(".", 1)[0].upper()
        if stem in _WINDOWS_RESERVED:
            raise ValueError(f"Windows-reserved archive entry: {name!r}")
        clean.append(part)
    if not clean:
        raise ValueError(f"archive entry resolves to nothing: {name!r}")
    return clean


def _reject_reparse_chain(path: Path) -> None:
    """Reject symlink/junction/reparse components in an archive source or destination path."""
    current = path.absolute()
    chain: list[Path] = []
    while True:
        chain.append(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    for item in reversed(chain):
        # Probe the entry itself, not its target, including dangling links.
        if _is_reparse(item, allow_missing=True):
            raise ValueError(f"archive path crosses a symbolic link/junction/reparse point: {item}")


def safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    dest = dest.absolute()
    _reject_reparse_chain(dest)
    dest = dest.resolve()
    infos = zf.infolist()
    if len(infos) > _MAX_ARCHIVE_ENTRIES:
        raise ValueError(f"archive has too many entries: {len(infos)}")
    total = 0
    seen_windows_paths: set[str] = set()
    for m in infos:
        if stat.S_ISLNK(m.external_attr >> 16):
            raise ValueError(f"symlink archive entry not allowed: {m.filename!r}")
        parts = _validate_archive_name(m.filename)
        windows_key = "/".join(unicodedata.normalize("NFC", part).casefold() for part in parts)
        if windows_key in seen_windows_paths:
            raise ValueError(f"case-insensitive/Unicode-normalized archive path collision: {m.filename!r}")
        seen_windows_paths.add(windows_key)
        if m.file_size > _MAX_ARCHIVE_ENTRY_BYTES:
            raise ValueError(f"archive entry too large: {m.filename!r}")
        if m.file_size > 16 * 1024 * 1024 and m.compress_size > 0 and m.file_size > m.compress_size * _MAX_COMPRESSION_RATIO:
            raise ValueError(f"archive entry compression ratio is unsafe: {m.filename!r}")
        total += m.file_size
        if total > _MAX_ARCHIVE_TOTAL_BYTES:
            raise ValueError("archive expanded size exceeds limit")
        target = dest.joinpath(*parts)
        _reject_reparse_chain(target)
        target = target.resolve()
        if not target.is_relative_to(dest):
            raise ValueError(f"unsafe archive entry: {m.filename!r}")
        if m.is_dir():
            if target.exists() and not target.is_dir():
                raise ValueError(f"archive directory collides with an existing file: {m.filename!r}")
            target.mkdir(parents=True, exist_ok=True)
            _reject_reparse_chain(target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        _reject_reparse_chain(target.parent)
        # Exclusive creation prevents truncating a pre-existing hard link on NTFS.
        try:
            out = target.open("xb")
        except FileExistsError as exc:
            raise ValueError(f"archive file collides with an existing path: {m.filename!r}") from exc
        try:
            # Own the output before opening a ZIP member, which may fail.
            with out, zf.open(m, "r") as src:
                copied = 0
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    copied += len(chunk)
                    if copied > _MAX_ARCHIVE_ENTRY_BYTES or copied > m.file_size + 1024 * 1024:
                        raise ValueError(f"archive entry expanded beyond declared safe size: {m.filename!r}")
                    out.write(chunk)
        except Exception:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
            raise


def rezip(src_dir: Path, out_path: Path) -> None:
    src_dir = src_dir.absolute()
    out_path = out_path.absolute()
    _reject_reparse_chain(src_dir)
    _reject_reparse_chain(out_path.parent)
    src_real = src_dir.resolve()
    if not src_real.is_dir():
        raise ValueError(f"OOXML source directory does not exist: {src_dir}")

    files: list[Path] = []
    seen_windows_paths: set[str] = set()
    stack = [src_real]
    while stack:
        directory = stack.pop()
        if _is_reparse(directory):
            raise ValueError(f"OOXML source contains a symbolic link/junction/reparse point: {directory}")
        with os.scandir(directory) as entries:
            for entry in entries:
                candidate = Path(entry.path)
                if entry.is_symlink() or _is_reparse(candidate):
                    raise ValueError(f"OOXML source contains a symbolic link/junction/reparse point: {candidate}")
                if entry.is_dir(follow_symlinks=False):
                    stack.append(candidate)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                _reject_hardlinked_file(candidate)
                rel = candidate.relative_to(src_real)
                parts = _validate_archive_name(rel.as_posix())
                windows_key = "/".join(unicodedata.normalize("NFC", part).casefold() for part in parts)
                if windows_key in seen_windows_paths:
                    raise ValueError(f"case-insensitive/Unicode-normalized OOXML path collision: {rel}")
                seen_windows_paths.add(windows_key)
                files.append(candidate)
    files.sort(key=lambda item: item.relative_to(src_real).as_posix())

    ct = src_real / "[Content_Types].xml"
    scratch = portable_temp_dir()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _reject_reparse_chain(out_path.parent)
    fd, tmp_name = tempfile.mkstemp(
        prefix=out_path.name + ".", suffix=".tmp", dir=scratch
    )
    tmp_out = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            with zipfile.ZipFile(fh, "w", zipfile.ZIP_DEFLATED) as zf:
                if ct.exists():
                    zf.write(ct, ct.relative_to(src_real), compress_type=zipfile.ZIP_STORED)
                for f in files:
                    if f == ct:
                        continue
                    zf.write(f, f.relative_to(src_real))
        if out_path.exists():
            if _is_reparse(out_path):
                raise ValueError(f"OOXML output must not be a symbolic link/junction/reparse point: {out_path}")
            mode = out_path.stat().st_mode & 0o777
        else:
            umask = os.umask(0)
            os.umask(umask)
            mode = 0o666 & ~umask
        os.chmod(tmp_out, mode)
        os.replace(tmp_out, out_path)
    finally:
        if tmp_out.exists():
            tmp_out.unlink()
