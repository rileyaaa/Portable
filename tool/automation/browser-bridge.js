'use strict';

// Thin policy transport around Microsoft's pinned MCP API. No browser is
// launched until an explicitly allowed tool call reaches the upstream server.
const fs = require('node:fs');
const path = require('node:path');

const allowedTools = new Set([
  'browser_close', 'browser_resize', 'browser_snapshot', 'browser_find',
  'browser_navigate', 'browser_navigate_back', 'browser_navigate_forward', 'browser_reload',
  'browser_tabs', 'browser_click', 'browser_hover', 'browser_drag',
  'browser_select_option', 'browser_check', 'browser_uncheck', 'browser_fill_form',
  'browser_type', 'browser_press_key', 'browser_press_sequentially',
  'browser_handle_dialog', 'browser_wait_for', 'browser_take_screenshot',
  'browser_console_messages', 'browser_console_clear', 'browser_network_requests',
  'browser_evaluate', 'browser_generate_locator',
]);

function checkedPath(root, input, {directory = false, missing = false} = {}) {
  if (typeof input !== 'string' || !input || /(^|[\\/])\.\.([\\/]|$)/.test(input) || input.includes('\0'))
    throw new Error('Invalid package path');
  if (process.platform === 'win32' && (/^\\\\/.test(input) || input.slice(2).includes(':')))
    throw new Error('Device, network and stream paths are not allowed');
  const base = path.resolve(root), full = path.resolve(root, input);
  const rel = path.relative(base, full);
  if (rel.startsWith('..' + path.sep) || rel === '..' || path.isAbsolute(rel))
    throw new Error('Path is outside the allowed directory');
  const ancestors = [];
  for (let current = full;;) {
    ancestors.push(current);
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }
  for (const current of ancestors.reverse()) {
    try {
      const stat = fs.lstatSync(current);
      if (stat.isSymbolicLink() || (stat.isFile() && stat.nlink !== 1))
        throw new Error('Links are not permitted');
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
  }
  let leaf;
  try { leaf = fs.lstatSync(full); } catch (error) {
    if (error.code !== 'ENOENT' || !missing) throw error;
  }
  if (leaf && (directory ? !leaf.isDirectory() : !leaf.isFile()))
    throw new Error('Unexpected package file type');
  return full;
}

function checkTree(root, directory) {
  checkedPath(root, directory, {directory: true});
  for (const entry of fs.readdirSync(directory, {withFileTypes: true})) {
    const candidate = path.join(directory, entry.name);
    checkedPath(root, candidate, {directory: entry.isDirectory()});
    if (entry.isDirectory()) checkTree(root, candidate);
  }
}

function browserConfiguration(root, executable, headed, environment = process.env) {
  executable = checkedPath(root, executable);
  checkTree(root, path.dirname(executable));
  const state = checkedPath(root, path.join(root, 'cache', 'browser'), {directory: true});
  // Reject nested links before Chromium reads persisted databases or preferences.
  checkTree(root, state);
  const directories = {};
  for (const name of ['profile', 'cache', 'crashes', 'downloads', 'runtime'])
    directories[name] = checkedPath(state, name, {directory: true});
  for (const key of ['HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP', 'TMPDIR',
    'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME',
    'PROGRAMDATA', 'ALLUSERSPROFILE', 'PUBLIC']) {
    if (checkedPath(root, environment[key], {directory: true}) !== directories.runtime)
      throw new Error('Launch through the portable wrapper to isolate browser data');
  }
  return {
    browserName: 'chromium', isolated: false, userDataDir: directories.profile,
    launchOptions: {
      executablePath: checkedPath(root, executable), headless: !headed, chromiumSandbox: true,
      downloadsPath: directories.downloads,
      args: [
        `--disk-cache-dir=${directories.cache}`,
        `--crash-dumps-dir=${directories.crashes}`,
        '--disable-breakpad',
      ],
    },
    contextOptions: {acceptDownloads: false, serviceWorkers: 'block'},
  };
}

function createBrowserOwner(chromium, configuration) {
  let current = null, closing = null, disposed = false;
  return {
    async get() {
      if (closing) await closing;
      if (disposed) throw new Error('Browser task has ended');
      if (!current) {
        const pending = chromium.launchPersistentContext(configuration.userDataDir, {
          ...configuration.launchOptions, ...configuration.contextOptions,
        });
        current = pending;
        try {
          const context = await pending;
          context.once('close', () => { if (current === pending) current = null; });
        } catch (error) {
          if (current === pending) current = null;
          throw error;
        }
      }
      return current;
    },
    async close() {
      if (closing) return closing;
      const pending = current;
      if (!pending) return;
      closing = (async () => {
        try { await (await pending).close(); }
        finally { if (current === pending) current = null; }
      })();
      try { await closing; } finally { closing = null; }
    },
    async dispose() { disposed = true; await this.close(); },
  };
}

function validateToolCall(workspace, params) {
  if (!params || !allowedTools.has(params.name))
    throw new Error('Tool is not enabled by the portable browser policy');
  const supplied = params.arguments ?? {};
  if (!supplied || typeof supplied !== 'object' || Array.isArray(supplied))
    throw new Error('Tool arguments must be an object');
  const args = {...supplied};
  // Upstream consumes _meta.cwd before schema parsing; never let it redirect
  // relative output after we have validated it against the selected workspace.
  delete args._meta;
  if (Object.hasOwn(args, 'filename'))
    args.filename = checkedPath(workspace, args.filename, {missing: true});
  if (params.name === 'browser_navigate' ||
      (params.name === 'browser_tabs' && Object.hasOwn(args, 'url'))) {
    const url = new URL(args.url);
    if (!['http:', 'https:'].includes(url.protocol) && url.href !== 'about:blank')
      throw new Error('Only HTTP(S) and about:blank navigation are enabled');
  }
  // Upload/drop, raw Node evaluation, installation, config, WebMCP and
  // filesystem tools never enter the allowlist. browser_evaluate is page JS.
  return args;
}

class PolicyTransport {
  constructor(inner, workspace, closeBrowser = null) {
    this.inner = inner;
    this.workspace = workspace;
    this.closeBrowser = closeBrowser;
    this.pending = new Map();
  }
  async start() {
    this.inner.onmessage = message => {
      try {
        if (!message || message.jsonrpc !== '2.0') throw new Error('Invalid JSON-RPC message');
        const method = message.method;
        if (method === 'initialize') {
          // Upstream otherwise trusts arbitrary roots supplied by the client.
          message = {...message, params: {...message.params, capabilities: {}}};
        } else if (method === 'tools/call') {
          const args = validateToolCall(this.workspace, message.params);
          message = {...message, params: {...message.params, arguments: args}};
        } else if (!['tools/list', 'ping', 'notifications/initialized', 'notifications/cancelled'].includes(method)) {
          throw new Error('MCP method is not enabled by the portable browser policy');
        }
        if (message.id !== undefined) {
          if (this.pending.size >= 128 || this.pending.has(message.id))
            throw new Error('Too many or duplicate requests');
          this.pending.set(message.id, method);
        }
        if (method === 'tools/call' && message.params.name === 'browser_close' && this.closeBrowser) {
          // The pinned API disposes its backend without closing the supplied context.
          // Closing our owner also resets that backend through its context-close event.
          void Promise.resolve().then(() => this.closeBrowser()).then(
            () => this.send({jsonrpc: '2.0', id: message.id, result: {
              content: [{type: 'text', text: 'Browser closed; package-local profile retained.'}],
            }}),
            error => this.send({jsonrpc: '2.0', id: message.id, error: {code: -32603, message: error.message}}),
          ).catch(error => this.onerror?.(error));
          return;
        }
        this.onmessage?.(message);
      } catch (error) {
        if (message?.id !== undefined)
          void Promise.resolve().then(() => this.inner.send({
            jsonrpc: '2.0', id: message.id, error: {code: -32602, message: error.message},
          })).catch(sendError => this.onerror?.(sendError));
      }
    };
    this.inner.onclose = () => this.onclose?.();
    this.inner.onerror = error => this.onerror?.(error);
    await this.inner.start();
  }
  async send(message) {
    if (message.id !== undefined && !message.method) {
      const method = this.pending.get(message.id);
      this.pending.delete(message.id);
      if (method === 'tools/list' && message.result?.tools)
        message = {...message, result: {...message.result, tools: message.result.tools.filter(t => allowedTools.has(t.name))}};
    }
    return this.inner.send(message);
  }
  async close() { return this.inner.close(); }
}

async function main() {
  if (process.argv.length !== 6 || process.argv[5] !== '--task-authorized')
    throw new Error('Explicit browser task selection is required');
  const root = path.resolve(__dirname, '..', '..');
  if (process.platform !== 'win32') throw new Error('The bundled browser entry point requires Windows x64');
  checkedPath(root, __filename);
  const workspace = checkedPath(root, process.argv[2], {directory: true});
  if (!path.relative(path.join(root, 'work'), workspace) ||
      path.relative(path.join(root, 'work'), workspace).startsWith('..'))
    throw new Error('Select a task subdirectory inside package/work');
  const executable = checkedPath(root, process.argv[3]);
  const headed = process.argv[4] === 'headed';
  if (!['headed', 'headless'].includes(process.argv[4]))
    throw new Error('Invalid browser launch arguments');
  const browser = browserConfiguration(root, executable, headed);
  const dependencies = path.join(__dirname, 'playwright', 'node_modules');
  checkTree(root, dependencies);
  process.chdir(workspace);
  const {createConnection} = require('./playwright/node_modules/@playwright/mcp');
  const {chromium} = require('./playwright/node_modules/playwright');
  const owner = createBrowserOwner(chromium, browser);
  const {StdioServerTransport} = require('./playwright/node_modules/playwright-core/lib/utilsBundle');
  const server = await createConnection({
    browser,
    capabilities: [], webmcp: false, allowUnrestrictedFileAccess: false,
    outputDir: workspace, outputMaxSize: 50 * 1024 * 1024,
    saveSession: false, codegen: 'none',
  }, () => owner.get());
  const transport = new PolicyTransport(new StdioServerTransport(), workspace, () => owner.close());
  let shutdownPromise;
  const shutdown = () => {
    if (!shutdownPromise) shutdownPromise = (async () => {
      try { await owner.dispose(); } finally { await server.close(); }
    })();
    return shutdownPromise;
  };
  const onEnd = () => void shutdown().catch(error => {
    process.stderr.write(`Portable browser shutdown: ${error.message}\n`);
    process.exitCode = 1;
  });
  process.stdin.once('end', onEnd);
  process.once('SIGINT', onEnd);
  process.once('SIGTERM', onEnd);
  try {
    await server.connect(transport);
    const previousClose = transport.onclose, previousError = transport.onerror;
    transport.onclose = () => { previousClose?.(); onEnd(); };
    transport.onerror = error => { previousError?.(error); onEnd(); };
  } catch (error) { await shutdown(); throw error; }
}

module.exports = {allowedTools, checkedPath, checkTree, browserConfiguration, createBrowserOwner, validateToolCall, PolicyTransport};
if (require.main === module) main().catch(error => {
  process.stderr.write(`Portable browser: ${error.message}\n`);
  process.exitCode = 1;
});
