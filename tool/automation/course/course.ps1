#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateSet('Owner','Client','Clean')][string]$Action,
    [Parameter(Mandatory=$true)][string]$Task,
    [Parameter(Mandatory=$true)][string]$Account,
    [string]$Origin = '',
    [string]$PagePath = '',
    [string]$Session = '',
    [switch]$TaskAuthorized,
    [switch]$AllowPracticeSelection,
    [switch]$OpenNonTimedLandingPage,
    [switch]$CleanupAuthorized
)
$ErrorActionPreference = 'Stop'
if (-not $TaskAuthorized) { throw 'Explicit course task selection required.' }
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or -not [Environment]::Is64BitProcess) { throw 'Windows x64 PowerShell required.' }
foreach ($id in @($Task,$Account)) {
    if ($id -cnotmatch '^[a-z0-9][a-z0-9_-]{0,47}$' -or $id -match '^(con|prn|aux|nul|com[1-9]|lpt[1-9])$') { throw 'Invalid task/account alias.' }
}
$helper = Join-Path (Split-Path -Parent $PSScriptRoot) 'portable-automation.ps1'
foreach ($entry in @($PSCommandPath,$helper)) {
    $chain = New-Object System.Collections.Stack
    $p = [IO.Path]::GetFullPath($entry)
    while ($p) {
        $chain.Push($p)
        $parent = Split-Path -Parent $p
        if ($parent -eq $p) { break }
        $p = $parent
    }
    while ($chain.Count) {
        $item = Get-Item -LiteralPath $chain.Pop() -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or ($item.PSObject.Properties['LinkType'] -and $item.LinkType)) { throw 'Linked automation entry refused.' }
    }
}
. $helper
$root = Get-AutomationRoot
$work = Assert-AutomationPath -Root $root -Path (Join-Path $root 'work') -Directory -MayNotExist
$state = Assert-AutomationPath -Root $work -Path (Join-Path (Join-Path $work ('course-'+$Task)) $Account) -Directory -MayNotExist
$node = Assert-AutomationPath -Root $root -Path (Join-Path $root 'tool\node\node.exe')
$entry = Assert-AutomationPath -Root $root -Path (Join-Path $PSScriptRoot 'course.js')
$python = Assert-AutomationPath -Root $root -Path (Join-Path $root 'tool\python\python.exe')
$pathGuard = Assert-AutomationPath -Root $root -Path (Join-Path $PSScriptRoot 'path_guard.py')
$versions = Get-Content -LiteralPath (Assert-AutomationPath -Root $root -Path (Join-Path (Split-Path -Parent $PSScriptRoot) 'versions.json')) -Raw | ConvertFrom-Json
$exe = Assert-AutomationPath -Root $root -Path (Join-Path (Split-Path -Parent $PSScriptRoot) $versions.browser.executable)
foreach ($relative in @('browser-bridge.js','course\ocr.ps1')) {
    [void](Assert-AutomationPath -Root $root -Path (Join-Path (Split-Path -Parent $PSScriptRoot) $relative))
}
$deps = Assert-AutomationPath -Root $root -Path (Join-Path (Split-Path -Parent $PSScriptRoot) 'playwright\node_modules') -Directory
if ($Action -eq 'Owner') {
    if ($CleanupAuthorized -or $Session -or -not $Origin -or -not $PagePath) { throw 'Owner requires origin and exact page path; no existing session.' }
    $state = New-AutomationDirectory -Root $work -Path $state
} elseif ($Action -eq 'Clean') {
    if (-not $CleanupAuthorized -or $Session -or $Origin -or $PagePath -or $AllowPracticeSelection -or $OpenNonTimedLandingPage) { throw 'Clean requires explicit per-account cleanup authorization only.' }
    $state = Assert-AutomationPath -Root $work -Path $state -Directory
} else {
    if ($CleanupAuthorized -or $Session -cnotmatch '^[0-9a-f]{32}$' -or $Origin -or $PagePath -or $AllowPracticeSelection -or $OpenNonTimedLandingPage) { throw 'Client requires only exact session and account.' }
    $state = Assert-AutomationPath -Root $work -Path $state -Directory
}
function Open-CourseLock([string]$Name) {
    $file = Assert-AutomationPath -Root $state -Path (Join-Path $state $Name) -MayNotExist
    $handle = $null
    try {
        $handle = [IO.File]::Open($file,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
        [void](Assert-AutomationPath -Root $state -Path $file)
        return $handle
    } catch {
        if ($null -ne $handle) { $handle.Dispose() }
        throw 'The specified account owner/client is in use or its lock is unsafe.'
    }
}
$lock = $null
$clientLock = $null
$oldEnvironment = @{}
try {
    if ($Action -eq 'Owner') {
        $lock = Open-CourseLock 'owner.lock'
        foreach ($name in @('profile','cache','crashes','downloads','runtime','tmp','notes')) {
            [void](New-AutomationDirectory -Root $state -Path (Join-Path $state $name))
        }
        Assert-AutomationTree -Root $root -Path (Split-Path -Parent $exe)
        # Locks are held by their wrappers; inspect state directories, not live lock handles.
        foreach ($name in @('profile','cache','crashes','downloads','runtime','tmp','notes')) {
            Assert-AutomationTree -Root $state -Path (Join-Path $state $name)
        }
    } elseif ($Action -eq 'Client') {
        $clientLock = Open-CourseLock 'client.lock'
    } else {
        # Both exclusive handles must be held before inspecting or deleting any
        # profile. The owner and client supervise their child jobs until exit.
        $lock = Open-CourseLock 'owner.lock'
        $clientLock = Open-CourseLock 'client.lock'
        $rooted = $state.TrimEnd('\') + '\'
        # Read process metadata only; no host process termination, no commands
        # or credentials printed. Refuse cleanup if this account's processes
        # are still visible, or if Windows cannot perform the scoped check.
        $ownedExe = @($node,$exe,$python)
        $processes = @(Get-CimInstance -ClassName Win32_Process -Filter "Name='node.exe' OR Name='chrome.exe' OR Name='python.exe' OR Name='powershell.exe'" -ErrorAction Stop)
        foreach ($proc in $processes) {
            if ($proc.ProcessId -eq $PID) { continue }
            $command = [string]$proc.CommandLine
            $image = [string]$proc.ExecutablePath
            if (($ownedExe -icontains $image) -and -not $command) { throw 'Cannot verify that all package child processes have exited.' }
            if (($ownedExe -icontains $image) -and ($command.IndexOf($rooted,[StringComparison]::OrdinalIgnoreCase) -ge 0 -or $command.IndexOf($state+'"',[StringComparison]::OrdinalIgnoreCase) -ge 0)) {
                throw 'An account-owned child process is still running; close it normally before cleaning.'
            }
        }
        $runtime = Assert-AutomationPath -Root $state -Path (Join-Path $state 'runtime') -Directory -MayNotExist
        # A second authorized cleanup is harmless after the directories were removed.
        if (-not (Test-Path -LiteralPath $runtime)) {
            foreach ($name in @('profile','cache','crashes','downloads','tmp')) {
                if (Test-Path -LiteralPath (Join-Path $state $name)) { throw 'Partial account cleanup; inspect the remaining account paths.' }
            }
            Write-Output 'COURSE_ACCOUNT_CLEANED=PASS; already clear'
            exit 0
        }
        foreach ($key in @('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TEMP','TMP','TMPDIR','PROGRAMDATA','ALLUSERSPROFILE','PUBLIC','PSModuleAnalysisCachePath')) {
            $oldEnvironment[$key] = [Environment]::GetEnvironmentVariable($key)
            $value = $runtime
            if ($key -eq 'PSModuleAnalysisCachePath') { $value = Join-Path $runtime 'ps-module-cache' }
            [Environment]::SetEnvironmentVariable($key,$value,'Process')
        }
        $targets = @()
        foreach ($name in @('profile','cache','crashes','downloads','runtime','tmp')) {
            $target = Assert-AutomationPath -Root $state -Path (Join-Path $state $name) -Directory -MayNotExist
            if (Test-Path -LiteralPath $target) {
                & $python -I -B $pathGuard tree $target
                if ($LASTEXITCODE) { throw 'Unsafe account cleanup tree; no deletion attempted.' }
                $targets += $target
            }
        }
        foreach ($key in @($oldEnvironment.Keys)) { [Environment]::SetEnvironmentVariable($key,$oldEnvironment[$key],'Process') }
        $oldEnvironment.Clear()
        foreach ($target in $targets) {
            Assert-AutomationTree -Root $state -Path $target
            Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction Stop
            if (Test-Path -LiteralPath $target) { throw 'Account cleanup incomplete; inspect only this account.' }
        }
        Write-Output 'COURSE_ACCOUNT_CLEANED=PASS; notes and other accounts retained'
        exit 0
    }
    Assert-AutomationTree -Root $root -Path $deps
    [void](Assert-AutomationPath -Root $state -Path (Join-Path $state 'tmp') -Directory)
    $runtime = Assert-AutomationPath -Root $state -Path (Join-Path $state 'runtime') -Directory
    if ($Action -eq 'Client') {
        [void](Assert-AutomationPath -Root $runtime -Path (Join-Path $runtime ('connection-'+$Session+'.json')))
    }
    foreach ($key in @('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TEMP','TMP','TMPDIR','PROGRAMDATA','ALLUSERSPROFILE','PUBLIC','PSModuleAnalysisCachePath')) {
        $oldEnvironment[$key] = [Environment]::GetEnvironmentVariable($key)
        $value = $runtime
        if ($key -eq 'PSModuleAnalysisCachePath') { $value = Join-Path $runtime 'ps-module-cache' }
        [Environment]::SetEnvironmentVariable($key,$value,'Process')
    }
    # Reuse the existing job supervisor with its compiler scratch rooted in
    # this account's tmp, not in the shared package tmp.
    . (Assert-AutomationPath -Root $root -Path (Join-Path $root 'tool\portable-process.ps1'))
    $arguments = @($entry,$Action.ToLowerInvariant(),$state,$Task,$Account,$exe)
    if ($Action -eq 'Owner') { $arguments += @($Origin,$PagePath, $(if ($AllowPracticeSelection) {'select'} else {'read'}), $(if ($OpenNonTimedLandingPage) {'open-non-timed'} else {'blank'})) }
    else { $arguments += @($Session) }
    $start = New-AutomationStartInfo -Root $root -FilePath $node -WorkingDirectory $state -Arguments $arguments -SessionDirectory $runtime
    $result = Invoke-PortableProcess -StartInfo $start -PackageRoot $state -TimeoutMs 0
} finally {
    foreach ($key in $oldEnvironment.Keys) { [Environment]::SetEnvironmentVariable($key,$oldEnvironment[$key],'Process') }
    if ($null -ne $clientLock) { $clientLock.Dispose() }
    if ($null -ne $lock) { $lock.Dispose() }
}
exit $result.ExitCode
