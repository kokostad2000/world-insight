#!/bin/bash
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
"$ROOT_DIR/scripts/start.sh" "$@"
RESULT=$?
if [ "$RESULT" -ne 0 ] && [ -t 0 ]; then
  echo "操作未完成，具体原因见上方。按回车关闭窗口。"
  read -r UNUSED_REPLY
fi
exit "$RESULT"
