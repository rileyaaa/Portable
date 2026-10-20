---
name: docx
description: "Use only when the user explicitly requests creating, reading, reviewing, editing, or converting a Word document (.docx) or Word template (.dotx), including formatting, tracked changes, comments, and template-based reports. A filename mention, discovered document, or loaded skill alone does not authorize file access, tool probes, installation, conversion, or execution. Do not use for unrelated coding, PDF, spreadsheet, or presentation tasks."
license: Proprietary. LICENSE.txt has complete terms
---

# DOCX creation, editing, and analysis

> **Codex Portable tool rule:** run Python helpers with `$env:CODEX_PYTHON` and use only package-local Python, Pandoc, LibreOffice, Poppler, Node/npm dependencies, and archive helpers exposed by the portable launcher. Report missing dependencies; provision them only when the user's authorization covers that installation. Never run host/global package managers or Office tools as a fallback.

> **Portable paths:** bundled Office helpers derive the package root from their own script location and ignore an inherited `CODEX_INSTALL_DIR`. Keep inputs, outputs, profiles, and temporary files inside that package; do not use `..` or linked paths. Moving the complete package must not redirect work to an old installation. External task files require authorization and a package-local working copy before using these helpers.

## Task activation and scope

- Start only for an explicit Word task. Loading this skill or finding a document does not trigger dependency probes, application startup, downloads, or processing.
- Reading or reviewing does not authorize rewriting the source, accepting revisions, running macros, or following external links. Create and edit in a task-local working copy; preserve the original unless replacement was requested.
- Use only dependencies needed for the requested operation. Existing environment setup is not proof that an optional renderer or converter is installed. No automatic installation.
- Script paths below are relative to this skill's directory. Resolve them to absolute paths and invoke them from a validated package-local task workspace; do not write deliverables or previews into the skill installation.

A `.docx` is a ZIP archive of XML files. Choose your approach by task:

| Task | Approach |
|---|---|
| **Create** a new document | Prefer bundled `python-docx`; `docx` (npm) is an optional authoring alternative |
| **Edit** an existing document or template | Use `python-docx` for supported changes; use `safe_ooxml.py unpack` → targeted XML edits → `safe_ooxml.py pack` when preservation requires it |
| **Read** content | `python-docx` for paragraphs/tables; inspect relevant OOXML parts for headers, footers, comments, revisions, and embedded content. Pandoc is optional |

## Template-first editing

- A user-supplied template or reference document takes precedence over generic design rules. Inspect page size, margins, sections, styles, numbering, tables, headers/footers, logos, and content controls before choosing an editing method.
- If no template was supplied and a cached template fits the request, inspect that template's `artifact-template.json` and preview under `home/plugins/cache/openai-curated-remote/openai-templates/0.1.1/skills/`, then copy its `reference.docx` into the task workspace. Do not enable the whole plugin, load every template skill, or invoke external apps to use these local assets.
- Preserve style IDs, numbering, section breaks, relationships, fields, and document properties outside the requested changes. Replace the smallest suitable runs: assigning `paragraph.text` discards run formatting. Do not silently accept tracked changes or remove comments.
- For a `.dotx` source, preserve the template when that is the requested output. A new `.docx` based on it needs the correct main-part content type; changing the filename extension alone is not conversion.
- Match the template's typography, including East Asian font settings for Chinese text. Renderer font substitution can change pagination; inspect the rendered result when rendering is available.

## Optional docx-js authoring — gotchas

Use `docx` only when it is available in the package-local Node environment and appropriate for the task. It is not required for the bundled Python workflow and cannot open existing documents. Check the installed version's API before using these patterns; do not install it automatically.

- **Page size defaults to A4.** For US Letter set `page: { size: { width: 12240, height: 15840 } }` (DXA; 1440 = 1″).
- **Landscape:** pass portrait dimensions and `orientation: PageOrientation.LANDSCAPE` — docx-js swaps width/height internally.
- **Tables need dual widths:** set `columnWidths` on the table AND `width` on every cell, both in `WidthType.DXA` (PERCENTAGE breaks in Google Docs). Column widths must sum to the table width.
- **Table shading:** use `ShadingType.CLEAR`, never `SOLID` (renders black).
- **Lists:** never insert `•` literally; use a `numbering` config with `LevelFormat.BULLET`.
- **`ImageRun` requires `type:`** (`"png"`, `"jpg"`, …).
- **`PageBreak` must be inside a `Paragraph`.**
- **Never use `\n`** — use separate `Paragraph` elements.
- **TOC:** headings must use built-in `HeadingLevel.*`; custom heading styles need `outlineLevel` set or they won't appear.
- **Don't use a table as a horizontal rule** — use a paragraph bottom border instead.
- **Dot-leader / right-aligned-on-same-line:** use `PositionalTab` (`alignment: PositionalTabAlignment.RIGHT`, `leader: PositionalTabLeader.DOT`) inside a `TextRun`, not literal `.` or space padding.

## Verify the output

Check content and structure after writing a `.docx`, including requested changes, preserved template elements, missing images, and leftover placeholders. Run the bundled validator for OOXML edits. When package-local LibreOffice and Poppler are available, render and inspect every page. Use a fresh, validated task-owned preview directory so old images cannot be mistaken for the new output:

