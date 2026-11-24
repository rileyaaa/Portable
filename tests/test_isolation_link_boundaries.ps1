#Requires -Version 5.1
# Actual direct isolation entry with only owned synthetic package/peer paths.
# No host-residue flag, real Marketplace, real credentials or host registry scan.
param([string]$BaselineCommit = '')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
. (Join-Path $root 'tool/automation/portable-automation.ps1')
[void](New-AutomationDirectory -Root $root -Path (Join-Path $root 'tmp'))
$fixture=New-AutomationDirectory -Root $root -Path (Join-Path $root ('tmp\isolation-links-'+[guid]::NewGuid().ToString('N')))
$engine=Join-Path ([Environment]::GetFolderPath('Windows')) 'System32\WindowsPowerShell\v1.0\powershell.exe'
$utf8=New-Object Text.UTF8Encoding($false)
$scriptName='检查隔离.ps1'
$links=New-Object 'System.Collections.Generic.List[string]'
function Assert-Case {param([bool]$Condition,[string]$Message) if (-not $Condition) {throw $Message}}
function Put-Synthetic {
    param([string]$Path,[string]$Content)
    [void](New-AutomationDirectory -Root $fixture -Path (Split-Path -Parent $Path))
    $full=Assert-AutomationPath -Root $fixture -Path $Path -MayNotExist
    [IO.File]::WriteAllText($full,$Content,$utf8)
    return $full
}
function Add-Junction {
    param([string]$Path,[string]$Target)
    [void](Assert-AutomationPath -Root $fixture -Path $Path -Directory -MayNotExist)
    [void](Assert-AutomationPath -Root $fixture -Path $Target -Directory)
    [void](New-Item -ItemType Junction -Path $Path -Target $Target)
    [void]$links.Add($Path)
}
function Drop-Junction {
    param([string]$Path)
    # Only a junction explicitly created and tracked by this test.
    if (-not $links.Contains($Path)) {throw 'Unowned link cleanup refused'}
    [IO.Directory]::Delete($Path,$false)
    [void]$links.Remove($Path)
}
function Invoke-Isolation {
    param([string]$ScriptPath)
    $psi=New-Object Diagnostics.ProcessStartInfo
    $psi.FileName=$engine
    $psi.Arguments='-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$ScriptPath+'"'
    $psi.WorkingDirectory=$fixture
    $psi.UseShellExecute=$false
    $psi.CreateNoWindow=$true
    $psi.RedirectStandardOutput=$true
    $psi.RedirectStandardError=$true
    $process=$null
    try {
        $process=[Diagnostics.Process]::Start($psi)
        $out=$process.StandardOutput.ReadToEndAsync()
        $err=$process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(45000)) {throw 'Synthetic isolation check timed out'}
        return [pscustomobject]@{Code=$process.ExitCode;Output=$out.GetAwaiter().GetResult();Error=$err.GetAwaiter().GetResult()}
    } finally {
        if ($null -ne $process) {
            try {if (-not $process.HasExited) {$process.Kill();[void]$process.WaitForExit(5000)}} finally {$process.Dispose()}
        }
    }
}
try {
    $base=New-AutomationDirectory -Root $fixture -Path (Join-Path $fixture 'actual-parent')
    $package=New-AutomationDirectory -Root $fixture -Path (Join-Path $base 'package')
    $script=Join-Path $package $scriptName
    if ($BaselineCommit) {
        if ($BaselineCommit -notmatch '^[a-f0-9]{40}$') {throw 'Invalid baseline commit'}
        $python=Join-Path $root 'tool\python\python.exe'
        [void](Assert-AutomationPath -Root $root -Path $python)
        $copyBaseline=@'
import subprocess
import sys
from pathlib import Path
root, revision, path, output = sys.argv[1:]
raw = subprocess.check_output(["git", "-C", root, "show", revision + ":" + path], timeout=15)
with Path(output).open("xb") as target:
    target.write(raw)
'@
        # Windows PowerShell 5.1 native argument marshalling strips quotes
        # inside -c source. Pass a real owned script file, not inline code.
        $copyBaselineScript=Join-Path $fixture 'copy-baseline.py'
        [void](Assert-AutomationPath -Root $fixture -Path $copyBaselineScript -MayNotExist)
        [IO.File]::WriteAllText($copyBaselineScript,$copyBaseline,$utf8)
        & $python -B $copyBaselineScript $root $BaselineCommit $scriptName $script
        if ($LASTEXITCODE -ne 0) {throw 'Cannot copy exact baseline isolation script'}
    } else {Copy-Item -LiteralPath (Join-Path $root $scriptName) -Destination $script}
    $alias=Join-Path $fixture 'linked-parent'
    Add-Junction $alias $base
    $linked=Invoke-Isolation (Join-Path $alias ('package\'+$scriptName))
    $tmp=Join-Path $package 'tmp'
    if ($BaselineCommit) {
        Assert-Case ($linked.Code -eq 0 -and [IO.Directory]::Exists($tmp)) 'Previous linked ancestor traversal did not reproduce'
        Write-Output 'REPRODUCED previous direct isolation entry initialized state through a linked ancestor'
    } else {
        Assert-Case ($linked.Code -ne 0 -and -not [IO.Directory]::Exists($tmp)) 'Linked ancestor was not refused before state initialization'
        Write-Output 'PASS direct entry rejects linked ancestor before creating runtime state'
    }
    Drop-Junction $alias

    # A separate owned peer stands in for a host directory. Its content is
    # deliberately harmless; no actual host file is accessed by the test.
    $peer=New-AutomationDirectory -Root $fixture -Path (Join-Path $fixture 'synthetic-peer')
    $externalMarket=Put-Synthetic (Join-Path $peer 'marketplace.json') '{}'
    $externalPlugin=Put-Synthetic (Join-Path $peer 'synthetic-external-plugin\.codex-plugin\plugin.json') '{}'
    $fixtureHome=New-AutomationDirectory -Root $package -Path (Join-Path $package 'home')
    $agents=New-AutomationDirectory -Root $package -Path (Join-Path $fixtureHome '.agents')
    $marketDir=Join-Path $agents 'plugins'
    $pluginRoot=Join-Path $fixtureHome 'plugins'
    Add-Junction $marketDir $peer
    Add-Junction $pluginRoot $peer
    $checked=Invoke-Isolation $script
    Assert-Case ($checked.Code -eq 0) 'Link warning must preserve report-only behavior'
    $marketRead=$checked.Output -match '(?m)^\s*OK\s+Marketplace JSON'
    $pluginVisited=$checked.Output -match 'synthetic-external-plugin[\\/]\.codex-plugin[\\/]plugin\.json'
    if ($BaselineCommit) {
        Assert-Case ($marketRead -and $pluginVisited) 'Previous plugin and marketplace link traversal did not reproduce'
        Write-Output 'REPRODUCED previous Marketplace read and plugin manifest enumeration followed linked directories'
    } else {
        Assert-Case (-not $marketRead -and -not $pluginVisited) 'Linked Marketplace or plugin target still inspected'
        Write-Output 'PASS linked Marketplace and plugin roots are not read/enumerated'
    }
    Drop-Junction $pluginRoot
    Drop-Junction $marketDir
    [void](New-AutomationDirectory -Root $package -Path $marketDir)
    [void](New-AutomationDirectory -Root $package -Path $pluginRoot)
    $market=Join-Path $marketDir 'marketplace.json'
    [void](New-Item -ItemType HardLink -Path $market -Target $externalMarket)
    try {
        $checked=Invoke-Isolation $script
        Assert-Case ($checked.Code -eq 0) 'Hardlink warning must preserve report-only behavior'
        $marketRead=$checked.Output -match '(?m)^\s*OK\s+Marketplace JSON'
        if ($BaselineCommit) {
            Assert-Case $marketRead 'Previous hardlinked Marketplace read did not reproduce'
            Write-Output 'REPRODUCED previous hardlinked Marketplace read'
        } else {
            Assert-Case (-not $marketRead) 'Hardlinked Marketplace was read'
            Write-Output 'PASS hardlinked Marketplace is not read'
        }
    } finally {
        # Remove the test-created hardlink name only, not the peer file.
        [IO.File]::Delete($market)
    }
    Assert-Case ([IO.File]::ReadAllText($externalMarket) -ceq '{}') 'Peer data changed'
    if ($BaselineCommit) {return}

    [void](Put-Synthetic $market '{}')
    $normalManifest=Put-Synthetic (Join-Path $pluginRoot 'normal-plugin\.codex-plugin\plugin.json') '{}'
    $linkedChild=Join-Path $pluginRoot 'linked-child'
    Add-Junction $linkedChild (Split-Path -Parent (Split-Path -Parent $externalPlugin))
    $checked=Invoke-Isolation $script
    Assert-Case ($checked.Code -eq 0 -and $checked.Output -match '(?m)^\s*OK\s+Marketplace JSON' -and
        $checked.Output -match 'normal-plugin[\\/]\.codex-plugin[\\/]plugin\.json' -and
        $checked.Output -notmatch 'linked-child[\\/]\.codex-plugin[\\/]plugin\.json') 'Ordinary report or per-plugin link boundary regressed'
    Drop-Junction $linkedChild
    Write-Output 'PASS ordinary Marketplace and manifest checks and individual linked plugin rejection'
} finally {
    foreach ($path in @($links.ToArray())) {Drop-Junction $path}
    Remove-AutomationSession -Root $root -Path $fixture
}
