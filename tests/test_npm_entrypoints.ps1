#Requires -Version 5.1
# Offline checks for the real CMD/PowerShell npm entrypoints. No install/network.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$NodeDirectory = Join-Path $Root 'tool/node'
$Fixture = $null
$Passed = 0

function Assert-True {
    param([bool]$Value, [string]$Message)
    if (-not $Value) { throw $Message }
}

foreach ($Mode in @('npm', 'npx')) {
    $Cmd = [IO.File]::ReadAllText((Join-Path $NodeDirectory ($Mode + '.cmd')))
    Assert-True ($Cmd.Contains('setlocal DisableDelayedExpansion')) 'CMD must disable delayed expansion'
    $GuardPosition = $Cmd.IndexOf('powershell.exe')
    Assert-True ($Cmd.IndexOf('set "PSModuleAnalysisCachePath=NUL"') -ge 0 -and
        $Cmd.IndexOf('set "PSModuleAnalysisCachePath=NUL"') -lt $GuardPosition) 'CMD must disable host caches before PowerShell starts'
    Assert-True ($Cmd.IndexOf('set "POWERSHELL_TELEMETRY_OPTOUT=1"') -ge 0 -and
        $Cmd.IndexOf('set "POWERSHELL_TELEMETRY_OPTOUT=1"') -lt $GuardPosition) 'CMD must disable telemetry before PowerShell starts'
    Assert-True ($Cmd.Contains('"%~dp0node.exe" "%~dp0portable-npm.js" ' + $Mode + ' %*')) 'CMD must bind local Node and wrapper'
    Assert-True ($Cmd -notmatch '(?im)^\s*(?:call|for /f)\s') 'CMD must not reconstruct arguments through CALL'
    Assert-True (-not $Cmd.Contains('npm-prefix.js')) 'CMD must not discover a global npm installation'
    foreach ($Name in @('NODE_OPTIONS', 'NODE_PATH', 'NODE_EXTRA_CA_CERTS',
                        'NODE_COMPILE_CACHE', 'NODE_V8_COVERAGE', 'NODE_REDIRECT_WARNINGS')) {
        Assert-True ($Cmd.Contains('set "' + $Name + '="')) 'CMD must clear Node startup injection/state'
    }
    $PsPath = Join-Path $NodeDirectory ($Mode + '.ps1')
    $Tokens = $null
    $Errors = $null
    $null = [Management.Automation.Language.Parser]::ParseFile($PsPath, [ref]$Tokens, [ref]$Errors)
    Assert-True ($Errors.Count -eq 0) 'PowerShell wrapper must parse'
    $Ps = [IO.File]::ReadAllText($PsPath)
    Assert-True ($Ps.Contains('& $NodeExecutable $PortableNpmScript ' + $Mode + ' @args')) 'PowerShell must preserve arguments as an array'
    Assert-True ($Ps -notmatch '(?i)Invoke-Expression|npm-prefix\.js') 'PowerShell must not rediscover or evaluate npm commands'
    $Sh = [IO.File]::ReadAllText((Join-Path $NodeDirectory $Mode))
    Assert-True ($Sh.Contains('-File "$entry_dir/' + $Mode + '.ps1" "$@"')) 'Git Bash must forward to the guarded local PowerShell entrypoint'
    Assert-True ($Sh.IndexOf('export PSModuleAnalysisCachePath=NUL') -ge 0 -and
        $Sh.IndexOf('export PSModuleAnalysisCachePath=NUL') -lt $Sh.IndexOf('exec "$system_root/')) 'Git Bash must disable host caches before PowerShell starts'
    Assert-True ($Sh -notmatch '(?im)^\s*(?:eval|NODE_EXE=node)\b') 'Git Bash must not evaluate commands or fall back to host Node'
    $Passed++
    Write-Output "PASS $Mode entrypoint structure and PowerShell syntax"
}

if ($env:OS -ne 'Windows_NT') {
    Write-Output "PASS $Passed structural checks; SKIP native CMD/PowerShell npm runs on non-Windows."
    exit 0
}

