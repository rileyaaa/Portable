---
name: apk-static-analysis
description: "Use for Android APK static inspection: manifest, permissions, components, resources, strings, endpoints, WebView, crypto, network-security-config, JADX/apktool/aapt outputs, and Markdown reports."
---

## Codex Portable execution boundary
- Resolve executable commands to package-local tools under `CODEX_INSTALL_DIR` (plus Windows system components explicitly required by the launcher). Never silently use host/global npm, Appium, Git, curl, Python, Java, Android SDK, or package-manager installs. `npx` may be used only with `--no-install`, from an explicitly selected project that is itself inside the Codex package.
- A connected phone, emulator, remote Android instance, or its filesystem/state is outside the Codex package. Before reading from or changing such a target, obtain explicit user approval for that target/session. Commands that mutate device state (`adb push/install/uninstall`, `adb shell am/pm/settings/input/chmod/rm/mv/cp`, Frida/Objection injection, Maestro/Appium sessions, reboot/root/trust changes) always require that approval before execution.
# APK Static Analysis

Use CLI tools only by default. Run JADX/apktool/aapt-like tools with cache and framework paths inside the package root. Emit structured files: `manifest.json`, `components.json`, `permissions.json`, `endpoints.json`, `crypto-usage.json`, `webviews.json`, `network-security.json`, `interesting-classes.json`, and `report/static-analysis.md`.

Search for URLs, domains, Retrofit/OkHttp/Volley/WebView/Cronet usage, exported components, content providers, certificate pinning, secrets references, and native library references. Return summaries and paths, not huge decompiled bodies.

## Portable constraints
- Resolve the package root dynamically from `CODEX_INSTALL_DIR`, `CODEX_HOME`, or this plugin path; never hard-code a drive letter.
- Keep inputs, outputs, temporary files, credentials, certificates, SDK homes, package-manager caches, and reports under the package root.
- Reject symlink/reparse-point escapes and any resolved path outside the package root.
- Prefer static/CLI analysis before device, GUI, screenshot, or OCR workflows.
- Treat long-running tools (Appium, mitmproxy, Frida, Ghidra, remote Android) as task-scoped processes and stop them at task end.
