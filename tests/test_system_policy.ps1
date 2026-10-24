#Requires -Version 5.1
# Synthetic registry boundary only: never read or change actual machine policy.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Tokens = $null
$ParseErrors = $null
$LauncherAst = [Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $Root 'run-codex.ps1'), [ref]$Tokens, [ref]$ParseErrors)
if ($ParseErrors.Count) { throw 'Launcher parse failed.' }
$Functions = @{}
foreach ($Name in @('Open-CodexSystemPolicyRegistryKey',
        'Test-CodexSystemRequirementsRegistryPolicy',
        'Assert-CodexSystemRequirementsRegistryPolicy')) {
    $Definitions = @($LauncherAst.FindAll({
        param($Node)
        $Node -is [Management.Automation.Language.FunctionDefinitionAst]
    }, $true) | Where-Object { $_.Name -ceq $Name })
    if ($Definitions.Count -ne 1) { throw "Expected one production definition of $Name" }
    $Functions[$Name] = $Definitions[0].Extent.Text
    # Do not import the real OS boundary, even on Windows.
    if ($Name -ne 'Open-CodexSystemPolicyRegistryKey') {
        . ([scriptblock]::Create($Definitions[0].Extent.Text))
    }
}

function Assert-True {
    param([bool]$Condition, [string]$Because)
    if (-not $Condition) { throw $Because }
}
function Assert-Rejected {
    param([scriptblock]$Body, [string]$ExpectedMessage)
    $Caught = $null
    try { & $Body } catch { $Caught = $_.Exception.Message }
    Assert-True ($null -ne $Caught) 'Expected policy rejection.'
    Assert-True ($Caught -like ('*' + $ExpectedMessage + '*')) "Unexpected error: $Caught"
}
function Test-Case {
    param([string]$Name, [scriptblock]$Body)
    $script:OpenCalls = 0
    $script:OpenError = $false
    $script:PolicyKey = $null
    & $Body
    $script:Passed++
    Write-Output "PASS $Name"
}
function New-FakePolicyKey {
    param([string[]]$ValueNames = @(), [bool]$EnumerationError = $false)
    $Key = [pscustomobject]@{
        ValueNames = $ValueNames
        EnumerationError = $EnumerationError
        NamesRead = 0
        ValuesRead = 0
        Disposed = 0
    }
    $Key | Add-Member -MemberType ScriptMethod -Name GetValueNames -Value {
        $this.NamesRead++
        if ($this.EnumerationError) { throw 'Synthetic registry enumeration denied.' }
        return $this.ValueNames
    }
    $Key | Add-Member -MemberType ScriptMethod -Name GetValue -Value {
        $this.ValuesRead++
        throw 'Policy data/target must never be read by the portable preflight.'
    }
    $Key | Add-Member -MemberType ScriptMethod -Name Dispose -Value { $this.Disposed++ }
    return $Key
}
function Open-CodexSystemPolicyRegistryKey {
    $script:OpenCalls++
    if ($script:OpenError) { throw 'Synthetic registry open denied.' }
    return $script:PolicyKey
}

