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
$Root=Join-Path $scratch ('auth-transition-test-'+[guid]::NewGuid().ToString('N'))
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
    # Extract both actual pre-login commit tails and the actual fresh-login
    # branch. Execute those statements with real filesystem helpers, but no
    # external client or login service.
    $menuStart=$normalized.IndexOf('$SelectedAuthMode = if ($UseAccountJsonLogin)')
    $menuEnd=$normalized.IndexOf('$ReasoningMenu = Get-ModelReasoningMenuInfo',$menuStart)
    $cliStart=$normalized.IndexOf('if ($ConfiguredAuthMode -ne "menu") { Write-CodexAuthMode $EffectiveAuthMode }')
    if ($menuStart -lt 0 -or $menuEnd -le $menuStart -or $cliStart -lt 0) { throw 'Commit tail not found.' }
    $menuCommit=[scriptblock]::Create($normalized.Substring($menuStart,$menuEnd-$menuStart))
    # CLI tail ends at the closing brace on a line of its own, after either
    # the old unconditional completion or new conditional completion.
    $cliText=$normalized.Substring($cliStart)
    $cliMatch=[regex]::Match($cliText,'(?s)\A(.*?)\n\}')
    if (-not $cliMatch.Success) { throw 'CLI commit tail not found.' }
    $cliCommit=[scriptblock]::Create($cliMatch.Groups[1].Value)
    $loginNodes=@($ast.FindAll({
        param($node)
        $node -is [Management.Automation.Language.IfStatementAst] -and
            $node.Clauses[0].Item1.Extent.Text -ceq '$UseBrowserLogin -and $BrowserLoginRequired'
    },$true))
    if ($loginNodes.Count -ne 1) { throw 'Fresh-login branch not found.' }
    $freshLogin=[scriptblock]::Create($loginNodes[0].Extent.Text)
    $script:LoginCalls=0
    $script:FailSnapshot=$false
    function Invoke-CodexOfficialAccountLogin {
        param([string]$Flow)
        if ($Flow -cne 'device_auth') { throw 'Original default login flow changed.' }
        $script:LoginCalls++
        if (-not (Test-CodexAuthTransitionPending)) { throw 'Login launched without a pending transition.' }
        Put-Auth $ActiveAuthPath $browser
        return 0
    }
    # Inject only a synthetic failure at the existing durable snapshot copy.
    $originalCopy=(Get-Command Copy-CodexAuthAtomic -CommandType Function).ScriptBlock
    function Copy-CodexAuthAtomic {
        param([string]$Source,[string]$Destination,[switch]$FreshLogin)
        if ($script:FailSnapshot -and $FreshLogin) { throw 'Synthetic snapshot commit failure.' }
        & $originalCopy -Source $Source -Destination $Destination -FreshLogin:$FreshLogin
    }

    Put-Auth $AccountJsonAuthPath $json
    Write-CodexAuthMode 'account_json'
    $UseAccountJsonLogin=$false
    $UseBrowserLogin=$true
    $BrowserLoginFlow='device_auth'
    $ConfiguredAuthMode='browser'
    $EffectiveAuthMode='browser'

    foreach ($tail in @($menuCommit,$cliCommit)) {
        $BrowserLoginRequired=$true
        Start-CodexAuthTransition
        & $tail
        $pending=Test-CodexAuthTransitionPending
        Assert-Case ((Read-CodexAuthMode) -ceq 'browser') 'Selected mode was not written.'
        # Simulate interruption after the official child has written auth.json
        # but before the wrapper has received a success exit and committed it.
        Put-Auth $ActiveAuthPath $browser
        & $recover
        if ($BaselineCommit) {
            Assert-Case (-not $pending -and (Test-Path -LiteralPath $BrowserAuthPath) -and
                (Read-Auth $BrowserAuthPath) -ceq $browser) 'Previous incomplete login promotion did not reproduce.'
            Remove-Item -LiteralPath $BrowserAuthPath,$ActiveAuthPath -Force
        } else {
            Assert-Case ($pending -and -not (Test-Path -LiteralPath $BrowserAuthPath) -and
                -not (Test-Path -LiteralPath $ActiveAuthPath)) 'Incomplete login was promoted or not quarantined.'
            Assert-Case (-not (Test-CodexAuthTransitionPending)) 'Existing recovery did not clear marker.'
        }
        Assert-Case ((Read-Auth $AccountJsonAuthPath) -ceq $json) 'Unrelated snapshot changed.'
    }
    if ($BaselineCommit) {
        Write-Output 'REPRODUCED both previous menu and CLI paths promoted interrupted official login into durable snapshot'
        return
    }
    Assert-Case (@(Get-ChildItem -LiteralPath $env:CODEX_HOME -File -Filter 'auth.json.invalid-transition-*').Count -eq 2) 'Incomplete credentials were not preserved separately.'
    Write-Output 'PASS both menu and CLI retain transition through incomplete fresh login and preserve unrelated snapshot'
    foreach ($tail in @($menuCommit,$cliCommit)) {
        $BrowserLoginRequired=$false
        Start-CodexAuthTransition
        & $tail
        Assert-Case (-not (Test-CodexAuthTransitionPending)) 'Existing snapshot restore no longer commits normally.'
    }
    $BrowserLoginRequired=$true
    Start-CodexAuthTransition
    & $cliCommit
    $script:FailSnapshot=$true
    $failed=$false
    try { & $freshLogin } catch {
        if ($_.Exception.Message -cne 'Synthetic snapshot commit failure.') { throw }
        $failed=$true
    }
    Assert-Case ($failed -and (Test-CodexAuthTransitionPending) -and -not (Test-Path -LiteralPath $BrowserAuthPath)) 'Failed durable copy falsely completed transition.'
    & $recover
    Assert-Case (-not (Test-Path -LiteralPath $ActiveAuthPath)) 'Failed durable copy was recycled.'
    $script:FailSnapshot=$false
    Set-CodexLogoutBlock 'browser'
    Start-CodexAuthTransition
    & $menuCommit
    & $freshLogin
    Assert-Case ((Read-Auth $BrowserAuthPath) -ceq $browser -and -not (Test-CodexAuthTransitionPending) -and
        -not (Test-CodexLogoutBlocked 'browser') -and $script:LoginCalls -eq 2) 'Successful fresh login did not commit normally.'
    Assert-Case ((Read-Auth $AccountJsonAuthPath) -ceq $json) 'Successful fresh login changed unrelated snapshot.'
    Write-Output 'PASS existing snapshot restore, failed durable write recovery and successful fresh-login commit'
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
