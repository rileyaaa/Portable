# ============================================================
# Codex Portable 配置文件
# 日常只改这个文件。换电脑时，把整个 Codex 文件夹一起带走。
# ============================================================

# ------------------------------------------------------------
# 0. 严格便携开关
# ------------------------------------------------------------
# 目标：所有 Codex 配置、日志、缓存、临时文件、工作目录都落在当前 Codex 目录下。
# 推荐保持 strict。
$env:CODEX_PORTABLE_PROFILE = "strict"

# PATH 固定为包内工具链 + Windows 必需系统目录；不提供宿主 PATH 回退开关。
# 如真实环境需要新增工具，请把工具放入 Codex\tool 并在检查器/安装脚本中登记。

# 是否允许 Codex 在需要越权时弹窗请求批准。
# 普通模式默认 on-request；Codex 0.149.0 起已移除旧值 untrusted，0.166.0 会拒绝该值。
# Version_History 的 YOLO 预设会把本项与 sandbox/network 三项一起切换。
$env:CODEX_APPROVAL_POLICY = "never"

# 沙箱模式：
# workspace-write = 仅允许写入工作区/便携包声明目录（受限模式）
# danger-full-access = 关闭文件系统沙箱；必须与 approval_policy=never 配对
$env:CODEX_SANDBOX_MODE = "danger-full-access"

# 无参数双击启动时是否显示登录、思考强度、联网和代理选择菜单。
# true = 常用模式显示菜单；false = 完全按 env.ps1 自动启动。
$env:CODEX_STARTUP_INTERACTIVE = "true"

# 带命令行参数启动（例如 exec / resume --last）时使用的认证模式。
# menu = 无参数时显示菜单，有参数时保持兼容并使用 api；last = 复用上次菜单选择。
# 也可固定为 api / account_json / browser。
$env:CODEX_AUTH_MODE = "menu"

# 官方账号登录方式（认证模式 browser / auth-browser.json 名称保持兼容）：
# device_auth = 默认设备码；账号须启用设备码登录，不自动打开宿主浏览器，失败不自动回退。
# system_browser = 仅在明确选择后打开系统默认浏览器，会读写宿主浏览器用户数据。
# 也可在 env.local.ps1 显式覆盖；不支持设备码时可改用账号 JSON 导入。
$env:CODEX_BROWSER_LOGIN_FLOW = "device_auth"

# 是否允许 Codex 执行的 shell 命令访问网络。
# 注意：这里限制的是 Codex 调用的本地命令，不影响 Codex 自己访问你的 API 接口。
# 普通模式默认禁止本地工具联网；YOLO 预设会与 approval/sandbox 一起明确开启。
$env:CODEX_SANDBOX_NETWORK_ACCESS = "true"

# Fast 服务层开关（与 YOLO、模型、Code Mode 相互独立）。
# false = 显式生成 service_tier="default"，保持 Standard 并阻止账号资格自动启用 Fast。
# true  = 生成 Codex 0.166.0 配置拼写 service_tier="priority"（旧值 fast 为兼容别名）。
$env:CODEX_FAST_MODE = "false"

# ------------------------------------------------------------
# 0.1 自定义 Provider 是否禁用 WebSocket
# ------------------------------------------------------------
# Codex 0.166.0 已移除 responses_websockets / responses_websockets_v2 feature；本包使用 provider.supports_websockets；
# provider 级 supports_websockets 才是本包的主控制。true=禁用 WS；false=只有在该上游确实支持 Responses WebSocket 时才声明 true。
# 自定义 Provider 的 supports_websockets 默认值本身就是 false，所以不能靠“省略字段”表达启用。
# custom_provider 会显式双向写 true/false；local_ollama 固定 HTTP/SSE。
# official_chatgpt 在禁用 WebSocket 时使用等价的 HTTP-only OpenAI-auth Provider。
$env:CODEX_DISABLE_WEBSOCKET = "true"