$script:Passed = 0
Test-Case 'OS boundary is fixed to read-only 64-bit HKLM policy' {
    $NativeSource = $Functions['Open-CodexSystemPolicyRegistryKey']
    Assert-True ($NativeSource -match '\[Microsoft\.Win32\.RegistryHive\]::LocalMachine') 'Machine policy hive required.'
    Assert-True ($NativeSource -match '\[Microsoft\.Win32\.RegistryView\]::Registry64') 'Must match the upstream 64-bit policy view.'
    Assert-True ($NativeSource -match "OpenSubKey\('SOFTWARE\\Policies\\OpenAI\\Codex', \`$false\)") 'Only the fixed key may be opened, read-only.'
    Assert-True ($NativeSource -notmatch 'GetValue|CreateSubKey|SetValue|Delete') 'The OS boundary must not access values or mutate policy.'
    Assert-True ($NativeSource -match 'finally\s*\{[\s\S]*\$baseKey\.Dispose\(\)') 'Base key must always be disposed.'
    Assert-True ($script:OpenCalls -eq 0) 'Static boundary inspection must not open the registry.'
}
Test-Case 'missing policy key allows normal portable startup' {
    Assert-CodexSystemRequirementsRegistryPolicy
    Assert-True ($script:OpenCalls -eq 1) 'The fixed policy key must be probed once.'
}
Test-Case 'unrelated value names do not block startup' {
    foreach ($Names in @(@(), @('', 'OtherPolicy', 'RequirementsPathBackup'))) {
        $script:PolicyKey = New-FakePolicyKey -ValueNames $Names
        Assert-CodexSystemRequirementsRegistryPolicy
        Assert-True ($script:PolicyKey.NamesRead -eq 1) 'Only value names are needed.'
        Assert-True ($script:PolicyKey.ValuesRead -eq 0) 'No value data may be read.'
        Assert-True ($script:PolicyKey.Disposed -eq 1) 'Policy key must be disposed.'
    }
}
Test-Case 'policy presence rejects before reading its data or target' {
    foreach ($Name in @('RequirementsPath', 'requirementspath', 'REQUIREMENTSPATH')) {
        $script:PolicyKey = New-FakePolicyKey -ValueNames @('OtherPolicy', $Name)
        Assert-Rejected { Assert-CodexSystemRequirementsRegistryPolicy } 'CODEX_ALLOW_HOST_SYSTEM_CONFIG'
        Assert-True ($script:PolicyKey.NamesRead -eq 1) 'Presence must be determined from names.'
        Assert-True ($script:PolicyKey.ValuesRead -eq 0) 'Even invalid or package-local policy targets require explicit authorization.'
        Assert-True ($script:PolicyKey.Disposed -eq 1) 'Rejected policy key must be disposed.'
    }
}
Test-Case 'explicit host policy authorization preserves existing behavior' {
    $script:PolicyKey = New-FakePolicyKey -ValueNames @('RequirementsPath')
    Assert-CodexSystemRequirementsRegistryPolicy -AllowHostSystemConfig $true
    Assert-True ($script:OpenCalls -eq 0) 'Authorized policy loading is left to Codex without extra probing.'
    Assert-True ($script:PolicyKey.ValuesRead -eq 0) 'The launcher never reads authorized policy contents.'
}
Test-Case 'policy key access failure fails closed' {
    $script:OpenError = $true
    Assert-Rejected { Assert-CodexSystemRequirementsRegistryPolicy } 'Synthetic registry open denied.'
    Assert-True ($script:OpenCalls -eq 1) 'A failed check must not retry or fall back.'
}
Test-Case 'policy enumeration failure fails closed and releases its handle' {
    $script:PolicyKey = New-FakePolicyKey -EnumerationError $true
    Assert-Rejected { Assert-CodexSystemRequirementsRegistryPolicy } 'Synthetic registry enumeration denied.'
    Assert-True ($script:PolicyKey.ValuesRead -eq 0) 'Failed enumeration must not fall back to reading a value.'
    Assert-True ($script:PolicyKey.Disposed -eq 1) 'Failed enumeration must release the policy key.'
}
Test-Case 'launcher invokes the policy gate before native client entry points' {
    $Commands = @($LauncherAst.FindAll({
        param($Node)
        $Node -is [Management.Automation.Language.CommandAst]
    }, $true) | Where-Object {
        $Ancestor = $_.Parent
        while ($null -ne $Ancestor -and $Ancestor -isnot [Management.Automation.Language.FunctionDefinitionAst]) {
            $Ancestor = $Ancestor.Parent
        }
        $null -eq $Ancestor
    })
    $Gate = @($Commands | Where-Object { $_.GetCommandName() -eq 'Assert-CodexSystemRequirementsRegistryPolicy' })
    Assert-True ($Gate.Count -eq 1) 'One real startup gate is required.'
    Assert-True ($Gate[0].Extent.Text -match '-AllowHostSystemConfig \$allowHostSystemConfig') 'Existing explicit authorization must reach the gate.'
    $NativeCalls = @($Commands | Where-Object { $_.GetCommandName() -match '^(Invoke-CodexChild|Invoke-CodexOfficialAccountLogin)' })
    Assert-True ($NativeCalls.Count -gt 0) 'Expected actual launcher client entry points.'
    foreach ($Call in $NativeCalls) {
        Assert-True ($Gate[0].Extent.StartOffset -lt $Call.Extent.StartOffset) 'Registry policy must be checked before starting Codex.'
    }
}
Write-Output "$script:Passed system policy tests passed; no real registry or policy target was accessed."
