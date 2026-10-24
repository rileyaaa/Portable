#Requires -Version 5.1
# Exercise the real process supervisor with synthetic package-local children.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $root 'tool/automation/portable-automation.ps1')
. (Join-Path $root 'tool/portable-process.ps1')
[void](New-AutomationDirectory -Root $root -Path (Join-Path $root 'tmp'))
$fixture = New-AutomationDirectory -Root $root -Path (Join-Path $root ('tmp\automation-process-' + [Guid]::NewGuid().ToString('N')))
$process = $null
try {
    # The production automation initializer must safely bootstrap a fresh tmp.
    $fresh = New-AutomationDirectory -Root $root -Path (Join-Path $fixture 'fresh package')
    $freshTool = New-AutomationDirectory -Root $root -Path (Join-Path $fresh 'tool')
    Copy-Item -LiteralPath (Join-Path $root 'tool/portable-process.ps1') -Destination $freshTool
    $freshTmp = Join-Path $fresh 'tmp'
    if (Test-Path -LiteralPath $freshTmp) { throw 'Fresh fixture unexpectedly contains tmp.' }
    Initialize-AutomationSupervisor -Root $fresh
    [void](Assert-AutomationPath -Root $fresh -Path $freshTmp -Directory)
    [IO.Directory]::Delete($freshTmp, $false)
    $linkedTarget = New-AutomationDirectory -Root $root -Path (Join-Path $fixture 'link-target')
    $linkType = 'SymbolicLink'
    if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) { $linkType = 'Junction' }
    [void](New-Item -ItemType $linkType -Path $freshTmp -Target $linkedTarget)
    try {
        $rejected = $false
        try { Initialize-AutomationSupervisor -Root $fresh } catch { $rejected = $true }
        if (-not $rejected) { throw 'Supervisor must refuse a linked tmp before compiler startup.' }
        if (@(Get-ChildItem -LiteralPath $linkedTarget -Force).Count -ne 0) { throw 'Supervisor wrote through a linked tmp.' }
    } finally { [IO.Directory]::Delete($freshTmp, $false) }
    Write-Output 'PASS fresh package supervisor creates tmp and refuses linked scratch'
    # Compiling the production C# does not call its Windows APIs.
    Initialize-PortableProcessJob -PackageRoot $root
    Write-Output 'PASS production process supervisor C# compiles'
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        Write-Output 'SKIP actual inherited/captured stdio requires Windows'
        return
    }
    $utf8 = New-Object Text.UTF8Encoding($false)
    $wrapper = Join-Path $fixture 'wrapper.ps1'
    $child = Join-Path $fixture 'child.cjs'
    $trace = Join-Path $fixture 'synthetic-child.json'
    $node = Assert-AutomationPath -Root $root -Path (Join-Path $root 'tool\node\node.exe')
    $powershell = Join-Path ([Environment]::GetFolderPath('Windows')) 'System32\WindowsPowerShell\v1.0\powershell.exe'
    function Get-SyntheticIODiagnostic($ExitCode, [string]$StdOut, [string]$StdErr) {
        # This test launches only the fixed synthetic child below. Never use this
        # diagnostic helper for a real browser, account or arbitrary command.
        $childTrace = 'not-started'
        if (Test-Path -LiteralPath $trace -PathType Leaf) {
            [void](Assert-AutomationPath -Root $fixture -Path $trace)
            $childTrace = [IO.File]::ReadAllText($trace)
        }
        return ([PSCustomObject]@{
            ExitCode = $ExitCode; StdOutLength = $StdOut.Length; StdErrLength = $StdErr.Length
            StdOut = $StdOut.Substring(0, [Math]::Min($StdOut.Length, 4096))
            StdErr = $StdErr.Substring(0, [Math]::Min($StdErr.Length, 4096)); ChildTrace = $childTrace
        } | ConvertTo-Json -Compress)
    }
    [IO.File]::WriteAllText($child, @'
const fs = require('node:fs');
const trace = process.argv[2];
const state = {started: true, stdinType: fs.fstatSync(0).mode, received: 0, eof: false, responseFlushed: false};
const record = () => { if (trace) fs.writeFileSync(trace, JSON.stringify(state)); };
record();
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('end', () => { state.eof = true; record(); });
process.stdin.on('error', error => { state.stdinError = error.code; record(); });
process.stdin.on('data', value => {
  input += value;
  state.received += Buffer.byteLength(value, 'utf8');
  record();
  if (input.includes('\n')) {
    // Wait for both pipe writes; process.exit can otherwise truncate async IO.
    process.stdout.write(JSON.stringify({echo: input.trim()}), () => {
      process.stderr.write('synthetic-stderr', () => {
        state.responseFlushed = true; record(); process.exit(0);
      });
    });
  }
});
'@, $utf8)
    [IO.File]::WriteAllText($wrapper, @'
param([string]$Root, [string]$Fixture, [string]$Child, [string]$Node, [string]$Trace)
$ErrorActionPreference = 'Stop'
. (Join-Path $Root 'tool/automation/portable-automation.ps1')
Initialize-AutomationSupervisor -Root $Root
$start = New-AutomationStartInfo -Root $Root -FilePath $Node -WorkingDirectory $Fixture -Arguments @($Child, $Trace) -SessionDirectory $Fixture
$result = Invoke-PortableProcess -StartInfo $start -PackageRoot $Root -TimeoutMs 15000
exit $result.ExitCode
'@, $utf8)
    # A real redirected parent -> noncapturing supervisor -> Node chain, matching
    # MCP launch semantics. Old CreateProcessW(false) loses these parent pipes.
    $start = New-AutomationStartInfo -Root $root -FilePath $powershell -WorkingDirectory $fixture -SessionDirectory $fixture -WindowsPowerShell -CaptureOutput -Arguments @(
        '-NoLogo','-NoProfile','-NonInteractive','-File',$wrapper,
        '-Root',$root,'-Fixture',$fixture,'-Child',$child,'-Node',$node,'-Trace',$trace)
    $start.StandardOutputEncoding = $utf8
    $start.StandardErrorEncoding = $utf8
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $start
    [void]$process.Start()
    $out = $process.StandardOutput.ReadToEndAsync()
    $err = $process.StandardError.ReadToEndAsync()
    $process.StandardInput.WriteLine('portable-stdio')
    $process.StandardInput.Close()
    if (-not $process.WaitForExit(60000)) { throw 'Inherited stdio regression timed out.' }
    $stdout = $out.GetAwaiter().GetResult()
    $stderr = $err.GetAwaiter().GetResult()
    if ($process.ExitCode -ne 0 -or $stdout -cne '{"echo":"portable-stdio"}' -or $stderr -cne 'synthetic-stderr') {
        throw ('Inherited stdio mismatch: ' + (Get-SyntheticIODiagnostic $process.ExitCode $stdout $stderr))
    }
    Write-Output 'PASS inherited MCP-style stdin/stdout/stderr through supervised child'
    $start = New-AutomationStartInfo -Root $root -FilePath $node -WorkingDirectory $fixture -SessionDirectory $fixture -CaptureOutput -Arguments @($child, $trace)
    $result = Invoke-PortableProcess -StartInfo $start -PackageRoot $root -TimeoutMs 15000 -InputText "captured-stdio`n"
    if ($result.ExitCode -ne 0 -or $result.StdOut -cne '{"echo":"captured-stdio"}' -or $result.StdErr -cne 'synthetic-stderr') {
        throw ('Captured stdio mismatch: ' + (Get-SyntheticIODiagnostic $result.ExitCode $result.StdOut $result.StdErr))
    }
    Write-Output 'PASS captured stdin/stdout/stderr remains functional'
} finally {
    if ($null -ne $process) {
        try { if (-not $process.HasExited) { $process.Kill(); [void]$process.WaitForExit(5000) } } catch {}
        $process.Dispose()
    }
    Remove-AutomationSession -Root $root -Path $fixture
}
