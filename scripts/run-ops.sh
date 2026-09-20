#!/bin/bash
set -eu
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${WORLD_INSIGHT_PYTHON:-python3.11}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  if command -v python3 >/dev/null 2>&1; then PYTHON_BIN="python3"; else
    echo "阻断：未找到 Python 3.11。请完成 README 首次准备，或设置 WORLD_INSIGHT_PYTHON。" >&2
    exit 1
  fi
fi
cd "$ROOT_DIR"
exec "$PYTHON_BIN" -m ops.cli "$@"
