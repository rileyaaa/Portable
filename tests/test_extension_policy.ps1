#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$LauncherPath = Join-Path $Root 'run-codex.ps1'
$LauncherSource = [System.IO.File]::ReadAllText($LauncherPath)
$Tokens = $null
$ParseErrors = $null
$LauncherAst = [System.Management.Automation.Language.Parser]::ParseFile(
    $LauncherPath, [ref]$Tokens, [ref]$ParseErrors
)
if ($ParseErrors.Count -gt 0) { throw "Launcher parse failed: $($ParseErrors[0].Message)" }

# Import actual production functions, without executing the Windows launcher or
# reading package credentials/configuration. Only synthetic fixtures are used.
foreach ($Name in @('Convert-ToTomlBool', 'Convert-ToFeatureBool',
        'Get-PortableExtensionPolicy', 'Get-PersistableCodexExtensionToml',
        'Get-RuntimeModelIdentityInstructions', 'New-RuntimeModelInstructions',
        'Convert-ToTomlString')) {
    $Definitions = @($LauncherAst.FindAll({
        param($Node)
        $Node -is [System.Management.Automation.Language.FunctionDefinitionAst]
    }, $true) | Where-Object { $_.Name -eq $Name })
    if ($Definitions.Count -ne 1) { throw "Expected one definition of $Name" }
    . ([scriptblock]::Create($Definitions[0].Extent.Text))
}

function Get-Assignment {
    param([string]$Variable)
    $Matches = @($LauncherAst.FindAll({
        param($Node)
        $Node -is [System.Management.Automation.Language.AssignmentStatementAst]
    }, $true) | Where-Object { $_.Left.Extent.Text -ceq ('$' + $Variable) })
    if ($Matches.Count -ne 1) { throw "Expected one assignment for $Variable" }
    return $Matches[0]
}

function Assert-True {
    param([bool]$Condition, [string]$Because)
    if (-not $Condition) { throw $Because }
}

function Assert-Equal {
    param($Actual, $Expected, [string]$Because)
    if ($Actual -cne $Expected) { throw "$Because -- expected '$Expected', got '$Actual'" }
}

function Test-Case {
    param([string]$Name, [scriptblock]$Body)
    & $Body
    $script:Passed += 1
    Write-Output "PASS $Name"
}

# Exercise the real command-line scan, including the -- terminator. Its extent
# ends before authentication, cache setup, or any client/device process can run.
$OptionStart = @($LauncherAst.FindAll({
    param($Node)
    $Node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
    $Node.Left.Extent.Text -ceq '$PortableMaintenanceMode' -and
    $Node.Right.Extent.Text -ceq '$false'
}, $true))
if ($OptionStart.Count -ne 1) { throw 'Expected one initial maintenance-mode assignment' }
$OptionEnd = Get-Assignment 'AllowUserMcp'
$OptionSource = $LauncherSource.Substring($OptionStart[0].Extent.StartOffset,
    $OptionEnd.Extent.EndOffset - $OptionStart[0].Extent.StartOffset)
