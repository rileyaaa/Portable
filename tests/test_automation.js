'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {EventEmitter} = require('node:events');
const {createHash} = require('node:crypto');
const {spawnSync} = require('node:child_process');
const root = path.resolve(__dirname, '..');
const bridge = require('../tool/automation/browser-bridge');

test('unselected browser entry exits before attempting to start a browser', () => {
  for (const name of ['browser-bridge.js', 'browser-task.js']) {
    const result = spawnSync(process.execPath, [path.join(root, 'tool/automation', name)], {
      cwd: root, encoding: 'utf8', timeout: 10000,
    });
    assert.equal(result.status, 1);
    assert.match(result.stderr, /Explicit browser task/);
  }
});

test('path guards reject traversal, hard links and linked ancestors', () => {
  const scratch = bridge.checkedPath(root, 'tmp', {directory: true, missing: true});
  fs.mkdirSync(scratch, {recursive: true});
  const base = fs.mkdtempSync(path.join(scratch, 'automation-test-'));
  try {
    const work = path.join(base, '包内 task');
    fs.mkdirSync(work);
    fs.writeFileSync(path.join(work, 'input'), 'synthetic');
    fs.linkSync(path.join(work, 'input'), path.join(work, 'hard'));
    assert.throws(() => bridge.checkedPath(work, 'input'), /Links/);
    assert.throws(() => bridge.checkedPath(work, '../escape', {missing: true}), /Invalid/);
    assert.throws(() => bridge.checkedPath(work, base, {directory: true}), /outside/);
    fs.symlinkSync(work, path.join(base, 'linked'), process.platform === 'win32' ? 'junction' : 'dir');
    assert.throws(() => bridge.checkedPath(base, 'linked/new', {missing: true}), /Links/);
    const originalLstat = fs.lstatSync;
    let childProbed = false;
    fs.lstatSync = function(candidate, ...args) {
      if (candidate === path.join(base, 'linked', 'new')) childProbed = true;
      return originalLstat.call(this, candidate, ...args);
    };
    try {
      assert.throws(() => bridge.checkedPath(base, 'linked/new', {missing: true}), /Links/);
      assert.equal(childProbed, false, 'Reject the linked ancestor before probing its target');
    } finally { fs.lstatSync = originalLstat; }
    fs.symlinkSync(path.join(base, 'absent'), path.join(base, 'dangling'), process.platform === 'win32' ? 'junction' : 'dir');
    assert.throws(() => bridge.checkedPath(base, 'dangling/new', {missing: true}), /Links/);
  } finally {
    fs.rmSync(base, {recursive: true, force: true});
  }
});

test('tool policy blocks host execution, uploads, installation and local-file navigation', () => {
  for (const name of ['browser_run_code_unsafe', 'browser_file_upload', 'browser_install', 'browser_config'])
    assert.throws(() => bridge.validateToolCall(root, {name, arguments: {}}), /not enabled/);
  assert.throws(() => bridge.validateToolCall(root, {
    name: 'browser_navigate', arguments: {url: 'file:///C:/Users/secret'},
  }), /Only HTTP/);
  assert.throws(() => bridge.validateToolCall(root, {
    name: 'browser_tabs', arguments: {action: 'new', url: 'file:///C:/Users/secret'},
  }), /Only HTTP/);
  assert.throws(() => bridge.validateToolCall(root, {
    name: 'browser_take_screenshot', arguments: {filename: '../outside.png'},
  }), /Invalid/);
  bridge.validateToolCall(root, {name: 'browser_navigate', arguments: {url: 'https://example.test/'}});
});

class MemoryTransport {
  constructor() { this.events = new EventEmitter(); this.sent = []; }
  async start() {}
  async close() { this.onclose?.(); }
  async send(message) { this.sent.push(message); this.events.emit('message', message); }
  request(message) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.events.off('message', handler); reject(new Error('Offline MCP timeout')); }, 5000);
      const handler = response => {
        if (response.id !== message.id) return;
        clearTimeout(timer); this.events.off('message', handler); resolve(response);
      };
      this.events.on('message', handler); this.onmessage(message);
    });
  }
}

test('transport strips client roots and refuses requests without forwarding them', async () => {
  const inner = new MemoryTransport();
  const policy = new bridge.PolicyTransport(inner, root);
  const forwarded = [];
  policy.onmessage = message => forwarded.push(message);
  await policy.start();
  inner.onmessage({jsonrpc: '2.0', id: 1, method: 'initialize', params: {capabilities: {roots: {listChanged: true}}}});
  assert.deepEqual(forwarded[0].params.capabilities, {});
  const rejected = await inner.request({jsonrpc: '2.0', id: 2, method: 'tools/call', params: {name: 'browser_run_code_unsafe'}});
  assert.ok(rejected.error);
  assert.equal(forwarded.length, 1);
  await policy.send({jsonrpc: '2.0', id: 1, result: {}});
  assert.equal(policy.pending.size, 0);
  inner.onmessage({jsonrpc: '2.0', id: 3, method: 'tools/call', params: {
    name: 'browser_take_screenshot', arguments: {filename: 'synthetic.png', _meta: {cwd: '/outside'}},
  }});
  const sanitized = forwarded[1].params.arguments;
  assert.equal(sanitized.filename, path.join(root, 'synthetic.png'));
  assert.ok(!Object.hasOwn(sanitized, '_meta'));
});

test('real pinned MCP initializes and lists filtered tools without browser startup', async () => {
  const {createConnection} = require('../tool/automation/playwright/node_modules/@playwright/mcp');
  const server = await createConnection({
    browser: {browserName: 'chromium', isolated: true}, capabilities: [], saveSession: false,
  });
  const inner = new MemoryTransport();
  const policy = new bridge.PolicyTransport(inner, root);
  try {
    await server.connect(policy);
    const initialized = await inner.request({
      jsonrpc: '2.0', id: 1, method: 'initialize',
      params: {protocolVersion: '2025-06-18', capabilities: {}, clientInfo: {name: 'offline-test', version: '1'}},
    });
    assert.ok(initialized.result);
    inner.onmessage({jsonrpc: '2.0', method: 'notifications/initialized'});
    const response = await inner.request({jsonrpc: '2.0', id: 2, method: 'tools/list'});
    assert.ok(response.result.tools.some(t => t.name === 'browser_snapshot'));
    assert.ok(response.result.tools.some(t => t.name === 'browser_navigate'));
    for (const tool of response.result.tools) assert.ok(bridge.allowedTools.has(tool.name));
    assert.ok(!response.result.tools.some(t => /run_code|upload|install/.test(t.name)));
  } finally { await server.close(); }
});

test('bundled dependencies match recorded bytes and the upstream version lock', () => {
  const manifest = require('../tool/automation/dependency-manifest.json');
  const lock = require('../tool/automation/playwright/package-lock.json');
  const versions = require('../tool/automation/versions.json');
  assert.equal(lock.packages['node_modules/@playwright/mcp'].version, versions.playwrightMcp);
  assert.equal(lock.packages['node_modules/playwright-core'].version, versions.playwright);
  for (const [name, hash] of Object.entries(manifest.files)) {
    const target = bridge.checkedPath(root, name);
    assert.equal(createHash('sha256').update(fs.readFileSync(target)).digest('hex'), hash, name);
  }
});
