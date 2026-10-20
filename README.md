# Codex Portable 0.156.1（Windows x64）

这是一个面向 Windows x64 的 Codex Portable 工作目录。它把 Codex、启动器、认证切换、包内工具路径和运行时状态约束在同一目录，方便在受控环境中携带、维护和复核。

当前固定的 OpenAI runtime pair 是：

- `codex.exe`：Codex 0.156.1 主程序。官方 SHA-256：`70bcb05f9bf1a4e7306edd0cd1b57d02af3267ad02a34b26f45c8c4bb20a3301`。
- `codex-code-mode-host.exe`：同一官方 release 的 Code Mode Host，SHA-256：`0f83a73dc6d511d43bd3e52cc0a999cb383c19c645ef3fbd8fbdaddde3088138`；它不是可选插件。两者必须位于包根目录，并由启动器固定身份校验。开发维护工作树中的检查器和 updater 不随 Clean Portable 发行包提供。

不要单独替换其中一个 EXE，也不要用关闭 Code Mode 来掩盖 Host 缺失。若 Host 缺失、链接不安全或身份不匹配，启动器会 fail closed。

## 目录与运行方式

根目录是 Portable 根。日常用户通常只需要：

> Clean Portable 发行包不附带开发检查器和版本升级工具；完整根工作树仍保留这些维护文件。

- `env.ps1`：正常模式的唯一长期默认配置入口。
- `env.local.ps1`：可选的本机私密覆盖文件；只允许项目定义的纯数据设置，不能放入发行包。
- `启动Codex.bat`：正常启动入口。
- `启动Codex-维护模式.bat`：明确的维护入口；只有有意维护包内内容时使用。
- `检查login_json.bat`：检查 `login_json` 中待导入的账号 JSON。
- `检查隔离.bat`：检查主机侧隔离前提与可选提示。
- `清理缓存.bat`：清理可再生缓存；不会把认证状态当缓存删除。
- `work`：你的工作区；启动器把 Codex 的默认工作目录设为此处。
- `home`：Codex 的包内配置与状态目录，包含高敏感认证文件；不要公开、同步或整目录复制给他人。

启动器会把临时目录、缓存和用户目录重定向到包内，并拒绝不安全的 reparse/hardlink 路径。Windows PowerShell 5.1 是这些 BAT/PowerShell 入口的目标宿主。

## 首次使用与日常流程

1. 解压到本地 NTFS 路径，例如 `D:\CodexPortable`；不要从网络盘、压缩包内或 junction/symlink 路径直接运行。
2. 确认根目录同时存在 `codex.exe` 与 `codex-code-mode-host.exe`。
3. 打开 `env.ps1`，按需配置模型、Provider 或 API 设置。私密值放在受限的 `env.local.ps1`，不要写入 README、日志或 ZIP。
4. 双击 `启动Codex.bat`。无参数默认显示登录/思考/网络/代理菜单；带参数时由 `CODEX_AUTH_MODE` 决定认证模式。
5. 日常确认可使用 `\.\codex.exe --version` 或查看启动器输出。Clean Portable 不附带开发检查器；遇到 runtime pair 问题时按下方故障排查恢复，不要手工 patch EXE。

常用只读维护命令：

```powershell
.\codex.exe --version
```

Clean Portable 不在发行包内原地升级 Codex/Host runtime pair。若需要更换 runtime，请重新解压经过验证的发行包，或在完整维护工作树中成对恢复匹配版本的 `codex.exe` 与 `codex-code-mode-host.exe`。

若看到 `failed to spawn code-mode host` 或 `host executable was not found`，先检查根目录 Host 是否存在且与主 EXE 同目录。Clean Portable 不附带 checker/updater；请重新解压经过验证的同版本发行包，或在维护工作树中恢复匹配的 runtime pair。不要手工 patch EXE、不要把 `code_mode_host=false` 当修复。

## 正常模式、YOLO 与 Fast

根目录 `env.ps1` 是**正常受限模式**：

- `CODEX_APPROVAL_POLICY=on-request`
- `CODEX_SANDBOX_MODE=workspace-write`
- `CODEX_SANDBOX_NETWORK_ACCESS=false`
- `CODEX_FAST_MODE=false`

