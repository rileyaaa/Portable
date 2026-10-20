---
name: windows-desktop
description: Use only when the user explicitly requests inspecting or operating a specified Windows application. Never activate from a Windows mention, an unrelated task, or skill discovery.
---

# Windows 应用调试

先确定用户授权的应用、进程及本次动作，不枚举整个桌面、其他窗口或个人资料。包内安装不会限制目标应用自身的写入位置；点击保存、设置、删除、发送等动作的影响仍须属于用户任务。工具开关只是调用方确认，不能代替用户授权。

使用当前包内 `tool/automation/desktop.ps1`；仅支持 Windows 的 UI Automation，系统组件不需安装。默认读取指定进程主窗口的有界控件树，不读密码控件，不使用剪贴板或坐标盲点，不提供全盘文件、任意 Shell、注册表或全桌面 MCP。

```powershell
# TargetProcessId 必须来自本次已选定的应用，不扫描其他应用寻找目标。
.\tool\automation\desktop.ps1 -TaskAuthorized -TargetProcessId 1234 -Action Tree
.\tool\automation\desktop.ps1 -TaskAuthorized -TargetProcessId 1234 -Action Invoke -AutomationId "previewButton" -AllowChanges
```

只调用当前树中唯一、可见、启用且属于目标进程的 AutomationId；树截断、匹配不唯一或目标变化时停止。`SetValue -Value "..." -AllowChanges` 只用于非密码、可编辑的字段。优先用应用自己的诊断接口；Electron/Web 页面调试优先浏览器方案。UI Automation 看不到的自绘、游戏或远程桌面控件须说明限制，不能自动扩大为全屏截图和全局鼠标键盘控制。

子进程缓存、用户目录和临时文件重定向到包内独立 `tmp/desktop-*`，受 30 秒进程监督；只清理本次会话文件。目标应用不会被启动或杀掉。实际输入可能在超时前已生效，应先检查目标状态，不能盲目重试。

已评估 Windows-MCP，但其默认桌面、Shell、文件和注册表工具范围过大，当前不安装或注册。确需全桌面工作流时重新确认具体范围和上游能力；不要把网络 MCP 权限或包内目录当作系统沙箱。Linux 语法/策略检查不等于 Windows UI Automation 已验收。