# ------------------------------------------------------------
# 0.2 模型输入能力：自动优先，手工覆盖只做兼容兜底
# ------------------------------------------------------------
# auto（推荐）：如果模型 slug 能匹配当前 codex.exe bundled catalog，就继承官方 input_modalities；
#               匹配不到的第三方/本地模型不强写该字段，让 Codex 0.166.0 使用自身兼容默认。
# text：       明确强制纯文本；会关闭 image_generation 注册。
# text_image： 明确强制文字+图片。
# 正常情况下不要改 auto；只有特殊中转模型兼容异常时再手工覆盖。
$env:CODEX_MODEL_MODALITIES = "auto"

# ------------------------------------------------------------
# 0.3 Codex Apps / 外部连接器
# ------------------------------------------------------------
# true  = 禁用 Codex Apps，避免未使用外部连接器时初始化 codex_apps MCP。
# false = 启用 Codex Apps，用于已授权的外部应用和连接器。
# 不影响本地文件、shell、模型 API，以及不依赖外部连接器的本地 Skills。
$env:CODEX_DISABLE_APPS = "true"

# 本地 Plugins 默认关闭；只有明确相关任务才添加启动参数 --portable-extensions。
# true  = 允许本次带 --portable-extensions 的会话启用 home\plugins
# false = 禁用本地插件功能；维护模式也不会自动启用
$env:CODEX_ENABLE_PLUGINS = "false"

# 是否允许插件分享/发布
$env:CODEX_ENABLE_PLUGIN_SHARING = "false"

# User-defined [mcp_servers.*] entries can launch host-side processes outside the workspace sandbox.
# Configuration stays persistent, but activation requires BOTH this value=true and --portable-extensions.
# Maintenance mode does not activate MCP. Enable it only for an explicitly requested related task.
$env:CODEX_PORTABLE_ALLOW_USER_MCP = "false"

# ------------------------------------------------------------
# 0.4 本地代理（v2ray / Clash 等）
# ------------------------------------------------------------
# 让 Codex 访问模型 API 时走本机代理，常用于接口慢/不稳时加速。
# 注意：这影响的是 Codex 自己访问 API 的连接，与上面"联网"开关无关。
#
# 是否默认开启代理：false=默认关（启动菜单可临时开）；true=默认开。
$env:CODEX_PROXY_ENABLED = "false"
# 代理协议：socks5(推荐) 或 http。v2ray 混合口两者都行，socks5 更轻量。
$env:CODEX_PROXY_PROTOCOL = "socks5"
# 代理地址与端口（v2ray 本地默认 127.0.0.1:10808）。
$env:CODEX_PROXY_HOST = "127.0.0.1"
$env:CODEX_PROXY_PORT = "10808"
# socks5 模式下给 Codex.exe 自动开一个本地 HTTP CONNECT bridge。
# 原因：PySocks 只对 Python 检测脚本生效，Codex.exe 本身不一定识别 socks5/ALL_PROXY。
$env:CODEX_PROXY_HTTP_BRIDGE = "true"
# 安全限制：bridge 只允许监听 localhost/127.0.0.1/::1。端口留空时每次启动随机选择空闲本地端口；仅在确需固定端口时填写 1-65535。
$env:CODEX_PROXY_BRIDGE_HOST = "127.0.0.1"
$env:CODEX_PROXY_BRIDGE_PORT = ""
# 联网开启时，Codex 在本机跑的命令(npm/pip)是否也走上面的代理。
# 仅在"联网 + 代理"都开时才有意义；双击启动时若两者都开，菜单会再追问一次。
# false=只代理 API 连接(默认)；true=本机下依赖也走代理。
$env:CODEX_PROXY_FOR_SUBPROCESS = "false"

# 开代理时，"模型接口地址"(CODEX_BASE_URL 的主机)是否始终直连、不走代理。
# true(默认,推荐)=把模型主机加入 NO_PROXY。本机/局域网/国内自建的 Ollama、中转，
#   开代理也不会被劫持导致连不上（典型坑：开代理给别的 API 加速，却把直连的模型搞挂）。
# false=模型接口也走代理。仅当你的 CODEX_BASE_URL 指向"必须翻墙才能访问的境外 API"时才需要。
$env:CODEX_PROXY_BYPASS_MODEL = "true"

