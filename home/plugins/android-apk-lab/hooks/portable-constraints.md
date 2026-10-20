# Portable constraints reference

This file is guidance only; it is not registered as a startup hook. Loading the plugin or entering maintenance mode must not run a probe, start MCP/ADB/Appium, scan devices, or install anything.

Read only the workflow selected by an explicit Android/APK task. Validate current-package paths with `scripts/portable_paths.ps1` or equivalent checks before creating, reading, writing, deleting, or launching. Device operations need authorization for the selected target/session; host package-local paths do not imply device authorization.
