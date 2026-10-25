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
        'tool/automation/versions.json', 'tool/node/node.exe',
        'Version_History/AI account format conversion/index.html',
        'Version_History/AI account format conversion/app/app.js',
        'Version_History/AI account format conversion/app/converter.js')) {
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
  // Exercise the actual offline converter UI with synthetic fields only.
  const fs = require('node:fs');
  const converterRoot = path.resolve(workspace, '../..', 'Version_History/AI account format conversion');
  const converterPage = await context.newPage();
  try {
    const html = fs.readFileSync(path.join(converterRoot, 'index.html'), 'utf8')
      .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '')
      .replace(/<link\b[^>]*>/gi, '');
    await converterPage.setContent(html);
    for (const script of ['converter.js', 'app.js']) {
      await converterPage.addScriptTag({content: fs.readFileSync(path.join(converterRoot, 'app', script), 'utf8')});
    }
    const marker = '<img src="data:,synthetic" onerror="window.__synthetic_type_marker=1">';
    await converterPage.locator('#inputText').fill(JSON.stringify({accounts:[{
      name:'synthetic',type:marker,credentials:{api_key:'synthetic-not-a-key'},
    }]}));
    await converterPage.locator('#convertBtn').click();
    if (!(await converterPage.locator('#detected').textContent()).includes(marker) ||
        await converterPage.locator('#detected img').count() !== 0 ||
        await converterPage.evaluate(() => Boolean(window.__synthetic_type_marker))) {
      throw new Error('Converter treated an imported type as executable HTML.');
    }
    const zipNamesOk = await converterPage.evaluate(() => {
      const name = '\u4fbf\u643a/\u8d26\u53f7.json';
      const data = makeZip({[name]:'synthetic'});
      const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
      const central = view.getUint32(data.length-6, true);
      return (view.getUint16(6,true)&0x800) === 0x800 &&
        (view.getUint16(central+8,true)&0x800) === 0x800 &&
        new TextDecoder().decode(data.slice(30,30+view.getUint16(26,true))) === name;
    });
    if (!zipNamesOk) throw new Error('Converter ZIP Unicode filename contract failed.');
    // Exercise rule mapping through the actual UI, not just isolated helpers.
    await converterPage.locator('#rulesToggle').check();
    await converterPage.locator('#rulesText').fill('{"token":"api_key"}');
    await converterPage.locator('#inputText').fill(
      '{"data":{"count":1},"items":[{"name":"synthetic-wrapped","token":"synthetic-only","constructor":"preserved","__proto__":{"note":"preserved"}}]}');
    await converterPage.locator('#convertBtn').click();
    const inputRulesOk = await converterPage.evaluate(() => {
      const account = state.canon && state.canon.accounts[0];
      const mapped = AccountConverter.ruleMapObject(
        {metadata:{syntheticFlag:true}}, {metadata:'__proto__'});
      return state.canon && state.canon.accounts.length === 1 &&
        account.name === 'synthetic-wrapped' && account.api_key === 'synthetic-only' &&
        Object.hasOwn(account.raw, 'constructor') && account.raw.constructor === 'preserved' &&
        Object.hasOwn(account.raw, '__proto__') && account.raw.__proto__.note === 'preserved' &&
        account.raw.note === undefined && Object.hasOwn(mapped, '__proto__') &&
        mapped.syntheticFlag === undefined &&
        JSON.parse(JSON.stringify(mapped)).__proto__.syntheticFlag === true;
    });
    if (!inputRulesOk) throw new Error('Converter wrapper/rule mapping lost data or inherited a field.');
  } finally {
    await converterPage.close();
  }
  return {title: await page.title(), version, converterUiAndZip: true,
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
    # Exercise a fresh extraction: the production wrapper must create safe tmp.
    if (Test-Path -LiteralPath (Join-Path $fixture 'tmp')) { throw 'Browser fixture must start without tmp.' }
    $output = & $engine -NoProfile -ExecutionPolicy Bypass -File $entry -Workspace $workspace -TaskScript $first -TaskAuthorized -TaskTimeoutSec 120
    if ($LASTEXITCODE -ne 0) { throw ('First real browser task failed; exit=' + $LASTEXITCODE) }
    [void](Assert-AutomationPath -Root $fixture -Path (Join-Path $fixture 'tmp') -Directory)
    $result = ($output -join "`n") | ConvertFrom-Json
    if ($result.title -cne 'Portable smoke' -or $result.cookie -cne 'persisted' -or $result.version -cne $expected -or $result.converterUiAndZip -ne $true) {
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
    Write-Output 'PASS real converter UI escapes imported types and emits UTF-8 ZIP filenames'
    Write-Output 'PASS real converter UI preserves wrapped arrays and prototype-named mapping fields'
    $cleaner = Join-Path $fixture '清理缓存.ps1'
    & $engine -NoProfile -ExecutionPolicy Bypass -File $cleaner -Yes
    if ($LASTEXITCODE -ne 0) { throw 'Fixture cache cleaner failed.' }
    if (Test-Path -LiteralPath $browserState) { throw 'Cache cleaner retained browser state.' }
    if (-not (Test-Path -LiteralPath $screenshot)) { throw 'Cache cleaner removed preserved work output.' }
    Write-Output 'PASS explicit cache cleanup removes browser profile while preserving work output'
} finally {
    Remove-AutomationSession -Root $root -Path $owned
}
