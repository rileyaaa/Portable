'use strict';
// One requested coding task, one browser process tree, no persistent daemon.
const path = require('node:path');
const {checkedPath, checkTree} = require('./browser-bridge');

async function main() {
  if (process.argv.length !== 7 || process.argv[5] !== '--task-authorized')
    throw new Error('Explicit browser task selection is required');
  if (process.platform !== 'win32') throw new Error('The bundled browser task requires Windows x64');
  const root = path.resolve(__dirname, '..', '..');
  checkedPath(root, __filename);
  const workspace = checkedPath(path.join(root, 'work'), process.argv[2], {directory: true});
  if (workspace === path.join(root, 'work')) throw new Error('Select a task subdirectory');
  const executable = checkedPath(root, process.argv[3]);
  const script = checkedPath(workspace, process.argv[6]);
  if (path.extname(script) !== '.cjs') throw new Error('Use an explicit .cjs task module');
  const mode = process.argv[4];
  if (!['headless', 'headed'].includes(mode)) throw new Error('Invalid browser launch mode');
  const session = checkedPath(path.join(root, 'tmp'), process.env.TEMP, {directory: true});
  for (const key of ['HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TMP', 'TMPDIR'])
    if (checkedPath(root, process.env[key], {directory: true}) !== session)
      throw new Error('Launch through the portable wrapper to isolate browser data');
  checkTree(root, path.join(__dirname, 'playwright/node_modules'));
  process.chdir(workspace);
  const task = require(script);
  if (typeof task !== 'function') throw new Error('The task module must export an async function');
  const {chromium} = require('./playwright/node_modules/playwright');
  const browser = await chromium.launch({
    executablePath: executable, headless: mode === 'headless', chromiumSandbox: true,
    downloadsPath: session,
    args: [
      `--disk-cache-dir=${path.join(session, 'browser-cache')}`,
      `--crash-dumps-dir=${path.join(session, 'crashes')}`,
      '--disable-breakpad',
    ],
  });
  try {
    const context = await browser.newContext({acceptDownloads: false, serviceWorkers: 'block'});
    const page = await context.newPage();
    const value = await task({page, context, workspace});
    const serialized = JSON.stringify(value ?? {completed: true});
    process.stdout.write((serialized.length <= 12000 ? serialized :
      JSON.stringify({truncated: true, text: serialized.slice(0, 12000)})) + '\n');
  } finally { await browser.close(); }
}

if (require.main === module) main().catch(error => {
  process.stderr.write(`Portable browser task: ${error.message}\n`);
  process.exitCode = 1;
});
