import base64
import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

PRIV_Q = Path("/storage/emulated/0/Download/shhtml/logs/priv")
PRIVD = Path("/storage/emulated/0/Download/shhtml/app/privd.sh")
PRIV_PID = PRIV_Q / "privd.pid"

_ROOT_SU = None
_ROOT_CACHE = None


def _q():
    try:
        PRIV_Q.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return PRIV_Q


def call(action, cmd="", timeout=25.0):
    q = _q()
    tid = uuid.uuid4().hex[:16]
    cf = q / (tid + ".cmd")
    of = q / (tid + ".out")
    payload = {"action": action, "cmd": cmd}
    tmp = q / (tid + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(str(tmp), str(cf))
    deadline = time.time() + timeout
    while time.time() < deadline:
        if of.exists():
            try:
                raw = of.read_text(encoding="utf-8", errors="replace")
            except OSError:
                raw = ""
            try:
                of.unlink()
            except OSError:
                pass
            try:
                return json.loads(raw) if raw.strip() else {"ok": False, "err": "empty"}
            except Exception:
                return {"ok": False, "err": "badjson", "raw": raw[:200]}
        time.sleep(0.05)
    try:
        cf.unlink()
    except OSError:
        pass
    return {"ok": False, "err": "timeout"}


_ALIVE_CACHE = [0.0, False]


def _alive(fresh=False):
    now = time.time()
    if not fresh and now - _ALIVE_CACHE[0] < 10.0:
        return _ALIVE_CACHE[1]
    ok = call("ping", timeout=4.0).get("ok", False)
    _ALIVE_CACHE[0] = now
    _ALIVE_CACHE[1] = ok
    return ok


def _daemon_pid():
    try:
        raw = PRIV_PID.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return None
    try:
        pid = int(raw.split()[0])
    except Exception:
        return None
    if pid <= 0:
        return None
    try:
        os.kill(pid, 0)
    except Exception:
        return None
    return pid


def status():
    q = _q()
    pid = _daemon_pid()
    if pid is None:
        r = {"ok": False, "err": "nodaemon"}
        a = False
    else:
        r = call("ping", timeout=2.0)
        a = r.get("ok", False)
    if _find_root():
        mode = "root"
    elif a:
        mode = "shizuku"
    else:
        mode = "local"
    info = {
        "ok": True,
        "daemon": a,
        "queue": str(q),
        "uid": r.get("uid") if a else _self_uid(),
        "pid": r.get("pid"),
        "pong": a,
        "mode": mode,
        "root": _find_root(),
    }
    return info


def _has_real_root():
    try:
        names = os.listdir("/data/data")
    except Exception:
        return False
    probe = 0
    for n in names[:80]:
        p = "/data/data/" + n
        try:
            os.listdir(p)
            probe += 1
            if probe >= 3:
                return True
        except Exception:
            continue
    return False


def _find_root():
    global _ROOT_SU, _ROOT_CACHE
    if _ROOT_CACHE is not None:
        return _ROOT_CACHE
    _ROOT_CACHE = False
    if _self_uid() == 0 and _has_real_root():
        _ROOT_SU = ""
        _ROOT_CACHE = True
        return True
    for cand in ("/system/bin/su", "/system/xbin/su", "/sbin/su", "/su/bin/su", "/debug_ramdisk/su", "/data/adb/ksu/bin/su", "/data/adb/magisk/su"):
        exe = cand
        if not os.path.exists(exe):
            continue
        try:
            r = subprocess.run([exe, "-c", "id"], capture_output=True, timeout=5)
        except Exception:
            continue
        txt = ((r.stdout or b"") + (r.stderr or b"")).decode("utf-8", "replace")
        if "uid=0" in txt and _has_real_root():
            _ROOT_SU = exe
            _ROOT_CACHE = True
            return True
    return False


def root_available():
    return _find_root()


def _run_local(cmd, timeout):
    try:
        r = subprocess.run(["sh", "-c", cmd], capture_output=True, timeout=timeout)
        out = (r.stdout or b"").decode("utf-8", "replace")
        err = (r.stderr or b"").decode("utf-8", "replace")
        return {"ok": True, "out": out + err, "code": r.returncode, "uid": _self_uid(), "mode": "local"}
    except Exception as e:
        return {"ok": False, "err": str(e), "out": "", "code": -1, "mode": "local"}


def _run_root(cmd, timeout):
    try:
        if _ROOT_SU == "":
            r = subprocess.run(["sh", "-c", cmd], capture_output=True, timeout=timeout)
        else:
            r = subprocess.run([_ROOT_SU, "-c", cmd], capture_output=True, timeout=timeout)
        out = (r.stdout or b"").decode("utf-8", "replace")
        err = (r.stderr or b"").decode("utf-8", "replace")
        return {"ok": True, "out": out + err, "code": r.returncode, "uid": "0", "mode": "root"}
    except Exception as e:
        return {"ok": False, "err": str(e), "out": "", "code": -1, "mode": "root"}


def _self_uid():
    try:
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("Uid:"):
                    return int(line.split()[1])
    except Exception:
        pass
    try:
        return os.getuid()
    except Exception:
        return None


def _best_mode():
    if _find_root():
        return "root"
    if _alive():
        return "shizuku"
    return "local"


def sh(cmd, timeout=25.0):
    if _find_root():
        return _run_root(cmd, timeout)
    if not _alive():
        return _run_local(cmd, timeout)
    r = call("exec", cmd, timeout=timeout)
    if not r.get("ok") and r.get("err") in ("timeout", "empty", "badjson"):
        return _run_local(cmd, timeout)
    if not r.get("ok"):
        return _run_local(cmd, timeout)
    out = r.get("out")
    if out is None and r.get("b64") is not None:
        try:
            out = base64.b64decode(r["b64"]).decode("utf-8", "replace")
        except Exception:
            out = ""
    return {"ok": True, "out": out or "", "uid": r.get("uid"), "code": 0, "mode": "shizuku"}


def _esc(s):
    return "'" + str(s).replace("'", "'\\''") + "'"


def ls(path):
    p = str(path)
    script = (
        'for x in "$P"/* "$P"/.[!.]*; do\n'
        '[ -e "$x" ] || continue\n'
        'if [ -d "$x" ]; then t=d; else t=f; fi\n'
        'sz=$(stat -c %s "$x" 2>/dev/null)\n'
        'ms=$(stat -c %Y "$x" 2>/dev/null)\n'
        'echo "$t|$sz|$ms|$(basename "$x")"\n'
        'done 2>&1'
    )
    cmd = "P=" + _esc(p) + "; " + script
    r = sh(cmd)
    if not r.get("ok"):
        return r
    items = []
    for line in (r.get("out") or "").splitlines():
        parts = line.split("|", 3)
        if len(parts) != 4:
            continue
        t, sz, ms, name = parts
        if t not in ("d", "f"):
            continue
        if name in (".", ".."):
            continue
        try:
            size = int(sz)
        except ValueError:
            size = 0
        try:
            mtime = int(ms)
        except ValueError:
            mtime = 0
        items.append({"name": name, "dir": t == "d", "size": size, "mtime": mtime})
    items.sort(key=lambda x: (not x["dir"], x["name"].lower()))
    return {"ok": True, "path": p, "items": items}


def read_text(path, limit=4 * 1024 * 1024):
    p = _esc(path)
    r = sh("stat -c %s " + p + " 2>/dev/null; echo '---'; head -c " + str(limit) + " " + p + " 2>&1 | base64")
    if not r.get("ok"):
        return r
    txt = r.get("out") or ""
    if "---" not in txt:
        return {"ok": False, "err": "read failed", "out": txt}
    head, b64 = txt.split("---", 1)
    try:
        size = int(head.strip() or 0)
    except ValueError:
        size = 0
    import base64 as _b
    try:
        data = _b.b64decode(b64.strip().replace("\n", ""))
    except Exception:
        return {"ok": False, "err": "decode failed"}
    return {"ok": True, "size": size, "text": data.decode("utf-8", errors="replace"), "truncated": size > limit}


def write_text(path, text):
    import base64 as _b
    b64 = _b.b64encode(text.encode("utf-8")).decode("ascii")
    p = _esc(path)
    cmd = "printf '%%s' %s | base64 -d > %s && echo WRITE_OK" % (_esc(b64), p)
    r = sh(cmd)
    if not r.get("ok"):
        return r
    if "WRITE_OK" not in (r.get("out") or ""):
        return {"ok": False, "err": r.get("out", "write failed")}
    return {"ok": True}


def op(action, path, target="", name=""):
    p = _esc(path)
    if action == "mkdir":
        cmd = "mkdir -p %s && echo DONE" % p
    elif action == "newfile":
        cmd = ": > %s && echo DONE" % p
    elif action == "remove":
        cmd = "rm -rf %s && echo DONE" % p
    elif action == "rename":
        cmd = "mv %s %s && echo DONE" % (p, _esc(target))
    elif action == "copy":
        cmd = "cp -a %s %s && echo DONE" % (p, _esc(target))
    elif action == "move":
        cmd = "mv %s %s && echo DONE" % (p, _esc(target))
    else:
        return {"ok": False, "err": "unknown op"}
    r = sh(cmd)
    if not r.get("ok"):
        return r
    ok = "DONE" in (r.get("out") or "")
    return {"ok": ok, "out": r.get("out", "")}


def start_hint():
    return "sh '%s' '%s'" % (str(PRIVD), str(PRIV_Q))
