#Requires -Version 5.1
# Real Chromium checks use an owned relocated fixture; never open a user's profile.
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'The release browser smoke test requires Windows x64.'
}
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $root 'tool/automation/portable-automation.ps1')
$owned = New-AutomationDirectory -Root $root -Path (Join-Path $root ('tmp\browser-release-' + [Guid]::NewGuid().ToString('N')))
$fixture = New-AutomationDirectory -Root $root -Path (Join-Path $owned 'Portable relocated')
$utf8 = New-Object Text.UTF8Encoding($false)
$engine = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
try {
    foreach ($relative in @('env.ps1', 'run-codex.ps1', '清理缓存.ps1', 'tool/portable-process.ps1',
        'tool/automation/portable-automation.ps1', 'tool/automation/start-browser.ps1',
        'tool/automation/browser-task.js', 'tool/automation/browser-bridge.js',
        'tool/automation/versions.json', 'tool/node/node.exe')) {
        $source = Assert-AutomationPath -Root $root -Path (Join-Path $root $relative)
        $target = Join-Path $fixture $relative
        [void](New-AutomationDirectory -Root $root -Path (Split-Path -Parent $target))
        Copy-Item -LiteralPath $source -Destination $target
    }
    # Only the root marker is needed; this test never executes Codex.
    [IO.File]::WriteAllText((Join-Path $fixture 'codex.exe'), 'synthetic package marker', $utf8)
    foreach ($relative in @('tool/automation/playwright', 'tool/automation/browsers')) {
        $source = Join-Path $root $relative
        Assert-AutomationTree -Root $root -Path $source
        Copy-Item -LiteralPath $source -Destination (Join-Path $fixture $relative) -Recurse
    }
    $workspace = New-AutomationDirectory -Root $root -Path (Join-Path $fixture 'work\browser-smoke')
    $first = Join-Path $workspace 'first.cjs'
    $second = Join-Path $workspace 'second.cjs'
    [IO.File]::WriteAllText($first, @'
module.exports = async ({page, context, workspace}) => {
  const path = require('node:path');
  await context.route('**/*', route => route.fulfill({
    status: 200, contentType: 'text/html', body: '<title>Portable smoke</title><h1>Package browser</h1>',
  }));
  await page.goto('https://portable-release.invalid/');
  await context.addCookies([{name: 'portable_release', value: 'persisted',
    url: 'https://portable-release.invalid/', expires: Math.floor(Date.now() / 1000) + 3600}]);
  await page.screenshot({path: path.join(workspace, 'smoke.png')});
  const cdp = await context.newCDPSession(page);
  const version = (await cdp.send('Browser.getVersion')).product.split('/').pop();
  await cdp.detach();
  return {title: await page.title(), version,
    cookie: (await context.cookies()).find(cookie => cookie.name === 'portable_release')?.value};
};
'@, $utf8)
    [IO.File]::WriteAllText($second, @'
module.exports = async ({context}) => ({
  cookie: (await context.cookies('https://portable-release.invalid/'))
    .find(cookie => cookie.name === 'portable_release')?.value,
});
'@, $utf8)
    $entry = Join-Path $fixture 'tool\automation\start-browser.ps1'
    $expected = (Get-Content -LiteralPath (Join-Path $fixture 'tool\automation\versions.json') -Raw | ConvertFrom-Json).browser.version
    $output = & $engine -NoProfile -ExecutionPolicy Bypass -File $entry -Workspace $workspace -TaskScript $first -TaskAuthorized -TaskTimeoutSec 120
    if ($LASTEXITCODE -ne 0) { throw 'First real browser task failed.' }
    $result = ($output -join "`n") | ConvertFrom-Json
    if ($result.title -cne 'Portable smoke' -or $result.cookie -cne 'persisted' -or $result.version -cne $expected) {
        throw 'Real browser navigation, version or cookie write failed.'
    }
    $screenshot = Assert-AutomationPath -Root $fixture -Path (Join-Path $workspace 'smoke.png')
    if ((Get-Item -LiteralPath $screenshot).Length -le 0) { throw 'Browser screenshot is empty.' }
    $browserState = Join-Path $fixture 'cache\browser'
    Assert-AutomationTree -Root $fixture -Path $browserState
    $output = & $engine -NoProfile -ExecutionPolicy Bypass -File $entry -Workspace $workspace -TaskScript $second -TaskAuthorized -TaskTimeoutSec 120
    if ($LASTEXITCODE -ne 0) { throw 'Second real browser task failed.' }
    $result = ($output -join "`n") | ConvertFrom-Json
    if ($result.cookie -cne 'persisted') {
        throw 'Browser profile did not persist across separate task processes.'
    }
    Write-Output 'PASS real bundled Chromium, relocated path with spaces, page rendering, screenshot and persistent cookie'
    $cleaner = Join-Path $fixture '清理缓存.ps1'
    & $engine -NoProfile -ExecutionPolicy Bypass -File $cleaner -Yes
    if ($LASTEXITCODE -ne 0) { throw 'Fixture cache cleaner failed.' }
    if (Test-Path -LiteralPath $browserState) { throw 'Cache cleaner retained browser state.' }
    if (-not (Test-Path -LiteralPath $screenshot)) { throw 'Cache cleaner removed preserved work output.' }
    Write-Output 'PASS explicit cache cleanup removes browser profile while preserving work output'
} finally {
    Remove-AutomationSession -Root $root -Path $owned
}
