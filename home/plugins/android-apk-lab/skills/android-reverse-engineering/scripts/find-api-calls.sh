#!/usr/bin/env bash
set -euo pipefail
# Compatibility wrapper for an explicitly provisioned package-local Bash.
# No host python3/grep/awk/sed fallback is allowed.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$SCRIPT_DIR"
for _ in 1 2 3 4 5 6 7 8; do
  if [[ -f "$ROOT/codex.exe" && -f "$ROOT/env.ps1" ]]; then break; fi
  PARENT="$(dirname "$ROOT")"
  [[ "$PARENT" == "$ROOT" ]] && break
  ROOT="$PARENT"
done
PY="$ROOT/tool/python/python.exe"
if [[ ! -f "$ROOT/codex.exe" || ! -f "$ROOT/env.ps1" ]]; then
  echo "ERROR: cannot locate Codex portable root" >&2; exit 2
fi
if [[ ! -f "$PY" ]]; then
  echo "ERROR: package-local Python is missing: $PY" >&2; exit 2
fi
exec "$PY" "$SCRIPT_DIR/find_api_calls.py" "$@"
