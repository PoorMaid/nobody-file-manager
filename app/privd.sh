#!/system/bin/sh
# Nobody 网页文件管理器 · 提权守护进程（shell 身份）
# 由 Shizuku / root 以 shell 身份启动，循环扫描队列目录执行指令。
# 指令格式：<taskid>.cmd（内含 JSON）  结果：<taskid>.out
Q="$1"
[ -z "$Q" ] && Q=/storage/emulated/0/Download/shhtml/logs/priv
mkdir -p "$Q" 2>/dev/null
PIDF="$Q/privd.pid"
if [ -f "$PIDF" ]; then
  OP=$(cat "$PIDF" 2>/dev/null)
  if [ -n "$OP" ] && [ -d "/proc/$OP" ]; then
    echo "already running pid=$OP" >> "$Q/privd.log"
    exit 0
  fi
fi
echo $$ > "$PIDF" 2>/dev/null
LOG="$Q/privd.log"
echo "[$(date '+%F %T')] privd start pid=$$ uid=$(id -u) q=$Q" >> "$LOG"
json_get() {
  printf '%s' "$1" | sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p"
}
json_get_raw() {
  printf '%s' "$1" | sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\([^,}]*\).*/\1/p"
}
unescape() {
  printf '%b' "$1"
}
clip() {
  n=${#1}
  if [ "$n" -gt "$2" ]; then printf '%s' "${1%${1#$3}}" | head -c "$2"; else printf '%s' "$1"; fi
}
while :; do
  found=0
  for f in "$Q"/*.cmd; do
    [ -f "$f" ] || continue
    found=1
    tid=$(basename "$f" .cmd)
    out="$Q/$tid.out"
    cmdjson=$(cat "$f" 2>/dev/null)
    rm -f "$f" 2>/dev/null
    [ -z "$cmdjson" ] && continue
    action=$(json_get "$cmdjson" "action")
    [ -z "$action" ] && action=$(json_get_raw "$cmdjson" "action")
    case "$action" in
      exec)
        c=$(json_get "$cmdjson" "cmd")
        c=$(unescape "$c")
        {
          printf '{"ok":true,"uid":"%s","b64":"' "$(id -u)"
          sh -c "$c" 2>&1 | base64 2>/dev/null | tr -d '\n'
          printf '"}'
        } > "$out.tmp" 2>&1
        mv "$out.tmp" "$out" 2>/dev/null
        ;;
      ping)
        printf '{"ok":true,"pong":true,"uid":%s,"pid":%s,"time":"%s"}' "$(id -u)" "$$" "$(date '+%F %T')" > "$out" 2>/dev/null
        ;;
      *)
        printf '{"ok":false,"err":"unknown action"}' > "$out" 2>/dev/null
        ;;
    esac
    echo "[$(date '+%F %T')] task $tid action=$action done" >> "$LOG"
  done
  [ "$found" = "1" ] && continue
  sleep 0.4
done
