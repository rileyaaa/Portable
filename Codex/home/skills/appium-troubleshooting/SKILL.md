---
name: appium-troubleshooting
description: "Diagnose existing UiAutomator2 session-startup, app-activity, adb transport, helper-server, native or hybrid locator failures, and XCUITest WebDriverAgent, session-startup, app install or launch, device or simulator state, alert, element-source, or locator failures. Use when a session or command under one of those drivers already fails. Do not use for first-time setup, pre-failure real-device provisioning, or Espresso, Chromium, Gecko, Safari, or Mac2 failures."
---

## Codex Portable execution boundary
- Resolve executable commands to package-local tools under `CODEX_INSTALL_DIR` (plus Windows system components explicitly required by the launcher). Never silently use host/global npm, Appium, Git, curl, Python, Java, Android SDK, or package-manager installs. `npx` may be used only with `--no-install`, from an explicitly selected project that is itself inside the Codex package.
- A connected phone, emulator, remote Android instance, or its filesystem/state is outside the Codex package. Before reading from or changing such a target, obtain explicit user approval for that target/session. Commands that mutate device state (`adb push/install/uninstall`, `adb shell am/pm/settings/input/chmod/rm/mv/cp`, Frida/Objection injection, Maestro/Appium sessions, reboot/root/trust changes) always require that approval before execution.

## APK Lab portable override
For this portable Codex package, treat any upstream examples that mention user-home installs, global package managers, system PATH edits, Homebrew, winget, choco, scoop, or OS-level install locations as layout examples only. Place tools, caches, generated files, credentials, test outputs, and temporary files under the package root (`CODEX_INSTALL_DIR`, or parent of `CODEX_HOME`). Prefer `tool/android`, `cache/android`, `tmp/android`, and `work/apk-jobs`.

# Appium Troubleshooting Workflow

## Troubleshooting routing and handoffs

Lock each run to UiAutomator2 or XCUITest. If the driver is unknown, capture
capabilities or the Appium log line that identifies it before proceeding. For
another driver, stop and report that this repository has no implemented
troubleshooting route for it.

When evidence identifies a prerequisite, installation, or doctor failure:

- UiAutomator2: continue with the bundled `../appium-setup-uiautomator2/SKILL.md`.
- XCUITest: this package has no dedicated local XCUITest setup Skill. Do not fabricate a child path; use current upstream Appium/XCUITest guidance only when the user explicitly chooses that route, and preserve the package boundary.

Real-device signing, provisioning, WDA deployment, trust changes, or other host-level changes require explicit user approval.

## Required inputs

Confirm the exact failing command and error, driver, target platform, global
package-local `appium` or an explicitly requested package-contained `npx --no-install appium` mode, host OS, device or
simulator state, relevant capabilities, recent server or device logs, smallest
reproduction, and permissions for rerunning checks.

## Decision logic

- UiAutomator2 session startup, wrong activity, early drop, `socket hang up`,
  helper-server, or adb transport symptoms use the declared UiAutomator2
  session-startup reference.
- UiAutomator2 native or hybrid locator symptoms use the declared
  UiAutomator2 locator reference.
- XCUITest WDA startup, install, reachability, app launch, or device/simulator
  state symptoms use the declared XCUITest troubleshooting reference.
- XCUITest element lookup or locator symptoms use the declared XCUITest
  element-lookup and locator references together.
- Load the shared capabilities Context only when capability values are part of
  the suspected cause.
- Use the community-search Context only after the matching official reference
  does not explain the exact symptom.

## Workflow outline

1. Resolve command mode once. Use package-local `appium` by default and verify it resolves inside `CODEX_INSTALL_DIR`. For explicitly selected project-local mode, the project must be inside the Codex package and commands must use `npx --no-install appium`; never let `npx` download or fall back to a host/global Appium.
2. Capture the exact error, platform, driver, relevant capabilities, and
   smallest reproduction before changing anything.
3. Record supplied Appium and driver versions. Run version, installed-list,
   connectivity, or doctor checks only when required evidence is missing or
   the symptom warrants them.
4. Load the matching driver profile and only the selected symptom references.
   Load a matching example only when it clarifies the reproduction.
5. If a prerequisite or doctor check fails, continue with the exact
   driver-specific setup Skill before deeper troubleshooting.
6. For a fix request, apply one targeted reversible change and rerun the
   smallest failing command, session start, WDA check, or locator lookup. For a
   diagnosis-only request, stop after evidence-backed cause isolation and
   present the targeted change as the next action.
7. Use official Appium and driver documentation first and community guidance
   only as a validated fallback.

## Troubleshooting safety and approval constraints

- Start with targeted evidence and the smallest reversible change.
- Request approval before a broad reset, reinstall, device erase, signing
  change, trust change, or unrelated capability change.
- Preserve package-local command mode unless a package-contained project-local mode was explicitly requested.
- Keep package-local and project-local command modes separate. If the selected Appium binary is missing, report that blocker instead of using a host/global installation or allowing `npx` to download a package.
- Apply setup or real-device approval gates before crossing into installation,
  privileged, signing, trust, or provisioning changes.
- Require a reproduced symptom or passing re-check for success. When evidence
  remains incomplete, report a hypothesis and the next discriminating check.

## Completion criteria

Complete a fix request when the failing check passes after a verified fix, or
when an exact manual blocker is isolated with command evidence and a concrete
next action. Complete a diagnosis-only request when matching evidence isolates
the cause and the smallest proposed fix or discriminating next check is
reported without changing state.

## Evidence boundary

Report the selected driver and symptom route, commands and results, any change,
the smallest re-check, and any driver-specific setup continuation. Treat
optional doctor warnings as non-blocking and report a setup or real-device
continuation as a handoff that still requires workflow selection.

## Self-Improvement Prompt

Before the final response, report any missing, ambiguous, outdated, or
retry-causing troubleshooting instruction with its asset path and proposed
wording. Leave unrelated assets unchanged.

## Evidence

Example input: `Diagnose why my UiAutomator2 session fails during startup with
this server log and desired capabilities.` Verify the suspected failure class
against logs, capabilities, device state, and driver-specific checks before
recommending a fix.

## Codex Portable APK Lab constraints
- Keep all downloaded tools, generated files, test artifacts, credentials, SDK state, package-manager caches, and temporary files under the Codex package root (`CODEX_INSTALL_DIR` or the parent of `CODEX_HOME`).
- Prefer package-local paths from `ANDROID_HOME`, `ANDROID_USER_HOME`, `APKTOOL_FRAMEWORK_DIR`, `FRIDA_CACHE_DIR`, `MITMPROXY_HOME`, `APPIUM_HOME`, `APK_LAB_CACHE_DIR`, `APK_LAB_TMP_DIR`, and `APK_LAB_JOBS_DIR`.
- Before writing/deleting, resolve the final absolute path and keep it inside the package root; skip reparse points/symlinks.
- Start Appium, device sessions, proxies, emulators, Frida, or GUI tools only for the current task and stop them when done.
