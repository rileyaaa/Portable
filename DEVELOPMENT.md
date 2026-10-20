# 开发与维护记录

## 维护约定

开始维护前阅读本节及 [README](README.md)。这里统一记录项目限制；使用方法、下载步骤分别维护在对应文档，不在多处复制整套说明。

1. **只维护四份项目文档。** 根 `README.md`、本文件、`tool/工具更新说明.md`、账号格式转换子项目的 `README.md` 是固定入口。未经用户同意不新增项目说明文档；确有必要时先说明理由并征得同意。每次功能新增、修改或删除，同步相关说明、变量注释及受影响的技能文档；直接更正、删除失效内容，不持续堆叠重复说明。已授权技能所必需的 `SKILL.md`、第三方功能文档和许可证、用户转换任务生成的交付报告不属于新增项目说明文档。
2. **记录原因和结果。** 本文件开头维护稳定规则，下面按日期记录变更原因、最终结果、验证和必要的遗留问题。同一天同一事项可合并更正；不记录逐次尝试、排查对话、无效假设或临时命令输出。已解决事项应更新状态，不长期保留为待办。
3. **目标平台。** 以 Windows x86-64（x64）、本地 NTFS、Windows PowerShell 5.1 为准；x64 不等于 32 位 x86。保留 BAT 的 ASCII/CRLF、PowerShell 的 PS5.1 语法和既有编码兼容。Linux 或 PowerShell 7 的检查不能代替 Windows 验收。
4. **任意解压位置。** `D:\Codex` 仅为常用示例。包根从当前脚本位置派生，不依赖固定盘符、工作目录或继承的旧 `CODEX_INSTALL_DIR`；工具、配置、缓存、状态和临时路径跟随当前包根。不得把机器绝对路径写入默认设置。搬迁回归须覆盖旧包仍存在、无关工作目录、空格和中文目录。
5. **目录边界。** 默认只处理当前包内任务文件，不主动扫描、读写或清理宿主用户目录、其他目录及旧包。包外任务文件按用户已授权的具体范围访问；Windows 必需程序、系统依赖和固定系统策略存在性检查属于明确的系统访问。维护模式扩大包内可写范围，不自动授权包外操作；`workspace-write` 不能保证阻止全部包外读取。
6. **先验证路径，再访问。** 先检查词法边界，再检查完整祖先及目标的 reparse/junction/symlink、输入硬链接和适用的 ACL；检查应早于创建目录、读取内容或执行程序。保留正常/维护模式分界、受保护变量和 CLI 覆盖限制，不通过关闭身份校验、放开路径或关闭 Code Mode 掩盖故障。MCP/插件的外部命令及绝对路径需另行核对。
7. **每次升级复核变量。** 更新 Codex、Host 或任何工具后，核对对应变量的声明、默认值、加载/覆盖、生成配置、子进程最终值和新版实际消费点，并查看上游 schema/发行说明。区分启动器私有接口、原生变量、兼容别名和仅预留路径；确认失效时移除或替换并同步文档、回归。变量存在或程序安装成功都不等于功能生效。
8. **保持工件与工具来源。** Codex/Host 使用同一官方稳定 release 的 Windows x64 工件，校验来源和摘要，更新固定身份、登录版本映射及 `tool/runtime-manifest.json`；保留所需配套资源与许可证，不修改官方 EXE/DLL 字节。本包明确只做文字与 Agent 工作，省略语音组件并关闭语音相关功能；今后升级也保留这一范围。其他工具按 [工具说明](tool/工具更新说明.md) 在包内安装/更新，工具缺失时明确报告，不静默调用宿主或全局包管理器，不永久修改系统/用户 PATH，不运行 Node 随附的系统安装脚本。
9. **保护状态与清理边界。** 不读取、记录或提交真实账号 JSON、API Key、认证快照、会话、机器私密配置及其内容/哈希。测试使用合成数据，临时文件放包内 `tmp` 的独立目录，创建前检查链接；只清理本次创建的文件和启动的进程。认证 snapshot、transition/logout/recovery 标记及 installation identity 不当作缓存删除，既有用户数据和进程应保留。
10. **单一维护来源与模式副本同步。** Android 完整流程统一维护在 `home/plugins/android-apk-lab/skills`，外层只保留精简 `apk-test-router`，保留用户编写的 `mumu-adb`。Office 的 docx/pptx/xlsx 共用 helper 副本保持一致。根 `env.ps1` / `run-codex.ps1` 更新时，必须同步 `Version_History` 下的四份常用/YOLO 模式文件：常用两份与根文件逐字节相同；YOLO 启动脚本与根相同，env 基于根生成，保持 `CODEX_PORTABLE_PROFILE=strict`，仅将 approval 改为 `never`、sandbox 改为 `danger-full-access`，并保留原 YOLO 的 `CODEX_SANDBOX_NETWORK_ACCESS=true`。Fast、扩展默认值及其他修复全部同步，不另维护旧版客户端身份。用回归验证差异仅为这三项赋值。其他真正历史资料不批量替换；账号格式转换器独立维护。
11. **验证与交付。** 运行与变更相关的回归，明确区分通过、失败、跳过和未运行；不能用假输出或空程序冒充工具可用。保留用户改动，使用现有 checkout，不另建 worktree，除非用户要求。提交/推送前核对差异、引用、Git LFS 工件及私密/临时文件排除；没有执行的 Windows、真实账号或设备流程不得写成已通过。
12. **按任务启用，默认关闭 Fast。** `CODEX_FAST_MODE=false`；Plugins、用户 MCP 默认关闭，维护模式也不自动启用。扩展配置须同时满足对应开关和本次 `--portable-extensions`。发现、读取技能或进入维护模式不代表授权运行其工具；只有用户明确提出相关任务，才检查依赖、启动服务、连接设备或操作目标。包内安装不等于授权控制整台电脑或模拟器；实际任务仍限已选目标。
13. **GitHub Actions 只手动运行。** 所有工作流仅允许 `workflow_dispatch`，不添加 push、PR、定时或关联工作流自动触发。临时下载使用短保留期，不建立长期大文件缓存；产物取回并校验后及时删除本次 artifact、临时分支/发行附件及下载缓存。未能执行或清理须明确报告，不能将保留期代替主动清理。
14. **及时提交并推送。** 每完成一批可独立验证、文档已同步的修改就提交并推送到用户指定仓库，不将大量已完成改动或多个提交长期堆在本地。推送前检查差异和测试，推送后核对远端提交；未完成的功能留待下一批，不能为赶进度发布已知损坏入口。
15. **控制体积与重复能力。** 同一用途优先复用已装依赖；浏览器统一为一套 Playwright 和一份配套 Chromium，不并装 ChromeDriver、第二套浏览器或 Chrome DevTools MCP。先检查现有 API/CDP 是否能完成任务，再考虑新增工具并说明收益与体积。精简前核对上游查找路径、共享依赖和实际功能；不因文件名相似就删除官方助手或资源，不为体积牺牲已保留功能。所有可配置的 profile、下载、缓存、临时文件随包根移动；不能以“便携”名义隐藏系统权限或工具自身的限制。

