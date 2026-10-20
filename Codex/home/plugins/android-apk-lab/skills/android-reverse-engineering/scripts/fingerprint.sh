#!/usr/bin/env bash
# Thin compatibility wrapper for Codex Portable on Windows/Git Bash.
# Security-sensitive ZIP parsing lives in fingerprint.py so Bash and PowerShell
# do not maintain separate extraction logic.
set -euo pipefail

find_portable_root() {
  local start current i
  start="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
  current="$start"
  for ((i=0; i<9; i++)); do
    if [[ -f "$current/codex.exe" && -f "$current/env.ps1" ]]; then
      printf '%s\n' "$current"
      return 0
    fi
    [[ "$current" == "/" ]] && break
    current="$(dirname -- "$current")"
  done
  return 1
}

[[ ! -L "${BASH_SOURCE[0]}" ]] || { echo "Error: script symlink is not allowed." >&2; exit 2; }
portable_root="$(find_portable_root)" || { echo "Error: unable to locate Codex Portable root from this script." >&2; exit 2; }
[[ ! -L "$portable_root" ]] || { echo "Error: portable root symlink is not allowed." >&2; exit 2; }
if [[ -n "${CODEX_INSTALL_DIR:-}" ]]; then
  declared="$(realpath -m -- "$CODEX_INSTALL_DIR")"
  [[ "$declared" == "$portable_root" ]] || { echo "Error: CODEX_INSTALL_DIR does not match this portable package." >&2; exit 2; }
fi
python_exe="$portable_root/tool/python/python.exe"
backend="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/fingerprint.py"
[[ -f "$python_exe" && -f "$backend" ]] || { echo "Error: package-local Python/fingerprint.py is missing." >&2; exit 2; }
export CODEX_INSTALL_DIR="$portable_root"
export HOME="$portable_root/home-runtime" USERPROFILE="$portable_root/home-runtime" TEMP="$portable_root/tmp" TMP="$portable_root/tmp" TMPDIR="$portable_root/tmp"
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
exec "$python_exe" "$backend" "$@"
