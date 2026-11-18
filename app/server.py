#!/usr/bin/env python3
import json
import io
import os
import shutil
import signal
import time
import sys
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs, unquote
from pathlib import Path
import base64
import shutil
import subprocess

BASE_DIR = Path(__file__).resolve().parent
APP_ROOT = BASE_DIR.parent
PANEL_HTML = APP_ROOT / "web" / "index.html"
PORT = int(os.environ.get("SHHTML_PORT", "9178"))
HOST = "0.0.0.0"

def choose_root():
    env = os.environ.get("SHHTML_ROOT")
    if env:
        p = Path(env).expanduser()
        try:
            if p.is_dir():
                return p
        except OSError:
            pass
    for root in (Path("/sdcard"), Path("/storage/emulated/0"), Path.home()):
        try:
            if root.is_dir():
                return root
        except OSError:
            pass
    return Path.cwd()

ROOT = str(choose_root())

def safe_join(root, rel):
    rel = "" if rel is None else unquote(str(rel))
    target = Path(os.path.normpath(os.path.join(root, rel)))
    root_path = Path(root)
    if target == root_path:
        return root_path, True
    try:
        target.relative_to(root_path)
        return target, True
    except ValueError:
        return None, False

def human_size(num):
    num = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return f"{int(num)} B" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"

