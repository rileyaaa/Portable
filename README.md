# Codex Portable（Windows x64）

将 Codex、启动器、包内工具和运行状态放在同一目录的便携项目，面向 **Windows x86-64、Windows PowerShell 5.1、本地 NTFS**，不支持 32 位 Windows。当前主客户端与 Code Mode Host 均为官方 **0.172.0**，用于文字与 Agent 工作，保留配套执行、搜索和沙箱组件，不包含语音聊天资源；来源和摘要见 [运行包清单](tool/runtime-manifest.json)。

默认面向 DBA 日常工作、爬虫与数据处理，也保留 Python 开发和调试能力。Python、Node 及已有文档/自动化运行依赖留在包内；Go 编译仍交给独立项目的手动 GitHub Actions，不预装 Go 编译器。Python EXE 打包已按用户授权恢复历史 PyInstaller，由 AI 直接调用包内 Python 的原生模块按任务使用，Windows 实际打包验收尚未执行。

**`D:\Codex` 只是常用位置，不是固定路径。** 解压到其他本地目录后，启动器从自身位置确定包根，重新设置工具、配置、用户状态、缓存和临时目录。最近正式发行版已通过 Windows 客户端启动、BAT/NTFS 专项、工具进程通信及真实浏览器持久化/清理检查；发行验证范围与来源见对应 Release：完整版本经过 Windows 门禁，限定脚本补丁记录定向验证及真机反馈；附件均须上传回读校验。真实账号、在线 Agent/Host 和跨电脑迁移仍需本机验收，详见 [开发文档](DEVELOPMENT.md)。

## 开始使用

