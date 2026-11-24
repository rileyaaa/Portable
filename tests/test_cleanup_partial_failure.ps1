#Requires -Version 5.1
# Run the complete production cache cleaner in a uniquely owned fixture.
# Synthetic files only. A Windows exclusive file handle injects a real
# deletion failure, not a substituted Remove-Item or fake cleanup result.
param([string]$BaselineCommit = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $root 'tool/automation/portable-automation.ps1')
function Assert-Case { param([bool]$Condition,[string]$Message) if (-not $Condition) { throw $Message } }
$fixture = New-AutomationDirectory -Root $root -Path (Join-Path $root ('tmp\cleanup-failure-' + [guid]::NewGuid().ToString('N')))
$engine = Join-Path ([Environment]::GetFolderPath('Windows')) 'System32\WindowsPowerShell\v1.0\powershell.exe'
$cleaner = Join-Path $fixture '清理缓存.ps1'
$utf8 = New-Object Text.UTF8Encoding($false)
$locked = $null
function Put-FixtureFile {
    param([string]$Relative,[string]$Content)
    $path = Join-Path $fixture $Relative
    [void](New-AutomationDirectory -Root $fixture -Path (Split-Path -Parent $path))
    $path = Assert-AutomationPath -Root $fixture -Path $path -MayNotExist
    [IO.File]::WriteAllText($path,$Content,$utf8)
    return $path
}
function Run-Cleaner {
    param([string]$Options)
    # All arguments are fixed test switches and an owned script path.
    $psi=New-Object Diagnostics.ProcessStartInfo
    $psi.FileName=$engine
    $psi.Arguments='-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$cleaner+'" '+$Options
    $psi.WorkingDirectory=$fixture
    $psi.UseShellExecute=$false
    $psi.CreateNoWindow=$true
    $psi.RedirectStandardOutput=$true
    $psi.RedirectStandardError=$true
    $child=$null
    try {
        $child=[Diagnostics.Process]::Start($psi)
        $out=$child.StandardOutput.ReadToEndAsync()
        $err=$child.StandardError.ReadToEndAsync()
        if (-not $child.WaitForExit(60000)) { throw 'Synthetic cleanup exceeded deadline' }
        # Do not depend on localized output or print arbitrary paths/content.
        [void]$out.GetAwaiter().GetResult()
        [void]$err.GetAwaiter().GetResult()
        return $child.ExitCode
    } finally {
        if ($null -ne $child) {
            try { if (-not $child.HasExited) { $child.Kill(); [void]$child.WaitForExit(5000) } } finally { $child.Dispose() }
        }
    }
}
function Assert-Persistent {
    foreach ($relative in $persistent) {
        $path=Join-Path $fixture $relative
        Assert-Case ([IO.File]::Exists($path) -and [IO.File]::ReadAllText($path) -ceq ('synthetic:'+$relative)) ('Protected file changed: '+$relative)
    }
}
function Assert-Bootstrap {
    Assert-Case ([IO.File]::Exists($config)) 'Safe bootstrap config is missing.'
    $body=[IO.File]::ReadAllText($config)
    Assert-Case ($body.Contains('sandbox_mode = "read-only"') -and $body.Contains('approval_policy = "on-request"') -and
        $body.Contains('cli_auth_credentials_store = "file"') -and -not $body.Contains('danger-full-access')) 'Safe bootstrap was not restored.'
}
try {
    if ($BaselineCommit) {
        if ($BaselineCommit -notmatch '^[a-f0-9]{40}$') { throw 'Invalid baseline commit' }
        # Preserve exact UTF-8/BOM and line endings of the old source, rather
        # than decoding/re-encoding its localized text through a console.
        $blob=(& git -C $root rev-parse ($BaselineCommit+':清理缓存.ps1') | Select-Object -First 1)
        if ($LASTEXITCODE -ne 0 -or $blob -notmatch '^[a-f0-9]{40}$') { throw 'Cannot find exact baseline blob.' }
        $psi=New-Object Diagnostics.ProcessStartInfo
        $psi.FileName=(Get-Command git.exe -CommandType Application).Source
        $psi.WorkingDirectory=$root
        $psi.Arguments='cat-file blob '+$blob
        $psi.UseShellExecute=$false
        $psi.RedirectStandardOutput=$true
        $git=[Diagnostics.Process]::Start($psi)
        try {
            $stream=[IO.File]::Open($cleaner,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
            try { $git.StandardOutput.BaseStream.CopyTo($stream) } finally { $stream.Dispose() }
            if (-not $git.WaitForExit(10000) -or $git.ExitCode -ne 0) {throw 'Cannot copy baseline cleaner.'}
        } finally {
            try { if (-not $git.HasExited) { $git.Kill(); [void]$git.WaitForExit(3000) } } finally {$git.Dispose()}
        }
    } else {
        Copy-Item -LiteralPath (Join-Path $root '清理缓存.ps1') -Destination $cleaner
    }
    foreach ($marker in @('codex.exe','run-codex.ps1','env.ps1')) {
        [void](Put-FixtureFile $marker 'synthetic package marker, never executed')
    }
    $helperDir=New-AutomationDirectory -Root $fixture -Path (Join-Path $fixture 'tool\automation')
    Copy-Item -LiteralPath (Join-Path $root 'tool\automation\portable-automation.ps1') -Destination $helperDir
    $persistent=@(
        'home\auth.json','home\auth-account-json.json','home\auth-browser.json',
        'home\auth-transition.block','home\logout-browser.block','home\logout-account_json.block',
        'home\installation_id','home\mode','home\portable-extensions.toml','home\cap_sid',
        'home\auth.json.invalid-synthetic','home\config.toml.bak-0123456789abcdef0123456789abcdef',
        'tmp\codex-official-update-0123456789abcdef0123456789abcdef\recovery.txt'
    )
    foreach ($relative in $persistent) { [void](Put-FixtureFile $relative ('synthetic:'+$relative)) }
    $config=Put-FixtureFile 'home\config.toml' 'sandbox_mode = "danger-full-access"'
    $work=Put-FixtureFile 'work\keep.txt' 'synthetic work'
    $skills=Put-FixtureFile 'home\skills\keep.txt' 'synthetic skill'
    $plugins=Put-FixtureFile 'home\plugins\keep.txt' 'synthetic plugin'
    $market=Put-FixtureFile 'home\.agents\plugins\keep.txt' 'synthetic marketplace'
    $cookie=Put-FixtureFile 'cache\browser\profile\synthetic-cookie' 'synthetic browser state'
    $log=Put-FixtureFile 'logs\synthetic.log' 'synthetic log'
    $blocked=Put-FixtureFile 'tmp\locked-directory\held.txt' 'synthetic busy file'
    $locked=[IO.File]::Open($blocked,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    $exit=Run-Cleaner '-WhatIf'
    Assert-Case ($exit -eq 0 -and [IO.File]::Exists($cookie) -and [IO.File]::Exists($log) -and
        [IO.File]::ReadAllText($config) -ceq 'sandbox_mode = "danger-full-access"') 'Preview changed existing content.'
    Assert-Persistent
    $exit=Run-Cleaner '-Yes'
    if ($BaselineCommit) {
        Assert-Case ($exit -ne 0 -and -not [IO.File]::Exists($config) -and [IO.File]::Exists($cookie) -and [IO.File]::Exists($log)) 'Previous deletion failure did not abort before bootstrap.'
        Assert-Persistent
        Write-Output 'REPRODUCED previous busy nested file aborts cleanup after deleting config and before later cache items'
        return
    }
    Assert-Case ($exit -eq 1 -and [IO.File]::Exists($blocked)) 'Failed item not retained or nonzero exit lost.'
    Assert-Case (-not [IO.File]::Exists($cookie) -and -not [IO.File]::Exists($log)) 'Independent later cache items were not processed.'
    Assert-Bootstrap
    Assert-Persistent
    foreach ($path in @($work,$skills,$plugins,$market)) {Assert-Case ([IO.File]::Exists($path)) 'Default cleanup removed preserved user assets.'}
    Write-Output 'PASS actual partial deletion reports failure, finishes independent safe items, restores bootstrap and preserves user assets'
    $locked.Dispose(); $locked=$null
    $exit=Run-Cleaner '-Yes'
    Assert-Case ($exit -eq 0 -and -not [IO.File]::Exists($blocked)) 'Existing cleanup cannot recover after release of busy file.'
    Assert-Bootstrap
    Assert-Persistent
    $exit=Run-Cleaner '-Yes -CleanAll'
    Assert-Case ($exit -eq 0) 'Explicit full cleanup failed.'
    foreach ($path in @($work,$skills,$plugins,$market)) {Assert-Case (-not [IO.File]::Exists($path)) 'Explicit full cleanup no longer removes selected assets.'}
    Assert-Bootstrap
    Assert-Persistent
    Write-Output 'PASS preview, cleanup after release, explicit CleanAll, persistent auth/identity/recovery and original bootstrap policy'
} finally {
    if ($null -ne $locked) {$locked.Dispose()}
    Remove-AutomationSession -Root $root -Path $fixture
}
