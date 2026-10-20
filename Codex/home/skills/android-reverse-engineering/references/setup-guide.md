# Android Reverse Engineering — Codex Portable Setup

This package uses a **package-local only** tool layout. Do not install dependencies into the Windows user profile, system directories, or persistent system/user `PATH`. `run-codex.ps1` adds the package-local tool directories to the current Codex process.

| Dependency | Package-local target | Upstream source |
| --- | --- | --- |
| Java 17+ | `tool/android/jdk` | Eclipse Temurin / Adoptium releases |
| jadx | `tool/android/jadx` | `https://github.com/skylot/jadx/releases` |
| Vineflower | `tool/android/vineflower` | `https://github.com/Vineflower/vineflower/releases` |
| dex2jar | `tool/android/dex2jar` | `https://github.com/pxb1988/dex2jar/releases` |
| apktool | `tool/android/apktool` | `https://apktool.org/docs/install/` |
| Android platform-tools / adb | `tool/android/sdk/platform-tools` | `https://developer.android.com/tools/releases/platform-tools` |

## Procedure

1. Start from `启动Codex.bat` so `CODEX_INSTALL_DIR` and the portable cache variables are set.
2. Run `scripts/check-deps.ps1` to see what is missing.
3. Run `scripts/install-dep.ps1 <dep>` only to obtain the approved local target and upstream source. It does **not** perform a host installation.
4. If the user approves downloading a dependency, place/extract it only into the target under `CODEX_INSTALL_DIR`.
5. Re-run `scripts/check-deps.ps1`.

## Boundary rules

- Never modify system/user `PATH` permanently.
- Never write dependencies to `%USERPROFILE%`, `%APPDATA%`, `%LOCALAPPDATA%`, or other package-external locations.
- Never invoke a host package manager as part of this portable workflow.
- If an operation genuinely requires a package-external path, obtain explicit user approval first.
- Reject symlink/reparse-point paths that could escape the package root.
