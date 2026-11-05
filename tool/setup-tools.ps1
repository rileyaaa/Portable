# ============================================================
# Codex Portable - 工具 / Python 环境一键准备脚本
# 作用：用包内 Python/pip 维护固定运行依赖；只接受 wheel，不在本机编译。
# 用法：联网后，在 PowerShell 中运行本脚本。可反复运行（补装/重建）。
# 依赖源：tool\python-packages.in.txt；首次成功解析/安装后会生成含版本与分发 hash 的完整 python-packages.lock.txt。
# 后续默认 --require-hashes 严格按 lock 重装，避免版本/工件随时间漂移。
# ============================================================
$ErrorActionPreference = 'Stop'

$ToolDir = $PSScriptRoot
$Root = [IO.Path]::GetFullPath((Split-Path -Parent $ToolDir)).TrimEnd('\')

function Assert-SetupPathAncestors([string]$Path) {
    # Walk from volume root toward the leaf before probing any descendants.
    $chain = New-Object 'System.Collections.Generic.List[string]'
    $cursor = [IO.Path]::GetFullPath($Path)
    while (-not [string]::IsNullOrWhiteSpace($cursor)) {
        [void]$chain.Add($cursor)
        $parent = [IO.Path]::GetDirectoryName($cursor)
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
    for ($index = $chain.Count - 1; $index -ge 0; $index--) {
        $item = Get-Item -LiteralPath $chain[$index] -Force -ErrorAction SilentlyContinue
        if ($null -eq $item) { continue }
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Setup path contains a junction/symlink/reparse point.' }
        if ($index -gt 0 -and -not $item.PSIsContainer) { throw 'Setup path ancestor is not a directory.' }
    }
}

Assert-SetupPathAncestors $PSCommandPath
foreach ($marker in @('codex.exe','env.ps1')) {
    $markerPath = Join-Path $Root $marker
    Assert-SetupPathAncestors $markerPath
    if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) { throw 'Current tool directory is not a valid portable package.' }
}

# This PowerShell process may inherit poisoned SystemRoot/ComSpec variables.
# Reconstruct OS essentials from the Windows SpecialFolder, not the host env.
function Get-SetupTrustedWindowsRoot {
    $windows = [IO.Path]::GetFullPath([Environment]::GetFolderPath('Windows')).TrimEnd('\')
    if ($windows -notmatch '^[A-Za-z]:\\' -or $windows.Substring(2).Contains(':') -or
        -not [IO.File]::Exists((Join-Path $windows 'System32\cmd.exe'))) {
        throw 'Setup requires a real local Windows system directory.'
    }
    return $windows
}
$SetupWindowsRoot = Get-SetupTrustedWindowsRoot
$env:SystemRoot = $SetupWindowsRoot
$env:WINDIR = $SetupWindowsRoot
$env:SystemDrive = [IO.Path]::GetPathRoot($SetupWindowsRoot).TrimEnd('\')
$env:ComSpec = Join-Path $SetupWindowsRoot 'System32\cmd.exe'
$env:PATHEXT = '.COM;.EXE;.BAT;.CMD'

function Resolve-PortableSetupPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    if (-not ($full.Equals($Root,[StringComparison]::OrdinalIgnoreCase) -or $full.StartsWith($Root + '\',[StringComparison]::OrdinalIgnoreCase))) {
        throw "拒绝包外路径：$Path"
    }
    Assert-SetupPathAncestors $full
    return $full
}

function Assert-PortableSetupRegularFile([string]$Name,[string]$Path) {
    $full = Resolve-PortableSetupPath $Path
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { throw "$Name 不存在或不是普通文件：$full" }
    try {
        $item = Get-Item -LiteralPath $full -Force -ErrorAction Stop
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "$Name 是重解析点：$full" }
        $linkTypeProperty = $item.PSObject.Properties['LinkType']
        $linkType = if ($null -ne $linkTypeProperty) { [string]$linkTypeProperty.Value } else { '' }
        if ($linkType -eq 'HardLink' -or ([string]$item.Mode).Contains('l')) { throw "$Name 是 hardlink/link：$full" }
    } catch {
        throw "无法安全确认 $Name 的链接类型：$full；$($_.Exception.Message)"
    }
    return $full
}

# setup-tools modifies executable/importable package state.  Acquire the same package-wide
# mutex + exclusive lock file used by run-codex.ps1 so dependencies cannot be hot-replaced
# while a Codex instance or another maintenance operation is active.
$SetupRootIdentity = [IO.Path]::GetFullPath($Root).TrimEnd('\').ToLowerInvariant()
$SetupRootIdentityBytes = [Text.Encoding]::UTF8.GetBytes($SetupRootIdentity)
$SetupRootIdentityHash = [BitConverter]::ToString(([Security.Cryptography.SHA256]::Create()).ComputeHash($SetupRootIdentityBytes)).Replace('-','').Substring(0,24)
$SetupMutex = $null
$SetupMutexHeld = $false
$SetupFileLock = $null
try {
$SetupMutex = New-Object Threading.Mutex($false, "Global\CodexPortable-$SetupRootIdentityHash")
try { $SetupMutexHeld = $SetupMutex.WaitOne(0,$false) } catch [Threading.AbandonedMutexException] { $SetupMutexHeld = $true }
if (-not $SetupMutexHeld) {
    $SetupMutex.Dispose()
    throw '当前 Codex Portable 目录正在运行或维护；setup-tools 已拒绝并发修改。'
}
$SetupFileLock = $null
$SetupLockPath = Resolve-PortableSetupPath (Join-Path $Root '.codex-portable.instance.lock')
if (Test-Path -LiteralPath $SetupLockPath -PathType Leaf) {
    [void](Assert-PortableSetupRegularFile 'package instance lock' $SetupLockPath)
}
try {
    $SetupFileLock = [IO.File]::Open($SetupLockPath,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
} catch {
    try { if ($SetupMutexHeld) { $SetupMutex.ReleaseMutex() } } catch {}
    $SetupMutexHeld = $false
    $SetupMutex.Dispose()
    throw '无法取得 Codex Portable 包级独占文件锁；可能仍有实例运行。'
}

$Bin     = Join-Path $ToolDir 'bin'
$PyDir   = Join-Path $ToolDir 'python'
$PyExe   = Join-Path $PyDir 'python.exe'
$Site    = Join-Path $PyDir 'Lib\site-packages'
$CacheDir = Join-Path $Root 'cache'
$PortableHome = Join-Path $Root 'home-runtime'
$PortableAppData = Join-Path $Root 'appdata'
$PortableLocalAppData = Join-Path $Root 'localappdata'
$PortableProgramData = Join-Path $Root 'programdata'
$PortableTmp = Join-Path $Root 'tmp'
$RequirementsIn = Join-Path $ToolDir 'python-packages.in.txt'
$RequirementsLock = Join-Path $ToolDir 'python-packages.lock.txt'
$RefreshCliShims = Join-Path $ToolDir 'refresh-python-cli-shims.py'
$LockHelper = Join-Path $ToolDir 'python-lock.py'
# Direct versions are pinned in the input; the report locks the complete wheel
# closure by SHA-256. Source builds and implicit optional bundles are excluded.

# 便携环境：缓存与解释器全部指向包内，绝不写出当前 Codex 包
$env:HOME = $PortableHome
$env:USERPROFILE = $PortableHome
$portableHomeRoot = [IO.Path]::GetPathRoot([IO.Path]::GetFullPath($PortableHome))
if ($portableHomeRoot -match '^[A-Za-z]:\\$') {
    $env:HOMEDRIVE = $portableHomeRoot.Substring(0, 2)
    $env:HOMEPATH = ([IO.Path]::GetFullPath($PortableHome)).Substring(2)
} else {
    Remove-Item Env:HOMEDRIVE -ErrorAction SilentlyContinue
    Remove-Item Env:HOMEPATH -ErrorAction SilentlyContinue
}
$env:APPDATA = $PortableAppData
$env:LOCALAPPDATA = $PortableLocalAppData
$env:PROGRAMDATA = $PortableProgramData
$env:ALLUSERSPROFILE = $PortableProgramData
$env:TEMP = $PortableTmp
$env:TMP = $PortableTmp
$env:TMPDIR = $PortableTmp
$env:XDG_CACHE_HOME = $CacheDir
$env:XDG_CONFIG_HOME = $PortableAppData
$env:XDG_DATA_HOME = $PortableLocalAppData
$env:XDG_STATE_HOME = Join-Path $PortableLocalAppData 'state'
$psModuleCacheDir = Join-Path $PortableLocalAppData 'Microsoft\Windows\PowerShell'
$env:PSModuleAnalysisCachePath = Join-Path $psModuleCacheDir 'ModuleAnalysisCache'
$portablePsModules = Resolve-PortableSetupPath (Join-Path $CacheDir 'powershell\modules')
$env:PSModulePath = $portablePsModules + ';' + (Join-Path $PSHOME 'Modules')
$env:PIP_CACHE_DIR = Join-Path $CacheDir 'pip'
$env:PYTHONUSERBASE = Join-Path $CacheDir 'python-userbase'
$env:PYTHONPYCACHEPREFIX = Join-Path $CacheDir 'pycache'
$env:NPM_CONFIG_CACHE = Join-Path $CacheDir 'npm'
$env:NPM_CONFIG_PREFIX = Join-Path $CacheDir 'npm-prefix'
$env:NPM_CONFIG_GLOBALCONFIG = Join-Path $CacheDir 'npm\global.npmrc'
$env:NPM_CONFIG_USERCONFIG = Join-Path $PortableHome '.npmrc'
$env:NODE_REPL_HISTORY = Join-Path $PortableHome '.node_repl_history'
$env:POWERSHELL_TELEMETRY_OPTOUT = '1'
$env:CODEX_INSTALL_DIR = $Root
$env:CODEX_PYTHON = $PyExe
$SetupScrubNames = @(
    # 凭证/令牌：setup-tools 只负责公开依赖安装，不应继承宿主秘密。确有需要时请在脚本内显式配置包内专用值。
    'OPENAI_API_KEY','OPENAI_ORG_ID','OPENAI_PROJECT_ID','OPENAI_BASE_URL','CODEX_API_KEY',
    'ANTHROPIC_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','GOOGLE_APPLICATION_CREDENTIALS',
    'AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','AWS_SESSION_TOKEN','AWS_SECURITY_TOKEN','AWS_WEB_IDENTITY_TOKEN_FILE',
    'AZURE_CLIENT_ID','AZURE_CLIENT_SECRET','AZURE_TENANT_ID','AZURE_FEDERATED_TOKEN_FILE',
    'GITHUB_TOKEN','GH_TOKEN','NPM_TOKEN','NODE_AUTH_TOKEN','PYPI_TOKEN','TWINE_PASSWORD',
    'HF_TOKEN','HUGGINGFACEHUB_API_TOKEN','CLOUDFLARE_API_TOKEN',
    # 包管理器 / 解释器 / 编译器注入。
    'PIP_CONFIG_FILE','PIP_INDEX_URL','PIP_EXTRA_INDEX_URL','PIP_TRUSTED_HOST','PIP_CERT','PIP_CLIENT_CERT',
    'UV_INDEX_URL','UV_DEFAULT_INDEX','UV_EXTRA_INDEX_URL','UV_INDEX','UV_FIND_LINKS','UV_NO_INDEX',
    'NPM_CONFIG_REGISTRY','NPM_CONFIG_SCRIPT_SHELL','NPM_CONFIG_NODE_OPTIONS','NPM_CONFIG_HTTPS_PROXY','NPM_CONFIG_PROXY',
    'NPM_CONFIG_CAFILE','NPM_CONFIG_CERT','NPM_CONFIG_KEY',
    'PYTHONPATH','PYTHONHOME','PYTHONSTARTUP','PYTHONINSPECT','PYTHONWARNINGS','PYTHONBREAKPOINT',
    'NODE_OPTIONS','NODE_PATH','NODE_EXTRA_CA_CERTS','JAVA_TOOL_OPTIONS','_JAVA_OPTIONS',
    'RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS',
    'GIT_ASKPASS','SSH_ASKPASS','GIT_SSH','GIT_SSH_COMMAND','GIT_CONFIG_GLOBAL','GIT_CONFIG_SYSTEM','GIT_CONFIG_COUNT',
    'SSH_AUTH_SOCK','SSH_AGENT_PID','GPG_AGENT_INFO','VIRTUAL_ENV','CONDA_PREFIX','CONDA_DEFAULT_ENV','CONDA_PROMPT_MODIFIER',
    'BASH_ENV','ENV','CDPATH','RUBYOPT','RUBYLIB','PERL5OPT','PERL5LIB','KUBECONFIG','DOCKER_HOST','DOCKER_CONTEXT',
    # TLS/代理也必须由便携包显式决定，不能静默继承宿主 CA 或代理。
    'SSL_CERT_FILE','SSL_CERT_DIR','REQUESTS_CA_BUNDLE','CURL_CA_BUNDLE',
    'HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy'
)
foreach ($name in $SetupScrubNames) { Remove-Item ("Env:" + $name) -ErrorAction SilentlyContinue }
# 补捉未显式列出的常见宿主秘密变量；包内 setup 不需要任何继承凭证。
Get-ChildItem Env: | Where-Object {
    $_.Name -match '^(?i:GIT_)' -or
    $_.Name -match '(?i)(^|_)(API_?KEY|ACCESS_?TOKEN|AUTH_?TOKEN|SECRET|PASSWORD|CREDENTIALS?)($|_)'
} | ForEach-Object { Remove-Item ("Env:" + $_.Name) -ErrorAction SilentlyContinue }
$env:GIT_CONFIG_NOSYSTEM = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONNOUSERSITE = '1'
# pip --isolated alone still loads system config; os.devnull disables all files.
$env:PIP_CONFIG_FILE = 'nul'
$systemPaths = @(
    (Join-Path $SetupWindowsRoot 'System32'),
    $SetupWindowsRoot,
    (Join-Path $SetupWindowsRoot 'System32\WindowsPowerShell\v1.0'),
    (Join-Path $SetupWindowsRoot 'System32\Wbem')
)
$portablePaths = @(
    (Resolve-PortableSetupPath $Bin),
    (Resolve-PortableSetupPath $PyDir)
)
# 安装器必须可重复且不依赖宿主 PATH；只使用包内 python/pip + Windows 基础系统目录。
$env:PATH = (($portablePaths + $systemPaths) |
    Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique) -join ';'


function ConvertTo-SetupWindowsCommandLineArgument([string]$Argument) {
    if ([string]::IsNullOrEmpty($Argument)) { return '""' }
    if ($Argument -notmatch '[\s"]') { return $Argument }
    $builder = New-Object System.Text.StringBuilder
    [void]$builder.Append('"')
    $backslashes = 0
    foreach ($ch in $Argument.ToCharArray()) {
        if ($ch -eq '\') { $backslashes++; continue }
        if ($ch -eq '"') {
            if ($backslashes -gt 0) { [void]$builder.Append('\' * ($backslashes * 2)) }
            [void]$builder.Append('\"'); $backslashes = 0; continue
        }
        if ($backslashes -gt 0) { [void]$builder.Append('\' * $backslashes); $backslashes = 0 }
        [void]$builder.Append($ch)
    }
    if ($backslashes -gt 0) { [void]$builder.Append('\' * ($backslashes * 2)) }
    [void]$builder.Append('"')
    return $builder.ToString()
}

function Set-SetupProcessEnvironmentValue {
    param([System.Diagnostics.ProcessStartInfo]$ProcessStartInfo,[string]$Name,[string]$Value)
    if ($null -eq $Value -or [string]::IsNullOrWhiteSpace($Name)) { return }
    try { $ProcessStartInfo.EnvironmentVariables.Set_Item($Name,$Value) } catch {
        try { $ProcessStartInfo.Environment[$Name] = $Value } catch {}
    }
}

function Set-SetupChildPortableEnvironment([System.Diagnostics.ProcessStartInfo]$ProcessStartInfo) {
    # Package installers/import tests can execute third-party code. Never pass arbitrary
    # host variables (including unusually named secrets) into those children.
    try { $ProcessStartInfo.EnvironmentVariables.Clear() } catch { try { $ProcessStartInfo.Environment.Clear() } catch {} }
    # Defend the child even if another function changes the process variables.
    $env:SystemRoot = $SetupWindowsRoot
    $env:WINDIR = $SetupWindowsRoot
    $env:SystemDrive = [IO.Path]::GetPathRoot($SetupWindowsRoot).TrimEnd('\')
    $env:ComSpec = Join-Path $SetupWindowsRoot 'System32\cmd.exe'
    $env:PATHEXT = '.COM;.EXE;.BAT;.CMD'
    foreach ($name in @('SystemRoot','WINDIR','SystemDrive','ComSpec','PATHEXT','OS','PROCESSOR_ARCHITECTURE','PROCESSOR_IDENTIFIER','NUMBER_OF_PROCESSORS','USERNAME','COMPUTERNAME')) {
        Set-SetupProcessEnvironmentValue $ProcessStartInfo $name ([Environment]::GetEnvironmentVariable($name))
    }
    foreach ($name in @(
        'PATH','HOME','USERPROFILE','HOMEDRIVE','HOMEPATH','APPDATA','LOCALAPPDATA','PROGRAMDATA','ALLUSERSPROFILE',
        'TEMP','TMP','TMPDIR','XDG_CACHE_HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_STATE_HOME',
        'PSModuleAnalysisCachePath','PSModulePath','POWERSHELL_TELEMETRY_OPTOUT',
        'PIP_CONFIG_FILE','PIP_CACHE_DIR','PYTHONUSERBASE','PYTHONPYCACHEPREFIX','PYTHONDONTWRITEBYTECODE','PYTHONNOUSERSITE',
        'NPM_CONFIG_CACHE','NPM_CONFIG_PREFIX','NPM_CONFIG_GLOBALCONFIG','NPM_CONFIG_USERCONFIG','NODE_REPL_HISTORY',
        'CODEX_INSTALL_DIR','CODEX_PYTHON','GIT_CONFIG_NOSYSTEM'
    )) {
        Set-SetupProcessEnvironmentValue $ProcessStartInfo $name ([Environment]::GetEnvironmentVariable($name))
    }
}

function Assert-SetupInstallTree([string]$Path) {
    $pending = New-Object 'System.Collections.Generic.Stack[string]'
    $pending.Push((Resolve-PortableSetupPath $Path))
    while ($pending.Count -gt 0) {
        $dir = Resolve-PortableSetupPath $pending.Pop()
        foreach ($entry in @(Get-ChildItem -LiteralPath $dir -Force -ErrorAction Stop)) {
            [void](Resolve-PortableSetupPath $entry.FullName)
            if ($entry.PSIsContainer) { $pending.Push($entry.FullName) }
            else { [void](Assert-PortableSetupRegularFile 'installed Python file' $entry.FullName) }
        }
    }
}

function Get-SetupPipArguments {
    param([ValidateSet('Resolve','Install')][string]$Action,[string]$Requirements,[string]$Report='')
    $arguments = @('-s','-B','-m','pip','--isolated','--disable-pip-version-check','--no-input',
        '--cache-dir',$env:PIP_CACHE_DIR,'install','--index-url','https://pypi.org/simple',
        '--only-binary=:all:','--no-compile','--target',$Site,'--requirement',$Requirements)
    if ($Action -eq 'Resolve') {
        if ([string]::IsNullOrWhiteSpace($Report)) { throw 'A report path is required for wheel resolution.' }
        $arguments += @('--dry-run','--ignore-installed','--report',$Report)
    } else {
        $arguments += @('--require-hashes','--upgrade')
    }
    return $arguments
}

function Invoke-SetupPortableChild {
    param([string]$Executable,[object[]]$Arguments=@())
    $exe = Assert-PortableSetupRegularFile 'portable child executable' $Executable
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $exe
    $psi.WorkingDirectory = $Root
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $false
    $psi.Arguments = (@($Arguments) | ForEach-Object { ConvertTo-SetupWindowsCommandLineArgument ([string]$_) }) -join ' '
    Set-SetupChildPortableEnvironment $psi
    $supervisor = Assert-PortableSetupRegularFile 'process supervisor' (Join-Path $Root 'tool\portable-process.ps1')
    . $supervisor
    return (Invoke-PortableProcess -StartInfo $psi -PackageRoot $Root -TimeoutMs 1800000).ExitCode
}

function Invoke-SetupPortableChildCapture {
    param([string]$Executable,[object[]]$Arguments=@())
    $exe = Assert-PortableSetupRegularFile 'portable child executable' $Executable
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $exe
    $psi.WorkingDirectory = $Root
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.Arguments = (@($Arguments) | ForEach-Object { ConvertTo-SetupWindowsCommandLineArgument ([string]$_) }) -join ' '
    Set-SetupChildPortableEnvironment $psi
    $psi.RedirectStandardInput = $true
    $supervisor = Assert-PortableSetupRegularFile 'process supervisor' (Join-Path $Root 'tool\portable-process.ps1')
    . $supervisor
    return Invoke-PortableProcess -StartInfo $psi -PackageRoot $Root -TimeoutMs 60000
}

function Write-SetupUtf8Atomic {
    param([string]$Path,[string]$Text)
    $dest = Resolve-PortableSetupPath $Path
    $parent = Resolve-PortableSetupPath (Split-Path -Parent $dest)
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    [void](Resolve-PortableSetupPath $parent)
    $temp = Resolve-PortableSetupPath (Join-Path $parent ('.setup-write-' + [Guid]::NewGuid().ToString('N') + '.tmp'))
    $backup = Resolve-PortableSetupPath (Join-Path $parent ('.setup-backup-' + [Guid]::NewGuid().ToString('N') + '.tmp'))
    if (Test-Path -LiteralPath $backup) { throw 'Recovery path already exists.' }
    $stream = $null; $temporaryOwned = $false; $committed = $false
    try {
        $bytes = (New-Object Text.UTF8Encoding($false)).GetBytes($Text)
        $stream = New-Object IO.FileStream($temp,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        $temporaryOwned = $true
        $stream.Write($bytes,0,$bytes.Length)
        $stream.Flush($true)
        $stream.Dispose()
        $stream = $null

        [void](Assert-PortableSetupRegularFile 'atomic staging file' $temp)
        [void](Resolve-PortableSetupPath $dest)
        if (Test-Path -LiteralPath $backup) { throw 'Recovery path appeared during staging.' }
        if (Test-Path -LiteralPath $dest -PathType Leaf) {
            [void](Assert-PortableSetupRegularFile 'existing atomic destination' $dest)
            [IO.File]::Replace($temp,$dest,$backup,$true)
        } elseif (Test-Path -LiteralPath $dest) {
            throw "atomic destination exists but is not a regular file: $dest"
        } else {
            [IO.File]::Move($temp,$dest)
        }
        $committed = $true
    } finally {
        if ($null -ne $stream) { try { $stream.Dispose() } catch {} }
        if ($temporaryOwned) { Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue }
        if ($committed) { Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue }
        elseif (Test-Path -LiteralPath $backup) { Write-Warning 'Atomic replacement failed; recovery backup retained.' }
    }
}

# Node 官方附带的 install_tools.bat 会安装 Chocolatey / 系统 Python / VS Build Tools。
# 终版包不携带它；若它再次出现，setup 直接 fail-closed，不在检查/安装过程中偷偷修改包体。
$UnsafeNodeInstaller = Resolve-PortableSetupPath (Join-Path $ToolDir 'node\install_tools.bat')
if (Test-Path -LiteralPath $UnsafeNodeInstaller -PathType Leaf) {
    throw "检测到不允许的 Node 系统安装入口：tool\node\install_tools.bat。请恢复干净终版包后再运行 setup-tools。"
}

try {
    [void](Assert-PortableSetupRegularFile 'portable python' $PyExe)
    [void](Assert-PortableSetupRegularFile 'bundled pip' (Join-Path $Site 'pip\__main__.py'))
    [void](Assert-PortableSetupRegularFile 'dependency lock helper' $LockHelper)
    [void](Assert-PortableSetupRegularFile 'Python CLI shim refresher' $RefreshCliShims)
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

# 直接依赖清单独立保存；不要让 setup 每次自动追随 PyPI 的未来新版本。
$RequirementsIn = Resolve-PortableSetupPath $RequirementsIn
$RequirementsLock = Resolve-PortableSetupPath $RequirementsLock
try { [void](Assert-PortableSetupRegularFile 'Python dependency manifest' $RequirementsIn) } catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
$requirementsInputText = [IO.File]::ReadAllText($RequirementsIn)
if ([string]::IsNullOrWhiteSpace(($requirementsInputText -replace '(?m)^\s*#.*$','').Trim())) {
    Write-Host "Python 依赖清单为空：$RequirementsIn" -ForegroundColor Red
    exit 1
}

$Site = Resolve-PortableSetupPath $Site
$PyExe = Resolve-PortableSetupPath $PyExe
New-Item -ItemType Directory -Force -Path $Site | Out-Null
foreach ($dir in @($PortableHome, $PortableAppData, $PortableLocalAppData, $PortableProgramData, $PortableTmp, $psModuleCacheDir, $portablePsModules, $env:PIP_CACHE_DIR, $env:PYTHONUSERBASE, $env:PYTHONPYCACHEPREFIX, $env:NPM_CONFIG_CACHE, $env:NPM_CONFIG_PREFIX)) {
    $safeDir = Resolve-PortableSetupPath $dir
    New-Item -ItemType Directory -Force -Path $safeDir | Out-Null
}

Assert-SetupInstallTree $PyDir
$inputCode = Invoke-SetupPortableChild -Executable $PyExe -Arguments @('-s','-B',$LockHelper,'validate-input','--requirements',$RequirementsIn)
if ($inputCode -ne 0) { throw 'Python input must contain reviewed exact version pins only.' }
$runtimeCode = Invoke-SetupPortableChild -Executable $PyExe -Arguments @('-s','-B',$LockHelper,'validate-runtime','--requirements',$RequirementsIn)
if ($runtimeCode -ne 0) { throw 'Fixed runtime repair refused: use controlled maintenance for version changes, extra packages or custom launchers. No pip installation was started.' }

$hasLock = $false
if (Test-Path -LiteralPath $RequirementsLock -PathType Leaf) {
    try {
        [void](Assert-PortableSetupRegularFile 'Python dependency lock' $RequirementsLock)
        $hasLock = (Get-Item -LiteralPath $RequirementsLock -Force -ErrorAction Stop).Length -gt 0
    } catch {
        Write-Host $_.Exception.Message -ForegroundColor Red
        exit 1
    }
}
# Both report and lock candidates are private to this invocation. Existing lock
# input hashes must match the current manifest; edits never silently reuse stale
# dependency selections. Keep a previous lock until replacement is validated.
$LockCandidate = $null
$ReportCandidate = $null
$LockForInstall = $RequirementsLock
try {
    if ($hasLock) {
        $checkCode = Invoke-SetupPortableChild -Executable $PyExe -Arguments @('-s','-B',$LockHelper,'validate','--lock',$RequirementsLock,'--requirements',$RequirementsIn)
        if ($checkCode -ne 0) { throw 'Python lock does not match the current pinned input; deliberately regenerate it before installing.' }
        Write-Host "使用现有 hash lock 安装 Python 运行包到 $Site ..." -ForegroundColor Cyan
    } else {
        $LockCandidate = Resolve-PortableSetupPath (Join-Path $PortableTmp ('python-lock-' + [Guid]::NewGuid().ToString('N') + '.txt'))
        $ReportCandidate = Resolve-PortableSetupPath (Join-Path $PortableTmp ('python-report-' + [Guid]::NewGuid().ToString('N') + '.json'))
        if ((Test-Path -LiteralPath $LockCandidate) -or (Test-Path -LiteralPath $ReportCandidate)) { throw 'Setup staging path already exists.' }
        Write-Host '解析固定运行依赖并锁定 wheel 摘要；不下载源码构建依赖。' -ForegroundColor Cyan
        $reportArgs = Get-SetupPipArguments -Action Resolve -Requirements $RequirementsIn -Report $ReportCandidate
        $reportCode = Invoke-SetupPortableChild -Executable $PyExe -Arguments $reportArgs
        if ($reportCode -ne 0) { throw "Python wheel resolution failed (exit $reportCode); no lock published." }
        [void](Assert-PortableSetupRegularFile 'pip wheel report' $ReportCandidate)
        $buildCode = Invoke-SetupPortableChild -Executable $PyExe -Arguments @('-s','-B',$LockHelper,'build','--report',$ReportCandidate,'--requirements',$RequirementsIn,'--output',$LockCandidate)
        if ($buildCode -ne 0) { throw 'Python wheel report failed source/hash validation; no lock published.' }
        [void](Assert-PortableSetupRegularFile 'generated dependency lock' $LockCandidate)
        $LockForInstall = $LockCandidate
    }

    $pipArgs = Get-SetupPipArguments -Action Install -Requirements $LockForInstall
    $pipCode = Invoke-SetupPortableChild -Executable $PyExe -Arguments $pipArgs
    if ($pipCode -ne 0) { throw "Python wheel installation failed (exit $pipCode); candidate lock not published." }
} catch {
    if ($null -ne $LockCandidate -and (Test-Path -LiteralPath $LockCandidate)) { Remove-Item -LiteralPath $LockCandidate -Force }
    throw
} finally {
    if ($null -ne $ReportCandidate -and (Test-Path -LiteralPath $ReportCandidate)) { Remove-Item -LiteralPath $ReportCandidate -Force }
}

Write-Host "刷新可移动 Python CLI shims ..." -ForegroundColor Cyan
$RefreshCliShims = Assert-PortableSetupRegularFile 'refresh shim code immediately before execution' $RefreshCliShims
$shimCode = Invoke-SetupPortableChild -Executable $PyExe -Arguments @($RefreshCliShims)
if ($shimCode -ne 0) {
    Write-Host "Python CLI shim 刷新失败，退出码 $shimCode" -ForegroundColor Red
    exit $shimCode
}

Write-Host "验证导入 ..." -ForegroundColor Cyan
$importCode = "import pip, requests, httpx, bs4, lxml.etree, pandas, numpy, openpyxl, dateutil, six, yaml, rich, docx, pptx, PIL, xlsxwriter, typing_extensions, socks, defusedxml, pymupdf, pymupdf4llm, tabulate, packaging; print('runtime imports OK')"
$code = Invoke-SetupPortableChild -Executable $PyExe -Arguments @('-c',$importCode)

Write-Host ""
if ($code -eq 0) {
    if ($null -ne $LockCandidate) {
        $candidateText = [IO.File]::ReadAllText((Assert-PortableSetupRegularFile 'verified dependency lock' $LockCandidate))
        Write-SetupUtf8Atomic -Path $RequirementsLock -Text $candidateText
    }
    Write-Host "完成：Python 运行依赖已就绪，全部位于 tool\python；未执行源码编译。" -ForegroundColor Green
} else {
    Write-Host "导入验证未通过（退出码 $code），请查看上面的报错。" -ForegroundColor Yellow
}
} finally {
if ($null -ne $LockCandidate -and (Test-Path -LiteralPath $LockCandidate)) { Remove-Item -LiteralPath $LockCandidate -Force -ErrorAction SilentlyContinue }
if ($null -ne $SetupFileLock) { try { $SetupFileLock.Dispose() } catch {}; $SetupFileLock = $null }
if ($SetupMutexHeld) { try { $SetupMutex.ReleaseMutex() } catch {}; $SetupMutexHeld = $false }
if ($null -ne $SetupMutex) { try { $SetupMutex.Dispose() } catch {} }
}
exit $code
