# 正式原 ZIP v0.172.0-portable.1 覆盖索引（只读证据整理）

- 冻结来源 `4fb0b50228057cd0be41fbb191e15e065e64e368`，AC [45739266926](https://github.com/rileyaaa/Portable/actions/runs/45739266926)，原 ZIP SHA-256 `a406e4487bde19057491b6515f7abcab74faf2e3437366b0b23f9940af5760dc`。
- 原始 JSON：[`release_audit_v0.172.0-portable.1-wrapper-corrected.json`](release_audit_v0.172.0-portable.1-wrapper-corrected.json)，Git blob `9fd88202bd73c79ad4e7dce79d2233f0aaa4ff5e`。新的机器可核验索引：[original_release_45739266926_coverage.json](original_release_45739266926_coverage.json)，逐条使用原 rows 数组的 **1 起始编号**，保留 mode、item、status 与源码引用；不改原 JSON、不引入 dev 结果。
- 9076 个原始 ZIP 成员完整性通过，功能 rows 共 576：PASS_ACTUAL=146；PROPAGATION_ONLY=157；KNOWN_LIMIT=6；FAIL=33；IDENTITY_ONLY=150；NOT_APPLICABLE=67；OBSERVED=2；NOT_REPEATED=1；NOT_RUN=13；BLOCKED_UNVERIFIED=1。消费者步骤完成不等于全通过。

| 清单 | 已验范围 | 已验范围+限制 | 限制/失败/条件不具备 | 未验 | 合计 |
|---|---:|---:|---:|---:|---:|
| entries | 36 | 4 | 38 | 314 | 392 |
| env | 42 | 7 | 0 | 122 | 171 |
| python | 40 | 3 | 1 | 5 | 49 |
| npm | 0 | 0 | 0 | 149 | 149 |
| mcp | 7 | 0 | 0 | 13 | 20 |

**分类范围**：已验范围只证明原始链接的具体 consumer 断言（可能是父入口或组合配置），不是整工具或所有模式/参数；有失败、已知限制或不适用时并列。仅文件完整性、metadata/version、环境变量传递、观察和未执行均不算功能通过。原脚本中的引用/内部/条件变量并不都是可启用用户配置。

## 尚无实际消费证据的变量

- `ADB_VENDOR_KEYS`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 3:PROPAGATION_ONLY, 181:PROPAGATION_ONLY, 363:PROPAGATION_ONLY
- `AI_MODELS_B64`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `AI_MODELS_OUTDIR`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `AI_MODELS_PS1`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `AI_MODELS_RC`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `ALLUSERSPROFILE`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 4:PROPAGATION_ONLY, 182:PROPAGATION_ONLY, 364:PROPAGATION_ONLY
- `ANDROID_HOME`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `ANDROID_SDK_HOME`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 5:PROPAGATION_ONLY, 184:PROPAGATION_ONLY, 365:PROPAGATION_ONLY
- `ANDROID_SDK_ROOT`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `ANDROID_USER_HOME`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 6:PROPAGATION_ONLY, 185:PROPAGATION_ONLY, 366:PROPAGATION_ONLY
- `APKTOOL_FRAMEWORK_DIR`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 7:PROPAGATION_ONLY, 186:PROPAGATION_ONLY, 367:PROPAGATION_ONLY
- `APK_LAB_CACHE_DIR`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 8:PROPAGATION_ONLY, 187:PROPAGATION_ONLY, 368:PROPAGATION_ONLY
- `APK_LAB_JOBS_DIR`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 9:PROPAGATION_ONLY, 188:PROPAGATION_ONLY, 369:PROPAGATION_ONLY
- `APK_LAB_TMP_DIR`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 10:PROPAGATION_ONLY, 189:PROPAGATION_ONLY, 370:PROPAGATION_ONLY
- `APPDATA`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 11:PROPAGATION_ONLY, 190:PROPAGATION_ONLY, 371:PROPAGATION_ONLY
- `APPIUM_HOME`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 12:PROPAGATION_ONLY, 191:PROPAGATION_ONLY, 372:PROPAGATION_ONLY
- `CD`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_ACCOUNT_JSON_AUTH`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_ALLOW_HOST_SYSTEM_CONFIG`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_BROWSER_LOGIN_FLOW`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_DISABLE_APPS`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_DISABLE_WEBSOCKET`：synthetic HTTP Responses succeeded; no independent websocket toggle/consumer comparison；原 rows 177:PASS_ACTUAL, 359:PASS_ACTUAL, 537:PASS_ACTUAL
- `CODEX_ENABLE_PLUGINS`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 13:PROPAGATION_ONLY, 192:PROPAGATION_ONLY, 373:PROPAGATION_ONLY
- `CODEX_ENABLE_PLUGIN_SHARING`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 14:PROPAGATION_ONLY, 193:PROPAGATION_ONLY, 374:PROPAGATION_ONLY
- `CODEX_EXIT_CODE`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_FAST_MODE`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_LOGIN_JSON_ALLOW_DIRECT`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_LOGIN_JSON_ALLOW_DIRECT_PARALLEL`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_LOGIN_JSON_CONNECT_TIMEOUT_SEC`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_LOGIN_JSON_HTTP_BACKEND`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_LOGIN_JSON_JOB_TIMEOUT_SEC`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_LOGIN_JSON_MAX_CREDENTIALS`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_LOGIN_JSON_MAX_FILES`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_LOGIN_JSON_PROXY_MODE`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_LOGIN_JSON_PROXY_MODE_OVERRIDE`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_LOGIN_JSON_THROTTLE`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_MODEL_CONTEXT_WINDOW`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_MODEL_MODALITIES`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_OSS_BASE_URL`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_OSS_PORT`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_PORTABLE_ALLOW_CUSTOM_MANUAL_URL`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_PORTABLE_INTERNAL_LOGIN_MUTEX_TOKEN`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_PORTABLE_MAINTENANCE_LAUNCHER`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_PROVIDER_ID`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_PROVIDER_MODE`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_PROVIDER_NAME`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_PROXY_BRIDGE_TOKEN`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_REASONING_EFFORT`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_REPARSE_ATTR`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_REPARSE_CURSOR`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_REPARSE_LEAF`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_REPARSE_PARENT`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_REPARSE_TARGET`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_STARTUP_INTERACTIVE`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_STATUS_LINE_DIR_ITEM`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_TUI_FULLSCREEN_TRANSCRIPT`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `CODEX_WIRE_API`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `COMSPEC`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `D`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `DT`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `ERRORLEVEL`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `FERNFLOWER_JAR_PATH`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `FRIDA_CACHE_DIR`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 22:PROPAGATION_ONLY, 201:PROPAGATION_ONLY, 382:PROPAGATION_ONLY
- `GIT_CONFIG_NOSYSTEM`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 23:PROPAGATION_ONLY, 202:PROPAGATION_ONLY, 383:PROPAGATION_ONLY
- `GOCACHE`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `GOMODCACHE`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `GOPATH`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `GOROOT`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `GOTOOLCHAIN`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `GRADLE_USER_HOME`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 24:PROPAGATION_ONLY, 203:PROPAGATION_ONLY, 384:PROPAGATION_ONLY
- `HOME`：root containment only; Windows expanduser/Node checked USERPROFILE instead；原 rows 25:PROPAGATION_ONLY, 55:PASS_ACTUAL, 204:PROPAGATION_ONLY, 237:PASS_ACTUAL, 385:PROPAGATION_ONLY, 415:PASS_ACTUAL
- `HOMEDRIVE`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 26:PROPAGATION_ONLY, 205:PROPAGATION_ONLY, 386:PROPAGATION_ONLY
- `HOMEPATH`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 27:PROPAGATION_ONLY, 206:PROPAGATION_ONLY, 387:PROPAGATION_ONLY
- `HTTPS_PROXY`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 207:PROPAGATION_ONLY
- `JAVA_HOME`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `LATEST_MODEL_BASE_URL`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `LATEST_MODEL_URL`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `LOCALAPPDATA`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 28:PROPAGATION_ONLY, 209:PROPAGATION_ONLY, 388:PROPAGATION_ONLY
- `LOGIN_JSON_PROXY_CHOICE`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `M`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `MAVEN_OPTS`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 29:PROPAGATION_ONLY, 210:PROPAGATION_ONLY, 389:PROPAGATION_ONLY
- `MITMPROXY_HOME`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 30:PROPAGATION_ONLY, 211:PROPAGATION_ONLY, 390:PROPAGATION_ONLY
- `MY_X_TITLE`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `NAME`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `NODE_COMPILE_CACHE`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `NODE_REDIRECT_WARNINGS`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `NODE_REPL_HISTORY`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 31:PROPAGATION_ONLY, 212:PROPAGATION_ONLY, 391:PROPAGATION_ONLY
- `NODE_V8_COVERAGE`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `OPENSSL_CONF`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `PATHEXT`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `PIP_CONFIG_FILE`：asserted value nul only; actual pip operation did not independently prove config file suppression；原 rows 37:PROPAGATION_ONLY, 62:PASS_ACTUAL, 63:PASS_ACTUAL, 64:PASS_ACTUAL, 219:PROPAGATION_ONLY, 244:PASS_ACTUAL, 245:PASS_ACTUAL, 246:PASS_ACTUAL, 397:PROPAGATION_ONLY, 422:PASS_ACTUAL, 423:PASS_ACTUAL, 424:PASS_ACTUAL
- `PNPM_HOME`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 38:PROPAGATION_ONLY, 220:PROPAGATION_ONLY, 398:PROPAGATION_ONLY
- `PNPM_STORE_DIR`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 39:PROPAGATION_ONLY, 221:PROPAGATION_ONLY, 399:PROPAGATION_ONLY
- `POWERSHELL_TELEMETRY_OPTOUT`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 40:PROPAGATION_ONLY, 222:PROPAGATION_ONLY, 400:PROPAGATION_ONLY
- `PRINT_VERSION`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `PROGRAMDATA`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 41:PROPAGATION_ONLY, 223:PROPAGATION_ONLY, 401:PROPAGATION_ONLY
- `PSMODULEANALYSISCACHEPATH`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `PSMODULEPATH`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `PYTHONDONTWRITEBYTECODE`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `PYTHONNOUSERSITE`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `RANDOM`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `SSL_CERT_DIR`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `SSL_CERT_FILE`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `SYSTEMDRIVE`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `SYSTEMROOT`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `TMP`：path within package, default Python temporary file verified but TMP not separately selected；原 rows 47:PROPAGATION_ONLY, 55:PASS_ACTUAL, 139:PASS_ACTUAL, 229:PROPAGATION_ONLY, 237:PASS_ACTUAL, 321:PASS_ACTUAL, 407:PROPAGATION_ONLY, 415:PASS_ACTUAL, 499:PASS_ACTUAL
- `TMPDIR`：path within package, default Python temporary file verified but TMPDIR not separately selected；原 rows 48:PROPAGATION_ONLY, 55:PASS_ACTUAL, 230:PROPAGATION_ONLY, 237:PASS_ACTUAL, 408:PROPAGATION_ONLY, 415:PASS_ACTUAL
- `UV_CACHE_DIR`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `UV_PYTHON_INSTALL_DIR`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `UV_TOOL_BIN_DIR`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `UV_TOOL_DIR`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `WINDIR`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `XDG_CACHE_HOME`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 50:PROPAGATION_ONLY, 232:PROPAGATION_ONLY, 410:PROPAGATION_ONLY
- `XDG_CONFIG_HOME`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 51:PROPAGATION_ONLY, 233:PROPAGATION_ONLY, 411:PROPAGATION_ONLY
- `XDG_DATA_HOME`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 52:PROPAGATION_ONLY, 234:PROPAGATION_ONLY, 412:PROPAGATION_ONLY
- `XDG_STATE_HOME`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 53:PROPAGATION_ONLY, 235:PROPAGATION_ONLY, 413:PROPAGATION_ONLY
- `Y`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `YARN_CACHE_FOLDER`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；原 rows 54:PROPAGATION_ONLY, 236:PROPAGATION_ONLY, 414:PROPAGATION_ONLY
- `_CODEX_BOOTSTRAP_CODE1`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `_CODEX_BOOTSTRAP_CODE2`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `_CODEX_BOOTSTRAP_ENTRYDIR`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行
- `_CODEX_BOOTSTRAP_ROOT`：No demonstrated individual actual consumer; consult raw mode/row evidence and frozen source references.；无直接行

## 变量实际消费范围（不是每项独立开关实验）

| 变量 | 分类 | 具体范围 | 原始行 |
|---|---|---|---|
| `ALL_PROXY` | 已验范围 | actual synthetic SOCKS browser proxy | 183:yolo/PROPAGATION_ONLY, 568:mcp-stdio/PASS_ACTUAL |
| `CODEX_APPROVAL_POLICY` | 已验范围+限制 | generated native approval policy and command execution; real interactive approval not tested | 2:normal/PASS_ACTUAL, 180:yolo/PASS_ACTUAL, 362:maintenance/FAIL |
| `CODEX_AUTH_MODE` | 已验范围 | synthetic API-mode native session, not genuine account login | 177:normal/PASS_ACTUAL, 359:yolo/PASS_ACTUAL, 537:maintenance/PASS_ACTUAL, 570:mcp-native/PASS_ACTUAL |
| `CODEX_BASE_URL` | 已验范围 | actual synthetic Responses endpoint | 177:normal/PASS_ACTUAL, 359:yolo/PASS_ACTUAL, 537:maintenance/PASS_ACTUAL, 570:mcp-native/PASS_ACTUAL |
| `CODEX_ENV_HTTP_HEADERS_TOML` | 已验范围 | actual configured synthetic environment header vs host conflict | 177:normal/PASS_ACTUAL, 359:yolo/PASS_ACTUAL, 537:maintenance/PASS_ACTUAL, 570:mcp-native/PASS_ACTUAL |
| `CODEX_HOME` | 已验范围+限制 | actual home/config root and native Codex startup | 2:normal/PASS_ACTUAL, 15:normal/PROPAGATION_ONLY, 55:normal/PASS_ACTUAL, 180:yolo/PASS_ACTUAL, 194:yolo/PROPAGATION_ONLY, 237:yolo/PASS_ACTUAL, 362:maintenance/FAIL, 375:maintenance/PROPAGATION_ONLY, 415:maintenance/PASS_ACTUAL |
| `CODEX_HTTP_HEADERS_TOML` | 已验范围 | actual static synthetic HTTP headers | 177:normal/PASS_ACTUAL, 359:yolo/PASS_ACTUAL, 537:maintenance/PASS_ACTUAL, 570:mcp-native/PASS_ACTUAL |
| `CODEX_INSTALL_DIR` | 已验范围+限制 | actual root and executable/path use | 2:normal/PASS_ACTUAL, 16:normal/PROPAGATION_ONLY, 55:normal/PASS_ACTUAL, 139:normal/PASS_ACTUAL, 180:yolo/PASS_ACTUAL, 195:yolo/PROPAGATION_ONLY, 237:yolo/PASS_ACTUAL, 321:yolo/PASS_ACTUAL, 362:maintenance/FAIL, 376:maintenance/PROPAGATION_ONLY, 415:maintenance/PASS_ACTUAL, 499:maintenance/PASS_ACTUAL |
| `CODEX_MODEL` | 已验范围 | actual synthetic Responses configured model | 177:normal/PASS_ACTUAL, 359:yolo/PASS_ACTUAL, 537:maintenance/PASS_ACTUAL, 570:mcp-native/PASS_ACTUAL |
| `CODEX_PORTABLE_ALLOW_USER_MCP` | 已验范围 | native extension opt-in/extension-off actual behavior; separate explicit flag required | 177:normal/PASS_ACTUAL, 359:yolo/PASS_ACTUAL, 537:maintenance/PASS_ACTUAL, 570:mcp-native/PASS_ACTUAL |
| `CODEX_PORTABLE_PROFILE` | 已验范围+限制 | native mode policy; combined mode selector, actual normal/YOLO writes only; maintenance failed | 2:normal/PASS_ACTUAL, 180:yolo/PASS_ACTUAL, 362:maintenance/FAIL |
| `CODEX_PROXY_BRIDGE_HOST` | 已验范围 | actual combined bridge listener request | 344:yolo/PASS_ACTUAL |
| `CODEX_PROXY_BRIDGE_PORT` | 已验范围 | actual combined bridge listener request | 344:yolo/PASS_ACTUAL |
| `CODEX_PROXY_BYPASS_MODEL` | 已验范围 | actual synthetic Responses with bypass configuration; not individual toggle test | 359:yolo/PASS_ACTUAL |
| `CODEX_PROXY_ENABLED` | 已验范围 | actual combined bridge/browser proxy consumer | 17:normal/PROPAGATION_ONLY, 196:yolo/PROPAGATION_ONLY, 344:yolo/PASS_ACTUAL, 377:maintenance/PROPAGATION_ONLY, 567:mcp-stdio/PASS_ACTUAL, 568:mcp-stdio/PASS_ACTUAL |
| `CODEX_PROXY_FOR_SUBPROCESS` | 已验范围 | actual combined inherited HTTP proxy consumer | 18:normal/PROPAGATION_ONLY, 197:yolo/PROPAGATION_ONLY, 344:yolo/PASS_ACTUAL, 378:maintenance/PROPAGATION_ONLY, 567:mcp-stdio/PASS_ACTUAL, 568:mcp-stdio/PASS_ACTUAL |
| `CODEX_PROXY_HOST` | 已验范围 | actual combined generated proxy bridge consumer | 344:yolo/PASS_ACTUAL |
| `CODEX_PROXY_HTTP_BRIDGE` | 已验范围 | actual combined generated bridge consumer | 344:yolo/PASS_ACTUAL |
| `CODEX_PROXY_PORT` | 已验范围 | actual combined generated proxy bridge consumer | 344:yolo/PASS_ACTUAL |
| `CODEX_PROXY_PROTOCOL` | 已验范围 | actual combined generated SOCKS/HTTP bridge setup | 344:yolo/PASS_ACTUAL |
| `CODEX_PYTHON` | 已验范围+限制 | actual bundled Python execution in combined path/Office consumer, not isolated override experiment | 2:normal/PASS_ACTUAL, 19:normal/PROPAGATION_ONLY, 55:normal/PASS_ACTUAL, 139:normal/PASS_ACTUAL, 180:yolo/PASS_ACTUAL, 198:yolo/PROPAGATION_ONLY, 237:yolo/PASS_ACTUAL, 321:yolo/PASS_ACTUAL, 362:maintenance/FAIL, 379:maintenance/PROPAGATION_ONLY, 415:maintenance/PASS_ACTUAL, 499:maintenance/PASS_ACTUAL |
| `CODEX_SANDBOX_MODE` | 已验范围+限制 | actual mode write boundaries (normal/YOLO); maintenance failed | 2:normal/PASS_ACTUAL, 180:yolo/PASS_ACTUAL, 362:maintenance/FAIL |
| `CODEX_SQLITE_HOME` | 已验范围 | actual Codex SQLite files | 21:normal/PROPAGATION_ONLY, 178:normal/PASS_ACTUAL, 200:yolo/PROPAGATION_ONLY, 360:yolo/PASS_ACTUAL, 381:maintenance/PROPAGATION_ONLY, 538:maintenance/PASS_ACTUAL |
| `HTTP_PROXY` | 已验范围 | actual bridge and HTTP browser proxy on synthetic peer | 208:yolo/PROPAGATION_ONLY, 344:yolo/PASS_ACTUAL, 567:mcp-stdio/PASS_ACTUAL |
| `NO_PROXY` | 已验范围 | actual synthetic loopback bypass | 213:yolo/PROPAGATION_ONLY, 344:yolo/PASS_ACTUAL, 567:mcp-stdio/PASS_ACTUAL, 568:mcp-stdio/PASS_ACTUAL |
| `NPM_CONFIG_CACHE` | 已验范围 | actual npm config get cache; offline local script, not actual package cache install | 32:normal/PROPAGATION_ONLY, 115:normal/PASS_ACTUAL, 116:normal/PASS_ACTUAL, 214:yolo/PROPAGATION_ONLY, 297:yolo/PASS_ACTUAL, 298:yolo/PASS_ACTUAL, 392:maintenance/PROPAGATION_ONLY, 475:maintenance/PASS_ACTUAL, 476:maintenance/PASS_ACTUAL |
| `NPM_CONFIG_GLOBALCONFIG` | 已验范围 | actual npm config get globalconfig; no separate custom config file change test | 33:normal/PROPAGATION_ONLY, 115:normal/PASS_ACTUAL, 116:normal/PASS_ACTUAL, 215:yolo/PROPAGATION_ONLY, 297:yolo/PASS_ACTUAL, 298:yolo/PASS_ACTUAL, 393:maintenance/PROPAGATION_ONLY, 475:maintenance/PASS_ACTUAL, 476:maintenance/PASS_ACTUAL |
| `NPM_CONFIG_PREFIX` | 已验范围 | actual npm global prefix read, local prefix distinct | 34:normal/PROPAGATION_ONLY, 115:normal/PASS_ACTUAL, 116:normal/PASS_ACTUAL, 216:yolo/PROPAGATION_ONLY, 297:yolo/PASS_ACTUAL, 298:yolo/PASS_ACTUAL, 394:maintenance/PROPAGATION_ONLY, 475:maintenance/PASS_ACTUAL, 476:maintenance/PASS_ACTUAL |
| `NPM_CONFIG_USERCONFIG` | 已验范围 | actual npm config get userconfig; no separate custom config file change test | 35:normal/PROPAGATION_ONLY, 115:normal/PASS_ACTUAL, 116:normal/PASS_ACTUAL, 217:yolo/PROPAGATION_ONLY, 297:yolo/PASS_ACTUAL, 298:yolo/PASS_ACTUAL, 395:maintenance/PROPAGATION_ONLY, 475:maintenance/PASS_ACTUAL, 476:maintenance/PASS_ACTUAL |
| `PATH` | 已验范围+限制 | actual resolved commands; independent rg and f2py failed; per-command evidence only | 57:normal/FAIL, 59:normal/PASS_ACTUAL, 60:normal/PASS_ACTUAL, 61:normal/PASS_ACTUAL, 62:normal/PASS_ACTUAL, 63:normal/PASS_ACTUAL, 64:normal/PASS_ACTUAL, 115:normal/PASS_ACTUAL, 116:normal/PASS_ACTUAL, 117:normal/PASS_ACTUAL, 118:normal/PASS_ACTUAL, 119:normal/PASS_ACTUAL, 127:normal/PASS_ACTUAL, 128:normal/PASS_ACTUAL, 129:normal/PASS_ACTUAL, 130:normal/PASS_ACTUAL, 131:normal/PASS_ACTUAL, 132:normal/FAIL, 133:normal/PASS_ACTUAL, 239:yolo/FAIL, 241:yolo/PASS_ACTUAL, 242:yolo/PASS_ACTUAL, 243:yolo/PASS_ACTUAL, 244:yolo/PASS_ACTUAL, 245:yolo/PASS_ACTUAL, 246:yolo/PASS_ACTUAL, 297:yolo/PASS_ACTUAL, 298:yolo/PASS_ACTUAL, 299:yolo/PASS_ACTUAL, 300:yolo/PASS_ACTUAL, 301:yolo/PASS_ACTUAL, 309:yolo/PASS_ACTUAL, 310:yolo/PASS_ACTUAL, 311:yolo/PASS_ACTUAL, 312:yolo/PASS_ACTUAL, 313:yolo/PASS_ACTUAL, 314:yolo/FAIL, 315:yolo/PASS_ACTUAL, 345:yolo/FAIL, 417:maintenance/FAIL, 419:maintenance/PASS_ACTUAL, 420:maintenance/PASS_ACTUAL, 421:maintenance/PASS_ACTUAL, 422:maintenance/PASS_ACTUAL, 423:maintenance/PASS_ACTUAL, 424:maintenance/PASS_ACTUAL, 475:maintenance/PASS_ACTUAL, 476:maintenance/PASS_ACTUAL, 477:maintenance/PASS_ACTUAL, 478:maintenance/PASS_ACTUAL, 479:maintenance/PASS_ACTUAL, 487:maintenance/PASS_ACTUAL, 488:maintenance/PASS_ACTUAL, 489:maintenance/PASS_ACTUAL, 490:maintenance/PASS_ACTUAL, 491:maintenance/PASS_ACTUAL, 492:maintenance/FAIL, 493:maintenance/PASS_ACTUAL |
| `PIP_CACHE_DIR` | 已验范围 | actual pip cache dir consumer | 36:normal/PROPAGATION_ONLY, 62:normal/PASS_ACTUAL, 63:normal/PASS_ACTUAL, 64:normal/PASS_ACTUAL, 218:yolo/PROPAGATION_ONLY, 244:yolo/PASS_ACTUAL, 245:yolo/PASS_ACTUAL, 246:yolo/PASS_ACTUAL, 396:maintenance/PROPAGATION_ONLY, 422:maintenance/PASS_ACTUAL, 423:maintenance/PASS_ACTUAL, 424:maintenance/PASS_ACTUAL |
| `PYTHONPYCACHEPREFIX` | 已验范围 | actual sys.pycache_prefix, not all cache writes | 44:normal/PROPAGATION_ONLY, 55:normal/PASS_ACTUAL, 226:yolo/PROPAGATION_ONLY, 237:yolo/PASS_ACTUAL, 404:maintenance/PROPAGATION_ONLY, 415:maintenance/PASS_ACTUAL |
| `PYTHONUSERBASE` | 已验范围 | actual site.getuserbase equals variable | 45:normal/PROPAGATION_ONLY, 55:normal/PASS_ACTUAL, 227:yolo/PROPAGATION_ONLY, 237:yolo/PASS_ACTUAL, 405:maintenance/PROPAGATION_ONLY, 415:maintenance/PASS_ACTUAL |
| `TEMP` | 已验范围 | actual Python temporary file in root, Node tmpdir equals TEMP | 46:normal/PROPAGATION_ONLY, 55:normal/PASS_ACTUAL, 139:normal/PASS_ACTUAL, 228:yolo/PROPAGATION_ONLY, 237:yolo/PASS_ACTUAL, 321:yolo/PASS_ACTUAL, 406:maintenance/PROPAGATION_ONLY, 415:maintenance/PASS_ACTUAL, 499:maintenance/PASS_ACTUAL |
| `USERPROFILE` | 已验范围 | actual Python expanduser and Node homedir | 49:normal/PROPAGATION_ONLY, 55:normal/PASS_ACTUAL, 231:yolo/PROPAGATION_ONLY, 237:yolo/PASS_ACTUAL, 409:maintenance/PROPAGATION_ONLY, 415:maintenance/PASS_ACTUAL |

特别审阅冻结 `tests/audit_release_zip_consumer.py` 的 effective_paths/pip_alias 与 native API peer：TMP、TMPDIR、HOME、PIP_CONFIG_FILE、CODEX_DISABLE_WEBSOCKET 在已验组合行内，但没有各自独立实际生效证据，故不升级为已验。NPM_CONFIG_* 只证明 npm config get 对应值及本地脚本；不是实际依赖安装。正常/维护 external 网络未探测，loopback OBSERVED 不是外网隔离通过。

## 原始入口限制及未验范围

完整 392 路径（含 223 vendor 内部组件）、49 Python distributions、149 npm 包与全部 MCP 名称在 JSON 逐项列出。重点缺口：

- 33 FAIL 仍原样，包含 maintenance native policy、standalone rg、f2py、Office 四子脚本、SSH、Android sqlite3/etc1tool、指令安装器、HTTPX CLI、cleanup fixture。后续 dev 证据不能回溯改判原包。
- Windows 实际桌面 UIAutomation、真实账户登录/在线校验、外部 API/设备/SSH 目标、提权沙箱 helper、可选依赖安装与真实 LibreOffice 渲染、SDK/JDK/Android 设备操作等未验或条件不具备。不得用真实用户数据、未授权设备或改变原包来补测。
- MCP 原始已实际调用：browser_close, browser_evaluate, browser_navigate, browser_take_screenshot, browser_snapshot, browser_click, browser_tabs。未调用：browser_resize, browser_console_messages, browser_handle_dialog, browser_find, browser_fill_form, browser_press_key, browser_type, browser_navigate_back, browser_network_requests, browser_drag, browser_hover, browser_select_option, browser_wait_for。仅 schema 发现不能算运行。
- Python：49 个包版本/锁校验与独立 consumer 分开；无具体验证的包（或仅传递依赖）：altgraph, invoke, pefile, pywin32-ctypes, setuptools。149 npm 包仅父入口/完整性及 metadata，不为每个包宣称独立功能。

## 复核方式

在冻结 JSON 的 rows[n-1] 查看完整 detail/covers/env/packages；以原审计脚本同名函数核对真实断言，再决定是否需要定向原包验证。当前仅整理，不重跑原包或把后续 dev 移植结果写入本表。


## 2026-11-26 独立原包补证：45754353202

[AC 45754353202](https://github.com/rileyaaa/Portable/actions/runs/45754353202) 实际原始 ZIP 哈希及 9076 成员重新核对，中文空格搬迁；仅原包 `original_release_contracts.rows`，不计同一 JSON 中 dev OCR。原 576 行及 33 FAIL 不改；补充 23 行（21 PASS_ACTUAL、1 PASS_CONFIG_GATE、1 HARNESS_READY），不能把两次运行简单相加为独立功能数。以下 14 个原未验变量增加窄范围实际证据，负向拒绝或组合优先级不等于变量可启用。三个 config gate 仍不计实际 consumer。

| 变量 | 新证据行（本次 JSON） | 具体范围 |
| --- | --- | --- |
| `CODEX_ACCESS_TOKEN` | 4, 11, 14 | 实际拒绝非法本机覆盖及宿主继承；组合请求仍使用包内合成授权；不是该变量可用。 |
| `CODEX_API_KEY` | 3, 11, 13 | 实际拒绝非法本机覆盖及宿主继承；组合请求仍使用包内合成授权；不是该变量可用。 |
| `CODEX_MODEL_CATALOG_JSON` | 9 | 实际拒绝包外输出路径，未创建输出；不证明任意模型目录内容可用。 |
| `CODEX_MODEL_INSTRUCTIONS_FILE` | 8, 12 | 实际拒绝包外路径且原文件未变；包内指令 marker 出现在实际 Responses 请求。 |
| `CODEX_PORTABLE_ALLOW_HOST_PATH` | 5 | 实际拒绝本机覆盖；不证明所有宿主 PATH 或写入边界。 |
| `CODEX_QUERY_PARAMS_TOML` | 10 | 实际 loopback Responses 请求 2/2 匹配配置 query。 |
| `CODEX_SANDBOX_NETWORK_ACCESS` | 6 | 实际拒绝 env.local.ps1 覆盖策略；没有独立外网隔离或网络开启试验。 |
| `GH_TOKEN` | 15 | 实际 native child 未继承合成宿主值；不证明 GitHub CLI 登录或连接器。 |
| `GITHUB_TOKEN` | 16 | 实际 native child 未继承合成宿主值；不证明 GitHub CLI 登录或连接器。 |
| `NODE_EXTRA_CA_CERTS` | 19 | 实际 native child 未继承合成宿主值；没有独立 TLS 信任链比较。 |
| `NODE_OPTIONS` | 7, 17, 20 | 实际拒绝本机覆盖及宿主继承，真包内 Node 未执行宿主合成 preload。 |
| `NODE_PATH` | 18 | 实际 native child 未继承合成宿主值；没有独立模块加载路径比较。 |
| `OPENAI_API_KEY` | 11 | 实际 loopback Responses 请求 2/2 匹配包内合成 Authorization；不涉及真实账号或 API。 |
| `OPENAI_BASE_URL` | 11 | 宿主假地址与包内配置冲突的组合试验，实际请求抵达指定 loopback；不证明此变量可单独配置。 |

`CODEX_DISABLE_APPS`、`CODEX_ENABLE_PLUGINS`、`CODEX_ENABLE_PLUGIN_SHARING`：新 row 21 PASS_CONFIG_GATE；实际 child 配置为 false，未使用真实扩展、连接器或授权。原 `CODEX_DISABLE_WEBSOCKET`、ACL/SSH、Office 等限制保持原判。机器索引 `supplemental_raw_rows`、`supplemental_evidence` 使用独立 run_id / row_path；旧 rows 编号不变。原始 JSON 不改。
