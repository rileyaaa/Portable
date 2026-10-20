---
name: xlsx
description: "Use only when the user explicitly requests creating, reading, reviewing, editing, repairing, or converting an Excel workbook (.xlsx, .xlsm, .xltx) or tabular file (.csv, .tsv). A review may return findings without generating a workbook. A filename mention, discovered file, or loaded skill alone does not authorize file access, tool probes, recalculation, installation, or execution. Do not use for unrelated coding or document tasks merely because they contain tables."
license: Proprietary. LICENSE.txt has complete terms
---

# XLSX creation, editing, and analysis

> **Codex Portable tool rule:** run helpers with `$env:CODEX_PYTHON`; use only package-local Python packages, MarkItDown, and LibreOffice. Report missing dependencies; provision them only when the user's authorization covers that installation. Never run host/global package managers or Office tools as a fallback.

> **Portable paths:** bundled Office helpers derive the package root from their own script location and ignore an inherited `CODEX_INSTALL_DIR`. Keep inputs, outputs, profiles, and temporary files inside that package; do not use `..` or linked paths. Moving the complete package must not redirect work to an old installation. External task files require authorization and a package-local working copy before using these helpers.

## Task activation and scope

- Start only for an explicit spreadsheet task. Loading this skill or finding a workbook does not trigger dependency probes, application startup, downloads, or processing.
- Reading or reviewing does not authorize saving, recalculating, updating external links, or executing macros. For edits, use a task-local output copy and preserve the original unless replacement was requested.
- A user-supplied workbook or template takes precedence over generic formatting guidance. Preserve sheet names/order, named ranges, formulas, styles, charts, validations, print settings, and protection outside the requested changes.
- For `.xlsm`, preserve VBA with `keep_vba=True` when supported; never execute it automatically. `openpyxl` does not preserve every Excel feature. For complex templates or unsupported features, prefer targeted OOXML edits using `scripts/office/safe_ooxml.py`, or report the limitation before a destructive rewrite.
- When no template was supplied and a cached template fits the request, inspect its `artifact-template.json` and preview under `home/plugins/cache/openai-curated-remote/openai-templates/0.1.1/skills/`, then copy its `reference.xlsx` into the task workspace. Do not enable the whole plugin, load every template skill, or invoke external apps to use local assets.
- Use only dependencies needed for this task. No automatic installation or LibreOffice startup.

| Task | Approach |
|---|---|
| **Create** or **edit** with formulas/formatting | `openpyxl` — see gotchas below |
| **Bulk data** in or out | `pandas` (`read_excel`, `to_excel`) |
| **Quick look** at a sheet | `openpyxl` for cells and coordinates or `pandas` for tables; available package-local MarkItDown is optional and omits cell coordinates |
| **Read** a model (formulas *and* values) | two `load_workbook` passes — see gotchas |

> The package's Python toolset includes `openpyxl`, `pandas`, and `XlsxWriter`. MarkItDown and LibreOffice are optional; check the actual component only when the explicit task needs it, and report missing dependencies.

> Script paths below are relative to this skill's directory. Resolve them to absolute paths and invoke helpers with the portable interpreter from a validated package-local task workspace. Do not write deliverables into the skill installation.

## Requirements for every output

- **Professional, legible formatting.** Preserve the supplied template's fonts and number formats. For new workbooks choose readable fonts, including suitable East Asian settings for Chinese content, and consistent widths, row heights, freeze panes, and print areas.
- **No newly introduced formula errors.** Inspect `recalc.py` findings when recalculation is available and fix regressions. To distinguish inherited errors, compare the original formula and cached value; a missing or stale cache is not proof of correctness. If no calculation engine is available, report that formulas were not recalculated.
- **Use formulas, never hardcoded results.** Write `sheet['B10'] = '=SUM(B2:B9)'`, not the Python-computed total. The sheet must recalculate when its inputs change.
- **Follow the user's spec literally.** Exact tab names, exact column headers, and the formula they spelled out. A redesign that computes something else fails, however elegant.
- **Document every assumption and hardcoded number** where the reader will see it — a cell comment, or an adjacent cell at a table's end. Cite a real source when one exists (`Source: Company 10-K, FY2024, Page 45, Revenue Note, [SEC EDGAR URL]`); when the number came from the user, say so plainly.
- **A workbook *you create* for someone to fill in** needs a short legend naming which cells to edit, and one example row of realistic values showing the expected format. Never add such a row to a file you were asked to edit.
- **Editing an existing file: match its conventions exactly.** They override every guideline here. Identify designated input cells and change only the requested ranges and formulas; leave unrelated formulas and layout intact.

## Recalculate changed outputs when a calculation engine is available

