# ============================================================
# Codex Portable 隔离检查脚本
# 默认只检查包内；读取真实用户目录/注册表属于包外操作，必须显式授权。
# 用法：
#   .\检查隔离.ps1                       # 仅包内
#   .\检查隔离.ps1 -ScanHostResidue      # 本次明确允许只读扫描宿主残留
#   .\检查隔离.ps1 -PromptHostScan       # 交互询问一次
# ============================================================
param(
    [switch]$Pause,
    [switch]$ScanHostResidue,
    [switch]$PromptHostScan
)

$ErrorActionPreference = "Stop"
$Root = [System.IO.Path]::GetFullPath((Split-Path -Parent $MyInvocation.MyCommand.Path)).TrimEnd("\\")
$RootItem = Get-Item -LiteralPath $Root -Force -ErrorAction Stop
if (($RootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { throw "拒绝以重解析点作为 Codex Portable 根目录：$Root" }

function Test-IsUnderDirectory {
    param([string]$Path, [string]$Directory)
    try {
        if ([string]::IsNullOrWhiteSpace($Path) -or [string]::IsNullOrWhiteSpace($Directory)) { return $false }
        $fullPath = [System.IO.Path]::GetFullPath($Path).TrimEnd("\\")
        $baseDir = [System.IO.Path]::GetFullPath($Directory).TrimEnd("\\")
        if (-not (Test-Path -LiteralPath $baseDir)) { return $false }
        $baseItem = Get-Item -LiteralPath $baseDir -Force -ErrorAction Stop
        if (($baseItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { return $false }
        if ($fullPath.Equals($baseDir, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
        $prefix = $baseDir + "\"
        if (-not $fullPath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) { return $false }
        $relative = $fullPath.Substring($prefix.Length)
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

$PortableHome = Join-Path $Root "home-runtime"
$PortableAppData = Join-Path $Root "appdata"
$PortableLocalAppData = Join-Path $Root "localappdata"
$PortableProgramData = Join-Path $Root "programdata"
$PortableTmp = Join-Path $Root "tmp"
$PortableCache = Join-Path $Root "cache"
foreach ($dir in @(
    $PortableHome, $PortableAppData, $PortableLocalAppData, $PortableProgramData, $PortableTmp,
    (Join-Path $PortableLocalAppData "Microsoft\Windows\PowerShell"),
    $PortableCache, (Join-Path $PortableCache "pip"), (Join-Path $PortableCache "npm"),
    (Join-Path $PortableCache "npm-prefix"), (Join-Path $PortableCache "python-userbase"),
    (Join-Path $PortableCache "pycache")
)) {
    if (-not (Test-IsUnderDirectory -Path $dir -Directory $Root)) { throw "拒绝包外或重解析点目录：$dir" }
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

$env:HOME=$PortableHome; $env:USERPROFILE=$PortableHome
$env:APPDATA=$PortableAppData; $env:LOCALAPPDATA=$PortableLocalAppData
$env:PROGRAMDATA=$PortableProgramData; $env:ALLUSERSPROFILE=$PortableProgramData
$env:TEMP=$PortableTmp; $env:TMP=$PortableTmp; $env:TMPDIR=$PortableTmp
$env:XDG_CACHE_HOME=$PortableCache; $env:XDG_CONFIG_HOME=$PortableAppData
$env:XDG_DATA_HOME=$PortableLocalAppData; $env:XDG_STATE_HOME=Join-Path $PortableLocalAppData "state"
$env:PSModuleAnalysisCachePath=Join-Path $PortableLocalAppData "Microsoft\Windows\PowerShell\ModuleAnalysisCache"
$env:PIP_CACHE_DIR=Join-Path $PortableCache "pip"; $env:PYTHONUSERBASE=Join-Path $PortableCache "python-userbase"
$env:PYTHONPYCACHEPREFIX=Join-Path $PortableCache "pycache"; $env:NPM_CONFIG_CACHE=Join-Path $PortableCache "npm"
$env:NPM_CONFIG_PREFIX=Join-Path $PortableCache "npm-prefix"; $env:NPM_CONFIG_GLOBALCONFIG=Join-Path $PortableCache "npm\global.npmrc"
$env:NPM_CONFIG_USERCONFIG=Join-Path $PortableHome ".npmrc"
$env:CODEX_INSTALL_DIR=$Root; $env:POWERSHELL_TELEMETRY_OPTOUT="1"

if ($PromptHostScan -and -not $ScanHostResidue) {
    $answer = Read-Host "隔离检查需要读取真实用户目录和 HKCU 注册表才能扫描包外残留。是否仅本次允许只读扫描宿主？(y/N)"
    if ($answer -match '^(?i:y|yes)$') { $ScanHostResidue = $true }
}

Write-Host "当前便携包目录： $Root" -ForegroundColor Cyan
Write-Host ""
Write-Host "包根安全检查：" -ForegroundColor Green
Write-Host "  OK  包根不是 junction/symlink/reparse point"

$KnownInside = @('home','logs','sqlite','login_json','tmp','work','cache','appdata','localappdata','programdata','home-runtime','tool') | ForEach-Object { Join-Path $Root $_ }
$PackageWarnings = $false
Write-Host ""
Write-Host "包内目录检查：" -ForegroundColor Green
foreach ($p in $KnownInside) {
    if (Test-Path -LiteralPath $p) {
        if (Test-IsUnderDirectory -Path $p -Directory $Root) { Write-Host "  OK  $p" }
        else { $PackageWarnings=$true; Write-Host "  警告：路径越界或含重解析点：$p" -ForegroundColor Yellow }
    } else { Write-Host "  缺少 $p" -ForegroundColor Yellow; $PackageWarnings=$true }
}

function Test-LegacyOpenPyxlRootTemp($item) {
    if ($null -eq $item -or $item.PSIsContainer) { return $false }
    if ([System.IO.Path]::GetDirectoryName($item.FullName).TrimEnd('\\') -ne $Root.TrimEnd('\\')) { return $false }
    return $item.Name -like 'openpyxl.*'
}
function Test-LoginJsonTempFile($item) {
    if ($null -eq $item -or $item.PSIsContainer) { return $false }
    return ($item.Name -like 'login-json-http-*' -or $item.Name -like 'login-json-probe-*.json' -or
        $item.Name -like 'login-json-*.body' -or $item.Name -like 'login-json-*.headers' -or
        $item.Name -like 'login-json-*.request.json' -or $item.Name -like 'login-json-*.stderr' -or
        $item.Name -like '__PSScriptPolicyTest_*' -or $item.Name -like 'openpyxl.*')
}
Write-Host ""
Write-Host "包内临时残留检查：" -ForegroundColor Green
$RootTempJunk=@(Get-ChildItem -LiteralPath $Root -Force -File -ErrorAction SilentlyContinue | Where-Object { Test-LegacyOpenPyxlRootTemp $_ })
$TmpTempJunk=@(); $TmpDir=Join-Path $Root 'tmp'
if (Test-Path -LiteralPath $TmpDir) { $TmpTempJunk=@(Get-ChildItem -LiteralPath $TmpDir -Force -File -ErrorAction SilentlyContinue | Where-Object { Test-LoginJsonTempFile $_ }) }
if ($RootTempJunk.Count) { $PackageWarnings=$true; Write-Host "  发现包根旧版 openpyxl 临时残留：$($RootTempJunk.Count) 个" -ForegroundColor Yellow } else { Write-Host "  未发现包根旧版 openpyxl 临时残留" }
if ($TmpTempJunk.Count) { $PackageWarnings=$true; Write-Host "  发现 tmp 内账号检测临时残留：$($TmpTempJunk.Count) 个" -ForegroundColor Yellow } else { Write-Host "  未发现 tmp 内账号检测临时残留" }

Write-Host ""
Write-Host "插件隔离检查（包内）：" -ForegroundColor Green
$CodexHome=Join-Path $Root 'home'; $PluginRoot=Join-Path $CodexHome 'plugins'; $PluginMarketplace=Join-Path $CodexHome '.agents\plugins\marketplace.json'
foreach ($p in @($PluginRoot,(Split-Path -Parent $PluginMarketplace))) {
    if (Test-IsUnderDirectory -Path $p -Directory $Root) { Write-Host "  OK  包内插件路径：$p" }
    else { $PackageWarnings=$true; Write-Host "  警告：插件路径不安全：$p" -ForegroundColor Yellow }
}
if (Test-Path -LiteralPath $PluginMarketplace) {
    try {
        $jsonText=[System.IO.File]::ReadAllText($PluginMarketplace)
        $null=$jsonText | ConvertFrom-Json
        Write-Host "  OK  Marketplace JSON 可解析"
        foreach ($m in [regex]::Matches($jsonText, '(\.\.?[/\\][^"'']+|[A-Za-z]:[/\\][^"'']+)')) {
            $ref=$m.Value; $resolved=if ([IO.Path]::IsPathRooted($ref)){$ref}else{Join-Path $CodexHome $ref}
            if (-not (Test-IsUnderDirectory -Path $resolved -Directory $PluginRoot)) { $PackageWarnings=$true; Write-Host "  警告：Marketplace 引用疑似越界：$ref" -ForegroundColor Yellow }
        }
    } catch { $PackageWarnings=$true; Write-Host "  警告：Marketplace JSON 格式错误" -ForegroundColor Yellow }
}
if (Test-Path -LiteralPath $PluginRoot) {
    foreach ($dir in Get-ChildItem -LiteralPath $PluginRoot -Directory -Force -ErrorAction SilentlyContinue) {
        $manifest=Join-Path $dir.FullName '.codex-plugin\plugin.json'
        if (Test-Path -LiteralPath $manifest) { Write-Host "  OK  插件清单：$manifest" } else { Write-Host "  提示：缺少插件清单：$($dir.FullName)" -ForegroundColor DarkGray }
    }
}

function Get-RegistryValue { param([string]$Path,[string]$Name)
    try { $item=Get-ItemProperty -LiteralPath $Path -ErrorAction Stop; $prop=$item.PSObject.Properties[$Name]; if($null-ne $prop -and -not [string]::IsNullOrWhiteSpace([string]$prop.Value)){return [string]$prop.Value} } catch {}
    return ''
}
function Get-ActualKnownFolder { param([string]$EnvName,[string]$ShellName,[string]$SpecialFolder)
    $value=Get-RegistryValue 'HKCU:\Volatile Environment' $EnvName
    if([string]::IsNullOrWhiteSpace($value)-and $ShellName){$value=Get-RegistryValue 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders' $ShellName}
    if([string]::IsNullOrWhiteSpace($value)-and $SpecialFolder){try{$value=[Environment]::GetFolderPath($SpecialFolder)}catch{}}
    return $value
}

$FoundHostResidue=$false
if ($ScanHostResidue) {
    Write-Host ""
    Write-Host "宿主只读残留检查（已获本次授权）：" -ForegroundColor Green
    $ActualUserProfile=Get-ActualKnownFolder 'USERPROFILE' '' 'UserProfile'
    $ActualAppData=Get-ActualKnownFolder 'APPDATA' 'AppData' 'ApplicationData'
    $ActualLocalAppData=Get-ActualKnownFolder 'LOCALAPPDATA' 'Local AppData' 'LocalApplicationData'
    $targets=New-Object System.Collections.Generic.List[string]
    foreach($pair in @(@($ActualUserProfile,'.codex'),@($ActualUserProfile,'.openai'),@($ActualUserProfile,'.agents\plugins'),@($ActualUserProfile,'plugins'),@($ActualAppData,'OpenAI'),@($ActualLocalAppData,'OpenAI'),@($ActualLocalAppData,'Programs\OpenAI\Codex'))){
        if(-not [string]::IsNullOrWhiteSpace([string]$pair[0])){$t=Join-Path $pair[0] $pair[1]; if(-not (Test-IsUnderDirectory -Path $t -Directory $Root)){$targets.Add($t)|Out-Null}}
    }
    foreach($p in $targets|Select-Object -Unique){if(Test-Path -LiteralPath $p){$FoundHostResidue=$true;Write-Host "  发现包外残留：$p" -ForegroundColor Yellow}else{Write-Host "  未发现：$p"}}
    $RootDrive=[IO.Path]::GetPathRoot($Root); $driveCache=Join-Path $RootDrive 'Microsoft\Windows\PowerShell\StartupProfileData-NonInteractive'
    if(-not (Test-IsUnderDirectory -Path $driveCache -Directory $Root) -and (Test-Path -LiteralPath $driveCache)){$FoundHostResidue=$true;Write-Host "  发现盘根 PowerShell 缓存：$driveCache" -ForegroundColor Yellow}
} else {
    Write-Host ""
    Write-Host "宿主残留检查：未执行。" -ForegroundColor DarkGray
    Write-Host "  原因：读取真实用户目录/注册表属于包外只读操作，尚未取得本次授权。" -ForegroundColor DarkGray
    Write-Host "  需要时运行：检查隔离.bat（会询问）或 检查隔离.ps1 -ScanHostResidue" -ForegroundColor DarkGray
}

Write-Host ""
if ($FoundHostResidue) { Write-Host "已发现宿主残留；本脚本只报告，不删除包外内容。" -ForegroundColor Yellow }
elseif ($ScanHostResidue -and $PackageWarnings) { Write-Host "宿主常见残留未发现；包内仍有警告。" -ForegroundColor Yellow }
elseif ($ScanHostResidue) { Write-Host "宿主常见残留未发现。" -ForegroundColor Green }
elseif ($PackageWarnings) { Write-Host "包内检查完成，但有警告；宿主未扫描。" -ForegroundColor Yellow }
else { Write-Host "包内隔离检查通过；宿主未扫描。" -ForegroundColor Green }
Write-Host "注意：Windows 事件日志、杀毒记录、DNS/系统网络缓存等不属于应用目录，便携脚本无法完全阻止。"
if ($Pause) { pause }
