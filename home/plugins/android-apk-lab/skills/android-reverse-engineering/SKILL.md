---
name: android-reverse-engineering
description: "Use only for an explicitly requested Android/APK task. Decompile Android APK, XAPK, JAR, and AAR files using jadx or Fernflower/Vineflower. Reverse engineer Android apps, extract HTTP API endpoints (Retrofit, OkHttp, Volley), and trace call flows from UI to network layer. Use when the user wants to decompile, analyze, or reverse engineer Android packages, find API endpoints, or follow call flows. 中文触发词：反编译APK、安卓逆向、提取API、分析安卓应用、反编译安卓、逆向工程、追踪调用链、提取接口"
---

## Task activation

Loading this skill, detecting an APK, or entering maintenance mode does not authorize execution. Do not run prerequisite probes, ADB, device discovery, servers, downloads, or installations until the user has requested the relevant Android/APK task. Use the existing authorization for the selected target/session; do not ask again for the same authorized operation. Device/helper installation and actions outside that scope need separate authorization. Resolve the current package root from this skill/script location and validate its markers and lexical ancestors first; environment roots such as `CODEX_INSTALL_DIR` are usable only after they match that current root. Never follow a stale root after moving the package.

## APK Lab portable override
For this portable Codex package, treat any upstream examples that mention user-home installs, global package managers, system PATH edits, Homebrew, winget, choco, scoop, or OS-level install locations as layout examples only. Place tools, caches, generated files, credentials, test outputs, and temporary files under the package root (`CODEX_INSTALL_DIR`, or parent of `CODEX_HOME`). Prefer `tool/android`, `cache/android`, `tmp/android`, and `work/apk-jobs`.

Portable execution boundary:
- Resolve executable commands to package-local tools under `CODEX_INSTALL_DIR` (or Windows system components explicitly required by the launcher). Never silently use host/global npm, Appium, Git, curl, Python, Java, Android SDK, or package-manager installs. `npx` may be used only with `--no-install`, from an explicitly selected project that is itself inside the Codex package.
- A connected phone, emulator, remote Android instance, or its filesystem/state is outside the Codex package. Before reading from or changing such a target, obtain explicit user approval for that target/session. Commands that mutate device state (`adb push/install/uninstall`, `adb shell am/pm/settings/input/chmod/rm/mv/cp`, Frida/Objection injection, Maestro/Appium sessions, reboot/root/trust changes) always require that approval before execution.


## Portable skill path

This Codex package does not define upstream assistant-specific plugin-root variables. Resolve this skill from the package root instead.

Bash / Git Bash:
```bash
APK_LAB_SKILL_ROOT="${CODEX_INSTALL_DIR}/home/plugins/android-apk-lab/skills/android-reverse-engineering"
```

PowerShell:
```powershell
$APK_LAB_SKILL_ROOT = Join-Path $env:CODEX_INSTALL_DIR 'home\plugins\android-apk-lab\skills\android-reverse-engineering'
```

All paths used by this skill must remain under `CODEX_INSTALL_DIR`.

# Android Reverse Engineering

Decompile Android APK, XAPK, JAR, and AAR files using jadx and Fernflower/Vineflower, trace call flows through application code and libraries, and produce structured documentation of extracted APIs. Two decompiler engines are supported — jadx for broad Android coverage and Fernflower for higher-quality output on complex Java code — and can be used together for comparison.

## Prerequisites

This skill requires **Java JDK 17+** and **jadx** to be installed. **Fernflower/Vineflower** and **dex2jar** are optional but recommended for better decompilation quality. On this Windows portable package, use the PowerShell checker first:

```powershell
& "$APK_LAB_SKILL_ROOT/scripts/check-deps.ps1"
```

Use the Bash checker only when a package-local Bash has been explicitly added and approved; never fall back to a host Git Bash/MSYS installation:
```bash
bash $APK_LAB_SKILL_ROOT/scripts/check-deps.sh
```

If anything is missing, follow the installation instructions in `$APK_LAB_SKILL_ROOT/references/setup-guide.md`.

