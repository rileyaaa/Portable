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
$Root=Join-Path $scratch ('auth-structure-test-'+[guid]::NewGuid().ToString('N'))
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
    # Token content is synthetic. Validate JSON value types, not JWT
    # claims, expiry, or live account validity.
    $bad=@(
        '{"auth_mode":"chatgpt","tokens":{"access_token":true}}',
        '{"auth_mode":"chatgpt","tokens":{"refresh_token":123}}',
        '{"auth_mode":"chatgpt","tokens":{"access_token":["synthetic"]}}',
        '{"auth_mode":"chatgpt","tokens":{"refresh_token":{"value":"synthetic"}}}',
        '{"auth_mode":"chatgpt","tokens":{"access_token":"synthetic","refresh_token":false}}',
        '{"auth_mode":"chatgpt","tokens":{"access_token":"synthetic","id_token":42}}',
        '{"auth_mode":"chatgpt","tokens":{"access_token":"synthetic","account_id":["synthetic"]}}',
        '{"auth_mode":"chatgpt","tokens":{"access_token":"synthetic","login_owner_id":{}}}',
        '{"auth_mode":"chatgpt","tokens":[{"access_token":"synthetic"}]}',
        '[{"auth_mode":"chatgpt","tokens":{"access_token":"synthetic"}}]',
        '{"auth_mode":["chatgpt"],"tokens":{"access_token":"synthetic"}}',
        '{"auth_mode":"apikey","OPENAI_API_KEY":123}',
        '{"auth_mode":"chatgpt","OPENAI_API_KEY":true,"tokens":{"access_token":"synthetic"}}'
    )
    $accepted=0
    foreach ($value in $bad) {
        Put-Auth $ActiveAuthPath $value
        if (Test-CodexAuthFile $ActiveAuthPath) { $accepted++ }
    }
    $corrupt=$bad[0]
    Put-Auth $ActiveAuthPath $corrupt
    Put-Auth $BrowserAuthPath $browser
    Put-Auth $AccountJsonAuthPath $json
    Write-CodexAuthMode 'browser'
    & $recover
    if ($BaselineCommit) {
        Assert-Case ($accepted -gt 0 -and (Read-Auth $BrowserAuthPath) -ceq $corrupt) 'Previous coercion and corrupt snapshot overwrite did not reproduce.'
        Write-Output ('REPRODUCED previous accepted malformed credential structures: '+$accepted+'; malformed token overwrote valid snapshot')
        return
    }
    Assert-Case ($accepted -eq 0) 'Malformed token, mode, API key or JSON container accepted.'
    Assert-Case ((Read-Auth $BrowserAuthPath) -ceq $browser -and (Read-Auth $AccountJsonAuthPath) -ceq $json) 'Malformed active credential replaced a snapshot.'
    Assert-Case (-not (Test-Path -LiteralPath $ActiveAuthPath)) 'Malformed active file was not quarantined.'
    $invalid=@(Get-ChildItem -LiteralPath $env:CODEX_HOME -File -Filter 'auth.json.invalid-*')
    Assert-Case ($invalid.Count -eq 1 -and (Read-Auth $invalid[0].FullName) -ceq $corrupt) 'Original malformed content was not preserved.'
    Write-Output ('PASS rejected '+$bad.Count+' malformed JSON value/container cases; prior snapshots unchanged')
    $valid=@(
        $api,
        $json,
        $browser,
        '{"auth_mode":"chatgpt","OPENAI_API_KEY":null,"tokens":{"access_token":"synthetic"}}',
        '{"auth_mode":"chatgpt","tokens":{"refresh_token":"synthetic"}}',
        '{"auth_mode":"chatgpt","tokens":{"access_token":"synthetic","refresh_token":null,"account_id":null}}',
        '{"auth_mode":"chatgpt","tokens":{"access_token":"","refresh_token":"synthetic","id_token":"","account_id":"synthetic","login_owner_id":"synthetic"}}'
    )
    foreach ($value in $valid) {
        Put-Auth $ActiveAuthPath $value
        Assert-Case (Test-CodexAuthFile $ActiveAuthPath) 'Existing string or partial credential shape no longer accepted.'
    }
    Put-Auth $ActiveAuthPath $api
    Assert-Case (-not (Test-CodexAuthFile $ActiveAuthPath -RequireChatGpt)) 'Prior official-only policy regressed.'
    Put-Auth $ActiveAuthPath '{"auth_mode":"chatgpt","tokens":{"access_token":"","refresh_token":" "}}'
    Assert-Case (-not (Test-CodexAuthFile $ActiveAuthPath)) 'Blank credentials accepted.'
    Write-Output 'PASS original API/ChatGPT string fields, partial legacy shapes and official-only policy'
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
