#Requires -Version 5.1
# Execute production early-startup ordering with owned synthetic settings only.
$ErrorActionPreference = 'Stop'
$SourceRoot = Split-Path -Parent $PSScriptRoot
$Source = [IO.File]::ReadAllText((Join-Path $SourceRoot 'run-codex.ps1'))
$Tokens=$null; $Errors=$null
$Ast=[Management.Automation.Language.Parser]::ParseInput($Source,[ref]$Tokens,[ref]$Errors)
if ($Errors.Count) { throw 'Launcher must parse before migration testing.' }
foreach ($Name in @('Get-PersistableCodexExtensionToml','Initialize-PortableExtensionStore','Get-PortableExtensionCommandNamespace')) {
    $Defs=@($Ast.FindAll({param($Node) $Node -is [Management.Automation.Language.FunctionDefinitionAst]},$true)|Where-Object{$_.Name -ceq $Name})
    if ($Defs.Count -ne 1) { throw ('Expected one production function: ' + $Name) }
    . ([scriptblock]::Create($Defs[0].Extent.Text))
}
$Begin=$Source.IndexOf('$GeneratedConfigPath = Join-Path')
$End=$Source.IndexOf('# Windows /',$Begin)
if ($Begin -lt 0 -or $End -le $Begin) { throw 'Unexpected production startup section.' }
$Startup=[scriptblock]::Create($Source.Substring($Begin,$End-$Begin))
. (Join-Path $SourceRoot 'tool/automation/portable-automation.ps1')
[void](New-AutomationDirectory -Root $SourceRoot -Path (Join-Path $SourceRoot 'tmp'))
$Owned=New-AutomationDirectory -Root $SourceRoot -Path (Join-Path $SourceRoot ('tmp/extension-migration-test-'+[Guid]::NewGuid().ToString('N')))
$OldHome=$env:CODEX_HOME
$Utf8=New-Object Text.UTF8Encoding($false)
$Seed="[mcp_servers.saved]`ncommand = 'synthetic-never-executed'`n[plugins.'saved@local']`nenabled = false`n[features]`nplugins = true`n"
$script:Passed=0
function Check([bool]$Value,[string]$Message) { if (-not $Value) { throw $Message } }
function Rejected([scriptblock]$Body) { $Failed=$false; try { & $Body } catch { $Failed=$true }; Check $Failed 'Expected a rejected startup.' }
function Assert-PortablePath($Name,$Path) {
    [void](Assert-AutomationPath -Root $Root -Path $Path -Directory:([IO.Directory]::Exists($Path)) -MayNotExist)
    if ($script:FailStage -and $Name -eq 'extension migration staging') { throw 'Synthetic staging failure.' }
    if ($script:CommitCollision -and $Name -eq 'extension store commit') {
        [IO.File]::WriteAllText($Path,'SYNTHETIC CONCURRENT OWNER',$Utf8)
    }
}
function Assert-PortableRegularInputFile($Name,$Path) {
    [void](Assert-AutomationPath -Root $Root -Path $Path)
}
function Case([string]$Name,[scriptblock]$Body) {
    $Root=New-AutomationDirectory -Root $SourceRoot -Path (Join-Path $Owned ('case-'+$script:Passed))
    $FixtureHome=New-AutomationDirectory -Root $SourceRoot -Path (Join-Path $Root 'home')
    $Tmp=New-AutomationDirectory -Root $SourceRoot -Path (Join-Path $Root 'tmp')
    $env:CODEX_HOME=$FixtureHome
    $Config=Join-Path $FixtureHome 'config.toml'; $Store=Join-Path $FixtureHome 'portable-extensions.toml'
    $script:FailStage=$false; $script:CommitCollision=$false
    & $Body
    Check (@(Get-ChildItem -LiteralPath $Tmp -Force).Count -eq 0) 'Migration left staging material.'
    $script:Passed++
    Write-Output ('PASS '+$Name)
}
try {
    Case 'legacy settings are durable before a later command rejection' {
        [IO.File]::WriteAllText($Config,$Seed,$Utf8)
        . $Startup
        Check (-not (Test-Path -LiteralPath $Config)) 'Stale generated config was not removed.'
        $Saved=[IO.File]::ReadAllText($Store)
        Check ($Saved.Contains('[mcp_servers.saved]') -and $Saved.Contains('saved@local') -and -not $Saved.Contains('[features]')) 'Migration lost extensions or retained forbidden settings.'
        Rejected { $null=Get-PortableExtensionCommandNamespace -Command mcp -AllowedNamespaces @() }
        . $Startup
        Check ($PreservedExtensionToml -ceq $Saved) 'Retry lost migrated settings.'
        Check ([IO.File]::ReadAllText($Store) -ceq $Saved) 'Retry rewrote the persistent store.'
    }
    Case 'existing durable bytes win over stale generated settings' {
        $Saved="# keep user comment`r`n[plugins.'original@local']`r`nenabled = false`r`n"
        [IO.File]::WriteAllText($Store,$Saved,$Utf8)
        [IO.File]::WriteAllText($Config,$Seed,$Utf8)
        . $Startup
        Check ([IO.File]::ReadAllText($Store) -ceq $Saved) 'Startup rewrote durable bytes.'
        Check ($PreservedExtensionToml.Contains('original@local') -and -not $PreservedExtensionToml.Contains('[mcp_servers.saved]')) 'Stale settings overrode the sidecar.'
    }
    Case 'empty durable store prevents legacy resurrection' {
        [IO.File]::WriteAllText($Store,'',$Utf8)
        [IO.File]::WriteAllText($Config,$Seed,$Utf8)
        . $Startup
        Check ($PreservedExtensionToml -ceq '' -and (Get-Item -LiteralPath $Store).Length -eq 0) 'Deleted settings were resurrected.'
    }
    Case 'fresh and extension-free configurations need no store' {
        . $Startup
        Check (-not (Test-Path -LiteralPath $Store)) 'Fresh startup created unnecessary store.'
        [IO.File]::WriteAllText($Config,"model = 'synthetic'`n",$Utf8)
        . $Startup
        Check (-not (Test-Path -LiteralPath $Store) -and -not (Test-Path -LiteralPath $Config)) 'Extension-free startup failed.'
    }
    Case 'staging failure keeps the only source for retry' {
        [IO.File]::WriteAllText($Config,$Seed,$Utf8)
        $script:FailStage=$true
        Rejected { . $Startup }
        Check ([IO.File]::ReadAllText($Config) -ceq $Seed) 'Failure discarded legacy config.'
        Check (-not (Test-Path -LiteralPath $Store)) 'Failure created partial persistent data.'
    }
    Case 'commit collision preserves both original and new destination' {
        [IO.File]::WriteAllText($Config,$Seed,$Utf8)
        $script:CommitCollision=$true
        Rejected { . $Startup }
        Check ([IO.File]::ReadAllText($Config) -ceq $Seed) 'Commit failure removed the source.'
        Check ([IO.File]::ReadAllText($Store) -ceq 'SYNTHETIC CONCURRENT OWNER') 'Commit overwrote another destination.'
    }
    Case 'invalid store type is rejected without discarding legacy input' {
        [IO.File]::WriteAllText($Config,$Seed,$Utf8)
        [void][IO.Directory]::CreateDirectory($Store)
        Rejected { . $Startup }
        Check ([IO.File]::ReadAllText($Config) -ceq $Seed) 'Invalid store type discarded source.'
    }
    Case 'hardlinked legacy config is refused before migration' {
        $Target=Join-Path $FixtureHome 'synthetic-target.toml'
        [IO.File]::WriteAllText($Target,$Seed,$Utf8)
        [void](New-Item -ItemType HardLink -Path $Config -Target $Target)
        try {
            Rejected { . $Startup }
            Check (-not (Test-Path -LiteralPath $Store)) 'Linked source was migrated.'
            Check ([IO.File]::ReadAllText($Target) -ceq $Seed) 'Linked target changed.'
        } finally { [IO.File]::Delete($Config) }
    }
    Write-Output ("$script:Passed production legacy-extension migration groups passed; synthetic inputs only.")
} finally {
    $env:CODEX_HOME=$OldHome
    Remove-AutomationSession -Root $SourceRoot -Path $Owned
}
