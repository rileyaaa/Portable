---
name: apk-intake
description: "Use only for an explicitly requested Android/APK task. Use when receiving APK, XAPK, APKS, AAB, DEX, or ZIP-like Android artifacts and creating a package-local job directory with hashes, metadata, routing, and first-pass triage."
---

## Task activation

Loading this skill, detecting an APK, or entering maintenance mode does not authorize execution. Do not run prerequisite probes, ADB, device discovery, servers, downloads, or installations until the user has requested the relevant Android/APK task. Use the existing authorization for the selected target/session; do not ask again for the same authorized operation. Device/helper installation and actions outside that scope need separate authorization. Resolve the current package root from this skill/script location and validate its markers and lexical ancestors first; environment roots such as `CODEX_INSTALL_DIR` are usable only after they match that current root. Never follow a stale root after moving the package.

## Codex Portable execution boundary
- Resolve executable commands to package-local tools under `CODEX_INSTALL_DIR` (plus Windows system components explicitly required by the launcher). Never silently use host/global npm, Appium, Git, curl, Python, Java, Android SDK, or package-manager installs. `npx` may be used only with `--no-install`, from an explicitly selected project that is itself inside the Codex package.
- A connected phone, emulator, remote Android instance, or its filesystem/state is outside the Codex package. Before reading from or changing such a target, obtain explicit user approval for that target/session. Commands that mutate device state (`adb push/install/uninstall`, `adb shell am/pm/settings/input/chmod/rm/mv/cp`, Frida/Objection injection, Maestro/Appium sessions, reboot/root/trust changes) always require that approval before execution.
# APK Intake

Create `work/apk-jobs/<SHA256>/` with `input`, `metadata`, `decoded`, `decompiled`, `native`, `network`, `patches`, `build`, `tests`, `runtime`, and `report` folders. Copy the source artifact into `input/` as read-only evidence, compute SHA-256, identify format, and write `metadata/intake.json`.

Routing:
1. APK/DEX: static analysis next.
2. AAB/APKS/XAPK: expand with bundle/archive tooling under the job directory before static analysis.
3. Native `.so` present: add native analysis.
4. Network strings/config present: add network analysis.
5. Packed/obfuscated indicators: mark dynamic analysis as optional follow-up, not default.

## Portable constraints
- Derive the current package root from this plugin path; validate it before using matching launcher variables. Never hard-code a drive letter or trust a stale inherited root.
- Keep inputs, outputs, temporary files, credentials, certificates, SDK homes, package-manager caches, and reports under the package root.
- Reject symlink/reparse-point escapes and any resolved path outside the package root.
- Prefer static/CLI analysis before device, GUI, screenshot, or OCR workflows.
- Treat long-running tools (Appium, mitmproxy, Frida, Ghidra, remote Android) as task-scoped processes and stop them at task end.
