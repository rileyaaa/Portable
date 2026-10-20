#Requires -Version 5.1
# Exercise the real process supervisor with synthetic package-local children.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $root 'tool/automation/portable-automation.ps1')
. (Join-Path $root 'tool/portable-process.ps1')
[void](New-AutomationDirectory -Root $root -Path (Join-Path $root 'tmp'))
# Compiling the production C# does not call its Windows APIs.
Initialize-PortableProcessJob -PackageRoot $root
Write-Output 'PASS production process supervisor C# compiles'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    Write-Output 'SKIP actual inherited/captured stdio requires Windows'
    return
}
$fixture = New-AutomationDirectory -Root $root -Path (Join-Path $root ('tmp\automation-process-' + [Guid]::NewGuid().ToString('N')))
$utf8 = New-Object Text.UTF8Encoding($false)
$wrapper = Join-Path $fixture 'wrapper.ps1'
$child = Join-Path $fixture 'child.cjs'
$node = Assert-AutomationPath -Root $root -Path (Join-Path $root 'tool\node\node.exe')
$powershell = Join-Path ([Environment]::GetFolderPath('Windows')) 'System32\WindowsPowerShell\v1.0\powershell.exe'
$process = $null
try {
    [IO.File]::WriteAllText($child, @'
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', value => {
  input += value;
  if (input.includes('\n')) {
    process.stdout.write(JSON.stringify({echo: input.trim()}));
    process.stderr.write('synthetic-stderr');
    process.exit(0);
  }
});
'@, $utf8)
    [IO.File]::WriteAllText($wrapper, @'
param([string]$Root, [string]$Fixture, [string]$Child, [string]$Node)
$ErrorActionPreference = 'Stop'
. (Join-Path $Root 'tool/automation/portable-automation.ps1')
Initialize-AutomationSupervisor -Root $Root
$start = New-AutomationStartInfo -Root $Root -FilePath $Node -WorkingDirectory $Fixture -Arguments @($Child) -SessionDirectory $Fixture
$result = Invoke-PortableProcess -StartInfo $start -PackageRoot $Root -TimeoutMs 15000
exit $result.ExitCode
'@, $utf8)
    # A real redirected parent -> noncapturing supervisor -> Node chain, matching
    # MCP launch semantics. Old CreateProcessW(false) loses these parent pipes.
    $start = New-AutomationStartInfo -Root $root -FilePath $powershell -WorkingDirectory $fixture -SessionDirectory $fixture -WindowsPowerShell -CaptureOutput -Arguments @(
        '-NoLogo','-NoProfile','-NonInteractive','-File',$wrapper,
        '-Root',$root,'-Fixture',$fixture,'-Child',$child,'-Node',$node)
    $start.StandardOutputEncoding = $utf8
    $start.StandardErrorEncoding = $utf8
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $start
    [void]$process.Start()
    $out = $process.StandardOutput.ReadToEndAsync()
    $err = $process.StandardError.ReadToEndAsync()
    $process.StandardInput.WriteLine('portable-stdio')
    $process.StandardInput.Close()
    if (-not $process.WaitForExit(30000)) { throw 'Inherited stdio regression timed out.' }
    $stdout = $out.GetAwaiter().GetResult()
    $stderr = $err.GetAwaiter().GetResult()
    if ($process.ExitCode -ne 0 -or $stdout -cne '{"echo":"portable-stdio"}' -or $stderr -cne 'synthetic-stderr') {
        throw 'Inherited stdio did not preserve the synthetic request/response.'
    }
    Write-Output 'PASS inherited MCP-style stdin/stdout/stderr through supervised child'
    $start = New-AutomationStartInfo -Root $root -FilePath $node -WorkingDirectory $fixture -SessionDirectory $fixture -CaptureOutput -Arguments @($child)
    $result = Invoke-PortableProcess -StartInfo $start -PackageRoot $root -TimeoutMs 15000 -InputText "captured-stdio`n"
    if ($result.ExitCode -ne 0 -or $result.StdOut -cne '{"echo":"captured-stdio"}' -or $result.StdErr -cne 'synthetic-stderr') {
        throw 'Captured stdio regression failed.'
    }
    Write-Output 'PASS captured stdin/stdout/stderr remains functional'
} finally {
    if ($null -ne $process) {
        try { if (-not $process.HasExited) { $process.Kill(); [void]$process.WaitForExit(5000) } } catch {}
        $process.Dispose()
    }
    Remove-AutomationSession -Root $root -Path $fixture
}
