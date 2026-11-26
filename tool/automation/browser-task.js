'use strict';
// One requested coding task, one browser process tree, no persistent daemon.
const path = require('node:path');
const {checkedPath, checkTree, browserConfiguration, checkBrowserTrees} = require('./browser-bridge');

// Preserve the existing JSON result format and enforce its actual serialized
// payload limit, including the escaping and metadata of a truncated result.
function formatTaskResult(value) {
  const limit = 12000;
  const serialized = JSON.stringify(value ?? {completed: true});
  if (serialized === undefined) throw new Error('Browser task result must be JSON-serializable');
  if (serialized.length <= limit) return serialized;
  const envelope = end => {
    // Never split a surrogate pair when truncating a Unicode string.
    if (end > 0 && end < serialized.length &&
        serialized.charCodeAt(end - 1) >= 0xd800 && serialized.charCodeAt(end - 1) <= 0xdbff &&
        serialized.charCodeAt(end) >= 0xdc00 && serialized.charCodeAt(end) <= 0xdfff) end--;
    return JSON.stringify({truncated: true, text: serialized.slice(0, end)});
  };
  let lo = 0, hi = limit;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (envelope(mid).length <= limit) lo = mid;
    else hi = mid - 1;
  }
  return envelope(lo);
}

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
  const browser = browserConfiguration(root, executable, mode === 'headed');
  checkTree(root, path.join(__dirname, 'playwright/node_modules'));
  process.chdir(workspace);
  const task = require(script);
  if (typeof task !== 'function') throw new Error('The task module must export an async function');
  const {chromium} = require('./playwright/node_modules/playwright');
  checkBrowserTrees(root, executable);
  const context = await chromium.launchPersistentContext(browser.userDataDir, {
    ...browser.launchOptions, ...browser.contextOptions,
  });
  const result = await runTaskAndClose(context, task, workspace);
  process.stdout.write(result + '\n');
}

// Serialize while the task context is still available, but do not report
// success until the existing close operation has completed.
async function runTaskAndClose(context, task, workspace) {
  try {
    const page = context.pages()[0] || await context.newPage();
    const value = await task({page, context, workspace});
    return formatTaskResult(value);
  } finally { await context.close(); }
}

module.exports = {formatTaskResult, runTaskAndClose};
if (require.main === module) main().catch(error => {
  process.stderr.write(`Portable browser task: ${error.message}\n`);
  process.exitCode = 1;
});
