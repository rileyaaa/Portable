---
name: pdf-library
description: Use only when the user explicitly requests searching or reading a collection of PDF manuals, indexing large PDFs, or converting PDFs into a Markdown library. Do not activate for a mere PDF mention, unrelated work, or proactive scanning.
---

# PDF 手册库

仅在用户明确提出相应 PDF 任务后使用。先搜索索引，再读取命中的页；转为 Markdown 本身并不保证节省 token，把所有 Markdown 一次读入上下文仍会很大。一般 PDF 编辑、合并、表单和新建任务使用相邻的 `pdf` 技能。

## 便携边界与依赖

- 用当前包内 `tool/python/python.exe` 和本技能 `scripts/pdf_library.py`。根目录由脚本实际位置确定，忽略旧安装的 `CODEX_INSTALL_DIR`；下面命令均从当前包根运行，无固定盘符。
- 输入、库、临时文件及 ZIP 都必须在当前包内。拒绝 `..`、符号链接、junction、reparse point、硬链接文件及不能在 Windows 保留的源文件名。包外输入须先取得授权，再复制到包内工作目录。
- 提取使用成熟上游 `PyMuPDF4LLM 0.2.9`、`PyMuPDF 1.26.6`、`tabulate 0.9.0`，适配器只负责便携校验、按页审计、索引和交付。版本及来源见 `tool/optional-python-manifest.json`。保留上游许可证；PyMuPDF / PyMuPDF4LLM 的 AGPL / 商业许可需按实际分发方式遵守。
- 不安装 `pymupdf-layout`、模型或驱动，不启动网络服务、MCP 或 OCR。缺依赖时如实说明，不借用宿主安装，也不自动下载。

## 建库与按需阅读

`--input` 可以是一个 PDF，也可以是 PDF 目录；递归保留原目录与文件名，仅将扩展名改为 `.md`。库目录须为空或由此工具创建，且与源目录分开。

```powershell
& .\tool\python\python.exe .\home\skills\pdf-library\scripts\pdf_library.py build --input .\work\manuals --library .\work\manual-library
& .\tool\python\python.exe .\home\skills\pdf-library\scripts\pdf_library.py search --library .\work\manual-library --query "connection_timeout" --limit 5 --max-chars 800
& .\tool\python\python.exe .\home\skills\pdf-library\scripts\pdf_library.py read --library .\work\manual-library --document "database/manual.pdf" --pages 12 13 --max-chars 12000
```

- `search` 按空白分词并要求同页包含全部词；`_`、`%` 等按字面搜索，返回文件名、页码及有限片段。无结果时缩短查询词再试，不直接读完全部手册。
- `read` 每次最多 10 页，默认最多 12,000 字符，输出截断会显式提示。片段不能作为“已经读完整页”的证据；需要时逐页继续。回答引用原 PDF 相对路径和页码。
- 重复 `build` 依据源文件 SHA-256、提取器版本和 OCR 选项跳过未变化文件；删除源文件后清理对应的自有 Markdown。已被用户修改或删除的生成正文会拒绝覆盖，需新建库。不要手改 `_index.sqlite3`。
- `search` / `read` / `verify` 以只读方式打开索引；不需要导入 PDF 引擎或运行 OCR。

## 转换和检查的实际范围

正文存放于 `manuals/`，UTF-8，逐页包含 `## PDF 第 N 页`。PyMuPDF4LLM 提取标题、列表、表格等结构；对缺失的原文字行补入 fenced text，字符计数仍不足则以该页原始文字层回退。只忽略空白核对，不删除下划线、标点、大小写或数字。代码优先保持原字符，复杂表格允许保真文本回退，不能把无法判定的字段关系编造成结构化表格。

库内还生成 `INDEX.md`、`VALIDATION.md`、`OCR.md`、`SHA256.md` 和私有 SQLite 索引。这些是用户本次转换任务的输出，不是新增项目说明文档。报告应始终依据当前实际输入；禁止复制示例或过去任务的手册数、页数、覆盖率作为本次结果。

- **文字层覆盖率**：针对 PyMuPDF 实际提取出的非空白字符计数；原 PDF 的字体映射、阅读顺序、表格语义、截图、矢量文字或空间关系可能仍有误差。
- **代码行覆盖率**：启发式识别的代码行按仅忽略空白的规则检查；不能声称识别了所有代码。
- **人工复核**：工具不会伪造抽查结果。正式交付按任务要求检查代码、复杂表格、跨页内容和图中文字；不足抽样数量则检查全部可用样本并说明。纠正后应使用新的任务工作副本或实现对应转换修正，不要绕过生成正文的哈希保护。
- 源 HTML/XML 或 Markdown 示例保留在代码围栏内；正文不输出 HTML 表格、图片链接、`data:image` 或 `_assets` 资源依赖。页码标题位于围栏外。

## OCR 必须显式选择

默认 `--ocr none`。有图片或文字稀少的页面会列为待检查，绝不将“文字层覆盖完整”描述为截图内容也完整。仅当本次任务确实要求 OCR，且包内已有以下工具，才选择：

```powershell
& .\tool\python\python.exe .\home\skills\pdf-library\scripts\pdf_library.py build --input .\work\manuals --library .\work\manual-library-ocr --ocr auto --language eng+chi_sim --strict
```

使用 `tool/ocr/tesseract/tesseract.exe` 和相邻 `tessdata/<语言>.traineddata`。`auto` 处理有图片或文字稀少的页，`all` 处理每一页；后者可用于检查矢量文字或自动信号漏检。OCR 只追加内容，不覆盖文字层；低置信度词标为 `[疑似：…]`。临时页图仅写入包内 `tmp/pdf-library-ocr/`，完成后清理，不放入交付 ZIP。

缺工具、缺语言数据、执行失败、未处理候选页或低置信度结果都会进入 OCR 报告。`build --strict` / `verify --strict` 返回退出码 **2**，保留已完成结果供检查；不能据此宣布完成严格交付。即使自动严格检查通过，也只表示文字/代码检查与已发现 OCR 问题满足自动门槛，仍需人工视觉检查。OCR 置信度不是正确率证明。

## 验证与纯 Markdown ZIP

```powershell
& .\tool\python\python.exe .\home\skills\pdf-library\scripts\pdf_library.py verify --library .\work\manual-library --strict
& .\tool\python\python.exe .\home\skills\pdf-library\scripts\pdf_library.py export --library .\work\manual-library --output .\work\manuals-markdown.zip --strict
```

导出前检查正文哈希、页映射、围栏及禁用资源，输出只含正文和四份 `.md` 报告，不含 SQLite、PDF、图片或其他附件。ZIP 写完后校验 CRC 和 UTF-8，命令输出 ZIP SHA-256。目标 ZIP 必须是包内的新路径，位于库目录之外；不会覆盖既有交付物。`export --strict` 在检查未完成时拒绝生成 ZIP。普通导出允许交付明确标为未完成的草稿，不能把它标成严格验收通过。
