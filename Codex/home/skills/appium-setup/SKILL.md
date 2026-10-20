---
name: appium-setup
description: "Route Appium setup requests. This portable package bundles a dedicated UiAutomator2 setup Skill; other Appium drivers must use upstream Appium guidance and must never be routed to a nonexistent local child Skill. Do not use for an existing failing session or command; use appium-troubleshooting instead."
---

## Codex Portable execution boundary
- Resolve executable commands to package-local tools under `CODEX_INSTALL_DIR` (plus Windows system components explicitly required by the launcher). Never silently use host/global npm, Appium, Git, curl, Python, Java, Android SDK, or package-manager installs. `npx` may be used only with `--no-install`, from an explicitly selected project that is itself inside the Codex package.
- A connected phone, emulator, remote Android instance, or its filesystem/state is outside the Codex package. Before reading from or changing such a target, obtain explicit user approval for that target/session. Commands that mutate device state (`adb push/install/uninstall`, `adb shell am/pm/settings/input/chmod/rm/mv/cp`, Frida/Objection injection, Maestro/Appium sessions, reboot/root/trust changes) always require that approval before execution.

## APK Lab portable override
For this portable Codex package, treat any upstream examples that mention user-home installs, global package managers, system PATH edits, Homebrew, winget, choco, scoop, or OS-level install locations as layout examples only. Place tools, caches, generated files, credentials, test outputs, and temporary files under the package root (`CODEX_INSTALL_DIR`, or parent of `CODEX_HOME`). Prefer `tool/android`, `cache/android`, `tmp/android`, and `work/apk-jobs`.

# Appium Setup Selection Workflow

## Setup routing and selection

Select only the driver or drivers requested by the user. Treat each
`renma.continues-with` item as a possible child Skill, not as execution order,
priority, or automatic invocation.

| Intended target | Portable package route |
| --- | --- |
| Android native or hybrid apps with UiAutomator2 | Bundled: `../appium-setup-uiautomator2/SKILL.md` |
| Espresso / Chromium / Gecko / Mac2 / Safari / XCUITest | No dedicated child Skill is bundled. Do not fabricate a local Skill path; use current upstream Appium driver documentation only after the user explicitly selects that driver. |

Normalize common names such as `uia2` to UiAutomator2. If no driver is named,
pause before environment changes and ask which driver or drivers are needed.
If one or more drivers are named, preserve every explicit selection and hand
off without asking the user to choose again.

## Required inputs

Resolve the selected drivers, package-local `appium` mode or an explicitly requested
package-contained project using `npx --no-install appium`, target platforms, host OS, available devices,
simulators, or browsers, permissions, and explicitly requested optional
dependencies.

## Workflow outline

1. Resolve the driver selection before changing the environment.
2. Hand UiAutomator2 to the bundled child Skill. For another explicitly selected driver, use current upstream Appium guidance without inventing a local child Skill.
3. For multiple drivers, preserve the user's stated order. When the request
   states no order, choose and report an order that reuses shared host
   prerequisites, then execute the selected Skills one at a time. Metadata
   declaration order has no execution meaning.
4. Collect each child Skill's required doctor, helper, smoke, and evidence
   result without weakening its completion gate.

## Setup selection safety and approval constraints

- Use only package-local Appium/npm tooling. The default `appium` command must resolve inside `CODEX_INSTALL_DIR`; never use a host/global npm prefix. `npx --no-install appium` is allowed only when explicitly requested from a project inside the Codex package, and it must never download packages.
- Install only explicitly selected drivers.
- Ask before optional FFmpeg or bundletool setup, third-party real-device
  tooling, privileged commands, browser installation, or authorization
  changes.
- Preserve working installations and prefer the smallest required change.

## Completion criteria

Complete a single-driver request only after the selected child Skill reaches
its completion criteria. Complete a multi-driver request only after every
selected child Skill reaches its own completion criteria or reports an exact
manual blocker. Optional warnings remain non-blocking.

## Evidence boundary

Report the selected child Skills, command mode, each child Skill's pass/fail
result, remaining optional items, and exact blockers. Attribute selection and
execution exclusively to decisions made by the workflow body.

## Self-Improvement Prompt

Before the final response, identify any missing, ambiguous, outdated, or
retry-causing instruction in this selection workflow or a loaded child Skill.
Report the asset path and proposed wording. Leave unrelated files unchanged.

## Evidence

- Input: `Set up Appium.` Ask which driver or drivers are needed.
- Input: `Set up UiAutomator2.` Continue with the bundled `../appium-setup-uiautomator2/SKILL.md`.
- Input: `Set up UiAutomator2 and XCUITest.` Use the bundled UiAutomator2 Skill for UiAutomator2; for XCUITest, state that no dedicated local child Skill is bundled and use current upstream Appium guidance only for that explicitly selected driver.

## Codex Portable APK Lab constraints
- Keep all downloaded tools, generated files, test artifacts, credentials, SDK state, package-manager caches, and temporary files under the Codex package root (`CODEX_INSTALL_DIR` or the parent of `CODEX_HOME`).
- Prefer package-local paths from `ANDROID_HOME`, `ANDROID_USER_HOME`, `APKTOOL_FRAMEWORK_DIR`, `FRIDA_CACHE_DIR`, `MITMPROXY_HOME`, `APPIUM_HOME`, `APK_LAB_CACHE_DIR`, `APK_LAB_TMP_DIR`, and `APK_LAB_JOBS_DIR`.
- Before writing/deleting, resolve the final absolute path and keep it inside the package root; skip reparse points/symlinks.
- Start Appium, device sessions, proxies, emulators, Frida, or GUI tools only for the current task and stop them when done.
