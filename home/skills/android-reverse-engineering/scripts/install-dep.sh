#!/usr/bin/env bash
set -euo pipefail

# Portable dependency locator only. It does not download/install, touch profiles,
# or invoke host package managers. Missing dependencies require explicit user action.
DEP="${1:-}"
if [[ -z "$DEP" ]]; then
  echo "usage: install-dep.sh <java|jadx|vineflower|dex2jar|apktool|adb>" >&2
  exit 2
fi
[[ ! -L "${BASH_SOURCE[0]}" ]] || { echo "ERROR: script symlink is not allowed." >&2; exit 2; }
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$SCRIPT_DIR"
for _ in {1..9}; do
  if [[ -f "$ROOT/codex.exe" && -f "$ROOT/env.ps1" ]]; then break; fi
  [[ "$ROOT" == "/" ]] && { echo "ERROR: unable to locate Codex Portable root." >&2; exit 2; }
  ROOT="$(dirname -- "$ROOT")"
done
[[ -f "$ROOT/codex.exe" && -f "$ROOT/env.ps1" && ! -L "$ROOT" ]] || { echo "ERROR: unsafe Codex Portable root." >&2; exit 2; }
if [[ -n "${CODEX_INSTALL_DIR:-}" ]]; then
  declared="$(realpath -m -- "$CODEX_INSTALL_DIR")"
  [[ "$declared" == "$ROOT" ]] || { echo "ERROR: CODEX_INSTALL_DIR does not match this package." >&2; exit 2; }
fi
case "$DEP" in
  java)       TARGET="$ROOT/tool/android/jdk"; SOURCE="https://adoptium.net/temurin/releases/" ;;
  jadx)       TARGET="$ROOT/tool/android/jadx"; SOURCE="https://github.com/skylot/jadx/releases" ;;
  vineflower) TARGET="$ROOT/tool/android/vineflower"; SOURCE="https://github.com/Vineflower/vineflower/releases" ;;
  dex2jar)    TARGET="$ROOT/tool/android/dex2jar"; SOURCE="https://github.com/pxb1988/dex2jar/releases" ;;
  apktool)    TARGET="$ROOT/tool/android/apktool"; SOURCE="https://apktool.org/docs/install/" ;;
  adb)        TARGET="$ROOT/tool/android/sdk/platform-tools"; SOURCE="https://developer.android.com/tools/releases/platform-tools" ;;
  *) echo "ERROR: unsupported dependency: $DEP" >&2; exit 2 ;;
esac
printf 'DEPENDENCY=%s\nTARGET=%s\nSOURCE=%s\nACTION=request-approval-then-manual-package-local-install-only\n' "$DEP" "$TARGET" "$SOURCE"