## 2026-10-20：文字/Agent 精简与联动检查

**原因与范围：** 用户确定不使用语音；此前分项回归不足以覆盖新运行包、进程监督和工具入口之间的依赖。本轮核对固定版本上游的资源查找、沙箱助手缓存和原生变量消费点，检查第一方脚本并执行现有综合回归，不将离线检查称为 Windows 全流程验收。

**精简结果：** 删除语音专用的 39 个文件，减少约 19.4 MB；Codex 运行组件现为 8 个文件、约 472.2 MB，保留主程序、Code Mode Host、搜索和两种沙箱助手的官方布局。生成配置明确关闭 `in_app_voice`、`in_app_dictation`、`realtime_conversation`。两份沙箱兼容副本仍保留；用途和取舍见 README。

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

**结果：** 仅采用一套固定 Playwright 依赖，共用一份配套 Chromium。任务脚本、可选 stdio MCP 与 CDP 诊断复用同一安装；无 ChromeDriver、第二浏览器或 Chrome DevTools MCP。进程用户目录、profile、缓存和临时下载落包内，退出时关闭本次进程并校验后清理。MCP 过滤任意 Node 执行、上传、安装、配置及客户端重定向根目录；任务脚本入口仍是受当前权限约束的代码执行，不能冒充不可信脚本沙箱。Windows 桌面入口使用系统 UI Automation，只读指定 PID 主窗口的有界树，修改动作需要额外开关，未安装通用 Windows-MCP。

**交付状态：** JS 依赖约 18.7 MB、185 个文件已安装并记录摘要；配套 Windows 浏览器尚未取得。已提供仅手动触发、artifact 保留 1 天并清理 runner 临时目录的下载工作流；云环境官方 CDN 与 Actions API 被网络策略拦截，已保存域名配置草稿，尚未触发工作流或产生远端 artifact。实际 Windows 浏览器、UI Automation 和进程退出行为待验。

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

**保留的限制：** 自定义 MCP/插件配置正文不会自动迁移，旧绝对路径需人工核对。直接绕过 BAT 启动 PowerShell 可能先使用宿主缓存；`tool/setup-tools.ps1` 和 Android 路径/bootstrap 的直接入口没有同等完整祖先保护，应从已验证的正常/维护入口使用，不经 junction 直接调用。这些直接入口场景尚待 Windows 专项处理。

## 2026-10-20：验证结果与待验范围

