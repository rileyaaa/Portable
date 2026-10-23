#Requires -Version 5.1
[CmdletBinding()]
param([switch]$Install, [switch]$Check)
$ErrorActionPreference = 'Stop'
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
$manifest = Get-Content -LiteralPath (Assert-AutomationPath -Root $root -Path (Join-Path $PSScriptRoot 'versions.json')) -Raw | ConvertFrom-Json
$browserRoot = Assert-AutomationPath -Root $root -Path (Join-Path $PSScriptRoot 'browsers') -Directory -MayNotExist
$python = Assert-AutomationPath -Root $root -Path (Join-Path $root 'tool\python\python.exe')
$installer = Assert-AutomationPath -Root $root -Path (Join-Path $PSScriptRoot 'install-browser.py')
$executable = Assert-AutomationPath -Root $root -Path (Join-Path $PSScriptRoot $manifest.browser.executable) -MayNotExist
$present = [IO.File]::Exists($executable)
if ($Check -or -not $Install) {
    [PSCustomObject]@{
        Action = $(if ($present) { 'Bundled browser present; -Install verifies its pinned files' } else { 'Explicit installation required: rerun with -Install' })
        MCPVersion = $manifest.playwrightMcp; BrowserVersion = $manifest.browser.version
        Destination = $browserRoot; OfficialURL = $manifest.browser.downloadUrl
        BrowserPresent = $present
    } | ConvertTo-Json
    exit 0
}
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or -not [Environment]::Is64BitOperatingSystem) {
    throw 'Install the Windows x64 browser from Windows x64.'
}
$browserLock = Open-AutomationBrowserLock -Root $root
$session = $null
try {
    $browserRoot = New-AutomationDirectory -Root $root -Path $browserRoot
    Assert-AutomationTree -Root $root -Path $browserRoot
    $session = New-AutomationDirectory -Root $root -Path (Join-Path $root ('tmp\browser-install-' + [Guid]::NewGuid().ToString('N')))
    Initialize-AutomationSupervisor -Root $root
    $start = New-AutomationStartInfo -Root $root -FilePath $python -WorkingDirectory $session -Arguments @('-B', $installer, '--install', '--session', $session) -SessionDirectory $session -CaptureOutput
    $result = Invoke-PortableProcess -StartInfo $start -PackageRoot $root -TimeoutMs 900000
    if ($result.StdOut) { Write-Output $result.StdOut }
    if ($result.ExitCode -ne 0) {
        throw 'Pinned Chromium installation or integrity check failed. No host browser fallback or additional browser components were installed.'
    }
    [void](Assert-AutomationPath -Root $root -Path $executable)
    Write-Output 'The pinned Windows Chromium browser is verified inside this package.'
} finally {
    try { if ($session) { Remove-AutomationSession -Root $root -Path $session } }
    finally { $browserLock.Dispose() }
}
