'use strict';

// Keep npm's project discovery inside this portable package. The upstream CLI
// remains intact; these checks are a launcher boundary, not a Node sandbox.
const fs = require('node:fs');
const path = require('node:path');

function inside(root, candidate, {directory = false, required = false} = {}) {
  root = path.resolve(root);
  const absolute = path.resolve(candidate);
  const relative = path.relative(root, absolute);
  if (relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative))
    throw new Error('Path must stay inside the current portable package');
  if (process.platform === 'win32' && (!/^[A-Za-z]:\\/.test(absolute) || absolute.slice(2).includes(':')))
    throw new Error('Use an ordinary local drive path');
  const parts = [];
  for (let cursor = absolute; ; cursor = path.dirname(cursor)) {
    parts.unshift(cursor);
    if (cursor === path.dirname(cursor)) break;
  }
  let leaf;
  for (const current of parts) {
    let info;
    try { info = fs.lstatSync(current); }
    catch (error) {
      if (error.code === 'ENOENT' && !required) continue;
      throw error;
    }
    if (info.isSymbolicLink()) throw new Error('Portable npm paths must not contain links');
    if (current !== absolute && !info.isDirectory()) throw new Error('Invalid path ancestor');
    if (current === absolute) leaf = info;
  }
  if (leaf) {
    if (directory ? !leaf.isDirectory() : !leaf.isFile() || leaf.nlink !== 1)
      throw new Error('Portable npm requires ordinary directories and single-link files');
  }
  return absolute;
}

function windowsSystemRoot(inherited) {
  const systemRoot = String(inherited.SystemRoot || inherited.SYSTEMROOT || inherited.WINDIR || '');
  // The ordinary Windows drive root has one backslash after the colon.
  if (!/^[A-Za-z]:\\/.test(systemRoot) || systemRoot.slice(2).includes(':') ||
      systemRoot.charAt(3) === '\\' || systemRoot.includes('\0') ||
      systemRoot.split('\\').some(part => part === '.' || part === '..'))
    throw new Error('Portable npm requires an ordinary Windows system root');
  return path.win32.normalize(systemRoot);
}

function portableEnvironment(root, inherited) {
  const env = {...inherited};
  const values = {
    HOME: 'home-runtime', USERPROFILE: 'home-runtime', APPDATA: 'appdata',
    LOCALAPPDATA: 'localappdata', PROGRAMDATA: 'programdata', ALLUSERSPROFILE: 'programdata',
    TEMP: 'tmp', TMP: 'tmp', TMPDIR: 'tmp',
    XDG_CONFIG_HOME: 'appdata', XDG_DATA_HOME: 'localappdata',
    XDG_STATE_HOME: 'localappdata/state', XDG_CACHE_HOME: 'cache/xdg',
    NPM_CONFIG_CACHE: 'cache/npm', NPM_CONFIG_PREFIX: 'cache/npm-prefix',
    NPM_CONFIG_USERCONFIG: 'home-runtime/.npmrc', NPM_CONFIG_GLOBALCONFIG: 'cache/npm/global.npmrc',
  };
  const files = new Set(['NPM_CONFIG_USERCONFIG', 'NPM_CONFIG_GLOBALCONFIG']);
  // Preserve the main launcher's package-local session caches. A stale inherited
  // path is replaced without probing that old/outside location.
  for (const [key, relative] of Object.entries(values)) {
    let value = path.join(root, relative);
    if (inherited[key]) {
      const candidate = path.resolve(inherited[key]);
      const rel = path.relative(root, candidate);
      if (rel !== '..' && !rel.startsWith(`..${path.sep}`) && !path.isAbsolute(rel)) value = candidate;
    }
    for (const name of Object.keys(env)) if (name.toUpperCase() === key) delete env[name];
    env[key] = inside(root, value, {directory: !files.has(key)});
  }
  // Direct npm/npx CMD entry points must not inherit host lifecycle injection:
  // npm v12 does not type script-shell or node-options as filesystem paths.
  for (const key of Object.keys(env)) {
    if (/^(NPM_CONFIG_(?:SCRIPT_SHELL|NODE_OPTIONS)|NODE_OPTIONS|NODE_PATH|NODE_EXTRA_CA_CERTS|NODE_COMPILE_CACHE|NODE_V8_COVERAGE|NODE_REDIRECT_WARNINGS|OPENSSL_CONF|SSL_CERT_FILE|SSL_CERT_DIR)$/i.test(key)) delete env[key];
  }
  if (process.platform === 'win32') {
    // Preserve only package-local PATH items (including the main launcher's
    // optional tools) plus Windows' required system executables.
    const windows = windowsSystemRoot(inherited);
    const localDirs = ['tool\\\\bin', 'tool\\\\python', 'tool\\\\node', 'tool\\\\android\\\\platform-tools']
      .map(relative => inside(root, path.win32.join(root, relative), {directory: true}));
    const retained = [];
    for (const item of String(inherited.PATH || inherited.Path || '').split(';')) {
      const candidate = item.trim();
      if (!candidate || candidate.includes('"')) continue;
      try { retained.push(inside(root, candidate, {directory: true})); }
      catch { /* Do not inspect or inherit outside PATH entries. */ }
    }
    const systemDirs = [path.win32.join(windows, 'System32'), windows,
      path.win32.join(windows, 'System32', 'WindowsPowerShell', 'v1.0'),
      path.win32.join(windows, 'System32', 'Wbem')];
    const seen = new Set(), safePaths = [];
    for (const item of [...localDirs, ...retained, ...systemDirs]) {
      const key = item.toLowerCase();
      if (!seen.has(key)) { seen.add(key); safePaths.push(item); }
    }
    for (const key of Object.keys(env)) {
      if (key.toUpperCase() === 'PATH' || key.toUpperCase() === 'COMSPEC') delete env[key];
    }
    env.PATH = safePaths.join(';');
    env.ComSpec = path.win32.join(windows, 'System32', 'cmd.exe');
  }
  env.NPM_CONFIG_UPDATE_NOTIFIER = 'false';
  return env;
}

