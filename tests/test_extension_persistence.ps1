#Requires -Version 5.1
# Exercise production command parsing and write-back without real credentials.
$ErrorActionPreference = 'Stop'
$SourceRoot = Split-Path -Parent $PSScriptRoot
$LauncherPath = Join-Path $SourceRoot 'run-codex.ps1'
$Tokens = $null; $Errors = $null
$Ast = [Management.Automation.Language.Parser]::ParseFile($LauncherPath, [ref]$Tokens, [ref]$Errors)
if ($Errors.Count) { throw 'Launcher must parse before persistence testing.' }
foreach ($Name in @('Get-PersistableCodexExtensionToml', 'Get-PortableExtensionCommandNamespace',
        'Save-PortableExtensionCommandResult', 'Test-AndNormalizeCodexCliArgs')) {
    $Defs = @($Ast.FindAll({ param($Node) $Node -is [Management.Automation.Language.FunctionDefinitionAst] }, $true) | Where-Object { $_.Name -ceq $Name })
    if ($Defs.Count -ne 1) { throw ('Expected one production function: ' + $Name) }
    . ([scriptblock]::Create($Defs[0].Extent.Text))
}
$Scratch = Join-Path $SourceRoot 'tmp'
$Cursor = [IO.Path]::GetFullPath($Scratch)
while ($Cursor) {
    $Item = Get-Item -LiteralPath $Cursor -Force -ErrorAction SilentlyContinue
    if ($null -ne $Item -and (-not $Item.PSIsContainer -or ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint))) { throw 'Unsafe fixture ancestor.' }
    $Cursor = Split-Path -Parent $Cursor
}
$null = New-Item -ItemType Directory -Path $Scratch -Force
$Fixture = Join-Path $Scratch ('extension-persistence-' + [Guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $Fixture
$ConfigPath = Join-Path $Fixture 'generated.toml'
$ExtensionStorePath = Join-Path $Fixture 'saved.toml'
# Only path/atomic-IO boundaries are substituted; the production transformation,
# CLI parser and lifecycle condition are exercised directly on owned text files.
function Assert-PortableRegularInputFile($Label, $Path) {
    if ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Path)) -cne $Fixture) { throw 'Non-fixture path access.' }
    $Item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if ($null -ne $Item -and ($Item.PSIsContainer -or ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint))) { throw 'Unsafe fixture file.' }
}
function Write-Utf8TextAtomic($Path, $Text) {
    Assert-PortableRegularInputFile 'output' $Path
    $script:Writes++
    [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding($false)))
}
function Stop-UnsafeCodexCliArgument($Argument, $Reason) { throw ('Expected policy rejection: ' + $Reason) }
function Check([bool]$Condition, [string]$Reason) { if (-not $Condition) { throw $Reason } }
function Case([string]$Name, [scriptblock]$Body) { & $Body; $script:Passed++; Write-Output ('PASS ' + $Name) }
function Rejected([scriptblock]$Body) { $Thrown=$false; try { & $Body } catch { $Thrown=$true }; Check $Thrown 'Expected rejection.' }
function Seed {
    [IO.File]::WriteAllText($ExtensionStorePath, $SeedText)
    [IO.File]::WriteAllText($ConfigPath, $SeedText)
    $script:Writes=0
}
function Save([string]$Command, [string[]]$Active) {
    Save-PortableExtensionCommandResult -ConfigPath $ConfigPath -StorePath $ExtensionStorePath -Command $Command -AllowedNamespaces $Active
}
function Parse([string]$Command) {
    $List=New-Object 'System.Collections.Generic.List[string]'
    $List.Add($Command); $List.Add('list')
    $null=Test-AndNormalizeCodexCliArgs -InputArgs $List
}
$SeedText = @'
# Synthetic only: never execute these entries.
[mcp_servers.existing]
command = "synthetic-not-executed"
[plugins."saved@local"]
enabled = false
'@
$script:Passed=0; $script:Writes=0
try {
    Case 'inactive maintenance commands reject before touching saved configuration' {
        Seed
        $PortableMaintenanceMode=$true
        $PortableExtensionPolicy=[pscustomobject]@{AllowedNamespaces=[string[]]@()}
        foreach($Command in @('mcp','plugin')) { Rejected { Parse $Command } }
        Check ($script:Writes -eq 0) 'Disabled command wrote settings.'
        Check ([IO.File]::ReadAllText($ExtensionStorePath) -ceq $SeedText) 'Disabled command lost saved settings.'
    }
    Case 'each management command requires its own explicitly active namespace' {
        $PortableMaintenanceMode=$true
        foreach($Pair in @(@{Command='mcp'; Namespace='mcp_servers'; Other='plugin'},@{Command='plugin'; Namespace='plugins'; Other='mcp'})) {
            $PortableExtensionPolicy=[pscustomobject]@{AllowedNamespaces=[string[]]@($Pair.Namespace)}
            Parse $Pair.Command
            Rejected { Parse $Pair.Other }
        }
    }
    Case 'ordinary mode still refuses configuration management when extensions are active' {
        $PortableMaintenanceMode=$false
        $PortableExtensionPolicy=[pscustomobject]@{AllowedNamespaces=[string[]]@('mcp_servers','plugins')}
        foreach($Command in @('mcp','plugin')) { Rejected { Parse $Command } }
    }
    Case 'MCP edits preserve inactive plugins and filter unsafe namespaces' {
        foreach($Active in @(@('mcp_servers'),@('mcp_servers','plugins'))) {
            Seed
            $Plugins=Get-PersistableCodexExtensionToml -Path $ExtensionStorePath -AllowedNamespaces @('plugins')
            [IO.File]::WriteAllText($ConfigPath,"[mcp_servers.changed]`ncommand = 'new-synthetic'`n[features]`nplugins = true`n[plugins.injected]`nenabled = true`n")
            Save 'mcp' $Active
            Check ((Get-PersistableCodexExtensionToml -Path $ExtensionStorePath -AllowedNamespaces @('plugins')) -ceq $Plugins) 'MCP write-back lost or modified plugins.'
            $Text=[IO.File]::ReadAllText($ExtensionStorePath)
            Check ($Text.Contains('[mcp_servers.changed]') -and -not $Text.Contains('[features]') -and -not $Text.Contains('[plugins.injected]')) 'Write-back imported an unrelated namespace.'
        }
    }
    Case 'plugin edits preserve stored MCP regardless of its activation state' {
        foreach($Active in @(@('plugins'),@('plugins','mcp_servers'))) {
            Seed
            $Mcp=Get-PersistableCodexExtensionToml -Path $ExtensionStorePath -AllowedNamespaces @('mcp_servers')
            [IO.File]::WriteAllText($ConfigPath,"[plugins.changed]`nenabled = true`n")
            Save 'plugin' $Active
            Check ((Get-PersistableCodexExtensionToml -Path $ExtensionStorePath -AllowedNamespaces @('mcp_servers')) -ceq $Mcp) 'Plugin write-back lost or modified MCP.'
        }
    }
    Case 'read-only extension commands leave sidecar bytes and ordering unchanged' {
        foreach($Command in @('mcp','plugin')) {
            Seed
            Save $Command @('mcp_servers','plugins')
            Check ($script:Writes -eq 0) 'Read-only command rewrote the sidecar.'
            Check ([IO.File]::ReadAllText($ExtensionStorePath) -ceq $SeedText) 'Read-only command altered sidecar bytes.'
        }
    }
    Case 'removing the final entry does not resurrect it or remove the other namespace' {
        foreach($Pair in @(@{Command='mcp'; Namespace='mcp_servers'; Other='plugins'},@{Command='plugin'; Namespace='plugins'; Other='mcp_servers'})) {
            Seed
            $Retained=Get-PersistableCodexExtensionToml -Path $ExtensionStorePath -AllowedNamespaces @($Pair.Other)
            [IO.File]::WriteAllText($ConfigPath,"model = 'synthetic'`n")
            Save $Pair.Command @($Pair.Namespace)
            Check ((Get-PersistableCodexExtensionToml -Path $ExtensionStorePath -AllowedNamespaces @($Pair.Namespace)) -ceq '') 'Deleted namespace was resurrected.'
            Check ([IO.File]::ReadAllText($ExtensionStorePath) -ceq $Retained) 'Deleting final entry lost the other namespace.'
        }
    }
    Case 'missing generated config never clears persistent settings' {
        Seed
        Remove-Item -LiteralPath $ConfigPath
        Rejected { Save 'mcp' @('mcp_servers') }
        Check ($script:Writes -eq 0 -and [IO.File]::ReadAllText($ExtensionStorePath) -ceq $SeedText) 'Missing config cleared the sidecar.'
    }
    Case 'write-back independently refuses an inactive namespace' {
        Seed
        Rejected { Save 'mcp' @('plugins') }
        Rejected { Save 'plugin' @('mcp_servers') }
        Check ($script:Writes -eq 0) 'Inactive write-back changed persistent settings.'
    }
    Case 'lifecycle persists only successful maintenance extension commands' {
        $Blocks=@($Ast.FindAll({param($Node) $Node -is [Management.Automation.Language.IfStatementAst] -and $Node.Extent.Text.Contains('Save-PortableExtensionCommandResult -ConfigPath')},$true))
        Check ($Blocks.Count -eq 1) 'Expected one production lifecycle gate.'
        $Block=[scriptblock]::Create($Blocks[0].Extent.Text)
        foreach($State in @(@{Exit=1; Maintenance=$true; Command='mcp'},@{Exit=0; Maintenance=$false; Command='mcp'},@{Exit=0; Maintenance=$true; Command='exec'},@{Exit=0; Maintenance=$true; Command='mcp'})) {
            Seed
            [IO.File]::WriteAllText($ConfigPath,"[mcp_servers.changed]`ncommand = 'new-synthetic'`n")
            $script:CodexProcessExitCode=$State.Exit; $PortableMaintenanceMode=$State.Maintenance; $script:CodexRootCommand=$State.Command
            $PortableExtensionPolicy=[pscustomobject]@{AllowedNamespaces=[string[]]@('mcp_servers')}
            . $Block
            $ExpectedWrites=if($State.Exit -eq 0 -and $State.Maintenance -and $State.Command -eq 'mcp'){1}else{0}
            Check ($script:Writes -eq $ExpectedWrites) 'Lifecycle write-back condition changed.'
        }
    }
    Write-Output ("$script:Passed extension-persistence regression groups passed; synthetic inputs only.")
} finally {
    Remove-Item -LiteralPath $Fixture -Recurse -Force
}
