import hashlib
import json
import os
import pathlib
import re
import shutil
import stat
import sys
import tempfile
import unicodedata
import zipfile
from datetime import datetime, timezone

RAW_PLUGIN_ROOT = pathlib.Path(__file__).absolute().parents[1]
MAX_ZIP_ENTRIES = 50_000
MAX_SCAN_ENTRY_BYTES = 20_000_000
MAX_SCAN_TOTAL_BYTES = 256_000_000
MAX_NATIVE_ENTRY_BYTES = 256_000_000
MAX_NATIVE_TOTAL_BYTES = 1_000_000_000
MAX_HAR_BYTES = 100_000_000
MAX_RPC_LINE_BYTES = 2_000_000
MAX_ENDPOINTS = 10_000
MAX_ENDPOINT_ENTRIES = 20
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_VERSION = "0.6.0"
URL_RE = re.compile(rb"(?i)\b(?:https?|wss?)://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]{4,512}")
PRINTABLE_RE = re.compile(rb"[\x20-\x7e]{4,}")
WINDOWS_BAD_CHARS_RE = re.compile(r'[<>:"|?*\x00-\x1f]')
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", "CLOCK$", "CONIN$", "CONOUT$", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
JOB_NAME_RE = re.compile(r"^[0-9a-f]{64}$")


