"""
Mission Control — FastAPI web server.
Serves the dashboard and proxies Hermes API.
"""
import asyncio
import json
import sqlite3
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

# ─── Metrics DB ──────────────────────────────────────────────────────────────────
_METRICS_DB = _ROOT_DIR / "metrics.db"
_metrics_conn = sqlite3.connect(str(_METRICS_DB), check_same_thread=False)
_metrics_conn.execute("""
  CREATE TABLE IF NOT EXISTS metrics (
    ts TEXT,
    metric TEXT,
    value REAL
  )
""")
# Track our own process start time
_MC_START_TS = datetime.now().isoformat()
# In-memory counters — updated by helper functions below
_cmd_count = 0
_err_count = 0
_events_received = 0

def _record(metric: str, value: float):
    _metrics_conn.execute(
      "INSERT INTO metrics (ts, metric, value) VALUES (?, ?, ?)",
      (datetime.now().isoformat(), metric, value)
    )
    _metrics_conn.commit()

def _inc_cmd():
    global _cmd_count
    _cmd_count += 1
    _record("commands", _cmd_count)

def _inc_err():
    global _err_count
    _err_count += 1
    _record("errors", _err_count)

def _inc_events():
    global _events_received
    _events_received += 1
    _record("events", _events_received)

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
_MAX_EVENT_LOG = 100  # ring buffer size
_event_log: list[dict] = []  # recent events for /api/events/recent


async def emit(event_type: str, data: dict):
    """Push an event to all SSE subscribers and append to the recent-event ring buffer."""
    entry = {"type": event_type, "data": data, "ts": datetime.now().isoformat()}
    # Ring buffer: maintain last MAX_EVENT_LOG entries (mutate in-place so _event_log stays module-scoped)
    _event_log.append(entry)
    if len(_event_log) > _MAX_EVENT_LOG:
        del _event_log[:-_MAX_EVENT_LOG]
    payload = json.dumps(entry)
    for q in _subscribers[:]:
        try:
            await q.put(payload)
        except Exception:
            pass
    # Record metrics
    _inc_events()


# ─── SSE Stream ───────────────────────────────────────────────────────────────
@app.get("/events")
async def events(request: Request):
    """Server-Sent Events stream of real-time Mission Control events."""
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.append(q)

    async def gen():
        try:
            yield {"event": "ping", "data": "keepalive"}
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=30)
                    yield {"event": "message", "data": payload}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "keepalive"}
        except GeneratorExit:
            pass
        finally:
            # Cleanup when client disconnects
            if q in _subscribers:
                _subscribers.remove(q)

    return EventSourceResponse(gen())


# ─── Panel API endpoints ──────────────────────────────────────────────────────
@app.get("/api/ping")
async def ping():
    return {"ok": True, "ts": datetime.now().isoformat()}


@app.get("/api/events/recent")
async def get_recent_events(limit: int = 50):
    """Return the last N events from the ring buffer (most recent last)."""
    return {"ok": True, "data": _event_log[-limit:]}


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
        # Emit event so the Events panel picks up briefing activity
        # (fire-and-forget — errors here must not break the briefing response)
        try:
            preview = str(data.get("morning_briefing") or "")[:120]
            asyncio.create_task(emit("briefing_loaded", {"session": data.get("session_id", ""), "preview": preview}))
        except Exception as emit_err:
            import logging
            logging.getLogger().warning(f"emit failed (non-fatal): {emit_err}")
        return {"ok": True, "data": data}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, limit: int = 8, offset: int = 0):
    """Recent messages from a specific session — click to expand a session.
    Supports pagination: ?limit=N&offset=M (offset pages through from start).
    """
    try:
        result = await hermes.get_session_messages(session_id, limit=min(limit, 20), offset=offset)
        return {"ok": True, **result, "session_id": session_id}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/sessions")
async def get_sessions(q: str = ""):
    """Active sessions across all platforms. Filter by q (searches name + message preview)."""
    try:
        sessions = await hermes.get_active_sessions(q=q)
        return {"ok": True, "data": sessions}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/paperclip/issues")
