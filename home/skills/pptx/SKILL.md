---
name: pptx
description: "Use only when the user explicitly requests creating, reading, reviewing, editing, or converting a PowerPoint presentation (.pptx) or template (.potx), including slides, charts, layouts, and speaker notes. A filename mention, discovered presentation, or loaded skill alone does not authorize file access, tool probes, installation, conversion, or execution. Do not use for unrelated coding or other document formats."
license: Proprietary. LICENSE.txt has complete terms
---

# PPTX creation, editing, and analysis

> **Codex Portable tool rule:** run Python helpers with `$env:CODEX_PYTHON` and use only package-local Python, Node/npm dependencies, MarkItDown, LibreOffice, Poppler, and archive helpers from the portable launcher. Report missing dependencies; provision them only when the user's authorization covers that installation. Never fall back to host/global package managers or Office tools.

> **Portable paths:** bundled Office helpers derive the package root from their own script location and ignore an inherited `CODEX_INSTALL_DIR`. Keep inputs, outputs, profiles, and temporary files inside that package; do not use `..` or linked paths. Moving the complete package must not redirect work to an old installation. External task files require authorization and a package-local working copy before using these helpers.

## Task activation and scope

- Start only for an explicit presentation task. Loading this skill or finding a deck does not trigger dependency probes, application startup, downloads, or processing.
- Reading or reviewing does not authorize rewriting the source, following external links, or running embedded content. Work on a task-local copy for edits and preserve the original unless replacement was requested.
- The user's template, brand rules, and requested format take precedence over generic styling advice. Inspect the template before choosing the authoring method.
- Use only dependencies needed for this task; no automatic installation. State which operations are unavailable when an optional dependency is absent.

A `.pptx` is a ZIP archive of XML files. Choose your approach by task:

| Task | Approach |
|---|---|
| **Create** a new deck | Bundled `python-pptx` for supported authoring; optional `pptxgenjs` for a task that benefits from it |
| **Edit** an existing deck, or build from a template | `safe_ooxml.py unpack` → edit `ppt/slides/slideN.xml` → `safe_ooxml.py pack` |
| **Read** content | `python-pptx` and relevant OOXML parts for text, tables, charts, notes, and relationships. MarkItDown is optional; `scripts/thumbnail.py` requires rendering dependencies |

## Scripts

Paths are relative to this skill's directory. Resolve them to absolute paths and invoke helpers with the portable interpreter from a validated package-local task workspace. Keep outputs and previews out of the skill installation.

| Script | What it does |
|---|---|
| `scripts/thumbnail.py deck.pptx [prefix]` | Labeled grid of every slide, for picking template layouts. `.pptx` only. Pass `prefix` — it defaults to `thumbnails`, which overwrites the grids of any other deck done in the same directory |
| `scripts/add_slide.py unpacked/ slide2.xml [--after slideN.xml]` | Duplicate a slide (or a `slideLayoutN.xml`) with all the package bookkeeping. Also takes a `.pptx` directly with `-o out.pptx` |
| `scripts/clean.py unpacked/` | Delete slides, media, and rels no longer referenced. Run **after** `<p:sldIdLst>` is final |
| `scripts/office/validate.py deck.pptx [--original src.pptx]` | Schema, relationship, content-type, chart and slide checks; each failure names its fix. Pass `--original` for any template-derived deck — it baselines the schema checks against the template, so the template's own XSD errors don't read as yours |
| `scripts/office/soffice.py --headless --convert-to pdf deck.pptx` | Package-local LibreOffice wrapper with an isolated profile; requires an installed LibreOffice payload |

## Optional pptxgenjs authoring — gotchas

Use `pptxgenjs` only when it is available in the package-local Node environment and appropriate for the task. It is not required for the bundled Python workflow. Check the installed version's API before using these patterns; do not install it automatically.