# 账号 JSON 检查/登录访问 chatgpt.com 的网络模式：
# auto   = 先直连/TUN，网络失败时最后再试本地代理端口（推荐）
# direct = 只直连/TUN
# proxy  = 只走 CODEX_PROXY_PROTOCOL/HOST/PORT 指定的本地代理端口
$env:CODEX_LOGIN_JSON_PROXY_MODE = "auto"
# Python/curl 连接阶段超时（1-30 秒）；powershell 后端仅支持整体请求超时。
$env:CODEX_LOGIN_JSON_CONNECT_TIMEOUT_SEC = "8"
$env:CODEX_LOGIN_JSON_HTTP_BACKEND = "python"
# 单个账号后台检测任务的总超时（30-3600 秒）；覆盖刷新、模型和额度检测，默认 420 秒。
$env:CODEX_LOGIN_JSON_JOB_TIMEOUT_SEC = "420"
$env:CODEX_LOGIN_JSON_THROTTLE = "12"  # login_json 检查并发数；账号很多时可临时调到 20
$env:CODEX_LOGIN_JSON_MAX_FILES = "0"   # 0 = 检查全部；临时抽样建议运行 检查login_json.bat -MaxFiles 10

# ------------------------------------------------------------
# 0.5 Android APK Lab / 本地工具链便携目录
# ------------------------------------------------------------
# 这些目录用于 android-apk-lab 插件和 Skills；全部基于便携包根目录动态生成。
# 包根只从当前 env 文件自身位置向上解析，不信任宿主预先注入的 CODEX_INSTALL_DIR。
# 这样即使直接 dot-source env.ps1，也不会被外部环境变量诱导去加载包外 env.local.ps1。
$Script:CodexPortableRoot = $null
$candidate = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
for ($depth = 0; $depth -lt 6; $depth++) {
    if ((Test-Path -LiteralPath (Join-Path $candidate 'codex.exe') -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $candidate 'env.ps1') -PathType Leaf)) {
        $Script:CodexPortableRoot = $candidate
        break
    }
    $parent = Split-Path -Parent $candidate
    if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $candidate) { break }
    $candidate = $parent
}
if ([string]::IsNullOrWhiteSpace($Script:CodexPortableRoot)) { throw "无法定位 Codex Portable 根目录：$PSScriptRoot" }
$Script:CodexPortableRoot = [IO.Path]::GetFullPath($Script:CodexPortableRoot).TrimEnd('\')
$RootItem = Get-Item -LiteralPath $Script:CodexPortableRoot -Force -ErrorAction Stop
if (($RootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "拒绝以重解析点作为 Codex Portable 根目录：$Script:CodexPortableRoot" }
$ScriptFull = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$Cursor = $Script:CodexPortableRoot
$RelativeScriptPath = $ScriptFull.Substring($Script:CodexPortableRoot.Length).TrimStart('\')
foreach ($Segment in @($RelativeScriptPath -split '\\')) {
    if ([string]::IsNullOrWhiteSpace($Segment)) { continue }
    $Cursor = Join-Path $Cursor $Segment
    if (Test-Path -LiteralPath $Cursor) {
        $Item = Get-Item -LiteralPath $Cursor -Force -ErrorAction Stop
        if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "拒绝通过重解析点加载便携配置：$Cursor" }
    }
}
$env:CODEX_INSTALL_DIR = $Script:CodexPortableRoot
$env:CODEX_PYTHON = Join-Path $Script:CodexPortableRoot "tool\python\python.exe"
$env:ANDROID_HOME = Join-Path $Script:CodexPortableRoot "tool\android\sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:ANDROID_USER_HOME = Join-Path $Script:CodexPortableRoot "home-runtime\.android"
$env:ANDROID_SDK_HOME = Join-Path $Script:CodexPortableRoot "home-runtime"
$env:JAVA_HOME = Join-Path $Script:CodexPortableRoot "tool\android\jdk"
$env:ADB_VENDOR_KEYS = Join-Path $Script:CodexPortableRoot "home-runtime\.android\adbkey"
$env:APKTOOL_FRAMEWORK_DIR = Join-Path $Script:CodexPortableRoot "cache\android\apktool-framework"
$env:FRIDA_CACHE_DIR = Join-Path $Script:CodexPortableRoot "cache\android\frida"
$env:MITMPROXY_HOME = Join-Path $Script:CodexPortableRoot "cache\android\mitmproxy"
$env:APPIUM_HOME = Join-Path $Script:CodexPortableRoot "cache\android\appium"
$env:APK_LAB_CACHE_DIR = Join-Path $Script:CodexPortableRoot "cache\android\apk-lab"
$env:APK_LAB_TMP_DIR = Join-Path $Script:CodexPortableRoot "tmp\android"
$env:APK_LAB_JOBS_DIR = Join-Path $Script:CodexPortableRoot "work\apk-jobs"

# ------------------------------------------------------------
# 1. 接口模式（r15-clean 只保留真实使用路径）
# ------------------------------------------------------------
# 可选值：
#   custom_provider  = OpenAI-compatible 中转站（你的主要 API 模式）
#   local_ollama     = 本机/局域网 Ollama
#   official_chatgpt = 官方 ChatGPT 账号路径；由登录方式 2/3 自动切换，通常不要手工设置
$env:CODEX_PROVIDER_MODE = "custom_provider"

# ------------------------------------------------------------
# 2. 通用 API 配置
# ------------------------------------------------------------
# custom_provider 使用 OPENAI_API_KEY；local_ollama 不需要 Key。
# official_chatgpt 使用 auth.json/账号 JSON，不读取中转站 Key。
# 私密 Key 放在真实包根目录 env.local.ps1；该文件已加入 .gitignore。
$env:OPENAI_API_KEY = ""

# API 地址：custom_provider 一般以 /v1 结尾；local_ollama 留空时默认 http://127.0.0.1:11434/v1。
# 示例：https://your-relay.example/v1 或 http://192.168.1.10:11434/v1
#$env:CODEX_BASE_URL = ""

# 模型名：必须和中转平台或 Ollama 暴露的模型名一致。
$env:CODEX_MODEL = "gpt-6-sol"

# 可选：用本地文件替换 Codex 内置模型指令。留空时不会写 model_instructions_file，
# 模型身份提示改用附加型 developer_instructions，不影响 Codex 内置指令。
# 相对路径会基于 home 解析。tool\codex-instruct.py 会把持久覆盖写入 env.local.ps1。
# 为兼容旧版本手工文件，只自动发现“与当前 CODEX_MODEL 同名”的 *-unrestricted.md；
# 自动发现使用 env.local.ps1 / 登录选择 / --model 覆盖后的模型；显式指令路径或显式空值优先。
$env:CODEX_MODEL_INSTRUCTIONS_FILE = ""
$script:CodexPortableAutoModelInstructions = $true
function Find-CodexPortableModelInstructions {
    param([string]$Model)
    if ([string]::IsNullOrWhiteSpace($Model)) { return "" }
    $ModelInstructionSafeName = ([string]$Model -replace '[<>:"/\\|?*]', '_').Trim()
    $ModelInstructionLegacyName = $ModelInstructionSafeName -replace '^gpt-', 'gpt'
    $InstructionCandidates = New-Object System.Collections.Generic.List[string]
    foreach ($Name in @($ModelInstructionSafeName, $ModelInstructionLegacyName) | Select-Object -Unique) {
        if ([string]::IsNullOrWhiteSpace($Name)) { continue }
        [void]$InstructionCandidates.Add((Join-Path $Script:CodexPortableRoot ("home\" + $Name + "-unrestricted.md")))
        [void]$InstructionCandidates.Add((Join-Path $Script:CodexPortableRoot ($Name + "-unrestricted.md")))
        [void]$InstructionCandidates.Add((Join-Path $Script:CodexPortableRoot ("Version_History\" + $Name + "-unrestricted.md")))
    }
    $PortableInstructionsFile = Get-ChildItem -LiteralPath @($InstructionCandidates) -File -ErrorAction SilentlyContinue | Select-Object -First 1
    return $(if ($null -eq $PortableInstructionsFile) { "" } else { $PortableInstructionsFile.FullName })
}

# Codex 当前推荐使用 responses wire API。通常不要改。
$env:CODEX_WIRE_API = "responses"

# 自定义/本地 provider 总是生成包内兼容 catalog，保留模型元数据并关闭内部 Responses Lite。
# 显式 modality/context 覆盖也写入此目录；官方账号继续使用原生目录。
# 文件由 run-codex.ps1 原子生成，请勿手工编辑。
$env:CODEX_MODEL_CATALOG_JSON = "home\model-catalog.custom.json"

# 自定义/本地模型的上下文窗口(token)。默认留空：不显式覆盖匹配到的原生上下文；
# 手工 modality 覆盖时若仍留空：能匹配 bundled 的模型保留其原 context/max；真正 unknown 才使用 0.166.0 的保守 272000 fallback。
$env:CODEX_MODEL_CONTEXT_WINDOW = ""

# 模型思考强度（reasoning effort）。
# custom_provider/local_ollama 默认留空：启动器不显式覆盖 effort；客户端仍可能采用模型目录默认值。
# official_chatgpt 在交互菜单中会从 bundled catalog 读取真实可选档位与默认。
# 如中转站明确支持 reasoning.effort，可填 low / medium / high / xhigh 或上游接受的自定义非空值。
$env:CODEX_REASONING_EFFORT = ""

# 底部状态栏的目录项。当前 Codex TUI 会异步加入右侧状态信息；中文/CJK
# 终端还可能把中点分隔符“·”显示为 2 列，而 TUI 布局按 1 列计算，最终覆盖左侧
# 最后 1 个字符（例如 medium 变成 mediu）。
# 默认 none：底部只显示“模型 + 推理等级”，目录仍会在启动欢迎框中完整显示。
# 可选：none（推荐）/ project-root（项目根目录名）/ current-dir（完整当前目录）。
$env:CODEX_STATUS_LINE_DIR_ITEM = "none"

# 全屏转录视图：false 使用终端 scrollback；true 使用 Codex Fullscreen。
# 默认关闭。可在 env.local.ps1 覆盖；每次启动重新生成配置，不能靠 /tui 保存长期偏好。
# --no-alt-screen 仍有优先限制；本项不改变认证、权限、代理或 --no-daemon。
$env:CODEX_TUI_FULLSCREEN_TRANSCRIPT = "false"

# ------------------------------------------------------------
# 3. custom_provider 可选配置
# ------------------------------------------------------------
$env:CODEX_PROVIDER_ID = "myproxy"
$env:CODEX_PROVIDER_NAME = "My Proxy"

# 静态 HTTP headers，必须是 TOML inline table 格式。
# 示例：'{ "HTTP-Referer" = "https://your-site.example", "X-Title" = "Codex Portable" }'
$env:CODEX_HTTP_HEADERS_TOML = ""

# 从环境变量读取 HTTP headers，必须是 TOML inline table 格式。
# 示例：'{ "HTTP-Referer" = "MY_HTTP_REFERER", "X-Title" = "MY_X_TITLE" }'
$env:CODEX_ENV_HTTP_HEADERS_TOML = ""

# query 参数，必须是 TOML inline table 格式。
# 示例：'{ "api-version" = "2025-04-01-preview" }'
$env:CODEX_QUERY_PARAMS_TOML = ""


# 本机私密覆盖文件按“纯数据”读取，不再 dot-source 执行 PowerShell。
# 允许格式只有：$env:NAME = "value" 或 $env:NAME = 'value'（以及空行/整行注释/行尾注释）。
# 这样 API Key、模型、Base URL、代理和自定义 header 仍可持久配置，但 env.local.ps1 不能成为任意代码执行入口。
function Import-CodexPortableLocalEnv {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return }
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "拒绝通过重解析点加载 env.local.ps1：$Path" }
    $linkTypeProperty = $item.PSObject.Properties['LinkType']
    $linkType = if ($null -ne $linkTypeProperty) { [string]$linkTypeProperty.Value } else { '' }
    if ($linkType -eq 'HardLink' -or ([string]$item.Mode).Contains('l')) { throw "env.local.ps1 must not be a hard link: $Path" }

    # 这些值属于便携边界/预设策略，不允许 env.local.ps1 低层覆盖。
    # 如确需改变审批/沙箱/网络，请修改对应 env.ps1 预设本身。
    $protectedExact = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($name in @(
        'PATH','HOME','USERPROFILE','HOMEDRIVE','HOMEPATH','APPDATA','LOCALAPPDATA','PROGRAMDATA','ALLUSERSPROFILE',
        'SYSTEMROOT','WINDIR','SYSTEMDRIVE','COMSPEC','PATHEXT','OS','PROCESSOR_ARCHITECTURE','PROCESSOR_IDENTIFIER','NUMBER_OF_PROCESSORS','USERNAME','COMPUTERNAME',
        'TEMP','TMP','TMPDIR','CODEX_HOME','CODEX_SQLITE_HOME','CODEX_INSTALL_DIR','CODEX_PYTHON','CODEX_PORTABLE_PROFILE',
        'CODEX_APPROVAL_POLICY','CODEX_SANDBOX_MODE','CODEX_SANDBOX_NETWORK_ACCESS','CODEX_FAST_MODE','GOTOOLCHAIN','GIT_CONFIG_NOSYSTEM',
        'MAVEN_OPTS','POWERSHELL_TELEMETRY_OPTOUT','PSModuleAnalysisCachePath','PSModulePath','JAVA_HOME','ADB_VENDOR_KEYS',
        'APKTOOL_FRAMEWORK_DIR','FRIDA_CACHE_DIR','MITMPROXY_HOME','APPIUM_HOME'
    )) { [void]$protectedExact.Add($name) }
    $protectedPatterns = @(
        '^(?i:XDG_)','^(?i:PIP_)','^(?i:PYTHON)','^(?i:NPM_)','^(?i:NODE_)','^(?i:YARN_)','^(?i:PNPM_)',
        '^(?i:GO(PATH|CACHE|MODCACHE|ROOT|TOOLCHAIN)$)','^(?i:GRADLE_USER_HOME$)','^(?i:UV_)','^(?i:ANDROID_)','^(?i:APK_LAB_)',
        '^(?i:GIT_)','^(?i:SSH_)','^(?i:GPG_)','^(?i:CONDA_)','^(?i:DOCKER_)','^(?i:SSL_CERT_)',
        '^(?i:HTTP_PROXY|HTTPS_PROXY|ALL_PROXY|NO_PROXY|http_proxy|https_proxy|all_proxy|no_proxy)$',
        '^(?i:REQUESTS_CA_BUNDLE|CURL_CA_BUNDLE|BASH_ENV|ENV|CDPATH|RUBYOPT|RUBYLIB|PERL5OPT|PERL5LIB|KUBECONFIG|VIRTUAL_ENV)$',
        '^(?i:CODEX_API_KEY|CODEX_ACCESS_TOKEN|OPENAI_FEDERATION_RULE_ID|OPENAI_IDENTITY_TOKEN_FILE|OPENAI_WORKLOAD_IDENTITY_CONTEXT)$'
    )

    # CODEX_* is not an arbitrary pass-through interface. Native diagnostic,
    # installer and remote-runtime variables can open/write paths before the
    # execution sandbox. Add supported settings here only after auditing the
    # upstream consumer; ordinary custom header variables remain available.
    $supportedCodex = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($name in @(
        'CODEX_ALLOW_HOST_SYSTEM_CONFIG','CODEX_AUTH_MODE','CODEX_BASE_URL','CODEX_BROWSER_LOGIN_FLOW',
        'CODEX_DISABLE_APPS','CODEX_DISABLE_WEBSOCKET','CODEX_ENABLE_PLUGINS','CODEX_ENABLE_PLUGIN_SHARING',
        'CODEX_ENV_HTTP_HEADERS_TOML','CODEX_HTTP_HEADERS_TOML','CODEX_QUERY_PARAMS_TOML',
        'CODEX_LOGIN_JSON_ALLOW_DIRECT','CODEX_LOGIN_JSON_ALLOW_DIRECT_PARALLEL',
        'CODEX_LOGIN_JSON_CONNECT_TIMEOUT_SEC','CODEX_LOGIN_JSON_HTTP_BACKEND','CODEX_LOGIN_JSON_JOB_TIMEOUT_SEC',
        'CODEX_LOGIN_JSON_MAX_CREDENTIALS','CODEX_LOGIN_JSON_MAX_FILES','CODEX_LOGIN_JSON_PROXY_MODE','CODEX_LOGIN_JSON_THROTTLE',
        'CODEX_MODEL','CODEX_MODEL_CATALOG_JSON','CODEX_MODEL_CONTEXT_WINDOW','CODEX_MODEL_INSTRUCTIONS_FILE','CODEX_MODEL_MODALITIES',
        'CODEX_PORTABLE_ALLOW_USER_MCP','CODEX_PROVIDER_ID','CODEX_PROVIDER_MODE','CODEX_PROVIDER_NAME',
        'CODEX_PROXY_BRIDGE_HOST','CODEX_PROXY_BRIDGE_PORT','CODEX_PROXY_BYPASS_MODEL','CODEX_PROXY_ENABLED',
        'CODEX_PROXY_FOR_SUBPROCESS','CODEX_PROXY_HOST','CODEX_PROXY_HTTP_BRIDGE','CODEX_PROXY_PORT','CODEX_PROXY_PROTOCOL',
        'CODEX_REASONING_EFFORT','CODEX_STARTUP_INTERACTIVE','CODEX_STATUS_LINE_DIR_ITEM','CODEX_WIRE_API',
        'CODEX_TUI_FULLSCREEN_TRANSCRIPT'
    )) { [void]$supportedCodex.Add($name) }

    # 双引号值按字面量读取（不做 PowerShell 插值）；单引号值仅支持数据文件常见的 '' -> '。
    # 分成两个表达式而不是依赖备选捕获组，避免 PowerShell $Matches 对未命中组返回空串时
    # 把单引号值误解析成空值。
    $doubleAssignmentPattern = '^\s*\$env:([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"([^"]*)"\s*(?:#.*)?$'
    $singleAssignmentPattern = '^\s*\$env:([A-Za-z_][A-Za-z0-9_]*)\s*=\s*''((?:''''|[^''])*)''\s*(?:#.*)?$'
    $lineNo = 0
    foreach ($line in [IO.File]::ReadAllLines($Path, (New-Object Text.UTF8Encoding($false)))) {
        $lineNo++
        # 兼容由 codex-instruct.py / Windows PowerShell 写出的 UTF-8 BOM。
        # BOM 只允许出现在文件首行开头，并作为编码标记剥离，不参与变量名解析。
        $dataLine = if ($lineNo -eq 1) { $line.TrimStart([char]0xFEFF) } else { $line }
        $trimmed = $dataLine.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith('#')) { continue }

        $name = $null
        $value = $null
        if ($dataLine -match $doubleAssignmentPattern) {
            $name = [string]$Matches[1]
            $value = [string]$Matches[2]
        } elseif ($dataLine -match $singleAssignmentPattern) {
            $name = [string]$Matches[1]
            $value = ([string]$Matches[2]).Replace("''", "'")
        } else {
            throw "env.local.ps1 第 $lineNo 行不是允许的纯数据赋值；拒绝执行：[source omitted]"
        }

        if ($protectedExact.Contains($name) -or @($protectedPatterns | Where-Object { $name -match $_ }).Count -gt 0) {
            throw "env.local.ps1 第 $lineNo 行试图覆盖受保护的便携变量：$name"
        }
        if ($name -match '^(?i:CODEX_)' -and -not $supportedCodex.Contains($name)) {
            throw "env.local.ps1 第 $lineNo 行使用了未经便携边界审核的 Codex 变量：$name"
        }
        if ($name -ieq 'CODEX_MODEL_INSTRUCTIONS_FILE') { $script:CodexPortableAutoModelInstructions = $false }
        [Environment]::SetEnvironmentVariable($name, $value, [EnvironmentVariableTarget]::Process)
    }
}

$LocalEnvFile = Join-Path $Script:CodexPortableRoot "env.local.ps1"
Import-CodexPortableLocalEnv -Path $LocalEnvFile

if ($script:CodexPortableAutoModelInstructions -and [string]::IsNullOrWhiteSpace($env:CODEX_MODEL_INSTRUCTIONS_FILE)) {
    $env:CODEX_MODEL_INSTRUCTIONS_FILE = Find-CodexPortableModelInstructions -Model $env:CODEX_MODEL
} else {
    $script:CodexPortableAutoModelInstructions = $false
}
