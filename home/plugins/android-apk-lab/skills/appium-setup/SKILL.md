---
name: appium-setup
description: Use only when the user explicitly requests Appium installation or repair. For Android/MuMu choose the maintained UiAutomator2 workflow; no probes, downloads, server startup or device sessions on skill load.
---

# Appium setup selection

For this Windows portable project, Android/MuMu native UI testing normally uses [UiAutomator2](../appium-setup-uiautomator2/SKILL.md). Reuse an existing explicit target/driver choice. Clarify only if the requested platform or driver cannot be inferred. Do not create an Android emulator when the user supplied MuMu.

Keep Node/npm, Appium, driver state, Java, SDK, caches and logs inside the current package. Use package-local executables by absolute path and selected compatible pinned versions; never use global npm or implicit `npx` installation. Select only dependencies needed for the task. The existing standalone ADB does not constitute an SDK/JDK/Appium installation.

A host setup request does not by itself authorize installing helper APKs or changing an external device. Before a real session, establish which device and actions are covered by the user's request. Do not repeat authorization questions already resolved in the task.

For an existing session failure, use [troubleshooting](../appium-troubleshooting/SKILL.md). For changes to these workflow files themselves, use [repository maintenance](../appium-prepare-development-environment/SKILL.md). Other Appium drivers are not bundled; use their official guidance only for an explicitly requested supported target. XCUITest requires macOS and is not a Windows-local fallback.

Completion means the selected package-local driver and prerequisites pass relevant checks. Report host readiness separately from a successful device session and semantic action. Do not refer to nonexistent local contexts, helper summaries or child skills.
