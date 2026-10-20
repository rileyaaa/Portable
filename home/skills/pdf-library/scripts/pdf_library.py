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
import stat
import subprocess
import sys
import tempfile
import unicodedata
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


def _write(path: Path, text: str) -> None:
    path = checked(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    checked(path.parent, exists=True, kind="dir")
    handle, temporary = tempfile.mkstemp(prefix=".pdf-library-", dir=path.parent)
    temp = Path(temporary)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        checked(path)
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
    connection = sqlite3.connect(db) if create else \
        sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA temp_store=MEMORY")
    identity = connection.execute("PRAGMA application_id").fetchone()[0]
    if identity not in ((0, APPLICATION_ID) if create else (APPLICATION_ID,)):
        connection.close()
        raise ValueError("Not a PDF library database")
    if not create:
        connection.execute("PRAGMA query_only=ON")
        return connection
    connection.execute("PRAGMA journal_mode=DELETE")
    if identity == 0 and connection.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table'"
    ).fetchone()[0]:
        connection.close()
        raise ValueError("Refusing an unrelated SQLite database")
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
    """)
    connection.commit()
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
    temporary = _safety.prepare_output_dir(ROOT / "tmp/pdf-library-ocr")
    with tempfile.TemporaryDirectory(prefix="page-", dir=temporary) as dirname:
        task = Path(dirname)
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
        old = {row["document"]: row for row in connection.execute("SELECT * FROM documents")}
        for row in old.values():
            _check_owned_output(library, row)
        current = {name for name, _ in items}
        for name, path in items:
            digest = sha256(path)
            previous = old.get(name)
            if previous and previous["source_sha"] == digest and previous["signature"] == signature:
                reused += 1
                continue
            output = _output(library, name)
            if previous is None and output.exists():
                raise ValueError("Refusing to replace an unowned Markdown output")
            pages = _render_document(path, ocr=ocr, language=language)
            text = "# " + Path(name).stem.replace("\n", " ") + "\n\n" + \
                "\n".join(page["markdown"] for page in pages)
            check_markdown(text)
            _write(output, text)
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
                               (name, digest, sha256(output), signature, len(pages)))
            connection.commit()
        for name in old.keys() - current:
            _output(library, name).unlink()
            connection.execute("DELETE FROM pages WHERE document=?", (name,))
            connection.execute("DELETE FROM documents WHERE document=?", (name,))
            removed += 1
        connection.commit()
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
    if not words:
        raise ValueError("A nonempty query is required")
    connection = _database(checked(library, exists=True, kind="dir"))
    try:
        terms = ["%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
                 for word in words]
        sql = "SELECT document,page,markdown FROM pages WHERE " + \
            " AND ".join("markdown LIKE ? ESCAPE '\\'" for _ in terms) + " ORDER BY document,page LIMIT ?"
        result = []
        for row in connection.execute(sql, (*terms, limit)):
            text = row["markdown"]
            hits = [text.casefold().find(word.casefold()) for word in words]
            start = max(0, min(hit for hit in hits if hit >= 0) - max_chars // 4)
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


def verify_library(library: Path) -> dict:
    library = checked(library, exists=True, kind="dir")
    connection = _database(library)
    try:
        for row in connection.execute("SELECT * FROM documents"):
            _check_owned_output(library, row)
            text = _output(library, row["document"]).read_text(encoding="utf-8")
            check_markdown(text)
            expected = list(range(1, row["pages"] + 1))
            actual = [int(x) for x in re.findall(r"^## PDF 第 (\d+) 页$", text, re.M)]
            if actual != expected:
                raise ValueError("Missing or repeated page mapping")
        for name in REPORTS:
            check_markdown(checked(library / name, exists=True, kind="file").read_text(encoding="utf-8"))
        return _summary(connection)
    finally:
        connection.close()


def export_library(library: Path, destination: Path) -> dict:
    library = checked(library, exists=True, kind="dir")
    destination = checked(destination)
    if destination.suffix.lower() != ".zip" or destination.is_relative_to(library):
        raise ValueError("Export must be a .zip outside the managed library, inside the package")
    if destination.exists():
        raise FileExistsError("Export destination already exists; choose a new output")
    summary = verify_library(library)
    connection = _database(library)
    try:
        files = [_output(library, row["document"])
                 for row in connection.execute("SELECT document FROM documents ORDER BY document")]
        files += [checked(library / name, exists=True, kind="file") for name in REPORTS]
        destination.parent.mkdir(parents=True, exist_ok=True)
        checked(destination.parent, exists=True, kind="dir")
        checksum_report = library / "SHA256.md"
        # A ZIP cannot contain its own final digest. Keep the latest ZIP receipt
        # in the existing external Markdown report, not a new non-MD artifact.
        checksum_text = checksum_report.read_text(encoding="utf-8").split(
            "\n## 最近导出的 ZIP（ZIP 外校验）\n", 1
        )[0].rstrip() + "\n"
        with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                if path == checksum_report:
                    archive.writestr("SHA256.md", checksum_text.encode("utf-8"))
                else:
                    archive.write(path, arcname=path.relative_to(library).as_posix())
        with zipfile.ZipFile(destination) as archive:
            if archive.testzip() is not None or any(
                Path(info.filename).suffix.lower() != ".md" for info in archive.infolist()
            ):
                raise ValueError("ZIP integrity/type validation failed")
            for name in archive.namelist():
                archive.read(name).decode("utf-8")
        digest = sha256(destination)
        _write(checksum_report, checksum_text +
               "\n## 最近导出的 ZIP（ZIP 外校验）\n\n" +
               "此摘要写在库目录的报告中，不在 ZIP 内自引用。\n\n" +
               fence(f"{digest}  {destination.relative_to(ROOT).as_posix()}"))
        return dict(sha256=digest, files=len(files), **summary)
    finally:
        connection.close()


def main(argv=None) -> int:
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
            audit = verify_library(args.library)
            if args.strict and not audit["strict_ok"]:
                print(json.dumps(audit, ensure_ascii=False, indent=2))
                return 2
            result = export_library(args.library, args.output)
        else:
            result = verify_library(args.library)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if getattr(args, "strict", False) and not result["strict_ok"] else 0
    except (OSError, ValueError, RuntimeError, sqlite3.DatabaseError) as error:
        print(f"PDF library: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