## Workflow

### Phase 0: Fingerprint the App (recommended before anything else)

Before installing tools or decompiling, run a fast triage to determine what
kind of app you are looking at. **Decompiling Java is mostly useless for
Flutter, React Native, Cordova/Capacitor, and Xamarin apps** — the real code
lives elsewhere. The fingerprint script tells you which.

On Windows, use the package Python implementation (no Bash/grep dependency):
```powershell
& (Join-Path $env:CODEX_INSTALL_DIR 'tool\python\python.exe') `
  "$APK_LAB_SKILL_ROOT\scripts\fingerprint.py" <file.apk|file.xapk>
```

The Bash compatibility wrapper is only for an explicitly provisioned package-local Git Bash/MSYS environment; it delegates to the same hardened Python backend:
```bash
bash "$APK_LAB_SKILL_ROOT/scripts/fingerprint.sh" <file.apk|file.xapk>
```

It prints, in one screen:

- **Mobile framework** (Flutter / React Native / Cordova / Xamarin / Native Kotlin / etc.) with the file marker that triggered the verdict.
- **HTTP stack** (Retrofit, OkHttp, Ktor, Apollo, Volley) detected via DEX string scan — works even when class names are obfuscated.
- **DI / serialization** signals (Hilt, Dagger, Koin, kotlinx.serialization, Moshi, Gson, Jackson).
- **Obfuscation level** estimate based on root-level short-named packages.
- **Notable third-party SDKs** (AppsFlyer, Datadog, Sentry, Firebase, payment SDKs, support/chat SDKs, etc.).
- **Consolidated native libraries** across the base APK and all splits — XAPK split bundles often place `.so` files in `config.<abi>.apk`, not in `base.apk`.
- **Recommended next step**, which differs by framework (e.g. for Flutter the script suggests `blutter` / `strings libapp.so` rather than jadx).

If the fingerprint says the app is Flutter / RN / Cordova / Xamarin, **stop**
and switch to the framework-appropriate tooling. Phases 1–5 below assume a
native (Java/Kotlin) Android app.

### Phase 1: Verify Dependencies and Provision Them Only With Approval

Before decompiling, confirm that the required tools are available. If something is missing, report the package-local target and obtain explicit approval before provisioning it.

**Action**: Run the dependency check script. On Windows use the package PowerShell entry point:

```powershell
& "$APK_LAB_SKILL_ROOT/scripts/check-deps.ps1"
```

Only use the Bash version when Bash itself is package-local and explicitly available:
```bash
bash $APK_LAB_SKILL_ROOT/scripts/check-deps.sh
```

The output contains machine-readable lines:
- `INSTALL_REQUIRED:<dep>` — must be installed before proceeding
- `INSTALL_OPTIONAL:<dep>` — recommended but not blocking

**If required dependencies are missing** (exit code 1), use the portable locator only:

On Windows (PowerShell):
```powershell
& "$APK_LAB_SKILL_ROOT/scripts/install-dep.ps1" <dep>
```

The Bash locator is only for an explicitly provisioned package-local Bash:
```bash
bash $APK_LAB_SKILL_ROOT/scripts/install-dep.sh <dep>
```

These scripts **do not install anything on the host**. They only report the approved package-local target under `tool/android` and the upstream source. Any actual download or extraction must stay under `CODEX_INSTALL_DIR`; ask for explicit user approval before accessing or modifying anything outside the package. Never use `sudo`, OS package managers, user-profile installs, or persistent PATH edits for this portable workflow.

**For optional dependencies**, ask the user if they want to install them. Vineflower and dex2jar are recommended for best results.

After package-local provisioning, re-run `check-deps.ps1` on Windows (or the package-local Bash wrapper when explicitly available) to confirm everything is in place. Do not proceed to Phase 2 until all required dependencies are OK.

### Phase 2: Decompile

Use the decompile wrapper script to process the target file. The script supports three engines: `jadx`, `fernflower`, and `both`.

**Action**: Choose the engine and run the decompile script. The script handles APK, XAPK, JAR, and AAR files.
APK Lab inputs and outputs must stay inside `CODEX_INSTALL_DIR`; if the source artifact is outside the package, obtain user approval and copy it into a package work/input directory before running these helpers.

On Windows (PowerShell):
```powershell
& "$APK_LAB_SKILL_ROOT/scripts/decompile.ps1" [OPTIONS] <file>
```

The Bash compatibility wrapper is only for an explicitly provisioned package-local Git Bash/MSYS environment; it delegates to the hardened PowerShell backend:
```bash
bash "$APK_LAB_SKILL_ROOT/scripts/decompile.sh" [OPTIONS] <file>
```

For **XAPK** files (ZIP bundles containing multiple APKs, used by APKPure and similar stores): the script automatically extracts the archive, identifies all APK files inside (base + split APKs), and decompiles each one into a separate subdirectory. The XAPK manifest is copied to the output for reference.

**Split/bundled APK detection**: Some APKs are actually bundle wrappers — the outer APK contains `base.apk` plus `split_config.*.apk` files inside its resources directory. When this happens, jadx will decompile the thin wrapper and produce very few Java files. The decompile scripts automatically detect this (≤10 Java files + inner APKs present) and re-decompile `base.apk` into an `<output>/base/` subdirectory. Config-only splits (ABI, language, density) are skipped. The main decompiled source will be in `<output>/base/sources/`.

Options:
- `-o <dir>` — Custom output directory (default: `<filename>-decompiled`)
- `--deobf` — Enable deobfuscation (recommended for obfuscated apps)
- `--no-res` — Skip resources, decompile code only (faster)
- `--engine ENGINE` — `jadx` (default), `fernflower`, or `both`

**Engine selection strategy**:

| Situation | Engine |
|---|---|
| First pass on any APK | `jadx` (fastest, handles resources) |
| JAR/AAR library analysis | `fernflower` (better Java output) |
| jadx output has warnings/broken code | `both` (compare and pick best per class) |
| Complex lambdas, generics, streams | `fernflower` |
| Quick overview of a large APK | `jadx --no-res` |

When using `--engine both`, the outputs go into `<output>/jadx/` and `<output>/fernflower/` respectively, with a comparison summary at the end showing file counts and jadx warning counts. Review classes with jadx warnings in the Fernflower output for better code.

For APK files with Fernflower, the script automatically uses dex2jar as an intermediate step. dex2jar must be installed for this to work.

See `$APK_LAB_SKILL_ROOT/references/jadx-usage.md` and `$APK_LAB_SKILL_ROOT/references/fernflower-usage.md` for the full CLI references.

### Phase 3: Analyze Structure

Navigate the decompiled output to understand the app's architecture.

**Actions**:

1. **Read AndroidManifest.xml** from `<output>/resources/AndroidManifest.xml`:
   - Identify the main launcher Activity
   - List all Activities, Services, BroadcastReceivers, ContentProviders
   - Note permissions (especially `INTERNET`, `ACCESS_NETWORK_STATE`)
   - Find the application class (`android:name` on `<application>`)

2. **Survey the package structure** under `<output>/sources/`:
   - Identify the main app package and sub-packages
   - Distinguish app code from third-party libraries
   - Look for packages named `api`, `network`, `data`, `repository`, `service`, `retrofit`, `http` — these are where API calls live

3. **Read every `BuildConfig.java`** — these are almost never obfuscated and frequently leak the highest-signal constants in the entire APK (base URLs, flavor names, build type, third-party API keys, feature flags):
   On Windows:
   ```powershell
   Get-ChildItem <output>/sources -Recurse -Filter BuildConfig.java -File |
     Select-String -Pattern '='
   ```
   A Bash `find/grep` form may be used only when those tools are package-local.
   Each Gradle module emits its own `BuildConfig`, so expect 1–N hits. Read all of them.

4. **Identify the architecture pattern**:
   - MVP: look for `Presenter` classes
   - MVVM: look for `ViewModel` classes and `LiveData`/`StateFlow`
   - Clean Architecture: look for `domain`, `data`, `presentation` packages
   - This informs where to look for network calls in the next phases

### Phase 3.5: Recover Kotlin Class Names (only for obfuscated Kotlin apps)

If Phase 0 reported moderate / high obfuscation **and** the app is Kotlin
(Compose / kotlin_module markers detected), run the metadata recovery
script before tracing call flows. R8 obfuscates JVM symbols but cannot
strip Kotlin metadata strings, so original FQNs leak through
`@DebugMetadata` and `@Metadata.d2`.

On Windows, use the package-Python implementation:

```powershell
$CodexPython = Join-Path $env:CODEX_INSTALL_DIR 'tool\python\python.exe'
& $CodexPython "$APK_LAB_SKILL_ROOT\scripts\recover_kotlin_names.py" `
    <output>/sources <output>/mapping
```

