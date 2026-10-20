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
$node = Assert-AutomationPath -Root $root -Path (Join-Path $root 'tool\node\node.exe')
$cli = Assert-AutomationPath -Root $root -Path (Join-Path $PSScriptRoot 'playwright\node_modules\playwright\cli.js')
if ($Check -or -not $Install) {
    [PSCustomObject]@{
        Action = 'Explicit installation required: rerun with -Install'
        MCPVersion = $manifest.playwrightMcp; BrowserVersion = $manifest.browser.version
        Destination = $browserRoot; OfficialURL = $manifest.browser.downloadUrl
        BrowserPresent = [IO.File]::Exists((Join-Path $PSScriptRoot $manifest.browser.executable))
    } | ConvertTo-Json
    exit 0
}
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or -not [Environment]::Is64BitOperatingSystem) {
    throw 'Install the Windows x64 browser from Windows x64.'
}
$browserRoot = New-AutomationDirectory -Root $root -Path $browserRoot
# Reject an existing linked subtree before the upstream installer writes into it.
foreach ($item in @(Get-ChildItem -LiteralPath $browserRoot -Force -Recurse)) {
    [void](Assert-AutomationPath -Root $root -Path $item.FullName -Directory:$item.PSIsContainer)
}
$session = New-AutomationDirectory -Root $root -Path (Join-Path $root ('tmp\browser-install-' + [Guid]::NewGuid().ToString('N')))
Initialize-AutomationSupervisor -Root $root
$start = New-AutomationStartInfo -Root $root -FilePath $node -WorkingDirectory $session -Arguments @($cli, 'install', '--no-shell', 'chromium') -SessionDirectory $session -CaptureOutput
$start.EnvironmentVariables.Remove('PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD')
try {
    $result = Invoke-PortableProcess -StartInfo $start -PackageRoot $root -TimeoutMs 900000
} finally {
    Remove-AutomationSession -Root $root -Path $session
}
if ($result.StdOut) { Write-Output $result.StdOut }
if ($result.ExitCode -ne 0) {
    # Upstream errors can include proxy URLs; leave raw stderr out of reports.
    throw 'Official Playwright browser installation failed. Check network policy and proxy configuration; no host browser fallback was used.'
}
[void](Assert-AutomationPath -Root $root -Path (Join-Path $PSScriptRoot $manifest.browser.executable))
Write-Output 'The pinned Windows Chromium browser is installed inside this package.'
