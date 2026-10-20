#!/usr/bin/env bash
# Thin compatibility wrapper for Codex Portable on Windows/Git Bash.
# Security-sensitive path/ZIP handling lives in decompile.ps1.
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
backend="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/decompile.ps1"
[[ -f "$backend" ]] || { echo "Error: decompile.ps1 backend is missing." >&2; exit 2; }
command -v cygpath >/dev/null 2>&1 || { echo "Error: this compatibility wrapper requires package-local Git Bash/cygpath." >&2; exit 2; }
[[ -n "${SYSTEMROOT:-}" ]] || { echo "Error: SYSTEMROOT is unavailable." >&2; exit 2; }
winroot="$(cygpath -u -- "$SYSTEMROOT")"
powershell="$winroot/System32/WindowsPowerShell/v1.0/powershell.exe"
[[ -f "$powershell" ]] || { echo "Error: Windows PowerShell bootstrap is unavailable." >&2; exit 2; }

ps_args=(-NoProfile -ExecutionPolicy Bypass -File "$backend")
input=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--output) [[ $# -ge 2 ]] || { echo "Error: $1 requires a value." >&2; exit 2; }; ps_args+=(-Output "$2"); shift 2 ;;
    --deobf) ps_args+=(-Deobf); shift ;;
    --no-res) ps_args+=(-NoRes); shift ;;
    --engine) [[ $# -ge 2 ]] || { echo "Error: --engine requires a value." >&2; exit 2; }; ps_args+=(-Engine "$2"); shift 2 ;;
    -h|--help) ps_args+=(-Help); shift ;;
    -*) echo "Error: unknown option: $1" >&2; exit 2 ;;
    *) [[ -z "$input" ]] || { echo "Error: only one input file is allowed." >&2; exit 2; }; input="$1"; shift ;;
  esac
done
[[ -z "$input" ]] || ps_args+=(-InputFile "$input")
export CODEX_INSTALL_DIR="$portable_root"
exec "$powershell" "${ps_args[@]}"