def _raw_is_reparse_or_symlink(path: pathlib.Path) -> bool:
    try:
        info = path.lstat()
        return stat.S_ISLNK(info.st_mode) or bool(
            getattr(info, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        )
    except FileNotFoundError:
        return False
    except OSError:
        return True


def _reject_raw_reparse_chain(root: pathlib.Path, leaf: pathlib.Path) -> None:
    try:
        rel = leaf.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("plugin path is not inside the portable root") from exc
    current = root
    if _raw_is_reparse_or_symlink(current):
        raise RuntimeError(f"portable root may not be a reparse/symlink: {current}")
    for part in rel.parts:
        current = current / part
        if _raw_is_reparse_or_symlink(current):
            raise RuntimeError(f"plugin path contains a reparse/symlink: {current}")


def find_package_root() -> pathlib.Path:
    # Derive from the installed layout; never probe unrelated parent directories
    # for markers or accept a stale/inherited install root after relocation.
    root = RAW_PLUGIN_ROOT.parents[2]
    if RAW_PLUGIN_ROOT != root / "home" / "plugins" / "android-apk-lab":
        raise RuntimeError("APK Lab must run from home/plugins/android-apk-lab")
    _reject_raw_reparse_chain(pathlib.Path(root.anchor), RAW_PLUGIN_ROOT)
    for marker in ("codex.exe", "env.ps1"):
        path = root / marker
        if _raw_is_reparse_or_symlink(path):
            raise RuntimeError(f"portable root marker may not be a link: {path}")
        try:
            info = path.lstat()
        except OSError as exc:
            raise RuntimeError(f"unable to locate Codex Portable root from {RAW_PLUGIN_ROOT}") from exc
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RuntimeError(f"portable root marker must be a single-link file: {path}")
    return root


# Initialized only after the caller explicitly selects this task's manual MCP.
# Import/discovery performs no root probing, directory creation, or device work.
PKG_ROOT: pathlib.Path
JOBS_ROOT: pathlib.Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_reparse_or_symlink(path: pathlib.Path) -> bool:
    return _raw_is_reparse_or_symlink(path)


def inside(path) -> pathlib.Path:
    if path is None:
        raise ValueError("path is required")
    raw = pathlib.Path(path)
    if not raw.is_absolute():
        raw = pathlib.Path.cwd() / raw
    lexical = pathlib.Path(os.path.abspath(os.fspath(raw)))
    try:
        lexical_rel = lexical.relative_to(PKG_ROOT)
    except ValueError as exc:
        raise ValueError(f"path escapes portable package: {path}") from exc
    current = PKG_ROOT
    if _is_reparse_or_symlink(current):
        raise ValueError(f"portable root may not be a reparse/symlink: {current}")
    for part in lexical_rel.parts:
        current = current / part
        if _is_reparse_or_symlink(current):
            raise ValueError(f"reparse/symlink component rejected: {current}")
    p = lexical.resolve(strict=False)
    try:
        p.relative_to(PKG_ROOT)
    except ValueError as exc:
        raise ValueError(f"path escapes portable package after resolution: {path}") from exc
    return p


def _inside_user_area(path) -> pathlib.Path:
    p = inside(path)
    allowed_roots = (inside(PKG_ROOT / "work"), inside(PKG_ROOT / "tmp"))
    if not any(p == root or root in p.parents for root in allowed_roots):
        raise ValueError("APK Lab host-side inputs are restricted to portable work/ and tmp/")
    return p


def _inside_user_input_file(path) -> pathlib.Path:
    p = _inside_user_area(path)
    if not p.is_file():
        raise ValueError(f"input file not found: {p}")
    try:
        info = os.stat(p, follow_symlinks=False)
    except OSError as exc:
        raise ValueError(f"unable to inspect input file safely: {p}: {exc}") from exc
    if getattr(info, "st_nlink", 1) != 1:
        raise ValueError(f"hard-linked APK Lab input is not allowed: {p}")
    return p


def inside_jobs(path) -> pathlib.Path:
    p = inside(path)
    jobs = inside(JOBS_ROOT)
    work = inside(PKG_ROOT / "work")
    try:
        jobs.relative_to(work)
    except ValueError as exc:
        raise ValueError("APK_LAB_JOBS_DIR must stay inside portable work/") from exc
    try:
        p.relative_to(jobs)
    except ValueError as exc:
        raise ValueError(f"job path escapes APK Lab jobs directory: {path}") from exc
    return p


def _prepare_atomic_destination(path, *, jobs_only=False):
    """Return a validated destination and parent for an atomic package-local write.

    Existing destination files are deliberately *not* opened in-place: replacing a
    directory entry is safe even when an attacker pre-created that entry as a hard
    link to another file.  Parent components are still rejected when they are
    symlinks/junctions/reparse points.
    """
    validator = inside_jobs if jobs_only else inside
    dest = validator(path)
    parent = validator(dest.parent)
    parent.mkdir(parents=True, exist_ok=True)
    parent = validator(parent)
    return dest, parent


def _atomic_write_text(path, text: str, *, encoding="utf-8", jobs_only=False):
    dest, parent = _prepare_atomic_destination(path, jobs_only=jobs_only)
    fd, temp_name = tempfile.mkstemp(prefix=".codex-write-", suffix=".tmp", dir=parent)
    temp = pathlib.Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        # Re-check the parent immediately before the replace. os.replace replaces a
        # symlink/hardlink directory entry rather than following the destination.
        (inside_jobs if jobs_only else inside)(parent)
        os.replace(temp, dest)
    except Exception:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return dest


def _atomic_copy_file(source, path, *, jobs_only=False):
    source = _inside_user_input_file(source)
    dest, parent = _prepare_atomic_destination(path, jobs_only=jobs_only)
    fd, temp_name = tempfile.mkstemp(prefix=".codex-copy-", suffix=".tmp", dir=parent)
    temp = pathlib.Path(temp_name)
    try:
        with source.open("rb") as src, os.fdopen(fd, "wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        (inside_jobs if jobs_only else inside)(parent)
        os.replace(temp, dest)
    except Exception:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return dest


def _atomic_copy_limited(source, path, expected_size: int, *, jobs_only=False):
    dest, parent = _prepare_atomic_destination(path, jobs_only=jobs_only)
    fd, temp_name = tempfile.mkstemp(prefix=".codex-extract-", suffix=".tmp", dir=parent)
    temp = pathlib.Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as target:
            _copy_limited(source, target, expected_size)
            target.flush()
            os.fsync(target.fileno())
        (inside_jobs if jobs_only else inside)(parent)
        os.replace(temp, dest)
    except Exception:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return dest


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_job(file_path):
    p = _inside_user_input_file(file_path)
    h = sha256_file(p)
    d = inside_jobs(JOBS_ROOT / h)
    for sub in ["input", "metadata", "decoded", "decompiled", "native", "network", "patches", "build", "tests", "runtime", "report"]:
        inside_jobs(d / sub).mkdir(parents=True, exist_ok=True)
    return p, h, d


def write_json(path, obj):
    path = _atomic_write_text(
        path,
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        jobs_only=True,
    )
    return str(path)


def checked_zip_infos(zf: zipfile.ZipFile):
    infos = zf.infolist()
    if len(infos) > MAX_ZIP_ENTRIES:
        raise ValueError(f"archive has too many entries: {len(infos)}")
    return infos


def file_type(p: pathlib.Path) -> str:
    suffix = p.suffix.lower()
    if suffix in [".apk", ".xapk", ".apks", ".aab", ".jar", ".zip"]:
        try:
            with zipfile.ZipFile(p) as zf:
                infos = checked_zip_infos(zf)
                return "zip-android" if any(info.filename.endswith("AndroidManifest.xml") for info in infos) else "zip"
        except (OSError, zipfile.BadZipFile, ValueError):
            return "invalid-zip"
    if suffix == ".dex":
        return "dex"
    return suffix.lstrip(".") or "unknown"


def inspect_apk(args):
    p, h, d = ensure_job(args.get("path"))
    meta = {"status": "ok", "createdAt": now(), "packageRoot": str(PKG_ROOT), "path": str(p), "sha256": h,
            "size": p.stat().st_size, "type": file_type(p), "jobDir": str(d), "entries": {},
            "next": ["apk-static-analysis", "apk-report"]}
    if zipfile.is_zipfile(p):
        with zipfile.ZipFile(p) as zf:
            infos = checked_zip_infos(zf)
            names = [info.filename for info in infos]
            meta["entries"] = {"count": len(names), "manifest": "AndroidManifest.xml" in names,
                               "dex": [n for n in names if n.endswith(".dex")][:50],
                               "native": [n for n in names if n.startswith("lib/") and n.endswith(".so")][:200],
                               "resources": [n for n in names if n.startswith("res/")][:50]}
            dest = inside_jobs(d / "input" / p.name)
            if p.resolve() != dest.resolve(strict=False):
                _atomic_copy_file(p, dest, jobs_only=True)
    out = write_json(d / "metadata" / "intake.json", meta)
    meta["artifacts"] = [out]
    return meta


def iter_bytes_from_artifact(p):
    p = inside(p)
    if zipfile.is_zipfile(p):
        total = 0
        with zipfile.ZipFile(p) as zf:
            for info in checked_zip_infos(zf):
                if info.is_dir() or info.file_size > MAX_SCAN_ENTRY_BYTES:
                    continue
                if total + info.file_size > MAX_SCAN_TOTAL_BYTES:
                    return
                try:
                    data = zf.read(info)
                except (OSError, RuntimeError, zipfile.BadZipFile):
                    continue
                if len(data) > MAX_SCAN_ENTRY_BYTES or total + len(data) > MAX_SCAN_TOTAL_BYTES:
                    return
                total += len(data)
                yield info.filename, data
    else:
        size = p.stat().st_size
        if size > MAX_SCAN_TOTAL_BYTES:
            raise ValueError(f"artifact too large for lightweight string scan: {size}")
        yield p.name, p.read_bytes()


def search_strings(args):
    p, _, d = ensure_job(args.get("path"))
    pattern = args.get("pattern")
    if pattern is not None and len(str(pattern)) > 512:
        raise ValueError("pattern is too long")
    rx = re.compile(re.escape(str(pattern).encode()), re.I) if pattern else re.compile(rb".*", re.I)
    try:
        limit = int(args.get("limit", 200))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    limit = max(1, min(limit, 5000))
    hits = []
    for name, data in iter_bytes_from_artifact(p):
        for match in PRINTABLE_RE.finditer(data):
            value = match.group(0)
            if rx.search(value):
                hits.append({"entry": name, "offset": match.start(), "text": value[:300].decode("utf-8", "replace")})
                if len(hits) >= limit:
                    break
        if len(hits) >= limit:
            break
    out = write_json(d / "metadata" / "strings.json", {"status": "ok", "count": len(hits), "hits": hits})
    return {"status": "ok", "count": len(hits), "artifacts": [out], "hits": hits[:20]}


def list_endpoints(args):
    p, _, d = ensure_job(args.get("path"))
    found: dict[str, set[str]] = {}
    truncated = False
    for name, data in iter_bytes_from_artifact(p):
        for match in URL_RE.finditer(data):
            url = match.group(0).decode("utf-8", "replace").rstrip(".,;)'\"")
            entries = found.get(url)
            if entries is None:
                if len(found) >= MAX_ENDPOINTS:
                    truncated = True
                    break
                entries = set()
                found[url] = entries
            if len(entries) < MAX_ENDPOINT_ENTRIES:
                entries.add(name)
        if truncated:
            break
    endpoints = [{"url": url, "entries": sorted(entries)} for url, entries in sorted(found.items())]
    payload = {"status": "ok", "count": len(endpoints), "truncated": truncated, "maxEndpoints": MAX_ENDPOINTS, "endpoints": endpoints}
    out = write_json(d / "network" / "endpoints.json", payload)
    return {"status": "ok", "count": len(endpoints), "truncated": truncated, "artifacts": [out], "endpoints": endpoints[:50]}


def _safe_windows_component(part: str) -> bool:
    if not part or part in {".", ".."} or part.endswith((" ", ".")) or len(part) > 255:
        return False
    if WINDOWS_BAD_CHARS_RE.search(part):
        return False
    base = part.split(".", 1)[0].upper()
    return base not in WINDOWS_RESERVED


def _validated_zip_parts(name: str):
    # ZIP names are defined with forward slashes. A backslash is a path separator
    # on Windows and therefore ambiguous/dangerous in a portable archive.
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError(f"unsafe native archive entry rejected: {name}")
    pure = pathlib.PurePosixPath(name)
    parts = pure.parts
    if (
        pure.is_absolute()
        or re.match(r"^[A-Za-z]:/", name)
        or not parts
        or any(part in ("", ".", "..") for part in parts)
        or any(not _safe_windows_component(part) for part in parts)
    ):
        raise ValueError(f"unsafe native archive entry rejected: {name}")
    return parts


def _zip_info_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def safe_native_parts(name: str):
    parts = _validated_zip_parts(name)
    if parts[0] != "lib":
        return None
    # Directory entries and non-library files under lib/ are allowed but never
    # extracted. Actual .so paths need an ABI/component beneath lib/.
    if len(parts) < 3 or not name.lower().endswith(".so"):
        return None
    return parts


def _copy_limited(source, target, expected_size: int):
    copied = 0
    while True:
        chunk = source.read(min(1024 * 1024, MAX_NATIVE_ENTRY_BYTES + 1 - copied))
        if not chunk:
            break
        copied += len(chunk)
        if copied > MAX_NATIVE_ENTRY_BYTES or copied > expected_size:
            raise ValueError("native entry expanded beyond declared/allowed size")
        target.write(chunk)
    if copied != expected_size:
        raise ValueError(f"native entry size mismatch: declared={expected_size}, actual={copied}")


def extract_native(args):
    p, _, d = ensure_job(args.get("path"))
    extracted = []
    seen_windows_paths: set[str] = set()
    total = 0
    if zipfile.is_zipfile(p):
        with zipfile.ZipFile(p) as zf:
            for info in checked_zip_infos(zf):
                parts = safe_native_parts(info.filename)
                if _zip_info_is_symlink(info):
                    raise ValueError(f"symlink archive entry rejected: {info.filename}")
                if parts is None or info.is_dir():
                    continue
                windows_key = unicodedata.normalize("NFC", "/".join(parts)).casefold()
                if windows_key in seen_windows_paths:
                    raise ValueError(f"Windows/Unicode archive path collision: {info.filename}")
                seen_windows_paths.add(windows_key)
                if info.file_size > MAX_NATIVE_ENTRY_BYTES:
                    raise ValueError(f"native entry too large: {info.filename}")
                total += info.file_size
                if total > MAX_NATIVE_TOTAL_BYTES:
                    raise ValueError("native extraction exceeds total size limit")
                dest = inside_jobs(d / "native" / pathlib.Path(*parts))
                with zf.open(info, "r") as source:
                    dest = _atomic_copy_limited(source, dest, info.file_size, jobs_only=True)
                extracted.append(str(dest))
    out = write_json(d / "native" / "native-libs.json", {"status": "ok", "count": len(extracted), "files": extracted})
    return {"status": "ok", "count": len(extracted), "artifacts": [out] + extracted[:20]}


def parse_capture(args):
    p = _inside_user_input_file(args.get("path"))
    if p.stat().st_size > MAX_HAR_BYTES:
        raise ValueError("HAR is too large for lightweight parsing")
    out = {"status": "ok", "path": str(p), "note": "Supported: HAR JSON summary. mitmproxy binary flows should be converted to HAR first."}
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(data, dict):
            raise ValueError("HAR root must be an object")
        entries = data.get("log", {}).get("entries", [])
        if not isinstance(entries, list):
            raise ValueError("HAR log.entries must be an array")
        out["requests"] = [{"method": e.get("request", {}).get("method"), "url": e.get("request", {}).get("url"),
                            "status": e.get("response", {}).get("status")} for e in entries[:500] if isinstance(e, dict)]
        out["count"] = len(entries)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        out["warning"] = f"unable to parse HAR: {type(exc).__name__}: {exc}"
    return out


def _validated_job_dir(job_dir):
    d = inside_jobs(job_dir)
    jobs = inside_jobs(JOBS_ROOT)
    if d.parent != jobs or not JOB_NAME_RE.fullmatch(d.name):
        raise ValueError("jobDir must be exactly APK_LAB_JOBS_DIR/<64 lowercase hex sha256>")
    if not d.is_dir():
        raise ValueError("jobDir does not reference an existing APK Lab job")
    evidence = (
        "metadata/intake.json",
        "metadata/strings.json",
        "network/endpoints.json",
        "native/native-libs.json",
    )
    if not any(inside_jobs(d / rel).is_file() for rel in evidence):
        raise ValueError("jobDir has no APK Lab-generated evidence; use a real input path first")
    return d


def report_generate(args):
    path = args.get("path")
    if path:
        _, h, d = ensure_job(path)
    else:
        d = _validated_job_dir(args.get("jobDir"))
        h = d.name
    report = inside_jobs(d / "report" / "summary.md")
    parts = ["# APK Lab Summary\n", f"- Generated: {now()}\n", f"- Job: `{h}`\n", f"- Directory: `{d}`\n"]
    for rel in ["metadata/intake.json", "network/endpoints.json", "native/native-libs.json", "metadata/strings.json"]:
        fp = d / rel
        if fp.is_file():
            parts.append(f"- Artifact: `{fp}`\n")
    report = _atomic_write_text(report, "".join(parts), encoding="utf-8", jobs_only=True)
    return {"status": "ok", "artifacts": [str(report)], "next": "Use apk-report skill to enrich domain reports."}


TOOL_FUNCS = {
    "apk.inspect": inspect_apk,
    "portable.resolve_path": lambda a: {"status": "ok", "path": str(_inside_user_area(a.get("path")))},
    "apk.search_strings": search_strings,
    "apk.list_endpoints": list_endpoints,
    "apk.extract_native": extract_native,
    "network.parse_capture": parse_capture,
    "report.generate": report_generate,
}


def _object_schema(properties, required=(), any_of=None):
    schema = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = list(required)
    if any_of:
        schema["anyOf"] = any_of
    return schema


TOOL_SCHEMAS = {
    "apk.inspect": ("Inspect an APK/ZIP-like artifact and create a package-local job metadata record.", _object_schema({"path": {"type": "string", "minLength": 1}}, ["path"])),
    "portable.resolve_path": ("Resolve and validate a work/tmp path; rejects package-private areas, hard escape paths, and reparse/symlink traversal.", _object_schema({"path": {"type": "string", "minLength": 1}})),
    "apk.search_strings": ("Search printable strings using a literal (not regex) pattern and write bounded package-local results.", _object_schema({"path": {"type": "string", "minLength": 1}, "pattern": {"type": "string", "maxLength": 512}, "limit": {"type": "integer", "minimum": 1, "maximum": 5000}}, ["path"])),
    "apk.list_endpoints": ("Extract a bounded set of HTTP/WS endpoints from an artifact and write package-local results.", _object_schema({"path": {"type": "string", "minLength": 1}}, ["path"])),
    "apk.extract_native": ("Extract bounded lib/**/*.so entries with traversal, reparse and Windows-name protection into the package-local job.", _object_schema({"path": {"type": "string", "minLength": 1}}, ["path"])),
    "network.parse_capture": ("Read a bounded HAR JSON file inside the package and summarize requests without writing outside the package.", _object_schema({"path": {"type": "string", "minLength": 1}}, ["path"])),
    "report.generate": ("Generate a package-local report from an input artifact or an exact APK Lab SHA-256 job directory.", _object_schema({"path": {"type": "string", "minLength": 1}, "jobDir": {"type": "string", "minLength": 1}}, any_of=[{"required": ["path"]}, {"required": ["jobDir"]}])),
}
TOOL_NAMES = list(TOOL_FUNCS)


def _validate_schema_value(value, spec, label):
    expected = spec.get("type")
    if expected == "string":
        if not isinstance(value, str):
            raise ValueError(f"{label} must be a string")
        if len(value) < int(spec.get("minLength", 0)):
            raise ValueError(f"{label} is shorter than minLength")
        if "maxLength" in spec and len(value) > int(spec["maxLength"]):
            raise ValueError(f"{label} exceeds maxLength")
        return
    if expected == "integer":
        # bool is a subclass of int in Python, but JSON Schema does not treat booleans as integers.
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{label} must be an integer")
        if "minimum" in spec and value < spec["minimum"]:
            raise ValueError(f"{label} is below minimum")
        if "maximum" in spec and value > spec["maximum"]:
            raise ValueError(f"{label} exceeds maximum")
        return
    if expected is not None:
        raise RuntimeError(f"unsupported internal tool schema type: {expected}")


def _validate_required_shape(args, requirement):
    required = requirement.get("required", [])
    return all(key in args for key in required)


def validate_tool_arguments(name, args):
    _, input_schema = TOOL_SCHEMAS[name]
    allowed = input_schema.get("properties", {})
    unknown = sorted(set(args) - set(allowed))
    if unknown and input_schema.get("additionalProperties") is False:
        raise ValueError(f"unknown tool argument(s): {', '.join(unknown)}")
    missing = [key for key in input_schema.get("required", []) if key not in args]
    if missing:
        raise ValueError(f"missing required tool argument(s): {', '.join(missing)}")
    any_of = input_schema.get("anyOf", [])
    if any_of and not any(_validate_required_shape(args, option) for option in any_of):
        choices = ["+".join(option.get("required", [])) for option in any_of]
        raise ValueError(f"tool arguments must satisfy one of: {', '.join(choices)}")
    for key, value in args.items():
        spec = allowed.get(key)
        if spec is not None:
            _validate_schema_value(value, spec, f"argument {key}")


def schema(name):
    description, input_schema = TOOL_SCHEMAS[name]
    return {"name": name, "description": description, "inputSchema": input_schema}


def rpc_error(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def tool_error_result(rid, exc):
    payload = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    return {"jsonrpc": "2.0", "id": rid, "result": {"isError": True, "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}}


def handle(req):
    if not isinstance(req, dict):
        return rpc_error(None, -32600, "request must be an object")
    rid = req.get("id")
    method = req.get("method")
    if method == "initialize":
        params = req.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return rpc_error(rid, -32602, "initialize params must be an object")
        requested = str(params.get("protocolVersion") or "")
        negotiated = requested if requested in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0]
        return {"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": negotiated, "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "apk_lab_mcp", "version": SERVER_VERSION}}}
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": [schema(n) for n in TOOL_NAMES]}}
    if method == "tools/call":
        params = req.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return rpc_error(rid, -32602, "tools/call params must be an object")
        name = params.get("name")
        if name not in TOOL_FUNCS:
            return rpc_error(rid, -32601, f"unknown tool: {name}")
        args = params.get("arguments")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return rpc_error(rid, -32602, "tool arguments must be an object")
        try:
            validate_tool_arguments(name, args)
            result = TOOL_FUNCS[name](args)
            return {"jsonrpc": "2.0", "id": rid, "result": {"isError": False, "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}}
        except Exception as exc:
            return tool_error_result(rid, exc)
    if rid is None:
        return None
    return rpc_error(rid, -32601, f"method not found: {method}")


def write_rpc(response):
    # MCP stdio is UTF-8 JSON regardless of the Windows console/pipe code page.
    # ASCII escapes preserve every Unicode value while remaining valid UTF-8;
    # binary output also prevents PYTHONIOENCODING from changing wire bytes.
    sys.stdout.buffer.write((json.dumps(response, ensure_ascii=True) + "\n").encode("ascii"))
    sys.stdout.buffer.flush()


def main() -> int:
    # This switch records the caller's task-scope decision; it cannot determine
    # user intent. No environment variable or maintenance mode enables it.
    if sys.argv[1:] != ["--task-authorized"]:
        print("APK Lab MCP requires explicit task selection: --task-authorized", file=sys.stderr)
        return 2
    global PKG_ROOT, JOBS_ROOT
    PKG_ROOT = find_package_root()
    JOBS_ROOT = pathlib.Path(os.environ.get("APK_LAB_JOBS_DIR", PKG_ROOT / "work" / "apk-jobs"))
    # Validate the optional output override lexically before resolving links.
    inside_jobs(JOBS_ROOT)
    while True:
        # Decode the protocol bytes explicitly, never through locale-bound stdin.
        raw = sys.stdin.buffer.readline(MAX_RPC_LINE_BYTES + 1)
        if not raw:
            break
        if len(raw) > MAX_RPC_LINE_BYTES:
            # readline(limit) leaves the rest of an oversized line buffered.
            # Drain it so one malformed request cannot desynchronize all later
            # JSON-RPC messages on the stdio transport.
            while raw and not raw.endswith(b"\n"):
                raw = sys.stdin.buffer.readline(MAX_RPC_LINE_BYTES + 1)
            write_rpc(rpc_error(None, -32700, "request line too large"))
            continue
        try:
            req = json.loads(raw.decode("utf-8"))
            response = handle(req)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            response = rpc_error(None, -32700, f"parse error: {type(exc).__name__}")
        except Exception as exc:
            response = rpc_error(None, -32000, f"{type(exc).__name__}: {exc}")
        if response is not None:
            write_rpc(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