- **Set `pres.layout` before adding slides.** The default canvas is `LAYOUT_16x9` = **10" × 5.625"**, not 13.3" wide. Coordinates past the edge are written, not clamped — the shape just isn't on the slide. (`LAYOUT_WIDE` is 13.3" × 7.5".)
- **Hex colors: never `#`, never 8 digits.** `color: "FF0000"`. Both `"#FF0000"` and alpha baked into the hex (`"00000020"`) **corrupt the file**. For translucency: `transparency: 0-100` on fills and images, `opacity: 0.0-1.0` on shadows — each is silently ignored on the other.
- **pptxgenjs mutates option objects in place** (converts values to EMU on first use). Never share one `shadow`/options object across two `add*` calls — build a fresh object each time.
- **Shadow `offset` must be ≥ 0** — a negative offset corrupts the file. To cast a shadow upward, use `angle: 270` with a positive offset.
- **`letterSpacing` is silently ignored** — the real option is `charSpacing`.
- **Lists:** `bullet: true` on each item, never a literal `•` (renders double bullets). Set `breakLine: true` on every array item except the last. Space bulleted paragraphs with `paraSpaceAfter`, not `lineSpacing` (huge gaps).
- **One `new pptxgen()` per output file** — never reuse an instance.
- **`rectRadius` only works on `ROUNDED_RECTANGLE`**, not `RECTANGLE`.
- **Gradient fills aren't supported** — use a gradient image as the background instead.
- **Text boxes have built-in internal padding** — set `margin: 0` whenever text must align with a shape, line, or icon at the same x.
- **Speaker notes go in `slide.addNotes("...")`** (plain text, once per slide), never in a text box on the slide.
- **Keep charts native.** Use `addChart()` for everything PowerPoint can chart (pass an array of `{type, data, options}` for combos). For PowerPoint-native features the library doesn't expose (trendlines, error bars), compute the extra series yourself or post-process the generated OOXML — do not fall back to a rendered image. Only chart types PowerPoint has no native form for (Sankey, network, chord) go in as images.
- **Default charts render bare** — no title, no data labels, dated palette. Set `showTitle` + `title`, `showValue: true` + `dataLabelPosition`, `chartColors: [...]` from your palette, and quiet the frame (`catAxisLabelColor`/`valAxisLabelColor`, `valGridLine: { color, size }`, `catGridLine: { style: "none" }`, `showLegend: false` for a single series).
- **On a stacked bar or column chart, `dataLabelPosition` must be `ctr`, `inEnd`, or `inBase`.** `outEnd` **corrupts the file**.
- **A combo series using `secondaryValAxis`/`secondaryCatAxis` needs both `valAxes` and `catAxes` on the chart options, two entries each.** Without them pptxgenjs writes axis *ids* it never declares, and PowerPoint **discards that chart** and reports the file as corrupt. Supplying only `valAxes` is not enough.
- **After `writeFile()`, run `& $env:CODEX_PYTHON scripts/office/validate.py deck.pptx`.** It reports the two chart faults above and the slide-XML defects PowerPoint refuses, and names the fix for each. Fix them in your generator, not by hand-editing the packed XML.
- **Never reorder the children of `<p:presentation>`.** pptxgenjs writes `<p:notesMasterIdLst>` right after `<p:sldIdLst>` and points both masters at one theme part. PowerPoint reads that happily — move the element and the same deck becomes unopenable.
- **Icons:** reuse template assets or available package-local images first. If the optional `react-icons`, `react`, `react-dom`, and `sharp` stack is already available, render SVG through `ReactDOMServer.renderToStaticMarkup`, rasterize at ≥256px, and insert via `addImage({ data: "image/png;base64," + buf.toString("base64") })`. Do not install an icon toolchain merely to decorate a slide.

## Editing existing decks and templates

Inspect the user's template first: aspect ratio, theme fonts/colors, masters/layouts, placeholders, image crops, chart styles, notes, and reading order. Preserve those features outside the requested changes. Map each section to a suitable existing layout and preserve editable text, charts, and tables where possible.

When no template was supplied and a cached template fits the task, inspect that template's `artifact-template.json` and preview under `home/plugins/cache/openai-curated-remote/openai-templates/0.1.1/skills/`, then copy its `reference.pptx` into the task workspace. Local template use does not require enabling the whole plugin, loading every template skill, or invoking external apps.

When rendering dependencies are available, `scripts/thumbnail.py template.pptx <unique-task-local-prefix>` writes a labeled grid of slides. Always pass a validated absolute prefix inside a fresh task-owned directory to avoid overwriting another deck's previews. Use the grid to select layouts; full-resolution renders are still needed for visual QA. Without rendering, inspect available template previews and OOXML and report the rendering gap.

