'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {runTaskAndClose, formatTaskResult} = require('../tool/automation/browser-task');

// Synthetic context only: no browser, filesystem, server or network.
test('task result is ready only after the existing context close completes', async () => {
  const page = {};
  const workspace = 'synthetic task';
  const value = {text: '\u4e2d\u6587\ud83d\ude00', completed: true};
  const expected = JSON.stringify(value);
  let releaseClose, enteredClose;
  const closeStarted = new Promise(resolve => { enteredClose = resolve; });
  const closeGate = new Promise(resolve => { releaseClose = resolve; });
  let closeCalls = 0;
  const context = {
    pages: () => [page],
    async close() { closeCalls++; enteredClose(); await closeGate; },
  };
  let settled = false;
  const result = runTaskAndClose(context, async actual => {
    assert.deepEqual(actual, {page, context, workspace});
    return value;
  }, workspace).then(output => { settled = true; return output; });
  try {
    await closeStarted;
    await Promise.resolve();
    assert.equal(settled, false);
    // Serialization is still a snapshot of the returned task result.
    value.completed = false;
  } finally { releaseClose(); }
  assert.equal(await result, expected);
  assert.equal(closeCalls, 1);
});

test('close failure does not yield a success result', async () => {
  const failure = new Error('synthetic close failure');
  let closeCalls = 0;
  const context = {pages: () => [{}], async close() { closeCalls++; throw failure; }};
  await assert.rejects(runTaskAndClose(context, async () => ({completed: true}), 'synthetic'),
    error => error === failure);
  assert.equal(closeCalls, 1);
});

test('task failure still closes the context and rejects', async () => {
  const failure = new Error('synthetic task failure');
  let closeCalls = 0;
  const context = {pages: () => [{}], async close() { closeCalls++; }};
  await assert.rejects(runTaskAndClose(context, async () => { throw failure; }, 'synthetic'),
    error => error === failure);
  assert.equal(closeCalls, 1);
});

test('serialization failure still closes the context and rejects', async () => {
  let closeCalls = 0;
  const context = {pages: () => [{}], async close() { closeCalls++; }};
  await assert.rejects(runTaskAndClose(context, async () => Symbol('synthetic'), 'synthetic'),
    /JSON-serializable/);
  assert.equal(closeCalls, 1);
});

test('new-page fallback and existing result envelope remain unchanged', async () => {
  const page = {};
  let created = 0, closed = 0;
  const context = {
    pages: () => [],
    async newPage() { created++; return page; },
    async close() { closed++; },
  };
  const value = {text: '\u4e2d\u6587\ud83d\ude00'.repeat(5000)};
  const output = await runTaskAndClose(context, async actual => {
    assert.equal(actual.page, page);
    return value;
  }, 'synthetic');
  assert.equal(created, 1);
  assert.equal(closed, 1);
  assert.equal(output, formatTaskResult(value));
  assert.ok(output.length <= 12000);
  assert.equal(JSON.parse(output).truncated, true);
});