// Match the upstream npx boundary: everything after the first positional
// command (or --) belongs to that command, including its own --prefix flag.
function npxOptionCount(args, definitions, shorthands) {
  const switches = new Set(['always-spawn', 'ignore-existing', 'shell-auto-fallback',
    'no-install', 'quiet', 'q', 'version', 'v', 'help', 'h']);
  for (const [key, {type}] of Object.entries(definitions)) {
    if (type === Boolean || Array.isArray(type) && type.includes(Boolean)) switches.add(key);
  }
  const options = new Set(['npm', 'node-arg', 'n', 'package', 'p', 'cache', 'userconfig', 'call', 'c', 'shell']);
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--' || !arg.startsWith('-')) return i;
    const [key, ...value] = arg.replace(/^-+/, '').split('=');
    const expanded = shorthands[key];
    const takesValue = options.has(key) || (expanded && expanded.length === 1
      ? !switches.has(expanded[0].replace(/^--/, '')) : !switches.has(key));
    if (!value.length && takesValue && (options.has(key) || args[i + 1] && !args[i + 1].startsWith('-'))) i++;
  }
  return args.length;
}

function planArguments({root, cwd, mode, args, env, npmPath, parser}) {
  if (!['npm', 'npx'].includes(mode)) throw new Error('Use npm or npx');
  cwd = inside(root, cwd, {directory: true, required: true});
  const end = mode === 'npx' ? npxOptionCount(args, parser.definitions, parser.shorthands)
    : (args.indexOf('--') < 0 ? args.length : args.indexOf('--'));
  const config = new parser.Config({
    ...parser, npmPath, cwd, env, execPath: process.execPath,
    argv: [process.execPath, path.join(npmPath, 'bin/npm-cli.js'), ...args.slice(0, end)], warn: false,
  });
  // These stages parse defaults and arguments only; no user/project config IO.
  config.loadDefaults();
  config.loadCLI();
  config.loadEnv();
  const cli = config.data.get('cli').data;
  const global = cli.global === true || cli.location === 'global';
  const selected = Object.hasOwn(cli, 'prefix') ? cli.prefix : global ? env.NPM_CONFIG_PREFIX : cwd;
  if (typeof selected !== 'string' || !selected) throw new Error('npm --prefix requires a package-local directory');
  const prefix = inside(root, path.resolve(cwd, selected), {directory: true});
  for (const file of ['package.json', '.npmrc']) inside(root, path.join(prefix, file));
  validateConfigPaths(root, config, cwd, parser.definitions, false);
  // Last CLI occurrence wins, including aliases parsed by bundled npm's nopt.
  // Preflight uses the same fixed prefix as the eventual CLI invocation.
  cli.prefix = prefix;
  return {prefix, config, args: [...args.slice(0, end), `--prefix=${prefix}`, ...args.slice(end)]};
}

