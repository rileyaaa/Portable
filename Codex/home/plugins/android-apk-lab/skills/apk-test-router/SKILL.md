---
name: apk-test-router
description: "Use to choose the lowest-cost APK validation method: static assertions, direct API tests, mocks, remote device, Appium page source, or visual screenshots."
---

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

Emit `tests/plan.json`, executable skeletons when useful, and `report/tests.md`.

## Portable constraints
- Resolve the package root dynamically from `CODEX_INSTALL_DIR`, `CODEX_HOME`, or this plugin path; never hard-code a drive letter.
- Keep inputs, outputs, temporary files, credentials, certificates, SDK homes, package-manager caches, and reports under the package root.
- Reject symlink/reparse-point escapes and any resolved path outside the package root.
- Prefer static/CLI analysis before device, GUI, screenshot, or OCR workflows.
- Treat long-running tools (Appium, mitmproxy, Frida, Ghidra, remote Android) as task-scoped processes and stop them at task end.
