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
const {formatTaskResult} = require('../tool/automation/browser-task');

test('unselected browser entry exits before attempting to start a browser', () => {
  for (const name of ['browser-bridge.js', 'browser-task.js']) {
    const result = spawnSync(process.execPath, [path.join(root, 'tool/automation', name)], {
      cwd: root, encoding: 'utf8', timeout: 10000,
    });
    assert.equal(result.status, 1);
    assert.match(result.stderr, /Explicit browser task/);
  }
});

test('task result limit includes JSON escaping and truncation metadata', () => {
  for (const value of [null, undefined, {text:'中文😀'}, 'x'.repeat(11998), false, 0])
    assert.equal(formatTaskResult(value), JSON.stringify(value ?? {completed:true}));
  for (const data of ['a'.repeat(30000), '"\\'.repeat(10000), '\n\t'.repeat(10000), '😀中文'.repeat(10000)]) {
    const serialized = JSON.stringify({data});
    const output = formatTaskResult({data});
    assert.ok(output.length <= 12000, 'Actual serialized payload exceeds limit');
    const parsed = JSON.parse(output);
    assert.equal(parsed.truncated, true);
    assert.ok(parsed.text.length > 5000);
    assert.ok(serialized.startsWith(parsed.text));
    assert.ok(!/[\uD800-\uDBFF]$/.test(parsed.text));
  }
  assert.throws(() => formatTaskResult(() => {}), /JSON-serializable/);
  assert.throws(() => formatTaskResult(Symbol('synthetic')), /JSON-serializable/);
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

test('tree walk avoids repeated leaf and empty-directory stats, still rejects links', () => {
  const scratch = bridge.checkedPath(root, 'tmp', {directory:true, missing:true});
  fs.mkdirSync(scratch, {recursive:true});
  const fixture = fs.mkdtempSync(path.join(scratch, 'tree-stat-test-'));
  const file = path.join(fixture, 'file.txt'), empty = path.join(fixture, 'empty');
  const originalLstat = fs.lstatSync, originalRead = fs.readdirSync;
  try {
    fs.writeFileSync(file, 'synthetic');
    fs.mkdirSync(empty);
    const counts = new Map();
    fs.lstatSync = function(candidate, ...args) {
      counts.set(candidate, (counts.get(candidate) ?? 0) + 1);
      return originalLstat.call(this, candidate, ...args);
    };
    bridge.checkTree(fixture, fixture);
    assert.equal(counts.get(file), 1);
    assert.equal(counts.get(empty), 1);
    assert.throws(() => bridge.checkedPath(fixture, 'missing'), /ENOENT/);
    assert.equal(bridge.checkedPath(fixture, 'missing', {missing:true}), path.join(fixture, 'missing'));
    assert.throws(() => bridge.checkedPath(fixture, 'file.txt/child', {missing:true}), /file type/);
    fs.lstatSync = originalLstat;
    const linked = path.join(fixture, 'linked');
    fs.symlinkSync(empty, linked, process.platform === 'win32' ? 'junction' : 'dir');
    let enumerated = false;
    fs.readdirSync = function(candidate, ...args) {
      if (candidate === linked) enumerated = true;
      return originalRead.call(this, candidate, ...args);
    };
    assert.throws(() => bridge.checkTree(fixture, fixture), /Links/);
    assert.equal(enumerated, false);
    fs.readdirSync = originalRead;
    fs.rmSync(linked);
    fs.linkSync(file, path.join(fixture, 'hardlink'));
    assert.throws(() => bridge.checkTree(fixture, fixture), /Links/);
  } finally {
    fs.lstatSync = originalLstat;
    fs.readdirSync = originalRead;
    fs.rmSync(fixture, {recursive:true, force:true});
  }
});

test('browser configuration reuses only the package-local persistent state', () => {
  const scratch = bridge.checkedPath(root, 'tmp', {directory: true, missing: true});
  fs.mkdirSync(scratch, {recursive: true});
  const fixture = fs.mkdtempSync(path.join(scratch, 'persistent-browser-'));
  try {
    const state = path.join(fixture, 'cache', 'browser');
    for (const name of ['profile', 'cache', 'crashes', 'downloads', 'runtime'])
      fs.mkdirSync(path.join(state, name), {recursive: true});
    const executable = path.join(fixture, 'synthetic.exe');
    fs.writeFileSync(executable, 'Never executable');
    const environment = Object.fromEntries(['HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA',
      'TEMP', 'TMP', 'TMPDIR', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME',
      'XDG_STATE_HOME', 'PROGRAMDATA', 'ALLUSERSPROFILE', 'PUBLIC'].map(key => [key, path.join(state, 'runtime')]));
    const first = bridge.browserConfiguration(fixture, executable, false, environment);
    fs.writeFileSync(path.join(first.userDataDir, 'synthetic-state'), 'survives the next task');
    const second = bridge.browserConfiguration(fixture, executable, true, environment);
    assert.equal(second.userDataDir, first.userDataDir);
    assert.equal(fs.readFileSync(path.join(second.userDataDir, 'synthetic-state'), 'utf8'), 'survives the next task');
    assert.equal(first.isolated, false);
    assert.equal(first.contextOptions.acceptDownloads, false);
    assert.equal(first.contextOptions.serviceWorkers, 'block');
    assert.ok(first.launchOptions.args.includes('--no-proxy-server'));
    const proxied = bridge.browserConfiguration(fixture, executable, false, {
      ...environment, HTTPS_PROXY: 'http://codex:synthetic%2Dtoken@127.0.0.1:18088',
      NO_PROXY: 'localhost,127.0.0.1,::1,model.invalid',
    });
    assert.deepEqual(proxied.launchOptions.proxy, {
      server: 'http://127.0.0.1:18088', username: 'codex', password: 'synthetic-token',
      bypass: 'localhost,127.0.0.1,[::1],model.invalid',
    });
    assert.ok(!proxied.launchOptions.args.includes('--no-proxy-server'));
    assert.equal(first.launchOptions.downloadsPath, path.join(state, 'downloads'));
    assert.ok(first.launchOptions.args.includes(`--disk-cache-dir=${path.join(state, 'cache')}`));
    assert.ok(first.launchOptions.args.includes(`--crash-dumps-dir=${path.join(state, 'crashes')}`));
    assert.throws(() => bridge.browserConfiguration(fixture, executable, false, {...environment, TEMP: root}), /outside/);
    assert.throws(() => bridge.browserConfiguration(fixture, executable, false, {...environment, APPDATA: fixture}), /portable wrapper/);
    const linked = path.join(first.userDataDir, 'linked');
    fs.symlinkSync(path.join(state, 'runtime'), linked, process.platform === 'win32' ? 'junction' : 'dir');
    assert.throws(() => bridge.browserConfiguration(fixture, executable, false, environment), /Links/);
    fs.rmSync(linked);
    fs.linkSync(path.join(first.userDataDir, 'synthetic-state'), path.join(state, 'hardlink'));
    assert.throws(() => bridge.browserConfiguration(fixture, executable, false, environment), /Links/);
  } finally { fs.rmSync(fixture, {recursive: true, force: true}); }
});

test('browser proxy parsing is explicit, rejects ambiguity and never reveals rejected credentials', () => {
  assert.equal(bridge.browserProxy({}), null);
  assert.deepEqual(bridge.browserProxy({ALL_PROXY:'socks5h://[::1]:1080'}), {server:'socks5://[::1]:1080'});
  assert.deepEqual(bridge.browserProxy({HTTP_PROXY:'http://127.0.0.1:80'}), {server:'http://127.0.0.1'});
  assert.throws(() => bridge.browserProxy({HTTP_PROXY:'http://a:1', HTTPS_PROXY:'http://b:2'}), /Conflicting/);
  for (const value of ['https://synthetic-secret@host:9','http://u:synthetic-secret@host:9/path','socks5://u:synthetic-secret@host:9']) {
    assert.throws(() => bridge.browserProxy({ALL_PROXY:value}), error => /Invalid browser proxy/.test(error.message) && !error.message.includes('synthetic-secret'));
  }
});

test('MCP automatic outputs have a separate owned directory per service', () => {
  const scratch = bridge.checkedPath(root, 'tmp', {directory: true, missing: true});
  fs.mkdirSync(scratch, {recursive: true});
  const workspace = fs.mkdtempSync(path.join(scratch, 'browser-output-test-'));
  try {
    const proof = path.join(workspace, 'user-result.txt');
    fs.writeFileSync(proof, 'preserve');
    const first = bridge.createMcpOutputDirectory(workspace), second = bridge.createMcpOutputDirectory(workspace);
    assert.notEqual(first, second);
    assert.equal(path.dirname(first), workspace);
    assert.equal(path.dirname(second), workspace);
    assert.equal(fs.readFileSync(proof, 'utf8'), 'preserve');
    assert.equal(bridge.validateToolCall(workspace, {name:'browser_take_screenshot', arguments:{filename:'proof.png'}}).filename, path.join(workspace, 'proof.png'));
  } finally { fs.rmSync(workspace, {recursive:true, force:true}); }
});

test('persistent browser owner is lazy, closes explicitly and serializes reopen', async () => {
  let starts = 0, closes = 0, releaseClose;
  const options = {userDataDir: 'synthetic/profile', launchOptions: {headless: true}, contextOptions: {acceptDownloads: false}};
  const chromium = {async launchPersistentContext(profile, supplied) {
    assert.equal(profile, options.userDataDir);
    assert.deepEqual(supplied, {headless: true, acceptDownloads: false});
    starts++;
    const context = new EventEmitter();
    context.close = async () => {
      closes++;
      if (closes === 1) await new Promise(resolve => { releaseClose = resolve; });
      context.emit('close');
    };
    return context;
  }};
  const owner = bridge.createBrowserOwner(chromium, options);
  await owner.close();
  assert.equal(starts, 0, 'Closing an unused MCP session must not launch a browser');
  const [first, same] = await Promise.all([owner.get(), owner.get()]);
  assert.equal(first, same);
  assert.equal(starts, 1);
  const closing = owner.close();
  const duplicateClose = owner.close();
  const reopened = owner.get();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(starts, 1, 'A second context must wait for the previous one to close');
  releaseClose();
  await Promise.all([closing, duplicateClose]);
  assert.notEqual(await reopened, first);
  assert.equal(starts, 2);
  assert.equal(closes, 1);
  await owner.dispose();
  assert.equal(closes, 2);
  await assert.rejects(owner.get(), /ended/);
});

test('failed browser close cannot open another context on the same profile', async () => {
  let starts = 0, failClose = true;
  const chromium = {async launchPersistentContext() {
    starts++;
    const context = new EventEmitter();
    context.close = async () => {
      if (failClose) { failClose = false; throw new Error('synthetic close failure'); }
      context.emit('close');
    };
    return context;
  }};
  const owner = bridge.createBrowserOwner(chromium, {userDataDir:'synthetic/profile'});
  const first = await owner.get();
  await assert.rejects(owner.close(), /synthetic close failure/);
  await assert.rejects(owner.get(), /Previous browser close failed/);
  assert.equal(starts, 1);
  await owner.close();
  assert.notEqual(await owner.get(), first);
  assert.equal(starts, 2);
  await owner.dispose();
});

test('launch failure and externally confirmed close allow retry', async () => {
  let starts = 0;
  const chromium = {async launchPersistentContext() {
    if (++starts === 1) throw new Error('synthetic launch failure');
    const context = new EventEmitter();
    context.close = async () => { throw new Error('synthetic close failure'); };
    return context;
  }};
  const owner = bridge.createBrowserOwner(chromium, {userDataDir:'synthetic/profile'});
  await assert.rejects(owner.get(), /synthetic launch failure/);
  const first = await owner.get();
  await assert.rejects(owner.close(), /synthetic close failure/);
  first.emit('close');
  const reopened = await owner.get();
  assert.notEqual(reopened, first);
  assert.equal(starts, 3);
  reopened.emit('close');
  await owner.dispose();
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

test('cancellation frees slots, drops late results and preserves the active request cap', async () => {
  const inner = new MemoryTransport();
  const policy = new bridge.PolicyTransport(inner, root);
  const forwarded = [];
  policy.onmessage = message => forwarded.push(message);
  await policy.start();
  const receive = (method, id, params) => inner.onmessage({jsonrpc:'2.0', method,
    ...(id === undefined ? {} : {id}), ...(params === undefined ? {} : {params})});
  receive('initialize', 'init', {capabilities:{}});
  receive('notifications/cancelled', undefined, {requestId:'init'});
  assert.equal(policy.pending.get('init'), 'initialize');
  await policy.send({jsonrpc:'2.0', id:'init', result:{}});
  for (let i=1; i<=130; i++) {
    receive('ping', i);
    receive('notifications/cancelled', undefined, {requestId:i, reason:'synthetic timeout'});
  }
  assert.equal(policy.pending.size, 0);
  assert.equal(forwarded.filter(m => m.method === 'ping').length, 130);
  const sentBefore = inner.sent.length;
  await policy.send({jsonrpc:'2.0', id:1, result:{}});
  assert.equal(inner.sent.length, sentBefore);
  receive('ping', 200);
  receive('notifications/cancelled', undefined, {requestId:200, reason:7});
  assert.equal(policy.pending.get(200), 'ping');
  await policy.send({jsonrpc:'2.0', id:200, result:{}});
  for (let id=300; id<428; id++) receive('ping', id);
  const rejected = await inner.request({jsonrpc:'2.0', id:428, method:'ping'});
  assert.match(rejected.error.message, /Too many/);
  assert.equal(policy.pending.size, 128);
  await policy.close();
  assert.equal(policy.pending.size, 0);
});

test('cancelled local close still finishes without an obsolete response', async () => {
  const inner = new MemoryTransport();
  let finishClose;
  const policy = new bridge.PolicyTransport(inner, root, () => new Promise(resolve => { finishClose = resolve; }));
  await policy.start();
  inner.onmessage({jsonrpc:'2.0', id:40, method:'tools/call', params:{name:'browser_close'}});
  await new Promise(resolve => setImmediate(resolve));
  inner.onmessage({jsonrpc:'2.0', method:'notifications/cancelled', params:{requestId:40}});
  finishClose();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(policy.pending.size, 0);
  assert.equal(inner.sent.length, 0);
});

test('browser_close closes the owned context without forwarding or starting a browser', async () => {
  const inner = new MemoryTransport();
  let closed = 0, forwarded = 0;
  const policy = new bridge.PolicyTransport(inner, root, async () => { closed++; });
  policy.onmessage = () => { forwarded++; };
  await policy.start();
  const response = await inner.request({jsonrpc: '2.0', id: 30, method: 'tools/call', params: {name: 'browser_close'}});
  assert.equal(closed, 1);
  assert.equal(forwarded, 0);
  assert.match(response.result.content[0].text, /profile retained/);
  assert.equal(policy.pending.size, 0);
});

test('a disconnected client during browser_close reports transport failure without leaking a rejection', async () => {
  const inner = new MemoryTransport();
  inner.send = async () => { throw new Error('synthetic closed pipe'); };
  const policy = new bridge.PolicyTransport(inner, root, async () => {});
  const reported = new Promise(resolve => { policy.onerror = resolve; });
  await policy.start();
  inner.onmessage({jsonrpc: '2.0', id: 31, method: 'tools/call', params: {name: 'browser_close'}});
  assert.match((await reported).message, /closed pipe/);
  assert.equal(policy.pending.size, 0);
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
    // Actual pinned SDK, not just a transport double.
    for (let id=100; id<230; id++) {
      inner.onmessage({jsonrpc:'2.0', id, method:'ping'});
      inner.onmessage({jsonrpc:'2.0', method:'notifications/cancelled', params:{requestId:id}});
      await new Promise(resolve => setImmediate(resolve));
    }
    assert.equal(policy.pending.size, 0);
    const ping = await inner.request({jsonrpc:'2.0', id:230, method:'ping'});
    assert.ok(ping.result);
    assert.equal(policy.pending.size, 0);
    assert.ok(!inner.sent.some(m => typeof m.id === 'number' && m.id >= 100 && m.id < 230));
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