```powershell
# These variables are validated package-local paths; $Poppler is pdftoppm.exe.
& $env:CODEX_PYTHON (Join-Path $SkillDir 'scripts/office/soffice.py') --headless --convert-to pdf --outdir $PreviewDir $OutputPath
if ($LASTEXITCODE -ne 0) { throw 'Word preview conversion failed' }
$PreviewPdf = Join-Path $PreviewDir ([IO.Path]::GetFileNameWithoutExtension($OutputPath) + '.pdf')
& $Poppler -jpeg -r 120 $PreviewPdf (Join-Path $PreviewDir 'page')
if ($LASTEXITCODE -ne 0) { throw 'Word preview rasterization failed' }
Get-ChildItem -LiteralPath $PreviewDir -Filter 'page-*.jpg' | Select-Object -ExpandProperty FullName
```

Open the images and inspect pagination, clipping, tables, headers/footers, fonts, and spacing; repair defects and regenerate the previews. `pdftoppm` zero-pads page numbers to the width of the page count (`page-01.jpg`…`page-12.jpg`). If rendering dependencies are missing or conversion fails, report visual QA as not performed and state which structural/content checks actually ran. Never describe XML inspection as a rendered preview.

## Editing existing documents

Legacy `.doc` files must be converted first: `& $env:CODEX_PYTHON scripts/office/soffice.py --headless --convert-to docx file.doc`.

```powershell
& $env:CODEX_PYTHON scripts/office/safe_ooxml.py unpack doc.docx unpacked/
& $env:CODEX_PYTHON scripts/merge_runs.py unpacked/   # coalesce fragmented runs so text is findable
# edit unpacked/word/document.xml in place — do NOT reformat or pretty-print
& $env:CODEX_PYTHON scripts/office/safe_ooxml.py pack unpacked/ out.docx
& $env:CODEX_PYTHON scripts/office/validate.py out.docx --original doc.docx   # XSD checks; --auto-repair fixes common issues
# redlining? add --author "<the name you redlined under>" to check every edit is tracked
```

Do not replace `safe_ooxml.py` with raw `unzip`, `Expand-Archive`, `zipfile.extractall`, or `zip`: external OOXML is untrusted, and the helper rejects traversal, Windows ADS/reserved names, symlinks/junctions, Unicode/case collisions, and oversized/compression-bomb entries before extraction.

Word splits text across many `<w:r>` runs (revision ids, spell-check markers), so a phrase you can see in the document often doesn't exist as a contiguous string in the XML. `merge_runs.py` merges adjacent identically-formatted runs in `word/document.xml` without changing content or rendering; it also accepts a `.docx` directly (`& $env:CODEX_PYTHON scripts/merge_runs.py doc.docx -o merged.docx`).

**Tracked changes:** when redlining, validate with `--author "<the name you redlined under>"` (needs `--original`) — it reports any text you changed without a `<w:ins>`/`<w:del>` around it, which is easy to do by accident and invisible in the accepted view. Wrap runs in `<w:ins>`/`<w:del>` with `w:id`, `w:author`, `w:date` attributes. Inside `<w:del>`, the text element is `<w:delText>`, not `<w:t>`. A deleted paragraph mark (`<w:pPr><w:rPr><w:del w:id=".." w:author=".." w:date=".."/></w:rPr></w:pPr>`) means "merge this paragraph into the next" — so deleting a paragraph outright is that plus a `<w:del>` around every run. The `<w:del/>` must come before the rPr's other children; their order is schema-enforced.

To produce a clean copy with all tracked changes accepted: `& $env:CODEX_PYTHON scripts/accept_changes.py in.docx out.docx`.

Accepting a deleted paragraph mark should join that paragraph to the one below it, so a paragraph whose runs are *all* deleted vanishes. Word does this; `accept_changes.py` and `pandoc --track-changes=accept` don't always. Both fail the same way — they strip the deleted text but leave the emptied paragraph behind, which reads as a stray empty bullet when it was auto-numbered:

- `pandoc --track-changes=accept` never joins the paragraphs.
- `accept_changes.py` (LibreOffice) joins them correctly, except when the deleted paragraph is followed by an empty spacer paragraph.

An empty bullet in either view is an artifact of that view, not a defect in the document. Check paragraph deletions in the XML.

## Comments

Comments require six cross-linked files. Use the helper — directory mode when you'll also be editing `document.xml` (saves an unzip/rezip cycle), `.docx`-direct mode otherwise:

```powershell
# Against an already-unpacked directory (preferred when also placing markers)
& $env:CODEX_PYTHON scripts/comment.py unpacked/ "Fees & expenses cap is too low"
& $env:CODEX_PYTHON scripts/comment.py unpacked/ "Agreed" --parent 0

# Against a .docx directly
& $env:CODEX_PYTHON scripts/comment.py contract.docx "This cap is too low" -o annotated.docx
```

The script writes `comments.xml`, `commentsExtended.xml`, `commentsIds.xml`, `commentsExtensible.xml`, the relationships, and the content-type overrides. Comment IDs are auto-assigned. It then prints the `<w:commentRangeStart>`/`<w:commentRangeEnd>`/`<w:commentReference>` snippet to add to `word/document.xml` so the comment anchors to specific text — until you place those markers, the comment exists but is not visible.

## Dependencies

The package's Python toolset includes `python-docx` and `lxml`; the validators additionally require `defusedxml`. Verify the specific import only when the task needs it. Optional routes require package-local `docx` (npm), Pandoc, LibreOffice, or Poppler respectively; their reserved paths do not establish availability. Report the missing component and continue only the checks supported by available dependencies.