Then use the lookup helper instead of host `grep` — every hit comes
annotated with the owning class's real name:

```powershell
& $CodexPython "$APK_LAB_SKILL_ROOT\scripts\lookup_name.py" `
    <output>/mapping --grep '"/api/' --sources <output>/sources
```

The legacy `.sh` helpers remain compatibility helpers only when Bash itself
is package-local and explicitly available. Do not silently use host Git Bash,
MSYS, grep, sed, or awk.

Typical recovery on a real-world Kotlin app: ~100% of `*Repository` /
`*ViewModel` / `*UseCase` / `*Impl` classes, ~80% of DTOs.

See `$APK_LAB_SKILL_ROOT/references/kotlin-name-recovery.md`
for the full technique and limitations.

### Phase 4: Trace Call Flows

Follow execution paths from user-facing entry points down to network calls.

**Actions**:

1. **Start from entry points**: Read the main Activity or Application class identified in Phase 3.

2. **Follow the initialization chain**: Application.onCreate() often sets up the HTTP client, base URL, and DI framework. Read this first.

3. **Trace user actions**: From an Activity, follow:
   - `onCreate()` → view setup → click listeners
   - Click handler → ViewModel/Presenter method
   - ViewModel → Repository → API service interface
   - API service → actual HTTP call

4. **Map DI bindings** (if Dagger/Hilt is used): Find `@Module` classes to understand which implementations are provided for which interfaces.

5. **Handle obfuscated code**: When class names are mangled, use string literals and library API calls as anchors. Retrofit annotations and URL strings are never obfuscated.

See `$APK_LAB_SKILL_ROOT/references/call-flow-analysis.md` for detailed techniques and grep commands.

### Phase 5: Extract and Document APIs

Find all API endpoints and produce structured documentation.

**Action**: Run the API search script for a broad sweep.

On Windows use the package-local Python scanner first. It has no Bash/grep dependency and enforces the portable path boundary:
```powershell
$CodexPython = Join-Path $env:CODEX_INSTALL_DIR 'tool\python\python.exe'
& $CodexPython "$APK_LAB_SKILL_ROOT\scripts\find_api_calls.py" <output>/sources/
```

Targeted searches use the same backend:
```powershell
& $CodexPython "$APK_LAB_SKILL_ROOT\scripts\find_api_calls.py" <output>/sources/ --retrofit
& $CodexPython "$APK_LAB_SKILL_ROOT\scripts\find_api_calls.py" <output>/sources/ --urls
& $CodexPython "$APK_LAB_SKILL_ROOT\scripts\find_api_calls.py" <output>/sources/ --auth
& $CodexPython "$APK_LAB_SKILL_ROOT\scripts\find_api_calls.py" <output>/sources/ --paths
```

`find-api-calls.ps1` remains a Windows-native compatibility scanner. The Bash wrapper may be used only with an explicitly provisioned package-local Git Bash/MSYS; it delegates to the same Python backend and never falls back to host `python3`, `grep`, `awk`, or `sed`:
```bash
bash "$APK_LAB_SKILL_ROOT/scripts/find-api-calls.sh" <output>/sources/ --urls
```

Document the endpoints in **two tiers** — going deep on every endpoint is
prohibitively expensive on apps with 100+ paths, and most of them do not
warrant it. Always produce Tier 1; expand Tier 2 only for the endpoints
that matter.

#### Tier 1 — flat inventory (always)

A single table covering every discovered endpoint. Aim for one line each;
if you cannot determine a column, write `?`.

| Host | Method | Path | Auth | Source file |
|------|--------|------|------|-------------|
| `api.example.com` | GET | `/v1/users/profile` | Bearer | `com/example/api/UserApi.java` |
| `api.example.com` | POST | `/v1/auth/login` | none | `com/example/api/AuthApi.java` |

This table answers "what does the backend look like" in one screen and
takes ~5 minutes to produce from the `--paths` output even on a large app.

#### Tier 2 — per-endpoint detail (only for high-value endpoints)

Reserve the detailed format for the few endpoints that actually need it:

- the entire authentication flow (login, refresh, logout, OTP/SMS, anonymous, registration)
- payment / checkout / order-creation endpoints
- anything the user explicitly asked about
- anything that looked unusual during the scan (custom signing, undocumented headers, etc.)

```markdown
### `METHOD /path`

