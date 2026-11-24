#Requires -Version 5.1
# Production routing and selection functions, with synthetic HTTP and cache
# doubles. No actual credentials, external requests, or writes.
param([string]$BaselineCommit = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$tokens = $null; $errors = $null
if ($BaselineCommit) {
    if ($BaselineCommit -notmatch '^[a-f0-9]{40}$') { throw 'Invalid baseline commit.' }
    $oldLines = & git -C $root show ($BaselineCommit + ':login-json.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Could not read baseline source.' }
    $ast = [Management.Automation.Language.Parser]::ParseInput(($oldLines -join "`n"), [ref]$tokens, [ref]$errors)
} else {
    $ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $root 'login-json.ps1'), [ref]$tokens, [ref]$errors)
}
if ($errors.Count) { throw 'Login source failed to parse.' }
$definitions = @($ast.FindAll({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] }, $true))
$names = @('Invoke-JsonHttp','Test-AutoDirectHttpSuccess','Add-HttpNetworkTag',
    'Test-PermanentRefreshFailure','Test-TransientHttpBlock','Select-LoginJson','Get-ModelSlug','Get-StringProperty','Get-ObjectProperty')
if (-not $BaselineCommit) { $names += 'Test-RefreshDeliveryUncertain' }
foreach ($name in $names) {
    $nodes = @($definitions | Where-Object { $_.Name -eq $name })
    if ($nodes.Count -ne 1) { throw ('Expected exactly one production function: ' + $name) }
    . ([scriptblock]::Create($nodes[0].Extent.Text))
}
function Assert-Case { param([bool]$Condition,[string]$Label) if (-not $Condition) { throw $Label } }
$script:Mode='auto'
$script:Routes=@()
function Assert-AllowedLoginJsonUrl { param([string]$Url) }
function Get-LoginJsonProxyMode { return $script:Mode }
function Get-ProxyUrl { param([switch]$Force) return 'http://127.0.0.1:65432' }
function Invoke-JsonHttpAttempt {
    param([string]$Method,[string]$Url,[hashtable]$Headers,$Body,[int]$TimeoutSec,[string]$ProxyUrl)
    if ([string]::IsNullOrWhiteSpace($ProxyUrl)) {
        $script:Routes += 'direct'
        return $script:Direct
    }
    $script:Routes += 'proxy'
    return $script:Proxy
}
function New-Response {
    param([int]$Status,$NotSent=$null,[string]$Body='')
    $r=[pscustomobject]@{StatusCode=$Status;Body=$Body;Json=$null;Error=''}
    if ($null -ne $NotSent) { $r | Add-Member -NotePropertyName RequestNotSent -NotePropertyValue $NotSent }
    return $r
}
function Test-Route {
    param([string]$Method,$Direct,$Proxy)
    $script:Routes=@()
    $script:Direct=$Direct
    $script:Proxy=$Proxy
    $url=if ($Method -eq 'POST') {'https://auth.openai.com/oauth/token'} else {'https://chatgpt.com/backend-api/wham/usage'}
    return (Invoke-JsonHttp -Method $Method -Url $url)
}
$uncertain=Test-Route POST (New-Response 0 $false) (New-Response 200)
$firstOK=($uncertain.StatusCode -eq 0 -and ($script:Routes -join ',') -ceq 'direct')
$uncertainSecond=Test-Route POST (New-Response 401 $null '{"error":"invalid_grant"}') (New-Response 0 $false)
$secondOK=($uncertainSecond.StatusCode -eq 0 -and -not (Test-PermanentRefreshFailure $uncertainSecond) -and
    ($script:Routes -join ',') -ceq 'direct,proxy')
