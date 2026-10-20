#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$LauncherPath = Join-Path $RepositoryRoot 'run-codex.ps1'
$FixtureBase = Join-Path $RepositoryRoot 'tmp'
$FixtureRoot = Join-Path $FixtureBase ('instruction-paths-' + [guid]::NewGuid().ToString('N'))
$FixtureCreated = $false
$RunningOnWindows = [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
$EnginePath = [System.Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
$Passed = 0

# Every input, link target, worker script, and generated file is synthetic and
# lives under this repository's tmp directory. "external" means outside the
# simulated portable package, never outside the repository.
$WorkerSource = @'
$ErrorActionPreference = 'Stop'
$LauncherPath = $env:CODEX_TEST_INSTRUCTIONS_LAUNCHER
$PackageRoot = $env:CODEX_TEST_INSTRUCTIONS_PACKAGE
$InputPath = $env:CODEX_TEST_INSTRUCTIONS_INPUT
$Tokens = $null
$ParseErrors = $null
$Ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $LauncherPath, [ref]$Tokens, [ref]$ParseErrors
)
if ($ParseErrors.Count -gt 0) { throw "Launcher parse failed: $($ParseErrors[0].Message)" }
$FunctionNames = @(
    'Test-IsUnderDirectory',
    'Assert-PortablePath',
    'Assert-PortableRegularInputFile',
    'Write-PortableNewUtf8File',
    'Move-TemporaryFileIntoPlace',
    'Write-Utf8TextAtomic',
    'Get-RuntimeModelIdentityInstructions',
    'Remove-PortableDerivedStateFile',
    'New-RuntimeModelInstructions'
)
foreach ($FunctionName in $FunctionNames) {
    $Definitions = @($Ast.FindAll({
        param($Node)
        $Node -is [System.Management.Automation.Language.FunctionDefinitionAst]
    }, $true) | Where-Object { $_.Name -eq $FunctionName })
    if ($Definitions.Count -ne 1) { throw "Expected one definition of $FunctionName" }
    . ([scriptblock]::Create($Definitions[0].Extent.Text))
}
$Root = $PackageRoot
$env:CODEX_HOME = Join-Path $Root 'home'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    # The production containment helper uses Windows separators and checks
    # Windows reparse chains. On Linux replace only that path helper with a
    # lexical fixture-boundary check. The production regular-input guard,
    # Get-Item LinkType/Mode detection, generator, and atomic writer are real.
    # This Linux test does not validate Windows parent-directory reparse checks.
    function Test-IsUnderDirectory {
        param([string]$Path, [string]$Directory)
        $FullPath = [IO.Path]::GetFullPath($Path)
        $BasePath = [IO.Path]::GetFullPath($Directory).TrimEnd([IO.Path]::DirectorySeparatorChar)
        return $FullPath.Equals($BasePath, [StringComparison]::Ordinal) -or
            $FullPath.StartsWith($BasePath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::Ordinal)
    }
}
$GeneratedPath = New-RuntimeModelInstructions -OriginalPath $InputPath -ModelSlug 'fixture-model'
if (-not (Test-Path -LiteralPath $GeneratedPath -PathType Leaf)) { throw 'Expected generated instructions' }
exit 0
'@

function Invoke-InstructionWorker {
    param([string]$PackageRoot, [string]$InputPath, [string]$RuntimeDirectory)
    $Start = New-Object Diagnostics.ProcessStartInfo
    $Start.FileName = $EnginePath
    # Pass fixture paths through the child environment; only the script filename
    # needs command-line quoting. No shell or inherited PowerShell profile runs.
    $Start.Arguments = '-NoLogo -NoProfile -NonInteractive -File "' + $WorkerPath + '"'
    $Start.UseShellExecute = $false
    $Start.CreateNoWindow = $true
    $Start.RedirectStandardOutput = $true
    $Start.RedirectStandardError = $true
    $Start.WorkingDirectory = $PackageRoot
    $Start.EnvironmentVariables['CODEX_TEST_INSTRUCTIONS_LAUNCHER'] = $LauncherPath
    $Start.EnvironmentVariables['CODEX_TEST_INSTRUCTIONS_PACKAGE'] = $PackageRoot
    $Start.EnvironmentVariables['CODEX_TEST_INSTRUCTIONS_INPUT'] = $InputPath
    $Start.EnvironmentVariables['CODEX_HOME'] = Join-Path $PackageRoot 'home'
    $Start.EnvironmentVariables['POWERSHELL_TELEMETRY_OPTOUT'] = '1'
    foreach ($Name in @('TEMP', 'TMP', 'TMPDIR', 'HOME', 'USERPROFILE',
                        'APPDATA', 'LOCALAPPDATA', 'XDG_CONFIG_HOME',
                        'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME')) {
        $Start.EnvironmentVariables[$Name] = $RuntimeDirectory
    }
    if ($RunningOnWindows) {
        $Start.EnvironmentVariables['HOMEDRIVE'] = $RuntimeDirectory.Substring(0, 2)
        $Start.EnvironmentVariables['HOMEPATH'] = $RuntimeDirectory.Substring(2)
    }
    $Start.EnvironmentVariables['PSModulePath'] = Join-Path $PSHOME 'Modules'
    $Start.EnvironmentVariables['PSModuleAnalysisCachePath'] = Join-Path $RuntimeDirectory 'ModuleAnalysisCache'
    $Process = New-Object Diagnostics.Process
    $Process.StartInfo = $Start
    try {
        [void]$Process.Start()
        $StdoutTask = $Process.StandardOutput.ReadToEndAsync()
        $StderrTask = $Process.StandardError.ReadToEndAsync()
        if (-not $Process.WaitForExit(30000)) {
            $Process.Kill()
            $Process.WaitForExit()
            throw 'The isolated instruction-path test exceeded 30 seconds.'
        }
        return [pscustomobject]@{
            ExitCode = $Process.ExitCode
            Output = $StdoutTask.GetAwaiter().GetResult() + $StderrTask.GetAwaiter().GetResult()
        }
    } finally {
        $Process.Dispose()
    }
}

