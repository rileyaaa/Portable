'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const {inside, portableEnvironment, planArguments, preflightConfigFiles} = require('../tool/node/portable-npm');

const repository = path.resolve(__dirname, '..');
const npmPath = path.join(repository, 'tool/node/node_modules/npm');
const parser = {
  Config: require(path.join(npmPath, 'node_modules/@npmcli/config')),
  ...require(path.join(npmPath, 'node_modules/@npmcli/config/lib/definitions')),
};

function fixture(t) {
  inside(repository, repository, {directory: true, required: true});
  const scratch = inside(repository, path.join(repository, 'tmp'), {directory: true});
  fs.mkdirSync(scratch, {recursive: true});
  const base = fs.mkdtempSync(path.join(scratch, 'npm-boundary-'));
  t.after(() => fs.rmSync(base, {recursive: true, force: true}));
  const root = path.join(base, 'portable package');
  const cwd = path.join(root, 'work', 'project with spaces');
  fs.mkdirSync(cwd, {recursive: true});
  fs.writeFileSync(path.join(base, 'package.json'), JSON.stringify({name: 'synthetic-parent', version: '1.0.0'}));
  fs.writeFileSync(path.join(base, '.npmrc'), 'tag=outside-parent-value\n');
  const env = portableEnvironment(root, {});
  return {base, root, cwd, env};
}

function plan(f, mode, args) {
  return planArguments({...f, npmPath, parser, mode, args});
}

async function actualConfig(f, argv) {
  const config = new parser.Config({...parser, npmPath, cwd: f.cwd, env: {...f.env},
    argv: [process.execPath, path.join(npmPath, 'bin/npm-cli.js'), ...argv], warn: false});
  await config.load();
  return config;
}

// Execute the bundled npx argument transformation, replacing only the final
// npm execution with a capture function. No process or network is started.
function actualNpxArguments(args) {
  const filename = path.join(npmPath, 'bin/npx-cli.js');
  const fakeProcess = {argv: [process.execPath, filename, ...args]};
  const requireForTest = name => {
    if (name === '../lib/cli.js') return () => {};
    if (name === '@npmcli/config/lib/definitions') return parser;
    throw new Error(`Unexpected npx dependency: ${name}`);
  };
  requireForTest.resolve = name => {
    assert.equal(name, './npm-cli.js');
    return path.join(npmPath, 'bin/npm-cli.js');
  };
  vm.runInNewContext(fs.readFileSync(filename, 'utf8'), {process: fakeProcess, require: requireForTest, console});
  return fakeProcess.argv.slice(2);
}

test('actual npm config ignores a parent project and its npmrc', async t => {
  const f = fixture(t);
  const planned = plan(f, 'npm', ['prefix']);
  const config = await actualConfig(f, planned.args);
  assert.equal(config.localPrefix, f.cwd);
  assert.equal(config.get('tag'), 'latest');
  assert.equal(config.get('cache'), f.env.NPM_CONFIG_CACHE);
});

test('explicit in-package prefix and global cache prefix remain usable', async t => {
  const f = fixture(t);
  const selected = path.join(f.root, 'work', 'selected package');
  fs.mkdirSync(selected);
  const explicit = plan(f, 'npm', ['--prefix', selected, 'prefix']);
  assert.equal((await actualConfig(f, explicit.args)).localPrefix, selected);
  const global = plan(f, 'npm', ['--global', 'prefix']);
  assert.equal(global.prefix, f.env.NPM_CONFIG_PREFIX);
  assert.equal((await actualConfig(f, global.args)).globalPrefix, f.env.NPM_CONFIG_PREFIX);
});

test('outside prefixes and cwd are rejected before npm config loading', t => {
  const f = fixture(t);
  for (const args of [['--prefix', f.base, 'prefix'], [`--prefix=${f.base}`, 'prefix'], [`--prefi=${f.base}`, 'prefix']])
    assert.throws(() => plan(f, 'npm', args), /inside the current portable package/);
  assert.throws(() => plan({...f, cwd: f.base}, 'npm', ['prefix']), /inside the current portable package/);
});

test('project npmrc links are rejected without loading their target', t => {
  const f = fixture(t);
  const dest = path.join(f.cwd, '.npmrc');
  try { fs.linkSync(path.join(f.base, '.npmrc'), dest); }
  catch (error) { t.skip(`Hardlink creation unavailable: ${error.code}`); return; }
  assert.throws(() => plan(f, 'npm', ['prefix']), /single-link files/);
});