本次维护在 Linux x86_64、Python 3.12、PowerShell 7.6.7 上执行。所有回归使用合成数据，没有读取真实认证或请求登录服务。

| 检查 | 结果与范围 |
| --- | --- |
| Python unittest discovery | 57 项通过：13 项 helper、4 项 HTTP 超时、5 项发行包、17 项 Android、14 项 PDF、2 项可选依赖摘要/架构、2 项模式副本检查 |
| `test_portable_config.ps1` | 13 项通过，2 项导出检查跳过；升级时另曾用匹配 0.163.0 的实际 bundled JSON 完成全部 15 项 |
| `test_portable_paths.ps1` | 12 项通过：真实加载 env.ps1，覆盖 15 个派生路径、中文/空格、旧根、无关 cwd、移动目录及 9 个受保护/未审核变量；不是整个启动链测试 |
| `test_instruction_paths.ps1` | 3 项通过：普通文件成功，真实硬链接/符号链接被拒绝；Linux 仅替换 Windows 路径包含判断，链接检查及写入用生产函数 |
| `test_extension_policy.ps1` | 12 项通过：Fast/扩展默认关闭、语音配置关闭、维护模式、显式开关、命名空间筛选、配置保留及两条模型指令生成路径 |
| `test_runtime_preflight.ps1` | 10 项合成工件检查通过：清单先校验、文件缺失/替换/链接、沙箱缓存新旧与状态硬链接；不执行客户端，不读取真实凭据 |
| `test_automation_paths.ps1` | 7 组通过：子进程目录重定向、参数引用、越界/硬链接、先查祖先再遍历、只清理自有目录、任务开关与 PowerShell 解析；没有启动 Windows 程序 |
| `test_automation_process.ps1` | 生产监督器 C# 编译通过；实际继承/捕获标准流需 Windows，Linux 明确跳过 |
| `test_automation.js` | 6 项通过：实际固定版 MCP 初始化与工具筛选、拒绝未选任务、路径边界、禁止能力、依赖字节摘要；不启动浏览器 |
| `test_bootstrap_paths.ps1` | Linux 明确跳过；15 个 Windows BAT 普通/junction 用例未运行，不执行真实客户端 |
| 语法、格式与 BAT 静态检查 | 本轮全部 30 个第一方 PowerShell 文件解析通过，87 个已跟踪第一方 Python 文件 AST 检查通过；此前 5 个 BAT 的编码、祖先循环及检查顺序检查通过，本轮未修改 BAT。项目差异检查通过；官方 wheel 与 npm payload 保留原字节 |
| 转换器 smoke / static audit | 通过；一个合成 fixture、四账号、17 种输出，命令见子项目 README |

在包根使用 Windows PowerShell 5.1 复验：

```powershell
.\tool\python\python.exe -B -m unittest discover -s tests -p 'test_*.py' -v
powershell.exe -NoProfile -File .\tests\test_portable_config.ps1
powershell.exe -NoProfile -File .\tests\test_portable_paths.ps1
powershell.exe -NoProfile -File .\tests\test_instruction_paths.ps1
powershell.exe -NoProfile -File .\tests\test_bootstrap_paths.ps1
powershell.exe -NoProfile -File .\tests\test_extension_policy.ps1
powershell.exe -NoProfile -File .\tests\test_runtime_preflight.ps1
powershell.exe -NoProfile -File .\tests\test_automation_paths.ps1
powershell.exe -NoProfile -File .\tests\test_automation_process.ps1
.\tool\node\node.exe --test .\tests\test_automation.js
```

配置回归可用匹配客户端的 `debug models --bundled` 成功导出到包内临时 UTF-8 JSON 后，传入 `-BundledModelsPath` 启用另两项检查；先检查导出退出码。Windows 链接回归需 NTFS，创建符号链接可能需要 Developer Mode 或相应权限；Python 无此能力时明确 skip，PowerShell 指令测试会报错，都不算通过。

**Windows 待验：** 正常/维护 BAT 在新盘符、中文、空格路径运行；NTFS 链接、ACL、进程监督、标准流和退出清理；实际 Codex/Host 启动与工具调用；生成配置最终变量；授权条件下的三种登录模式、代理和 Windows 沙箱。语音已排除，不再列为待验功能。旧版本的历史验收记录不代替 0.163.0 的实际结果，也不据离线测试宣称项目没有其他 bug。

**已知实现注意点：** PS5.1 的 `File.Replace`、泛型集合和原生空参数传递曾有兼容问题，后续改动应保留对应处理；认证多文件切换依赖 transition/logout 标记与 snapshot 归属，不可猜测回收；缺少 Host 时恢复匹配完整布局，不能用关闭 Code Mode 作为修复。当前 checkout 不包含历史 checker/updater 套件，不引用不存在的脚本或把旧版本哈希当成当前身份。
