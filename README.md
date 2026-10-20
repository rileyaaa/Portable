# Codex Portable（Windows x64）

将 Codex、启动器、包内工具和运行状态放在同一目录的便携项目，面向 **Windows x86-64、Windows PowerShell 5.1、本地 NTFS**，不支持 32 位 Windows。当前主客户端与 Code Mode Host 均为官方 **0.163.0**，用于文字与 Agent 工作，保留配套执行、搜索和沙箱组件，不包含语音聊天资源；来源和摘要见 [运行包清单](tool/runtime-manifest.json)。

**`D:\Codex` 只是常用位置，不是固定路径。** 解压到其他本地目录后，启动器从自身位置确定包根，重新设置工具、配置、用户状态、缓存和临时目录。当前版本已完成离线回归，Windows 客户端、Host、登录及 NTFS 行为仍待真机验收，详见 [开发文档](DEVELOPMENT.md)。

## 开始使用

`codex.exe` 使用 Git LFS 管理。通过 Git 克隆后先执行 `git lfs pull`；使用源码 ZIP 时确认其中包含实际 EXE，而不是文本形式的 LFS 指针。缺少实际工件时按[工具文档](tool/工具更新说明.md)取得并校验完整运行包。

1. 解压到独立目录，例如 `D:\Codex` 或 `E:\Tools\Codex Portable`。不要从压缩包、网络盘或 symlink/junction 路径运行。
2. 保留根目录 `codex.exe`、`codex-code-mode-host.exe` 及 `codex-package.json`、`codex-path`、`codex-resources` 等配套内容，不要只复制两个 EXE。
3. 按下文配置认证方式。使用自定义 API 时，需要接口地址、Key 和上游实际支持的模型名；官方账号可在启动菜单选择账号 JSON 或浏览器登录。
4. 双击 `启动Codex.bat`，按菜单选择登录、思考等级、网络和代理。默认工作目录为包内 `work`。

日常和维护都通过 BAT 进入。BAT 会在创建运行目录前检查包根祖先，并在启动 PowerShell 前重定向用户目录与缓存；直接执行 `powershell -File ...` 可能在项目脚本接管前使用宿主缓存。

### Codex 的几个 EXE 分别做什么

它们来自同一官方运行包，承担不同功能，并不是多装了几套 Codex：

| 文件 | 用途及保留理由 |
| --- | --- |
| `codex.exe` | 主客户端，必需。 |
| `codex-code-mode-host.exe` | 执行 Code Mode 工具调用的配套进程；当前项目保留此能力，必需与主客户端匹配。 |
| `codex-command-runner.exe` | Windows 沙箱中的命令执行助手；删除会破坏使用它的沙箱执行路径。 |
| `codex-windows-sandbox-setup.exe` | Windows 沙箱初始化助手，按需使用；不是另一套客户端。 |
| `codex-path/rg.exe` | Codex 自带的文件内容搜索程序，避免依赖宿主安装。 |
| `codex-voice-host.exe` 及语音资源 | 已按项目用途移除，并关闭语音、听写和实时会话配置；文字与 Agent 工作不依赖此组件。 |

两个沙箱助手在根目录和 `codex-resources` 中有同字节副本，这是上游 ZIP 的兼容布局，并非四种工具。去掉语音专用的 39 个文件后，Codex 运行包解压体积从约 **491.6 MB** 降为 **472.2 MB**；不含 `tool` 工具链。两份沙箱重复副本共约 **25.9 MB**，因不同启动路径可能使用不同位置，本次保留。进一步精简必须验证受影响功能和查找路径，不能只看 EXE 数量。

## 五个 BAT 入口

| 文件 | 用途与注意事项 |
| --- | --- |
| `启动Codex.bat` | 日常受限启动。无参数默认显示菜单；带参数可执行 `exec`、`resume` 等允许的客户端命令。 |
| `启动Codex-维护模式.bat` | 有意修改包内脚本、工具、Skills、Plugins 或 MCP 时使用；扩大包内可写范围，扩展仍须明确选择后启用。 |
| `检查login_json.bat` | 检查 `login_json` 中待导入账号，生成包内 CSV 报告；会访问认证服务，网络失败不代表账号可删除。 |
| `检查隔离.bat` | 检查便携目录和隔离条件。双击时会询问是否允许本次只读扫描宿主残留，默认拒绝；不会自动获得包外清理权限。 |
| `清理缓存.bat` | 清理可再生缓存并重建必要目录；不将认证快照、切换/退出标记或安装身份当缓存删除。 |

命令行示例，在包根打开终端：

```powershell
.\启动Codex.bat exec "检查当前项目"
.\启动Codex.bat resume --last
.\codex.exe --version
```

带参数启动时，`CODEX_AUTH_MODE=menu` 默认使用 API；如需沿用上次选择，设为 `last`，或明确设为 `api`、`account_json`、`browser`。

