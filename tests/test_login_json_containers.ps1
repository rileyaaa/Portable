#Requires -Version 5.1
# Exercise the actual parser and pruning functions with in-memory synthetic JSON.
# No real credential files, authentication services, or filesystem deletions.
param([string]$BaselineCommit = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$tokens = $null; $errors = $null
if ($BaselineCommit) {
    if ($BaselineCommit -notmatch '^[a-f0-9]{40}$') { throw 'Invalid baseline commit.' }
    $oldLines = & git -C $root show ($BaselineCommit + ':login-json.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Could not read baseline production source.' }
    $ast = [Management.Automation.Language.Parser]::ParseInput(($oldLines -join "`n"), [ref]$tokens, [ref]$errors)
} else {
    $ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $root 'login-json.ps1'), [ref]$tokens, [ref]$errors)
}
if ($errors.Count) { throw 'Login source failed to parse.' }
$definitions = @($ast.FindAll({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] }, $true))
foreach ($name in @(
    'Get-ObjectProperty','Get-StringProperty','Test-LooksLikeCredentialObject',
    'Add-CredentialEntry','Add-CredentialEntriesFromItem','Get-CredentialEntriesFromJson',
    'Set-ObjectProperty','Add-RemovalIndex','Remove-IndexesFromArrayValue',
    'Set-ArrayPropertyAfterRemoval','Remove-ObjectPropertyIfPresent','Add-RemovalListIndex',
    'Add-RemovalListName','Test-ItemHasCredentialEntries','Remove-CredentialSourcesFromJson'
)) {
    $nodes = @($definitions | Where-Object { $_.Name -eq $name })
    if ($nodes.Count -ne 1) { throw ('Expected exactly one production function: ' + $name) }
    . ([scriptblock]::Create($nodes[0].Extent.Text))
}
function Assert-Case { param([bool]$Condition,[string]$Label) if (-not $Condition) { throw $Label } }
$path = Join-Path $root 'tmp/synthetic-container-never-written.json'
$single = '{"accounts":[{"access_token":"synthetic-a","account_id":"account-a"}]}' | ConvertFrom-Json
$entries = @(Get-CredentialEntriesFromJson -Path $path -Json $single)
$singleOK = ($entries.Count -eq 1 -and $entries[0].Source -ceq 'accounts[0]' -and -not $entries[0].LoadError)
$partial = '{"accounts":[{"credentials":[{"access_token":"synthetic-invalid"},{"note":"untested"}]},{"access_token":"synthetic-keep"}]}' | ConvertFrom-Json
$pruned = Remove-CredentialSourcesFromJson -Json $partial -Sources @('accounts[0].credentials[0]')
$partialOK = ($pruned.Json.accounts.Count -eq 2 -and $pruned.Json.accounts[0].credentials.Count -eq 1 -and $pruned.Json.accounts[0].credentials[0].note -ceq 'untested')
if ($BaselineCommit) {
    Assert-Case (-not $singleOK) 'Baseline singleton bug did not reproduce.'
    Assert-Case (-not $partialOK) 'Baseline untested sibling prune bug did not reproduce.'
    Write-Output 'REPRODUCED exact previous source: singleton accounts array misclassified; untested nested sibling pruned'
    return
}
Assert-Case $singleOK 'Singleton accounts array must retain indexed source.'
Assert-Case ($entries[0].CredentialIndex -eq 0 -and $entries[0].DeleteAllowed) 'Existing single-entry deletion policy changed.'
Assert-Case ($single.accounts -is [array]) 'Source account array shape changed.'
Write-Output 'PASS singleton account array and existing single-entry deletion policy'
foreach ($case in @(
    @{json='{"credentials":[{"access_token":"synthetic-a"}]}'; source='credentials[0]'},
    @{json='{"credentials":{"access_token":"synthetic-a"}}'; source='credentials'},
    @{json='{"accounts":[{"credentials":[{"access_token":"synthetic-a"}]}]}'; source='accounts[0].credentials[0]'},
    @{json='{"accounts":{"named":{"credentials":{"access_token":"synthetic-a"}}}}'; source='accounts.named.credentials[0]'},
    @{json='{"accounts":[{"credentials":[],"access_token":"synthetic-a"}]}'; source='accounts[0]'},
    @{json='{"access_token":"synthetic-a"}'; source='root'}
)) {
    $obj = $case.json | ConvertFrom-Json
    $items = @(Get-CredentialEntriesFromJson -Path $path -Json $obj)
    Assert-Case ($items.Count -eq 1 -and -not $items[0].LoadError -and $items[0].Source -ceq $case.source) ('Parser source mismatch: ' + $case.source)
    Assert-Case ($items[0].DeleteAllowed -eq $true) 'Single-entry delete policy changed.'
}
Write-Output 'PASS singleton array, scalar, named map, empty-list fallback and root formats'
$multi = '{"accounts":[{"credentials":[{"access_token":"synthetic-invalid"},{"access_token":"synthetic-valid","account_id":"account-b"}]}]}' | ConvertFrom-Json
$before = @(Get-CredentialEntriesFromJson -Path $path -Json $multi)
Assert-Case ($before.Count -eq 2 -and -not $before[0].DeleteAllowed -and -not $before[1].DeleteAllowed) 'Multi-entry deletion policy changed.'
$after = Remove-CredentialSourcesFromJson -Json $multi -Sources @($before[0].Source)
$remaining = @(Get-CredentialEntriesFromJson -Path $path -Json $after.Json)
Assert-Case ($after.Matched -eq 1 -and $remaining.Count -eq 1 -and -not $remaining[0].LoadError) 'Pruned singleton is not readable.'
Assert-Case ($remaining[0].Source -ceq 'accounts[0].credentials[0]' -and $remaining[0].CredentialIndex -eq 0) 'Remaining credential index/source is incorrect.'
Assert-Case ($remaining[0].Json.access_token -ceq 'synthetic-valid') 'Prune changed the surviving credential.'
Assert-Case ($after.Json.accounts -is [array] -and $after.Json.accounts[0].credentials -is [array]) 'Prune changed the container shape.'
Write-Output 'PASS multi-entry prune, singleton reread, renumbering and token preservation'
Assert-Case $partialOK 'Partial prune removed an untested sibling.'
$remaining = @(Get-CredentialEntriesFromJson -Path $path -Json $pruned.Json)
Assert-Case ($remaining.Count -eq 2 -and $remaining[0].Json.note -ceq 'untested' -and $remaining[1].Json.access_token -ceq 'synthetic-keep') 'Partial prune no longer exposes remaining records for their own checks.'
Assert-Case (-not $remaining[0].DeleteAllowed -and -not $remaining[1].DeleteAllowed) 'Surviving multi-container must retain local pruning.'
$fullyChecked = Remove-CredentialSourcesFromJson -Json $pruned.Json -Sources @($remaining[0].Source)
$last = @(Get-CredentialEntriesFromJson -Path $path -Json $fullyChecked.Json)
Assert-Case ($last.Count -eq 1 -and $last[0].Json.access_token -ceq 'synthetic-keep') 'Final rejected nested entry should still be removed.'
Write-Output 'PASS partial prune preserves unchecked record; later confirmed removal works'
