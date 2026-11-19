#!/system/bin/sh
# Nobody 网页文件管理器 · 启动脚本（免 root）
# 用法：sh 启动.sh            进入菜单
#       sh 启动.sh start      直接启动
#       sh 启动.sh stop       直接停止
#       sh 启动.sh status     查看状态
#       sh 启动.sh install    自动安装 Python

# ---------- 1. 自定位：算出脚本所在目录 ----------
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
if [ -z "$DIR" ] || [ ! -d "$DIR" ]; then
  for t in /storage/emulated/0/Download/shhtml /sdcard/Download/shhtml "$(pwd)"; do
    [ -f "$t/启动.sh" ] && DIR="$t" && break
  done
fi
if [ -z "$DIR" ] || [ ! -d "$DIR" ]; then
  echo "❌ 无法定位脚本所在目录，请 cd 到本文件夹后执行。"
  exit 1
fi

APP="$DIR/app/server.py"
WEB="$DIR/web/index.html"
LOGDIR="$DIR/logs"
LOG="$LOGDIR/server.log"
PIDF="$LOGDIR/server.pid"
PORTF="$LOGDIR/port.txt"
RUNCMD="sh '$DIR/启动.sh'"
STOPCMD="sh '$DIR/停止.sh'"
STATCMD="sh '$DIR/启动.sh' status"
MENUCMD="sh '$DIR/启动.sh'"
show_cmds() {
  echo ""
  echo "  ---- 复制到其它终端执行 Copy to another terminal ----"
  echo "  启动 Start  ：$RUNCMD"
  echo "  停止 Stop   ：$STOPCMD"
  echo "  状态 Status ：$STATCMD"
  echo "  菜单 Menu   ：$MENUCMD"
  echo "  提示 Tip    ：安卓原生 shell 装不了 python，请用 Termux 或 proot Linux"
  echo "   --------------------------------------------------"
}

mkdir -p "$LOGDIR" 2>/dev/null

# ---------- 2. 工具函数 ----------
pause_any() {
  [ -t 0 ] || return 0
  echo ""
  printf "  按回车返回菜单 ... "
  read -r _x
}

find_python() {
  PY=""
  for c in python3 python "$PREFIX/bin/python3" /usr/bin/python3 /usr/local/bin/python3 /data/data/com.termux/files/usr/bin/python3; do
    [ -z "$c" ] && continue
    P=$(command -v "$c" 2>/dev/null)
    if [ -n "$P" ]; then
      PY="$P"
      return 0
    fi
  done
  return 1
}

port_busy() {
  _p="$1"
  [ -z "$_p" ] && return 1
  # fuser 在 proot 下会误报已死进程，不采用
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | grep -q ":$_p\$" && return 0
  fi
  if command -v netstat >/dev/null 2>&1; then
    netstat -ltn 2>/dev/null | grep -q ":$_p " && return 0
  fi
  [ -z "$PY" ] && return 1
  "$PY" - "$_p" <<'PYEOF' >/dev/null 2>&1
import socket, sys
p = int(sys.argv[1])
s = socket.socket()
s.settimeout(0.4)
try:
    r = s.connect_ex(("127.0.0.1", p))
finally:
    s.close()
sys.exit(0 if r == 0 else 1)
PYEOF
  return $?
}

running_pid() {
  [ -f "$PIDF" ] || return 1
  _pid=$(cat "$PIDF" 2>/dev/null)
  [ -z "$_pid" ] && return 1
  kill -0 "$_pid" 2>/dev/null || return 1
  echo "$_pid"
}

show_head() {
  echo ""
  echo "=============================================="
  echo "  Nobody 网页文件管理器"
  echo "  时间 Time：$(date '+%Y-%m-%d %H:%M:%S')"
  echo "  目录 Dir ：$DIR"
  if [ -n "$PY" ]; then
    echo "  Python   ：$PY"
  else
    echo "  Python   ：✗ 未安装 Not installed"
  fi
  echo "=============================================="
}

