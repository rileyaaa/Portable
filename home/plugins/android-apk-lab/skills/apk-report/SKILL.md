---
name: apk-report
description: "Use to assemble APK analysis outputs into summary.md, evidence.json, metadata, checksums, and per-domain Markdown reports for later AI continuation."
---

## Codex Portable execution boundary
- Resolve executable commands to package-local tools under `CODEX_INSTALL_DIR` (plus Windows system components explicitly required by the launcher). Never silently use host/global npm, Appium, Git, curl, Python, Java, Android SDK, or package-manager installs. `npx` may be used only with `--no-install`, from an explicitly selected project that is itself inside the Codex package.
- A connected phone, emulator, remote Android instance, or its filesystem/state is outside the Codex package. Before reading from or changing such a target, obtain explicit user approval for that target/session. Commands that mutate device state (`adb push/install/uninstall`, `adb shell am/pm/settings/input/chmod/rm/mv/cp`, Frida/Objection injection, Maestro/Appium sessions, reboot/root/trust changes) always require that approval before execution.
# APK Report

Assemble `report/summary.md`, `metadata.json`, `static-analysis.md`, `native-analysis.md`, `network-analysis.md`, `patches.md`, `tests.md`, `runtime.md`, `evidence.json`, and `checksums.txt`. Include source file hashes, tool versions when known, commands or scripts used, generated artifact paths, and next-step recommendations.

Keep reports concise and machine-followable. Link to package-local artifacts instead of embedding massive code, captures, binaries, or secret-bearing content.

## Portable constraints
- Resolve the package root dynamically from `CODEX_INSTALL_DIR`, `CODEX_HOME`, or this plugin path; never hard-code a drive letter.
- Keep inputs, outputs, temporary files, credentials, certificates, SDK homes, package-manager caches, and reports under the package root.
- Reject symlink/reparse-point escapes and any resolved path outside the package root.
- Prefer static/CLI analysis before device, GUI, screenshot, or OCR workflows.
- Treat long-running tools (Appium, mitmproxy, Frida, Ghidra, remote Android) as task-scoped processes and stop them at task end.
