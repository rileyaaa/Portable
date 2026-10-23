#Requires -Version 5.1
# Exercise installer policy and ancestor checks without network or installation.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Tokens = $null; $Errors = $null
$Ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $Root 'tool/setup-tools.ps1'), [ref]$Tokens, [ref]$Errors)
if ($Errors.Count) { throw 'Python setup script does not parse.' }
foreach ($Name in @('Get-SetupPipArguments','Assert-SetupPathAncestors','Set-SetupProcessEnvironmentValue','Set-SetupChildPortableEnvironment')) {
    $Found = @($Ast.FindAll({param($Node) $Node -is [Management.Automation.Language.FunctionDefinitionAst]}, $true) | Where-Object { $_.Name -eq $Name })
    if ($Found.Count -ne 1) { throw ('Missing setup function: ' + $Name) }
    . ([scriptblock]::Create($Found[0].Extent.Text))
}
$Site = Join-Path $Root 'tool/python/Lib/site-packages'
$env:PIP_CACHE_DIR = Join-Path $Root 'cache/pip'
$env:PIP_CONFIG_FILE = 'nul'
$Requirements = Join-Path $Root 'tool/python-packages.in.txt'
$Resolve = @(Get-SetupPipArguments -Action Resolve -Requirements $Requirements -Report (Join-Path $Root 'tmp/synthetic-report.json'))
$Install = @(Get-SetupPipArguments -Action Install -Requirements (Join-Path $Root 'tmp/synthetic-lock.txt'))
foreach ($Arguments in @($Resolve, $Install)) {
    foreach ($Required in @('-s','-B','--isolated','--disable-pip-version-check','--no-input','--only-binary=:all:','--no-compile')) {
        if ($Arguments -notcontains $Required) { throw ('Missing pip isolation flag: ' + $Required) }
    }
    if ($Arguments[$Arguments.IndexOf('--target') + 1] -ne $Site) { throw 'Installer target escaped the portable site directory.' }
    if ($Arguments[$Arguments.IndexOf('--index-url') + 1] -ne 'https://pypi.org/simple') { throw 'Unexpected dependency index.' }
}
if ($Resolve -notcontains '--dry-run' -or $Resolve -notcontains '--ignore-installed' -or $Resolve -contains '--upgrade') { throw 'Resolution must not install packages.' }
if ($Install -notcontains '--require-hashes' -or $Install -notcontains '--upgrade' -or $Install -contains '--dry-run') { throw 'Installation must enforce the selected wheel hashes.' }
Write-Output 'PASS resolver/install command policy uses wheels, hashes and package-local paths'
$StartInfo = New-Object Diagnostics.ProcessStartInfo
$StartInfo.EnvironmentVariables['UNREVIEWED_SECRET'] = 'synthetic'
Set-SetupChildPortableEnvironment $StartInfo
if ($StartInfo.EnvironmentVariables['PIP_CONFIG_FILE'] -ne 'nul' -or $StartInfo.EnvironmentVariables.ContainsKey('UNREVIEWED_SECRET')) { throw 'Pip child environment isolation failed.' }
Write-Output 'PASS installer child disables config files and drops arbitrary inherited values'
$SetupText = $Ast.Extent.Text
$PreflightStart = $SetupText.IndexOf('$inputCode = Invoke-SetupPortableChild', [StringComparison]::Ordinal)
$PreflightEnd = $SetupText.IndexOf('$hasLock = $false', [StringComparison]::Ordinal)
if ($PreflightStart -lt 0 -or $PreflightEnd -le $PreflightStart) { throw 'Missing installer repair preflight.' }
foreach ($Call in @($Ast.FindAll({param($Node)
    $Node -is [Management.Automation.Language.CommandAst] -and $Node.GetCommandName() -eq 'Get-SetupPipArguments'
}, $true))) {
    if ($Call.Extent.StartOffset -lt $PreflightEnd) { throw 'Pip can be invoked before repair scope validation.' }
}
$script:RepairCalls = New-Object 'System.Collections.Generic.List[string]'
function Invoke-SetupPortableChild {
    param([string]$Executable, [object[]]$Arguments)
    if ($Arguments -contains 'validate-input') { $script:RepairCalls.Add('input'); return 0 }
    if ($Arguments -contains 'validate-runtime') { $script:RepairCalls.Add('runtime'); return 2 }
    throw 'Unexpected installer child reached during rejected repair.'
}
$PyExe = 'synthetic-python'; $LockHelper = 'synthetic-helper'; $RequirementsIn = $Requirements
$RepairRejected = $false
try {
    & ([scriptblock]::Create($SetupText.Substring($PreflightStart, $PreflightEnd - $PreflightStart)))
} catch {
    $RepairRejected = $_.Exception.Message -like '*No pip installation was started*'
}
if (-not $RepairRejected -or ($script:RepairCalls -join ',') -ne 'input,runtime') { throw 'Unsafe repair did not stop before pip.' }
Write-Output 'PASS rejected runtime scope stops actual setup preflight before any pip command'
$Fixture = Join-Path $Root ('tmp/python-setup-' + [Guid]::NewGuid().ToString('N'))
Assert-SetupPathAncestors $Fixture
[void][IO.Directory]::CreateDirectory($Fixture)
try {
    $Target = Join-Path $Fixture 'target'
    [void][IO.Directory]::CreateDirectory($Target)
    $Nested = Join-Path $Target 'nested'
    [void][IO.Directory]::CreateDirectory($Nested)
    Assert-SetupPathAncestors $Nested
    $Link = Join-Path $Fixture 'linked'
    $Kind = if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) { 'Junction' } else { 'SymbolicLink' }
    [void](New-Item -ItemType $Kind -Path $Link -Target $Target)
    $Rejected = $false
    try { Assert-SetupPathAncestors (Join-Path $Link 'nested/missing') } catch { $Rejected = $true }
    if (-not $Rejected) { throw 'Linked package ancestor was accepted.' }
    Write-Output 'PASS full ancestor chain rejects linked parents before setup marker access'
} finally {
    if (Test-Path -LiteralPath (Join-Path $Fixture 'linked')) { Remove-Item -LiteralPath (Join-Path $Fixture 'linked') -Force }
    Remove-Item -LiteralPath $Fixture -Recurse -Force
}
