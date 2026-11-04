#Requires -Version 5.1
# Validate real bundled tool executables and env.ps1 mappings on Windows.
# No network requests, personal credentials, installations or Release writes.
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\')
$Config = Join-Path $Root 'env.ps1'
if (Test-Path -LiteralPath (Join-Path $Root 'env.local.ps1')) {
    throw 'Refuse private local overrides in a release verification checkout.'
}
if (-not (Test-Path -LiteralPath $Config -PathType Leaf)) { throw 'Missing portable env.ps1.' }
# Host-supplied paths may never redirect portable tool state.
$env:CODEX_INSTALL_DIR = Join-Path $env:TEMP 'untrusted-root'
$env:CODEX_PYTHON = Join-Path $env:TEMP 'untrusted-python.exe'
. $Config
function Assert-Var([string]$Name, [string]$Expected) {
    $Actual = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if ($Actual -cne $Expected) {
        throw "Tool variable $Name escaped the portable package: $Actual"
    }
}
Assert-Var 'CODEX_INSTALL_DIR' $Root
Assert-Var 'CODEX_PYTHON' (Join-Path $Root 'tool\python\python.exe')
Assert-Var 'ANDROID_HOME' (Join-Path $Root 'tool\android\sdk')
Assert-Var 'ANDROID_SDK_ROOT' (Join-Path $Root 'tool\android\sdk')
Assert-Var 'ANDROID_USER_HOME' (Join-Path $Root 'home-runtime\.android')
Assert-Var 'ANDROID_SDK_HOME' (Join-Path $Root 'home-runtime')
Assert-Var 'JAVA_HOME' (Join-Path $Root 'tool\android\jdk')
Assert-Var 'ADB_VENDOR_KEYS' (Join-Path $Root 'home-runtime\.android\adbkey')
Assert-Var 'APKTOOL_FRAMEWORK_DIR' (Join-Path $Root 'cache\android\apktool-framework')
Assert-Var 'FRIDA_CACHE_DIR' (Join-Path $Root 'cache\android\frida')
Assert-Var 'MITMPROXY_HOME' (Join-Path $Root 'cache\android\mitmproxy')
Assert-Var 'APPIUM_HOME' (Join-Path $Root 'cache\android\appium')
Assert-Var 'APK_LAB_CACHE_DIR' (Join-Path $Root 'cache\android\apk-lab')
Assert-Var 'APK_LAB_TMP_DIR' (Join-Path $Root 'tmp\android')
Assert-Var 'APK_LAB_JOBS_DIR' (Join-Path $Root 'work\apk-jobs')
'02_TOOL_ENV_EFFECTIVE=PASS; root and 15 package-local tool mappings' | Write-Output

$Inventory = Get-Content -LiteralPath (Join-Path $Root 'tool\installed-tools.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Inventory.platform -cne 'win32-x64' -or $Inventory.schema -ne 1) {
    throw 'Unreviewed tool inventory.'
}
$Tracked = @('python','pip','paramiko','node','npm','corepack','playwright-mcp','chromium','adb','7zip','ripgrep','fd','jq')
foreach ($Name in $Tracked) {
    $Entry = $Inventory.tools.$Name
    if ($null -eq $Entry -or $Entry.status -cne 'bundled' -or [string]::IsNullOrWhiteSpace($Entry.version)) {
        throw "Required bundled tool missing from installed-tools.json: $Name"
    }
    $Relative = [string]$Entry.path
    if ($Relative -notmatch '^tool/[a-zA-Z0-9_./-]+$' -or $Relative -match '(^|/)\.\.?(?:/|$)') {
        throw "Untrusted tool path: $Name"
    }
    $File = Join-Path $Root $Relative
    if (-not (Test-Path -LiteralPath $File)) { throw "Bundled tool payload missing: $Name" }
    $Item = Get-Item -LiteralPath $File -Force -ErrorAction Stop
    if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Bundled tool link is not allowed: $Name"
    }
}
'02_TOOL_INVENTORY_AND_PAYLOAD_PATHS=PASS' | Write-Output

