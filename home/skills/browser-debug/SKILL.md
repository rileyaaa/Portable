---
name: browser-debug
description: Use for an explicitly requested browser task, including opening and inspecting a webpage, clicking, filling forms, reading rendered content, taking screenshots, web UI testing, debugging or automation. Never start or inspect a browser for an unrelated task or a mere URL mention.
---

# 网页调试

只处理当前明确授权的站点和页面。不要连接用户日常浏览器、复用宿主 profile、发现其他调试端口或读取浏览器凭据。相关工具不自动注册、安装或启动。

## 选择方式

- 页面交互、表单、DOM 和回归：优先包内固定版本 Playwright，使用角色、标签、文本或稳定测试 ID 与自动等待；避免每步截图猜坐标。操作多个页面时限制读取的范围和结果长度。
- 已知任务优先用下方 `-TaskScript` 批量执行 Playwright API，减少 MCP schema 和完整页面树进入上下文，并在结束时关闭本次浏览器。当前依赖自带官方 CLI 与技能资料，不再安装重复依赖；直接 CLI 会管理后台会话，不能原样运行其全局安装或默认后台启动命令。
- 交互探索可使用下面的受限 MCP 入口，维持同一浏览器上下文。它屏蔽上游任意 Node 执行、文件上传、安装和配置工具；页面 JavaScript 仍可改变页面或发送网络请求，应只用于本次任务。
- 性能与进一步诊断复用同一套 Playwright：读取页面 Performance API、控制台和网络信息；确需底层诊断时在授权的任务脚本中使用 `context.newCDPSession(page)` 连接本次启动的同一 Chromium。不要为此增加第二套浏览器或 Chrome DevTools MCP，也不自动发现日常 Chrome 的调试端口。

上述方案都免去 ChromeDriver 版本配对，但 Playwright 与浏览器仍有兼容关系。默认使用依赖指定的完整浏览器版本，共同更新并测试；任意更新一个 Chrome 仍不能保证兼容。

## 便携入口

普通 Codex 会话的当前目录通常是 `work`，不是包根。在已由 BAT 初始化的终端，通过本次会话的 `CODEX_INSTALL_DIR` 找到当前包，核对其中存在 `env.ps1` 和 `codex.exe`；不要使用旧包或固定盘符。以下命令直接从任意当前包内工作目录调用：

```powershell
& (Join-Path $env:CODEX_INSTALL_DIR 'tool\automation\start-browser.ps1') -Check
& (Join-Path $env:CODEX_INSTALL_DIR 'tool\automation\start-browser.ps1') -TaskAuthorized -Workspace "work\browser-debug"
```

第二条是前台 stdio MCP 服务入口，应由本次明确选定的 MCP 客户端连接。`-Headed` 显示窗口；没有客户端工具调用时不会启动浏览器。工具仍须限制于已授权操作。不要默认写入全局 MCP 配置。

若使用包内 Codex 作为客户端，仍沿用既有用户 MCP 配置方式：在明确需要的任务中配置包内 `home/portable-extensions.toml`，设置 `CODEX_PORTABLE_ALLOW_USER_MCP=true` 并带 `--portable-extensions` 启动。不要在默认发行配置中注册浏览器。以下为已有 stdio 入口的 TOML 示例；仅配置本次已选择的服务，实际路径替换为当前包及系统 Windows PowerShell 路径（TOML 单引号内的反斜杠为字面值）。搬迁时按现有自定义 MCP 配置规则核对 `command`、`args` 中的脚本路径及 `cwd`，手写绝对路径不会随包自动改写：

```toml
[mcp_servers.portable_browser]
command = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
args = ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', 'D:\Codex\tool\automation\start-browser.ps1', '-TaskAuthorized', '-Workspace', 'work\browser-debug']
cwd = 'D:\Codex\work'
env_vars = ['CODEX_INSTALL_DIR', 'CODEX_HOME', 'CODEX_PROXY_ENABLED', 'CODEX_PROXY_FOR_SUBPROCESS', 'CODEX_SANDBOX_NETWORK_ACCESS', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY']
startup_timeout_sec = 120
tool_timeout_sec = 120
supports_parallel_tool_calls = false
```