正常模式限制 Codex 工具的写入与网络边界；它不是当前会话的临时授权状态。根目录 `env.ps1` 是当前配置的唯一依据；`Version_History` 中保留的预设脚本仅用于历史兼容和差异追溯，不应覆盖根配置。YOLO 只在用户明确选择隔离的无人值守用途时使用，不要把它当作对未知项目的默认运行方式。

Fast 与 YOLO、模型及 Code Mode Host 独立。`CODEX_FAST_MODE=false` 会显式生成 `service_tier="default"`，保持 Standard 并避免账号资格自动启用 Fast；`true` 才生成 Codex 0.156.1 支持的 `service_tier="fast"`。非法布尔值会被拒绝。要确认本次有效设置，请看启动器打印的 `Fast`、`Approval`、`Sandbox`、`ShellNetwork` 行，而不是只看 TUI 状态栏。

## GPT-6 模型与思考等级

默认模型改为 `gpt-6-sol`。官方账号下可在 `/model` 切换 `gpt-6-sol`、`gpt-6-luna`；菜单通过当前 `codex.exe debug models --bundled` 读取各模型支持的思考等级与默认值。若目录读取失败，Sol 菜单兜底为 low/medium/high/xhigh/max/ultra（默认 medium），Luna 为 low/medium/high/xhigh/max（默认 high）；实际账号可用性仍以登录后的模型列表为准。API 中转站必须自己提供相应模型；只升级客户端不会让中转站自动具备模型访问权。`CODEX_REASONING_EFFORT` 留空时，API/本地模式不强制发送思考等级；填入固定值时需与所选模型及上游支持的等级一致。

## 环境变量兼容范围

`env.ps1` 中大部分 `CODEX_*` 是本项目启动器读取的开关，不要求 Codex 官方直接识别同名变量；启动器生成的 `model`、`model_reasoning_effort`、`service_tier`、`model_catalog_json`、Provider、沙箱与 shell 环境配置仍见官方配置参考。`CODEX_HOME` 与 `CODEX_SQLITE_HOME` 固定包内状态目录。`ANDROID_HOME`、`JAVA_HOME`、`APPIUM_HOME` 等是预留给第三方工具的路径；对应可选程序未预置时，环境变量本身不会安装或启用工具。`CODEX_DISABLE_APPS` 与 `CODEX_ENABLE_PLUGINS` 仍由启动器写入 `[features]`。`CODEX_FAST_MODE=false` 保留现有 Standard 行为，避免升级顺带切换服务层。完整可用性仍需在 Windows 上用新版 pair 启动验证。

## 认证模式

启动菜单和 `CODEX_AUTH_MODE` 支持三种模式：

| 模式 | 用途 | 持久状态 |
|---|---|---|
| `api` | 使用 `env.ps1` / `env.local.ps1` 的 API 配置 | 不依赖账号快照；API Key 不应进入包或迁移副本 |
| `account_json` | 从 `login_json` 中选择并导入账号 JSON | `home\auth-account-json.json` |
| `browser` | 运行官方浏览器登录 | `home\auth-browser.json` |

`home\auth.json` 是 Codex 当前实际读取的**活动槽位**，不是两种账号模式共享的长期档案。启动器根据 `home\mode` 选择相应 snapshot 原子复制到活动槽位；运行期间 refresh 后的活动凭据会在后续启动和正常退出清理路径按 `mode` 回收至正确 snapshot。因此 account JSON 与 browser 的账号不会互相覆盖。

显式 logout 会删除对应 snapshot，并设置 `logout-account_json.block` 或 `logout-browser.block`，阻止旧 snapshot 被自动恢复；只有新的成功登录才会清除该 block。`auth-transition.block` 表示多文件认证切换尚未提交；启动器会隔离不明归属的活动凭据到 `auth.json.invalid-transition-*`，而不是猜测它属于哪个账号模式。

### 换电脑：安全迁移表

所有下列文件均等同账号 token/密码。不要把它们放入 Git、截图、公开网盘、ZIP、日志或聊天记录；不要读取、编辑或比较其内容/哈希。