# An absolute-path version check alone cannot prove that typing adb, npm,
# python or the CLI tools in a Codex shell resolves to the bundled binary.
# Guard BOTH the launcher declarations and actual Windows command discovery.
$LauncherSource = Get-Content -LiteralPath (Join-Path $Root 'run-codex.ps1') -Raw -Encoding UTF8
$RequiredLauncherDirs = @('bin', 'python', 'node', 'android\platform-tools')
foreach ($RelativeDir in $RequiredLauncherDirs) {
    $Declaration = '(Join-Path $PortableTool "' + $RelativeDir + '")'
    $Pattern = '(?m)^[ \t]*' + [regex]::Escape($Declaration) + ',?[ \t]*\r?$'
    if ([regex]::Matches($LauncherSource, $Pattern).Count -ne 1) {
        throw "Codex launcher does not declare the real tool PATH entry: $RelativeDir"
    }
}
foreach ($Bat in @('启动Codex.bat', '启动Codex-维护模式.bat', '检查login_json.bat')) {
    $Source = Get-Content -LiteralPath (Join-Path $Root $Bat) -Raw -Encoding UTF8
    if (-not $Source.Contains('%~dp0tool\android\platform-tools;')) {
        throw "Windows batch entry misses bundled ADB: $Bat"
    }
}
$CommandPaths = [ordered]@{
    'python.exe' = 'tool\python\python.exe'
    'pip.cmd' = 'tool\bin\pip.cmd'
    'node.exe' = 'tool\node\node.exe'
    'npm.cmd' = 'tool\node\npm.cmd'
    'npx.cmd' = 'tool\node\npx.cmd'
    'corepack.cmd' = 'tool\node\corepack.cmd'
    'adb.exe' = 'tool\android\platform-tools\adb.exe'
    '7z.exe' = 'tool\bin\7z.exe'
    'rg.exe' = 'tool\bin\rg.exe'
    'fd.exe' = 'tool\bin\fd.exe'
    'jq.exe' = 'tool\bin\jq.exe'
}
$OldPath = $env:PATH
try {
    # Simulate only the verified portable PATH prefixes; do not use any host
    # package manager or installed third-party directory as a fallback.
    $PortableDirs = @(
        (Join-Path $Root 'tool\bin'),
        (Join-Path $Root 'tool\python'),
        (Join-Path $Root 'tool\node'),
        (Join-Path $Root 'tool\android\platform-tools')
    )
    $env:PATH = ($PortableDirs -join ';')
    foreach ($Command in $CommandPaths.Keys) {
        $Expected = [IO.Path]::GetFullPath((Join-Path $Root $CommandPaths[$Command]))
        $Resolved = @(Get-Command -Name $Command -CommandType Application -ErrorAction Stop)
        if ($Resolved.Count -ne 1 -or
            [IO.Path]::GetFullPath([string]$Resolved[0].Source) -cne $Expected) {
            throw "Portable command $Command resolves outside its audited package path"
        }
    }
} finally {
    $env:PATH = $OldPath
}
'02_TOOL_PATH_COMMAND_RESOLUTION=PASS; 11 direct commands and 3 BAT launchers' | Write-Output

$Python = Join-Path $Root 'tool\python\python.exe'
$Node = Join-Path $Root 'tool\node\node.exe'
function Assert-NativeVersion([string]$Label, [string]$Version, [string]$Executable, [string[]]$Arguments) {
    $Output = (& $Executable @Arguments 2>&1) -join [Environment]::NewLine
    if ($LASTEXITCODE -ne 0 -or $Output -notmatch [regex]::Escape($Version)) {
        throw "Bundled $Label native version mismatch (expected $Version): $Output"
    }
    Write-Output "02_TOOL_NATIVE_VERSION=PASS;$Label=$Version"
}
Assert-NativeVersion 'python' $Inventory.tools.python.version $Python @('--version')
Assert-NativeVersion 'pip' $Inventory.tools.pip.version $Python @('-E','-s','-B','-m','pip','--version')
Assert-NativeVersion 'paramiko' $Inventory.tools.paramiko.version $Python @('-E','-s','-B','-c','import paramiko; print(paramiko.__version__)')
Assert-NativeVersion 'node' $Inventory.tools.node.version $Node @('--version')
Assert-NativeVersion 'npm' $Inventory.tools.npm.version $Node @((Join-Path $Root 'tool\node\node_modules\npm\bin\npm-cli.js'),'--version')
Assert-NativeVersion 'corepack' $Inventory.tools.corepack.version $Node @((Join-Path $Root 'tool\node\node_modules\corepack\dist\corepack.js'),'--version')
$CorepackCmd = Join-Path $Root 'tool\node\corepack.cmd'
$CorepackResult = (& $CorepackCmd '--version' 2>&1) -join [Environment]::NewLine
if ($LASTEXITCODE -ne 0 -or $CorepackResult.Trim() -cne [string]$Inventory.tools.corepack.version) {
    throw 'Bundled Corepack CMD wrapper failed direct portable version check.'
}
'02_TOOL_COREPACK_SHIM=PASS; guarded Corepack --version' | Write-Output
Assert-NativeVersion 'adb' $Inventory.tools.adb.version (Join-Path $Root 'tool\android\platform-tools\adb.exe') @('version')
Assert-NativeVersion '7zip' $Inventory.tools.'7zip'.version (Join-Path $Root 'tool\bin\7z.exe') @('i')
Assert-NativeVersion 'ripgrep' $Inventory.tools.ripgrep.version (Join-Path $Root 'tool\bin\rg.exe') @('--version')
Assert-NativeVersion 'fd' $Inventory.tools.fd.version (Join-Path $Root 'tool\bin\fd.exe') @('--version')
Assert-NativeVersion 'jq' $Inventory.tools.jq.version (Join-Path $Root 'tool\bin\jq.exe') @('--version')
$Playwright = Get-Content -LiteralPath (Join-Path $Root 'tool\automation\versions.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Playwright.playwrightMcp -cne $Inventory.tools.'playwright-mcp'.version -or
    $Playwright.browser.version -cne $Inventory.tools.chromium.version) {
    throw 'Playwright/Chromium lock versions differ from installed inventory.'
}
& $Python -E -s -B (Join-Path $Root 'tool\automation\install-browser.py') --check
if ($LASTEXITCODE -ne 0) { throw 'Playwright browser contents or pinned SHA-256 are invalid.' }
'02_TOOL_NATIVE_AND_BROWSER_COMPATIBILITY=PASS; offline/no-user-credentials' | Write-Output
