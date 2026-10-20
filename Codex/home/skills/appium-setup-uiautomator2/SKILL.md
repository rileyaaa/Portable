---
name: appium-setup-uiautomator2
description: "Prepare and verify Appium UiAutomator2 by validating Node/Appium, Android SDK and Java prerequisites, driver installation, doctor output, and server smoke evidence. Use after the setup Skill selects UiAutomator2 or appium-troubleshooting hands off a UiAutomator2 prerequisite or doctor failure. Do not use for an existing runtime failure after prerequisites pass."
---

## Codex Portable execution boundary
- Resolve executable commands to package-local tools under `CODEX_INSTALL_DIR` (plus Windows system components explicitly required by the launcher). Never silently use host/global npm, Appium, Git, curl, Python, Java, Android SDK, or package-manager installs. `npx` may be used only with `--no-install`, from an explicitly selected project that is itself inside the Codex package.
- A connected phone, emulator, remote Android instance, or its filesystem/state is outside the Codex package. Before reading from or changing such a target, obtain explicit user approval for that target/session. Commands that mutate device state (`adb push/install/uninstall`, `adb shell am/pm/settings/input/chmod/rm/mv/cp`, Frida/Objection injection, Maestro/Appium sessions, reboot/root/trust changes) always require that approval before execution.

## APK Lab portable override
For this portable Codex package, treat any upstream examples that mention user-home installs, global package managers, system PATH edits, Homebrew, winget, choco, scoop, or OS-level install locations as layout examples only. Place tools, caches, generated files, credentials, test outputs, and temporary files under the package root (`CODEX_INSTALL_DIR`, or parent of `CODEX_HOME`). Prefer `tool/android`, `cache/android`, `tmp/android`, and `work/apk-jobs`.

# UiAutomator2 Setup Workflow

## Routing

Use this Skill to prepare or repair UiAutomator2 prerequisites selected by
`skills/setup/SKILL.md` or handed off by
`skills/appium-troubleshooting/SKILL.md`. After required setup checks pass,
route an existing UiAutomator2 session or command failure back to
`skills/appium-troubleshooting/SKILL.md`. Load FFmpeg or bundletool only when
the user explicitly requested that capability.

## Required inputs

Confirm Android as the target, package-local `appium` mode or an explicitly requested
package-contained project using `npx --no-install appium`, host OS, device or emulator expectations, permissions,
and optional dependency requests.

## Workflow outline

1. Load the package-local Appium command profile by default. Use a project-local profile only when explicitly requested, only from a project inside the Codex package, and only with `npx --no-install`.
2. Load the Android profile, shared Appium setup basics, and Android emulator
   setup Context.
3. Load the UiAutomator2 decision, installation, doctor, and smoke references
   in that order.
4. Verify directly with `node --version`, `appium --version`, `adb version`, `java -version`, `appium driver list --installed`, and `appium driver doctor uiautomator2`; pass
   `--appium-mode local` only for an explicitly requested package-contained project-local mode. Apply required fixes in technical
   dependency order and rerun the affected check after each fix.
5. Run the UiAutomator2 doctor and server smoke checks. Load the matching
   example only when it clarifies execution.

## Verification

1. Re-run `appium driver list --installed` and `appium driver doctor uiautomator2`; add
   `--appium-mode local` only for an explicitly requested package-contained project-local mode. Verify
   `summary.requiredOk: true`, `summary.driverInstalled: true`, a populated
   `summary.driverVersion`, and `summary.doctorRequiredOk: true`.
2. Verify the direct doctor output reports `0 required fixes needed` using
   `appium driver doctor uiautomator2`, or
   `npx --no-install appium driver doctor uiautomator2` in local mode.
3. Start the Appium server in the selected mode, request
   `http://127.0.0.1:4723/status`, and verify the response indicates readiness
   while the server log lists `uiautomator2` as an available driver.
4. Stop the server and verify no Appium server process remains, following the
   platform-specific cleanup check in the smoke-status reference.

## UiAutomator2 setup safety and approval constraints

- Preserve the selected command mode throughout the workflow.
- Ask before optional FFmpeg or bundletool setup, privileged commands, SDK
  license changes, or emulator creation that changes local state.
- Preserve working Java, Android SDK, device, emulator, and driver
  installations.

## Completion criteria

- Android environment completion criteria pass.
- Appium succeeds in the selected command mode.
- The installed driver list includes `uiautomator2`.
- `appium driver doctor uiautomator2` reports `0 required fixes needed`;
  optional warnings are non-blocking.
- `/status` succeeds, server logs list `uiautomator2`, and cleanup leaves no
  Appium server process.

## Evidence boundary

Report Appium and UiAutomator2 versions, helper `requiredOk`, Android
prerequisite summary, doctor required/optional summary, `/status`, server
driver evidence, cleanup, and explicitly requested optional capability results.

## Self-Improvement Prompt

Before the final response, report any missing, ambiguous, outdated, or
retry-causing UiAutomator2 setup instruction with its asset path and proposed
wording. Leave unrelated assets unchanged.

## Codex Portable APK Lab constraints
- Keep all downloaded tools, generated files, test artifacts, credentials, SDK state, package-manager caches, and temporary files under the Codex package root (`CODEX_INSTALL_DIR` or the parent of `CODEX_HOME`).
- Prefer package-local paths from `ANDROID_HOME`, `ANDROID_USER_HOME`, `APKTOOL_FRAMEWORK_DIR`, `FRIDA_CACHE_DIR`, `MITMPROXY_HOME`, `APPIUM_HOME`, `APK_LAB_CACHE_DIR`, `APK_LAB_TMP_DIR`, and `APK_LAB_JOBS_DIR`.
- Before writing/deleting, resolve the final absolute path and keep it inside the package root; skip reparse points/symlinks.
- Start Appium, device sessions, proxies, emulators, Frida, or GUI tools only for the current task and stop them when done.
