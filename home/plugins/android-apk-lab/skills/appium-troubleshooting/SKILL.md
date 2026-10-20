---
name: appium-troubleshooting
description: Use only when the user explicitly asks to diagnose or fix an observed Android/MuMu Appium UiAutomator2 failure. Do not start discovery, reinstall drivers, reset devices, or create sessions just because this skill is loaded.
---

# Android Appium troubleshooting

Use the supplied error, selected serial/app, package-local Appium/driver versions, session capabilities and smallest reproduction. Collect only missing evidence relevant to that failure. Keep logs and outputs inside the package and redact supplied secrets before quoting them.

| Evidence | Next bounded check |
| --- | --- |
| Appium executable or driver is missing | Confirm the package-local project/home; route the authorized setup repair to `../appium-setup-uiautomator2/SKILL.md`. Do not silently use global Appium. |
| Session cannot reach target / unauthorized adb | Confirm the authorized MuMu instance/serial and its reported transport; follow the user's mumu-adb workflow. Do not connect to unrelated devices. |
| Helper deployment or SDK/JDK failure | Compare selected driver prerequisites and device-side installation error with the official UiAutomator2 documentation. Establish permission before deploying/replacing device helpers. |
| Locator timeout | Inspect the current context and one current hierarchy; prefer resource-id/content-desc and an explicit wait. Check that the app is on the expected screen before changing selectors. |
| Canvas/custom rendering exposes no hierarchy | Report the semantic limitation; use a bounded screenshot/coordinate fallback only for the requested action. |
| Hybrid WebView / Chromedriver mismatch | Identify the selected WebView engine and current context. Native UiAutomator2 does not remove WebView driver compatibility requirements. Do not enable automatic driver downloads silently. |

Apply the smallest justified reversible change, then repeat the failing check once. Avoid broad reinstalls, emulator resets, trust/root changes, device erasure, or killing pre-existing servers. A diagnosis-only request does not authorize applying fixes outside its scope.

Use [official Appium documentation](https://appium.io/docs/en/latest/) and [UiAutomator2 troubleshooting](https://github.com/appium/appium-uiautomator2-driver) for the selected version. No local upstream `contexts/` or helper-summary scripts are bundled. XCUITest is not a Windows-local route.

Report the observed cause or remaining hypothesis, actual recheck result, selected target, package-local artifacts and task-owned process cleanup. Reuse existing task authorization; ask only for actions or external targets beyond it.
