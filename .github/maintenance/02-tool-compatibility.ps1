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
function Assert-Var([string]$Name, [object]$Expected) {
    $Actual = [Environment]::GetEnvironmentVariable($Name, 'Process')
    # SDK/JDK are optional. [string] parameters turn PowerShell 5.1's
    # expected $null into "", which wrongly fails a genuinely unset variable.
    # Keep $null distinct from "" and reject any unexpected host value.
    if ($null -eq $Expected) {
        if ($null -ne $Actual) {
            throw "Optional tool variable $Name must be absent: $Actual"
        }
        return
    }
    if ($Expected -isnot [string] -or [string]::IsNullOrEmpty($Expected)) {
        throw "Invalid required tool variable expectation: $Name"
    }
    if ($Actual -cne $Expected) {
        throw "Tool variable $Name escaped the portable package: $Actual"
    }
}
Assert-Var 'CODEX_INSTALL_DIR' $Root
Assert-Var 'CODEX_PYTHON' (Join-Path $Root 'tool\python\python.exe')
$Sdk = Join-Path $Root 'tool\android\sdk'
$SdkPresent = Test-Path -LiteralPath (Join-Path $Sdk 'cmdline-tools\latest\bin\sdkmanager.bat') -PathType Leaf
if (-not $SdkPresent -and (Test-Path -LiteralPath (Join-Path $Sdk 'build-tools') -PathType Container)) {
    $SdkPresent = @(Get-ChildItem -LiteralPath (Join-Path $Sdk 'build-tools') -Directory -ErrorAction Stop | Where-Object {
        Test-Path -LiteralPath (Join-Path $_.FullName 'aapt2.exe') -PathType Leaf
    }).Count -gt 0
}
Assert-Var 'ANDROID_HOME' $(if ($SdkPresent) { $Sdk } else { $null })
Assert-Var 'ANDROID_SDK_ROOT' $(if ($SdkPresent) { $Sdk } else { $null })
Assert-Var 'ANDROID_USER_HOME' (Join-Path $Root 'home-runtime\.android')
Assert-Var 'ANDROID_SDK_HOME' (Join-Path $Root 'home-runtime')
$Jdk = Join-Path $Root 'tool\android\jdk'
$JdkPresent = (Test-Path -LiteralPath (Join-Path $Jdk 'bin\java.exe') -PathType Leaf) -and
              (Test-Path -LiteralPath (Join-Path $Jdk 'bin\javac.exe') -PathType Leaf)
