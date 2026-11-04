'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const {inside, windowsSystemRoot, portableEnvironment, corepackEnvironment, planCorepackArguments,
  planArguments, preflightConfigFiles} = require('../tool/node/portable-npm');

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
  // Windows tests must model the indispensable OS-provided SystemRoot.
  // Do not weaken the direct portable entrypoint's fail-closed root check.
  const systemEnv = process.platform === 'win32'
    ? {SystemRoot: process.env.SystemRoot || process.env.WINDIR} : {};
  const env = portableEnvironment(root, systemEnv);
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
  // Canonical prefix spellings must always reach the portable path guard.
  for (const args of [['--prefix', f.base, 'prefix'], [`--prefix=${f.base}`, 'prefix']])
    assert.throws(() => plan(f, 'npm', args), /inside the current portable package/);
  // npm 11 accepted --prefi as an alias; npm 12 explicitly rejects ambiguous
  // abbreviations before the path guard. Both outcomes fail closed. Do not
  // weaken the canonical --prefix assertions or permit an outside path.
  assert.throws(() => plan(f, 'npm', [`--prefi=${f.base}`, 'prefix']),
    /inside the current portable package|Invalid abbreviated flag "--prefi"/);
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


test('Windows native npm refuses a missing system root even in a synthetic package', t => {
  if (process.platform !== 'win32') return;
  const f = fixture(t);
  assert.equal(typeof f.env.ComSpec, 'string');
  assert.throws(() => portableEnvironment(f.root, {}), /ordinary Windows system root/);
});

test('normal single-backslash Windows roots work; malformed host roots fail', t => {
  assert.equal(windowsSystemRoot({SystemRoot: 'C:\\Windows'}), 'C:\\Windows');
  assert.equal(windowsSystemRoot({WINDIR: 'D:\\WinNT'}), 'D:\\WinNT');
  for (const invalid of [
    '', 'C:Windows', 'C:/Windows', '\\\\server\\share',
    'C:\\\\Windows', 'C:\\Windows\\..\\outside',
    'C:\\Windows:stream', 'C:\\Windows\0x',
  ]) {
    assert.throws(() => windowsSystemRoot({SystemRoot: invalid}), /ordinary Windows system root/);
  }
});

test('direct npm shims discard inherited host shell and lifecycle Node options', t => {
  const f = fixture(t);
  const env = portableEnvironment(f.root, {
    ...f.env,
    NPM_CONFIG_SCRIPT_SHELL: path.join(f.base, 'host-shell.exe'),
    npm_config_node_options: '--require=host.js',
    NPM_CONFIG_SHELL: path.join(f.base, 'host-shell.exe'),
    NPM_CONFIG_EDITOR: path.join(f.base, 'host-editor.exe'),
    NPM_CONFIG_GIT: path.join(f.base, 'host-git.exe'),
    SHELL: path.join(f.base, 'host-shell.exe'),
    EDITOR: path.join(f.base, 'host-editor.exe'),
    VISUAL: path.join(f.base, 'host-editor.exe'),
    GIT_CONFIG_SYSTEM: path.join(f.base, 'host-gitconfig'),
    SSH_ASKPASS: path.join(f.base, 'host-ssh.exe'),
    NODE_OPTIONS: '--require=host.js',
  });
  assert.equal(Object.keys(env).filter(key =>
    /^(NPM_CONFIG_(SCRIPT_SHELL|NODE_OPTIONS|SHELL|EDITOR|GIT)|NODE_OPTIONS|SHELL|EDITOR|VISUAL|SSH_.*|GIT_CONFIG_SYSTEM)$/i.test(key)).length, 0);
  assert.equal(env.GIT_CONFIG_NOSYSTEM, '1');
});

test('local npmrc cannot load external script-shell or inject lifecycle Node options', async t => {
  const f = fixture(t);
  const context = {...f, root: repository, npmPath, parser};
  const outside = path.join(path.dirname(repository), 'must-not-be-probed-shell.exe');
  for (const declaration of [
    `script-shell=${outside}\n`,
    `shell=${outside}\n`,
    `editor=${outside}\n`,
    `git=${outside}\n`,
    `browser=${outside}\n`,
    `viewer=${outside}\n`,
    `node-options=--require=${outside}\n`,
  ]) {
    fs.writeFileSync(path.join(f.cwd, '.npmrc'), declaration);
    const selected = planArguments({...context, mode: 'npm', args: ['prefix']});
    await assert.rejects(preflightConfigFiles(context, selected.config),
      /inside the current portable package|lifecycle node-options|package-local absolute path/);
  }
});

