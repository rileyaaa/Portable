---
name: apk-test-router
description: Use only when the user explicitly requests APK analysis, modification, reverse engineering, repacking, or Android/MuMu testing. Route to one package-local workflow; do not start tools merely because APK files are present.
---

# Android task entry

This is the lightweight entry point. The maintained workflows live once under `home/plugins/android-apk-lab/skills`; reading them does not require enabling plugins or starting MCP.

Resolve the current package root from this skill's location (`home/skills/apk-test-router/SKILL.md`), validate that it contains `env.ps1` and `codex.exe`, and reject linked paths. Never use an inherited old install root. Read only the workflow needed by the user's current request:

| Requested work | Workflow relative to the current package root |
| --- | --- |
| Inspect an APK and create its working copy | `home/plugins/android-apk-lab/skills/apk-intake/SKILL.md` |
| Manifest, resources, decompilation, names, code flow | `home/plugins/android-apk-lab/skills/apk-static-analysis/SKILL.md`; load `android-reverse-engineering/SKILL.md` in that skills directory only as needed |
| Native libraries / captured network traffic | `home/plugins/android-apk-lab/skills/apk-native-analysis/SKILL.md` / `apk-network-analysis/SKILL.md` |
| Modify, rebuild, align, sign | `home/plugins/android-apk-lab/skills/apk-repack-sign/SKILL.md` |
| Choose a test or produce a report | `home/plugins/android-apk-lab/skills/apk-test-router/SKILL.md` / `apk-report/SKILL.md` |
| MuMu connection and task cleanup | `home/skills/mumu-adb/SKILL.md` (the user's own skill; retain it) |
| Semantic Android UI automation | `home/plugins/android-apk-lab/skills/appium-setup-uiautomator2/SKILL.md`; use `appium-troubleshooting/SKILL.md` only for an observed failure |

Do not run ADB, scan devices, start an emulator/server/MCP, probe dependencies, download tools, or install a device helper unless the requested task needs that action and its target/scope is authorized. A static APK task does not authorize touching MuMu. Installation on an Android device is outside the host package and must be covered by device/session authorization.

Prefer existing static evidence first. For authorized UI testing, use the accessibility/UI hierarchy and stable selectors with waits; screenshots are for visual checks or controls that expose no usable hierarchy. Do not claim semantic control is available until a real session and locator action succeed.

The optional `home/plugins/android-apk-lab/scripts/start_apk_lab_mcp.ps1 -TaskAuthorized` starts an offline APK analysis/report helper only after explicit selection. It does not control MuMu or install Appium. Its `.mcp.manual.json` is an opt-in example, not an automatically registered server. The switch records the caller's deliberate choice; it does not establish authorization by itself.
