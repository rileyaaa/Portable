#Requires -Version 5.1
# Exercise the real env.ps1 in disposable child processes. No launcher, EXE,
# real env.local.ps1 or authentication file is executed/read by these tests.
$ErrorActionPreference = 'Stop'
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$TempRoot = Join-Path $RepositoryRoot 'tmp'
$FixtureRoot = Join-Path $TempRoot ('portable-paths-' + [Guid]::NewGuid().ToString('N'))
$Engine = [Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
$Utf8 = New-Object Text.UTF8Encoding($true)
$Passed = 0

function Assert-Equal {
    param($Expected, $Actual, [string]$Description)
    if ($Expected -cne $Actual) {
        throw "$Description (expected '$Expected', received '$Actual')"
    }
}

function Test-Case {
    param([string]$Name, [scriptblock]$Body)
    & $Body
    $script:Passed++
    Write-Output "PASS $Name"
}

function Set-SyntheticLocalEnv {
    param([string]$PackageRoot, [string]$ExtraLine = '')
    $Lines = @(
        '$env:CODEX_MODEL = "synthetic-current-package"'
        '$env:CODEX_MODEL_INSTRUCTIONS_FILE = ""'
    )
    if ($ExtraLine) { $Lines += $ExtraLine }
    [IO.File]::WriteAllLines((Join-Path $PackageRoot 'env.local.ps1'), $Lines, $Utf8)
}

function Invoke-EnvWorker {
    param([string]$PackageRoot, [string]$RejectedVariable = '', [switch]$RuntimeTools)
    $Start = New-Object Diagnostics.ProcessStartInfo
    $Start.FileName = $Engine
    # ProcessStartInfo executes directly, without a command shell. The worker
    # file has no quotes or trailing directory separator in its absolute path.
    $Start.Arguments = '-NoLogo -NoProfile -NonInteractive -File "' + $WorkerPath + '"'
    $Start.UseShellExecute = $false
    $Start.CreateNoWindow = $true
    $Start.RedirectStandardOutput = $true
    $Start.RedirectStandardError = $true
    $Start.WorkingDirectory = $UnrelatedRoot
    $Start.EnvironmentVariables['CODEX_INSTALL_DIR'] = $OldRoot
    $Start.EnvironmentVariables['CODEX_MODEL'] = 'synthetic-inherited-host'
    $Start.EnvironmentVariables['CODEX_TEST_PACKAGE_ROOT'] = $PackageRoot
    $Start.EnvironmentVariables['CODEX_TEST_OLD_ROOT'] = $OldRoot
    $Start.EnvironmentVariables['CODEX_TEST_UNRELATED_ROOT'] = $UnrelatedRoot
    $Start.EnvironmentVariables['CODEX_TEST_REJECTED_VARIABLE'] = $RejectedVariable
    $Start.EnvironmentVariables['CODEX_TEST_RUNTIME_TOOLS'] = [string][int]$RuntimeTools.IsPresent
    $Start.EnvironmentVariables['CODEX_TEST_LAUNCHER'] = Join-Path $RepositoryRoot 'run-codex.ps1'
    $Start.EnvironmentVariables.Remove('CODEX_TEST_OLD_LOCAL_READ')
    $Start.EnvironmentVariables.Remove('CODEX_TEST_UNRELATED_LOCAL_READ')
    $Start.EnvironmentVariables['POWERSHELL_TELEMETRY_OPTOUT'] = '1'
    foreach ($Name in @('TEMP', 'TMP', 'TMPDIR', 'HOME', 'USERPROFILE',
                        'APPDATA', 'LOCALAPPDATA', 'XDG_CONFIG_HOME',
                        'XDG_CACHE_HOME', 'XDG_DATA_HOME')) {
        $Start.EnvironmentVariables[$Name] = $ChildRuntime
    }
    $Start.EnvironmentVariables['PSModuleAnalysisCachePath'] = Join-Path $ChildRuntime 'ModuleAnalysisCache'
    $Process = New-Object Diagnostics.Process
    $Process.StartInfo = $Start
    try {
        [void]$Process.Start()
        $StdoutTask = $Process.StandardOutput.ReadToEndAsync()
        $StderrTask = $Process.StandardError.ReadToEndAsync()
        if (-not $Process.WaitForExit(60000)) {
            $Process.Kill()
            $Process.WaitForExit()
            throw 'The isolated env.ps1 test exceeded 60 seconds.'
        }
        $Stdout = $StdoutTask.GetAwaiter().GetResult()
        $Stderr = $StderrTask.GetAwaiter().GetResult()
        if ($Process.ExitCode -ne 0) {
            throw "Isolated env.ps1 test failed ($($Process.ExitCode)):`n$Stdout`n$Stderr"
        }
        Assert-Equal 'worker-ok' $Stdout.Trim() 'Worker must complete its assertions'
    } finally {
        $Process.Dispose()
    }
}

# Check tmp and every ancestor before any fixture writes. Get-Item (without a
# Test-Path gate) also exposes dangling links that must not be followed.
$FixtureAncestor = $TempRoot
while (-not [string]::IsNullOrWhiteSpace($FixtureAncestor)) {
    $FixtureItem = Get-Item -LiteralPath $FixtureAncestor -Force -ErrorAction SilentlyContinue
    if ($null -ne $FixtureItem -and (
        -not $FixtureItem.PSIsContainer -or
        ($FixtureItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
        throw "Unsafe test fixture directory: $FixtureAncestor"
    }
    $FixtureAncestor = Split-Path -Parent $FixtureAncestor
}
[void][IO.Directory]::CreateDirectory($TempRoot)

try {
    [void][IO.Directory]::CreateDirectory($FixtureRoot)
    # Construct Chinese names without requiring a particular source encoding.
    $Chinese = ([string][char]0x4FBF) + [char]0x643A
    $OldRoot = Join-Path $FixtureRoot 'old package'
    $CurrentRoot = Join-Path $FixtureRoot ("new $Chinese package")
    $MovedRoot = Join-Path $FixtureRoot ("moved $Chinese package")
    $UnrelatedRoot = Join-Path $FixtureRoot 'unrelated working directory'
    $ChildRuntime = Join-Path $FixtureRoot 'child runtime'
    foreach ($Path in @($OldRoot, $CurrentRoot, $UnrelatedRoot, $ChildRuntime)) {
        [void][IO.Directory]::CreateDirectory($Path)
    }
    $OldLocal = Join-Path $OldRoot 'env.local.ps1'
    $UnrelatedLocal = Join-Path $UnrelatedRoot 'env.local.ps1'
    [IO.File]::WriteAllLines($OldLocal, @(
        '$env:CODEX_MODEL = "synthetic-wrong-old-package"'
        '$env:CODEX_TEST_OLD_LOCAL_READ = "true"'
    ), $Utf8)
    [IO.File]::WriteAllLines($UnrelatedLocal, @(
        '$env:CODEX_MODEL = "synthetic-wrong-working-directory"'
        '$env:CODEX_TEST_UNRELATED_LOCAL_READ = "true"'
    ), $Utf8)
    $OldLocalBefore = [IO.File]::ReadAllText($OldLocal)
    $UnrelatedLocalBefore = [IO.File]::ReadAllText($UnrelatedLocal)
    Copy-Item -LiteralPath (Join-Path $RepositoryRoot 'env.ps1') -Destination (Join-Path $CurrentRoot 'env.ps1')
    [IO.File]::WriteAllText((Join-Path $CurrentRoot 'codex.exe'), 'synthetic marker; never executable', $Utf8)
    Set-SyntheticLocalEnv $CurrentRoot
    $WorkerPath = Join-Path $FixtureRoot 'env-worker.ps1'
    $WorkerSource = @'
#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
try {
    $ExpectedRoot = $env:CODEX_TEST_PACKAGE_ROOT
    $ExpectedOldRoot = $env:CODEX_TEST_OLD_ROOT
    $RejectedVariable = $env:CODEX_TEST_REJECTED_VARIABLE
    if ($env:CODEX_INSTALL_DIR -cne $ExpectedOldRoot) { throw 'Missing inherited stale installation root.' }
    if ((Get-Location).Path -cne $env:CODEX_TEST_UNRELATED_ROOT) { throw 'Unexpected initial working directory.' }
    $ExpectedPaths = [ordered]@{
        CODEX_INSTALL_DIR = ''
        CODEX_PYTHON = 'tool\python\python.exe'
        ANDROID_HOME = 'tool\android\sdk'
        ANDROID_SDK_ROOT = 'tool\android\sdk'
        ANDROID_USER_HOME = 'home-runtime\.android'
        ANDROID_SDK_HOME = 'home-runtime'
        JAVA_HOME = 'tool\android\jdk'
        ADB_VENDOR_KEYS = 'home-runtime\.android\adbkey'
        APKTOOL_FRAMEWORK_DIR = 'cache\android\apktool-framework'
        FRIDA_CACHE_DIR = 'cache\android\frida'
        MITMPROXY_HOME = 'cache\android\mitmproxy'
        APPIUM_HOME = 'cache\android\appium'
        APK_LAB_CACHE_DIR = 'cache\android\apk-lab'
        APK_LAB_TMP_DIR = 'tmp\android'
        APK_LAB_JOBS_DIR = 'work\apk-jobs'
    }
    foreach ($Name in $ExpectedPaths.Keys) {
        if ($Name -ne 'CODEX_INSTALL_DIR') {
            [Environment]::SetEnvironmentVariable($Name, (Join-Path $ExpectedOldRoot 'stale'), 'Process')
        }
    }
    $LoadError = $null
    try { . (Join-Path $ExpectedRoot 'env.ps1') } catch { $LoadError = $_ }
    if ($RejectedVariable) {
        if ($null -eq $LoadError) { throw "Local override of $RejectedVariable was accepted." }
        if ($LoadError.Exception.Message -notmatch [regex]::Escape($RejectedVariable)) {
            throw "Override failed for an unexpected reason: $($LoadError.Exception.Message)"
        }
    } elseif ($null -ne $LoadError) {
        throw $LoadError
    }
    foreach ($Name in $ExpectedPaths.Keys) {
        $Relative = $ExpectedPaths[$Name]
        $Expected = if ($Relative) { Join-Path $ExpectedRoot $Relative } else { $ExpectedRoot }
        $Actual = [Environment]::GetEnvironmentVariable($Name, 'Process')
        if ($Actual -cne $Expected) { throw "$Name did not follow package root: '$Actual' != '$Expected'." }
    }
    if ($env:CODEX_MODEL -cne 'synthetic-current-package') { throw 'Loaded the wrong local environment file.' }
    if ($env:CODEX_TEST_OLD_LOCAL_READ -or $env:CODEX_TEST_UNRELATED_LOCAL_READ) {
        throw 'Read a local environment file outside the current package.'
    }
    if ($env:CODEX_MODEL_INSTRUCTIONS_FILE) { throw 'Explicit empty model instructions were not retained.' }
    if ((Get-Location).Path -cne $env:CODEX_TEST_UNRELATED_ROOT) { throw 'Loading env.ps1 changed the working directory.' }
    if ($env:CODEX_TEST_RUNTIME_TOOLS -eq '1') {
        # Exercise the real launcher reset and child-environment builder without
        # running native clients or creating tool/runtime state directories.
        $Tokens = $null; $Errors = $null
        $Ast = [Management.Automation.Language.Parser]::ParseFile($env:CODEX_TEST_LAUNCHER, [ref]$Tokens, [ref]$Errors)
        if ($Errors.Count) { throw 'Launcher parse failure.' }
        foreach ($Name in @('Reset-PortableInvariantEnvironment','Set-PortableProcessPath',
                            'Set-CodexChildPortableEnvironment','Set-ProcessEnvironmentValue',
                            'Get-ConfiguredHeaderEnvironmentVariableNames','Append-TomlSet','Convert-ToTomlString')) {
            $Definition = @($Ast.FindAll({param($Node) $Node -is [Management.Automation.Language.FunctionDefinitionAst]}, $true) | Where-Object { $_.Name -eq $Name })
            if ($Definition.Count -ne 1) { throw 'Missing launcher function.' }
            . ([scriptblock]::Create($Definition[0].Extent.Text))
        }
        $Root = $ExpectedRoot
        $PortableTool = Join-Path $Root 'tool'; $PortableCache = Join-Path $Root 'cache'
        $PortableHome = Join-Path $Root 'home-runtime'; $PortableTmp = Join-Path $Root 'tmp'
        $PortableWork = Join-Path $Root 'work'; $PortableAppData = Join-Path $Root 'appdata'
        $PortableLocalData = Join-Path $Root 'localappdata'; $PortableProgramData = Join-Path $Root 'programdata'
        $PortablePsModules = Join-Path $PortableCache 'powershell/modules'
        $SystemPaths = @()
        # Path security is covered by dedicated tests; this adapter keeps the
        # environment-mapping test runnable with Linux path separators too.
        function Assert-PortablePath {
            param([string]$Name, [string]$Path)
            if (-not [IO.Path]::GetFullPath($Path).StartsWith($Root + [IO.Path]::DirectorySeparatorChar)) {
                throw 'Generated tool path left the synthetic package.'
            }
        }
        $ToolAssignment = @($Ast.FindAll({param($Node) $Node -is [Management.Automation.Language.AssignmentStatementAst]}, $true) | Where-Object { $_.Left.Extent.Text -eq '$ToolPaths' } | Sort-Object { $_.Extent.StartOffset } | Select-Object -First 1)
        if ($ToolAssignment.Count -ne 1) { throw 'Missing tool PATH definition.' }
        . ([scriptblock]::Create($ToolAssignment[0].Extent.Text))
        $GoNames = @('GOPATH','GOCACHE','GOMODCACHE','GOROOT','GOTOOLCHAIN',
                     'UV_CACHE_DIR','UV_PYTHON_INSTALL_DIR','UV_TOOL_DIR','UV_TOOL_BIN_DIR')
        foreach ($Name in $GoNames) { [Environment]::SetEnvironmentVariable($Name, (Join-Path $ExpectedOldRoot 'stale-go'), 'Process') }
        $env:PIP_CONFIG_FILE = Join-Path $ExpectedOldRoot 'synthetic-host-pip.ini'
        Reset-PortableInvariantEnvironment
        $Child = New-Object Diagnostics.ProcessStartInfo
        Set-CodexChildPortableEnvironment $Child
        # Every tool path declared in env.ps1 must reach the real Codex child,
        # and then its shell_environment_policy.set (not merely this process).
        foreach ($Name in $ExpectedPaths.Keys) {
            $Expected = [Environment]::GetEnvironmentVariable($Name, 'Process')
            if ($Child.EnvironmentVariables[$Name] -cne $Expected) {
                throw "Tool variable $Name did not reach the Codex child."
            }
            $PolicyAssignment = 'Append-TomlSet $Builder "' + $Name + '" $env:' + $Name
            if (-not $Ast.Extent.Text.Contains($PolicyAssignment)) {
                throw "Tool variable $Name is absent from Codex shell policy."
            }
        }
        foreach ($Name in @('CODEX_HOME','CODEX_SQLITE_HOME','HOME','USERPROFILE',
                            'APPDATA','LOCALAPPDATA','TEMP','TMP','TMPDIR','XDG_CACHE_HOME',
                            'PIP_CACHE_DIR','PYTHONUSERBASE','NPM_CONFIG_CACHE',
                            'NPM_CONFIG_PREFIX','NPM_CONFIG_GLOBALCONFIG',
                            'NPM_CONFIG_USERCONFIG','NODE_REPL_HISTORY','YARN_CACHE_FOLDER',
                            'PNPM_HOME','PNPM_STORE_DIR','GRADLE_USER_HOME','PYTHONPYCACHEPREFIX',
                            'PSModulePath','GIT_CONFIG_NOSYSTEM')) {
            $Expected = [Environment]::GetEnvironmentVariable($Name, 'Process')
            if ($Child.EnvironmentVariables[$Name] -cne $Expected) {
                throw "Portable process variable $Name was lost by the child environment."
            }
        }
        if ($env:PIP_CONFIG_FILE -cne 'nul' -or $Child.EnvironmentVariables['PIP_CONFIG_FILE'] -cne 'nul') {
            throw 'Pip config suppression did not survive launcher reset and child environment mapping.'
        }
        $PipCommand = @($Ast.FindAll({param($Node) $Node -is [Management.Automation.Language.CommandAst]}, $true) | Where-Object {
            $_.Extent.Text -ceq 'Append-TomlSet $Builder "PIP_CONFIG_FILE" $env:PIP_CONFIG_FILE'
        })
        if ($PipCommand.Count -ne 1) { throw 'Missing pip shell-policy config setting.' }
        $Builder = New-Object Text.StringBuilder
        . ([scriptblock]::Create($PipCommand[0].Extent.Text))
        if ($Builder.ToString().Trim() -cne 'PIP_CONFIG_FILE = "nul"') {
            throw 'Generated shell policy did not disable pip config files.'
        }
        foreach ($Name in $GoNames) {
            if ([Environment]::GetEnvironmentVariable($Name) -or $Child.EnvironmentVariables.ContainsKey($Name)) {
                throw "Removed compiler state leaked into process environment: $Name"
            }
        }
        $Paths = @($Child.EnvironmentVariables['PATH'] -split ';')
        foreach ($Required in @((Join-Path $PortableTool 'python'), (Join-Path $PortableTool 'node'), (Join-Path $PortableTool 'android\platform-tools'))) {
            if ($Required -notin $Paths) { throw 'Required runtime PATH disappeared.' }
        }
        if ((Join-Path $PortableTool 'go\bin') -in $Paths) { throw 'Removed compiler remains on runtime PATH.' }
        # Custom headers use ordinary variable names, not the protected CODEX_* namespace.
        $env:CODEX_ENV_HTTP_HEADERS_TOML = '{ "HTTP-Referer" = "MY_HTTP_REFERER", "X-Title" = "MY_X_TITLE" }'
        $env:MY_HTTP_REFERER = 'https://synthetic.invalid/'
        $env:MY_X_TITLE = 'synthetic portable task'
        Set-CodexChildPortableEnvironment $Child
        if ($Child.EnvironmentVariables['MY_HTTP_REFERER'] -cne $env:MY_HTTP_REFERER -or
            $Child.EnvironmentVariables['MY_X_TITLE'] -cne $env:MY_X_TITLE) {
            throw 'Configured custom headers did not reach the client environment.'
        }
        if (Test-Path -LiteralPath $PortableTool) { throw 'Environment setup recreated removed compiler/tool directories.' }
    }
    Write-Output 'worker-ok'
    exit 0
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
'@
    [IO.File]::WriteAllText($WorkerPath, $WorkerSource, $Utf8)

    Test-Case 'Current package overrides stale inherited paths and ignores other local files' {
        Invoke-EnvWorker $CurrentRoot
    }
    Test-Case 'Moving the complete package rebases all 15 env.ps1 paths' {
        [IO.Directory]::Move($CurrentRoot, $MovedRoot)
        Invoke-EnvWorker $MovedRoot
        Assert-Equal $false (Test-Path -LiteralPath $CurrentRoot) 'Original location must no longer exist'
    }
    Test-Case 'Launcher keeps runtime paths without a Go installation or inherited compiler state' {
        Invoke-EnvWorker $MovedRoot -RuntimeTools
    }
    foreach ($ProtectedName in @('CODEX_INSTALL_DIR', 'CODEX_PYTHON', 'ANDROID_HOME', 'APK_LAB_TMP_DIR',
        'CODEX_ROLLOUT_TRACE_ROOT', 'CODEX_TUI_SESSION_LOG_PATH', 'CODEX_MANAGED_PACKAGE_ROOT',
        'CODEX_WINDOWS_REGISTERED_CORE', 'CODEX_FUTURE_UNREVIEWED_PATH', 'PIP_CONFIG_FILE')) {
        Test-Case "Local override of $ProtectedName is rejected without changing derived paths" {
            $EscapedOldRoot = $OldRoot.Replace("'", "''")
            Set-SyntheticLocalEnv $MovedRoot ('$env:' + $ProtectedName + " = '" + $EscapedOldRoot + "'")
            Invoke-EnvWorker $MovedRoot $ProtectedName
        }
    }
    Test-Case 'Old package and unrelated local files remain unchanged' {
        Assert-Equal $OldLocalBefore ([IO.File]::ReadAllText($OldLocal)) 'Old local file changed'
        Assert-Equal $UnrelatedLocalBefore ([IO.File]::ReadAllText($UnrelatedLocal)) 'Unrelated local file changed'
        Assert-Equal 3 @(Get-ChildItem -LiteralPath $MovedRoot -Force).Count 'env.ps1 created unexpected package files'
    }
    Write-Output "Passed $Passed portable path tests."
    Write-Output 'Scope: env.ps1 and launcher environment mapping; Windows PowerShell 5.1, NTFS and client startup still require Windows validation.'
} finally {
    # Never clean the shared tmp directory, other test runs or any real package.
    if (Test-Path -LiteralPath $FixtureRoot) {
        Remove-Item -LiteralPath $FixtureRoot -Recurse -Force
    }
}