test('inherited npm configuration and arbitrary host secrets do not reach the direct CLI', t => {
  const f = fixture(t);
  const injected = portableEnvironment(f.root, {
    ...f.env, OPENAI_API_KEY: 'host-secret', AWS_ACCESS_KEY_ID: 'host-secret',
    GITHUB_TOKEN: 'host-secret', PRIVATE_SESSION_VALUE: 'host-secret',
    RUSTC_WRAPPER: path.join(f.base, 'host.exe'), PYTHONPATH: f.base,
    NODE_OPTIONS: '--require=host.js', PSModulePath: path.join(f.base, 'Modules'),
    npm_config_cafile: path.join(f.base, 'private.pem'),
    NPM_CONFIG_PACK_DESTINATION: f.base,
    NPM_CONFIG_REGISTRY: 'https://host-registry.invalid/',
    NPM_CONFIG_HTTPS_PROXY: 'http://host.invalid:8443',
    HTTP_PROXY: 'http://host.invalid:8443', NO_PROXY: '*',
    CI: 'true', TERM: 'xterm-256color',
  });
  for (const name of ['OPENAI_API_KEY','AWS_ACCESS_KEY_ID','GITHUB_TOKEN',
    'PRIVATE_SESSION_VALUE','RUSTC_WRAPPER','PYTHONPATH','NODE_OPTIONS',
    'npm_config_cafile','NPM_CONFIG_PACK_DESTINATION','NPM_CONFIG_REGISTRY',
    'NPM_CONFIG_HTTPS_PROXY','HTTP_PROXY','NO_PROXY']) {
    assert.equal(Object.keys(injected).some(k => k.toUpperCase() === name.toUpperCase()),
      false, 'Must not inherit: ' + name);
  }
  assert.equal(injected.CI, 'true');
  assert.equal(injected.TERM, 'xterm-256color');
  assert.equal(injected.PIP_CONFIG_FILE, 'nul');
  assert.equal(injected.PNPM_STORE_DIR, path.join(f.root, 'cache', 'pnpm-store'));
  assert.equal(injected.PSModuleAnalysisCachePath, 'NUL');
  assert.equal(plan({...f, env: injected}, 'npm', ['prefix']).prefix, f.cwd);
});

test('package-authorized proxy remains usable; host proxy and stale roots are dropped', t => {
  const f = fixture(t);
  const parent = {...f.env, HTTP_PROXY: 'http://127.0.0.1:10808',
    NO_PROXY: 'localhost', CODEX_INSTALL_DIR: f.root,
    CODEX_HOME: path.join(f.root, 'home'),
    CODEX_PROXY_ENABLED: 'true', CODEX_PROXY_FOR_SUBPROCESS: 'true',
    CODEX_SANDBOX_NETWORK_ACCESS: 'true'};
  const ok = portableEnvironment(f.root, parent);
  assert.equal(ok.HTTP_PROXY, parent.HTTP_PROXY);
  assert.equal(ok.NO_PROXY, parent.NO_PROXY);
  assert.equal(ok.CODEX_INSTALL_DIR, undefined);
  for (const overrides of [
    {CODEX_PROXY_FOR_SUBPROCESS: 'false'}, {CODEX_SANDBOX_NETWORK_ACCESS: 'false'},
    {CODEX_PROXY_ENABLED: 'false'}, {CODEX_INSTALL_DIR: f.base},
    {CODEX_HOME: path.join(f.base, 'home')},
  ]) assert.equal(portableEnvironment(f.root, {...parent, ...overrides}).HTTP_PROXY, undefined);
});