发行命名为 `Codex Portable <CodexVersion> - Portable r<N>`；同一客户端版本的打包更新递增便携修订。优先下载 [Releases](https://github.com/rileyaaa/Codex-Portable/releases) 中命名为 `Codex-Portable-版本-windows-x64.zip` 的发行附件，并用同次发布的 `SHA256SUMS` 核对摘要。客户发行包不含第一方测试、CI 工作流、Git 配置、开发打包器或用户运行数据；测试保留在 GitHub 源码中。GitHub 自动生成的 Source code ZIP 不等同于便携发行包。

新版官方 EXE、搜索程序和配套浏览器使用 Git LFS 管理。通过 Git 克隆后先执行 `git lfs pull`；使用源码 ZIP 时确认其中包含实际 EXE，而不是文本形式的 LFS 指针。缺少实际工件时按[工具文档](tool/工具更新说明.md)取得并校验完整运行包。

1. 解压到独立目录，例如 `D:\Codex` 或 `E:\Tools\Codex Portable`。不要从压缩包、网络盘或 symlink/junction 路径运行。
2. 保留清单中的六个运行文件：主客户端、Code Mode Host、两个根目录沙箱助手、`codex-package.json` 和 `codex-path/rg.exe`，以及布局所需的 `codex-resources` 目录，不要只复制两个 EXE。
3. 按下文配置认证方式。使用自定义 API 时，需要接口地址、Key 和上游实际支持的模型名；官方账号可在启动菜单选择账号 JSON 或设备码登录。
4. 双击 `启动Codex.bat`，按菜单选择登录、思考等级、网络和代理。默认工作目录为包内 `work`。

日常和维护都通过 BAT 进入。BAT 会在创建运行目录前检查包根祖先，并在启动 PowerShell 前重定向用户目录与缓存；直接执行 `powershell -File ...` 可能在项目脚本接管前使用宿主缓存。

### Codex 的几个 EXE 分别做什么

这些程序来自同一官方版本，承担不同的运行职责：

| 文件 | 用途及保留理由 |
| --- | --- |
| `codex.exe` | 主客户端，必需。 |
| `codex-code-mode-host.exe` | Code Mode 工具执行进程，文字 Agent 也会用到；保留此能力就需要它，并且必须与主客户端匹配。 |
| `codex-command-runner.exe` | **提权 Windows 沙箱（elevated）**的命令执行助手；当前默认 unelevated 路径不调用它。 |
| `codex-windows-sandbox-setup.exe` | **提权 Windows 沙箱**的初始化助手；普通便携启动不因此自动提权或执行系统初始化。 |
| `codex-path/rg.exe` | Codex 自带的文件内容搜索程序，避免依赖宿主安装。 |
| `codex-voice-host.exe` 及语音资源 | 已按文字/Agent 用途移除；有效的 App 语音/听写开关保持关闭，TUI 语音快捷键解除绑定。上游 0.166.0 仍可显示 `/voice`，本包不支持该语音功能。 |

之前只有 Codex 和 Host 也能运行，是因为默认的 `windows.sandbox="unelevated"` 使用客户端内置的受限令牌执行路径。仍保留一对根目录沙箱助手，是因为 TUI 的 `/elevate-sandbox` 入口可达，不能靠普通配置可靠地移除；缺少助手时，上游还可能退回按文件名查找程序。保留包内匹配文件可避免该功能缺件及宿主程序回退。提权沙箱的系统级初始化需要另行明确授权。

当前为 0.172.0；运行组件的查找顺序须经发布前兼容检查确认，省略 `codex-resources` 中两份重复助手和语音组件。当前保留六个运行文件（体积及摘要以清单为准）；不含 `tool` 工具和用户状态。0.166.0 新增的独立 `codex-exec-server.exe` 属于可选服务端程序，本地文字/TUI/Agent 不依赖它，本包已将其及 `codex-package.json` 的 `execServer` 字段一并省略；官方 npm 包也采用这种精简布局。`codex.exe` 本身仍内置 `exec-server` 子命令，便携启动器会拒绝直接调用该入口；删除独立 EXE 不等于在二进制级别移除全部网络/远程代码。

交互界面、`resume` 和 `fork` 默认附带官方 `--no-daemon`，使用当前进程内的服务。0.166.0 共享后台服务禁止把状态目录放在其 CLI 包内，因此本包采用此模式保留包内 `home`；文字、Agent 和 Code Mode 仍可使用，共享后台服务功能不启用。若使用旧包遇到 `CODEX_HOME must be outside the source CLI package`，API 模式可临时通过 `.\启动Codex.bat --portable-auth api --no-daemon` 启动；沿用此前已保存的认证使用 `--portable-auth last`，它不等同于 API 模式。恢复会话在相同参数后加 `resume --last`。

## 五个 BAT 入口

| 文件 | 用途与注意事项 |
| --- | --- |
| `启动Codex.bat` | 日常受限启动。无参数默认显示菜单；带参数可执行 `exec`、`resume` 等允许的客户端命令。 |
| `启动Codex-维护模式.bat` | 有意修改包内脚本、工具、Skills、Plugins 或 MCP 时使用；扩大包内可写范围，扩展仍须明确选择后启用。 |
| `检查login_json.bat` | 检查 `login_json` 中待导入账号，生成包内 CSV 报告；会访问认证服务，网络失败不代表账号可删除；输入不可读、无法解析或指定索引不存在时保留原文件，不按失效凭证删除。 |
| `检查隔离.bat` | 检查便携目录和隔离条件。双击时会询问是否允许本次只读扫描宿主残留，默认拒绝；不会自动获得包外清理权限。 |
| `清理缓存.bat` | 退出工具后清理包内缓存，包括浏览器 Cookies、网站登录状态和缓存；浏览器运行时拒绝清理。不删除 Codex 认证快照、切换/退出标记或安装身份。 |

命令行示例，在包根打开终端：

```powershell
.\启动Codex.bat exec "检查当前项目"
.\启动Codex.bat resume --last
.\codex.exe --version
```

带参数启动时，`CODEX_AUTH_MODE=menu` 默认使用 API；如需沿用上次选择，设为 `last`，或明确设为 `api`、`account_json`、`browser`。命令行显式 `--portable-auth <模式>`（或等号写法）即使不附加 Codex 子命令或提示词，也沿用原有非菜单认证路径；显式 `menu` 和普通无参数双击保留启动菜单。

## 目录与配置

| 位置 | 内容 |
| --- | --- |
| `env.ps1` | 长期默认配置；包含各变量的用途、默认值和适用模式。 |
| `env.local.ps1` | 可选的本机配置与私密值，仅允许受支持的纯数据赋值；不要提交或随包分发。 |
| `work` | 默认项目工作区。 |
| `home`、`sqlite` | Codex 配置、认证、会话和数据库状态；不要公开或整目录迁移给他人。 |
| `login_json` | 待导入的账号文件与检查报告，按凭据管理。 |
| `cache/browser` | 配套浏览器的 profile、缓存、崩溃和临时下载、进程用户目录；任务结束保留，通过“清理缓存”统一删除。 |
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

### 终端显示模式

`CODEX_TUI_FULLSCREEN_TRANSCRIPT` 默认 `false`，在每次启动时生成 `tui.fullscreen_transcript = false`。需要启用 Codex 全屏转录视图时，在包根 `env.local.ps1` 添加：

```powershell
$env:CODEX_TUI_FULLSCREEN_TRANSCRIPT = "true"
```

改回 `"false"` 即使用终端 scrollback。修改在下次启动生效，非法布尔值会拒绝启动；命令行 `--no-alt-screen` 仍优先限制备用屏幕。启动器每次重新生成 `home\config.toml`，所以不要依赖 `/tui` 写入的设置在重启后保留。本开关不更改登录、模型、代理、普通/YOLO 权限或 `--no-daemon`。它是显示模式选择，不代表已证明或修复全部终端叠字问题。

### 常用功能设置

| 设置 | 默认行为与修改方式 |
| --- | --- |
| 登录菜单 | `CODEX_STARTUP_INTERACTIVE=true`；设为 `false` 后按配置启动，非法布尔值会报错。 |
| Provider | `CODEX_PROVIDER_MODE=custom_provider`；支持 `local_ollama`，默认本地地址为 `http://127.0.0.1:11434/v1`；账号登录由启动器选择 `official_chatgpt`。 |
| 模型 | `CODEX_MODEL=gpt-6-sol`。官方账号可在 `/model` 选择实际可用模型；中转站必须自行提供对应模型。 |
| 思考等级 | `CODEX_REASONING_EFFORT` 默认空，启动器在自定义/本地模式不显式覆盖，客户端仍可能采用模型目录默认；官方菜单读取客户端内置目录。目录不可用时 Sol/Luna 均默认 `medium`。 |
| 输入能力与上下文 | `CODEX_MODEL_MODALITIES=auto`、`CODEX_MODEL_CONTEXT_WINDOW` 留空。手动 `text`/`text_image` 或上下文数值仅用于自定义/本地模型兼容，官方账号使用官方目录。 |
| 模型指令文件 | `CODEX_MODEL_INSTRUCTIONS_FILE` 必须为包内普通单链接文件，相对路径基于 `home`；在 `env.local.ps1` 显式设为空会同时关闭旧指令文件自动发现。 |
| WebSocket | `CODEX_DISABLE_WEBSOCKET=true`。自定义接口确实支持时才改为 `false`；Ollama 固定 HTTP/SSE。 |
| Apps / Plugins | `CODEX_DISABLE_APPS=true`、`CODEX_ENABLE_PLUGINS=false`、`CODEX_ENABLE_PLUGIN_SHARING=false`。Plugins 须配置为 true 且本次启动带 `--portable-extensions`；Apps 还需要官方登录与连接器授权。 |
| 用户 MCP | `CODEX_PORTABLE_ALLOW_USER_MCP=false`，保留配置但不激活。须配置为 true 且本次启动带 `--portable-extensions`；维护模式不会自动启用。 |

自定义 API/本地 provider 使用标准 Responses 协议，生成包内当前模型目录以关闭 0.166.0 内置的内部 Responses Lite；模型名保持配置原值，官方账号使用原生目录。`CODEX_MODEL_CATALOG_JSON` 是输出路径，相对包根解析，不是导入任意模型目录的入口。其他 Provider header、query、状态栏等选项见 `env.ps1` 注释；需要 TOML 的选项使用单行 inline table。`CODEX_ENV_HTTP_HEADERS_TOML` 引用的自定义变量需在当前包 `env.ps1` 或 `env.local.ps1` 显式赋值，不回退到宿主同名变量；原必要系统/便携运行时变量白名单不变。

### 权限、联网与 Fast

根配置默认为 `CODEX_APPROVAL_POLICY=on-request`、`CODEX_SANDBOX_MODE=workspace-write`、`CODEX_SANDBOX_NETWORK_ACCESS=false`、`CODEX_FAST_MODE=false`。这些策略只能在 `env.ps1` 修改，不接受 `env.local.ps1` 覆盖。

正常模式主要开放 `work` 和受管理的会话临时目录；维护模式扩大到包内维护范围。`workspace-write` 主要限制写入，并不保证禁止所有包外读取；默认不扫描或处理宿主用户文件，需要包外任务文件时按用户授权的具体范围访问。Windows 系统程序、系统依赖及固定系统策略文件的存在性检查是必要系统访问。维护模式不自动授权包外操作。

联网开关控制 Codex 执行的本地命令，不限制模型 API 连接。Fast 与权限模式独立：关闭生成 `service_tier="default"`，开启生成 `priority`，实际可用性还取决于账号、模型和上游。以启动器的 `Fast`、`Approval`、`Sandbox`、`ShellNetwork` 输出确认本次配置。YOLO 仅用于明确选择的隔离无人值守场景；`danger-full-access` 要求与 `approval_policy=never` 配对，旧值 `untrusted` 已不支持。

`Version_History` 的常用两份文件与根文件相同；YOLO 使用同一启动器，保留 `strict`，将 approval/sandbox/network 分别设为 `never` / `danger-full-access` / `true`。YOLO 不再等待权限批准，但关闭了执行器的文件写入沙箱；包内路径设置仍保留，不能保证任意命令绝不越界。要求严格写入边界时使用常用模式。无人值守还需要可用认证及非交互命令，例如 `exec`，仅改变权限设置不会自动完成登录或跳过菜单。

### 代理与账号检查

**Codex 0.166.0 便携包发布门禁：** 两次代理修复使用同一官方 0.166.0 运行时，不更改认证或权限默认值。正式打包前必须在 Windows runner 使用包内 Python 完成当前源码的全量门禁和新的 10 轮随机种子回归，源码变化或任一失败、错误、跳过均阻止发布。十轮包含代理单元、回环 TCP/子进程、h11 互操作与运行时/模式副本/打包回归，不将它称为整个产品十次真机验收。发布状态和真实结果以对应 Release/Actions 为准。

**2026-10-30 源码修正：** HTTP bridge 已修复 CONNECT 单向半关闭时提前截断另一方向数据、上游响应中断后把第二个 HTTP 错误状态拼进响应体，以及非 ASCII 代理认证头异常。正常认证仍使用恒定时间比较；认证头只裁剪 HTTP 允许的空格和制表符，不把其他空白字符归一化成有效凭据。监听范围、代理路由、超时及权限默认值不变。新增离线故障注入与本机 TCP 回归，覆盖双向半关闭、分块请求、流水线隔离和响应中断；这些检查不替代 Windows、真实 SOCKS 服务或付费 API 验收，此前已删除的旧 r1 发行包不包含本次源码补丁。

**同日十轮复查补充：** 修复 Basic 认证方案名大小写兼容、扩展 HTTP 方法被误拒绝、端口/IPv6 authority 校验过宽、HTTP/1.0 错误接受 chunked 请求和上游未发送响应即关闭时没有返回 502 的问题；客户端语法错误、请求超时、请求体过大与请求头过大分别返回 400、408、413、431，已经开始的响应仍不会追加第二个错误状态。凭据本身区分大小写并继续恒定时间比较；监听、代理路由、限额和权限默认值不变。新增参数化边界、随机分片、并发 TCP 与独立 h11 互操作检查；这些检查运行在 Linux，本机合成上游不等同于真实 PySocks/SOCKS 协商、Windows 或实际账号验收。上述修复与独立 Exec Server 精简内容统一进入重新打包的 `v0.166.0-portable.1`；原 r1 已删除且没有残留标签，r2 仅在新 r1 经 Windows 全量测试、十轮检查、ZIP 上传回读验证并正式发布后删除。稳定可用的 0.164.0 发行包不受影响。

代理默认关闭，可在菜单或 `CODEX_PROXY_ENABLED` 中开启。`CODEX_PROXY_PROTOCOL` 支持 `socks5` / `http`，默认端点为 `127.0.0.1:10808`；SOCKS5 默认通过包内 Python 的 HTTP bridge 使用，bridge 仅监听回环地址。

`CODEX_PROXY_BYPASS_MODEL=true` 默认让自定义模型接口直连；接口本身需要代理时改为 `false`。本地工具需同时满足联网开启、代理开启和 `CODEX_PROXY_FOR_SUBPROCESS=true` 才会继承代理。不要直接覆盖启动器生成的 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY`、`NO_PROXY`。

账号 JSON 检查的 `CODEX_LOGIN_JSON_PROXY_MODE` 支持 `auto`（先直连后代理）、`direct`、`proxy`。默认 HTTP 后端为包内 Python；连接超时 `CODEX_LOGIN_JSON_CONNECT_TIMEOUT_SEC` 默认 8 秒、最多 30 秒，Python 还受本次请求总限约束；PowerShell 后端仅支持整体超时，且不支持 SOCKS5。任务总限、并发和文件数分别由 `CODEX_LOGIN_JSON_JOB_TIMEOUT_SEC`（420）、`CODEX_LOGIN_JSON_THROTTLE`（12）、`CODEX_LOGIN_JSON_MAX_FILES`（0 表示全部）控制。

## 认证与换电脑迁移

| 模式 | 用途 | 持久认证 |
| --- | --- | --- |
| `api` | 自定义 API / 本地 Provider | 自定义 API 使用本机配置中的 Key；Ollama 不要求 Key。 |
| `account_json` | 从 `login_json` 选择并导入账号 | `home\auth-account-json.json` |
| `browser` | 官方设备码登录（默认） | `home\auth-browser.json` |

`home\auth.json` 是当前活动槽位，`home\mode` 记录其认证模式。启动器从对应快照恢复活动槽位，并在正常退出或后续启动时将刷新后的凭据回收到正确快照；两种账号模式的长期快照分开保存。

官方账号默认执行设备码登录，显示网址和一次性代码，不自动打开系统浏览器；可在配套浏览器或另一设备完成。账号需启用设备码登录，未启用时可改用账号 JSON。若明确接受系统浏览器保存自己的 Cookies/历史，可在 `env.local.ps1` 设置 `$env:CODEX_BROWSER_LOGIN_FLOW = "system_browser"`；默认值为 `device_auth`，失败不自动切换。

显式退出登录会删除对应快照并设置 `logout-*.block`，阻止旧快照复活；成功重新登录后才清除。`auth-transition.block` 表示认证切换未完成，`auth.json.invalid-transition-*` 是归属不明的恢复材料，都不能当普通迁移文件处理。

### 同一台电脑换目录

正常退出 Codex、Host 和相关工具后移动完整目录，再从新位置的 BAT 启动。受管理环境路径和生成配置会自动重建。自定义 `env.local.ps1`、模型指令、MCP 或插件中的绝对路径仍需核对，确认不会继续调用旧包或包外程序；启动器不会推测并改写这些用户配置。

### 迁移到另一台电脑

1. 在 A 机正常退出 Codex、Host 和工具，确认认证切换已完成，最新活动凭据已回收到快照；有 transition、logout block 或归属不明的恢复文件时，先解决或选择在 B 机重新登录。
2. 在 B 机解压同版本干净包，复制所需 `work` 项目和非私密配置；不要直接复制整个 `home`、缓存或会话目录。
3. API 模式在 B 机重新配置 Key。需要延续账号登录时，仅通过私有受控渠道复制该模式的认证快照和一致的 `home\mode`；无法确认快照包含最新刷新凭据时，重新登录更稳妥，不要单独搬运或编辑活动 `auth.json`。
4. B 机保留或生成自己的 `installation_id`。从 BAT 启动并选择对应认证模式；若出现 401、refresh 无效或账号不一致，重新登录。

浏览器 `cache/browser` 包含 Cookies 和网站资料，不应随公开包分发。它能在本机连续任务间保留登录；Windows 加密可能绑定账号或机器，换电脑后应准备重新登录，不能保证复制 profile 就能沿用网站登录。

认证快照、账号 JSON、API Key 和私密配置等同密码，不得进入 Git、公开压缩包、截图或日志；不要读取、编辑或比较真实凭据内容/哈希。同机完整搬迁与对外分发是不同操作，发布包必须排除这些私密状态。

## 按任务使用技能

技能可以被发现和阅读，但只有你明确提出相关任务后才能运行其工具、检查依赖、启动服务或连接设备。例如文档任务不会顺带运行 APK、MuMu 或浏览器工具。安装在包内只规定文件位置，不代表授权操作整个桌面。

| 工作 | 当前方案 |
| --- | --- |
| Word / PPT / Excel | 保留 `docx`、`pptx`、`xlsx`。用户提供的模板优先；PPT 检查版式、层次、字体与实际预览，Word 保留样式和结构，Excel 检查公式及重算结果。缺渲染/重算工具时明确标注未验证。 |
| PDF 编辑与大量手册阅读 | 普通编辑使用 `pdf`；`pdf-library` 使用 PyMuPDF4LLM 按页转换并建立本地索引，先搜索后读取命中页，支持增量更新和纯 Markdown ZIP。仅转换格式不保证省 token；避免一次加载全部全文。OCR 引擎尚未预置，扫描/图中文字会标为待处理。 |
| APK / MuMu | `apk-test-router` 按任务读取插件内唯一的完整流程；你的 `mumu-adb` 保留。测试优先考虑 Appium/UiAutomator2 的 UI 树、resource-id、accessibility 和等待条件，画布/游戏界面仍可能需要截图。完整 SDK/JDK/Appium 尚未预置。 |
| 网页调试 | `browser-debug` 共用一套 Playwright：任务脚本、可选 MCP、控制台/网络及 CDP 诊断都使用同一份 Chromium，无需 ChromeDriver，也不另装 Chrome DevTools MCP。已包含匹配的 Windows x64 Chromium 155.0.8059.12；同一份浏览器约 458 MB 解压体积。 |
| Windows 应用调试 | `windows-desktop` 使用系统 UI Automation，仅处理明确指定的进程主窗口。默认读取控件树，点击/赋值需明确选择；不提供全盘 Shell、注册表或整桌面 MCP。实际 Windows 行为待验。 |

维护模式的 `mcp` / `plugin` 管理命令也需对应开关和 `--portable-extensions`，确保命令处理完整的该类配置；缺少时明确拒绝，不会清空保存的配置。成功修改只回写当前类型，另一类保持不变；查看无变更不回写。首次迁移旧 config 中的扩展时，先保存到 `home\portable-extensions.toml`，再重建生成配置；即使后续启动失败，也可重试。已有持久文件优先（空文件表示已清空），启动不会用旧配置覆盖它。

需要启用已配置的扩展时，在本机配置中将对应开关设为 `true`，再通过 `.\启动Codex.bat --portable-extensions` 明确选择本次扩展会话；这个启动器参数不会传给官方 CLI。技能本身可按需读取，不要求启用整套插件。扩展配置保存不等于运行授权，实际工具调用仍须符合当前任务。浏览器 MCP 继续使用已有的前台 stdio 入口和用户 MCP 配置；按本次任务选择，默认不注册。子进程代理及配置示例见 `browser-debug` 技能。

包内入口管理的用户资料、配置、下载临时文件和缓存随解压目录移动；任务脚本必须遵守同样的路径约定。这些路径设置不能阻止任意自行执行的程序越界，也不能控制 Windows 的事件日志等系统记录。常用模式提供写入沙箱；YOLO 和明确选择的宿主浏览器登录有上文说明的边界。

## 工具、更新与故障处理

当前包保留 Python 的网络、数据、Office/PDF 依赖，支持日常脚本开发和调试；Node 用于已有浏览器工具与账号转换器，Android 已有工具和技能也保留。Git、完整 Android SDK/JDK、Office 渲染和 OCR 等可选工具尚未预置，目录或变量存在不表示工具已安装。

Go、uv 系列和可再生 Python 字节码仍不包含在默认包中。已恢复 PyInstaller 6.21.0、配套 hooks 和必要依赖；AI 在明确的打包任务中直接使用包内 `python.exe -m PyInstaller`，不另维护专用 CMD 或自定义封装，也不直接执行带旧安装路径的 vendor EXE。AI 须按项目约定设置包内 tmp、cache 和工作输出路径。默认 PATH 不暴露 vendor Python bin 中绑定旧绝对路径的 EXE；使用已有便携 CMD 或包内 Python 模块。实际 Windows EXE 冻结构建仍需按任务验收；依赖维护继续使用包内 pip、固定版本和 wheel 摘要，见 [工具下载与更新](tool/工具更新说明.md)。

启动器固定 `PIP_CONFIG_FILE=nul`，日常 Agent 命令与安装器均不读取宿主的 `pip.ini`；依赖维护参数按工具文档显式指定。

包内 `npm` / `npx` 入口默认把当前包内目录作为项目根，不再向外层寻找项目配置。需要操作包内其他项目或 monorepo 根时，显式指定 `--prefix <包内项目目录>`；全局安装位置也留在包内。不要绕过这些入口调用原始 CLI 来获取便携约束。

| 现象 | 处理 |
| --- | --- |
| `failed to spawn code-mode host` / Host 缺失或身份不匹配 | 恢复同一版本的完整 runtime pair 和配套资源，不单独覆盖 EXE、不关闭 Code Mode 绕过校验。 |
| 配置修改启动后消失 | 修改 `env.ps1` 或允许的 `env.local.ps1`，而不是生成的 `home\config.toml`。 |
| 本机配置被拒绝 | 检查是否包含受保护变量、表达式或非法值；用脚本支持的纯数据设置。 |
| 工具找不到 | 核对包内实际 payload 和工具文档，不回退系统 PATH 或使用空 EXE 充数。 |
| 移动后仍访问旧位置 | 核对自定义模型指令、MCP、插件和本机配置中的绝对路径。 |
| 提示存在宿主系统配置 | 默认拒绝加载；只有确需采用组织系统策略时，才显式设置 `CODEX_ALLOW_HOST_SYSTEM_CONFIG=true`。 |

只维护 `main` 作为稳定版本来源，不启用自动升级工作流。维护者按 [工具文档](tool/工具更新说明.md) 手动准备同版本的 Codex/Host 组件、执行兼容性和 Windows 验证后再打包；用户仍通过完整、已验证的发行包更新，不从开发分支或旧版执行记录推断可用性。维护规则、变量兼容核对、测试命令及更新记录统一见 [开发文档](DEVELOPMENT.md)；账号格式转换器独立说明见 [子项目 README](Version_History/AI%20account%20format%20conversion/README.md)。

## SSH / SFTP 扩展（开发候选）

已在源码中加入 `tool/portable-ssh.py` 与 `home/skills/portable-ssh`，目标是通过包内 Python / Paramiko 操作用户明确授权的远端主机。私钥、固定主机指纹及本地传输文件集中在包内 `work/ssh/`（Git 和客户 ZIP 均排除），默认拒绝读取宿主 `~/.ssh`、SSH Agent，且不会自动信任远端主机。连接、执行命令和传输操作须指定目标并明确授权。完整使用方法见 [SSH 技能说明](home/skills/portable-ssh/SKILL.md)。

**开发分支的 Windows Python 运行树已经跟踪 Paramiko 5.1.0 及其固定依赖，输入清单和哈希锁均已包含该组。** 真实 SSH/SFTP、用户目标及本次完整兼容性验收仍需单独核对；不因此宣称正式发行包已通过 SSH 验收。
