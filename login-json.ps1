param(
    [ValidateSet("Check", "Select", "Probe", "Use")]
    [string]$Mode = "Check",
    [string]$ResultPath = "",
    [string]$CredentialPath = "",
    [int]$CredentialIndex = -1,
    [string]$ProbeResultPath = "",
    [string]$AuthModel = "",
    [string]$ClientVersion = "",
    [int]$ThrottleLimit = 0,
    [int]$MaxFiles = -1,
    [int]$MaxCredentials = -1,
    [switch]$Sequential,
    [switch]$SkipEnvFile,
    [switch]$NoProxyPrompt,
    [switch]$SkipPackageMutex,
    [string]$PackageMutexBypassToken = ""
)

$ErrorActionPreference = "Stop"
# Keep PowerShell file checks and .NET reads/writes on the same absolute path.
foreach ($pathParameterName in @('ResultPath','CredentialPath','ProbeResultPath')) {
    $pathParameterValue = Get-Variable -Name $pathParameterName -ValueOnly
    if (-not [string]::IsNullOrWhiteSpace($pathParameterValue)) {
        Set-Variable -Name $pathParameterName -Value ([IO.Path]::GetFullPath($pathParameterValue))
    }
}
$InternalMutexTokenName = "CODEX_PORTABLE_INTERNAL_LOGIN_MUTEX_TOKEN"
$ExpectedMutexBypassToken = [Environment]::GetEnvironmentVariable($InternalMutexTokenName)
if ($SkipPackageMutex) {
    if ($Mode -notin @("Probe", "Select")) {
        throw "-SkipPackageMutex is internal and only valid for launcher Select or child Probe operations."
    }
    if ([string]::IsNullOrWhiteSpace($PackageMutexBypassToken) -or
        [string]::IsNullOrWhiteSpace($ExpectedMutexBypassToken) -or
        -not $PackageMutexBypassToken.Equals($ExpectedMutexBypassToken, [System.StringComparison]::Ordinal)) {
        throw "-SkipPackageMutex requires an internal one-time capability token from the lock-owning parent."
    }
} elseif (-not [string]::IsNullOrWhiteSpace($PackageMutexBypassToken)) {
    throw "PackageMutexBypassToken is internal and cannot be supplied without -SkipPackageMutex."
}
# Never let the parent capability leak into arbitrary subprocesses. Probe jobs mint their own token.
Remove-Item ("Env:" + $InternalMutexTokenName) -ErrorAction SilentlyContinue
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootItem = Get-Item -LiteralPath $Root -Force -ErrorAction Stop
if (($RootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { throw "拒绝以重解析点作为 Codex Portable 根目录：$Root" }

$LoginDir = Join-Path $Root "login_json"
$HomeDir  = Join-Path $Root "home"
$TmpDir   = Join-Path $Root "tmp"
$LogDir   = Join-Path $Root "logs"
$ScanCachePath = Join-Path $LoginDir "login_json_report.cache.json"
$ScanCacheVersion = 3


function Clear-StandaloneInheritedEnvironment {
    # Standalone login checker must not use host credentials/proxy/runtime injection before env.ps1 is loaded.
    # When -SkipEnvFile is used by run-codex.ps1, the caller has already sanitized and loaded package env.
    foreach ($name in @(
        "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_ORGANIZATION", "OPENAI_PROJECT", "CODEX_OSS_BASE_URL", "CODEX_OSS_PORT", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY",
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN", "AWS_WEB_IDENTITY_TOKEN_FILE", "AWS_PROFILE",
        "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID", "AZURE_FEDERATED_TOKEN_FILE", "AZURE_SUBSCRIPTION_ID",
        "GOOGLE_APPLICATION_CREDENTIALS", "CLOUDSDK_CONFIG",
        "GITHUB_TOKEN", "GH_TOKEN", "NPM_TOKEN", "NODE_AUTH_TOKEN", "PYPI_TOKEN", "TWINE_PASSWORD", "HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN",
        "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONINSPECT", "PYTHONWARNINGS", "PYTHONBREAKPOINT",
        "NODE_OPTIONS", "NODE_PATH", "NODE_EXTRA_CA_CERTS", "JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS",
        "PIP_CONFIG_FILE", "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "PIP_TRUSTED_HOST", "PIP_CERT", "PIP_CLIENT_CERT",
        "UV_INDEX_URL", "UV_DEFAULT_INDEX", "UV_EXTRA_INDEX_URL", "UV_INDEX", "UV_FIND_LINKS", "UV_NO_INDEX",
        "NPM_CONFIG_REGISTRY", "NPM_CONFIG_SCRIPT_SHELL", "NPM_CONFIG_NODE_OPTIONS", "NPM_CONFIG_HTTPS_PROXY", "NPM_CONFIG_PROXY", "NPM_CONFIG_CAFILE", "NPM_CONFIG_CERT", "NPM_CONFIG_KEY",
        "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS",
        "GIT_ASKPASS", "SSH_ASKPASS", "GIT_SSH", "GIT_SSH_COMMAND", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_COUNT",
        "SSH_AUTH_SOCK", "SSH_AGENT_PID", "GPG_AGENT_INFO", "VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV", "CONDA_PROMPT_MODIFIER",
        "BASH_ENV", "ENV", "CDPATH", "RUBYOPT", "RUBYLIB", "PERL5OPT", "PERL5LIB", "KUBECONFIG", "DOCKER_HOST", "DOCKER_CONTEXT",
        "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy",
        "CODEX_PORTABLE_ALLOW_HOST_PATH", "CODEX_PROXY_ENABLED", "CODEX_PROXY_PROTOCOL", "CODEX_PROXY_HOST", "CODEX_PROXY_PORT",
        "CODEX_PROXY_HTTP_BRIDGE", "CODEX_PROXY_BRIDGE_HOST", "CODEX_PROXY_BRIDGE_PORT", "CODEX_PROXY_FOR_SUBPROCESS", "CODEX_PROXY_BYPASS_MODEL",
        "CODEX_LOGIN_JSON_PROXY_MODE", "CODEX_LOGIN_JSON_HTTP_BACKEND", "CODEX_LOGIN_JSON_ALLOW_DIRECT_PARALLEL",
        "LATEST_MODEL_URL", "LATEST_MODEL_BASE_URL", "CODEX_PORTABLE_ALLOW_CUSTOM_MANUAL_URL", "NODE"
    )) {
        Remove-Item ("Env:" + $name) -ErrorAction SilentlyContinue
    }
    Get-ChildItem Env: | Where-Object { $_.Name -match '^GIT_CONFIG_(KEY|VALUE)_\d+$' } | ForEach-Object {
        Remove-Item ("Env:" + $_.Name) -ErrorAction SilentlyContinue
    }
    $env:GIT_CONFIG_NOSYSTEM = "1"
}

function Test-IsUnderDirectory {
    param([string]$Path, [string]$Directory)
    try {
        if ([string]::IsNullOrWhiteSpace($Path) -or [string]::IsNullOrWhiteSpace($Directory)) { return $false }
        $fullPath = [System.IO.Path]::GetFullPath($Path).TrimEnd("\")
        $baseDir = [System.IO.Path]::GetFullPath($Directory).TrimEnd("\")
        if (-not (Test-Path -LiteralPath $baseDir)) { return $false }
        $baseItem = Get-Item -LiteralPath $baseDir -Force -ErrorAction Stop
        if (($baseItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { return $false }
        if ($fullPath.Equals($baseDir, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
        $fullDir = $baseDir + "\"
        if (-not $fullPath.StartsWith($fullDir, [System.StringComparison]::OrdinalIgnoreCase)) { return $false }

        $relative = $fullPath.Substring($fullDir.Length)
        $current = $baseDir
        foreach ($segment in @($relative -split '\\')) {
            if ([string]::IsNullOrWhiteSpace($segment)) { continue }
            $current = Join-Path $current $segment
            if (Test-Path -LiteralPath $current) {
                $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
                if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { return $false }
            }
        }
        return $true
    } catch {
        return $false
    }
}


function Test-IsPortableSingleLinkRegularFile {
    param([string]$Path, [string]$Directory = $Root)
    if (-not (Test-IsUnderDirectory -Path $Path -Directory $Directory)) { return $false }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    try {
        $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { return $false }
        $linkTypeProperty = $item.PSObject.Properties['LinkType']
        $linkType = if ($null -ne $linkTypeProperty) { [string]$linkTypeProperty.Value } else { '' }
        if ($linkType -eq 'HardLink' -or ([string]$item.Mode).Contains('l')) { return $false }
        return $true
    } catch { return $false }
}


# A token alone is only an accidental-misuse guard because the package owner can set
# process environment variables.  For the mutable Select path, also require this script
# to be running under one of the byte-identical hardened run-codex.ps1 launchers.
if ($SkipPackageMutex -and $Mode -eq "Select") {
    $rootLauncher = Join-Path $Root "run-codex.ps1"
    if (-not (Test-IsPortableSingleLinkRegularFile -Path $rootLauncher -Directory $Root)) {
        throw "Internal Select bypass refused: hardened root launcher is missing or unsafe."
    }
    $rootLauncherHash = (Get-FileHash -LiteralPath $rootLauncher -Algorithm SHA256 -ErrorAction Stop).Hash
    $trustedLauncherFrame = $false
    foreach ($frame in @(Get-PSCallStack)) {
        $frameScript = [string]$frame.ScriptName
        if ([string]::IsNullOrWhiteSpace($frameScript)) { continue }
        if (-not (Test-IsUnderDirectory -Path $frameScript -Directory $Root)) { continue }
        $leaf = [IO.Path]::GetFileName($frameScript)
        if ($leaf -ne 'run-codex.ps1' -and $leaf -notlike '*-run-codex.ps1') { continue }
        if (-not (Test-IsPortableSingleLinkRegularFile -Path $frameScript -Directory $Root)) { continue }
        try {
            if ((Get-FileHash -LiteralPath $frameScript -Algorithm SHA256 -ErrorAction Stop).Hash -eq $rootLauncherHash) {
                $trustedLauncherFrame = $true
                break
            }
        } catch {}
    }
    if (-not $trustedLauncherFrame) {
        throw "Internal Select bypass refused: no byte-identical hardened launcher frame is active."
    }
}

function New-Dir {
    param([string]$Path)
    if (-not (Test-IsUnderDirectory -Path $Path -Directory $Root)) { throw "Refusing package directory through outside/reparse path: $Path" }
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function ConvertTo-PortableJsonText {
    param(
        $InputObject,
        [int]$Depth = 64,
        [switch]$Compress
    )
    if ($Compress) {
        $json = ConvertTo-Json -InputObject $InputObject -Depth $Depth -Compress
    } else {
        $json = ConvertTo-Json -InputObject $InputObject -Depth $Depth
    }
    if ($json -is [array]) { return ($json -join [Environment]::NewLine) }
    return [string]$json
}

function Write-PortableNewUtf8File {
    param([string]$Path, [AllowEmptyString()][string]$Text, [switch]$EmitBom)
    if (-not (Test-IsUnderDirectory -Path $Path -Directory $Root)) { throw 'Unsafe exclusive-write path.' }
    $stream = $null
    $created = $false
    try {
        $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $created = $true
        $encoding = New-Object Text.UTF8Encoding($EmitBom.IsPresent)
        if ($EmitBom) { $bom = $encoding.GetPreamble(); $stream.Write($bom, 0, $bom.Length) }
        $data = $encoding.GetBytes($Text)
        $stream.Write($data, 0, $data.Length)
        $stream.Flush($true)
    } catch {
        if ($null -ne $stream) { $stream.Dispose(); $stream = $null }
        if ($created) { Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue }
        throw
    } finally { if ($null -ne $stream) { $stream.Dispose() } }
}

function Write-Utf8JsonFile {
    param(
        [string]$Path,
        $InputObject,
        [int]$Depth = 64,
        [switch]$Compress
    )
    if (-not (Test-IsUnderDirectory -Path $Path -Directory $Root)) {
        throw "Refusing JSON write outside package or through reparse path: $Path"
    }
    if ((Test-Path -LiteralPath $Path) -and -not (Test-IsPortableSingleLinkRegularFile -Path $Path -Directory $Root)) {
        throw "Refusing JSON destination that is not a single-link regular package file: $Path"
    }
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    $temporaryPath = "$Path.tmp-$([System.Guid]::NewGuid().ToString('N'))"
    $backupPath = "$Path.bak-$([System.Guid]::NewGuid().ToString('N'))"
    if (Test-Path -LiteralPath $backupPath) { throw 'Recovery path already exists.' }
    $committed = $false; $temporaryOwned = $false
    try {
        Write-PortableNewUtf8File -Path $temporaryPath -Text (ConvertTo-PortableJsonText -InputObject $InputObject -Depth $Depth -Compress:$Compress)
        $temporaryOwned = $true
        if (-not (Test-IsUnderDirectory -Path $Path -Directory $Root)) { throw 'Destination path changed during staging.' }
        if (Test-Path -LiteralPath $Path) {
            if (-not (Test-IsPortableSingleLinkRegularFile -Path $Path -Directory $Root)) { throw 'Destination file changed during staging.' }
            [System.IO.File]::Replace($temporaryPath, $Path, $backupPath)
        } else {
            [System.IO.File]::Move($temporaryPath, $Path)
        }
        $committed = $true
    } finally {
        if ($temporaryOwned) { Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue }
        if ($committed) { Remove-Item -LiteralPath $backupPath -Force -ErrorAction SilentlyContinue }
        elseif (Test-Path -LiteralPath $backupPath) { Write-Warning 'Atomic replacement failed; recovery backup retained.' }
    }
}

function Write-Utf8CsvFileAtomic {
    param(
        [string]$Path,
        $Rows
    )
    if (-not (Test-IsUnderDirectory -Path $Path -Directory $Root)) {
        throw "Refusing CSV write outside package or through reparse path: $Path"
    }
    $parent = Split-Path -Parent $Path
    if (-not (Test-IsUnderDirectory -Path $parent -Directory $Root)) {
        throw "Refusing CSV parent outside package or through reparse path: $parent"
    }
    if ((Test-Path -LiteralPath $Path) -and -not (Test-IsPortableSingleLinkRegularFile -Path $Path -Directory $Root)) {
        throw "Refusing CSV destination that is not a single-link regular package file: $Path"
    }
    $temporaryPath = Join-Path $parent (".codex-csv-" + [System.Guid]::NewGuid().ToString('N') + '.tmp')
    $backupPath = Join-Path $parent (".codex-csv-" + [System.Guid]::NewGuid().ToString('N') + '.bak')
    if (Test-Path -LiteralPath $backupPath) { throw 'Recovery path already exists.' }
    $committed = $false; $temporaryOwned = $false
    try {
        $csvLines = @(@($Rows) | ConvertTo-Csv -NoTypeInformation)
        $csvText = if ($csvLines.Count) { ($csvLines -join [Environment]::NewLine) + [Environment]::NewLine } else { '' }
        Write-PortableNewUtf8File -Path $temporaryPath -Text $csvText -EmitBom
        $temporaryOwned = $true
        if (-not (Test-IsUnderDirectory -Path $parent -Directory $Root)) {
            throw "CSV parent changed into an unsafe path during write: $parent"
        }
        if (-not (Test-IsUnderDirectory -Path $Path -Directory $Root)) { throw 'Destination path changed during staging.' }
        if (Test-Path -LiteralPath $Path) {
            if (-not (Test-IsPortableSingleLinkRegularFile -Path $Path -Directory $Root)) { throw 'Destination file changed during staging.' }
            [System.IO.File]::Replace($temporaryPath, $Path, $backupPath)
        } else {
            [System.IO.File]::Move($temporaryPath, $Path)
        }
        $committed = $true
    } finally {
        if ($temporaryOwned) { Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue }
        if ($committed) { Remove-Item -LiteralPath $backupPath -Force -ErrorAction SilentlyContinue }
        elseif (Test-Path -LiteralPath $backupPath) { Write-Warning 'Atomic replacement failed; recovery backup retained.' }
    }
}

# Windows runtime environment must not be inherited from an arbitrary shell.
function Set-LoginTrustedWindowsEnvironment {
    $windows = [IO.Path]::GetFullPath([Environment]::GetFolderPath('Windows')).TrimEnd('\')
    if ($windows -notmatch '^[A-Za-z]:\\' -or $windows.Substring(2).Contains(':') -or
        -not [IO.File]::Exists((Join-Path $windows 'System32\cmd.exe'))) {
        throw 'JSON login requires a real local Windows system directory.'
    }
    $env:SystemRoot = $windows
    $env:WINDIR = $windows
    $env:SystemDrive = [IO.Path]::GetPathRoot($windows).TrimEnd('\')
    $env:ComSpec = Join-Path $windows 'System32\cmd.exe'
    $env:PATHEXT = '.COM;.EXE;.BAT;.CMD'
    return $windows
}

function Set-PortableEnvironment {
    [void](Set-LoginTrustedWindowsEnvironment)
    New-Dir $LoginDir
    New-Dir $HomeDir
    New-Dir $TmpDir
    New-Dir $LogDir
    New-Dir (Join-Path $Root "home-runtime")
    New-Dir (Join-Path $Root "appdata")
    New-Dir (Join-Path $Root "localappdata")
    New-Dir (Join-Path $Root "programdata")

    $env:CODEX_HOME = $HomeDir
    $env:CODEX_SQLITE_HOME = Join-Path $Root "sqlite"
    $env:HOME = Join-Path $Root "home-runtime"
    $env:USERPROFILE = $env:HOME
    try {
        $homeRoot = [System.IO.Path]::GetPathRoot($env:HOME)
        if (-not [string]::IsNullOrWhiteSpace($homeRoot) -and $homeRoot -match '^[A-Za-z]:\\$') {
            $env:HOMEDRIVE = $homeRoot.Substring(0, 2)
            $env:HOMEPATH = $env:HOME.Substring(2)
        }
    } catch {}
    $env:APPDATA = Join-Path $Root "appdata"
    $env:LOCALAPPDATA = Join-Path $Root "localappdata"
    $env:PROGRAMDATA = Join-Path $Root "programdata"
    $env:ALLUSERSPROFILE = $env:PROGRAMDATA
    $env:TEMP = $TmpDir
    $env:TMP = $TmpDir
    $env:TMPDIR = $TmpDir
    $env:XDG_CACHE_HOME = Join-Path $Root "cache"
    $env:XDG_CONFIG_HOME = $env:APPDATA
    $env:XDG_DATA_HOME = $env:LOCALAPPDATA
    $env:XDG_STATE_HOME = Join-Path $env:LOCALAPPDATA "state"
    $psModuleCacheDir = Join-Path $env:LOCALAPPDATA "Microsoft\Windows\PowerShell"
    New-Dir $psModuleCacheDir
    $env:PSModuleAnalysisCachePath = Join-Path $psModuleCacheDir "ModuleAnalysisCache"
    $portablePsModules = Join-Path $Root "cache\powershell\modules"
    New-Dir $portablePsModules
    $builtinPsModules = Join-Path $PSHOME "Modules"
    $env:PSModulePath = $portablePsModules + ";" + $builtinPsModules
    $env:POWERSHELL_TELEMETRY_OPTOUT = "1"
    $env:GIT_CONFIG_NOSYSTEM = "1"
    $env:CODEX_INSTALL_DIR = $Root
}

function Set-PortableProcessPath {
    $tool = Join-Path $Root "tool"
    # Only audited portable command shims and installed runtimes.
    # Vendor Python bin EXEs can carry stale interpreter launchers, and Go is absent.
    $portableCandidates = @(
        (Join-Path $tool "bin"),
        (Join-Path $tool "python"),
        (Join-Path $tool "node")
    )
    foreach ($candidate in $portableCandidates) {
        if (-not (Test-IsUnderDirectory -Path $candidate -Directory $Root)) {
            throw "Refusing package tool path through outside/reparse path: $candidate"
        }
    }
    $WindowsRoot = Set-LoginTrustedWindowsEnvironment
    $systemCandidates = @(
        (Join-Path $WindowsRoot "System32"),
        $WindowsRoot,
        (Join-Path $WindowsRoot "System32\WindowsPowerShell\v1.0"),
        (Join-Path $WindowsRoot "System32\Wbem")
    )
    $parts = New-Object System.Collections.Generic.List[string]
    foreach ($candidate in @($portableCandidates + $systemCandidates)) {
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        if (-not $parts.Contains($candidate)) { [void]$parts.Add($candidate) }
    }
    $env:PATH = ($parts -join ";")
}

function ConvertTo-WindowsCommandLineArgument {
    param([string]$Argument)
    if ([string]::IsNullOrEmpty($Argument)) { return '""' }
    if ($Argument -notmatch '[\s"]') { return $Argument }
    $builder = New-Object System.Text.StringBuilder
    [void]$builder.Append('"')
    $backslashes = 0
    foreach ($ch in $Argument.ToCharArray()) {
        if ($ch -eq '\') { $backslashes++; continue }
        if ($ch -eq '"') {
            if ($backslashes -gt 0) { [void]$builder.Append('\' * ($backslashes * 2)) }
            [void]$builder.Append('\"')
            $backslashes = 0
            continue
        }
        if ($backslashes -gt 0) { [void]$builder.Append('\' * $backslashes); $backslashes = 0 }
        [void]$builder.Append($ch)
    }
    if ($backslashes -gt 0) { [void]$builder.Append('\' * ($backslashes * 2)) }
    [void]$builder.Append('"')
    return $builder.ToString()
}

function Clear-LoginJsonTempFiles {
    param(
        [string[]]$ExcludePaths = @(),
        [int]$MinAgeMinutes = 60
    )
    if (-not (Test-Path -LiteralPath $TmpDir)) { return }
    $tmpRoot = [System.IO.Path]::GetFullPath($TmpDir).TrimEnd("\") + "\"
    $cutoff = (Get-Date).ToUniversalTime().AddMinutes(-[Math]::Max(1, $MinAgeMinutes))
    $excluded = @{}
    foreach ($excludePath in @($ExcludePaths)) {
        if ([string]::IsNullOrWhiteSpace($excludePath)) { continue }
        try {
            $excluded[[System.IO.Path]::GetFullPath($excludePath).ToLowerInvariant()] = $true
        } catch {}
    }
    $patterns = @(
        "login-json-http-*",
        "login-json-probe-*.json",
        "login-json-*.body",
        "login-json-*.headers",
        "login-json-*.request.json",
        "login-json-*.stderr",
        "__PSScriptPolicyTest_*",
        "openpyxl.*"
    )
    foreach ($pattern in $patterns) {
        foreach ($file in (Get-ChildItem -LiteralPath $TmpDir -Filter $pattern -File -Force -ErrorAction SilentlyContinue)) {
            try {
                $full = [System.IO.Path]::GetFullPath($file.FullName)
                if ($excluded.ContainsKey($full.ToLowerInvariant())) { continue }
                if ($file.LastWriteTimeUtc -le $cutoff -and $full.StartsWith($tmpRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
                    Remove-Item -LiteralPath $full -Force -ErrorAction SilentlyContinue
                }
            } catch {}
        }
    }
}

function Test-Truthy {
    param([string]$Value, [bool]$Default)
    if ([string]::IsNullOrWhiteSpace($Value)) { return $Default }
    $v = $Value.Trim().ToLowerInvariant()
    if ($v -in @("1", "true", "yes", "y", "on")) { return $true }
    if ($v -in @("0", "false", "no", "n", "off")) { return $false }
    return $Default
}

function Get-LoginJsonProxyMode {
    $mode = $env:CODEX_LOGIN_JSON_PROXY_MODE
    if ([string]::IsNullOrWhiteSpace($mode)) {
        if (Test-Truthy $env:CODEX_LOGIN_JSON_ALLOW_DIRECT $false) { return "direct" }
        return "auto"
    }
    $mode = $mode.Trim().ToLowerInvariant()
    switch ($mode) {
        "auto"   { return "auto" }
        "direct" { return "direct" }
        "proxy"  { return "proxy" }
        default   { throw "CODEX_LOGIN_JSON_PROXY_MODE 只支持 auto / direct / proxy：$mode" }
    }
}

function Get-LoginJsonConnectTimeout {
    $value = 8
    $fromEnv = 0
    if (-not [string]::IsNullOrWhiteSpace($env:CODEX_LOGIN_JSON_CONNECT_TIMEOUT_SEC) -and [int]::TryParse($env:CODEX_LOGIN_JSON_CONNECT_TIMEOUT_SEC, [ref]$fromEnv) -and $fromEnv -gt 0) {
        $value = [Math]::Min($fromEnv, 30)
    }
    return $value
}

function Get-ProxyUrl {
    param([switch]$Force)
    if (-not $Force -and -not (Test-Truthy $env:CODEX_PROXY_ENABLED $false)) { return "" }

    $hostName = $env:CODEX_PROXY_HOST
    if ([string]::IsNullOrWhiteSpace($hostName)) { $hostName = "127.0.0.1" }
    $hostName = $hostName.Trim()

    $port = $env:CODEX_PROXY_PORT
    if ([string]::IsNullOrWhiteSpace($port)) { $port = "10808" }
    $port = $port.Trim()

    $protocol = $env:CODEX_PROXY_PROTOCOL
    if ([string]::IsNullOrWhiteSpace($protocol)) { $protocol = "socks5" }
    $protocol = $protocol.Trim().ToLowerInvariant()

    $parsedPort = 0
    if (-not [int]::TryParse($port, [ref]$parsedPort) -or $parsedPort -lt 1 -or $parsedPort -gt 65535) {
        throw "CODEX_PROXY_PORT 必须是 1-65535：$port"
    }
    if ($protocol -notin @("http", "socks5")) {
        throw "CODEX_PROXY_PROTOCOL 只支持 http / socks5：$protocol"
    }
    $uriHost = $hostName
    if ($uriHost.Contains(":") -and -not ($uriHost.StartsWith("[") -and $uriHost.EndsWith("]"))) { $uriHost = "[$uriHost]" }
    try { $null = [System.Uri]("http://${uriHost}:${parsedPort}") } catch { throw "CODEX_PROXY_HOST 无效：$hostName" }
    if ($protocol -eq "http") { return "http://${uriHost}:${parsedPort}" }
    return "socks5h://${uriHost}:${parsedPort}"
}

function Add-HttpNetworkTag {
    param($Response, [string]$Network)
    if ($null -ne $Response) {
        if ($Response.PSObject.Properties["Network"]) {
            $Response.Network = $Network
        } else {
            $Response | Add-Member -NotePropertyName "Network" -NotePropertyValue $Network -Force
        }
    }
    return $Response
}

function Test-AutoDirectHttpSuccess {
    param($Response)
    if ($null -eq $Response) { return $false }
    $status = 0
    if (-not [int]::TryParse([string]$Response.StatusCode, [ref]$status)) { return $false }
    return ($status -ge 200 -and $status -lt 300)
}

function Set-ProxyEnvironment {
    foreach ($name in @("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy")) {
        Remove-Item "Env:$name" -ErrorAction SilentlyContinue
    }

    $proxyUrl = Get-ProxyUrl
    if ([string]::IsNullOrWhiteSpace($proxyUrl)) { return }

    if ($proxyUrl.StartsWith("http", [System.StringComparison]::OrdinalIgnoreCase)) {
        $env:HTTP_PROXY = $proxyUrl
        $env:HTTPS_PROXY = $proxyUrl
        $env:http_proxy = $proxyUrl
        $env:https_proxy = $proxyUrl
    } else {
        $env:ALL_PROXY = $proxyUrl
        $env:all_proxy = $proxyUrl
    }
    $env:NO_PROXY = "localhost,127.0.0.1,::1"
    $env:no_proxy = $env:NO_PROXY
}

function Get-ObjectProperty {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $prop = $Object.PSObject.Properties[$Name]
    if ($null -eq $prop) { return $null }
    return $prop.Value
}

function Get-StringProperty {
    param($Object, [string[]]$Names)
    foreach ($name in $Names) {
        $value = Get-ObjectProperty $Object $name
        if ($null -ne $value -and -not [string]::IsNullOrWhiteSpace([string]$value)) {
            return ([string]$value).Trim()
        }
    }
    return ""
}

function Test-LooksLikeCredentialObject {
    param($Object)
    if ($null -eq $Object) { return $false }
    foreach ($name in @("access_token", "accessToken", "id_token", "idToken", "id_token_synthetic", "session_token", "sessionToken", "refresh_token", "refreshToken")) {
        if (-not [string]::IsNullOrWhiteSpace((Get-StringProperty $Object @($name)))) {
            return $true
        }
    }
    $account = Get-ObjectProperty $Object "account"
    $user = Get-ObjectProperty $Object "user"
    if ($null -ne $account -and $null -ne $user -and -not [string]::IsNullOrWhiteSpace((Get-StringProperty $Object @("accessToken")))) {
        return $true
    }
    return $false
}

function Add-CredentialEntry {
    param(
        [System.Collections.ArrayList]$Entries,
        [string]$Path,
        $RootJson,
        $Json,
        $Parent = $null,
        [string]$Source = "",
        [switch]$AllowEmpty
    )
    if ($null -eq $Json -or ((-not $AllowEmpty) -and -not (Test-LooksLikeCredentialObject $Json))) { return }
    $idx = $Entries.Count
    $Entries.Add([pscustomobject][ordered]@{
        Path = $Path
        File = [System.IO.Path]::GetFileName($Path)
        CredentialIndex = $idx
        CredentialKey = ([string]$idx)
        Source = $Source
        RootJson = $RootJson
        Json = $Json
        Parent = $Parent
        LoadError = ""
        DeleteAllowed = $true
    }) | Out-Null
}

function Add-CredentialEntriesFromItem {
    param(
        [System.Collections.ArrayList]$Entries,
        [string]$Path,
        $RootJson,
        $Item,
        [string]$Source
    )
    if ($null -eq $Item) { return }

    $credentials = Get-ObjectProperty $Item "credentials"
    if ($null -ne $credentials) {
        $credentialItems = @($credentials)
        if ($credentials -is [array]) { $credentialItems = @($credentials) }
        for ($i = 0; $i -lt $credentialItems.Count; $i++) {
            Add-CredentialEntry -Entries $Entries -Path $Path -RootJson $RootJson -Json $credentialItems[$i] -Parent $Item -Source "$Source.credentials[$i]" -AllowEmpty
        }
        return
    }

    if (Test-LooksLikeCredentialObject $Item) {
        Add-CredentialEntry -Entries $Entries -Path $Path -RootJson $RootJson -Json $Item -Parent $null -Source $Source
    }
}

function Get-CredentialEntriesFromJson {
    param([string]$Path, $Json)
    $entries = New-Object System.Collections.ArrayList

    if ($Json -is [array]) {
        $items = @($Json)
        for ($i = 0; $i -lt $items.Count; $i++) {
            Add-CredentialEntriesFromItem -Entries $entries -Path $Path -RootJson $Json -Item $items[$i] -Source "[$i]"
        }
    } else {
        $accounts = Get-ObjectProperty $Json "accounts"
        if ($null -ne $accounts) {
            if ($accounts -is [array]) {
                $accountItems = @($accounts)
                for ($i = 0; $i -lt $accountItems.Count; $i++) {
                    Add-CredentialEntriesFromItem -Entries $entries -Path $Path -RootJson $Json -Item $accountItems[$i] -Source "accounts[$i]"
                }
            } else {
                foreach ($prop in @($accounts.PSObject.Properties)) {
                    Add-CredentialEntriesFromItem -Entries $entries -Path $Path -RootJson $Json -Item $prop.Value -Source "accounts.$($prop.Name)"
                }
            }
        }

        if ($entries.Count -eq 0) {
            $credentials = Get-ObjectProperty $Json "credentials"
            if ($null -ne $credentials) {
                if ($credentials -is [array]) {
                    $credentialItems = @($credentials)
                    for ($i = 0; $i -lt $credentialItems.Count; $i++) {
                        Add-CredentialEntry -Entries $entries -Path $Path -RootJson $Json -Json $credentialItems[$i] -Parent $Json -Source "credentials[$i]" -AllowEmpty
                    }
                } else {
                    Add-CredentialEntry -Entries $entries -Path $Path -RootJson $Json -Json $credentials -Parent $Json -Source "credentials" -AllowEmpty
                }
            }
        }

        if ($entries.Count -eq 0) {
            Add-CredentialEntry -Entries $entries -Path $Path -RootJson $Json -Json $Json -Parent $null -Source "root"
        }
    }

    if ($entries.Count -eq 0) {
        $entries.Add([pscustomobject][ordered]@{
            Path = $Path
            File = [System.IO.Path]::GetFileName($Path)
            CredentialIndex = -1
            CredentialKey = ""
            Source = ""
            RootJson = $Json
            Json = $null
            Parent = $null
            LoadError = "no credential entries found"
            DeleteAllowed = $true
        }) | Out-Null
    } else {
        $multi = $entries.Count -gt 1
        for ($i = 0; $i -lt $entries.Count; $i++) {
            $entries[$i].CredentialIndex = $i
            $entries[$i].CredentialKey = ([string]$i)
            if ($multi) {
                $entries[$i].File = "{0}#{1}" -f ([System.IO.Path]::GetFileName($Path)), ($i + 1)
                $entries[$i].DeleteAllowed = $false
            } else {
                $entries[$i].File = [System.IO.Path]::GetFileName($Path)
                $entries[$i].DeleteAllowed = $true
            }
        }
    }

    return @($entries)
}

function Get-CredentialEntriesForFile {
    param([string]$Path)
    try {
        if (-not (Test-IsPortableSingleLinkRegularFile -Path $Path -Directory $LoginDir)) {
            throw "credential path is outside login_json, uses a reparse point, or is a hard link"
        }
        $raw = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
        $json = $raw | ConvertFrom-Json
        return @(Get-CredentialEntriesFromJson -Path $Path -Json $json)
    } catch {
        return @([pscustomobject][ordered]@{
            Path = $Path
            File = [System.IO.Path]::GetFileName($Path)
            CredentialIndex = -1
            CredentialKey = ""
            Source = ""
            RootJson = $null
            Json = $null
            Parent = $null
            LoadError = "invalid or unsafe credential JSON; input details suppressed"
            DeleteAllowed = $true
        })
    }
}

function Set-ObjectProperty {
    param($Object, [string]$Name, $Value)
    if ($Object.PSObject.Properties[$Name]) {
        $Object.PSObject.Properties[$Name].Value = $Value
    } else {
        $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    }
}

function ConvertFrom-Base64Url {
    param([string]$Value)
    $padded = $Value.Replace("-", "+").Replace("_", "/")
    switch ($padded.Length % 4) {
        2 { $padded += "==" }
        3 { $padded += "=" }
        0 { }
        default { throw "Invalid base64url length." }
    }
    return [System.Convert]::FromBase64String($padded)
}

function Decode-JwtPayload {
    param([string]$Jwt)
    if ([string]::IsNullOrWhiteSpace($Jwt)) { return $null }
    $parts = $Jwt.Split(".")
    if ($parts.Count -lt 3 -or [string]::IsNullOrWhiteSpace($parts[1])) { return $null }
    try {
        $bytes = ConvertFrom-Base64Url $parts[1]
        $json = [System.Text.Encoding]::UTF8.GetString($bytes)
        return ($json | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Get-JwtExpiration {
    param([string]$Jwt)
    $payload = Decode-JwtPayload $Jwt
    if ($null -eq $payload) { return $null }
    $exp = Get-ObjectProperty $payload "exp"
    if ($null -eq $exp) { return $null }
    try {
        $epoch = [int64]$exp
        return ([System.DateTimeOffset]::FromUnixTimeSeconds($epoch)).UtcDateTime
    } catch {
        return $null
    }
}

function Get-JwtEmail {
    param($Payload)
    $email = Get-StringProperty $Payload @("email")
    if (-not [string]::IsNullOrWhiteSpace($email)) { return $email }
    $profile = Get-ObjectProperty $Payload "https://api.openai.com/profile"
    return (Get-StringProperty $profile @("email"))
}

function Get-JwtAuthField {
    param($Payload, [string]$Name)
    $auth = Get-ObjectProperty $Payload "https://api.openai.com/auth"
    return (Get-StringProperty $auth @($Name))
}

function ConvertTo-SafeMessage {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return "" }
    $compact = ($Text -replace "\s+", " ").Trim()
    if ($compact.Length -gt 220) { return $compact.Substring(0, 220) + "..." }
    return $compact
}

function Assert-AllowedLoginJsonUrl {
    param([Parameter(Mandatory=$true)][string]$Url)
    try { $uri = [System.Uri]$Url } catch { throw "Invalid login API URL." }
    if (-not $uri.IsAbsoluteUri -or $uri.Scheme -ne 'https' -or -not [string]::IsNullOrEmpty($uri.UserInfo) -or $uri.Port -ne 443 -or $uri.Fragment -or $Url -match '[\x00-\x20\x7f#@]') {
        throw "Login API URL must be credential-free HTTPS on port 443."
    }
    $apiHost = $uri.DnsSafeHost.TrimEnd('.').ToLowerInvariant()
    $path = $uri.AbsolutePath
    $allowed = (($apiHost -eq 'auth.openai.com') -and ($path -eq '/oauth/token')) -or
               (($apiHost -eq 'chatgpt.com') -and ($path -in @('/backend-api/codex/models','/backend-api/wham/usage')))
    $rawAllowed = $Url -cmatch '^(?i:https://auth\.openai\.com\.?)(?::443)?/oauth/token$' -or
                  $Url -cmatch '^(?i:https://chatgpt\.com\.?)(?::443)?/backend-api/wham/usage$' -or
                  $Url -cmatch '^(?i:https://chatgpt\.com\.?)(?::443)?/backend-api/codex/models(?:\?client_version=[0-9]+\.[0-9]+\.[0-9]+)?$'
    if (-not $allowed -or -not $rawAllowed) { throw "Login API URL is outside the fixed Codex allowlist." }
}

function Assert-AllowedLoginJsonRequest {
    param([string]$Method, [string]$Url, [hashtable]$Headers, $Body, [int]$TimeoutSec, [string]$ProxyUrl)
    Assert-AllowedLoginJsonUrl $Url
    $expected = if (([Uri]$Url).AbsolutePath -ceq '/oauth/token') { 'POST' } else { 'GET' }
    if ($Method.ToUpperInvariant() -cne $expected -or ($expected -eq 'GET' -and $null -ne $Body)) { throw 'Forbidden login API method or body.' }
    if ($TimeoutSec -lt 1 -or $TimeoutSec -gt 300) { throw 'Invalid login API timeout.' }
    $forbidden = @('host','proxy-authorization','proxy-connection','connection','content-length','transfer-encoding','te','trailer','upgrade')
    foreach ($key in @($Headers.Keys)) {
        if ($key -isnot [string] -or $Headers[$key] -isnot [string] -or
            $key -notmatch "^[!#$%&'*+.^_``|~0-9A-Za-z-]+$" -or $key.ToLowerInvariant() -in $forbidden -or
            $Headers[$key] -match '[\x00-\x08\x0a-\x1f\x7f]') { throw 'Forbidden or invalid login API header.' }
    }
    if ($ProxyUrl) {
        try { $proxy = [Uri]$ProxyUrl } catch { throw 'Invalid proxy URL.' }
        if (-not $proxy.IsAbsoluteUri -or $proxy.Scheme -notin @('http','https','socks5','socks5h') -or
            -not $proxy.Host -or $proxy.AbsolutePath -notin @('','/') -or $proxy.Query -or $proxy.Fragment -or
            $ProxyUrl -match '[\x00-\x20\x7f?#]' -or $proxy.Port -eq 0 -or $proxy.Port -gt 65535) { throw 'Invalid proxy URL.' }
    }
}

function Import-LoginProcessSupervisor {
    $supervisor = Join-Path $Root 'tool\portable-process.ps1'
    if (-not (Test-IsPortableSingleLinkRegularFile -Path $supervisor -Directory $Root)) { throw 'Unsafe process supervisor; child NOT EXECUTED.' }
    . $supervisor
    Set-Item -Path Function:script:Initialize-PortableProcessJob -Value ${function:Initialize-PortableProcessJob}
    Set-Item -Path Function:script:Invoke-PortableProcess -Value ${function:Invoke-PortableProcess}
}

function Invoke-JsonHttpFallback {
    param(
        [string]$Method,
        [string]$Url,
        [hashtable]$Headers,
        $Body,
        [int]$TimeoutSec,
        [string]$ProxyUrl = ""
    )
    Assert-AllowedLoginJsonRequest $Method $Url $Headers $Body $TimeoutSec $ProxyUrl


    if ($ProxyUrl.StartsWith("socks", [System.StringComparison]::OrdinalIgnoreCase)) {
        return [pscustomobject]@{
            StatusCode = 0
            Body = ""
            Json = $null
            Error = "curl.exe is required for socks5 proxy requests."
        }
    }

    try {
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
    } catch {}

    $params = @{
        Uri = $Url
        Method = $Method
        Headers = $Headers
        TimeoutSec = $TimeoutSec
        UseBasicParsing = $true
        MaximumRedirection = 0
    }
    if (-not [string]::IsNullOrWhiteSpace($ProxyUrl)) {
        $params.Proxy = $ProxyUrl
    }
    if ($null -ne $Body) {
        $params.ContentType = "application/json"
        $params.Body = ConvertTo-PortableJsonText -InputObject $Body -Depth 32 -Compress
    }

    $savedDefaultProxy = [Net.WebRequest]::DefaultWebProxy
    try {
        [Net.WebRequest]::DefaultWebProxy = $null
        $response = Invoke-WebRequest @params
        $text = [string]$response.Content
        $json = $null
        if (-not [string]::IsNullOrWhiteSpace($text)) {
            try { $json = $text | ConvertFrom-Json } catch {}
        }
        return [pscustomobject]@{
            StatusCode = [int]$response.StatusCode
            Body = $text
            Json = $json
            Error = ""
        }
    } catch {
        $status = 0
        $text = ""
        try {
            if ($_.Exception.Response) {
                $status = [int]$_.Exception.Response.StatusCode
                $stream = $_.Exception.Response.GetResponseStream()
                if ($stream) {
                    $reader = New-Object System.IO.StreamReader($stream)
                    $text = $reader.ReadToEnd()
                    $reader.Dispose()
                }
            }
        } catch {}
        $json = $null
        if (-not [string]::IsNullOrWhiteSpace($text)) {
            try { $json = $text | ConvertFrom-Json } catch {}
        }
        return [pscustomobject]@{
            StatusCode = $status
            Body = $text
            Json = $json
            Error = "HTTP request failed; sensitive diagnostics suppressed"
        }
    } finally {
        [Net.WebRequest]::DefaultWebProxy = $savedDefaultProxy
    }
}

function Set-LoginChildEnvironmentValue {
    param([System.Diagnostics.ProcessStartInfo]$StartInfo,[string]$Name,[string]$Value)
    if ($null -eq $Value -or [string]::IsNullOrWhiteSpace($Name)) { return }
    try { $StartInfo.EnvironmentVariables.Set_Item($Name, $Value) } catch { try { $StartInfo.Environment[$Name] = $Value } catch {} }
}

function Protect-LoginChildEnvironment {
    param([System.Diagnostics.ProcessStartInfo]$StartInfo)

    # True 7A isolation: clear the entire inherited environment, then restore only
    # Windows runtime essentials and package-local HOME/TEMP/PATH. Request credentials
    # are passed in the HTTP request itself, never through inherited variables.
    try { $StartInfo.EnvironmentVariables.Clear() } catch { try { $StartInfo.Environment.Clear() } catch {} }
    [void](Set-LoginTrustedWindowsEnvironment)
    foreach ($name in @("SystemRoot","WINDIR","SystemDrive","ComSpec","PATHEXT","OS","PROCESSOR_ARCHITECTURE","PROCESSOR_IDENTIFIER","NUMBER_OF_PROCESSORS","USERNAME","COMPUTERNAME","PATH","HOME","USERPROFILE","APPDATA","LOCALAPPDATA","TEMP","TMP","TMPDIR")) {
        Set-LoginChildEnvironmentValue $StartInfo $name ([Environment]::GetEnvironmentVariable($name))
    }
    Set-LoginChildEnvironmentValue $StartInfo "PYTHONDONTWRITEBYTECODE" "1"
    Set-LoginChildEnvironmentValue $StartInfo "PYTHONNOUSERSITE" "1"
    Set-LoginChildEnvironmentValue $StartInfo "GIT_CONFIG_NOSYSTEM" "1"
}

function Invoke-JsonHttpPython {
    param(
        [string]$Method,
        [string]$Url,
        [hashtable]$Headers = @{},
        $Body = $null,
        [int]$TimeoutSec = 45,
        [string]$ProxyUrl = ""
    )
    Assert-AllowedLoginJsonRequest $Method $Url $Headers $Body $TimeoutSec $ProxyUrl


    $python = Join-Path $Root "tool\python\python.exe"
    $helper = Join-Path $Root "login-json-http.py"
    if (-not (Test-IsUnderDirectory -Path $python -Directory $Root) -or -not (Test-IsUnderDirectory -Path $helper -Directory $Root) -or
        -not (Test-IsPortableSingleLinkRegularFile -Path $python -Directory $Root) -or
        -not (Test-IsPortableSingleLinkRegularFile -Path $helper -Directory $Root)) {
        return [pscustomobject]@{
            StatusCode = 0
            Body = ""
            Json = $null
            Error = "portable python HTTP helper is missing or unsafe"
        }
    }

    try {
        $payload = [ordered]@{
            method = $Method.ToUpperInvariant()
            url = $Url
            headers = $Headers
            body = $Body
            timeout = $TimeoutSec
            connect_timeout = Get-LoginJsonConnectTimeout
            proxy_url = $ProxyUrl
        }
    $payloadText = ConvertTo-PortableJsonText -InputObject $payload -Depth 32 -Compress

        $oldPythonNoByteCode = $env:PYTHONDONTWRITEBYTECODE
        $env:PYTHONDONTWRITEBYTECODE = "1"
        try {
            $psi = New-Object System.Diagnostics.ProcessStartInfo
            $psi.FileName = $python
            $psi.Arguments = '-X utf8 -E -s -B "' + ($helper.Replace('"', '\"')) + '" -'
            $psi.WorkingDirectory = $Root
            $psi.UseShellExecute = $false
            $psi.CreateNoWindow = $true
            $psi.RedirectStandardInput = $true
            $psi.RedirectStandardOutput = $true
            $psi.RedirectStandardError = $true
            try { $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
            try { $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8 } catch {}
            Protect-LoginChildEnvironment -StartInfo $psi

            Import-LoginProcessSupervisor
            $capture = Invoke-PortableProcess -StartInfo $psi -PackageRoot $Root -TimeoutMs (($TimeoutSec + 5) * 1000) -InputText $payloadText -MaxOutputChars 8388608
            $rawText = $capture.StdOut.Trim()
            $stderrText = $capture.StdErr.Trim()
        } finally {
            if ($null -eq $oldPythonNoByteCode) {
                Remove-Item "Env:PYTHONDONTWRITEBYTECODE" -ErrorAction SilentlyContinue
            } else {
                $env:PYTHONDONTWRITEBYTECODE = $oldPythonNoByteCode
            }
        }

        if ([string]::IsNullOrWhiteSpace($rawText)) {
            return [pscustomobject]@{
                StatusCode = 0
                Body = ""
                Json = $null
                Error = "python HTTP helper returned no valid output; diagnostics suppressed"
            }
        }

        $response = $rawText | ConvertFrom-Json
        $text = ""
        if ($response.PSObject.Properties["body_b64"] -and -not [string]::IsNullOrWhiteSpace([string]$response.body_b64)) {
            try {
                $text = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String([string]$response.body_b64))
            } catch {
                $text = ""
            }
        } elseif ($response.PSObject.Properties["body"]) {
            $text = [string]$response.body
        }
        $json = $null
        if (-not [string]::IsNullOrWhiteSpace($text)) {
            try { $json = $text | ConvertFrom-Json } catch {}
        }
        return [pscustomobject]@{
            StatusCode = [int]$response.status_code
            Body = $text
            Json = $json
            Error = ConvertTo-SafeMessage ([string]$response.error)
        }
    } catch {
        return [pscustomobject]@{
            StatusCode = 0
            Body = ""
            Json = $null
            Error = ConvertTo-SafeMessage $_.Exception.Message
        }
    }
}

function Invoke-JsonHttpAttempt {
    param(
        [string]$Method,
        [string]$Url,
        [hashtable]$Headers = @{},
        $Body = $null,
        [int]$TimeoutSec = 45,
        [string]$ProxyUrl = ""
    )
    Assert-AllowedLoginJsonRequest $Method $Url $Headers $Body $TimeoutSec $ProxyUrl


    $backend = $env:CODEX_LOGIN_JSON_HTTP_BACKEND
    if ([string]::IsNullOrWhiteSpace($backend)) { $backend = "python" }
    $backend = $backend.Trim().ToLowerInvariant()
    if ($backend -eq "python") {
        return Invoke-JsonHttpPython -Method $Method -Url $Url -Headers $Headers -Body $Body -TimeoutSec $TimeoutSec -ProxyUrl $ProxyUrl
    }
    if ($backend -eq "powershell") {
        return Invoke-JsonHttpFallback -Method $Method -Url $Url -Headers $Headers -Body $Body -TimeoutSec $TimeoutSec -ProxyUrl $ProxyUrl
    }
    if ($backend -ne "curl") {
        return [pscustomobject]@{
            StatusCode = 0
            Body = ""
            Json = $null
            Error = "Unsupported CODEX_LOGIN_JSON_HTTP_BACKEND '$backend'. Use python, curl, or powershell."
        }
    }

    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($null -eq $curl) {
        return [pscustomobject]@{
            StatusCode = 0
            Body = ""
            Json = $null
            Error = "curl backend requested, but curl.exe is unavailable."
        }
    }
    $curlSource = [IO.Path]::GetFullPath([string]$curl.Source)
    $curlIsPortable = (Test-IsUnderDirectory -Path $curlSource -Directory $Root) -and
                      (Test-IsPortableSingleLinkRegularFile -Path $curlSource -Directory $Root)
    if (-not $curlIsPortable) {
        return [pscustomobject]@{
            StatusCode = 0
            Body = ""
            Json = $null
            Error = "Refusing host/system curl.exe. Strict portable mode requires package-local curl or the default package-local python backend."
        }
    }

    # curl reads all request/proxy credentials from stdin, never process arguments
    # or request files. Response stdout is bounded by the same supervisor.
    $config = New-Object 'System.Collections.Generic.List[string]'
    $options = [ordered]@{
        'silent' = $null; 'show-error' = $null
        'connect-timeout' = [string](Get-LoginJsonConnectTimeout)
        'max-time' = [string]$TimeoutSec
        'max-filesize' = '4194304'
        'request' = $Method.ToUpperInvariant()
        'proxy' = $ProxyUrl
        'url' = $Url
        'write-out' = "`nCODEX_HTTP_STATUS:%{http_code}"
    }
    foreach ($key in $options.Keys) {
        if ($null -eq $options[$key]) { $config.Add([string]$key) }
        else { $config.Add(([string]$key + ' = ' + (ConvertTo-CurlConfigString ([string]$options[$key])))) }
    }
    foreach ($key in $Headers.Keys) { $config.Add('header = ' + (ConvertTo-CurlConfigString ("{0}: {1}" -f $key, $Headers[$key]))) }
    if ($null -ne $Body) {
        $config.Add('header = "Content-Type: application/json"')
        $config.Add('data-binary = ' + (ConvertTo-CurlConfigString (ConvertTo-PortableJsonText -InputObject $Body -Depth 32 -Compress)))
    }
    $psi = New-Object Diagnostics.ProcessStartInfo
    $psi.FileName = $curlSource; $psi.Arguments = '--disable --config -'
    $psi.WorkingDirectory = $Root; $psi.UseShellExecute = $false; $psi.CreateNoWindow = $true
    $psi.RedirectStandardInput = $true; $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = [Text.Encoding]::UTF8; $psi.StandardErrorEncoding = [Text.Encoding]::UTF8
    Protect-LoginChildEnvironment -StartInfo $psi
    Import-LoginProcessSupervisor
    $capture = Invoke-PortableProcess -StartInfo $psi -PackageRoot $Root -TimeoutMs (($TimeoutSec + 5) * 1000) -InputText (($config -join "`n") + "`n") -MaxOutputChars 8388608
    $rawText = $capture.StdOut
    $status = 0; $text = ''; $json = $null; $err = ''
    $match = [regex]::Match($rawText, '(?s)^(.*)\nCODEX_HTTP_STATUS:([0-9]{3})$')
    if ($match.Success) { $text = $match.Groups[1].Value; $status = [int]$match.Groups[2].Value }
    else { $err = 'curl returned an invalid response envelope.' }
    if ($capture.ExitCode -ne 0) { $err = 'curl request failed; sensitive diagnostics suppressed.' }
    if ($text) { try { $json = $text | ConvertFrom-Json } catch {} }
    return [pscustomobject]@{ StatusCode = $status; Body = $text; Json = $json; Error = $err }
}

function ConvertTo-CurlConfigString {
    param([AllowEmptyString()][string]$Value)
    return '"' + $Value.Replace('\','\\').Replace('"','\"').Replace("`r",'\r').Replace("`n",'\n').Replace("`t",'\t') + '"'
}

function Invoke-JsonHttp {
    param(
        [string]$Method,
        [string]$Url,
        [hashtable]$Headers = @{},
        $Body = $null,
        [int]$TimeoutSec = 45
    )

    Assert-AllowedLoginJsonUrl -Url $Url
    $mode = Get-LoginJsonProxyMode
    $proxyUrl = Get-ProxyUrl -Force

    if ($mode -eq "direct") {
        return Add-HttpNetworkTag (Invoke-JsonHttpAttempt -Method $Method -Url $Url -Headers $Headers -Body $Body -TimeoutSec $TimeoutSec -ProxyUrl "") "direct"
    }
    if ($mode -eq "proxy") {
        return Add-HttpNetworkTag (Invoke-JsonHttpAttempt -Method $Method -Url $Url -Headers $Headers -Body $Body -TimeoutSec $TimeoutSec -ProxyUrl $proxyUrl) "proxy"
    }

    $direct = Add-HttpNetworkTag (Invoke-JsonHttpAttempt -Method $Method -Url $Url -Headers $Headers -Body $Body -TimeoutSec $TimeoutSec -ProxyUrl "") "direct"
    if ((Test-AutoDirectHttpSuccess $direct) -or [string]::IsNullOrWhiteSpace($proxyUrl)) {
        return $direct
    }

    # auto: direct/TUN is considered usable only for 2xx; redirects are never followed for credential-bearing login APIs.
    # If proxy fails, return direct 401 to refresh/delete logic; keep direct 403 conservative because it may be Cloudflare/region/IP blocking.
    $proxied = Add-HttpNetworkTag (Invoke-JsonHttpAttempt -Method $Method -Url $Url -Headers $Headers -Body $Body -TimeoutSec $TimeoutSec -ProxyUrl $proxyUrl) "proxy"
    if ($proxied.StatusCode -ne 0) {
        return $proxied
    }

    if ($direct.StatusCode -eq 401) {
        if (-not [string]::IsNullOrWhiteSpace($proxied.Error)) {
            $direct.Error = "direct returned http 401; proxy failed: $($proxied.Error)"
        }
        return $direct
    }
    if ($direct.StatusCode -eq 403) {
        $proxied.Error = "direct returned http 403; proxy failed: $($proxied.Error)"
        return $proxied
    }

    if (-not [string]::IsNullOrWhiteSpace($direct.Error) -and -not [string]::IsNullOrWhiteSpace($proxied.Error)) {
        $direct.Error = "direct failed: $($direct.Error); proxy failed: $($proxied.Error)"
    }
    return $direct
}

function Get-CodexClientVersion {
    # Standalone login checks must never execute an arbitrary package-local codex.exe.
    # Map exact official/staging hashes to their client versions instead.
    $knownHashes = @{
        '9d563ee4e0441ff9d59d612013e0460ddf8e5709735c2d9f6b98b7ef8ca4eb42' = '0.166.0'
        '70bcb05f9bf1a4e7306edd0cd1b57d02af3267ad02a34b26f45c8c4bb20a3301' = '0.156.1'
        '83751f15cb6a0a7b97df67752c001e3fe1c20e18ffbfec3ff63567296205eb6c' = '0.145.0'
    }
    foreach ($candidate in @(
        (Join-Path $Root "codex.exe"),
        (Join-Path $Root "bin\codex.exe")
    )) {
        if ((Test-IsUnderDirectory -Path $candidate -Directory $Root) -and
            (Test-IsPortableSingleLinkRegularFile -Path $candidate -Directory $Root)) {
            try {
                $hash = ([string](Get-FileHash -LiteralPath $candidate -Algorithm SHA256 -ErrorAction Stop).Hash).ToLowerInvariant()
                if ($knownHashes.ContainsKey($hash)) { return [string]$knownHashes[$hash] }
            } catch {}
        }
    }
    return "0.0.0"
}

function Convert-CredentialEntryToCredential {
    param($Entry)
    if ($null -eq $Entry -or -not [string]::IsNullOrWhiteSpace($Entry.LoadError)) {
        throw $(if ($null -eq $Entry) { "credential entry was not found" } else { $Entry.LoadError })
    }

    $json = $Entry.Json
    $parent = $Entry.Parent
    $rootJson = $Entry.RootJson

    $idToken = Get-StringProperty $json @("id_token", "idToken")
    if ([string]::IsNullOrWhiteSpace($idToken)) {
        $synthetic = Get-ObjectProperty $json "id_token_synthetic"
        if (($synthetic -is [string]) -and $synthetic.Contains(".")) {
            $idToken = $synthetic.Trim()
        }
    }
    $accessToken = Get-StringProperty $json @("access_token", "accessToken")
    $refreshToken = Get-StringProperty $json @("refresh_token", "refreshToken")
    $sessionToken = Get-StringProperty $json @("session_token", "sessionToken")
    $payload = Decode-JwtPayload $idToken

    $user = Get-ObjectProperty $json "user"
    $account = Get-ObjectProperty $json "account"
    $extra = Get-ObjectProperty $parent "extra"

    $email = Get-StringProperty $json @("email", "name")
    if ([string]::IsNullOrWhiteSpace($email)) { $email = Get-StringProperty $user @("email", "name") }
    if ([string]::IsNullOrWhiteSpace($email)) { $email = Get-StringProperty $extra @("email", "name") }
    if ([string]::IsNullOrWhiteSpace($email)) { $email = Get-StringProperty $parent @("email", "name") }
    if ([string]::IsNullOrWhiteSpace($email)) { $email = Get-JwtEmail $payload }

    $plan = Get-StringProperty $json @("chatgpt_plan_type", "plan_type", "planType")
    if ([string]::IsNullOrWhiteSpace($plan)) { $plan = Get-StringProperty $account @("planType", "plan_type") }
    if ([string]::IsNullOrWhiteSpace($plan)) { $plan = Get-StringProperty $parent @("chatgpt_plan_type", "plan_type", "planType") }
    if ([string]::IsNullOrWhiteSpace($plan)) { $plan = Get-JwtAuthField $payload "chatgpt_plan_type" }

    $accountId = Get-StringProperty $json @("chatgpt_account_id", "account_id", "accountId")
    if ([string]::IsNullOrWhiteSpace($accountId)) { $accountId = Get-StringProperty $account @("id", "account_id", "accountId") }
    if ([string]::IsNullOrWhiteSpace($accountId)) { $accountId = Get-StringProperty $parent @("chatgpt_account_id", "account_id", "accountId") }
    if ([string]::IsNullOrWhiteSpace($accountId)) { $accountId = Get-JwtAuthField $payload "chatgpt_account_id" }

    $expires = Get-StringProperty $json @("expires", "expires_at", "expiresAt")
    if ([string]::IsNullOrWhiteSpace($expires)) { $expires = Get-StringProperty $parent @("expires", "expires_at", "expiresAt") }

    return [pscustomobject]@{
        Json = $json
        RootJson = $rootJson
        Entry = $Entry
        IdToken = $idToken
        AccessToken = $accessToken
        RefreshToken = $refreshToken
        SessionToken = $sessionToken
        AccountId = $accountId
        Email = $email
        Plan = $plan
        Expires = $expires
        Payload = $payload
    }
}

function Read-CredentialFile {
    param([string]$Path, [int]$CredentialIndex = -1, $Entry = $null)
    if ($null -ne $Entry) {
        return (Convert-CredentialEntryToCredential $Entry)
    }

    $entries = @(Get-CredentialEntriesForFile -Path $Path)
    if ($CredentialIndex -ge 0) {
        $entry = $entries | Where-Object { $_.CredentialIndex -eq $CredentialIndex } | Select-Object -First 1
        if ($null -eq $entry) { throw "credential index $CredentialIndex was not found in $([System.IO.Path]::GetFileName($Path))" }
        return (Convert-CredentialEntryToCredential $entry)
    }
    if ($entries.Count -ne 1) {
        throw "file contains $($entries.Count) credential entries; specify CredentialIndex"
    }
    return (Convert-CredentialEntryToCredential $entries[0])
}

function Save-CredentialFile {
    param([string]$Path, $Credential)
    $jsonToWrite = $Credential.Json
    if ($null -ne $Credential.RootJson) { $jsonToWrite = $Credential.RootJson }
    Write-Utf8JsonFile -Path $Path -InputObject $jsonToWrite -Depth 64
}

function Remove-InvalidCredential {
    param([string]$Path)
    if (-not (Test-IsUnderDirectory -Path $Path -Directory $LoginDir)) {
        throw "Refusing to delete outside login_json: $Path"
    }
    Remove-Item -LiteralPath $Path -Force
}

function Write-JsonFile {
    param([string]$Path, $Json)
    if (-not (Test-IsUnderDirectory -Path $Path -Directory $LoginDir)) {
        throw "Refusing to write outside login_json: $Path"
    }
    Write-Utf8JsonFile -Path $Path -InputObject $Json -Depth 64
}

function Add-RemovalIndex {
    param([hashtable]$Map, [string]$Key, [int]$Index)
    if (-not $Map.ContainsKey($Key)) {
        $Map[$Key] = New-Object System.Collections.ArrayList
    }
    if (-not $Map[$Key].Contains($Index)) {
        [void]$Map[$Key].Add($Index)
    }
}

function Remove-IndexesFromArrayValue {
    param($ArrayValue, $Indexes)
    $items = @($ArrayValue)
    $remove = @{}
    foreach ($idx in @($Indexes)) {
        $n = -1
        if ([int]::TryParse([string]$idx, [ref]$n) -and $n -ge 0) {
            $remove[[string]$n] = $true
        }
    }
    $kept = New-Object System.Collections.ArrayList
    for ($i = 0; $i -lt $items.Count; $i++) {
        if (-not $remove.ContainsKey([string]$i)) {
            [void]$kept.Add($items[$i])
        }
    }
    return @($kept.ToArray())
}

function Set-ArrayPropertyAfterRemoval {
    param($Object, [string]$PropertyName, $Indexes)
    if ($null -eq $Object) { return $false }
    $value = Get-ObjectProperty $Object $PropertyName
    if ($null -eq $value) { return $false }
    Set-ObjectProperty -Object $Object -Name $PropertyName -Value @(Remove-IndexesFromArrayValue -ArrayValue $value -Indexes $Indexes)
    return $true
}

function Remove-ObjectPropertyIfPresent {
    param($Object, [string]$PropertyName)
    if ($null -eq $Object -or [string]::IsNullOrWhiteSpace($PropertyName)) { return $false }
    if ($Object.PSObject.Properties[$PropertyName]) {
        [void]$Object.PSObject.Properties.Remove($PropertyName)
        return $true
    }
    return $false
}

function Add-RemovalListIndex {
    param([System.Collections.ArrayList]$List, [int]$Index)
    if ($null -eq $List -or $Index -lt 0) { return }
    if (-not $List.Contains($Index)) { [void]$List.Add($Index) }
}

function Add-RemovalListName {
    param([System.Collections.ArrayList]$List, [string]$Name)
    if ($null -eq $List -or [string]::IsNullOrWhiteSpace($Name)) { return }
    if (-not $List.Contains($Name)) { [void]$List.Add($Name) }
}

function Test-ItemHasCredentialEntries {
    param($Item)
    if ($null -eq $Item) { return $false }
    $credentials = Get-ObjectProperty $Item "credentials"
    if ($null -ne $credentials) {
        foreach ($credential in @($credentials)) {
            if (Test-LooksLikeCredentialObject $credential) { return $true }
        }
        return $false
    }
    return (Test-LooksLikeCredentialObject $Item)
}

function Remove-CredentialSourcesFromJson {
    param($Json, [string[]]$Sources)
    $topCredentialIndexes = New-Object System.Collections.ArrayList
    $rootItemIndexes = New-Object System.Collections.ArrayList
    $rootItemCredentialIndexes = @{}
    $accountArrayIndexes = New-Object System.Collections.ArrayList
    $accountArrayCredentialIndexes = @{}
    $accountObjectNames = New-Object System.Collections.ArrayList
    $accountObjectCredentialIndexes = @{}
    $matched = 0

    foreach ($source in @($Sources)) {
        if ([string]::IsNullOrWhiteSpace($source)) { continue }
        $m = [regex]::Match($source, '^credentials\[(\d+)\]$')
        if ($m.Success) {
            [void]$topCredentialIndexes.Add([int]$m.Groups[1].Value)
            $matched++
            continue
        }
        $m = [regex]::Match($source, '^\[(\d+)\]$')
        if ($m.Success) {
            [void]$rootItemIndexes.Add([int]$m.Groups[1].Value)
            $matched++
            continue
        }
        $m = [regex]::Match($source, '^\[(\d+)\]\.credentials\[(\d+)\]$')
        if ($m.Success) {
            Add-RemovalIndex -Map $rootItemCredentialIndexes -Key $m.Groups[1].Value -Index ([int]$m.Groups[2].Value)
            $matched++
            continue
        }
        $m = [regex]::Match($source, '^accounts\[(\d+)\]$')
        if ($m.Success) {
            [void]$accountArrayIndexes.Add([int]$m.Groups[1].Value)
            $matched++
            continue
        }
        $m = [regex]::Match($source, '^accounts\[(\d+)\]\.credentials\[(\d+)\]$')
        if ($m.Success) {
            Add-RemovalIndex -Map $accountArrayCredentialIndexes -Key $m.Groups[1].Value -Index ([int]$m.Groups[2].Value)
            $matched++
            continue
        }
        $m = [regex]::Match($source, '^accounts\.(.+)\.credentials\[(\d+)\]$')
        if ($m.Success) {
            Add-RemovalIndex -Map $accountObjectCredentialIndexes -Key $m.Groups[1].Value -Index ([int]$m.Groups[2].Value)
            $matched++
            continue
        }
        $m = [regex]::Match($source, '^accounts\.(.+)$')
        if ($m.Success) {
            [void]$accountObjectNames.Add($m.Groups[1].Value)
            $matched++
            continue
        }
    }

    if ($Json -is [array]) {
        $rootItems = @($Json)
        foreach ($key in @($rootItemCredentialIndexes.Keys)) {
            $idx = [int]$key
            if ($idx -ge 0 -and $idx -lt $rootItems.Count) {
                [void](Set-ArrayPropertyAfterRemoval -Object $rootItems[$idx] -PropertyName "credentials" -Indexes $rootItemCredentialIndexes[$key])
                if (-not (Test-ItemHasCredentialEntries $rootItems[$idx])) {
                    Add-RemovalListIndex -List $rootItemIndexes -Index $idx
                }
            }
        }
        if ($rootItemIndexes.Count -gt 0) {
            $Json = @(Remove-IndexesFromArrayValue -ArrayValue $rootItems -Indexes $rootItemIndexes)
        }
    } else {
        if ($topCredentialIndexes.Count -gt 0) {
            [void](Set-ArrayPropertyAfterRemoval -Object $Json -PropertyName "credentials" -Indexes $topCredentialIndexes)
        }

        $accounts = Get-ObjectProperty $Json "accounts"
        if ($accounts -is [array]) {
            $accountItems = @($accounts)
            foreach ($key in @($accountArrayCredentialIndexes.Keys)) {
                $idx = [int]$key
                if ($idx -ge 0 -and $idx -lt $accountItems.Count) {
                    [void](Set-ArrayPropertyAfterRemoval -Object $accountItems[$idx] -PropertyName "credentials" -Indexes $accountArrayCredentialIndexes[$key])
                    if (-not (Test-ItemHasCredentialEntries $accountItems[$idx])) {
                        Add-RemovalListIndex -List $accountArrayIndexes -Index $idx
                    }
                }
            }
            if ($accountArrayIndexes.Count -gt 0) {
                Set-ObjectProperty -Object $Json -Name "accounts" -Value @(Remove-IndexesFromArrayValue -ArrayValue $accountItems -Indexes $accountArrayIndexes)
            }
        } elseif ($null -ne $accounts) {
            foreach ($key in @($accountObjectCredentialIndexes.Keys)) {
                $accountItem = Get-ObjectProperty $accounts $key
                if ($null -ne $accountItem) {
                    [void](Set-ArrayPropertyAfterRemoval -Object $accountItem -PropertyName "credentials" -Indexes $accountObjectCredentialIndexes[$key])
                    if (-not (Test-ItemHasCredentialEntries $accountItem)) {
                        Add-RemovalListName -List $accountObjectNames -Name $key
                    }
                }
            }
            foreach ($name in @($accountObjectNames)) {
                [void](Remove-ObjectPropertyIfPresent -Object $accounts -PropertyName $name)
            }
        }
    }

    return [pscustomobject]@{ Json = $Json; Matched = $matched }
}

function Prune-InvalidCredentialEntries {
    param($Results)
    $targets = @($Results | Where-Object {
        $deleteAllowed = $true
        if ($_.PSObject.Properties["DeleteAllowed"]) {
            $deleteAllowed = [bool]$_.DeleteAllowed
        } else {
            # Older/parallel probe records did not serialize DeleteAllowed; INVALID_KEPT with Source is a multi-entry container candidate.
            $deleteAllowed = $false
        }
        $_.Status -eq "INVALID_KEPT" -and
        -not $deleteAllowed -and
        -not [string]::IsNullOrWhiteSpace([string]$_.Path) -and
        -not [string]::IsNullOrWhiteSpace([string]$_.Source)
    })
    if ($targets.Count -eq 0) { return 0 }

    $pruned = 0
    foreach ($group in ($targets | Group-Object Path)) {
        $path = [string]$group.Name
        if (-not (Test-IsPortableSingleLinkRegularFile -Path $path -Directory $LoginDir)) { continue }
        try {
            $raw = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
            $json = $raw | ConvertFrom-Json
            $sources = @($group.Group | ForEach-Object { [string]$_.Source })
            $updated = Remove-CredentialSourcesFromJson -Json $json -Sources $sources
            if ($updated.Matched -le 0) { continue }

            $remainingEntries = @(Get-CredentialEntriesFromJson -Path $path -Json $updated.Json | Where-Object { [string]::IsNullOrWhiteSpace([string]$_.LoadError) })
            $action = ""
            if ($remainingEntries.Count -eq 0) {
                Remove-InvalidCredential $path
                $action = "pruned invalid credential entries; removed empty multi-account file"
            } else {
                Write-JsonFile -Path $path -Json $updated.Json
                $action = "pruned invalid credential entries from multi-account file"
            }

            foreach ($result in @($group.Group)) {
                $result.Status = "INVALID_DELETED"
                $result.Deleted = $true
                $result.Message = (([string]$result.Message) -replace ';\s*kept multi-account container', '')
                $result.Message = "$($result.Message); $action"
            }
            $pruned += [int]$updated.Matched
        } catch {
            foreach ($result in @($group.Group)) {
                $result.Status = "ERROR_KEPT"
                $result.Message = "$($result.Message); prune failed: $(ConvertTo-SafeMessage $_.Exception.Message)"
                $result.Deleted = $false
            }
        }
    }

    if ($pruned -gt 0) {
        Write-Host "Pruned invalid credential entries from multi-account JSON: $pruned" -ForegroundColor Yellow
    }
    return $pruned
}

function Test-PermanentRefreshFailure {
    param($Response)
    if ($Response.StatusCode -notin @(400, 401, 403)) { return $false }
    $body = $Response.Body
    if ([string]::IsNullOrWhiteSpace($body)) { return $Response.StatusCode -eq 401 }
    $lower = $body.ToLowerInvariant()
    if (Test-TransientHttpBlock $Response) { return $false }
    foreach ($code in @("refresh_token_expired", "refresh_token_reused", "refresh_token_invalidated", "invalid_grant", "invalid_token")) {
        if ($lower.Contains($code)) { return $true }
    }
    return $Response.StatusCode -eq 401
}

function Test-TransientHttpBlock {
    param($Response)
    if ($null -eq $Response) { return $false }
    if ($Response.StatusCode -ne 403) { return $false }
    $body = [string]$Response.Body
    if ([string]::IsNullOrWhiteSpace($body)) { return $true }
    $lower = $body.ToLowerInvariant()
    foreach ($marker in @(
        "<!doctype html", "<html", "cloudflare", "cf-ray", "cf-chl", "captcha",
        "just a moment", "attention required", "access denied", "request blocked",
        "challenge", "verify you are human"
    )) {
        if ($lower.Contains($marker)) { return $true }
    }
    return $false
}

function Test-DefinitiveAuthFailure {
    param($Response)
    if ($null -eq $Response) { return $false }
    if ($Response.StatusCode -eq 401) { return $true }
    if ($Response.StatusCode -ne 403) { return $false }
    if (Test-TransientHttpBlock $Response) { return $false }
    $body = [string]$Response.Body
    if ([string]::IsNullOrWhiteSpace($body)) { return $false }
    $lower = $body.ToLowerInvariant()
    foreach ($marker in @(
        "invalid_token", "token_expired", "session_expired", "expired access token",
        "invalid session", "unauthorized", "authentication required"
    )) {
        if ($lower.Contains($marker)) { return $true }
    }
    return $false
}

function Refresh-Credential {
    param([string]$Path, $Credential)

    if ([string]::IsNullOrWhiteSpace($Credential.RefreshToken)) {
        return [pscustomobject]@{ Success = $false; Permanent = $true; Message = "missing refresh_token" }
    }

    $body = [ordered]@{
        client_id = "app_EMoamEEZ73f0CkXaXp7hrann"
        grant_type = "refresh_token"
        refresh_token = $Credential.RefreshToken
    }
    $headers = @{ "User-Agent" = "codex-cli" }
    $response = Invoke-JsonHttp -Method "POST" -Url "https://auth.openai.com/oauth/token" -Headers $headers -Body $body -TimeoutSec 60

    if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300 -and $null -ne $response.Json) {
        $newAccess = Get-StringProperty $response.Json @("access_token")
        $newRefresh = Get-StringProperty $response.Json @("refresh_token")
        $newId = Get-StringProperty $response.Json @("id_token")

        if ([string]::IsNullOrWhiteSpace($newAccess)) {
            return [pscustomobject]@{ Success = $false; Permanent = $false; Message = "refresh response did not contain access_token" }
        }

        Set-ObjectProperty $Credential.Json "access_token" $newAccess
        $Credential.AccessToken = $newAccess

        if (-not [string]::IsNullOrWhiteSpace($newRefresh)) {
            Set-ObjectProperty $Credential.Json "refresh_token" $newRefresh
            $Credential.RefreshToken = $newRefresh
        }
        if (-not [string]::IsNullOrWhiteSpace($newId)) {
            Set-ObjectProperty $Credential.Json "id_token" $newId
            $Credential.IdToken = $newId
            $Credential.Payload = Decode-JwtPayload $newId
        }

        Set-ObjectProperty $Credential.Json "last_refresh" ((Get-Date).ToUniversalTime().ToString("o"))
        Set-ObjectProperty $Credential.Json "expired" $false

        if ([string]::IsNullOrWhiteSpace($Credential.AccountId)) {
            $Credential.AccountId = Get-StringProperty $Credential.Json @("chatgpt_account_id", "account_id", "accountId")
            $account = Get-ObjectProperty $Credential.Json "account"
            if ([string]::IsNullOrWhiteSpace($Credential.AccountId)) {
                $Credential.AccountId = Get-StringProperty $account @("id", "account_id", "accountId")
            }
            if ([string]::IsNullOrWhiteSpace($Credential.AccountId)) {
                $Credential.AccountId = Get-JwtAuthField $Credential.Payload "chatgpt_account_id"
            }
        }
        if ([string]::IsNullOrWhiteSpace($Credential.Email)) {
            $Credential.Email = Get-JwtEmail $Credential.Payload
        }
        if ([string]::IsNullOrWhiteSpace($Credential.Plan)) {
            $Credential.Plan = Get-JwtAuthField $Credential.Payload "chatgpt_plan_type"
        }

        Save-CredentialFile -Path $Path -Credential $Credential
        return [pscustomobject]@{ Success = $true; Permanent = $false; Message = "refreshed" }
    }

    $permanent = Test-PermanentRefreshFailure $response
    $message = $response.Error
    if ([string]::IsNullOrWhiteSpace($message)) { $message = ConvertTo-SafeMessage $response.Body }
    if ([string]::IsNullOrWhiteSpace($message)) { $message = "refresh http $($response.StatusCode)" }
    return [pscustomobject]@{ Success = $false; Permanent = $permanent; Message = $message }
}

function Invoke-Models {
    param($Credential, [string]$ClientVersion)
    $encodedVersion = [System.Uri]::EscapeDataString($ClientVersion)
    $url = "https://chatgpt.com/backend-api/codex/models?client_version=$encodedVersion"
    $headers = @{
        "Authorization" = "Bearer $($Credential.AccessToken)"
        "ChatGPT-Account-Id" = $Credential.AccountId
        "version" = $ClientVersion
        "User-Agent" = "codex-cli"
    }
    return Invoke-JsonHttp -Method "GET" -Url $url -Headers $headers -TimeoutSec 60
}

function Invoke-Usage {
    param($Credential)
    $headers = @{
        "Authorization" = "Bearer $($Credential.AccessToken)"
        "ChatGPT-Account-Id" = $Credential.AccountId
        "User-Agent" = "codex-cli"
    }
    return Invoke-JsonHttp -Method "GET" -Url "https://chatgpt.com/backend-api/wham/usage" -Headers $headers -TimeoutSec 45
}

function Get-ModelSlug {
    param($Model)
    $slug = Get-StringProperty $Model @("slug", "id", "name")
    return $slug
}

function Get-UsageSummary {
    param($UsageResponse)
    if ($null -eq $UsageResponse -or $UsageResponse.StatusCode -lt 200 -or $UsageResponse.StatusCode -ge 300 -or $null -eq $UsageResponse.Json) {
        $detail = ""
        if ($null -ne $UsageResponse) {
            $detail = "usage http $($UsageResponse.StatusCode)"
            if (-not [string]::IsNullOrWhiteSpace($UsageResponse.Error)) { $detail = $UsageResponse.Error }
        }
        return [pscustomobject]@{ Quota = "UNKNOWN"; Reset = ""; Detail = $detail }
    }

    $text = ConvertTo-PortableJsonText -InputObject $UsageResponse.Json -Depth 64 -Compress
    $lower = $text.ToLowerInvariant()
    $hasQuota = $false
    $explicitNoQuota = $false
    $ambiguousNoQuota = $false

    if ($lower -match '"has_credits"\s*:\s*true' -or $lower -match '"available_count"\s*:\s*[1-9]\d*') {
        $hasQuota = $true
    }
    if ($lower -match '"is_exhausted"\s*:\s*true') {
        $explicitNoQuota = $true
    }
    if ($lower -match '"has_credits"\s*:\s*false') {
        $ambiguousNoQuota = $true
    }

    $remainingMatches = [regex]::Matches($lower, '"remaining"\s*:\s*(\d+)')
    if ($remainingMatches.Count -gt 0) {
        $anyPositive = $false
        foreach ($m in $remainingMatches) {
            if ([int64]$m.Groups[1].Value -gt 0) { $anyPositive = $true }
        }
        if ($anyPositive) { $hasQuota = $true } else { $ambiguousNoQuota = $true }
    }

    $reset = ""
    $resetMatch = [regex]::Match($text, '"(reset_at|resets_at|reset_time|resetTime)"\s*:\s*"([^"]+)"')
    if ($resetMatch.Success) {
        $reset = $resetMatch.Groups[2].Value
    } else {
        $afterMatch = [regex]::Match($lower, '"(reset_after_seconds|retry_after)"\s*:\s*(\d+)')
        if ($afterMatch.Success) {
            $seconds = [int64]$afterMatch.Groups[2].Value
            $reset = (Get-Date).ToUniversalTime().AddSeconds($seconds).ToString("o")
        }
    }

    $rateLimit = Get-ObjectProperty $UsageResponse.Json "rate_limit"
    $allowed = Get-ObjectProperty $rateLimit "allowed"
    $limitReached = Get-ObjectProperty $rateLimit "limit_reached"
    if ($null -ne $allowed) {
        $allowedText = ([string]$allowed).Trim().ToLowerInvariant()
        if ($allowedText -eq "false") {
            return [pscustomobject]@{ Quota = "NO_QUOTA"; Reset = $reset; Detail = "rate_limit.allowed=false" }
        }
        if ($allowedText -eq "true" -and $null -eq $limitReached) {
            return [pscustomobject]@{ Quota = "HAS_QUOTA"; Reset = $reset; Detail = "rate_limit.allowed=true" }
        }
    }
    if ($null -ne $limitReached) {
        $limitReachedText = ([string]$limitReached).Trim().ToLowerInvariant()
        if ($limitReachedText -eq "true") {
            return [pscustomobject]@{ Quota = "NO_QUOTA"; Reset = $reset; Detail = "rate_limit.limit_reached=true" }
        }
        if ($limitReachedText -eq "false") {
            return [pscustomobject]@{ Quota = "HAS_QUOTA"; Reset = $reset; Detail = "rate_limit.limit_reached=false" }
        }
    }

    $rateLimitReachedType = Get-StringProperty $UsageResponse.Json @("rate_limit_reached_type")
    if (-not [string]::IsNullOrWhiteSpace($rateLimitReachedType)) {
        return [pscustomobject]@{ Quota = "NO_QUOTA"; Reset = $reset; Detail = "rate_limit_reached_type=$rateLimitReachedType" }
    }

    if ($explicitNoQuota -and -not $hasQuota) {
        return [pscustomobject]@{ Quota = "NO_QUOTA"; Reset = $reset; Detail = "usage indicates exhausted/no credits" }
    }
    if ($hasQuota) {
        return [pscustomobject]@{ Quota = "HAS_QUOTA"; Reset = $reset; Detail = "usage indicates remaining credits" }
    }
    if ($ambiguousNoQuota) {
        return [pscustomobject]@{ Quota = "UNKNOWN"; Reset = $reset; Detail = "usage quota signal is ambiguous; not treated as exhausted" }
    }
    return [pscustomobject]@{ Quota = "UNKNOWN"; Reset = $reset; Detail = "usage schema not recognized" }
}

function New-ScanResult {
    param([string]$Path, $Entry = $null)
    $file = [System.IO.Path]::GetFileName($Path)
    $credentialIndex = -1
    $source = ""
    $deleteAllowed = $true
    if ($null -ne $Entry) {
        if ($Entry.PSObject.Properties["File"]) { $file = $Entry.File }
        if ($Entry.PSObject.Properties["CredentialIndex"]) { $credentialIndex = [int]$Entry.CredentialIndex }
        if ($Entry.PSObject.Properties["Source"]) { $source = [string]$Entry.Source }
        if ($Entry.PSObject.Properties["DeleteAllowed"]) { $deleteAllowed = [bool]$Entry.DeleteAllowed }
    }
    return [pscustomobject][ordered]@{
        File = $file
        Path = $Path
        CredentialIndex = $credentialIndex
        Source = $source
        Network = ""
        Email = ""
        AccountId = ""
        Plan = ""
        Status = "UNKNOWN"
        Quota = "UNKNOWN"
        Reset = ""
        Models = @()
        Message = ""
        Deleted = $false
        DeleteAllowed = $deleteAllowed
        Credential = $null
    }
}

function Set-DeletedResult {
    param($Result, [string]$Path, [string]$Message, $Entry = $null)
    $deleteAllowed = $true
    if ($null -ne $Entry -and $Entry.PSObject.Properties["DeleteAllowed"]) {
        $deleteAllowed = [bool]$Entry.DeleteAllowed
    } elseif ($Result.PSObject.Properties["DeleteAllowed"]) {
        $deleteAllowed = [bool]$Result.DeleteAllowed
    }
    if (-not $deleteAllowed) {
        $Result.Status = "INVALID_KEPT"
        $Result.Message = "$Message; kept multi-account container"
        $Result.Deleted = $false
        return
    }
    try {
        Remove-InvalidCredential $Path
        $Result.Status = "INVALID_DELETED"
        $Result.Message = $Message
        $Result.Deleted = $true
    } catch {
        $Result.Status = "ERROR_KEPT"
        $Result.Message = "$Message; delete failed: $(ConvertTo-SafeMessage $_.Exception.Message)"
        $Result.Deleted = $false
    }
}

function Test-CredentialFile {
    param([string]$Path, [string]$ClientVersion, [int]$CredentialIndex = -1, $Entry = $null)

    if ($null -eq $Entry -and $CredentialIndex -ge 0) {
        try {
            $Entry = @(Get-CredentialEntriesForFile -Path $Path) | Where-Object { $_.CredentialIndex -eq $CredentialIndex } | Select-Object -First 1
        } catch {}
    }
    $result = New-ScanResult -Path $Path -Entry $Entry

    if ($null -ne $Entry -and -not [string]::IsNullOrWhiteSpace($Entry.LoadError)) {
        # Inspection/parse failure is not proof of an invalid credential.
        # ERROR_KEPT also excludes this entry from multi-account pruning.
        $result.Status = "ERROR_KEPT"
        $result.Message = "credential input could not be safely read or parsed; kept file"
        return [pscustomobject]$result
    }

    try {
        $cred = Read-CredentialFile -Path $Path -CredentialIndex $CredentialIndex -Entry $Entry
        $result.Email = $cred.Email
        $result.AccountId = $cred.AccountId
        $result.Plan = $cred.Plan
        $result.Credential = $cred
    } catch {
        # Includes file access errors and a missing/stale credential index.
        # Do not delete a whole container when selecting one entry failed.
        $result.Status = "ERROR_KEPT"
        $result.Message = "credential input could not be safely read or parsed; kept file"
        $result.Credential = $null
        return [pscustomobject]$result
    }

    if ([string]::IsNullOrWhiteSpace($cred.AccessToken)) {
        Set-DeletedResult -Result $result -Path $Path -Message "missing access_token/accessToken" -Entry $Entry
        return [pscustomobject]$result
    }

    $needRefresh = $false
    if (-not [string]::IsNullOrWhiteSpace($cred.IdToken) -and $null -ne $cred.Payload) {
        $exp = Get-JwtExpiration $cred.IdToken
        if ($null -ne $exp -and $exp -lt (Get-Date).ToUniversalTime().AddMinutes(2)) {
            $needRefresh = $true
        }
    }
    $expiredFlag = Get-ObjectProperty $cred.Json "expired"
    if ($null -ne $expiredFlag -and ([string]$expiredFlag).ToLowerInvariant() -eq "true") {
        $needRefresh = $true
    }
    if (-not [string]::IsNullOrWhiteSpace($cred.Expires)) {
        try {
            $expDto = [System.DateTimeOffset]::Parse($cred.Expires)
            if ($expDto.UtcDateTime -lt (Get-Date).ToUniversalTime().AddMinutes(2)) {
                $needRefresh = $true
            }
        } catch {}
    }

    if ($needRefresh -and -not [string]::IsNullOrWhiteSpace($cred.RefreshToken)) {
        $refresh = Refresh-Credential -Path $Path -Credential $cred
        if (-not $refresh.Success) {
            if ($refresh.Permanent) {
                Set-DeletedResult -Result $result -Path $Path -Message ("refresh rejected: " + $refresh.Message) -Entry $Entry
            } else {
                $result.Status = "ERROR_KEPT"
                $result.Message = ("refresh transient error: " + $refresh.Message)
            }
            return [pscustomobject]$result
        }
    }

    if ([string]::IsNullOrWhiteSpace($cred.AccountId)) {
        $cred.AccountId = Get-StringProperty $cred.Json @("chatgpt_account_id", "account_id", "accountId")
        $account = Get-ObjectProperty $cred.Json "account"
        if ([string]::IsNullOrWhiteSpace($cred.AccountId)) { $cred.AccountId = Get-StringProperty $account @("id", "account_id", "accountId") }
        if ([string]::IsNullOrWhiteSpace($cred.AccountId)) { $cred.AccountId = Get-JwtAuthField $cred.Payload "chatgpt_account_id" }
    }
    if ([string]::IsNullOrWhiteSpace($cred.AccountId)) {
        Set-DeletedResult -Result $result -Path $Path -Message "missing account_id/chatgpt_account_id/account.id" -Entry $Entry
        return [pscustomobject]$result
    }

    $modelsResponse = Invoke-Models -Credential $cred -ClientVersion $ClientVersion
    if ($modelsResponse.PSObject.Properties["Network"]) { $result.Network = [string]$modelsResponse.Network }
    if ($modelsResponse.StatusCode -in @(401, 403)) {
        if (Test-TransientHttpBlock $modelsResponse) {
            $result.Status = "ERROR_KEPT"
            $result.Message = "models endpoint returned 403 network/proxy challenge; kept credential"
            return [pscustomobject]$result
        }
        if ($modelsResponse.StatusCode -eq 403 -and -not (Test-DefinitiveAuthFailure $modelsResponse)) {
            $result.Status = "ERROR_KEPT"
            $result.Message = "models endpoint returned ambiguous 403; kept credential to avoid deleting a valid account"
            return [pscustomobject]$result
        }
        if ([string]::IsNullOrWhiteSpace($cred.RefreshToken)) {
            Set-DeletedResult -Result $result -Path $Path -Message "models endpoint returned unauthorized and no refresh_token is available" -Entry $Entry
            return [pscustomobject]$result
        }
        $refresh = Refresh-Credential -Path $Path -Credential $cred
        if (-not $refresh.Success) {
            if ($refresh.Permanent) {
                Set-DeletedResult -Result $result -Path $Path -Message ("models auth failed and refresh rejected: " + $refresh.Message) -Entry $Entry
            } else {
                $result.Status = "ERROR_KEPT"
                $result.Message = ("models auth failed; refresh transient error: " + $refresh.Message)
            }
            return [pscustomobject]$result
        }
        $modelsResponse = Invoke-Models -Credential $cred -ClientVersion $ClientVersion
        if ($modelsResponse.PSObject.Properties["Network"]) { $result.Network = [string]$modelsResponse.Network }
    }

    if ($modelsResponse.PSObject.Properties["Network"]) { $result.Network = [string]$modelsResponse.Network }
    if ($modelsResponse.StatusCode -in @(401, 403)) {
        if (Test-TransientHttpBlock $modelsResponse) {
            $result.Status = "ERROR_KEPT"
            $result.Message = "models endpoint returned 403 network/proxy challenge after refresh; kept credential"
            return [pscustomobject]$result
        }
        if ($modelsResponse.StatusCode -eq 403 -and -not (Test-DefinitiveAuthFailure $modelsResponse)) {
            $result.Status = "ERROR_KEPT"
            $result.Message = "models endpoint returned ambiguous 403 after refresh; kept credential"
            return [pscustomobject]$result
        }
        Set-DeletedResult -Result $result -Path $Path -Message "models endpoint returned unauthorized after refresh" -Entry $Entry
        return [pscustomobject]$result
    }

    if ($modelsResponse.StatusCode -lt 200 -or $modelsResponse.StatusCode -ge 300 -or $null -eq $modelsResponse.Json) {
        $result.Status = "ERROR_KEPT"
        $msg = $modelsResponse.Error
        if ([string]::IsNullOrWhiteSpace($msg)) { $msg = ConvertTo-SafeMessage $modelsResponse.Body }
        if ([string]::IsNullOrWhiteSpace($msg)) { $msg = "models http $($modelsResponse.StatusCode)" }
        $result.Message = $msg
        return [pscustomobject]$result
    }

    $models = @()
    if ($modelsResponse.Json.PSObject.Properties["models"]) {
        $models = @($modelsResponse.Json.models | Where-Object { -not [string]::IsNullOrWhiteSpace((Get-ModelSlug $_)) })
    }
    $result.Models = $models
    $result.Status = "VALID"
    $result.Message = "models: $($models.Count)"

    $usage = Invoke-Usage -Credential $cred
    if ([string]::IsNullOrWhiteSpace($result.Network) -and $usage.PSObject.Properties["Network"]) { $result.Network = [string]$usage.Network }
    $summary = Get-UsageSummary $usage
    $result.Quota = $summary.Quota
    $result.Reset = $summary.Reset
    if (-not [string]::IsNullOrWhiteSpace($summary.Detail)) {
        $result.Message = "$($result.Message); $($summary.Detail)"
    }

    $result.Email = $cred.Email
    $result.AccountId = $cred.AccountId
    $result.Plan = $cred.Plan
    $result.Credential = $cred
    return [pscustomobject]$result
}

function ConvertTo-BeijingTimeText {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return "" }
    try {
        $dto = [System.DateTimeOffset]::Parse($Value)
        $tz = [System.TimeZoneInfo]::FindSystemTimeZoneById("China Standard Time")
        return ([System.TimeZoneInfo]::ConvertTime($dto, $tz)).ToString("yyyy-MM-dd HH:mm:ss zzz")
    } catch {
        return $Value
    }
}

function Write-Report {
    param(
        $Results,
        [string]$ClientVersion,
        [int]$TotalFiles = 0,
        [int]$ScanLimit = 0
    )
    $csvPath = Join-Path $LoginDir "login_json_report.csv"
    if (-not (Test-IsUnderDirectory -Path $csvPath -Directory $LoginDir)) {
        throw "Refusing report write outside login_json or through reparse path: $csvPath"
    }
    $csvRows = New-Object System.Collections.Generic.List[object]
    foreach ($r in $Results) {
        $modelCount = @($r.Models).Count
        $resetBeijing = ConvertTo-BeijingTimeText $r.Reset
        $csvRows.Add([pscustomobject][ordered]@{
            状态 = $r.Status
            额度 = $r.Quota
            网络 = $(if ($r.PSObject.Properties["Network"]) { $r.Network } else { "" })
            北京时间刷新 = $resetBeijing
            UTC刷新 = $r.Reset
            模型数量 = $modelCount
            邮箱 = $r.Email
            套餐 = $r.Plan
            账号ID = $r.AccountId
            文件名 = $r.File
            凭证序号 = $r.CredentialIndex
            来源 = $r.Source
            说明 = $r.Message
        }) | Out-Null
    }
    Write-Utf8CsvFileAtomic -Path $csvPath -Rows $csvRows
    return $csvPath
}

function Save-PartialReport {
    param($Results, [switch]$Force)
    try {
        if ($null -eq $Results) { return }
        $count = @($Results).Count
        if ($Results -is [System.Collections.ArrayList]) { $count = $Results.Count }
        $now = (Get-Date).ToUniversalTime()
        if (-not $Force) {
            if ($count -gt 1 -and ($count % 10) -ne 0) {
                if ($null -ne $script:LastPartialReportWriteUtc -and $script:LastPartialReportWriteUtc -is [datetime]) {
                    if (($now - $script:LastPartialReportWriteUtc).TotalSeconds -lt 5) { return }
                }
            }
        }
        if ($Results -is [System.Collections.ArrayList]) {
            [void](Write-Report -Results @($Results.ToArray()) -ClientVersion "" -TotalFiles 0 -ScanLimit 0)
        } else {
            [void](Write-Report -Results @($Results) -ClientVersion "" -TotalFiles 0 -ScanLimit 0)
        }
        $script:LastPartialReportWriteUtc = $now
    } catch {}
}

function Write-ScanResultProgress {
    param($Result, [int]$Done = 0, [int]$Total = 0)
    if ($null -eq $Result) { return }
    $prefix = "done"
    if ($Done -gt 0 -and $Total -gt 0) { $prefix = "$Done/$Total" }
    $network = ""
    if ($Result.PSObject.Properties["Network"]) { $network = [string]$Result.Network }
    if ([string]::IsNullOrWhiteSpace($network)) { $network = "-" }
    $quota = ""
    if ($Result.PSObject.Properties["Quota"]) { $quota = [string]$Result.Quota }
    if ([string]::IsNullOrWhiteSpace($quota)) { $quota = "-" }
    $msg = ConvertTo-SafeMessage ([string]$Result.Message)
    $line = ("  {0} {1}: {2} quota={3} net={4} {5}" -f $prefix, $Result.File, $Result.Status, $quota, $network, $msg)
    $color = "Gray"
    switch -Regex ([string]$Result.Status) {
        "^VALID$" { $color = "Green"; break }
        "INVALID|DELETED" { $color = "Yellow"; break }
        "ERROR" { $color = "DarkYellow"; break }
    }
    Write-Host $line -ForegroundColor $color
}

function ConvertTo-ResultRecord {
    param($Result)
    $models = @()
    foreach ($model in @($Result.Models)) {
        $slug = Get-ModelSlug $model
        if ([string]::IsNullOrWhiteSpace($slug)) { continue }
        $display = Get-StringProperty $model @("display_name")
        if ([string]::IsNullOrWhiteSpace($display)) { $display = $slug }
        $models += [pscustomobject][ordered]@{
            slug = $slug
            display_name = $display
        }
    }

    return [pscustomobject][ordered]@{
        File = $Result.File
        Path = $Result.Path
        RelativePath = (Get-RelativePathUnderRoot $Result.Path)
        CredentialIndex = $Result.CredentialIndex
        Source = $Result.Source
        Network = $(if ($Result.PSObject.Properties["Network"]) { $Result.Network } else { "" })
        Email = $Result.Email
        AccountId = $Result.AccountId
        Plan = $Result.Plan
        Status = $Result.Status
        Quota = $Result.Quota
        Reset = $Result.Reset
        Models = $models
        Message = $Result.Message
        Deleted = $Result.Deleted
        DeleteAllowed = $(if ($Result.PSObject.Properties["DeleteAllowed"]) { [bool]$Result.DeleteAllowed } else { $true })
    }
}

function Test-IsInternalLoginJsonFile {
    param([string]$Name)
    if ([string]::IsNullOrWhiteSpace($Name)) { return $false }
    $lower = $Name.Trim().ToLowerInvariant()
    return ($lower -in @("login_json_report.json", "login_json_report.cache.json"))
}

function Get-LoginCredentialFiles {
    if (-not (Test-Path -LiteralPath $LoginDir)) { return @() }
    return @(Get-ChildItem -LiteralPath $LoginDir -Filter "*.json" -File -ErrorAction SilentlyContinue |
        Where-Object { -not (Test-IsInternalLoginJsonFile $_.Name) } |
        Where-Object { Test-IsPortableSingleLinkRegularFile -Path $_.FullName -Directory $LoginDir } |
        Sort-Object Name)
}

function Get-ScanFileState {
    param($Files)
    $states = New-Object System.Collections.ArrayList
    foreach ($file in @($Files)) {
        [void]$states.Add([pscustomobject][ordered]@{
            file = $file.Name
            relative_path = (Get-RelativePathUnderRoot $file.FullName)
            length = [int64]$file.Length
            last_write_utc = $file.LastWriteTimeUtc.ToString("o")
        })
    }
    return @($states.ToArray())
}

function Test-ScanCacheFileState {
    param($CachedFiles, $CurrentFiles)
    $cached = @($CachedFiles)
    $current = @(Get-ScanFileState -Files $CurrentFiles)
    if ($cached.Count -ne $current.Count) { return $false }
    for ($i = 0; $i -lt $current.Count; $i++) {
        $c = $cached[$i]
        $n = $current[$i]
        if ([string]$c.relative_path -ne [string]$n.relative_path) { return $false }
        if ([string]$c.file -ne [string]$n.file) { return $false }
        $cachedLength = 0L
        if (-not [int64]::TryParse([string]$c.length, [ref]$cachedLength)) { return $false }
        if ($cachedLength -ne [int64]$n.length) { return $false }
        if ([string]$c.last_write_utc -ne [string]$n.last_write_utc) { return $false }
    }
    return $true
}

function Resolve-ScanCacheResultPaths {
    param($Results)
    $loginDir = Join-Path $Root "login_json"
    foreach ($result in @($Results)) {
        $resolved = ""
        if ($result.PSObject.Properties["RelativePath"] -and -not [string]::IsNullOrWhiteSpace([string]$result.RelativePath)) {
            $candidatePath = Join-Path $Root ([string]$result.RelativePath)
            if ((Test-IsUnderDirectory -Path $candidatePath -Directory $loginDir) -and (Test-Path -LiteralPath $candidatePath)) {
                $resolved = $candidatePath
            }
        }
        if ([string]::IsNullOrWhiteSpace($resolved) -and $result.PSObject.Properties["Path"] -and -not [string]::IsNullOrWhiteSpace([string]$result.Path)) {
            $candidatePath = [string]$result.Path
            if ((Test-IsUnderDirectory -Path $candidatePath -Directory $loginDir) -and (Test-Path -LiteralPath $candidatePath)) {
                $resolved = $candidatePath
            }
        }
        if (-not [string]::IsNullOrWhiteSpace($resolved)) {
            if ($result.PSObject.Properties["Path"]) {
                $result.Path = $resolved
            } else {
                $result | Add-Member -NotePropertyName "Path" -NotePropertyValue $resolved
            }
        }
    }
    return @($Results)
}

function Write-ScanCache {
    param(
        $Results,
        [string]$ClientVersion,
        $ScannedFiles,
        [int]$ScanLimit,
        [int]$CredentialLimit
    )
    $records = @($Results | ForEach-Object { ConvertTo-ResultRecord $_ })
    $payload = [ordered]@{
        cache_version = $ScanCacheVersion
        generated_at = (Get-Date).ToUniversalTime().ToString("o")
        client_version = $ClientVersion
        scan_limit = $ScanLimit
        credential_limit = $CredentialLimit
        files = @(Get-ScanFileState -Files $ScannedFiles)
        results = $records
    }
    Write-Utf8JsonFile -Path $ScanCachePath -InputObject $payload -Depth 64
    return $ScanCachePath
}

function Read-ScanCache {
    param([string]$ClientVersion)
    if (-not (Test-IsPortableSingleLinkRegularFile -Path $ScanCachePath -Directory $LoginDir)) { return $null }
    try {
        $raw = [System.IO.File]::ReadAllText($ScanCachePath, [System.Text.Encoding]::UTF8)
        $cache = $raw | ConvertFrom-Json
        if ($null -eq $cache) { return $null }
        $cacheVersion = 0
        if (-not [int]::TryParse([string]$cache.cache_version, [ref]$cacheVersion) -or $cacheVersion -ne $ScanCacheVersion) { return $null }
        if ([string]$cache.client_version -ne $ClientVersion) { return $null }

        $scanLimit = Resolve-MaxFiles
        $credentialLimit = Resolve-MaxCredentials
        $cacheScanLimit = -1
        $cacheCredentialLimit = -1
        if (-not [int]::TryParse([string]$cache.scan_limit, [ref]$cacheScanLimit) -or $cacheScanLimit -ne $scanLimit) { return $null }
        if (-not [int]::TryParse([string]$cache.credential_limit, [ref]$cacheCredentialLimit) -or $cacheCredentialLimit -ne $credentialLimit) { return $null }

        $allFiles = @(Get-LoginCredentialFiles)
        if ($scanLimit -gt 0) {
            $files = @($allFiles | Select-Object -First $scanLimit)
        } else {
            $files = @($allFiles)
        }
        if (-not (Test-ScanCacheFileState -CachedFiles $cache.files -CurrentFiles $files)) { return $null }

        $results = @(Resolve-ScanCacheResultPaths -Results @($cache.results))
        if ($results.Count -eq 0 -and $files.Count -gt 0) { return $null }
        return $results
    } catch {
        return $null
    }
}

function Read-CsvReportCache {
    $csvPath = Join-Path $LoginDir "login_json_report.csv"
    if (-not (Test-IsPortableSingleLinkRegularFile -Path $csvPath -Directory $LoginDir)) { return $null }
    $modelSlug = $env:CODEX_MODEL
    if ([string]::IsNullOrWhiteSpace($modelSlug)) { return $null }

    try {
        $csvItem = Get-Item -LiteralPath $csvPath
        $credentialFiles = @(Get-LoginCredentialFiles)
        foreach ($file in $credentialFiles) {
            if ($file.LastWriteTimeUtc -gt $csvItem.LastWriteTimeUtc.AddSeconds(2)) {
                return $null
            }
        }

        $rows = @(Import-Csv -LiteralPath $csvPath -Encoding UTF8)
        $records = New-Object System.Collections.ArrayList
        foreach ($row in $rows) {
            if (([string]$row.'状态') -ne "VALID") { continue }
            $fileName = ([string]$row.'文件名')
            if ([string]::IsNullOrWhiteSpace($fileName) -or (Test-IsInternalLoginJsonFile $fileName)) { continue }
            # 多账号 CSV 的显示名形如 file.json#2，实际文件名不包含序号后缀。
            $diskFileName = $fileName -replace '(?i)(\.json)#\d+$', '$1'
            $credentialPath = Join-Path $LoginDir $diskFileName
            if (-not (Test-IsUnderDirectory -Path $credentialPath -Directory $LoginDir)) { continue }
            if (-not (Test-Path -LiteralPath $credentialPath)) { continue }

            $modelCount = 0
            if (-not [int]::TryParse(([string]$row.'模型数量'), [ref]$modelCount) -or $modelCount -le 0) { continue }

            $credentialIndex = 0
            [void][int]::TryParse(([string]$row.'凭证序号'), [ref]$credentialIndex)

            $quota = ([string]$row.'额度')
            $message = ([string]$row.'说明')
            if (-not (Test-IsUnderDirectory -Path $credentialPath -Directory $LoginDir)) { continue }
            if ($quota -eq "NO_QUOTA" -and $message -match "usage indicates exhausted/no credits") {
                $quota = "UNKNOWN"
                $message = "$message; cached CSV quota treated as ambiguous"
            }

            [void]$records.Add([pscustomobject][ordered]@{
                File = $fileName
                Path = $credentialPath
                RelativePath = (Get-RelativePathUnderRoot $credentialPath)
                CredentialIndex = $credentialIndex
                Source = ([string]$row.'来源')
                Network = ([string]$row.'网络')
                Email = ([string]$row.'邮箱')
                AccountId = ([string]$row.'账号ID')
                Plan = ([string]$row.'套餐')
                Status = ([string]$row.'状态')
                Quota = $quota
                Reset = ([string]$row.'UTC刷新')
                Models = @([pscustomobject][ordered]@{ slug = $modelSlug; display_name = $modelSlug })
                Message = $message
                Deleted = $false
            })
        }
        if ($records.Count -eq 0) { return $null }
        return @($records)
    } catch {
        return $null
    }
}

function Resolve-ThrottleLimit {
    if ($ThrottleLimit -gt 0) { return [Math]::Min($ThrottleLimit, 20) }
    $fromEnv = 0
    if (-not [string]::IsNullOrWhiteSpace($env:CODEX_LOGIN_JSON_THROTTLE) -and [int]::TryParse($env:CODEX_LOGIN_JSON_THROTTLE, [ref]$fromEnv) -and $fromEnv -gt 0) {
        return [Math]::Min($fromEnv, 20)
    }
    return 6
}

function Resolve-MaxFiles {
    if ($MaxFiles -ge 0) { return $MaxFiles }
    $fromEnv = -1
    if (-not [string]::IsNullOrWhiteSpace($env:CODEX_LOGIN_JSON_MAX_FILES) -and [int]::TryParse($env:CODEX_LOGIN_JSON_MAX_FILES, [ref]$fromEnv) -and $fromEnv -ge 0) {
        return $fromEnv
    }
    return 0
}

function Resolve-MaxCredentials {
    if ($MaxCredentials -ge 0) { return $MaxCredentials }
    $fromEnv = -1
    if (-not [string]::IsNullOrWhiteSpace($env:CODEX_LOGIN_JSON_MAX_CREDENTIALS) -and [int]::TryParse($env:CODEX_LOGIN_JSON_MAX_CREDENTIALS, [ref]$fromEnv) -and $fromEnv -ge 0) {
        return $fromEnv
    }
    return 0
}

function Resolve-JobTimeoutSec {
    $fromEnv = 0
    if (-not [string]::IsNullOrWhiteSpace($env:CODEX_LOGIN_JSON_JOB_TIMEOUT_SEC) -and [int]::TryParse($env:CODEX_LOGIN_JSON_JOB_TIMEOUT_SEC, [ref]$fromEnv) -and $fromEnv -ge 30) {
        return [Math]::Min($fromEnv, 3600)
    }
    return 420
}

function New-ProbeErrorResult {
    param([string]$Path, [string]$Message)
    $result = New-ScanResult $Path
    $result.Status = "ERROR_KEPT"
    $result.Message = $Message
    return (ConvertTo-ResultRecord $result)
}

function Receive-CompletedProbeJobs {
    param(
        [System.Collections.ArrayList]$Jobs,
        [System.Collections.ArrayList]$Results,
        [switch]$OnlyFinished
    )

    for ($i = $Jobs.Count - 1; $i -ge 0; $i--) {
        $item = $Jobs[$i]
        $job = $item.Job
        $timedOut = $false
        $jobIsActive = $job.State -in @("NotStarted", "Running")
        if ($jobIsActive) {
            $elapsed = ((Get-Date).ToUniversalTime() - $item.StartedAtUtc).TotalSeconds
            $timedOut = $elapsed -ge $item.TimeoutSec
        }
        if ($OnlyFinished -and $jobIsActive -and -not $timedOut) { continue }
        if ($timedOut) {
            Stop-Job -Job $job -ErrorAction SilentlyContinue
        } elseif (-not $OnlyFinished -and $jobIsActive) {
            Wait-Job -Job $job -Timeout $item.TimeoutSec | Out-Null
            if ($job.State -in @("NotStarted", "Running")) {
                $timedOut = $true
                Stop-Job -Job $job -ErrorAction SilentlyContinue
            }
        }

        $output = ""
        try {
            $output = (Receive-Job -Job $job -ErrorAction SilentlyContinue | Out-String).Trim()
        } catch {}

        if (-not $timedOut -and (Test-IsPortableSingleLinkRegularFile -Path $item.ResultPath -Directory $TmpDir)) {
            try {
                $raw = [System.IO.File]::ReadAllText($item.ResultPath, [System.Text.Encoding]::UTF8)
                $record = ($raw | ConvertFrom-Json)
                $Results.Add($record) | Out-Null
                Write-ScanResultProgress -Result $record -Done $Results.Count -Total $script:LoginJsonProgressTotal
                Save-PartialReport -Results $Results
            } catch {
                $record = (New-ProbeErrorResult -Path $item.FilePath -Message ("failed to read probe result: " + (ConvertTo-SafeMessage $_.Exception.Message)))
                $Results.Add($record) | Out-Null
                Write-ScanResultProgress -Result $record -Done $Results.Count -Total $script:LoginJsonProgressTotal
                Save-PartialReport -Results $Results
            }
        } else {
            $msg = if ($timedOut) { "probe timed out after $($item.TimeoutSec) seconds" } else { "probe did not write a result" }
            if (-not $timedOut -and -not [string]::IsNullOrWhiteSpace($output)) {
                $msg = ConvertTo-SafeMessage $output
            } elseif (-not $timedOut -and $job.State -ne "Completed") {
                $msg = "probe job state: $($job.State)"
            }
            $record = (New-ProbeErrorResult -Path $item.FilePath -Message $msg)
            $Results.Add($record) | Out-Null
            Write-ScanResultProgress -Result $record -Done $Results.Count -Total $script:LoginJsonProgressTotal
            Save-PartialReport -Results $Results
        }

        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $item.ResultPath -ErrorAction SilentlyContinue
        $Jobs.RemoveAt($i)
    }
}

function Invoke-ParallelCredentialChecks {
    param($Targets, [string]$ClientVersion, [int]$Limit)

    $scriptPath = $MyInvocation.MyCommand.Path
    if ([string]::IsNullOrWhiteSpace($scriptPath)) { $scriptPath = Join-Path $Root "login-json.ps1" }
    $jobs = New-Object System.Collections.ArrayList
    $pending = New-Object System.Collections.ArrayList
    foreach ($target in @($Targets)) { [void]$pending.Add($target) }
    $results = New-Object System.Collections.ArrayList
    $jobTimeoutSec = Resolve-JobTimeoutSec

    try {
    while ($pending.Count -gt 0 -or $jobs.Count -gt 0) {
        Receive-CompletedProbeJobs -Jobs $jobs -Results $results -OnlyFinished

        while ($pending.Count -gt 0 -and @($jobs | Where-Object { $_.Job.State -in @("NotStarted", "Running") }).Count -lt $Limit) {
            $activePaths = @($jobs | Where-Object { $_.Job.State -in @("NotStarted", "Running") } | ForEach-Object { [System.IO.Path]::GetFullPath($_.FilePath) })
            $nextIndex = -1
            for ($i = 0; $i -lt $pending.Count; $i++) {
                $candidatePath = [System.IO.Path]::GetFullPath([string]$pending[$i].Path)
                if ($candidatePath -notin $activePaths) { $nextIndex = $i; break }
            }
            if ($nextIndex -lt 0) { break }

            $target = $pending[$nextIndex]
            $pending.RemoveAt($nextIndex)
            $resultPath = Join-Path $TmpDir ("login-json-probe-{0}.json" -f ([System.Guid]::NewGuid().ToString("N")))
            Write-Host "  queued $($target.File) [$($target.CredentialIndex)]" -ForegroundColor DarkCyan
            $probeBypassToken = ([Guid]::NewGuid().ToString("N") + [Guid]::NewGuid().ToString("N"))
            [Environment]::SetEnvironmentVariable($InternalMutexTokenName, $probeBypassToken, [EnvironmentVariableTarget]::Process)
            try {
                if (-not (Test-IsPortableSingleLinkRegularFile -Path $scriptPath -Directory $Root)) { throw 'Unsafe probe script; NOT EXECUTED.' }
                $job = Start-Job -ScriptBlock {
                    param($ScriptPath, $CredentialPath, $CredentialIndex, $ProbeResultPath, $ClientVersion, $MutexToken, $PackageRoot)
                    $ErrorActionPreference = 'Stop'
                    $base = [IO.Path]::GetFullPath($PackageRoot).TrimEnd('\')
                    $code = [IO.Path]::GetFullPath($ScriptPath)
                    if (-not $code.Equals((Join-Path $base 'login-json.ps1'), [StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected probe script; NOT EXECUTED.' }
                    $cursor = $code
                    $leaf = $true
                    while ($cursor) {
                        $item = Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
                        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked probe path; NOT EXECUTED.' }
                        if ($leaf) {
                            $link = $item.PSObject.Properties['LinkType']
                            if ($item.PSIsContainer -or $null -eq $link -or $link.Value -eq 'HardLink' -or ([string]$item.Mode).Contains('l')) { throw 'Unsafe probe script; NOT EXECUTED.' }
                        } elseif (-not $item.PSIsContainer) { throw 'Invalid probe parent; NOT EXECUTED.' }
                        $leaf = $false
                        $next = [IO.Path]::GetDirectoryName($cursor.TrimEnd('\'))
                        if ($next -eq $cursor) { break }
                        $cursor = $next
                    }
                    Set-Location -LiteralPath $base
                    & $code -Mode Probe -CredentialPath $CredentialPath -CredentialIndex $CredentialIndex -ProbeResultPath $ProbeResultPath -ClientVersion $ClientVersion -SkipEnvFile -NoProxyPrompt -SkipPackageMutex -PackageMutexBypassToken $MutexToken -ThrottleLimit 1
                } -ArgumentList $scriptPath, $target.Path, $target.CredentialIndex, $resultPath, $ClientVersion, $probeBypassToken, $Root
            } finally {
                Remove-Item ("Env:" + $InternalMutexTokenName) -ErrorAction SilentlyContinue
            }
            $jobs.Add([pscustomobject]@{
                Job = $job
                FilePath = $target.Path
                ResultPath = $resultPath
                StartedAtUtc = (Get-Date).ToUniversalTime()
                TimeoutSec = $jobTimeoutSec
            }) | Out-Null
        }

        if ($jobs.Count -gt 0) {
            Start-Sleep -Milliseconds 300
        } elseif ($pending.Count -gt 0) {
            throw "credential scheduler could not start a pending job"
        }
    }

    return @($results | Sort-Object File)
    } finally {
        # Reclaim only jobs created by this invocation before the package lock is released.
        foreach ($owned in @($jobs)) {
            try { Stop-Job -Job $owned.Job -ErrorAction Stop } catch {}
            try { Remove-Job -Job $owned.Job -Force -ErrorAction Stop } catch {}
        }
    }
}

function Scan-LoginJson {
    param([switch]$SkipPrune)
    Clear-LoginJsonTempFiles
    $clientVersion = Get-CodexClientVersion
    $allFiles = @(Get-LoginCredentialFiles)
    $scanLimit = Resolve-MaxFiles
    $credentialLimit = Resolve-MaxCredentials
    if ($scanLimit -gt 0) {
        $files = @($allFiles | Select-Object -First $scanLimit)
    } else {
        $files = @($allFiles)
    }
    $results = @()
    if ($allFiles.Count -eq 0) {
        $report = Write-Report -Results @() -ClientVersion $clientVersion -TotalFiles 0 -ScanLimit $scanLimit
        [void](Write-ScanCache -Results @() -ClientVersion $clientVersion -ScannedFiles @() -ScanLimit $scanLimit -CredentialLimit $credentialLimit)
        Write-Host "No JSON files found in: $LoginDir" -ForegroundColor Yellow
        Write-Host "CSV: $report"
        return @()
    }
    if ($files.Count -eq 0) {
        $report = Write-Report -Results @() -ClientVersion $clientVersion -TotalFiles $allFiles.Count -ScanLimit $scanLimit
        [void](Write-ScanCache -Results @() -ClientVersion $clientVersion -ScannedFiles @() -ScanLimit $scanLimit -CredentialLimit $credentialLimit)
        Write-Host "MaxFiles is 0? Full scan is enabled; if this appears unexpectedly, check CODEX_LOGIN_JSON_MAX_FILES." -ForegroundColor Yellow
        Write-Host "CSV: $report"
        return @()
    }
    if ($scanLimit -gt 0 -and $files.Count -lt $allFiles.Count) {
        Write-Host "Scanning first $($files.Count) of $($allFiles.Count) login JSON file(s). Set CODEX_LOGIN_JSON_MAX_FILES=0 for all." -ForegroundColor Yellow
    }

    $targets = @()
    foreach ($file in $files) {
        $targets += @(Get-CredentialEntriesForFile -Path $file.FullName)
    }
    if ($credentialLimit -gt 0 -and $targets.Count -gt $credentialLimit) {
        Write-Host "Scanning first $credentialLimit of $($targets.Count) credential entries. Set CODEX_LOGIN_JSON_MAX_CREDENTIALS=0 for all." -ForegroundColor Yellow
        $targets = @($targets | Select-Object -First $credentialLimit)
    }

    $limit = Resolve-ThrottleLimit
    $proxyMode = Get-LoginJsonProxyMode
    $script:LoginJsonProgressTotal = @($targets).Count
    $script:LastPartialReportWriteUtc = [datetime]::MinValue
    $httpBackend = $env:CODEX_LOGIN_JSON_HTTP_BACKEND
    if ([string]::IsNullOrWhiteSpace($httpBackend)) { $httpBackend = "python" }
    $httpBackend = $httpBackend.Trim().ToLowerInvariant()
    $directParallelAllowed = ($httpBackend -eq "python") -or (Test-Truthy $env:CODEX_LOGIN_JSON_ALLOW_DIRECT_PARALLEL $false)
    $forceSequential = $Sequential -or $targets.Count -le 1 -or $limit -le 1 -or (($proxyMode -in @("auto", "direct")) -and -not $directParallelAllowed)
    if ($forceSequential) {
        if (-not $Sequential -and $targets.Count -gt 1 -and $limit -gt 1 -and $proxyMode -in @("auto", "direct")) {
            Write-Host "TUN/direct mode uses sequential checks to avoid background PowerShell TLS failures." -ForegroundColor Yellow
        }
        Write-Host "Checking $($targets.Count) credential entries from $($files.Count) login JSON file(s) sequentially..." -ForegroundColor Cyan
        foreach ($target in $targets) {
            Write-Host "  checking $($target.File) ..." -ForegroundColor DarkCyan
            # 每次重新读取同一容器文件，避免后一个刷新用扫描开始时的旧 RootJson 覆盖前一个刷新。
            $one = Test-CredentialFile -Path $target.Path -CredentialIndex $target.CredentialIndex -ClientVersion $clientVersion
            $results += $one
            Write-ScanResultProgress -Result $one -Done (@($results).Count) -Total $script:LoginJsonProgressTotal
            Save-PartialReport -Results @($results)
        }
    } else {
        Write-Host "Checking $($targets.Count) credential entries from $($files.Count) login JSON file(s) in parallel (throttle=$limit)..." -ForegroundColor Cyan
        $results = @(Invoke-ParallelCredentialChecks -Targets $targets -ClientVersion $clientVersion -Limit $limit)
    }
    $prunedCount = 0
    if (-not $SkipPrune) {
        $prunedCount = Prune-InvalidCredentialEntries -Results $results
    }
    if ($prunedCount -gt 0) {
        Write-Host "Credential indexes changed after pruning; rescanning once before writing cache and reports." -ForegroundColor Cyan
        return @(Scan-LoginJson -SkipPrune)
    }
    $reportPath = Write-Report -Results $results -ClientVersion $clientVersion -TotalFiles $allFiles.Count -ScanLimit $scanLimit
    $cachePath = Write-ScanCache -Results $results -ClientVersion $clientVersion -ScannedFiles $files -ScanLimit $scanLimit -CredentialLimit $credentialLimit
    $validCount = @($results | Where-Object { $_.Status -eq "VALID" }).Count
    $deletedCount = @($results | Where-Object { $_.Status -eq "INVALID_DELETED" }).Count
    $invalidKeptCount = @($results | Where-Object { $_.Status -eq "INVALID_KEPT" }).Count
    $keptErrorCount = @($results | Where-Object { $_.Status -eq "ERROR_KEPT" }).Count
    Write-Host "Valid: $validCount, Deleted invalid: $deletedCount, Invalid kept: $invalidKeptCount, Error kept: $keptErrorCount" -ForegroundColor Cyan
    Write-Host "CSV: $reportPath" -ForegroundColor Cyan
    Write-Host "Cache: $cachePath" -ForegroundColor Cyan
    Clear-LoginJsonTempFiles
    return $results
}

function Get-ResultCredentialIndex {
    param($Result)
    if ($null -ne $Result -and $Result.PSObject.Properties["CredentialIndex"]) {
        return [int]$Result.CredentialIndex
    }
    return -1
}

function Test-ResultHasModel {
    param($Result, [string]$Model)
    if ([string]::IsNullOrWhiteSpace($Model)) { return $true }
    foreach ($modelEntry in @($Result.Models)) {
        if ((Get-ModelSlug $modelEntry) -eq $Model) { return $true }
    }
    return $false
}

function Test-NoQuotaResetStillPending {
    param($Result)
    if ($null -eq $Result) { return $false }
    $quota = ""
    if ($Result.PSObject.Properties["Quota"]) { $quota = ([string]$Result.Quota).Trim().ToUpperInvariant() }
    if ($quota -ne "NO_QUOTA") { return $false }

    $resetText = ""
    if ($Result.PSObject.Properties["Reset"]) { $resetText = ([string]$Result.Reset).Trim() }
    if ([string]::IsNullOrWhiteSpace($resetText)) { return $false }

    $resetAt = [datetime]::MinValue
    $styles = [System.Globalization.DateTimeStyles]::AssumeUniversal -bor [System.Globalization.DateTimeStyles]::AdjustToUniversal
    if (-not [datetime]::TryParse($resetText, [System.Globalization.CultureInfo]::InvariantCulture, $styles, [ref]$resetAt)) {
        return $false
    }
    return ($resetAt.ToUniversalTime() -gt (Get-Date).ToUniversalTime())
}

function Set-ResultQuotaUnknown {
    param($Result, [string]$Reason)
    if ($null -eq $Result) { return }
    if ($Result.PSObject.Properties["Quota"]) {
        $Result.Quota = "UNKNOWN"
    } else {
        $Result | Add-Member -NotePropertyName "Quota" -NotePropertyValue "UNKNOWN" -Force
    }

    if (-not [string]::IsNullOrWhiteSpace($Reason)) {
        $message = ""
        if ($Result.PSObject.Properties["Message"]) { $message = [string]$Result.Message }
        if ($message -notmatch [regex]::Escape($Reason)) {
            $message = $(if ([string]::IsNullOrWhiteSpace($message)) { $Reason } else { "$message; $Reason" })
            if ($Result.PSObject.Properties["Message"]) {
                $Result.Message = $message
            } else {
                $Result | Add-Member -NotePropertyName "Message" -NotePropertyValue $message -Force
            }
        }
    }
}

function Get-RelativePathUnderRoot {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return "" }
    try {
        $fullPath = [System.IO.Path]::GetFullPath($Path)
        $fullRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd("\") + "\"
        if (-not $fullPath.StartsWith($fullRoot, [System.StringComparison]::OrdinalIgnoreCase)) { return "" }
        return $fullPath.Substring($fullRoot.Length)
    } catch {
        return ""
    }
}

function Write-AuthJson {
    param($Selection, [string]$Model)
    if ([string]::IsNullOrWhiteSpace($ResultPath)) {
        $ResultPath = Join-Path $TmpDir "login-json-selection.json"
    } elseif (-not (Test-IsUnderDirectory -Path $ResultPath -Directory $TmpDir)) {
        throw "ResultPath must be inside tmp."
    }
    if ((Test-Path -LiteralPath $ResultPath) -and -not (Test-IsPortableSingleLinkRegularFile -Path $ResultPath -Directory $TmpDir)) {
        throw 'ResultPath must be a single-link regular file.'
    }
    $transitionPath = Join-Path $HomeDir 'auth-transition.block'
    if (Test-Path -LiteralPath $transitionPath) {
        if (-not $SkipPackageMutex -or -not (Test-IsPortableSingleLinkRegularFile -Path $transitionPath -Directory $HomeDir)) {
            throw 'An unfinished auth transition must be recovered by the launcher first.'
        }
    }
    $cred = $null
    if ($Selection.PSObject.Properties["Credential"]) { $cred = $Selection.Credential }
    if ($null -eq $cred) {
        if (-not (Test-IsUnderDirectory -Path $Selection.Path -Directory $LoginDir)) {
            throw "Selected credential path is outside login_json."
        }
        $cred = Read-CredentialFile -Path $Selection.Path -CredentialIndex (Get-ResultCredentialIndex $Selection)
    }
    if ([string]::IsNullOrWhiteSpace($cred.AccountId)) {
        throw "Selected credential is missing account_id/chatgpt_account_id."
    }
    $idTokenForAuth = $cred.IdToken
    if ([string]::IsNullOrWhiteSpace($idTokenForAuth) -and -not [string]::IsNullOrWhiteSpace($cred.AccessToken) -and $cred.AccessToken.Contains(".")) {
        $idTokenForAuth = $cred.AccessToken
    }
    $auth = [ordered]@{
        auth_mode = "chatgpt"
        OPENAI_API_KEY = $null
        tokens = [ordered]@{
            id_token = $idTokenForAuth
            access_token = $cred.AccessToken
            refresh_token = $cred.RefreshToken
            account_id = $cred.AccountId
        }
        last_refresh = (Get-Date).ToUniversalTime().ToString("o")
    }
    $authPath = Join-Path $HomeDir "auth.json"
    if (-not (Test-Path -LiteralPath $transitionPath)) {
        Write-PortableNewUtf8File -Path $transitionPath -Text 'Auth transition not committed; do not recycle active credentials.'
    }
    Write-Utf8JsonFile -Path $authPath -InputObject $auth -Depth 16
    $result = [ordered]@{
        success = $true
        model = $Model
        account_id = $cred.AccountId
        email = $cred.Email
        plan = $cred.Plan
        credential_file = $Selection.File
        credential_path = $Selection.Path
        credential_index = (Get-ResultCredentialIndex $Selection)
        network_mode = $(if ($Selection.PSObject.Properties["Network"]) { [string]$Selection.Network } else { "" })
        auth_json = $authPath
    }
    Write-Utf8JsonFile -Path $ResultPath -InputObject $result -Depth 8
    if (-not $SkipPackageMutex) {
        # Standalone Select owns the whole transition; the runner commits its own
        # selection when it holds the package lock and passes the internal token.
        Write-Utf8JsonFile -Path (Join-Path $HomeDir 'auth-account-json.json') -InputObject $auth -Depth 16
        $modePath = Join-Path $HomeDir 'mode'
        $modeTemp = $modePath + '.tmp-' + [Guid]::NewGuid().ToString('N')
        $modeReplaceBackup = $modePath + '.bak-' + [Guid]::NewGuid().ToString('N')
        $modeTempOwned = $false
        try {
            Write-PortableNewUtf8File -Path $modeTemp -Text 'account_json'
            $modeTempOwned = $true
            if (-not (Test-IsPortableSingleLinkRegularFile -Path $modeTemp -Directory $HomeDir)) { throw 'Unsafe auth mode staging file.' }
            if (-not (Test-IsUnderDirectory -Path $modePath -Directory $HomeDir)) { throw 'Unsafe auth mode path.' }
            if (Test-Path -LiteralPath $modePath) {
                if (-not (Test-IsPortableSingleLinkRegularFile -Path $modePath -Directory $HomeDir)) { throw 'Unsafe auth mode destination.' }
                if (Test-Path -LiteralPath $modeReplaceBackup) { throw 'Unexpected auth mode replace-backup collision.' }
                [IO.File]::Replace($modeTemp, $modePath, $modeReplaceBackup, $true)
                $modeTempOwned = $false
                if (-not (Test-IsPortableSingleLinkRegularFile -Path $modeReplaceBackup -Directory $HomeDir)) { throw 'Unsafe auth mode replace backup.' }
                Remove-Item -LiteralPath $modeReplaceBackup -Force -ErrorAction Stop
            } else {
                [IO.File]::Move($modeTemp, $modePath)
                $modeTempOwned = $false
            }
        } finally {
            if ($modeTempOwned) { Remove-Item -LiteralPath $modeTemp -Force -ErrorAction SilentlyContinue }
        }
        $logoutBlock = Join-Path $HomeDir 'logout-account_json.block'
        if (Test-Path -LiteralPath $logoutBlock) {
            if (-not (Test-IsPortableSingleLinkRegularFile -Path $logoutBlock -Directory $HomeDir)) { throw 'Unsafe logout block after fresh login.' }
            Remove-Item -LiteralPath $logoutBlock -Force -ErrorAction Stop
        }
        if (-not (Test-IsPortableSingleLinkRegularFile -Path $transitionPath -Directory $HomeDir)) { throw 'Unsafe committed auth transition marker.' }
        Remove-Item -LiteralPath $transitionPath -Force -ErrorAction Stop
    }
    return $ResultPath
}

function Select-LoginJson {
    $clientVersion = Get-CodexClientVersion
    $cachedResults = Read-ScanCache -ClientVersion $clientVersion
    $usedCsvReportCache = $false
    if ($null -eq $cachedResults) {
        $cachedResults = Read-CsvReportCache
        if ($null -ne $cachedResults) { $usedCsvReportCache = $true }
    }
    if ($null -ne $cachedResults -and (Get-LoginJsonProxyMode) -eq "auto") {
        $cachedValid = @($cachedResults | Where-Object { $_.Status -eq "VALID" })
        $missingNetwork = @($cachedValid | Where-Object { -not $_.PSObject.Properties["Network"] -or [string]::IsNullOrWhiteSpace([string]$_.Network) }).Count
        if ($missingNetwork -gt 0) {
            Write-Host "Cached login_json result has no network mode; rescanning for auto TUN/proxy detection." -ForegroundColor Cyan
            $cachedResults = $null
            $usedCsvReportCache = $false
        }
    }
    if ($null -eq $cachedResults) {
        $results = Scan-LoginJson
    } else {
        $results = @($cachedResults)
        if ($usedCsvReportCache) {
            Write-Host "Using cached login_json CSV report. CSV has no model list, so only CODEX_MODEL is offered." -ForegroundColor Cyan
        } else {
            Write-Host "Using cached login_json scan: $ScanCachePath" -ForegroundColor Cyan
        }
    }
    $validWithModels = @($results | Where-Object { $_.Status -eq "VALID" -and @($_.Models).Count -gt 0 })
    $valid = @()
    $skippedNoQuota = 0
    $resetDueNoQuota = 0
    foreach ($result in $validWithModels) {
        $quota = ""
        if ($result.PSObject.Properties["Quota"]) { $quota = ([string]$result.Quota).Trim().ToUpperInvariant() }
        if ($quota -ne "NO_QUOTA") {
            $valid += $result
            continue
        }

        if (Test-NoQuotaResetStillPending $result) {
            $skippedNoQuota++
            continue
        }

        Set-ResultQuotaUnknown -Result $result -Reason "cached NO_QUOTA reset is due; recheck on use"
        $resetDueNoQuota++
        $valid += $result
    }
    if ($valid.Count -eq 0) {
        if ($validWithModels.Count -gt 0) {
            throw "No valid account with remaining quota was found in $LoginDir. See login_json_report.csv."
        }
        throw "No valid account with a usable model list was found in $LoginDir. See login_json_report.csv."
    }
    if ($skippedNoQuota -gt 0) {
        Write-Host "Skipped $skippedNoQuota account(s) with quota=NO_QUOTA before reset time." -ForegroundColor Yellow
    }
    if ($resetDueNoQuota -gt 0) {
        Write-Host "Returned $resetDueNoQuota cached NO_QUOTA account(s) whose reset time has passed." -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "Available accounts:" -ForegroundColor Cyan
    for ($i = 0; $i -lt $valid.Count; $i++) {
        $r = $valid[$i]
        $num = $i + 1
        Write-Host ("  {0}) {1}  plan={2}  quota={3}  models={4}  file={5}" -f $num, $r.Email, $r.Plan, $r.Quota, @($r.Models).Count, $r.File)
    }

    $accountIndex = 0
    while ($true) {
        $accountChoice = Read-Host "Select account (1-$($valid.Count), Enter=1)"
        if ([string]::IsNullOrWhiteSpace($accountChoice)) { $accountChoice = "1" }
        if ([int]::TryParse($accountChoice, [ref]$accountIndex) -and $accountIndex -ge 1 -and $accountIndex -le $valid.Count) {
            break
        }
        Write-Host "Invalid account selection. Enter 1-$($valid.Count), or press Enter for 1." -ForegroundColor Yellow
    }
    $selected = $valid[$accountIndex - 1]

    $models = @($selected.Models | Sort-Object { Get-ModelSlug $_ })
    $defaultModel = $env:CODEX_MODEL
    if ([string]::IsNullOrWhiteSpace($defaultModel) -or -not ($models | Where-Object { (Get-ModelSlug $_) -eq $defaultModel } | Select-Object -First 1)) {
        $defaultModel = Get-ModelSlug $models[0]
    }

    Write-Host ""
    Write-Host "Available models for $($selected.Email):" -ForegroundColor Cyan
    for ($i = 0; $i -lt $models.Count; $i++) {
        $slug = Get-ModelSlug $models[$i]
        $display = Get-StringProperty $models[$i] @("display_name")
        if ([string]::IsNullOrWhiteSpace($display)) { $display = $slug }
        $mark = ""
        if ($slug -eq $defaultModel) { $mark = " [default]" }
        Write-Host ("  {0}) {1} ({2}){3}" -f ($i + 1), $slug, $display, $mark)
    }

    $selectedModel = $defaultModel
    while ($true) {
        $modelChoice = Read-Host "Select model (1-$($models.Count), Enter=$defaultModel)"
        if ([string]::IsNullOrWhiteSpace($modelChoice)) {
            $selectedModel = $defaultModel
            break
        }
        $matchedModel = $models | Where-Object { (Get-ModelSlug $_) -eq $modelChoice } | Select-Object -First 1
        if ($null -ne $matchedModel) {
            $selectedModel = Get-ModelSlug $matchedModel
            break
        }
        $modelIndex = 0
        if (-not [int]::TryParse($modelChoice, [ref]$modelIndex) -or $modelIndex -lt 1 -or $modelIndex -gt $models.Count) {
            Write-Host "Invalid model selection. Enter 1-$($models.Count), a model slug, or press Enter for $defaultModel." -ForegroundColor Yellow
            continue
        }
        $selectedModel = Get-ModelSlug $models[$modelIndex - 1]
        break
    }

    # 只写入本次人工选择的账号。
    $path = Write-AuthJson -Selection $selected -Model $selectedModel
    Write-Host "Selected account: $($selected.Email)" -ForegroundColor Green
    Write-Host "Selected model  : $selectedModel" -ForegroundColor Green
    $authDisplayPath = Join-Path $HomeDir "auth.json"
    Write-Host "Auth JSON       : $authDisplayPath" -ForegroundColor Green
    return $path
}

$LoginJsonPackageMutex = $null
$LoginJsonPackageMutexHeld = $false
$LoginJsonPackageFileLock = $null
$LoginJsonOperationStarted = $false
$LoginJsonPrimaryError = $null
try {
if (-not $SkipPackageMutex) {
    # 命名 Mutex 使用规范化路径；同一物理包经 junction/路径别名访问时由独占文件锁兜底。
    $rootIdentity = [System.IO.Path]::GetFullPath($Root).TrimEnd("\").ToLowerInvariant()
    $rootIdentityBytes = [System.Text.Encoding]::UTF8.GetBytes($rootIdentity)
    $rootIdentityHash = [System.BitConverter]::ToString(([System.Security.Cryptography.SHA256]::Create()).ComputeHash($rootIdentityBytes)).Replace("-", "").Substring(0, 24)
    $LoginJsonPackageMutex = New-Object System.Threading.Mutex($false, "Global\CodexPortable-$rootIdentityHash")
    try {
        $LoginJsonPackageMutexHeld = $LoginJsonPackageMutex.WaitOne(0, $false)
    } catch [System.Threading.AbandonedMutexException] {
        $LoginJsonPackageMutexHeld = $true
    }
    if (-not $LoginJsonPackageMutexHeld) {
        $LoginJsonPackageMutex.Dispose()
        Write-Host "这个 Codex Portable 目录正在运行启动器或账号检查，本次账号操作已取消。" -ForegroundColor Red
        exit 2
    }

    $lockPath = Join-Path $Root ".codex-portable.instance.lock"
    if (-not (Test-IsUnderDirectory -Path $lockPath -Directory $Root)) {
        try { $LoginJsonPackageMutex.ReleaseMutex() } catch {}
        $LoginJsonPackageMutexHeld = $false
        $LoginJsonPackageMutex.Dispose()
        throw "Refusing package lock outside package or through reparse path: $lockPath"
    }
    if (Test-Path -LiteralPath $lockPath -PathType Leaf) {
        if (-not (Test-IsPortableSingleLinkRegularFile -Path $lockPath -Directory $Root)) {
            try { $LoginJsonPackageMutex.ReleaseMutex() } catch {}
            $LoginJsonPackageMutexHeld = $false
            $LoginJsonPackageMutex.Dispose()
            throw "Refusing hardlinked/reparse package lock file: $lockPath"
        }
    }
    try {
        $LoginJsonPackageFileLock = [System.IO.File]::Open(
            $lockPath,
            [System.IO.FileMode]::OpenOrCreate,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )
    } catch {
        try { $LoginJsonPackageMutex.ReleaseMutex() } catch {}
        $LoginJsonPackageMutexHeld = $false
        $LoginJsonPackageMutex.Dispose()
        Write-Host "这个 Codex Portable 目录已被另一个实例占用，或无法安全创建包级锁文件。本次账号操作已取消。" -ForegroundColor Red
        exit 2
    }
}

$loginJsonProxyModeOverride = [Environment]::GetEnvironmentVariable("CODEX_LOGIN_JSON_PROXY_MODE_OVERRIDE")
if (-not $SkipEnvFile) { Clear-StandaloneInheritedEnvironment }
Set-PortableEnvironment
if ($Mode -in @("Check", "Select")) {
    Clear-LoginJsonTempFiles
}
if (-not $SkipEnvFile) {
    $envFile = Join-Path $Root "env.ps1"
    if (Test-Path -LiteralPath $envFile -PathType Leaf) {
        if (-not (Test-IsPortableSingleLinkRegularFile -Path $envFile -Directory $Root)) {
            throw "Refusing env.ps1 that is outside package, reparse-backed, hardlinked, or not a regular file: $envFile"
        }
        . $envFile
    }
}
Set-PortableProcessPath
if (-not [string]::IsNullOrWhiteSpace($loginJsonProxyModeOverride)) {
    $env:CODEX_LOGIN_JSON_PROXY_MODE = $loginJsonProxyModeOverride.Trim()
}
if ([string]::IsNullOrWhiteSpace($env:CODEX_PROXY_PROTOCOL)) { $env:CODEX_PROXY_PROTOCOL = "socks5" }
if ([string]::IsNullOrWhiteSpace($env:CODEX_PROXY_HOST)) { $env:CODEX_PROXY_HOST = "127.0.0.1" }
if ([string]::IsNullOrWhiteSpace($env:CODEX_PROXY_PORT)) { $env:CODEX_PROXY_PORT = "10808" }
$loginJsonProxyMode = Get-LoginJsonProxyMode
if ($loginJsonProxyMode -eq "proxy") {
    $env:CODEX_PROXY_ENABLED = "true"
    $env:CODEX_PROXY_BYPASS_MODEL = "false"
} else {
    $env:CODEX_PROXY_ENABLED = "false"
}
if (-not $NoProxyPrompt -and [Environment]::UserInteractive) {
    Write-Host ""
    if ($loginJsonProxyMode -eq "direct") {
        Write-Host "Login JSON check mode: direct/TUN." -ForegroundColor Cyan
    } elseif ($loginJsonProxyMode -eq "proxy") {
        Write-Host "Login JSON check mode: proxy $($env:CODEX_PROXY_PROTOCOL)://$($env:CODEX_PROXY_HOST):$($env:CODEX_PROXY_PORT)" -ForegroundColor Cyan
    } else {
        Write-Host "Login JSON check mode: auto (direct/TUN first, proxy port last)." -ForegroundColor Cyan
    }
}
Set-ProxyEnvironment

$LoginJsonOperationStarted = $true
    if ($Mode -eq "Probe") {
        if ([string]::IsNullOrWhiteSpace($CredentialPath) -or [string]::IsNullOrWhiteSpace($ProbeResultPath)) {
            throw "Probe mode requires CredentialPath and ProbeResultPath."
        }
        if (-not (Test-IsUnderDirectory -Path $CredentialPath -Directory $LoginDir)) {
            throw "Probe credential path must be inside login_json."
        }
        if (-not (Test-IsUnderDirectory -Path $ProbeResultPath -Directory $TmpDir)) {
            throw "Probe result path must be inside tmp."
        }
        if ([string]::IsNullOrWhiteSpace($ClientVersion)) {
            $ClientVersion = Get-CodexClientVersion
        }
        $probeResult = Test-CredentialFile -Path $CredentialPath -CredentialIndex $CredentialIndex -ClientVersion $ClientVersion
        $record = ConvertTo-ResultRecord $probeResult
        Write-Utf8JsonFile -Path $ProbeResultPath -InputObject $record -Depth 64
        return
    }

    if ($Mode -eq "Use") {
        if ([string]::IsNullOrWhiteSpace($CredentialPath)) {
            throw "Use mode requires CredentialPath."
        }
        if (-not (Test-IsUnderDirectory -Path $CredentialPath -Directory $LoginDir)) {
            throw "Use credential path must be inside login_json."
        }
        if ([string]::IsNullOrWhiteSpace($AuthModel)) {
            $AuthModel = $env:CODEX_MODEL
        }
        if ([string]::IsNullOrWhiteSpace($AuthModel)) {
            throw "Use mode requires AuthModel or CODEX_MODEL."
        }
        $entries = @(Get-CredentialEntriesForFile -Path $CredentialPath)
        $entry = $null
        if ($CredentialIndex -ge 0) {
            $entry = $entries | Where-Object { $_.CredentialIndex -eq $CredentialIndex } | Select-Object -First 1
        } elseif ($entries.Count -eq 1) {
            $entry = $entries[0]
        }
        if ($null -eq $entry) {
            throw "Credential entry was not found."
        }
        $selection = [pscustomobject]@{
            File = $entry.File
            Path = $entry.Path
            CredentialIndex = $entry.CredentialIndex
            Credential = (Read-CredentialFile -Path $entry.Path -CredentialIndex $entry.CredentialIndex -Entry $entry)
        }
        [void](Write-AuthJson -Selection $selection -Model $AuthModel)
        return
    }

    if ($Mode -eq "Check") {
        [void](Scan-LoginJson)
        return
    }

    [void](Select-LoginJson)
} catch {
    $LoginJsonPrimaryError = $_
    throw
} finally {
    try {
        if ($LoginJsonOperationStarted -and $Mode -in @("Check", "Select")) {
            Clear-LoginJsonTempFiles -ExcludePaths @($ResultPath, $ProbeResultPath)
        }
    } catch {
        if ($null -eq $LoginJsonPrimaryError) { throw }
        Write-Warning 'Login temporary cleanup failed; primary failure preserved.'
    } finally {
    if ($null -ne $LoginJsonPackageFileLock) {
        try { $LoginJsonPackageFileLock.Dispose() } catch {}
        $LoginJsonPackageFileLock = $null
    }
    if ($LoginJsonPackageMutexHeld) {
        try { $LoginJsonPackageMutex.ReleaseMutex() } catch {}
    }
    if ($null -ne $LoginJsonPackageMutex) { try { $LoginJsonPackageMutex.Dispose() } catch {} }
    }
}
