#Requires -Version 5.1
# Run production argument parsing only; no client, credential or filesystem IO.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $root 'run-codex.ps1'), [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Launcher parsing failed.' }
foreach ($name in @('Test-AndNormalizeCodexCliArgs', 'Get-PortableExtensionCommandNamespace')) {
    $definitions = @($ast.FindAll({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] }, $true) | Where-Object { $_.Name -eq $name })
    if ($definitions.Count -ne 1) { throw ('Expected one production definition: ' + $name) }
    . ([scriptblock]::Create($definitions[0].Extent.Text))
}
function Stop-UnsafeCodexCliArgument($Argument, $Reason) { throw ('MODEL_CLI_REJECT:' + $Argument) }
$PortableMaintenanceMode = $true
$PortableExtensionPolicy = [pscustomobject]@{ AllowedNamespaces = @('mcp_servers', 'plugins') }
$ConfiguredAuthMode = 'api'; $PreviousAuthMode = ''
$cases = @(
    @{ Name = 'internal tunnel rejected'; Tokens = @('tcp-tunnel','--proxy-origins-file','C:\outside\origins.txt'); Reject = $true },
    @{ Name = 'short separate'; Tokens = @('-m', 'Synthetic/Model', '--version'); Value = 'Synthetic/Model' },
    @{ Name = 'short attached'; Tokens = @('-mSynthetic/Model', '--version'); Value = 'Synthetic/Model' },
    @{ Name = 'short equals'; Tokens = @('-m=Synthetic/Model', '--version'); Value = 'Synthetic/Model' },
    @{ Name = 'long separate'; Tokens = @('--model', 'Synthetic/Model', '--version'); Value = 'Synthetic/Model' },
    @{ Name = 'long equals'; Tokens = @('--model=Synthetic/Model', '--version'); Value = 'Synthetic/Model' },
    @{ Name = 'leading literal equals'; Tokens = @('-m==literal', '--version'); Value = '=literal' },
    @{ Name = 'last model wins'; Tokens = @('-m', 'first', '--model=second', '-m=third', '--version'); Value = 'third' },
    @{ Name = 'exec scope'; Tokens = @('exec', '-m=synthetic', 'prompt'); Value = 'synthetic' },
    @{ Name = 'resume scope'; Tokens = @('resume', '-m=synthetic', '--last'); Value = 'synthetic' },
    @{ Name = 'command-like model'; Tokens = @('-m=update', '--version'); Value = 'update' },
    @{ Name = 'marketplace is not model'; Tokens = @('plugin', 'add', 'sample@local', '-m=marketplace'); Value = '' },
    @{ Name = 'terminator leaves literal alone'; Tokens = @('--', '-m='); Value = '' },
    @{ Name = 'prompt then short separate'; Tokens = @('Inspect this project', '-m', 'after-prompt'); Value = 'after-prompt' },
    @{ Name = 'prompt then short attached'; Tokens = @('Inspect this project', '-mafter-prompt'); Value = 'after-prompt' },
    @{ Name = 'prompt then short equals'; Tokens = @('Inspect this project', '-m=after-prompt'); Value = 'after-prompt' },
    @{ Name = 'prompt then long separate'; Tokens = @('Inspect this project', '--model', 'after-prompt'); Value = 'after-prompt' },
    @{ Name = 'prompt then long equals'; Tokens = @('Inspect this project', '--model=after-prompt'); Value = 'after-prompt' },
    @{ Name = 'model before and after prompt'; Tokens = @('-m=before', 'Inspect this project', '--model=after'); Value = 'after' },
    @{ Name = 'exec prompt then model'; Tokens = @('exec', 'Inspect this project', '-m=after-prompt'); Value = 'after-prompt' },
    @{ Name = 'case-sensitive positional prompt'; Tokens = @('Review', '-m=after-prompt'); Value = 'after-prompt' },
    @{ Name = 'prompt terminator preserves literal'; Tokens = @('Inspect this project', '--', '-m=literal'); Value = '' },
    @{ Name = 'prompt then empty model'; Tokens = @('Inspect this project', '-m='); Reject = $true },
    @{ Name = 'prompt then missing model'; Tokens = @('Inspect this project', '--model'); Reject = $true },
    @{ Name = 'uppercase logout is a prompt'; Tokens = @('Logout', '-m=after-prompt'); Value = 'after-prompt'; Root = '' },
    @{ Name = 'uppercase MCP is a prompt'; Tokens = @('MCP', '-m=after-prompt'); Value = 'after-prompt'; Root = '' },
    @{ Name = 'uppercase plugin is a prompt'; Tokens = @('Plugin', '-m=after-prompt'); Value = 'after-prompt'; Root = '' },
    @{ Name = 'uppercase update is a prompt'; Tokens = @('Update', '-m=after-prompt'); Value = 'after-prompt'; Root = '' },
    @{ Name = 'native plugin stays a command'; Tokens = @('plugin', 'list'); Value = ''; Root = 'plugin' },
    @{ Name = 'native logout remains guarded'; Tokens = @('logout'); Reject = $true },
    @{ Name = 'empty short equals'; Tokens = @('-m='); Reject = $true },
    @{ Name = 'empty long equals'; Tokens = @('--model='); Reject = $true },
    @{ Name = 'missing short value'; Tokens = @('-m'); Reject = $true },
    @{ Name = 'missing long value'; Tokens = @('--model'); Reject = $true }
)
foreach ($case in $cases) {
    $inputArgs = New-Object 'System.Collections.Generic.List[string]'
    foreach ($token in $case.Tokens) { $inputArgs.Add($token) }
    if ($case.ContainsKey('Reject')) {
        $rejected = $false
        try { $null = Test-AndNormalizeCodexCliArgs -InputArgs $inputArgs }
        catch { if ($_.Exception.Message -notlike 'MODEL_CLI_REJECT:*') { throw }; $rejected = $true }
        if (-not $rejected) { throw ('Empty/missing model was accepted: ' + $case.Name) }
    } else {
        $output = @(Test-AndNormalizeCodexCliArgs -InputArgs $inputArgs)
        if ($script:CliModelOverride -cne $case.Value) { throw ('Incorrect model value: ' + $case.Name) }
        if ($case.ContainsKey('Root') -and $script:CodexRootCommand -cne $case.Root) { throw ('Prompt/command state was confused: ' + $case.Name) }
        if ($output.Count -ne $inputArgs.Count) { throw ('Argument count changed: ' + $case.Name) }
        for ($i = 0; $i -lt $inputArgs.Count; $i++) {
            if ($output[$i] -cne $inputArgs[$i]) { throw ('Native argument was modified: ' + $case.Name) }
        }
    }
    Write-Output ('PASS model CLI ' + $case.Name)
}
Write-Output ($cases.Count.ToString() + ' production model-option cases passed (offline).')

