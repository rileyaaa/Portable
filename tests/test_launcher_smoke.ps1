#Requires -Version 5.1
# Real BAT -> launcher -> pinned native client, with synthetic API settings only.
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'This integration check requires Windows.' }
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $root 'tool/automation/portable-automation.ps1')
[void](New-AutomationDirectory -Root $root -Path (Join-Path $root 'tmp'))
$owned = New-AutomationDirectory -Root $root -Path (Join-Path $root ('tmp/launcher-smoke-' + [Guid]::NewGuid().ToString('N')))
$fixture = New-AutomationDirectory -Root $root -Path (Join-Path $owned 'Portable initial')
$cwd = New-AutomationDirectory -Root $root -Path (Join-Path $owned 'unrelated cwd')
$utf8 = New-Object Text.UTF8Encoding($false)
$entry = ([string][char]0x542f + [char]0x52a8 + 'Codex.bat')
$maintenance = ([string][char]0x542f + [char]0x52a8 + 'Codex-' + [char]0x7ef4 + [char]0x62a4 + [char]0x6a21 + [char]0x5f0f + '.bat')
function Invoke-OwnedSmokeProcess {
    param([Diagnostics.ProcessStartInfo]$StartInfo)
    $p = New-Object Diagnostics.Process
    $p.StartInfo = $StartInfo
    try {
        [void]$p.Start()
        $out = $p.StandardOutput.ReadToEndAsync(); $err = $p.StandardError.ReadToEndAsync()
        $p.StandardInput.Close()
        if (-not $p.WaitForExit(180000)) {
            & (Join-Path $env:SystemRoot 'System32/taskkill.exe') /PID $p.Id /T /F 2>&1 | Out-Null
            throw 'Owned launcher smoke process exceeded its finite deadline.'
        }
        $stdout = $out.GetAwaiter().GetResult(); $stderr = $err.GetAwaiter().GetResult()
        if ($p.ExitCode -ne 0) { throw ('Synthetic launcher smoke failed; exit=' + $p.ExitCode + "`n" + $stdout + "`n" + $stderr) }
        return $stdout
    } finally {
        if ($null -ne $p) {
            try { if (-not $p.HasExited) { & (Join-Path $env:SystemRoot 'System32/taskkill.exe') /PID $p.Id /T /F 2>&1 | Out-Null } } catch {}
            $p.Dispose()
        }
    }
}
try {
    $manifest = Get-Content -LiteralPath (Join-Path $root 'tool/runtime-manifest.json') -Raw | ConvertFrom-Json
    $relativeFiles = @('env.ps1','run-codex.ps1','tool/runtime-manifest.json','tool/portable-process.ps1',$entry,$maintenance)
    $relativeFiles += @($manifest.files.PSObject.Properties | ForEach-Object { $_.Name })
    foreach ($relative in $relativeFiles) {
        $source = Assert-AutomationPath -Root $root -Path (Join-Path $root $relative)
        $destination = Join-Path $fixture $relative
        [void](New-AutomationDirectory -Root $root -Path (Split-Path -Parent $destination))
        Copy-Item -LiteralPath $source -Destination $destination
    }
    [void](New-AutomationDirectory -Root $root -Path (Join-Path $fixture 'codex-resources'))
    [IO.File]::WriteAllText((Join-Path $fixture 'env.local.ps1'), @'
$env:CODEX_AUTH_MODE = "api"
$env:CODEX_BASE_URL = "http://127.0.0.1:9/v1"
$env:OPENAI_API_KEY = "synthetic-offline-key-not-a-credential"
'@, $utf8)
    $validator = Join-Path $owned 'validate_config.py'
    [IO.File]::WriteAllText($validator, @'
import os, pathlib, sys, tomllib
root = pathlib.Path(sys.argv[1]).resolve()
mode = sys.argv[2]
cfg = tomllib.loads((root / 'home' / 'config.toml').read_text(encoding='utf-8-sig'))
assert cfg['approval_policy'] == 'on-request'
assert cfg['sandbox_mode'] == 'workspace-write'
assert cfg['service_tier'] == 'default'
assert cfg['cli_auth_credentials_store'] == 'file'
assert cfg['windows']['sandbox'] == 'unelevated'
assert cfg['sandbox_workspace_write']['network_access'] is False
expected = [root] if mode == 'maintenance' else [root/'work', root/'tmp']
norm = lambda p: os.path.normcase(os.path.normpath(str(p)))
assert set(map(norm, cfg['sandbox_workspace_write']['writable_roots'])) == set(map(norm, expected))
for feature in ('apps','plugins','plugin_sharing','fast_mode','in_app_voice','in_app_dictation'):
    assert cfg['features'][feature] is False, feature
assert 'realtime_conversation' not in cfg['features']
assert cfg['shell_environment_policy']['inherit'] == 'core'
assert cfg['shell_environment_policy']['set']['PIP_CONFIG_FILE'] == 'nul'
for key in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TEMP','TMP','CODEX_HOME','CODEX_SQLITE_HOME'):
    path = cfg['shell_environment_policy']['set'][key]
    assert os.path.commonpath([norm(root), norm(path)]) == norm(root), key
assert not any(key.startswith(('GO','UV_')) for key in cfg['shell_environment_policy']['set'])
assert not list((root / 'tmp').glob('session-state-*')), 'Session scratch leaked after launcher exit'
assert not list((root / 'home').glob('auth*.json')), 'Version-only smoke must not create authentication'
print('PASS full launcher generated configuration: ' + mode)
'@, $utf8)
    $oldRoot = $fixture
    foreach ($case in @('normal', 'relocated', 'maintenance')) {
        if ($case -eq 'relocated') {
            $newRoot = Join-Path $owned ('Portable ' + [char]0x642c + [char]0x8fc1 + ' renamed')
            [IO.Directory]::Move($fixture, $newRoot)
            $fixture = $newRoot
            [void](New-AutomationDirectory -Root $root -Path $oldRoot)
            [IO.File]::WriteAllText((Join-Path $oldRoot 'env.local.ps1'), 'SENTINEL - obsolete path must not be read', $utf8)
        }
        $bat = if ($case -eq 'maintenance') { $maintenance } else { $entry }
        $start = New-Object Diagnostics.ProcessStartInfo
        $start.FileName = Join-Path $env:SystemRoot 'System32/cmd.exe'
        $start.Arguments = '/d /s /c ""' + (Join-Path $fixture $bat) + '" --version"'
        $start.WorkingDirectory = $cwd
        $start.UseShellExecute = $false; $start.CreateNoWindow = $true
        $start.RedirectStandardInput = $true; $start.RedirectStandardOutput = $true; $start.RedirectStandardError = $true
        $start.StandardOutputEncoding = $utf8; $start.StandardErrorEncoding = $utf8
        $start.EnvironmentVariables['CODEX_INSTALL_DIR'] = $oldRoot
        $output = Invoke-OwnedSmokeProcess -StartInfo $start
        if ($output -notmatch ('codex-cli ' + [regex]::Escape($manifest.version))) { throw 'Full launcher did not execute the pinned native client.' }
        $python = Join-Path $root 'tool/python/python.exe'
        $policy = if ($case -eq 'maintenance') { 'maintenance' } else { 'normal' }
        & $python -B $validator $fixture $policy
        if ($LASTEXITCODE -ne 0) { throw 'Full launcher generated configuration did not match the portable contract.' }
        Write-Output ('PASS real BAT/native launch: ' + $case)
    }
    if ([IO.File]::ReadAllText((Join-Path $oldRoot 'env.local.ps1')) -cne 'SENTINEL - obsolete path must not be read') { throw 'Old fixture was modified.' }
} finally {
    Remove-AutomationSession -Root $root -Path $owned
}
