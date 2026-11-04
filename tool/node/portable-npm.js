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

function inheritedValue(environment, name) {
  // Windows environment keys are case-insensitive.
  for (const [key, value] of Object.entries(environment))
    if (key.toUpperCase() === name.toUpperCase() && typeof value === 'string')
      return value;
  return '';
}

function portableEnvironment(root, inherited) {
  // Start from an allowlist: otherwise arbitrary host secrets, npm registry
  // settings and tool overrides flow into lifecycle scripts and grandchildren.
  const env = {};
  for (const name of [
    'SystemRoot', 'WINDIR', 'SystemDrive', 'PATHEXT', 'OS',
    'PROCESSOR_ARCHITECTURE', 'PROCESSOR_IDENTIFIER', 'NUMBER_OF_PROCESSORS',
    'USERNAME', 'USERDOMAIN', 'COMPUTERNAME', 'CI', 'TERM', 'COLORTERM',
    'NO_COLOR', 'FORCE_COLOR', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TZ',
  ]) {
    const value = inheritedValue(inherited, name);
    if (value) env[name] = value;
  }

  // Preserve the explicitly selected package proxy, never an ambient host
  // proxy. Package anchors are provenance hints, not an OS security token.
  const truthy = value => /^(?:1|true|yes|on)$/i.test(String(value).trim());
  const samePath = (a, b) => {
    if (!a) return false;
    const x = path.resolve(a), y = path.resolve(b);
    return process.platform === 'win32' ? x.toLowerCase() === y.toLowerCase() : x === y;
  };
  const forwardProxy = samePath(inheritedValue(inherited, 'CODEX_INSTALL_DIR'), root) &&
    samePath(inheritedValue(inherited, 'CODEX_HOME'), path.join(root, 'home')) &&
    truthy(inheritedValue(inherited, 'CODEX_PROXY_ENABLED')) &&
    truthy(inheritedValue(inherited, 'CODEX_PROXY_FOR_SUBPROCESS')) &&
    truthy(inheritedValue(inherited, 'CODEX_SANDBOX_NETWORK_ACCESS'));
  if (forwardProxy) {
    for (const name of ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
      'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy']) {
      const value = inheritedValue(inherited, name);
      if (value) env[name] = value;
    }
  }
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
  // Only these derived environment values, not host tool configuration.
  env.GIT_CONFIG_NOSYSTEM = '1';
  env.PIP_CONFIG_FILE = 'nul';
  env.PIP_NO_CACHE_DIR = '1';
  env.PIP_DISABLE_PIP_VERSION_CHECK = '1';
  env.PYTHONDONTWRITEBYTECODE = '1';
  env.PYTHONNOUSERSITE = '1';
  for (const [name, relative] of Object.entries({
    PYTHONUSERBASE: 'cache/python-userbase', PYTHONPYCACHEPREFIX: 'cache/pycache',
    YARN_CACHE_FOLDER: 'cache/yarn', PNPM_HOME: 'cache/pnpm',
    PNPM_STORE_DIR: 'cache/pnpm-store', GRADLE_USER_HOME: 'cache/gradle',
  })) env[name] = inside(root, path.join(root, relative), {directory: true});
  env.MAVEN_OPTS = '-Dmaven.repo.local="' + path.join(root, 'cache', 'maven') + '"';
  env.POWERSHELL_TELEMETRY_OPTOUT = '1';
  env.PSModuleAnalysisCachePath = 'NUL';
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
    const portableHome = path.win32.resolve(env.HOME);
    env.HOMEDRIVE = portableHome.slice(0, 2);
    env.HOMEPATH = portableHome.slice(2);
    env.PSModulePath = [
      inside(root, path.join(root, 'cache', 'powershell', 'modules'), {directory: true}),
      path.win32.join(windows, 'System32', 'WindowsPowerShell', 'v1.0', 'Modules'),
    ].join(';');
  }
  env.NPM_CONFIG_UPDATE_NOTIFIER = 'false';
  return env;
}