# ---------- 3. 自动安装 Python ----------
do_install_python() {
  show_head
  echo ""
  echo "  🔧 自动安装 Python"
  echo ""
  find_python
  if [ -n "$PY" ]; then
    echo "  ✅ 已经装好了 Already installed"
    echo "  · 路径 Path：$PY"
    echo "  · 版本 Ver ：$($PY -V 2>&1)"
    pause_any
    return 0
  fi
  PM=""
  if [ -n "$PREFIX" ] && command -v pkg >/dev/null 2>&1; then PM="pkg"
  elif command -v apt >/dev/null 2>&1; then PM="apt"
  elif command -v apt-get >/dev/null 2>&1; then PM="apt-get"
  elif command -v dnf >/dev/null 2>&1; then PM="dnf"
  elif command -v yum >/dev/null 2>&1; then PM="yum"
  elif command -v pacman >/dev/null 2>&1; then PM="pacman"
  elif command -v apk >/dev/null 2>&1; then PM="apk"
  fi
  if [ -z "$PM" ]; then
    echo "  ❌ 没找到可用的包管理器 Package manager not found"
    echo ""
    echo "  【A】当前是 Android 原生 shell，装不了 python"
    echo "       请改用 Termux 或 proot 环境"
    echo "  【B】自己在别处装好后，回到菜单选 1 启动"
    pause_any
    return 1
  fi
  echo "  · 包管理器 Package manager：$PM"
  echo "  · 开始安装，可能需要几分钟，请稍候 ......"
  echo ""
  case "$PM" in
    pkg)
      pkg update -y 2>&1 | tail -5
      pkg install -y python 2>&1 | tail -10
      ;;
    apt|apt-get)
      export DEBIAN_FRONTEND=noninteractive
      if [ "$(id -u)" = "0" ]; then
        $PM update -y 2>&1 | tail -5
        $PM install -y python3 2>&1 | tail -10
      else
        sudo $PM update -y 2>&1 | tail -5
        sudo $PM install -y python3 2>&1 | tail -10
      fi
      ;;
    dnf|yum)
      $PM install -y python3 2>&1 | tail -10
      ;;
    pacman)
      pacman -Sy --noconfirm python 2>&1 | tail -10
      ;;
    apk)
      apk add python3 2>&1 | tail -10
      ;;
  esac
  echo ""
  find_python
  if [ -n "$PY" ]; then
    echo "  ✅ 安装成功 Install successful"
    echo "  · 路径 Path：$PY"
    echo "  · 版本 Ver ：$($PY -V 2>&1)"
    echo ""
    echo "  回到菜单选 1 即可启动。"
    pause_any
    return 0
  fi
  echo "  ❌ 还是没找到 python Still not found"
  echo ""
  echo "  【A】关掉终端重开，让 PATH 刷新后重试"
  echo "  【B】换用 Termux（F-Droid 版）安装 python"
  echo "  【C】换用 proot Linux 环境安装 python3"
  pause_any
  return 1
}

