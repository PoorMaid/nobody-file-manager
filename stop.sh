#!/bin/sh
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
if pgrep -f "python3 .*server\.py" >/dev/null 2>&1; then
  pkill -f "python3 .*server\.py" || true
fi
echo "已停止 Nobody 文件管理器服务。"