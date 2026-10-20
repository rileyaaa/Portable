#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$Workspace = 'work\browser-debug',
    [string]$ExecutablePath = '',
    [string]$TaskScript = '',
    [ValidateRange(1,1800)][int]$TaskTimeoutSec = 120,
    [switch]$Headed,
    [switch]$Check,
    [switch]$TaskAuthorized,
    [switch]$KeepSessionData
)
$ErrorActionPreference = 'Stop'
if (-not $Check -and -not $TaskAuthorized) {
    throw 'Select a browser task explicitly with -TaskAuthorized before starting the server.'
}
# Validate the entry path and helper before loading project code.
$bootstrapCursor = [IO.Path]::GetFullPath($PSCommandPath)
while ($bootstrapCursor) {
    $bootstrapItem = Get-Item -LiteralPath $bootstrapCursor -Force -ErrorAction Stop
    if (($bootstrapItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
        ($bootstrapItem.PSObject.Properties['LinkType'] -and $bootstrapItem.LinkType) -or
        (-not $bootstrapItem.PSIsContainer -and ([string]$bootstrapItem.Mode).Contains('l'))) {
        throw 'Automation entry path must not contain links.'
    }
    $bootstrapParent = Split-Path -Parent $bootstrapCursor
    if ($bootstrapParent -eq $bootstrapCursor) { break }
    $bootstrapCursor = $bootstrapParent
}
$helperPath = Join-Path $PSScriptRoot 'portable-automation.ps1'
$helperItem = Get-Item -LiteralPath $helperPath -Force -ErrorAction Stop
if ($helperItem.PSIsContainer -or ($helperItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
    ($helperItem.PSObject.Properties['LinkType'] -and $helperItem.LinkType) -or ([string]$helperItem.Mode).Contains('l')) {
    throw 'Automation helper must be an ordinary single-link package file.'
}
. $helperPath
$root = Get-AutomationRoot
$manifestPath = Assert-AutomationPath -Root $root -Path (Join-Path $PSScriptRoot 'versions.json')
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if (-not [IO.Path]::IsPathRooted($Workspace)) { $Workspace = Join-Path $root $Workspace }
$workRoot = Assert-AutomationPath -Root $root -Path (Join-Path $root 'work') -Directory -MayNotExist
$Workspace = Assert-AutomationPath -Root $workRoot -Path $Workspace -Directory -MayNotExist
if ($Workspace -eq $workRoot) { throw 'Select a task subdirectory inside work.' }
if (-not $ExecutablePath) { $ExecutablePath = Join-Path $PSScriptRoot $manifest.browser.executable }
elseif (-not [IO.Path]::IsPathRooted($ExecutablePath)) { $ExecutablePath = Join-Path $root $ExecutablePath }
[void](Assert-AutomationPath -Root $root -Path $ExecutablePath -MayNotExist)
$node = Assert-AutomationPath -Root $root -Path (Join-Path $root 'tool\node\node.exe')
$bridge = Assert-AutomationPath -Root $root -Path (Join-Path $PSScriptRoot 'browser-bridge.js')
if ($TaskScript) {
    if (-not [IO.Path]::IsPathRooted($TaskScript)) { $TaskScript = Join-Path $root $TaskScript }
    $TaskScript = Assert-AutomationPath -Root $Workspace -Path $TaskScript
    if ([IO.Path]::GetExtension($TaskScript) -ne '.cjs') { throw 'Browser task scripts must be .cjs modules inside the selected workspace.' }
    $bridge = Assert-AutomationPath -Root $root -Path (Join-Path $PSScriptRoot 'browser-task.js')
}
[void](Assert-AutomationPath -Root $root -Path (Join-Path $PSScriptRoot 'playwright\node_modules\@playwright\mcp\index.js'))
if ($Check) {
    [PSCustomObject]@{
        PackageRoot = $root; Workspace = $Workspace
        MCPVersion = $manifest.playwrightMcp; BrowserVersion = $manifest.browser.version
        BrowserExecutable = $ExecutablePath; BrowserPresent = [IO.File]::Exists($ExecutablePath)
        AutomaticStart = $false; Mode = $(if ($TaskScript) { 'task-script' } else { 'stdio-mcp' }); Headed = [bool]$Headed
    } | ConvertTo-Json
    exit 0
}
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or -not [Environment]::Is64BitOperatingSystem) {
    throw 'Browser automation requires Windows x64.'
}
[void](Assert-AutomationPath -Root $root -Path $ExecutablePath)
$Workspace = New-AutomationDirectory -Root $root -Path $Workspace
$session = New-AutomationDirectory -Root $root -Path (Join-Path $root ('tmp\browser-' + [Guid]::NewGuid().ToString('N')))
Initialize-AutomationSupervisor -Root $root
$mode = 'headless'; if ($Headed) { $mode = 'headed' }
$arguments = @($bridge, $Workspace, $ExecutablePath, $mode, '--task-authorized')
if ($TaskScript) { $arguments += $TaskScript }
$start = New-AutomationStartInfo -Root $root -FilePath $node -WorkingDirectory $Workspace -Arguments $arguments -SessionDirectory $session
# Foreground stdio only. The supervisor closes the whole browser job on exit.
# Session cleanup follows process exit and refuses any linked subtree.
try {
    $timeout = 0
    if ($TaskScript) { $timeout = $TaskTimeoutSec * 1000 }
    $result = Invoke-PortableProcess -StartInfo $start -PackageRoot $root -TimeoutMs $timeout
} finally {
    if (-not $KeepSessionData) { Remove-AutomationSession -Root $root -Path $session }
}
exit $result.ExitCode
