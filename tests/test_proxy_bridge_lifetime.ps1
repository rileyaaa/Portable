#Requires -Version 5.1
# Windows bridge lifetime regression. Start the real bundled bridge through
# the exact production launcher functions. Use only a synthetic loopback
# endpoint; never send model requests or use actual proxy configuration.
param([string]$BaselineCommit = '', [switch]$Child, [string]$ReadyPath = '', [switch]$NormalStop)
$ErrorActionPreference = 'Stop'
$Root=Split-Path -Parent $PSScriptRoot
$PortableWindowsRoot=[Environment]::GetFolderPath('Windows')
function Assert-Case { param([bool]$Condition,[string]$Message) if (-not $Condition) { throw $Message } }
function Get-Source {
    if ($BaselineCommit) {
        if ($BaselineCommit -notmatch '^[a-f0-9]{40}$') { throw 'Invalid baseline commit.' }
        $lines=& git -C $Root show ($BaselineCommit+':run-codex.ps1')
        if ($LASTEXITCODE -ne 0) { throw 'Unable to read baseline source.' }
        return ($lines -join "`n")
    }
    return [IO.File]::ReadAllText((Join-Path $Root 'run-codex.ps1'))
}
$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseInput((Get-Source),[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'Launcher source parse failed.' }
$definitions=@($ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]},$true))
foreach ($name in @('Test-IsUnderDirectory','Assert-PortablePath','Assert-PortableRegularInputFile',
    'Convert-ToTomlBool','Reset-CodexTrustedSystemEnvironment','Set-ProcessEnvironmentValue',
    'ConvertTo-WindowsCommandLineArgument','Import-CodexProcessSupervisor','Format-HostForUri',
    'Test-TcpPortOpen','Start-CodexSocksHttpBridge','Stop-CodexSocksHttpBridge')) {
    $node=@($definitions | Where-Object Name -eq $name)
    if ($node.Count -ne 1) {throw ('Missing production function: '+$name)}
    . ([scriptblock]::Create($node[0].Extent.Text))
}
if ($Child) {
    Assert-PortablePath 'synthetic ready marker' $ReadyPath
    $env:CODEX_PROXY_HTTP_BRIDGE='true'
    $env:CODEX_PROXY_BRIDGE_HOST='127.0.0.1'
    $env:CODEX_PROXY_BRIDGE_PORT=''
    $env:PATH=Join-Path $PortableWindowsRoot 'System32'
    $env:TEMP=Split-Path -Parent $ReadyPath
    $env:TMP=$env:TEMP
    $env:HOME=$env:TEMP
    $env:USERPROFILE=$env:TEMP
    $script:CodexProxyBridgeProcess=$null
    $script:CodexProxyBridgeJob=$null
    try {
        $url=Start-CodexSocksHttpBridge -SocksHost '127.0.0.1' -SocksPort '1'
        $port=([uri]$url).Port
        # The parent identifies only this owned listener by PID and executable,
        # never dumps the URL, environment, token, or process command line.
        [IO.File]::WriteAllText($ReadyPath,[string]$port)
        if ($NormalStop) {
            # Allow the controller to observe the live listener first.
            $ack=$ReadyPath+'.ack'
            $watch=[Diagnostics.Stopwatch]::StartNew()
            while (-not [IO.File]::Exists($ack)) {
                if ($watch.ElapsedMilliseconds -gt 15000) {throw 'Controller acknowledgement timed out.'}
                Start-Sleep -Milliseconds 50
            }
            Stop-CodexSocksHttpBridge
            Stop-CodexSocksHttpBridge
            return
        }
        Start-Sleep -Seconds 60
    } finally { Stop-CodexSocksHttpBridge }
    return
}
# Work only beneath a uniquely owned synthetic test directory.
. (Join-Path $Root 'tool/automation/portable-automation.ps1')
[void](New-AutomationDirectory -Root $Root -Path (Join-Path $Root 'tmp'))
$fixture=New-AutomationDirectory -Root $Root -Path (Join-Path $Root ('tmp\proxy-bridge-lifetime-'+[guid]::NewGuid().ToString('N')))
$engine=Join-Path $PortableWindowsRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$expectedPython=Join-Path $Root 'tool\python\python.exe'
function Run-Case {
    param([bool]$Graceful)
    $ready=Join-Path $fixture ('ready-'+[guid]::NewGuid().ToString('N'))
    $start=New-Object Diagnostics.ProcessStartInfo
    $start.FileName=$engine
    $start.UseShellExecute=$false
    $start.CreateNoWindow=$true
    $start.WorkingDirectory=$Root
    $arguments=@('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$PSCommandPath,'-Child','-ReadyPath',$ready)
    if ($BaselineCommit) { $arguments+=@('-BaselineCommit',$BaselineCommit) }
    if ($Graceful) { $arguments+='-NormalStop' }
    $start.Arguments=($arguments | ForEach-Object {ConvertTo-WindowsCommandLineArgument ([string]$_)}) -join ' '
    $parentProcess=$null; $bridgeProcess=$null; $port=0
    try {
        $parentProcess=[Diagnostics.Process]::Start($start)
        $watch=[Diagnostics.Stopwatch]::StartNew()
        while (-not [IO.File]::Exists($ready)) {
            if ($parentProcess.HasExited -or $watch.ElapsedMilliseconds -gt 45000) {throw 'Owned bridge startup failed.'}
            Start-Sleep -Milliseconds 50
        }
        # The ready file is small and written once; wait for a complete value.
        while (-not [int]::TryParse([IO.File]::ReadAllText($ready),[ref]$port) -or $port -lt 1) {
            if ($watch.ElapsedMilliseconds -gt 45000) {throw 'Invalid ready marker.'}
            Start-Sleep -Milliseconds 50
        }
        Assert-Case (Test-TcpPortOpen -HostName '127.0.0.1' -Port $port) 'Bridge did not listen.'
        $listeners=@(Get-NetTCPConnection -State Listen -LocalAddress '127.0.0.1' -LocalPort $port -ErrorAction Stop)
        Assert-Case ($listeners.Count -eq 1) 'Cannot identify unique owned bridge listener.'
        $bridgeProcess=[Diagnostics.Process]::GetProcessById([int]$listeners[0].OwningProcess)
        Assert-Case ($bridgeProcess.Path -ieq $expectedPython) 'Listener is not the bundled synthetic bridge.'
        # Retain the process handle now, before any exit or PID reuse.
        $null=$bridgeProcess.Handle
        if ($Graceful) {
            [IO.File]::WriteAllText(($ready+'.ack'),'ok')
            Assert-Case ($parentProcess.WaitForExit(15000) -and $parentProcess.ExitCode -eq 0) 'Normal stop failed.'
            Assert-Case ($bridgeProcess.WaitForExit(5000)) 'Bridge survived graceful stop.'
            Write-Output 'PASS real bridge start, normal stop and repeated cleanup'
        } else {
            # Process.Kill() on .NET Framework kills only this PowerShell process,
            # not its child tree. No finally block can run in the killed owner.
            $parentProcess.Kill()
            Assert-Case ($parentProcess.WaitForExit(5000)) 'Could not terminate synthetic launcher.'
            $exited=$bridgeProcess.WaitForExit(3000)
            if ($BaselineCommit) {
                Assert-Case (-not $exited) 'Previous unmanaged bridge orphan did not reproduce.'
                Write-Output 'REPRODUCED old bridge survives forced termination of its owning launcher'
            } else {
                Assert-Case $exited 'Job-owned bridge survived owner termination.'
                Assert-Case (-not (Test-TcpPortOpen -HostName '127.0.0.1' -Port $port)) 'Bridge port remains open after owner termination.'
                Write-Output 'PASS actual bridge reclaimed after forced launcher termination'
            }
        }
    } finally {
        if ($null -ne $parentProcess) {
            try {if (-not $parentProcess.HasExited) {$parentProcess.Kill(); [void]$parentProcess.WaitForExit(5000)}} catch {}
            $parentProcess.Dispose()
        }
        if ($null -ne $bridgeProcess) {
            try {
                if (-not $bridgeProcess.HasExited -and $bridgeProcess.Path -ieq $expectedPython) {
                    $bridgeProcess.Kill(); [void]$bridgeProcess.WaitForExit(5000)
                }
            } finally {$bridgeProcess.Dispose()}
        }
    }
}
try {
    Run-Case -Graceful $false
    if (-not $BaselineCommit) { Run-Case -Graceful $true }
} finally {
    # The fixture contains only controller markers and no credentials.
    foreach ($item in @(Get-ChildItem -LiteralPath $fixture -Force)) {
        if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unexpected fixture child.' }
        [void](Assert-AutomationPath -Root $Root -Path $item.FullName)
        [IO.File]::Delete($item.FullName)
    }
    [IO.Directory]::Delete($fixture,$false)
}