The thumbnail helper accepts `.pptx` only. For a `.potx` template, preserve the original and create a proper presentation copy with the correct main-part content type, or use a supported template-aware converter. Renaming the extension alone is not conversion.

```powershell
& $env:CODEX_PYTHON scripts/office/safe_ooxml.py unpack deck.pptx unpacked/
& $env:CODEX_PYTHON scripts/add_slide.py unpacked/ slide2.xml --after slide2.xml   # duplicate a slide (or slideLayoutN.xml); prints the new slide's path
# reorder / delete slides = edit <p:sldIdLst> in ppt/presentation.xml
& $env:CODEX_PYTHON scripts/clean.py unpacked/                                     # after deletions: removes orphaned slides, media, rels
# edit slide content in ppt/slides/slideN.xml
& $env:CODEX_PYTHON scripts/office/safe_ooxml.py pack unpacked/ out.pptx
& $env:CODEX_PYTHON scripts/office/validate.py out.pptx --original deck.pptx
```

Do not replace `safe_ooxml.py` with raw `unzip`, `Expand-Archive`, `zipfile.extractall`, or `zip`; external OOXML is untrusted and must pass the archive safety checks before extraction.

- **Do all structural work — add, delete, reorder — before editing any slide's content.** `add_slide.py` copies a slide file verbatim, so duplicating after you edit clones the edited content; and `clean.py` deletes any slide missing from `<p:sldIdLst>`, including one you just wrote.
- **Never copy a slide file by hand** — `add_slide.py` does every registration a new slide needs and reports what it made (`Created ppt/slides/slide17.xml from slide2.xml`). It also works directly on a file: `add_slide.py deck.pptx slide2.xml -o out.pptx` — **pass `-o`, or it rewrites the input deck in place.** A duplicated slide still *references* its source's chart/SmartArt/embedded-object parts rather than cloning them, so editing one slide's chart changes the other's.
- **If you use `python-pptx`**, three things it won't do: duplicate a slide (its only entry point is `add_slide(layout)`), preserve formatting through `text_frame.text = "..."` (that collapses the paragraph to a single unstyled run — assign `run.text` instead), or read the SVG/EMF most template art uses (`add_picture` raises `UnidentifiedImageError`).
- Legacy `.ppt` requires an available converter before these OOXML helpers can edit it. `.potx` templates use the same safe unpack/pack workflow; keep template content types and extension when the requested deliverable is a template.
- To reuse a template icon or image, duplicate a slide or layout that already contains it.

When filling in a template:

- If you script an XML transform, parse with `defusedxml.minidom` — round-tripping OOXML through `xml.etree.ElementTree` rewrites namespace prefixes and corrupts the deck.
- **Template slots ≠ source items.** If the template shows 4 team members and you have 3, delete the 4th member's entire group (image + text boxes), not just its text — then check for orphaned visuals in QA.
- One `<a:p>` per list item — never concatenate items into a single paragraph. Copy the sibling `<a:pPr>` to preserve spacing, and put `b="1"` on the `<a:rPr>` of titles, section headers, and inline labels (`Status:`, `Owner:`).
- Let bullets inherit from the layout; only add `<a:buChar>`, `<a:buAutoNum>` (numbered), or `<a:buNone>` to override — never a literal `•` in the text.
- Text with leading or trailing spaces needs `xml:space="preserve"` on its `<a:t>`.

## Design and narrative

Start with the audience, purpose, evidence, and decision the deck supports. Build a clear sequence: context/problem → supporting evidence or options → recommendation → next steps, adapting it to the user's material. Give each slide one takeaway and use a message title when appropriate. Preserve source facts, units, dates, uncertainty, and citations; never invent data to fill a layout.

The user's template overrides the suggestions below. Good design makes the message easier to understand: choose diagrams for relationships, charts for comparisons, images for context, and concise text when text is the clearest form. Do not add decorative content just to fill space.

### Before Starting

- **Choose a coherent palette:** use the user's brand or template first; otherwise choose a dominant neutral/base, supporting tone, and limited accent with clear contrast.
- **Establish hierarchy:** titles, evidence, annotations, and sources should have consistent visual roles.
- **Use contrast deliberately:** a dark opening or section divider can work, but a consistent light deck is also valid.
- **Repeat a visual system:** align margins, spacing, shape styles, chart colors, and emphasis across slides while varying layouts to suit content.