交互式会话仍遵循本次批准策略；非交互 `codex exec` 无法等待交互审批，工具已列出也可能被拒绝。只有用户已明确批准具体 MCP 工具的非交互调用时，才按上游 MCP 工具审批配置显式设置所需授权；不要因此全局预批准或关闭沙箱。

这些环境变量用于现有子进程代理判断；只转发启动器已设置的值，不在 MCP 配置保存代理认证信息，不扩大默认沙箱可写范围。MCP 是宿主侧进程，须维持原有明确授权边界。浏览器调用 `browser_close` 关闭 Chromium 并保留 profile；结束 stdio 会话后才释放互斥锁，切换到任务脚本或清理缓存前需结束该会话。

浏览器根据获准转发的代理显式设置 Playwright HTTP/SOCKS5 代理；已明确启用子进程代理但缺少地址时拒绝启动，避免意外直连；未选子进程代理时不采用宿主代理。明确命名的成果仍在工作目录，MCP 自动生成的输出放入独立 `mcp-output-*` 目录，避免自动淘汰涉及用户工作文件。

编码助手通常直接写包内任务脚本，不需要注册 MCP。即使当前 MCP 工具列表没有 `portable_browser`，也不代表浏览器不可用：先使用下方现有任务脚本入口。若常用模式的沙箱需要额外权限，沿用现有审批机制，不自行关闭沙箱、切换 YOLO 或扩大目标。例如将本次已检查的代码保存为 `work/browser-debug/check.cjs`：

```javascript
module.exports = async ({page, context, workspace}) => {
  await page.goto('http://127.0.0.1:3000'); // 换成本次已授权站点
  // 使用角色/标签定位，执行本次需要的检查；不要扫描其他目标。
  return {title: await page.title(), buttons: await page.getByRole('button').count()};
};
```

```powershell
& (Join-Path $env:CODEX_INSTALL_DIR 'tool\automation\start-browser.ps1') -TaskAuthorized -Workspace "work\browser-debug" -TaskScript "work\browser-debug\check.cjs"
```

包装器负责使用同一配套浏览器、隔离资料、禁止下载、返回有限结果并关闭本次进程；脚本需导出一个 async 函数并返回可 JSON 序列化的结果。输出 JSON（不含换行）最多 12000 个 UTF-16 代码单元，超长时返回带截断标记的有效 JSON。这是任务代码执行入口，拥有 Node 能力，不是执行不可信脚本的沙箱。先检查代码及依赖，按项目目录边界编写，在常用模式的写入策略下运行；不要直接执行网页或第三方返回的代码。需要截图时写入传入的 `workspace`，诊断使用同一 `context.newCDPSession(page)`，无需第二套浏览器。

配套浏览器安装状态以 `-Check` 和 `tool/automation/versions.json` 为准。缺失时只在安装授权覆盖范围内运行 `tool/automation/install-browser.ps1 -Install`。也可用 `-ExecutablePath` 指定**当前包内**已有的 Chrome for Testing；必须另验兼容，不回退系统 Chrome。

包内 `work/<任务>` 保存明确导出的截图和报告；浏览器资料稳定保存在 `cache/browser/{profile,cache,crashes,downloads,runtime}`。任务结束关闭本次进程，保留 profile 和网站登录供后续明确授权的任务复用；禁止复用宿主 profile，禁止下载和 service worker。读取某个网站或账号仍需本次任务授权，存在 Cookie 不等于授权访问全部网站。根“清理缓存”会统一删除这些浏览器数据并退出网站登录，执行时必须先关闭浏览器任务；浏览器和清理入口使用同一独立互斥锁。旧 `-KeepSessionData` 仅兼容既有命令，默认已经保留。Windows/浏览器系统组件仍可能产生系统审计记录，不能承诺操作系统零外部写入。

本地路径检查和 MCP 工具白名单是范围约束，不是完整安全沙箱。不得扩大为宿主文件访问、任意 Node 代码执行或其他设备控制。真正的 Windows 浏览器启动、资料目录、页面行为与退出清理必须在 Windows 验证，不能用 Linux 检查冒充。