function validateConfigPaths(root, config, cwd, definitions, includeDefaults = true) {
  const directories = new Set(['prefix', 'cache', 'logs-dir', 'pack-destination']);
  const names = new Set(['pack-destination']);
  for (const [name, definition] of Object.entries(definitions)) {
    if (definition.type === path || Array.isArray(definition.type) && definition.type.includes(path)) names.add(name);
  }
  const check = (name, value) => {
    if (value === null || value === undefined || value === '') return;
    if (typeof value !== 'string') throw new Error('Invalid npm path configuration');
    inside(root, path.resolve(cwd, value), {directory: directories.has(name)});
  };
  // npm flattens each source independently; even an overridden cafile can be
  // opened while flattening. Check all explicit sources, not just the winner.
  for (const [where, {data}] of config.data) {
    if (where === 'default') continue;
    for (const name of Object.keys(data)) {
      // Explicit config sources must not use a host shell or inject a child
      // Node preload. npm v12 defines these as String rather than path.
      if (name === 'node-options' && data[name])
        throw new Error('Portable npm refuses injected lifecycle node-options');
      if (name === 'script-shell' && data[name]) {
        const shell = data[name];
        if (typeof shell !== 'string') throw new Error('Invalid npm script shell');
        if (!(process.platform === 'win32' && shell.toLowerCase() === 'cmd.exe')) {
          if (!path.isAbsolute(shell)) throw new Error('npm script-shell must be package-local and absolute');
          inside(root, shell, {required: true});
        }
      }
      if (names.has(name) || /:(?:certfile|keyfile)$/.test(name)) check(name, data[name]);
    }
  }
  if (includeDefaults) {
    const effective = config.data.get('cli').data;
    for (const name of names) check(name, effective[name]);
  }
}

async function preflightConfigFiles({root, cwd, npmPath, parser}, config) {
  // Parse only checked package-local files with npm's own parser. Each source
  // can choose the next config file, so validate before every subsequent read.
  // No flatten/get-flat call is made here: cafile contents stay unread until
  // every source's paths have passed validation.
  inside(root, path.join(npmPath, 'npmrc'));
  await config.loadBuiltinConfig();
  validateConfigPaths(root, config, cwd, parser.definitions);
  await config.loadProjectConfig();
  validateConfigPaths(root, config, cwd, parser.definitions);
  inside(root, config.data.get('cli').data.userconfig);
  await config.loadUserConfig();
  validateConfigPaths(root, config, cwd, parser.definitions);
  inside(root, config.data.get('cli').data.globalconfig);
  await config.loadGlobalConfig();
  validateConfigPaths(root, config, cwd, parser.definitions);
}

async function main() {
  const root = path.resolve(__dirname, '..', '..');
  for (const marker of ['codex.exe', 'env.ps1', 'tool/node/node.exe', 'tool/node/portable-npm.js'])
    inside(root, path.join(root, marker), {required: true});
  const npmPath = path.join(__dirname, 'node_modules/npm');
  const [mode, ...args] = process.argv.slice(2);
  if (!['npm', 'npx'].includes(mode)) throw new Error('Use npm or npx');
  const cliPath = inside(root, path.join(npmPath, 'bin', `${mode}-cli.js`), {required: true});
  inside(root, process.cwd(), {directory: true, required: true});
  const environment = portableEnvironment(root, process.env);
  for (const key of Object.keys(process.env)) if (!(key in environment)) delete process.env[key];
  Object.assign(process.env, environment);
  inside(root, path.join(npmPath, 'package.json'), {required: true});
  const configEntry = inside(root, path.join(npmPath, 'node_modules/@npmcli/config/lib/index.js'), {required: true});
  const definitionsEntry = inside(root, path.join(npmPath, 'node_modules/@npmcli/config/lib/definitions/index.js'), {required: true});
  const parser = {Config: require(configEntry), ...require(definitionsEntry)};
  const plan = planArguments({root, cwd: process.cwd(), mode, args, env: environment, npmPath, parser});
  await preflightConfigFiles({root, cwd: process.cwd(), npmPath, parser}, plan.config);
  process.argv = [process.execPath, cliPath, ...plan.args];
  require(cliPath);
}

if (require.main === module) {
  main().catch(error => {
    // Do not echo config contents, proxy credentials or private path values.
    process.stderr.write(`Portable npm refused unsafe or unreadable configuration (${error.code || error.name}).\n`);
    process.exitCode = 2;
  });
}

module.exports = {inside, windowsSystemRoot, portableEnvironment, planArguments, npxOptionCount, preflightConfigFiles};
