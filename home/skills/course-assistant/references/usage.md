# Windows 独立前台会话

必须由本人另开 Windows PowerShell 窗口，从当前包根执行（示例域名和路径需替换，不带 query、片段或凭据）。不要从 Codex 的短命令/job 启动长期 owner。

    & .\tool\automation\course\course.ps1 -Action Owner -TaskAuthorized -Task class-a -Account a -Origin https://example.invalid -PagePath /course/lesson

另一窗口以 Account b 运行。Task/Account 为小写 ASCII 字母、数字、连字符/下划线，最长 48 字符，禁止 Windows 保留名。账号别名不是网站身份。本人在 Chromium 窗口正常打开站点并登录。默认只打开空白窗口，不导航。只有用户另行明确要求打开已确认不会开启计时的入口页时，才加 -OpenNonTimedLandingPage；它仅在 owner 启动时打开指定 origin/path，不能用于计时页、开始页或答题回跳。显示 COURSE_SESSION_READY 后记录 session ID。登录页、其他 origin/path 或多个匹配页不绑定；只有本人确认当前标签才 course_bind。绑定后主文档导航（包括同 URL 刷新）或 URL 变化（含 query/hash）拒绝继续；重新连接同 session 不会重新绑定、刷新、导航。下一页必须由本人操作并重新明确授权，可用 course_unbind(confirmed=true) 后，在同一授权路径内重新绑定；不同路径不属于该 owner 授权。

按既有用户 MCP 配置机制手动选择服务，显式 CODEX_PORTABLE_ALLOW_USER_MCP=true 和 --portable-extensions，保留交互审批。不要默认注册或绕过审批。下例仅供已授权的 a；b 用不同服务名和 Session。搬迁后按实际包根重新配置。

    [mcp_servers.course_a]
    command = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
    args = ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', 'D:\Codex\tool\automation\course\course.ps1', '-Action', 'Client', '-TaskAuthorized', '-Task', 'class-a', '-Account', 'a', '-Session', '<owner session ID>']
    cwd = 'D:\Codex\work'
    startup_timeout_sec = 120
    tool_timeout_sec = 120
    supports_parallel_tool_calls = false

Session 为 32 位小写十六进制随机值；owner 在账号 runtime 写仅本次有效的连接文件。不要复制、公开、持久化内容。client 只读精确文件，用随机密钥验证双方每次本地 IPC 请求；不监听 TCP/CDP，不搜索端口。连接文件依赖当前 Windows 用户的文件权限，不是对恶意同 OS 用户的沙箱。断开客户端不影响窗口；明确授权同一 session 才重连，失效连接不启动窗口。关闭由本人手动关窗或 course_close(confirmed=true)；正常关闭删本次连接文件，异常后文件不能连接新的 session。Client 同账号独占 client.lock，强制终止客户端后需确认原进程树退出才可重新连接。

规则允许且用户明确授权实际选取时，本人可启动 owner 时增加 -AllowPracticeSelection，默认不可选取。没有开始/交卷/导航/任意点击工具。仅支持原生 radio/checkbox 与关联 label；iframe、跨源、任意 JavaScript、自定义控件和自动提交风险不支持。示例选择器由实际授权页面观察确认：

    course_bind {confirmed:true}
    course_read {selector:"article .lesson",maxChars:12000}
    course_scroll {pixels:600}
    course_questions {questionSelector:".question",stemSelector:".stem"}
    course_select {questionSelector:".question",stemSelector:".stem",fingerprint:"<current>",choices:["完整选项"],confirmed:true}

course_questions 仅报告已渲染的题目，分段滚动后重读，按 fingerprint 核对并与页面显示总数对照。course_select 每次操作一题并回读；中途页面变化则停止，记录可能已产生的选择，不盲重试。提交由本人正常操作。course_status 不读取凭据或 URL query。

OCR：course_ocr_check {language:"zh-Hans-CN"}；再 course_ocr {selector:"article img.slide",pageSelector:".page-number",language:"zh-Hans-CN"}。报告目标语言、Windows 可用性（windowsSupported / zhHansSupported）、实际引擎与 actualLanguage。仅 zh-Hans-CN 的 Windows 引擎缺失时考虑经过分发审核的固定包内备援；目前开发锁关闭，无二进制分发。PNG 先验证签名、CRC、完整解码、20 MiB/4096 边长/16 Mi 像素上限；损坏、超限、非 PNG 和动画 PNG 拒绝。空输出 status=empty，不猜测内容；异常 stderr 不回显原文，固定已知 TIFF 字型诊断仅在原生返回成功且 TSV 合法时以 TIFF_FONT_UNAVAILABLE 代码报告。Windows 引擎可用但失败时不换引擎；缺语言不联网、不安装。只允许单个可见 img/canvas；OCR 即时返回、不落盘，临时 PNG 仅在账号 tmp。官方 API：https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr.ocrengine?view=winrt-26100

运行目录：work/course-<task>/<account>/{profile,cache,crashes,downloads,runtime,tmp,notes}。禁止浏览器下载。包内路径检查包含祖先、junction/reparse、单链接文件与解析结果；不防恶意同 OS 用户的并发替换。正常/YOLO/维护权限策略不变。Windows/Chromium 系统组件不保证零系统记录。不要修改宿主 PATH、注册表或系统语言。通用 browser-debug 和根缓存清理仍使用原状态；课件资料归 work。明确要求清理且对应 owner/client 均退出后，可用下列 Clean 命令；不清另一账号、notes 或宿主路径。

经本人/助手复核并去除个资、原始 OCR 和签名 URL 后，可调用 course_save_notes {slug:"lesson-a",markdown:"# 课程...",excludedText:["需剔除的标识"],confirmed:true}。只在当前账号 notes 下独占新建 course-lesson-a.md，不覆盖既有成果。工具仅拒绝常见签名 URL/凭据格式，不宣称自动识别全部个人资料；保存前仍须审核内容。


    & .\tool\automation\course\course.ps1 -Action Clean -TaskAuthorized -CleanupAuthorized -Task class-a -Account b

Clean 同时持有两个独占锁，检查相关包内进程和所有待删目录实际路径；若未退出、路径越界或检查失败则拒绝。只删指定账号 profile/cache/crashes/downloads/runtime/tmp，保留 notes 与锁文件。之后用同一 Owner 入口（不带 OpenNonTimedLandingPage）打开空白窗口，由本人登录。系统级 LocalLow/Intel/ShaderCache 等不由此工具清理；实际可能存在系统记录，Windows 验收必须如实记录。

保留练习时：

    course_progress {questionSelector:".question",stemSelector:".stem",totalSelector:"#total",expectedTotal:50,pendingSelector:"#submission-state",pendingText:"Not submitted",timerSelector:"#remaining"}

totalSelector 应精确指向显示题数的数字元素；pendingText 必须来自当前网页实际未提交状态。只有 rendered=answered=total 且 pending=true 才显示待交卷；siteTimer 是原站可见文本，不启动、修改、暂停或替代其计时。OCR 返回 pageLabel、imageSelector、bindingId 及 OCR 行词框；输出笔记引用页码与图表位置，不存原图、原始 OCR 或个人水印。excludedText 只能检查已识别并提供的标识，不能保证自动识别所有个资。

实际原生 Codex 验收使用正常/维护模式既有双重扩展选择，连接同一 owner；不自动保存或注册用户真实 MCP。`course_progress` 的已答数量只表示选中，不代表正确，保留前须按题干和完整选项再次核对。
