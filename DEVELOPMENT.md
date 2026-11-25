# 开发与维护记录

## 2026-11-25：独立候选合批与首因记录

[45588115342](https://github.com/rileyaaa/Portable/actions/runs/45588115342) 的源代码 62 项及旧版 HTTP/Office 回归通过；在旧 urllib3 官方 wheel 内容校验时，因为已随原包安装的 `urllib3/contrib/emscripten/emscripten_fetch_worker.js` 不属于原 Python 后缀列表而停止，尚未替换载荷。仓库、官方 2.7.0 与 2.8.0 标签该文件 Git blob 均为 `faf141e1fa4113a0c14480d1681ddecb9678ced4`，故仅增加这一固定路径及固定 blob 检查，不开放其他 JS 或改变工件验证边界。

将 HTTP、tzdata 2026.2→2026.6、XlsxWriter 3.2.9→3.3.4 分开进行工件/旧新真实消费者验收，失败组还原自身路径，其他组独立继续；成功候选统一经过现有 Windows 原生门禁方可推送。Excel 旧版日期序列、数组公式文本以及 SINGLE 公式替换有可复现错误；时区数据按 IANA 2026f 检查历史/当前实际偏移，不调用宿主时区数据。XlsxWriter 兼顾已安装的 VBA 提取脚本首行固定旧盘符，不新增宏执行、CLI 或功能。仅将官方稳定版作为候选，不声称升级已经成功。

浏览器：上游 Playwright 1.65.1 稳定标签 bbd948344ea9a60bf1e6f125c02ca99b2b51593b 已包含 MCP createConnection 和 stdio transport；可作为旧 standalone alpha 配套的替代路线，仍需实际 npm 工件、配套 Chromium 159.0.8154.6/revision 1255 及既有过滤、隔离、搬迁验收，不能直接绕过便携桥接层或独立替换其中之一。

## 2026-11-25：第六组 HTTP 候选首轮基线测试纠正

Windows AC #45587545731 在替换任何 wheel 之前停止：旧 urllib3 2.7.0 的 `response.stream(11)` 直接读取 gzip 编码字节，原探针却要求解压后的内容。独立用旧 2.7.0 回环 HTTP 复现；显式 `decode_content=True` 后压缩流、HTTP 代理认证、重定向、requests、httpx、AnyIO 同步/异步测试通过；另保留显式 `decode_content=False` 的原始 gzip 字节及独立解压校验。此前 Windows 已通过 SSH 17、PDF 索引 23、PDF 15、登录 HTTP 7 项源码回归。此次只纠正探针契约和一次性入口，不改产品 HTTP 实现，不放宽依赖归属或原生门禁，不重跑无关旧候选。候选未进入安装，urllib3/AnyIO 仍为原版。

## 2026-11-25：第五组既有 SSH 与 PDF 检索缺陷修正（源码候选）

固定 0.172.0 及既有启动变量、模式、工具版本和权限不变。包内实际 Paramiko 5.1.0 client.py 的 _key_from_filepath 会在禁用 agent/自动密钥搜索时仍查找相邻 -cert.pub，显式证书路径又会推导私钥；原入口只检查一个路径。现按固定版本实际推导规则，在构建 SSHClient 前检查另一条路径及完整祖先、普通单链接；保留正常证书/私钥、显式授权与主机指纹策略。远端 exec 在持续读 stdout/stderr 时也检查既有截止时间，不改输出限额和退出码。PDF 索引原 SQLite LIKE 筛选后用全文 casefold 的位置截取原文本，含大量 ß 等展开字符的手册可返回空片段或错误位置；保持 SQL 字面量及 ASCII 大小写匹配规则，用原字符串坐标截取，拒绝 NUL 查询。新增合成文件/通道和 SQLite 索引回归；未访问任何真实 SSH 服务器。Windows 实际验收待本组门禁，未测设备、真实账号、外部网络、Office 渲染及重算不视为通过。仅修正文档与实际 SSH 依赖树不一致的当前说明，不恢复预览组件、不新增功能、不发布。

## 2026-11-25：第四组 typing_extensions 独立稳定更新

仅将已有纯 Python 单模块 typing_extensions 4.15.0 更新到 4.16.0（PSF-2.0，Python >=3.9）；固定 Python 3.14.10、pip/certifi、Node/npm/Corepack、Codex/Host、浏览器/MCP、其他 48 个已装发行包和原 CLI/权限不动。官方 PyPI wheel SHA-256 481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8，旧 wheel f0fa19c6845758ab08074a0cfa8b7aecb71c999ca73d62883bc25cc018c4e548；PyPI 发布证明标明官方仓库提交 f29cd28d8ed7642cafb1d18daf5aa41be6a5c0aa。本轮实际核对 wheel 摘要、RECORD、许可证与固定上游模块 Git blob ced78373258ef307c9a94ef15286e6da359e7a80，不声称本地独立验证了 Sigstore 证明。旧包 INSTALLER 为 uv，仍只使用现有固定 pip 在独占目标进行 hash-only、no-index/no-deps/no-compile 安装；不增 console_script、脚本、native binary 或其他依赖。实际同 runner 新旧版本公共导出、TypedDict/Protocol、已有 HTTP 同步异步回环、DOCX/PPTX/XLSX 中文路径创建读回及完整 Windows 原生门禁；不代表真实网络、账号、SSH、用户设备、Office 渲染或公式重算。Python 3.14 中 no_type_check_decorator 仍保留；不启用上游新增 API 作为项目功能。XlsxWriter 新版另有历史 vendor vba_extract.py 变化，暂不混入；SSH 候选边界不变。回退仅恢复该模块、dist-info、输入/锁及本组测试/说明。

Windows AC: https://github.com/rileyaaa/Portable/actions/runs/45579383659

## 2026-11-25：第三组 npm / Corepack 来源审计完成，保留现版

[Windows AC 45577656242](https://github.com/rileyaaa/Portable/actions/runs/45577656242)（job 139079469743，审计提交 5b8fea2b1bddc482e380a70906b577dc3b1901ba）成功是只读来源与受控离线探针通过，不是升级安装或完整原生回归通过。固定 Node 26.13.1 官方 Windows x64 ZIP SHA-256 e2edda75bfb089654705cf65a13b58933bfd5f57148e8ebda916f58a2474f1f7，包内 node.exe 与官方字节一致；实际 ZIP node_modules 只有 npm，未分发 Corepack。npm 11.20.0 的 1926 个跟踪文件全部与 Git 原始 blob 一致，与官方 Node ZIP 1925 个逐字节相同及 1 个已审核空 .npmrc；无未知来源、无 ZIP 省略文件。与 Registry 11.20.0 同版本 tarball（SHA-256 d1a92f40e6c407b84c3a00c3cf978a10b24fd42f153c527e2016cef7bb34a483）对照为 16 精确、1872 严格换行等价、1 空 .npmrc、37 内容差异，另有 18 个仅 Registry 存在的测试文件。原 npm-completion.md 的 Git/工作树/Node ZIP 均为 943 字节、36 CRLF、SHA-256 04237f3b0bf93e69b73c54e0c947d3b0332c216d45f7639770747f2e68ff143a；Registry 为 908 字节 LF、SHA-256 74f866ad8a9b501e4a21e055b2f183da32940190c3e088e86abb370192ef974c，多一个行尾空格，不是 Git 属性造成。其他真实内容差异包括 tar/minimatch/sigstore/lru-cache/diff 等 JS 运行依赖、文档及许可文件，逐项路径见 AC 日志。npm 11.21.3 官方 Artistic-2.0 工件 SHA-256 ee5fc68e724c4bdba38db9d96d9c661d4e736e4be7001ae44d2fbbaa52159514、Registry ECDSA 签名与 SHA-512/SHA-1 均通过；未获得等价替换依据，不以忽略空白或扩大白名单强行覆盖 Node 官方 bundle，保留 11.20.0。

Corepack 0.35.0 独立官方 Registry tarball（MIT）SHA-256 f62535fc7be1f77e4b12cd1e420b8542b8e895cbb14178926963a41a9232a4fe，54 个文件与 Git 工作树一致、与官方工件 15 精确及 39 严格换行等价，无未知/省略。新版 0.36.0 官方 tarball SHA-256 9128cfe26aee0c99f4fc68c15c6b8b12309a68be0de2c012cdfea2a463cb722f，Registry 签名和摘要通过；同场仅在合成包内目录执行版本与禁止联网的 pack 探针，两版退出 1 且未生成归档，旧版不加载合成父项目 .corepack.env，新版加载。上游发现行为改变，现有 vendor Corepack 入口并非六份 npm/npx 受管 shim；不增加包装、启用其他包管理器或修改隔离/默认功能，保留 0.35.0。前两次来源失败（45575268947、45576439406）已由此次四方审计及独立 Corepack 来源确认解释，不再重跑；没有候选提交或生产 payload 变更。清理本次一次性 workflow，保留原提交、日志及正式 main/tag/Release。下一组先选现有纯 Python、低耦合的稳定文档依赖；任何替换仍须通过固定 wheel、许可、闭包、实际功能及完整 Windows 原生门禁。

## 2026-11-25：第二组 pip / certifi 暂缓，保留原固定版本

仅在 dev/stable-tool-refresh 进行候选验证，实际跟踪的 pip 26.1.2、certifi 2026.5.20、Python 3.14.10 及依赖锁均未替换。目标 pip 26.3 / certifi 2026.11.20（MIT / MPL-2.0）官方 wheel 固定 SHA-256 分别为 f3b60b20ffaadd4415ed7957212a38ac63fa4c5fa375bd0f4a797777940fad13 与 7422df25243767b9877031a2248cb14d09ddac9beee846f4cef3d5c9191d488f。原入口 main→cli 是上游正式安全变更；新旧三个 CMD 的普通 wheel 安装、自更新拒绝、官方 python -m pip 的暂存安装、CA/锁/RECORD 与依赖闭包已取得真实对照。原生配置隔离的 kinds→Kind 仅是测试内部 API 变化；[AC 45565688956](https://github.com/rileyaaa/Portable/actions/runs/45565688956) 两版真实 config list（合成配置发现位置）四组对照、PowerShell 缓存隔离、候选范围、原生常用/未知模型、中文搬迁、常用浏览器只读均通过。该候选本地提交 8a639f34 未推送，YOLO 浏览器调用出现 Script running with cell ID 1、write_stdin Unknown process id，合成 Responses 未取得任务完成标记；不能据此认定新版 pip 导致浏览器回归或仅为夹具问题。该次后续 MCP、Office/PDF、发行门禁未执行。

修正候选夹具编辑锚点后，[AC 45571984323](https://github.com/rileyaaa/Portable/actions/runs/45571984323) 最终在暂存脚本第 515 行将含中文的诊断输出写至 cp1252 stdout 时发生 UnicodeEncodeError，冻结版实际浏览器对照未完成、候选未推送。按用户阶段边界停止本批，不重跑、不宣称已通过完整兼容性验收；不修改生产包装器、pip 保护、固定 Codex/Host、权限或浏览器。移除已用完的一次性 workflow，原验证提交与 Actions 历史保留。以后如恢复本组，先修 CI 输出编码并完成同场冻结/候选浏览器及剩余完整原生门禁，不将部分通过当作完整通过。下一独立组先审核 npm/Corepack 稳定工件及其与现有包装器的兼容性。正式 main/tag/Release 不变。

## 2026-11-25：稳定工具更新开发分支，第一组独立 ripgrep

本组只更新 `tool/bin/rg.exe` 15.2.0 → 16.0.0，官方 Windows x64 MSVC ZIP 通过固定大小和 SHA-256 核验，原 MIT/Unlicense 许可文本逐项对比；`codex-path/rg.exe` 仍由 0.172.0 运行清单固定，不修改 Codex/Host、启动器、权限、PATH 顺序或模式副本。`tool/cli-versions.json` 与既有 CLI verifier 同步固定新工件；Linux 16.0.0 仅记录官方工件摘要，未执行 Linux 新版。回退应整体恢复本组的独立 EXE、清单、verifier 和测试/说明，不恢复或改动 main/tag/Release。Windows 门禁通过才推送实际候选提交，合成 Responses 触发真实 BAT/Codex 和命令，不代表真实在线账号或模型决策。工具全量元数据盘点、实际常用/YOLO、中文搬迁、浏览器/MCP、Office/PDF、原生签名/文件及发行输入结果见本次 AC；网络元数据失败项保持未确认，不据此升级。保留已知 ADB 宿主路径、PowerShell 启动模块路径限制及未测真实设备/交互审批/Office 重算。新版 MCP 0.0.86 仍固定 alpha Playwright，暂不升级该组；Python 3.15 涉及 ABI，暂不跨小版本；优先随后审核 Python pip/certifi 安全修复兼容组，再审核 npm 配套依赖。当前实际 dist-info 与旧 SSH 说明不完全一致，SSH 真实功能及说明另行验证，不在本组冒称已验。

[Windows AC](https://github.com/rileyaaa/Portable/actions/runs/45553475532), rg.exe SHA-256: a140ac0ec5346e6aa59e13bdb09f001237632bafcede54c13b885e08efcecf64.

原 AC #45551379691 在 Windows write_text 默认 CRLF 上误断言 LF。此次同一 Windows runner 对固定 15.2.0/16.0.0 原样复现旧断言，要求两版在 CRLF 和显式 LF 夹具均逐字节返回正确文本，保留中文、忽略规则、JSON、路径和退出码门禁；真实常用/YOLO 测试继续使用同一对照。

## 2026-11-25：0.172.0 现有功能维护最终验收与收尾（暂用终稿）

[Windows 45535807535](https://github.com/rileyaaa/Portable/actions/runs/45535807535)（job 138941979770，attempt 1）全部成功，验证提交 `c596090712e02a51881161d11acc93dcc3b29afb`，Git tree `b6895c1699de9d2ea41bfe39d28e1aeb16455f23`；收尾前 main 提交与 tree 完全相同。原始日志确认在中文搬迁目录 `Relocated 便携 Portable` 经真实 BAT/Codex 0.172.0 常用模式（workspace-write、on-request、命令网络关闭、默认未启用浏览器 MCP）、包内 Python 3.14 执行；合成 Responses 仅负责发出工具调用，不代表真实在线模型自主决策。原生命令实际退出成功，10 个本地 Skills 进入模型上下文。Python isolated/safe_path/ignore_environment=1，启动路径仅包内三项，_pth 字节未变。三份 Office validate.py 均通过实际绝对路径独立进程执行：DOCX 原文及修订基线通过、非法核心属性实际拒绝且不因 validator unavailable 失败，PPTX 原文基线通过，XLSX 原有明确无 XSD 校验分支和清理通过；三种文件均实际创建、读回，XLSX 仅保留公式未重算。校验输入未改、临时目录清理通过；PDF 真实创建、提取、页渲染及手册库重复 build/search/read/verify/export、只读索引和 ZIP 摘要核对全部通过。PDF 单元 37 项、Office 边界/离线 XSD 22 项、发行输入检查通过。LibreOffice profile 只模拟外部进程，实际临时目录创建/清理经过受限进程验证，不代表 LibreOffice 已安装或实际渲染、重算、宏执行通过。

既有 [Windows 45398279081](https://github.com/rileyaaa/Portable/actions/runs/45398279081) 核心工具、常用模式沙箱写入边界、Unicode、Header、浏览器/MCP、模式副本及发行输入均成功；[Windows 45408248526](https://github.com/rileyaaa/Portable/actions/runs/45408248526) PDF 专项成功。已核对 45398279081 已验 tree 与本次已验 tree 的完整 Git blob 清单，固定工具、启动器、模式 env、副本及原两个工作流未变；此后生产修改限 Office/PDF 相关，最终专项通过。不重跑已通过项目；仅随本记录移除一次性 `.github/workflows/native-documents-0172.yml`，不动 `import-round12.yml` 或 `release.yml`，不触发发布、不生成或上传 Artifact。本轮源码候选可以作为暂用终稿，可以收尾；并非正式客户 ZIP 已发布或全部功能无缺陷的证明。

剩余明确边界：ADB 37.0.1 Windows 宿主 `.android` 限制、PowerShell 启动时模块路径重建（任务内调整已验证、启动阶段未完全隔离）保持原状。真实在线账号/模型自主工具选择、常用模式交互审批/TUI、实际用户电脑及真实设备、可选 LibreOffice/Poppler/OCR、Office 实际视觉渲染和公式重算/宏执行、未集成 Paramiko 的真实 SSH，以及正式发行 ZIP 构建/上传/回读未验；DCMI 2003-04-02 镜像来源已固定但未与官方原始字节直接比对。仅在明确真实复现或用户另行授权时再维护，不做越界重构。

## 2026-11-24：Office 原生校验及临时目录兼容性

在 PDF 手册库实际 ACL 问题解决后，检查现有三个相同的 Office helper 副本，发现 packed validate、原文件 schema 比对、Word redlining、PPT 原始缺陷比对及 LibreOffice profile 同样采用 Python TemporaryDirectory。统一使用现有包内 tmp/office 下唯一、Windows 继承 ACL/POSIX 0700 的自有目录，保留归档安全检查、已有 profile 策略、退出码和原权限；不改宿主 ACL。validate 使用 ExitStack 保证成功、失败及提前退出清理，并与 PDF CLI 一致处理非交互 UTF-8；三份公共 helper/validator 同步。补原生常用模式 DOCX 原文/redline 校验、PPTX 原文基线和 XLSX 明确不支持 XSD 分支及清理实测；仅 mock LibreOffice profile 调用，不安装/启动 LibreOffice，不声称真实渲染、公式重算或宏执行通过。[Windows 45412482193](https://github.com/rileyaaa/Portable/actions/runs/45412482193) PDF 37 项、Office 19 项边界与发行输入成功；首次实际常用模式 Word validate.py 在 `from helpers import` 处报 ModuleNotFoundError，工具退出 1 后合成 API 因缺少成功标记返回 400（连带错误，不是协议故障）。根因与固定 python314._pth 启用 isolated/safe_path、未自动添加脚本目录一致；三份 validate.py 现有内容完全相同。仅修 docx/pptx/xlsx 三份直接校验 CLI 入口：从自身已校验的包内普通文件布局导出 office 目录，添加进本进程 sys.path；不改 _pth、PYTHONPATH、宿主环境、其他 Office CLI 或固定依赖。补同一受限原生 Python 的 isolated/safe_path/ignore_environment、初始 sys.path、无环境 helpers、_pth 字节不变及入口本地路径/链接拒绝测试。原生 DOCX/PPTX/XLSX（明确不支持 XSD 分支）、PDF 实验和单独标记的 LibreOffice profile mock 保留，待复验；ADB 宿主路径和 PowerShell 启动路径限制仍保留，不为已知限制重构。

[Windows 45533763596](https://github.com/rileyaaa/Portable/actions/runs/45533763596) 与 HEAD 2697ff8 一致。真实受限 Python isolated/safe_path/ignore_environment=1，初始 sys.path 只有包内 ZIP/解释器/site-packages；Office 入口已成功导入 helpers。PDF 37 项、Office 21 项及发行输入通过。首个新失败是 DOCX docProps/core.xml 的 opc-coreProperties.xsd 编译失败（不再掩盖为文档通过）。源码原引用 2003-04-02 的两个 DCMI 网络 schema，且 XML namespace 未指定文件；包内未包含 DCMI 依赖。只补该既有校验所需的 dc/dcterms/dcmitype 三个同日期 schema，三份 Office 副本同步；固定上游版本来源见 DCMI https://www.dublincore.org/schemas/xmls/ 。当前环境无法直接下载官方 XML，采用 UNC-Libraries/box-c 固定提交 1af8a888240033409d43a63df2189008144e6367 的 2003-04-02 文件，原 blob、原 URL、许可和本地引用改动均记在 XSD 注释；未声称官方字节已比对。仅改导入位置，复用已有 ISO xml.xsd，不更改类型/元素约束、不跳过校验、不允许运行时联网、不升级固定程序依赖。Portions of this software may use XML schemas Copyright © 2011 DCMI, the Dublin Core Metadata Initiative (https://www.dublincore.org/). See https://www.dublincore.org/about/copyright/#schemanotice and https://creativecommons.org/licenses/by/4.0/ ; dated schema index also specifies https://creativecommons.org/licenses/by/3.0/ . 补实际离线编译、合法核心属性、非法元素和错误日期单元验证，并在原常用模式中文搬迁包内实测拒绝非法核心属性，仍待完整 Windows 回归；未改启动器、沙箱、_pth 或其他固定工具。

## 2026-11-24：Office/PDF 实际业务路径补充验证

[Windows 45398279081](https://github.com/rileyaaa/Portable/actions/runs/45398279081) 已确认常用模式与未知模型核心工具（含临时 PSModulePath 子进程验证）、Unicode 路径及 GPT-6.2 Sol 常用模式浏览器只读入口通过，未创建浏览器锁/profile。该运行全部成功：51 个实际子进程配置值一致，两个模式/模型的 Python userbase、pycache prefix 均实际生效；PowerShell 额外模块路径分别为包内 home-runtime/Documents/PowerShell/Modules、当前 PowerShell 7 系统模块及 Program Files/PowerShell/Modules，任务内 reset 通过但启动阶段未完全隔离。YOLO 浏览器、实际 MCP/HTTP、启动器、模式副本及发行输入均通过。此前 Office/PDF 仅证明 Python 导入及旧单元测试通过，不能代替由实际受限 Codex Shell 创建/读取文件。PDF 手册库 CLI 自身输出中文 Markdown/JSON，嵌入式 Python 重定向 CP1252 与前述 pip 同类风险，补非交互 UTF-8 输出并保留原控制台/文件格式/退出码，增加旧编码单元回归。新增 `documents` 模式，以合成 Responses 实际在常用模式的中文搬迁包内生成并读回 DOCX/XLSX/PPTX/PDF、PyMuPDF 页渲染与 PDF 手册库 build/search/read/verify/export；不启动宿主 Office、安装依赖、访问真实资料或扩大权限。公式只验保存与读取，不声称重算；可选 LibreOffice/Poppler/OCR 不在本轮验收范围。[Windows 45400559757](https://github.com/rileyaaa/Portable/actions/runs/45400559757) PDF 35 项单元与 Office 17 项边界回归成功；真实常用模式 DOCX、XLSX（未重算）、PPTX、PDF 渲染均成功，PDF 手册库首次 build 成功但 search 创建 pdf-ownership-* 临时目录报 WinError 5。与前述 Python 3.14 Windows 0700 私有目录 ACL 问题一致，属于实际工具缺陷而非本轮模型或测试夹具失败。保留 SQLite ownership snapshot、WAL 复制、只读连接和原子写入，改 Windows 合成临时子目录继承包内 tmp 现有 ACL（POSIX 仍 0700），同类 OCR 暂存复用该创建方式，不修改已有 ACL。新增失败清理、无关文件保留、重复 build、只读索引字节及暂存清理验证。[Windows 45408248526](https://github.com/rileyaaa/Portable/actions/runs/45408248526) 全部成功：37 项 PDF 单元、17 项 Office 边界，以及真实常用模式 DOCX/XLSX/PPTX/PDF、PDF 手册库重复 build/search/read/verify/export、只读索引及临时目录清理通过。OCR 未安装/未执行。无发布。

## 2026-11-24：0.172.0 核心工具验证与现有技能入口补正

[Windows 45395755596](https://github.com/rileyaaa/Portable/actions/runs/45395755596) 截至本次核对，Python CLI 编码/原有 shim 单元、常用模式及未知模型中文路径核心工具、pip/npm 实际配置（本地 prefix 为任务目录、显式 global prefix 为包内配置值）、两类合成受保护文件写入拒绝、Header 隔离、YOLO 无 MCP 浏览器和已启用 MCP 端到端均已成功；启动器及发行输入余项以该运行最终状态为准。ADB 与 PowerShell 启动路径重构仍非全量通过。保留官方 ADB 37.0.1，明确上游 Windows home API 限制；不改 Windows 用户目录或 ACL、不增工具、不换依赖。补 `browser-check` 原生常用模式只读发现（实际 0.172.0、GPT-6.2 Sol、双重扩展开关未开，使用 `-Check` 确认存在，不创建锁或 profile），区分实际任务启动须按既有审批处理；增加现有 shell 的临时 PSModulePath 调整实测，不宣称启动阶段已隔离。同步 desktop、pdf-library、portable-ssh 现有 Skill 示例，避免默认 work 下的根相对路径错误；保留设备授权、PDF 安全路径及 SSH 未集成依赖边界。新一轮专项 AC 尚未取得结果，实际交互批准与真实模型自主判断仍待实测。

## 2026-11-24：0.172.0 技能发现与实际子命令环境补充验收

按用户要求扩大现有能力的验收，不增加工具、注册方式、默认权限或依赖。0.172.0 上游仍通过兼容路径读取 `$CODEX_HOME/skills`，技能目录注入默认开启；`code_mode_host_grpc` 已废弃，本包未设置，MCP lazy stdio 默认开启。原端到端 MCP 夹具未复制技能目录，不能证明模型上下文可发现本地技能或 shell 实际接收全部环境变量。补充真实 BAT/Responses 捕获和工具调用回归，覆盖普通模式、YOLO 模式、新旧模型与未知自定义模型；合成文件/页面及固定依赖，不使用真实账号、外部网络或设备。修订现有 browser-debug 描述，覆盖明确打开网页、读取渲染内容、截图和交互；命令从当前包根派生，不假定工作目录为包根，MCP 未启用时提示现有任务脚本入口，不绕开审批。[Windows 45382687326](https://github.com/rileyaaa/Portable/actions/runs/45382687326) 已确认三个模型的 10 个 Skills 均进入请求；YOLO 无 MCP 的真实 Playwright 与原有 MCP 往返通过。常用及未知模型进入受限 PowerShell 后无法解析已存在的 probe.ps1，工具及实际 env 比对未完成；诊断随后被 CP1252 编码异常遮蔽。Work 独立 Linux 原生审计证实 0.172.0 的模型/协议、技能与合成 MCP 路径，Linux bwrap/Chromium 受执行环境限制。此次保留普通/YOLO 权限原值、双重扩展开关及全部固定依赖。修复测试 UTF-8 输出，补真实受限 shell 的 cwd/绝对相对文件解析/技能读取/work 写入及版本对照；先定位根因，不修改沙箱。修复自定义 Header 从宿主同名普通变量继承的问题：共用原子进程固定环境白名单，在加载包配置前清除其余继承变量，保留包内显式赋值及必要系统变量，不改变认证、代理、Header 配置语法或权限。补独立合成回归。[Windows 45387387694](https://github.com/rileyaaa/Portable/actions/runs/45387387694) 的旧版对照已进入 ConstrainedLanguage，但首轮诊断使用禁止的 Exception.GetType()，遮蔽实际路径异常；旧版记录显示 PowerShell provider cwd 与进程 cwd 不同，不能据此断定 0.172.0 引入故障。改用受限语言兼容的错误字段，将文件读取、位置切换、独立小脚本与直接工具执行分别验收，最终核对原生 JSON command exit 及实际写入文件；同一轮新版原生诊断也因 CLM 禁止 Exception.GetType() 退出，YOLO、MCP、模式副本和发行输入成功；Header 夹具实际失败于 PS5.1 AppendAllLines 三参数泛型重载，未达最终断言。修正该处为 AppendAllText 及 worker 多余输出；在已有原生 BAT/Responses/MCP 往返中用两个合成父环境值验证明确包内 Header 覆盖及未赋值 Header 缺失，不使用真实凭据。[Windows 45388511433](https://github.com/rileyaaa/Portable/actions/runs/45388511433) 同条件下 0.170.0 与 0.172.0 的真实受限 shell 均对 work、Skill、工具路径报 Access denied；YOLO 浏览器与原 MCP 回归通过。核对 CPython 3.14 `Modules/posixmodule.c` 的 Windows 0700 mkdir：`TemporaryDirectory` 默认建立受保护 DACL，仅 SYSTEM/Administrators/Owner；与通常解压目录不同。此为待验证的测试 ACL 根因，改为包内 tmp 新建唯一默认继承 ACL 的合成解压目录，输出本次夹具 ACL 证据，不修改任何现有目录 ACL，不扩大沙箱范围。另 [Windows 45388654479](https://github.com/rileyaaa/Portable/actions/runs/45388654479) 真实 HTTP 请求已确认包内 Header 值正确、未配置的宿主 Header 不发送，启动器/模式/发行输入也通过；PS5.1 子环境仍出现未设键，原 `[string]$Value` 参数会将 null 转为空串。修复共用环境写入函数在转换前保留 null 判定，明确空串语义不变，同步两份启动器；新增 null/空串断言。两种模式、认证、代理策略、固定运行组件均不改变；[Windows 45390453600](https://github.com/rileyaaa/Portable/actions/runs/45390453600) 已确认正常继承 ACL 使两个版本/两个模型均能读取 Skill、执行绝对/相对脚本、写入 work、定位并调用大部分包内工具，先前访问拒绝来自夹具；原权限配置不变。Header 缺失/空串、真实 HTTP、YOLO 浏览器、MCP、启动器和发行输入均通过。新增实际问题：两个版本的 ADB version 均试图创建宿主 `.android` 后遭拒绝，Windows 上游 `adb_get_homedir_path()` 直接调用 SHGetFolderPathW(CSIDL_PROFILE)，常规 ANDROID_* 变量不足；中文目录下 pip 入口 CP1252 崩溃；PowerShell 启动自行重构 PSModulePath；其余 Python import 已通过。修复现有 Python CLI helper 的非交互 UTF-8 输出（保留官方版本及控制台），新增 CP1252 单元回归及真实 pip/npm 配置消费、Python 隔离观察、包内保护文件/包外合成哨兵写入拒绝检查。ADB 严格便携与 PSModulePath 全隔离为独立未解决门禁，不再执行会触碰宿主目录的 ADB 版本探针，不将 core 验收通过称为全部工具或全量隔离通过；既有 ADB 二进制、两种模式策略及宿主配置不变。新一轮验收待验证。

## 2026-11-24：Codex 0.172.0 官方运行时升级候选（人工维护）

在独立检出目录中从官方 rust-v0.172.0 准备固定 Windows x64 工件，核对官方发布摘要与独立程序摘要，替换本地文字/Agent 所需主程序、Host、搜索和沙箱助手，并同步版本固定值、登录映射、运行清单、相关配置与模式副本。语音及独立 Exec Server 继续不打包；官方原始程序字节不修改。

**状态：已完成源码升级及 Windows 门禁，未发布新客户 ZIP。** [Windows 45377536184](https://github.com/rileyaaa/Portable/actions/runs/45377536184) 全部成功，实际校验官方 0.172.0 工件、45 个受管理 CODEX 变量、生成配置与真实模型导出、PowerShell 5.1 全量回归、309 项 Python（308 通过、1 项 POSIX mode 用例跳过）、Node、真实 Chromium/stdio、原生 Codex/Host/MCP/Chromium 合成 Responses 往返以及发行输入与 LFS。已推送 `3a5e5c6694c5ce483af8fa1e000a39949fa30f9d`。该轮 Responses 独立脚本仅执行 --help，不计为独立线协议实测；真实账号、联网模型自主选择工具、设备、TUI 与发行 ZIP 尚未验收。固定浏览器/Python/Node 等依赖保持不变。

## 2026-11-24：本轮现有功能维护收尾

本轮按原有功能、权限、便携隔离及固定依赖的设计完成浏览器/MCP、账号 JSON、认证切换、启动器/环境、代理桥、缓存清理、隔离检查、依赖维护及发行输入专项复核。各模块的实际旧版复现、新版验证、测试夹具修正和未覆盖边界见下文记录及对应 Windows Actions；不再因继续寻找细小问题进行例行生产源码调整。最近一次综合 Python 回归共 309 项，308 项通过、1 项按现有 SSH 候选依赖条件跳过（45371488924）。最后一轮 [Windows 45374794159](https://github.com/rileyaaa/Portable/actions/runs/45374794159) 已最终完成且全部通过：旧版隔离缺陷复现、新版隔离专项、现有路径/BAT 防护及发行输入检查。验证提交之后仅删除一次性工作流并更新本开发记录，生产源码未变；该次运行无 artifact。上述为源码候选验收，不代表使用真实账号、代理、外部模型服务或用户机器完成实测，不代表已生成或发布新客户 ZIP。

收尾核对：主分支生产源码基线 `ac2537685c93dbb533a362366f34bbabac25bf76` 与正式发行标签 `v0.170.0-portable.2`（`9350ad7fa5856595ff07af4469afae6a3251ebbd`）的差异中无 Codex 原生组件、浏览器固定工件、Python/Node 等固定依赖的更换；根及常用/YOLO 启动器相同，根与常用 env 相同，YOLO 的 approval/sandbox/network 保持既有差异。现存工作流仅原 `import-round12.yml` 与 `release.yml`，本轮一次性触发入口已移除。正式 Release 及旧版下载不动，不构建发布、不升级依赖，不把 Paramiko 等候选当成已发布功能。后续只处理实际反馈、明确复现的问题或用户另行授权的维护任务。

## 2026-11-24：依赖与打包维护复核

核对 `tool/工具更新说明.md` 的固定 wheel/hash lock、无源码编译、固定运行依赖修复而非自动升级、客户发行筛选和人工发布规则；源码复核 setup-tools 的路径/互斥、修复范围预检、lock 校验、候选发布时机以及 package-release 的干净索引、链接/私有状态、固定 runtime/browser、ZIP 核验设计。未发现必须调整的生产逻辑。[Windows 45371488924](https://github.com/rileyaaa/Portable/actions/runs/45371488924) 的维护入口和路径步骤、309 项 Python（308 通过、SSH 原生依赖用例 1 项按现有条件跳过）及 `package-release.py --check` 均通过；未实际联网重装依赖、构建正式客户 ZIP 或发布。已核对 GitHub 正式 Release 为 `v0.170.0-portable.2`，保留旧 Release 和固定工具；仅纠正过时文档，不引入 Paramiko 或其它候选依赖。依赖管理与发行输入专项不再做例行源码调整，等待实际问题及明确发布授权。

## 2026-11-24：隔离检查链接路径边界复核（源码候选）

保留默认仅包内、显式宿主只读扫描授权、报告而不删除宿主内容及 BAT 入口保护。旧直接 PS1 检查仅验证包根自身，未验证入口与祖先；Marketplace 和插件根警告后仍可能读取/枚举链接目标。复用其它入口既有的完整祖先检查，创建运行目录前拒绝 hardlink/reparse/link；Marketplace 读取前检查路径和普通单链接文件，插件根及各插件清单存在性检查前拒绝链接路径，不因诊断警告而继续访问目标。正常包内检查与已授权宿主扫描不变，不增加扫描范围或权限。合成 Windows 夹具使用自建 junction/hardlink 模拟边界，真实生产脚本旧/新对照，无真实宿主残留扫描或凭证。[Windows 45370271251](https://github.com/rileyaaa/Portable/actions/runs/45370271251) 新专项未进入用例（PS5.1 `-c` 引号问题）；[Windows 45371488924](https://github.com/rileyaaa/Portable/actions/runs/45371488924) 已复现旧入口穿越 linked ancestor 并验证新入口拒绝初始化。随后两版夹具均因变量 `$home` 与 PS5.1 内置只读 `$HOME` 冲突而停止，尚未验证 Marketplace 和插件链接用例。仅将夹具变量改名为 `$fixtureHome`，生产脚本不变。[Windows 45374794159](https://github.com/rileyaaa/Portable/actions/runs/45374794159) 的旧版复现和新版专项均通过，覆盖入口祖先、Marketplace 链接目录及 hardlink、插件根和个别插件链接及普通清单检查。该次 Windows 运行最终全部通过，综合路径/BAT 防护及发行输入步骤均成功；无 artifact。验证提交 `cc8bcb3204b154b5fe7b2954fa9eb13fc4e9a33b`。

## 2026-11-24：缓存清理单项失败与安全 bootstrap 恢复复核（源码候选）

保留现有清理范围、默认保留 Skills/work/Plugins、显式 CleanAll、预览/确认、包级与浏览器锁、认证及恢复状态保护、路径树校验及安全 bootstrap 策略。旧目录清理遇到占用文件时抛出的异常直接终止整个流程；若已删除生成的 config.toml，则后续 bootstrap 重建和失败统计均被跳过。现只在已批准计划的单项删除循环捕获失败，保留非零退出与现有计数，对剩余独立项目仍逐项执行原校验，最后按原策略尝试重建安全配置。无新增清理范围、用户参数或依赖。不保证被占用项目已经完全删除，也不把部分删除计入完整成功；增加完整 Windows 合成包的真实独占文件旧/新对照、预览、释放占用后再次清理、显式完整清理及认证/身份/恢复状态保护回归，不读取真实凭据或用户缓存。[Windows 45363684720](https://github.com/rileyaaa/Portable/actions/runs/45363684720) 路径、浏览器清理、309 项 Python 和发行输入通过；新增专项在读取旧源码的 Git 进程启动时失败，未执行文件占用用例。改用已固定包内 Python 的字节复制读取 Git baseline；[Windows 45370271251](https://github.com/rileyaaa/Portable/actions/runs/45370271251) 又在 PS5.1 将 Python `-c` 源码双引号剥离后产生 SyntaxError，两个新专项仍未进入实际用例。改为独占合成目录内的 Python 脚本文件调用，分别执行旧版复现和新版测试，不再由 baseline 失败跳过新版；原生产代码不动。该轮原有路径、浏览器、309 项 Python（SSH 原生依赖仍按既有条件跳过 1 项）及发行输入通过。[Windows 45371488924](https://github.com/rileyaaa/Portable/actions/runs/45371488924) 两个独立清理专项全部通过：实际复现旧占用文件导致 config 丢失与后续清理中断，修订后完成独立安全项、恢复 bootstrap、保留用户资产与认证/身份/恢复状态、占用释放后清理及显式 CleanAll，预览内容不变。原有路径/维护入口、Python 309 项（1 项按条件跳过）与发行输入检查通过；该运行的其他隔离夹具失败单独记录，不影响已通过的缓存专项。验证提交 `c59af70191abd27c2325d37a1960fb67a9df1c7d`。缓存清理专项结束。

## 2026-11-24：代理端口规范化与 IPv6 SOCKS 上游地址复核（源码候选）

保留原 HTTP/SOCKS5、代理开关、模型绕过、直连及超时/单次连接策略。启动器原端口通过 Int32 校验后仍以用户原字符串生成 URI，正数带加号等写法会产生无效 URI；改用已经校验的数值生成 URI 与 bridge 参数，账号 JSON 既有 Get-ProxyUrl 已使用数值，不改该模块。固定包内 PySocks `socksocket` 默认 AF_INET，而启动器原已接受裸 IPv6 与方括号 IPv6 地址，桥接上游使用 IPv4 socket 导致实际失败。bridge 将已支持的 IPv6 字面地址按 socket 所需形式去除括号并使用 AF_INET6，保留 IPv4、DNS 名称的原有路径及现有远端解析策略，不改变地址族自动选择、重试、连接限时、HTTP 转发或认证规则。根及两模式副本同步。新增准确的旧/新生产配置语句对照及真实包内 PySocks 对本机合成 SOCKS5 协议测试，覆盖 IPv4/IPv6、代理关闭、模型绕过，不访问外部 DNS、账号或服务；[Windows 45358089375](https://github.com/rileyaaa/Portable/actions/runs/45358089375) 全部通过，旧端口与 IPv6 失败复现、新配置及实际 IPv4/IPv6 SOCKS5 协商、进程生命周期、309 项 Python 与发行输入检查通过，验证提交 `b824fd95e9c0bd97a899f3340592e7226e6e3098`。代理/启动器专项结束，后续按实际反馈处理。

## 2026-11-24：SOCKS HTTP bridge 进程归属复核（源码候选）

保留代理开关、HTTP/SOCKS5、TUN/直连、模型绕过规则、随机或指定回环监听端口、每次启动认证 token 及现有 Python 转发/超时机制。原 bridge 直接 Process.Start，正常退出依赖 finally 清理；若启动器被强制终止，独立监听进程可能继续运行。复用包内现有 ProcessJobR20/SuspendedChildR20，在 bridge 执行前加入独立 kill-on-close Job Object，正常关闭/启动失败统一释放该 job 及子进程，重复清理安全；不改共享进程监管实现或代理协议，不新增依赖、权限或后台服务。根启动器与两模式副本保持一致。新增真实 Windows 合成 bridge 生命周期回归，以进程句柄验证强制终止与正常停止；不使用真实代理账号或外部请求。[Windows 45355771627](https://github.com/rileyaaa/Portable/actions/runs/45355771627) 已全部通过，实际复现旧进程残留，修订后强制终止/正常退出/重复清理均通过，原生进程、启动器、306 项 Python 和发行输入检查通过，验证提交 `a221d3b668dfdc931a8ea4037a5fb12cca39dbf6`。

## 2026-11-24：启动器显式认证参数及空输出参数复核（源码候选）

保留无参数交互菜单、`CODEX_STARTUP_INTERACTIVE`、默认 `menu` 带原生参数时使用 API、维护/扩展入口及 `--` 字面边界。旧启动器先剥离 `--portable-auth` 再按剩余原生参数数目决定是否显示菜单，单独显式指定 `api/account_json/browser/last` 仍可能进入菜单覆盖所选模式；现仅明确 CLI 非 menu 选择沿用已有非菜单认证路径，env 默认与显式 menu 不变。另修正 exec 的空短输出参数 `-o=` 落入 `-o<值>` 分支并把等号当文件名的问题；统一通过原路径空值检查拒绝，实际文件名为 `=` 的 `-o==`、正常短/长写法及 `--` 字面内容仍保留。无新增用户参数、权限或依赖，根启动器及两模式副本同步。实际生产解析语句及合成主机交互条件/路径桩旧新对照，不执行真实认证或创建输出文件；[Windows 45354768448](https://github.com/rileyaaa/Portable/actions/runs/45354768448) 已全部通过，验证提交 `9fbb6c3dd76590cf9c8861489a79935daf054b30`。

## 2026-11-24：首次官方账号登录的认证提交时机复核（源码候选）

保留设备码默认、显式系统浏览器、现有账号快照、启动菜单及非交互认证入口。旧 menu/CLI 两条路径在首次官方登录尚未调用客户端前就清除 auth-transition.block；若客户端写入活动凭证后中断，下一次启动可能按 browser mode 将未确认完成的活动凭证升级为持久快照，与现有未完成认证切换保护冲突。现只在已有快照恢复或非首次登录时按原位置完成切换；首次官方登录须等客户端成功退出、活动凭证校验、持久快照保存和原 logout block 清除后才完成。失败和中断继续走原隔离恢复，不增加自动重试、登录方式、文件或权限。根与两模式副本同步，使用实际生产提交/恢复语句和合成凭证验证两条路径、持久写失败与正常成功；不访问真实账号或网络。[Windows 45353687587](https://github.com/rileyaaa/Portable/actions/runs/45353687587) 已完整通过旧/新提交时机、登录与启动器综合回归、运行组件和发行输入检查，验证提交 `3064dbffaae7a3285b30984ede2bf799a58c3897`。

继续复核快照内容校验：核对固定上游 `codex-rs/login/src/auth/storage.rs` 和 `codex-rs/login/src/token_data.rs` 的 AuthDotJson/TokenData 类型。旧 PS5.1 通过 `[string]` 强制转换 token，可把非空布尔、数字、对象及数组误认成凭证并覆盖正确快照。现拒绝非对象根/Token 容器、非字符串 auth_mode 和非 null 的已知 token/身份/API Key 字段的非字符串类型；原缺失/null 字段、至少一个非空 access/refresh 字符串的兼容判定保留，此为本地结构检查，并非完整原生反序列化、JWT 或在线有效性验证。不新增认证格式、模式、依赖或文件，根启动器及两个模式副本一致。增加合成旧/新回归和快照不被覆盖的实际文件验证；[Windows 45354184468](https://github.com/rileyaaa/Portable/actions/runs/45354184468) 已全部通过，覆盖结构、原认证恢复、登录/启动器回归、306 项 Python 和发行输入检查，验证提交 `588dedb4b511b190ec014a19f6be02af39dbba56`。认证切换专项结束，后续按实际问题维护。

## 2026-11-24：官方账号快照类型边界复核（源码候选）

保留 API、账号 JSON、官方设备码三种模式、旧包 ChatGPT 凭证迁移、活动槽位和独立快照、logout block 与 transition 恢复机制。旧通用认证校验接受 apikey 与 chatgpt，官方账号快照复制及恢复也使用该通用校验，可能将合法但类型不符的 API-key 文件归入官方快照。现官方账号恢复、备份、临时副本及新登录验证要求 chatgpt；按旧 mode 回收时不把类型不符的活动文件覆盖到快照，沿用原 invalid 隔离保留机制。通用 API-key 文件校验与正常 API/env/provider 不变，不引入新的模式或配置。同步根启动器与常用/YOLO 副本，增加 Windows 合成文件旧/新回归，覆盖原迁移、退出及未完成切换恢复；不访问真实凭证或网络。[Windows 45353264857](https://github.com/rileyaaa/Portable/actions/runs/45353264857) 全部通过，验证提交 `c3d20a4de3e6354a319e96d39e6c8ba788fac402`。

## 2026-11-24：账号模块收尾——扫描文件状态复核（源码候选）

原调度器已对同一文件按凭证顺序串行检查、不同文件并发；保留该设计，不改并发值、刷新触发和删除规则。原扫描枚举 FileInfo 可能缓存刷新前的长度/写入时间，导致成功原子保存且完成检查的账号仍使刚写出的缓存立即失效。本轮只在本次成功保存后记录该文件的非凭证元数据，随内部 probe 结果传递，按同文件最后一次保存更新原扫描文件状态；未写过的文件、删除/新增造成的扫描范围变化仍沿用原校验，不对所有文件重新取末尾快照，不额外保存 token 或哈希，不修改缓存时效和持久结果格式。新增真实 Windows 合成文件写入、旧/新缓存对照，以及原调度器的作业桩回归；[Windows 45352874065](https://github.com/rileyaaa/Portable/actions/runs/45352874065) 已复现旧缓存失效，修订后的实际写入、缓存复用、非本次写入和扫描范围变化测试通过；新增调度断言的 PowerShell 数组拼接表达式错误，日志中的实际入队顺序正确。仅修正测试预期表达式，不改调度器。[Windows 45353264857](https://github.com/rileyaaa/Portable/actions/runs/45353264857) 已全部通过，确认原调度顺序、实际缓存状态、账号全部回归、306 项 Python 与发行输入检查；账号 JSON 专项结束，后续以实际反馈为主。

## 2026-11-24：账号缓存复用与刷新网络边界复核（源码候选）

保留合法 JSON 缓存复用、无 JSON 且未指定扫描限制时的旧 CSV 兼容入口；已有 JSON 缓存未通过版本、扫描范围或文件状态校验时，不再回退同批 CSV 绕过校验，显式文件/凭证限制也不由不记录限制的 CSV 替代。缓存版本 3 升至 4 使旧解析、局部清理与额度重置结果一次性失效，不增加定时刷新或修改原有缓存时效。固定 Python Requests 默认禁止重试；ConnectTimeout 与包装的 urllib3 NewConnectionError 可证明连接未建立，PowerShell 的明确 DNS/连接失败和 curl 5/6/7 同理。仅对现有 OAuth refresh POST，在无法确认发送结果的传输异常、408、5xx 情况下停止自动换路重放；若第二路 POST 的结果不明，不再用第一路 401 判定永久失效。明确连接未建立及原有 4xx 拒绝的代理回退、普通 GET、显式 direct/proxy、确认失效删除逻辑保留。不声称可恢复服务端已经轮换但未收到的新令牌。无新增用户功能、依赖或请求地址；旧/新合成对照与固定后端异常分类回归均不访问真实凭证或网络。[Windows 45352023171](https://github.com/rileyaaa/Portable/actions/runs/45352023171) 已通过全部步骤，含旧行为复现、缓存及刷新网络边界回归、306 项 Python 与发行输入检查，验证提交 `09b7a861804173c5c875bfdf9cebcc4aa3acd215`。

## 2026-11-24：账号刷新字段一致性及额度重置时间复核（源码候选）

维持原刷新触发、认证错误分类、auto/direct/proxy 路由、额度分类及缓存复用策略。刷新成功后仍写既有标准 token 字段，同时更新已存在的 camelCase 别名；服务端返回合法正数 expires_in 时更新已存在的显式有效期（旧父级回退仅由当前凭证自身 expires 覆盖），不改共享父级或无有效期元数据的格式，不凭空推断缺失的有效期。核对固定 Codex 0.170.0 上游 `codex-rs/backend-client/src/client.rs` 的 rate limit 映射及测试，普通 rate_limit 主/次窗口包含 used_percent、reset_at（Unix 秒）和 reset_after_seconds；既有明确 NO_QUOTA 的 allowed=false/limit_reached=true 分支改用耗尽窗口中最晚的已知重置时间，不使用未耗尽窗口或附加额度的重置时间；有耗尽窗口时间无法判定时留空，旧无窗口格式继续沿用原解析。其他额度分类不变。增加真实生产函数旧/新合成回归，不读取真实账号或访问认证服务。[Windows 45351481533](https://github.com/rileyaaa/Portable/actions/runs/45351481533) 已完整通过旧行为复现、刷新字段/重置窗口及原有分类、304 项 Python 回归和发行输入检查，验证提交 `a8684111773effef425df53ab7eca1dcd0e47db3`。

## 2026-11-24：账号检查报告归属及登录选择一致性复核（源码候选）

保留并发调度、超时、自动删除、缓存及显式 Use 行为。修复并发探测超时或未能读取结果时 ERROR_KEPT 报告丢失原凭证序号、来源、显示名和容器删除标记的问题；队列仅保存非凭证的报告身份字段。缓存选中账号若有明确账号 ID，则在写入认证切换标记之前与实际读出的凭证 ID 比较，不一致时拒绝导入并提示使用原检查入口；正常一致、旧报告无 ID 和显式 Use 不变，不新增网络检查。此保护不等于证明同一账号 ID 下的所有令牌身份一致，不改缓存时效与刷新策略。新增 Windows PS5.1 生产函数旧/新对照，用合成凭证身份及作业/写入桩，不访问真实凭证或网络；[Windows 45336475794](https://github.com/rileyaaa/Portable/actions/runs/45336475794) 已全部通过，旧行为复现、报告身份、登录写入前一致性、原有容器/输入/登录回归、304 项 Python 及发行输入检查均通过，验证提交 `fddcfe34b44d261c762aeb997d43aab70a38b865`。

## 2026-11-24：账号 JSON 容器识别与局部清理复核（源码候选）

保持账号检查原有直连/代理、按需刷新、额度分类、缓存、并发、确定失效自动删除及认证快照设计。只修复 PowerShell 返回数组被展开导致单元素 accounts/credentials 容器识别错误，以及局部清理后用“是否已具备 token”而非解析器实际识别的非空嵌套记录判断剩余兄弟项、可能删除尚未检查的记录。保留 JSON 数组形状，空列表仍沿用原直接凭证回退；只在局部删除后保留未单独判定的记录，明确失效条目和最终空容器仍按原规则清理。未改变单条/多条删除判定或新增认证格式。新增合成容器生产函数回归，并在 Windows PS5.1 对照精确旧提交；无真实凭证、网络或文件删除。[Windows 45334691275](https://github.com/rileyaaa/Portable/actions/runs/45334691275) 已完整通过，精确旧源码两处问题复现、修订容器回归、9 项输入异常、URL 合同、304 项 Python、7 项登录流程和发行输入检查均通过，验证提交 `dc77533c9f98e527bd0022025dc88ee5c0af889a`。

## 2026-11-24：现有浏览器与 MCP 异常恢复复核（源码候选）

上一轮 [Windows 验证 45328294982](https://github.com/rileyaaa/Portable/actions/runs/45328294982) 已完整通过：304 项 Python、Node/PowerShell、真实 Chromium/stdio、认证 HTTP 代理、缓存清理、原用户 MCP 配置的真实 BAT → Codex 0.170.0 → MCP → Chromium → 本地合成 Responses 往返及发行输入检查；验证提交 `1f92a7aebbf05a2d65c682e085a65954ce639743`。

本轮定位两项可复现缺陷：固定 MCP SDK 1.29.0 取消请求时不发送结果，旧包装器因此无法释放 pending 槽位，128 次取消后拒绝后续正常请求；旧 browser owner 在关闭抛错时无条件丢弃当前上下文，可能再次尝试占用同一 profile。合成故障对照旧生产函数复现，修订函数通过：有效取消释放槽位、丢弃迟到结果、连接关闭清理；失败关闭保留上下文直到成功重试或收到 close 事件。并发逻辑上限、工具白名单保留，不宣称强制停止已发起的浏览器操作。Node 路径检查仅合并同一次 leaf stat 和紧邻的递归目录检查，枚举前仍检查完整祖先及链接、类型；PowerShell 防护不变。新增固定 SDK 取消、关闭恢复和 stat 次数断言。未测实际启动提速比例，不新增功能、参数、依赖或权限。[Windows 45330085918](https://github.com/rileyaaa/Portable/actions/runs/45330085918) 已完成全部回归与真实 Codex/MCP/Chromium 往返、发行输入检查；验证提交 `3978b62bbf31ab569d3ce5772fdf0f34e6510e38`。

继续复核既有任务结果和代理边界：旧 task JSON 截断未计入转义及包装长度，实际合成结果分别达到 12031/24022 字符，顶层函数结果触发未定义 length 错误。现按最终 JSON 序列化长度限制 12000 个 UTF-16 代码单元，保留正常格式及超长截断标志。原生自动化包装器在三个代理开关全部有效、包根匹配但代理地址未传入时曾允许直连；现明确报错，不改变正常直连与 HTTP/SOCKS 路由。修正 MCP Cookie 测试的页面重复写入（只在初次调用时种入 Cookie），增加本地认证 HTTP 代理的 loopback 绕过及真实合成 SOCKS5 验证，不访问外部站点。本轮新增回归均为开发测试，不新增用户功能。[Windows 45331102698](https://github.com/rileyaaa/Portable/actions/runs/45331102698) 已完整通过 304 项 Python 回归、Node/PowerShell、单次种入 Cookie 后重开、认证 HTTP 代理、本地绕过、真实合成 SOCKS5、原生 Codex/MCP/Chromium 往返及发行输入检查；验证提交 `9e62a75fb4d2c8e0d7d55e4a76dfd66738aaadfc`。

收尾复核：旧 owner 在并行获取同一个尚未完成启动的 context 时，如同时收到 close/dispose，两个获取调用仍可返回已经关闭的 context（合成故障对照两种场景均复现）。现所有等待调用在启动完成后重新确认所属 context、关闭与终止状态，旧调用拒绝，后续正常重开保留。原 Node 递归浏览器 payload/profile 检查在 stdio 初始化时只执行一次，延迟启动与重开可能使用已变化的目录。现将该层完整树检查移到每次真实 Chromium launch 前（任务脚本及 MCP 共用，正在使用的 context 不重复扫描），同时验证必需状态目录类型；PowerShell 层、依赖树、互斥和其他路径边界不变。合成旧/新函数对照通过；增加共享启动竞态、首次延迟启动与关闭后重开路径变化的回归。此为现有模块收尾，保留已验证设计，不新增功能。 [Windows 收尾验证 45332946246](https://github.com/rileyaaa/Portable/actions/runs/45332946246) 已自动触发，验证提交 `bd485b4177eb0b9ab378f3042d6f2f98e3005841`；临时触发器已删除，全部 Windows 回归、真实 Codex/MCP/Chromium 往返和发行输入检查通过。浏览器/MCP 专项结束，停止例行生产代码改动，转入真实使用反馈；在线账号、第三方站点兼容性及实际用户电脑仍需实测。

## 2026-11-24：现有浏览器与 MCP 专项修复（源码候选）

仅优化现有能力，不新增启动参数、MCP 注册机制、服务、工具或默认权限。撤销初次候选的 `--portable-browser-mcp`，继续使用原 stdio 入口、用户 MCP 持久配置和原双重启用条件。修复 core shell 环境漏传的代理控制变量，规范化有效布尔值；浏览器通过现有 Playwright 显式采用获准的 HTTP/SOCKS5 代理，自动生成输出目录与用户工作文件隔离。保留浏览器资料、互斥、工具白名单和正常/维护/YOLO 边界；同步原模式副本。用户 MCP 环境配置示例放在原 browser-debug 技能中，不默认注册。

验证记录：[综合 Windows 45325563396](https://github.com/rileyaaa/Portable/actions/runs/45325563396) 已通过 LFS、Python、Node、PowerShell、真实 Chromium、原生 stdio MCP 操作及认证 HTTP 代理、持久化、清理和发行输入检查（针对初次候选）。[完整链路 45325941104](https://github.com/rileyaaa/Portable/actions/runs/45325941104) 在测试脚本导入阶段失败：包内嵌入式 Python 不搜索相邻脚本，尚未实际进入 Codex/MCP 调用。修订测试改为显式加载同目录测试 helper，并使用原有用户 MCP 配置入口；不得将先前通过的结果当作本次收敛后的最终验收。真实在线账号/模型及跨机器状态仍须实测；不修改正式 Release 或固定依赖。

## 2026-11-19：Codex 0.170.0 官方运行时升级候选（人工维护）

在独立检出目录中从官方 rust-v0.170.0 准备固定 Windows x64 工件，核对官方发布摘要与独立程序摘要，替换本地文字/Agent 所需主程序、Host、搜索和沙箱助手，并同步版本固定值、登录映射、运行清单、相关配置与模式副本。语音及独立 Exec Server 继续不打包；官方原始程序字节不修改。

**状态：候选源码更新，尚不能视为正式版或已确认兼容。** 必须在 Windows x64 上完成离线与原生兼容性检查、环境变量与工具/浏览器验证，处理新版 schema、请求协议与真实功能不兼容项；经 ZIP 解压、移位和哈希复核后方可人工发布。实际账号、联网 Agent 和用户终端显示须另行实测。

## 2026-11-19：收敛为 main 的稳定人工维护模式

继续以 `main` 的 Codex/Code Mode Host 0.166.0 为基础；不再运行 AC 自动升级，不引入开发分支整套 Tool、MCP、Chromium 或候选发布框架。仅增补固定浏览器下载防重定向和发行标签与实际 Codex 版本匹配的检查。Android 独立 ADB 保持技能规定的包内绝对路径调用，不加入 PATH。后续升级需人工选择官方成对工件、检查兼容性，并在 Windows 验证后单独发布；本次源代码调整不代表创建了新 Release。

### 清理后的有限功能回收

仅从已删除开发分支的原提交 SHA 中移植经审查的 Windows 系统路径修复、缺失 SDK/JDK 的环境标识、断开的 NTFS junction 保护、登录及 Python 安装入口的系统环境修复、浏览器/桌面自动化子进程的显式代理继承规则。继续使用 0.166.0 的官方运行组件、原有 MCP/Chromium/Skills 和用户编写的 Android ADB 绝对路径策略；不引入 0.169.0 配置、开发版自动升级工具、额外服务或后台工作流。根启动器与常用/YOLO 副本同步；不自动创建 Release。

## 2026-10-31：按使用者要求重新打包 0.166.0 为 Portable r1

原 `v0.166.0-portable.1` 的 Release 与标签均已不存在；原 r2 仍已发布，但尚未经过使用者实际验收。本次将前一批本地独立执行器精简后的源码重新命名为 `v0.166.0-portable.1`，并保持 `0.166.0` 官方主客户端、Host 与沙箱组件不变。r1 必须通过新的完整 Windows 工作流和十轮随机测试，客户 ZIP 及三个附件回读成功后才能成为正式版；**只有新 r1 验证成功，才允许删除旧 r2 Release 及其标签**。不要先删掉唯一已发布的 0.166.0 包，也不修改 0.164.0 稳定发行版。

现有 GitHub Connector 无法直接调用 workflow_dispatch 或删除 Release。为执行此项明确授权的重新打包和删旧发布任务，允许本次使用一个严格匹配提交信息和专用文件路径的单次 push 引导器；它只调度既有 `release.yml` 的 `workflow_dispatch` 全量门禁，等待成功并回读后才删除旧 r2。成功后必须从 main 删除临时引导工作流，现有正式发布工作流仍仅允许手动调度。若失败，保留 r2 并报告真实失败状态，不绕过全量门禁或重用旧测试结果。

## 2026-10-30：可选独立执行器精简（0.166.0 便携修订）

仅面向本地 Windows TUI/文字 Agent，删除未使用的 `codex-exec-server.exe` Git LFS 文件及 `codex-package.json` 的 `execServer` 字段。官方 `rust-v0.166.0` 的 npm staging 同样省略二者；主 `codex.exe`、Code Mode Host、沙箱助手和 `--no-daemon` 不变。此操作只移除可选独立程序，不声称从主客户端二进制中删除全部远程相关代码；便携启动器原本就拒绝 `exec-server` 等服务端子命令。

同步 `tool/runtime-manifest.json`、`codex-package.json`、启动器固定摘要及常用/YOLO 模式副本，调整打包身份白名单、回归和使用说明。已完成任务的一次性 0.166 升级 Actions/适配脚本清理，不允许再次自动引入该 EXE。客户包以固定源码的干净工作树生成；重新打包的 `v0.166.0-portable.1` 必须由现有 `release.yml` 的手动分发入口运行完整 Windows 检查与十轮回归，通过 ZIP/远端附件逐项回读后才发布。线上账号、实际端到端模型调用、用户终端滚动显示不在自动验收范围。只有用户实际使用的 0.164.0 可作为已确认稳定基准。

## 2026-10-30：Codex 0.166.0 官方运行时升级（自动化候选）

本次使用 GitHub Actions 从官方固定 release 下载 Windows x64 canonical package，校验归档与独立 EXE 摘要，同步主程序、Code Mode Host、执行器、沙箱助手、搜索工具及 manifest，保留包根启动和全部便携隔离策略。新版新增 codex-exec-server.exe 并适配 package metadata 的 execServer 字段；语音继续不打包，重复沙箱助手继续精简。

启动器 `CODEX_TUI_FULLSCREEN_TRANSCRIPT` 默认 false、可在受控 env.local.ps1 覆盖；继续使用 `--no-daemon` 防止共享 daemon 把状态迁到包外。本提交只有经 runner 验证的文件；真正的 Windows 全量发行门禁由单独 release workflow 执行。账号登录、真实网络代理、付费模型及用户终端重绘不以合成测试冒充实测。

## 维护约定

开始维护前阅读本节及 [README](README.md)。这里统一记录项目限制；使用方法、下载步骤分别维护在对应文档，不在多处复制整套说明。

1. **只维护四份项目文档。** 根 `README.md`、本文件、`tool/工具更新说明.md`、账号格式转换子项目的 `README.md` 是固定入口。未经用户同意不新增项目说明文档；确有必要时先说明理由并征得同意。每次功能新增、修改或删除，同步相关说明、变量注释及受影响的技能文档；直接更正、删除失效内容，不持续堆叠重复说明。已授权技能所必需的 `SKILL.md`、第三方功能文档和许可证、用户转换任务生成的交付报告不属于新增项目说明文档。
2. **记录原因和结果。** 本文件开头维护稳定规则，下面按日期记录变更原因、最终结果、验证和必要的遗留问题。同一天同一事项可合并更正；不记录逐次尝试、排查对话、无效假设或临时命令输出。已解决事项应更新状态，不长期保留为待办。
3. **目标平台。** 以 Windows x86-64（x64）、本地 NTFS、Windows PowerShell 5.1 为准；x64 不等于 32 位 x86。保留 BAT 的 ASCII/CRLF、PowerShell 的 PS5.1 语法和既有编码兼容。Linux 或 PowerShell 7 的检查不能代替 Windows 验收。
4. **任意解压位置。** `D:\Codex` 仅为常用示例。包根从当前脚本位置派生，不依赖固定盘符、工作目录或继承的旧 `CODEX_INSTALL_DIR`；工具、配置、缓存、状态和临时路径跟随当前包根。不得把机器绝对路径写入默认设置。搬迁回归须覆盖旧包仍存在、无关工作目录、空格和中文目录。
5. **目录边界。** 默认只处理当前包内任务文件，不主动扫描、读写或清理宿主用户目录、其他目录及旧包。包外任务文件按用户已授权的具体范围访问；Windows 必需程序、系统依赖和固定系统策略存在性检查属于明确的系统访问。维护模式扩大包内可写范围，不自动授权包外操作；`workspace-write` 不能保证阻止全部包外读取。
6. **先验证路径，再访问。** 先检查词法边界，再检查完整祖先及目标的 reparse/junction/symlink、输入硬链接和适用的 ACL；检查应早于创建目录、读取内容或执行程序。保留正常/维护模式分界、受保护变量和 CLI 覆盖限制，不通过关闭身份校验、放开路径或关闭 Code Mode 掩盖故障。MCP/插件的外部命令及绝对路径需另行核对。
7. **每次升级复核变量。** 更新 Codex、Host 或任何工具后，核对对应变量的声明、默认值、加载/覆盖、生成配置、子进程最终值和新版实际消费点，并查看上游 schema/发行说明。区分启动器私有接口、原生变量、兼容别名和仅预留路径；确认失效时移除或替换并同步文档、回归。变量存在或程序安装成功都不等于功能生效。
8. **保持工件与工具来源。** Codex/Host 使用同一官方稳定 release 的 Windows x64 工件，校验来源和摘要，更新固定身份、登录版本映射及 `tool/runtime-manifest.json`；保留所需配套资源与许可证，不修改官方 EXE/DLL 字节。本包明确只做文字与 Agent 工作，省略语音组件并关闭仍有效的语音开关；无开关的上游入口如实说明不支持，不能保留失效配置冒充禁用。今后升级也保留文字/Agent 范围。其他工具按 [工具说明](tool/工具更新说明.md) 在包内安装/更新，工具缺失时明确报告，不静默调用宿主或全局包管理器，不永久修改系统/用户 PATH，不运行 Node 随附的系统安装脚本。
9. **保护状态与清理边界。** 不读取、记录或提交真实账号 JSON、API Key、认证快照、会话、机器私密配置及其内容/哈希。测试使用合成数据，临时文件放包内 `tmp` 的独立目录，创建前检查链接；只清理本次创建的文件和启动的进程。认证 snapshot、transition/logout/recovery 标记及 installation identity 不当作缓存删除，既有用户数据和进程应保留。配套浏览器资料固定在 `cache/browser`，任务退出只关闭进程，默认保留资料；用户运行“清理缓存”时才统一删除 Cookies、网站登录和缓存，并通过专用锁拒绝清理活动会话。
10. **单一维护来源与模式副本同步。** Android 完整流程统一维护在 `home/plugins/android-apk-lab/skills`，外层只保留精简 `apk-test-router`，保留用户编写的 `mumu-adb`。Office 的 docx/pptx/xlsx 共用 helper 副本保持一致。根 `env.ps1` / `run-codex.ps1` 更新时，必须同步 `Version_History` 下的四份常用/YOLO 模式文件：常用两份与根文件逐字节相同；YOLO 启动脚本与根相同，env 基于根生成，保持 `CODEX_PORTABLE_PROFILE=strict`，仅将 approval 改为 `never`、sandbox 改为 `danger-full-access`，并保留原 YOLO 的 `CODEX_SANDBOX_NETWORK_ACCESS=true`。Fast、扩展默认值及其他修复全部同步，不另维护旧版客户端身份。用回归验证差异仅为这三项赋值。其他真正历史资料不批量替换；账号格式转换器独立维护。
11. **验证与交付。** 运行与变更相关的回归，明确区分通过、失败、跳过和未运行；不能用假输出或空程序冒充工具可用。保留用户改动，使用现有 checkout，不另建 worktree，除非用户要求。提交/推送前核对差异、引用、Git LFS 工件及私密/临时文件排除；没有执行的 Windows、真实账号或设备流程不得写成已通过。正式包从干净提交的文件清单生成，包含实际 LFS 工件，逐项验证 ZIP，并附来源提交与 SHA-256；不递归打包整个工作目录。
12. **按任务启用，默认关闭 Fast。** `CODEX_FAST_MODE=false`；Plugins、用户 MCP 默认关闭，维护模式也不自动启用。扩展配置须同时满足对应开关和本次 `--portable-extensions`。发现、读取技能或进入维护模式不代表授权运行其工具；只有用户明确提出相关任务，才检查依赖、启动服务、连接设备或操作目标。包内安装不等于授权控制整台电脑或模拟器；实际任务仍限已选目标。
13. **GitHub Actions 只手动运行。** 所有工作流仅允许 `workflow_dispatch`，不添加 push、PR、定时或关联工作流自动触发。临时下载使用短保留期，不建立长期大文件缓存；产物取回并校验后及时删除本次 artifact、临时分支/发行附件及下载缓存。未能执行或清理须明确报告，不能将保留期代替主动清理。
14. **及时提交并推送。** 每完成一批可独立验证、文档已同步的修改就提交并推送到用户指定仓库，不将大量已完成改动或多个提交长期堆在本地。推送前检查差异和测试，推送后核对远端提交；未完成的功能留待下一批，不能为赶进度发布已知损坏入口。
15. **控制体积与重复能力。** 默认面向 DBA、Python 爬虫/数据处理和偶尔开发调试；保留常用运行依赖，低频 Go 编译仍优先放独立项目的手动 GitHub Actions，不自动补回 Go 编译工具；Python EXE 打包已于 2026-10-25 获用户明确授权恢复历史 PyInstaller 及必要依赖，仅在明确打包任务中由 AI 直接调用包内 Python 原生模块，不额外维护打包封装。同一用途优先复用已装依赖；浏览器统一为一套 Playwright 和一份配套 Chromium，不并装 ChromeDriver、第二套浏览器或 Chrome DevTools MCP。先检查现有 API/CDP 是否能完成任务，再考虑新增工具并说明收益与体积。精简前核对上游查找路径、共享依赖和实际功能；不因文件名相似就删除官方助手或资源，不为体积牺牲已保留功能。所有可配置的 profile、下载、缓存、临时文件随包根移动；不能以“便携”名义隐藏系统权限或工具自身的限制。
16. **客户发行内容。** 先在源码检出中完成验证，再从干净提交构建发行 ZIP。第一方测试、CI、Git 配置和开发打包器留在仓库，不进入客户包；临时文件、缓存、账号和本机配置不发布。保留运行依赖、许可证和四篇说明，逐项验证 ZIP 与来源清单。
17. **按风险选择验证范围。** 小改动也可能阻断启动或改变请求协议，不能只按行数判断。客户端/Host、依赖工件、权限与路径边界有变化时执行完整 Windows 门禁。已授权维护范围内、工件未变的脚本补丁，可依据已通过的全量基线、差异核对、定向回归与必要的真机反馈重打包；记录未重跑的范围，逐项校验 ZIP 与上传回读。已知问题未解决时不得以旧测试通过覆盖它，也不将旧测试记成本次新测试。
18. **Release naming and language.** Use `Codex Portable <CodexVersion> - Portable r<N>` for the title, `v<CodexVersion>-portable.<N>` for the tag, and `Codex-Portable-v<CodexVersion>-portable.<N>-windows-x64.zip` for the package. Titles, tags and asset names must be ASCII; release notes must be English. Increment the portable revision when the downloadable package changes; restart at 1 after a Codex upgrade. Documentation-only commits do not require a new package revision. Never overwrite published tags or assets; keep dates in release metadata and maintenance records.

19. **终端偏好由启动器显式生成。** `CODEX_TUI_FULLSCREEN_TRANSCRIPT=false` 为默认值；`env.local.ps1` 仅通过受支持变量白名单覆盖，复用严格布尔解析并写入 `tui.fullscreen_transcript`。根脚本和四份模式副本同步；`--no-alt-screen` 的原生限制和 `--no-daemon` 的隔离策略保持不变。升级时核对该字段的定义、默认值及真正渲染消费点，不能把配置成功解析当作 Windows 滚动重绘验收。

### 升级必须检查的项目

- **来源与配套文件：** 官方固定 release、架构、摘要、许可证、Host/搜索/沙箱助手及实际查找顺序；同步 manifest、版本映射与四份模式模板。
- **真实交互入口：** 在真实终端覆盖双击、提示文本、resume/fork；检查共享后台服务的默认行为、安装路径及本包 `--no-daemon` 策略，不能为启动将 CODEX_HOME 移到包外。版本输出、模型导出和配置读取成功不代表交互启动成功。
- **认证与会话：** API、账号 JSON、官方设备码分别确认认证选择与实际请求路由；检查切换、刷新、退出及失败恢复的 snapshot/标记归属。`last` 不能替代显式认证模式诊断。没有实际验证的流程如实列为待验，不索取或记录真实 Key/账号文件。
- **模型与请求协议：** 核对模型 slug、元数据/schema、默认推理档位、上下文、工具声明及变量实际消费点；特别检查 `use_responses_lite` 等内部协议字段。不能仅看 `wire_api=responses` 就假定协议不变；对照实际请求路径、模型、头和消息/工具结构。自定义 API 保持配置原模型名并使用标准 Responses；官方账号单独验证。Fast 默认仍关闭。
- **代理与网络条件：** 沿用用户实际 HTTP/SOCKS 类型、主机、端口、桥接与 NO_PROXY 条件；覆盖明确开启、默认开启/回车、模型绕过及本地命令代理。模型 API 联网与 shell 沙箱联网分开检查；不能用跳过菜单的直连测试代替用户的代理流程。
- **便携路径与状态：** 正常/维护/YOLO、旧包仍存在、换盘符、中文/空格路径；确认配置、数据库、下载、缓存、编译临时文件随当前根移动，链接拒绝先于访问，清缓存不删除认证。系统依赖访问与“系统层面零包外写入”不能混为一谈；未做文件访问跟踪不能宣称后者已证实。
- **实际功能：** 覆盖模型回复与包内一项 Agent/Host 工具调用，确认功能没有因精简或兼容开关被关闭。假接口用于隔离协议/代理回归，不能单独算真实账号、模型或设备验收；不可用的测试环境要明确说明。
- **交付与编码：** Windows PowerShell 5.1、ASCII/CRLF BAT、单个 UTF-8 BOM、受保护变量及模式副本。下载脚本原文件，避免复制网页引入重复 BOM。按风险选择检查后，从干净提交打包，排除测试/临时/用户状态，上传回读后才发布；成功替代后再删除问题发行包，保留 Git 历史追溯。

## 2026-10-26: Windows-confirmed compatibility hotfix release

**Cause and result:** Codex 0.164.0 changed interactive daemon preparation and bundled model metadata. The fixes keep CODEX_HOME inside the package by using the official `--no-daemon` option for interactive startup, and preserve standard Responses requests for custom API providers without changing the configured model name or proxy. The user confirmed that downloading the updated GitHub scripts restored operation. Copying rendered web text can introduce an extra BOM; the repository scripts retain a single UTF-8 BOM for Windows PowerShell 5.1.

**Published:** [Codex Portable 0.164.0 - Portable r1](https://github.com/rileyaaa/Codex-Portable/releases/tag/v0.164.0-portable.1), source `f4c0c4706fd052bdddc8b33207c6f2ea0145c4d1`, contains 8,689 customer files in a 534,778,576-byte ZIP. Archive SHA-256: `bd3971f7d7633fd1260dedafa1e9a1aa88c6f0ddfaddca38d7406353a3409a5b`. The known-broken `v2026.10.26` Release and its assets were removed after the replacement was verified; Git history and the old tag remain available for traceability.

**Validation:** Manual Windows [run 40267390511](https://github.com/rileyaaa/Codex-Portable/actions/runs/40267390511) passed in approximately 4.5 minutes. The scoped hotfix gate verified the allowed source diff and unchanged default environment assignments against full Windows baseline `8e09466f` (run 40253783757), checked native version, mode copies and packaging regressions, and ran the PowerShell 5.1 model/configuration checks including 34 model-option and 11 interactive-dispatch cases. Client/Host and dependency payloads remain unchanged. Prior offline native-client comparisons verified standard Responses over the project HTTP/SOCKS bridge without real credentials or paid model calls. The customer ZIP excludes first-party tests, CI, Git configuration, development builders and user state. All three uploaded assets were downloaded and verified; ZIP contents were checked individually before publication, and the latest-release metadata and published checksums were checked again afterward. Runner temporary files were cleaned, with no Actions artifacts or caches retained. This scoped run does not count as a new full Windows suite, real account login, live Agent/Host call or device acceptance test.

## 2026-10-26：自定义 API 的标准 Responses 兼容

**原因与修复：** 官方 0.164.0 内置 gpt-6.1-sol 等模型条目启用了 `use_responses_lite`。与原包 0.156.1 对照发现，新客户端即便 provider 声明 `wire_api=responses`，仍会自动发送内部 Lite 标记、additional_tools 等不同结构。现在自定义 API/本地 provider 总是生成包内兼容 catalog，在保留模型 slug、上下文与其余原生元数据的同时将 `use_responses_lite=false`；官方账号继续使用原生目录。保留 1080 等用户配置的代理端口，不改认证、模型名称或权限。

**实际验证：** 在包内独立 tmp 下载并核验两个官方 Linux 工件，两个版本均经项目原有 HTTP→SOCKS5 桥与本地模拟 1080 端口请求假接口。原包与新版均原样请求 `gpt-6.1-sol`；新版修复后不再发送内部 Lite 请求头及 additional_tools，标准 tools/消息结构的请求成功收到合成回复。不使用真实 Key、不调用收费模型；非测试目标均被模拟代理拒绝。手动检查器 `tests/check_responses_wire.py` 已保留：原 0.156.1 标准请求通过，未使用兼容目录的 0.164.0 会明确检出 Lite 请求头，使用生产函数生成的目录后通过。它仅供源码维护使用，不进入客户包，不自动下载客户端。这证明请求协议与代理链；随后用户已确认直接下载 GitHub 脚本恢复正常。该 Linux 对照本身不称为 Windows 原生测试。

## 2026-10-26：真实交互启动与后台服务冲突

**原因与修复：** 用户真机反馈 `CODEX_HOME must be outside the source CLI package`。固定 0.164.0 的共享后台服务安装器拒绝 CODEX_HOME 位于源 CLI 包内；此前 `--version` 和 `features list` 检查没有覆盖自动后台服务准备。最终交互启动统一附带官方 `--no-daemon`，普通 TUI、提示文本、resume/fork 均覆盖，显式参数不重复追加；exec、登录和配置管理调用保持原有参数。CODEX_HOME 保持包内，权限、认证、Fast 和 Host 身份不变，模式副本同步。普通 Agent/Code Mode 使用嵌入服务，跨进程共享后台服务不启用。

**验证与边界：** 生产最终分发函数的 11 组参数/退出码检查与模式副本检查通过；用户已确认直接下载原文件后恢复正常。此前 `--portable-auth last` 不能代替显式 API 选择，排查时须保留用户实际代理条件。云端 ConPTY 驱动未能稳定识别终端界面，已移除新增驱动与临时检查选项，不将失败或版本输出当作交互测试成功，不新增长期测试依赖。

## 2026-10-26：独立审查后的目录与数据保护修复

**原因与结果：** 默认 PATH 移除带历史绝对解释器路径的 vendor Python bin，五个 BAT、Android 子入口与模式副本同步；已有通用 CMD 入口保留，PyInstaller 继续使用包内 `python -m PyInstaller`。严格入口拒绝内部 `tcp-tunnel`，避免未审核的文件读取与网络服务入口。修正打包来源清单中的旧入口说明。

**数据保护：** 未知 SQLite 索引先复制 DB/WAL 到包内 tmp，再由 SQLite 识别归属；拒绝时不打开原库，避免 checkpoint 或 SHM 改写。指令安装在两份输出都提交前保留原 MD 的逐字节备份，配置失败恢复旧 MD；回滚受阻时保留包内恢复文件并明确报错。Python shim 刷新先验证一级 dist-info 目录，再检查元数据文件，避免 glob 提前枚举链接目标。

**转换器：** 预览按实际凭据及其 JSON/URL/shell 表示隐藏值，复制/下载仍为原内容。dotenv 对含特殊字符的值安全引用；换行、NUL 和无法一致引用的值不生成配置，提示改用 JSON，避免截断或注入额外配置项。

**验证范围：** 新增第二份配置提交失败、崩溃残留 WAL 原文件保持、链接元数据拒绝前不得枚举、默认 PATH、内部子命令拒绝及凭据/ dotenv 语义回归。合成测试不读取真实账号；Windows 完整验证和发布状态以对应手动工作流实际结果为准。

**发布结果：** 完整 Windows 验证及附件回读通过，正式版为 `v2026.10.26`，来源 `8e09466f`；完整结果与真实使用待验范围见文末。

## 2026-10-25：撤销多余打包封装并复查

**范围：** 按用户要求保留已恢复的 PyInstaller 与必要依赖、许可证和来源记录，撤销上次额外加入的专用 CMD、自定义参数／路径封装及其专属测试。通用 Python CLI helper 恢复为此前已验证的原文件，不改变其他命令；原有依赖闭包、历史对象核对保留，Windows 版本测试改用原生 `-m PyInstaller`。现行使用说明同步为 AI 按任务调用原生模块并遵守包内路径约定。此前 PDF、Office、Android、账号保护及所有官方组件不变。

**复核与测试修正：** 首轮三个全新 Linux runner 对相同源码的 164 项回归均通过。随后完整 Windows 工作流 `40206266734` 发现 4 条 PDF 测试在清理阶段报 WinError 32：测试自身用于核对索引的 `with sqlite3.connect(...)` 只结束事务、未关闭连接。现仅将这四处改为 `contextlib.closing`，原有数据保护断言、生产脚本、官方组件及发布门禁不变；未通过的发布已提前取消，没有打包或上传。独立连接审计在原测试复现 4 个未关闭连接，修改后为 0。

**重新复核：** 测试修正后重新计数：Actions `40207107803` 的三个全新 Linux runner 对固定提交 `fc188e9ab77617698a8b348759f56744662eb9c9` 分别正序、逆序和固定随机顺序执行 164 项源码／元数据回归，失败、错误、跳过和遗留 SQLite 连接均为 0；每轮浏览器离线策略、转换器、源码解析和 PowerShell 离线契约均通过。Windows 原生项目留待同一最终提交的完整发布门禁，不借用此前未完成的 Windows 结果。

**发布边界：** 仅当三轮复核通过后，才清理本次临时工作流并请求既有 release.yml 的 check_set=full。完整 Windows 验证、干净提交打包、上传附件回读全部通过才发布；实际状态以 Release 和对应工作流为准，不用源码检查冒充 Windows 通过。真实账号、在线 Agent/Host、提权沙箱、任意 PyInstaller spec/hook 的实际冻结产物与真实设备不在本轮范围。


## 2026-10-25：按授权恢复 Python EXE 打包工具（不编译、不发布）

**来源与范围：** 以 `ea68ed98de7a1e92a8ccccb4430347917dab0dc9` 为基线重新检查。确认 PyInstaller 在精简时被移除；按用户本次明确要求，从 `fcaf45e5dfe4c97f096475f211a423b6d882c4ae` 恢复 PyInstaller 6.21.0、hooks 2026.6、altgraph、pefile、pywin32-ctypes、setuptools 及元数据/许可证，保留当前 packaging 26.2，不升级其他运行库。`tool/python-build-manifest.json` 记录所用历史 Git 对象；`_distutils_hack` 只恢复源文件，不恢复旧 `__pycache__`。不恢复 Go、uv 或宿主编译器，不改 Codex/Host、认证、权限、扩展开关或已有 PDF/Office/Android 修复。

**便携入口：** 新增由现行生成器产生的 `tool/bin/pyinstaller.cmd`，沿用现有 Python CLI helper，避免直接执行嵌入旧绝对路径的 vendor EXE。通过固定版本原解析器保留普通脚本、既有 spec 和 `--` 后参数语义；固定包内解释器，先检查主输入和受管目录，暂存限 `tmp`、缓存 `cache/pyinstaller`、默认产物/spec 为 `work/dist`/`work/spec`。失败只清理本次临时目录并恢复进程环境。其他 Python CLI 仍走原入口。固定依赖清单从 36 项增加为 42 项；原锁摘要失效时仍拒绝使用，不伪造历史 wheel 哈希。

**三轮复核：** 最终代码在三个新进程分别正序、逆序、固定随机顺序执行 179 项可本地运行的 Python 测试（含新增 19 项包装入口/路径/状态回归），三轮均无失败、错误或跳过。每轮另通过 8 项离线浏览器策略及转换器 12 项输入/映射、8 项模板、18 项界面/ZIP/账号库检查；第二轮另通过 24 个真实 ZIP/文件系统独立子进程场景，第三轮核对 102 份 Python、10 份 JavaScript 语法和 Office 三副本一致性。本轮未再确认新的遗留生产 Bug，没有为了检查而修改无关正常逻辑。新入口测试以替身捕获参数和环境，不执行 PyInstaller 构建引擎，不把这些结果当作 EXE 打包成功。

**提交与未验证边界：** 仅提交恢复组件、便携入口、原有依赖测试的扩展、新入口回归及既有三份文档；不启动 Actions，不编译 EXE，不生成客户包或修改 Release。完整 Git/LFS/原生运行环境依赖的 5 个测试模块和 3 个单项未在本地运行；已为后续完整检出增加历史对象一致性和 Windows `--version` 检查，但本轮不计为通过。实际 Windows 冻结产物、任意第三方 hook、真实账号/设备与完整 Windows 发布验收仍待单独验证。入口只是路径/状态管理，不是执行沙箱；spec/hook 是可信代码才能运行。三轮源码复核不保证所有场景绝对无 Bug。

## 2026-10-25：Office 解压链接边界与失败句柄保护（源码已提交）

**原因与修复：** 以 `cd6e46542c8debc44a2300d7bfedc08de7d42ec0` 为基线，复现 `safe_extract` 先解析成员路径、后检查链接，导致解压可沿已有内部链接或悬空链接写入重定向目录；ZIP 成员打开失败时，输出文件尚未进入上下文管理，清理时句柄仍然打开。现先用不跟随目标的检查验证完整祖先链，再解析成员路径；先接管输出句柄，再打开 ZIP 成员。三份 Office helper 同步，保留独占创建、已有文件保护、正常 XML／二进制内容和失败清理。不修改 PDF／Android 已有修复、认证、普通／YOLO 权限、Fast、扩展开关或官方组件。

**复现与三轮本地复核：** 在原测试文件新增 7 项回归，未修复 helper 出现 5 项失败，修复后相关 17 项全部通过。最后一次生产修改后，新进程正序、逆序、固定随机顺序分别执行 160 项可本地运行的 Python 源码回归，三轮均无失败、错误或跳过；每轮另通过 8 项离线浏览器策略，以及转换器 12 项输入／映射、8 项模板和 18 项界面／ZIP／账号库检查。第二轮 24 个独立子进程覆盖三份 helper 的真实损坏 ZIP 文件头、CRC 错误、内部／外部／悬空链接、硬链接冲突、路径穿越、正常提取与重新封装；原实现对照 24 场景检出 12 个预期失败，另 12 个正常控制仍通过。101 份 Python、10 份 JavaScript 语法及 Office 副本一致性通过。所有样本为包内 tmp 中的合成数据，没有调用真实账号、设备或外部服务。

**提交与边界：** 修复与测试已通过 GitHub 连接器提交至 main，并回读校验文件摘要；原始补丁及三轮本地日志保留。按用户最新要求，不启动 Actions、不编译、不构建客户发行包、不发布或覆盖 Release。Windows／PowerShell 5.1、真实 Chromium、完整原生依赖及真实 PDF 提取本轮未运行；5 个依赖模块和 3 项依赖完整 Git/LFS 的检查另列未执行，不计入通过数。三轮结论仅限本次源码与合成场景，不保证所有场景无 Bug，也不宣称消除校验与系统调用之间全部竞争窗口。

## 2026-10-25：Office／Android 暂存目录与失败句柄保护（仅源码提交）

**原因与修复：** 以 `15c340fc82dea15c2ded1fde753848070b0415cc` 为基线，复现 Office 重新封装、Android 文本写入／复制／提取仍在持久输出目录创建暂存文件，且损坏的包内 `tmp` 未在创建输出目录前拒绝。现统一先校验并准备当前包的 `tmp`（Office 使用既有 `tmp/office`），再创建输出父目录；保留原子替换、正文／二进制内容及失败时仅清理本次暂存的行为。另复现 Android 复制源打开失败时暂存描述符未关闭，调整上下文管理器顺序，先接管暂存句柄再打开源文件。三份 Office helper 同步，未改动已有 PDF 修复、账号转换器、认证、权限、扩展开关或官方运行组件。

**三轮本地复核：** 原有三份测试文件新增 13 项回归；独立未修复源码对照检出 15 个失败断言（含参数化子案例，错误与跳过均为 0），修复后相关 40 项测试通过。最后一次生产修改后，分别在新进程正序、逆序、固定随机顺序执行 146 项可本地运行的 Python 源码回归，三轮均无失败、错误或跳过；每轮另通过 8 项离线浏览器策略，以及转换器 12 项输入／映射、8 项模板、18 项界面／ZIP／账号库检查。第二轮额外用 40 个独立子进程及实际文件系统审计验证中文／空格路径、搬迁和旧环境变量、链接／文件型 tmp、输出失败、源文件中途消失、截断流与编码失败；第三轮核对 101 份 Python、8 份 JavaScript 语法、Office 副本一致性及固定修复文件摘要。三轮在本次范围内未发现新的可复现问题，测试只使用包内 tmp 中的合成数据，不操作真实账户或设备。

**提交与边界：** 按用户最新要求暂停编译和发布，本次不触发 Actions、不构建客户发行包、不创建或覆盖 Release；仅提交修复、原有测试及本记录，并移除遗留一次性取消工作流。Windows／PowerShell 5.1、原生组件、实际 Chromium、完整依赖和真实 PDF 提取验收未在本轮执行；缺少完整 Git/LFS 检出的 3 项检查及 5 个原生依赖测试模块明确列为未运行，不计作通过。上述三轮是本地源码复核，不替代今后发布前的完整 Windows 验收与附件回读，也不保证所有场景绝对无 Bug。

## 2026-10-25：PDF 资料库原子写入暂存边界

**原因与范围：** 在 `adf8b0c9d3fbea5ca181b03a44f7e9512d33d989` 复现正文及报告的原子写入把 `.pdf-library-*` 暂存文件放在持久库目录，而非包内 `tmp`。现先校验并准备当前包的 `tmp`，再创建输出父目录和独占暂存文件；保留原有 UTF-8/LF 写入、原子替换及失败清理逻辑。不改变 PDF 提取、SQLite 归属、用户正文保护、账号转换器、认证、权限或运行组件。

**复现与前两轮：** 原有 128 项源码回归通过，但未覆盖暂存位置。原数据库测试文件新增 5 项纯合成写入回归，旧实现共 12 项中 3 项失败，修复后 12 项全部通过。第一轮重新运行 133 项源码回归、8 项浏览器策略以及转换器 12 项输入/映射、8 项模板和 18 项界面/ZIP/账号库检查，并核对 573 份源码、6,941 个跟踪路径及 Python/JavaScript 语法；第二轮新进程逆序通过同组 133 项，并用 10 个独立子进程检查 Unicode、大文本、搬迁、链接、替换失败和编码失败，独立核对 6,893 个客户路径及 48 项开发文件排除。两轮未发现新问题；临时产物仅在本轮包内 tmp，测试未使用真实账号。

**第三轮与发布门禁：** Actions `40183181411` 的全新 Linux/Windows runner 检出修复提交 `057a49ed362bd78e3f2eacf47a2ef961d4986374`：134 项随机顺序源码回归无失败、错误或跳过，浏览器策略、转换器、101 份 Python 和 41 份 PowerShell 解析及离线策略通过；Windows 包内 Python 的 159 项回归（含真实 PDF 提取与本轮暂存检查）、20 项 Node 回归、真实 Chromium、账号库、Cookie 持久化和主动清理均通过。本地 133 与 CI 134 的差异为完整 Git 检出的文件清单检查。修复后三轮连续未发现新的可复现问题。已下载校验的临时源码 artifact 主动删除，本工作流随记录清理；再由未修改的 release.yml 对最终提交完整验证、打包及上传回读，成功后才发布新版本。真实账号、在线 Agent/Host、提权沙箱和真实设备未测；三轮通过不是所有场景绝对无 Bug 的保证。
**后续补丁（只提交源码，不启动 Actions）：** 后续检查还发现：初次核对索引的生成 Markdown 后，耗时的 PDF 渲染可能与用户新建／修改／删除 Markdown 交错，旧流程会覆盖新内容；删除源 PDF 时，旧流程可能删除初检后刚被用户修改的 Markdown。现在输出写入时在暂存文件准备完成后、最终替换之前再次检查旧文件 SHA-256 或新文件必须不存在；删除旧源输出前再次校验归属。原有的正常增量复用、输出原子替换与失败暂存清理不变。新增 7 项合成场景覆盖渲染及暂存期间的新增、修改、删除、旧源清理与正常增量；原有源码负例中 4 项失败，修复后本地三轮可运行回归通过。该检查不能宣称消除检查与系统调用之间的所有极短竞争窗口；Windows 原生与正式发布验收未执行，仍待后续单独验证。

## 2026-10-25：转换模板的字符串与命令参数保护

**原因与修复：** 从 `1326836bfc5a578b23455b1bcbd08403032e8bf6` 复现两类模板问题：LiteLLM YAML 的动态字段没有作为字符串编码，`#team` 被当作注释、`true` 密钥被当作布尔值；cURL 草稿直接插入 URL、凭据和多行账号名，`&` 会拆分命令，变量与引号会改变实际参数，账号名换行会脱离注释。现仅对 YAML 动态标量做字符串编码（含 YAML 特殊换行），对 POSIX cURL 的 URL 和凭据做字面量引用，并逐行保留账号名注释。未提供凭据时保留原 OPENAI_API_KEY 环境变量占位。保留账号内容、识别规则、其他输出格式及既有账号库保护，不修改 Codex/Host、认证、权限、扩展默认值或运行工具。

**本地复现与前两轮检查：** 在原 smoke 中新增 8 项模板回归，未修复代码 8 项失败，修复后全部通过。第一轮 128 项 Python 源码回归、8 项浏览器策略、12 项输入/映射和 18 项 UI/ZIP/账号库检查通过；解析 101 份 Python、9 份第一方 JavaScript，并核对 573 份源码及 6,941 个跟踪路径。第二轮在新进程逆序复核同组 128 项源码回归；独立 YAML 解析器验证 500 组字符串往返，真实 POSIX shell 以无联网的 curl 替身验证 98 组参数，另对照 24 组原实现输出，确认除 YAML/cURL 及文件包中对应 cURL 内容外均逐字节一致。两轮未发现新的可复现问题，所有输入均为合成数据。

**第三轮与发布门禁：** Actions `40179590268` 的全新 Linux runner 检出修复提交 `45b8cffcbf8af8fb11c31e152180340457292833`：129 项随机顺序 Python 源码回归无失败、错误或跳过，8 项浏览器策略、12 项输入/映射、8 项模板和 18 项 UI/ZIP/账号库检查全部通过；101 份 Python、41 份 PowerShell 解析，以及 33 项模型参数、12 项权限显示、9 项登录保护、7 项登录流程与共享 URL 契约也通过。129 与本地 128 的差异是完整 Git checkout 额外执行实际跟踪清单检查。修复后三轮连续未发现新的可复现问题。本记录与临时审核工作流清理后，仍须由未修改的 release.yml 对最终提交执行 check_set=full；Windows 包内运行环境、PowerShell 5.1、原生启动链、浏览器、干净源码打包及上传附件回读全部通过才发布新版本，不覆盖已有 Release。实际发布状态和来源提交以新 Release 为准；本次未导出新的源码 artifact。真实账号、在线 Agent/Host、提权沙箱及真实设备未测，三轮源码复查不能冒充 Windows 验收或所有场景无 Bug 的保证。

## 2026-10-25：账号库与异步导入保护

**原因与范围：** 在 `fd915c83521bf7b1de786ac9334a6c9d8749c580` 上重新复现三项尚未入库的账号库问题：大密文展开为函数参数导致导出栈溢出、异步导出读取了点击后变更的状态、无效导入在失败前已替换原状态。现分块编码 Base64、在首次 await 前固定导出快照、先校验完整导入内容再更新页面。另复现旧 FileReader/解密异步任务覆盖后续清空、编辑、转换或新文件的问题；增加输入版本标记，丢弃过期导入结果和错误提示。保留远端已修复的包装数组和规则映射代码与测试，不改动账号库 v1、PBKDF2-SHA256 150000、AES-GCM、认证、权限、Fast 或官方工件。

**复现与验证：** 旧账号库代码在新回归中失败 5 项；仅修复账号库而未加异步保护时，新增 5 项竞争回归全部失败。最终本地版本的 18 项 UI/ZIP/账号库检查及原有 12 项 smoke 回归均通过。第一轮正序 128 项 Python 源码回归、8 项浏览器策略通过；第二轮分两个新进程逆序跑完同组 128 项，并通过独立 Python/Node 加密交叉验证：8 次解密（最大明文 1189316 字节）、16 次错误密码/篡改拒绝、10 组 Base64、1331 组包装输入、10 种无效导入保护、5 次兼容导入、21 组代理边界和 10 个 Python CLI 子进程场景。本地两轮未发现新的可复现问题，未使用真实凭据。

**第三轮与发布门禁：** Actions `40176018534` 在全新 Linux/Windows runner 检出修复提交 `7a2847eeeed89769a90fba18de619a537347b798`：129 项随机顺序源码回归无失败、错误或跳过；浏览器策略、18 项转换器检查、既有包装/映射 smoke、PowerShell 解析及离线策略通过。包内 Windows Python/Node、真实 Chromium Web Crypto/FileReader、大账号库往返、错误密码保留、清空取消导入、既有 HTML/ZIP/规则映射、截图、Cookie 持久化及主动清理均通过。三轮连续未发现新的可复现问题。临时源码 artifact 已主动删除，本工作流随本记录一并移除；正式发布仍由原 release.yml 对最终提交执行 check_set=full，完整验证、打包、上传回读全部成功后才发布，不覆盖已有 Release。真实账号、在线 Agent/Host、提权沙箱及设备未测，三轮通过不等于任何场景绝对无 Bug。

## 2026-10-25：包装数组与字段映射的后续复查

**原因与修复：** 以已发布 `v2026.10.25.1` 的 `a716f58213b523215fbca2742575f2b57e1ad205` 为基线，再次复现两类转换器问题：`data/items` 是元数据、后续字段才是数组时，原逻辑仍选中前面的非数组并报错；规则映射会读取继承属性，破坏 `constructor/toString` 等合法 JSON 键，映射到 `__proto__` 还会改变结果原型并丢失字段。现只调整数组选取、规则自有属性判断和普通数据属性写入三处，不改变合法数组优先级、账号内容、认证或输出格式。新增 12 项输入/映射回归，旧代码稳定失败 8 项，修复后全部通过；既有 Windows 浏览器测试增加真实页面导入和规则映射检查。

**本次验证：** 第一轮重新通过 128 项 Python 源码回归、8 项浏览器策略、转换器 smoke/UI/ZIP 检查，解析 101 份 Python 和 10 份 JavaScript，并核对 573 份源码及 6,941 个跟踪路径。第二轮使用独立 Python 参考实现核对 512 组包装字段组合和 200 组递归映射输入，另执行 10 个独立 Python CLI 场景及逆序 128 项源码回归，均未发现新问题。第三轮 Actions `40173977873` 在全新 Linux/Windows runner 检出修复提交 `0309d53936090e48def86125c8cf832cd39055d2`：129 项随机顺序 Python 源码回归无失败/错误/跳过，浏览器策略、转换器及 PowerShell 解析/离线策略检查通过；Windows 包内 Python/Node、真实 Chromium 页面导入/规则映射、既有 HTML/ZIP、截图、Cookie 持久化和清理检查也通过。三轮连续未发现新的可复现问题。完整发布仍须对清理后的最终提交执行原有 `release.yml` 的 `check_set=full`，只有打包及上传附件回读通过后才发布 `v2026.10.25.2`，以对应 Release 的实际来源提交和运行结果为准。

**范围与边界：** 仅修改账号转换器、对应原有测试和两份既有说明，不变更官方 0.164.0 工件、普通/YOLO 权限、Fast、MCP/Plugins 默认值或用户状态。所有输入均为合成数据；三轮复查通过不等于所有场景绝对无 Bug，真实账号、在线 Agent/Host、提权沙箱和真实设备仍不在本次验证范围。正式发布须沿用完整 Windows 门禁，不覆盖已有版本。

## 2026-10-25：辅助工具、账号转换器修复与三轮复查

**Python 用户文件保护：** `88967f671569296a3fdcc5b8c155201f53805582` 修复刷新器覆盖同名用户 CMD，以及指令安装在无效本地配置被拒绝前覆盖旧指令的问题。刷新前和原子替换前核对生成内容归属；用户修改保留，并以既有状态码 3 报告未完成项。指令安装先预检本地配置，再写入指令；写入和替换前拒绝链接、硬链接及非普通输出。原 30 项测试通过；新增 23 项后旧实现有 19 项失败，修复后 53 项通过。配置预检不等于跨两个文件的事务保证，也不声称完全消除并发竞争。

**本轮祖先检查修复：** `6cf2e4d618beec24350643224f5aa4c0e6e0f7fe` 修复命令刷新器从包根向上检查、先查询链接后方目录再拒绝的问题；改为从文件系统根向下检查。两项父级/更高层链接回归在旧代码稳定失败，修复后命令刷新 24 项及指令安装 31 项全部通过。正常 CMD 模板、认证、普通/YOLO 权限、Fast、扩展开关、模式副本和官方 0.164.0 工件均未改变。

**本轮账号转换器修复：** `3c0f043b2f3749c1492f30c87fa9d0925c7e121c` 修复导入账号 `type` 直接进入识别区域 HTML，以及 ZIP 的 UTF-8 文件名字节未设置编码标志、中文名被误解码的问题。仅补现有 HTML 转义及 ZIP 本地头/中央目录的 UTF-8 标志，不更改账号内容或转换格式。新增四项真实页面处理函数/ZIP 回归，旧代码稳定失败两项、修复后全部通过。既有 Windows 浏览器测试增加真实页面文本显示、无注入节点及 Unicode ZIP 检查，并保留原版本、渲染、截图、跨进程 Cookie 持久化和显式缓存清理检查。

**最终重新计数的三轮复查：** 发现转换器问题后停止尚未打包的 `40159811138`，此前三轮不再作为新修改的最终验收。第一轮对最新修复的源码副本重新执行 128 项 Python 回归、8 项浏览器策略、账号转换器 smoke 和四项 UI/ZIP 检查，均通过。第二轮重新执行 13 个独立 Python 进程场景、11 组代理/路径/发行清单边界；另以独立 Python HTML 解析器检查九类导入字段，以标准 ZIP 解码器检查八种多语言路径、原始内容和 CRC，全部通过。第三轮 Actions `40161313406` 在全新 Linux 和 Windows runner 检出上述同一转换器修复提交：129 项源码回归无失败/错误/跳过，8 项浏览器策略、转换器测试、101 份 Python 与 41 份 PowerShell 解析，以及 33 项模型参数、12 项权限显示、9 项登录输入保护、7 项登录流程和共享 URL 契约检查均通过；Windows PowerShell 5.1 和真实配套 Chromium 的新增页面/ZIP、截图、Cookie 持久化与清理检查也通过。129 与 128 的差异为完整 Git checkout 额外执行实际跟踪清单测试，不是重复引用旧日志。三轮均未发现新的可复现问题。

**发布门禁与边界：** 清理临时审核工作流并更新本记录后，既有 `release.yml` 必须对最终提交重新执行 `check_set=full`；完整 Windows 启动链、中文/空格路径、权限、MCP、Python/Node、浏览器、干净 Git/LFS 打包及上传附件回读全部通过后，才允许发布 `v2026.10.25.1`。实际发布状态、来源提交和完整验证链接以对应 Release 为准，不覆盖 `v2026.10.25`。本次私有源码 artifact 已主动删除，不长期保留自动触发入口。测试只使用合成账号/传输/设备输入；真实账号刷新、全部在线 Agent/Host、提权沙箱及真实设备仍未测。三轮通过不代表所有场景绝对没有 Bug。

## 2026-10-25：SQLite 归属检查与发布复查

**PDF 手册库数据库保护：** 原归属检查在拒绝无关 SQLite 文件前先设置 journal_mode=DELETE，会改变既有 WAL 数据库；仅检查 table 也会误认领只有 view 的数据库。现先检查 application_id 和所有持久 schema 对象，确认是本工具库或空库后才设置日志模式；拒绝时不改写无关文件。只调整 PDF 手册库的数据库初始化顺序，不改转换内容、索引格式、认证、权限或官方工件。新增 7 项纯合成数据库回归，旧实现稳定复现 2 项失败，修复后 7 项通过，覆盖外部归属、视图库、WAL、空库、既有库和只读打开。修复后独立运行 40115142380 依次在全新 Linux 和 Windows runner 检出同一修复提交：102 项 Python 合成回归、源码解析与生产策略函数检查，以及现有 20 个 Windows 验证组全部通过；新增 7 项数据库检查也在包内 Windows Python 执行通过。第二轮未发现新的可复现问题；不等于所有场景无 bug，真实账号、在线 Agent/Host、提权沙箱及设备操作未测。本任务仅修复和验证，不构建或发布 Release。

## 2026-10-24：0.164.0 配套升级与配置兼容

**原因与结果：** 中断期间官方发布 [0.164.0](https://github.com/openai/codex/releases/tag/rust-v0.164.0)，Codex/Host 及配套助手、搜索程序成对更新；六个运行文件约 464.5 MB，官方 ZIP 摘要、PE 架构、许可证与完整布局已核验，保留原始 EXE 字节。继续省略 39 个语音文件和两份重复助手；固定身份、登录版本映射和模式副本同步。

**变量复核：** 44 个有效 `CODEX_*` 默认赋值仍有生产消费者，provider、Fast、扩展、文件凭证存储和默认 unelevated 沙箱映射继续有效。`realtime_conversation` 已成为 Removed feature，删除失效赋值；有效 App 语音/听写开关保持 false，TUI 的 `toggle_voice` / `toggle_voice_mute` 设为空绑定。上游仍可显示 `/voice`，本包不支持语音，不宣称已隐藏该命令。模型目录与上一版一致，Luna 默认仍为 medium。新增的 64 位 HKLM 固定策略键 `SOFTWARE\Policies\OpenAI\Codex` 的 `RequirementsPath` 会改变官方系统策略文件来源；启动器先检查该值名是否存在，未明确允许宿主策略时拒绝启动，不读取它指向的文件。显式允许宿主策略时保持上游行为。参见官方[系统策略加载](https://github.com/openai/codex/blob/rust-v0.164.0/codex-rs/config/src/loader/mod.rs#L819)、[语音 feature](https://github.com/openai/codex/blob/rust-v0.164.0/codex-rs/features/src/lib.rs#L432)和[默认 Windows 后端](https://github.com/openai/codex/blob/rust-v0.164.0/codex-rs/windows-sandbox-rs/src/unified_exec/mod.rs#L59)。

## 2026-10-24：Windows 验证与 npm 目录边界

**Python 命令入口刷新：** 修正清理时仅凭 helper 文件名子串判断归属、误删用户自建或改写 CMD，以及当前 vendor 缺少入口元数据时误删原命令的问题；只删除与本工具生成内容逐字节一致且已无对应 vendor 的旧入口，无法确认的文件保留。替换暂存统一放当前包内 tmp，并拒绝链接/硬链接输出；正常 CMD 模板字节不变。本项不改 Python 依赖、启动器、认证、权限或官方工件。11 项新增合成回归中，旧实现有 6 项失败，修复后全部通过；本轮全部修复提交后依次用全新 Linux 与 Windows runner 复查，95 项 Python 合成回归、源码解析与生产策略函数检查，以及现有 20 个 Windows 验证组全部通过。验证运行 40110404921；本任务只验证和记录，不构建或发布 Release，不使用真实凭据。

**模型列表请求契约：** 修正生产 Invoke-Models 构造 client_version 查询参数、但 PowerShell 与 Python 双层白名单全部拒绝查询参数的联动错误。仅模型列表固定 HTTPS 端点可带单个数字三段版本；刷新/额度端点仍禁止查询参数，域名、端口、请求方法、请求体、敏感头与禁止重定向规则不变。共享 7 个合法和 26 个非法 URL 用例，Python 额外验证方法/请求体/头限制；PowerShell 直接调用实际模型/额度请求构造函数和实际双层校验，最终传输为合成 stub。旧 helper 的四个合法版本 URL 失败已复现，修复后专项通过；修复后的两阶段独立复查 40110404921 已通过，Python 与 Windows PowerShell 5.1 均验证共享 URL 用例和实际请求构造；不声明真实账号联网已测。

**账号输入异常保留：** 修正账号检查将文件访问/解析异常、缺失索引及 LoadError 统一送入失效凭据删除分支的问题；错误索引不再导致删除整个容器。两处输入失败分支改为 ERROR_KEPT，避免后续多账号 prune，并抑制异常详情；成功解析后缺少必需字段、明确服务端认证失效及网络错误的既有分类不变。9 项生产函数回归全部使用合成对象，网络与删除均为 stub；旧实现可复现错误分类，修复后专项通过。修复后的两阶段独立复查 40110404921 已通过，9 项输入异常回归也在真实 Windows PowerShell 5.1 执行通过；测试不访问真实账号或认证服务。

**模型指令安装入口：** 单独调用 `tool/codex-instruct.py` 时，旧实现会先解析入口祖先或输入链接再拒绝，并在 home/包根暂存写入文件。现先做词法规范化，再从文件系统根向下检查祖先与普通单链接包标记；输入、自定义 home 和本机配置在跟随链接目标前拒绝，实际 I/O 使用同一规范化路径。原子写入的独占暂存文件改为当前包内 `tmp`，失败只清理本次暂存，不动其他文件。不改指令内容、持久配置格式、认证、权限或官方工件。合计 19 项合成回归覆盖入口/输入/输出链接、先拒绝后探测、暂存范围、失败清理、正常安装和真实搬迁；新用例在修复前可复现失败，修复后 Linux 合成回归通过。修复后独立运行 40105103992 在全新 runner 检出提交复查，81 项 Python 合成测试、42 份 PowerShell 解析及 CLI/权限提示/扩展迁移与持久化等生产函数回归全部通过，未发现新的可复现问题。Linux/PS7 不替代 Windows；完整 Windows 验收和发行附件回读仍为发布前置条件，最终结果以对应 Release 与 Actions 为准。

**权限状态提示：** 修正 YOLO 仍显示 SAFE/work/tmp 及只读模式套用 workspace-write 网络提示的错误。显示优先按实际 sandbox 模式区分；YOLO 明确不提供包外写入或命令网络限制，只读不冒充宿主进程完全不写入。仅修改提示表达式并同步模式启动器，不改权限、网络、认证和二进制。新增 12 种生产表达式组合回归，与模式副本检查一起通过专项检查；修复后全新检出的源码及生产函数回归再次通过，未发现新增可复现问题；完整 Windows 验收与附件回读仍为发布前置条件，最终结果以对应 Release 与 Actions 为准。

**扩展配置生命周期复查：** 修正维护命令整体回写导致未启用的 MCP/Plugin 配置丢失，以及旧 config 首次迁移只保存在内存、后续启动被拒绝时丢失的问题。旧扩展先在包内 tmp 独占写入、刷盘并原子提交持久文件，成功后才删除旧生成配置；失败保留原文件，已有持久文件（包括空文件）优先且不在启动时重写。管理命令需显式启用对应类型，成功后只回写该类型，另一类不变；查看无变更不写回，删除最后一项不复活。同步模式启动器，不改认证、权限或官方工件。迁移失败、目标冲突、链接拒绝、重启恢复及真实维护 MCP add/list/remove 均纳入回归；迁移、回写和 CLI 参数专项显式接入正式 Windows 门禁。 修复后从新检出的提交再次核对启动失败恢复、命名空间回写、CLI、模式副本、固定版本变量与发行门禁，源码及专项回归通过，未发现新增可复现问题；Linux/PS7 结果不替代随后完整 Windows 发布验收。

**CLI 模型参数：** 修正 `-m=模型名` 把等号并入模型名的解析错误，使其与分离写法及 `--model=...` 一致；空值拒绝，插件子命令的 `-m` 仍是 marketplace 参数。继续修正先写 TUI 提示词再写模型参数时启动器漏读覆盖的问题：按固定版本命令名区分子命令与提示词，保留插件 marketplace 参数和 `--` 边界。同时将 TUI 提示词与子命令生命周期状态分离，避免 `Logout` / `MCP` 等大小写不同的提示词误触退出登录或扩展管理逻辑；真正的小写子命令继续受原有权限约束。33 项生产解析回归覆盖参数形式、顺序、空值及命令边界；中文搬迁场景用 `Logout` 提示词实际验证短参数、生成配置与原生客户端的一致性，不执行真实退出登录。修复后从全新检出独立复查源码、固定版本变量、模式副本与扩展迁移/持久化，并增加 23 项提示词/真实子命令边界验证，均通过；本轮未发现新增可复现问题。该复查使用 Linux/PS7，不代替完整 Windows 验收；最终发行仍须全量 Windows 检查和上传附件回读通过。

**收尾复核与发布门禁：** 按固定 0.164.0 上游 schema、feature 定义和当前生产引用复核 42 项字面量默认设置及 2 项派生路径，未将仅预留工具路径当作已安装功能。源码检查 40067858314 通过 97 份 Python AST、11 份 JavaScript 语法、38 份 PowerShell 语法、5 个 BAT 的 ASCII/CRLF 和模式副本检查；其中 PowerShell 解析在 Linux/PS7 执行，不代替 Windows 运行。正式工作流保留原有全量检查，补入真实 BAT/客户端完整启动回归，并以固定客户端的只读 features/list 检查生成配置的实际加载与关闭开关，避免仅靠 --version 推断配置有效。上传先创建 draft，重新下载三个附件、比对 SHA-256 并逐项验证 ZIP/来源清单后才公开为非预发布；测试、下载和验证材料只使用本次包内 tmp。最终发布结果以对应完整 Windows 运行及 Release 附件为准。

**完整启动补验：** 新增真实 BAT → 启动器 → 固定原生客户端的离线回归，发现 PS5.1 / .NET Framework CodeDOM 在含中文的包内临时目录编译失败。仅将编译入口改为当前 Windows Framework 自带 csc、Unicode 子进程环境和 UTF-8 参数文件；源码、输出和清理仍限本次包内 `tmp`，监督器 C#、Job、标准流、模式和凭据逻辑不变。Windows 专项运行 40066085104 的普通、中文/空格改名搬迁、旧根仍存在及维护入口三组启动与生成配置、继承/捕获标准流均通过；该任务最后的文档写回失败，不将任务总状态记为成功。修复已按通过测试的精确字节提交，完整启动检查纳入后续正式发布门禁。

**标准流回归修复：** 全量运行 `40056474654` 中，已知编译临时目录保留提示导致 stderr 精确匹配误报。测试现仅接受这条提示出现一次，保留 stdout、退出码及捕获模式的严格检查；新增 14 个正反例。不修改生产监督器，不丢弃未知诊断，不放宽发布门禁。修复后已通过 [Windows 全量运行 40064538870](https://github.com/rileyaaa/Codex-Portable/actions/runs/40064538870)，该次仅验证不发布。

**原因与结果：** npm 的用户/全局配置虽位于包内，上游仍会从工作目录向父层发现项目 `.npmrc`。六个 npm/npx 入口现统一使用包内 Node 和固定项目根，保留经校验的显式包内 `--prefix`，配置和缓存路径先校验后加载；不依赖增加环境变量来假定隔离。实际 bundled npm 配置加载、参数保留及 Windows 入口纳入发布回归。

**Windows 修复：** 账号检查 BAT 的菜单提示包含未转义的右括号，导致 CMD 在解析分支时中止；现正确转义，保留原菜单行为。首次直接运行浏览器时由监督器安全创建缺失的包内 `tmp`，不再依赖先运行 BAT。进程监督器保守保留未能安全删除的包内编译临时目录，提示改写到 stderr，避免污染 MCP 的 JSON-RPC stdout；残留可由“清理缓存”回收，不进入发行包。Windows 专用入口和进程监督继续通过独立测试验收。

**验证约束：** Windows 工作流使用与便携入口一致的包内/系统 PowerShell 模块路径，各组检查单独显示结果并设有限超时。实测纯 PowerShell 启动约 0.26 秒，首次加载文件系统模块约 25 秒；合成测试使用 60 秒有限等待，较长的多进程测试组另设 8 分钟上限，不以无限等待掩盖失败。BAT 合成测试超时时按本次 PID 回收子进程树，避免只杀父进程后阻塞临时目录清理。

## 2026-10-23：发布复查与打包

**精简决定：** 复核后没有可无损删去的大块内容。C/C++ PDF 开发文件及两份搜索程序最多约可省 10.5 MB 解压体积；用户明确选择保留现状，修复 bug 后发布。没有删除这些候选；测试保留在源码中，客户 ZIP 排除第一方测试、CI 和打包脚本，模式模板与转换器运行文件继续交付。

**修复：** 之前只在依赖安装器中禁用了宿主 pip 配置，普通 Agent 命令仍可能经 Windows 系统路径读取 `pip.ini`。根启动器、五个 BAT、子进程环境和生成的 shell 配置现统一固定 `PIP_CONFIG_FILE=nul`，模式副本同步；真实 bundled pip 加载器的合成回归验证普通和 isolated 模式下均不读取配置文件。

**边界复查：** 修复 PPT 多张缩略图派生文件、Poppler 可执行文件和 Android 映射/规则输入漏验链接的问题；登录 HTTP helper 移除未使用的文件参数，只接收启动器传入的标准输入。Windows 实测暴露 Android MCP 的中文 JSON 响应受默认码页影响，现统一通过字节流输出合法 ASCII/UTF-8 JSON，并覆盖低码页及无效 UTF-8 后恢复处理。官方账号默认改用设备码，避免系统默认浏览器写入宿主资料；原方式仅在明确设置 `CODEX_BROWSER_LOGIN_FLOW=system_browser` 后启用，失败不自动回退，模式副本同步。

**浏览器：** 固定资料改为 `cache/browser`，任务结束关闭进程并保留 Cookies/登录；“清理缓存”统一删除，并与浏览器通过独立锁互斥。修复固定 MCP 上游关闭连接未必关闭浏览器上下文的问题，由包装器显式持有和关闭上下文。只下载固定官方 Chromium ZIP，不额外安装 ffmpeg、winldd、ChromeDriver 或第二套浏览器。

**发行准备：** 新增打包器，仅接受已提交且干净的完整 checkout，拒绝私密路径、链接、Windows 文件名冲突和 LFS 指针，验证固定运行包身份；ZIP 生成后逐项检查内容摘要与 CRC，另产出来源清单和 SHA256SUMS。补齐官方固定版本的 LICENSE/NOTICE，保留原始字节。新增手动发布工作流，在 Windows 运行回归后打包，上传 draft 成功才转为正式 Release；不创建长期 artifact 或缓存，结束后清理本次 runner 文件。真实账号、在线 Agent/Host、提权沙箱与设备操作仍不属于该工作流的验收范围。

**发布要求：** GitHub API 已恢复访问；Windows 发布工作流及最终 Release 是否完成以实际运行和远端附件为准，不能将本地 ZIP、代码提交或工作流文件当作已发布。

## 2026-10-23：DBA/Python 用途精简

**原因与结果：** 本地主要使用文字 Agent、Python 爬虫和数据处理，编译频率低。移除 Go、PyInstaller 及其专用依赖、可再生 Python 字节码、uv/uvx/uvw 和两份重复沙箱助手，项目文件由约 1,146 MB 降为 807 MB，减少约 339 MB（30%）；按解压后的受版本管理文件统计，不含 Git 历史、用户状态和尚未下载的浏览器。Python、Node、Office/PDF、现有 Android 和浏览器脚本依赖保留，36 个 Windows Python 运行包的依赖关系闭合。

默认 unelevated 沙箱使用客户端内置执行路径；两个根目录助手用于 elevated 沙箱。保留它们是因为 TUI 提权入口仍可达，缺件时上游可能按裸文件名查找程序；仅删除已核对同根目录优先查找的资源副本。当时的 0.163.0 运行文件为六个、约 446.3 MB，固定清单和模式副本同步更新。

| 关联问题 | 最终处理 |
| --- | --- |
| 删除编译工具后仍导出旧路径、创建空工具目录 | 五个 BAT 和启动器清除继承的 Go/uv 变量，移除 PATH、缓存骨架及生成配置中的对应项；正常和 YOLO 四份模板同步 |
| 安装器会补回 PyInstaller 和大范围可选依赖 | 改用已有 Python/pip，固定现有 36 个版本；仅接受官方 PyPI wheel，完整依赖加 SHA-256 锁，安装和导入成功后才发布新锁 |
| pip 覆盖安装会保留旧版本元数据、替换整个 CLI 目录 | 补装前拒绝版本冲突、重复或额外发行包及无法归属的入口；固定运行集可同版修复，跨版本升级另用受控暂存副本，避免静默损坏用户后来添加的工具 |
| pip 隔离参数仍可能加载系统配置，安装入口漏查包根祖先 | 显式禁用 pip 配置文件并固定索引；完整祖先检查早于 marker 访问，安装前检查 Python 树中的链接 |
| 文本输入大小限制误用于大型 EXE marker | marker 只检查普通文件与链接；32 MB 上限仅约束锁输入，回归包含大型稀疏 marker 和超限报告 |
| 依赖安装器会重写 dist-info/RECORD，导致原始字节摘要误报 | 四个 RECORD 从已安装文件摘要中排除；149 个运行/许可文件、官方完整 wheel 和源码摘要继续校验 |
| 自定义 header 示例使用受保护的 CODEX_* 名称 | 改为普通变量名，验证生成的子进程环境实际接收配置中的 header 值 |

从官方 PyPI 成功解析全部 36 个 Windows x64 / CPython 3.14 wheel，并生成、验证候选哈希锁；只做解析，没有在 Linux 冒充 Windows 安装。综合回归及待验范围见文末。未新增项目说明文档。

## 2026-10-20：文字/Agent 精简与联动检查

**原因与范围：** 用户确定不使用语音；此前分项回归不足以覆盖新运行包、进程监督和工具入口之间的依赖。本轮核对固定版本上游的资源查找、沙箱助手缓存和原生变量消费点，检查第一方脚本并执行现有综合回归，不将离线检查称为 Windows 全流程验收。

**精简结果：** 删除语音专用的 39 个文件，减少约 19.4 MB；保留主程序、Code Mode Host、搜索和两种沙箱助手。当时生成配置关闭 `in_app_voice`、`in_app_dictation`、`realtime_conversation`；最后一项在 0.164.0 已移除，当前处理见最新升级记录。资源目录中的重复沙箱副本已在后续 DBA 精简中移除，当前布局和取舍见 README。

| 联动问题 | 修复结果 |
| --- | --- |
| 仅校验主程序/Host，未覆盖新布局的 metadata、搜索和沙箱资源 | 启动前固定 manifest 摘要并验证全部所列文件；固定清单原始字节，防止 Windows 换行转换破坏新摘要；检查沙箱状态树链接及可复用助手缓存，不读取沙箱凭据内容 |
| 任意 `CODEX_*` 可通过本机设置进入原生客户端 | 本机配置只接受已核对的启动器设置，拒绝原生日志、跟踪和安装路径等未经审核的变量；既有支持项保留 |
| MCP 前台进程未显式继承管道，桌面中文输出可能按错误编码解读 | 监督器只传递三个标准句柄，保留 Job 管理和捕获模式；桌面 worker 明确输出 UTF-8，新增 Windows 实际标准流回归入口 |
| 浏览器目录先递归后查链接，MCP 元数据可再次改变工作目录 | 先逐层验证再遍历；移除上游 `_meta.cwd`，输出路径固定成已校验绝对路径，新标签 URL 同样限制为允许协议 |
| Android 反编译入口存在语法错误，Python 守卫漏查祖先/悬空链接 | 修正三处插值；补齐固定包根、完整祖先、单链接 marker、越界先拒绝及搬迁测试 |
| Office 子进程部分状态目录仍可继承宿主环境 | 三套 helper 同步验证并重定向 AppData、ProgramData、Public、XDG 等目录，先验证再创建临时目录 |
| 缺少 OCR 工具后，增量构建永久复用失败结果 | 相同文件和参数下也会重试此前 `missing` / `failed` 页；成功缓存仍可复用 |
| Git 忽略规则未覆盖沙箱秘密和运行状态 | 排除沙箱数据、日志、会话、扩展私密配置及缓存目录；确认这些目录没有已跟踪文件 |

根脚本改动及语音限制已同步四份模式文件；未新增项目说明文档。当前测试范围、结果和 Windows 待验项统一维护在文末。

## 2026-10-20：常用与 YOLO 模式同步

**原因：** 四份模式文件仍保留旧客户端身份及扩展默认值；这些是需要持续同步的发行模板，并非冻结历史。

**结果：** 常用两份与根文件完全一致；YOLO 启动脚本同步，env 只保留 approval、sandbox、network 三项差异。`strict` 在两种模式中都相同，Fast 和扩展默认关闭。`never` + `danger-full-access` 可避免权限批准等待，但会关闭执行器文件写入沙箱；路径重定向仍生效，不能据此保证任意命令绝不越界。严格写入边界使用常用模式。无人值守还需预先完成认证并选择非交互启动。

## 2026-10-20：统一浏览器与限定应用调试

**原因：** ChromeDriver 与 Chrome 分别更新容易失配；多套浏览器/MCP 增加便携包体积，默认桌面 MCP 的操作范围又过大。

**结果：** 仅采用一套固定 Playwright 依赖，共用一份配套 Chromium。任务脚本、可选 stdio MCP 与 CDP 诊断复用同一安装；无 ChromeDriver、第二浏览器或 Chrome DevTools MCP。进程用户目录、profile、缓存和临时下载落包内，退出时关闭本次进程；资料保留与统一清理见上面的维护约定。MCP 过滤任意 Node 执行、上传、安装、配置及客户端重定向根目录；任务脚本入口仍是受当前权限约束的代码执行，不能冒充不可信脚本沙箱。Windows 桌面入口使用系统 UI Automation，只读指定 PID 主窗口的有界树，修改动作需要额外开关，未安装通用 Windows-MCP。

**交付状态：** JS 依赖约 18.7 MB、185 个文件已安装并记录摘要；10 月 23 日通过官方 CDN/Google 存储取得唯一配套 Chromium，305 个文件约 458 MB（官方 ZIP 约 207 MB），来源和摘要记录在 browser-manifest.json。浏览器 payload 使用 Git LFS，发行 ZIP 包含实际文件。未使用下载 Actions 或生成临时 artifact；手动下载工作流保留为备用。

**附带修正：** PDF ZIP 摘要写回现有 `SHA256.md` 的最近导出记录，ZIP 内仍只含 Markdown，不自引用最终 ZIP 哈希，也不增加项目说明文档。复现了 Windows `core.autocrlf=true` 会改写新增官方 Python 文本文件、导致摘要失配的问题；`.gitattributes` 现固定 Python、Playwright 和客户端资源的原始字节，不改动上游内容。

## 2026-10-20：技能去重、任务开关与 PDF 检索

**原因：** Android 外层技能与插件内 17 组流程完全重复，维护模式会自动激活用户 MCP；大量 PDF 全文进入上下文造成额外开销，Office 技能存在“依赖已安装”等不准确说明。

**结果：** 删除 43 份重复 Android 文件，保留插件内完整流程与外层精简入口；保留 `mumu-adb` 和可作为离线模板资料的 OpenAI templates，移除不相关的 plugin-management 缓存及生成字节码。Plugins/MCP 默认关闭并增加本次会话开关；关闭时仍完整保存用户扩展配置。默认和自定义模型指令都加入任务授权规则，Fast 保持关闭。

Office 保留现有 OOXML/Python 工作流，改为用户模板优先、按需选择模板资料、检查实际渲染结果，缺失渲染工具不宣称成品已验收。新增 `pdf-library` 适配成熟 PyMuPDF4LLM：按页转换、原文字补充、SHA 增量更新、限长检索/读取与纯 Markdown ZIP；文字、代码、OCR 和视觉结构分别报告。安装经官方 wheel 与 RECORD 校验的 Windows PyMuPDF、PyMuPDF4LLM、tabulate、defusedxml，来源及文件摘要见 `tool/optional-python-manifest.json`。

**修复：** APK MCP PowerShell 入口的 `$Label:` 插值和路径拆分正则原本无效；已修复。MCP 启动增加明确任务开关，并提前检查完整路径祖先、链接和输入边界；不自动注册、启动或连接设备。

**验证：** 11 项 Android 子进程/路径测试、13 项真实合成 PDF 行为测试、11 项 PowerShell 扩展策略测试通过。PDF 测试在 Linux 使用匹配版本上游引擎；Windows payload 的摘要/架构检查不代替 Windows 实际运行。未执行 MuMu、Appium、真实桌面操作或用户文档转换。

## 2026-10-20：统一项目文档

**原因：** 项目使用、变量、维护规则和版本记录分散，存在重复、历史状态混入当前说明及过多过程描述。

**结果：** 文档归并为四个入口，维护限制集中到本文件开头；README 统一说明 Git LFS 工件获取、五个 BAT、配置、目录搬迁和换电脑迁移；工具文档集中下载来源、布局和更新；转换器保留独立说明。原根级规则、变量清单和变更日志的有效内容已合并，不再单独维护；功能性技能和第三方文档不因本次整理删除。开发记录改为日期、原因、结果及验证，过时事实直接更正。

**文档核验：** 清点 358 份 Markdown，读取并筛查项目维护约束；完整审阅项目主文档及相关技能规则。第三方文档用于确认归属与引用，不宣称逐字审计其全部技术内容。修正两份 Appium 技能的维护文档入口；转换器文档按实际代码区分预览脱敏、JWT 展示和静态离线说明。

## 2026-10-20：0.163.0 升级与变量兼容

**原因：** 原 0.156.1 runtime pair 需要升级；部分变量虽有声明，但未传到实际调用，或生成了过时配置值。

**结果：** 从 [官方 rust-v0.163.0](https://github.com/openai/codex/releases/tag/rust-v0.163.0) 的完整 Windows x64 ZIP 成对更新 Codex/Host，补齐沙箱及搜索资源；按当前文字/Agent 用途省略语音专用目录。仅把 metadata 的入口名称适配为 `codex.exe`；保留的官方二进制字节不变。来源、ZIP 摘要、实际文件及明确省略组件以 [runtime-manifest.json](tool/runtime-manifest.json) 为准，启动器和登录版本映射同步更新。

| 原因 / 兼容点 | 最终处理 |
| --- | --- |
| Python 登录后端忽略连接超时变量 | 将 `CODEX_LOGIN_JSON_CONNECT_TIMEOUT_SEC` 传入 requests 连接超时，默认 8 秒、上限 30 秒且不超过请求总限；PowerShell 后端仍只有整体超时 |
| 菜单开关拼写错误被静默当作 false | `CODEX_STARTUP_INTERACTIVE` 使用严格布尔解析，非法非空值报错 |
| Fast 配置使用旧值 | 改为 `service_tier="priority"`，关闭时仍明确生成 `default`；旧 `fast` 仅是上游兼容别名 |
| Luna 目录读取失败时默认档位过时 | 回退改为 `medium`，与本版本 bundled 目录一致 |
| 新版优先解析资源目录中的 Host | 对存在的资源目录 Host 追加路径及固定 SHA 校验，避免只校验根文件 |
| 旧 WebSocket feature 已移除 | 保持 provider 的 `supports_websockets` 映射，不恢复 `responses_websockets` / `responses_websockets_v2` |
| 工具变量被误当成安装或启用证明 | 明确 `ANDROID_SDK_ROOT` 为兼容别名；独立 ADB 不等于完整 SDK，预留 Java/Office 等路径不表示已有程序 |

核对覆盖 43 个显式 `CODEX_*` 设置。判定依据包括 [配置 schema](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/core/config.schema.json)、[Provider 定义](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/model-provider-info/src/lib.rs) 和 [feature 定义](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/features/src/lib.rs)。`CODEX_*` 多数由启动器翻译，不因官方没有同名环境变量就认定失效；官方模式忽略自定义 modality/context 是设计约束，Apps/Fast/模型权限仍取决于账号和上游。

## 2026-10-20：搬迁与目录边界修复

**原因：** 正常启动已按脚本位置派生包根，但部分辅助工具仍信任旧环境变量，文件链接及 bootstrap 检查顺序存在遗漏。

| 问题 | 结果 |
| --- | --- |
| 旧 `CODEX_INSTALL_DIR` 可把 Office/PDF 引向仍存在的旧包 | 7 个 helper 改为从自身脚本布局定位根，验证 marker、脚本和完整祖先链；同步三套 Office 副本 |
| 临时目录 category 可带 `..`，部分检查先跟随链接目标 | 提前拒绝越界/带 anchor 的工具与临时分类路径，拒绝悬空链接，避免先查询包外目标 |
| 模型指令文件缺少硬链接输入检查 | 读取内容前调用 `Assert-PortableRegularInputFile`，链接输入被拒绝且不生成指令文件 |
| BAT 在完整祖先检查之前创建目录 | 五个根 BAT 的首次检查改为纯 CMD 遍历至卷根，早于 `cd/mkdir`；后续 PowerShell 校验保留 |
| MuMu 默认检查宿主用户和系统 Temp | 默认限包内 ADB 状态与日志；包外故障诊断按具体授权，仅检查必要元数据；包外删除须有对应授权 |
| Maven bootstrap 路径含空格时缺少内部引号 | 五个 BAT 对齐启动器已有的带引号赋值；这是初始化一致性改进，未证实原 Codex 会话中发生 Maven 故障 |
| Host 回归使用系统临时目录 | 改为仓库 `tmp` 下独立 fixture，隔离子进程临时状态并仅清理本次文件 |

**保留的限制：** 自定义 MCP/插件配置正文不会自动迁移，旧绝对路径需人工核对。直接绕过 BAT 启动 PowerShell 可能先使用宿主缓存；`tool/setup-tools.ps1` 已补完整祖先保护，Android 路径/bootstrap 的直接入口尚无同等保护。应从已验证的正常/维护入口使用，不经 junction 直接调用；直接入口场景仍待 Windows 专项验证。

## 验证结果与待验范围（2026-10-26）

[完整 Windows 运行 40253783757](https://github.com/rileyaaa/Codex-Portable/actions/runs/40253783757) 对 `8e09466f` 执行全部发布门禁并通过，正式发布 [v2026.10.26](https://github.com/rileyaaa/Codex-Portable/releases/tag/v2026.10.26)。192 项 Python 回归、34 项 CLI 参数、完整 BAT/原生客户端及真实 Chromium 均通过；上传后回读三个附件，逐项验证 8,689 个客户文件，排除 48 个开发文件。Actions 临时 artifact/cache 为零。本地 Linux 检查明确跳过 Windows 原生执行项，不代替此 Windows 结果。所有样本为合成数据，不读取真实凭据。

| 检查 | 结果与范围 |
| --- | --- |
| Python unittest discovery | Windows 192 项通过：便携路径、HTTP、运行包、Android、Office/PDF、固定依赖、模式副本、pip 隔离、浏览器安装与发行 ZIP 校验 |
| `test_portable_config.ps1` | 最新 Windows 全量运行中 15 项通过，包含固定 0.164.0 客户端实际导出目录；离线无导出输入时另两项明确跳过 |
| `test_portable_paths.ps1` | 14 项通过：真实加载 env.ps1，覆盖 15 个派生路径、中文/空格、旧根、无关 cwd、移动目录及受保护/未审核变量；另验证真实启动器函数清除 Go/uv 变量、保留 Python/Node 路径、转发 header，并将 pip 配置禁用传到子进程和 TOML，不执行整个启动链 |
| `test_python_setup.ps1` | 4 组通过：实际 pip 参数、配置禁用与子进程变量筛选、修复范围拒绝早于任何 pip 调用、完整祖先链接拒绝；不执行安装 |
| 官方 PyPI wheel 解析 | Windows x64 / CPython 3.14 的 36 个固定版本解析成功，候选锁生成和校验通过；未执行 Windows 安装 |
| `test_instruction_paths.ps1` | 3 项通过：普通文件成功，真实硬链接/符号链接被拒绝；Linux 仅替换 Windows 路径包含判断，链接检查及写入用生产函数 |
| `test_extension_policy.ps1` | 12 项通过：Fast/扩展默认关闭、语音配置关闭、维护模式、显式开关、命名空间筛选、配置保留及两条模型指令生成路径 |
| `test_runtime_preflight.ps1` | 10 项合成工件检查通过：清单先校验、文件缺失/替换/链接、沙箱缓存新旧与状态硬链接；不执行客户端，不读取真实凭据 |
| `test_automation_paths.ps1` | 通过：子进程目录重定向、参数引用、越界/硬链接、先查祖先再遍历、只清理自有目录、任务开关与 PowerShell 解析；没有启动 Windows 程序 |
| `test_automation_process.ps1` | Windows 全量运行 40064538870 及中文编译修复专项均通过；包含 14 个严格诊断正反例和真实继承/捕获标准流 |
| `test_automation.js` | 10 项通过：实际固定版 MCP 初始化与工具筛选、拒绝未选任务、路径边界、禁止能力、依赖字节摘要；不启动浏览器 |
| `test_portable_npm.js` / `test_npm_entrypoints.ps1` | 10 项真实 npm 配置回归通过；Windows CMD/PowerShell 入口、显式项目根与包外拒绝已通过 |
| `test_system_policy.ps1` | 8 项合成检查通过：固定 Registry64/HKLM、值名存在性、授权 gate、异常拒绝与句柄回收；不读真实策略 |
| `test_browser_login_flow.ps1` | 7 项离线检查通过：默认设备码、显式系统浏览器、非法值与失败无回退 |
| `test_bootstrap_paths.ps1` | 15 个 Windows BAT 普通/junction 用例通过；测试入口环境与链接拒绝，不代替完整登录链 |
| `test_launcher_smoke.ps1` | 普通、中文/空格搬迁及维护入口三组真实 BAT/原生启动已通过专项 40066085104；新增客户端配置消费断言与全部正式门禁一同复验，不使用真实账号 |
| `test_browser_smoke.ps1` | Windows 实际 Chromium 在搬迁后的合成包启动、截图、关闭后重新打开并保留 Cookie，随后由缓存清理器删除资料且保留工作输出；通过 |
| 原生客户端与模型目录 | Windows Codex 0.164.0 启动及 `debug models --bundled` 导出通过 |
| 语法、格式与 BAT 静态检查 | 第一方 PowerShell 解析和 Python AST 检查通过；5 个 BAT 的 ASCII/CRLF、Go/uv 变量清除、pip 配置禁用和祖先检查先于目录创建检查通过。按 CRLF 规则检查项目差异；保留的官方 EXE/DLL、Playwright 依赖及原始 npm CLI 字节未改写；六个 npm/npx shim 为便携入口 |
| 转换器 smoke / static audit | 通过；一个合成 fixture、四账号、17 种输出，命令见子项目 README |

以下开发测试仅随 GitHub 源码提供，客户发行包不附带。在源码包根使用 Windows PowerShell 5.1 复验：

```powershell
.\tool\python\python.exe -B -m unittest discover -s tests -p 'test_*.py' -v
powershell.exe -NoProfile -File .\tests\test_portable_config.ps1
powershell.exe -NoProfile -File .\tests\test_portable_paths.ps1
powershell.exe -NoProfile -File .\tests\test_instruction_paths.ps1
powershell.exe -NoProfile -File .\tests\test_bootstrap_paths.ps1
powershell.exe -NoProfile -File .\tests\test_extension_policy.ps1
powershell.exe -NoProfile -File .\tests\test_runtime_preflight.ps1
powershell.exe -NoProfile -File .\tests\test_python_setup.ps1
powershell.exe -NoProfile -File .\tests\test_automation_paths.ps1
powershell.exe -NoProfile -File .\tests\test_automation_process.ps1
.\tool\node\node.exe --test .\tests\test_automation.js .\tests\test_portable_npm.js
powershell.exe -NoProfile -File .\tests\test_browser_login_flow.ps1
powershell.exe -NoProfile -File .\tests\test_system_policy.ps1
powershell.exe -NoProfile -File .\tests\test_npm_entrypoints.ps1
powershell.exe -NoProfile -File .\tests\test_browser_smoke.ps1
```

配置回归可用匹配客户端的 `debug models --bundled` 成功导出到包内临时 UTF-8 JSON 后，传入 `-BundledModelsPath` 启用另两项检查；先检查导出退出码。Windows 链接回归需 NTFS，创建符号链接可能需要 Developer Mode 或相应权限；Python 无此能力时明确 skip，PowerShell 指令测试会报错，都不算通过。

**真实使用待验：** 新盘符、中文/空格目录下的完整正常/维护会话及跨电脑迁移；真实 Agent/Host 工具调用与实际命令环境；Python 安装器的真实重装；授权条件下的三种登录模式、刷新凭据、代理和 Windows 沙箱。合成 NTFS、BAT、进程与浏览器检查已覆盖相应自动化行为，不代替上述完整使用流程。语音已排除，不再列为待验功能。旧版本的历史验收记录不代替 0.164.0 的实际结果，也不据离线测试宣称项目没有其他 bug。

**已知实现注意点：** PS5.1 的 `File.Replace`、泛型集合和原生空参数传递曾有兼容问题，后续改动应保留对应处理；认证多文件切换依赖 transition/logout 标记与 snapshot 归属，不可猜测回收；缺少 Host 时恢复匹配完整布局，不能用关闭 Code Mode 作为修复。当前 checkout 不包含历史 checker/updater 套件，不引用不存在的脚本或把旧版本哈希当成当前身份。

## 2026-11-25: fixed stable dependency candidate

xlsxwriter 3.2.9 -> 3.3.4

Official wheel SHA-256, RECORD, previous Git payload, dependency closure and actual Windows consumer checks passed. No extra distribution or feature enabled. Full native regression must pass before this commit is pushed. Run: https://github.com/rileyaaa/Portable/actions/runs/45589159314