## 目录与配置

| 位置 | 内容 |
| --- | --- |
| `env.ps1` | 长期默认配置；包含各变量的用途、默认值和适用模式。 |
| `env.local.ps1` | 可选的本机配置与私密值，仅允许受支持的纯数据赋值；不要提交或随包分发。 |
| `work` | 默认项目工作区。 |
| `home`、`sqlite` | Codex 配置、认证、会话和数据库状态；不要公开或整目录迁移给他人。 |
| `login_json` | 待导入的账号文件与检查报告，按凭据管理。 |
| `cache`、`tmp`、`home-runtime`、`appdata` 等 | 包内缓存、临时文件及工具用户状态；部分路径会进一步指向本次会话目录。 |
| `tool`、`home/skills`、`home/plugins` | 工具、技能和插件。变量或目录存在不代表对应工具已安装。 |
| `Version_History` | 与根脚本同步的常用/YOLO 四份模式模板，以及独立账号格式转换子项目。 |

启动器先清理宿主继承的相关变量，再加载 `env.ps1` 和允许的 `env.local.ps1` 设置，处理菜单与命令行参数，最后生成 `home\config.toml`。**不要直接修改生成的 `config.toml` 保存长期设置。** 大部分 `CODEX_*` 是启动器接口，会转换成客户端配置，并非要求官方客户端识别同名变量。

`env.local.ps1` 只接受单行字符串赋值和注释，不执行表达式或变量插值。自定义 API 的基本示例：

```powershell
$env:CODEX_AUTH_MODE = "api"
$env:CODEX_PROVIDER_MODE = "custom_provider"
$env:CODEX_BASE_URL = "https://your-provider.example/v1"
$env:OPENAI_API_KEY = "替换为自己的Key"
$env:CODEX_MODEL = "上游实际提供的模型名"
```

不要使用 `CODEX_API_KEY` 代替 `OPENAI_API_KEY`，也不要只设置 `OPENAI_BASE_URL` 代替本项目的 `CODEX_BASE_URL`。包根、`PATH`、用户目录、缓存/临时目录及工具链路径受保护，不能在本机配置中覆盖。`CODEX_*` 仅接受启动器明确支持的设置；未经核对的原生调试、日志或安装路径变量会被拒绝，避免绕过包内路径限制。

### 常用功能设置

| 设置 | 默认行为与修改方式 |
| --- | --- |
| 登录菜单 | `CODEX_STARTUP_INTERACTIVE=true`；设为 `false` 后按配置启动，非法布尔值会报错。 |
| Provider | `CODEX_PROVIDER_MODE=custom_provider`；支持 `local_ollama`，默认本地地址为 `http://127.0.0.1:11434/v1`；账号登录由启动器选择 `official_chatgpt`。 |
| 模型 | `CODEX_MODEL=gpt-6-sol`。官方账号可在 `/model` 选择实际可用模型；中转站必须自行提供对应模型。 |
| 思考等级 | `CODEX_REASONING_EFFORT` 默认空，自定义/本地模式不强制发送；官方菜单读取客户端内置目录。目录不可用时 Sol/Luna 均默认 `medium`。 |
| 输入能力与上下文 | `CODEX_MODEL_MODALITIES=auto`、`CODEX_MODEL_CONTEXT_WINDOW` 留空。手动 `text`/`text_image` 或上下文数值仅用于自定义/本地模型兼容，官方账号使用官方目录。 |
| 模型指令文件 | `CODEX_MODEL_INSTRUCTIONS_FILE` 必须为包内普通单链接文件，相对路径基于 `home`；在 `env.local.ps1` 显式设为空会同时关闭旧指令文件自动发现。 |
| WebSocket | `CODEX_DISABLE_WEBSOCKET=true`。自定义接口确实支持时才改为 `false`；Ollama 固定 HTTP/SSE。 |
| Apps / Plugins | `CODEX_DISABLE_APPS=true`、`CODEX_ENABLE_PLUGINS=false`、`CODEX_ENABLE_PLUGIN_SHARING=false`。Plugins 须配置为 true 且本次启动带 `--portable-extensions`；Apps 还需要官方登录与连接器授权。 |
| 用户 MCP | `CODEX_PORTABLE_ALLOW_USER_MCP=false`，保留配置但不激活。须配置为 true 且本次启动带 `--portable-extensions`；维护模式不会自动启用。 |

手动模型能力覆盖生成的 `CODEX_MODEL_CATALOG_JSON` 是输出路径，相对包根解析，不是导入任意模型目录的入口。其他 Provider header、query、状态栏等选项见 `env.ps1` 注释；需要 TOML 的选项使用单行 inline table。

### 权限、联网与 Fast