function Invoke-PortableNpmFixture {
    param([string]$Entry, [string[]]$Arguments)
    $EntryPath = Join-Path $NodeDirectory $Entry
    $Start = New-Object Diagnostics.ProcessStartInfo
    # All test arguments are fixed flags and synthetic paths without double quotes.
    $QuotedArguments = @($Arguments | ForEach-Object {
        if ($_.Contains('"')) { throw 'Unexpected quote in synthetic test argument' }
        '"' + $_ + '"'
    }) -join ' '
    if ($Entry.EndsWith('.cmd')) {
        $Start.FileName = Join-Path $env:SystemRoot 'System32/cmd.exe'
        $Start.Arguments = '/d /s /c ""' + $EntryPath + '" ' + $QuotedArguments + '"'
    } else {
        $Start.FileName = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
        $Start.Arguments = '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $EntryPath + '" ' + $QuotedArguments
    }
    $Start.WorkingDirectory = $WorkDirectory
    $Start.UseShellExecute = $false
    $Start.CreateNoWindow = $true
    $Start.RedirectStandardOutput = $true
    $Start.RedirectStandardError = $true
    foreach ($Name in @('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'PROGRAMDATA',
                        'ALLUSERSPROFILE', 'PUBLIC', 'TEMP', 'TMP', 'TMPDIR',
                        'XDG_CACHE_HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME')) {
        $Start.EnvironmentVariables[$Name] = $RuntimeDirectory
    }
    $Start.EnvironmentVariables['POWERSHELL_TELEMETRY_OPTOUT'] = '1'
    $Start.EnvironmentVariables['PSModuleAnalysisCachePath'] = Join-Path $RuntimeDirectory 'ModuleAnalysisCache'
    $Start.EnvironmentVariables['NPM_CONFIG_CACHE'] = Join-Path $RuntimeDirectory 'npm-cache'
    $Start.EnvironmentVariables['NPM_CONFIG_PREFIX'] = Join-Path $RuntimeDirectory 'npm-prefix'
    $Start.EnvironmentVariables['NPM_CONFIG_USERCONFIG'] = Join-Path $RuntimeDirectory 'npm-user.rc'
    $Start.EnvironmentVariables['NPM_CONFIG_GLOBALCONFIG'] = Join-Path $RuntimeDirectory 'npm-global.rc'
    # If a shim forgets to clear startup injection, even --version will fail.
    $Start.EnvironmentVariables['NODE_OPTIONS'] = '--require="' + $InjectionScript + '"'
    $Process = New-Object Diagnostics.Process
    $Process.StartInfo = $Start
    try {
        $null = $Process.Start()
        $Stdout = $Process.StandardOutput.ReadToEndAsync()
        $Stderr = $Process.StandardError.ReadToEndAsync()
        if (-not $Process.WaitForExit(60000)) {
            $Process.Kill()
            $Process.WaitForExit()
            throw 'Offline npm entrypoint test exceeded 60 seconds'
        }
        return [pscustomobject]@{ ExitCode = $Process.ExitCode; Output = $Stdout.Result.Trim(); Error = $Stderr.Result.Trim() }
    } finally {
        $Process.Dispose()
    }
}