test('npx keeps target arguments intact and prevents parent discovery', async t => {
  const f = fixture(t);
  const target = ['example-tool', '--prefix', f.base, 'literal $(text) & value'];
  for (const options of [[], ['--yes'], ['-p', 'synthetic-package'], ['--package=synthetic-package']]) {
    const planned = plan(f, 'npx', [...options, ...target]);
    assert.deepEqual(planned.args.slice(-target.length), target);
    const transformed = actualNpxArguments(planned.args);
    assert.deepEqual(transformed.slice(transformed.indexOf('--') + 1), target);
    assert.equal((await actualConfig(f, transformed)).localPrefix, f.cwd);
  }
});

test('npx validates explicit prefix options before its command', async t => {
  const f = fixture(t);
  const prefix = path.join(f.root, 'work');
  const planned = plan(f, 'npx', ['--prefix', prefix, 'example-tool']);
  assert.equal((await actualConfig(f, actualNpxArguments(planned.args))).localPrefix, prefix);
  assert.throws(() => plan(f, 'npx', ['--prefix', f.base, 'example-tool']), /inside the current portable package/);
});

test('npm -- preserves subcommand options without interpreting its prefix', async t => {
  const f = fixture(t);
  const target = ['--prefix', f.base];
  const planned = plan(f, 'npm', ['run', 'example', '--', ...target]);
  assert.deepEqual(planned.args.slice(-target.length), target);
  assert.equal((await actualConfig(f, planned.args)).localPrefix, f.cwd);
});

test('stale state paths rebase while safe session paths are retained', t => {
  const f = fixture(t);
  const cache = path.join(f.root, 'tmp', 'session-cache');
  const env = portableEnvironment(f.root, {HOME: f.base, NPM_CONFIG_CACHE: cache,
    NPM_CONFIG_USERCONFIG: path.join(f.base, '.npmrc'), NODE_OPTIONS: '--require outside.js'});
  assert.equal(env.HOME, path.join(f.root, 'home-runtime'));
  assert.equal(env.NPM_CONFIG_CACHE, cache);
  assert.equal(env.NPM_CONFIG_USERCONFIG, path.join(f.root, 'home-runtime', '.npmrc'));
  assert.equal(env.NODE_OPTIONS, undefined);
});


test('inherited npm path options cannot redirect files outside the package', t => {
  const f = fixture(t);
  for (const [name, value] of Object.entries({
    npm_config_cafile: path.join(f.base, 'outside.pem'),
    NPM_CONFIG_LOGS_DIR: path.join(f.base, 'outside-logs'),
    NPM_CONFIG_INIT_MODULE: path.join(f.base, 'outside-init.js'),
    NPM_CONFIG_PROVENANCE_FILE: path.join(f.base, 'outside.json'),
    NPM_CONFIG_PACK_DESTINATION: f.base,
  })) {
    const env = portableEnvironment(f.root, {...f.env, [name]: value});
    assert.throws(() => plan({...f, env}, 'npm', ['prefix']), /inside the current portable package/);
  }
});

test('config file preflight rejects external paths before following the config chain', async t => {
  const f = fixture(t);
  // Trusted bundled parser/defaults remain in the real package; only synthetic
  // configuration files are read. The external path must never be probed.
  const context = {...f, root: repository, npmPath, parser};
  const outside = path.join(path.dirname(repository), 'must-not-be-probed-npm-private');
  const npmrc = path.join(f.cwd, '.npmrc');
  for (const declaration of [
    `cafile=${outside}\n`, `globalconfig=${outside}\n`,
    `//registry.invalid/:certfile=${outside}\n`,
    `pack-destination=${outside}\n`,
  ]) {
    fs.writeFileSync(npmrc, declaration);
    const selected = planArguments({...context, mode: 'npm', args: ['prefix']});
    await assert.rejects(preflightConfigFiles(context, selected.config), /inside the current portable package/);
  }
  fs.writeFileSync(npmrc, 'registry=https://registry.npmjs.org/\nproxy=http://127.0.0.1:9999\n');
  const selected = planArguments({...context, mode: 'npm', args: ['prefix']});
  await preflightConfigFiles(context, selected.config);
  assert.equal(selected.config.data.get('cli').data.registry, 'https://registry.npmjs.org/');
  assert.equal(selected.config.data.get('cli').data.proxy, 'http://127.0.0.1:9999');
});