根配置默认为 `CODEX_APPROVAL_POLICY=on-request`、`CODEX_SANDBOX_MODE=workspace-write`、`CODEX_SANDBOX_NETWORK_ACCESS=false`、`CODEX_FAST_MODE=false`。这些策略只能在 `env.ps1` 修改，不接受 `env.local.ps1` 覆盖。

正常模式主要开放 `work` 和受管理的会话临时目录；维护模式扩大到包内维护范围。`workspace-write` 主要限制写入，并不保证禁止所有包外读取；默认不扫描或处理宿主用户文件，需要包外任务文件时按用户授权的具体范围访问。Windows 系统程序、系统依赖及固定系统策略文件的存在性检查是必要系统访问。维护模式不自动授权包外操作。

联网开关控制 Codex 执行的本地命令，不限制模型 API 连接。Fast 与权限模式独立：关闭生成 `service_tier="default"`，开启生成 `priority`，实际可用性还取决于账号、模型和上游。以启动器的 `Fast`、`Approval`、`Sandbox`、`ShellNetwork` 输出确认本次配置。YOLO 仅用于明确选择的隔离无人值守场景；`danger-full-access` 要求与 `approval_policy=never` 配对，旧值 `untrusted` 已不支持。

`Version_History` 的常用两份文件与根文件相同；YOLO 使用同一启动器，保留 `strict`，将 approval/sandbox/network 分别设为 `never` / `danger-full-access` / `true`。YOLO 不再等待权限批准，但关闭了执行器的文件写入沙箱；包内路径设置仍保留，不能保证任意命令绝不越界。要求严格写入边界时使用常用模式。无人值守还需要可用认证及非交互命令，例如 `exec`，仅改变权限设置不会自动完成登录或跳过菜单。

### 代理与账号检查

代理默认关闭，可在菜单或 `CODEX_PROXY_ENABLED` 中开启。`CODEX_PROXY_PROTOCOL` 支持 `socks5` / `http`，默认端点为 `127.0.0.1:10808`；SOCKS5 默认通过包内 Python 的 HTTP bridge 使用，bridge 仅监听回环地址。