foreach ($name in @('Get-PortableInteractiveLaunchArgs', 'Invoke-CodexChild')) {
    $node = @($ast.FindAll({ param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] }, $true) | Where-Object Name -eq $name)
    . ([scriptblock]::Create($node[0].Extent.Text))
}
function Invoke-CodexChildInteractive { param([object[]]$LaunchArgs) $script:ObservedLaunchArgs = @($LaunchArgs); return 23 }
$dispatchCases = @(
    @{ Root = ''; Tokens = @(); Expected = @('--no-daemon') },
    @{ Root = ''; Tokens = @('synthetic prompt'); Expected = @('--no-daemon','synthetic prompt') },
    @{ Root = 'resume'; Tokens = @('resume','--last'); Expected = @('--no-daemon','resume','--last') },
    @{ Root = 'fork'; Tokens = @('fork','--last'); Expected = @('--no-daemon','fork','--last') },
    @{ Root = ''; Tokens = @('--no-daemon'); Expected = @('--no-daemon') },
    @{ Root = 'resume'; Tokens = @('resume','--last','--no-daemon'); Expected = @('resume','--last','--no-daemon') },
    @{ Root = ''; Tokens = @('--','--no-daemon'); Expected = @('--no-daemon','--','--no-daemon') },
    @{ Root = ''; Tokens = @('--version'); Expected = @('--no-daemon','--version') },
    @{ Root = 'exec'; Tokens = @('exec','synthetic'); Expected = @('exec','synthetic') },
    @{ Root = 'mcp'; Tokens = @('mcp','list'); Expected = @('mcp','list') },
    @{ Root = 'logout'; Tokens = @('logout'); Expected = @('logout') }
)
foreach ($case in $dispatchCases) {
    $script:CodexRootCommand = $case.Root
    Invoke-CodexChild -LaunchArgs $case.Tokens
    if ($script:CodexProcessExitCode -ne 23) { throw 'Native exit code was lost.' }
    if (($script:ObservedLaunchArgs -join [char]0) -cne ($case.Expected -join [char]0)) { throw ('Incorrect daemon dispatch: ' + $case.Root) }
}
Write-Output ($dispatchCases.Count.ToString() + ' production interactive dispatch cases passed.')
