#Requires -Version 5.1
# Real launcher validation, synthetic release files, no native EXE execution.
$ErrorActionPreference = 'Stop'
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$FixtureBase = Join-Path $RepositoryRoot 'tmp'
$FixtureRoot = Join-Path $FixtureBase ('runtime-preflight-' + [Guid]::NewGuid().ToString('N'))
$Engine = [Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
$Utf8 = New-Object Text.UTF8Encoding($false)
$Passed = 0
$RunningOnWindows = [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
$Cursor = $FixtureBase
while (-not [string]::IsNullOrWhiteSpace($Cursor)) {
    $Item = Get-Item -LiteralPath $Cursor -Force -ErrorAction SilentlyContinue
    if ($null -ne $Item -and (-not $Item.PSIsContainer -or ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint))) {
        throw 'Unsafe test fixture ancestor.'
    }
    $Cursor = Split-Path -Parent $Cursor
}
$WorkerSource = @'
$ErrorActionPreference = 'Stop'
$Tokens = $null; $Errors = $null
$Ast = [Management.Automation.Language.Parser]::ParseFile($env:TEST_RUNTIME_LAUNCHER, [ref]$Tokens, [ref]$Errors)
if ($Errors.Count) { throw 'Launcher parse failure.' }
foreach ($Name in @('Test-IsUnderDirectory','Assert-PortablePath','Assert-PortableRegularInputFile','Assert-PinnedRuntimePackage')) {
    $Function = @($Ast.FindAll({ param($Node) $Node -is [Management.Automation.Language.FunctionDefinitionAst] }, $true) | Where-Object { $_.Name -eq $Name })
    if ($Function.Count -ne 1) { throw 'Missing runtime validation function.' }
    . ([scriptblock]::Create($Function[0].Extent.Text))
}
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    # Linux adapter for Windows path separators only. Regular-file/link guards,
    # manifest pinning, payload hashing and cache freshness logic stay real.
    function Test-IsUnderDirectory {
        param([string]$Path, [string]$Directory)
        $Full = [IO.Path]::GetFullPath($Path)
        $Base = [IO.Path]::GetFullPath($Directory).TrimEnd('/')
        return $Full -eq $Base -or $Full.StartsWith($Base + '/', [StringComparison]::Ordinal)
    }
}
$Root = $env:TEST_RUNTIME_ROOT
$ExpectedRuntimeManifestSha256 = $env:TEST_RUNTIME_MANIFEST_HASH
$ExpectedCodexVersion = '0.164.0'
Assert-PinnedRuntimePackage
Write-Output 'preflight-ok'
'@
try {
    [void][IO.Directory]::CreateDirectory($FixtureRoot)
    $Worker = Join-Path $FixtureRoot 'worker.ps1'
    [IO.File]::WriteAllText($Worker, $WorkerSource, $Utf8)
    foreach ($Case in @('valid','metadata-tamper','manifest-tamper','resource-tamper','missing-resource','hardlink-resource','symlink-resource','fresh-cache-tamper','stale-cache','state-hardlink')) {
        $CaseRoot = Join-Path $FixtureRoot $Case
        $Package = Join-Path $CaseRoot ('portable ' + [char]0x4FBF + [char]0x643A)
        [void][IO.Directory]::CreateDirectory((Join-Path $Package 'tool'))
        [void][IO.Directory]::CreateDirectory((Join-Path $Package 'codex-resources'))
        [void][IO.Directory]::CreateDirectory((Join-Path $Package 'home/.sandbox-bin'))
        $Files = [ordered]@{}
        foreach ($Relative in @('codex.exe','codex-command-runner.exe','codex-package.json','codex-resources/codex-command-runner.exe')) {
            $Path = Join-Path $Package $Relative
            [IO.File]::WriteAllText($Path, ('synthetic runtime ' + $Relative), $Utf8)
            $Files[$Relative] = @{ sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
        }
        $Manifest = Join-Path $Package 'tool/runtime-manifest.json'
        [IO.File]::WriteAllText($Manifest, (@{version='0.164.0';target='x86_64-pc-windows-msvc';files=$Files} | ConvertTo-Json -Depth 8), $Utf8)
        $ManifestHash = (Get-FileHash -LiteralPath $Manifest -Algorithm SHA256).Hash
        $Resource = Join-Path $Package 'codex-resources/codex-command-runner.exe'
        $ExpectedSuccess = $Case -in @('valid','stale-cache')
        switch ($Case) {
            'metadata-tamper' { [IO.File]::WriteAllText((Join-Path $Package 'codex-package.json'), '{}', $Utf8) }
            'manifest-tamper' { [IO.File]::WriteAllText($Manifest, 'untrusted invalid JSON', $Utf8) }
            'resource-tamper' { [IO.File]::WriteAllText($Resource, 'changed', $Utf8) }
            'missing-resource' { [IO.File]::Delete($Resource) }
            { $_ -in @('hardlink-resource','symlink-resource') } {
                $Outside = Join-Path $CaseRoot 'outside-synthetic.exe'
                [IO.File]::WriteAllText($Outside, 'synthetic external bytes', $Utf8)
                [IO.File]::Delete($Resource)
                $Kind = if ($Case -eq 'hardlink-resource') { 'HardLink' } else { 'SymbolicLink' }
                [void](New-Item -ItemType $Kind -Path $Resource -Target $Outside)
            }
            { $_ -in @('fresh-cache-tamper','stale-cache') } {
                $Source = Join-Path $Package 'codex-command-runner.exe'
                $Cache = Join-Path $Package 'home/.sandbox-bin/codex-command-runner-0.164.0.exe'
                $Length = (Get-Item -LiteralPath $Source).Length
                [IO.File]::WriteAllText($Cache, (('X' * $Length) -join ''), $Utf8)
                [IO.File]::SetLastWriteTimeUtc($Cache, [DateTime]::UtcNow.AddDays($(if ($Case -eq 'stale-cache') { -1 } else { 1 })))
            }
            'state-hardlink' {
                $Outside = Join-Path $CaseRoot 'synthetic-secret.txt'
                [IO.File]::WriteAllText($Outside, 'synthetic; never read by validator', $Utf8)
                [void][IO.Directory]::CreateDirectory((Join-Path $Package 'home/.sandbox-secrets'))
                [void](New-Item -ItemType HardLink -Path (Join-Path $Package 'home/.sandbox-secrets/sandbox_users.json') -Target $Outside)
            }
        }
        $Start = New-Object Diagnostics.ProcessStartInfo
        $Start.FileName = $Engine
        $Start.Arguments = '-NoLogo -NoProfile -NonInteractive -File "' + $Worker + '"'
        $Start.UseShellExecute = $false
        $Start.RedirectStandardOutput = $true; $Start.RedirectStandardError = $true
        $Start.WorkingDirectory = $FixtureRoot
        $Start.EnvironmentVariables['TEST_RUNTIME_LAUNCHER'] = Join-Path $RepositoryRoot 'run-codex.ps1'
        $Start.EnvironmentVariables['TEST_RUNTIME_ROOT'] = $Package
        $Start.EnvironmentVariables['TEST_RUNTIME_MANIFEST_HASH'] = $ManifestHash
        $Runtime = Join-Path $CaseRoot 'child-state'
        [void][IO.Directory]::CreateDirectory($Runtime)
        foreach ($Name in @('HOME','USERPROFILE','TEMP','TMP','TMPDIR','APPDATA','LOCALAPPDATA','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_STATE_HOME')) { $Start.EnvironmentVariables[$Name] = $Runtime }
        $Start.EnvironmentVariables['PSModuleAnalysisCachePath'] = Join-Path $Runtime 'ModuleAnalysisCache'
        $Start.EnvironmentVariables['POWERSHELL_TELEMETRY_OPTOUT'] = '1'
        $Process = New-Object Diagnostics.Process
        $Process.StartInfo = $Start
        try {
            [void]$Process.Start()
            $Output = $Process.StandardOutput.ReadToEndAsync(); $ErrorOutput = $Process.StandardError.ReadToEndAsync()
            if (-not $Process.WaitForExit(60000)) { $Process.Kill(); throw 'Runtime preflight test timeout.' }
            $StdOut = $Output.GetAwaiter().GetResult(); $StdErr = $ErrorOutput.GetAwaiter().GetResult()
            if (($Process.ExitCode -eq 0) -ne $ExpectedSuccess) { throw "$Case unexpected exit $($Process.ExitCode): $StdOut $StdErr" }
            if ($ExpectedSuccess -and $StdOut.Trim() -ne 'preflight-ok') { throw "$Case did not finish validation." }
            if ($Case -eq 'manifest-tamper' -and $StdErr -notmatch 'Runtime manifest does not match') { throw 'Unpinned manifest reached JSON parsing.' }
        } finally { $Process.Dispose() }
        $Passed++
        Write-Output "PASS $Case"
    }
    Write-Output "$Passed runtime preflight tests passed; no native client was executed."
} finally {
    # All links point to synthetic siblings owned by this single test invocation.
    if (Test-Path -LiteralPath $FixtureRoot) { Remove-Item -LiteralPath $FixtureRoot -Recurse -Force }
}