async def get_paperclip_issues(status: str = ""):
    """Paperclip issues — optionally filter by status (open,blocked,in_progress)."""
    try:
        issues = hermes.get_paperclip_issues(status=status)
        return {"ok": True, "data": issues}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/paperclip/goals")
async def get_paperclip_goals():
    """Paperclip goals."""
    try:
        goals = hermes.get_paperclip_goals()
        return {"ok": True, "data": goals}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/system-info")
async def get_system_info():
    """Server health: CPU, memory, disk, uptime."""
    try:
        info = hermes.get_system_info()
        return {"ok": True, "data": info}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/graph")
async def get_graph():
    """Knowledge Graph: force-directed entity graph from memory_store.db."""
    try:
        graph = hermes.get_knowledge_graph()
        return {"ok": True, "data": graph}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/skills-catalog")
async def get_skills_catalog():
    """Skills catalog: all available skills with triggers + descriptions."""
    try:
        catalog = hermes.get_skills_catalog()
        return {"ok": True, "data": catalog}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/metrics")
async def get_metrics(limit: int = 100):
    """Mission Control uptime and history metrics from SQLite."""
    try:
        # Get latest values for counters
        cur = _metrics_conn.execute("""
            SELECT metric, value FROM metrics
            WHERE metric IN ('commands','errors','events')
            AND ts > datetime('now','-24 hours')
            ORDER BY ts DESC
            LIMIT 300
        """)
        rows = cur.fetchall()

        # Latest snapshot per metric
        latest = {}
        for metric, value in rows:
            if metric not in latest:
                latest[metric] = value

        # Time-series for sparklines (last 24h, 1h buckets)
        cur = _metrics_conn.execute("""
            SELECT
              strftime('%Y-%m-%d %H:00', ts) as hour,
              metric,
              COUNT(*),
              MAX(value)
            FROM metrics
            WHERE ts > datetime('now', '-24 hours')
            GROUP BY hour, metric
            ORDER BY hour ASC
        """)
        ts_rows = cur.fetchall()

        # Uptime
        start = datetime.fromisoformat(_MC_START_TS)
        uptime_sec = (datetime.now() - start).total_seconds()

        return {
            "ok": True,
            "data": {
                "start_ts": _MC_START_TS,
                "uptime_sec": uptime_sec,
                "commands": latest.get("commands", _cmd_count),
                "errors": latest.get("errors", _err_count),
                "events": latest.get("events", _events_received),
                "timeseries": ts_rows,
            }
        }
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/history/search")
async def search_history(q: str = "", limit: int = 10):
    """Full-text search across conversation history using FTS5."""
    try:
        results = hermes.search_history(q, limit=min(limit, 50))
        return {"ok": True, "data": results, "query": q, "count": len(results)}
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
        _inc_cmd()
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
        _inc_err()
        return JSONResponse({"ok": False, "error": "Hermes timed out after 60s"}, status_code=504)
    except Exception as e:
        _inc_err()
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
        _inc_cmd()

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
                                parsed = json.loads(payload)
                                choices = parsed.get("choices")
                                if choices and isinstance(choices, list):
                                    delta = choices[0].get("delta", {}).get("content", "")
                                    if delta:
                                        yield {"event": "token", "data": delta}
                            except Exception:
                                pass
            except Exception as e:
                _inc_err()
                yield {"event": "error", "data": str(e)}

        return EventSourceResponse(stream_gen())
    except Exception as e:
        _inc_err()
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


# ─── Background event poller ───────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    asyncio.create_task(_poll_hermes())
    # Emit startup event so the Events panel is never empty on fresh load
    try:
        status = await hermes.get_status()
        platforms = {n: {"state": p.state, "error": p.error} for n, p in status.platforms.items()}
        await emit("mission_control_startup", {
            "version": "0.11.0",
            "platforms": platforms,
            "model": status.model,
        })
    except Exception:
        await emit("mission_control_startup", {"version": "0.11.0", "error": "could not reach Hermes"})


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
