---
name: apk-network-analysis
description: "Use for APK network endpoint extraction, certificate/network-security analysis, mitmproxy capture parsing, HAR/OpenAPI generation, and API test skeletons."
---

## Codex Portable execution boundary
- Resolve executable commands to package-local tools under `CODEX_INSTALL_DIR` (plus Windows system components explicitly required by the launcher). Never silently use host/global npm, Appium, Git, curl, Python, Java, Android SDK, or package-manager installs. `npx` may be used only with `--no-install`, from an explicitly selected project that is itself inside the Codex package.
- A connected phone, emulator, remote Android instance, or its filesystem/state is outside the Codex package. Before reading from or changing such a target, obtain explicit user approval for that target/session. Commands that mutate device state (`adb push/install/uninstall`, `adb shell am/pm/settings/input/chmod/rm/mv/cp`, Frida/Objection injection, Maestro/Appium sessions, reboot/root/trust changes) always require that approval before execution.
# APK Network Analysis

Start with static endpoint extraction from code, resources, manifest, network-security-config, protobuf/graphql/websocket hints, and token refresh logic. Write `network/endpoints.json`, `network/auth-flows.json`, `network/websocket.json`, and `report/network-analysis.md`.

If dynamic capture is required, start mitmproxy only for the task, store flows/HAR in `network/`, then stop it. Prefer API-level pytest/httpx/Schemathesis tests over UI/device automation. Use apk-mitm or Frida hooks only after the static location of the relevant pinning/check logic is identified.

## Portable constraints
- Resolve the package root dynamically from `CODEX_INSTALL_DIR`, `CODEX_HOME`, or this plugin path; never hard-code a drive letter.
- Keep inputs, outputs, temporary files, credentials, certificates, SDK homes, package-manager caches, and reports under the package root.
- Reject symlink/reparse-point escapes and any resolved path outside the package root.
- Prefer static/CLI analysis before device, GUI, screenshot, or OCR workflows.
- Treat long-running tools (Appium, mitmproxy, Frida, Ghidra, remote Android) as task-scoped processes and stop them at task end.
