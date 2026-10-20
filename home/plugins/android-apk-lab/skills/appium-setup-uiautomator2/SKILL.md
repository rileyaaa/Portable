---
name: appium-setup-uiautomator2
description: Use only for explicitly requested Android or MuMu UI automation and UiAutomator2 setup. Prefer UI hierarchy and stable selectors to repeated screenshot coordinates; never start a server or device session merely on skill load.
---

# Appium UiAutomator2 for portable Windows

## Activation and scope

Start only for the user's current Android/MuMu testing or setup request. Confirm the intended instance/serial and authorized actions from the request; reuse existing authorization instead of asking for it repeatedly. Static APK analysis needs no device/server. Preserve the user's `home/skills/mumu-adb/SKILL.md` for ADB connection and cleanup.

Host downloads, runtimes, npm packages, SDK, driver state, logs and temporary files must stay under the current package root, derived from the skill/script location. No host/global npm, Java, Android SDK, registry installs, system PATH edits, or automatic `npx` downloads. A device/emulator is a separate target: UiAutomator2 session startup can install its server/settings helper APKs and change device state. Proceed only when the requested test session covers this deployment; otherwise report the required device change before creating a session.

## Select and prepare the smallest toolchain

Use the maintained [Appium installation guide](https://appium.io/docs/en/latest/quickstart/install/) and [UiAutomator2 driver](https://github.com/appium/appium-uiautomator2-driver) requirements for the selected versions. Record exact Appium/driver versions; do not blindly use `latest` or copy global-install examples.

| Component | Package-local location |
| --- | --- |
| Node and npm | `tool/node`; invoke its `node.exe` and `node_modules/npm/bin/npm-cli.js` explicitly |
| Appium npm project | `tool/automation/appium`; retain its package and lock files |
| UiAutomator2 driver state | A persistent Appium home under that project; use the same home for installation and runtime |
| Java | `tool/android/jdk`; set `JAVA_HOME` for this process |
| Android SDK / SDK adb | `tool/android/sdk`; set `ANDROID_HOME` and compatible `ANDROID_SDK_ROOT` |
| npm / Android user state | Current package `cache` and `home-runtime/.android` |
| Test logs and artifacts | A dedicated task directory under `work/apk-jobs` or `tmp` |

The bundled `tool/android/platform-tools/adb.exe` is standalone ADB, not a complete SDK. Do not claim the toolchain is ready merely because that file exists. Do not invoke a host Appium if the package-local project is missing. For an explicitly authorized setup, select compatible pinned versions, install only UiAutomator2 using the local Appium CLI and package-local npm cache/prefix/home, and accept SDK licences only within the approved setup scope. Optional FFmpeg, extra drivers, emulators and Android Studio are not required defaults.

After preparation, run the needed package-local version/driver/doctor checks. Start Appium only on loopback (`127.0.0.1`), with task-local logs and a retained PID. A successful `/status` or driver doctor check proves host readiness only; it does not prove that the target device can be controlled.

## Semantic test session

1. Select the already authorized MuMu serial explicitly; never operate on whichever device happens to be first. For a preinstalled app, use its package/activity and `appium:noReset=true`; do not reset or reinstall it as a default repair.
2. Create a session using `platformName=Android`, `appium:automationName=UiAutomator2`, and that `appium:udid`. Set a bounded command timeout. Do not use automatic browser/Chromedriver downloads for native-app testing.
3. Read page source only when structure changes or the requested assertion needs it. Prefer `resource-id` and accessibility/content-description selectors; scoped text is next, XPath last. Use explicit waits for visibility/enabled state, then perform a specific action and verify its resulting state.
4. Save a screenshot only for layout/color evidence, a failed assertion, or a control without a usable semantic tree. Canvas/game surfaces and some WebViews expose insufficient hierarchy; report this limitation and use the minimum authorized visual fallback instead of claiming universal intelligent control.
5. For hybrid WebView work, inspect the selected context and its engine version. This still has a WebDriver compatibility boundary; do not assume native UiAutomator2 removes every Chromedriver requirement.
6. End the WebDriver session and stop only servers/helpers started by this task. Preserve an existing ADB server, existing user/device data, and test outputs the user wants. Never erase an emulator or uninstall unrelated helper packages as routine cleanup.

## Completion evidence

Report host versions and package paths, selected serial/app, whether helper APK deployment occurred, one successful hierarchy/selector action and assertion, relevant artifacts, and task-owned process cleanup. If no Windows device session was run, state that clearly. Route observed setup or locator failures to `../appium-troubleshooting/SKILL.md`; this package does not contain the upstream repository's `contexts/` or readiness-summary scripts.
