# 开发与维护记录

## 维护约定

开始维护前阅读本节及 [README](README.md)。这里统一记录项目限制；使用方法、下载步骤分别维护在对应文档，不在多处复制整套说明。

1. **文档分工与更新。** 项目说明仅保留四个入口：根 `README.md`、本文件、`tool/工具更新说明.md`、账号格式转换子项目的 `README.md`。每次功能新增、修改或删除，同步相关说明、变量注释及受影响的技能文档。直接更正旧说法、删除失效内容、合并重复段落；不要靠追加一段新说明保留前后矛盾。技能、插件、第三方依赖的功能文档与许可证保留在原处。
2. **记录原因和结果。** 本文件开头维护稳定规则，下面按日期记录变更原因、最终结果、验证和必要的遗留问题。同一天同一事项可合并更正；不记录逐次尝试、排查对话、无效假设或临时命令输出。已解决事项应更新状态，不长期保留为待办。
3. **目标平台。** 以 Windows x86-64（x64）、本地 NTFS、Windows PowerShell 5.1 为准；x64 不等于 32 位 x86。保留 BAT 的 ASCII/CRLF、PowerShell 的 PS5.1 语法和既有编码兼容。Linux 或 PowerShell 7 的检查不能代替 Windows 验收。
4. **任意解压位置。** `D:\Codex` 仅为常用示例。包根从当前脚本位置派生，不依赖固定盘符、工作目录或继承的旧 `CODEX_INSTALL_DIR`；工具、配置、缓存、状态和临时路径跟随当前包根。不得把机器绝对路径写入默认设置。搬迁回归须覆盖旧包仍存在、无关工作目录、空格和中文目录。
5. **目录边界。** 默认只处理当前包内任务文件，不主动扫描、读写或清理宿主用户目录、其他目录及旧包。包外任务文件按用户已授权的具体范围访问；Windows 必需程序、系统依赖和固定系统策略存在性检查属于明确的系统访问。维护模式扩大包内可写范围，不自动授权包外操作；`workspace-write` 不能保证阻止全部包外读取。
6. **先验证路径，再访问。** 先检查词法边界，再检查完整祖先及目标的 reparse/junction/symlink、输入硬链接和适用的 ACL；检查应早于创建目录、读取内容或执行程序。保留正常/维护模式分界、受保护变量和 CLI 覆盖限制，不通过关闭身份校验、放开路径或关闭 Code Mode 掩盖故障。MCP/插件的外部命令及绝对路径需另行核对。
7. **每次升级复核变量。** 更新 Codex、Host 或任何工具后，核对对应变量的声明、默认值、加载/覆盖、生成配置、子进程最终值和新版实际消费点，并查看上游 schema/发行说明。区分启动器私有接口、原生变量、兼容别名和仅预留路径；确认失效时移除或替换并同步文档、回归。变量存在或程序安装成功都不等于功能生效。
8. **保持工件与工具来源。** Codex/Host 使用同一官方稳定 release 的 Windows x64 工件，校验来源和摘要，更新固定身份、登录版本映射及 `tool/runtime-manifest.json`；保留配套资源与许可证，不修改官方 EXE/DLL 字节。其他工具按 [工具说明](tool/工具更新说明.md) 在包内安装/更新，工具缺失时明确报告，不静默调用宿主或全局包管理器，不永久修改系统/用户 PATH，不运行 Node 随附的系统安装脚本。
9. **保护状态与清理边界。** 不读取、记录或提交真实账号 JSON、API Key、认证快照、会话、机器私密配置及其内容/哈希。测试使用合成数据，临时文件放包内 `tmp` 的独立目录，创建前检查链接；只清理本次创建的文件和启动的进程。认证 snapshot、transition/logout/recovery 标记及 installation identity 不当作缓存删除，既有用户数据和进程应保留。
10. **同步副本，保留历史语义。** 修改 `home/skills` 与 `home/plugins/android-apk-lab/skills` 的同名技能时核对并同步对应副本；Office 的 docx/pptx/xlsx 共用 helper 副本同样保持一致，保留技能入口、frontmatter、引用和许可证。根脚本代表当前行为；`Version_History` 的旧预设不批量升级，不覆盖当前配置。账号格式转换器作为独立子项目维护。
11. **验证与交付。** 运行与变更相关的回归，明确区分通过、失败、跳过和未运行；不能用假输出或空程序冒充工具可用。保留用户改动，使用现有 checkout，不另建 worktree，除非用户要求。提交/推送前核对差异、引用、Git LFS 工件及私密/临时文件排除；没有执行的 Windows、真实账号或设备流程不得写成已通过。

## 2026-10-20：统一项目文档

