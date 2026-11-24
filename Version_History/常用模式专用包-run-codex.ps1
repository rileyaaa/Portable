# ============================================================
# Codex Portable 启动脚本
#
# 目标：
#   1. 不安装、不注册、不写系统 PATH。
#   2. Codex 自身数据固定在当前目录下。
#   3. 子进程常见缓存目录尽量固定在当前目录下。
#   4. 默认工作目录固定为 .\work。
#   5. 普通 workspace-write 默认只开放 work/tmp；可执行/运行时缓存改用每次启动的 tmp 会话目录。
#      维护模式才显式开放整个便携包。包外写入仍由 Codex 权限策略决定。
#
# 日常使用：
#   双击 启动Codex.bat
#
# 命令行使用（严格便携推荐仍从 BAT 进入，以便在 PowerShell 启动前重定向环境）：
#   .\启动Codex.bat
#   .\启动Codex.bat exec "检查当前项目"
# 直接 powershell -File .\run-codex.ps1 虽能运行，但 PowerShell 启动阶段可能先使用宿主用户缓存。
# ============================================================

$ErrorActionPreference = "Stop"
$PortableMaintenanceEntryAuthorized = ([Environment]::GetEnvironmentVariable("CODEX_PORTABLE_MAINTENANCE_LAUNCHER") -eq "1")
Remove-Item Env:CODEX_PORTABLE_MAINTENANCE_LAUNCHER -ErrorAction SilentlyContinue
$LauncherDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-CodexPortableRoot {
    param([string]$StartDirectory)
    $current = [System.IO.Path]::GetFullPath($StartDirectory).TrimEnd("\")
    for ($depth = 0; $depth -lt 6; $depth++) {
        $codexExe = Join-Path $current "codex.exe"
        $rootEnv = Join-Path $current "env.ps1"
        if ((Test-Path -LiteralPath $codexExe -PathType Leaf) -and (Test-Path -LiteralPath $rootEnv -PathType Leaf)) {
            return $current
        }
        $parent = Split-Path -Parent $current
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $current) { break }
        $current = $parent
    }
    throw "无法从启动脚本位置定位 Codex Portable 根目录：$StartDirectory"
}

function Get-CodexBrowserLoginFlow {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return 'device_auth' }
    $flow = $Value.Trim().ToLowerInvariant()
    if ($flow -notin @('device_auth', 'system_browser')) {
        throw 'CODEX_BROWSER_LOGIN_FLOW 只支持 device_auth / system_browser。'
    }
    return $flow
}

function Invoke-CodexOfficialAccountLogin {
    param([string]$Flow)
    $flow = Get-CodexBrowserLoginFlow -Value $Flow
    if ($flow -eq 'system_browser') {
        Write-Host '已明确启用 system_browser：将打开系统默认浏览器，会读写宿主浏览器用户数据。' -ForegroundColor Yellow
        $loginArgs = @('login')
    } else {
        Write-Host '正在启动 Codex 官方设备码登录，请按终端提示在你选择的设备/浏览器完成授权。' -ForegroundColor Cyan
        Write-Host '账号须启用设备码登录；本包不会自动打开浏览器，失败也不会回退到系统浏览器。' -ForegroundColor Yellow
        $loginArgs = @('login', '--device-auth')
    }
    # One attempt only: an unavailable device-auth flow must never silently
    # turn into an OS browser launch outside the portable storage boundary.
    return (Invoke-CodexChildInteractive -LaunchArgs $loginArgs)
}

