# ============================================================
# [codex-clean-cache] Codex Portable - 缓存 / 运行残留清理脚本
# 新交互：先询问是否完整清理；选择 N 后逐项询问 Skills/work/Plugins。
# 参数：-CleanSkills -CleanWork -CleanPlugins -CleanAll -Preserve* -WhatIf -Yes
# ============================================================
param(
    [switch]$WhatIf,
    [switch]$Yes,
    [switch]$PreserveSkills,
    [switch]$PreserveWork,
    [switch]$PreservePlugins,
    [switch]$CleanSkills,
    [switch]$CleanWork,
    [switch]$CleanPlugins,
    [switch]$CleanAll,
    [switch]$InteractiveMode
)
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
# Reject a linked package ancestor before checking markers or opening either lock.
$bootstrapAncestors = New-Object System.Collections.Stack
$bootstrapCursor = [IO.Path]::GetFullPath($PSCommandPath)
while ($bootstrapCursor) {
    $bootstrapAncestors.Push($bootstrapCursor)
    $bootstrapParent = Split-Path -Parent $bootstrapCursor
    if ($bootstrapParent -eq $bootstrapCursor) { break }
    $bootstrapCursor = $bootstrapParent
}
while ($bootstrapAncestors.Count -gt 0) {
    $bootstrapItem = Get-Item -LiteralPath $bootstrapAncestors.Pop() -Force -ErrorAction Stop
    if (($bootstrapItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
        ($bootstrapItem.PSObject.Properties['LinkType'] -and $bootstrapItem.LinkType) -or
        (-not $bootstrapItem.PSIsContainer -and ([string]$bootstrapItem.Mode).Contains('l'))) {
        throw '缓存清理入口及其祖先目录不能是 hardlink/reparse/link。'
    }
}

foreach ($g in @('codex.exe', 'run-codex.ps1', 'env.ps1')) {
    if (-not (Test-Path -LiteralPath (Join-Path $Root $g))) {
        Write-Host "[安全终止] 当前目录不像 Codex 便携包（缺少 $g），未删除任何文件。" -ForegroundColor Red
        exit 1
    }
}

function Resolve-FullPath([string]$Path) { return [System.IO.Path]::GetFullPath($Path).TrimEnd('\') }
function Test-IsUnderDirectory {
    param([string]$Path, [string]$Directory)
    try {
        if ([string]::IsNullOrWhiteSpace($Path) -or [string]::IsNullOrWhiteSpace($Directory)) { return $false }
        $fullPath = Resolve-FullPath $Path
        $baseDir = Resolve-FullPath $Directory
        if (-not (Test-Path -LiteralPath $baseDir)) { return $false }
        $baseItem = Get-Item -LiteralPath $baseDir -Force -ErrorAction Stop
        if (($baseItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { return $false }

        if ($fullPath.Equals($baseDir, [System.StringComparison]::OrdinalIgnoreCase)) { return $false }
        if (-not $fullPath.StartsWith($baseDir + '\', [System.StringComparison]::OrdinalIgnoreCase)) { return $false }
        $relative = $fullPath.Substring(($baseDir + '\').Length)
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
    } catch { return $false }
}
function Assert-PackagePath([string]$Path) {
    if (-not (Test-IsUnderDirectory -Path $Path -Directory $Root)) { throw "拒绝包外或包根路径：$Path" }
}

# 与启动器/账号检查共用包根独占文件锁：运行中的便携包不允许同时清缓存。
$CleanupPackageFileLock = $null
$CleanupBrowserFileLock = $null
$CleanupPackageLockPath = Join-Path $Root '.codex-portable.instance.lock'
Assert-PackagePath $CleanupPackageLockPath
if (Test-Path -LiteralPath $CleanupPackageLockPath -PathType Leaf) {
    $lockItem = Get-Item -LiteralPath $CleanupPackageLockPath -Force -ErrorAction Stop
    $lockLinkTypeProperty = $lockItem.PSObject.Properties['LinkType']
    $lockLinkType = if ($null -ne $lockLinkTypeProperty) { [string]$lockLinkTypeProperty.Value } else { '' }
    if (($lockItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 -or
        $lockLinkType -eq 'HardLink' -or ([string]$lockItem.Mode).Contains('l')) {
        Write-Host "[安全终止] 包级锁文件是 hardlink/reparse/link；未清理任何文件。" -ForegroundColor Red
        exit 2
    }
}
try {
try {
    $CleanupPackageFileLock = [System.IO.File]::Open(
        $CleanupPackageLockPath,
        [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None
    )
} catch {
    Write-Host "[安全终止] Codex 便携包正在运行，或无法安全创建包级锁文件；未清理任何文件。" -ForegroundColor Red
    exit 2
}
# A browser task may run independently of Codex. Hold its own lock for the whole
# preview/cleanup operation so persistent profiles cannot be deleted during use.
try {
    $CleanupBrowserFileLock = & {
        param([string]$PackageRoot)
        $helper = Join-Path $PackageRoot 'tool\automation\portable-automation.ps1'
        # Inspect the complete helper ancestry before loading any project code.
        $ancestors = New-Object System.Collections.Stack
        $cursor = [IO.Path]::GetFullPath($helper)
        while ($cursor) {
            $ancestors.Push($cursor)
            $parent = Split-Path -Parent $cursor
            if ($parent -eq $cursor) { break }
            $cursor = $parent
        }
        while ($ancestors.Count -gt 0) {
            $item = Get-Item -LiteralPath $ancestors.Pop() -Force -ErrorAction Stop
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
                ($item.PSObject.Properties['LinkType'] -and $item.LinkType) -or
                (-not $item.PSIsContainer -and ([string]$item.Mode).Contains('l'))) {
                throw 'Browser cleanup helper path must not contain links.'
            }
        }
        if ($item.PSIsContainer) { throw 'Browser cleanup helper must be an ordinary file.' }
        # The child scope keeps helper StrictMode and functions out of this script.
        . $helper
        Open-AutomationBrowserLock -Root $PackageRoot
    } $Root
} catch {
    Write-Host '[安全终止] 浏览器正在运行，或浏览器状态锁/清理助手不安全；未清理任何文件。' -ForegroundColor Red
    exit 2
}
function Read-YesNo([string]$Prompt, [string]$Default = 'N') {
    while ($true) {
        $ans = (Read-Host "$Prompt [Y/N，默认 $Default]").Trim()
        if ([string]::IsNullOrWhiteSpace($ans)) { $ans = $Default }
        switch -Regex ($ans) {
            '^(y|yes|是)$' { return $true }
            '^(n|no|否)$' { return $false }
            default { Write-Host "输入无效，请输入 Y 或 N。" -ForegroundColor Yellow }
        }
    }
}

$BoundPreserve = $PSBoundParameters.ContainsKey('PreserveSkills') -or $PSBoundParameters.ContainsKey('PreserveWork') -or $PSBoundParameters.ContainsKey('PreservePlugins')
$BoundClean = $PSBoundParameters.ContainsKey('CleanSkills') -or $PSBoundParameters.ContainsKey('CleanWork') -or $PSBoundParameters.ContainsKey('CleanPlugins') -or $PSBoundParameters.ContainsKey('CleanAll')
if ($BoundPreserve -and $BoundClean) {
    throw '不能同时使用 -Preserve* 和 -Clean* 参数。'
}

# 非交互模式默认保留用户资产；-Clean* 的范围与 -Yes/-WhatIf 是否存在无关。
if (-not $InteractiveMode -and -not $BoundPreserve) {
    $PreserveSkills = $true
    $PreserveWork = $true
    $PreservePlugins = $true
    if ($CleanAll) {
        $PreserveSkills = $false; $PreserveWork = $false; $PreservePlugins = $false
    } else {
        if ($CleanSkills) { $PreserveSkills = $false }
        if ($CleanWork) { $PreserveWork = $false }
        if ($CleanPlugins) { $PreservePlugins = $false }
    }
}

if ($InteractiveMode -or (-not $BoundPreserve -and -not $BoundClean -and -not $Yes -and -not $WhatIf)) {
    Write-Host ""
    Write-Host "Codex 便携包缓存清理" -ForegroundColor Cyan
    $all = Read-YesNo "是否清理全部缓存（包括 Skills、work、Plugins）？" 'N'
    if ($all) {
        $PreserveSkills = $false; $PreserveWork = $false; $PreservePlugins = $false
    } else {
        $CleanSkills = Read-YesNo "是否清理 Skills？" 'N'
        $CleanWork = Read-YesNo "是否清理 work？" 'N'
        $CleanPlugins = Read-YesNo "是否清理 Plugins？" 'N'
        $PreserveSkills = -not $CleanSkills
        $PreserveWork = -not $CleanWork
        $PreservePlugins = -not $CleanPlugins
    }
}

$PortableHome = Join-Path $Root 'home-runtime'
$PortableAppData = Join-Path $Root 'appdata'
$PortableLocalAppData = Join-Path $Root 'localappdata'
$PortableProgramData = Join-Path $Root 'programdata'
$PortableTmp = Join-Path $Root 'tmp'
$PortableCache = Join-Path $Root 'cache'
$env:CODEX_HOME = Join-Path $Root 'home'
$env:CODEX_SQLITE_HOME = Join-Path $Root 'sqlite'
$env:HOME = $PortableHome; $env:USERPROFILE = $PortableHome
$env:APPDATA = $PortableAppData; $env:LOCALAPPDATA = $PortableLocalAppData
$env:PROGRAMDATA = $PortableProgramData; $env:ALLUSERSPROFILE = $PortableProgramData
$env:TEMP = $PortableTmp; $env:TMP = $PortableTmp; $env:TMPDIR = $PortableTmp
$env:XDG_CACHE_HOME = $PortableCache; $env:XDG_CONFIG_HOME = $PortableAppData
$env:XDG_DATA_HOME = $PortableLocalAppData; $env:XDG_STATE_HOME = Join-Path $PortableLocalAppData 'state'
$env:PSModuleAnalysisCachePath = Join-Path $PortableLocalAppData 'Microsoft\Windows\PowerShell\ModuleAnalysisCache'
$env:PIP_CACHE_DIR = Join-Path $PortableCache 'pip'; $env:PYTHONUSERBASE = Join-Path $PortableCache 'python-userbase'
$env:PYTHONPYCACHEPREFIX = Join-Path $PortableCache 'pycache'; $env:NPM_CONFIG_CACHE = Join-Path $PortableCache 'npm'
$env:NPM_CONFIG_PREFIX = Join-Path $PortableCache 'npm-prefix'; $env:NPM_CONFIG_GLOBALCONFIG = Join-Path $PortableCache 'npm\global.npmrc'
$env:NPM_CONFIG_USERCONFIG = Join-Path $PortableHome '.npmrc'
$env:CODEX_INSTALL_DIR = $Root; $env:POWERSHELL_TELEMETRY_OPTOUT = '1'
$env:ANDROID_HOME = Join-Path $Root 'tool\android\sdk'
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:ANDROID_USER_HOME = Join-Path $Root 'home-runtime\.android'
$env:ANDROID_SDK_HOME = Join-Path $Root 'home-runtime'
$env:JAVA_HOME = Join-Path $Root 'tool\android\jdk'
$env:ADB_VENDOR_KEYS = Join-Path $Root 'home-runtime\.android\adbkey'
$env:APKTOOL_FRAMEWORK_DIR = Join-Path $PortableCache 'android\apktool-framework'
$env:FRIDA_CACHE_DIR = Join-Path $PortableCache 'android\frida'
$env:MITMPROXY_HOME = Join-Path $PortableCache 'android\mitmproxy'
$env:APPIUM_HOME = Join-Path $PortableCache 'android\appium'
$env:APK_LAB_CACHE_DIR = Join-Path $PortableCache 'android\apk-lab'
$env:APK_LAB_TMP_DIR = Join-Path $Root 'tmp\android'
$env:APK_LAB_JOBS_DIR = Join-Path $Root 'work\apk-jobs'

foreach ($dir in @('home','home\skills','home\plugins','home\.agents\plugins','home-runtime','home-runtime\.android','sqlite','appdata','localappdata','programdata','tmp','tmp\android','cache','cache\android','cache\android\apktool-framework','cache\android\frida','cache\android\mitmproxy','cache\android\appium','cache\android\apk-lab','logs','work','work\apk-jobs','tool','tool\android')) {
    $dirPath = Join-Path $Root $dir
    Assert-PackagePath $dirPath
    New-Item -ItemType Directory -Force -Path $dirPath | Out-Null
}
$PluginKeep = Join-Path $Root 'home\plugins\.keep'
if (-not (Test-Path -LiteralPath $PluginKeep)) { New-Item -ItemType File -Force -Path $PluginKeep | Out-Null }

$Protected = New-Object System.Collections.Generic.List[object]
if ($PreserveSkills) { $Protected.Add([pscustomobject]@{Name='Skills'; Path=(Join-Path $Root 'home\skills')}) | Out-Null }
if ($PreserveWork) { $Protected.Add([pscustomobject]@{Name='work'; Path=(Join-Path $Root 'work')}) | Out-Null }
if ($PreservePlugins) {
    $Protected.Add([pscustomobject]@{Name='Plugins'; Path=(Join-Path $Root 'home\plugins')}) | Out-Null
    $Protected.Add([pscustomobject]@{Name='Plugins Marketplace'; Path=(Join-Path $Root 'home\.agents\plugins')}) | Out-Null
}
function Test-IsProtectedPath([string]$Path) {
    # Failed transactions retain these paths for recovery, not cache disposal.
    $full = Resolve-FullPath $Path
    $baseRoot = Resolve-FullPath $Root
    if ($full.StartsWith($baseRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        $relative = $full.Substring($baseRoot.Length + 1)
        if ($relative -match '^tmp\\codex-official-update-[0-9a-f]{32}(\\|$)' -or
            $relative -match '^home\\[^\\]+\.bak-[0-9a-f]{32}$') { return $true }
    }
    foreach ($entry in $Protected) {
        $full = Resolve-FullPath $Path; $base = Resolve-FullPath $entry.Path
        if ($full.Equals($base, [System.StringComparison]::OrdinalIgnoreCase) -or $full.StartsWith($base + '\', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    return $false
}
function Test-LegacyOpenPyxlRootTemp($item) {
    if ($null -eq $item -or $item.PSIsContainer) { return $false }
    if ((Resolve-FullPath ([System.IO.Path]::GetDirectoryName($item.FullName))) -ne (Resolve-FullPath $Root)) { return $false }
    return $item.Name -like 'openpyxl.*'
}
$PersistentHomeFilePaths = @(
    'auth.json','auth-account-json.json','auth-browser.json','auth-transition.block','logout-browser.block','logout-account_json.block','installation_id','mode','portable-extensions.toml','cap_sid'
) | ForEach-Object { Resolve-FullPath (Join-Path $Root ('home\' + $_)) }
# `.keep` is a package skeleton marker only at known package-owned locations. Do not
# preserve an arbitrary user/project file merely because its basename is `.keep`.
$ExpectedKeepFilePaths = @(
    'appdata\.keep',
    'cache\.keep','cache\aws\.keep','cache\azure\.keep','cache\cargo\.keep','cache\composer\.keep',
    'cache\docker\.keep','cache\dotnet\.keep','cache\gradle\.keep','cache\maven\.keep',
    'cache\npm\.keep','cache\nuget\.keep','cache\pip\.keep','cache\pnpm\.keep','cache\pycache\.keep',
    'cache\ruby\.keep','cache\rustup\.keep','cache\yarn\.keep',
    'home-runtime\.keep','home\.keep','home\.sandbox\.keep','home\plugins\.keep',
    'localappdata\.keep','logs\.keep','programdata\.keep','sqlite\.keep','tmp\.keep','work\.keep'
) | ForEach-Object { Resolve-FullPath (Join-Path $Root $_) }
function Test-ContainsProtectedPath([string]$Path) {
    $full = Resolve-FullPath $Path
    foreach ($entry in $Protected) {
        $base = Resolve-FullPath $entry.Path
        if ($base.StartsWith($full + '\', [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    return $false
}
function Get-RemovableItems([string]$dir) {
    $out = New-Object System.Collections.Generic.List[object]
    foreach ($child in (Get-ChildItem -LiteralPath $dir -Force -ErrorAction SilentlyContinue)) {
        if (Test-IsProtectedPath $child.FullName) { continue }
        if (-not (Test-IsUnderDirectory -Path $child.FullName -Directory $Root)) { continue }
        if (-not $child.PSIsContainer) {
            $childFullPath = Resolve-FullPath $child.FullName
            $homeRootForState = Resolve-FullPath (Join-Path $Root 'home')
            $isPersistentHomeFile = $childFullPath -in $PersistentHomeFilePaths
            $isExpectedKeep = $childFullPath -in $ExpectedKeepFilePaths
            $isInvalidAuthBackup = ((Resolve-FullPath ([System.IO.Path]::GetDirectoryName($child.FullName))) -eq $homeRootForState) -and
                                   ($child.Name -like 'auth*.json.invalid-*')
            if (-not $isPersistentHomeFile -and -not $isExpectedKeep -and -not $isInvalidAuthBackup) { $out.Add($child) }
        } else {
            if (($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { continue }
            $expectedKeepPath = Resolve-FullPath (Join-Path $child.FullName '.keep')
            $hasKeep = ($expectedKeepPath -in $ExpectedKeepFilePaths) -and (Test-Path -LiteralPath $expectedKeepPath -PathType Leaf)
            $mustRecurseSafely = $hasKeep -or (Test-ContainsProtectedPath $child.FullName) -or (Test-ContainsReparsePoint $child.FullName)
            if ($mustRecurseSafely) { foreach ($sub in (Get-RemovableItems $child.FullName)) { $out.Add($sub) } }
            else { $out.Add($child) }
        }
    }
    return $out
}
function Test-ContainsReparsePoint([string]$Path) {
    Assert-PackagePath $Path
    try {
        $rootItem = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        if (($rootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { return $true }
        if (-not $rootItem.PSIsContainer) { return $false }

        # 不使用 Get-ChildItem -Recurse：手工遍历并在重解析点处立即停止，
        # 避免枚举器本身跟随 junction/symlink 进入包外。
        $pending = New-Object 'System.Collections.Generic.Stack[string]'
        $pending.Push($rootItem.FullName)
        while ($pending.Count -gt 0) {
            $dir = $pending.Pop()
            foreach ($entry in (Get-ChildItem -LiteralPath $dir -Force -ErrorAction Stop)) {
                if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { return $true }
                if ($entry.PSIsContainer) { $pending.Push($entry.FullName) }
            }
        }
        return $false
    } catch {
        # 无法完整枚举时按“不安全”处理，避免 Remove-Item -Recurse 穿过未知目录结构。
        return $true
    }
}

function Get-SafeTreeSnapshot([string]$Path) {
    Assert-PackagePath $Path
    $directories = New-Object 'System.Collections.Generic.List[object]'
    $files = New-Object 'System.Collections.Generic.List[object]'
    $pending = New-Object 'System.Collections.Generic.Stack[string]'
    try {
        $rootItem = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        if (($rootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            return [pscustomobject]@{ Safe=$false; Reason='root-reparse'; Directories=@(); Files=@() }
        }
        if (-not $rootItem.PSIsContainer) {
            return [pscustomobject]@{ Safe=$true; Reason=''; Directories=@(); Files=@($rootItem) }
        }
        $pending.Push($rootItem.FullName)
        while ($pending.Count -gt 0) {
            $dir = $pending.Pop()
            $dirItem = Get-Item -LiteralPath $dir -Force -ErrorAction Stop
            if (($dirItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                return [pscustomobject]@{ Safe=$false; Reason=('reparse:' + $dir); Directories=$directories.ToArray(); Files=$files.ToArray() }
            }
            if (Test-IsProtectedPath $dir) {
                return [pscustomobject]@{ Safe=$false; Reason=('protected:' + $dir); Directories=$directories.ToArray(); Files=$files.ToArray() }
            }
            [void]$directories.Add($dirItem)
            foreach ($entry in @(Get-ChildItem -LiteralPath $dir -Force -ErrorAction Stop)) {
                if (-not (Test-IsUnderDirectory -Path $entry.FullName -Directory $Root)) {
                    return [pscustomobject]@{ Safe=$false; Reason=('outside:' + $entry.FullName); Directories=$directories.ToArray(); Files=$files.ToArray() }
                }
                if (($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                    return [pscustomobject]@{ Safe=$false; Reason=('reparse:' + $entry.FullName); Directories=$directories.ToArray(); Files=$files.ToArray() }
                }
                if (Test-IsProtectedPath $entry.FullName) {
                    return [pscustomobject]@{ Safe=$false; Reason=('protected:' + $entry.FullName); Directories=$directories.ToArray(); Files=$files.ToArray() }
                }
                if ($entry.PSIsContainer) { $pending.Push($entry.FullName) } else { [void]$files.Add($entry) }
            }
        }
        return [pscustomobject]@{ Safe=$true; Reason=''; Directories=$directories.ToArray(); Files=$files.ToArray() }
    } catch {
        return [pscustomobject]@{ Safe=$false; Reason=('enumeration:' + $_.Exception.Message); Directories=$directories.ToArray(); Files=$files.ToArray() }
    }
}
function Get-ItemSize($item) {
    if (-not $item.PSIsContainer) { return [long]$item.Length }
    $snapshot = Get-SafeTreeSnapshot $item.FullName
    if (-not $snapshot.Safe) { return 0L }
    [long]$sum = 0L
    foreach ($file in @($snapshot.Files)) { $sum += [long]$file.Length }
    return $sum
}
function Write-SafeBootstrapConfig {
    $configPath = Join-Path $Root 'home\config.toml'
    Assert-PackagePath $configPath
    if (Test-Path -LiteralPath $configPath -PathType Leaf) {
        $existing = Get-Item -LiteralPath $configPath -Force -ErrorAction Stop
        $linkTypeProperty = $existing.PSObject.Properties['LinkType']
        $linkType = if ($null -ne $linkTypeProperty) { [string]$linkTypeProperty.Value } else { '' }
        if (($existing.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 -or
            $linkType -eq 'HardLink' -or ([string]$existing.Mode).Contains('l')) {
            throw '拒绝覆盖 hardlink/reparse/link 的 home\config.toml。'
        }
    } elseif (Test-Path -LiteralPath $configPath) {
        throw 'home\config.toml 存在但不是普通文件。'
    }

    $bootstrap = @"
# Bootstrap-only safe fallback. run-codex.ps1 replaces this file on every supported launch.
# Do not put secrets, machine-specific absolute paths, or trusted-project state here.

check_for_update_on_startup = false
cli_auth_credentials_store = "file"
mcp_oauth_credentials_store = "file"
sandbox_mode = "read-only"
approval_policy = "on-request"

[history]
persistence = "none"

[windows]
sandbox = "unelevated"
"@
    $tmp = Join-Path (Split-Path -Parent $configPath) ('.config.toml.bootstrap-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    $replaceBackup = Join-Path (Split-Path -Parent $configPath) ('.config.toml.bootstrap-backup-' + [Guid]::NewGuid().ToString('N') + '.bak')
    Assert-PackagePath $tmp
    Assert-PackagePath $replaceBackup
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $bytes = $utf8NoBom.GetBytes($bootstrap)
    $stream = $null; $temporaryOwned = $false
    try {
        $stream = New-Object System.IO.FileStream($tmp, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
        $temporaryOwned = $true
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
        $stream.Dispose(); $stream = $null
        if (Test-Path -LiteralPath $configPath -PathType Leaf) {
            if (Test-Path -LiteralPath $replaceBackup) { throw 'bootstrap config replace-backup collision' }
            [System.IO.File]::Replace($tmp, $configPath, $replaceBackup, $true)
            $temporaryOwned = $false
            $backupItem = Get-Item -LiteralPath $replaceBackup -Force -ErrorAction Stop
            $backupLinkProperty = $backupItem.PSObject.Properties['LinkType']
            $backupLinkType = if ($null -ne $backupLinkProperty) { [string]$backupLinkProperty.Value } else { '' }
            if ($backupItem.PSIsContainer -or ($backupItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 -or
                $backupLinkType -eq 'HardLink' -or ([string]$backupItem.Mode).Contains('l')) {
                throw 'bootstrap config replace backup is not a safe regular file'
            }
            Remove-Item -LiteralPath $replaceBackup -Force -ErrorAction Stop
        } else {
            [System.IO.File]::Move($tmp, $configPath)
            $temporaryOwned = $false
        }
    } finally {
        if ($null -ne $stream) { try { $stream.Dispose() } catch {} }
        if ($temporaryOwned) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
    }
}

function Remove-PortableItem($item) {
    $path = $item.FullName
    if (Test-IsProtectedPath $path) { Write-Host "[跳过] 保护区：$path" -ForegroundColor DarkGray; return $false }
    if (-not (Test-IsUnderDirectory -Path $path -Directory $Root)) { Write-Host "[跳过] 拒绝清理包外路径：$path" -ForegroundColor Yellow; return $false }
    if (-not $item.PSIsContainer) {
        Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
        return (-not (Test-Path -LiteralPath $path))
    }

    $snapshot = Get-SafeTreeSnapshot $path
    if (-not $snapshot.Safe) {
        Write-Host "[跳过] 目录树无法安全验证，拒绝清理：$path [$($snapshot.Reason)]" -ForegroundColor Yellow
        return $false
    }
    foreach ($file in @($snapshot.Files)) { Remove-Item -LiteralPath $file.FullName -Force -ErrorAction Stop }
    foreach ($dir in @($snapshot.Directories | Sort-Object { $_.FullName.Length } -Descending)) {
        Remove-Item -LiteralPath $dir.FullName -Force -ErrorAction Stop
    }
    return (-not (Test-Path -LiteralPath $path))
}

$RuntimeDirs = @('home','home-runtime','sqlite','appdata','localappdata','programdata','tmp','work','logs','cache','Microsoft')
Write-Host ""
Write-Host "Codex 便携包 - 缓存 / 运行残留清理" -ForegroundColor Cyan
Write-Host "包目录：$Root"
Write-Host "本次清理范围："
Write-Host ("  Skills  ：" + $(if ($PreserveSkills) {'保留'} else {'清理'}))
Write-Host ("  work    ：" + $(if ($PreserveWork) {'保留'} else {'清理'}))
Write-Host ("  Plugins ：" + $(if ($PreservePlugins) {'保留'} else {'清理'}))
Write-Host "  运行缓存：清理"
Write-Host "  浏览器数据：清理 cache\browser（包括 Cookies、网站登录状态和浏览器缓存）"
if (-not $PreserveWork) { Write-Host "注意：本次会清理 work 工作区中的项目文件。" -ForegroundColor Red }

$plan=@(); $grand=0L
$rootItems=@(Get-ChildItem -LiteralPath $Root -Force -File -ErrorAction SilentlyContinue | Where-Object { Test-LegacyOpenPyxlRootTemp $_ })
if ($rootItems.Count -gt 0) { $size=0L; foreach($it in $rootItems){$itemSize=Get-ItemSize $it; $it|Add-Member PortablePlannedSize ([long]$itemSize) -Force; $size+=$itemSize}; $plan += [pscustomobject]@{Dir='包根临时';Items=$rootItems;Count=$rootItems.Count;Size=$size}; $grand+=$size }
foreach ($d in $RuntimeDirs) {
    $p=Join-Path $Root $d
    if (-not (Test-Path -LiteralPath $p)) { continue }
    Assert-PackagePath $p
    $items=@(Get-RemovableItems $p)
    if ($items.Count -eq 0) { continue }
    $size=0L; foreach($it in $items){$itemSize=Get-ItemSize $it; $it|Add-Member PortablePlannedSize ([long]$itemSize) -Force; $size+=$itemSize}
    $plan += [pscustomobject]@{Dir=$d;Items=$items;Count=$items.Count;Size=$size}; $grand+=$size
}
if ($plan.Count -eq 0) {
    if ($WhatIf) {
        Write-Host "已经很干净，没有可清理的运行期残留。" -ForegroundColor Green
        if ($null -ne $CleanupPackageFileLock) { $CleanupPackageFileLock.Dispose(); $CleanupPackageFileLock = $null }
        exit 0
    }
    try {
        # Even when no removable cache remains, restore a missing/stale-safe
        # generated config to the location-independent bootstrap form.
        Write-SafeBootstrapConfig
        Write-Host "已经很干净；安全 bootstrap config 已确认/重建。" -ForegroundColor Green
        if ($null -ne $CleanupPackageFileLock) { $CleanupPackageFileLock.Dispose(); $CleanupPackageFileLock = $null }
        exit 0
    } catch {
        Write-Host ("[失败] 无法确认/重建安全 bootstrap config：" + $_.Exception.Message) -ForegroundColor Red
        if ($null -ne $CleanupPackageFileLock) { $CleanupPackageFileLock.Dispose(); $CleanupPackageFileLock = $null }
        exit 1
    }
}
Write-Host ""
Write-Host "将清理以下内容：" -ForegroundColor Yellow
foreach ($row in $plan) { Write-Host ("  {0,-18} {1,5} 项  {2,12:N0} 字节" -f $row.Dir,$row.Count,$row.Size) }
Write-Host ("  ---- 合计约 " + [math]::Round($grand / 1MB, 2) + " MB ----") -ForegroundColor Yellow
if ($WhatIf) { Write-Host "[预览模式] 未删除任何文件。" -ForegroundColor Cyan; if ($null -ne $CleanupPackageFileLock) { $CleanupPackageFileLock.Dispose(); $CleanupPackageFileLock = $null }; exit 0 }
if (-not $Yes) { if (-not (Read-YesNo "确认执行清理？" 'N')) { Write-Host "已取消，未删除任何文件。" -ForegroundColor Cyan; if ($null -ne $CleanupPackageFileLock) { $CleanupPackageFileLock.Dispose(); $CleanupPackageFileLock = $null }; exit 0 } }
$freed=0L; $errs=0
foreach($row in $plan){ foreach($item in $row.Items){ if(Remove-PortableItem $item){ if($item.PSObject.Properties['PortablePlannedSize']){$freed += [long]$item.PortablePlannedSize} } else { $errs++ } } }
New-Item -ItemType Directory -Force -Path (Join-Path $Root 'home\plugins') | Out-Null
if (-not (Test-Path -LiteralPath $PluginKeep)) { New-Item -ItemType File -Force -Path $PluginKeep | Out-Null }
try {
    # config.toml is generated runtime state, not persistent user configuration.
    # Recreate a location-independent fail-safe bootstrap instead of preserving a
    # possibly stale maintenance/YOLO snapshot. portable-extensions.toml is kept.
    # cap_sid is intentionally preserved once Windows creates it: it is a sandbox
    # capability-SID ledger tied to NTFS ACLs, not an ordinary disposable cache.
    Write-SafeBootstrapConfig
} catch {
    $errs++
    Write-Host ("[失败] 无法重建安全 bootstrap config：" + $_.Exception.Message) -ForegroundColor Red
}
Write-Host ""
if ($errs -eq 0) { Write-Host ("清理完成，释放约 " + [math]::Round($freed / 1MB, 2) + " MB。") -ForegroundColor Green }
else { Write-Host ("清理基本完成（释放约 " + [math]::Round($freed / 1MB, 2) + " MB），但有 $errs 项失败或受保护未删除。") -ForegroundColor Yellow }
if ($null -ne $CleanupPackageFileLock) { $CleanupPackageFileLock.Dispose(); $CleanupPackageFileLock = $null }
if ($errs -gt 0) { exit 1 }
exit 0

} finally {
    if ($null -ne $CleanupBrowserFileLock) {
        try { $CleanupBrowserFileLock.Dispose() } catch {}
        $CleanupBrowserFileLock = $null
    }
    if ($null -ne $CleanupPackageFileLock) {
        try { $CleanupPackageFileLock.Dispose() } catch {}
        $CleanupPackageFileLock = $null
    }
}
