#Requires -Version 5.1
# Offline tests of exact production functions. Synthetic identities only.
# Network, credential reads, auth writes and job operations are test doubles.
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
foreach ($name in @('New-ScanResult','ConvertTo-ResultRecord','Get-RelativePathUnderRoot',
    'New-ProbeErrorResult','Receive-CompletedProbeJobs','Write-AuthJson','Get-ResultCredentialIndex')) {
    $nodes = @($definitions | Where-Object { $_.Name -eq $name })
    if ($nodes.Count -ne 1) { throw ('Expected exactly one production function: ' + $name) }
    . ([scriptblock]::Create($nodes[0].Extent.Text))
}
function Assert-Case { param([bool]$Condition,[string]$Label) if (-not $Condition) { throw $Label } }
$TmpDir = Join-Path $root 'tmp'
$LoginDir = Join-Path $root 'login_json'
$HomeDir = Join-Path $root 'home'
$ResultPath = Join-Path $TmpDir 'synthetic-selection-never-written.json'
$SkipPackageMutex = $true
$path = Join-Path $LoginDir 'synthetic-never-read.json'
$script:Stops = 0; $script:Removals = 0; $script:Writes = 0
function Stop-Job { param($Job) $script:Stops++; $Job.State = 'Stopped' }
function Receive-Job { param($Job) }
function Remove-Job { param($Job,[switch]$Force) }
function Remove-Item {
    param([string]$LiteralPath)
    if ($LiteralPath -notin @((Join-Path $TmpDir 'synthetic-result-1.json'),(Join-Path $TmpDir 'synthetic-result-2.json'))) {
        throw 'Unexpected synthetic cleanup path.'
    }
    $script:Removals++
}
function Test-IsPortableSingleLinkRegularFile { param([string]$Path,[string]$Directory) return $false }
function Test-IsUnderDirectory { param([string]$Path,[string]$Directory) return $true }
function Test-Path { param([string]$LiteralPath) return $false }
function ConvertTo-SafeMessage { param([string]$Text) return 'Synthetic diagnostic' }
function Write-ScanResultProgress { param($Result,[int]$Done,[int]$Total) }
function Save-PartialReport { param($Results) }
function Write-PortableNewUtf8File { param([string]$Path,[string]$Text) $script:Writes++ }
function Write-Utf8JsonFile { param([string]$Path,$InputObject,[int]$Depth) $script:Writes++ }
function Read-CredentialFile {
    param([string]$Path,[int]$CredentialIndex)
    if ($Path -cne $path -or $CredentialIndex -ne 1) { throw 'Unexpected synthetic credential selection.' }
    return [pscustomobject]@{ AccountId='synthetic-current'; AccessToken='synthetic-access'; RefreshToken='synthetic-refresh'; IdToken='synthetic-id'; Email=''; Plan='' }
}
$jobs = New-Object System.Collections.ArrayList
$results = New-Object System.Collections.ArrayList
foreach ($i in 1,2) {
    [void]$jobs.Add([pscustomobject]@{
        Job=[pscustomobject]@{State=$(if ($i -eq 1) {'Running'} else {'Completed'})}
        FilePath=$path
        Entry=[pscustomobject]@{File=('synthetic-never-read.json#'+($i+1));CredentialIndex=$i;Source=('accounts['+$i+']');DeleteAllowed=$false}
        ResultPath=(Join-Path $TmpDir ('synthetic-result-'+$i+'.json'))
        StartedAtUtc=[datetime]::UtcNow.AddMinutes(-2)
        TimeoutSec=30
    })
}
$script:LoginJsonProgressTotal=2
Receive-CompletedProbeJobs -Jobs $jobs -Results $results -OnlyFinished
Assert-Case ($jobs.Count -eq 0 -and $results.Count -eq 2 -and $script:Stops -eq 1 -and $script:Removals -eq 2) 'Synthetic job cleanup changed.'
$byIndex = @($results | Sort-Object CredentialIndex)
$identityOK = ($byIndex[0].CredentialIndex -eq 1 -and $byIndex[0].Source -ceq 'accounts[1]' -and
    $byIndex[0].File -ceq 'synthetic-never-read.json#2' -and
    $byIndex[1].CredentialIndex -eq 2 -and $byIndex[1].Source -ceq 'accounts[2]' -and
    $byIndex[1].File -ceq 'synthetic-never-read.json#3' -and
    -not $byIndex[0].DeleteAllowed -and -not $byIndex[1].DeleteAllowed)
foreach ($r in $results) {
    Assert-Case ($r.Status -ceq 'ERROR_KEPT' -and -not $r.Deleted) 'Job failure changed existing keep policy.'
}
$selection=[pscustomobject]@{File='synthetic-never-read.json#2';Path=$path;CredentialIndex=1;AccountId='synthetic-stale'}
$blocked=$false
try { $null=Write-AuthJson -Selection $selection -Model 'synthetic-model' } catch {
    if ($_.Exception.Message -notlike '*no longer matches the reported account ID*') { throw }
    $blocked=$true
}
if ($BaselineCommit) {
    Assert-Case (-not $identityOK) 'Previous report identity loss did not reproduce.'
    Assert-Case (-not $blocked -and $script:Writes -eq 3) 'Previous stale-account import did not reproduce.'
    Write-Output 'REPRODUCED old probe error identity loss and stale selected account reaching all three synthetic writes'
    return
}
Assert-Case $identityOK 'Failed probe lost its exact credential report identity.'
Assert-Case ($byIndex[0].Message -like '*timed out*' -and $byIndex[1].Message -like '*did not write a result*') 'Existing diagnostics changed.'
Assert-Case ($blocked -and $script:Writes -eq 0) 'Mismatched account reached an authentication write.'
Write-Output 'PASS timeout/missing result keep exact multi-account report identity and existing ERROR_KEPT policy'
Write-Output 'PASS stale account ID rejected before transition/auth/selection writes'
$selection.AccountId='synthetic-current'
$null=Write-AuthJson -Selection $selection -Model 'synthetic-model'
Assert-Case ($script:Writes -eq 3) 'Matching account did not retain original write flow.'
$selection.AccountId=''
$null=Write-AuthJson -Selection $selection -Model 'synthetic-model'
Assert-Case ($script:Writes -eq 6) 'Legacy record without account ID changed.'
$explicit=[pscustomobject]@{File=$selection.File;Path=$path;CredentialIndex=1;Credential=(Read-CredentialFile -Path $path -CredentialIndex 1)}
$null=Write-AuthJson -Selection $explicit -Model 'synthetic-model'
Assert-Case ($script:Writes -eq 9) 'Explicit Use selection without reported identity changed.'
Write-Output 'PASS matching cache, legacy empty ID and explicit Use retain original write flow'
