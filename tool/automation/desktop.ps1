#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][int]$TargetProcessId,
    [ValidateSet('Tree','Invoke','SetValue')][string]$Action = 'Tree',
    [string]$AutomationId = '',
    [AllowEmptyString()][string]$Value = '',
    [ValidateRange(1,500)][int]$MaxNodes = 150,
    [switch]$AllowChanges,
    [switch]$TaskAuthorized
)
$ErrorActionPreference = 'Stop'
if (-not $TaskAuthorized) { throw 'Select the desktop task and target before using -TaskAuthorized.' }
if ($TargetProcessId -le 0) { throw 'Select a positive target process ID.' }
if ($Action -ne 'Tree' -and -not $AllowChanges) { throw 'A modifying action requires -AllowChanges.' }
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Windows UI Automation is required.' }
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
$worker = Assert-AutomationPath -Root $root -Path (Join-Path $PSScriptRoot 'desktop-worker.ps1')
$session = New-AutomationDirectory -Root $root -Path (Join-Path $root ('tmp\desktop-' + [Guid]::NewGuid().ToString('N')))
$arguments = @('-NoLogo','-NoProfile','-NonInteractive','-File',$worker,
    '-TargetProcessId',[string]$TargetProcessId,'-Action',$Action,'-MaxNodes',[string]$MaxNodes,'-TaskAuthorized')
if ($AutomationId) { $arguments += @('-AutomationId',$AutomationId) }
if ($Action -eq 'SetValue') {
    $arguments += @('-ValueBase64',[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Value)))
}
if ($AllowChanges) { $arguments += '-AllowChanges' }
$powershell = Join-Path ([Environment]::GetFolderPath('Windows')) 'System32\WindowsPowerShell\v1.0\powershell.exe'
Initialize-AutomationSupervisor -Root $root
$start = New-AutomationStartInfo -Root $root -FilePath $powershell -WorkingDirectory $session -Arguments $arguments -SessionDirectory $session -CaptureOutput -WindowsPowerShell
try {
    $result = Invoke-PortableProcess -StartInfo $start -PackageRoot $root -TimeoutMs 30000
} finally {
    Remove-AutomationSession -Root $root -Path $session
}
if ($result.ExitCode -ne 0) { throw 'The selected UI Automation operation failed; no other target was tried.' }
Write-Output $result.StdOut