**原因：** 项目使用、变量、维护规则和版本记录分散，存在重复、历史状态混入当前说明及过多过程描述。

**结果：** 文档归并为四个入口，维护限制集中到本文件开头；README 统一说明 Git LFS 工件获取、五个 BAT、配置、目录搬迁和换电脑迁移；工具文档集中下载来源、布局和更新；转换器保留独立说明。原根级规则、变量清单和变更日志的有效内容已合并，不再单独维护；功能性技能和第三方文档不因本次整理删除。开发记录改为日期、原因、结果及验证，过时事实直接更正。

**文档核验：** 清点 358 份 Markdown，读取并筛查项目维护约束；完整审阅项目主文档及相关技能规则。第三方文档用于确认归属与引用，不宣称逐字审计其全部技术内容。修正两份 Appium 技能的维护文档入口；转换器文档按实际代码区分预览脱敏、JWT 展示和静态离线说明。

## 2026-10-20：0.163.0 升级与变量兼容

**原因：** 原 0.156.1 runtime pair 需要升级；部分变量虽有声明，但未传到实际调用，或生成了过时配置值。

**结果：** 从 [官方 rust-v0.163.0](https://github.com/openai/codex/releases/tag/rust-v0.163.0) 安装完整 Windows x64 ZIP 的 47 个文件，成对更新 Codex/Host，补齐沙箱、PATH 和语音资源。仅把 metadata 的入口名称适配为 `codex.exe`；官方二进制字节不变。来源、ZIP 摘要及逐文件摘要以 [runtime-manifest.json](tool/runtime-manifest.json) 为准，启动器和登录版本映射同步更新。

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
| Python unittest discovery | 18 项通过：11 项 helper 搬迁/路径测试、4 项连接超时、3 项发行包摘要/架构/版本检查 |
| `test_portable_config.ps1` | 13 项通过，2 项导出检查跳过；升级时另曾用匹配 0.163.0 的实际 bundled JSON 完成全部 15 项 |
| `test_portable_paths.ps1` | 7 项通过：真实加载 env.ps1，覆盖 15 个派生路径、中文/空格、旧根、无关 cwd、移动目录及 4 个受保护变量；不是整个启动链测试 |
| `test_instruction_paths.ps1` | 3 项通过：普通文件成功，真实硬链接/符号链接被拒绝；Linux 仅替换 Windows 路径包含判断，链接检查及写入用生产函数 |
| `test_bootstrap_paths.ps1` | Linux 明确跳过；15 个 Windows BAT 普通/junction 用例未运行，不执行真实客户端 |
| 语法、格式与 BAT 静态检查 | 11 个 PowerShell 文件无解析错误；5 个 BAT 的编码、祖先循环及检查顺序检查通过；项目文件差异检查通过。官方 LGPL/proxy-libintl 许可证自带空白格式告警，保留原字节及摘要 |
| 转换器 smoke / static audit | 通过；一个合成 fixture、四账号、17 种输出，命令见子项目 README |

在包根使用 Windows PowerShell 5.1 复验：

```powershell
.\tool\python\python.exe -B -m unittest discover -s tests -p 'test_*.py' -v
powershell.exe -NoProfile -File .\tests\test_portable_config.ps1
powershell.exe -NoProfile -File .\tests\test_portable_paths.ps1
powershell.exe -NoProfile -File .\tests\test_instruction_paths.ps1
powershell.exe -NoProfile -File .\tests\test_bootstrap_paths.ps1
```

配置回归可用匹配客户端的 `debug models --bundled` 成功导出到包内临时 UTF-8 JSON 后，传入 `-BundledModelsPath` 启用另两项检查；先检查导出退出码。Windows 链接回归需 NTFS，创建符号链接可能需要 Developer Mode 或相应权限；Python 无此能力时明确 skip，PowerShell 指令测试会报错，都不算通过。

**Windows 待验：** 正常/维护 BAT 在新盘符、中文、空格路径运行；NTFS 链接、ACL、进程监督和退出清理；实际 Codex/Host 启动与工具调用；生成配置最终变量；授权条件下的三种登录模式、代理、elevated 沙箱和语音设备。旧版本的历史验收记录不代替 0.163.0 的实际结果，也不据离线测试宣称项目没有其他 bug。

**已知实现注意点：** PS5.1 的 `File.Replace`、泛型集合和原生空参数传递曾有兼容问题，后续改动应保留对应处理；认证多文件切换依赖 transition/logout 标记与 snapshot 归属，不可猜测回收；缺少 Host 时恢复匹配完整布局，不能用关闭 Code Mode 作为修复。当前 checkout 不包含历史 checker/updater 套件，不引用不存在的脚本或把旧版本哈希当成当前身份。
