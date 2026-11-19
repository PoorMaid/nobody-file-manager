import os
import pty
import select
import shlex
import signal
import subprocess
import threading
import time
import uuid

MAXOUT = 400000

_sessions = {}
_lock = threading.Lock()


class Session:
    def __init__(self, cwd, mode="local"):
        self.id = uuid.uuid4().hex[:12]
        self.cwd = cwd
        self.mode = mode
        self.buf = ""
        self.alive = True
        self.code = None
        self.started = time.time()
        self.master = None
        self.proc = None
        self._th = None

    def start(self, argv):
        master, slave = pty.openpty()
        self.master = master
        env = dict(os.environ)
        env["TERM"] = "dumb"
        env["PS1"] = ""
        env["PS2"] = ""
        env["PYTHONUNBUFFERED"] = "1"
        self.proc = subprocess.Popen(
            argv,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            cwd=self.cwd,
            env=env,
            preexec_fn=os.setsid,
            close_fds=True,
        )
        os.close(slave)
        self._th = threading.Thread(target=self._reader, daemon=True)
        self._th.start()

    def _reader(self):
        fd = self.master
        while True:
            try:
                r, _, _ = select.select([fd], [], [], 0.25)
            except Exception:
                break
            if not r:
                if self.proc is not None and self.proc.poll() is not None:
                    break
                continue
            try:
                chunk = os.read(fd, 8192)
            except OSError:
                break
            if not chunk:
                break
            self.buf += chunk.decode("utf-8", "replace")
            if len(self.buf) > MAXOUT:
                self.buf = self.buf[-MAXOUT:]
        try:
            if self.proc is not None:
                self.code = self.proc.wait(timeout=1.0)
                for _ in range(20):
                    try:
                        r2, _, _ = select.select([fd], [], [], 0.02)
                    except Exception:
                        break
                    if not r2:
                        break
                    try:
                        tail = os.read(fd, 8192)
                    except OSError:
                        break
                    if not tail:
                        break
                    self.buf += tail.decode("utf-8", "replace")
                    if len(self.buf) > MAXOUT:
                        self.buf = self.buf[-MAXOUT:]
        except Exception:
            pass
        self.alive = False
        try:
            os.close(fd)
        except Exception:
            pass

    def drain(self, reset=True):
        with _lock:
            out = self.buf
            if reset and self.alive:
                self.buf = ""
        return out

    def write(self, data):
        if not self.alive or self.master is None:
            return False
        with _lock:
            try:
                os.write(self.master, data.encode("utf-8", "replace"))
                return True
            except Exception:
                return False

    def kill(self):
        try:
            if self.proc is not None and self.proc.poll() is None:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
        except Exception:
            pass
        self.alive = False

    def info(self):
        return {
            "ok": True,
            "id": self.id,
            "alive": self.alive,
            "code": self.code,
            "cwd": self.cwd,
            "mode": self.mode,
            "pid": self.proc.pid if self.proc else None,
            "elapsed": round(time.time() - self.started, 2),
        }


def open_script(path, cwd, mode="local"):
    s = Session(cwd, mode)
    s.start(["sh", path])
    with _lock:
        _sessions[s.id] = s
    return s


def open_shell(cwd, mode="local"):
    s = Session(cwd, mode)
    s.start(["sh", "-i"])
    with _lock:
        _sessions[s.id] = s
    return s


def get(sid):
    with _lock:
        return _sessions.get(sid)


def close(sid):
    s = get(sid)
    if not s:
        return False
    s.kill()
    with _lock:
        _sessions.pop(sid, None)
    return True


def gc(max_idle=1800):
    now = time.time()
    dead = []
    with _lock:
        for k, s in list(_sessions.items()):
            if not s.alive and now - s.started > 60:
                dead.append(k)
            elif now - s.started > max_idle:
                dead.append(k)
        for k in dead:
            s = _sessions.pop(k, None)
            if s:
                s.kill()
    return len(dead)
