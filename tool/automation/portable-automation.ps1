#Requires -Version 5.1
# Shared, inert helpers. Dot-sourcing this file never launches a tool.
Set-StrictMode -Version 2.0

function Assert-AutomationPath {
    param(
        [Parameter(Mandatory=$true)][string]$Root,
        [Parameter(Mandatory=$true)][string]$Path,
        [switch]$Directory,
        [switch]$MayNotExist
    )
    if ($Path -match '(^|[\\/])\.\.([\\/]|$)' -or $Path.IndexOf([char]0) -ge 0) {
        throw 'Parent traversal and NUL are not allowed.'
    }
    $base = [IO.Path]::GetFullPath($Root).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $full = [IO.Path]::GetFullPath($Path)
    $comparison = [StringComparison]::OrdinalIgnoreCase
    if ([IO.Path]::DirectorySeparatorChar -ne '\') { $comparison = [StringComparison]::Ordinal }
    if (-not ($full.Equals($base, $comparison) -or $full.StartsWith($base + [IO.Path]::DirectorySeparatorChar, $comparison))) {
        throw 'Automation paths must remain inside this package.'
    }
    if ([IO.Path]::DirectorySeparatorChar -eq '\' -and
        ($full.StartsWith('\\') -or $full.Substring(2).Contains(':'))) {
        throw 'UNC, device paths and alternate data streams are not supported.'
    }
    # Inspect all ancestors, including those above the package root.
    $ancestors = New-Object System.Collections.Stack
    $cursor = $full
    while ($cursor) {
        $ancestors.Push($cursor)
        $parent = Split-Path -Parent $cursor
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
    while ($ancestors.Count -gt 0) {
        $item = Get-Item -LiteralPath $ancestors.Pop() -Force -ErrorAction SilentlyContinue
        if ($null -ne $item) {
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
                ($item.PSObject.Properties['LinkType'] -and $item.LinkType)) {
                throw 'Automation refuses links and reparse points.'
            }
            if (-not $item.PSIsContainer -and (
                ([string]$item.Mode).Contains('l') -or
                ($item.PSObject.Properties['Target'] -and @($item.Target).Count -gt 1))) {
                throw 'Automation refuses multiply linked files.'
            }
        }
    }
    $leaf = Get-Item -LiteralPath $full -Force -ErrorAction SilentlyContinue
    if ($null -eq $leaf) {
        if (-not $MayNotExist) { throw 'Required package path is missing.' }
    } elseif ([bool]$leaf.PSIsContainer -ne [bool]$Directory) {
        throw 'Package path has the wrong file type.'
    }
    return $full
}

function Get-AutomationRoot {
    $root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
    if ([IO.Path]::DirectorySeparatorChar -ne '\') {
        $root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
    }
    [void](Assert-AutomationPath -Root $root -Path $root -Directory)
    [void](Assert-AutomationPath -Root $root -Path (Join-Path $root 'env.ps1'))
    return $root
}

function New-AutomationDirectory {
    param([string]$Root, [string]$Path)
    $full = Assert-AutomationPath -Root $Root -Path $Path -Directory -MayNotExist
    [void][IO.Directory]::CreateDirectory($full)
    return (Assert-AutomationPath -Root $Root -Path $full -Directory)
}

function Assert-AutomationTree {
    param([string]$Root, [string]$Path)
    $full = Assert-AutomationPath -Root $Root -Path $Path -Directory
    # Validate each child before descending. Recursive enumeration can cross a
    # junction before the caller gets a chance to inspect its attributes.
    $directories = New-Object System.Collections.Stack
    $directories.Push($full)
    while ($directories.Count -gt 0) {
        $current = $directories.Pop()
        [void](Assert-AutomationPath -Root $full -Path $current -Directory)
        foreach ($entry in @(Get-ChildItem -LiteralPath $current -Force)) {
            [void](Assert-AutomationPath -Root $full -Path $entry.FullName -Directory:$entry.PSIsContainer)
            if ($entry.PSIsContainer) { $directories.Push($entry.FullName) }
        }
    }
}

function Open-AutomationBrowserLock {
    param([Parameter(Mandatory=$true)][string]$Root)
    # Separate from the Codex lock: the parent Codex process may already own it.
    # Keep this file outside cache so clearing browser state cannot unlink a live lock.
    $lockPath = Assert-AutomationPath -Root $Root -Path (Join-Path $Root '.codex-browser.instance.lock') -MayNotExist
    $handle = $null
    try {
        $handle = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        [void](Assert-AutomationPath -Root $Root -Path $lockPath)
        return $handle
    } catch {
        if ($null -ne $handle) { $handle.Dispose() }
        throw 'Browser state is in use, or its package lock is unsafe; close the browser task before retrying.'
    }
}

function Initialize-AutomationBrowserState {
    param([Parameter(Mandatory=$true)][string]$Root)
    # Caller holds Open-AutomationBrowserLock until the entire owned process tree exits.
    $state = New-AutomationDirectory -Root $Root -Path (Join-Path (Join-Path $Root 'cache') 'browser')
    Assert-AutomationTree -Root $Root -Path $state
    $paths = [ordered]@{ Root = $state }
    foreach ($name in @('profile', 'cache', 'crashes', 'downloads', 'runtime')) {
        $paths[$name] = New-AutomationDirectory -Root $Root -Path (Join-Path $state $name)
    }
    return [PSCustomObject]$paths
}

function Remove-AutomationSession {
    param([string]$Root, [string]$Path)
    $temporary = Join-Path $Root 'tmp'
    $full = Assert-AutomationPath -Root $temporary -Path $Path -Directory
    if ($full -eq [IO.Path]::GetFullPath($temporary)) { throw 'Cannot remove the shared temporary root.' }
    # Only call after the owned job exits.
    Assert-AutomationTree -Root $Root -Path $full
    Remove-Item -LiteralPath $full -Recurse -Force
}

function ConvertTo-AutomationArgument {
    param([AllowEmptyString()][string]$Value)
    # CommandLineToArgvW / CRT quotation, including quotes and trailing slashes.
    return '"' + [regex]::Replace([regex]::Replace($Value, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
}

function New-AutomationStartInfo {
    param(
        [string]$Root, [string]$FilePath, [string]$WorkingDirectory,
        [string[]]$Arguments, [string]$SessionDirectory, [switch]$CaptureOutput,
        [switch]$WindowsPowerShell
    )
    [void](Assert-AutomationPath -Root $Root -Path $WorkingDirectory -Directory)
    [void](Assert-AutomationPath -Root $Root -Path $SessionDirectory -Directory)
    # The real OS Windows directory, not an inherited SystemRoot/ComSpec.
    $windowsFolder = [IO.Path]::GetFullPath([Environment]::GetFolderPath('Windows')).TrimEnd('\')
    if ($windowsFolder -notmatch '^[A-Za-z]:\\' -or $windowsFolder.Substring(2).Contains(':')) {
        throw 'Automation requires a local Windows system directory.'
    }
    $systemCmd = Join-Path $windowsFolder 'System32\cmd.exe'
    if (-not [IO.File]::Exists($systemCmd)) { throw 'Windows command processor is unavailable.' }
    if ($WindowsPowerShell) {
        # Windows PowerShell is an OS facility, not a third-party host fallback.
        $trusted = Join-Path $windowsFolder 'System32\WindowsPowerShell\v1.0\powershell.exe'
        if ($FilePath -cne $trusted -or -not [IO.File]::Exists($trusted)) { throw 'Only built-in Windows PowerShell is permitted.' }
    } else {
        [void](Assert-AutomationPath -Root $Root -Path $FilePath)
    }
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = $FilePath
    $start.Arguments = (@($Arguments | ForEach-Object { ConvertTo-AutomationArgument $_ }) -join ' ')
    $start.WorkingDirectory = $WorkingDirectory
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = [bool]$CaptureOutput
    $start.RedirectStandardError = [bool]$CaptureOutput
    $start.RedirectStandardInput = [bool]$CaptureOutput
    $start.EnvironmentVariables.Clear()
    $start.EnvironmentVariables['SystemRoot'] = $windowsFolder
    $start.EnvironmentVariables['WINDIR'] = $windowsFolder
    $start.EnvironmentVariables['SYSTEMDRIVE'] = [IO.Path]::GetPathRoot($windowsFolder).TrimEnd('\')
    $start.EnvironmentVariables['COMSPEC'] = $systemCmd
    $start.EnvironmentVariables['PATHEXT'] = '.COM;.EXE;.BAT;.CMD'
    $start.EnvironmentVariables['NUMBER_OF_PROCESSORS'] = [string][Environment]::ProcessorCount
    $start.EnvironmentVariables['PROCESSOR_ARCHITECTURE'] = 'AMD64'

    # A direct browser or desktop task must not adopt a host proxy. Only the
    # main launcher's explicit package-local proxy choice may be forwarded.
    $proxyEnabled = [string]::Equals(
        [Environment]::GetEnvironmentVariable('CODEX_INSTALL_DIR'), $Root,
        [StringComparison]::OrdinalIgnoreCase) -and
        [string]::Equals(
        [Environment]::GetEnvironmentVariable('CODEX_HOME'), (Join-Path $Root 'home'),
        [StringComparison]::OrdinalIgnoreCase)
    foreach ($name in @('CODEX_PROXY_ENABLED', 'CODEX_PROXY_FOR_SUBPROCESS',
                        'CODEX_SANDBOX_NETWORK_ACCESS')) {
        $value = [string][Environment]::GetEnvironmentVariable($name)
        if ($value.Trim() -notmatch '^(?i:1|true|yes|on)$') { $proxyEnabled = $false }
    }
    if ($proxyEnabled) {
        foreach ($name in @('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
                            'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy')) {
            $value = [Environment]::GetEnvironmentVariable($name)
            if (-not [string]::IsNullOrWhiteSpace($value)) {
                $start.EnvironmentVariables[$name] = $value
            }
        }
    }
    foreach ($name in @('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP', 'TMPDIR',
                        'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME')) {
        $start.EnvironmentVariables[$name] = $SessionDirectory
    }
    if ([IO.Path]::DirectorySeparatorChar -eq '\') {
        $drive = [IO.Path]::GetPathRoot($SessionDirectory).TrimEnd('\')
        $start.EnvironmentVariables['HOMEDRIVE'] = $drive
        $start.EnvironmentVariables['HOMEPATH'] = $SessionDirectory.Substring($drive.Length)
    }
    $start.EnvironmentVariables['PATH'] = (Join-Path $Root 'tool\node')
    $start.EnvironmentVariables['PLAYWRIGHT_BROWSERS_PATH'] = Join-Path $Root 'tool\automation\browsers'
    $start.EnvironmentVariables['PLAYWRIGHT_SKIP_BROWSER_GC'] = '1'
    $start.EnvironmentVariables['PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD'] = '1'
    $start.EnvironmentVariables['npm_config_cache'] = Join-Path $SessionDirectory 'npm-cache'
    $start.EnvironmentVariables['npm_config_userconfig'] = Join-Path $SessionDirectory 'npmrc'
    $start.EnvironmentVariables['npm_config_globalconfig'] = Join-Path $SessionDirectory 'npm-globalrc'
    $start.EnvironmentVariables['POWERSHELL_TELEMETRY_OPTOUT'] = '1'
    $start.EnvironmentVariables['PSModuleAnalysisCachePath'] = Join-Path $SessionDirectory 'ps-module-cache'
    $start.EnvironmentVariables['ANONYMIZED_TELEMETRY'] = 'false'
    $start.EnvironmentVariables['PROGRAMDATA'] = $SessionDirectory
    $start.EnvironmentVariables['ALLUSERSPROFILE'] = $SessionDirectory
    $start.EnvironmentVariables['PUBLIC'] = $SessionDirectory
    return $start
}

function Initialize-AutomationSupervisor {
    param([string]$Root)
    $helper = Assert-AutomationPath -Root $Root -Path (Join-Path $Root 'tool\portable-process.ps1')
    # Direct tool entry points must also work in a fresh extracted package.
    # Create only the validated package-local compiler scratch root.
    [void](New-AutomationDirectory -Root $Root -Path (Join-Path $Root 'tmp'))
    . $helper
    # Dot-source into the caller's script scope, not this function's local scope.
    Set-Item -Path Function:script:Invoke-PortableProcess -Value ${function:Invoke-PortableProcess}
    Set-Item -Path Function:script:Initialize-PortableProcessJob -Value ${function:Initialize-PortableProcessJob}
}