Recalculation changes a workbook. Do not run it on the source during a read/review task.
For a created or edited output containing formulas, `openpyxl` does not calculate their
cached values. When package-local LibreOffice is available and supports the workbook's
features, recalculate a working output copy and inspect the result. Without a compatible
engine, check formulas and references structurally and report the calculation gap;
do not claim the workbook was recalculated or overwrite formulas with guessed values.

```powershell
& $env:CODEX_PYTHON scripts/recalc.py output.xlsx [timeout_seconds]   # default 30
```

The helper asks LibreOffice to calculate formulas, the file is **rewritten in place**, and you get JSON:
`status` (`success` | `errors_found`), `total_formulas`, `total_errors`, and an
`error_summary` naming up to 100 cells per error type (`locations_truncated` says how many it
withheld — trust `total_errors`, not the length of the list). Fix what it names and run it
again. **JSON with an `error` key instead of a `status` means nothing was recalculated**, and
only that case exits non-zero — `errors_found` exits 0, so never treat a clean exit as a clean
workbook.

**A green recalc proves your formulas *evaluate*, not that they are *right*.** An off-by-one
range or a reference to the wrong row yields a clean, error-free file with wrong numbers.
Write 2–3 formulas first and check they pull the values you expect, before building out a grid.

**External links need a preservation check.** A formula such as
`='[1]Returns Analysis'!$B$2` refers to a separate workbook via an external-reference index.
Saving with `openpyxl` can discard formula caches, and recalculating without the linked
source can change values or damage links. `recalc.py` refuses detected missing-cache link
risks. Do not bypass that refusal with `--force`, fetch outside files, or replace formulas
with constants without authorization covering that change. Preserve the original and
report the blocked calculation; keeping links is not proof their values are current.

## Choosing formulas that survive verification

Choose formulas for the user's target Excel version and the actual verification engine.
Do not assume a reserved LibreOffice path means a particular version is installed.

- Prefer widely supported functions such as `SUMIFS`, `INDEX`, `MATCH`, `IFERROR`, and `SUMPRODUCT` when they meet the requirement; do not rewrite the user's modern formulas merely to fit an optional preview tool.
- Future functions, including `XLOOKUP`, and dynamic arrays depend on the writer and calculation engine versions. Check required `_xlfn.` prefixes and array metadata for the chosen library; do not assume one prefix works for every function.
- For `SORT`, `FILTER`, `UNIQUE`, `SEQUENCE`, and other spilling formulas, verify the entire expected spill range, dimensions, and values. A valid top-left cell or `total_errors: 0` does not prove a complete result.
- Verify representative inputs, boundary rows, totals, and cross-sheet references against expected results. A formula that evaluates without an error can still reference the wrong cells.

## openpyxl gotchas

- **Reading a model takes two loads.** `data_only=True` yields cached values with the formulas gone; the default yields formula strings with no values. One pass cannot give you both.
- **`data_only=True` is destructive if you save.** That workbook has no formulas left, so saving replaces every one with a literal — permanently.
- **`data_only=True` on a file openpyxl just wrote returns `None` everywhere** — run `recalc.py` first. (A formula whose result is `""` also reads back as `None`.)
- **Merged cells: write the top-left anchor only.** Every other cell in the range is a `MergedCell` whose `.value` is read-only.
- **`.xlsm` loses its macros unless you pass `keep_vba=True`** to `load_workbook`.
- **A sheet name containing a space must be quoted** in a cross-sheet reference: `='Assumptions Inputs'!$B$5`. Unquoted, it evaluates to `#VALUE!`.

## Financial models

Unless the user says otherwise, or the existing file already does something else.

**Color:** blue text (`0,0,255`) for hardcoded inputs and scenario levers · black for formulas ·
green (`0,128,0`) for links to another sheet · red (`255,0,0`) for links to another file ·
yellow fill (`255,255,0`) for key assumptions and cells the user should fill in.

**Numbers:** currency `$#,##0`, with the unit named in the header (`Revenue ($mm)`) · zeros
render as `-`, including in percentages (`$#,##0;($#,##0);-`) · negatives in parentheses ·
percentages `0.0%`, **stored as fractions** (`0.15` renders `15.0%`; storing `15` renders
`1500.0%`) · valuation multiples `0.0x` · years as text (`"2024"`, never `2,024`).

**Structure:** every assumption in its own labeled cell, referenced by the formulas that use it
(`=B5*(1+$B$6)`, never `=B5*1.05`) · formulas consistent across every projection period, since a
lone edited cell mid-row is the commonest silent error · guard denominators that can be zero.

## Dependencies

Bundled Python routes use `openpyxl`, `pandas`, or `XlsxWriter`; OOXML validation requires `lxml` and `defusedxml`. MarkItDown is optional for text extraction. Formula evaluation needs a compatible package-local calculation engine such as LibreOffice; `scripts/office/soffice.py` locates and isolates it but does not install it. Verify only task-relevant dependencies, and report unavailable recalculation or rendering honestly.
