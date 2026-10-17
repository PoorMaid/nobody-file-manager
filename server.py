#!/usr/bin/env python3
import json
import os
import signal
import sys
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs, unquote
from pathlib import Path
import base64
import shutil

BASE_DIR = Path(__file__).resolve().parent
PANEL_HTML = BASE_DIR / "index.html"
PORT = int(os.environ.get("SHHTML_PORT", "8080"))
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
    os.chdir(BASE_DIR)
    server = HTTPServer((HOST, PORT), Handler)
    print(f"[shhtml] listening on http://{HOST}:{PORT}", flush=True)
    print(f"[shhtml] root={ROOT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()