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
    $cursor = $full
    while ($cursor) {
        $item = Get-Item -LiteralPath $cursor -Force -ErrorAction SilentlyContinue
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
        $parent = Split-Path -Parent $cursor
        if ($parent -eq $cursor) { break }
        $cursor = $parent
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

function Remove-AutomationSession {
    param([string]$Root, [string]$Path)
    $temporary = Join-Path $Root 'tmp'
    $full = Assert-AutomationPath -Root $temporary -Path $Path -Directory
    if ($full -eq [IO.Path]::GetFullPath($temporary)) { throw 'Cannot remove the shared temporary root.' }
    # Validate before descending; Get-ChildItem -Recurse could follow a link
    # before its attributes are inspected. Only call after the owned job exits.
    $directories = New-Object System.Collections.Stack
    $directories.Push($full)
    while ($directories.Count -gt 0) {
        $current = $directories.Pop()
        foreach ($entry in @(Get-ChildItem -LiteralPath $current -Force)) {
            [void](Assert-AutomationPath -Root $full -Path $entry.FullName -Directory:$entry.PSIsContainer)
            if ($entry.PSIsContainer) { $directories.Push($entry.FullName) }
        }
    }
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
    if ($WindowsPowerShell) {
        # Windows PowerShell is an OS facility, not a third-party host fallback.
        $trusted = Join-Path ([Environment]::GetFolderPath('Windows')) 'System32\WindowsPowerShell\v1.0\powershell.exe'
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
    foreach ($name in @('SystemRoot', 'WINDIR', 'SYSTEMDRIVE', 'COMSPEC', 'NUMBER_OF_PROCESSORS',
                        'PROCESSOR_ARCHITECTURE', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
                        'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy')) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if ($value) { $start.EnvironmentVariables[$name] = $value }
    }
    foreach ($name in @('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP', 'TMPDIR',
                        'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME')) {
        $start.EnvironmentVariables[$name] = $SessionDirectory
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
    . $helper
    # Dot-source into the caller's script scope, not this function's local scope.
    Set-Item -Path Function:script:Invoke-PortableProcess -Value ${function:Invoke-PortableProcess}
    Set-Item -Path Function:script:Initialize-PortableProcessJob -Value ${function:Initialize-PortableProcessJob}
}
