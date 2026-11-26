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
$checkOnly = $Check -or -not $Install
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or -not [Environment]::Is64BitOperatingSystem) {
    throw 'Check or install the Windows x64 browser from Windows x64.'
}
$browserLock = $null
$session = $null
try {
    if (-not $checkOnly) {
        $browserLock = Open-AutomationBrowserLock -Root $root
        $browserRoot = New-AutomationDirectory -Root $root -Path $browserRoot
        Assert-AutomationTree -Root $root -Path $browserRoot
    }
    # Use the same isolated supervisor even for a read-only inventory check.
    # Only owned package scratch is created; no browser or profile changes.
    $session = New-AutomationDirectory -Root $root -Path (Join-Path $root ('tmp\browser-install-' + [Guid]::NewGuid().ToString('N')))
    Initialize-AutomationSupervisor -Root $root
    $operation = if ($checkOnly) { '--check' } else { '--install' }
    $start = New-AutomationStartInfo -Root $root -FilePath $python -WorkingDirectory $session -Arguments @('-B', $installer, $operation, '--session', $session) -SessionDirectory $session -CaptureOutput
    $result = Invoke-PortableProcess -StartInfo $start -PackageRoot $root -TimeoutMs 900000
    $status = $null
    if ($result.StdOut) {
        try { $status = $result.StdOut | ConvertFrom-Json -ErrorAction Stop }
        catch { $status = $null }
    }
    if ($checkOnly) {
        if ($null -eq $status -or -not $status.PSObject.Properties['state'] -or
            $status.version -cne $manifest.browser.version -or
            $status.state -notin @('missing','incomplete','verified') -or
            ($status.state -eq 'verified' -and $result.ExitCode -ne 0) -or
            ($status.state -ne 'verified' -and $result.ExitCode -ne 1)) {
            throw 'Pinned browser inventory check failed; no browser or profile changes were made.'
        }
        [PSCustomObject]@{
            Action = $status.action
            MCPVersion = $manifest.playwrightMcp; BrowserVersion = $manifest.browser.version
            Destination = $browserRoot; OfficialURL = $manifest.browser.downloadUrl
            BrowserPresent = [IO.File]::Exists($executable)
            BrowserVerified = ($status.state -eq 'verified')
            BrowserState = $status.state
        } | ConvertTo-Json
        exit 0
    }
    if ($result.StdOut) { Write-Output $result.StdOut }
    if ($result.ExitCode -ne 0) {
        if ($null -ne $status -and $status.PSObject.Properties['state'] -and
            $status.state -eq 'incomplete' -and $status.version -ceq $manifest.browser.version) {
            throw 'Existing pinned browser revision is incomplete or changed. Restore the same version from a verified package; preserve cache/browser/profile. No automatic replacement was attempted.'
        }
        throw 'Pinned Chromium installation or integrity check failed. No host browser fallback or additional browser components were installed.'
    }
    [void](Assert-AutomationPath -Root $root -Path $executable)
    Write-Output 'The pinned Windows Chromium browser is verified inside this package.'
} finally {
    try { if ($session) { Remove-AutomationSession -Root $root -Path $session } }
    finally { if ($browserLock) { $browserLock.Dispose() } }
}