Assert-Var 'JAVA_HOME' $(if ($JdkPresent) { $Jdk } else { $null })
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
# Windows PowerShell 5.1 reads BOM-less .ps1 text using the host ANSI codepage.
# Construct exact Unicode BAT names from ASCII-only source on every locale.
$BatStart = -join @([char]0x542F, [char]0x52A8, 'Codex.bat')
$BatMaintenance = -join @([char]0x542F, [char]0x52A8, 'Codex-', [char]0x7EF4, [char]0x62A4, [char]0x6A21, [char]0x5F0F, '.bat')
$BatLoginCheck = -join @([char]0x68C0, [char]0x67E5, 'login_json.bat')
foreach ($Bat in @($BatStart, $BatMaintenance, $BatLoginCheck)) {
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
# Run real standalone Python CMD entrypoints under hostile host configuration.
# Merely checking python.exe -m pip bypasses the new Python console_script
# sanitizer; neither command below installs packages nor contacts the network.
$HostileNames = @('PIP_CONFIG_FILE','PYTHONPATH','OPENAI_API_KEY','NODE_OPTIONS','HTTP_PROXY')
$SavedHostile = @{}
foreach ($Name in $HostileNames) {
    $SavedHostile[$Name] = [Environment]::GetEnvironmentVariable($Name, 'Process')
}
try {
    $env:PIP_CONFIG_FILE = 'Z:\untrusted-host-pip.ini'
    $env:PYTHONPATH = 'Z:\untrusted-host-site'
    $env:OPENAI_API_KEY = 'fake-host-secret-canary'
    $env:NODE_OPTIONS = '--require=Z:\untrusted-host-node.js'
    $env:HTTP_PROXY = 'http://host-proxy.invalid:9999'
    $PipShim = Join-Path $Root 'tool\bin\pip.cmd'
    $PipShimResult = (& $PipShim '--version' 2>&1) -join [Environment]::NewLine
    if ($LASTEXITCODE -ne 0 -or $PipShimResult -notmatch ('pip ' + [regex]::Escape([string]$Inventory.tools.pip.version))) {
        throw 'Direct portable pip.cmd failed with injected host configuration.'
    }
    $HttpxShim = Join-Path $Root 'tool\bin\httpx.cmd'
    $HttpxHelp = (& $HttpxShim '--help' 2>&1) -join [Environment]::NewLine
    if ($LASTEXITCODE -ne 0 -or $HttpxHelp -notmatch '(?i)usage') {
        throw 'Direct portable httpx.cmd help failed with injected host configuration.'
    }
} finally {
    foreach ($Name in $HostileNames) {
        [Environment]::SetEnvironmentVariable($Name, $SavedHostile[$Name], 'Process')
    }
}
'02_TOOL_PYTHON_SHIMS=PASS; real pip/httpx CMD under hostile host environment' | Write-Output
# XlsxWriter's legacy vba_extract.cmd is not a console_script, so check
# that the special guarded dispatch prints its genuine bundled help without
# opening any XLSM file, making network requests or writing extracted macros.
$VbaShim = Join-Path $Root 'tool\bin\vba_extract.cmd'
$VbaOutput = (& $VbaShim 2>&1) -join [Environment]::NewLine
if ($LASTEXITCODE -ne 0 -or $VbaOutput -notmatch 'Usage:\s+vba_extract file\.xlsm') {
    throw 'Legacy VBA CLI failed its direct guarded no-argument help check.'
}
'02_TOOL_VBA_SHIM=PASS; guarded vba_extract.cmd usage; no XLSM touched' | Write-Output
Assert-NativeVersion 'node' $Inventory.tools.node.version $Node @('--version')
Assert-NativeVersion 'npm' $Inventory.tools.npm.version $Node @((Join-Path $Root 'tool\node\node_modules\npm\bin\npm-cli.js'),'--version')
Assert-NativeVersion 'corepack' $Inventory.tools.corepack.version $Node @((Join-Path $Root 'tool\node\node_modules\corepack\dist\corepack.js'),'--version')
$CorepackCmd = Join-Path $Root 'tool\node\corepack.cmd'
$CorepackResult = (& $CorepackCmd '--version' 2>&1) -join [Environment]::NewLine
if ($LASTEXITCODE -ne 0 -or $CorepackResult.Trim() -cne [string]$Inventory.tools.corepack.version) {
    throw 'Bundled Corepack CMD wrapper failed direct portable version check.'
}
'02_TOOL_COREPACK_SHIM=PASS; guarded Corepack --version' | Write-Output
# Exercise real CMD + PowerShell pre-bootstrap under a poisoned *child-only*
# Windows environment. Explicit real cmd.exe avoids starting a fake shell,
# and ProcessStartInfo prevents mutation of the test runner's own SystemRoot.
function Assert-PoisonedNativeBootstrap([string]$Shim, [string]$Version) {
    $Windows = [IO.Path]::GetFullPath([Environment]::GetFolderPath('Windows'))
    $TrustedCmd = Join-Path $Windows 'System32\cmd.exe'
    if (-not [IO.File]::Exists($TrustedCmd)) { throw 'Cannot find trusted native CMD.' }
    $Start = New-Object Diagnostics.ProcessStartInfo
    $Start.FileName = $TrustedCmd
    # CMD /S removes the outer quotes, preserving a quoted path with spaces.
    $Start.Arguments = '/d /s /c ""' + $Shim + '" --version"'
    $Start.WorkingDirectory = $Root
    $Start.UseShellExecute = $false
    $Start.CreateNoWindow = $true
    $Start.RedirectStandardOutput = $true
    $Start.RedirectStandardError = $true
    $Start.EnvironmentVariables.Clear()
    foreach ($name in @('SystemRoot','WINDIR')) {
        $Start.EnvironmentVariables[$name] = 'Z:\host-fake-windows'
    }
    $Start.EnvironmentVariables['ComSpec'] = 'Z:\host-fake-cmd.exe'
    $Start.EnvironmentVariables['__APPDIR__'] = 'Z:\host-fake\System32\'
    $Start.EnvironmentVariables['PATH'] = 'Z:\host-fake-tools'
    $Start.EnvironmentVariables['PSModulePath'] = 'Z:\host-fake-modules'
    # CLR profiler injection can run BEFORE PowerShell's -Command preflight.
    # These harmless invalid paths/IDs must not reach managed bootstrap.
    $Start.EnvironmentVariables['COR_ENABLE_PROFILING'] = '1'
    $Start.EnvironmentVariables['COR_PROFILER'] = '{11111111-1111-1111-1111-111111111111}'
    $Start.EnvironmentVariables['COR_PROFILER_PATH'] = 'Z:\host-clr-profiler.dll'
    $Start.EnvironmentVariables['CORECLR_ENABLE_PROFILING'] = '1'
    $Start.EnvironmentVariables['CORECLR_PROFILER_PATH'] = 'Z:\host-coreclr-profiler.dll'
    $Start.EnvironmentVariables['DOTNET_ENABLE_PROFILING'] = '1'
    $Start.EnvironmentVariables['DOTNET_STARTUP_HOOKS'] = 'Z:\host-startup-hook.dll'
    $Start.EnvironmentVariables['NODE_OPTIONS'] = '--require=Z:\host-injected.js'
    $Start.EnvironmentVariables['PIP_CONFIG_FILE'] = 'Z:\host-pip.ini'
    $Start.EnvironmentVariables['OPENAI_API_KEY'] = 'synthetic-host-canary'
    $Start.EnvironmentVariables['TEMP'] = Join-Path $Root 'tmp'
    $Start.EnvironmentVariables['TMP'] = Join-Path $Root 'tmp'
    $Started = New-Object Diagnostics.Process
    $Started.StartInfo = $Start
    try {
        if (-not $Started.Start()) { throw 'Synthetic native bootstrap did not start.' }
        $OutTask = $Started.StandardOutput.ReadToEndAsync()
        $ErrTask = $Started.StandardError.ReadToEndAsync()
        if (-not $Started.WaitForExit(30000)) {
            try { $Started.Kill() } catch {}
            throw 'Synthetic native bootstrap timed out.'
        }
        $Output = $OutTask.GetAwaiter().GetResult()
        $Errors = $ErrTask.GetAwaiter().GetResult()
        if ($Started.ExitCode -ne 0 -or $Output -notmatch [regex]::Escape($Version)) {
            throw 'CMD native bootstrap failed to reject host SystemRoot/__APPDIR__: ' +
                  (Split-Path -Leaf $Shim) + ';exit=' + $Started.ExitCode +
                  ';stdout=' + $Output.Substring(0,[Math]::Min(150,$Output.Length)) +
                  ';stderr=' + $Errors.Substring(0,[Math]::Min(150,$Errors.Length))
        }
    } finally {
        $Started.Dispose()
    }
}
Assert-PoisonedNativeBootstrap (Join-Path $Root 'tool\bin\pip.cmd') ('pip ' + [string]$Inventory.tools.pip.version)
Assert-PoisonedNativeBootstrap (Join-Path $Root 'tool\node\npm.cmd') ([string]$Inventory.tools.npm.version)
Assert-PoisonedNativeBootstrap (Join-Path $Root 'tool\node\npx.cmd') ([string]$Inventory.tools.npm.version)
Assert-PoisonedNativeBootstrap (Join-Path $Root 'tool\node\corepack.cmd') ([string]$Inventory.tools.corepack.version)
'02_TOOL_NATIVE_CMD_POISONED=PASS; isolated real CMD ignores forged SystemRoot/ComSpec/__APPDIR__' | Write-Output
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
