#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    Write-Output 'SKIP bootstrap path behavior: requires Windows cmd.exe, NTFS junctions, and Windows PowerShell 5.1.'
    exit 0
}

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$FixtureBase = Join-Path $RepositoryRoot 'tmp'
$FixtureRoot = Join-Path $FixtureBase ('bootstrap-paths-' + [guid]::NewGuid().ToString('N'))
$FixtureCreated = $false
$Junctions = New-Object 'System.Collections.Generic.List[string]'
$CmdPath = Join-Path $env:SystemRoot 'System32\cmd.exe'
$BatFiles = @(Get-ChildItem -LiteralPath $RepositoryRoot -Filter '*.bat' -File)
if ($BatFiles.Count -ne 5) { throw 'Expected exactly five root BAT entry points' }
$Passed = 0

# Run only copied BAT files and this synthetic target. No real launcher,
# authentication, configuration, cleanup script, or client executable runs.
$TargetSource = @'
$ErrorActionPreference = 'Stop'
[IO.File]::WriteAllText($env:CODEX_BOOTSTRAP_TEST_MARKER, 'synthetic-target-ran')
exit 0
'@

function Invoke-BootstrapFixture {
    param([string]$BatPath, [string]$MarkerPath, [string]$RuntimeDirectory)
    $Start = New-Object Diagnostics.ProcessStartInfo
    $Start.FileName = $CmdPath
    # /d disables host AutoRun; /v:off preserves literal ! in package paths.
    # A nonempty argument suppresses interactive menus and pauses in all BATs.
    $Start.Arguments = '/d /e:on /v:off /s /c ""' + $BatPath + '" --fixture"'
    $Start.UseShellExecute = $false
    $Start.CreateNoWindow = $true
    $Start.RedirectStandardOutput = $true
    $Start.RedirectStandardError = $true
    $Start.WorkingDirectory = $FixtureRoot
    $Start.EnvironmentVariables['CODEX_BOOTSTRAP_TEST_MARKER'] = $MarkerPath
    $Start.EnvironmentVariables['POWERSHELL_TELEMETRY_OPTOUT'] = '1'
    foreach ($Name in @('TEMP', 'TMP', 'TMPDIR', 'HOME', 'USERPROFILE',
                        'APPDATA', 'LOCALAPPDATA', 'XDG_CONFIG_HOME',
                        'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME')) {
        $Start.EnvironmentVariables[$Name] = $RuntimeDirectory
    }
    $Start.EnvironmentVariables['HOMEDRIVE'] = $RuntimeDirectory.Substring(0, 2)
    $Start.EnvironmentVariables['HOMEPATH'] = $RuntimeDirectory.Substring(2)
    $Start.EnvironmentVariables['PSModuleAnalysisCachePath'] = Join-Path $RuntimeDirectory 'ModuleAnalysisCache'
    $Start.EnvironmentVariables['PSModulePath'] = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\Modules'
    $Process = New-Object Diagnostics.Process
    $Process.StartInfo = $Start
    try {
        [void]$Process.Start()
        $StdoutTask = $Process.StandardOutput.ReadToEndAsync()
        $StderrTask = $Process.StandardError.ReadToEndAsync()
        if (-not $Process.WaitForExit(30000)) {
            # Kill this owned cmd.exe tree, not only cmd: its PowerShell child
            # otherwise keeps the fixture and redirected pipes open. Retain the
            # Process handle until cleanup finishes; never discover other PIDs.
            if (-not $Process.HasExited) {
                $TreeStop = New-Object Diagnostics.Process
                $TreeStop.StartInfo = New-Object Diagnostics.ProcessStartInfo
                $TreeStop.StartInfo.FileName = Join-Path $env:SystemRoot 'System32\taskkill.exe'
                $TreeStop.StartInfo.Arguments = '/PID ' + $Process.Id + ' /T /F'
                $TreeStop.StartInfo.UseShellExecute = $false
                $TreeStop.StartInfo.CreateNoWindow = $true
                $TreeStop.StartInfo.RedirectStandardOutput = $true
                $TreeStop.StartInfo.RedirectStandardError = $true
                try {
                    [void]$TreeStop.Start()
                    $StopOutput = $TreeStop.StandardOutput.ReadToEndAsync()
                    $StopError = $TreeStop.StandardError.ReadToEndAsync()
                    if (-not $TreeStop.WaitForExit(10000)) {
                        # This process is also owned by the fixture.
                        try { $TreeStop.Kill() } catch {
                            if (-not $TreeStop.HasExited) { throw }
                        }
                        [void]$TreeStop.WaitForExit(5000)
                        throw 'Timed out stopping the owned BAT process tree.'
                    }
                    # A nonzero taskkill code is harmless when the original
                    # process exited between HasExited and taskkill startup.
                    if (-not $Process.WaitForExit(5000)) {
                        throw 'The owned BAT process tree could not be stopped.'
                    }
                    if (-not $StdoutTask.Wait(5000) -or -not $StderrTask.Wait(5000)) {
                        throw 'Owned BAT child pipes remained open after tree cleanup.'
                    }
                } finally {
                    $TreeStop.Dispose()
                }
            }
            throw 'The isolated BAT test exceeded 30 seconds; its owned process tree was stopped.'
        }
        return [pscustomobject]@{
            ExitCode = $Process.ExitCode
            Output = $StdoutTask.GetAwaiter().GetResult() + $StderrTask.GetAwaiter().GetResult()
        }
    } finally {
        $Process.Dispose()
    }
}

