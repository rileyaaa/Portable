---
name: apk-runtime-analysis
description: "Use when APK work requires actual runtime evidence: remote/root Android, physical test phone, Frida, logcat, Appium page source, and task-scoped process cleanup."
---

## Codex Portable execution boundary
- Resolve executable commands to package-local tools under `CODEX_INSTALL_DIR` (plus Windows system components explicitly required by the launcher). Never silently use host/global npm, Appium, Git, curl, Python, Java, Android SDK, or package-manager installs. `npx` may be used only with `--no-install`, from an explicitly selected project that is itself inside the Codex package.
- A connected phone, emulator, remote Android instance, or its filesystem/state is outside the Codex package. Before reading from or changing such a target, obtain explicit user approval for that target/session. Commands that mutate device state (`adb push/install/uninstall`, `adb shell am/pm/settings/input/chmod/rm/mv/cp`, Frida/Objection injection, Maestro/Appium sessions, reboot/root/trust changes) always require that approval before execution.
# APK Runtime Analysis

Default route: avoid device if static/API verification is sufficient. If runtime is required, prefer a remote/root Android instance or a dedicated physical test phone over a local emulator. Store logcat, Frida JSONL, mitm flows, app file snapshots, page sources, and rare screenshots under `runtime/`.

Start Appium/mitmproxy/Frida/remote device only when needed; register cleanup steps and stop them at task end. Use Accessibility ID, resource ID, UIAutomator selectors, XPath/page source before screenshots; screenshots are evidence for visual failures, not a control loop.

## Portable constraints
- Resolve the package root dynamically from `CODEX_INSTALL_DIR`, `CODEX_HOME`, or this plugin path; never hard-code a drive letter.
- Keep inputs, outputs, temporary files, credentials, certificates, SDK homes, package-manager caches, and reports under the package root.
- Reject symlink/reparse-point escapes and any resolved path outside the package root.
- Prefer static/CLI analysis before device, GUI, screenshot, or OCR workflows.
- Treat long-running tools (Appium, mitmproxy, Frida, Ghidra, remote Android) as task-scoped processes and stop them at task end.
