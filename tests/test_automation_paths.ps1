# Offline production-helper tests; never launch Windows or browser processes.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $root 'tool/automation/portable-automation.ps1')
$scratch = New-AutomationDirectory -Root $root -Path (Join-Path $root 'tmp')
$fixture = New-AutomationDirectory -Root $root -Path (Join-Path $scratch ('automation-ps-' + [Guid]::NewGuid().ToString('N')))
function Assert-Test([bool]$Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
try {
    $session = New-AutomationDirectory -Root $root -Path (Join-Path $fixture 'session')
    $executable = Join-Path $fixture 'synthetic.exe'
    [IO.File]::WriteAllText($executable, 'Fixture only; never executable.')
    $start = New-AutomationStartInfo -Root $root -FilePath $executable -WorkingDirectory $fixture -Arguments @('space and 中文', 'quote"slash\', '') -SessionDirectory $session
    foreach ($name in @('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TEMP','TMP','TMPDIR','PROGRAMDATA','ALLUSERSPROFILE','PUBLIC')) {
        Assert-Test ($start.EnvironmentVariables[$name] -ceq $session) "Child $name must use owned package state."
    }
    Assert-Test (-not $start.UseShellExecute) 'Shell execution must be disabled.'
    Assert-Test (-not $start.EnvironmentVariables.ContainsKey('NODE_OPTIONS')) 'Host code injection must not be inherited.'
    Assert-Test ($start.Arguments.Contains('""')) 'Empty CRT argument must be retained.'
    Write-Output 'PASS isolated child environment and quoted arguments'
    foreach ($bad in @((Join-Path $fixture '../escape'), (Split-Path -Parent $root))) {
        $threw = $false
        try { $null = Assert-AutomationPath -Root $fixture -Path $bad -Directory -MayNotExist } catch { $threw = $true }
        Assert-Test $threw 'Traversal/outside paths must be refused.'
    }
    Write-Output 'PASS lexical package boundary'
    $hard = Join-Path $fixture 'hard.exe'
    $null = New-Item -ItemType HardLink -Path $hard -Target $executable
    $threw = $false
    try { $null = Assert-AutomationPath -Root $root -Path $hard } catch { $threw = $true }
    Assert-Test $threw 'Hardlinked code input must be refused.'
    Write-Output 'PASS hardlinked executable rejection'
    $owned = New-AutomationDirectory -Root $root -Path (Join-Path $fixture 'cleanup')
    [IO.File]::WriteAllText((Join-Path $owned 'owned.txt'), 'synthetic')
    Remove-AutomationSession -Root $root -Path $owned
    Assert-Test (-not [IO.Directory]::Exists($owned)) 'Owned session must be removed.'
    Assert-Test ([IO.File]::Exists($executable)) 'Cleanup must preserve other fixture data.'
    $threw = $false
    try { Remove-AutomationSession -Root $root -Path $scratch } catch { $threw = $true }
    Assert-Test $threw 'Shared temporary root must never be deleted.'
    Write-Output 'PASS owned session cleanup and shared-root protection'
    foreach ($name in @('desktop.ps1','desktop-worker.ps1','start-browser.ps1')) {
        $callArguments = @{}
        if ($name -ne 'start-browser.ps1') { $callArguments['TargetProcessId'] = 123456 }
        $threw = $false
        try { & (Join-Path $root ('tool/automation/' + $name)) @callArguments }
        catch { $threw = $_.Exception.Message -match 'task|TaskAuthorized' }
        Assert-Test $threw "Unselected entry must reject before UI/process work: $name"
    }
    Write-Output 'PASS task selection gates before process work'
    foreach ($name in @('desktop.ps1','desktop-worker.ps1','start-browser.ps1','install-browser.ps1','portable-automation.ps1')) {
        $tokens=$null; $errors=$null
        $null = [Management.Automation.Language.Parser]::ParseFile((Join-Path $root ('tool/automation/' + $name)),[ref]$tokens,[ref]$errors)
        Assert-Test ($errors.Count -eq 0) "Production script must parse: $name"
    }
    Write-Output 'PASS all automation PowerShell scripts parse'
} finally {
    Remove-Item -LiteralPath $fixture -Recurse -Force
}
