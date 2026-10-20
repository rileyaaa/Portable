# CHANGELOG

本文件记录 Codex Portable 的长期项目演进；当前使用方法请看 [README.md](README.md)，工具可用性与安装路径请看 [tool\\工具更新说明.md](tool/%E5%B7%A5%E5%85%B7%E6%9B%B4%E6%96%B0%E8%AF%B4%E6%98%8E.md)。历史 `Rxx` 审计的中间结论已在本文件归并，不应再被当成当前运行状态。

## Current — Codex Portable 0.156.1 Windows x64

- 目标 runtime pair：`codex.exe` SHA-256 `70bcb05f9bf1a4e7306edd0cd1b57d02af3267ad02a34b26f45c8c4bb20a3301`，`codex-code-mode-host.exe` SHA-256 `0f83a73dc6d511d43bd3e52cc0a999cb383c19c645ef3fbd8fbdaddde3088138`；启动器保持成对身份校验。
- 默认模型更新为 `gpt-6-sol`；支持 `gpt-6-luna`。思考菜单继续优先读取新版内置模型目录，读取失败时分别提供 Sol 和 Luna 的官方档位兜底；不会对第三方模型主动施加思考等级。
- 账号 JSON 的 Codex 客户端版本映射更新为 0.156.1。旧运行时版本、哈希和旧预设保留在历史章节，不作为当前入口。
- 审核了 `env.ps1` 中各类变量与生成配置的关系；启动器私有开关继续由脚本翻译，工具预留路径只在可选工具已安装时生效。官方账号可用模型取决于账号与工作区，第三方 API 模式仍取决于上游模型权限。
- 已将从官方 0.156.1 发行包取得的两份 Windows x64 EXE 成对替换并校验 SHA-256，且核对打包目录的文件清单；当前执行环境为 Linux，未进行 Windows PowerShell 5.1 启动或账号登录实测。

## Previous — Codex Portable 0.153.2 Windows x64

- 固定 OpenAI Codex 0.153.2 Windows x64 runtime，并将 `codex.exe` 与 `codex-code-mode-host.exe` 作为不可拆分的 runtime pair。
- 当前固定身份：codex.exe SHA-256 e86ffd96751ded51f669b520d70ba3139b514eb36313a8eeeedde37baa7b58e3；codex-code-mode-host.exe SHA-256 ee37f218b8052cf7c2c99fcc5414da20c07262eaab14c81870c6ed8cd522d3f0。早期占位/待真机结论已由后续 Windows 完成态取代。
- Code Mode Host 缺失曾导致 `failed to spawn code-mode host`；现已纳入 launcher、checker、VerifyOnly 和 updater 的 package-local、regular-file、reparse/hardlink/ACL 与固定 SHA identity gate。每次真正 spawn Codex 前都会重新校验。
- updater 的 `-VerifyOnly` 改为严格只读：不获取 package exclusive lock、不下载、不替换、不删除、不另起 Codex version probe，因而可在当前实例运行时检查。真实更新保留独占锁，并对 Codex + Host 同时 stage、验证、替换、post-verify 后才 COMMIT；失败会回滚 pair，并在回滚失败时保留恢复材料。
- 默认 normal source 是受限 `on-request + workspace-write + shell network false`。YOLO 是独立预设，仅改变无人值守所需的三个权限值；它不改变 binary identity、Host gate 或认证隔离。
- 新增严格 `CODEX_FAST_MODE`：默认 `false` 明确生成 Standard/default tier；仅 `true` 生成 0.153.2 的 Fast tier。Fast 与 YOLO、模型和 Code Mode 独立。
- 默认模型配置为 `gpt-5.6-sol`；Fast、reasoning 与生成 config 的最终值由 launcher 输出与 runtime config 决定。
- Windows 真机验证已覆盖 PS5.1 解析、Code Mode Host spawn、正常工具动作、Fast source/config mapping、runtime-pair VerifyOnly、NTFS link/ACL gate、portable-process Job Object 路径、native/Python regressions 与 updater pair fault matrix。
- Clean Portable 发行包不携带开发检查器、版本升级工具与 DEV/TEST selftest；README、工具说明和 launcher 的恢复提示已同步，不再引导用户运行发行包中不存在的维护文件。