`CODEX_PROXY_BYPASS_MODEL=true` 默认让自定义模型接口直连；接口本身需要代理时改为 `false`。本地工具需同时满足联网开启、代理开启和 `CODEX_PROXY_FOR_SUBPROCESS=true` 才会继承代理。不要直接覆盖启动器生成的 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY`、`NO_PROXY`。

账号 JSON 检查的 `CODEX_LOGIN_JSON_PROXY_MODE` 支持 `auto`（先直连后代理）、`direct`、`proxy`。默认 HTTP 后端为包内 Python；连接超时 `CODEX_LOGIN_JSON_CONNECT_TIMEOUT_SEC` 默认 8 秒、最多 30 秒，Python 还受本次请求总限约束；PowerShell 后端仅支持整体超时，且不支持 SOCKS5。任务总限、并发和文件数分别由 `CODEX_LOGIN_JSON_JOB_TIMEOUT_SEC`（420）、`CODEX_LOGIN_JSON_THROTTLE`（12）、`CODEX_LOGIN_JSON_MAX_FILES`（0 表示全部）控制。

## 认证与换电脑迁移

| 模式 | 用途 | 持久认证 |
| --- | --- | --- |
| `api` | 自定义 API / 本地 Provider | 自定义 API 使用本机配置中的 Key；Ollama 不要求 Key。 |
| `account_json` | 从 `login_json` 选择并导入账号 | `home\auth-account-json.json` |
| `browser` | 官方浏览器登录 | `home\auth-browser.json` |

`home\auth.json` 是当前活动槽位，`home\mode` 记录其认证模式。启动器从对应快照恢复活动槽位，并在正常退出或后续启动时将刷新后的凭据回收到正确快照；两种账号模式的长期快照分开保存。

显式退出登录会删除对应快照并设置 `logout-*.block`，阻止旧快照复活；成功重新登录后才清除。`auth-transition.block` 表示认证切换未完成，`auth.json.invalid-transition-*` 是归属不明的恢复材料，都不能当普通迁移文件处理。

### 同一台电脑换目录

正常退出 Codex、Host 和相关工具后移动完整目录，再从新位置的 BAT 启动。受管理环境路径和生成配置会自动重建。自定义 `env.local.ps1`、模型指令、MCP 或插件中的绝对路径仍需核对，确认不会继续调用旧包或包外程序；启动器不会推测并改写这些用户配置。

### 迁移到另一台电脑

1. 在 A 机正常退出 Codex、Host 和工具，确认认证切换已完成，最新活动凭据已回收到快照；有 transition、logout block 或归属不明的恢复文件时，先解决或选择在 B 机重新登录。
2. 在 B 机解压同版本干净包，复制所需 `work` 项目和非私密配置；不要直接复制整个 `home`、缓存或会话目录。
3. API 模式在 B 机重新配置 Key。需要延续账号登录时，仅通过私有受控渠道复制该模式的认证快照和一致的 `home\mode`；无法确认快照包含最新刷新凭据时，重新登录更稳妥，不要单独搬运或编辑活动 `auth.json`。
4. B 机保留或生成自己的 `installation_id`。从 BAT 启动并选择对应认证模式；若出现 401、refresh 无效或账号不一致，重新登录。

认证快照、账号 JSON、API Key 和私密配置等同密码，不得进入 Git、公开压缩包、截图或日志；不要读取、编辑或比较真实凭据内容/哈希。同机完整搬迁与对外分发是不同操作，发布包必须排除这些私密状态。

## 按任务使用技能

技能可以被发现和阅读，但只有你明确提出相关任务后才能运行其工具、检查依赖、启动服务或连接设备。例如文档任务不会顺带运行 APK、MuMu 或浏览器工具。安装在包内只规定文件位置，不代表授权操作整个桌面。

| 工作 | 当前方案 |
| --- | --- |
| Word / PPT / Excel | 保留 `docx`、`pptx`、`xlsx`。用户提供的模板优先；PPT 检查版式、层次、字体与实际预览，Word 保留样式和结构，Excel 检查公式及重算结果。缺渲染/重算工具时明确标注未验证。 |
| PDF 编辑与大量手册阅读 | 普通编辑使用 `pdf`；`pdf-library` 使用 PyMuPDF4LLM 按页转换并建立本地索引，先搜索后读取命中页，支持增量更新和纯 Markdown ZIP。仅转换格式不保证省 token；避免一次加载全部全文。OCR 引擎尚未预置，扫描/图中文字会标为待处理。 |
| APK / MuMu | `apk-test-router` 按任务读取插件内唯一的完整流程；你的 `mumu-adb` 保留。测试优先考虑 Appium/UiAutomator2 的 UI 树、resource-id、accessibility 和等待条件，画布/游戏界面仍可能需要截图。完整 SDK/JDK/Appium 尚未预置。 |
| 网页调试 | `browser-debug` 共用一套 Playwright：任务脚本、可选 MCP、控制台/网络及 CDP 诊断都使用同一份 Chromium，无需 ChromeDriver，也不另装 Chrome DevTools MCP。JS 依赖已包含；配套 Windows 浏览器下载尚受云环境网络策略阻塞，不能视为已可启动。 |
| Windows 应用调试 | `windows-desktop` 使用系统 UI Automation，仅处理明确指定的进程主窗口。默认读取控件树，点击/赋值需明确选择；不提供全盘 Shell、注册表或整桌面 MCP。实际 Windows 行为待验。 |

需要启用已配置的扩展时，在本机配置中将对应开关设为 `true`，再通过 `.\启动Codex.bat --portable-extensions` 明确选择本次扩展会话；这个启动器参数不会传给官方 CLI。技能本身可按需读取，不要求启用整套插件。扩展配置保存不等于运行授权，实际工具调用仍须符合当前任务。

## 工具、更新与故障处理

完整工作树包含 Python、Node、Go、Skills、Plugins 和部分工具；Git、完整 Android SDK/JDK、Office/PDF 等工具可能仅预留路径。Minimal Runnable 包只保证其清单列出的基础 Codex/认证能力，不应假定具备完整工具链。安装位置、下载来源和更新步骤统一见 [工具下载与更新](tool/工具更新说明.md)。

| 现象 | 处理 |
| --- | --- |
| `failed to spawn code-mode host` / Host 缺失或身份不匹配 | 恢复同一版本的完整 runtime pair 和配套资源，不单独覆盖 EXE、不关闭 Code Mode 绕过校验。 |
| 配置修改启动后消失 | 修改 `env.ps1` 或允许的 `env.local.ps1`，而不是生成的 `home\config.toml`。 |
| 本机配置被拒绝 | 检查是否包含受保护变量、表达式或非法值；用脚本支持的纯数据设置。 |
| 工具找不到 | 核对包内实际 payload 和工具文档，不回退系统 PATH 或使用空 EXE 充数。 |
| 移动后仍访问旧位置 | 核对自定义模型指令、MCP、插件和本机配置中的绝对路径。 |
| 提示存在宿主系统配置 | 默认拒绝加载；只有确需采用组织系统策略时，才显式设置 `CODEX_ALLOW_HOST_SYSTEM_CONFIG=true`。 |

当前仓库没有历史 checker/updater，发行包不提供原地自动升级。升级应按工具文档成对更新并校验，或重新解压经过验证的同版本完整包。维护规则、变量兼容核对、测试命令及更新记录统一见 [开发文档](DEVELOPMENT.md)；账号格式转换器独立说明见 [子项目 README](Version_History/AI%20account%20format%20conversion/README.md)。