$Root = Find-CodexPortableRoot $LauncherDir
$RootItem = Get-Item -LiteralPath $Root -Force -ErrorAction Stop
if (($RootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    Write-Host "Codex Portable 根目录本身是 junction/symlink/reparse point，无法证明物理路径仍在便携包内；本次启动已拒绝。" -ForegroundColor Red
    exit 3
}

# Environment variables named SystemRoot/WINDIR/ComSpec are caller-controlled.
# Query the OS instead of trusting them when rebuilding child PATH/system tools.
# This happens after PowerShell has started; the BAT pre-bootstrap limitation
# must be audited separately and is NOT a substitute for a native OS sandbox.
function Get-CodexTrustedWindowsRoot {
    $windows = [IO.Path]::GetFullPath([Environment]::GetFolderPath('Windows')).TrimEnd('\')
    if ($windows -notmatch '^[A-Za-z]:\\' -or $windows.Substring(2).Contains(':') -or
        -not [IO.File]::Exists((Join-Path $windows 'System32\cmd.exe'))) {
        throw 'Codex Portable requires a real local Windows system directory.'
    }
    return $windows
}
$PortableWindowsRoot = Get-CodexTrustedWindowsRoot
function Reset-CodexTrustedSystemEnvironment {
    $env:SystemRoot = $PortableWindowsRoot
    $env:WINDIR = $PortableWindowsRoot
    $env:SystemDrive = [IO.Path]::GetPathRoot($PortableWindowsRoot).TrimEnd('\')
    $env:ComSpec = Join-Path $PortableWindowsRoot 'System32\cmd.exe'
    $env:PATHEXT = '.COM;.EXE;.BAT;.CMD'
}
Reset-CodexTrustedSystemEnvironment

# Version_History 中的专用启动器自动加载同名前缀的 *-env.ps1；根目录启动器仍使用 env.ps1。
if ([string]::IsNullOrWhiteSpace($EnvFile)) {
    $scriptLeaf = Split-Path -Leaf $PSCommandPath
    if ($scriptLeaf -like "*-run-codex.ps1") {
        $pairedEnvName = $scriptLeaf -replace "-run-codex\.ps1$", "-env.ps1"
        $pairedEnvPath = Join-Path $LauncherDir $pairedEnvName
        if (Test-Path -LiteralPath $pairedEnvPath -PathType Leaf) { $EnvFile = $pairedEnvPath }
    }
}

# 同一便携包共享 auth.json、mode 与 config.toml，必须覆盖整个启动器/Codex 生命周期。
function Get-PortableRootIdentity {
    param([string]$Path)
    # 命名 Mutex 使用规范化路径作为快速并发检查；junction/路径别名由后面的独占文件锁兜底。
    return [System.IO.Path]::GetFullPath($Path).TrimEnd("\").ToLowerInvariant()
}
$RootIdentity = Get-PortableRootIdentity $Root
$RootIdentityBytes = [System.Text.Encoding]::UTF8.GetBytes($RootIdentity)
$RootIdentityHash = [System.BitConverter]::ToString(([System.Security.Cryptography.SHA256]::Create()).ComputeHash($RootIdentityBytes)).Replace("-", "").Substring(0, 24)
$PortableInstanceMutex = $null
$PortableInstanceMutexHeld = $false
$PortableInstanceFileLock = $null
try {
$PortableInstanceMutex = New-Object System.Threading.Mutex($false, "Global\CodexPortable-$RootIdentityHash")
try {
    $PortableInstanceMutexHeld = $PortableInstanceMutex.WaitOne(0, $false)
} catch [System.Threading.AbandonedMutexException] {
    $PortableInstanceMutexHeld = $true
}
if (-not $PortableInstanceMutexHeld) {
    $PortableInstanceMutex.Dispose()
    Write-Host "这个 Codex Portable 目录已有一个实例正在运行。为避免登录凭证和配置互相覆盖，本次启动已取消。" -ForegroundColor Red
    exit 2
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
            # A broken NTFS junction can be invisible to Test-Path.
            # Inspect its directory entry even if its target is missing.
            try {
                $attrs = [IO.File]::GetAttributes($current)
                if (($attrs -band [IO.FileAttributes]::ReparsePoint) -ne 0) { return $false }
            } catch [IO.FileNotFoundException] {
                # A genuinely missing package-local component is permitted.
            } catch [IO.DirectoryNotFoundException] {
                # An ordinary missing parent is also permitted.
            } catch {
                # Unexpected filesystem errors fail closed.
                return $false
            }
        }
        return $true
    } catch {
        return $false
    }
}

# The launcher itself must also live on a non-reparse path inside the package.
# This matters for Version_History entry points: a replaced Version_History junction
# must not become an alternate executable path into the real portable root.
if (-not (Test-IsUnderDirectory -Path $LauncherDir -Directory $Root)) {
    Write-Host "启动器自身路径不在安全的 Codex Portable 包内，或路径链含 junction/symlink/reparse point：$LauncherDir" -ForegroundColor Red
    exit 3
}

function Assert-PortablePath {
    param([string]$Name, [string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return }
    if (-not (Test-IsUnderDirectory -Path $Path -Directory $Root)) {
        Write-Host "$Name 必须位于当前 Codex 目录内，拒绝越界路径：$Path" -ForegroundColor Red
        exit 1
    }
}

# Reparse checks do not detect NTFS hard links.  For *input* files, a package-local
# hard-link name can still reference the same file object as a sensitive file outside
# the intended input area.  Windows PowerShell exposes HardLink through LinkType/Mode.
function Assert-PortableRegularInputFile {
    param([string]$Name, [string]$Path)
    Assert-PortablePath $Name $Path
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Write-Host "$Name 不存在或不是普通文件：$Path" -ForegroundColor Red
        exit 3
    }
    try {
        $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        $linkTypeProperty = $item.PSObject.Properties['LinkType']
        $linkType = if ($null -ne $linkTypeProperty) { [string]$linkTypeProperty.Value } else { "" }
        if ($linkType -eq 'HardLink' -or ([string]$item.Mode).Contains('l')) {
            Write-Host "$Name 拒绝 hardlink/link 输入文件：$Path" -ForegroundColor Red
            exit 3
        }
    } catch {
        Write-Host "$Name 无法安全确认文件链接类型：$Path" -ForegroundColor Red
        exit 3
    }
}

function Test-PortablePinnedExecutableAcl {
    param([string]$Path)
    try {
        $acl = Get-Acl -LiteralPath $Path -ErrorAction Stop
        $broadSids = @('S-1-1-0','S-1-5-11','S-1-5-32-545') # Everyone, Authenticated Users, Users
        $writeMask = [Security.AccessControl.FileSystemRights]::WriteData -bor
                     [Security.AccessControl.FileSystemRights]::AppendData -bor
                     [Security.AccessControl.FileSystemRights]::WriteExtendedAttributes -bor
                     [Security.AccessControl.FileSystemRights]::WriteAttributes -bor
                     [Security.AccessControl.FileSystemRights]::Delete -bor
                     [Security.AccessControl.FileSystemRights]::ChangePermissions -bor
                     [Security.AccessControl.FileSystemRights]::TakeOwnership
        foreach ($rule in $acl.Access) {
            if ($rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow) { continue }
            try { $sid = $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value } catch { continue }
            if ($sid -in $broadSids -and (($rule.FileSystemRights -band $writeMask) -ne 0)) {
                return $false
            }
        }
        return $true
    } catch { return $false }
}

# Broad/unverifiable executable ACLs are a portability warning, not a hard stop.
# Exact package-local path/link checks and pinned SHA-256 verification remain fail-closed.
$script:PortableAclWarningsShown = @{}
function Assert-PortablePinnedExecutableAcl {
    param([string]$Name, [string]$Path)
    if (-not (Test-PortablePinnedExecutableAcl $Path)) {
        $warningKey = ([IO.Path]::GetFullPath($Path)).ToLowerInvariant()
        if (-not $script:PortableAclWarningsShown.ContainsKey($warningKey)) {
            Write-Host "[Codex] Warning: $Name ACL is broadly writable or could not be verified safely; continuing because exact SHA-256 pinning is still enforced: $Path" -ForegroundColor Yellow
            $script:PortableAclWarningsShown[$warningKey] = $true
        }
    }
}

# 命名 Mutex 负责常规并发；包根独占文件锁负责 junction/路径别名场景。
# 文件锁按实际文件对象生效，不依赖路径别名或管理员权限工具。
$PortableInstanceFileLock = $null
$PortableInstanceLockPath = Join-Path $Root ".codex-portable.instance.lock"
Assert-PortablePath "instance lock" $PortableInstanceLockPath
if (Test-Path -LiteralPath $PortableInstanceLockPath -PathType Leaf) {
    Assert-PortableRegularInputFile "instance lock" $PortableInstanceLockPath
}
try {
    $PortableInstanceFileLock = [System.IO.File]::Open(
        $PortableInstanceLockPath,
        [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None
    )
} catch {
    if ($PortableInstanceMutexHeld) {
        try { $PortableInstanceMutex.ReleaseMutex() } catch {}
        $PortableInstanceMutexHeld = $false
    }
    if ($null -ne $PortableInstanceMutex) { $PortableInstanceMutex.Dispose() }
    Write-Host "这个 Codex Portable 目录已被另一个实例占用，或无法安全创建包级锁文件。本次启动已取消。" -ForegroundColor Red
    exit 2
}

# ------------------------------------------------------------
# 0.5 锁定目标 Codex 主程序；任何包体写入/配置迁移之前先验收
# ------------------------------------------------------------
$CodexExeRoot = Join-Path $Root "codex.exe"
$CodexExeBin  = Join-Path $Root "bin\codex.exe"
if (Test-Path -LiteralPath $CodexExeRoot -PathType Leaf) {
    $CodexExe = $CodexExeRoot
} elseif (Test-Path -LiteralPath $CodexExeBin -PathType Leaf) {
    $CodexExe = $CodexExeBin
} else {
    Write-Host "未找到 codex.exe。请把官方 codex.exe 放到：$Root\codex.exe" -ForegroundColor Red
    Write-Host "也可以放到：$Root\bin\codex.exe" -ForegroundColor Yellow
    exit 1
}
Assert-PortablePath "codex.exe" $CodexExe
Assert-PortableRegularInputFile "codex.exe" $CodexExe
Assert-PortablePinnedExecutableAcl "codex.exe" $CodexExe

# This hardened launcher is version-specific.  Never run the 0.170.0 config/schema
# assumptions against an older, newer, zero-byte, or locally modified Codex binary.
$ExpectedCodexVersion = "0.170.0"
$ExpectedRuntimeManifestSha256 = "01B6152F5F9996F1F6B753D2333DD3694CD65BD8D96321C59C08C5A4576FB895"
$ExpectedCodexSha256 = "8D06DC231DBA649C7D48D3EECAB239C452A1AC498C41DD6492A6F301B90A22CE"
$CodeModeHost = Join-Path $Root "codex-code-mode-host.exe"
$ExpectedCodeModeHostSha256 = "4DD22666894CBAD119023ED64C973105050146F59847BACB8094DFE456EFBB62"
$KnownStagingCodexSha256 = "83751F15CB6A0A7B97DF67752C001E3FE1C20E18FFBFEC3FF63567296205EB6C"
try {
    $actualCodexSha256 = (Get-FileHash -LiteralPath $CodexExe -Algorithm SHA256 -ErrorAction Stop).Hash.ToUpperInvariant()
} catch {
    Write-Host "无法读取 codex.exe SHA-256；严格便携模式拒绝启动：$($_.Exception.Message)" -ForegroundColor Red
    exit 3
}
if ($actualCodexSha256 -ne $ExpectedCodexSha256) {
    if ($actualCodexSha256 -eq $KnownStagingCodexSha256) {
        Write-Host "当前仍是完整母版的官方 Codex 0.145.0 staging binary。" -ForegroundColor Yellow
        Write-Host "Clean Portable 不附带升级工具；请重新解压经过验证的 0.170.0 发行包，或使用维护工作树恢复匹配的 Codex + Host runtime pair。" -ForegroundColor Yellow
    } else {
        Write-Host "codex.exe 不是本启动器锁定的官方 Codex $ExpectedCodexVersion。" -ForegroundColor Red
        Write-Host "expected SHA-256: $ExpectedCodexSha256" -ForegroundColor DarkGray
        Write-Host "actual   SHA-256: $actualCodexSha256" -ForegroundColor DarkGray
    }
    exit 3
}

# Code Mode is an upstream runtime component of the pinned Codex release. Keep
# this package-local check fail-closed for every launcher mode.
function Assert-PinnedCodeModeHost {
    # 0.170.0 resolves a resource-directory host before the sibling executable.
    # Validate every present candidate so another path cannot bypass the root pin.
    $hostCandidates = @($CodeModeHost)
    $resourceHost = Join-Path $Root "codex-resources\codex-code-mode-host.exe"
    if (Test-Path -LiteralPath $resourceHost) { $hostCandidates += $resourceHost }
    foreach ($hostPath in $hostCandidates) {
        Assert-PortableRegularInputFile "codex-code-mode-host.exe" $hostPath
        Assert-PortablePinnedExecutableAcl "codex-code-mode-host.exe" $hostPath
        try {
            $hostHash = (Get-FileHash -LiteralPath $hostPath -Algorithm SHA256 -ErrorAction Stop).Hash.ToUpperInvariant()
        } catch {
            Write-Host "无法读取 codex-code-mode-host.exe SHA-256；严格便携模式拒绝启动：$($_.Exception.Message)" -ForegroundColor Red
            exit 3
        }
        if ($hostHash -ne $ExpectedCodeModeHostSha256) {
            Write-Host "codex-code-mode-host.exe 不是当前 Codex $ExpectedCodexVersion 的锁定官方 Host，拒绝启动：$hostPath" -ForegroundColor Red
            Write-Host "expected SHA-256: $ExpectedCodeModeHostSha256" -ForegroundColor DarkGray
            Write-Host "actual   SHA-256: $hostHash" -ForegroundColor DarkGray
            exit 3
        }
    }
}

# The native client discovers metadata, rg, sandbox helpers, voice resources and
# DLLs independently. Pin the manifest itself before trusting any of its paths or
# hashes, then validate every recorded input before the first native invocation.
function Assert-PinnedRuntimePackage {
    $manifestPath = Join-Path $Root 'tool\runtime-manifest.json'
    Assert-PortableRegularInputFile 'runtime manifest' $manifestPath
    $manifestHash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256 -ErrorAction Stop).Hash
    if ($manifestHash -ne $ExpectedRuntimeManifestSha256) {
        throw 'Runtime manifest does not match the pinned release; restore the verified complete package.'
    }
    $manifest = [IO.File]::ReadAllText($manifestPath, [Text.Encoding]::UTF8) | ConvertFrom-Json
    if ($manifest.version -ne $ExpectedCodexVersion -or $manifest.target -ne 'x86_64-pc-windows-msvc') {
        throw 'Runtime manifest version or platform does not match the launcher.'
    }
    $runtimeExecutables = @{}
    foreach ($entry in @($manifest.files.PSObject.Properties)) {
        $relative = [string]$entry.Name
        if ($relative -notmatch '^[A-Za-z0-9_. /-]+$' -or
            $relative.StartsWith('/') -or @($relative -split '/' | Where-Object { $_ -in @('', '.', '..') }).Count -gt 0) {
            throw 'Runtime manifest contains an invalid relative path.'
        }
        $path = Join-Path $Root $relative
        Assert-PortableRegularInputFile ('runtime file ' + $relative) $path
        $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256 -ErrorAction Stop).Hash
        if ($actual -ne [string]$entry.Value.sha256) {
            throw ('Runtime file differs from the pinned release: ' + $relative)
        }
        if ($relative.EndsWith('.exe', [StringComparison]::OrdinalIgnoreCase)) {
            $runtimeExecutables[[IO.Path]::GetFileName($path)] = $path
        }
    }
    # These directories are touched by native sandbox initialization before a
    # tool's write sandbox exists. Inspect links/metadata only, never secrets.
    foreach ($relative in @('home\.sandbox', 'home\.sandbox-bin', 'home\.sandbox-secrets')) {
        $stateRoot = Join-Path $Root $relative
        Assert-PortablePath 'sandbox state directory' $stateRoot
        if (-not (Test-Path -LiteralPath $stateRoot)) { continue }
        $pending = New-Object 'System.Collections.Generic.Stack[string]'
        $pending.Push($stateRoot)
        while ($pending.Count -gt 0) {
            $dir = $pending.Pop()
            Assert-PortablePath 'sandbox state directory' $dir
            $dirItem = Get-Item -LiteralPath $dir -Force -ErrorAction Stop
            if (-not $dirItem.PSIsContainer) { throw 'Sandbox state path must be a directory.' }
            foreach ($item in @(Get-ChildItem -LiteralPath $dir -Force -ErrorAction Stop)) {
                Assert-PortablePath 'sandbox state entry' $item.FullName
                if ($item.PSIsContainer) { $pending.Push($item.FullName) }
                else { Assert-PortableRegularInputFile 'sandbox state file' $item.FullName }
            }
        }
    }
    # Upstream reuses materialized helpers by size+mtime, not digest. Validate
    # files it would reuse; stale copies remain eligible for upstream replacement.
    $runtimeExecutables['codex-command-runner-' + $ExpectedCodexVersion + '.exe'] = Join-Path $Root 'codex-command-runner.exe'
    foreach ($name in @($runtimeExecutables.Keys)) {
        $cachedPath = Join-Path (Join-Path $Root 'home\.sandbox-bin') $name
        Assert-PortablePath 'cached sandbox helper' $cachedPath
        if (-not (Test-Path -LiteralPath $cachedPath)) { continue }
        Assert-PortableRegularInputFile 'cached sandbox helper' $cachedPath
        $source = Get-Item -LiteralPath $runtimeExecutables[$name] -Force -ErrorAction Stop
        $cached = Get-Item -LiteralPath $cachedPath -Force -ErrorAction Stop
        if ($cached.Length -eq $source.Length -and $cached.LastWriteTimeUtc -ge $source.LastWriteTimeUtc) {
            $sourceHash = (Get-FileHash -LiteralPath $source.FullName -Algorithm SHA256 -ErrorAction Stop).Hash
            $cachedHash = (Get-FileHash -LiteralPath $cachedPath -Algorithm SHA256 -ErrorAction Stop).Hash
            if ($cachedHash -ne $sourceHash) { throw ('Cached sandbox helper differs from the pinned release: ' + $name) }
        }
    }
}

Assert-PinnedRuntimePackage
Assert-PinnedCodeModeHost

# Re-check the exact executable immediately before every host-level Codex spawn.
# The package lock prevents cooperative concurrent maintenance; this closes the
# remaining window for an unrelated process that changes codex.exe after startup.
function Assert-PinnedCodexExecutable {
    Assert-PortableRegularInputFile "codex.exe" $CodexExe
    Assert-PortablePinnedExecutableAcl "codex.exe" $CodexExe
    try {
        $hashNow = (Get-FileHash -LiteralPath $CodexExe -Algorithm SHA256 -ErrorAction Stop).Hash.ToUpperInvariant()
    } catch {
        Write-Host "codex.exe pre-spawn SHA-256 validation failed: $($_.Exception.Message)" -ForegroundColor Red
        exit 3
    }
    if ($hashNow -ne $ExpectedCodexSha256) {
        Write-Host "codex.exe changed after launcher preflight; refusing to execute." -ForegroundColor Red
        Write-Host "expected SHA-256: $ExpectedCodexSha256" -ForegroundColor DarkGray
        Write-Host "actual   SHA-256: $hashNow" -ForegroundColor DarkGray
        exit 3
    }
}


# ------------------------------------------------------------
# 1. 目录准备 / r15-clean 安全迁移
# ------------------------------------------------------------
# 旧版本为未使用工具链留下的 cache 骨架只在“整棵树无 reparse 且没有真实文件（仅 .keep/空目录）”时删除。
# 不使用 Get-ChildItem/Remove-Item -Recurse 作为安全边界，避免内部 junction/symlink 被递归跟随。
function Inspect-PortableTree {
    param([string]$Path)
    Assert-PortablePath "tree" $Path
    $dirs = New-Object System.Collections.Generic.List[string]
    $files = New-Object System.Collections.Generic.List[string]
    $stack = New-Object 'System.Collections.Generic.Stack[string]'
    $stack.Push([IO.Path]::GetFullPath($Path))
    try {
        while ($stack.Count -gt 0) {
            $dir = $stack.Pop()
            $dirItem = Get-Item -LiteralPath $dir -Force -ErrorAction Stop
            if (($dirItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                return [pscustomobject]@{ Safe=$false; Reparse=$dir; Directories=@($dirs); Files=@($files) }
            }
            [void]$dirs.Add($dir)
            foreach ($entry in @(Get-ChildItem -LiteralPath $dir -Force -ErrorAction Stop)) {
                if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                    return [pscustomobject]@{ Safe=$false; Reparse=$entry.FullName; Directories=@($dirs); Files=@($files) }
                }
                Assert-PortablePath "tree entry" $entry.FullName
                if ($entry.PSIsContainer) { $stack.Push($entry.FullName) } else { [void]$files.Add($entry.FullName) }
            }
        }
        return [pscustomobject]@{ Safe=$true; Reparse=''; Directories=@($dirs); Files=@($files) }
    } catch {
        return [pscustomobject]@{ Safe=$false; Reparse=''; Directories=@($dirs); Files=@($files); Error=$_.Exception.Message }
    }
}

function Remove-PortableEmptyTree {
    param([string]$Path)
    $inspection = Inspect-PortableTree -Path $Path
    if (-not $inspection.Safe) {
        $detail = if (-not [string]::IsNullOrWhiteSpace([string]$inspection.Reparse)) { $inspection.Reparse } else { [string]$inspection.Error }
        Write-Host "保留存在 reparse/无法完整验证的旧缓存目录：$Path $detail" -ForegroundColor DarkYellow
        return
    }
    $realFiles = @($inspection.Files | Where-Object { [IO.Path]::GetFileName($_) -ne '.keep' })
    if ($realFiles.Count -gt 0) {
        Write-Host "保留非空旧缓存目录：$Path" -ForegroundColor DarkYellow
        return
    }
    foreach ($file in @($inspection.Files)) { Remove-Item -LiteralPath $file -Force -ErrorAction Stop }
    foreach ($dir in @($inspection.Directories | Where-Object { -not $_.Equals([IO.Path]::GetFullPath($Path),[StringComparison]::OrdinalIgnoreCase) } | Sort-Object { $_.Length } -Descending)) {
        Remove-Item -LiteralPath $dir -Force -ErrorAction Stop
    }
    Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
}

# Session-state trees are freshly randomized per launch and may contain arbitrary
# cache files. Remove only after a complete no-reparse walk; deleting a hard-link
# directory entry is safe because Remove-Item does not open/follow its target.
function Remove-PortableSessionTree {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) { return }
    $inspection = Inspect-PortableTree -Path $Path
    if (-not $inspection.Safe) {
        $detail = if (-not [string]::IsNullOrWhiteSpace([string]$inspection.Reparse)) { $inspection.Reparse } else { [string]$inspection.Error }
        Write-Host "会话缓存包含 reparse/无法完整验证，拒绝递归清理并留给清理缓存工具处理：$Path $detail" -ForegroundColor DarkYellow
        return
    }
    foreach ($file in @($inspection.Files)) { Remove-Item -LiteralPath $file -Force -ErrorAction Stop }
    foreach ($dir in @($inspection.Directories | Where-Object { -not $_.Equals([IO.Path]::GetFullPath($Path),[StringComparison]::OrdinalIgnoreCase) } | Sort-Object { $_.Length } -Descending)) {
        Remove-Item -LiteralPath $dir -Force -ErrorAction Stop
    }
    Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
}

$ObsoleteCacheDirs = @("cache\aws","cache\azure","cache\cargo","cache\composer","cache\docker","cache\dotnet","cache\nuget","cache\ruby","cache\rustup")
foreach ($rel in $ObsoleteCacheDirs) {
    $candidate = Join-Path $Root $rel
    if (-not (Test-Path -LiteralPath $candidate -PathType Container)) { continue }
    Remove-PortableEmptyTree -Path $candidate
}

$Dirs = @(
    "home",
    "home\sessions",
    "home\skills",
    "home\plugins",
    "home\.agents",
    "home\.agents\plugins",
    "home\.sandbox",
    "home\.sandbox-bin",
    "home\.sandbox-secrets",
    "home\tmp",
    "home\tmp\arg0",
    "logs",
    "sqlite",
    "login_json",
    "tmp",
    "work",
    "appdata",
    "localappdata",
    "localappdata\Microsoft\Windows\PowerShell",
    "programdata",
    "home-runtime",
    "cache",
    "cache\android",
    "cache\android\apktool-framework",
    "cache\android\frida",
    "cache\android\mitmproxy",
    "cache\android\appium",
    "cache\android\apk-lab",
    "cache\gradle",
    "cache\maven",
    "cache\npm",
    "cache\npm-prefix",
    "cache\pip",
    "cache\python-userbase",
    "cache\pnpm",
    "cache\pnpm-store",
    "cache\pycache",
    "cache\yarn",
    "tool",
    "tool\android",
    "tool\android\cli",
    "tool\android\cli\bin",
    "tool\bin",
    "tool\node",
    "tool\git",
    "tool\git\cmd",
    "tool\git\bin",
    "tool\python",
    "tool\python\Scripts"
)
foreach ($Dir in $Dirs) {
    $dirPath = Join-Path $Root $Dir
    Assert-PortablePath "便携目录" $dirPath
    New-Item -ItemType Directory -Force -Path $dirPath | Out-Null
}

# Codex arg0 会在 $CODEX_HOME\tmp\arg0 下清理旧会话目录并创建 apply_patch helper。
# 该路径在普通 sandbox 建立之前就会被写入，因此不仅根路径本身，已有子树也必须无 reparse。
$CodexArg0Root = Join-Path $Root "home\tmp\arg0"
$CodexArg0Inspection = Inspect-PortableTree -Path $CodexArg0Root
if (-not $CodexArg0Inspection.Safe) {
    $detail = if (-not [string]::IsNullOrWhiteSpace([string]$CodexArg0Inspection.Reparse)) { $CodexArg0Inspection.Reparse } else { [string]$CodexArg0Inspection.Error }
    Write-Host "检测到不安全的 CODEX_HOME\tmp\arg0 文件树；Codex 会在 sandbox 前写入这里，严格便携模式拒绝启动：$detail" -ForegroundColor Red
    exit 3
}
# Node 官方 Windows 包附带的 install_tools.bat 会调用 Chocolatey/管理员安装系统 Python/VS Build Tools，
# 与便携边界冲突。终版包不携带该入口；若它再次出现，拒绝启动而不是静默修改包体。
$UnsafeNodeInstaller = Join-Path $Root "tool\node\install_tools.bat"
Assert-PortablePath "Node system installer" $UnsafeNodeInstaller
if (Test-Path -LiteralPath $UnsafeNodeInstaller -PathType Leaf) {
    Write-Host "检测到不允许的 Node 系统安装入口：tool\node\install_tools.bat。请使用干净终版包；严格便携模式拒绝启动。" -ForegroundColor Red
    exit 3
}

# ------------------------------------------------------------
# 2. 先固定所有便携环境变量，再读取 env.ps1
# ------------------------------------------------------------
$PortableHome       = Join-Path $Root "home-runtime"
$PortableAppData    = Join-Path $Root "appdata"
$PortableLocalData  = Join-Path $Root "localappdata"
$PortableProgramData = Join-Path $Root "programdata"
$PortableTmp        = Join-Path $Root "tmp"
$PortableCache      = Join-Path $Root "cache"
$PortableWork       = Join-Path $Root "work"

# Codex 官方核心目录
$env:CODEX_HOME = Join-Path $Root "home"
$env:CODEX_SQLITE_HOME = Join-Path $Root "sqlite"

# config.toml 的安全/Provider 主体完全由本启动器生成。
# 仅保留用户显式添加的 MCP / Plugin 表；其它旧配置一律不继承，避免旧机器绝对路径、
# sandbox/approval/provider/features 等高优先级项穿透严格便携边界。
function Get-PersistableCodexExtensionToml {
    param(
        [string]$Path,
        [string[]]$AllowedNamespaces = @("mcp_servers", "plugins")
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return "" }
    Assert-PortableRegularInputFile "extension configuration" $Path
    try { $text = [System.IO.File]::ReadAllText($Path) } catch { throw "Unable to read extension configuration safely: $Path" }
    $allowedNamespaceSet = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($allowedNamespace in @($AllowedNamespaces)) {
        if (-not [string]::IsNullOrWhiteSpace([string]$allowedNamespace)) { [void]$allowedNamespaceSet.Add([string]$allowedNamespace) }
    }
    if ([string]::IsNullOrWhiteSpace($text)) { return "" }

    $out = New-Object System.Collections.Generic.List[string]
    $keep = $false
    $inMultilineBasic = $false
    $inMultilineLiteral = $false
    $arrayDepth = 0

    foreach ($line in @($text -split "`r?`n")) {
        $trim = $line.Trim()
        $isHeader = $false

        # Detect a table header before deciding whether it belongs to an allowed
        # extension namespace.  Comments are stripped lexically (not with IndexOf)
        # so `#`, `=` or `,` inside a quoted key cannot hide a security table.
        # Any header we cannot safely interpret turns preservation OFF (fail closed).
        if (-not $inMultilineBasic -and -not $inMultilineLiteral -and $arrayDepth -eq 0 -and $trim.StartsWith("[")) {
            $headerCandidate = $trim
            $inHeaderBasic = $false
            $inHeaderLiteral = $false
            $headerEscape = $false
            $commentCut = $headerCandidate.Length
            for ($hi = 0; $hi -lt $headerCandidate.Length; $hi++) {
                $hc = $headerCandidate[$hi]
                if ($inHeaderBasic) {
                    if ($headerEscape) { $headerEscape = $false; continue }
                    if ($hc -eq '\') { $headerEscape = $true; continue }
                    if ($hc -eq '"') { $inHeaderBasic = $false }
                    continue
                }
                if ($inHeaderLiteral) {
                    if ($hc -eq "'") { $inHeaderLiteral = $false }
                    continue
                }
                if ($hc -eq '"') { $inHeaderBasic = $true; continue }
                if ($hc -eq "'") { $inHeaderLiteral = $true; continue }
                if ($hc -eq '#') { $commentCut = $hi; break }
            }
            $headerText = $headerCandidate.Substring(0, $commentCut).Trim()
            $inner = $null
            if ($headerText.StartsWith("[[") -and $headerText.EndsWith("]]")) {
                $inner = $headerText.Substring(2, $headerText.Length - 4).Trim()
            } elseif ($headerText.StartsWith("[") -and -not $headerText.StartsWith("[[") -and $headerText.EndsWith("]")) {
                $inner = $headerText.Substring(1, $headerText.Length - 2).Trim()
            }
            if ($null -ne $inner) {
                $isHeader = $true
                $namespace = ""
                # Preserve only table paths whose *first TOML key segment* can be
                # interpreted unambiguously as mcp_servers or plugins.  Plain and
                # unescaped quoted keys are accepted. Escaped/complex first keys are
                # intentionally dropped instead of risking a namespace smuggle.
                if ($inner -match '^(mcp_servers|plugins)(?:\s*\.|\s*$)') {
                    $namespace = $Matches[1]
                } elseif ($inner -match '^"(mcp_servers|plugins)"(?:\s*\.|\s*$)') {
                    $namespace = $Matches[1]
                } elseif ($inner -match "^'(mcp_servers|plugins)'(?:\s*\.|\s*$)") {
                    $namespace = $Matches[1]
                }
                $keep = (-not [string]::IsNullOrWhiteSpace($namespace)) -and $allowedNamespaceSet.Contains($namespace)
            }
        }
        if ($keep) { [void]$out.Add($line) }

        if ($isHeader) { continue }

        # Lightweight TOML lexical state: enough to distinguish table-looking text
        # inside strings/arrays without reserializing or otherwise modifying the
        # user's original TOML text.
        $inBasicSingle = $false
        $inLiteralSingle = $false
        $i = 0
        while ($i -lt $line.Length) {
            if ($inMultilineBasic) {
                if ($i + 2 -lt $line.Length -and $line.Substring($i,3) -eq '"""') {
                    $slashCount = 0; $j = $i - 1
                    while ($j -ge 0 -and $line[$j] -eq '\') { $slashCount++; $j-- }
                    if (($slashCount % 2) -eq 0) { $inMultilineBasic = $false; $i += 3; continue }
                }
                $i++; continue
            }
            if ($inMultilineLiteral) {
                if ($i + 2 -lt $line.Length -and $line.Substring($i,3) -eq "'''") { $inMultilineLiteral = $false; $i += 3; continue }
                $i++; continue
            }
            if ($inBasicSingle) {
                if ($line[$i] -eq '\') { $i += 2; continue }
                if ($line[$i] -eq '"') { $inBasicSingle = $false }
                $i++; continue
            }
            if ($inLiteralSingle) {
                if ($line[$i] -eq "'") { $inLiteralSingle = $false }
                $i++; continue
            }

            if ($line[$i] -eq '#') { break }
            if ($i + 2 -lt $line.Length -and $line.Substring($i,3) -eq '"""') { $inMultilineBasic = $true; $i += 3; continue }
            if ($i + 2 -lt $line.Length -and $line.Substring($i,3) -eq "'''") { $inMultilineLiteral = $true; $i += 3; continue }
            if ($line[$i] -eq '"') { $inBasicSingle = $true; $i++; continue }
            if ($line[$i] -eq "'") { $inLiteralSingle = $true; $i++; continue }
            if ($line[$i] -eq '[') { $arrayDepth++ }
            elseif ($line[$i] -eq ']' -and $arrayDepth -gt 0) { $arrayDepth-- }
            $i++
        }
    }
    if ($out.Count -eq 0) { return "" }
    return (($out -join [Environment]::NewLine).Trim() + [Environment]::NewLine)
}
# A maintenance command must see its complete namespace, not a filtered view.
function Get-PortableExtensionCommandNamespace {
    param(
        [ValidateSet('mcp','plugin')][string]$Command,
        [AllowEmptyCollection()][string[]]$AllowedNamespaces = @()
    )
    $namespace = if ($Command -eq 'mcp') { 'mcp_servers' } else { 'plugins' }
    if ($namespace -cnotin @($AllowedNamespaces)) {
        $setting = if ($Command -eq 'mcp') { 'CODEX_PORTABLE_ALLOW_USER_MCP' } else { 'CODEX_ENABLE_PLUGINS' }
        throw ("Extension configuration management requires --portable-extensions and " + $setting + "=true; saved configuration was not changed.")
    }
    return $namespace
}

function Save-PortableExtensionCommandResult {
    param(
        [string]$ConfigPath, [string]$StorePath,
        [ValidateSet('mcp','plugin')][string]$Command,
        [AllowEmptyCollection()][string[]]$AllowedNamespaces = @()
    )
    $namespace = Get-PortableExtensionCommandNamespace -Command $Command -AllowedNamespaces $AllowedNamespaces
    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
        throw 'Extension command did not leave a readable generated configuration; saved configuration was not changed.'
    }
    $updated = Get-PersistableCodexExtensionToml -Path $ConfigPath -AllowedNamespaces @($namespace)
    $previous = Get-PersistableCodexExtensionToml -Path $StorePath -AllowedNamespaces @($namespace)
    # Read-only commands must not rewrite or reorder the durable sidecar.
    if ($updated -ceq $previous) { return }
    $otherNamespaces = @('mcp_servers','plugins') | Where-Object { $_ -cne $namespace }
    $retained = Get-PersistableCodexExtensionToml -Path $StorePath -AllowedNamespaces @($otherNamespaces)
    # Replacing only the edited namespace preserves inactive settings, while an
    # explicit removal of its last entry remains a removal (never resurrect it).
    Write-Utf8TextAtomic -Path $StorePath -Text ($retained + $updated)
}

# Preserve legacy extension settings before any generated-config removal. A later
# startup rejection must not leave the only copy in process memory.
function Initialize-PortableExtensionStore {
    param([string]$ConfigPath, [string]$StorePath)
    Assert-PortablePath 'generated config' $ConfigPath
    Assert-PortablePath 'extension store' $StorePath
    if (Test-Path -LiteralPath $StorePath) {
        Assert-PortableRegularInputFile 'extension store' $StorePath
        # Even an explicitly empty store is authoritative; never resurrect old settings.
        return (Get-PersistableCodexExtensionToml -Path $StorePath)
    }
    $legacy = Get-PersistableCodexExtensionToml -Path $ConfigPath
    if ([string]::IsNullOrWhiteSpace($legacy)) { return '' }
    $scratch = Join-Path $Root 'tmp'
    Assert-PortablePath 'extension migration scratch' $scratch
    if (-not (Test-Path -LiteralPath $scratch -PathType Container)) { throw 'Extension migration requires the package temporary directory.' }
    $temporary = Join-Path $scratch ('extension-migration-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    Assert-PortablePath 'extension migration staging' $temporary
    $owned = $false
    try {
        $stream = [IO.File]::Open($temporary, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $owned = $true
        try {
            $bytes = (New-Object Text.UTF8Encoding($false)).GetBytes($legacy)
            $stream.Write($bytes, 0, $bytes.Length)
            $stream.Flush($true)
        } finally { $stream.Dispose() }
        Assert-PortableRegularInputFile 'staged extension migration' $temporary
        Assert-PortablePath 'extension store commit' $StorePath
        # File.Move never overwrites a destination created since the first check.
        # Any failure leaves the original config untouched for a safe retry.
        [IO.File]::Move($temporary, $StorePath)
        $owned = $false
    } finally {
        if ($owned) {
            Assert-PortableRegularInputFile 'owned extension migration cleanup' $temporary
            [IO.File]::Delete($temporary)
        }
    }
    return $legacy
}

$GeneratedConfigPath = Join-Path $env:CODEX_HOME "config.toml"
$ExtensionStorePath = Join-Path $env:CODEX_HOME "portable-extensions.toml"
Assert-PortablePath "generated config" $GeneratedConfigPath
Assert-PortablePath "extension store" $ExtensionStorePath
$PreservedExtensionToml = Initialize-PortableExtensionStore -ConfigPath $GeneratedConfigPath -StorePath $ExtensionStorePath
if (Test-Path -LiteralPath $GeneratedConfigPath -PathType Leaf) {
    Assert-PortableRegularInputFile 'stale generated config' $GeneratedConfigPath
    Remove-Item -LiteralPath $GeneratedConfigPath -Force -ErrorAction Stop
}

# Windows / 通用用户目录变量
$env:HOME = $PortableHome
$env:USERPROFILE = $PortableHome
$env:APPDATA = $PortableAppData
$env:LOCALAPPDATA = $PortableLocalData
$env:PROGRAMDATA = $PortableProgramData
$env:ALLUSERSPROFILE = $PortableProgramData
$env:TEMP = $PortableTmp
$env:TMP = $PortableTmp
$env:TMPDIR = $PortableTmp

# HOMEDRIVE / HOMEPATH 也固定到便携 home-runtime
try {
    $HomeRoot = [System.IO.Path]::GetPathRoot($PortableHome)
    if (-not [string]::IsNullOrWhiteSpace($HomeRoot) -and $HomeRoot -match '^[A-Za-z]:\\$') {
        $env:HOMEDRIVE = $HomeRoot.Substring(0, 2)
        $env:HOMEPATH = $PortableHome.Substring(2)
    }
} catch {}

# XDG 变量
$env:XDG_CACHE_HOME = Join-Path $PortableCache "xdg"
$env:XDG_CONFIG_HOME = $PortableAppData
$env:XDG_DATA_HOME = $PortableLocalData
$env:XDG_STATE_HOME = Join-Path $PortableLocalData "state"

# 常见开发工具缓存，尽量避免子进程写到用户目录
$env:PIP_CONFIG_FILE = "nul"
$env:PIP_CACHE_DIR = Join-Path $PortableCache "pip"
$env:PYTHONUSERBASE = Join-Path $PortableCache "python-userbase"
$env:NPM_CONFIG_CACHE = Join-Path $PortableCache "npm"
$env:NPM_CONFIG_PREFIX = Join-Path $PortableCache "npm-prefix"
$env:NPM_CONFIG_GLOBALCONFIG = Join-Path $PortableCache "npm\global.npmrc"
$env:NPM_CONFIG_USERCONFIG = Join-Path $PortableHome ".npmrc"
$env:NODE_REPL_HISTORY = Join-Path $PortableHome ".node_repl_history"
$env:YARN_CACHE_FOLDER = Join-Path $PortableCache "yarn"
$env:PNPM_HOME = Join-Path $PortableCache "pnpm"
$env:PNPM_STORE_DIR = Join-Path $PortableCache "pnpm-store"
$env:GRADLE_USER_HOME = Join-Path $PortableCache "gradle"
$env:MAVEN_OPTS = "-Dmaven.repo.local=`"" + (Join-Path $PortableCache "maven") + "`""
$env:POWERSHELL_TELEMETRY_OPTOUT = "1"
$env:PSModuleAnalysisCachePath = Join-Path $PortableLocalData "Microsoft\Windows\PowerShell\ModuleAnalysisCache"
$PortablePsModules = Join-Path $PortableCache "powershell\modules"
$env:PSModulePath = $PortablePsModules + ";" + (Join-Path $PSHOME "Modules")
Assert-PortablePath "PowerShell modules" $PortablePsModules
New-Item -ItemType Directory -Force -Path $PortablePsModules | Out-Null

# OpenAI/Codex 安装器相关变量：即使误触安装脚本，也尽量不跑到用户目录
$env:CODEX_INSTALL_DIR = $Root

# ------------------------------------------------------------
# 2.1 便携工具：tool 目录（python / node 等）
#     全部前插 PATH；Python 的缓存与安装目录固定到包内，避免越界写入用户目录
# ------------------------------------------------------------
$PortableTool = Join-Path $Root "tool"
$env:CODEX_PYTHON = Join-Path $PortableTool "python\python.exe"
$env:PYTHONPYCACHEPREFIX   = Join-Path $PortableCache "pycache"

# Android SDK build-tools 使用版本目录（例如 build-tools\36.0.0），不能写死版本号。
# 优先选最高版本的完整目录；若只有不完整目录，则仍加入最高可用目录，交给检查器逐项 WARN。
function Get-PortableAndroidBuildToolsPath {
    param([string]$SdkRoot)
    $buildToolsRoot = Join-Path $SdkRoot "build-tools"
    Assert-PortablePath "Android build-tools root" $buildToolsRoot
    if (-not (Test-Path -LiteralPath $buildToolsRoot -PathType Container)) { return "" }

    $candidates = @()
    foreach ($dir in @(Get-ChildItem -LiteralPath $buildToolsRoot -Directory -Force -ErrorAction SilentlyContinue)) {
        Assert-PortablePath "Android build-tools candidate" $dir.FullName
        $baseVersion = ([string]$dir.Name -replace '-.*$','')
        try { $version = [Version]$baseVersion } catch { $version = [Version]'0.0' }
        $expected = @(
            (Join-Path $dir.FullName 'aapt.exe'),
            (Join-Path $dir.FullName 'aapt2.exe'),
            (Join-Path $dir.FullName 'apksigner.bat'),
            (Join-Path $dir.FullName 'zipalign.exe')
        )
        $unsafeExpected = @($expected | Where-Object {
            (Test-Path -LiteralPath $_ -PathType Leaf) -and (-not (Test-IsUnderDirectory -Path $_ -Directory $Root))
        }).Count
        if ($unsafeExpected -gt 0) { continue }
        $present = @($expected | Where-Object {
            (Test-Path -LiteralPath $_ -PathType Leaf) -and ((Get-Item -LiteralPath $_ -Force).Length -gt 0)
        }).Count
        $isPrerelease = $(if ([string]$dir.Name -match '-') { 1 } else { 0 })
        $candidates += [pscustomobject]@{ Path=$dir.FullName; Version=$version; IsPrerelease=$isPrerelease; Name=[string]$dir.Name; Present=$present }
    }
    if ($candidates.Count -eq 0) { return "" }
    $ordered = @($candidates | Sort-Object @{Expression='Version';Descending=$true}, @{Expression='IsPrerelease';Descending=$false}, @{Expression='Name';Descending=$true})
    $complete = @($ordered | Where-Object { $_.Present -eq 4 } | Select-Object -First 1)
    if ($complete.Count -gt 0) { return [string]$complete[0].Path }
    $partial = @($ordered | Where-Object { $_.Present -gt 0 } | Select-Object -First 1)
    if ($partial.Count -gt 0) { return [string]$partial[0].Path }
    return ""
}

$AndroidBuildToolsPath = Get-PortableAndroidBuildToolsPath -SdkRoot (Join-Path $PortableTool "android\sdk")

$ToolPaths = @(
    (Join-Path $PortableTool "bin"),
    (Join-Path $PortableTool "git\cmd"),
    (Join-Path $PortableTool "git\bin"),
    (Join-Path $PortableTool "git"),
    (Join-Path $PortableTool "python"),
    (Join-Path $PortableTool "python\Scripts"),
    (Join-Path $PortableCache "python-userbase\Scripts"),
    (Join-Path $PortableTool "node"),
    (Join-Path $PortableCache "npm-prefix"),
    (Join-Path $PortableCache "npm-prefix\node_modules\.bin"),
    (Join-Path $PortableCache "pnpm"),
    (Join-Path $PortableTool "android\jdk\bin"),
    (Join-Path $PortableTool "android\sdk\platform-tools"),
    (Join-Path $PortableTool "android\sdk\emulator"),
    (Join-Path $PortableTool "android\sdk\cmdline-tools\latest\bin"),
    (Join-Path $PortableTool "android\jadx\bin"),
    (Join-Path $PortableTool "android\dex2jar"),
    (Join-Path $PortableTool "android\apktool"),
    (Join-Path $PortableTool "android\maestro\bin"),
    (Join-Path $PortableTool "android\cli"),
    (Join-Path $PortableTool "android\cli\bin"),
    (Join-Path $PortableTool "android\bundletool"),
    (Join-Path $PortableTool "office\libreoffice\program"),
    (Join-Path $PortableTool "office\pandoc"),
    (Join-Path $PortableTool "pdf\poppler\Library\bin"),
    (Join-Path $PortableTool "pdf\poppler\bin"),
    (Join-Path $PortableTool "pdf\qpdf\bin"),
    (Join-Path $PortableTool "media\ffmpeg\bin"),
    (Join-Path $PortableTool "ocr\tesseract")
)
if (-not [string]::IsNullOrWhiteSpace($AndroidBuildToolsPath)) { $ToolPaths = @($AndroidBuildToolsPath) + $ToolPaths }
$SystemPaths = @(
    (Join-Path $PortableWindowsRoot "System32"),
    $PortableWindowsRoot,
    (Join-Path $PortableWindowsRoot "System32\WindowsPowerShell\v1.0"),
    (Join-Path $PortableWindowsRoot "System32\Wbem")
)

function Set-PortableProcessPath {
    foreach ($candidate in @($ToolPaths)) {
        Assert-PortablePath "便携工具路径" $candidate
    }
    $parts = New-Object System.Collections.Generic.List[string]
    foreach ($candidate in @($ToolPaths + $SystemPaths)) {
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        if (-not $parts.Contains($candidate)) { [void]$parts.Add($candidate) }
    }
    $env:PATH = ($parts -join ";")
}

Set-PortableProcessPath

function ConvertTo-WindowsCommandLineArgument {
    param([string]$Argument)
    if ([string]::IsNullOrEmpty($Argument)) { return '""' }
    if ($Argument -notmatch '[\s"]') { return $Argument }

    $builder = New-Object System.Text.StringBuilder
    [void]$builder.Append('"')
    $backslashes = 0
    foreach ($ch in $Argument.ToCharArray()) {
        if ($ch -eq '\') {
            $backslashes++
            continue
        }
        if ($ch -eq '"') {
            if ($backslashes -gt 0) { [void]$builder.Append('\' * ($backslashes * 2)) }
            [void]$builder.Append('\"')
            $backslashes = 0
            continue
        }
        if ($backslashes -gt 0) {
            [void]$builder.Append('\' * $backslashes)
            $backslashes = 0
        }
        [void]$builder.Append($ch)
    }
    if ($backslashes -gt 0) { [void]$builder.Append('\' * ($backslashes * 2)) }
    [void]$builder.Append('"')
    return $builder.ToString()
}

# ------------------------------------------------------------
# 3. 读取 API / Provider 配置
# ------------------------------------------------------------

function Convert-ToTomlBool {
    param([string]$Value, [bool]$Default)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $(if ($Default) { "true" } else { "false" })
    }
    $v = $Value.Trim().ToLowerInvariant()
    if ($v -in @("1","true","yes","y","on")) { return "true" }
    if ($v -in @("0","false","no","n","off")) { return "false" }
    throw "布尔配置只支持 true/false（也接受 1/0、yes/no、on/off），当前无效值：$Value"
}

function Convert-ToFeatureBool {
    param([string]$Value, [bool]$Default)
    return (Convert-ToTomlBool $Value $Default) -eq "true"
}

# An old env.local.ps1 value alone must never activate host-side extensions.
# Parse both settings even when the session flag is absent so invalid values fail closed.
function Get-PortableExtensionPolicy {
    param(
        [bool]$TaskRequested = $false,
        [string]$PluginsValue = "",
        [string]$UserMcpValue = ""
    )
    $pluginsConfigured = Convert-ToFeatureBool $PluginsValue $false
    $userMcpConfigured = Convert-ToFeatureBool $UserMcpValue $false
    $pluginsEnabled = $TaskRequested -and $pluginsConfigured
    $userMcpEnabled = $TaskRequested -and $userMcpConfigured
    $allowedNamespaces = @()
    if ($pluginsEnabled) { $allowedNamespaces += "plugins" }
    if ($userMcpEnabled) { $allowedNamespaces += "mcp_servers" }
    return [pscustomobject]@{
        TaskRequested = $TaskRequested
        PluginsEnabled = $pluginsEnabled
        UserMcpEnabled = $userMcpEnabled
        AllowedNamespaces = [string[]]$allowedNamespaces
    }
}

function Initialize-PortablePlugins {
    param([string]$PluginRoot, [string]$MarketplaceFile)
    Assert-PortablePath "PluginRoot" $PluginRoot
    Assert-PortablePath "PluginMarketplace" $MarketplaceFile
    New-Item -ItemType Directory -Force -Path $PluginRoot | Out-Null
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $MarketplaceFile) | Out-Null
    $keep = Join-Path $PluginRoot ".keep"
    if (-not (Test-Path -LiteralPath $keep)) { New-Item -ItemType File -Force -Path $keep | Out-Null }
    if (-not (Test-Path -LiteralPath $MarketplaceFile)) {
        $json = '{"version":1,"marketplaces":[{"name":"Codex Portable Local","root":".","plugins":[]}]}'
        Write-Utf8TextAtomic -Path $MarketplaceFile -Text $json
    } else {
        Assert-PortableRegularInputFile "PluginMarketplace" $MarketplaceFile
        try { $null = (Get-Content -LiteralPath $MarketplaceFile -Raw | ConvertFrom-Json) }
        catch {
            Write-Host "插件 Marketplace 配置无法解析：$MarketplaceFile" -ForegroundColor Yellow
            Write-Host "已保留原文件；请修复 JSON 后重新启动。" -ForegroundColor Yellow
        }
    }
    $pluginTreeInspection = Inspect-PortableTree -Path $PluginRoot
    if (-not $pluginTreeInspection.Safe) {
        throw "Plugin tree contains a reparse point or cannot be inspected safely: $PluginRoot"
    }
    foreach ($pluginFile in @($pluginTreeInspection.Files)) {
        Assert-PortableRegularInputFile "plugin file" $pluginFile
    }
}

if ([string]::IsNullOrWhiteSpace($EnvFile)) { $EnvFile = Join-Path $Root "env.ps1" }
# Bind validation and dot-source to one path even when PS and .NET cwd differ.
$EnvFile = [IO.Path]::GetFullPath($EnvFile)
Assert-PortablePath "env.ps1" $EnvFile
if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
    Write-Host "未找到 env.ps1，请确认文件存在：$EnvFile" -ForegroundColor Red
    exit 1
}
Assert-PortableRegularInputFile "env.ps1" $EnvFile

# 严格便携模式先清掉宿主进程可能注入的凭证/代码加载/外部配置变量。
# 随后再加载包内 env.ps1 / env.local.ps1；确实需要的值必须在包内显式重新设置。
foreach ($hostSensitiveName in @(
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN", "AWS_WEB_IDENTITY_TOKEN_FILE",
    "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID", "AZURE_FEDERATED_TOKEN_FILE",
    "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_API_KEY", "GEMINI_API_KEY",
    "GITHUB_TOKEN", "GH_TOKEN", "NPM_TOKEN", "NODE_AUTH_TOKEN", "PYPI_TOKEN", "TWINE_PASSWORD",
    "HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN", "ANTHROPIC_API_KEY", "CLOUDFLARE_API_TOKEN",
    "OPENAI_ORGANIZATION", "OPENAI_PROJECT", "OPENAI_BASE_URL", "CODEX_OSS_BASE_URL", "CODEX_OSS_PORT",
    "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONINSPECT", "PYTHONWARNINGS", "PYTHONBREAKPOINT",
    "NODE_OPTIONS", "NODE_PATH", "NODE_EXTRA_CA_CERTS", "JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS",
    "PIP_CONFIG_FILE", "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "PIP_TRUSTED_HOST", "PIP_CERT", "PIP_CLIENT_CERT",
    "UV_INDEX_URL", "UV_DEFAULT_INDEX", "UV_EXTRA_INDEX_URL", "UV_INDEX", "UV_FIND_LINKS", "UV_NO_INDEX",
    "NPM_CONFIG_REGISTRY", "NPM_CONFIG_SCRIPT_SHELL", "NPM_CONFIG_NODE_OPTIONS", "NPM_CONFIG_HTTPS_PROXY", "NPM_CONFIG_PROXY",
    "NPM_CONFIG_CAFILE", "NPM_CONFIG_CERT", "NPM_CONFIG_KEY",
    "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS",
    "GIT_ASKPASS", "SSH_ASKPASS", "GIT_SSH", "GIT_SSH_COMMAND", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_COUNT",
    "SSH_AUTH_SOCK", "SSH_AGENT_PID", "GPG_AGENT_INFO", "VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV", "CONDA_PROMPT_MODIFIER",
    "BASH_ENV", "ENV", "CDPATH", "RUBYOPT", "RUBYLIB", "PERL5OPT", "PERL5LIB", "KUBECONFIG", "DOCKER_HOST", "DOCKER_CONTEXT",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    "LATEST_MODEL_URL", "LATEST_MODEL_BASE_URL", "CODEX_PORTABLE_ALLOW_CUSTOM_MANUAL_URL", "NODE"
)) {
    Remove-Item "Env:$hostSensitiveName" -ErrorAction SilentlyContinue
}
Get-ChildItem Env: | Where-Object { $_.Name -match '^(?i:GIT_)' } | ForEach-Object {
    Remove-Item ("Env:" + $_.Name) -ErrorAction SilentlyContinue
}
$env:GIT_CONFIG_NOSYSTEM = "1"
# 7A strict isolation: no host CODEX_*/OPENAI_* settings survive into package config.
$portableAnchorNames = @("CODEX_HOME", "CODEX_SQLITE_HOME", "CODEX_INSTALL_DIR", "CODEX_PYTHON")
Get-ChildItem Env: | Where-Object { $_.Name -match '^(?i:CODEX_|OPENAI_)' -and $_.Name -notin $portableAnchorNames } | ForEach-Object {
    Remove-Item ("Env:" + $_.Name) -ErrorAction SilentlyContinue
}

$script:CodexPortableAutoModelInstructions = $false
. $EnvFile
# Validate the package's explicit login choice before touching account state.
$BrowserLoginFlow = Get-CodexBrowserLoginFlow -Value $env:CODEX_BROWSER_LOGIN_FLOW
# Validate the visual preference before any account-state selection.
$TuiFullscreenTranscript = Convert-ToTomlBool -Value $env:CODEX_TUI_FULLSCREEN_TRANSCRIPT -Default $false

# env.ps1/env.local.ps1 加载后，重新固定所有“便携边界常量”。
# 用户配置只能改变模型/API/代理等业务值，不能把工具链、用户目录或缓存重新指向宿主机。
function Reset-PortableInvariantEnvironment {
    Reset-CodexTrustedSystemEnvironment
    # This edition ships runtime tools only; stale compiler paths must not survive.
    foreach ($name in @('GOPATH','GOCACHE','GOMODCACHE','GOROOT','GOTOOLCHAIN','UV_CACHE_DIR','UV_PYTHON_INSTALL_DIR','UV_TOOL_DIR','UV_TOOL_BIN_DIR')) {
        Remove-Item ("Env:" + $name) -ErrorAction SilentlyContinue
    }
    $env:CODEX_HOME = Join-Path $Root "home"
    $env:CODEX_SQLITE_HOME = Join-Path $Root "sqlite"
    $env:CODEX_INSTALL_DIR = $Root
    $env:CODEX_PYTHON = Join-Path $PortableTool "python\python.exe"

    $env:HOME = $PortableHome
    $env:USERPROFILE = $PortableHome
    $env:APPDATA = $PortableAppData
    $env:LOCALAPPDATA = $PortableLocalData
    $env:PROGRAMDATA = $PortableProgramData
    $env:ALLUSERSPROFILE = $PortableProgramData
    $env:TEMP = $PortableTmp
    $env:TMP = $PortableTmp
    $env:TMPDIR = $PortableTmp
    try {
        $homeRoot = [IO.Path]::GetPathRoot($PortableHome)
        if (-not [string]::IsNullOrWhiteSpace($homeRoot) -and $homeRoot -match '^[A-Za-z]:\\$') {
            $env:HOMEDRIVE = $homeRoot.Substring(0,2)
            $env:HOMEPATH = $PortableHome.Substring(2)
        }
    } catch {}

    $env:XDG_CACHE_HOME = Join-Path $PortableCache "xdg"
    $env:XDG_CONFIG_HOME = $PortableAppData
    $env:XDG_DATA_HOME = $PortableLocalData
    $env:XDG_STATE_HOME = Join-Path $PortableLocalData "state"
    # Windows pip uses Shell Folders for config paths; rebasing APPDATA is insufficient.
    $env:PIP_CONFIG_FILE = "nul"
    $env:PIP_CACHE_DIR = Join-Path $PortableCache "pip"
    $env:PYTHONUSERBASE = Join-Path $PortableCache "python-userbase"
    $env:PYTHONPYCACHEPREFIX = Join-Path $PortableCache "pycache"
    $env:NPM_CONFIG_CACHE = Join-Path $PortableCache "npm"
    $env:NPM_CONFIG_PREFIX = Join-Path $PortableCache "npm-prefix"
    $env:NPM_CONFIG_GLOBALCONFIG = Join-Path $PortableCache "npm\global.npmrc"
    $env:NPM_CONFIG_USERCONFIG = Join-Path $PortableHome ".npmrc"
    $env:NODE_REPL_HISTORY = Join-Path $PortableHome ".node_repl_history"
    $env:YARN_CACHE_FOLDER = Join-Path $PortableCache "yarn"
    $env:PNPM_HOME = Join-Path $PortableCache "pnpm"
    $env:PNPM_STORE_DIR = Join-Path $PortableCache "pnpm-store"
    $env:GRADLE_USER_HOME = Join-Path $PortableCache "gradle"
    $env:MAVEN_OPTS = "-Dmaven.repo.local=`"" + (Join-Path $PortableCache "maven") + "`""
    $env:POWERSHELL_TELEMETRY_OPTOUT = "1"
    $env:PSModuleAnalysisCachePath = Join-Path $PortableLocalData "Microsoft\Windows\PowerShell\ModuleAnalysisCache"
    $env:PSModulePath = $PortablePsModules + ";" + (Join-Path $PSHOME "Modules")
    $env:GIT_CONFIG_NOSYSTEM = "1"

    $env:ANDROID_HOME = Join-Path $PortableTool "android\sdk"
    $sdkRoot = $env:ANDROID_HOME
    # Standalone ADB does not imply an installed Android SDK.
    $sdkPresent = Test-Path -LiteralPath (Join-Path $sdkRoot "cmdline-tools\latest\bin\sdkmanager.bat") -PathType Leaf
    if (-not $sdkPresent -and (Test-Path -LiteralPath (Join-Path $sdkRoot "build-tools") -PathType Container)) {
        $sdkPresent = @(Get-ChildItem -LiteralPath (Join-Path $sdkRoot "build-tools") -Directory -ErrorAction Stop | Where-Object {
            Test-Path -LiteralPath (Join-Path $_.FullName "aapt2.exe") -PathType Leaf
        }).Count -gt 0
    }
    if (-not $sdkPresent) { Remove-Item Env:ANDROID_HOME -ErrorAction SilentlyContinue }
    $env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
    $env:ANDROID_USER_HOME = Join-Path $PortableHome ".android"
    $env:ANDROID_SDK_HOME = $PortableHome
    $env:JAVA_HOME = Join-Path $PortableTool "android\jdk"
    if (-not ((Test-Path -LiteralPath (Join-Path $env:JAVA_HOME "bin\java.exe") -PathType Leaf) -and
               (Test-Path -LiteralPath (Join-Path $env:JAVA_HOME "bin\javac.exe") -PathType Leaf))) {
        Remove-Item Env:JAVA_HOME -ErrorAction SilentlyContinue
    }
    $env:ADB_VENDOR_KEYS = Join-Path $PortableHome ".android\adbkey"
    $env:APKTOOL_FRAMEWORK_DIR = Join-Path $PortableCache "android\apktool-framework"
    $env:FRIDA_CACHE_DIR = Join-Path $PortableCache "android\frida"
    $env:MITMPROXY_HOME = Join-Path $PortableCache "android\mitmproxy"
    $env:APPIUM_HOME = Join-Path $PortableCache "android\appium"
    $env:APK_LAB_CACHE_DIR = Join-Path $PortableCache "android\apk-lab"
    $env:APK_LAB_TMP_DIR = Join-Path $PortableTmp "android"
    $env:APK_LAB_JOBS_DIR = Join-Path $PortableWork "apk-jobs"
    Set-PortableProcessPath
}
Reset-PortableInvariantEnvironment
# PATH 已确定，不把原宿主 PATH 快照继续暴露给 Codex/子进程。

# Codex 0.170.0 在进程非常早期会自动读取 $CODEX_HOME\.env，并把除 CODEX_* 外的变量
# 再次注入自身环境。那一步发生在启动器对子进程完成“清空 + 白名单重建”之后，可能重新带入
# OPENAI_BASE_URL / OPENAI_API_KEY / 代理 / PYTHONPATH / NODE_OPTIONS / HOME 等值。
# 严格便携模式因此不允许这个隐式配置入口；请统一使用根目录 env.local.ps1。
$CodexDotEnvPath = Join-Path $env:CODEX_HOME ".env"
if (Test-Path -LiteralPath $CodexDotEnvPath) {
    if (-not (Test-IsUnderDirectory -Path $CodexDotEnvPath -Directory $Root)) {
        Write-Host "检测到不安全的 CODEX_HOME\.env 路径（含 reparse/越界）：$CodexDotEnvPath" -ForegroundColor Red
    } else {
        Write-Host "检测到 Codex 会自动加载的隐藏环境文件：$CodexDotEnvPath" -ForegroundColor Red
    }
    Write-Host '严格便携模式拒绝启动。请把需要的模型/API/代理配置迁移到包根 env.local.ps1，然后移走 home\.env。' -ForegroundColor Yellow
    exit 3
}

$PortableProfile = $env:CODEX_PORTABLE_PROFILE
if ([string]::IsNullOrWhiteSpace($PortableProfile)) { $PortableProfile = "strict" }
$PortableProfile = $PortableProfile.Trim().ToLowerInvariant()
if ($PortableProfile -ne "strict") {
    Write-Host "CODEX_PORTABLE_PROFILE 当前仅支持 strict，检测到：$PortableProfile" -ForegroundColor Red
    exit 1
}

# Codex 0.170.0 also reads a machine policy from the 64-bit registry view.
# Only enumerate the fixed policy key's value names: do not read RequirementsPath
# or inspect/open its target before the user has opted into host system policy.
function Open-CodexSystemPolicyRegistryKey {
    $baseKey = [Microsoft.Win32.RegistryKey]::OpenBaseKey(
        [Microsoft.Win32.RegistryHive]::LocalMachine,
        [Microsoft.Win32.RegistryView]::Registry64)
    try {
        return $baseKey.OpenSubKey('SOFTWARE\Policies\OpenAI\Codex', $false)
    } finally {
        if ($null -ne $baseKey) { $baseKey.Dispose() }
    }
}

function Test-CodexSystemRequirementsRegistryPolicy {
    $policyKey = Open-CodexSystemPolicyRegistryKey
    try {
        if ($null -eq $policyKey) { return $false }
        return (@($policyKey.GetValueNames()) -icontains 'RequirementsPath')
    } finally {
        if ($null -ne $policyKey) { $policyKey.Dispose() }
    }
}

function Assert-CodexSystemRequirementsRegistryPolicy {
    param([bool]$AllowHostSystemConfig = $false)
    if ($AllowHostSystemConfig) { return }
    if (Test-CodexSystemRequirementsRegistryPolicy) {
        throw 'Windows Codex RequirementsPath policy is configured. Portable mode refuses to load system policy by default. To explicitly use administrator policy, set CODEX_ALLOW_HOST_SYSTEM_CONFIG = "true" in env.local.ps1.'
    }
}

# Codex 0.170.0 在 Windows 通过 Known Folder API 读取真实 %ProgramData%\OpenAI\Codex，
# 这不受上面的 $env:PROGRAMDATA 重定向影响。默认拒绝宿主 system config/requirements；
# 如组织策略明确要求使用，可在 env.local.ps1 写 CODEX_ALLOW_HOST_SYSTEM_CONFIG="true" 显式同意。
$allowHostSystemConfig = Convert-ToFeatureBool ([string]$env:CODEX_ALLOW_HOST_SYSTEM_CONFIG) $false
try {
    Assert-CodexSystemRequirementsRegistryPolicy -AllowHostSystemConfig $allowHostSystemConfig
    $hostProgramData = [Environment]::GetFolderPath([System.Environment+SpecialFolder]::CommonApplicationData)
    if (-not [string]::IsNullOrWhiteSpace($hostProgramData)) {
        $hostCodexSystemDir = Join-Path $hostProgramData "OpenAI\Codex"
        $hostSystemFiles = @(
            (Join-Path $hostCodexSystemDir "config.toml"),
            (Join-Path $hostCodexSystemDir "requirements.toml"),
            (Join-Path $hostCodexSystemDir "managed_config.toml")
        ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
        if ($hostSystemFiles.Count -gt 0 -and -not $allowHostSystemConfig) {
            Write-Host "检测到宿主 Codex 系统级配置；它的优先级/约束不受便携 PROGRAMDATA 重定向控制：" -ForegroundColor Red
            foreach ($hostSystemFile in $hostSystemFiles) { Write-Host "  $hostSystemFile" -ForegroundColor Yellow }
            Write-Host '严格便携模式默认拒绝启动。确需采用这些管理员/系统策略时，在 env.local.ps1 设置 $env:CODEX_ALLOW_HOST_SYSTEM_CONFIG = "true"。' -ForegroundColor Yellow
            exit 3
        }
    }
} catch {
    Write-Host ("无法验证 Windows Codex 系统配置：" + $_.Exception.Message) -ForegroundColor Red
    exit 3
}

# 严格便携模式不继承宿主机的 Codex access token 或 workload identity，
# 防止它们覆盖启动菜单选择的 API Key / auth.json 认证方式。
foreach ($externalAuthName in @(
    "CODEX_API_KEY", "CODEX_ACCESS_TOKEN", "OPENAI_FEDERATION_RULE_ID",
    "OPENAI_IDENTITY_TOKEN_FILE", "OPENAI_WORKLOAD_IDENTITY_CONTEXT"
)) {
    Remove-Item "Env:$externalAuthName" -ErrorAction SilentlyContinue
}

foreach ($portableName in @(
    "CODEX_HOME", "CODEX_SQLITE_HOME", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "ALLUSERSPROFILE",
    "TEMP", "TMP", "TMPDIR", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME",
    "PIP_CACHE_DIR", "PYTHONUSERBASE", "NPM_CONFIG_CACHE", "NPM_CONFIG_PREFIX", "NPM_CONFIG_GLOBALCONFIG", "NPM_CONFIG_USERCONFIG", "NODE_REPL_HISTORY",
    "YARN_CACHE_FOLDER", "PNPM_HOME", "PNPM_STORE_DIR",
    "GRADLE_USER_HOME",
    "PYTHONPYCACHEPREFIX", "PSModuleAnalysisCachePath", "CODEX_INSTALL_DIR",
    "ANDROID_HOME", "ANDROID_SDK_ROOT", "ANDROID_USER_HOME", "ANDROID_SDK_HOME", "JAVA_HOME", "ADB_VENDOR_KEYS",
    "APKTOOL_FRAMEWORK_DIR", "FRIDA_CACHE_DIR", "MITMPROXY_HOME", "APPIUM_HOME", "APK_LAB_CACHE_DIR", "APK_LAB_TMP_DIR", "APK_LAB_JOBS_DIR"
)) {
    Assert-PortablePath $portableName ([Environment]::GetEnvironmentVariable($portableName))
}

$env:CODEX_ACCOUNT_JSON_AUTH = "false"
$CodexAuthDisplay = "API/env.ps1"
$UseAccountJsonLogin = $false
$UseBrowserLogin = $false
$BrowserLoginRequired = $false
$ActiveAuthPath = Join-Path $env:CODEX_HOME "auth.json"
$AccountJsonAuthPath = Join-Path $env:CODEX_HOME "auth-account-json.json"
$BrowserAuthPath = Join-Path $env:CODEX_HOME "auth-browser.json"
$AuthModePath = Join-Path $env:CODEX_HOME "mode"
foreach ($authStatePath in @($ActiveAuthPath, $AccountJsonAuthPath, $BrowserAuthPath, $AuthModePath)) {
    Assert-PortablePath "auth state" $authStatePath
}

function Test-CodexAuthFile {
    param([string]$Path, [switch]$RequireChatGpt)
    if (-not (Test-IsUnderDirectory -Path $Path -Directory $Root)) { return $false }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    try {
        $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        if ($item.Length -le 0 -or (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)) { return $false }
        $linkTypeProperty = $item.PSObject.Properties['LinkType']
        $linkType = if ($null -ne $linkTypeProperty) { [string]$linkTypeProperty.Value } else { "" }
        if ($linkType -eq 'HardLink' -or ([string]$item.Mode).Contains('l')) { return $false }
        $auth = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
        if ($null -eq $auth -or [string]::IsNullOrWhiteSpace([string]$auth.auth_mode)) { return $false }
        if ([string]$auth.auth_mode -eq "chatgpt") {
            if ($null -eq $auth.tokens) { return $false }
            return (-not [string]::IsNullOrWhiteSpace([string]$auth.tokens.refresh_token)) -or
                   (-not [string]::IsNullOrWhiteSpace([string]$auth.tokens.access_token))
        }
        if (-not $RequireChatGpt -and [string]$auth.auth_mode -eq "apikey") {
            return -not [string]::IsNullOrWhiteSpace([string]$auth.OPENAI_API_KEY)
        }
        return $false
    } catch {
        return $false
    }
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

function Move-TemporaryFileIntoPlace {
    param([string]$TemporaryPath, [string]$Destination)
    Assert-PortableRegularInputFile "temporary file" $TemporaryPath
    Assert-PortablePath "destination file" $Destination
    $backupPath = "$Destination.bak-$([System.Guid]::NewGuid().ToString('N'))"
    Assert-PortablePath "backup file" $backupPath
    if (Test-Path -LiteralPath $backupPath) { throw 'Recovery path already exists.' }
    $committed = $false
    try {
        if (Test-Path -LiteralPath $Destination) {
            Assert-PortableRegularInputFile "destination immediately before replace" $Destination
            [System.IO.File]::Replace($TemporaryPath, $Destination, $backupPath)
        } else {
            [System.IO.File]::Move($TemporaryPath, $Destination)
        }
        $committed = $true
    } finally {
        if ($committed) { Remove-Item -LiteralPath $backupPath -Force -ErrorAction SilentlyContinue }
        elseif (Test-Path -LiteralPath $backupPath) { Write-Warning 'Atomic replacement failed; recovery backup was retained.' }
    }
}

function Move-InvalidCodexAuthFile {
    param([string]$Path)
    Assert-PortablePath "invalid auth" $Path
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return }
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $quarantinePath = "$Path.invalid-$stamp-$([System.Guid]::NewGuid().ToString('N').Substring(0, 8))"
    Assert-PortablePath "invalid auth quarantine" $quarantinePath
    Move-Item -LiteralPath $Path -Destination $quarantinePath -Force
    Write-Host "检测到无效凭证，已保留为：$quarantinePath" -ForegroundColor Yellow
}

function Copy-CodexAuthAtomic {
    param([string]$Source, [string]$Destination, [switch]$FreshLogin)
    foreach ($mode in @('browser','account_json')) {
        $snapshot = if ($mode -eq 'browser') { $BrowserAuthPath } else { $AccountJsonAuthPath }
        if ($Source -eq $snapshot -and (Test-CodexLogoutBlocked $mode)) { throw 'Logged-out snapshot restore is blocked.' }
        if ($Destination -eq $snapshot -and -not $FreshLogin -and (Test-CodexLogoutBlocked $mode)) { throw 'Logged-out snapshot backup is blocked.' }
    }
    if ($FreshLogin -and ($Source -ne $ActiveAuthPath -or $Destination -notin @($BrowserAuthPath,$AccountJsonAuthPath))) { throw 'Invalid fresh-login snapshot transition.' }
    # This copy helper only moves the two official account snapshots.
    if (-not (Test-CodexAuthFile $Source -RequireChatGpt)) {
        throw "凭证文件无效，拒绝复制：$Source"
    }
    $temporaryPath = "$Destination.tmp-$([System.Guid]::NewGuid().ToString('N'))"
    $temporaryOwned = $false
    try {
        Assert-PortableRegularInputFile 'auth copy source' $Source
        Assert-PortablePath 'auth copy staging' $temporaryPath
        [IO.File]::Copy($Source, $temporaryPath, $false)
        $temporaryOwned = $true
        if (-not (Test-CodexAuthFile $temporaryPath -RequireChatGpt)) {
            throw "凭证临时副本校验失败：$temporaryPath"
        }
        Move-TemporaryFileIntoPlace -TemporaryPath $temporaryPath -Destination $Destination
    } finally {
        if ($temporaryOwned) { Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue }
    }
}

function Read-CodexAuthMode {
    if (-not (Test-IsUnderDirectory -Path $AuthModePath -Directory $Root)) { return "" }
    if (-not (Test-Path -LiteralPath $AuthModePath -PathType Leaf)) { return "" }
    Assert-PortableRegularInputFile "auth mode" $AuthModePath
    try {
        $value = [System.IO.File]::ReadAllText($AuthModePath, [System.Text.Encoding]::UTF8).Trim().ToLowerInvariant()
        if ($value -in @("api", "account_json", "browser")) { return $value }
    } catch {}
    return ""
}

function Write-CodexAuthMode {
    param([string]$Mode)
    if ($Mode -notin @("api", "account_json", "browser")) { throw "未知认证模式：$Mode" }
    $temporaryPath = "$AuthModePath.tmp-$([System.Guid]::NewGuid().ToString('N'))"
    $temporaryOwned = $false
    try {
        Write-PortableNewUtf8File -Path $temporaryPath -Text $Mode
        $temporaryOwned = $true
        Move-TemporaryFileIntoPlace -TemporaryPath $temporaryPath -Destination $AuthModePath
    } finally {
        if ($temporaryOwned) { Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue }
    }
}


function Remove-PortableAuthStateFile {
    param([string]$Path, [string]$Name)
    Assert-PortablePath $Name $Path
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return }
    Assert-PortableRegularInputFile $Name $Path
    Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
}

function Test-CodexAuthTransitionPending {
    $path = Join-Path $env:CODEX_HOME 'auth-transition.block'
    Assert-PortablePath 'auth transition' $path
    if (-not (Test-Path -LiteralPath $path)) { return $false }
    Assert-PortableRegularInputFile 'auth transition' $path
    return $true
}

function Start-CodexAuthTransition {
    if (Test-CodexAuthTransitionPending) { throw 'An unfinished auth transition must be recovered before switching modes.' }
    Write-PortableNewUtf8File -Path (Join-Path $env:CODEX_HOME 'auth-transition.block') -Text 'Auth transition not committed; do not recycle active credentials.'
}

function Complete-CodexAuthTransition {
    if (Test-CodexAuthTransitionPending) {
        Remove-PortableAuthStateFile -Path (Join-Path $env:CODEX_HOME 'auth-transition.block') -Name 'committed auth transition'
    }
}

function Repair-CodexAuthTransition {
    if (-not (Test-CodexAuthTransitionPending)) { return }
    # The active file can belong to either mode. Preserve it without attributing it
    # to a snapshot; File.Move never overwrites an existing recovery destination.
    if (Test-Path -LiteralPath $ActiveAuthPath) {
        Assert-PortableRegularInputFile 'uncommitted active auth' $ActiveAuthPath
        $recovery = $ActiveAuthPath + '.invalid-transition-' + [Guid]::NewGuid().ToString('N')
        Assert-PortablePath 'uncommitted auth recovery' $recovery
        [IO.File]::Move($ActiveAuthPath, $recovery)
        Write-Warning 'An unfinished authentication transition was recovered; ambiguous active credentials were preserved separately.'
    }
    Complete-CodexAuthTransition
}

function Get-CodexLogoutBlockPath {
    param([string]$Mode)
    if ($Mode -notin @('browser','account_json')) { throw 'Invalid logout block mode.' }
    return Join-Path $env:CODEX_HOME ('logout-' + $Mode + '.block')
}

function Test-CodexLogoutBlocked {
    param([string]$Mode)
    $path = Get-CodexLogoutBlockPath $Mode
    Assert-PortablePath 'logout block' $path
    if (-not (Test-Path -LiteralPath $path)) { return $false }
    Assert-PortableRegularInputFile 'logout block' $path
    return $true
}

function Set-CodexLogoutBlock {
    param([string]$Mode)
    if (Test-CodexLogoutBlocked $Mode) { return }
    $path = Get-CodexLogoutBlockPath $Mode
    $stream = [IO.File]::Open($path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes('Explicit logout: snapshot restore disabled until fresh login.')
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    } finally { $stream.Dispose() }
}

function Clear-CodexLogoutBlockAfterFreshLogin {
    param([string]$Mode)
    if (Test-CodexLogoutBlocked $Mode) {
        Remove-PortableAuthStateFile -Path (Get-CodexLogoutBlockPath $Mode) -Name 'logout block after fresh login'
    }
}

function Backup-LegacyAccountJsonAuthForBrowser {
    if ((Test-CodexLogoutBlocked 'browser') -or (Test-CodexLogoutBlocked 'account_json')) { return }
    # 兼容改造前的便携包：首次切到浏览器模式时，先保护可能属于选项 2 的旧 auth.json。
    if (-not (Test-CodexAuthFile $ActiveAuthPath -RequireChatGpt) -or (Test-CodexAuthFile $AccountJsonAuthPath -RequireChatGpt)) { return }

    $activeIsBrowserAuth = $false
    if (Test-CodexAuthFile $BrowserAuthPath -RequireChatGpt) {
        try {
            $activeIsBrowserAuth = (Get-FileHash -LiteralPath $ActiveAuthPath -Algorithm SHA256).Hash -eq
                                   (Get-FileHash -LiteralPath $BrowserAuthPath -Algorithm SHA256).Hash
        } catch {}
    }
    if (-not $activeIsBrowserAuth) {
        Copy-CodexAuthAtomic -Source $ActiveAuthPath -Destination $AccountJsonAuthPath
        Write-Host "已先备份原账号 JSON 登录凭证：$AccountJsonAuthPath" -ForegroundColor Green
    }
}

# 上次进程即使被强制关闭，活动 auth.json 仍可能包含刚刷新的 token。
# 在载入本次模式前，先按 mode 记录把它回收到正确的持久凭证文件。
Repair-CodexAuthTransition
$PreviousAuthMode = Read-CodexAuthMode
if ($PreviousAuthMode -in @('browser','account_json') -and (Test-CodexLogoutBlocked $PreviousAuthMode)) {
    Remove-PortableAuthStateFile -Path $ActiveAuthPath -Name 'active auth from logged-out mode'
}
# A syntactically valid API-key auth file is not an official account
# credential. Preserve a mismatched active file instead of overwriting
# a known account snapshot with it.
if (Test-CodexAuthFile $ActiveAuthPath -RequireChatGpt:($PreviousAuthMode -in @("account_json", "browser"))) {
    if ($PreviousAuthMode -eq "account_json") {
        Copy-CodexAuthAtomic -Source $ActiveAuthPath -Destination $AccountJsonAuthPath
    } elseif ($PreviousAuthMode -eq "browser") {
        Copy-CodexAuthAtomic -Source $ActiveAuthPath -Destination $BrowserAuthPath
    }
} elseif (Test-Path -LiteralPath $ActiveAuthPath -PathType Leaf) {
    Move-InvalidCodexAuthFile $ActiveAuthPath
}
foreach ($savedAuthPath in @($AccountJsonAuthPath, $BrowserAuthPath)) {
    if ((Test-Path -LiteralPath $savedAuthPath -PathType Leaf) -and -not (Test-CodexAuthFile $savedAuthPath -RequireChatGpt)) {
        Move-InvalidCodexAuthFile $savedAuthPath
    }
}

$ConfiguredAuthMode = $env:CODEX_AUTH_MODE
if ([string]::IsNullOrWhiteSpace($ConfiguredAuthMode)) { $ConfiguredAuthMode = "menu" }
$PortableMaintenanceMode = $false
$PortableExtensionsRequested = $false
$CodexLaunchArgs = New-Object System.Collections.Generic.List[string]
$portableOptionScan = $true
for ($argumentIndex = 0; $argumentIndex -lt $args.Count; $argumentIndex++) {
    $argument = [string]$args[$argumentIndex]
    if ($portableOptionScan -and $argument -eq "--") {
        $portableOptionScan = $false
        $CodexLaunchArgs.Add($argument)
        continue
    }
    if ($portableOptionScan -and $argument -eq "--portable-maintenance") {
        if (-not $PortableMaintenanceEntryAuthorized) {
            Write-Host "--portable-maintenance 只能由 启动Codex-维护模式.bat 进入；普通启动器拒绝升级写权限。" -ForegroundColor Red
            exit 3
        }
        $PortableMaintenanceMode = $true
        continue
    }
    if ($portableOptionScan -and $argument -eq "--portable-extensions") {
        $PortableExtensionsRequested = $true
        continue
    }
    if ($portableOptionScan -and $argument -eq "--portable-auth") {
        if ($argumentIndex + 1 -ge $args.Count) {
            Write-Host "--portable-auth 后需要填写认证模式。" -ForegroundColor Red
            exit 1
        }
        $argumentIndex++
        $ConfiguredAuthMode = [string]$args[$argumentIndex]
        continue
    }
    if ($portableOptionScan -and $argument.StartsWith("--portable-auth=", [System.StringComparison]::OrdinalIgnoreCase)) {
        $ConfiguredAuthMode = $argument.Substring("--portable-auth=".Length)
        continue
    }
    $CodexLaunchArgs.Add($argument)
}
$PortableExtensionPolicy = Get-PortableExtensionPolicy -TaskRequested $PortableExtensionsRequested -PluginsValue $env:CODEX_ENABLE_PLUGINS -UserMcpValue $env:CODEX_PORTABLE_ALLOW_USER_MCP
$AllowUserMcp = $PortableExtensionPolicy.UserMcpEnabled
$ConfiguredAuthMode = $ConfiguredAuthMode.Trim().ToLowerInvariant()
if ($ConfiguredAuthMode -notin @("menu", "last", "api", "account_json", "browser")) {
    Write-Host "CODEX_AUTH_MODE 只支持 menu / last / api / account_json / browser：$ConfiguredAuthMode" -ForegroundColor Red
    exit 1
}

# 普通模式的持久缓存也不能成为跨会话代码注入点。Python pycache、Gradle
# user-home、npm/yarn/pnpm store 等都可能保存后续会话会加载或
# 执行的内容。因此它们在普通模式全部重定向到本次启动独有的 tmp 子目录；
# 维护模式才继续使用 cache 下的持久位置。
$PortableSessionState = $null
$script:PortableLifecycleExitCode = $null
try {
if (-not $PortableMaintenanceMode) {
    $PortableSessionState = Join-Path $PortableTmp ("session-state-" + [Guid]::NewGuid().ToString("N"))
    Assert-PortablePath "session runtime state" $PortableSessionState
    New-Item -ItemType Directory -Path $PortableSessionState -ErrorAction Stop | Out-Null
    Assert-PortablePath "session runtime state" $PortableSessionState

    $env:XDG_CACHE_HOME = Join-Path $PortableSessionState "xdg-cache"
    $env:XDG_STATE_HOME = Join-Path $PortableSessionState "xdg-state"
    $env:PIP_CACHE_DIR = Join-Path $PortableSessionState "pip"
    $env:PYTHONPYCACHEPREFIX = Join-Path $PortableSessionState "pycache"
    $env:NPM_CONFIG_CACHE = Join-Path $PortableSessionState "npm"
    $env:NODE_REPL_HISTORY = Join-Path $PortableSessionState "node-repl-history"
    $env:YARN_CACHE_FOLDER = Join-Path $PortableSessionState "yarn"
    $env:PNPM_STORE_DIR = Join-Path $PortableSessionState "pnpm-store"
    $env:GRADLE_USER_HOME = Join-Path $PortableSessionState "gradle"
    $env:MAVEN_OPTS = "-Dmaven.repo.local=`"" + (Join-Path $PortableSessionState "maven") + "`""
    $env:PSModuleAnalysisCachePath = Join-Path $PortableSessionState "powershell\ModuleAnalysisCache"
    $env:APKTOOL_FRAMEWORK_DIR = Join-Path $PortableSessionState "android\apktool-framework"
    $env:FRIDA_CACHE_DIR = Join-Path $PortableSessionState "android\frida"
    $env:MITMPROXY_HOME = Join-Path $PortableSessionState "android\mitmproxy"
    $env:APPIUM_HOME = Join-Path $PortableSessionState "android\appium"
    $env:APK_LAB_CACHE_DIR = Join-Path $PortableSessionState "android\apk-lab"
    $env:APK_LAB_TMP_DIR = Join-Path $PortableSessionState "android\tmp"
}

# From session-state creation onward, the outer lifecycle guard covers all
# configuration, bridge/login initialization, Codex execution, and early exit paths.

# 严格便携入口不允许 Codex CLI 的高优先级参数把刚生成的安全 config.toml 覆盖掉。
# 这里只约束从本启动器透传的用户参数；启动器内部的 `debug models --bundled` 不经过此列表。
function Stop-UnsafeCodexCliArgument {
    param([string]$Argument,[string]$Reason)
    Write-Host "严格便携模式拒绝 Codex 参数：$Argument" -ForegroundColor Red
    Write-Host $Reason -ForegroundColor Yellow
    Write-Host "如确实需要绕过便携边界，请不要经由本严格启动器执行。" -ForegroundColor Yellow
    exit 3
}

function Assert-WindowsSafeCliPathLexical {
    param([string]$OptionName,[string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { Stop-UnsafeCodexCliArgument $OptionName "$OptionName requires a portable file path." }
    $raw = [string]$Value
    if ($raw -ne $raw.Trim()) {
        Stop-UnsafeCodexCliArgument "$OptionName=$Value" "Leading/trailing whitespace in CLI file paths is not allowed."
    }
    if ($raw.StartsWith('\\?\') -or $raw.StartsWith('\\.\')) {
        Stop-UnsafeCodexCliArgument "$OptionName=$Value" "Win32 device/extended path syntax is not allowed."
    }
    $rawWindows = $raw.Replace('/', '\')
    $rawRelative = $rawWindows
    try {
        if ([IO.Path]::IsPathRooted($rawWindows)) {
            $rawPathRoot = [IO.Path]::GetPathRoot($rawWindows)
            if (-not [string]::IsNullOrEmpty($rawPathRoot)) { $rawRelative = $rawWindows.Substring($rawPathRoot.Length) }
        }
    } catch {
        Stop-UnsafeCodexCliArgument "$OptionName=$Value" "The raw path cannot be parsed safely."
    }
    foreach ($pathSegment in @($rawRelative -split '\\')) {
        if ([string]::IsNullOrEmpty($pathSegment) -or $pathSegment -eq '.' -or $pathSegment -eq '..') { continue }
        if ($pathSegment.Contains(':')) {
            Stop-UnsafeCodexCliArgument "$OptionName=$Value" "NTFS alternate-data-stream/device path syntax is not allowed."
        }
        if ($pathSegment.EndsWith('.') -or $pathSegment.EndsWith(' ')) {
            Stop-UnsafeCodexCliArgument "$OptionName=$Value" "Windows trailing-dot/space path aliases are not allowed."
        }
        $deviceStem = (($pathSegment.TrimEnd(' ','.') -split '\.', 2)[0]).ToUpperInvariant()
        if ($deviceStem -in @('CON','PRN','AUX','NUL','CLOCK$','CONIN$','CONOUT$','COM1','COM2','COM3','COM4','COM5','COM6','COM7','COM8','COM9','LPT1','LPT2','LPT3','LPT4','LPT5','LPT6','LPT7','LPT8','LPT9')) {
            Stop-UnsafeCodexCliArgument "$OptionName=$Value" "Windows reserved device names are not allowed in CLI file paths."
        }
    }
}

function Resolve-PortableCliPath {
    param([string]$OptionName,[string]$Value,[bool]$MustExist)
    Assert-WindowsSafeCliPathLexical -OptionName $OptionName -Value $Value
    $candidate = [string]$Value
    if (-not [IO.Path]::IsPathRooted($candidate)) { $candidate = Join-Path $PortableWork $candidate }
    try { $candidate = [IO.Path]::GetFullPath($candidate) } catch { Stop-UnsafeCodexCliArgument "$OptionName=$Value" "Path normalization failed." }
    Assert-PortablePath "CLI $OptionName" $candidate

    # These files are read/written by the Codex host process, not only by sandboxed shell commands.
    # SAFE mode therefore limits them to user-data roots as well. Maintenance mode is explicit opt-in.
    if (-not $PortableMaintenanceMode -and
        -not (Test-IsUnderDirectory -Path $candidate -Directory $PortableWork) -and
        -not (Test-IsUnderDirectory -Path $candidate -Directory $PortableTmp)) {
        Stop-UnsafeCodexCliArgument "$OptionName=$Value" "SAFE mode only allows CLI file inputs/outputs under work or tmp."
    }

    if ($MustExist) {
        Assert-PortableRegularInputFile "CLI $OptionName" $candidate
    } else {
        $parent = Split-Path -Parent $candidate
        if ([string]::IsNullOrWhiteSpace($parent) -or -not (Test-Path -LiteralPath $parent -PathType Container)) {
            Stop-UnsafeCodexCliArgument "$OptionName=$Value" "The output file parent directory must already exist inside the current portable data roots."
        }
        Assert-PortablePath "CLI $OptionName parent" $parent
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            try {
                $existing = Get-Item -LiteralPath $candidate -Force -ErrorAction Stop
                if (($existing.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                    Stop-UnsafeCodexCliArgument "$OptionName=$Value" "Existing output file is a reparse point/link."
                }
                $linkTypeProperty = $existing.PSObject.Properties['LinkType']
                $linkType = if ($null -ne $linkTypeProperty) { [string]$linkTypeProperty.Value } else { "" }
                if ($linkType -eq 'HardLink' -or ([string]$existing.Mode).Contains('l')) {
                    Stop-UnsafeCodexCliArgument "$OptionName=$Value" "Existing output file is a hardlink/link; refusing host-process in-place writes to a shared file object."
                }
            } catch {
                Stop-UnsafeCodexCliArgument "$OptionName=$Value" "Unable to verify the existing output file safely."
            }
        }
    }
    return $candidate
}

function Test-AndNormalizeCodexCliArgs {
    param([System.Collections.Generic.List[string]]$InputArgs)
    $result = New-Object System.Collections.Generic.List[string]
    $scanOptions = $true
    $rootCommand = ""
    $rootIsPrompt = $false
    $pluginSubcommand = ""
    $expectModelValue = $false
    $script:CliModelOverride = ""
    $script:CodexRootCommand = ""
    $script:PortableLogoutMode = ""
    $expectOutputKind = ""

    for ($i = 0; $i -lt $InputArgs.Count; $i++) {
        $arg = [string]$InputArgs[$i]

        if (-not $scanOptions) { $result.Add($arg); continue }
        if ($arg -eq '--') { $scanOptions = $false; $result.Add($arg); continue }

        if ($expectModelValue) {
            $expectModelValue = $false
            if ([string]::IsNullOrWhiteSpace($arg)) { Stop-UnsafeCodexCliArgument '--model' '--model/-m 的模型值不能为空。' }
            $script:CliModelOverride = $arg
            $result.Add($arg)
            continue
        }
        if (-not [string]::IsNullOrWhiteSpace($expectOutputKind)) {
            $kind = $expectOutputKind
            $expectOutputKind = ""
            $mustExist = ($kind -eq '--output-schema')
            $normalizedCliPath = Resolve-PortableCliPath -OptionName $kind -Value $arg -MustExist $mustExist
            $result.Add($normalizedCliPath)
            continue
        }

        $lower = $arg.ToLowerInvariant()

        # Config / approval / sandbox / cwd / provider / feature overrides.
        # -c and -C both lowercase to -c here; both are intentionally blocked.
        if ($lower -in @('-c','--config','-s','--sandbox','-a','--ask-for-approval','-p','--profile','--cd','--add-dir','--local-provider')) {
            Stop-UnsafeCodexCliArgument $arg '该参数可覆盖便携包固定的配置、审批、沙箱、工作目录或 Provider。'
        }
        if ($lower.StartsWith('--config=') -or $lower.StartsWith('--sandbox=') -or $lower.StartsWith('--ask-for-approval=') -or
            $lower.StartsWith('--profile=') -or $lower.StartsWith('--cd=') -or $lower.StartsWith('--add-dir=') -or $lower.StartsWith('--local-provider=') -or
            (($lower.StartsWith('-c') -or $lower.StartsWith('-s') -or $lower.StartsWith('-a') -or $lower.StartsWith('-p')) -and $lower.Length -gt 2)) {
            Stop-UnsafeCodexCliArgument $arg '该参数可覆盖便携包固定的配置、审批、沙箱、工作目录或 Provider。'
        }
        if ($lower -in @('--enable','--disable') -or $lower.StartsWith('--enable=') -or $lower.StartsWith('--disable=')) {
            Stop-UnsafeCodexCliArgument $arg '--enable/--disable 等价于高优先级 features 配置覆盖。'
        }
        if ($lower -in @('--dangerously-bypass-approvals-and-sandbox','--yolo','--dangerously-bypass-hook-trust','--approve-for-me','--not-so-yolo','--full-auto','--oss','--ignore-user-config','--ignore-rules')) {
            Stop-UnsafeCodexCliArgument $arg '该参数会绕过或改变严格便携的配置/审批/沙箱/信任规则。'
        }
        if ($lower -in @('--remote','--remote-auth-token-env') -or $lower.StartsWith('--remote=') -or $lower.StartsWith('--remote-auth-token-env=')) {
            Stop-UnsafeCodexCliArgument $arg '严格便携入口不透传远程控制覆盖参数。'
        }

        # `-m` is not globally synonymous with model after every subcommand.
        # For example, `codex plugin add ... -m NAME` uses -m for --marketplace.
        # Treat it as a model override only in scopes that actually flatten Codex
        # SharedCliOptions/TuiCli; otherwise leave the token to the subcommand parser.
        $modelOptionApplies = $rootIsPrompt -or [string]::IsNullOrWhiteSpace($rootCommand) -or
                              $rootCommand -in @('exec','e','resume','fork','queue','archive','delete','unarchive')
        if ($modelOptionApplies) {
            # Model consumes exactly one following value; do this before root-subcommand
            # detection so `-m update` before a root command is a model named update.
            if ($lower -in @('-m','--model')) {
                $expectModelValue = $true
                $result.Add($arg)
                continue
            }
            if ($lower.StartsWith('--model=')) {
                $modelValue = $arg.Substring('--model='.Length)
                if ([string]::IsNullOrWhiteSpace($modelValue)) { Stop-UnsafeCodexCliArgument $arg '--model 的模型值不能为空。' }
                $script:CliModelOverride = $modelValue
                $result.Add($arg)
                continue
            }
            if ($lower.StartsWith('-m') -and $lower.Length -gt 2) {
                # An attached '=' separates the option from its value.
                $modelValue = if ($lower.StartsWith('-m=')) { $arg.Substring(3) } else { $arg.Substring(2) }
                if ([string]::IsNullOrWhiteSpace($modelValue)) { Stop-UnsafeCodexCliArgument $arg '-m 的模型值不能为空。' }
                $script:CliModelOverride = $modelValue
                $result.Add($arg)
                continue
            }
        }

        # --image in Codex 0.170.0 accepts 1.. values. Detached form is ambiguous to a wrapper,
        # so strict mode only accepts an attached comma-delimited list and validates every item.
        $imagePayload = $null
        if ($lower.StartsWith('--image=')) { $imagePayload = $arg.Substring('--image='.Length) }
        elseif ($lower.StartsWith('-i=')) { $imagePayload = $arg.Substring(3) }
        elseif ($lower.StartsWith('-i') -and $arg.Length -gt 2) { $imagePayload = $arg.Substring(2) }
        elseif ($lower -in @('-i','--image')) {
            Stop-UnsafeCodexCliArgument $arg '为避免 1.. 多值参数边界歧义，请使用 --image=包内图1,包内图2（或 -i=...）。'
        }
        if ($null -ne $imagePayload) {
            $imageItems = @($imagePayload -split ',' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
            if ($imageItems.Count -eq 0) { Stop-UnsafeCodexCliArgument $arg '--image 没有有效路径。' }
            $normalizedImageItems = New-Object System.Collections.Generic.List[string]
            foreach ($imageItem in $imageItems) {
                $normalizedImageItems.Add((Resolve-PortableCliPath -OptionName '--image' -Value $imageItem -MustExist $true))
            }
            $result.Add('--image=' + (($normalizedImageItems.ToArray()) -join ','))
            continue
        }

        # Root subcommand: only the first positional token before -- can be one.
        if ([string]::IsNullOrWhiteSpace($rootCommand) -and -not $arg.StartsWith('-')) {
            $rootCommand = $lower
            # A positional TUI prompt is not a subcommand; later -m still applies.
            # Match the pinned CLI command spelling case-sensitively, not prompt text.
            $rootIsPrompt = $arg -cnotin @('agents','tcp-tunnel','exec','e','review','login','logout','mcp','plugin','app-server','remote-control','app','completion','update','doctor','sandbox','debug','execpolicy','apply','a','resume','queue','archive','delete','migrate-rollouts','migrate-nfs-db','unarchive','fork','cloud','cloud-tasks','responses-api-proxy','stdio-to-uds','exec-server','features','mcp-server','help')
            if ($rootIsPrompt) {
                # A TUI prompt must not enter subcommand guards or exit cleanup.
                $rootCommand = '__portable_tui_prompt__'
                $script:CodexRootCommand = ''
                $result.Add($arg)
                continue
            }
            $script:CodexRootCommand = $rootCommand
            if ($rootCommand -in @('tcp-tunnel','app','app-server','update','sandbox','debug','execpolicy','agents','remote-control','responses-api-proxy','stdio-to-uds','exec-server','mcp-server','features','login')) {
                Stop-UnsafeCodexCliArgument $arg '该 Codex 子命令具有安装/更新、直接沙箱调试、隐藏规则文件读取、共享 daemon、远程控制、服务端模式、非标准宿主 I/O、会修改由 env.ps1 管理的固定 feature 配置，或会绕过便携包受控登录流程，因此不从严格便携入口开放。官方账号登录请使用便携启动器的认证菜单。'
            }
            if ($rootCommand -eq 'logout') {
                $logoutMode = $ConfiguredAuthMode
                if ($logoutMode -eq 'last') { $logoutMode = $PreviousAuthMode }
                if ($logoutMode -notin @('browser','account_json')) {
                    Stop-UnsafeCodexCliArgument $arg '便携 logout 必须明确指定要退出的持久凭证，例如 --portable-auth browser logout 或 --portable-auth account_json logout。这样才能同时撤销官方登录并删除对应便携副本。'
                }
                $script:PortableLogoutMode = $logoutMode
            }
            if (-not $PortableMaintenanceMode -and $rootCommand -in @('mcp','plugin')) {
                Stop-UnsafeCodexCliArgument $arg '该 Codex 子命令可直接修改 MCP 或 Plugin 状态；SAFE 模式禁止绕过便携配置持久化边界。请使用维护模式。'
            }
            if ($rootCommand -in @('mcp','plugin')) {
                [void](Get-PortableExtensionCommandNamespace -Command $rootCommand -AllowedNamespaces $PortableExtensionPolicy.AllowedNamespaces)
            }
            $result.Add($arg)
            continue
        }

        # The official plugin marketplace command accepts local/Git marketplace
        # sources and persists them under [marketplaces.*].  A local source may
        # point outside this portable package, which would re-introduce host code
        # into later plugin discovery.  Keep plugin add/list/remove available in
        # maintenance mode, but do not expose marketplace source management through
        # the strict portable wrapper.
        if ($rootCommand -eq 'plugin' -and [string]::IsNullOrWhiteSpace($pluginSubcommand) -and -not $arg.StartsWith('-')) {
            $pluginSubcommand = $lower
            if ($pluginSubcommand -eq 'marketplace') {
                Stop-UnsafeCodexCliArgument $arg '严格便携入口不允许 codex plugin marketplace 添加/升级/移除包外 Marketplace 来源；请只使用本包已配置的 Marketplace，或在受控维护流程中人工审核后修改包内配置。'
            }
            $result.Add($arg)
            continue
        }

        # exec/e file-valued options remain available, but paths must stay inside the package.
        if ($rootCommand -in @('exec','e')) {
            if ($lower -in @('-o','--output-last-message','--output-schema')) {
                $expectOutputKind = $(if ($lower -eq '--output-schema') { '--output-schema' } else { '--output-last-message' })
                $result.Add($arg)
                continue
            }
            if ($lower.StartsWith('--output-last-message=')) {
                $normalizedCliPath = Resolve-PortableCliPath -OptionName '--output-last-message' -Value $arg.Substring('--output-last-message='.Length) -MustExist $false
                $result.Add('--output-last-message=' + $normalizedCliPath)
                continue
            } elseif ($lower.StartsWith('--output-schema=')) {
                $normalizedCliPath = Resolve-PortableCliPath -OptionName '--output-schema' -Value $arg.Substring('--output-schema='.Length) -MustExist $true
                $result.Add('--output-schema=' + $normalizedCliPath)
                continue
            } elseif ($lower.StartsWith('-o=') -and $arg.Length -gt 3) {
                $normalizedCliPath = Resolve-PortableCliPath -OptionName '--output-last-message' -Value $arg.Substring(3) -MustExist $false
                $result.Add('-o=' + $normalizedCliPath)
                continue
            } elseif ($lower.StartsWith('-o') -and $arg.Length -gt 2) {
                $normalizedCliPath = Resolve-PortableCliPath -OptionName '--output-last-message' -Value $arg.Substring(2) -MustExist $false
                $result.Add('-o=' + $normalizedCliPath)
                continue
            }
        }
        $result.Add($arg)
    }

    if ($expectModelValue) { Stop-UnsafeCodexCliArgument '--model' '--model/-m 缺少模型值。' }
    if (-not [string]::IsNullOrWhiteSpace($expectOutputKind)) { Stop-UnsafeCodexCliArgument $expectOutputKind "$expectOutputKind 缺少路径值。" }
    return $result
}


# Launcher-only privilege marker must never flow into codex.exe or tool children.
Remove-Item Env:CODEX_PORTABLE_MAINTENANCE_LAUNCHER -ErrorAction SilentlyContinue
$CodexLaunchArgs = Test-AndNormalizeCodexCliArgs -InputArgs $CodexLaunchArgs

# ------------------------------------------------------------
# 3.4 定位 codex.exe，并读取当前模型支持的思考档位
# ------------------------------------------------------------
# All codex.exe invocations, including preflight debug/login calls, use the same
# minimal portable process environment. This closes the gap where a pre-launch
# Codex child could otherwise inherit unrelated host variables.
function Get-ConfiguredHeaderEnvironmentVariableNames {
    $names = New-Object System.Collections.Generic.HashSet[string] ([System.StringComparer]::OrdinalIgnoreCase)
    $table = [string]$env:CODEX_ENV_HTTP_HEADERS_TOML
    if ([string]::IsNullOrWhiteSpace($table)) { return @() }
    # env_http_headers values are environment-variable names, e.g. { "X-Token" = "MY_TOKEN" }.
    foreach ($match in [regex]::Matches($table, '=\s*["'']([A-Za-z_][A-Za-z0-9_]*)["'']')) {
        [void]$names.Add($match.Groups[1].Value)
    }
    return @($names)
}

function Set-ProcessEnvironmentValue {
    param([System.Diagnostics.ProcessStartInfo]$ProcessStartInfo,[string]$Name,[string]$Value)
    if ($null -eq $Value -or [string]::IsNullOrWhiteSpace($Name)) { return }
    try { $ProcessStartInfo.EnvironmentVariables.Set_Item($Name, $Value) } catch {
        try { $ProcessStartInfo.Environment[$Name] = $Value } catch {}
    }
}

function Set-CodexChildPortableEnvironment {
    param([System.Diagnostics.ProcessStartInfo]$ProcessStartInfo)
    try { $ProcessStartInfo.EnvironmentVariables.Clear() } catch { try { $ProcessStartInfo.Environment.Clear() } catch {} }

    Reset-CodexTrustedSystemEnvironment
    foreach ($name in @("SystemRoot","WINDIR","SystemDrive","ComSpec","PATHEXT","OS","PROCESSOR_ARCHITECTURE","PROCESSOR_IDENTIFIER","NUMBER_OF_PROCESSORS","USERNAME","COMPUTERNAME")) {
        Set-ProcessEnvironmentValue $ProcessStartInfo $name ([Environment]::GetEnvironmentVariable($name))
    }

    $fixed = @(
        "PATH","CODEX_HOME","CODEX_SQLITE_HOME","HOME","USERPROFILE","HOMEDRIVE","HOMEPATH","APPDATA","LOCALAPPDATA","PROGRAMDATA","ALLUSERSPROFILE",
        "TEMP","TMP","TMPDIR","XDG_CACHE_HOME","XDG_CONFIG_HOME","XDG_DATA_HOME","XDG_STATE_HOME","PIP_CONFIG_FILE","PIP_CACHE_DIR","PYTHONUSERBASE",
        "NPM_CONFIG_CACHE","NPM_CONFIG_PREFIX","NPM_CONFIG_GLOBALCONFIG","NPM_CONFIG_USERCONFIG","NODE_REPL_HISTORY","YARN_CACHE_FOLDER","PNPM_HOME","PNPM_STORE_DIR",
        "GRADLE_USER_HOME","MAVEN_OPTS","POWERSHELL_TELEMETRY_OPTOUT","PSModuleAnalysisCachePath","PSModulePath",
        "PYTHONPYCACHEPREFIX","GIT_CONFIG_NOSYSTEM","CODEX_INSTALL_DIR","CODEX_PYTHON",
        "ANDROID_HOME","ANDROID_SDK_ROOT","ANDROID_USER_HOME","ANDROID_SDK_HOME","JAVA_HOME","ADB_VENDOR_KEYS","APKTOOL_FRAMEWORK_DIR","FRIDA_CACHE_DIR","MITMPROXY_HOME","APPIUM_HOME",
        "APK_LAB_CACHE_DIR","APK_LAB_TMP_DIR","APK_LAB_JOBS_DIR","HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","NO_PROXY","http_proxy","https_proxy","all_proxy","no_proxy"
    )
    $headerEnvNames = @(Get-ConfiguredHeaderEnvironmentVariableNames)
    $names = New-Object System.Collections.Generic.HashSet[string] ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($n in @($fixed + $headerEnvNames)) { if (-not [string]::IsNullOrWhiteSpace($n)) { [void]$names.Add($n) } }
    # CODEX_/OPENAI_ values were scrubbed before package config loaded, so any value
    # present now is package/dynamic state. Arbitrary host variables are not inherited.
    Get-ChildItem Env: | Where-Object { $_.Name -match '^(?i:CODEX_|OPENAI_)' } | ForEach-Object { [void]$names.Add($_.Name) }
    foreach ($name in $names) {
        $effective = [Environment]::GetEnvironmentVariable($name)
        if ($name -in @('ANDROID_HOME','ANDROID_SDK_ROOT','JAVA_HOME') -and
            [string]::IsNullOrWhiteSpace($effective)) { continue }
        Set-ProcessEnvironmentValue $ProcessStartInfo $name $effective
    }
}

function New-CodexChildStartInfo {
    param([object[]]$LaunchArgs,[switch]$RedirectOutput)
    Assert-PinnedRuntimePackage
    Assert-PinnedCodeModeHost
    Assert-PinnedCodexExecutable
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $CodexExe
    $psi.WorkingDirectory = $PortableWork
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $RedirectOutput.IsPresent
    if ($RedirectOutput) {
        $psi.RedirectStandardInput = $true
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        try { $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
        try { $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8 } catch {}
    }
    Set-CodexChildPortableEnvironment -ProcessStartInfo $psi
    $psi.Arguments = (@($LaunchArgs) | ForEach-Object { ConvertTo-WindowsCommandLineArgument ([string]$_) }) -join " "
    return $psi
}

function Import-CodexProcessSupervisor {
    $supervisor = Join-Path $Root 'tool\portable-process.ps1'
    Assert-PortableRegularInputFile 'process supervisor' $supervisor
    # Dot-source in script scope because this loader is itself a function.
    . $supervisor
    Set-Item -Path Function:script:Initialize-PortableProcessJob -Value ${function:Initialize-PortableProcessJob}
    Set-Item -Path Function:script:Invoke-PortableProcess -Value ${function:Invoke-PortableProcess}
}

function Invoke-CodexChildCapture {
    param([object[]]$LaunchArgs)
    $psi = New-CodexChildStartInfo -LaunchArgs $LaunchArgs -RedirectOutput
    Import-CodexProcessSupervisor
    return Invoke-PortableProcess -StartInfo $psi -PackageRoot $Root -TimeoutMs 30000 -MaxOutputChars 16777216
}

function Invoke-CodexChildInteractive {
    param([object[]]$LaunchArgs)
    $psi = New-CodexChildStartInfo -LaunchArgs $LaunchArgs
    Import-CodexProcessSupervisor
    return (Invoke-PortableProcess -StartInfo $psi -PackageRoot $Root -TimeoutMs 0).ExitCode
}

function Get-ModelReasoningMenuInfo {
    param([string]$ModelSlug)

    $catalogs = New-Object System.Collections.Generic.List[object]
    $providerModeForCatalog = [string]$env:CODEX_PROVIDER_MODE
    $useOfficialCatalog = $UseAccountJsonLogin -or $UseBrowserLogin -or ($providerModeForCatalog -eq "official_chatgpt")

    if ($useOfficialCatalog) {
        try {
            $capture = Invoke-CodexChildCapture -LaunchArgs @("debug","models","--bundled")
            $raw = [string]$capture.StdOut
            if ($capture.ExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace($raw)) {
                $catalogs.Add([pscustomobject]@{ Source = "Codex 内置模型目录"; Data = ($raw | ConvertFrom-Json) })
            }
        } catch {}
    }

    $configuredCatalog = $env:CODEX_MODEL_CATALOG_JSON
    if ($useOfficialCatalog -and -not [string]::IsNullOrWhiteSpace($configuredCatalog)) {
        if (-not [System.IO.Path]::IsPathRooted($configuredCatalog)) {
            $configuredCatalog = Join-Path $Root $configuredCatalog
        }
        if (Test-Path -LiteralPath $configuredCatalog -PathType Leaf) {
            try {
                Assert-PortableRegularInputFile "reasoning menu catalog" $configuredCatalog
                $raw = [System.IO.File]::ReadAllText($configuredCatalog, [System.Text.Encoding]::UTF8)
                $catalogs.Add([pscustomobject]@{ Source = "本地模型目录"; Data = ($raw | ConvertFrom-Json) })
            } catch {}
        }
    }

    foreach ($catalog in $catalogs) {
        $entry = $catalog.Data.models | Where-Object { $_.slug -eq $ModelSlug } | Select-Object -First 1
        if ($null -eq $entry) { continue }
        $levels = @($entry.supported_reasoning_levels | ForEach-Object { [string]$_.effort } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)
        if ($levels.Count -eq 0) { continue }
        $catalogDefault = [string]$entry.default_reasoning_level
        if ([string]::IsNullOrWhiteSpace($catalogDefault) -or $catalogDefault -notin $levels) {
            $catalogDefault = if ("medium" -in $levels) { "medium" } else { $levels[0] }
        }
        return [pscustomobject]@{ Levels = $levels; Default = $catalogDefault; Source = $catalog.Source }
    }

    # 仅在官方目录未能读取时，为两种新模型提供保守菜单兜底；正常情况以客户端目录为准。
    if ($useOfficialCatalog -and $ModelSlug -eq "gpt-6-sol") {
        return [pscustomobject]@{ Levels = @("low", "medium", "high", "xhigh", "max", "ultra"); Default = "medium"; Source = "GPT-6 Sol 兼容回退" }
    }
    if ($useOfficialCatalog -and $ModelSlug -eq "gpt-6-luna") {
        return [pscustomobject]@{ Levels = @("low", "medium", "high", "xhigh", "max"); Default = "medium"; Source = "GPT-6 Luna 兼容回退" }
    }
    # 第三方/本地模型默认不主动发送 reasoning effort；只有用户明确选择才发送。
    return [pscustomobject]@{
        Levels = @("minimal", "low", "medium", "high", "xhigh", "max", "ultra")
        Default = ""
        Source = $(if ($useOfficialCatalog) { "通用回退（官方目录无匹配项）" } else { "第三方/本地模型（默认不指定 effort）" })
    }
}

function Normalize-ReasoningEffortValue {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return "" }
    $trimmed = $Value.Trim()
    foreach ($known in @("minimal", "low", "medium", "high", "xhigh", "max", "ultra")) {
        if ($trimmed.Equals($known, [System.StringComparison]::OrdinalIgnoreCase)) { return $known }
    }
    return $trimmed
}

# ------------------------------------------------------------
# 3.5 交互式启动选项（仅启用交互、双击 / 无参数启动时弹出；exec 带任务时自动跳过）
# ------------------------------------------------------------
$StartupInteractiveEnabled = Convert-ToFeatureBool $env:CODEX_STARTUP_INTERACTIVE $true
$ReasoningSettingSource = "env.ps1"
$ShowStartupMenu = $StartupInteractiveEnabled -and $CodexLaunchArgs.Count -eq 0 -and [Environment]::UserInteractive
if ($ShowStartupMenu) {
    # 计算各项“回车=默认”实际会用到的值(取自 env.ps1),显示给用户看
    $MenuTruthy = @("1","true","yes","y","on")
    $DefNet      = if ((-not [string]::IsNullOrWhiteSpace($env:CODEX_SANDBOX_NETWORK_ACCESS)) -and ($env:CODEX_SANDBOX_NETWORK_ACCESS.Trim().ToLowerInvariant() -in $MenuTruthy)) { "开启" } else { "关闭" }
    $DefProxy    = if ((-not [string]::IsNullOrWhiteSpace($env:CODEX_PROXY_ENABLED)) -and ($env:CODEX_PROXY_ENABLED.Trim().ToLowerInvariant() -in $MenuTruthy)) { "开启" } else { "关闭" }
    $DefProxySub = if ((-not [string]::IsNullOrWhiteSpace($env:CODEX_PROXY_FOR_SUBPROCESS)) -and ($env:CODEX_PROXY_FOR_SUBPROCESS.Trim().ToLowerInvariant() -in $MenuTruthy)) { "是" } else { "否" }

    Write-Host ""
    Write-Host "登录方式:" -ForegroundColor Cyan
    Write-Host "  1) API 登录(沿用 env.ps1)" -ForegroundColor Cyan
    Write-Host "  2) 账号 JSON 导入登录(login_json)" -ForegroundColor Cyan
    $OfficialLoginLabel = if ($BrowserLoginFlow -eq 'system_browser') { '系统浏览器，已显式启用' } else { '设备码' }
    Write-Host "  3) 官方账号登录($OfficialLoginLabel)   [回车=默认: API]" -ForegroundColor Cyan
    $LoginChoice = Read-Host "请选择登录方式 (1/2/3, 回车=API)"
    if ($LoginChoice.Trim() -eq "2") {
        $UseAccountJsonLogin = $true
        $env:CODEX_ACCOUNT_JSON_AUTH = "true"
        $CodexAuthDisplay = "login_json"
        Start-CodexAuthTransition
        if (Test-CodexLogoutBlocked 'account_json') {
            Remove-PortableAuthStateFile -Path $ActiveAuthPath -Name 'old active auth before fresh JSON selection'
        }
        if (-not (Test-CodexLogoutBlocked 'account_json') -and (Test-Path -LiteralPath $AccountJsonAuthPath -PathType Leaf) -and ((Get-Item -LiteralPath $AccountJsonAuthPath).Length -gt 0)) {
            Copy-CodexAuthAtomic -Source $AccountJsonAuthPath -Destination $ActiveAuthPath
            Write-Host "已切回账号 JSON 登录凭证：$AccountJsonAuthPath" -ForegroundColor Green
        }
        $env:CODEX_PROVIDER_MODE = "official_chatgpt"
        $env:CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
        $env:OPENAI_BASE_URL = $env:CODEX_BASE_URL
        $env:CODEX_PROXY_BYPASS_MODEL = "false"
        if ([string]::IsNullOrWhiteSpace($env:CODEX_PROXY_PROTOCOL)) { $env:CODEX_PROXY_PROTOCOL = "socks5" }
        if ([string]::IsNullOrWhiteSpace($env:CODEX_PROXY_HOST)) { $env:CODEX_PROXY_HOST = "127.0.0.1" }
        if ([string]::IsNullOrWhiteSpace($env:CODEX_PROXY_PORT)) { $env:CODEX_PROXY_PORT = "10808" }

        $LoginJsonProxyMode = $env:CODEX_LOGIN_JSON_PROXY_MODE
        if ([string]::IsNullOrWhiteSpace($LoginJsonProxyMode)) { $LoginJsonProxyMode = "auto" }
        $LoginJsonProxyMode = $LoginJsonProxyMode.Trim().ToLowerInvariant()
        $UseLoginJsonProxy = $false
        if ($LoginJsonProxyMode -eq "proxy") {
            $UseLoginJsonProxy = $true
        } elseif ($LoginJsonProxyMode -eq "direct") {
            $UseLoginJsonProxy = $false
        } elseif ($LoginJsonProxyMode -eq "auto") {
            $UseLoginJsonProxy = ($DefProxy -eq "开启")
        } else {
            Write-Host "CODEX_LOGIN_JSON_PROXY_MODE 只支持 auto / direct / proxy：$LoginJsonProxyMode" -ForegroundColor Red
            exit 1
        }
        $JsonProxyDefault = if ($UseLoginJsonProxy) { "开启" } else { "关闭" }
        Write-Host ""
        Write-Host "账号 JSON 登录访问 ChatGPT 后端是否走本地代理:" -ForegroundColor Cyan
        Write-Host "  1) 关闭(直连/TUN)   2) 开启(本地代理)   [回车=默认: $JsonProxyDefault]" -ForegroundColor Cyan
        $JsonProxyChoice = Read-Host "请选择是否走本地代理 (1/2, 回车=默认: $JsonProxyDefault)"
        switch ($JsonProxyChoice.Trim()) {
            "1" { $UseLoginJsonProxy = $false }
            "2" { $UseLoginJsonProxy = $true }
            default { }
        }
        if ($UseLoginJsonProxy) {
            $LoginJsonProxyMode = "proxy"
            $env:CODEX_LOGIN_JSON_PROXY_MODE = "proxy"
            $env:CODEX_PROXY_ENABLED = "true"
            $env:CODEX_PROXY_BYPASS_MODEL = "false"
        } else {
            $LoginJsonProxyMode = "direct"
            $env:CODEX_LOGIN_JSON_PROXY_MODE = "direct"
            $env:CODEX_PROXY_ENABLED = "false"
        }
        Write-Host ""
        Write-Host "账号 JSON 登录网络模式：$LoginJsonProxyMode（按人工选择，不再自动判断 TUN）" -ForegroundColor Cyan

        $LoginJsonScript = Join-Path $Root "login-json.ps1"
        Assert-PortablePath "login-json.ps1" $LoginJsonScript
        if (-not (Test-Path -LiteralPath $LoginJsonScript -PathType Leaf)) {
            Write-Host "未找到 login-json.ps1：$LoginJsonScript" -ForegroundColor Red
            exit 1
        }
        Assert-PortableRegularInputFile "login-json.ps1" $LoginJsonScript
        $LoginResultPath = Join-Path $Root "tmp\login-json-selection.json"
        Assert-PortablePath "login JSON result" $LoginResultPath
        Remove-Item -LiteralPath $LoginResultPath -ErrorAction SilentlyContinue
        $loginMutexBypassToken = ([Guid]::NewGuid().ToString("N") + [Guid]::NewGuid().ToString("N"))
        $loginMutexTokenName = "CODEX_PORTABLE_INTERNAL_LOGIN_MUTEX_TOKEN"
        [Environment]::SetEnvironmentVariable($loginMutexTokenName, $loginMutexBypassToken, [EnvironmentVariableTarget]::Process)
        try {
            & $LoginJsonScript -Mode Select -ResultPath $LoginResultPath -SkipEnvFile -NoProxyPrompt -SkipPackageMutex -PackageMutexBypassToken $loginMutexBypassToken
        } finally {
            Remove-Item ("Env:" + $loginMutexTokenName) -ErrorAction SilentlyContinue
        }
        if (-not (Test-Path -LiteralPath $LoginResultPath)) {
            Write-Host "账号 JSON 登录未返回选择结果：$LoginResultPath" -ForegroundColor Red
            exit 1
        }
        Assert-PortableRegularInputFile "login JSON result" $LoginResultPath
        $LoginResultRaw = [System.IO.File]::ReadAllText($LoginResultPath, [System.Text.Encoding]::UTF8)
        $LoginResult = $LoginResultRaw | ConvertFrom-Json
        if ([string]::IsNullOrWhiteSpace($LoginResult.model)) {
            Write-Host "账号 JSON 登录未选择模型。" -ForegroundColor Red
            exit 1
        }
        $env:CODEX_MODEL = $LoginResult.model
        $CodexAuthDisplay = "login_json ($($LoginResult.email))"
        if (-not (Test-CodexAuthFile $ActiveAuthPath -RequireChatGpt)) {
            Write-Host "账号 JSON 登录生成的 auth.json 无效：$ActiveAuthPath" -ForegroundColor Red
            exit 1
        }
        Copy-CodexAuthAtomic -Source $ActiveAuthPath -Destination $AccountJsonAuthPath -FreshLogin
        Clear-CodexLogoutBlockAfterFreshLogin 'account_json'
        if ($LoginJsonProxyMode -eq "proxy") {
            $env:CODEX_PROXY_ENABLED = "true"
            $env:CODEX_PROXY_BYPASS_MODEL = "false"
            Write-Host "账号 JSON 登录：Codex 运行期将按你的选择走本地代理 $($env:CODEX_PROXY_PROTOCOL)://$($env:CODEX_PROXY_HOST):$($env:CODEX_PROXY_PORT)" -ForegroundColor Cyan
        } else {
            $env:CODEX_PROXY_ENABLED = "false"
            Write-Host "账号 JSON 登录：Codex 运行期将按你的选择直连，不强制本地代理。" -ForegroundColor Cyan
        }
        Remove-Item "Env:OPENAI_API_KEY" -ErrorAction SilentlyContinue
        Write-Host ""
    } elseif ($LoginChoice.Trim() -eq "3") {
        $UseBrowserLogin = $true
        $env:CODEX_PROVIDER_MODE = "official_chatgpt"
        $env:CODEX_ACCOUNT_JSON_AUTH = "false"
        $CodexAuthDisplay = "官方账号登录 (auth-browser.json)"

        # 官方账号模式不能继承 API 模式的中转地址或 Key。
        foreach ($name in @("OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_BASE_URL")) {
            Remove-Item "Env:$name" -ErrorAction SilentlyContinue
        }

        Backup-LegacyAccountJsonAuthForBrowser
        $HasBrowserAuth = -not (Test-CodexLogoutBlocked 'browser') -and (Test-CodexAuthFile $BrowserAuthPath -RequireChatGpt)

        Start-CodexAuthTransition
        if ($HasBrowserAuth) {
            Copy-CodexAuthAtomic -Source $BrowserAuthPath -Destination $ActiveAuthPath
            Write-Host "已载入官方账号凭证，无需重新登录：$BrowserAuthPath" -ForegroundColor Green
        } else {
            $BrowserLoginRequired = $true
            # 防止选项 2 留下的活动 auth.json 让 `codex login` 误判为已登录。
            Remove-PortableAuthStateFile -Path $ActiveAuthPath -Name 'active auth before fresh login'
            Write-Host "未找到官方账号凭证，将使用 $BrowserLoginFlow 完成登录。" -ForegroundColor Yellow
        }
        Write-Host ""
    }
    $SelectedAuthMode = if ($UseAccountJsonLogin) { "account_json" } elseif ($UseBrowserLogin) { "browser" } else { "api" }
    Write-CodexAuthMode $SelectedAuthMode
    Complete-CodexAuthTransition

    $ReasoningMenu = Get-ModelReasoningMenuInfo -ModelSlug $env:CODEX_MODEL
    $ReasoningLevels = @($ReasoningMenu.Levels)
    if ([string]::IsNullOrWhiteSpace($env:CODEX_REASONING_EFFORT)) {
        $DefEffort = [string]$ReasoningMenu.Default
        $ReasoningSettingSource = "模型目录默认"
    } else {
        $DefEffort = Normalize-ReasoningEffortValue $env:CODEX_REASONING_EFFORT
    }
    $env:CODEX_REASONING_EFFORT = $DefEffort
    $DefEffortDisplay = if ([string]::IsNullOrWhiteSpace($DefEffort)) { "不指定" } else { $DefEffort }

    $ReasoningLabels = @{ minimal = "最少"; low = "较快"; medium = "中等"; high = "沉思"; xhigh = "极限"; max = "最大"; ultra = "超高" }
    $ReasoningItems = for ($i = 0; $i -lt $ReasoningLevels.Count; $i++) {
        $level = $ReasoningLevels[$i]
        $label = if ($ReasoningLabels.ContainsKey($level)) { $ReasoningLabels[$level] } else { $level }
        "{0}){1}({2})" -f ($i + 1), $label, $level
    }
    $CustomEffortIndex = $ReasoningLevels.Count + 1
    Write-Host ""
    Write-Host "思考强度（模型: $($env:CODEX_MODEL)，来源: $($ReasoningMenu.Source)）:" -ForegroundColor Cyan
    Write-Host ("  " + ($ReasoningItems -join "  ") + "  $CustomEffortIndex)自定义值   [回车=默认: $DefEffortDisplay]") -ForegroundColor Cyan
    $EffortChoice = (Read-Host "请选择思考强度 (1-$CustomEffortIndex, 回车=默认: $DefEffortDisplay)").Trim()
    $EffortIndex = 0
    if ([int]::TryParse($EffortChoice, [ref]$EffortIndex) -and $EffortIndex -ge 1 -and $EffortIndex -le $ReasoningLevels.Count) {
        $env:CODEX_REASONING_EFFORT = $ReasoningLevels[$EffortIndex - 1]
        $ReasoningSettingSource = "启动菜单"
    } elseif ($EffortIndex -eq $CustomEffortIndex) {
        $CustomEffort = (Read-Host "请输入第三方 API 接受的 reasoning.effort 值").Trim()
        if (-not [string]::IsNullOrWhiteSpace($CustomEffort)) {
            $env:CODEX_REASONING_EFFORT = Normalize-ReasoningEffortValue $CustomEffort
            $ReasoningSettingSource = "启动菜单自定义值"
        }
    }

    Write-Host ""
    Write-Host "联网（仅影响 Codex 调用的本地命令，不影响访问 API）:" -ForegroundColor Cyan
    Write-Host "  1) 关闭(更安全)   2) 开启(可下依赖)   [回车=默认: $DefNet]" -ForegroundColor Cyan
    $NetChoice = Read-Host "请选择联网 (1/2, 回车=默认: $DefNet)"
    switch ($NetChoice.Trim()) {
        "1" { $env:CODEX_SANDBOX_NETWORK_ACCESS = "false" }
        "2" { $env:CODEX_SANDBOX_NETWORK_ACCESS = "true" }
        default { }  # 回车或其它输入 = 沿用 env.ps1 的默认值
    }

    if (-not $UseAccountJsonLogin) {
        Write-Host ""
        Write-Host "本地代理（让 Codex 访问模型 API 时走 v2ray/Clash 等本机代理，与上面联网无关）:" -ForegroundColor Cyan
        Write-Host "  1) 关闭   2) 开启   [回车=默认: $DefProxy]" -ForegroundColor Cyan
        $ProxyChoice = Read-Host "请选择是否走本地代理 (1/2, 回车=默认: $DefProxy)"
        switch ($ProxyChoice.Trim()) {
            "1" { $env:CODEX_PROXY_ENABLED = "false" }
            "2" {
                $env:CODEX_PROXY_ENABLED = "true"
                $env:CODEX_PROXY_BYPASS_MODEL = "false"
            }
            default { }  # 回车或其它输入 = 沿用 env.ps1 的默认值
        }
    } else {
        Write-Host ""
        Write-Host "本地代理: 已按账号 JSON 登录前的选择生效（用于登录检查和 Codex 访问 ChatGPT 后端）。" -ForegroundColor Cyan
    }

    # 仅当"联网"和"代理"都将开启时，才追问：联网时本机命令是否也走代理
    $MenuNetOn = (-not [string]::IsNullOrWhiteSpace($env:CODEX_SANDBOX_NETWORK_ACCESS)) -and ($env:CODEX_SANDBOX_NETWORK_ACCESS.Trim().ToLowerInvariant() -in @("1","true","yes","y","on"))
    $MenuProxyOn = (-not [string]::IsNullOrWhiteSpace($env:CODEX_PROXY_ENABLED)) -and ($env:CODEX_PROXY_ENABLED.Trim().ToLowerInvariant() -in @("1","true","yes","y","on"))
    if ($MenuNetOn -and $MenuProxyOn) {
        Write-Host ""
        Write-Host "联网时本机命令是否也走代理（npm/pip 下依赖时走 v2ray）:" -ForegroundColor Cyan
        Write-Host "  1) 否(只代理 API)   2) 是(下依赖也走代理)   [回车=默认: $DefProxySub]" -ForegroundColor Cyan
        $ProxyNetChoice = Read-Host "请选择联网命令是否走代理 (1/2, 回车=默认: $DefProxySub)"
        switch ($ProxyNetChoice.Trim()) {
            "1" { $env:CODEX_PROXY_FOR_SUBPROCESS = "false" }
            "2" { $env:CODEX_PROXY_FOR_SUBPROCESS = "true" }
            default { }  # 回车或其它输入 = 沿用 env.ps1 的默认值
        }
    }
    Write-Host ""
}

if (-not $ShowStartupMenu) {
    $EffectiveAuthMode = $ConfiguredAuthMode
    if ($EffectiveAuthMode -eq "menu") { $EffectiveAuthMode = "api" }
    if ($EffectiveAuthMode -eq "last") {
        $EffectiveAuthMode = if ([string]::IsNullOrWhiteSpace($PreviousAuthMode)) { "api" } else { $PreviousAuthMode }
    }

    switch ($EffectiveAuthMode) {
        "account_json" {
            if ((Test-CodexLogoutBlocked 'account_json') -or -not (Test-CodexAuthFile $AccountJsonAuthPath -RequireChatGpt)) {
                Write-Host "命令行账号 JSON 模式缺少有效凭证：$AccountJsonAuthPath" -ForegroundColor Red
                exit 1
            }
            Start-CodexAuthTransition
            Copy-CodexAuthAtomic -Source $AccountJsonAuthPath -Destination $ActiveAuthPath
            $UseAccountJsonLogin = $true
            $env:CODEX_ACCOUNT_JSON_AUTH = "true"
            $CodexAuthDisplay = "账号 JSON (auth-account-json.json)"
            $env:CODEX_PROVIDER_MODE = "official_chatgpt"
            $env:CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
            $env:OPENAI_BASE_URL = $env:CODEX_BASE_URL
            $env:CODEX_PROXY_BYPASS_MODEL = "false"
            $loginJsonProxyMode = [string]$env:CODEX_LOGIN_JSON_PROXY_MODE
            if (-not [string]::IsNullOrWhiteSpace($loginJsonProxyMode)) {
                $loginJsonProxyMode = $loginJsonProxyMode.Trim().ToLowerInvariant()
                if ($loginJsonProxyMode -eq "proxy") { $env:CODEX_PROXY_ENABLED = "true" }
                elseif ($loginJsonProxyMode -eq "direct") { $env:CODEX_PROXY_ENABLED = "false" }
                elseif ($loginJsonProxyMode -ne "auto") { Write-Host "CODEX_LOGIN_JSON_PROXY_MODE 只支持 auto / direct / proxy：$loginJsonProxyMode" -ForegroundColor Red; exit 1 }
            }
            Remove-Item "Env:OPENAI_API_KEY" -ErrorAction SilentlyContinue
        }
        "browser" {
            Backup-LegacyAccountJsonAuthForBrowser
            $UseBrowserLogin = $true
            $env:CODEX_PROVIDER_MODE = "official_chatgpt"
            $env:CODEX_ACCOUNT_JSON_AUTH = "false"
            $CodexAuthDisplay = "官方账号登录 (auth-browser.json)"
            foreach ($name in @("OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_BASE_URL")) {
                Remove-Item "Env:$name" -ErrorAction SilentlyContinue
            }
            Start-CodexAuthTransition
            if (-not (Test-CodexLogoutBlocked 'browser') -and (Test-CodexAuthFile $BrowserAuthPath -RequireChatGpt)) {
                Copy-CodexAuthAtomic -Source $BrowserAuthPath -Destination $ActiveAuthPath
            } else {
                $BrowserLoginRequired = $true
                Remove-PortableAuthStateFile -Path $ActiveAuthPath -Name 'active auth before fresh login'
            }
        }
        "api" { }
    }
    # menu 在带参数时临时使用 API，但不覆盖用户上次明确选择的模式。
    if ($ConfiguredAuthMode -ne "menu") { Write-CodexAuthMode $EffectiveAuthMode }
    Complete-CodexAuthTransition
}

# `-m/--model` is a real Codex override. Mirror its final value back into the
# launcher state before deriving catalog/modalities/instructions and status output,
# so the wrapper never reports/configures model B while codex.exe actually runs A.
if (-not [string]::IsNullOrWhiteSpace($script:CliModelOverride)) {
    $env:CODEX_MODEL = $script:CliModelOverride.Trim()
}

# ------------------------------------------------------------
# 5. 工具函数
# ------------------------------------------------------------
function Convert-ToTomlString {
    param([string]$Value)
    if ($null -eq $Value) { return "" }
    return $Value.Replace('\', '\\').Replace('"', '\"').Replace("`b", '\b').Replace("`t", '\t').Replace("`n", '\n').Replace("`f", '\f').Replace("`r", '\r')
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

function Write-Utf8TextAtomic {
    param([string]$Path, [string]$Text)
    $temporaryPath = "$Path.tmp-$([System.Guid]::NewGuid().ToString('N'))"
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    $temporaryOwned = $false
    try {
        Write-PortableNewUtf8File -Path $temporaryPath -Text $Text
        $temporaryOwned = $true
        Move-TemporaryFileIntoPlace -TemporaryPath $temporaryPath -Destination $Path
    } finally {
        if ($temporaryOwned) { Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue }
    }
}

function Test-IsBlankOrPlaceholder {
    param([string]$Value, [string[]]$Placeholders)
    if ([string]::IsNullOrWhiteSpace($Value)) { return $true }
    foreach ($p in $Placeholders) {
        if ($Value -eq $p) { return $true }
    }
    return $false
}

function Assert-EnvValue {
    param([string]$Name, [string]$Value, [string[]]$Placeholders)
    if (Test-IsBlankOrPlaceholder $Value $Placeholders) {
        Write-Host "请先编辑 env.ps1，填写 $Name。" -ForegroundColor Red
        exit 1
    }
}

function Resolve-HttpBaseUrl {
    param([string]$Name, [string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        Write-Host "$Name 不能为空。" -ForegroundColor Red
        exit 1
    }
    try {
        $uri = [System.Uri]$Value.Trim()
        if (-not $uri.IsAbsoluteUri -or $uri.Scheme -notin @("http","https") -or [string]::IsNullOrWhiteSpace($uri.Host)) { throw "invalid" }
        if (-not [string]::IsNullOrWhiteSpace($uri.UserInfo)) { throw "credentials in URL are not allowed" }
        return $uri.AbsoluteUri.TrimEnd('/')
    } catch {
        Write-Host "$Name 必须是合法的 http/https 绝对 URL，且 URL 中不能内嵌账号密码：$Value" -ForegroundColor Red
        exit 1
    }
}

function Assert-TomlInlineTable {
    param([string]$Name, [string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return }
    $trimmed = $Value.Trim()
    if ($trimmed.Contains("`r") -or $trimmed.Contains("`n") -or -not $trimmed.StartsWith("{") -or -not $trimmed.EndsWith("}")) {
        Write-Host "$Name 必须是单行 TOML inline table（{ ... }），拒绝可能破坏配置的值。" -ForegroundColor Red
        exit 1
    }
}

function Append-TomlSet {
    param(
        [System.Text.StringBuilder]$Builder,
        [string]$Name,
        [string]$Value
    )
    if ($null -ne $Value) {
        $Escaped = Convert-ToTomlString $Value
        [void]$Builder.AppendLine("$Name = `"$Escaped`"")
    }
}

$script:CodexProxyBridgeProcess = $null

function Test-TcpPortOpen {
    param([string]$HostName, [int]$Port, [int]$TimeoutMs = 700)
    $client = $null
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        if ($null -ne $client) { try { $client.Close() } catch {} }
    }
}

function Format-HostForUri {
    param([string]$HostName)
    if ([string]::IsNullOrWhiteSpace($HostName)) { return $HostName }
    $value = $HostName.Trim()
    if ($value.Contains(":") -and -not ($value.StartsWith("[") -and $value.EndsWith("]"))) {
        return "[$value]"
    }
    return $value
}

function Start-CodexSocksHttpBridge {
    param([string]$SocksHost, [string]$SocksPort)

    $script:CodexProxyBridgeDisplayUrl = ""
    $bridgeEnabled = (Convert-ToTomlBool $env:CODEX_PROXY_HTTP_BRIDGE $true) -eq "true"
    if (-not $bridgeEnabled) { return "" }

    $bridgeHost = $env:CODEX_PROXY_BRIDGE_HOST
    if ([string]::IsNullOrWhiteSpace($bridgeHost)) { $bridgeHost = "127.0.0.1" }
    $bridgeHost = $bridgeHost.Trim()
    if ($bridgeHost -notin @("127.0.0.1", "localhost", "::1")) {
        throw "CODEX_PROXY_BRIDGE_HOST 只允许回环地址：$bridgeHost"
    }

    $parsedSocksPort = 0
    if (-not [int]::TryParse($SocksPort, [ref]$parsedSocksPort) -or $parsedSocksPort -lt 1 -or $parsedSocksPort -gt 65535) {
        throw "SOCKS 代理端口必须是 1-65535：$SocksPort"
    }

    $bridgePortText = $env:CODEX_PROXY_BRIDGE_PORT
    $bridgePortExplicit = -not [string]::IsNullOrWhiteSpace($bridgePortText)
    $bridgePort = 0
    if ($bridgePortExplicit) {
        if (-not [int]::TryParse($bridgePortText, [ref]$bridgePort) -or $bridgePort -lt 1 -or $bridgePort -gt 65535) {
            throw "CODEX_PROXY_BRIDGE_PORT 必须是 1-65535：$bridgePortText"
        }
        if (Test-TcpPortOpen -HostName $bridgeHost -Port $bridgePort -TimeoutMs 300) {
            throw "显式代理桥端口已被占用：$bridgePort"
        }
    } else {
        # A fixed predictable loopback proxy makes it easier for another local/sandboxed
        # process to discover and reuse it. Pick a fresh ephemeral port each launch.
        $listener = $null
        try {
            $listenAddress = if ($bridgeHost -eq "::1") { [System.Net.IPAddress]::IPv6Loopback } else { [System.Net.IPAddress]::Loopback }
            $listener = New-Object System.Net.Sockets.TcpListener($listenAddress, 0)
            $listener.Start()
            $bridgePort = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
        } catch {
            throw "无法为 SOCKS HTTP bridge 选择空闲回环端口：$($_.Exception.Message)"
        } finally {
            if ($null -ne $listener) { try { $listener.Stop() } catch {} }
        }
    }
    $bridgeToken = ([Guid]::NewGuid().ToString("N") + [Guid]::NewGuid().ToString("N"))
    $bridgeUriHost = Format-HostForUri $bridgeHost
    $bridgeUrl = "http://codex:${bridgeToken}@${bridgeUriHost}:${bridgePort}"
    $bridgeDisplayUrl = "http://${bridgeUriHost}:${bridgePort}"

    $python = Join-Path $Root "tool\python\python.exe"
    $bridgeScript = Join-Path $Root "tool\socks-http-bridge.py"
    Assert-PortablePath "bridge python" $python
    Assert-PortablePath "SOCKS bridge script" $bridgeScript
    if (-not (Test-Path -LiteralPath $python -PathType Leaf) -or -not (Test-Path -LiteralPath $bridgeScript -PathType Leaf)) {
        throw "CODEX_PROXY_HTTP_BRIDGE=true，但包内 Python 或 bridge 脚本缺失。"
    }
    Assert-PortableRegularInputFile "bridge python" $python
    Assert-PortableRegularInputFile "SOCKS bridge script" $bridgeScript

    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $python
        $psi.WorkingDirectory = $Root
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $bridgeArgs = @(
            "-B", $bridgeScript,
            "--listen-host", $bridgeHost,
            "--listen-port", [string]$bridgePort,
            "--socks-host", $SocksHost,
            "--socks-port", [string]$parsedSocksPort,
            "--auth-token-env", "CODEX_PROXY_BRIDGE_TOKEN"
        )
        $psi.Arguments = ($bridgeArgs | ForEach-Object { ConvertTo-WindowsCommandLineArgument ([string]$_) }) -join " "
        try { $psi.EnvironmentVariables.Clear() } catch { try { $psi.Environment.Clear() } catch {} }
        Reset-CodexTrustedSystemEnvironment
        foreach ($name in @("SystemRoot","WINDIR","SystemDrive","ComSpec","PATHEXT","OS","PROCESSOR_ARCHITECTURE","TEMP","TMP","HOME","USERPROFILE","PATH")) {
            Set-ProcessEnvironmentValue $psi $name ([Environment]::GetEnvironmentVariable($name))
        }
        Set-ProcessEnvironmentValue $psi "PYTHONDONTWRITEBYTECODE" "1"
        Set-ProcessEnvironmentValue $psi "PYTHONNOUSERSITE" "1"
        Set-ProcessEnvironmentValue $psi "CODEX_PROXY_BRIDGE_TOKEN" $bridgeToken
        $script:CodexProxyBridgeProcess = [System.Diagnostics.Process]::Start($psi)
        for ($i = 0; $i -lt 25; $i++) {
            Start-Sleep -Milliseconds 120
            if (-not $script:CodexProxyBridgeProcess.HasExited -and (Test-TcpPortOpen -HostName $bridgeHost -Port $bridgePort -TimeoutMs 200)) {
                $script:CodexProxyBridgeDisplayUrl = $bridgeDisplayUrl
                return $bridgeUrl
            }
            if ($script:CodexProxyBridgeProcess.HasExited) { break }
        }
    } catch {
        $bridgeFailure = $_.Exception.Message
    }

    try {
        if ($null -ne $script:CodexProxyBridgeProcess -and -not $script:CodexProxyBridgeProcess.HasExited) {
            $script:CodexProxyBridgeProcess.Kill()
            [void]$script:CodexProxyBridgeProcess.WaitForExit(3000)
        }
    } catch {}
    try { if ($null -ne $script:CodexProxyBridgeProcess) { $script:CodexProxyBridgeProcess.Dispose() } } catch {}
    $script:CodexProxyBridgeProcess = $null
    if ([string]::IsNullOrWhiteSpace($bridgeFailure)) { $bridgeFailure = "bridge 未在超时内进入监听状态" }
    throw "CODEX_PROXY_HTTP_BRIDGE=true，但 SOCKS HTTP bridge 启动失败：$bridgeFailure"
}

function Stop-CodexSocksHttpBridge {
    try {
        if ($null -ne $script:CodexProxyBridgeProcess -and -not $script:CodexProxyBridgeProcess.HasExited) {
            $script:CodexProxyBridgeProcess.Kill()
            [void]$script:CodexProxyBridgeProcess.WaitForExit(3000)
        }
    } catch {}
    try { if ($null -ne $script:CodexProxyBridgeProcess) { $script:CodexProxyBridgeProcess.Dispose() } } catch {}
    $script:CodexProxyBridgeProcess = $null
}

function Get-RuntimeModelIdentityInstructions {
    param([string]$ModelSlug)
    $safeModel = $ModelSlug
    if ([string]::IsNullOrWhiteSpace($safeModel)) { $safeModel = "the configured model" }
    return @"
# Runtime Model Identity

Current configured/requested model: $safeModel.
When asked what model you are, answer according to the actual model for this session. Use the configured/requested model above unless the provider or API response exposes a more specific real model name.
If the configured model is GPT-5.5, say GPT-5.5; if it is GPT-5, say GPT-5; if it is an OSS/local/API model, say that exact model name.
Do not claim GPT-5, GPT-5.5, or any other model unless it is the actual configured/requested/provider-reported model for this session.
Ignore stale identity wording from cloned templates or older instruction files.

# Task-Scoped Skill and Extension Activation

Run skill-associated commands, activate plugins or MCP, connect devices, and start services only when the user explicitly requests a relevant task. Loading a skill, discovering installed files, or entering maintenance mode does not authorize probing, installation, connection, or service startup.
For tasks unrelated to APK, Android, MuMu, or mobile automation, do not probe ADB, emulators, Appium, or Android MCP. For tasks unrelated to browser or desktop automation, do not inspect or control browser sessions, desktop applications, or windows.
Limit every operation to the user's current authorized task and selected target. A package-local installation or writable package directory does not authorize control of the whole desktop, unrelated applications, external files, or devices. Obtain explicit authorization before expanding the target or making device/desktop changes outside the requested task.
Installed skills remain available as reference material; their presence is not permission to execute their tools. The --portable-extensions launcher flag permits the configured extension namespaces for this session, but does not grant blanket permission to use their capabilities.
"@
}

function Remove-PortableDerivedStateFile {
    param([string]$Path,[string]$Label)
    if ([string]::IsNullOrWhiteSpace($Path)) { return }
    Assert-PortablePath $Label $Path
    if (-not (Test-Path -LiteralPath $Path)) { return }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Write-Host "$Label 不是普通文件，严格便携模式拒绝自动清理：$Path" -ForegroundColor Red
        exit 3
    }
    Assert-PortableRegularInputFile $Label $Path
    Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
}

# Old mother-base model catalog snapshots are derived state and are not consumed by this launcher.
foreach ($obsoleteCatalogState in @(
    (Join-Path $env:CODEX_HOME "model-catalog.local.json"),
    (Join-Path $env:CODEX_HOME "model-catalog.local.json.version")
)) {
    Remove-PortableDerivedStateFile -Path $obsoleteCatalogState -Label "obsolete model catalog state"
}

function New-RuntimeModelInstructions {
    param([string]$OriginalPath, [string]$ModelSlug)

    $runtimePath = Join-Path $env:CODEX_HOME "codex-runtime-instructions.generated.md"
    if ([string]::IsNullOrWhiteSpace($OriginalPath) -or -not (Test-Path -LiteralPath $OriginalPath -PathType Leaf)) {
        # Derived state from an older model/instruction selection must not survive a switch back to defaults.
        Remove-PortableDerivedStateFile -Path $runtimePath -Label "stale runtime model instructions"
        return ""
    }

    Assert-PortableRegularInputFile "model instructions" $OriginalPath

    $builder = New-Object System.Text.StringBuilder
    [void]$builder.AppendLine((Get-RuntimeModelIdentityInstructions -ModelSlug $ModelSlug).Trim())
    [void]$builder.AppendLine("")

    $text = [System.IO.File]::ReadAllText($OriginalPath, [System.Text.Encoding]::UTF8)
    $text = $text -replace '(?im)^You are Codex,\s*based on GPT-5\.5,\s*', 'You are Codex, '
    $text = $text -replace '(?im)^You are Codex,\s*based on GPT-5,\s*', 'You are Codex, '
    $text = $text -replace '(?im)^You are Codex,\s*a coding agent based on GPT-5\.\s*', 'You are Codex, a coding agent. '
    $text = $text -replace '(?im)^You are Codex,\s*a coding agent based on the [^.`r`n]+ model\.\s*', 'You are Codex, a coding agent. '
    [void]$builder.AppendLine("# User Model Instructions")
    [void]$builder.AppendLine("")
    [void]$builder.AppendLine($text.Trim())
    [void]$builder.AppendLine("")

    Write-Utf8TextAtomic -Path $runtimePath -Text $builder.ToString()
    return $runtimePath
}

# ------------------------------------------------------------
# 5.1 手工 modality/context 兼容模型目录
#   背景：旧式静态 model catalog 是某个 codex 版本 schema 的快照，
#         一旦 codex.exe 升级、schema 变动，旧快照可能因 missing field 启动报错。
#   方案：从“当前 codex.exe”现场导出 bundled 模型库（schema 必然匹配本版本）。
#         能按 Codex 0.170.0 规则匹配 bundled 元数据时克隆原 entry，只覆盖明确请求项；
#         真正未知模型才使用 fallback-shaped 最小 entry。
#   稳健：第三方显式 override 的目录生成失败必须停止，避免配置看似生效其实被 fallback 截断。
# ------------------------------------------------------------
$script:BundledModelsCache = $null

function Get-BundledModelsResponse {
    param([string]$CodexExe)
    if ($null -ne $script:BundledModelsCache) { return $script:BundledModelsCache }
    try {
        $capture = Invoke-CodexChildCapture -LaunchArgs @("debug","models","--bundled")
        $raw = [string]$capture.StdOut
        if ($capture.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) { return $null }
        $obj = $raw | ConvertFrom-Json
        if ($null -eq $obj -or $null -eq $obj.models) { return $null }
        $script:BundledModelsCache = $obj
        return $obj
    } catch { return $null }
}

function Find-BundledModelSource {
    param([object]$Bundled, [string]$ModelSlug)
    if ($null -eq $Bundled -or $null -eq $Bundled.models -or [string]::IsNullOrWhiteSpace($ModelSlug)) { return $null }

    # Mirror Codex 0.170.0 ModelsManager matching: longest starts_with prefix first.
    $best = $null
    $bestLength = -1
    foreach ($candidate in @($Bundled.models)) {
        $candidateSlug = [string]$candidate.slug
        if ([string]::IsNullOrWhiteSpace($candidateSlug)) { continue }
        if ($ModelSlug.StartsWith($candidateSlug, [System.StringComparison]::Ordinal) -and $candidateSlug.Length -gt $bestLength) {
            $best = $candidate
            $bestLength = $candidateSlug.Length
        }
    }
    if ($null -ne $best) { return $best }

    # Codex also retries one simple provider namespace: namespace/model-name.
    $firstSlash = $ModelSlug.IndexOf('/')
    if ($firstSlash -le 0 -or $firstSlash -ne $ModelSlug.LastIndexOf('/')) { return $null }
    $namespace = $ModelSlug.Substring(0, $firstSlash)
    $suffix = $ModelSlug.Substring($firstSlash + 1)
    if ([string]::IsNullOrWhiteSpace($suffix) -or $namespace -notmatch '^[A-Za-z0-9_-]+$') { return $null }

    $best = $null
    $bestLength = -1
    foreach ($candidate in @($Bundled.models)) {
        $candidateSlug = [string]$candidate.slug
        if ([string]::IsNullOrWhiteSpace($candidateSlug)) { continue }
        if ($suffix.StartsWith($candidateSlug, [System.StringComparison]::Ordinal) -and $candidateSlug.Length -gt $bestLength) {
            $best = $candidate
            $bestLength = $candidateSlug.Length
        }
    }
    return $best
}

function Resolve-ModelInputModalities {
    param([string]$CodexExe, [string]$ModelSlug, [switch]$ForceBundled)
    $mode = if ($ForceBundled) { "auto" } else { [string]$env:CODEX_MODEL_MODALITIES }
    if ([string]::IsNullOrWhiteSpace($mode)) { $mode = "auto" }
    $mode = $mode.Trim().ToLowerInvariant()
    switch ($mode) {
        "text" { return @("text") }
        { $_ -in @("text_image", "text-image", "text+image") } { return @("text", "image") }
        "auto" {
            $bundled = Get-BundledModelsResponse -CodexExe $CodexExe
            if ($null -ne $bundled) {
                $entry = Find-BundledModelSource -Bundled $bundled -ModelSlug $ModelSlug
                if ($null -ne $entry -and $null -ne $entry.input_modalities) {
                    $resolved = @($entry.input_modalities | ForEach-Object { ([string]$_).Trim().ToLowerInvariant() } | Where-Object { $_ -in @("text","image") } | Select-Object -Unique)
                    if ($resolved.Count -gt 0) { return $resolved }
                }
            }
            return @()
        }
        default {
            Write-Host "CODEX_MODEL_MODALITIES 只支持 auto / text / text_image；当前值无效，已停止启动：$mode" -ForegroundColor Red
            exit 1
        }
    }
}

function Get-PortableGenericBaseInstructions {
    param([object]$Bundled)
    if ($null -eq $Bundled -or $null -eq $Bundled.models) { return "" }

    function Get-CandidateInstructions([object]$Candidate) {
        if ($null -eq $Candidate) { return "" }
        $legacy = [string]$Candidate.base_instructions
        if (-not [string]::IsNullOrWhiteSpace($legacy)) { return $legacy }
        if ($null -eq $Candidate.model_messages) { return "" }
        $template = [string]$Candidate.model_messages.instructions_template
        if ([string]::IsNullOrWhiteSpace($template)) { return "" }
        if ($template.Contains('{{ personality }}')) {
            $personality = ""
            if ($null -ne $Candidate.model_messages.instructions_variables) {
                $personality = [string]$Candidate.model_messages.instructions_variables.personality_default
            }
            $template = $template.Replace('{{ personality }}', $personality)
        }
        return $template
    }

    $source = $Bundled.models | Where-Object {
        ([string]$_.slug) -eq "gpt-5.2" -and -not [string]::IsNullOrWhiteSpace((Get-CandidateInstructions $_))
    } | Select-Object -First 1
    if ($null -eq $source) {
        $source = $Bundled.models | Where-Object {
            -not [string]::IsNullOrWhiteSpace((Get-CandidateInstructions $_)) -and
            $null -eq $_.tool_mode -and $null -eq $_.multi_agent_version -and
            $null -eq $_.auto_review_model_override -and $null -eq $_.model_specialty -and
            -not [bool]$_.node_repl_auto_review_required
        } | Sort-Object priority | Select-Object -First 1
    }
    if ($null -eq $source) { return "" }
    $instructions = Get-CandidateInstructions $source
    if ([string]::IsNullOrWhiteSpace($instructions)) { return "" }

    $lines = @($instructions -split "`r?`n", 0, "RegexMatch")
    if ($lines.Count -gt 1) {
        $first = [string]$lines[0]
        $sourceSlug = [string]$source.slug
        $sourceDisplay = [string]$source.display_name
        $mentionsSource = (-not [string]::IsNullOrWhiteSpace($sourceSlug) -and $first.IndexOf($sourceSlug, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) -or
                          (-not [string]::IsNullOrWhiteSpace($sourceDisplay) -and $first.IndexOf($sourceDisplay, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
        $looksLikeModelIdentity = $first -match '^(?i)\s*You are Codex\b' -and $first -match '(?i)\b(GPT|model)\b'
        if ($mentionsSource -or $looksLikeModelIdentity) { $instructions = ($lines[1..($lines.Count-1)] -join "`n").TrimStart() }
    }
    return $instructions
}

function Ensure-ModelCatalog {
    param([string]$CatalogPath, [string]$CodexExe, [string]$ModelSlug, [string[]]$InputModalities, [int]$ContextWindow = 0)
    try {
        $bundled = Get-BundledModelsResponse -CodexExe $CodexExe
        if ($null -eq $bundled) { throw "无法从当前 codex.exe 导出 bundled 模型目录" }

        $source = Find-BundledModelSource -Bundled $bundled -ModelSlug $ModelSlug
        if ($null -ne $source) {
            $entry = ([string]($source | ConvertTo-Json -Depth 64)) | ConvertFrom-Json
            $entry | Add-Member -NotePropertyName slug -NotePropertyValue $ModelSlug -Force
            # Third-party Responses endpoints do not imply OpenAI internal Responses Lite.
            $entry | Add-Member -NotePropertyName use_responses_lite -NotePropertyValue $false -Force
            if ($null -ne $InputModalities -and @($InputModalities).Count -gt 0) {
                $entry | Add-Member -NotePropertyName input_modalities -NotePropertyValue @($InputModalities) -Force
            }
            if ($ContextWindow -gt 0) {
                $entry | Add-Member -NotePropertyName context_window -NotePropertyValue $ContextWindow -Force
                $entry | Add-Member -NotePropertyName max_context_window -NotePropertyValue $ContextWindow -Force
            }
        } else {
            $baseInstructions = Get-PortableGenericBaseInstructions -Bundled $bundled
            if ([string]::IsNullOrWhiteSpace($baseInstructions)) { throw "当前 bundled 模型目录中找不到可复用的通用 Codex 指令" }
            $fallbackContextWindow = $(if ($ContextWindow -gt 0) { $ContextWindow } else { 272000 })
            $entry = [ordered]@{
                slug = $ModelSlug; display_name = $ModelSlug; description = "Portable fallback metadata for an unknown third-party model."
                default_reasoning_level = $null; supported_reasoning_levels = @(); shell_type = "unified_exec"; visibility = "none"; supported_in_api = $true; priority = 99
                additional_speed_tiers = @(); service_tiers = @(); default_service_tier = $null; availability_nux = $null; upgrade = $null
                base_instructions = $baseInstructions
                include_skills_usage_instructions = $false; include_plugin_usage_instructions = $false; include_apps_usage_instructions = $false
                supports_reasoning_summary_parameter = $true; default_reasoning_summary = "auto"; support_verbosity = $false; default_verbosity = $null
                apply_patch_tool_type = $null; web_search_tool_type = "text"; truncation_policy = [ordered]@{ mode = "bytes"; limit = 10000 }
                supports_image_detail_original = $false; context_window = $fallbackContextWindow; max_context_window = $fallbackContextWindow; auto_compact_token_limit = $null
                comp_hash = $null; effective_context_window_percent = 95; experimental_supported_tools = @(); supports_search_tool = $false; use_responses_lite = $false
                node_repl_auto_review_required = $false; node_repl_disabled = $false; auto_review_model_override = $null; model_specialty = $null
                tool_mode = $null; multi_agent_version = $null; multi_agent_reasoning_effort = $null
            }
            if ($null -ne $InputModalities -and @($InputModalities).Count -gt 0) { $entry.input_modalities = @($InputModalities) }
        }
        $catalog = [ordered]@{ models = @([pscustomobject]$entry) }
        Write-Utf8TextAtomic -Path $CatalogPath -Text (ConvertTo-PortableJsonText -InputObject $catalog -Depth 64)
        return $true
    } catch {
        Write-Host "ModelCatalog  : 生成失败：$($_.Exception.Message)" -ForegroundColor Yellow
        return $false
    }
}

$TomlRoot        = Convert-ToTomlString $Root
$TomlWork        = Convert-ToTomlString $PortableWork
$TomlLogs        = Convert-ToTomlString (Join-Path $Root "logs")

$WorkspaceWritableRootPaths = if ($PortableMaintenanceMode) {
    @($Root)
} else {
    # Codex already starts in work. Keep the only additional writable package area
    # as tmp; mutable caches are redirected above into a random per-launch tmp tree.
    # Persistent command/module/config/cache trees stay readable but not writable.
    @(
        $PortableWork,
        $PortableTmp
    ) | Select-Object -Unique
}
foreach ($workspaceWritablePath in $WorkspaceWritableRootPaths) {
    Assert-PortablePath "workspace writable root" $workspaceWritablePath
    if (-not (Test-Path -LiteralPath $workspaceWritablePath -PathType Container)) {
        New-Item -ItemType Directory -Force -Path $workspaceWritablePath | Out-Null
    }
    Assert-PortablePath "workspace writable root" $workspaceWritablePath
}
$TomlWorkspaceWritableRoots = (@($WorkspaceWritableRootPaths | ForEach-Object {
    '"' + (Convert-ToTomlString $_) + '"'
}) -join ', ')
$TomlSqlite      = Convert-ToTomlString (Join-Path $Root "sqlite")
$TomlChatGptBaseUrl = Convert-ToTomlString "https://chatgpt.com/backend-api"
$TomlModel       = Convert-ToTomlString $env:CODEX_MODEL

$ProviderMode = [string]$env:CODEX_PROVIDER_MODE
if ([string]::IsNullOrWhiteSpace($ProviderMode)) { $ProviderMode = "custom_provider" }
$ProviderMode = $ProviderMode.Trim().ToLowerInvariant()
if ($ProviderMode -notin @("custom_provider", "local_ollama", "official_chatgpt")) {
    Write-Host "未知 CODEX_PROVIDER_MODE：$ProviderMode" -ForegroundColor Red
    Write-Host "r15-clean 仅支持：custom_provider, local_ollama, official_chatgpt" -ForegroundColor Yellow
    exit 1
}
$UseOfficialModelCatalog = $UseAccountJsonLogin -or $UseBrowserLogin -or ($ProviderMode -eq "official_chatgpt")

# Codex 0.170.0 clamps model_context_window to ModelInfo.max_context_window.
# Unknown-model fallback metadata has max_context_window=272000, so a third-party model
# that explicitly requests a different context window needs a matching local catalog entry.
$CustomModelContextWindow = 0
if (-not $UseOfficialModelCatalog -and -not [string]::IsNullOrWhiteSpace($env:CODEX_MODEL_CONTEXT_WINDOW)) {
    if (-not [int]::TryParse($env:CODEX_MODEL_CONTEXT_WINDOW.Trim(), [ref]$CustomModelContextWindow) -or $CustomModelContextWindow -le 0) {
        Write-Host "CODEX_MODEL_CONTEXT_WINDOW 必须是正整数，已停止启动：$($env:CODEX_MODEL_CONTEXT_WINDOW)" -ForegroundColor Red
        exit 1
    }
}

# Refresh only automatic discovery after the final model selection; explicit overrides remain authoritative.
if ($script:CodexPortableAutoModelInstructions) {
    $env:CODEX_MODEL_INSTRUCTIONS_FILE = Find-CodexPortableModelInstructions -Model $env:CODEX_MODEL
}
$OriginalModelInstructionsFile = $env:CODEX_MODEL_INSTRUCTIONS_FILE
$ResolvedOriginalModelInstructionsFile = ""
if ($null -ne $OriginalModelInstructionsFile) { $OriginalModelInstructionsFile = $OriginalModelInstructionsFile.Trim() }
if (-not [string]::IsNullOrWhiteSpace($OriginalModelInstructionsFile)) {
    $InstructionsPathForValidation = $OriginalModelInstructionsFile
    if (-not [System.IO.Path]::IsPathRooted($InstructionsPathForValidation)) { $InstructionsPathForValidation = Join-Path $env:CODEX_HOME $InstructionsPathForValidation }
    Assert-PortablePath "CODEX_MODEL_INSTRUCTIONS_FILE" $InstructionsPathForValidation
    $ResolvedOriginalModelInstructionsFile = $InstructionsPathForValidation
}
$ModelInstructionsFile = New-RuntimeModelInstructions -OriginalPath $ResolvedOriginalModelInstructionsFile -ModelSlug $env:CODEX_MODEL
if (-not [string]::IsNullOrWhiteSpace($ModelInstructionsFile)) { Assert-PortablePath "CODEX_MODEL_INSTRUCTIONS_FILE(runtime)" $ModelInstructionsFile }
$TomlModelInstructionsFile = Convert-ToTomlString $ModelInstructionsFile
$RuntimeModelIdentityInstructions = Get-RuntimeModelIdentityInstructions -ModelSlug $env:CODEX_MODEL
$TomlRuntimeModelIdentityInstructions = Convert-ToTomlString $RuntimeModelIdentityInstructions.Trim()
$ModelInputModalities = if ($UseOfficialModelCatalog) { @(Resolve-ModelInputModalities -CodexExe $CodexExe -ModelSlug $env:CODEX_MODEL -ForceBundled) } else { @(Resolve-ModelInputModalities -CodexExe $CodexExe -ModelSlug $env:CODEX_MODEL) }
$ModelModalitiesKnown = @($ModelInputModalities).Count -gt 0
$ModelAllowsImage = (-not $ModelModalitiesKnown) -or [bool]($ModelInputModalities -contains "image")

# Custom APIs always use a schema-matched catalog to select standard Responses,
# independently of bundled models opting into the internal Responses Lite protocol.
# Explicit metadata overrides are also applied here:
#   1) text/text_image modality override;
#   2) CODEX_MODEL_CONTEXT_WINDOW, because Codex 0.170.0 clamps against fallback max_context_window=272000.
$RequestedModalityMode = if ($UseOfficialModelCatalog) { "auto" } else { [string]$env:CODEX_MODEL_MODALITIES }
if ([string]::IsNullOrWhiteSpace($RequestedModalityMode)) { $RequestedModalityMode = "auto" }
$RequestedModalityMode = $RequestedModalityMode.Trim().ToLowerInvariant()
$ManualModalityOverride = (-not $UseOfficialModelCatalog) -and ($RequestedModalityMode -ne "auto")
$ExplicitContextOverride = (-not $UseOfficialModelCatalog) -and ($CustomModelContextWindow -gt 0)
$NeedCustomModelCatalog = (-not $UseOfficialModelCatalog) -or $ManualModalityOverride -or $ExplicitContextOverride
$ModelCatalogJson = ""
if (-not $NeedCustomModelCatalog) {
    foreach ($staleCustomCatalog in @(
        (Join-Path $env:CODEX_HOME "model-catalog.custom.json"),
        (Join-Path $env:CODEX_HOME "model-catalog.custom.json.version")
    )) {
        Remove-PortableDerivedStateFile -Path $staleCustomCatalog -Label "stale custom model catalog"
    }
}
if ($NeedCustomModelCatalog) {
    $ModelCatalogJson = [string]$env:CODEX_MODEL_CATALOG_JSON
    if ([string]::IsNullOrWhiteSpace($ModelCatalogJson)) { $ModelCatalogJson = Join-Path $env:CODEX_HOME "model-catalog.custom.json" }
    $ModelCatalogJson = $ModelCatalogJson.Trim()
    if (-not [System.IO.Path]::IsPathRooted($ModelCatalogJson)) { $ModelCatalogJson = Join-Path $Root $ModelCatalogJson }
    Assert-PortablePath "CODEX_MODEL_CATALOG_JSON" $ModelCatalogJson
    $catalogContextWindow = $CustomModelContextWindow # 0 = do not override a matched bundled model; unknown fallback chooses 272000 internally.
    $catalogReady = Ensure-ModelCatalog -CatalogPath $ModelCatalogJson -CodexExe $CodexExe -ModelSlug $env:CODEX_MODEL -InputModalities $ModelInputModalities -ContextWindow $catalogContextWindow
    if (-not $catalogReady) {
        Write-Host "标准 Responses 或手工模型覆盖所需的兼容 catalog 生成失败，已停止启动：$ModelCatalogJson" -ForegroundColor Red
        exit 1
    }
}
$TomlModelCatalogJson = Convert-ToTomlString $ModelCatalogJson

$UseAccountJsonAuth = (Convert-ToTomlBool $env:CODEX_ACCOUNT_JSON_AUTH $false) -eq "true"

$WireApi = $env:CODEX_WIRE_API
if ([string]::IsNullOrWhiteSpace($WireApi)) { $WireApi = "responses" }
$WireApi = $WireApi.Trim()
if ($WireApi -ne "responses") {
    Write-Host "当前 Codex 配置建议 CODEX_WIRE_API 使用 responses。请把 env.ps1 里的 CODEX_WIRE_API 改成 responses。" -ForegroundColor Red
    exit 1
}
$TomlWireApi = Convert-ToTomlString $WireApi

$ApprovalPolicy = $env:CODEX_APPROVAL_POLICY
if ([string]::IsNullOrWhiteSpace($ApprovalPolicy)) { $ApprovalPolicy = "on-request" }
$ApprovalPolicy = $ApprovalPolicy.Trim().ToLowerInvariant()
if ($ApprovalPolicy -eq "untrusted") {
    Write-Host "CODEX_APPROVAL_POLICY=untrusted 不在 Codex 0.170.0 的 approval_policy schema 中，会被拒绝。请改为 on-request（推荐）或 never。" -ForegroundColor Red
    exit 1
}
if ($ApprovalPolicy -notin @("never", "on-request")) {
    Write-Host "CODEX_APPROVAL_POLICY 只支持 on-request（推荐）或 never。细粒度 granular 是原生 TOML 对象，本便携环境变量接口不把它伪装成字符串。" -ForegroundColor Red
    exit 1
}
$TomlApprovalPolicy = Convert-ToTomlString $ApprovalPolicy

$SandboxMode = $env:CODEX_SANDBOX_MODE
if ([string]::IsNullOrWhiteSpace($SandboxMode)) { $SandboxMode = "workspace-write" }
$SandboxMode = $SandboxMode.Trim().ToLowerInvariant()
if ($SandboxMode -notin @("read-only", "workspace-write", "danger-full-access")) {
    Write-Host "CODEX_SANDBOX_MODE 只支持 read-only / workspace-write / danger-full-access。" -ForegroundColor Red
    exit 1
}
if ($SandboxMode -eq "danger-full-access" -and $ApprovalPolicy -ne "never") {
    Write-Host "danger-full-access 仅允许与 approval_policy=never 的无人值守 YOLO 配置一起使用。" -ForegroundColor Red
    exit 1
}
$TomlSandboxMode = Convert-ToTomlString $SandboxMode

$SandboxNetworkAccess = Convert-ToTomlBool $env:CODEX_SANDBOX_NETWORK_ACCESS $false
$FastModeEnabled = (Convert-ToTomlBool $env:CODEX_FAST_MODE $false) -eq "true"
$ServiceTier = $(if ($FastModeEnabled) { "priority" } else { "default" })

$DisableWebSocket = (Convert-ToTomlBool $env:CODEX_DISABLE_WEBSOCKET $true) -eq "true"
$ProviderSupportsWebSocketsToml = $(if ($DisableWebSocket) { "false" } else { "true" })

# Codex Apps、Plugins 与插件分享分别控制。
$DisableApps = (Convert-ToTomlBool $env:CODEX_DISABLE_APPS $true) -eq "true"
$EnablePlugins = $PortableExtensionPolicy.PluginsEnabled
$EnablePluginSharing = (Convert-ToFeatureBool $env:CODEX_ENABLE_PLUGIN_SHARING $false) -and $EnablePlugins
$PluginRoot = Join-Path $env:CODEX_HOME "plugins"
$PluginMarketplaceFile = Join-Path $env:CODEX_HOME ".agents\plugins\marketplace.json"
Assert-PortablePath "PluginRoot" $PluginRoot
Assert-PortablePath "PluginMarketplace" $PluginMarketplaceFile
if ($EnablePlugins) { Initialize-PortablePlugins -PluginRoot $PluginRoot -MarketplaceFile $PluginMarketplaceFile }

# 先清除宿主代理变量，再按便携包配置重建，避免继承外部代理。
foreach ($pv in @("HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","NO_PROXY","http_proxy","https_proxy","all_proxy","no_proxy")) {
    Remove-Item "Env:$pv" -ErrorAction SilentlyContinue
}
$ProxyEnabled = (Convert-ToTomlBool $env:CODEX_PROXY_ENABLED $false) -eq "true"
$ProxyForSubprocess = (Convert-ToTomlBool $env:CODEX_PROXY_FOR_SUBPROCESS $false) -eq "true"
# Use the effective normalized session switches, not raw or inherited strings.
$env:CODEX_PROXY_ENABLED = $ProxyEnabled.ToString().ToLowerInvariant()
$env:CODEX_PROXY_FOR_SUBPROCESS = $ProxyForSubprocess.ToString().ToLowerInvariant()
$env:CODEX_SANDBOX_NETWORK_ACCESS = $SandboxNetworkAccess
$ProxyDisplay = "off"
if ($ProxyEnabled) {
    $ProxyHost = $env:CODEX_PROXY_HOST
    if ([string]::IsNullOrWhiteSpace($ProxyHost)) { $ProxyHost = "127.0.0.1" }
    $ProxyHost = $ProxyHost.Trim()

    $ProxyPort = $env:CODEX_PROXY_PORT
    if ([string]::IsNullOrWhiteSpace($ProxyPort)) { $ProxyPort = "10808" }
    $ProxyPort = $ProxyPort.Trim()
    $parsedProxyPort = 0
    if (-not [int]::TryParse($ProxyPort, [ref]$parsedProxyPort) -or $parsedProxyPort -lt 1 -or $parsedProxyPort -gt 65535) {
        Write-Host "CODEX_PROXY_PORT 必须是 1-65535：$ProxyPort" -ForegroundColor Red
        exit 1
    }

    $ProxyProtocol = $env:CODEX_PROXY_PROTOCOL
    if ([string]::IsNullOrWhiteSpace($ProxyProtocol)) { $ProxyProtocol = "socks5" }
    $ProxyProtocol = $ProxyProtocol.Trim().ToLowerInvariant()
    if ($ProxyProtocol -notin @("http", "socks5")) {
        Write-Host "CODEX_PROXY_PROTOCOL 只支持 http / socks5：$ProxyProtocol" -ForegroundColor Red
        exit 1
    }
    try { $null = [System.Uri]("http://" + (Format-HostForUri $ProxyHost) + ":" + $parsedProxyPort) } catch {
        Write-Host "CODEX_PROXY_HOST 无效：$ProxyHost" -ForegroundColor Red; exit 1
    }

    if ($ProxyProtocol -eq "http") {
        $ProxyUriHost = Format-HostForUri $ProxyHost
        $ProxyUrl = "http://${ProxyUriHost}:${ProxyPort}"
        $env:HTTP_PROXY  = $ProxyUrl
        $env:HTTPS_PROXY = $ProxyUrl
        $env:ALL_PROXY   = $ProxyUrl
        $env:http_proxy  = $ProxyUrl
        $env:https_proxy = $ProxyUrl
        $env:all_proxy   = $ProxyUrl
    } else {
        # Codex.exe 不一定识别 socks5/ALL_PROXY；PySocks 只对 Python requests 生效。
        # 因此 socks5 入站默认先启动一个本地 HTTP CONNECT bridge，再把 HTTP(S)_PROXY 指给 Codex.exe。
        $ProxyProtocol = "socks5"
        $ProxyUriHost = Format-HostForUri $ProxyHost
        $SocksProxyUrl = "socks5h://${ProxyUriHost}:${ProxyPort}"
        $BridgeProxyUrl = Start-CodexSocksHttpBridge -SocksHost $ProxyHost -SocksPort $ProxyPort
        if (-not [string]::IsNullOrWhiteSpace($BridgeProxyUrl)) {
            $ProxyUrl = $BridgeProxyUrl
            $env:HTTP_PROXY  = $ProxyUrl
            $env:HTTPS_PROXY = $ProxyUrl
            $env:ALL_PROXY   = $ProxyUrl
            $env:http_proxy  = $ProxyUrl
            $env:https_proxy = $ProxyUrl
            $env:all_proxy   = $ProxyUrl
            $BridgeDisplay = if (-not [string]::IsNullOrWhiteSpace($script:CodexProxyBridgeDisplayUrl)) { $script:CodexProxyBridgeDisplayUrl } else { "local authenticated HTTP bridge" }
            $ProxyDisplay = "$BridgeDisplay -> $SocksProxyUrl"
        } else {
            $ProxyUrl = $SocksProxyUrl
            $env:ALL_PROXY = $ProxyUrl
            $env:all_proxy = $ProxyUrl
            $ProxyDisplay = "$ProxyUrl (bridge 已显式关闭，直接 SOCKS fallback)"
        }
    }
    # 本地地址不走代理，避免本机 ollama / lmstudio 被代理
    $NoProxyList = [System.Collections.Generic.List[string]]@("localhost", "127.0.0.1", "::1")
    # 默认让“模型接口地址”也直连：把 CODEX_BASE_URL 的主机加入 NO_PROXY。
    # 否则当 BASE_URL 指向远程/局域网/国内自建的 Ollama 或中转时，开代理会把模型流量劫持到 v2ray/Clash，
    # 多半连不上（典型坑：开代理给别的 API 加速，却顺手把本来直连的模型搞挂）。
    # 如需让模型接口也走代理（BASE_URL 是需翻墙的境外 API），把 env.ps1 的 CODEX_PROXY_BYPASS_MODEL 设为 false。
    $BypassModelHost = (Convert-ToTomlBool $env:CODEX_PROXY_BYPASS_MODEL $true) -eq "true"
    $ModelBypassed = $false
    if ($BypassModelHost -and (-not [string]::IsNullOrWhiteSpace($env:CODEX_BASE_URL))) {
        try {
            $ModelHost = ([System.Uri]$env:CODEX_BASE_URL).Host
            if ((-not [string]::IsNullOrWhiteSpace($ModelHost)) -and (-not $NoProxyList.Contains($ModelHost))) {
                $NoProxyList.Add($ModelHost)
                $ModelBypassed = $true
            }
        } catch {}
    }
    $NoProxyValue = ($NoProxyList -join ",")
    $env:NO_PROXY = $NoProxyValue
    $env:no_proxy = $NoProxyValue
    if ($ProxyDisplay -eq "off" -or [string]::IsNullOrWhiteSpace($ProxyDisplay)) {
        $ProxyDisplay = if (-not [string]::IsNullOrWhiteSpace($script:CodexProxyBridgeDisplayUrl)) { $script:CodexProxyBridgeDisplayUrl } else { $ProxyUrl }
    }
    if ($ProxyForSubprocess) {
        $ProxyDisplayBase = if (-not [string]::IsNullOrWhiteSpace($script:CodexProxyBridgeDisplayUrl)) { $script:CodexProxyBridgeDisplayUrl } else { $ProxyUrl }
        $ProxyDisplay = "$ProxyDisplayBase (本机命令也走)"
    }
    if ($ModelBypassed) { $ProxyDisplay = "$ProxyDisplay (模型接口直连)" }
}

# 思考强度（reasoning effort）：留空 = 用模型默认；非空值原样交给 Codex 和上游 API。
# 第三方 Responses API 可使用自己的 effort 值；是否生效由上游决定。
$ReasoningEffort = Normalize-ReasoningEffortValue $env:CODEX_REASONING_EFFORT
$TomlReasoningEffort = Convert-ToTomlString $ReasoningEffort
# 模型一般都必须填写
Assert-EnvValue "CODEX_MODEL" $env:CODEX_MODEL @("你的模型名称")

# ------------------------------------------------------------
# 6. 生成 config.toml
# ------------------------------------------------------------
$Builder = New-Object System.Text.StringBuilder
[void]$Builder.AppendLine("# This file is auto-generated by run-codex.ps1. Do not edit directly.")
[void]$Builder.AppendLine("# Edit env.ps1 instead.")
[void]$Builder.AppendLine("")
[void]$Builder.AppendLine("model = `"$TomlModel`"")
if ($CustomModelContextWindow -gt 0) {
    [void]$Builder.AppendLine("model_context_window = $CustomModelContextWindow")
}
if (-not [string]::IsNullOrWhiteSpace($ModelInstructionsFile)) {
    [void]$Builder.AppendLine("model_instructions_file = `"$TomlModelInstructionsFile`"")
} else {
    # developer_instructions 是附加指令，不会替换 Codex 内置模型指令。
    [void]$Builder.AppendLine("developer_instructions = `"$TomlRuntimeModelIdentityInstructions`"")
}
if (-not [string]::IsNullOrWhiteSpace($ReasoningEffort)) {
    [void]$Builder.AppendLine("model_reasoning_effort = `"$TomlReasoningEffort`"")
}
[void]$Builder.AppendLine("service_tier = `"$ServiceTier`"")
if (-not [string]::IsNullOrWhiteSpace($ModelCatalogJson)) {
    [void]$Builder.AppendLine("model_catalog_json = `"$TomlModelCatalogJson`"")
}
[void]$Builder.AppendLine("")
[void]$Builder.AppendLine("check_for_update_on_startup = false")
[void]$Builder.AppendLine("cli_auth_credentials_store = `"file`"")
[void]$Builder.AppendLine("mcp_oauth_credentials_store = `"file`"")
[void]$Builder.AppendLine("log_dir = `"$TomlLogs`"")
[void]$Builder.AppendLine("sqlite_home = `"$TomlSqlite`"")
[void]$Builder.AppendLine("sandbox_mode = `"$TomlSandboxMode`"")
[void]$Builder.AppendLine("approval_policy = `"$TomlApprovalPolicy`"")
[void]$Builder.AppendLine("allow_login_shell = false")
[void]$Builder.AppendLine("project_root_markers = []")
[void]$Builder.AppendLine("")

switch ($ProviderMode) {
    "official_chatgpt" {
        if (-not ($UseAccountJsonLogin -or $UseBrowserLogin)) {
            Write-Host "official_chatgpt 只供登录方式 2/3 使用；API 中转请使用 custom_provider。" -ForegroundColor Red
            exit 1
        }
        $officialCodexUrl = "https://chatgpt.com/backend-api/codex"
        $env:CODEX_BASE_URL = $officialCodexUrl
        if ($UseAccountJsonLogin) { $env:OPENAI_BASE_URL = $officialCodexUrl } else { Remove-Item Env:OPENAI_BASE_URL -ErrorAction SilentlyContinue }
        [void]$Builder.AppendLine("chatgpt_base_url = `"$TomlChatGptBaseUrl`"")
        if ($DisableWebSocket) {
            [void]$Builder.AppendLine("model_provider = `"portable-openai-official-http`"")
            [void]$Builder.AppendLine("")
            [void]$Builder.AppendLine("[model_providers.portable-openai-official-http]")
            [void]$Builder.AppendLine("name = `"OpenAI`"")
            [void]$Builder.AppendLine("base_url = `"$officialCodexUrl`"")
            [void]$Builder.AppendLine("wire_api = `"$TomlWireApi`"")
            [void]$Builder.AppendLine("requires_openai_auth = true")
            [void]$Builder.AppendLine("supports_websockets = false")
            [void]$Builder.AppendLine("supports_standalone_web_search = true")
        } elseif ($UseAccountJsonLogin) {
            $officialToml = Convert-ToTomlString $officialCodexUrl
            [void]$Builder.AppendLine("openai_base_url = `"$officialToml`"")
        }
    }

    "custom_provider" {
        Assert-EnvValue "OPENAI_API_KEY" $env:OPENAI_API_KEY @("在这里填写你的中转Key")
        $resolvedBaseUrl = Resolve-HttpBaseUrl -Name "CODEX_BASE_URL" -Value $env:CODEX_BASE_URL
        $env:CODEX_BASE_URL = $resolvedBaseUrl
        $env:OPENAI_BASE_URL = $resolvedBaseUrl
        $TomlBaseUrl = Convert-ToTomlString $resolvedBaseUrl

        $ProviderId = [string]$env:CODEX_PROVIDER_ID
        if ([string]::IsNullOrWhiteSpace($ProviderId)) { $ProviderId = "myproxy" }
        $ProviderId = $ProviderId.Trim()
        if ($ProviderId -notmatch '^[A-Za-z0-9_-]+$') { Write-Host "CODEX_PROVIDER_ID 只能使用字母、数字、下划线、短横线。" -ForegroundColor Red; exit 1 }
        if ($ProviderId -in @("openai","ollama","chatgpt","azure","amazon-bedrock")) { Write-Host "CODEX_PROVIDER_ID 使用了保留名：$ProviderId" -ForegroundColor Red; exit 1 }
        $ProviderName = [string]$env:CODEX_PROVIDER_NAME
        if ([string]::IsNullOrWhiteSpace($ProviderName)) { $ProviderName = "My Proxy" }
        $TomlProviderName = Convert-ToTomlString $ProviderName

        Assert-TomlInlineTable "CODEX_HTTP_HEADERS_TOML" $env:CODEX_HTTP_HEADERS_TOML
        Assert-TomlInlineTable "CODEX_ENV_HTTP_HEADERS_TOML" $env:CODEX_ENV_HTTP_HEADERS_TOML
        Assert-TomlInlineTable "CODEX_QUERY_PARAMS_TOML" $env:CODEX_QUERY_PARAMS_TOML

        [void]$Builder.AppendLine("model_provider = `"$ProviderId`"")
        [void]$Builder.AppendLine("")
        [void]$Builder.AppendLine("[model_providers.$ProviderId]")
        [void]$Builder.AppendLine("name = `"$TomlProviderName`"")
        [void]$Builder.AppendLine("base_url = `"$TomlBaseUrl`"")
        [void]$Builder.AppendLine("env_key = `"OPENAI_API_KEY`"")
        [void]$Builder.AppendLine("wire_api = `"$TomlWireApi`"")
        [void]$Builder.AppendLine("supports_websockets = $ProviderSupportsWebSocketsToml")
        if (-not [string]::IsNullOrWhiteSpace($env:CODEX_HTTP_HEADERS_TOML)) { [void]$Builder.AppendLine("http_headers = $($env:CODEX_HTTP_HEADERS_TOML.Trim())") }
        if (-not [string]::IsNullOrWhiteSpace($env:CODEX_ENV_HTTP_HEADERS_TOML)) { [void]$Builder.AppendLine("env_http_headers = $($env:CODEX_ENV_HTTP_HEADERS_TOML.Trim())") }
        if (-not [string]::IsNullOrWhiteSpace($env:CODEX_QUERY_PARAMS_TOML)) { [void]$Builder.AppendLine("query_params = $($env:CODEX_QUERY_PARAMS_TOML.Trim())") }
    }

    "local_ollama" {
        $base = [string]$env:CODEX_BASE_URL
        if ([string]::IsNullOrWhiteSpace($base) -or $base -eq "https://你的中转地址/v1") { $base = "http://127.0.0.1:11434/v1" }
        $resolvedBaseUrl = Resolve-HttpBaseUrl -Name "CODEX_BASE_URL(local_ollama)" -Value $base
        $env:CODEX_BASE_URL = $resolvedBaseUrl
        $env:OPENAI_BASE_URL = $resolvedBaseUrl
        $TomlBaseUrl = Convert-ToTomlString $resolvedBaseUrl
        Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
        [void]$Builder.AppendLine("model_provider = `"local_ollama`"")
        [void]$Builder.AppendLine("")
        [void]$Builder.AppendLine("[model_providers.local_ollama]")
        [void]$Builder.AppendLine("name = `"Ollama`"")
        [void]$Builder.AppendLine("base_url = `"$TomlBaseUrl`"")
        [void]$Builder.AppendLine("wire_api = `"$TomlWireApi`"")
        [void]$Builder.AppendLine("supports_websockets = false")
        if (-not $DisableWebSocket) { Write-Host "local_ollama 固定 HTTP/SSE；需要自定义 WebSocket 网关时请使用 custom_provider。" -ForegroundColor Yellow }
    }
}

# ------------------------------------------------------------
# 7. 通用严格便携配置
# ------------------------------------------------------------
[void]$Builder.AppendLine("")
[void]$Builder.AppendLine("[features]")
# Text/agent edition: disable the supported app voice/dictation features.
# 0.164 removed the realtime_conversation gate; /voice follows platform support.
[void]$Builder.AppendLine("in_app_voice = false")
[void]$Builder.AppendLine("in_app_dictation = false")
if (-not $ModelAllowsImage) {
    # text 模式下不向 Responses 请求注册 image_generation 工具，避免上游 403。
    [void]$Builder.AppendLine("image_generation = false")
}
# Fast、Apps、Plugins、PluginSharing 使用各自独立开关。
[void]$Builder.AppendLine("fast_mode = " + ($(if ($FastModeEnabled) { "true" } else { "false" })))
[void]$Builder.AppendLine("apps = " + ($(if ($DisableApps) { "false" } else { "true" })))
[void]$Builder.AppendLine("plugins = " + ($(if ($EnablePlugins) { "true" } else { "false" })))
[void]$Builder.AppendLine("plugin_sharing = " + ($(if ($EnablePluginSharing) { "true" } else { "false" })))
[void]$Builder.AppendLine("")
[void]$Builder.AppendLine("[tui]")
[void]$Builder.AppendLine("fullscreen_transcript = $TuiFullscreenTranscript")
[void]$Builder.AppendLine("resume_cwd = `"current`"")
# 当前 Codex TUI 使用分隔符显示状态栏项目，且启动后会异步加入右侧状态信息。
# U+00B7 在中文/CJK 终端中可能占 2 列，但 TUI 布局按 1 列计算，二次布局时可能
# 覆盖左侧最后 1 个字符。默认不在底部重复显示目录，从根源上避开该分隔符宽度差。
$StatusLineDirItem = $env:CODEX_STATUS_LINE_DIR_ITEM
if ([string]::IsNullOrWhiteSpace($StatusLineDirItem)) {
    $StatusLineDirItem = "none"
}
$StatusLineDirItem = $StatusLineDirItem.Trim().ToLowerInvariant()
if ($StatusLineDirItem -notin @("none", "project-root", "current-dir")) {
    Write-Host "CODEX_STATUS_LINE_DIR_ITEM 仅支持 none、project-root 或 current-dir，已回退到 none。" -ForegroundColor Yellow
    $StatusLineDirItem = "none"
}
if ($StatusLineDirItem -eq "none") {
    [void]$Builder.AppendLine('status_line = ["model-with-reasoning"]')
} else {
    [void]$Builder.AppendLine(('status_line = ["{0}", "model-with-reasoning"]' -f $StatusLineDirItem))
}
[void]$Builder.AppendLine("")
# Empty bindings prevent accidental voice hotkeys; upstream /voice remains visible.
[void]$Builder.AppendLine("[tui.keymap.chat]")
[void]$Builder.AppendLine("toggle_voice = []")
[void]$Builder.AppendLine("toggle_voice_mute = []")
[void]$Builder.AppendLine("")
[void]$Builder.AppendLine("[analytics]")
[void]$Builder.AppendLine("enabled = false")
[void]$Builder.AppendLine("")
[void]$Builder.AppendLine("[history]")
[void]$Builder.AppendLine("persistence = `"none`"")
[void]$Builder.AppendLine("")
[void]$Builder.AppendLine("[projects.`"$TomlWork`"]")
[void]$Builder.AppendLine("trust_level = `"untrusted`"")
[void]$Builder.AppendLine("")
[void]$Builder.AppendLine("[windows]")
[void]$Builder.AppendLine("sandbox = `"unelevated`"")
[void]$Builder.AppendLine("")
[void]$Builder.AppendLine("[sandbox_workspace_write]")
[void]$Builder.AppendLine("writable_roots = [$TomlWorkspaceWritableRoots]")
[void]$Builder.AppendLine("network_access = $SandboxNetworkAccess")
[void]$Builder.AppendLine("")
[void]$Builder.AppendLine("[shell_environment_policy]")
[void]$Builder.AppendLine("inherit = `"core`"")
[void]$Builder.AppendLine("experimental_use_profile = false")
[void]$Builder.AppendLine("ignore_default_excludes = false")
[void]$Builder.AppendLine("")
[void]$Builder.AppendLine("[shell_environment_policy.set]")
Append-TomlSet $Builder "CODEX_HOME" $env:CODEX_HOME
Append-TomlSet $Builder "CODEX_SQLITE_HOME" $env:CODEX_SQLITE_HOME
# PATH 不写入 policy.set：继承已清洗的 Codex 进程 PATH，并保留 Codex 自己 prepend 的 apply_patch helper。
Append-TomlSet $Builder "PSModulePath" $env:PSModulePath
Append-TomlSet $Builder "GIT_CONFIG_NOSYSTEM" $env:GIT_CONFIG_NOSYSTEM
Append-TomlSet $Builder "CODEX_ENABLE_PLUGINS" $env:CODEX_ENABLE_PLUGINS
Append-TomlSet $Builder "CODEX_ENABLE_PLUGIN_SHARING" $env:CODEX_ENABLE_PLUGIN_SHARING
Append-TomlSet $Builder "HOME" $env:HOME
Append-TomlSet $Builder "USERPROFILE" $env:USERPROFILE
Append-TomlSet $Builder "APPDATA" $env:APPDATA
Append-TomlSet $Builder "LOCALAPPDATA" $env:LOCALAPPDATA
Append-TomlSet $Builder "PROGRAMDATA" $env:PROGRAMDATA
Append-TomlSet $Builder "ALLUSERSPROFILE" $env:ALLUSERSPROFILE
Append-TomlSet $Builder "TEMP" $env:TEMP
Append-TomlSet $Builder "TMP" $env:TMP
Append-TomlSet $Builder "TMPDIR" $env:TMPDIR
Append-TomlSet $Builder "XDG_CACHE_HOME" $env:XDG_CACHE_HOME
Append-TomlSet $Builder "XDG_CONFIG_HOME" $env:XDG_CONFIG_HOME
Append-TomlSet $Builder "XDG_DATA_HOME" $env:XDG_DATA_HOME
Append-TomlSet $Builder "XDG_STATE_HOME" $env:XDG_STATE_HOME
Append-TomlSet $Builder "PIP_CONFIG_FILE" $env:PIP_CONFIG_FILE
Append-TomlSet $Builder "PIP_CACHE_DIR" $env:PIP_CACHE_DIR
Append-TomlSet $Builder "PYTHONUSERBASE" $env:PYTHONUSERBASE
Append-TomlSet $Builder "NPM_CONFIG_CACHE" $env:NPM_CONFIG_CACHE
Append-TomlSet $Builder "NPM_CONFIG_PREFIX" $env:NPM_CONFIG_PREFIX
Append-TomlSet $Builder "NPM_CONFIG_GLOBALCONFIG" $env:NPM_CONFIG_GLOBALCONFIG
Append-TomlSet $Builder "NPM_CONFIG_USERCONFIG" $env:NPM_CONFIG_USERCONFIG
Append-TomlSet $Builder "NODE_REPL_HISTORY" $env:NODE_REPL_HISTORY
Append-TomlSet $Builder "YARN_CACHE_FOLDER" $env:YARN_CACHE_FOLDER
Append-TomlSet $Builder "PNPM_HOME" $env:PNPM_HOME
Append-TomlSet $Builder "PNPM_STORE_DIR" $env:PNPM_STORE_DIR
Append-TomlSet $Builder "GRADLE_USER_HOME" $env:GRADLE_USER_HOME
Append-TomlSet $Builder "MAVEN_OPTS" $env:MAVEN_OPTS
Append-TomlSet $Builder "POWERSHELL_TELEMETRY_OPTOUT" $env:POWERSHELL_TELEMETRY_OPTOUT
Append-TomlSet $Builder "PSModuleAnalysisCachePath" $env:PSModuleAnalysisCachePath
Append-TomlSet $Builder "PYTHONPYCACHEPREFIX" $env:PYTHONPYCACHEPREFIX
Append-TomlSet $Builder "CODEX_INSTALL_DIR" $env:CODEX_INSTALL_DIR
Append-TomlSet $Builder "CODEX_PYTHON" $env:CODEX_PYTHON
if (-not [string]::IsNullOrWhiteSpace($env:ANDROID_HOME)) { Append-TomlSet $Builder "ANDROID_HOME" $env:ANDROID_HOME }
if (-not [string]::IsNullOrWhiteSpace($env:ANDROID_SDK_ROOT)) { Append-TomlSet $Builder "ANDROID_SDK_ROOT" $env:ANDROID_SDK_ROOT }
Append-TomlSet $Builder "ANDROID_USER_HOME" $env:ANDROID_USER_HOME
Append-TomlSet $Builder "ANDROID_SDK_HOME" $env:ANDROID_SDK_HOME
if (-not [string]::IsNullOrWhiteSpace($env:JAVA_HOME)) { Append-TomlSet $Builder "JAVA_HOME" $env:JAVA_HOME }
Append-TomlSet $Builder "ADB_VENDOR_KEYS" $env:ADB_VENDOR_KEYS
Append-TomlSet $Builder "APKTOOL_FRAMEWORK_DIR" $env:APKTOOL_FRAMEWORK_DIR
Append-TomlSet $Builder "FRIDA_CACHE_DIR" $env:FRIDA_CACHE_DIR
Append-TomlSet $Builder "MITMPROXY_HOME" $env:MITMPROXY_HOME
Append-TomlSet $Builder "APPIUM_HOME" $env:APPIUM_HOME
Append-TomlSet $Builder "APK_LAB_CACHE_DIR" $env:APK_LAB_CACHE_DIR
Append-TomlSet $Builder "APK_LAB_TMP_DIR" $env:APK_LAB_TMP_DIR
Append-TomlSet $Builder "APK_LAB_JOBS_DIR" $env:APK_LAB_JOBS_DIR
if (-not [string]::IsNullOrWhiteSpace($env:HOMEDRIVE)) { Append-TomlSet $Builder "HOMEDRIVE" $env:HOMEDRIVE }
if (-not [string]::IsNullOrWhiteSpace($env:HOMEPATH)) { Append-TomlSet $Builder "HOMEPATH" $env:HOMEPATH }

# The core shell allowlist excludes these CODEX_* switches. The existing
# automation wrapper needs all three to accept the explicitly chosen proxy.
Append-TomlSet $Builder "CODEX_PROXY_ENABLED" $env:CODEX_PROXY_ENABLED
Append-TomlSet $Builder "CODEX_PROXY_FOR_SUBPROCESS" $env:CODEX_PROXY_FOR_SUBPROCESS
Append-TomlSet $Builder "CODEX_SANDBOX_NETWORK_ACCESS" $env:CODEX_SANDBOX_NETWORK_ACCESS

# 联网时本机命令也走代理：把代理变量传给沙箱子命令(npm/pip)。
# 仅在 代理开 + 选了走代理 + 联网开 时注入（联网关时子命令本就断网，注入无意义）。
# 外层 IsNullOrWhiteSpace 守卫：socks5 模式下 HTTP_PROXY 为 $null，避免写出空值。
if ($ProxyEnabled -and $ProxyForSubprocess -and $SandboxNetworkAccess -eq "true") {
    if (-not [string]::IsNullOrWhiteSpace($env:HTTP_PROXY))  { Append-TomlSet $Builder "HTTP_PROXY"  $env:HTTP_PROXY }
    if (-not [string]::IsNullOrWhiteSpace($env:HTTPS_PROXY)) { Append-TomlSet $Builder "HTTPS_PROXY" $env:HTTPS_PROXY }
    if (-not [string]::IsNullOrWhiteSpace($env:ALL_PROXY))   { Append-TomlSet $Builder "ALL_PROXY"   $env:ALL_PROXY }
    if (-not [string]::IsNullOrWhiteSpace($env:NO_PROXY))    { Append-TomlSet $Builder "NO_PROXY"    $env:NO_PROXY }
}

# 用户 MCP / Plugin 扩展配置只在生成主体之后追加，且不能覆盖上面的安全命名空间。
# Legacy extensions are already durable before early startup can fail. Existing
# sidecar bytes are not rewritten just to build this session's filtered view.
$EffectiveExtensionToml = Get-PersistableCodexExtensionToml -Path $ExtensionStorePath -AllowedNamespaces $PortableExtensionPolicy.AllowedNamespaces
if (-not [string]::IsNullOrWhiteSpace($EffectiveExtensionToml)) {
    [void]$Builder.AppendLine("")
    [void]$Builder.AppendLine("# Preserved portable extension configuration")
    [void]$Builder.Append($EffectiveExtensionToml)
}
if (-not $AllowUserMcp -and -not [string]::IsNullOrWhiteSpace($PreservedExtensionToml) -and $PreservedExtensionToml -match '(?m)^\s*\[\[?\s*(?:mcp_servers|[''"]mcp_servers[''"])' ) {
    Write-Host "User MCP configuration is stored in home\portable-extensions.toml but disabled for this session. A related task requires --portable-extensions AND CODEX_PORTABLE_ALLOW_USER_MCP=true; maintenance mode does not enable it." -ForegroundColor DarkYellow
}

$ConfigPath = $GeneratedConfigPath
Write-Utf8TextAtomic -Path $ConfigPath -Text $Builder.ToString()

if ($UseBrowserLogin -and $BrowserLoginRequired -and $script:CodexRootCommand -eq 'logout') {
    Write-Host "没有可退出的官方账号便携凭证：$BrowserAuthPath" -ForegroundColor Yellow
    exit 1
}

if ($UseBrowserLogin -and $BrowserLoginRequired) {
    $BrowserLoginExitCode = Invoke-CodexOfficialAccountLogin -Flow $BrowserLoginFlow
    if (($BrowserLoginExitCode -ne 0) -or -not (Test-CodexAuthFile $ActiveAuthPath -RequireChatGpt)) {
        Write-Host "官方账号登录未完成，未生成有效凭证：$ActiveAuthPath" -ForegroundColor Red
        if ($BrowserLoginFlow -eq 'device_auth') {
            Write-Host '请确认账号已启用设备码登录；也可选择账号 JSON，或在 env.local.ps1 明确设置 CODEX_BROWSER_LOGIN_FLOW="system_browser"（会读写宿主浏览器数据）。' -ForegroundColor Yellow
        }
        exit 1
    }
    Copy-CodexAuthAtomic -Source $ActiveAuthPath -Destination $BrowserAuthPath -FreshLogin
    Clear-CodexLogoutBlockAfterFreshLogin 'browser'
    Write-Host "官方账号登录凭证已独立保存：$BrowserAuthPath" -ForegroundColor Green
}

function Get-PortableInteractiveLaunchArgs {
    param([object[]]$LaunchArgs, [string]$RootCommand)
    # The managed shared daemon cannot install beneath its own source package.
    # Keep CODEX_HOME inside this package and use the official local TUI backend.
    if ($RootCommand -notin @('', 'resume', 'fork')) { return $LaunchArgs }
    foreach ($argument in $LaunchArgs) {
        if ([string]$argument -eq '--') { break }
        if ([string]$argument -ceq '--no-daemon') { return $LaunchArgs }
    }
    return @('--no-daemon') + @($LaunchArgs)
}

function Invoke-CodexChild {
    param([object[]]$LaunchArgs)
    $interactiveArgs = @(Get-PortableInteractiveLaunchArgs -LaunchArgs $LaunchArgs -RootCommand $script:CodexRootCommand)
    $script:CodexProcessExitCode = Invoke-CodexChildInteractive -LaunchArgs $interactiveArgs
}

# ------------------------------------------------------------
# 8. 固定工作目录并启动 Codex
# ------------------------------------------------------------
Set-Location $PortableWork

$WriteScopeDisplay = if ($SandboxMode -eq "danger-full-access") {
    "YOLO （沙箱关闭；不限制包外写入）"
} elseif ($SandboxMode -eq "read-only") {
    "READ-ONLY （只读沙箱；不代表宿主进程完全不写入）"
} elseif ($PortableMaintenanceMode) {
    "MAINTENANCE （workspace-write；整个便携包可写，审批提升另计）"
} else {
    "SAFE （workspace-write；默认 work/tmp，审批提升另计）"
}
$ShellNetworkDisplay = if ($SandboxMode -eq "danger-full-access") {
    "unrestricted （danger-full-access；沙箱不限制本地命令网络）"
} elseif ($SandboxMode -eq "read-only") {
    "policy （read-only；不使用 workspace-write 网络配置）"
} else {
    "$SandboxNetworkAccess ($(if ($SandboxNetworkAccess -eq 'true') { '本地命令可联网' } else { '本地命令默认断网' }))"
}

Write-Host "Codex Portable 严格便携模式已启动" -ForegroundColor Green
Write-Host "Root          : $Root"
Write-Host "Auth          : $CodexAuthDisplay"
Write-Host "ProviderMode  : $ProviderMode"
Write-Host "Model         : $env:CODEX_MODEL"
Write-Host "Approval      : $ApprovalPolicy"
Write-Host "Sandbox       : $SandboxMode"
Write-Host "Fast          : $(if ($FastModeEnabled) { 'ON (service_tier=priority)' } else { 'OFF (service_tier=default)' })"
Write-Host "Reasoning     : $(if ([string]::IsNullOrWhiteSpace($ReasoningEffort)) { '默认 — 未指定,用模型自带默认(codex 界面显示 default)' } else { $ReasoningEffort + ' (来源: ' + $ReasoningSettingSource + ')' })"
$ModalitiesDisplay = if ($ModelModalitiesKnown) { $ModelInputModalities -join "+" } else { "auto (unknown model -> Codex compatibility default)" }
Write-Host "Modalities    : $ModalitiesDisplay ($(if ($ModelAllowsImage) { 'image_generation 按 Codex 默认' } else { 'image_generation 已禁用' }))"
Write-Host "ShellNetwork  : $ShellNetworkDisplay"
if ($ProviderMode -eq "local_ollama") {
    Write-Host "Transport     : HTTP/SSE（local_ollama 固定 supports_websockets=false）"
} elseif ($ProviderMode -eq "custom_provider") {
    Write-Host "Transport     : $(if ($DisableWebSocket) { 'HTTP/SSE（supports_websockets=false）' } else { 'Responses WebSocket 已显式声明支持（需中转站真实支持）' })"
} elseif ($DisableWebSocket) {
    Write-Host "Transport     : HTTP/SSE（official_chatgpt HTTP-only provider）"
} else {
    Write-Host "Transport     : Codex 官方 ChatGPT 默认传输"
}
Write-Host "Codex Apps    : $(if ($DisableApps) { 'disabled (外部 Apps/Connectors 已关闭)' } else { 'enabled' })"
Write-Host "Plugins       : $(if ($EnablePlugins) { 'enabled' } else { 'disabled' })"
Write-Host "User MCP      : $(if ($AllowUserMcp) { 'enabled (host extension)' } else { 'stored/disabled for this session' })"
Write-Host "PluginSharing : $(if ($EnablePluginSharing) { 'enabled' } else { 'disabled' })"
if ($EnablePlugins -and (Test-Path -LiteralPath $PluginRoot) -and (Test-Path -LiteralPath $PluginMarketplaceFile)) {
    Write-Host "PluginRoot    : $PluginRoot"
    Write-Host "Marketplace   : $PluginMarketplaceFile"
} elseif ($EnablePlugins) {
    Write-Host "PluginRoot    : unavailable" -ForegroundColor Yellow
    Write-Host "Marketplace   : unavailable" -ForegroundColor Yellow
    Write-Host "请检查 home\plugins 与 home\.agents\plugins\marketplace.json 是否可写。" -ForegroundColor Yellow
}
Write-Host "Proxy         : $ProxyDisplay"
Write-Host "CODEX_HOME    : $env:CODEX_HOME"
Write-Host ("写入范围      : " + $WriteScopeDisplay)
if (-not $PortableMaintenanceMode -and -not [string]::IsNullOrWhiteSpace($PortableSessionState)) { Write-Host "SessionCache  : $PortableSessionState" }
Write-Host "Config        : $ConfigPath"
Write-Host "Workdir       : $(Get-Location)"
Write-Host "(以上为本次生效设置;想改默认请编辑 env.ps1 后重启)" -ForegroundColor DarkGray
Write-Host ""

try {
    if ($script:CodexRootCommand -eq 'logout') {
        if ($script:PortableLogoutMode -in @('browser','account_json')) { Set-CodexLogoutBlock $script:PortableLogoutMode }
        $UseAccountJsonLogin = $false
        $UseBrowserLogin = $false
    }
    Invoke-CodexChild -LaunchArgs @($CodexLaunchArgs)

    # `codex logout` only clears Codex's active credential store. This portable
    # wrapper keeps per-mode credential snapshots as well, so an explicit logout
    # must remove the matching snapshot after the official revoke succeeds or the
    # next launch could silently restore the just-logged-out credential.
    if ($script:CodexProcessExitCode -eq 0 -and $script:CodexRootCommand -eq 'logout') {
        if ($script:PortableLogoutMode -eq 'browser') {
            Remove-PortableAuthStateFile -Path $BrowserAuthPath -Name 'browser auth snapshot'
        } elseif ($script:PortableLogoutMode -eq 'account_json') {
            Remove-PortableAuthStateFile -Path $AccountJsonAuthPath -Name 'account JSON auth snapshot'
        }
        Remove-PortableAuthStateFile -Path $ActiveAuthPath -Name 'active auth state'
        Write-CodexAuthMode 'api'
        $UseAccountJsonLogin = $false
        $UseBrowserLogin = $false
        Write-Host "便携登录状态已同步退出；对应持久凭证副本已删除。" -ForegroundColor Green
    }

    # In maintenance mode, successful official `codex mcp` / `codex plugin`
    # commands may rewrite generated config.toml. Persist only the allowlisted
    # extension namespaces back to the sidecar after a successful command.
    if ($script:CodexProcessExitCode -eq 0 -and $PortableMaintenanceMode -and $script:CodexRootCommand -in @('mcp','plugin')) {
        Save-PortableExtensionCommandResult -ConfigPath $ConfigPath -StorePath $ExtensionStorePath -Command $script:CodexRootCommand -AllowedNamespaces $PortableExtensionPolicy.AllowedNamespaces
    }
} finally {
    # Credential snapshots are part of Codex-run cleanup.  Host resource cleanup is
    # intentionally outside this nested block so it also covers failures before the
    # Codex process starts (for example a bridge-success/config-failure path).
    if ($script:CodexRootCommand -ne 'logout' -and $UseAccountJsonLogin -and -not (Test-CodexLogoutBlocked 'account_json') -and (Test-CodexAuthFile $ActiveAuthPath -RequireChatGpt)) {
        Copy-CodexAuthAtomic -Source $ActiveAuthPath -Destination $AccountJsonAuthPath
    }
    if ($script:CodexRootCommand -ne 'logout' -and $UseBrowserLogin -and -not (Test-CodexLogoutBlocked 'browser') -and (Test-CodexAuthFile $ActiveAuthPath -RequireChatGpt)) {
        Copy-CodexAuthAtomic -Source $ActiveAuthPath -Destination $BrowserAuthPath
    }
}
$script:PortableLifecycleExitCode = $script:CodexProcessExitCode
} finally {
    # Idempotent outer lifecycle cleanup: every early exit/throw after session-state
    # creation reaches here, including failures after the SOCKS bridge has started.
    try {
        $stopBridge = Get-Command Stop-CodexSocksHttpBridge -CommandType Function -ErrorAction SilentlyContinue
        if ($null -ne $stopBridge) {
            try { Stop-CodexSocksHttpBridge } catch { Write-Host ("代理桥清理失败：" + $_.Exception.Message) -ForegroundColor DarkYellow }
        }
    } finally {
        if (-not $PortableMaintenanceMode -and -not [string]::IsNullOrWhiteSpace($PortableSessionState)) {
            try { Remove-PortableSessionTree -Path $PortableSessionState } catch { Write-Host ("会话缓存清理失败：" + $_.Exception.Message) -ForegroundColor DarkYellow }
        }

    }
}
} finally {
    if ($null -ne $PortableInstanceFileLock) {
        try { $PortableInstanceFileLock.Dispose() } catch {}
        $PortableInstanceFileLock = $null
    }
    if ($PortableInstanceMutexHeld) {
        try { $PortableInstanceMutex.ReleaseMutex() } catch {}
        $PortableInstanceMutexHeld = $false
    }
    if ($null -ne $PortableInstanceMutex) {
        try { $PortableInstanceMutex.Dispose() } catch {}
        $PortableInstanceMutex = $null
    }
}
if ($null -ne $script:PortableLifecycleExitCode) { exit $script:PortableLifecycleExitCode }
exit 1
