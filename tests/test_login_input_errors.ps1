#Requires -Version 5.1
# Offline production-function tests. No credentials, files or network are used.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $root 'login-json.ps1'), [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Login source failed to parse.' }
foreach ($name in @('New-ScanResult','Read-CredentialFile','Set-DeletedResult','Test-CredentialFile','Test-TransientHttpBlock','Test-DefinitiveAuthFailure')) {
    $nodes = @($ast.FindAll({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] }, $true) | Where-Object { $_.Name -eq $name })
    if ($nodes.Count -ne 1) { throw ('Expected one production function: ' + $name) }
    . ([scriptblock]::Create($nodes[0].Extent.Text))
}
function Remove-InvalidCredential { param([string]$Path) $script:Deletes++ }
function ConvertTo-SafeMessage { param([string]$Text) return 'Synthetic suppressed diagnostic' }
function Get-CredentialEntriesForFile {
    param([string]$Path)
    switch ($script:Failure) {
        'io' { throw (New-Object IO.IOException('Synthetic file sharing failure')) }
        'access' { throw (New-Object UnauthorizedAccessException('Synthetic access failure')) }
        'parse' { throw (New-Object FormatException('Synthetic parse failure')) }
    }
    return $script:Entries
}
function Convert-CredentialEntryToCredential {
    param($Entry)
    if ($null -eq $Entry -or $Entry.LoadError) { throw 'Synthetic unavailable input' }
    return $script:Credential
}
function Get-ObjectProperty {
    param($Object, [string]$Name)
    if ($null -ne $Object -and $Object.PSObject.Properties[$Name]) { return $Object.$Name }
    return $null
}
function Invoke-Models {
    param($Credential, [string]$ClientVersion)
    $script:ModelCalls++
    return [pscustomobject]@{ StatusCode=$script:ModelsStatus; Body=''; Json=$null; Error='Synthetic transport result'; Network='synthetic' }
}
function Reset-SyntheticProbe {
    $script:Deletes=0; $script:ModelCalls=0; $script:Failure=''; $script:ModelsStatus=0
    $script:Entries=@([pscustomobject]@{ File='synthetic.json'; CredentialIndex=0; Source='root'; LoadError=''; DeleteAllowed=$true })
    $script:Credential=[pscustomobject]@{ Email=''; AccountId='synthetic-account'; Plan=''; AccessToken=''; RefreshToken=''; IdToken=''; Payload=$null; Expires=''; Json=[pscustomobject]@{} }
}
function Assert-Equal { param($Expected,$Actual,[string]$Label) if ($Expected -cne $Actual) { throw ($Label + ': expected ' + $Expected + ', got ' + $Actual) } }
$path=Join-Path $root 'tmp/synthetic-probe-never-opened.json'
$passed=0
foreach ($kind in @('io','access','parse')) {
    Reset-SyntheticProbe
    $script:Failure=$kind
    $result=Test-CredentialFile -Path $path -ClientVersion 'synthetic'
    Assert-Equal 'ERROR_KEPT' $result.Status ('Unreadable input status: '+$kind)
    Assert-Equal 0 $script:Deletes 'Unreadable input must never request deletion'
    Assert-Equal 0 $script:ModelCalls 'Unreadable input must not reach the model API'
    $passed++; Write-Output ('PASS input failure is kept: '+$kind)
}
Reset-SyntheticProbe
$result=Test-CredentialFile -Path $path -ClientVersion 'synthetic' -CredentialIndex 99
Assert-Equal 'ERROR_KEPT' $result.Status 'Missing credential index'
Assert-Equal 0 $script:Deletes 'Missing index must not delete a container'
Assert-Equal 0 $script:ModelCalls 'Missing index must not reach the model API'
$passed++; Write-Output 'PASS missing credential index preserves container'
foreach ($allow in @($true,$false)) {
    Reset-SyntheticProbe
    $entry=[pscustomobject]@{ File='synthetic.json'; CredentialIndex=0; Source='accounts[0]'; LoadError='Synthetic inspection failure'; DeleteAllowed=$allow }
    $result=Test-CredentialFile -Path $path -ClientVersion 'synthetic' -Entry $entry
    Assert-Equal 'ERROR_KEPT' $result.Status 'LoadError must not become INVALID_KEPT for later pruning'
    Assert-Equal 0 $script:Deletes 'LoadError must not request deletion'
    Assert-Equal 0 $script:ModelCalls 'LoadError must not reach the model API'
    $passed++; Write-Output ('PASS load error preserves input; original DeleteAllowed='+$allow)
}
Reset-SyntheticProbe
$result=Test-CredentialFile -Path $path -ClientVersion 'synthetic'
Assert-Equal 'INVALID_DELETED' $result.Status 'Parsed input with missing required access token retains existing policy'
Assert-Equal 1 $script:Deletes 'Known-invalid input keeps its existing delete path'
$passed++; Write-Output 'PASS successfully parsed missing-token policy is unchanged'
Reset-SyntheticProbe
$script:Credential.AccessToken='synthetic-not-a-credential'
$result=Test-CredentialFile -Path $path -ClientVersion 'synthetic'
Assert-Equal 'ERROR_KEPT' $result.Status 'Transport failure retains input'
Assert-Equal 0 $script:Deletes 'Transport failure must not delete'
Assert-Equal 1 $script:ModelCalls 'One synthetic model request'
$passed++; Write-Output 'PASS transport errors still retain input'
Reset-SyntheticProbe
$script:Credential.AccessToken='synthetic-not-a-credential'; $script:ModelsStatus=401
$result=Test-CredentialFile -Path $path -ClientVersion 'synthetic'
Assert-Equal 'INVALID_DELETED' $result.Status 'Definitive unauthorized with no refresh retains existing policy'
Assert-Equal 1 $script:Deletes 'Known-invalid server result keeps existing delete path'
$passed++; Write-Output 'PASS definitive unauthorized policy is unchanged'
Write-Output ($passed.ToString()+' offline login input-error cases passed; deletion and network are stubs only.')