# ---------- 4. 启动服务 ----------
do_start() {
  show_head
  echo ""
  OP=$(running_pid)
  if [ -n "$OP" ]; then
    echo "  ⚠️ 服务已在运行 Service already running"
    echo "  · 进程 PID：$OP"
    echo ""
    if [ ! -t 0 ]; then
      echo "  · 非交互模式，不重启 Non-interactive, skip restart"
      return 0
    fi
    echo "  【1】重启服务 Restart"
    echo "  【2】返回菜单 Back"
    printf "  请选择："
    read -r _c
    case "$_c" in
      1)
        kill "$OP" 2>/dev/null
        sleep 1
        kill -9 "$OP" 2>/dev/null
        rm -f "$PIDF"
        echo ""
        echo "  · 旧进程已结束"
        ;;
      *) return 0 ;;
    esac
  fi
  echo ""
  echo "  [1/5] 检查文件 Check files"
  if [ ! -f "$APP" ]; then
    echo "  ❌ 缺少后端文件：$APP"
    pause_any
    return 1
  fi
  if [ ! -f "$WEB" ]; then
    echo "  ❌ 缺少前端文件：$WEB"
    pause_any
    return 1
  fi
  echo "        OK"
  echo ""
  echo "  [2/5] 检查 Python Check Python"
  if ! find_python; then
    echo "  ❌ 未找到 python3 Not installed"
    echo ""
    if [ ! -t 0 ]; then
      echo "  · 非交互模式，跳过安装 Non-interactive, skip install"
      show_cmds
      return 1
    fi
    echo "  【1】自动安装 Python Install Python"
    echo "  【2】返回菜单 Back"
    printf "  请选择："
    read -r _c
    case "$_c" in
      1) do_install_python; find_python ;;
      *) return 1 ;;
    esac
    if [ -z "$PY" ]; then
      echo "  ❌ 仍然没有 python，无法启动"
      pause_any
      return 1
    fi
  fi
  echo "        OK：$PY ($($PY -V 2>&1))"
  echo ""
  echo "  [3/5] 清理旧进程 Clean old process"
  if [ -f "$PIDF" ]; then
    OLDPID=$(cat "$PIDF" 2>/dev/null)
    if [ -n "$OLDPID" ]; then
      kill "$OLDPID" 2>/dev/null && echo "        已结束旧进程 $OLDPID" || true
      sleep 1
      kill -9 "$OLDPID" 2>/dev/null || true
    fi
    rm -f "$PIDF"
  fi
  echo "        OK"
  echo ""
  echo "  [4/5] 选择端口并启动 Select port and start"
  PORT=""
  for p in "${SHHTML_PORT:-9178}" 9178 9179 9180 9181 9190 8888 9000; do
    if ! port_busy "$p"; then
      PORT="$p"
      break
    fi
  done
  if [ -z "$PORT" ]; then
    echo "  ❌ 没有可用端口，可用 SHHTML_PORT=xxxx sh 启动.sh 指定"
    pause_any
    return 1
  fi
  SU_BIN=""
  for s in su /system/bin/su /system/xbin/su /sbin/su; do
    if command -v "$s" >/dev/null 2>&1 || [ -x "$s" ]; then
      if "$s" -c "id" >/dev/null 2>&1; then SU_BIN="$s"; break; fi
    fi
  done
  if [ -n "$SU_BIN" ]; then
    echo "        Root：已获取 ($SU_BIN)，后端以 root 运行"
    SHHTML_PORT="$PORT" SHHTML_ROOT="${SHHTML_ROOT:-/}" nohup "$SU_BIN" -c "SHHTML_PORT=$PORT SHHTML_ROOT=${SHHTML_ROOT:-/} \"$PY\" \"$APP\"" >"$LOG" 2>&1 &
  else
    echo "        Root：未获取，后端以当前用户运行（根目录受限）"
    SHHTML_PORT="$PORT" nohup "$PY" "$APP" >"$LOG" 2>&1 &
  fi
  SRVPID=$!
  echo "$SRVPID" > "$PIDF"
  sleep 1
  if ! kill -0 "$SRVPID" 2>/dev/null; then
    echo "  ❌ 进程启动后立即退出，日志如下："
    tail -20 "$LOG" 2>/dev/null
    rm -f "$PIDF"
    pause_any
    return 1
  fi
  echo "        Port：$PORT  PID：$SRVPID"
  OK=""
  _hc=0
  while [ $_hc -lt 10 ]; do
    if command -v curl >/dev/null 2>&1; then
      curl -s -o /dev/null -m 3 "http://127.0.0.1:$PORT/" && { OK="1"; break; }
    else
      "$PY" - "$PORT" <<'HEOF' >/dev/null 2>&1 && { OK="1"; break; }
import sys, urllib.request
urllib.request.urlopen("http://127.0.0.1:%s/" % sys.argv[1], timeout=3).read()
HEOF
    fi
    kill -0 "$SRVPID" 2>/dev/null || break
    sleep 0.5
    _hc=$((_hc+1))
  done
  if [ -z "$OK" ]; then
    echo "  ⚠️ 健康检查未通过，请看日志：$LOG"
    tail -20 "$LOG" 2>/dev/null
    pause_any
    return 1
  fi
  echo "        Health check passed"
  echo ""
  echo "  [5/5] 获取访问网址 Get access URL"
  LAN=$("$PY" - <<'PYEOF' 2>/dev/null
import socket
ip = ""
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    s.close()
except Exception:
    ip = ""
if not ip or ip.startswith("127."):
    try:
        for r in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            a = r[4][0]
            if not a.startswith("127."):
                ip = a
                break
    except Exception:
        pass
print(ip)
PYEOF
)
  [ -z "$LAN" ] && LAN="127.0.0.1"
  URL="http://$LAN:$PORT/"
  echo "$PORT" > "$PORTF"
  echo "$URL" > "$LOGDIR/url.txt"
  echo ""
  echo "=============================================="
  echo "  ✅ 启动成功 Startup successful"
  echo "=============================================="
  echo "  访问网址 URL   ：$URL"
  echo "  本机网址 Local ：http://127.0.0.1:$PORT/"
  echo "  端口 Port      ：$PORT"
  echo "  进程 PID       ：$SRVPID"
  echo "=============================================="
  echo ""
  echo "  📋 复制网址 Copy URL：$URL"
  echo ""
  echo "  · 同一 WiFi 下的手机/电脑，浏览器打开上面网址即可"
  echo "  · 停止服务 Stop：$STOPCMD"
  echo "  · 查看日志 Log ：cat '$LOG'"
  show_cmds
  echo ""
  echo "  服务已在后台运行，可关闭此终端。"
  echo "  Service is running in background, you can close this terminal."
  pause_any
  return 0
}

