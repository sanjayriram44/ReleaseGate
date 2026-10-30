#!/usr/bin/env bash
# Non-destructive post-deploy checks (CLAUDE.md §16.2); see scripts/post_deploy_check.py.
#   bash scripts/post_deploy_check.sh <base_url> <expected_sha> [--test-endpoints on|off] [--wait S]
# Uses the project venv (it needs PyYAML and httpx); set PYTHON to use another interpreter.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -z "${PYTHON:-}" ]; then
  for candidate in "$ROOT/.venv/bin/python" "$ROOT/.venv/Scripts/python.exe"; do
    if [ -x "$candidate" ]; then PYTHON="$candidate"; break; fi
  done
fi
cd "$ROOT"
exec "${PYTHON:-python3}" -m scripts.post_deploy_check "$@"