### Color Palettes

When no brand or template palette was specified, these are optional starting points:

| Theme | Primary | Secondary | Accent |
|-------|---------|-----------|--------|
| **Midnight Executive** | `1E2761` (navy) | `CADCFC` (ice blue) | `FFFFFF` (white) |
| **Forest & Moss** | `2C5F2D` (forest) | `97BC62` (moss) | `F5F5F5` (cream) |
| **Coral Energy** | `F96167` (coral) | `F9E795` (gold) | `2F3C7E` (navy) |
| **Warm Terracotta** | `B85042` (terracotta) | `E7E8D1` (sand) | `A7BEAE` (sage) |
| **Ocean Gradient** | `065A82` (deep blue) | `1C7293` (teal) | `21295C` (midnight) |
| **Charcoal Minimal** | `36454F` (charcoal) | `F2F2F2` (off-white) | `212121` (black) |
| **Teal Trust** | `028090` (teal) | `00A896` (seafoam) | `02C39A` (mint) |
| **Berry & Cream** | `6D2E46` (berry) | `A26769` (dusty rose) | `ECE2D0` (cream) |
| **Sage Calm** | `84B59F` (sage) | `69A297` (eucalyptus) | `50808E` (slate) |
| **Cherry Bold** | `990011` (cherry) | `FCF6F5` (off-white) | `2F3C7E` (navy) |

### For Each Slide

Choose a visual only when it explains the slide's message. A deliberate title, quotation, agenda, or conclusion slide can use text alone.

**Layout options:**
- Two-column (text left, illustration on right)
- Icon + text rows (icon in colored circle, bold header, description below)
- 2x2 or 2x3 grid (image on one side, grid of content blocks on other)
- Half-bleed image (full left or right side) with content overlay

**Data display:**
- Large stat callouts (big numbers 60-72pt with small labels below)
- Comparison columns (before/after, pros/cons, side-by-side options)
- Timeline or process flow (numbered steps, arrows)

**Visual polish:**
- Icons in small colored circles next to section headers
- Italic accent text for key stats or taglines

### Typography

Keep template fonts unless the user requests a change. Check the fonts actually available to the chosen renderer when rendering the task; a font family name does not guarantee it is installed or metrically identical on another computer. For Chinese or mixed-language slides, preserve East Asian font settings and check punctuation and wrapping.

LibreOffice may substitute fonts and differ from the recipient's PowerPoint. Leave sensible layout slack, inspect rendered text fit, and disclose substitution or unverified target rendering. Do not silently install host fonts or claim that a fixed font list guarantees fidelity.

| Element | Size |
|---------|------|
| Slide title | 36-44pt bold |
| Section header | 20-24pt bold |
| Body text | 18-24pt; split dense content instead of shrinking it |
| Captions and sources | 12-14pt, legible at presentation size |

### Spacing

- 0.5" minimum margins
- 0.3-0.5" between content blocks
- Leave breathing room—don't fill every inch

### Avoid (Common Mistakes)

- **Don't repeat the same layout** — vary columns, cards, and callouts across slides
- **Don't center body text** — left-align paragraphs and lists; center only titles
- **Keep a clear size hierarchy** — use the template's hierarchy or distinguish titles, body text, and sources consistently
- **Keep colors purposeful** — preserve brand colors and use accents to explain meaning
- **Don't mix spacing randomly** — choose 0.3" or 0.5" gaps and use consistently
- **Don't style one slide and leave the rest plain** — commit fully or keep it simple throughout
- **Don't force decorative visuals** — avoid repeating a dense title-and-bullets layout when a chart or diagram explains the content better
- **Don't forget text box padding** — when aligning lines or shapes with text edges, set `margin: 0` on the text box or offset the shape to account for padding
- **Don't use low-contrast elements** — icons AND text need strong contrast against the background; avoid light text on light backgrounds or dark text on dark backgrounds
- **Avoid decoration without a purpose** — preserve the supplied template's lines, bars, and motifs; for new decks, use whitespace and restrained emphasis
- **Don't ship text that overflows its shape** — shorten carefully, split across slides, or enlarge the container before reducing text below a legible size

