---
name: mumu-adb
description: Use local ADB to connect to a MuMu Android emulator on Windows and clean up ADB processes and files created by the task. Use for any authorized MuMu ADB task.
---

# MuMu ADB

Use `D:\Codex\tool\android\platform-tools\adb.exe` by absolute path. Keep Platform Tools installed there and do not add it to `PATH`. Do not run ADB when this skill is merely loaded. Start it only when a task needs it; after finishing, stop the ADB processes started for that task. A later task can start it again.

## Before using ADB

Confirm which MuMu instance the task targets and what device actions the user authorized. Before the **first ADB command**, including `adb version`, record existing `adb.exe` processes, their executable paths and PIDs, and the pre-existing files in likely ADB key and log locations. Check:

- the actual Windows user's `.android` directory; obtain the Windows profile path rather than relying only on `USERPROFILE`, which can point elsewhere in this environment;
- `$env:USERPROFILE\.android` and the location selected by `ANDROID_SDK_HOME`, if set;
- `$env:TEMP\adb.log`, `$env:TMP\adb.log`, the actual Windows user's `AppData\Local\Temp\adb.log`, and `C:\Windows\Temp\adb.log`;
- `ANDROID_ADB_LOG_PATH`, if set.

Record each location's existence and the names, sizes, and modification times of its files. This baseline distinguishes files created by the current task from existing user data. Keep the baseline in the task's output area.

## Connect and work

Run `adb devices -l` to inspect existing connections. Use the MuMu ADB endpoint configured for the chosen instance. If it is not known, `127.0.0.1:16384` and `127.0.0.1:5555` are common local candidates; confirm which one actually belongs to the target instance. Once connected, use `adb -s <serial>` for device commands, especially when more than one device appears.

Run only commands needed for the current task. For any long-running ADB command, retain its process ID and output path so it can be stopped and accounted for later. Choose whether to collect, preserve, or clear device logs according to that task's instructions; this skill does not prescribe a logcat workflow.

## Finish every task

1. Stop long-running ADB commands and helper processes started by this task. If this task started the ADB server, run this copy of `adb.exe kill-server` and verify the server exited. If a server was already running before the task, leave it alone; disconnect only a transport created by this task when appropriate. Do not keep a task-started server running for the next task.
2. Compare ADB key and log locations with the baseline. Delete only files proved to have been created by this task, including new `adbkey`, `adbkey.pub`, or `adb.log` files. Remove a new `.android` directory only if it did not exist before and every item inside is task-created. Never clear a whole Temp directory, an existing `.android` directory, or another user's keys.
3. Recheck relevant locations and ADB processes. Report what was removed and what was retained. Keep the installed Platform Tools and any task output the user wants to retain.

If permissions prevent required cleanup, request approval instead of bypassing filesystem restrictions. Do not describe process and file cleanup as a complete rollback of changes made on the emulator.
