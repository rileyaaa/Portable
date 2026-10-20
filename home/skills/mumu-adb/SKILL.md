---
name: mumu-adb
description: Use local ADB to connect to a MuMu Android emulator on Windows and clean up ADB processes and files created by the task. Use for any authorized MuMu ADB task.
---

# MuMu ADB

Resolve the current portable package root from this skill file (`home/skills/mumu-adb/SKILL.md`: three parent directories above the skill directory), then use `<package-root>\tool\android\platform-tools\adb.exe` by absolute path. Validate that the root contains `env.ps1` and `codex.exe`; do not assume a drive letter or installation folder. This standalone Platform Tools directory is separate from the full SDK location `tool\android\sdk` used by `ANDROID_HOME`. Keep Platform Tools in its package-local directory and do not add it to `PATH`. Do not run ADB when this skill is merely loaded. Start it only when a task needs it; after finishing, stop the ADB processes started for that task. A later task can start it again.

## Before using ADB

Confirm which MuMu instance the task targets and what device actions the user authorized. Before the **first ADB command**, including `adb version`, record existing `adb.exe` processes, their executable paths and PIDs. Validate that the effective ADB user/key and temporary/log paths are inside the current package and do not traverse symlinks, junctions, or other reparse points. Use the current portable launcher's environment; if a required path is missing, stale, or outside this package, correct the task environment to package-local paths before starting ADB.

Record a baseline only for the validated package-local locations:

- `ANDROID_USER_HOME`, `$env:USERPROFILE\.android`, and the `.android` directory under `ANDROID_SDK_HOME`, as applicable;
- the key path selected by `ADB_VENDOR_KEYS`;
- `$env:TEMP\adb.log`, `$env:TMP\adb.log`, and `ANDROID_ADB_LOG_PATH`, if set.

Record existence, names, sizes, and modification times only; do not read key contents or follow linked files. Keep the baseline in the package-local task output area. This distinguishes files created by the task from existing state.

Do not routinely inspect the actual Windows user's `.android`, AppData, or system Temp directories. If a concrete failure requires host diagnostics, first establish user authorization for the specific external locations, then inspect only the necessary metadata. Derive any required system path from the Windows environment rather than a fixed drive letter. Diagnostic access does not authorize deleting host files.

## Connect and work

Run `adb devices -l` to inspect existing connections. Use the MuMu ADB endpoint configured for the chosen instance. If it is not known, `127.0.0.1:16384` and `127.0.0.1:5555` are common local candidates; confirm which one actually belongs to the target instance. Once connected, use `adb -s <serial>` for device commands, especially when more than one device appears.

Run only commands needed for the current task. For any long-running ADB command, retain its process ID and output path so it can be stopped and accounted for later. Choose whether to collect, preserve, or clear device logs according to that task's instructions; this skill does not prescribe a logcat workflow.

## Finish every task

1. Stop long-running ADB commands and helper processes started by this task. If this task started the ADB server, run this copy of `adb.exe kill-server` and verify the server exited. If a server was already running before the task, leave it alone; disconnect only a transport created by this task when appropriate. Do not keep a task-started server running for the next task.
2. Compare package-local ADB key and log locations with the baseline. Delete only ordinary files proved to have been created by this task, including new `adbkey`, `adbkey.pub`, or `adb.log` files. Remove a new package-local `.android` directory only if it did not exist before and every item inside is task-created. Never clear a whole Temp directory, an existing `.android` directory, or another user's keys. If host files were found during authorized diagnostics, report them; delete them only with authorization that explicitly covers those external files.
3. Recheck relevant locations and ADB processes. Report what was removed and what was retained. Keep the installed Platform Tools and any task output the user wants to retain.

If permissions prevent required cleanup, request approval instead of bypassing filesystem restrictions. Do not describe process and file cleanup as a complete rollback of changes made on the emulator.
