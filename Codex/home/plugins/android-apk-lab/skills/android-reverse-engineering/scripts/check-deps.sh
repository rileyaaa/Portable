#!/usr/bin/env bash
set -euo pipefail

# Package-local dependency check for the Windows portable bundle.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$SCRIPT_DIR"
for _ in 1 2 3 4 5 6 7 8; do
  if [[ -f "$ROOT/codex.exe" && -f "$ROOT/env.ps1" ]]; then break; fi
  PARENT="$(dirname "$ROOT")"
  if [[ "$PARENT" == "$ROOT" ]]; then break; fi
  ROOT="$PARENT"
done
if [[ ! -f "$ROOT/codex.exe" || ! -f "$ROOT/env.ps1" ]]; then
  echo "ERROR: cannot locate Codex portable root from this script" >&2
  exit 2
fi

required_missing=()
optional_missing=()

check_file() {
  local name="$1" path="$2" required="$3"
  if [[ -f "$path" ]]; then
    echo "[OK] $name: $path"
  else
    echo "[MISSING] $name: $path"
    if [[ "$required" == "required" ]]; then required_missing+=("$name"); else optional_missing+=("$name"); fi
  fi
}

check_file java "$ROOT/tool/android/jdk/bin/java.exe" required
if [[ -f "$ROOT/tool/android/jadx/bin/jadx.bat" || -f "$ROOT/tool/android/jadx/bin/jadx.exe" ]]; then
  echo "[OK] jadx: package-local"
else
  echo "[MISSING] jadx: $ROOT/tool/android/jadx"
  required_missing+=("jadx")
fi
if [[ -f "$ROOT/tool/android/vineflower/vineflower.jar" ]]; then echo "[OK] vineflower: package-local"; else echo "[MISSING] vineflower (optional)"; optional_missing+=("vineflower"); fi
if [[ -f "$ROOT/tool/android/dex2jar/d2j-dex2jar.bat" ]]; then echo "[OK] dex2jar: package-local"; else echo "[MISSING] dex2jar (optional)"; optional_missing+=("dex2jar"); fi
if [[ -f "$ROOT/tool/android/apktool/apktool.bat" || -f "$ROOT/tool/android/apktool/apktool.jar" ]]; then echo "[OK] apktool: package-local"; else echo "[MISSING] apktool (optional)"; optional_missing+=("apktool"); fi
check_file adb "$ROOT/tool/android/sdk/platform-tools/adb.exe" optional

for dep in "${required_missing[@]}"; do echo "INSTALL_REQUIRED:$dep"; done
for dep in "${optional_missing[@]}"; do echo "INSTALL_OPTIONAL:$dep"; done
if (( ${#required_missing[@]} > 0 )); then exit 1; fi
exit 0
