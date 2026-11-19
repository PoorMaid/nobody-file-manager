#!/system/bin/sh
# Nobody 网页文件管理器 · 提权自动引导
# 用法：sh app/privboot.sh [项目目录]
# 作用：按 su -> rish -> adb 顺序探测可用的提权通道，
#       找到就以该身份拉起 app/privd.sh，让后端拿到 shell 权限。
# 全部失败则安静退出（返回码 1），不影响服务本身启动。

DIR="$1"
if [ -z "$DIR" ]; then
  SELF="$0"
  case "$SELF" in
    */*) ;;
    *) C=$(command -v "$SELF" 2>/dev/null); [ -n "$C" ] && SELF="$C" ;;
  esac
  DIR=$(cd "$(dirname "$SELF")/.." 2>/dev/null && pwd)
fi
[ -z "$DIR" ] && DIR=/storage/emulated/0/Download/shhtml

PRIVD="$DIR/app/privd.sh"
PQ="$DIR/logs/priv"
PIDF="$PQ/privd.pid"
BOOTLOG="$PQ/privboot.log"

[ -f "$PRIVD" ] || { echo "缺 privd.sh"; exit 1; }
mkdir -p "$PQ" 2>/dev/null

say() {
  echo "$1"
  echo "[$(date '+%F %T')] $1" >> "$BOOTLOG" 2>/dev/null
}

# 已有存活实例就不重复启动
if [ -f "$PIDF" ]; then
  OLD=$(tr -d ' \r\n' < "$PIDF" 2>/dev/null)
  if [ -n "$OLD" ] && [ -d "/proc/$OLD" ]; then
    OUID=$(awk '/^Uid:/{print $2}' "/proc/$OLD/status" 2>/dev/null)
    say "privd 已在线 pid=$OLD uid=$OUID"
    [ "$OUID" = "2000" ] && exit 0
    exit 0
  fi
fi

# 后台脱离启动，避免终端关闭后被杀
LAUNCH="(setsid sh '$PRIVD' '$PQ' >/dev/null 2>&1 </dev/null &)"

# 启动后等 privd 回 ping，确认身份
wait_ok() {
  i=0
  while [ $i -lt 20 ]; do
    if [ -f "$PIDF" ]; then
      P=$(tr -d ' \r\n' < "$PIDF" 2>/dev/null)
      if [ -n "$P" ] && [ -d "/proc/$P" ]; then
        U=$(awk '/^Uid:/{print $2}' "/proc/$P/status" 2>/dev/null)
        [ -n "$U" ] && { echo "$P"; return 0; }
      fi
    fi
    sleep 0.25
    i=$((i+1))
  done
  return 1
}

try_done() {
  P=$(wait_ok)
  if [ -n "$P" ]; then
    U=$(awk '/^Uid:/{print $2}' "/proc/$P/status" 2>/dev/null)
    say "✅ 提权成功：渠道=$1 pid=$P uid=$U"
    exit 0
  fi
  say "⚠️ 渠道 $1 已执行但 privd 未起来，继续尝试下一个"
  return 1
}

# ---------- 渠道 1：su / root ----------
for s in su /system/bin/su /system/xbin/su /sbin/su; do
  if command -v "$s" >/dev/null 2>&1 || [ -x "$s" ]; then
    if "$s" -c "id -u" 2>/dev/null | grep -q '^0$'; then
      say "发现 root：$s"
      "$s" -c "$LAUNCH" >/dev/null 2>&1
      try_done "su($s)" && exit 0
      break
    fi
  fi
done

# ---------- 渠道 2：rish / Shizuku ----------
RISH=""
for r in "$DIR/rish" /data/local/tmp/rish \
         /sdcard/Android/data/moe.shizuku.privileged.api/files/rikka.shizuku/rish \
         /storage/emulated/0/Android/data/moe.shizuku.privileged.api/files/rikka.shizuku/rish; do
  if [ -f "$r" ]; then
    if sh "$r" -c 'id -u' 2>/dev/null | grep -q '^2000$'; then
      RISH="$r"
      break
    fi
  fi
done
if [ -z "$RISH" ] && command -v rish >/dev/null 2>&1; then
  RISH=$(command -v rish)
fi

if [ -n "$RISH" ]; then
  say "发现 Shizuku 通道：$RISH"
  sh "$RISH" -c "$LAUNCH" >/dev/null 2>&1
  try_done "rish" && exit 0
else
  # rish 缺失时尝试用 Shizuku 的 dex 自建（同目录已有 dex 则由上面覆盖）
  if [ -f "$DIR/rish_shizuku.dex" ]; then
    say "未找到 rish，但检测到 rish_shizuku.dex"
  fi
fi

# ---------- 渠道 3：adb ----------
ADB=""
for a in adb /system/bin/adb /root/android-sdk/platform-tools/adb "$PREFIX/bin/adb"; do
  if command -v "$a" >/dev/null 2>&1 || [ -x "$a" ]; then
    if "$a" shell 'id -u' 2>/dev/null | tr -d '\r' | grep -q '^2000$'; then
      ADB="$a"
      break
    fi
  fi
done
if [ -n "$ADB" ]; then
  say "发现 adb 通道：$ADB"
  "$ADB" shell "$LAUNCH" >/dev/null 2>&1
  try_done "adb" && exit 0
fi

# ---------- 全部失败 ----------
say "未发现可用提权通道（su/rish/adb 均不可用）"
say "如需提权：在 Shizuku 终端执行 sh '$PRIVD' '$PQ' &"
exit 1