function corepackEnvironment(root, inherited, cwd) {
  const env = portableEnvironment(root, inherited);
  // portableEnvironment() starts from an allowlist, so no host COREPACK_*,
  // YARN_* or PNPM_* setting survives. Preserve the *reconstructed* package-
  // local Yarn/pnpm cache and executable paths for Corepack's grandchildren.
  // Removing them here would undo that isolation and can break normal tools.
  env.COREPACK_HOME = inside(root, path.join(root, 'cache', 'corepack'), {directory: true});
  env.COREPACK_ENV_FILE = '0';
  env.COREPACK_ENABLE_UNSAFE_CUSTOM_URLS = '0';

  // Corepack normally searches parent directories for package.json. A portable
  // cwd with no package metadata must NOT read a host parent project's settings.
  let cursor = inside(root, cwd, {directory: true, required: true});
  let localProject = false;
  const boundary = path.resolve(root);
  for (;;) {
    const manifest = inside(root, path.join(cursor, 'package.json'));
    if (fs.existsSync(manifest)) { localProject = true; break; }
    if (cursor === boundary) break;
    cursor = path.dirname(cursor);
  }
  env.COREPACK_ENABLE_PROJECT_SPEC = localProject ? '1' : '0';
  return env;
}

function planCorepackArguments(root, cwd, args) {
  inside(root, cwd, {directory: true, required: true});
  const command = args.find(arg => arg && !arg.startsWith('-')) || '';
  // Corepack enable emits unmanaged Yarn/pnpm shims, and enable npm can replace
  // the audited npm.cmd entirely; disable can delete them. Other commands work.
  if (command === 'enable' || command === 'disable')
    throw new Error('Portable Corepack refuses unmanaged enable/disable shims');
  // Other commands (for example "corepack pnpm ...") forward their options to
  // the manager. Do NOT interpret a Yarn/pnpm -o or --output as a Corepack
  // archive output or suppress arbitrary manager CLI features.
  if (!['pack', 'install'].includes(command)) return args;
  const checked = (value, required = false) => {
    if (!value || value.startsWith('-'))
      throw new Error('Corepack file argument is required');
    return inside(root, path.resolve(cwd, value), {required});
  };
  for (let i = 0; i < args.length; i++) {
    const argument = args[i];
    if (command === 'pack' && (argument === '-o' || argument === '--output')) {
      checked(args[++i]);
    } else if (command === 'pack' && argument.startsWith('--output=')) {
      checked(argument.slice('--output='.length));
    } else if (command === 'pack' && /^-o[^-]/.test(argument)) {
      checked(argument.slice(argument.startsWith('-o=') ? 3 : 2));
    } else if (command === 'install' && argument === '--cache-only') {
      checked(args[++i], true);
    } else if (command === 'install' && argument.startsWith('--cache-only=')) {
      checked(argument.slice('--cache-only='.length), true);
    }
  }
  return args;
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
      if (['script-shell', 'shell', 'editor', 'git', 'browser', 'viewer'].includes(name) &&
          data[name] !== undefined && data[name] !== null && data[name] !== false && data[name] !== '') {
        const executable = data[name];
        if (typeof executable !== 'string' || /[\r\n\0]/.test(executable))
          throw new Error('Invalid npm executable option');
        // Windows cmd.exe is required by npm lifecycle scripts. These short
        // command names resolve only via the already sanitized portable PATH.
        const builtin = process.platform === 'win32' && (
          (['script-shell', 'shell'].includes(name) && executable.toLowerCase() === 'cmd.exe') ||
          (name === 'browser' && executable === 'start'));
        const portableName = (name === 'git' && executable === 'git') ||
          (name === 'viewer' && executable === 'browser');
        if (!builtin && !portableName) {
          if (!path.isAbsolute(executable))
            throw new Error('npm executable option must use a package-local absolute path');
          inside(root, executable, {required: true});
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
  if (!['npm', 'npx', 'corepack'].includes(mode)) throw new Error('Use npm, npx or corepack');
  const cliPath = inside(root, mode === 'corepack'
    ? path.join(__dirname, 'node_modules/corepack/dist/corepack.js')
    : path.join(npmPath, 'bin', mode + '-cli.js'), {required: true});
  inside(root, process.cwd(), {directory: true, required: true});
  const environment = mode === 'corepack'
    ? corepackEnvironment(root, process.env, process.cwd())
    : portableEnvironment(root, process.env);
  if (mode === 'corepack') planCorepackArguments(root, process.cwd(), args);
  for (const key of Object.keys(process.env)) if (!(key in environment)) delete process.env[key];
  Object.assign(process.env, environment);
  if (mode === 'corepack') {
    process.argv = [process.execPath, cliPath, ...args];
    require(cliPath);
    return;
  }
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

module.exports = {inside, windowsSystemRoot, portableEnvironment, corepackEnvironment, planCorepackArguments,
  planArguments, npxOptionCount, preflightConfigFiles};
