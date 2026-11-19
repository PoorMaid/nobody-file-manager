#!/system/bin/sh
# Nobody 网页文件管理器 · 停止脚本
# 用法：sh 停止.sh   （脚本会自己定位所在目录，不需要 cd）

SELF="$0"
case "$SELF" in
  */*) ;;
  *) C=$(command -v "$SELF" 2>/dev/null); [ -n "$C" ] && SELF="$C" ;;
esac
while [ -L "$SELF" ]; do
  L=$(ls -ld "$SELF" 2>/dev/null | sed 's/.*-> //')
  [ -z "$L" ] && break
  case "$L" in /*) SELF="$L" ;; *) SELF="$(dirname "$SELF")/$L" ;; esac
done
DIR=$(dirname "$SELF")
DIR=$(cd "$DIR" 2>/dev/null && pwd)
if [ -z "$DIR" ] || [ ! -f "$DIR/app/server.py" ]; then
  for c in /storage/emulated/0/Download/shhtml /sdcard/Download/shhtml "$(pwd)"; do
    if [ -f "$c/app/server.py" ]; then DIR=$(cd "$c" && pwd); break; fi
  done
fi

PIDF="$DIR/logs/server.pid"
PORTF="$DIR/logs/port.txt"
STOPTIP="sh '$DIR/停止.sh'"
STARTTIP="sh '$DIR/启动.sh'"

if [ -z "$DIR" ] || [ ! -f "$DIR/app/server.py" ]; then
  echo ""
  echo "❌ 无法定位程序目录"
  echo "   Failed to locate application directory"
  exit 1
fi

echo ""
echo "=============================================="
echo "  Nobody 网页文件管理器 · 停止程序"
echo "  Nobody Web File Manager · Stop"
echo "=============================================="
echo "  目录 Dir ：$DIR"
echo "  时间 Time：$(date '+%Y-%m-%d %H:%M:%S')"
echo ""

PORT=""
[ -f "$PORTF" ] && PORT=$(cat "$PORTF" 2>/dev/null | tr -d ' \r\n')
[ -z "$PORT" ] && PORT=9178

# 还有没有 server.py 进程活着
proc_alive() {
  for d in /proc/[0-9]*; do
    [ -d "$d" ] || continue
    pid=${d#/proc/}
    [ "$pid" = "$$" ] && continue
    cmd=$(tr '\0' ' ' < "$d/cmdline" 2>/dev/null)
    case "$cmd" in
      *server.py*) return 0 ;;
      *nohup*python*shhtml*|*python*shhtml*server*) return 0 ;;
    esac
  done
  return 1
}

# 端口有没有 HTTP 应答（只在确认进程仍在时才可能为真）
port_alive() {
  command -v curl >/dev/null 2>&1 || return 1
  code=$(curl -s -o /dev/null -m 2 -w '%{http_code}' "http://127.0.0.1:$PORT/" 2>/dev/null)
  case "$code" in
    2*|3*|4*|5*) return 0 ;;
  esac
  return 1
}

# 综合判定：进程活着 或 端口真有应答
still_running() {
  proc_alive && return 0
  port_alive && return 0
  return 1
}

# ---- 1. 首选：走服务自带的退出接口（无需 PID，无权限问题） ----
if command -v curl >/dev/null 2>&1; then
  echo "  · 请求服务自行退出 Requesting self-exit ..."
  curl -s -o /dev/null -m 3 "http://127.0.0.1:$PORT/api/stop_server" 2>/dev/null
  sleep 2
fi

# ---- 2. 仍未停，才按 PID 结束 ----
if still_running; then
  CANDS=""
  if [ -f "$PIDF" ]; then
    P=$(cat "$PIDF" 2>/dev/null | tr -d ' \r\n')
    [ -n "$P" ] && CANDS="$P"
  fi
  for d in /proc/[0-9]*; do
    [ -d "$d" ] || continue
    pid=${d#/proc/}
    case " $CANDS " in *" $pid "*) continue ;; esac
    cmd=$(tr '\0' ' ' < "$d/cmdline" 2>/dev/null)
    case "$cmd" in
      *server.py*) CANDS="$CANDS $pid" ;;
      *nobody*server*|*shhtml*server*) CANDS="$CANDS $pid" ;;
    esac
  done
  CANDS=$(echo "$CANDS" | tr ' ' '\n' | grep -E '^[0-9]+$' | sort -u | tr '\n' ' ')

  LIVE=""
  for pid in $CANDS; do
    kill -0 "$pid" 2>/dev/null || continue
    echo "  · 结束进程 Terminating PID：$pid"
    kill "$pid" 2>/dev/null
    LIVE="$LIVE $pid"
  done
  [ -n "$LIVE" ] && sleep 2
  for pid in $LIVE; do
    kill -0 "$pid" 2>/dev/null || continue
    echo "  · 强制结束 Force kill PID：$pid"
    kill -9 "$pid" 2>/dev/null
  done
  [ -n "$LIVE" ] && sleep 1
fi

# ---- 3. 校验（给服务 2 秒收尾时间，避免刚退出被误判） ----
sleep 2
if still_running; then
  echo ""
  echo "❌ 停止失败 Stop failed：端口 $PORT 仍在响应"
  echo ""
  echo "  服务在另一个环境里运行，本终端结束不了它的进程。"
  echo "  请回到启动它的那个终端（Termux / Ubuntu）按 Ctrl+C。"
  echo ""
  exit 1
fi

rm -f "$PIDF"
PPIDF="$DIR/logs/priv/privd.pid"
if [ -f "$PPIDF" ]; then
  PPD=$(cat "$PPIDF" 2>/dev/null | tr -d ' \r\n')
  if [ -n "$PPD" ] && [ -d "/proc/$PPD" ]; then
    echo "  · 结束提权守护 privd PID：$PPD"
    kill "$PPD" 2>/dev/null || true
    sleep 1
    [ -d "/proc/$PPD" ] && kill -9 "$PPD" 2>/dev/null || true
  fi
  rm -f "$PPIDF"
fi
echo ""
echo "=============================================="
echo "  ✅ 服务已停止 Service stopped"
echo "=============================================="
echo "  端口 $PORT 已释放 Port released"
echo ""
echo "  重新启动 Start again：$STARTTIP"
echo ""
