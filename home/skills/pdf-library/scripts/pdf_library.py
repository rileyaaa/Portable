"""Local, page-addressable PDF library using PyMuPDF4LLM and PyMuPDF.

No model, network, browser, MCP server or OCR process starts on import.
Generated libraries are task output, not additional project documentation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
import uuid
import zipfile

SCHEMA = 1
APPLICATION_ID = 1129335857
REPORTS = ("INDEX.md", "VALIDATION.md", "OCR.md", "SHA256.md")
CODE = re.compile(
    r"^\s*(?:#\s*(?:define|include|if|else|endif)\b|"
    r"(?:SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|FROM|WHERE|JOIN|"
    r"BEGIN|END|DECLARE|EXEC|GRANT|REVOKE)\b|"
    r"(?:def|class|import|from|public|private|return|const|let|var)\b|"
    r"[{}]|<[/!?]?[A-Za-z]|(?:[A-Za-z_][\w.]*\s*[:=])|"
    r"(?:(?:\./|/)[\w./-]+)|(?:[A-Z_][A-Z_0-9]*))"
)
BAD_LAYOUT = re.compile(
    r"</?(?:table|tbody|thead|tfoot|tr|td|th|details|summary)\b[^>]*>"
    r"|<!--[\s\S]*?-->|&nbsp;|!\[[^\]]*\]\([^)]*\)"
    r"|data:image/|(?:^|[\s/])_assets(?:/|\b)", re.I
)


def _checked_root() -> Path:
    script = Path(__file__).absolute()
    if len(script.parents) < 5:
        raise RuntimeError("PDF library helper is outside the bundled layout")
    root = script.parents[4]
    if script.relative_to(root).parts != (
        "home", "skills", "pdf-library", "scripts", "pdf_library.py"
    ):
        raise RuntimeError("PDF library helper is outside the bundled layout")
    for path in (*reversed(script.parents), script):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise RuntimeError("PDF library path contains a link/reparse point")
    for path in (script, root / "env.ps1", root / "codex.exe"):
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                getattr(info, "st_file_attributes", 0) & 0x400):
            raise RuntimeError("PDF library requires ordinary single-link package files")
    return root


ROOT = _checked_root()
_safety_path = ROOT / "home/skills/pdf/scripts/portable_safety.py"
for _entry in (ROOT / "home", ROOT / "home/skills", ROOT / "home/skills/pdf",
               ROOT / "home/skills/pdf/scripts", _safety_path):
    _info = _entry.lstat()
    if stat.S_ISLNK(_info.st_mode) or getattr(_info, "st_file_attributes", 0) & 0x400:
        raise RuntimeError("PDF safety helper path contains a link/reparse point")
if not stat.S_ISREG(_info.st_mode) or _info.st_nlink != 1:
    raise RuntimeError("PDF safety helper must be an ordinary single-link file")
_spec = importlib.util.spec_from_file_location("_pdf_library_safety", _safety_path)
_safety = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_safety)


def checked(path: str | Path, *, exists=False, kind=None) -> Path:
    return _safety.resolve_inside(path, must_exist=exists, kind=kind)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with checked(path, exists=True, kind="file").open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized(text: str) -> str:
    # Whitespace only. Do not drop underscores, punctuation, case or digits.
    return re.sub(r"\s+", "", text)


def fence(text: str, language="text") -> str:
    length = max((len(x) for x in re.findall(r"`+", text)), default=0)
    ticks = "`" * max(3, length + 1)
    return f"{ticks}{language}\n{text.rstrip()}\n{ticks}\n" if text.strip() else ""


def outside_fences(text: str) -> str:
    lines, open_fence = [], None
    for line in text.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if open_fence is None:
                open_fence = token
            elif token[0] == open_fence[0] and len(token) >= len(open_fence):
                open_fence = None
            continue
        if open_fence is None:
            lines.append(line)
    if open_fence:
        raise ValueError("Unclosed Markdown code fence")
    return "\n".join(lines)


def check_markdown(text: str) -> None:
    plain = outside_fences(text)
    if BAD_LAYOUT.search(plain):
        raise ValueError("Markdown contains layout HTML, image references or assets")
    # Source HTML/XML and literal Markdown examples are valid inside fences.
    open_fence = None
    for line in text.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if open_fence is None:
                open_fence = token
            elif token[0] == open_fence[0] and len(token) >= len(open_fence):
                open_fence = None
        elif open_fence and re.fullmatch(r"## PDF 第 \d+ 页", line):
            raise ValueError("Page heading is inside a code fence")


def ensure_coverage(raw: str, structured: str) -> tuple[str, dict]:
    """Keep extraction output, supplement missing original lines, then audit.

    The character-multiset check catches missing repeated characters too. It
    measures PyMuPDF's extracted text, not visual correctness of the PDF.
    """
    try:
        check_markdown(structured)
    except ValueError:
        structured = ""
    result = structured.strip()
    available = normalized(result)
    missing = []
    for line in raw.splitlines():
        item = normalized(line)
        if item and item not in available:
            missing.append(line)
            available += item
    if missing:
        result += "\n\n### 原始文字补充\n\n" + fence("\n".join(missing))
    needed = Counter(normalized(raw))
    have = Counter(normalized(result))
    # If counts still differ, replace the structural rendering rather than
    # repeating an entire page alongside it.
    if any(have[char] < count for char, count in needed.items()):
        result = "### 原始文字层（保真回退）\n\n" + fence(raw)
    have = Counter(normalized(result))
    total = sum(needed.values())
    matched = sum(min(count, have[char]) for char, count in needed.items())
    code_lines = [line for line in raw.splitlines() if CODE.match(line) and line.strip()]
    exact = normalized(result)
    code_matched = sum(normalized(line) in exact for line in code_lines)
    check_markdown(result)
    return result.strip(), {
        "text_total": total, "text_matched": matched,
        "code_total": len(code_lines), "code_matched": code_matched,
        "supplement_lines": len(missing),
    }


def _write(path: Path, text: str, *, expected_sha: str | None = None,
           require_absent: bool = False) -> None:
    path = checked(path)
    # Keep transient writes out of persistent work/library directories.
    scratch = _safety.prepare_output_dir(ROOT / "tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    checked(path.parent, exists=True, kind="dir")
    handle, temporary = tempfile.mkstemp(prefix=".pdf-library-", dir=scratch)
    temp = Path(temporary)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        checked(path)
        # Recheck output ownership after staging, just before replacing. Users
        # may edit or create Markdown while an expensive PDF render is running.
        if expected_sha is not None:
            if not path.is_file() or sha256(path) != expected_sha:
                raise ValueError("Generated Markdown was removed/edited during conversion; "
                                 "refusing to overwrite user changes")
        elif require_absent and path.exists():
            raise ValueError("Refusing to replace an unowned Markdown output")
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _pdfs(source: Path) -> list[tuple[str, Path]]:
    source = checked(source, exists=True)
    if source.is_file():
        if source.suffix.lower() != ".pdf":
            raise ValueError("Input file must be PDF")
        _portable_name(source.name)
        return [(source.name, source)]
    result, stack = [], [source]
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                item = checked(entry.path, exists=True)
                if item.is_dir():
                    stack.append(item)
                elif item.is_file() and item.suffix.lower() == ".pdf":
                    relative = item.relative_to(source).as_posix()
                    _portable_name(relative)
                    result.append((relative, item))
    names = [unicodedata.normalize("NFC", str(Path(name).with_suffix(".md"))).casefold()
             for name, _ in result]
    if len(names) != len(set(names)):
        raise ValueError("PDF names collide after Windows Markdown filename normalization")
    return sorted(result)


def _portable_name(relative: str) -> None:
    """Reject names Windows cannot preserve, including ADS and device aliases."""
    for part in relative.split("/"):
        if (not part or part in (".", "..") or part.endswith((" ", ".")) or
                re.search(r'[<>:"\\|?*\x00-\x1f]', part) or
                re.fullmatch(r"(?i)(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part)):
            raise ValueError(f"Filename cannot be preserved safely on Windows: {relative}")


@contextlib.contextmanager
def _scratch_directory(parent: Path, prefix: str):
    """Create an owned scratch child without replacing the Windows parent ACL.

    Python 3.13+ gives mkdir(0o700), including tempfile.TemporaryDirectory,
    a protected Windows DACL. A restricted Codex process may be denied access
    to that directory even though its package-local tmp parent is writable.
    Inherit the existing ACL on Windows; keep mode 0700 on POSIX. This is not
    a grant of access to any other directory or a privacy guarantee.
    """
    parent = _safety.prepare_output_dir(parent)
    staging = checked(parent / (prefix + uuid.uuid4().hex))
    staging.mkdir(mode=0o777 if os.name == "nt" else 0o700)
    identity = staging.lstat()
    try:
        checked(staging, exists=True, kind="dir")
        yield staging
    finally:
        # Never follow a replaced directory or delete somebody else's tree.
        checked(staging, exists=True, kind="dir")
        current = staging.lstat()
        if (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
            raise RuntimeError("PDF scratch directory identity changed; refusing cleanup")
        shutil.rmtree(staging)


def _database(library: Path, *, create=False):
    library = checked(library)
    db = checked(library / "_index.sqlite3")
    for suffix in ("-journal", "-wal", "-shm"):
        checked(Path(str(db) + suffix))
    if not db.exists():
        if not create:
            raise FileNotFoundError("Library index is missing; run build first")
        if library.exists() and any(library.iterdir()):
            raise ValueError("Refusing an unmanaged, nonempty library directory")
        library.mkdir(parents=True, exist_ok=True)
    else:
        checked(db, exists=True, kind="file")
        with _scratch_directory(ROOT / "tmp", "pdf-ownership-") as staging:
            snapshot = staging / "index.sqlite3"
            shutil.copyfile(db, snapshot)
            wal = checked(Path(str(db) + "-wal"))
            if wal.exists():
                shutil.copyfile(wal, Path(str(snapshot) + "-wal"))
            with contextlib.closing(sqlite3.connect(snapshot)) as probe:
                identity = probe.execute("PRAGMA application_id").fetchone()[0]
                if identity not in ((0, APPLICATION_ID) if create else (APPLICATION_ID,)):
                    raise ValueError("Not a PDF library database")
                if identity == 0 and probe.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]:
                    raise ValueError("Refusing an unrelated SQLite database")
    connection = sqlite3.connect(db) if create else \
        sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA temp_store=MEMORY")
    identity = connection.execute("PRAGMA application_id").fetchone()[0]
    if identity not in ((0, APPLICATION_ID) if create else (APPLICATION_ID,)):
        connection.close()
        raise ValueError("Not a PDF library database")
    if not create:
        try:
            connection.execute("PRAGMA query_only=ON")
            # Check recovery state and read the index in the same snapshot.
            connection.execute("BEGIN")
            _require_complete(connection)
        except BaseException:
            connection.close()
            raise
        return connection
    # Establish ownership before any persistent PRAGMA. Views and other schema
    # objects also identify a nonempty, unowned database; do not adopt it.
    if identity == 0 and connection.execute(
        "SELECT count(*) FROM sqlite_master"
    ).fetchone()[0]:
        connection.close()
        raise ValueError("Refusing an unrelated SQLite database")
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.executescript(f"""
        PRAGMA application_id={APPLICATION_ID};
        CREATE TABLE IF NOT EXISTS documents(
            document TEXT PRIMARY KEY, source_sha TEXT NOT NULL,
            output_sha TEXT NOT NULL, signature TEXT NOT NULL, pages INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS pages(
            document TEXT NOT NULL, page INTEGER NOT NULL, markdown TEXT NOT NULL,
            text_total INTEGER, text_matched INTEGER, code_total INTEGER, code_matched INTEGER,
            ocr_status TEXT, ocr_reason TEXT, images INTEGER, supplement_lines INTEGER,
            PRIMARY KEY(document,page));
        CREATE TABLE IF NOT EXISTS pending_output(
            singleton INTEGER PRIMARY KEY CHECK(singleton=1),
            document TEXT NOT NULL, previous_sha TEXT, desired_sha TEXT,
            publication_token TEXT DEFAULT 'unknown',
            CHECK(previous_sha IS NOT NULL OR desired_sha IS NOT NULL));
    """)
    connection.commit()
    # Older pending rows did not record whether the output operation started.
    # Never grant them new publication permission merely by upgrading.
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        if "publication_token" not in {row[1] for row in connection.execute(
                "PRAGMA table_info(pending_output)")}:
            connection.execute("ALTER TABLE pending_output ADD COLUMN "
                               "publication_token TEXT DEFAULT 'unknown'")
    return connection


def _dependencies():
    try:
        # Upstream can emit a layout-extra suggestion on import; no extra or
        # model is installed by this adapter.
        with contextlib.redirect_stdout(io.StringIO()):
            import pymupdf
            import pymupdf4llm
    except ImportError as error:
        raise RuntimeError(
            "Package-local PyMuPDF/PyMuPDF4LLM is missing. Provision the pinned "
            "PDF-library dependencies; do not use host tools or auto-install."
        ) from error
    return pymupdf, pymupdf4llm


def _ocr(page, *, language: str, raw: str) -> tuple[str, str, str]:
    if not re.fullmatch(r"[A-Za-z0-9_]+(?:\+[A-Za-z0-9_]+)*", language):
        raise ValueError("Invalid OCR language list")
    executable = checked(ROOT / "tool/ocr/tesseract/tesseract.exe")
    data = checked(ROOT / "tool/ocr/tesseract/tessdata")
    if not executable.is_file() or not data.is_dir():
        return "", "missing", "Package-local Tesseract/tessdata missing"
    for name in language.split("+"):
        if not checked(data / (name + ".traineddata")).is_file():
            return "", "missing", "Requested package-local OCR language data missing"
    with _scratch_directory(ROOT / "tmp/pdf-library-ocr", "page-") as task:
        image = task / "page.png"
        page.get_pixmap(dpi=200).save(image)
        allowed = ("SystemRoot", "SYSTEMROOT", "WINDIR", "SystemDrive", "ComSpec",
                   "PATHEXT", "OS", "NUMBER_OF_PROCESSORS")
        environment = {key: os.environ[key] for key in allowed if key in os.environ}
        for key in ("HOME", "USERPROFILE", "TEMP", "TMP", "TMPDIR", "APPDATA",
                    "LOCALAPPDATA", "XDG_CACHE_HOME", "XDG_CONFIG_HOME"):
            environment[key] = str(task)
        environment["TESSDATA_PREFIX"] = str(data)
        environment["PATH"] = str(executable.parent)
        try:
            run = subprocess.run(
                [str(executable), str(image), "stdout", "--tessdata-dir", str(data),
                 "-l", language, "tsv"], cwd=task, env=environment, timeout=120,
                check=True, capture_output=True, text=True, encoding="utf-8",
            )
        except (OSError, subprocess.SubprocessError):
            return "", "failed", "Package-local OCR failed or timed out"
        lines, uncertain = {}, False
        for record in csv.DictReader(io.StringIO(run.stdout), delimiter="\t"):
            word = (record.get("text") or "").strip()
            if not word:
                continue
            confidence = float(record.get("conf", "-1"))
            if confidence < 0:
                continue
            if confidence < 70:
                word = "[疑似：" + word + "]"
                uncertain = True
            key = tuple(record.get(key) for key in
                        ("page_num", "block_num", "par_num", "line_num"))
            lines.setdefault(key, []).append(word)
        source = normalized(raw)
        novel = [" ".join(words) for words in lines.values()
                 if normalized(" ".join(words)) not in source]
        return "\n".join(novel), "low-confidence" if uncertain else "processed", \
            "OCR requires visual spot checks; confidence is not a correctness guarantee"


def _render_document(path: Path, *, ocr: str, language: str) -> list[dict]:
    pymupdf, formatter = _dependencies()
    results = []
    with pymupdf.open(path) as document:
        if document.needs_pass:
            raise ValueError("Encrypted PDF needs a separately authorized decrypted working copy")
        for index, page in enumerate(document):
            raw = page.get_text("text", sort=True)
            # Never save/embed images; margins=0 keeps header/footer text for
            # verification. Repeated prose is not automatically deleted.
            with contextlib.redirect_stdout(io.StringIO()):
                structured = formatter.to_markdown(
                    document, pages=[index], write_images=False, embed_images=False,
                    ignore_images=True, margins=0, force_text=True, show_progress=False,
                )
            markdown, audit = ensure_coverage(raw, structured)
            images = len(page.get_images())
            candidate = images > 0 or len(normalized(raw)) < 20
            reason = "image content or sparse text layer" if candidate else \
                "No image/sparse-text signal; vector and visual layout still need review"
            status = "not-requested" if candidate else "not-flagged"
            if ocr == "all" or (ocr == "auto" and candidate):
                additional, status, reason = _ocr(page, language=language, raw=raw)
                if additional.strip():
                    markdown += "\n\n### 图示或截图中的文字（OCR）\n\n" + fence(additional)
            markdown = f"## PDF 第 {index + 1} 页\n\n{markdown.strip()}\n"
            check_markdown(markdown)
            results.append(dict(
                page=index + 1, markdown=markdown, ocr_status=status,
                ocr_reason=reason, images=images, **audit
            ))
    return results


def _output(library: Path, document: str) -> Path:
    _portable_name(document)
    relative = Path(document)
    if relative.anchor or ".." in relative.parts or relative.suffix.lower() != ".pdf":
        raise ValueError("Invalid indexed document path")
    return checked(library / "manuals" / relative.with_suffix(".md"))


def _check_owned_output(library: Path, row) -> None:
    output = _output(library, row["document"])
    if not output.is_file() or sha256(output) != row["output_sha"]:
        raise ValueError(f"Generated Markdown was removed/edited: {row['document']}; "
                         "use a new library instead of overwriting user changes")


def _check_orphan_pages(connection) -> None:
    if connection.execute(
        "SELECT 1 FROM pages p LEFT JOIN documents d ON p.document=d.document "
        "WHERE d.document IS NULL LIMIT 1"
    ).fetchone():
        raise ValueError("Library index contains orphan pages")


def _indexed_text(connection, row) -> str:
    document = row["document"]
    indexed = connection.execute(
        "SELECT page,markdown FROM pages WHERE document=? ORDER BY page", (document,)
    ).fetchall()
    expected = list(range(1, row["pages"] + 1))
    if [page["page"] for page in indexed] != expected:
        raise ValueError(f"Indexed page mapping differs from generated Markdown: {document}")
    return "# " + Path(document).stem.replace("\n", " ") + "\n\n" + \
        "\n".join(page["markdown"] for page in indexed)


def _check_indexed_output(library: Path, connection, row) -> str:
    document = row["document"]
    # Reconstruct the same UTF-8 text written by build, including page separators.
    # Do not normalize newlines when comparing the indexed and generated content.
    raw = checked(_output(library, document), exists=True, kind="file").read_bytes()
    if hashlib.sha256(raw).hexdigest() != row["output_sha"]:
        raise ValueError(f"Generated Markdown was removed/edited: {document}; "
                         "use a new library instead of overwriting user changes")
    text = raw.decode("utf-8")
    if _indexed_text(connection, row) != text:
        raise ValueError(f"Indexed page content differs from generated Markdown: {document}")
    return text


def _require_complete(connection) -> None:
    # Existing libraries have no recovery table until the next build.
    if (connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='pending_output'"
        ).fetchone() and connection.execute(
            "SELECT 1 FROM pending_output LIMIT 1"
        ).fetchone()):
        raise ValueError("Unfinished Markdown/index update; rerun build to recover it")


def _recover_output(library: Path, connection) -> None:
    # The index and intent are already committed. NULL means publication has
    # never been authorized; a durable token means it may have happened.
    # Only the call that commits a new token may change the previous output.
    claim = None
    while True:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            pending = connection.execute("SELECT * FROM pending_output").fetchone()
            if claim is not None and (pending is None or pending["publication_token"] != claim):
                raise ValueError("Pending Markdown update changed during recovery; retry")
            if pending is None:
                return
            document = pending["document"]
            previous, desired = pending["previous_sha"], pending["desired_sha"]
            if any(value is not None and not re.fullmatch(r"[0-9a-f]{64}", value)
                   for value in (previous, desired)):
                raise ValueError("Invalid pending Markdown identity")
            output = checked(_output(library, document), kind="file")
            row = connection.execute("SELECT * FROM documents WHERE document=?", (document,)).fetchone()
            _check_orphan_pages(connection)
            if desired is None:
                if row is not None:
                    raise ValueError("Pending Markdown deletion differs from index")
            else:
                if row is None or row["output_sha"] != desired:
                    raise ValueError("Pending Markdown identity differs from index")
                text = _indexed_text(connection, row)
                if hashlib.sha256(text.encode("utf-8")).hexdigest() != desired:
                    raise ValueError("Pending Markdown content differs from index")
                check_markdown(text)
            actual = sha256(output) if output.exists() else None
            if actual != desired:
                if actual != previous:
                    raise ValueError("Pending Markdown was removed/edited; refusing to overwrite user changes")
                if claim is None:
                    if pending["publication_token"] is not None:
                        raise ValueError(f"Pending Markdown publication is uncertain: {document}; "
                                         "refusing to overwrite user changes; preserve this library "
                                         "and use a new library or reconcile the pending output before retrying")
                    claim = uuid.uuid4().hex
                    connection.execute("UPDATE pending_output SET publication_token=? WHERE singleton=1",
                                       (claim,))
                    # Exiting this transaction commits the token BEFORE touching
                    # the file. Reacquire the write lock and recheck its identity,
                    # index and current bytes before using the one-shot claim.
                    continue
                if desired is None:
                    _check_owned_output(library, {"document": document, "output_sha": previous})
                    checked(output, exists=True, kind="file").unlink()
                else:
                    _write(output, text, expected_sha=previous, require_absent=previous is None)
            if (sha256(output) if output.exists() else None) != desired:
                raise ValueError("Pending Markdown output differs after recovery")
            connection.execute("DELETE FROM pending_output WHERE singleton=1")
            return


@contextlib.contextmanager
def _document_update(library: Path, connection, name, previous, desired):
    # One document at a time. SQL failure rolls back both the index and the
    # intent before touching Markdown. Once committed, recovery is forward-only.
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        _require_complete(connection)
        row = connection.execute("SELECT * FROM documents WHERE document=?", (name,)).fetchone()
        if row != previous:
            raise ValueError("Indexed document changed during build; retry")
        if previous is None:
            if _output(library, name).exists():
                raise ValueError("Refusing to replace an unowned Markdown output")
        else:
            _check_owned_output(library, previous)
        connection.execute("INSERT INTO pending_output "
                           "(singleton,document,previous_sha,desired_sha,publication_token) VALUES(1,?,?,?,NULL)",
                           (name, previous["output_sha"] if previous is not None else None, desired))
        yield
    _recover_output(library, connection)


def _summary(connection) -> dict:
    totals = connection.execute(
        "SELECT count(*),coalesce(sum(text_total),0),coalesce(sum(text_matched),0),"
        "coalesce(sum(code_total),0),coalesce(sum(code_matched),0) FROM pages"
    ).fetchone()
    incomplete = connection.execute(
        "SELECT count(*) FROM pages WHERE ocr_status NOT IN ('processed','not-flagged')"
    ).fetchone()[0]
    return dict(
        documents=connection.execute("SELECT count(*) FROM documents").fetchone()[0],
        pages=totals[0], text_coverage=1.0 if totals[1] == 0 else totals[2] / totals[1],
        code_coverage=1.0 if totals[3] == 0 else totals[4] / totals[3],
        detected_code_lines=totals[3], incomplete_ocr_pages=incomplete,
        strict_ok=totals[0] > 0 and totals[1] == totals[2] and
                  totals[3] == totals[4] and incomplete == 0,
    )


def _reports(library: Path, connection, summary: dict) -> None:
    rows = connection.execute("SELECT * FROM documents ORDER BY document").fetchall()
    index = ["# PDF 手册索引", "", "先 search，再 read 所需页；不要把全部手册送入上下文。", "",
             "| 文档 | 页数 |", "| --- | ---: |"]
    checksums = ["# SHA-256", "", "以下摘要用于增量和交付核对，不代表内容无损。", "",
                 "| PDF 相对路径 | 原 PDF | Markdown |", "| --- | --- | --- |"]
    for row in rows:
        label = row["document"].replace("|", "\\|")
        index.append(f"| {label} | {row['pages']} |")
        checksums.append(f"| {label} | `{row['source_sha']}` | `{row['output_sha']}` |")
    validation = [
        "# 转换与验收报告", "",
        f"- 手册数：{summary['documents']}；总页数：{summary['pages']}。",
        f"- PyMuPDF 可提取文字层字符覆盖率（仅忽略空白）：{summary['text_coverage']:.2%}。",
        f"- 检测到的代码行覆盖率：{summary['code_coverage']:.2%}"
        f"（{summary['detected_code_lines']} 行；启发式检测不保证发现全部代码）。",
        "- 结构化转换：PyMuPDF4LLM；漏行使用原始文字补充，计数不足则改为整页保真回退。",
        "- 覆盖检查针对提取器输出，不验证字体映射、阅读顺序、表格语义或原 PDF 视觉内容。",
        "- 图片、截图、箭头、颜色、空间关系不能宣称无损；OCR 与人工检查见 OCR.md。",
        "- 人工抽查：尚未执行。正式验收按任务要求抽查代码、表格、跨页与截图；"
        "不足 5 份手册或 20 张表格时检查全部可用样本并说明。",
        f"- 自动严格检查：{'通过' if summary['strict_ok'] else '未完成'}；"
        "这不是视觉/OCR 正确率 100% 的声明。",
    ]
    ocr = ["# OCR 校验报告", "",
           "不覆盖原文字层，不保存图片到交付 ZIP。未被自动标记的页面也可能需要人工检查。",
           "", "| 文档 | 页 | 状态 | 原因 |", "| --- | ---: | --- | --- |"]
    for row in connection.execute(
        "SELECT document,page,ocr_status,ocr_reason FROM pages ORDER BY document,page"
    ):
        ocr.append("| " + " | ".join(str(x).replace("|", "\\|") for x in row) + " |")
    for name, lines in zip(REPORTS, (index, validation, ocr, checksums)):
        _write(library / name, "\n".join(lines) + "\n")


def build_library(input_path: Path, library_path: Path, *, ocr="none",
                  language="eng", strict=False) -> dict:
    if ocr not in ("none", "auto", "all"):
        raise ValueError("OCR must be none, auto or all")
    source = checked(input_path, exists=True)
    library = checked(library_path)
    if source == library or library.is_relative_to(source) or source.is_relative_to(library):
        raise ValueError("Source and library must be separate directories")
    items = _pdfs(source)
    pymupdf, formatter = _dependencies()
    signature = json.dumps([SCHEMA, pymupdf.VersionBind, formatter.__version__, ocr, language])
    connection = _database(library, create=True)
    reused = removed = 0
    try:
        _recover_output(library, connection)
        _check_orphan_pages(connection)
        old = {row["document"]: row for row in connection.execute("SELECT * FROM documents")}
        for row in old.values():
            _check_owned_output(library, row)
        current = {name for name, _ in items}
        for name, path in items:
            digest = sha256(path)
            previous = old.get(name)
            retry_ocr = previous and connection.execute(
                "SELECT 1 FROM pages WHERE document=? AND ocr_status IN ('missing','failed') LIMIT 1",
                (name,),
            ).fetchone() is not None
            if (previous and previous["source_sha"] == digest and
                    previous["signature"] == signature and not retry_ocr):
                _check_indexed_output(library, connection, previous)
                reused += 1
                continue
            output = _output(library, name)
            if previous is None and output.exists():
                raise ValueError("Refusing to replace an unowned Markdown output")
            pages = _render_document(path, ocr=ocr, language=language)
            # Conversion may take a long time. Do not publish output with
            # the hash of a source that was replaced or edited during it.
            if sha256(path) != digest:
                raise ValueError("Source PDF changed during conversion; retry with stable input")
            text = "# " + Path(name).stem.replace("\n", " ") + "\n\n" + \
                "\n".join(page["markdown"] for page in pages)
            check_markdown(text)
            desired = hashlib.sha256(text.encode("utf-8")).hexdigest()
            with _document_update(library, connection, name, previous, desired):
                connection.execute("DELETE FROM pages WHERE document=?", (name,))
                for page in pages:
                    connection.execute(
                        "INSERT INTO pages VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (name, page["page"], page["markdown"], page["text_total"],
                         page["text_matched"], page["code_total"], page["code_matched"],
                         page["ocr_status"], page["ocr_reason"], page["images"],
                         page["supplement_lines"]),
                    )
                connection.execute("INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?)",
                                   (name, digest, desired, signature, len(pages)))
        for name in old.keys() - current:
            with _document_update(library, connection, name, old[name], None):
                connection.execute("DELETE FROM pages WHERE document=?", (name,))
                connection.execute("DELETE FROM documents WHERE document=?", (name,))
            removed += 1
        summary = _summary(connection)
        summary.update(reused=reused, removed=removed)
        _reports(library, connection, summary)
        return summary
    finally:
        connection.close()


def search_library(library: Path, query: str, limit=5, max_chars=800) -> list[dict]:
    if not 1 <= limit <= 20 or not 80 <= max_chars <= 4000:
        raise ValueError("Search limits: 1..20 hits, 80..4000 characters per hit")
    words = [word for word in query.split() if word]
    if not words or "\x00" in query:
        raise ValueError("A nonempty query without NUL is required")
    connection = _database(checked(library, exists=True, kind="dir"))
    try:
        terms = ["%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                 for word in words]
        sql = "SELECT document,page,markdown FROM pages WHERE " + \
            " AND ".join("markdown LIKE ? ESCAPE '\\'" for _ in terms) + " ORDER BY document,page LIMIT ?"
        result = []
        for row in connection.execute(sql, (*terms, limit)):
            text = row["markdown"]
            # SQLite LIKE folds ASCII case only. Full Unicode casefold can
            # expand characters (e.g. sharp s) and yield offsets into a
            # different string, or select a false match before the SQL hit.
            matches = [re.search(re.escape(word), text, re.IGNORECASE | re.ASCII)
                       for word in words]
            if not all(matches):
                continue
            start = max(0, min(match.start() for match in matches) - max_chars // 4)
            snippet = text[start:start + max_chars]
            result.append(dict(document=row["document"], page=row["page"],
                               text=snippet, truncated=start > 0 or start + max_chars < len(text)))
        return result
    finally:
        connection.close()


def read_pages(library: Path, document: str, pages: list[int], max_chars=12000) -> str:
    if not pages or len(pages) > 10 or any(page < 1 for page in pages):
        raise ValueError("Read 1..10 positive page numbers per request")
    if not 80 <= max_chars <= 40000:
        raise ValueError("Read character limit must be 80..40000")
    connection = _database(checked(library, exists=True, kind="dir"))
    try:
        result = []
        for page in sorted(set(pages)):
            row = connection.execute(
                "SELECT markdown FROM pages WHERE document=? AND page=?", (document, page)
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown document/page: {document}, {page}")
            result.append(row[0])
        text = "\n".join(result)
        warning = "\n\n[输出已截断；请缩小页范围继续读取，不能据此声称已读完整页。]\n"
        return text if len(text) <= max_chars else \
            text[:max_chars - len(warning)] + warning
    finally:
        connection.close()


def _verified_entries(library: Path, connection):
    """Yield the actual validated bytes, not paths to be read again later."""
    _check_orphan_pages(connection)
    for row in connection.execute("SELECT * FROM documents ORDER BY document"):
        _check_owned_output(library, row)
        text = _check_indexed_output(library, connection, row)
        check_markdown(text)
        expected = list(range(1, row["pages"] + 1))
        actual = [int(x) for x in re.findall(r"^## PDF 第 (\d+) 页$", text, re.M)]
        if actual != expected:
            raise ValueError("Missing or repeated page mapping")
        yield _output(library, row["document"]).relative_to(library).as_posix(), text.encode("utf-8")
    for name in REPORTS:
        raw = checked(library / name, exists=True, kind="file").read_bytes()
        check_markdown(raw.decode("utf-8"))
        yield name, raw


def verify_library(library: Path) -> dict:
    library = checked(library, exists=True, kind="dir")
    connection = _database(library)
    try:
        for _ in _verified_entries(library, connection):
            pass
        return _summary(connection)
    finally:
        connection.close()


def export_library(library: Path, destination: Path, *, strict=False) -> dict:
    library = checked(library, exists=True, kind="dir")
    destination = checked(destination)
    if destination.suffix.lower() != ".zip" or destination.is_relative_to(library):
        raise ValueError("Export must be a .zip outside the managed library, inside the package")
    if destination.exists():
        raise FileExistsError("Export destination already exists; choose a new output")
    connection = _database(library)
    try:
        summary = _summary(connection)
        if strict and not summary["strict_ok"]:
            for _ in _verified_entries(library, connection):
                pass
            return summary
        # Use one read-only index snapshot. Compress the same bytes just
        # checked; never read a Markdown path a second time for the archive.
        # Stage under the existing owned scratch root, so a late validation
        # failure cannot leave a misleading destination ZIP.
        with _scratch_directory(ROOT / "tmp", "pdf-export-") as staging:
            staged = staging / "export.zip"
            names = set()
            with zipfile.ZipFile(staged, "x", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, raw in _verified_entries(library, connection):
                    if name in names:
                        raise ValueError("Repeated ZIP entry")
                    names.add(name)
                    if name == "SHA256.md":
                        receipt_sha = hashlib.sha256(raw).hexdigest()
                        checksum_text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n").split(
                            "\n## 最近导出的 ZIP（ZIP 外校验）\n", 1
                        )[0].rstrip() + "\n"
                        raw = checksum_text.encode("utf-8")
                    archive.writestr(name, raw)
            with zipfile.ZipFile(staged) as archive:
                if (archive.testzip() is not None or set(archive.namelist()) != names or
                        len(archive.namelist()) != len(names) or any(
                            Path(name).suffix.lower() != ".md" for name in names)):
                    raise ValueError("ZIP integrity/type validation failed")
                for name in archive.namelist():
                    archive.read(name).decode("utf-8")
            digest = sha256(staged)
            # Exclusive creation preserves an output that arrived during
            # validation. Only the owned scratch directory is cleaned up.
            destination = checked(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            checked(destination.parent, exists=True, kind="dir")
            with staged.open("rb") as source, checked(destination).open("xb") as target:
                shutil.copyfileobj(source, target)
            if sha256(destination) != digest:
                raise ValueError("Exported ZIP digest mismatch")
        _write(library / "SHA256.md", checksum_text +
               "\n## 最近导出的 ZIP（ZIP 外校验）\n\n" +
               "此摘要写在库目录的报告中，不在 ZIP 内自引用。\n\n" +
               fence(f"{digest}  {destination.relative_to(ROOT).as_posix()}"),
               expected_sha=receipt_sha)
        return dict(sha256=digest, files=len(names), **summary)
    finally:
        connection.close()


def main(argv=None) -> int:
    # JSON and Markdown are Unicode outputs. The embedded Windows Python may
    # ignore PYTHONIOENCODING and use the ANSI code page for redirected streams.
    # Preserve interactive console behavior and do not change library imports.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and not stream.isatty() and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--input", type=Path, required=True)
    build.add_argument("--library", type=Path, required=True)
    build.add_argument("--ocr", choices=("none", "auto", "all"), default="none")
    build.add_argument("--language", default="eng")
    build.add_argument("--strict", action="store_true")
    search = commands.add_parser("search")
    search.add_argument("--library", type=Path, required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=5)
    search.add_argument("--max-chars", type=int, default=800)
    read = commands.add_parser("read")
    read.add_argument("--library", type=Path, required=True)
    read.add_argument("--document", required=True)
    read.add_argument("--pages", type=int, nargs="+", required=True)
    read.add_argument("--max-chars", type=int, default=12000)
    export = commands.add_parser("export")
    export.add_argument("--library", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--strict", action="store_true")
    verify = commands.add_parser("verify")
    verify.add_argument("--library", type=Path, required=True)
    verify.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = build_library(args.input, args.library, ocr=args.ocr,
                                   language=args.language, strict=args.strict)
        elif args.command == "search":
            result = search_library(args.library, args.query, args.limit, args.max_chars)
        elif args.command == "read":
            print(read_pages(args.library, args.document, args.pages, args.max_chars))
            return 0
        elif args.command == "export":
            result = export_library(args.library, args.output, strict=args.strict)
        else:
            result = verify_library(args.library)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if getattr(args, "strict", False) and not result["strict_ok"] else 0
    except (OSError, ValueError, RuntimeError, sqlite3.DatabaseError) as error:
        print(f"PDF library: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