| 文件/模式 | 作用 | A→B 是否建议复制 | 前置条件与说明 |
|---|---|---|---|
| API | `env.local.ps1` 中的 API Key/Provider 私密值 | 否 | 在 B 机重新按自己的安全方式配置 Key；不要把 Key 随 Portable 发行。 |
| `auth-account-json.json` | account_json 的持久快照 | 是，仅该模式 | A 上正常退出所有 Codex，确认无 pending transition/logout block；复制到 B 的 `home` 同名位置。 |
| `auth-browser.json` | browser 的持久快照 | 是，仅该模式 | 同上；若服务端要求重新认证、refresh 无效或出现 401，直接在 B 重新 browser login。 |
| `auth.json` | 当前活动槽位，可能含最新 refresh | 视 clean reconciliation 而定 | 推荐先在 A 正常关闭并让下一次 launcher reconciliation 回收到 snapshot；若无法证明已回收，和对应 snapshot 及 `mode` 一起在受控私有传输中迁移，B 首次启动后只保留项目生成的活动槽位。 |
| `mode` | 上次确认的 `api` / `account_json` / `browser`，决定 snapshot 归属 | 是，随账号 snapshot | 只在 mode 与所复制 snapshot 一致、无 block/transition 时复制；否则在 B 重新选择登录模式。 |
| `installation_id` | 安装/设备身份，不是登录凭据 | 否 | B 保留或生成自己的 installation identity。 |

推荐步骤：

1. 在 A 完全退出 Codex 与 Host，且不要在 `home` 中存在 `auth-transition.block`、`logout-*.block` 或 `auth.json.invalid-transition-*`。
2. 确认当前登录模式；只选择相应 snapshot。API 模式通常应在 B 重新配置 API Key。
3. 通过私有、受控渠道把所需 snapshot 和一致的 `mode` 放进 B 的 `home`；不要复制整个 `home`。
4. 在 B 用相同版本的 Portable 启动器启动，让它按 snapshot/mode 规则恢复活动槽位。
5. 若无效、401、账号不一致或服务端要求重新登录，不要手工编辑 JSON；在 B 走对应的登录流程重新认证。

`auth-transition.block`、`logout-*.block`、`auth.json.invalid-transition-*`、cache、session、日志以及 `installation_id` 都不是普通迁移文件。存在这些标记时先恢复/重新登录，不要盲目复制。

## 认证与维护入口

- `启动Codex.bat`：日常入口；选择 API、账号 JSON 或浏览器登录。
- `检查login_json.bat`：只检查 `login_json` 内待导入 JSON，生成本地 CSV 报告；网络异常不会当作可安全删除的凭据。
- `启动Codex-维护模式.bat`：仅用于有意维护包、MCP 或插件；比正常模式拥有更宽的包内写入范围。
- `检查隔离.bat`：检查便携隔离与主机侧条件，不是模型启动入口。
- `清理缓存.bat`：清除可再生缓存并重建安全 bootstrap；认证 snapshot、transition、logout block、installation identity 不当作缓存。
- Clean Portable 不附带开发检查器、版本升级工具与 DEV/TEST selftest；这些仅保留在完整维护工作树中。

更多工具是否存在、如何受支持地补齐以及 Full/Minimal 差异，见 [tool\\工具更新说明.md](tool/%E5%B7%A5%E5%85%B7%E6%9B%B4%E6%96%B0%E8%AF%B4%E6%98%8E.md)。项目演进和已解决问题见 [CHANGELOG.md](CHANGELOG.md)。

## 完整包与 Minimal Runnable 包

完整工作树保留包内 Python、Node、Go、工具、Skills 与 Plugins，适合维护、扩展与全部高级工作流。Minimal Runnable 包只保留基础 Codex/Code Mode、三种认证入口、必要的 Python/PowerShell helper、固定身份检查和核心维护入口；它不携带当前机器认证、缓存、会话、日志或可选大工具 runtime。

Minimal 的精确内容、缺失能力和校验结果以发行包旁的本 README 与 `tool\工具更新说明.md` 为准。若需要 Android、Office、PDF、媒体、OCR、Node 或 Go 工作流，请使用完整包或受支持的包内安装方式，不要依赖宿主 PATH 的偶然存在。
