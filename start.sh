#!/bin/sh
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "启动 Nobody 文件管理器…"

# 停止旧进程
if pgrep -f "python3 .*server\.py" >/dev/null 2>&1; then
  pkill -f "python3 .*server\.py" || true
  sleep 1
fi
rm -f server.log

PY="$(command -v python3 || command -v python)"
if [ -z "$PY" ]; then
  echo "错误：未找到 python3，无法启动。"
  exit 1
fi

nohup "$PY" server.py > server.log 2>&1 &
SRVPID=$!
sleep 2
if ! kill -0 "$SRVPID" >/dev/null 2>&1; then
  echo "错误：Python 启动后立即退出，日志如下："
  cat server.log
  exit 1
fi

HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
[ -z "$HOST_IP" ] && HOST_IP="127.0.0.1"
PORT="$(grep -oP 'PORT = int\(os\.environ\.get\("SHHTML_PORT", "\K\d+' server.py 2>/dev/null || true)"
[ -z "$PORT" ] && PORT="8080"

echo ""
echo "==============================="
echo " Nobody 文件管理器已启动"
echo " 访问地址：http://$HOST_IP:$PORT/"
echo " 服务 PID：$SRVPID"
echo " 停止：sh stop.sh"
echo "==============================="