try {
    $Scratch = Join-Path $Root 'tmp'
    $Cursor = $Scratch
    while (-not [string]::IsNullOrWhiteSpace($Cursor)) {
        $Item = Get-Item -LiteralPath $Cursor -Force -ErrorAction SilentlyContinue
        if ($null -ne $Item -and (-not $Item.PSIsContainer -or
            ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw 'Unsafe npm test fixture ancestor'
        }
        $Cursor = Split-Path -Parent $Cursor
    }
    $null = New-Item -ItemType Directory -Force -Path $Scratch
    $Fixture = Join-Path $Scratch ('npm-entrypoints-' + [guid]::NewGuid().ToString('N'))
    $WorkDirectory = Join-Path $Fixture 'working with spaces'
    $RuntimeDirectory = Join-Path $Fixture 'runtime'
    $ExplicitPrefix = Join-Path $Fixture 'explicit prefix'
    foreach ($Path in @($WorkDirectory, $RuntimeDirectory, $ExplicitPrefix)) {
        $null = New-Item -ItemType Directory -Force -Path $Path
    }
    $Encoding = New-Object Text.UTF8Encoding($false)
    foreach ($Name in @('npm-user.rc', 'npm-global.rc')) {
        [IO.File]::WriteAllText((Join-Path $RuntimeDirectory $Name), '', $Encoding)
    }
    # Load the actual guard definition only, then trap any metadata access beyond
    # an owned junction. Its target is synthetic data inside this test fixture.
    $GuardAst = [Management.Automation.Language.Parser]::ParseFile(
        (Join-Path $NodeDirectory 'npm.ps1'), [ref]$Tokens, [ref]$Errors)
    $GuardDefinition = @($GuardAst.FindAll({ param($Node)
        $Node -is [Management.Automation.Language.FunctionDefinitionAst] -and $Node.Name -eq 'Assert-NpmBootstrapPath'
    }, $true))
    Assert-True ($GuardDefinition.Count -eq 1) 'Expected one production npm bootstrap guard'
    . ([scriptblock]::Create($GuardDefinition[0].Extent.Text))
    $LinkedParent = Join-Path $Fixture 'linked-parent'
    $LinkedLeaf = Join-Path $LinkedParent 'must-not-probe.txt'
    $null = New-Item -ItemType Junction -Path $LinkedParent -Target $RuntimeDirectory
    $script:NpmProbedLinkedLeaf = $false
    function Get-Item {
        param([string]$LiteralPath, [switch]$Force, $ErrorAction)
        if ($LiteralPath -eq $LinkedLeaf) { $script:NpmProbedLinkedLeaf = $true }
        Microsoft.PowerShell.Management\Get-Item -LiteralPath $LiteralPath -Force:$Force -ErrorAction $ErrorAction
    }
    try {
        $Denied = $false
        try { Assert-NpmBootstrapPath $LinkedLeaf $true } catch { $Denied = $true }
        Assert-True ($Denied -and -not $script:NpmProbedLinkedLeaf) 'npm guard must reject ancestors before probing linked descendants'
    } finally {
        Remove-Item Function:Get-Item
        [IO.Directory]::Delete($LinkedParent)
    }
    $Passed++
    Write-Output 'PASS npm bootstrap checks ancestors before following a junction'
    $InjectionScript = Join-Path $Fixture 'forbidden-startup.js'
    [IO.File]::WriteAllText($InjectionScript, 'throw new Error("npm shim did not remove NODE_OPTIONS");', $Encoding)
    foreach ($Entry in @('npm.cmd', 'npx.cmd', 'npm.ps1', 'npx.ps1')) {
        $Result = Invoke-PortableNpmFixture $Entry @('--version')
        Assert-True ($Result.ExitCode -eq 0 -and $Result.Output -match '^\d+\.\d+\.\d+$') "$Entry --version failed: $($Result.Error)"
        $Passed++
        Write-Output "PASS $Entry --version with hostile startup options removed"
    }
    foreach ($Entry in @('npm.cmd', 'npm.ps1')) {
        $Result = Invoke-PortableNpmFixture $Entry @('prefix')
        Assert-True ($Result.ExitCode -eq 0 -and $Result.Output -ieq $WorkDirectory) "$Entry prefix escaped the package cwd: $($Result.Output) $($Result.Error)"
        $Result = Invoke-PortableNpmFixture $Entry @('--prefix', $ExplicitPrefix, 'prefix')
        Assert-True ($Result.ExitCode -eq 0 -and $Result.Output -ieq $ExplicitPrefix) "$Entry rejected a safe explicit prefix: $($Result.Error)"
        # This lexical path is deliberately never created/read by the test.
        $OutsidePrefix = [IO.Path]::GetFullPath((Join-Path $Root '../npm-outside-must-not-be-read'))
        $Result = Invoke-PortableNpmFixture $Entry @('--prefix', $OutsidePrefix, 'prefix')
        Assert-True ($Result.ExitCode -ne 0) "$Entry accepted a package-external prefix"
        $Passed++
        Write-Output "PASS $Entry package cwd, explicit prefix and external-prefix rejection"
    }
} finally {
    if ($null -ne $Fixture -and (Test-Path -LiteralPath $Fixture)) {
        Remove-Item -LiteralPath $Fixture -Recurse -Force
    }
}
Write-Output "PASS $Passed npm entrypoint checks (offline)"