$OptionScript = [scriptblock]::Create($OptionSource + @'

[pscustomobject]@{
    Maintenance = $PortableMaintenanceMode
    Policy = $PortableExtensionPolicy
    Arguments = @($CodexLaunchArgs.ToArray())
    AuthMode = $ConfiguredAuthMode
}
'@)

function Invoke-OptionPolicy {
    param([string[]]$Arguments = @(), [string]$Plugins = '', [string]$Mcp = '')
    $OldPlugins = $env:CODEX_ENABLE_PLUGINS
    $OldMcp = $env:CODEX_PORTABLE_ALLOW_USER_MCP
    try {
        $env:CODEX_ENABLE_PLUGINS = $Plugins
        $env:CODEX_PORTABLE_ALLOW_USER_MCP = $Mcp
        $ConfiguredAuthMode = 'menu'
        $PortableMaintenanceEntryAuthorized = $true
        return & $OptionScript @Arguments
    } finally {
        $env:CODEX_ENABLE_PLUGINS = $OldPlugins
        $env:CODEX_PORTABLE_ALLOW_USER_MCP = $OldMcp
    }
}

$FixtureBase = Join-Path $Root 'tmp'
$FixtureAncestor = $FixtureBase
while (-not [string]::IsNullOrWhiteSpace($FixtureAncestor)) {
    $FixtureItem = Get-Item -LiteralPath $FixtureAncestor -Force -ErrorAction SilentlyContinue
    if ($null -ne $FixtureItem -and (
        -not $FixtureItem.PSIsContainer -or
        ($FixtureItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)) {
        throw "Unsafe test fixture directory: $FixtureAncestor"
    }
    $FixtureAncestor = Split-Path -Parent $FixtureAncestor
}
$null = New-Item -ItemType Directory -Path $FixtureBase -Force
$FixtureRoot = Join-Path $FixtureBase ('extension-policy-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $FixtureRoot

# Replace only the file boundary; path/reparse/hard-link behavior has separate
# launcher regressions. Every file read or written here is an owned fixture.
function Assert-FixtureFile {
    param([string]$Path)
    if ([System.IO.Path]::GetDirectoryName([System.IO.Path]::GetFullPath($Path)) -cne $FixtureRoot) {
        throw "Attempted non-fixture access: $Path"
    }
    $Item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if ($null -ne $Item -and ($Item.PSIsContainer -or
        ($Item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)) {
        throw "Unsafe fixture file: $Path"
    }
}
function Assert-PortableRegularInputFile {
    param([string]$Label, [string]$Path)
    Assert-FixtureFile $Path
}
function Write-Utf8TextAtomic {
    param([string]$Path, [string]$Text)
    Assert-FixtureFile $Path
    [System.IO.File]::WriteAllText($Path, $Text, (New-Object System.Text.UTF8Encoding($false)))
}

$script:Passed = 0
try {
    Test-Case 'fast, plugins and user MCP ship disabled' {
        $EnvTokens = $null
        $EnvErrors = $null
        $EnvAst = [System.Management.Automation.Language.Parser]::ParseFile(
            (Join-Path $Root 'env.ps1'), [ref]$EnvTokens, [ref]$EnvErrors
        )
        Assert-Equal $EnvErrors.Count 0 'env.ps1 must parse'
        foreach ($Setting in @('CODEX_FAST_MODE', 'CODEX_ENABLE_PLUGINS', 'CODEX_PORTABLE_ALLOW_USER_MCP')) {
            $Assignments = @($EnvAst.FindAll({
                param($Node)
                $Node -is [System.Management.Automation.Language.AssignmentStatementAst]
            }, $true) | Where-Object { $_.Left.Extent.Text -ceq ('$env:' + $Setting) })
            Assert-Equal $Assignments.Count 1 "one default for $Setting"
            Assert-Equal $Assignments[0].Right.Extent.Text '"false"' "$Setting must default off"
        }
    }
    Test-Case 'generated TOML disables supported voice flags and unbinds voice hotkeys' {
        $StartMarker = '[void]$Builder.AppendLine("[features]")'
        $EndMarker = '[void]$Builder.AppendLine("[analytics]")'
        $StartOffset = $LauncherSource.IndexOf($StartMarker, [StringComparison]::Ordinal)
        $EndOffset = $LauncherSource.IndexOf($EndMarker, $StartOffset, [StringComparison]::Ordinal)
        Assert-True ($StartOffset -ge 0 -and $EndOffset -gt $StartOffset) 'feature generation block must exist'
        $FeatureScript = [scriptblock]::Create($LauncherSource.Substring($StartOffset, $EndOffset - $StartOffset))
        foreach ($ExtensionsEnabled in @($false, $true)) {
            $Builder = New-Object Text.StringBuilder
            $ModelAllowsImage = $true
            $FastModeEnabled = $false
            $DisableApps = $true
            $EnablePlugins = $ExtensionsEnabled
            $EnablePluginSharing = $false
            . $FeatureScript
            $Generated = $Builder.ToString()
            foreach ($Feature in @('in_app_voice','in_app_dictation')) {
                Assert-True ($Generated -match ('(?m)^' + $Feature + ' = false\r?$')) "$Feature must stay disabled"
            }
            Assert-True ($Generated -notmatch '(?m)^realtime_conversation\s*=') 'removed feature must not be emitted as a working restriction'
            Assert-True ($Generated -match '(?ms)^\[tui\.keymap\.chat\]\r?\ntoggle_voice = \[\]\r?\ntoggle_voice_mute = \[\]\r?$') 'voice hotkeys must be explicitly unbound in the correct TOML table'
            Assert-True ($Generated -match '(?m)^resume_cwd = "current"\r?$') 'existing TUI configuration must remain present'
            Assert-True ($Generated -match '(?m)^fast_mode = false\r?$') 'voice restriction must preserve Fast default'
            Assert-True ($Generated -match ('(?m)^plugins = ' + $ExtensionsEnabled.ToString().ToLowerInvariant() + '\r?$')) 'voice restriction must preserve explicit plugin behavior'
        }
    }
    Test-Case 'missing values and explicit session flag both default off' {
        foreach ($Arguments in @(@(), @('--portable-extensions'))) {
            $Result = Invoke-OptionPolicy -Arguments $Arguments
            Assert-True (-not $Result.Policy.PluginsEnabled) 'plugins require a configured true value'
            Assert-True (-not $Result.Policy.UserMcpEnabled) 'MCP requires a configured true value'
            Assert-Equal $Result.Policy.AllowedNamespaces.Count 0 'no namespaces allowed by default'
        }
    }
    Test-Case 'old true settings cannot activate extensions on their own' {
        $Result = Invoke-OptionPolicy -Plugins 'true' -Mcp 'true'
        Assert-True (-not $Result.Policy.PluginsEnabled) 'persisted plugin true is insufficient'
        Assert-True (-not $Result.Policy.UserMcpEnabled) 'persisted MCP true is insufficient'
    }
    Test-Case 'maintenance mode does not grant extension activation' {
        $Result = Invoke-OptionPolicy -Arguments @('--portable-maintenance') -Plugins 'true' -Mcp 'true'
        Assert-True $Result.Maintenance 'actual maintenance flag must be consumed'
        Assert-True (-not $Result.Policy.PluginsEnabled) 'maintenance must not enable plugins'
        Assert-True (-not $Result.Policy.UserMcpEnabled) 'maintenance must not enable MCP'
        Assert-Equal $Result.Arguments.Count 0 'private flag must not reach the official CLI'
    }
    Test-Case 'session confirmation activates only the configured namespace' {
        $Plugins = Invoke-OptionPolicy -Arguments @('--portable-extensions', '--portable-auth=api', 'exec', 'fixture') -Plugins 'yes' -Mcp 'false'
        Assert-Equal ($Plugins.Policy.AllowedNamespaces -join ',') 'plugins' 'plugin-only activation'
        Assert-Equal ($Plugins.Arguments -join ',') 'exec,fixture' 'private flags must be consumed'
        Assert-Equal $Plugins.AuthMode 'api' 'existing private auth flag must still work'
        $Mcp = Invoke-OptionPolicy -Arguments @('--portable-extensions') -Plugins 'off' -Mcp '1'
        Assert-Equal ($Mcp.Policy.AllowedNamespaces -join ',') 'mcp_servers' 'MCP-only activation'
        $Both = Invoke-OptionPolicy -Arguments @('--portable-maintenance', '--portable-extensions') -Plugins 'on' -Mcp 'true'
        Assert-Equal ($Both.Policy.AllowedNamespaces -join ',') 'plugins,mcp_servers' 'both require explicit session confirmation'
    }
    Test-Case 'argument terminator prevents accidental extension activation' {
        $Result = Invoke-OptionPolicy -Arguments @('--', '--portable-extensions') -Plugins 'true' -Mcp 'true'
        Assert-True (-not $Result.Policy.TaskRequested) 'literal prompt argument must not activate extensions'
        Assert-Equal ($Result.Arguments -join ',') '--,--portable-extensions' 'terminated arguments are forwarded literally'
    }
    Test-Case 'invalid booleans are rejected even when extensions are inactive' {
        foreach ($TaskRequested in @($false, $true)) {
            foreach ($InvalidKey in @('PluginsValue', 'UserMcpValue')) {
                $Arguments = @{ TaskRequested = $TaskRequested; PluginsValue = 'false'; UserMcpValue = 'false' }
                $Arguments[$InvalidKey] = 'sometimes'
                $Threw = $false
                try { $null = Get-PortableExtensionPolicy @Arguments } catch { $Threw = $true }
                Assert-True $Threw "$InvalidKey must reject an invalid value"
            }
        }
    }
    Test-Case 'plugin sharing cannot remain enabled when plugins are inactive' {
        $PluginFlags = [scriptblock]::Create(
            (Get-Assignment 'EnablePlugins').Extent.Text + [Environment]::NewLine +
            (Get-Assignment 'EnablePluginSharing').Extent.Text + [Environment]::NewLine +
            '[pscustomobject]@{ Plugins = $EnablePlugins; Sharing = $EnablePluginSharing }'
        )
        $OldSharing = $env:CODEX_ENABLE_PLUGIN_SHARING
        try {
            $env:CODEX_ENABLE_PLUGIN_SHARING = 'true'
            $PortableExtensionPolicy = Get-PortableExtensionPolicy
            $Flags = & $PluginFlags
            Assert-True (-not $Flags.Plugins -and -not $Flags.Sharing) 'sharing requires active plugins'
            $PortableExtensionPolicy = Get-PortableExtensionPolicy -TaskRequested $true -PluginsValue 'true'
            $Flags = & $PluginFlags
            Assert-True ($Flags.Plugins -and $Flags.Sharing) 'explicitly configured sharing remains available'
        } finally { $env:CODEX_ENABLE_PLUGIN_SHARING = $OldSharing }
    }

    $ExtensionSourcePath = Join-Path $FixtureRoot 'source.toml'
    $ExtensionStorePath = Join-Path $FixtureRoot 'stored.toml'
    $SourceText = @'
model = "fixture-model"
[mcp_servers.fixture]
command = "fixture-only-no-process"
note = """
[plugins.not_a_table]
"""
[mcp_servers.fixture.env]
FIXTURE = "test"
[plugins."fixture#one"]
enabled = true
[plugins."fixture#one".settings]
description = "fixture"
[sandbox_workspace_write]
writable_roots = ["/outside"]
["features"]
plugins = true
'@
    Write-Utf8TextAtomic -Path $ExtensionSourcePath -Text $SourceText
    $SourceHash = (Get-FileHash -LiteralPath $ExtensionSourcePath -Algorithm SHA256).Hash
    $PersistStart = @($LauncherAst.FindAll({
        param($Node)
        $Node -is [System.Management.Automation.Language.IfStatementAst] -and
        $Node.Extent.Text.StartsWith('if (-not [string]::IsNullOrWhiteSpace($PreservedExtensionToml)) {')
    }, $true))
    if ($PersistStart.Count -ne 1) { throw 'Expected one extension persistence block' }
    $PersistEnd = Get-Assignment 'EffectiveExtensionToml'
    $PersistScript = [scriptblock]::Create(
        $LauncherSource.Substring($PersistStart[0].Extent.StartOffset,
            $PersistEnd.Extent.EndOffset - $PersistStart[0].Extent.StartOffset) +
        [Environment]::NewLine + '$EffectiveExtensionToml'
    )
    Test-Case 'generated config filters namespaces while retaining full extension storage' {
        $PreservedExtensionToml = Get-PersistableCodexExtensionToml -Path $ExtensionSourcePath
        Assert-True ($PreservedExtensionToml.Contains('[mcp_servers.fixture]')) 'MCP config remains persistent'
        Assert-True ($PreservedExtensionToml.Contains('[plugins."fixture#one"]')) 'plugin config remains persistent'
        Assert-True (-not $PreservedExtensionToml.Contains('writable_roots')) 'security namespace cannot be inherited'
        Assert-True (-not $PreservedExtensionToml.Contains('["features"]')) 'feature namespace cannot be inherited'
        foreach ($Case in @(
            @{ Task = $false; Plugins = 'true'; Mcp = 'true'; ExpectPlugins = $false; ExpectMcp = $false },
            @{ Task = $true; Plugins = 'true'; Mcp = 'false'; ExpectPlugins = $true; ExpectMcp = $false },
            @{ Task = $true; Plugins = 'false'; Mcp = 'true'; ExpectPlugins = $false; ExpectMcp = $true },
            @{ Task = $true; Plugins = 'true'; Mcp = 'true'; ExpectPlugins = $true; ExpectMcp = $true }
        )) {
            $PortableExtensionPolicy = Get-PortableExtensionPolicy -TaskRequested $Case.Task -PluginsValue $Case.Plugins -UserMcpValue $Case.Mcp
            $Effective = [string](& $PersistScript)
            Assert-Equal $Effective.Contains('[plugins."fixture#one"]') $Case.ExpectPlugins 'plugin namespace selection'
            Assert-Equal $Effective.Contains('[mcp_servers.fixture]') $Case.ExpectMcp 'MCP namespace selection'
            Assert-Equal ([System.IO.File]::ReadAllText($ExtensionStorePath)) $PreservedExtensionToml 'inactive extension configuration must not be lost'
        }
        Assert-Equal (Get-FileHash -LiteralPath $ExtensionSourcePath -Algorithm SHA256).Hash $SourceHash 'source configuration remains unchanged'
    }
    Test-Case 'default developer instructions contain the task activation policy' {
        $RuntimeModelIdentityInstructions = Get-RuntimeModelIdentityInstructions -ModelSlug 'fixture-model'
        $TomlRuntimeModelIdentityInstructions = Convert-ToTomlString $RuntimeModelIdentityInstructions.Trim()
        $InstructionBranches = @($LauncherAst.FindAll({
            param($Node)
            $Node -is [System.Management.Automation.Language.IfStatementAst] -and
            $Node.Extent.Text.StartsWith('if (-not [string]::IsNullOrWhiteSpace($ModelInstructionsFile)) {') -and
            $Node.Extent.Text.Contains('developer_instructions =')
        }, $true))
        Assert-Equal $InstructionBranches.Count 1 'one production instruction selection branch'
        $Builder = New-Object System.Text.StringBuilder
        $ModelInstructionsFile = ''
        . ([scriptblock]::Create($InstructionBranches[0].Extent.Text))
        $Generated = $Builder.ToString()
        Assert-True ($Generated.Contains('developer_instructions =')) 'default instruction entry must be emitted'
        Assert-True ($Generated.Contains('Task-Scoped Skill and Extension Activation')) 'default entry must include policy'
        Assert-True ($Generated.Contains('only when the user explicitly requests a relevant task')) 'explicit task requirement must be retained'
        Assert-True ($Generated.Contains('whole desktop')) 'selected-target boundary must be retained'
    }
    Test-Case 'custom model instructions include the same task activation policy' {
        $TemplatePath = Join-Path $FixtureRoot 'template.md'
        Write-Utf8TextAtomic -Path $TemplatePath -Text 'Synthetic custom instructions marker.'
        $OldCodexHome = $env:CODEX_HOME
        try {
            $env:CODEX_HOME = $FixtureRoot
            $GeneratedPath = New-RuntimeModelInstructions -OriginalPath $TemplatePath -ModelSlug 'fixture-model'
            Assert-FixtureFile $GeneratedPath
            $Generated = [System.IO.File]::ReadAllText($GeneratedPath)
            $CommonInstructions = (Get-RuntimeModelIdentityInstructions -ModelSlug 'fixture-model').Trim()
            Assert-True ($Generated.StartsWith($CommonInstructions)) 'custom entry must use the same policy prefix'
            Assert-True ($Generated.Contains('Synthetic custom instructions marker.')) 'custom user content remains present'
            Assert-True ($Generated.Contains('entering maintenance mode does not authorize')) 'maintenance must not imply tool authorization'
        } finally { $env:CODEX_HOME = $OldCodexHome }
    }
    Write-Output "$script:Passed extension-policy checks passed."
} finally {
    if (Test-Path -LiteralPath $FixtureRoot -PathType Container) {
        Remove-Item -LiteralPath $FixtureRoot -Recurse -Force
    }
}
