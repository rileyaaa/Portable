#Requires -Version 5.1
# Exact production refresh and quota functions; synthetic data and stubbed HTTP/save.
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
$names = @('Get-ObjectProperty','Get-StringProperty','Set-ObjectProperty','ConvertTo-PortableJsonText',
    'Convert-CredentialEntryToCredential','Refresh-Credential','Get-UsageSummary',
    'Test-NoQuotaResetStillPending','Test-PermanentRefreshFailure','Test-TransientHttpBlock',
    'ConvertFrom-Base64Url','Decode-JwtPayload','Get-JwtEmail','Get-JwtAuthField')
if (-not $BaselineCommit) { $names += @('Set-RefreshedTokenProperty','Get-BlockedRateLimitReset') }
foreach ($name in $names) {
    $nodes = @($definitions | Where-Object { $_.Name -eq $name })
    if ($nodes.Count -ne 1) { throw ('Expected exactly one production function: ' + $name) }
    . ([scriptblock]::Create($nodes[0].Extent.Text))
}
function Assert-Case { param([bool]$Condition,[string]$Label) if (-not $Condition) { throw $Label } }
$script:Requests = 0; $script:Saves = 0
$script:Response = [pscustomobject]@{StatusCode=200;Body='';Error='';Json=[pscustomobject]@{
    access_token='synthetic-new-access'; refresh_token='synthetic-new-refresh'; id_token='synthetic-new-id'; expires_in=3600
}}
function Invoke-JsonHttp {
    param([string]$Method,[string]$Url,[hashtable]$Headers,$Body,[int]$TimeoutSec)
    Assert-Case ($Method -ceq 'POST' -and $Url -ceq 'https://auth.openai.com/oauth/token' -and $Body.grant_type -ceq 'refresh_token') 'Existing refresh request contract changed.'
    $script:Requests++
    return $script:Response
}
function Save-CredentialFile { param([string]$Path,$Credential) $script:Saves++ }
function ConvertTo-SafeMessage { param([string]$Text) return 'Synthetic diagnostic' }
function New-TestCredential {
    param([string]$Json,[string]$ParentJson='{}')
    $item = $Json | ConvertFrom-Json
    $parent = $ParentJson | ConvertFrom-Json
    $entry = [pscustomobject]@{Json=$item;RootJson=$parent;Parent=$parent;LoadError=''}
    return (Convert-CredentialEntryToCredential $entry)
}
function Test-Quota {
    param($Json)
    return (Get-UsageSummary ([pscustomobject]@{StatusCode=200;Json=$Json;Error=''}))
}
$path = Join-Path $root 'tmp/synthetic-never-written.json'
$oldExpiry='2020-01-01T00:00:00Z'
$cred=New-TestCredential '{"accessToken":"synthetic-old-access","refreshToken":"synthetic-old-refresh","idToken":"synthetic-old-id","account_id":"synthetic-account","expiresAt":"2020-01-01T00:00:00Z","expired":true}'
$before=[DateTimeOffset]::UtcNow
$refresh=Refresh-Credential -Path $path -Credential $cred
Assert-Case ($refresh.Success -and $script:Requests -eq 1 -and $script:Saves -eq 1) 'Successful refresh contract changed.'
$aliasOK=($cred.Json.accessToken -ceq 'synthetic-new-access' -and $cred.Json.refreshToken -ceq 'synthetic-new-refresh' -and $cred.Json.idToken -ceq 'synthetic-new-id')
$expiryOK=($cred.Json.expiresAt -ne $oldExpiry -and $cred.Expires -eq $cred.Json.expiresAt)
$primaryReset=$before.AddHours(2).ToUnixTimeSeconds()
$secondaryReset=$before.AddDays(3).ToUnixTimeSeconds()
$expectedSecondary=[DateTimeOffset]::FromUnixTimeSeconds($secondaryReset).UtcDateTime.ToString('o')
$payload=[pscustomobject]@{rate_limit=[pscustomobject]@{
    allowed=$false;limit_reached=$true
    primary_window=[pscustomobject]@{used_percent=100;reset_after_seconds=7200;reset_at=$primaryReset}
    secondary_window=[pscustomobject]@{used_percent=100;reset_after_seconds=259200;reset_at=$secondaryReset}
}}
$summary=Test-Quota $payload
$resetOK=($summary.Quota -ceq 'NO_QUOTA' -and $summary.Reset -ceq $expectedSecondary)
if ($BaselineCommit) {
    Assert-Case (-not $aliasOK -and -not $expiryOK) 'Previous stale alias/expiry behavior did not reproduce.'
    Assert-Case (-not $resetOK -and $summary.Quota -ceq 'NO_QUOTA') 'Previous wrong reset behavior did not reproduce.'
    Write-Output 'REPRODUCED old refreshed aliases/expiry left stale and first-window reset selected instead of later exhausted window'
    return
}
Assert-Case ($aliasOK -and $expiryOK) 'Successful refresh did not update original token aliases and expiry.'
Assert-Case ($cred.Json.access_token -ceq $cred.Json.accessToken -and $cred.Json.refresh_token -ceq $cred.Json.refreshToken -and $cred.Json.id_token -ceq $cred.Json.idToken -and -not $cred.Json.expired) 'Canonical refresh fields changed.'
$parsed=[DateTimeOffset]::Parse($cred.Expires)
Assert-Case ($parsed -ge $before.AddSeconds(3599) -and $parsed -le [DateTimeOffset]::UtcNow.AddSeconds(3600)) 'Server lifetime not used.'
Write-Output 'PASS refreshed canonical and existing alias tokens, explicit expiry and expired marker'
$nested=New-TestCredential '{"access_token":"synthetic-a","refresh_token":"synthetic-r","account_id":"synthetic-account"}' '{"expires":"2020-01-01T00:00:00Z","credentials":[{"note":"sibling"}]}'
$null=Refresh-Credential -Path $path -Credential $nested
Assert-Case ($nested.Json.expires -and $nested.Json.expires -eq $nested.Expires -and $nested.RootJson.expires -ceq $oldExpiry -and $nested.RootJson.credentials[0].note -ceq 'sibling') 'Shared parent expiry or sibling changed.'
Write-Output 'PASS refresh overrides stale parent fallback on selected entry only'
$script:Response.Json=[pscustomobject]@{access_token='synthetic-access-only'}
$null=Refresh-Credential -Path $path -Credential $cred
Assert-Case ($cred.Json.refreshToken -ceq 'synthetic-new-refresh' -and $cred.Json.idToken -ceq 'synthetic-new-id' -and $cred.Json.expiresAt -eq $cred.Expires) 'Omitted optional refresh fields changed.'
$script:Response.Json | Add-Member -NotePropertyName expires_in -NotePropertyValue '9223372036854775807' -Force
$prior=$cred.Expires
$null=Refresh-Credential -Path $path -Credential $cred
Assert-Case ($cred.Expires -ceq $prior) 'Out-of-range lifetime invented an expiry.'
$script:Response.Json.expires_in=3600
$noExpiry=New-TestCredential '{"access_token":"synthetic-a","refresh_token":"synthetic-r","account_id":"synthetic-account"}'
$null=Refresh-Credential -Path $path -Credential $noExpiry
Assert-Case (-not $noExpiry.Json.PSObject.Properties['expires'] -and -not $noExpiry.Expires) 'New expiry field added to format without existing metadata.'
$script:Response=[pscustomobject]@{StatusCode=401;Body='{"error":"invalid_grant"}';Error='';Json=$null}
$savesBefore=$script:Saves
$rejected=Refresh-Credential -Path $path -Credential $cred
Assert-Case (-not $rejected.Success -and $rejected.Permanent -and $script:Saves -eq $savesBefore) 'Definitive refresh rejection changed.'
Write-Output 'PASS optional/invalid lifetime handling and permanent refresh failure policy'
Assert-Case $resetOK 'Both exhausted windows must use the later absolute reset.'
Assert-Case (Test-NoQuotaResetStillPending $summary) 'Existing quota exclusion does not recognize normalized reset.'
$payload.rate_limit.primary_window.used_percent=25
Assert-Case ((Test-Quota $payload).Reset -ceq $expectedSecondary) 'Non-exhausted primary window was used.'
$payload.rate_limit.primary_window.used_percent=100
$payload.rate_limit.secondary_window.used_percent=80
$expectedPrimary=[DateTimeOffset]::FromUnixTimeSeconds($primaryReset).UtcDateTime.ToString('o')
Assert-Case ((Test-Quota $payload).Reset -ceq $expectedPrimary) 'Non-exhausted secondary window was used.'
$payload.rate_limit.allowed=$true
$payload.rate_limit.limit_reached=$true
Assert-Case ((Test-Quota $payload).Reset -ceq $expectedPrimary) 'limit_reached branch lost structured reset.'
$payload.rate_limit.secondary_window.used_percent=100
$payload.rate_limit.secondary_window.reset_at='invalid'
$payload.rate_limit.secondary_window.reset_after_seconds='invalid'
Assert-Case ((Test-Quota $payload).Reset -eq '') 'Unknown exhausted-window reset was replaced with an unrelated time.'
$payload.rate_limit.secondary_window.reset_after_seconds=259200
$relative=(Test-Quota $payload).Reset
Assert-Case ([DateTimeOffset]::Parse($relative) -ge $before.AddDays(3)) 'Relative reset fallback failed.'
Write-Output 'PASS ordinary primary/secondary exhausted-window reset, missing and relative fallback'
$legacy='{"rate_limit":{"allowed":false},"reset_at":"2030-01-01T00:00:00Z"}' | ConvertFrom-Json
$legacySummary=Test-Quota $legacy
Assert-Case ($legacySummary.Quota -ceq 'NO_QUOTA' -and $legacySummary.Reset -ceq '2030-01-01T00:00:00Z') 'Legacy reset policy changed.'
$available='{"rate_limit":{"allowed":true,"limit_reached":false}}' | ConvertFrom-Json
Assert-Case ((Test-Quota $available).Quota -ceq 'HAS_QUOTA') 'Existing available quota policy changed.'
$ambiguous='{"credits":{"has_credits":false}}' | ConvertFrom-Json
Assert-Case ((Test-Quota $ambiguous).Quota -ceq 'UNKNOWN') 'Existing ambiguous quota policy changed.'
Write-Output 'PASS legacy reset and existing HAS_QUOTA/UNKNOWN classifications'
