#Requires -Version 5.1
# Offline production-function tests: no client launch, account data or host browser.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Passed = 0
$SavedFlow = [Environment]::GetEnvironmentVariable('CODEX_BROWSER_LOGIN_FLOW', 'Process')
$Fixture = $null

function Assert-Equal {
    param($Expected, $Actual, [string]$Description)
    if ($Expected -cne $Actual) { throw "$Description (expected '$Expected', got '$Actual')" }
}

function Test-Case {
    param([string]$Name, [scriptblock]$Body)
    & $Body
    $script:Passed++
    Write-Output "PASS $Name"
}

function Read-SourceAst {
    param([string]$Path)
    $Tokens = $null
    $Errors = $null
    $Ast = [Management.Automation.Language.Parser]::ParseFile($Path, [ref]$Tokens, [ref]$Errors)
    if ($Errors.Count -gt 0) { throw "Parse failure: $($Errors[0].Message)" }
    return $Ast
}

$LauncherAst = Read-SourceAst (Join-Path $Root 'run-codex.ps1')
$EnvAst = Read-SourceAst (Join-Path $Root 'env.ps1')
foreach ($Pair in @(
    @($LauncherAst, 'Get-CodexBrowserLoginFlow'),
    @($LauncherAst, 'Invoke-CodexOfficialAccountLogin'),
    @($EnvAst, 'Import-CodexPortableLocalEnv')
)) {
    $Definitions = @($Pair[0].FindAll({
        param($Node)
        $Node -is [Management.Automation.Language.FunctionDefinitionAst]
    }, $true) | Where-Object { $_.Name -eq $Pair[1] })
    Assert-Equal 1 $Definitions.Count 'Expected one production function'
    . ([scriptblock]::Create($Definitions[0].Extent.Text))
}

function Invoke-CodexChildInteractive {
    param([object[]]$LaunchArgs)
    $script:Attempts.Add([string[]]@($LaunchArgs))
    return $script:LoginExitCode
}

function Reset-LoginStub {
    param([int]$ExitCode = 0)
    $script:Attempts = New-Object 'System.Collections.Generic.List[object]'
    $script:LoginExitCode = $ExitCode
}

try {
    Test-Case 'Package default replaces an inherited system-browser setting' {
        $Assignments = @($EnvAst.FindAll({
            param($Node)
            $Node -is [Management.Automation.Language.AssignmentStatementAst] -and
                $Node.Left.Extent.Text -ceq '$env:CODEX_BROWSER_LOGIN_FLOW'
        }, $true))
        Assert-Equal 1 $Assignments.Count 'Expected one explicit package default'
        $env:CODEX_BROWSER_LOGIN_FLOW = 'system_browser'
        . ([scriptblock]::Create($Assignments[0].Extent.Text))
        Assert-Equal 'device_auth' $env:CODEX_BROWSER_LOGIN_FLOW 'Package must explicitly default to device auth'
    }

    Test-Case 'Missing, empty and whitespace choices use device authentication' {
        foreach ($Value in @($null, '', '   ')) {
            Reset-LoginStub
            Assert-Equal 0 (Invoke-CodexOfficialAccountLogin -Flow $Value) 'Default login result'
            Assert-Equal 1 $script:Attempts.Count 'Only one login attempt is allowed'
            Assert-Equal 'login|--device-auth' ($script:Attempts[0] -join '|') 'Default arguments'
        }
    }

    Test-Case 'Explicit device authentication is normalized and retained' {
        Reset-LoginStub
        Assert-Equal 'device_auth' (Get-CodexBrowserLoginFlow ' DEVICE_AUTH ') 'Normalized flow'
        Assert-Equal 0 (Invoke-CodexOfficialAccountLogin ' DEVICE_AUTH ') 'Device login result'
        Assert-Equal 'login|--device-auth' ($script:Attempts[0] -join '|') 'Explicit device-auth arguments'
    }

    Test-Case 'Explicit system_browser is the only browser-opening flow' {
        Reset-LoginStub
        Assert-Equal 0 (Invoke-CodexOfficialAccountLogin 'system_browser') 'Browser login result'
        Assert-Equal 1 $script:Attempts.Count 'One browser attempt'
        Assert-Equal 'login' ($script:Attempts[0] -join '|') 'Explicit browser arguments'
    }

    Test-Case 'Unknown values fail before any process invocation' {
        foreach ($Value in @('browser', 'auto', 'false', '--device-auth', 'device_auth system_browser')) {
            Reset-LoginStub
            $Rejected = $false
            try { $null = Invoke-CodexOfficialAccountLogin $Value } catch { $Rejected = $true }
            Assert-Equal $true $Rejected 'Invalid flow must be rejected'
            Assert-Equal 0 $script:Attempts.Count 'Invalid flow must not launch a process'
        }
    }

    Test-Case 'Device-auth failure returns its code without browser fallback' {
        Reset-LoginStub -ExitCode 37
        Assert-Equal 37 (Invoke-CodexOfficialAccountLogin 'device_auth') 'Failure code must reach launcher'
        Assert-Equal 1 $script:Attempts.Count 'Failed device auth must not retry'
        Assert-Equal 'login|--device-auth' ($script:Attempts[0] -join '|') 'Failure must not start browser login'
    }

    Test-Case 'Local configuration permits only an explicitly configured supported flow' {
        $Scratch = Join-Path $Root 'tmp'
        $Cursor = $Scratch
        while (-not [string]::IsNullOrWhiteSpace($Cursor)) {
            $Item = Get-Item -LiteralPath $Cursor -Force -ErrorAction SilentlyContinue
            if ($null -ne $Item -and (-not $Item.PSIsContainer -or
                ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
                throw 'Unsafe synthetic test fixture ancestor'
            }
            $Cursor = Split-Path -Parent $Cursor
        }
        $null = New-Item -ItemType Directory -Force -Path $Scratch
        $script:Fixture = Join-Path $Scratch ('login-flow-test-' + [guid]::NewGuid().ToString('N'))
        $null = New-Item -ItemType Directory -Path $script:Fixture
        $LocalFile = Join-Path $script:Fixture 'synthetic-local.ps1'
        $Encoding = New-Object Text.UTF8Encoding($true)
        foreach ($Value in @('device_auth', 'system_browser')) {
            [IO.File]::WriteAllText($LocalFile, ('$env:CODEX_BROWSER_LOGIN_FLOW = "' + $Value + '"'), $Encoding)
            Import-CodexPortableLocalEnv -Path $LocalFile
            Assert-Equal $Value (Get-CodexBrowserLoginFlow $env:CODEX_BROWSER_LOGIN_FLOW) 'Supported local setting'
        }
        [IO.File]::WriteAllText($LocalFile, '$env:CODEX_BROWSER_LOGIN_FLOW = "auto"', $Encoding)
        Import-CodexPortableLocalEnv -Path $LocalFile
        Reset-LoginStub
        $Rejected = $false
        try { $null = Invoke-CodexOfficialAccountLogin $env:CODEX_BROWSER_LOGIN_FLOW } catch { $Rejected = $true }
        Assert-Equal $true $Rejected 'Invalid local choice must be rejected'
        Assert-Equal 0 $script:Attempts.Count 'Invalid local choice must not launch a process'
    }
} finally {
    [Environment]::SetEnvironmentVariable('CODEX_BROWSER_LOGIN_FLOW', $SavedFlow, 'Process')
    if ($null -ne $Fixture -and (Test-Path -LiteralPath $Fixture)) {
        Remove-Item -LiteralPath $Fixture -Recurse -Force
    }
}

Write-Output "PASS $Passed browser login flow checks (offline)"
