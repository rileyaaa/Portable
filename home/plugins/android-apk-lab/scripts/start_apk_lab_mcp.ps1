#Requires -Version 5.1
param([switch]$TaskAuthorized)
$ErrorActionPreference = 'Stop'

# Caller records that this MCP was selected for the current task. This switch
# does not infer user intent, and maintenance mode cannot supply it implicitly.
if (-not $TaskAuthorized) {
    throw 'APK Lab MCP requires explicit task selection: -TaskAuthorized'
}
$PluginRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$PluginScriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PluginParent = Split-Path -Parent $PluginRoot
$HomeDirBeforeHelper = Split-Path -Parent $PluginParent
$PackageRootBeforeHelper = Split-Path -Parent $HomeDirBeforeHelper
# Inspect the lexical path from the volume root down, before following any link.
$BootstrapAncestors = @()
$BootstrapCursor = [IO.Path]::GetFullPath($PluginScriptsDir)
while (-not [string]::IsNullOrWhiteSpace($BootstrapCursor)) {
    $BootstrapAncestors = @($BootstrapCursor) + $BootstrapAncestors
    $BootstrapParent = Split-Path -Parent $BootstrapCursor
    if ($BootstrapParent -eq $BootstrapCursor) { break }
    $BootstrapCursor = $BootstrapParent
}
foreach ($guardDir in $BootstrapAncestors) {
    $guardItem = Get-Item -LiteralPath $guardDir -Force -ErrorAction Stop
    if (-not $guardItem.PSIsContainer -or (($guardItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
        throw "Refusing reparse/non-directory APK Lab bootstrap path: $guardDir"
    }
}
function Assert-ApkBootstrapSingleLinkFile([string]$Path,[string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "$Label not found: $Path" }
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Refusing reparse-point ${Label}: $Path" }
    $linkTypeProperty = $item.PSObject.Properties['LinkType']
    $linkType = if ($null -ne $linkTypeProperty) { [string]$linkTypeProperty.Value } else { '' }
    if ($linkType -eq 'HardLink' -or ([string]$item.Mode).Contains('l')) { throw "Refusing hardlink/link ${Label}: $Path" }
}
[void](Assert-ApkBootstrapSingleLinkFile $PSCommandPath 'APK Lab MCP starter')
$PortablePathsScript = Join-Path $PluginRoot 'scripts\portable_paths.ps1'
[void](Assert-ApkBootstrapSingleLinkFile $PortablePathsScript 'portable path helper')
. $PortablePathsScript
$Root = Get-ApkLabRoot
$PluginRoot = Resolve-ApkLabPath $PluginRoot
$env:CODEX_INSTALL_DIR = $Root

# MCP is part of the portable package: never silently fall back to a host Python.
$Python = Resolve-ApkLabPath (Join-Path $Root 'tool\python\python.exe')
[void](Assert-ApkBootstrapSingleLinkFile $Python 'portable Python')
$McpScript = Resolve-ApkLabPath (Join-Path $PluginRoot 'scripts\apk_lab_mcp.py')
[void](Assert-ApkBootstrapSingleLinkFile $McpScript 'APK Lab MCP Python script')

$PortableTmpRoot = Resolve-ApkLabPath (Join-Path $Root 'tmp')
function Get-ApkLabSessionScopedPath {
    param([string]$Candidate, [string]$Fallback)
    if (-not [string]::IsNullOrWhiteSpace($Candidate)) {
        try {
            $safeCandidate = Resolve-ApkLabPath $Candidate
            $tmpPrefix = $PortableTmpRoot.TrimEnd('\') + '\'
            if ($safeCandidate.StartsWith($tmpPrefix, [StringComparison]::OrdinalIgnoreCase)) {
                $relative = $safeCandidate.Substring($tmpPrefix.Length)
                $first = @($relative -split '\\')[0]
                if ($first -match '^session-state-[0-9A-Fa-f]{32}$') {
                    return $safeCandidate
                }
            }
        } catch {}
    }
    return Resolve-ApkLabPath $Fallback
}

# Preserve the launcher's random session cache roots when this MCP is started by
# Codex.  Direct/manual MCP starts fall back to package-local persistent paths.
$InheritedXdgCache = $env:XDG_CACHE_HOME
$InheritedPycache = $env:PYTHONPYCACHEPREFIX
$InheritedApktool = $env:APKTOOL_FRAMEWORK_DIR
$InheritedFrida = $env:FRIDA_CACHE_DIR
$InheritedMitm = $env:MITMPROXY_HOME
$InheritedAppium = $env:APPIUM_HOME
$InheritedApkCache = $env:APK_LAB_CACHE_DIR
$InheritedApkTmp = $env:APK_LAB_TMP_DIR

# MCP 子进程只需要本插件和包内工具。删除与 APK Lab 无关的宿主凭证、代理和代码注入变量，
# 防止它们被 Python/第三方库意外读取；需要的值必须由包内启动配置显式重新设置。
$McpScrubNames = @(
    'OPENAI_API_KEY','OPENAI_ORG_ID','OPENAI_PROJECT_ID','ANTHROPIC_API_KEY','GOOGLE_API_KEY','GEMINI_API_KEY',
    'AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','AWS_SESSION_TOKEN','AWS_SECURITY_TOKEN','AWS_WEB_IDENTITY_TOKEN_FILE',
    'AZURE_CLIENT_ID','AZURE_CLIENT_SECRET','AZURE_TENANT_ID','AZURE_FEDERATED_TOKEN_FILE','GOOGLE_APPLICATION_CREDENTIALS',
    'GITHUB_TOKEN','GH_TOKEN','NPM_TOKEN','NODE_AUTH_TOKEN','PYPI_TOKEN','TWINE_PASSWORD','HF_TOKEN','HUGGINGFACEHUB_API_TOKEN',
    'HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy',
    'PYTHONPATH','PYTHONHOME','PYTHONSTARTUP','PYTHONINSPECT','PYTHONWARNINGS','PYTHONBREAKPOINT',
    'NODE_OPTIONS','NODE_PATH','NODE_EXTRA_CA_CERTS','JAVA_TOOL_OPTIONS','_JAVA_OPTIONS',
    'GIT_ASKPASS','SSH_ASKPASS','GIT_SSH','GIT_SSH_COMMAND','GIT_CONFIG_GLOBAL','GIT_CONFIG_SYSTEM','GIT_CONFIG_COUNT',
    'SSH_AUTH_SOCK','SSH_AGENT_PID','GPG_AGENT_INFO','BASH_ENV','ENV','CDPATH','RUBYOPT','RUBYLIB','PERL5OPT','PERL5LIB'
)
foreach ($name in $McpScrubNames) { Remove-Item ("Env:" + $name) -ErrorAction SilentlyContinue }
Get-ChildItem Env: | Where-Object { $_.Name -match '^GIT_CONFIG_(KEY|VALUE)_\d+$' } | ForEach-Object { Remove-Item ("Env:" + $_.Name) -ErrorAction SilentlyContinue }
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONNOUSERSITE = '1'
$env:CODEX_HOME = Resolve-ApkLabPath (Join-Path $Root 'home')
$env:HOME = Resolve-ApkLabPath (Join-Path $Root 'home-runtime')
$env:USERPROFILE = $env:HOME
$env:APPDATA = Resolve-ApkLabPath (Join-Path $Root 'appdata')
$env:LOCALAPPDATA = Resolve-ApkLabPath (Join-Path $Root 'localappdata')
$env:PROGRAMDATA = Resolve-ApkLabPath (Join-Path $Root 'programdata')
$env:ALLUSERSPROFILE = $env:PROGRAMDATA
$env:TEMP = Resolve-ApkLabPath (Join-Path $Root 'tmp')
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
$env:XDG_CACHE_HOME = Get-ApkLabSessionScopedPath $InheritedXdgCache (Join-Path $Root 'cache')
$env:XDG_CONFIG_HOME = $env:APPDATA
$env:XDG_DATA_HOME = $env:LOCALAPPDATA
$env:XDG_STATE_HOME = Resolve-ApkLabPath (Join-Path $env:LOCALAPPDATA 'state')
$env:ANDROID_HOME = Resolve-ApkLabPath (Join-Path $Root 'tool\android\sdk')
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:ANDROID_USER_HOME = Resolve-ApkLabPath (Join-Path $Root 'home-runtime\.android')
$env:ANDROID_SDK_HOME = Resolve-ApkLabPath (Join-Path $Root 'home-runtime')
$env:JAVA_HOME = Resolve-ApkLabPath (Join-Path $Root 'tool\android\jdk')
$env:APKTOOL_FRAMEWORK_DIR = Get-ApkLabSessionScopedPath $InheritedApktool (Join-Path $Root 'cache\android\apktool-framework')
$env:FRIDA_CACHE_DIR = Get-ApkLabSessionScopedPath $InheritedFrida (Join-Path $Root 'cache\android\frida')
$env:MITMPROXY_HOME = Get-ApkLabSessionScopedPath $InheritedMitm (Join-Path $Root 'cache\android\mitmproxy')
$env:APPIUM_HOME = Get-ApkLabSessionScopedPath $InheritedAppium (Join-Path $Root 'cache\android\appium')
$env:APK_LAB_CACHE_DIR = Get-ApkLabSessionScopedPath $InheritedApkCache (Join-Path $Root 'cache\android\apk-lab')
$env:APK_LAB_TMP_DIR = Get-ApkLabSessionScopedPath $InheritedApkTmp (Join-Path $Root 'tmp\android')
$env:APK_LAB_JOBS_DIR = Resolve-ApkLabPath (Join-Path $Root 'work\apk-jobs')
$env:PYTHONPYCACHEPREFIX = Get-ApkLabSessionScopedPath $InheritedPycache (Join-Path $Root 'cache\pycache')
foreach ($d in @($env:HOME,$env:APPDATA,$env:LOCALAPPDATA,$env:PROGRAMDATA,$env:TEMP,$env:XDG_CACHE_HOME,$env:XDG_STATE_HOME,$env:ANDROID_USER_HOME,$env:APKTOOL_FRAMEWORK_DIR,$env:FRIDA_CACHE_DIR,$env:MITMPROXY_HOME,$env:APPIUM_HOME,$env:APK_LAB_CACHE_DIR,$env:APK_LAB_TMP_DIR,$env:APK_LAB_JOBS_DIR,$env:PYTHONPYCACHEPREFIX)) {
    $safe = Resolve-ApkLabPath $d
    New-Item -ItemType Directory -Force -Path $safe | Out-Null
}

$env:PATH = @(
    (Resolve-ApkLabPath (Join-Path $Root 'tool\bin')),
    (Resolve-ApkLabPath (Join-Path $Root 'tool\python')),
    (Resolve-ApkLabPath (Join-Path $Root 'tool\python\Scripts')),
    (Join-Path $env:SystemRoot 'System32'),
    $env:SystemRoot,
    (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0')
) -join ';'

& $Python -B $McpScript --task-authorized
exit $LASTEXITCODE