$LoginDir=Join-Path $root 'login_json'
$HomeDir=Join-Path $root 'home'
$ScanCachePath=Join-Path $LoginDir 'login_json_report.cache.json'
$script:CacheExists=$true
$script:FileLimit=0
$script:CredentialLimit=0
$script:JsonCache=$null
$script:CsvCalls=0
$script:ScanCalls=0
function Get-CodexClientVersion { return '0.170.0' }
function Resolve-MaxFiles { return $script:FileLimit }
function Resolve-MaxCredentials { return $script:CredentialLimit }
function Test-Path { param([string]$LiteralPath) if ($LiteralPath -cne $ScanCachePath) { throw 'Unexpected path' }; return $script:CacheExists }
function Read-ScanCache { param([string]$ClientVersion) return $script:JsonCache }
function New-SelectionRecord {
    param([string]$Source)
    return [pscustomobject]@{
        Status='VALID'; Quota='HAS_QUOTA'; Network='direct'; Models=@([pscustomobject]@{slug='synthetic-model'})
        Email='synthetic'; Plan='synthetic'; File=$Source
    }
}
function Read-CsvReportCache { $script:CsvCalls++; return (New-SelectionRecord 'legacy-csv') }
function Scan-LoginJson { $script:ScanCalls++; return (New-SelectionRecord 'new-scan') }
function Read-Host { param([string]$Prompt) return '' }
function Write-AuthJson { param($Selection,[string]$Model) return $Selection.File }
function Write-Host { param($Object,[string]$ForegroundColor) }
$selected=Select-LoginJson
$cacheOK=($selected -ceq 'new-scan' -and $script:CsvCalls -eq 0 -and $script:ScanCalls -eq 1)
if ($BaselineCommit) {
    Assert-Case (-not $firstOK -and $uncertain.StatusCode -eq 200) 'Previous ambiguous refresh replay did not reproduce.'
    Assert-Case (-not $secondOK -and (Test-PermanentRefreshFailure $uncertainSecond)) 'Previous proxy ambiguity was not treated as permanent.'
    Assert-Case (-not $cacheOK -and $selected -ceq 'legacy-csv') 'Previous CSV bypass did not reproduce.'
    Write-Output 'REPRODUCED old refresh replay, false permanent classification after second-route uncertainty, and invalid JSON cache bypass'
    return
}
Assert-Case ($firstOK -and $secondOK) 'Ambiguous refresh was replayed or incorrectly classified permanent.'
foreach ($status in 408,500,502,503) {
    $r=Test-Route POST (New-Response $status) (New-Response 200)
    Assert-Case ($r.StatusCode -eq $status -and ($script:Routes -join ',') -ceq 'direct' -and -not (Test-PermanentRefreshFailure $r)) 'Uncertain HTTP response replayed.'
}
$r=Test-Route POST (New-Response 0 $true) (New-Response 200)
Assert-Case ($r.StatusCode -eq 200 -and ($script:Routes -join ',') -ceq 'direct,proxy') 'Proven connection failure lost proxy fallback.'
foreach ($proof in @('true',1)) {
    $r=Test-Route POST (New-Response 0 $proof) (New-Response 200)
    Assert-Case ($r.StatusCode -eq 0 -and ($script:Routes -join ',') -ceq 'direct') 'Non-boolean proof accepted.'
}
$r=Test-Route POST (New-Response 401 $null '{"error":"invalid_grant"}') (New-Response 0 $true)
Assert-Case ($r.StatusCode -eq 401 -and (Test-PermanentRefreshFailure $r) -and ($script:Routes -join ',') -ceq 'direct,proxy') 'Definitive failure classification changed when second request was provably unsent.'
$r=Test-Route POST (New-Response 403 $null '<html>challenge</html>') (New-Response 200)
Assert-Case ($r.StatusCode -eq 200 -and ($script:Routes -join ',') -ceq 'direct,proxy') 'Existing challenge fallback changed.'
foreach ($status in 0,403,500) {
    $r=Test-Route GET (New-Response $status) (New-Response 200)
    Assert-Case ($r.StatusCode -eq 200 -and ($script:Routes -join ',') -ceq 'direct,proxy') 'Ordinary GET fallback changed.'
}
foreach ($mode in 'direct','proxy') {
    $script:Mode=$mode
    $r=Test-Route POST (New-Response 0) (New-Response 0)
    Assert-Case (($script:Routes -join ',') -ceq $mode) 'Explicit route changed.'
}
$script:Mode='auto'
Write-Output 'PASS ambiguous refresh protection, proven connect failure fallback, definitive rejection and GET/direct/proxy behavior'
Assert-Case $cacheOK 'Invalid authoritative cache fell back to legacy CSV.'
$script:JsonCache=New-SelectionRecord 'verified-json'
$selected=Select-LoginJson
Assert-Case ($selected -ceq 'verified-json' -and $script:CsvCalls -eq 0 -and $script:ScanCalls -eq 1) 'Valid JSON cache no longer reused.'
$script:JsonCache=$null
$script:CacheExists=$false
$selected=Select-LoginJson
Assert-Case ($selected -ceq 'legacy-csv' -and $script:CsvCalls -eq 1 -and $script:ScanCalls -eq 1) 'Legacy CSV compatibility lost.'
$script:FileLimit=1
$selected=Select-LoginJson
Assert-Case ($selected -ceq 'new-scan' -and $script:CsvCalls -eq 1 -and $script:ScanCalls -eq 2) 'Explicit file limit bypassed.'
$script:FileLimit=0
$script:CredentialLimit=1
$selected=Select-LoginJson
Assert-Case ($selected -ceq 'new-scan' -and $script:CsvCalls -eq 1 -and $script:ScanCalls -eq 3) 'Explicit credential limit bypassed.'
Write-Output 'PASS authoritative cache validation, valid cache reuse, legacy CSV compatibility and explicit scan limits'
