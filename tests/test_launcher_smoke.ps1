#Requires -Version 5.1
# Real BAT -> launcher -> pinned native client, with synthetic API settings only.
param([switch]$TuiOnly)
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
    param([Diagnostics.ProcessStartInfo]$StartInfo, [switch]$ExpectFailure)
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
        if ($ExpectFailure) {
            if ($p.ExitCode -eq 0) { throw 'Expected launcher rejection did not occur.' }
            return ($stdout + "`n" + $stderr)
        }
        if ($p.ExitCode -ne 0) { throw ('Synthetic launcher smoke failed; exit=' + $p.ExitCode + "`n" + $stdout + "`n" + $stderr) }
        return $stdout
    } finally {
        if ($null -ne $p) {
            try { if (-not $p.HasExited) { & (Join-Path $env:SystemRoot 'System32/taskkill.exe') /PID $p.Id /T /F 2>&1 | Out-Null } } catch {}
            $p.Dispose()
        }
    }
}
function Invoke-OwnedTuiSmoke {
    # Use a genuine Windows pseudoconsole and synthetic API settings; no prompt
    # is submitted. Disable the launcher menu only inside this owned fixture.
    $localSettings = Join-Path $fixture 'env.local.ps1'
    $beforeTuiSettings = [IO.File]::ReadAllBytes($localSettings)
    try {
        [IO.File]::AppendAllText($localSettings, "`n" + '$env:CODEX_STARTUP_INTERACTIVE = "false"' + "`n", $utf8)
        & (Join-Path $root 'tool/python/python.exe') -B (Join-Path $root 'tests/test_tui_console.py') $fixture $entry
        if ($LASTEXITCODE -ne 0) { throw 'Real interactive TUI startup regression.' }
    } finally {
        [IO.File]::WriteAllBytes($localSettings, $beforeTuiSettings)
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
    if ($TuiOnly) { Invoke-OwnedTuiSmoke; return }
    $validator = Join-Path $owned 'validate_config.py'
    [IO.File]::WriteAllText($validator, @'
import os, pathlib, sys, tomllib
root = pathlib.Path(sys.argv[1]).resolve()
mode = sys.argv[2]
cfg = tomllib.loads((root / 'home' / 'config.toml').read_text(encoding='utf-8-sig'))
if len(sys.argv) > 3 and sys.argv[3]:
    assert cfg['model'] == sys.argv[3], 'CLI model and generated configuration differ'
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
assert not list((root / 'home').glob('auth*.json')), 'Offline smoke must not create authentication'
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
        $expectedModel = if ($case -eq 'relocated') { 'portable-model-smoke' } else { '' }
        $modelArgument = if ($expectedModel) { ' "Logout" -m=' + $expectedModel } else { '' }
        $start = New-Object Diagnostics.ProcessStartInfo
        $start.FileName = Join-Path $env:SystemRoot 'System32/cmd.exe'
        $start.Arguments = '/d /s /c ""' + (Join-Path $fixture $bat) + '"' + $modelArgument + ' --version"'
        $start.WorkingDirectory = $cwd
        $start.UseShellExecute = $false; $start.CreateNoWindow = $true
        $start.RedirectStandardInput = $true; $start.RedirectStandardOutput = $true; $start.RedirectStandardError = $true
        $start.StandardOutputEncoding = $utf8; $start.StandardErrorEncoding = $utf8
        $start.EnvironmentVariables['CODEX_INSTALL_DIR'] = $oldRoot
        $output = Invoke-OwnedSmokeProcess -StartInfo $start
        if ($output -notmatch ('codex-cli ' + [regex]::Escape($manifest.version))) { throw 'Full launcher did not execute the pinned native client.' }
        # --version alone bypasses native configuration loading. The read-only
        # features/list implementation in the pinned release actually loads it.
        # Invoke only that exact command in this synthetic fixture; the production
        # launcher still rejects general feature-management commands.
        $consumerState = New-AutomationDirectory -Root $root -Path (Join-Path $fixture 'tmp/config-consumer')
        $consumerArgs = @('features','list')
        if ($expectedModel) { $consumerArgs = @('-m=' + $expectedModel) + $consumerArgs }
        $native = New-AutomationStartInfo -Root $fixture -FilePath (Join-Path $fixture 'codex.exe') -WorkingDirectory (Join-Path $fixture 'work') -SessionDirectory $consumerState -CaptureOutput -Arguments $consumerArgs
        $native.EnvironmentVariables['CODEX_HOME'] = Join-Path $fixture 'home'
        $native.EnvironmentVariables['CODEX_SQLITE_HOME'] = Join-Path $fixture 'sqlite'
        $native.StandardOutputEncoding = $utf8; $native.StandardErrorEncoding = $utf8
        $configPath = Join-Path $fixture 'home/config.toml'
        $configHash = (Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash
        $features = Invoke-OwnedSmokeProcess -StartInfo $native
        foreach ($feature in @('apps','plugins','plugin_sharing','fast_mode','in_app_voice','in_app_dictation')) {
            if ($features -cnotmatch ('(?m)^' + [regex]::Escape($feature) + '\s+[^\r\n]+\s+false\s*$')) {
                throw ('Native config consumer did not retain the disabled feature: ' + $feature)
            }
        }
        if ((Get-FileHash -LiteralPath $configPath -Algorithm SHA256).Hash -cne $configHash) { throw 'Read-only config inspection changed the generated configuration.' }
        Write-Output ('PASS native client consumes generated configuration: ' + $case)
        $python = Join-Path $root 'tool/python/python.exe'
        $policy = if ($case -eq 'maintenance') { 'maintenance' } else { 'normal' }
        & $python -B $validator $fixture $policy $expectedModel
        if ($LASTEXITCODE -ne 0) { throw 'Full launcher generated configuration did not match the portable contract.' }
        Write-Output ('PASS real BAT/native launch: ' + $case)
    }
    Invoke-OwnedTuiSmoke
    # A real offline maintenance lifecycle must keep the inactive plugin sidecar.
    # These stdio entries are synthetic non-existent commands; add/list/remove
    # manage configuration only and must never launch an MCP server.
    $store = Join-Path $fixture 'home/portable-extensions.toml'
    $seed = "[mcp_servers.existing]`ncommand = 'synthetic-never-executed'`n[plugins.'saved@local']`nenabled = false`n"
    if (Test-Path -LiteralPath $store) { throw 'Fresh fixture unexpectedly has an extension store.' }
    # Simulate upgrading a legacy installation whose only copy is config.toml.
    [IO.File]::WriteAllText((Join-Path $fixture 'home/config.toml'), $seed, $utf8)
    $start.Arguments = '/d /s /c ""' + (Join-Path $fixture $maintenance) + '" mcp list"'
    $denied = Invoke-OwnedSmokeProcess -StartInfo $start -ExpectFailure
    if ($denied -notmatch 'Extension configuration management requires') { throw 'MCP command failed for an unexpected reason.' }
    $migrated = [IO.File]::ReadAllText($store)
    if ($migrated -notmatch '\[mcp_servers.existing\]' -or $migrated -notmatch 'saved@local') { throw 'Rejected startup discarded legacy extensions.' }
    Write-Output 'PASS rejected real launcher preserves legacy extensions for retry'
    [IO.File]::AppendAllText((Join-Path $fixture 'env.local.ps1'), "`n" + '$env:CODEX_PORTABLE_ALLOW_USER_MCP = "true"' + "`n", $utf8)
    foreach ($command in @('mcp add added -- synthetic-never-executed', 'mcp list', 'mcp remove added', 'mcp remove existing')) {
        $start.Arguments = '/d /s /c ""' + (Join-Path $fixture $maintenance) + '" --portable-extensions ' + $command + '"'
        $beforeStoreHash = (Get-FileHash -LiteralPath $store -Algorithm SHA256).Hash
        $null = Invoke-OwnedSmokeProcess -StartInfo $start
        if ($command -eq 'mcp list' -and (Get-FileHash -LiteralPath $store -Algorithm SHA256).Hash -cne $beforeStoreHash) { throw 'Read-only native command rewrote persistent settings.' }
        $saved = [IO.File]::ReadAllText($store)
        if ($saved -notmatch '\[plugins\.' -or $saved -notmatch 'saved@local') { throw 'Native MCP command lost the inactive plugin settings.' }
        if ($command -eq 'mcp add added -- synthetic-never-executed' -and ($saved -notmatch '\[mcp_servers.added\]' -or $saved -notmatch '\[mcp_servers.existing\]')) { throw 'Native MCP add did not retain both servers.' }
    }
    if ([IO.File]::ReadAllText($store) -match '\[mcp_servers\.') { throw 'Deleted last MCP entry was resurrected.' }
    Write-Output 'PASS real maintenance MCP add/list/remove and inactive plugin preservation'
    if ([IO.File]::ReadAllText((Join-Path $oldRoot 'env.local.ps1')) -cne 'SENTINEL - obsolete path must not be read') { throw 'Old fixture was modified.' }
} finally {
    Remove-AutomationSession -Root $root -Path $owned
}
