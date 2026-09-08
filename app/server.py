from __future__ import annotations

import argparse
import json
import mimetypes
import os
import secrets
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from core import ForgeCore, ForgeError

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
EVE_ROOT = os.environ.get("EIF_EVE_ROOT", "/opt/unetlab")
STATE_ROOT = os.environ.get("EIF_STATE_ROOT", "/var/lib/eve-image-forge")
TOKEN_FILE = Path(os.environ.get("EIF_TOKEN_FILE", "/etc/eve-image-forge/token"))
CORE = ForgeCore(EVE_ROOT, STATE_ROOT)
VERSION_FILE = HERE.parent / "VERSION"
APP_VERSION = VERSION_FILE.read_text().strip() if VERSION_FILE.exists() else CORE.VERSION
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def load_token() -> str:
    env = os.environ.get("EIF_TOKEN")
    if env:
        return env.strip()
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    # Dev fallback only: generated per process.
    return secrets.token_hex(24)

TOKEN = load_token()


def job_worker(job_id: str, spec: dict):
    def log(msg: str):
        with JOBS_LOCK:
            JOBS[job_id]["logs"].append(msg)
            JOBS[job_id]["updated"] = time.time()
    def progress(v: int):
        with JOBS_LOCK:
            JOBS[job_id]["progress"] = int(v)
            JOBS[job_id]["updated"] = time.time()
    try:
        result = CORE.install(spec, log, progress)
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "done"
            JOBS[job_id]["result"] = result
            JOBS[job_id]["progress"] = 100
    except Exception as e:
        log(f"ERREUR: {e}")
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["error"] = str(e)


class Handler(BaseHTTPRequestHandler):
    server_version = f"EVEImageForge/{APP_VERSION}"

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def _json(self, status: int, obj: dict):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(n)

    def _json_body(self) -> dict:
        try:
            return json.loads(self._body() or b"{}")
        except Exception:
            raise ForgeError("JSON invalide")

    def _auth(self) -> bool:
        supplied = self.headers.get("X-EIF-Token", "")
        return bool(supplied) and secrets.compare_digest(supplied, TOKEN)

    def _need_auth(self) -> bool:
        if self._auth():
            return True
        self._json(401, {"error": "Jeton invalide"})
        return False

    def _static(self, name: str):
        path = (STATIC / name).resolve()
        if STATIC.resolve() not in path.parents and path != STATIC.resolve():
            return self._json(404, {"error": "not found"})
        if not path.exists() or not path.is_file():
            return self._json(404, {"error": "not found"})
        b = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/":
            return self._static("index.html")
        if p.startswith("/static/"):
            return self._static(p.removeprefix("/static/"))
        if not self._need_auth():
            return
        try:
            if p == "/api/status":
                status = CORE.system_status()
                status["version"] = APP_VERSION
                return self._json(200, status)
            if p == "/api/templates":
                return self._json(200, {"templates": CORE.discover_templates()})
            if p == "/api/installed":
                return self._json(200, {"images": CORE.installed_images()})
            if p.startswith("/api/jobs/"):
                jid = p.rsplit("/", 1)[-1]
                with JOBS_LOCK:
                    job = JOBS.get(jid)
                    if not job:
                        return self._json(404, {"error": "Job introuvable"})
                    return self._json(200, job.copy())
            return self._json(404, {"error": "not found"})
        except Exception as e:
            return self._json(500, {"error": str(e)})

    def do_PUT(self):
        p = urlparse(self.path).path
        if not self._need_auth():
            return
        try:
            if p.startswith("/api/uploads/") and p.endswith("/chunk"):
                uid = p.split("/")[3]
                offset = int(self.headers.get("X-Offset", "0"))
                data = self._body()
                new_size = CORE.append_upload(uid, offset, data)
                return self._json(200, {"received": new_size})
            return self._json(404, {"error": "not found"})
        except ForgeError as e:
            return self._json(400, {"error": str(e)})
        except Exception as e:
            return self._json(500, {"error": str(e)})

    def do_POST(self):
        p = urlparse(self.path).path
        if not self._need_auth():
            return
        try:
            if p == "/api/uploads/init":
                d = self._json_body()
                uid = secrets.token_hex(12)
                return self._json(200, CORE.prepare_upload(uid, d["filename"], int(d["size"])))
            if p.startswith("/api/uploads/") and p.endswith("/finish"):
                uid = p.split("/")[3]
                return self._json(200, CORE.finish_upload(uid))
            if p == "/api/analyze":
                d = self._json_body()
                result = CORE.analyze(d["upload_id"])
                return self._json(200, result)
            if p == "/api/install":
                spec = self._json_body()
                jid = secrets.token_hex(8)
                with JOBS_LOCK:
                    JOBS[jid] = {
                        "job_id": jid, "status": "running", "progress": 0,
                        "logs": [], "result": None, "error": None,
                        "created": time.time(), "updated": time.time(),
                    }
                threading.Thread(target=job_worker, args=(jid, spec), daemon=True).start()
                return self._json(202, {"job_id": jid})
            return self._json(404, {"error": "not found"})
        except ForgeError as e:
            return self._json(400, {"error": str(e)})
        except (KeyError, ValueError) as e:
            return self._json(400, {"error": f"Paramètre invalide: {e}"})
        except Exception as e:
            traceback.print_exc()
            return self._json(500, {"error": str(e)})


def main():
    ap = argparse.ArgumentParser(description="EVE Image Forge")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8088)
    args = ap.parse_args()
    print(f"EVE Image Forge v{APP_VERSION} Smart Import - http://{args.host}:{args.port}")
    print(f"EVE root: {EVE_ROOT}")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