# Refuse pre-existing links anywhere from tmp up through the repository's
# ancestors before creating a fixture. A lexical repository-local path alone
# does not prevent a redirected tmp directory from writing outside the package.
$FixtureAncestor = $FixtureBase
while (-not [string]::IsNullOrWhiteSpace($FixtureAncestor)) {
    $FixtureItem = $null
    try {
        $FixtureItem = Get-Item -LiteralPath $FixtureAncestor -Force -ErrorAction Stop
    } catch [System.Management.Automation.ItemNotFoundException] {
        # The repository-local tmp directory may not exist yet.
    }
    if ($null -ne $FixtureItem -and (
        -not $FixtureItem.PSIsContainer -or
        ($FixtureItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
        throw "Unsafe test fixture directory: $FixtureAncestor"
    }
    $FixtureAncestor = Split-Path -Parent $FixtureAncestor
}
$null = New-Item -ItemType Directory -Path $FixtureBase -Force

try {
    $null = New-Item -ItemType Directory -Path $FixtureRoot
    $FixtureCreated = $true
    $WorkerPath = Join-Path $FixtureRoot 'worker.ps1'
    [IO.File]::WriteAllText($WorkerPath, $WorkerSource, (New-Object Text.UTF8Encoding($true)))
    foreach ($Case in @('ordinary', 'hardlink', 'symlink')) {
        $CaseRoot = Join-Path $FixtureRoot $Case
        $PackageRoot = Join-Path $CaseRoot 'package'
        $HomeDirectory = Join-Path $PackageRoot 'home'
        $null = New-Item -ItemType Directory -Path $HomeDirectory -Force
        $ChildRuntime = Join-Path $CaseRoot 'runtime'
        $null = New-Item -ItemType Directory -Path $ChildRuntime
        $InputPath = Join-Path $HomeDirectory 'instructions.md'
        $GeneratedPath = Join-Path $HomeDirectory 'codex-runtime-instructions.generated.md'
        $Marker = 'Synthetic instruction marker for ' + $Case
        if ($Case -eq 'ordinary') {
            [IO.File]::WriteAllText($InputPath, $Marker, (New-Object Text.UTF8Encoding($false)))
        } else {
            $ExternalTarget = Join-Path $CaseRoot 'external-source.txt'
            [IO.File]::WriteAllText($ExternalTarget, $Marker, (New-Object Text.UTF8Encoding($false)))
            $LinkKind = if ($Case -eq 'hardlink') { 'HardLink' } else { 'SymbolicLink' }
            try {
                $null = New-Item -ItemType $LinkKind -Path $InputPath -Target $ExternalTarget -ErrorAction Stop
            } catch {
                throw "Cannot create $LinkKind fixture. Windows symbolic-link creation requires Developer Mode or suitable privileges. $($_.Exception.Message)"
            }
            $LinkItem = Get-Item -LiteralPath $InputPath -Force
            if ([string]$LinkItem.LinkType -ne $LinkKind) { throw "Expected a real $LinkKind fixture" }
        }

        # A separate process preserves the production exit statements. In
        # particular, hardlink rejection must return exit 3 without reaching
        # either ReadAllText or the generated-file writer.
        $WorkerResult = Invoke-InstructionWorker -PackageRoot $PackageRoot -InputPath $InputPath -RuntimeDirectory $ChildRuntime
        $ExitCode = $WorkerResult.ExitCode
        $ExpectedExit = if ($Case -eq 'ordinary') { 0 } elseif ($Case -eq 'symlink' -and $RunningOnWindows) { 1 } else { 3 }
        # Windows rejects symlinks earlier in Assert-PortablePath (exit 1).
        # Linux's lexical path adapter leaves rejection to the real regular
        # input guard (exit 3); neither case may generate model instructions.
        if ($ExitCode -ne $ExpectedExit) {
            throw "$Case expected exit $ExpectedExit, got $ExitCode. $($WorkerResult.Output)"
        }
        if ($Case -eq 'ordinary') {
            $GeneratedText = [IO.File]::ReadAllText($GeneratedPath)
            if (-not $GeneratedText.Contains($Marker) -or -not $GeneratedText.Contains('fixture-model')) {
                throw 'Ordinary instructions did not retain input and runtime model identity'
            }
        } elseif (Test-Path -LiteralPath $GeneratedPath) {
            throw "$Case unexpectedly generated model instructions"
        }
        $Passed++
        Write-Output "PASS $Case instruction input (exit $ExitCode)"
    }
    Write-Output "$Passed instruction-path tests passed."
} finally {
    if ($FixtureCreated -and (Test-Path -LiteralPath $FixtureRoot)) {
        Remove-Item -LiteralPath $FixtureRoot -Recurse -Force
    }
}
