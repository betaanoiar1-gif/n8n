from __future__ import annotations
import argparse, asyncio, json, os, base64, time
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv, set_key

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "workflow_source.json"
ENV_FILE = ROOT / ".env"
UI_DIR = Path(__file__).resolve().parent / "ui"
load_dotenv(ENV_FILE, override=True)

from .executor import Executor
from .storage import Postgres

app = FastAPI(title="YouTube Autonomous Growth OS - Python")
app.mount("/ui", StaticFiles(directory=UI_DIR, html=True), name="ui")

run_lock = asyncio.Lock()
scheduler_task: asyncio.Task | None = None
last_run = {"status": "idle", "started_at": None, "finished_at": None, "error": None}

class Settings(BaseModel):
    POSTGRES_DSN: str = ""
    WORKER_CREDENTIAL_VALUE: str = ""
    KIOS_API_KEY: str = ""
    PEXELS_API_KEY: str = ""
    PIXABAY_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    YOUTUBE_ACCESS_TOKEN: str = ""
    YOUTUBE_CLIENT_ID: str = ""
    YOUTUBE_CLIENT_SECRET: str = ""
    YOUTUBE_REFRESH_TOKEN: str = ""
    SCHEDULE_ENABLED: bool = True

SECRET_KEYS = {
    "WORKER_CREDENTIAL_VALUE", "KIOS_API_KEY", "PEXELS_API_KEY",
    "PIXABAY_API_KEY", "OPENROUTER_API_KEY", "YOUTUBE_ACCESS_TOKEN",
    "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"
}

def load_settings():
    load_dotenv(ENV_FILE, override=True)
    keys = list(Settings.model_fields.keys())
    out = {}
    for k in keys:
        if k == "SCHEDULE_ENABLED":
            out[k] = os.getenv(k, "true").lower() == "true"
        else:
            out[k] = os.getenv(k, "")
    return out

def save_settings(s: Settings):
    ENV_FILE.touch(exist_ok=True)
    data = s.model_dump()
    for k, v in data.items():
        set_key(str(ENV_FILE), k, str(v).lower() if isinstance(v, bool) else str(v))
        os.environ[k] = str(v).lower() if isinstance(v, bool) else str(v)
    load_dotenv(ENV_FILE, override=True)

async def build_executor():
    load_dotenv(ENV_FILE, override=True)
    dsn = os.getenv("POSTGRES_DSN")
    if not dsn:
        raise RuntimeError("PostgreSQL connection is not configured.")
    db = Postgres(dsn)
    await db.connect()
    return Executor(json.loads(WORKFLOW.read_text(encoding="utf-8")), db), db

async def run_once(trigger="manual", body=None):
    global last_run
    async with run_lock:
        last_run = {"status": "running", "started_at": time.time(), "finished_at": None, "error": None}
        ex = db = None
        try:
            ex, db = await build_executor()
            result = await ex.run(
                {"manual": "Manual Start", "scheduled": "Every 15 Minutes"}[trigger],
                {"json": {"trigger": trigger, "input": body or {"mode": "full_cycle"}}},
            )
            last_run["status"] = "completed"
            last_run["finished_at"] = time.time()
            return result
        except Exception as exc:
            last_run["status"] = "error"
            last_run["error"] = str(exc)
            last_run["finished_at"] = time.time()
            raise
        finally:
            if db:
                await db.close()

def auth(token):
    expected = os.getenv("WORKER_CREDENTIAL_VALUE")
    if expected and token != expected:
        raise HTTPException(401, "Invalid worker credential")

async def scheduler_loop():
    while True:
        try:
            await asyncio.sleep(900)
            load_dotenv(ENV_FILE, override=True)
            if os.getenv("SCHEDULE_ENABLED", "true").lower() != "true":
                continue
            await run_once("scheduled")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print("[scheduler]", exc)
        await asyncio.sleep(900)

@app.on_event("startup")
async def startup():
    global scheduler_task
    if scheduler_task is None or scheduler_task.done():
        scheduler_task = asyncio.create_task(scheduler_loop())

@app.on_event("shutdown")
async def shutdown():
    global scheduler_task
    if scheduler_task and not scheduler_task.done():
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass

@app.get("/")
async def root():
    return JSONResponse({"name": app.title, "ui": "/ui/"})

@app.get("/api/status")
async def status():
    settings = load_settings()
    return {
        "status": last_run,
        "scheduler_enabled": settings["SCHEDULE_ENABLED"],
        "interval_seconds": 900,
        "workflow_nodes": len(json.loads(WORKFLOW.read_text(encoding="utf-8"))["nodes"]),
        "configured": bool(settings["POSTGRES_DSN"]),
    }

@app.get("/api/settings")
async def get_settings():
    s = load_settings()
    for k in SECRET_KEYS:
        if s[k]:
            s[k] = "••••••••"
    return s

@app.post("/api/settings")
async def update_settings(settings: Settings):
    current = load_settings()
    data = settings.model_dump()
    for k in SECRET_KEYS:
        if data[k] == "••••••••":
            data[k] = current[k]
    save_settings(Settings(**data))
    return {"ok": True}

@app.post("/api/run")
async def api_run(payload: dict | None = None):
    try:
        result = await run_once("manual", payload or {"mode": "full_cycle"})
        return {"ok": True, "result": result or {"status": "completed"}}
    except Exception as exc:
        raise HTTPException(500, str(exc))

@app.post("/api/scheduler")
async def scheduler_control(payload: dict):
    enabled = bool(payload.get("enabled", True))
    s = load_settings()
    s["SCHEDULE_ENABLED"] = enabled
    save_settings(Settings(**s))
    return {"ok": True, "enabled": enabled}

@app.post("/webhook/youtube-autonomous-growth-os")
async def control(payload: dict, x_worker_key: str | None = Header(default=None)):
    auth(x_worker_key)
    ex, db = await build_executor()
    try:
        return JSONResponse(content=await ex.run("Authenticated Control Webhook", {"json": {"body": payload}}) or {"accepted": True})
    finally:
        await db.close()

@app.post("/webhook/youtube-growth-os-v2/worker-bundle")
async def bundle(x_worker_key: str | None = Header(default=None)):
    auth(x_worker_key)
    ex, db = await build_executor()
    try:
        out = await ex.run("Authenticated Worker Bundle Download", {"json": {"headers": {"x-worker-key": x_worker_key}}})
        if not out:
            raise HTTPException(404, "Worker bundle was not produced")
        binary = out.get("binary", {}).get("data", {}) if isinstance(out, dict) else {}
        data = base64.b64decode(binary["data"]) if binary.get("data") else None
        if not data:
            raise HTTPException(500, "Worker bundle binary missing")
        return Response(data, media_type=binary.get("mimeType", "application/zip"),
                        headers={"Content-Disposition": f'attachment; filename="{binary.get("fileName", "growth_os_v2_local_worker.zip")}"'})
    finally:
        await db.close()

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--schedule", action="store_true")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8443)
    ap.add_argument("--mode", default="full_cycle")
    ap.add_argument("--action", default="run")
    ap.add_argument("--job-id")
    ap.add_argument("--actor")
    a = ap.parse_args()
    if a.run:
        r = await run_once("manual", {"mode": a.mode, "action": a.action, "job_id": a.job_id, "actor": a.actor})
        print(json.dumps(r or {"status": "completed"}, ensure_ascii=False, indent=2, default=str))
        return
    if a.schedule:
        await scheduler_loop()
        return
    await uvicorn.Server(uvicorn.Config(app, host=a.host, port=a.port, log_level="info")).serve()

if __name__ == "__main__":
    asyncio.run(main())
