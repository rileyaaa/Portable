#Requires -Version 5.1
# Actual production auth helpers, with synthetic files in an owned fixture.
# No real account, API request, official login or host credential store.
param([string]$BaselineCommit = '')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$tokens=$null; $errors=$null
if ($BaselineCommit) {
    if ($BaselineCommit -notmatch '^[a-f0-9]{40}$') { throw 'Invalid baseline commit.' }
    $lines = & git -C $repoRoot show ($BaselineCommit + ':run-codex.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Could not read baseline.' }
    $source = $lines -join "`n"
    $ast = [Management.Automation.Language.Parser]::ParseInput($source,[ref]$tokens,[ref]$errors)
} else {
    $source=[IO.File]::ReadAllText((Join-Path $repoRoot 'run-codex.ps1'))
    $ast = [Management.Automation.Language.Parser]::ParseInput($source,[ref]$tokens,[ref]$errors)
}
if ($errors.Count) { throw 'Launcher parse failed.' }
$definitions=@($ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$true))
foreach ($name in @('Test-IsUnderDirectory','Assert-PortablePath','Assert-PortableRegularInputFile',
    'Test-CodexAuthFile','Write-PortableNewUtf8File','Move-TemporaryFileIntoPlace',
    'Move-InvalidCodexAuthFile','Copy-CodexAuthAtomic','Read-CodexAuthMode','Write-CodexAuthMode',
    'Remove-PortableAuthStateFile','Test-CodexAuthTransitionPending','Start-CodexAuthTransition',
    'Complete-CodexAuthTransition','Repair-CodexAuthTransition','Get-CodexLogoutBlockPath',
    'Test-CodexLogoutBlocked','Set-CodexLogoutBlock','Clear-CodexLogoutBlockAfterFreshLogin',
    'Backup-LegacyAccountJsonAuthForBrowser')) {
    $nodes=@($definitions | Where-Object {$_.Name -eq $name})
    if ($nodes.Count -ne 1) { throw ('Missing production function: '+$name) }
    . ([scriptblock]::Create($nodes[0].Extent.Text))
}
# Execute the exact startup recovery statements, without running the launcher.
$begin=$source.IndexOf("Repair-CodexAuthTransition`n`$PreviousAuthMode = Read-CodexAuthMode")
$normalized=$source.Replace("`r`n","`n")
$begin=$normalized.IndexOf("Repair-CodexAuthTransition`n`$PreviousAuthMode = Read-CodexAuthMode")
$end=$normalized.IndexOf('$ConfiguredAuthMode = $env:CODEX_AUTH_MODE',$begin)
if ($begin -lt 0 -or $end -le $begin) { throw 'Startup recovery source not found.' }
$recover=[scriptblock]::Create($normalized.Substring($begin,$end-$begin))
function Assert-Case {param([bool]$Condition,[string]$Label) if (-not $Condition) {throw $Label}}
$cursor=[IO.Path]::GetFullPath($repoRoot).TrimEnd('\')
while ($cursor) {
    $item=Get-Item -LiteralPath $cursor -Force
    if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unsafe fixture ancestor.' }
    $cursor=[IO.Path]::GetDirectoryName($cursor)
}
$scratch=Join-Path $repoRoot 'tmp'
if (-not (Test-Path -LiteralPath $scratch)) { [void](New-Item -ItemType Directory -Path $scratch) }
$si=Get-Item -LiteralPath $scratch -Force
if (-not $si.PSIsContainer -or ($si.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unsafe tmp.' }
$Root=Join-Path $scratch ('auth-snapshot-type-test-'+[guid]::NewGuid().ToString('N'))
[void](New-Item -ItemType Directory -Path $Root)
$oldHome=$env:CODEX_HOME
try {
    $env:CODEX_HOME=Join-Path $Root 'home'
    [void](New-Item -ItemType Directory -Path $env:CODEX_HOME)
    $ActiveAuthPath=Join-Path $env:CODEX_HOME 'auth.json'
    $AccountJsonAuthPath=Join-Path $env:CODEX_HOME 'auth-account-json.json'
    $BrowserAuthPath=Join-Path $env:CODEX_HOME 'auth-browser.json'
    $AuthModePath=Join-Path $env:CODEX_HOME 'mode'
    $api='{"auth_mode":"apikey","OPENAI_API_KEY":"synthetic-key"}'
    $json='{"auth_mode":"chatgpt","tokens":{"refresh_token":"synthetic-json","access_token":"synthetic-json-access"}}'
    $browser='{"auth_mode":"chatgpt","tokens":{"refresh_token":"synthetic-browser","access_token":"synthetic-browser-access"}}'
    function Put-Auth {param([string]$Path,[string]$Content) [IO.File]::WriteAllText($Path,$Content)}
    function Read-Auth {param([string]$Path) return [IO.File]::ReadAllText($Path)}
    Put-Auth $ActiveAuthPath $api
    Put-Auth $AccountJsonAuthPath $json
    Put-Auth $BrowserAuthPath $browser
    Write-CodexAuthMode 'browser'
    Assert-Case (Test-CodexAuthFile $ActiveAuthPath) 'General API-key file validation changed.'
    & $recover
    $preserved=(Read-Auth $BrowserAuthPath) -ceq $browser
    if ($BaselineCommit) {
        Assert-Case (-not $preserved -and (Read-Auth $BrowserAuthPath) -ceq $api) 'Previous wrong-type overwrite did not reproduce.'
        Remove-Item -LiteralPath $AccountJsonAuthPath -Force
        Remove-Item -LiteralPath $BrowserAuthPath -Force
        Backup-LegacyAccountJsonAuthForBrowser
        Assert-Case ((Read-Auth $AccountJsonAuthPath) -ceq $api) 'Previous wrong-type legacy backup did not reproduce.'
        Write-Output 'REPRODUCED previous API-key active file overwrites official snapshot and enters legacy account backup'
        return
    }
    Assert-Case ($preserved -and (Read-Auth $AccountJsonAuthPath) -ceq $json) 'Official snapshots overwritten by wrong credential type.'
    Assert-Case (-not (Test-Path -LiteralPath $ActiveAuthPath)) 'Mismatched active file not quarantined.'
    $quarantine=@(Get-ChildItem -LiteralPath $env:CODEX_HOME -File -Filter 'auth.json.invalid-*')
    Assert-Case ($quarantine.Count -eq 1 -and (Read-Auth $quarantine[0].FullName) -ceq $api) 'Mismatched active file not preserved.'
    Write-Output 'PASS previous browser mode does not recycle API-key auth into either snapshot'
    Put-Auth $AccountJsonAuthPath $api
    Put-Auth $BrowserAuthPath $api
    Write-CodexAuthMode 'api'
    & $recover
    Assert-Case (-not (Test-Path -LiteralPath $AccountJsonAuthPath) -and -not (Test-Path -LiteralPath $BrowserAuthPath)) 'Wrong-type snapshots accepted.'
    Assert-Case (@(Get-ChildItem -LiteralPath $env:CODEX_HOME -File -Filter 'auth-*.json.invalid-*').Count -eq 2) 'Wrong-type snapshots not preserved.'
    Put-Auth $ActiveAuthPath $api
    Backup-LegacyAccountJsonAuthForBrowser
    Assert-Case (-not (Test-Path -LiteralPath $AccountJsonAuthPath)) 'API-key auth entered legacy account snapshot.'
    $refused=$false
    try { Copy-CodexAuthAtomic -Source $ActiveAuthPath -Destination $BrowserAuthPath -FreshLogin } catch { $refused=$true }
    Assert-Case ($refused -and -not (Test-Path -LiteralPath $BrowserAuthPath)) 'Fresh official copy accepted wrong type.'
    Write-Output 'PASS wrong-type snapshots quarantined, legacy API-key backup and wrong-type fresh copy refused'
    Put-Auth $ActiveAuthPath $json
    Backup-LegacyAccountJsonAuthForBrowser
    Assert-Case ((Read-Auth $AccountJsonAuthPath) -ceq $json) 'Original legacy ChatGPT backup no longer works.'
    Put-Auth $BrowserAuthPath $browser
    Start-CodexAuthTransition
    Copy-CodexAuthAtomic -Source $BrowserAuthPath -Destination $ActiveAuthPath
    Write-CodexAuthMode 'browser'
    Complete-CodexAuthTransition
    Assert-Case ((Read-Auth $ActiveAuthPath) -ceq $browser) 'Official restore changed.'
    Put-Auth $ActiveAuthPath ($browser.Replace('synthetic-browser','synthetic-refreshed'))
    & $recover
    Assert-Case ((Read-Auth $BrowserAuthPath) -ceq (Read-Auth $ActiveAuthPath) -and (Read-Auth $AccountJsonAuthPath) -ceq $json) 'Correct mode recycling failed.'
    Set-CodexLogoutBlock 'browser'
    & $recover
    Assert-Case (-not (Test-Path -LiteralPath $ActiveAuthPath)) 'Logged-out active credentials restored.'
    $blocked=$false
    try { Copy-CodexAuthAtomic -Source $BrowserAuthPath -Destination $ActiveAuthPath } catch { $blocked=$true }
    Assert-Case $blocked 'Logout block bypassed.'
    Put-Auth $ActiveAuthPath $browser
    Copy-CodexAuthAtomic -Source $ActiveAuthPath -Destination $BrowserAuthPath -FreshLogin
    Clear-CodexLogoutBlockAfterFreshLogin 'browser'
    Assert-Case (-not (Test-CodexLogoutBlocked 'browser')) 'Fresh login did not clear original logout block.'
    Start-CodexAuthTransition
    & $recover
    Assert-Case (-not (Test-Path -LiteralPath $ActiveAuthPath) -and -not (Test-CodexAuthTransitionPending)) 'Interrupted transition recovery changed.'
    Assert-Case (@(Get-ChildItem -LiteralPath $env:CODEX_HOME -File -Filter 'auth.json.invalid-transition-*').Count -eq 1) 'Interrupted transition material lost.'
    Assert-Case ((Read-Auth $AccountJsonAuthPath) -ceq $json -and (Read-Auth $BrowserAuthPath) -ceq $browser) 'Recovery changed durable snapshots.'
    Write-Output 'PASS original legacy ChatGPT backup, restore, recycling, logout block, fresh login and interrupted transition'
} finally {
    $env:CODEX_HOME=$oldHome
    if (Test-Path -LiteralPath $Root) {
        $item=Get-Item -LiteralPath $Root -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {throw 'Unsafe fixture cleanup.'}
        foreach ($child in @(Get-ChildItem -LiteralPath $Root -Force -Recurse)) {
            if ($child.Attributes -band [IO.FileAttributes]::ReparsePoint) {throw 'Linked fixture cleanup refused.'}
        }
        Remove-Item -LiteralPath $Root -Recurse -Force
    }
}