# ---------- 5. 停止服务 ----------
do_stop() {
  show_head
  echo ""
  P=$(running_pid)
  if [ -z "$P" ]; then
    echo "  · 服务未在运行 Service not running"
    rm -f "$PIDF"
    pause_any
    return 0
  fi
  echo "  · 正在停止 PID $P ......"
  kill "$P" 2>/dev/null
  i=0
  while [ $i -lt 5 ]; do
    kill -0 "$P" 2>/dev/null || break
    sleep 1
    i=$((i+1))
  done
  if kill -0 "$P" 2>/dev/null; then
    kill -9 "$P" 2>/dev/null
    sleep 1
  fi
  rm -f "$PIDF"
  echo ""
  echo "  ✅ 服务已停止 Service stopped"
  echo "  · 端口已释放 Port released"
  pause_any
  return 0
}

# ---------- 6. 查看状态 ----------
do_status() {
  show_head
  echo ""
  P=$(running_pid)
  if [ -n "$P" ]; then
    PT=$(cat "$PORTF" 2>/dev/null)
    [ -z "$PT" ] && PT="?"
    echo "  · 状态 Status：✅ 运行中 Running"
    echo "  · PID        ：$P"
    echo "  · 端口 Port  ：$PT"
    if [ -f "$LOGDIR/url.txt" ]; then
      echo "  · 网址 URL   ：$(cat "$LOGDIR/url.txt" 2>/dev/null)"
    fi
  else
    echo "  · 状态 Status：· 未运行 Not running"
  fi
  echo ""
  if [ -n "$PY" ]; then
    echo "  · Python     ：$PY ($($PY -V 2>&1))"
  else
    echo "  · Python     ：✗ 未安装 Not installed"
  fi
  echo "  · 后端 Back  ：$APP"
  echo "  · 前端 Front ：$WEB"
  echo "  · 日志 Log   ：$LOG"
  pause_any
  return 0
}

# ---------- 7. 查看日志 ----------
do_log() {
  show_head
  echo ""
  if [ ! -f "$LOG" ]; then
    echo "  · 还没有日志 No log yet"
    pause_any
    return 0
  fi
  echo "  ---- 最后 30 行 Last 30 lines ----"
  tail -30 "$LOG" 2>/dev/null
  echo "  --------------------------------"
  pause_any
  return 0
}

# ---------- 8. 主菜单 ----------
main_menu() {
  while :; do
    find_python >/dev/null 2>&1
    show_head
    echo ""
    if [ -n "$PY" ]; then
      P=$(running_pid)
      if [ -n "$P" ]; then
        echo "  状态 Status：✅ 运行中 Running（PID $P）"
      else
        echo "  状态 Status：· 未运行 Not running"
      fi
      echo ""
      echo "  【1】启动 Start"
      echo "  【2】停止 Stop"
      echo "  【3】重新安装 Python Reinstall Python"
      echo "  【4】查看状态 Status"
      echo "  【5】查看日志 Log"
      echo "  【0】退出 Exit"
    else
      echo "  状态 Status：✗ 没有 Python，无法启动"
      echo ""
      echo "  【1】自动安装 Python Install Python"
      echo "  【2】退出 Exit"
    fi
    echo ""
    show_cmds
    echo ""
    printf "  请输入编号："
    read -r CH
    echo ""
    if [ -z "$PY" ]; then
      case "$CH" in
        1) do_install_python ;;
        2|0|q|Q) echo "  已退出 Bye"; exit 0 ;;
        *) echo "  ⚠️ 无效输入 Invalid input，请输入 1 或 2" ; sleep 1 ;;
      esac
    else
      case "$CH" in
        1) do_start ;;
        2) do_stop ;;
        3) do_install_python ;;
        4) do_status ;;
        5) do_log ;;
        0|q|Q) echo "  已退出 Bye"; exit 0 ;;
        *) echo "  ⚠️ 无效输入 Invalid input，请输入 0-5" ; sleep 1 ;;
      esac
    fi
  done
}

# ---------- 9. 入口 ----------
find_python >/dev/null 2>&1
case "$1" in
  start) do_start ;;
  stop) do_stop ;;
  status) do_status ;;
  install) do_install_python ;;
  log) do_log ;;
  *) main_menu ;;
esac
exit 0
