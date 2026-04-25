"""
Mission Control — FastAPI web server.
Serves the dashboard and proxies Hermes API.
"""
import asyncio
import json
import time
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
import httpx

from adaptor.hermes import HermesAdaptor

# Load config — resolve relative to this file's directory, so it works from any cwd
_SERVICE_DIR = Path(__file__).parent
_ROOT_DIR = _SERVICE_DIR.parent
CONFIG = json.loads((_ROOT_DIR / "config" / "settings.json").read_text())
PORT = CONFIG.get("mission_control_port", 8420)
HERMES_BASE = CONFIG.get("hermes_api_base", "http://127.0.0.1:9119")
LOG_LEVEL = CONFIG.get("log_level", "info")

app = FastAPI(title="Mission Control", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Lock down to local network in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

hermes = HermesAdaptor(api_base=HERMES_BASE)

# ─── In-memory event store for SSE ───────────────────────────────────────────
_event_queue: asyncio.Queue = asyncio.Queue()
_subscribers: list[asyncio.Queue] = []


async def emit(event_type: str, data: dict):
    """Push an event to all SSE subscribers."""
    payload = json.dumps({"type": event_type, "data": data, "ts": datetime.now().isoformat()})
    for q in _subscribers[:]:
        try:
            await q.put(payload)
        except Exception:
            pass


# ─── SSE Stream ───────────────────────────────────────────────────────────────
@app.get("/events")
async def events(request: Request):
    """Server-Sent Events stream of real-time Mission Control events."""
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.append(q)

    async def gen():
        yield {"event": "ping", "data": "keepalive"}
        while True:
            try:
                payload = await asyncio.wait_for(q.get(), timeout=30)
                yield {"event": "message", "data": payload}
            except asyncio.TimeoutError:
                yield {"event": "ping", "data": "keepalive"}
            except GeneratorExit:
                break

    async def cleanup():
        _subscribers.remove(q)

    request.add_event_callback(cleanup)
    return EventSourceResponse(gen())


# ─── Panel API endpoints ──────────────────────────────────────────────────────
@app.get("/api/ping")
async def ping():
    return {"ok": True, "ts": datetime.now().isoformat()}


@app.get("/api/status")
async def get_status():
    """System status panel: Hermes gateway + all platforms."""
    try:
        status = await hermes.get_status()
        # Enrich with Hermes version from CLI (cached, 5-min TTL)
        try:
            ver = await hermes.get_hermes_version()
        except Exception:
            ver = {"version": "unknown", "release_date": "unknown"}
        return {
            "ok": True,
            "data": {
                "version": ver.get("version", "unknown"),
                "release_date": ver.get("release_date", "unknown"),
                "hermes_home": status.hermes_home,
                "gateway_running": status.gateway_running,
                "gateway_pid": status.gateway_pid,
                "gateway_state": status.gateway_state,
                "model": status.model,
                "model_provider": status.model_provider,
                "platforms": {
                    name: {"state": p.state, "error": p.error}
                    for name, p in status.platforms.items()
                },
                "checked_at": status.checked_at,
            }
        }
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/cron-jobs")
async def get_crons():
    """Cron jobs panel."""
    try:
        jobs = await hermes.get_cron_jobs()
        return {
            "ok": True,
            "data": [job.__dict__ for job in jobs]
        }
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/context")
async def get_context():
    """Hermes Brain Dump: full context snapshot."""
    try:
        ctx = await hermes.get_full_context()
        # Trim large fields for the panel
        for job in ctx.get("cron_jobs", []):
            job["prompt_preview"] = job["prompt_preview"][:200]
        return {"ok": True, "data": ctx}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/toolsets")
async def get_toolsets():
    """Toolsets status."""
    try:
        toolsets = await hermes.get_toolsets()
        return {"ok": True, "data": toolsets}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/briefing")
async def get_briefing():
    """Morning briefing: recent conversations, pending crons, latest briefing output."""
    try:
        data = await hermes.get_briefing()
        return {"ok": True, "data": data}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/sessions")
async def get_sessions():
    """Active sessions across all platforms."""
    try:
        sessions = await hermes.get_active_sessions()
        return {"ok": True, "data": sessions}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/skills")
async def get_skills():
    try:
        skills = await hermes.get_skills()
        return {"ok": True, "data": skills}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/api/cron-jobs/{job_id}/trigger")
async def trigger_cron(job_id: str):
    """Trigger an immediate cron job run."""
    try:
        result = await hermes.trigger_cron_run(job_id)
        await emit("cron_triggered", {"job_id": job_id})
        return {"ok": True, "data": result}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/api/command")
async def post_command(request: Request):
    """
    Command bar: accepts a text prompt, returns Hermes response via OpenAI-compatible API.
    """
    try:
        body = await request.json()
        prompt = body.get("prompt", "").strip()
        if not prompt:
            return {"ok": False, "error": "empty prompt"}

        # Call Hermes via OpenAI-compatible API
        result = await hermes.ask(prompt, stream=False)
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        await emit("command_executed", {"prompt": prompt[:80]})
        return {
            "ok": True,
            "data": {
                "prompt": prompt,
                "response": content,
                "model": result.get("model", "hermes-agent"),
                "usage": result.get("usage", {}),
            }
        }
    except httpx.TimeoutException:
        return JSONResponse({"ok": False, "error": "Hermes timed out after 60s"}, status_code=504)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/api/command/stream")
async def post_command_stream(request: Request):
    """
    Streaming version: SSE stream yielding Hermes response tokens as they arrive.
    Events: token (delta content), done, error
    """
    try:
        body = await request.json()
        prompt = body.get("prompt", "").strip()
        if not prompt:
            return JSONResponse({"ok": False, "error": "empty prompt"}, status_code=400)

        await emit("command_executed", {"prompt": prompt[:80]})

        async def stream_gen():
            try:
                buffer = ""
                async for line in await hermes.ask(prompt, stream=True):
                    # SSE events end with \n\n — accumulate until we have a full event
                    buffer += line + "\n"
                    while "\n\n" in buffer:
                        event, buffer = buffer.split("\n\n", 1)
                        if event.startswith("data: "):
                            payload = event[6:].strip()
                            if payload == "[DONE]":
                                yield {"event": "done", "data": ""}
                                return
                            try:
                                import json
                                parsed = json.loads(payload)
                                delta = (
                                    parsed.get("choices", [{}])
                                    .get(0, {})
                                    .get("delta", {})
                                    .get("content", "")
                                )
                                if delta:
                                    yield {"event": "token", "data": delta}
                            except Exception:
                                pass
            except Exception as e:
                yield {"event": "error", "data": str(e)}

        return EventSourceResponse(stream_gen())
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ─── Background event poller ───────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    asyncio.create_task(_poll_hermes())


async def _poll_hermes():
    """Poll Hermes status every 30s and emit change events."""
    last_state: dict = {}
    while True:
        try:
            status = await hermes.get_status()
            state = {name: p.state for name, p in status.platforms.items()}
            if state != last_state and last_state:
                changed = {k: v for k, v in state.items() if last_state.get(k) != v}
                await emit("platform_change", {
                    "changed_platforms": changed,
                    "full_state": state
                })
            last_state = state
        except Exception as e:
            await emit("error", {"source": "poller", "msg": str(e)})
        await asyncio.sleep(30)


# ─── Dashboard UI ──────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the single-page Mission Control dashboard."""
    html = (_ROOT_DIR / "service" / "templates" / "index.html").read_text()
    return HTMLResponse(content=html)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level=LOG_LEVEL)