# Verify tmp and its ancestors before any fixture writes. Get-Item exposes
# dangling links too; only a missing path is allowed to be created later.
$FixtureAncestor = $FixtureBase
while (-not [string]::IsNullOrWhiteSpace($FixtureAncestor)) {
    $Item = $null
    try {
        $Item = Get-Item -LiteralPath $FixtureAncestor -Force -ErrorAction Stop
    } catch [System.Management.Automation.ItemNotFoundException] {}
    if ($null -ne $Item -and (
        -not $Item.PSIsContainer -or
        ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
        throw "Unsafe test fixture directory: $FixtureAncestor"
    }
    $FixtureAncestor = Split-Path -Parent $FixtureAncestor
}
$null = New-Item -ItemType Directory -Path $FixtureBase -Force

try {
    $null = New-Item -ItemType Directory -Path $FixtureRoot
    $FixtureCreated = $true
    $Index = 0
    foreach ($BatFile in $BatFiles) {
        $Index++
        foreach ($Variant in @('ordinary', 'root-junction', 'ancestor-junction')) {
            $CaseRoot = Join-Path $FixtureRoot ("$Index-$Variant space !")
            $ActualAncestor = Join-Path $CaseRoot 'actual ancestor !'
            $PackageRoot = Join-Path $ActualAncestor 'package space !'
            $null = New-Item -ItemType Directory -Path $PackageRoot -Force
            $RuntimeDirectory = Join-Path $CaseRoot 'runtime'
            $null = New-Item -ItemType Directory -Path $RuntimeDirectory
            $MarkerPath = Join-Path $PackageRoot 'target-ran.marker'
            $CopiedBat = Join-Path $PackageRoot $BatFile.Name
            [IO.File]::Copy($BatFile.FullName, $CopiedBat)
            # The two launcher BATs use run-codex.ps1; the login checker uses
            # login-json.ps1; other entry points use their matching basename.
            $TargetNames = @(
                'run-codex.ps1',
                'login-json.ps1',
                [IO.Path]::ChangeExtension($BatFile.Name, '.ps1')
            ) | Select-Object -Unique
            foreach ($TargetName in $TargetNames) {
                [IO.File]::WriteAllText(
                    (Join-Path $PackageRoot $TargetName),
                    $TargetSource,
                    (New-Object Text.UTF8Encoding($true))
                )
            }

            $LaunchRoot = $PackageRoot
            if ($Variant -eq 'root-junction') {
                $JunctionPath = Join-Path $CaseRoot 'linked package !'
                $null = New-Item -ItemType Junction -Path $JunctionPath -Target $PackageRoot
                $Junctions.Add($JunctionPath)
                $LaunchRoot = $JunctionPath
            } elseif ($Variant -eq 'ancestor-junction') {
                $JunctionPath = Join-Path $CaseRoot 'linked ancestor !'
                $null = New-Item -ItemType Junction -Path $JunctionPath -Target $ActualAncestor
                $Junctions.Add($JunctionPath)
                $LaunchRoot = Join-Path $JunctionPath 'package space !'
            }

            $Result = Invoke-BootstrapFixture -BatPath (Join-Path $LaunchRoot $BatFile.Name) -MarkerPath $MarkerPath -RuntimeDirectory $RuntimeDirectory
            if ($Variant -eq 'ordinary') {
                if ($Result.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $MarkerPath -PathType Leaf)) {
                    throw "$($BatFile.Name) ordinary path failed ($($Result.ExitCode)): $($Result.Output)"
                }
                if ([IO.File]::ReadAllText($MarkerPath) -ne 'synthetic-target-ran') {
                    throw 'Unexpected synthetic target marker'
                }
            } else {
                if ($Result.ExitCode -ne 3) {
                    throw "$($BatFile.Name) $Variant expected exit 3, got $($Result.ExitCode): $($Result.Output)"
                }
                if (Test-Path -LiteralPath $MarkerPath) { throw "$Variant executed the target script" }
                # These are the BAT's pre-PowerShell mkdir destinations. None
                # may be created through either root or ancestor junctions.
                foreach ($Name in @('home', 'sqlite', 'tmp', 'home-runtime', 'appdata',
                                    'localappdata', 'programdata', 'cache', 'login_json', 'tool')) {
                    if (Test-Path -LiteralPath (Join-Path $PackageRoot $Name)) {
                        throw "$($BatFile.Name) $Variant wrote package directory '$Name' before rejecting the link"
                    }
                }
            }
            $Passed++
            Write-Output "PASS $($BatFile.Name) $Variant"
        }
    }
    Write-Output "$Passed Windows bootstrap-path tests passed."
} finally {
    # Remove owned junction names without recursion before deleting synthetic
    # trees. In particular, do not let PS5.1 recursive cleanup follow junctions.
    foreach ($JunctionPath in $Junctions) {
        $Item = Get-Item -LiteralPath $JunctionPath -Force -ErrorAction Stop
        if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) {
            throw "Expected owned junction during cleanup: $JunctionPath"
        }
        [IO.Directory]::Delete($JunctionPath)
    }
    if ($FixtureCreated -and (Test-Path -LiteralPath $FixtureRoot)) {
        Remove-Item -LiteralPath $FixtureRoot -Recurse -Force
    }
}
