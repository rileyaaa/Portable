#Requires -Version 5.1
# Exercise exact production launcher option parsing and menu predicate. The
# interactive host flag is injected; no real authentication, process or output
# file is created. The path stub checks empty values and captures arguments.
param([string]$BaselineCommit = '')
$ErrorActionPreference = 'Stop'
$root=Split-Path -Parent $PSScriptRoot
$tokens=$null; $errors=$null
if ($BaselineCommit) {
    if ($BaselineCommit -notmatch '^[a-f0-9]{40}$') { throw 'Invalid baseline commit.' }
    $lines=& git -C $root show ($BaselineCommit+':run-codex.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Unable to read exact baseline.' }
    $source=$lines -join "`n"
} else {
    $source=[IO.File]::ReadAllText((Join-Path $root 'run-codex.ps1'))
}
$source=$source.Replace("`r`n","`n")
$ast=[Management.Automation.Language.Parser]::ParseInput($source,[ref]$tokens,[ref]$errors)
if ($errors.Count) {throw 'Launcher failed to parse.'}
$definitions=@($ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$true))
foreach ($name in @('Test-AndNormalizeCodexCliArgs','Get-PortableExtensionCommandNamespace')) {
    $nodes=@($definitions | Where-Object Name -eq $name)
    if ($nodes.Count -ne 1) {throw ('Expected one production definition: '+$name)}
    . ([scriptblock]::Create($nodes[0].Extent.Text))
}
$start=$source.IndexOf('$ConfiguredAuthMode = $env:CODEX_AUTH_MODE')
if ($start -lt 0) {throw 'Missing production option scan.'}
$end=$source.IndexOf('$PortableSessionState = $null',$start)
if ($start -lt 0 -or $end -le $start) {throw 'Missing production option scan.'}
$scan=[scriptblock]::Create($source.Substring($start,$end-$start))
$menuNodes=@($ast.FindAll({
    param($node)
    $node -is [Management.Automation.Language.AssignmentStatementAst] -and
        $node.Left.Extent.Text -ceq '$ShowStartupMenu'
},$true))
if ($menuNodes.Count -ne 1) {throw 'Missing production menu predicate.'}
$menu=[scriptblock]::Create($menuNodes[0].Extent.Text.Replace('[Environment]::UserInteractive','$SyntheticUserInteractive'))
function Assert-Case {param([bool]$Condition,[string]$Label) if (-not $Condition) {throw $Label}}
function Get-PortableExtensionPolicy {
    param([bool]$TaskRequested,[string]$PluginsValue,[string]$UserMcpValue)
    return [pscustomobject]@{UserMcpEnabled=$false;AllowedNamespaces=@()}
}
function Stop-UnsafeCodexCliArgument {param($Argument,$Reason) throw ('CLI_REJECT:'+ $Argument)}
function Resolve-PortableCliPath {
    param([string]$OptionName,[string]$Value,[bool]$MustExist)
    if ([string]::IsNullOrWhiteSpace($Value)) {Stop-UnsafeCodexCliArgument $OptionName 'Missing path'}
    $script:PathValues += $Value
    return ('RESOLVED:'+ $Value)
}
function Get-LaunchState {
    param([string[]]$Arguments,[string]$DefaultMode='menu',[bool]$Interactive=$true,[bool]$HostInteractive=$true)
    $env:CODEX_AUTH_MODE=$DefaultMode
    $PortableMaintenanceEntryAuthorized=$true
    $PreviousAuthMode='browser'
    $StartupInteractiveEnabled=$Interactive
    $SyntheticUserInteractive=$HostInteractive
    . $scan @Arguments
    $CodexLaunchArgs=Test-AndNormalizeCodexCliArgs -InputArgs $CodexLaunchArgs
    . $menu
    return [pscustomobject]@{Mode=$ConfiguredAuthMode;Menu=$ShowStartupMenu;Args=@($CodexLaunchArgs);Maintenance=$PortableMaintenanceMode;Extensions=$PortableExtensionsRequested}
}
$oldAuthMode=$env:CODEX_AUTH_MODE
try {
    $script:PathValues=@()
    $explicit=Get-LaunchState -Arguments @('--portable-auth=browser')
    $api=Get-LaunchState -Arguments @('--portable-auth','api')
    $emptyOutputRejected=$false
    try { $null=Get-LaunchState -Arguments @('exec','-o=','synthetic prompt') }
    catch {
        if ($_.Exception.Message -notlike 'CLI_REJECT:*') {throw}
        $emptyOutputRejected=$true
    }
    if ($BaselineCommit) {
        Assert-Case ($explicit.Menu -and $api.Menu -and $explicit.Mode -eq 'browser' -and $api.Mode -eq 'api') 'Prior explicit selection overridden by menu did not reproduce.'
        Assert-Case (-not $emptyOutputRejected -and $script:PathValues.Count -eq 1 -and $script:PathValues[0] -ceq '=') 'Prior short empty output became equals filename did not reproduce.'
        Write-Output 'REPRODUCED explicit authentication choice overridden by startup menu; empty -o= became equals filename'
        return
    }
    Assert-Case (-not $explicit.Menu -and $explicit.Mode -eq 'browser' -and $explicit.Args.Count -eq 0) 'Explicit browser choice not honored.'
    Assert-Case (-not $api.Menu -and $api.Mode -eq 'api' -and $api.Args.Count -eq 0) 'Explicit API choice not honored.'
    foreach ($mode in @('api','account_json','browser','last')) {
        foreach ($argsForMode in @(@{Items=@('--portable-auth',$mode)},@{Items=@('--portable-auth='+$mode)})) {
            $state=Get-LaunchState -Arguments $argsForMode.Items
            Assert-Case (-not $state.Menu -and $state.Mode -ceq $mode -and $state.Args.Count -eq 0) ('Explicit mode failed: '+$mode)
        }
    }
    Assert-Case ((Get-LaunchState -Arguments @()).Menu) 'Bare interactive startup no longer opens menu.'
    Assert-Case ((Get-LaunchState -Arguments @() -DefaultMode 'api').Menu) 'Existing env-only menu behavior changed.'
    Assert-Case ((Get-LaunchState -Arguments @('--portable-auth','menu')).Menu) 'Explicit menu no longer opens menu.'
    Assert-Case ((Get-LaunchState -Arguments @('--portable-auth=api','--portable-auth=menu')).Menu) 'Last explicit menu did not win.'
    Assert-Case (-not (Get-LaunchState -Arguments @('--portable-auth=menu','--portable-auth=api')).Menu) 'Last explicit API did not win.'
    $maintenance=Get-LaunchState -Arguments @('--portable-maintenance')
    Assert-Case ($maintenance.Menu -and $maintenance.Maintenance) 'Existing maintenance menu changed.'
    $extension=Get-LaunchState -Arguments @('--portable-extensions')
    Assert-Case ($extension.Menu -and $extension.Extensions) 'Existing extension-only menu changed.'
    $state=Get-LaunchState -Arguments @('--portable-auth=last','--portable-extensions')
    Assert-Case (-not $state.Menu -and $state.Extensions -and $state.Mode -ceq 'last') 'Explicit auth and extension selection inconsistent.'
    Assert-Case (-not (Get-LaunchState -Arguments @() -Interactive $false).Menu) 'Disabled startup menu opened.'
    Assert-Case (-not (Get-LaunchState -Arguments @() -HostInteractive $false).Menu) 'Noninteractive host opened menu.'
    $native=Get-LaunchState -Arguments @('exec','synthetic prompt')
    Assert-Case (-not $native.Menu -and ($native.Args -join '|') -ceq 'exec|synthetic prompt') 'Existing native arguments changed.'
    $literal=Get-LaunchState -Arguments @('--','--portable-auth=browser')
    Assert-Case (-not $literal.Menu -and $literal.Mode -ceq 'menu' -and ($literal.Args -join '|') -ceq '--|--portable-auth=browser') 'Existing terminator changed.'
    Write-Output 'PASS explicit authentication mode precedence and existing menu, maintenance, extensions, native and literal paths'
    Assert-Case ($emptyOutputRejected -and $script:PathValues.Count -eq 0) 'Empty short output value accepted.'
    foreach ($bad in @(@{Items=@('exec','--output-last-message=')},@{Items=@('exec','-o','')},@{Items=@('exec','-o')},@{Items=@('exec','--output-schema=')})) {
        $rejected=$false
        try {$null=Get-LaunchState -Arguments $bad.Items} catch {
            if ($_.Exception.Message -notlike 'CLI_REJECT:*') {throw}; $rejected=$true
        }
        Assert-Case $rejected 'Existing empty path guard regressed.'
    }
    foreach ($good in @(
        @{Items=@('exec','-o=out.txt');Output='exec|-o=RESOLVED:out.txt'},
        @{Items=@('exec','-oout.txt');Output='exec|-o=RESOLVED:out.txt'},
        @{Items=@('exec','-o','out.txt');Output='exec|-o|RESOLVED:out.txt'},
        @{Items=@('exec','-o==');Output='exec|-o=RESOLVED:='},
        @{Items=@('exec','--output-last-message=out.txt');Output='exec|--output-last-message=RESOLVED:out.txt'},
        @{Items=@('exec','--output-schema','schema.json');Output='exec|--output-schema|RESOLVED:schema.json'},
        @{Items=@('exec','--','-o=');Output='exec|--|-o='}
    )) {
        $state=Get-LaunchState -Arguments $good.Items
        Assert-Case (($state.Args -join '|') -ceq $good.Output) ('Existing path argument changed: '+$good.Output)
    }
    Write-Output 'PASS empty -o= rejected and ordinary/explicit equals/terminator/output-schema forms unchanged'
} finally { $env:CODEX_AUTH_MODE=$oldAuthMode }