## Authentication and state safety

- API、account JSON、browser 三模式明确区分。
- `auth-account-json.json` 与 `auth-browser.json` 是互不覆盖的持久 snapshot；`auth.json` 是活动槽位；`mode` 记录活动槽位归属。
- 多文件切换使用 durable `auth-transition.block`；中断后的活动凭据会隔离，而不会猜测写回错误模式。
- 显式 logout 使用 per-mode block，直到新的成功登录才允许对应 snapshot 再次恢复。
- 缓存清理不删除认证 snapshot、transition/logout block、recovery 文件或 installation identity。

## R22–R23 — Windows reliability and launch correctness

- 修复 Windows CreateProcess 参数中空参数丢失、相对路径验证与实际消费目录不一致、认证模式提交顺序及中断恢复。
- 修复 Windows PowerShell 5.1 `File.Replace` 空备份参数兼容问题、generic list 兼容问题，以及 helper 定义顺序导致的 launcher failure。
- 将 launcher/checker 的 generated config、Fast default、runtime identity 和 Version_History 预设契约纳入回归。
- 识别并保留真实限制：当前运行中的主实例不会被强制终止以重生 config；受保护 Skill/vendor runtime 的缺失依赖或审计失败不能被 Project 层伪造为 PASS。

## R19–R21 — security and transaction hardening

- 对启动 BAT、PowerShell entry point、包路径、hardlink、junction/reparse、Windows device path 与宽松 ACL 加入 fail-closed gate。
- portable process supervisor 采用 CreateProcessW suspended、Job Object 先挂载后 resume、受限 stdout/stderr、timeout 与子树清理。
- HTTP/SOCKS bridge 限制 framing、代理凭据传播、deadline、worker cap 与失败清理。
- login JSON 路径、URL、子进程参数和异常信息处理收紧，避免凭据出现在命令行或诊断中。
- checker 的安全前置条件会阻止后续动态探针执行；optional 工具缺失与 required runtime failure 分级报告。

## R15–R18 — portable architecture foundation

- 建立 package-local PATH、环境隔离、SAFE/maintenance 分界、包内 cache/tmp/home 路由与 host-system-config gate。
- 固定 Provider/config 生成链，禁止高优先级 CLI 配置、sandbox、cwd、feature 等覆盖绕过入口策略。
- Node 的系统安装入口不随包保留；Python CLI 使用可再生相对路径 shim，避免旧机器绝对路径。
- 工具、Skills、Plugins、runtime 与 private state 分层：Project integration 可修复，upstream/vendor bytes 和真实凭据不可被审计/打包流程改写。

## Documentation and minimal distribution consolidation

- 将散落的使用说明、环境报告、迁移报告、审计整改、预检查、独立审计和验证报告整理为三个长期权威入口：根 `README.md`、根 `CHANGELOG.md`、`tool\\工具更新说明.md`。
- 旧 R18–R23 过程文档的有效事实被归并为当前操作、工具状态或历史演进；已被后续 Windows 证据推翻的“NOT RUN/待验证”中间状态不再描述为当前事实。
- 由完整工作树构建独立 Minimal Runnable staging：保留 runtime pair、核心 launcher/auth/process/network helper 与必要文档；排除真实认证、installation identity、session/cache/log/work、历史报告、测试证据与 optional 大型工具 payload。

## Historical boundary

旧预检查、审计报告、发布哈希记录和模型提示副本已归并并删除。`Version_History` 仅保留被迁移清单引用的预设脚本，以及用途尚不能确认可删除的本地账号格式转换器代码；这些材料不代表当前 launcher 状态。当前行为始终由根目录源码、README 和本 CHANGELOG 描述。