- **Source**: `com.example.api.ApiService` (ApiService.java:42)
- **Base URL**: `https://api.example.com/v1`
- **Path params**: `id` (String)
- **Query params**: `page` (int), `limit` (int)
- **Headers**: `Authorization: Bearer <token>`
- **Request body**: `{ "email": "string", "password": "string" }`
- **Response**: `ApiResponse<User>`
- **Called from**: `LoginActivity → LoginViewModel → UserRepository → ApiService`
```

As a default, do not produce Tier 2 entries for more than ~10 endpoints
unless the user explicitly asks for more — Tier 1 plus a Tier 2 deep dive
on auth + 1-2 key flows is what most consumers of this work actually want.

See `$APK_LAB_SKILL_ROOT/references/api-extraction-patterns.md` for library-specific search patterns and the full documentation template.

## Output

At the end of the workflow, deliver:

1. **Decompiled source** in the output directory
2. **Architecture summary** — app structure, main packages, pattern used
3. **API documentation** — all discovered endpoints in the format above
4. **Call flow map** — key paths from UI to network (especially authentication and main features)

## References

- `$APK_LAB_SKILL_ROOT/references/setup-guide.md` — Installing Java, jadx, Fernflower/Vineflower, dex2jar, and optional tools
- `$APK_LAB_SKILL_ROOT/references/jadx-usage.md` — jadx CLI options and workflows
- `$APK_LAB_SKILL_ROOT/references/fernflower-usage.md` — Fernflower/Vineflower CLI options, when to use, APK workflow
- `$APK_LAB_SKILL_ROOT/references/api-extraction-patterns.md` — Library-specific search patterns and documentation template
- `$APK_LAB_SKILL_ROOT/references/call-flow-analysis.md` — Techniques for tracing call flows in decompiled code

## Codex Portable APK Lab constraints
- Keep all downloaded tools, generated files, test artifacts, credentials, SDK state, package-manager caches, and temporary files under the Codex package root (`CODEX_INSTALL_DIR` or the parent of `CODEX_HOME`).
- On Windows, prefer the `.ps1` and package-Python entry points documented above. Do not silently use host Bash, grep, sed, awk, Git, Java, Python, or Android tools.
- A path outside `CODEX_INSTALL_DIR` requires explicit user approval through the Codex permission flow; scripts that cannot observe such approval must fail closed rather than bypass the package boundary.
- Prefer package-local paths from `ANDROID_HOME`, `ANDROID_USER_HOME`, `APKTOOL_FRAMEWORK_DIR`, `FRIDA_CACHE_DIR`, `MITMPROXY_HOME`, `APPIUM_HOME`, `APK_LAB_CACHE_DIR`, `APK_LAB_TMP_DIR`, and `APK_LAB_JOBS_DIR`.
- Before writing/deleting, resolve the final absolute path and keep it inside the package root; skip reparse points/symlinks.
- Start Appium, device sessions, proxies, emulators, Frida, or GUI tools only for the current task and stop them when done.
