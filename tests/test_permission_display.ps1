#Requires -Version 5.1
# Evaluate only the production status expressions; no native client or credentials.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$source = [IO.File]::ReadAllText((Join-Path $root 'run-codex.ps1'))
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseInput($source, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Launcher must parse before permission-display checks.' }
$expressions = @{}
foreach ($name in @('WriteScopeDisplay', 'ShellNetworkDisplay')) {
    $left = '$' + $name
    $nodes = @($ast.FindAll({ param($node) $node -is [Management.Automation.Language.AssignmentStatementAst] }, $true) | Where-Object { $_.Left.Extent.Text -ceq $left })
    if ($nodes.Count -ne 1) { throw ('Expected exactly one production assignment: ' + $name) }
    $expressions[$name] = [scriptblock]::Create($nodes[0].Extent.Text)
}
if (-not $source.Contains('Write-Host "ShellNetwork  : $ShellNetworkDisplay"') -or
    -not $source.Contains(' + $WriteScopeDisplay)')) { throw 'Startup must display the evaluated policy summaries.' }
$count = 0
foreach ($SandboxMode in @('workspace-write', 'read-only', 'danger-full-access')) {
    foreach ($PortableMaintenanceMode in @($false, $true)) {
        foreach ($SandboxNetworkAccess in @('false', 'true')) {
            . $expressions['WriteScopeDisplay']
            . $expressions['ShellNetworkDisplay']
            if ($SandboxMode -eq 'danger-full-access') {
                if (-not $WriteScopeDisplay.StartsWith('YOLO ') -or
                    -not $ShellNetworkDisplay.StartsWith('unrestricted ') -or
                    $WriteScopeDisplay.Contains('SAFE') -or $ShellNetworkDisplay.StartsWith('false')) {
                    throw 'Disabled sandbox was incorrectly displayed as restricted.'
                }
            } elseif ($SandboxMode -eq 'read-only') {
                if (-not $WriteScopeDisplay.StartsWith('READ-ONLY ') -or
                    -not $ShellNetworkDisplay.StartsWith('policy ')) { throw 'Read-only mode inherited a workspace-write claim.' }
            } else {
                $expected = if ($PortableMaintenanceMode) { 'MAINTENANCE ' } else { 'SAFE ' }
                if (-not $WriteScopeDisplay.StartsWith($expected) -or
                    -not $ShellNetworkDisplay.StartsWith($SandboxNetworkAccess + ' ')) { throw 'Workspace-write status lost the selected scope or network policy.' }
            }
            $count++
            Write-Output ('PASS permission display: ' + $SandboxMode + ', maintenance=' + $PortableMaintenanceMode + ', workspace-network=' + $SandboxNetworkAccess)
        }
    }
}
Write-Output ($count.ToString() + ' production permission-display combinations passed (offline).')