def unzip_into(zip_path, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename
            parts = [x for x in name.replace(chr(92), '/').split('/') if x not in ('', '.', '..')]
            if not parts:
                continue
            dest = out_dir.joinpath(*parts)
            try:
                dest.resolve().relative_to(out_dir.resolve())
            except ValueError:
                continue
            if name.endswith('/'):
                dest.mkdir(parents=True, exist_ok=True)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(dest, 'wb') as dst:
                shutil.copyfileobj(src, dst)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s\n" % (fmt % args))

    def _send_json(self, payload, code=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, text, code=200):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send_json({"ok": True})

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path = parsed.path
        
        if path == "/":
            try:
                content = PANEL_HTML.read_text(encoding="utf-8")
            except OSError:
                content = "<h1>index.html missing</h1>"
            self._send_html(content)
            return
            
        if path == "/api/info":
            self._send_json({
                "root": ROOT,
                "port": PORT,
            })
            return

        if path == "/api/stop_server":
            self._send_json({"ok": True, "message": "stopping"})
            os.kill(os.getpid(), signal.SIGTERM)
            return
            
        if path == "/api/list":
            rel = qs.get("rel", [""])[0]
            target, ok = safe_join(ROOT, rel)
            if not ok or target is None:
                self._send_error(400, "invalid path")
                return
            if not target.is_dir():
                self._send_error(404, "not a directory")
                return
                
            items = []
            try:
                entries = sorted(target.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
                for entry in entries:
                    name = entry.name
                    is_dir = entry.is_dir()
                    size = entry.stat().st_size if not is_dir else 0
                    mtime = entry.stat().st_mtime
                    items.append({
                        "name": name,
                        "path": f"{rel.rstrip('/')}/{name}" if rel and rel != "/" else name,
                        "rel": f"{rel.rstrip('/')}/{name}" if rel and rel != "/" else name,
                        "isDir": is_dir,
                        "size": size,
                        "mtime": int(mtime),
                    })
            except OSError as e:
                self._send_error(500, str(e))
                return
                
            self._send_json({"root": ROOT, "rel": rel, "items": items})
            return
            
        if path == "/api/text":
            rel = qs.get("rel", [""])[0]
            target, ok = safe_join(ROOT, rel)
            if not ok or target is None:
                self._send_error(400, "invalid path")
                return
            try:
                if not target.is_file():
                    self._send_error(400, "not a file")
                    return
                text = target.read_text(encoding="utf-8", errors="replace")[:2000000]
                self._send_json({"ok": True, "text": text})
            except Exception as e:
                self._send_error(500, str(e))
            return
            
        if path == "/api/zipdown":
            rels = qs.get("rels", [""])[0]
            name = qs.get("name", ["archive.zip"])[0] or "archive.zip"
            if not name.endswith(".zip"):
                name += ".zip"
            targets = []
            for r in [x for x in rels.split(chr(10)) if x.strip()]:
                tp, ok_t = safe_join(ROOT, r)
                if ok_t and tp is not None and tp.exists():
                    targets.append(tp)
            if not targets:
                self._send_error(400, "nothing to zip")
                return
            try:
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for tp in targets:
                        if tp.is_dir():
                            for root_dir, _dirs, files in os.walk(tp):
                                for fname in files:
                                    fp = Path(root_dir) / fname
                                    zf.write(fp, fp.relative_to(tp.parent))
                        else:
                            zf.write(tp, tp.name)
                data = buf.getvalue()
                from urllib.parse import quote
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", "attachment; filename=" + chr(34) + name + chr(34) + "; filename*=UTF-8''" + quote(name))
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self._send_error(500, str(e))
            return

        if path == "/api/file":
            rel = qs.get("rel", [""])[0]
            target, ok = safe_join(ROOT, rel)
            if not ok or target is None:
                self._send_error(400, "invalid path")
                return
            try:
                if not target.is_file():
                    self._send_error(400, "not a file")
                    return
                data = target.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", f'attachment; filename="{target.name}"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self._send_error(500, str(e))
            return

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""
        
        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except:
            data = {}
            
        if path == "/api/op":
            rel = data.get("rel", "")
            act = data.get("act", "")
            
            if act == "mkdir":
                name = data.get("name", "")
                target, ok = safe_join(ROOT, rel)
                if not ok or not name or "/" in name:
                    self._send_error(400, "invalid input")
                    return
                p = target / name
                if p.exists():
                    self._send_error(400, "already exists")
                    return
                try:
                    p.mkdir()
                    self._send_json({"ok": True, "result": name})
                except Exception as e:
                    self._send_error(500, str(e))
                    
            elif act == "newfile":
                name = data.get("name", "")
                target, ok = safe_join(ROOT, rel)
                if not ok or not name or "/" in name:
                    self._send_error(400, "invalid input")
                    return
                p = target / name
                if p.exists():
                    self._send_error(400, "already exists")
                    return
                try:
                    p.touch()
                    self._send_json({"ok": True, "result": name})
                except Exception as e:
                    self._send_error(500, str(e))
                    
            elif act == "rename":
                newname = data.get("name", "")
                target, ok = safe_join(ROOT, rel)
                if not ok or not newname:
                    self._send_error(400, "invalid input")
                    return
                dst = target.parent / newname
                if dst.exists():
                    self._send_error(400, "already exists")
                    return
                try:
                    target.rename(dst)
                    self._send_json({"ok": True, "result": newname})
                except Exception as e:
                    self._send_error(500, str(e))
                    
            elif act == "remove":
                target, ok = safe_join(ROOT, rel)
                if not ok or target == Path(ROOT) or not target.exists():
                    self._send_error(400, "cannot remove")
                    return
                try:
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                    self._send_json({"ok": True, "removed": rel})
                except Exception as e:
                    self._send_error(500, str(e))
                    
            elif act == "save":
                text = data.get("text", "")
                target, ok = safe_join(ROOT, rel)
                if not ok:
                    self._send_error(400, "invalid path")
                    return
                try:
                    target.write_text(text, encoding="utf-8")
                    self._send_json({"ok": True})
                except Exception as e:
                    self._send_error(500, str(e))
                    
            elif act == "copy_multi":
                rels = data.get("rels", []) or []
                dst = data.get("dst", "")
                dst_dir, ok2 = safe_join(ROOT, dst if dst else ".")
                if not ok2 or dst_dir is None or not dst_dir.is_dir():
                    self._send_error(400, "invalid destination")
                    return
                done, failed = 0, []
                for rel_item in rels:
                    src, ok_s = safe_join(ROOT, rel_item)
                    if not ok_s or src is None or not src.exists():
                        failed.append(rel_item)
                        continue
                    dest = dst_dir / src.name
                    n = 1
                    stem, suffix = src.name, ""
                    if src.is_file() and "." in src.name[1:]:
                        stem = src.name[: src.name.rfind(".")]
                        suffix = src.name[src.name.rfind("."):]
                    while dest.exists():
                        dest = dst_dir / ("%s (%d)%s" % (stem, n, suffix))
                        n += 1
                    try:
                        if src.is_dir():
                            shutil.copytree(src, dest)
                        else:
                            shutil.copy2(src, dest)
                        done += 1
                    except Exception:
                        failed.append(rel_item)
                self._send_json({"ok": True, "done": done, "failed": failed})

            elif act == "copy" or act == "move":
                dst = data.get("dst", "")
                target, ok = safe_join(ROOT, rel)
                dst_dir, ok2 = safe_join(ROOT, dst)
                if not ok or not ok2:
                    self._send_error(400, "invalid paths")
                    return
                dest = dst_dir / target.name
                if dest.exists():
                    self._send_error(400, "destination exists")
                    return
                try:
                    if act == "copy":
                        if target.is_dir():
                            shutil.copytree(target, dest)
                        else:
                            shutil.copy2(target, dest)
                    else:
                        shutil.move(str(target), str(dest))
                    self._send_json({"ok": True})
                except Exception as e:
                    self._send_error(500, str(e))
                    
            elif act == "unzip":
                target, ok = safe_join(ROOT, rel)
                if not ok or target is None or not target.is_file():
                    self._send_error(400, "not a file")
                    return
                lower = target.name.lower()
                if not (lower.endswith(".zip") or lower.endswith(".jar") or lower.endswith(".apk")):
                    self._send_error(400, "not a zip file")
                    return
                base = target.name
                for ext in (".zip", ".jar", ".apk"):
                    if base.lower().endswith(ext):
                        base = base[: -len(ext)]
                        break
                out_dir = target.parent / (base or "unzip")
                n = 1
                while out_dir.exists():
                    out_dir = target.parent / ("%s (%d)" % (base or "unzip", n))
                    n += 1
                try:
                    unzip_into(target, out_dir)
                    self._send_json({"ok": True, "result": out_dir.name})
                except Exception as e:
                    try:
                        if out_dir.exists():
                            shutil.rmtree(out_dir, ignore_errors=True)
                    except Exception:
                        pass
                    self._send_error(500, str(e))

            elif act == "zip":
                rels = data.get("rels", [])
                dst_rel = data.get("dst", "archive.zip")
                out_dir, ok_out = safe_join(ROOT, os.path.dirname(dst_rel) or ".")
                out_name = os.path.basename(dst_rel) or "archive.zip"
                if not ok_out or not out_name:
                    self._send_error(400, "invalid zip path")
                    return
                out_path = out_dir / out_name
                if out_path.exists():
                    self._send_error(400, "destination exists")
                    return
                try:
                    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
                        for rel_item in rels:
                            item, ok_item = safe_join(ROOT, rel_item)
                            if not ok_item or item is None:
                                continue
                            if item.is_dir():
                                for root_dir, _, files in os.walk(item):
                                    for fname in files:
                                        fp = Path(root_dir) / fname
                                        zf.write(fp, os.path.relpath(fp, item.parent) if item != Path(ROOT) else os.path.relpath(fp, item))
                            else:
                                zf.write(item, item.name)
                    self._send_json({"ok": True, "result": str(out_path)})
                except Exception as e:
                    self._send_error(500, str(e))

            else:
                self._send_error(400, "unknown action")
                
        elif path == "/api/exec":
            cmd = data.get("cmd", "")
            cwd = data.get("cwd", "") or ROOT
            timeout = data.get("timeout", 30)
            if not cmd.strip():
                self._send_error(400, "empty command")
                return
            try:
                timeout = max(1, min(int(timeout), 300))
            except Exception:
                timeout = 30
            real_cwd, ok_cwd = safe_join(ROOT, cwd)
            if not ok_cwd or real_cwd is None or not real_cwd.is_dir():
                real_cwd = Path(ROOT)
            try:
                proc = subprocess.run(
                    ["bash", "-lc", cmd],
                    cwd=str(real_cwd),
                    capture_output=True,
                    timeout=timeout,
                )
                out = proc.stdout.decode("utf-8", "replace")
                err = proc.stderr.decode("utf-8", "replace")
                self._send_json({
                    "ok": True,
                    "code": proc.returncode,
                    "stdout": out[-200000:],
                    "stderr": err[-200000:],
                    "cwd": str(real_cwd),
                })
            except subprocess.TimeoutExpired as e:
                o = (e.stdout or b"").decode("utf-8", "replace") if e.stdout else ""
                er = (e.stderr or b"").decode("utf-8", "replace") if e.stderr else ""
                self._send_json({
                    "ok": False,
                    "code": -1,
                    "stdout": o[-200000:],
                    "stderr": (er + "\n[超时 %ds 已终止]" % timeout)[-200000:],
                    "cwd": str(real_cwd),
                })
            except Exception as e:
                self._send_error(500, str(e))

        elif path == "/api/upload":
            rel_dir = data.get("rel", "")
            target, ok = safe_join(ROOT, rel_dir)
            if not ok:
                self._send_error(400, "invalid path")
                return
                
            files = data.get("files", [])
            saved = []
            for f in files:
                name = os.path.basename(f.get("name", ""))
                b64 = f.get("data", "")
                if not name or not b64:
                    continue
                try:
                    raw = base64.b64decode(b64)
                    (target / name).write_bytes(raw)
                    saved.append(name)
                except Exception as e:
                    self._send_error(500, f"upload {name} failed: {e}")
                    return
            self._send_json({"ok": True, "saved": saved})
            
        else:
            self._send_error(404, "not found")

    def _send_error(self, code, msg):
        self._send_json({"error": msg}, code)

def main():
    os.chdir(APP_ROOT)
    server = HTTPServer((HOST, PORT), Handler)
    try:
        (APP_ROOT / "logs" / "port.txt").write_text(str(PORT), encoding="utf-8")
    except OSError:
        pass
    try:
        (APP_ROOT / "logs" / "server.pid").write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass
    print(f"[shhtml] listening on http://{HOST}:{PORT}", flush=True)
    print(f"[shhtml] root={ROOT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()