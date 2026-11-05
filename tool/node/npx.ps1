# Portable npm entrypoint. Do not search host Node or global npm installations.
$ErrorActionPreference = 'Stop'
# Direct PS1 invocation already runs inside PowerShell; prevent this wrapper
# from passing forged host Windows paths or autoloading host modules before
# checking package input. Preserve the caller's process environment on exit.
$NativeNames = @('SystemRoot', 'WINDIR', 'SystemDrive', 'ComSpec', 'PATHEXT',
                 'PSModulePath', 'PSModuleAnalysisCachePath', 'POWERSHELL_TELEMETRY_OPTOUT')
$PreviousNativeSettings = @{}
foreach ($name in $NativeNames) {
    $PreviousNativeSettings[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
try {
    $TrustedWindowsRoot = [IO.Path]::GetFullPath([Environment]::GetFolderPath('Windows')).TrimEnd('\')
    if ($TrustedWindowsRoot -notmatch '^[A-Za-z]:\\' -or $TrustedWindowsRoot.Substring(2).Contains(':') -or
        -not [IO.File]::Exists((Join-Path $TrustedWindowsRoot 'System32\cmd.exe'))) {
        throw 'Portable npm requires a real Windows system directory.'
    }
    $env:SystemRoot = $TrustedWindowsRoot
    $env:WINDIR = $TrustedWindowsRoot
    $env:SystemDrive = [IO.Path]::GetPathRoot($TrustedWindowsRoot).TrimEnd('\')
    $env:ComSpec = Join-Path $TrustedWindowsRoot 'System32\cmd.exe'
    $env:PATHEXT = '.COM;.EXE;.BAT;.CMD'
    $env:PSModulePath = Join-Path $TrustedWindowsRoot 'System32\WindowsPowerShell\v1.0\Modules'
    $env:PSModuleAnalysisCachePath = 'NUL'
    $env:POWERSHELL_TELEMETRY_OPTOUT = '1'
function Assert-NpmBootstrapPath {
    param([string]$Path, [bool]$File)
    $Path = [IO.Path]::GetFullPath($Path)
    if ($Path -notmatch '^[A-Za-z]:\\' -or $Path.Substring(2).Contains(':')) { throw 'Local Windows paths are required.' }
    # Compute the chain lexically; inspect parents before touching descendants.
    $Ancestors = New-Object 'System.Collections.Generic.Stack[string]'
    $Cursor = $Path
    while (-not [string]::IsNullOrWhiteSpace($Cursor)) {
        $Ancestors.Push($Cursor)
        $Cursor = [IO.Path]::GetDirectoryName($Cursor)
    }
    while ($Ancestors.Count) {
        $Cursor = $Ancestors.Pop()
        $Item = Get-Item -LiteralPath $Cursor -Force -ErrorAction Stop
        if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Reparse points are not allowed.' }
        if ($Cursor -eq $Path -and $File) {
            if ($Item.PSIsContainer -or $null -eq $Item.PSObject.Properties['LinkType'] -or
                [string]$Item.LinkType -eq 'HardLink' -or ([string]$Item.Mode).Contains('l')) { throw 'A regular single-link file is required.' }
        } elseif (-not $Item.PSIsContainer) { throw 'A directory is required.' }
    }
}
try {
    $PortableNpmRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\')
    $CurrentDirectory = (Get-Location).ProviderPath
    if ([string]::IsNullOrWhiteSpace($CurrentDirectory) -or -not (
        $CurrentDirectory.Equals($PortableNpmRoot, [StringComparison]::OrdinalIgnoreCase) -or
        $CurrentDirectory.StartsWith($PortableNpmRoot + '\', [StringComparison]::OrdinalIgnoreCase))) {
        throw 'Working directory must remain inside this portable package.'
    }
    Assert-NpmBootstrapPath $PortableNpmRoot $false
    Assert-NpmBootstrapPath $CurrentDirectory $false
    $NodeExecutable = Join-Path $PSScriptRoot 'node.exe'
    $PortableNpmScript = Join-Path $PSScriptRoot 'portable-npm.js'
    foreach ($Path in @($PSCommandPath, $NodeExecutable, $PortableNpmScript)) {
        Assert-NpmBootstrapPath $Path $true
    }
} catch {
    [Console]::Error.WriteLine('Safety stop: unsafe package/code/cwd; npm NOT EXECUTED.')
    exit 3
}
$StartupVariables = @('NODE_OPTIONS','NODE_PATH','NODE_EXTRA_CA_CERTS','NODE_COMPILE_CACHE',
    'NODE_V8_COVERAGE','NODE_REDIRECT_WARNINGS','OPENSSL_CONF','SSL_CERT_FILE','SSL_CERT_DIR')
$PreviousNodeSettings = @{}
$NpmExitCode = 1
try {
    foreach ($Name in $StartupVariables) {
        $PreviousNodeSettings[$Name] = [Environment]::GetEnvironmentVariable($Name, 'Process')
        [Environment]::SetEnvironmentVariable($Name, $null, 'Process')
    }
    if ($MyInvocation.ExpectingInput) {
        $input | & $NodeExecutable $PortableNpmScript npx @args
    } else {
        & $NodeExecutable $PortableNpmScript npx @args
    }
    $NpmExitCode = $LASTEXITCODE
} finally {
    foreach ($Name in $PreviousNodeSettings.Keys) {
        [Environment]::SetEnvironmentVariable($Name, $PreviousNodeSettings[$Name], 'Process')
    }
}
} finally {
    foreach ($name in $NativeNames) {
        [Environment]::SetEnvironmentVariable($name, $PreviousNativeSettings[$name], 'Process')
    }
}
exit $NpmExitCode
