---
name: apk-test-router
description: "Use only for an explicitly requested Android/APK task. Use to choose the lowest-cost APK validation method: static assertions, direct API tests, mocks, remote device, Appium page source, or visual screenshots."
---

## Task activation

Loading this skill, detecting an APK, or entering maintenance mode does not authorize execution. Do not run prerequisite probes, ADB, device discovery, servers, downloads, or installations until the user has requested the relevant Android/APK task. Use the existing authorization for the selected target/session; do not ask again for the same authorized operation. Device/helper installation and actions outside that scope need separate authorization. Resolve the current package root from this skill/script location and validate its markers and lexical ancestors first; environment roots such as `CODEX_INSTALL_DIR` are usable only after they match that current root. Never follow a stale root after moving the package.

## Codex Portable execution boundary
- Resolve executable commands to package-local tools under `CODEX_INSTALL_DIR` (plus Windows system components explicitly required by the launcher). Never silently use host/global npm, Appium, Git, curl, Python, Java, Android SDK, or package-manager installs. `npx` may be used only with `--no-install`, from an explicitly selected project that is itself inside the Codex package.
- A connected phone, emulator, remote Android instance, or its filesystem/state is outside the Codex package. Before reading from or changing such a target, obtain explicit user approval for that target/session. Commands that mutate device state (`adb push/install/uninstall`, `adb shell am/pm/settings/input/chmod/rm/mv/cp`, Frida/Objection injection, Maestro/Appium sessions, reboot/root/trust changes) always require that approval before execution.
# APK Test Router

For each test request, choose the lowest-cost proof:
1. Static assertion if manifest/resources/code prove it.
2. Direct API test if server behavior is the target.
3. Mock/WireMock/mitmproxy fault injection for error paths.
4. Remote Android only for framework/runtime behavior.
5. Appium page source/selectors for UI structure.
6. Screenshot diff only for visual layout evidence.

Create only the test plan, executable test or report needed by the requested task, under its package-local job directory. For an existing MuMu target, prefer Appium UiAutomator2 hierarchy and stable resource-id/accessibility selectors; reuse a valid hierarchy until the screen changes. Screenshots remain useful for visual assertions or surfaces that expose no UI tree. The bundled APK Lab MCP performs offline file analysis only; it does not control devices. Consult `../appium-setup-uiautomator2/SKILL.md` when semantic UI testing is required.

## Portable constraints
- Derive the current package root from this plugin path; validate it before using matching launcher variables. Never hard-code a drive letter or trust a stale inherited root.
- Keep inputs, outputs, temporary files, credentials, certificates, SDK homes, package-manager caches, and reports under the package root.
- Reject symlink/reparse-point escapes and any resolved path outside the package root.
- Prefer static/CLI analysis before device, GUI, screenshot, or OCR workflows.
- Treat long-running tools (Appium, mitmproxy, Frida, Ghidra, remote Android) as task-scoped processes and stop them at task end.