test('Windows child home drive and module path are rebuilt inside the package', t => {
  if (process.platform !== 'win32') return;
  const f = fixture(t);
  const e = portableEnvironment(f.root, {...f.env,
    HOMEDRIVE: 'Z:', HOMEPATH: '\\Users\\Host', PSModulePath: 'Z:\\HostModules'});
  assert.equal(e.HOMEDRIVE, path.win32.parse(f.root).root.slice(0, 2));
  assert.equal(e.HOMEPATH, path.win32.resolve(e.HOME).slice(2));
  assert.ok(e.PSModulePath.includes(path.win32.join(f.root, 'cache', 'powershell', 'modules')));
  assert.ok(!e.PSModulePath.includes('Z:\\HostModules'));
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

test('Corepack direct entry clears host overrides and keeps its cache inside the package', t => {
  const f = fixture(t);
  const injected = corepackEnvironment(f.root, {
    ...f.env,
    COREPACK_HOME: f.base,
    COREPACK_ENV_FILE: path.join(f.base, '.corepack.env'),
    COREPACK_NPM_TOKEN: 'host-secret',
    COREPACK_NPM_REGISTRY: 'https://host.invalid',
    COREPACK_ENABLE_UNSAFE_CUSTOM_URLS: '1',
    COREPACK_INTEGRITY_KEYS: '0',
    YARN_RC_FILENAME: path.join(f.base, '.yarnrc.yml'),
    PNPM_STORE_DIR: path.join(f.base, 'pnpm-store'),
  }, f.cwd);
  assert.equal(injected.COREPACK_HOME, path.join(f.root, 'cache', 'corepack'));
  assert.equal(injected.COREPACK_ENV_FILE, '0');
  assert.equal(injected.COREPACK_ENABLE_UNSAFE_CUSTOM_URLS, '0');
  assert.equal(injected.COREPACK_ENABLE_PROJECT_SPEC, '0');
  for (const name of ['COREPACK_NPM_TOKEN', 'COREPACK_NPM_REGISTRY',
    'COREPACK_INTEGRITY_KEYS', 'YARN_RC_FILENAME'])
    assert.equal(injected[name], undefined);
  assert.equal(injected.YARN_CACHE_FOLDER, path.join(f.root, 'cache', 'yarn'));
  assert.equal(injected.PNPM_HOME, path.join(f.root, 'cache', 'pnpm'));
  assert.equal(injected.PNPM_STORE_DIR, path.join(f.root, 'cache', 'pnpm-store'));
  assert.equal(injected.LOCALAPPDATA, path.join(f.root, 'localappdata'));
});

test('Corepack honors only package-local project discovery', t => {
  const f = fixture(t);
  // The fixture already has a package.json in the untrusted parent.
  assert.equal(corepackEnvironment(f.root, f.env, f.cwd).COREPACK_ENABLE_PROJECT_SPEC, '0');
  const manifest = path.join(f.root, 'work', 'package.json');
  fs.writeFileSync(manifest, '{"name":"portable-project","version":"1.0.0"}');
  assert.equal(corepackEnvironment(f.root, f.env, f.cwd).COREPACK_ENABLE_PROJECT_SPEC, '1');
});

test('Corepack preserves ordinary commands but refuses unmanaged shims and outside files', t => {
  const f = fixture(t);
  const archive = path.join(f.cwd, 'manager.tgz');
  fs.writeFileSync(archive, 'fixture');
  assert.deepEqual(planCorepackArguments(f.root, f.cwd, ['--version']), ['--version']);
  assert.deepEqual(planCorepackArguments(f.root, f.cwd, ['pack', '-o', 'output.tgz']),
    ['pack', '-o', 'output.tgz']);
  assert.deepEqual(planCorepackArguments(f.root, f.cwd,
    ['install', '-g', '--cache-only', archive]),
    ['install', '-g', '--cache-only', archive]);
  for (const command of [['enable'], ['enable', 'npm'], ['disable', 'npm']])
    assert.throws(() => planCorepackArguments(f.root, f.cwd, command), /unmanaged/);
  // These are explicitly passed to the package manager, not Corepack's
  // pack/install archive handling. No accidental CLI regression.
  for (const command of [
    ['pnpm', 'install', '-o', path.join(f.base, 'manager-specific-output')],
    ['yarn', '--output=' + path.join(f.base, 'manager-specific-output')],
    ['pnpm', 'install', '--cache-only', path.join(f.base, 'manager-data')],
  ]) assert.deepEqual(planCorepackArguments(f.root, f.cwd, command), command);
  assert.deepEqual(planCorepackArguments(f.root, f.cwd,
    ['install', '-g', '--install-directory', 'ordinary-forwarded-option']),
    ['install', '-g', '--install-directory', 'ordinary-forwarded-option']);
  for (const command of [
    ['pack', '-o', path.join(f.base, 'outside.tgz')],
    ['pack', '--output=' + path.join(f.base, 'outside.tgz')],
    ['install', '-g', '--cache-only', path.join(f.base, 'outside.tgz')],
  ])
    assert.throws(() => planCorepackArguments(f.root, f.cwd, command),
      /inside the current portable package/);
  assert.throws(() => planCorepackArguments(f.root, f.cwd, ['pack', '--output']),
    /file argument is required/);
});