## QA (Required)

Perform content, structural, and visual checks appropriate to the requested change. Fix found defects and recheck affected slides; master/theme changes can affect the whole deck. Report failed or skipped checks and missing dependencies accurately.

### Content QA

Read the saved output with `python-pptx` and relevant OOXML parts; an available package-local MarkItDown is an optional text dump. Check slide order, requested content, tables, notes, labels, numbers, units, citations, and chart data. Search for leftover placeholders such as `XXX`, `Lorem ipsum`, `TODO`, and `[insert ...]`, then inspect matches in context. A text dump alone does not verify layout or embedded charts.

### File QA (required)

```powershell
& $env:CODEX_PYTHON scripts/office/validate.py output.pptx                      # built from scratch
& $env:CODEX_PYTHON scripts/office/validate.py output.pptx --original src.pptx  # built from a template
```

**If the deck came from a template, always pass `--original`.** A template may itself
contain parts the XSD rejects, so a bare run can report failures you never caused — and
a genuine regression can hide among them. `--original` baselines
the schema and slide checks against the template, suppressing errors it already had.
The structural checks — relationships, content types, charts — ignore `--original` and
report template-inherited problems either way, so read those on their own merits.

Some generator defects, including invalid chart axis references or label positions, can
survive a successful `python-pptx` load or LibreOffice render. Inspect the validator's
findings as well, fix generator defects at the source, and rebuild.

### Visual QA

When package-local rendering dependencies are available, convert the slides to images (see [Converting to Images](#converting-to-images)) and inspect every slide. If dependencies are missing or rendering fails, report visual QA as not performed; never claim that XML inspection or a template's old preview is a render of the new deck. User-visible defects to look for:

- **Text overflow or text cut off at a box or slide boundary — check this first.** Font substitution makes target rendering uncertain even when a preview fits; identify that limitation.
- Overlapping elements (text through shapes, lines through words, stacked elements)
- Source citations or footers colliding with content above
- Elements too close (< 0.3" gaps) or cards/sections nearly touching
- Uneven gaps (large empty area in one place, cramped in another)
- Insufficient margin from slide edges (< 0.5")
- Columns or similar elements not aligned consistently
- Low-contrast text (e.g., light gray text on cream-colored background)
- Template decoration mispositioned after text replacement — e.g., a title underline positioned for one line, but the replaced title wrapped to two
- Low-contrast icons (e.g., dark icons on dark backgrounds without a contrasting circle)
- Text boxes too narrow causing excessive wrapping
- Leftover placeholder content

## Converting to Images

Use a fresh, validated task-owned preview directory for each render so stale pages cannot enter QA:

```powershell
# These variables are validated package-local paths; $Poppler is pdftoppm.exe.
& $env:CODEX_PYTHON (Join-Path $SkillDir 'scripts/office/soffice.py') --headless --convert-to pdf --outdir $PreviewDir $OutputPath
if ($LASTEXITCODE -ne 0) { throw 'Slide preview conversion failed' }
$PreviewPdf = Join-Path $PreviewDir ([IO.Path]::GetFileNameWithoutExtension($OutputPath) + '.pdf')
& $Poppler -jpeg -r 150 $PreviewPdf (Join-Path $PreviewDir 'slide')
if ($LASTEXITCODE -ne 0) { throw 'Slide preview rasterization failed' }
Get-ChildItem -LiteralPath $PreviewDir -Filter 'slide-*.jpg' | Select-Object -ExpandProperty FullName
```

**Pass the absolute paths printed above directly to the view tool.** `pdftoppm` zero-pads based on page count: `slide-1.jpg` for decks under 10 pages, `slide-01.jpg` for 10-99, `slide-001.jpg` for 100+.

**After fixes, regenerate the PDF and images from the edited `.pptx`.** Clean up only previews created by this task, within its validated directory.

## Dependencies

The package's Python toolset includes `python-pptx`, `Pillow`, and `lxml`; validation and thumbnail helpers also require `defusedxml`. Optional routes require package-local `pptxgenjs`, MarkItDown, LibreOffice, or Poppler respectively. Check only the components needed by the explicit task; reserved paths and configuration do not prove that a payload is installed. Thumbnails and full slide rendering need working rendering dependencies.
