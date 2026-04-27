# Mission Control — AI OS Plan

## What Are We Building
A unified AI OS dashboard that sits on top of Hermes Agent as its "core" — think Bloomberg Terminal meets Raycast meets NASA Mission Control. One interface to see everything that matters, trigger any action, and get AI-assisted synthesis of your entire digital life.

**Core Thesis:** Hermes is already the nervous system of Aaron's digital life (Telegram, Discord, GitHub, Paperclip, homelab, fitness). This project makes that intelligence **visible, navigable, and interactive** through a persistent web dashboard — not just chat.

---

## Reference Architecture (What Others Built)

| Project | What They Did Right | What We're Taking |
|---|---|---|
| **Raycast** | Command palette + extensibility + AI native | Fast command execution, keyboard-first UX |
| **Linear** | Dense info, keyboard nav, beautiful states | Clean data hierarchy, context-awareness |
| **Home Assistant** | Entity-level control, real-time state | Live sensor feeds, automation triggers |
| **NASA Mission Control** | Multi-panel live data, alert prioritization | Status tiers, criticality coloring |
| **Arc Browser** | Spaces/contexts, split views | Tab/grouped contexts |
| **Bloomberg Terminal** | Dense keyboard-driven, all-data-all-the-time | Information density, hotkeys |

---

## MVP Scope (Ship First)

### Layer 0 — The Hermes Adaptor
The foundation. A Python class that exposes Hermes capabilities as a clean API:
- `HermesAdaptor.ask(prompt)` — stateless prompt → response
- `HermesAdaptor.get_status()` — what's online, what's not
- `HermesAdaptor.trigger_action(tool, params)` — execute a tool
- `HermesAdaptor.subscribe_events()` — SSE stream of what's happening
- `HermesAdaptor.get_context()` — recent conversation, active projects

### Layer 1 — Mission Control Web UI
Single-page dashboard (no page reloads). Served by FastAPI + uvicorn as systemd service.

**MVP Panels:**
1. **System Status Bar** — All connected platforms: Telegram ✓ Discord ✓ API Server ✓. Color-coded.
2. **Live Activity Feed** — Real-time stream of events: messages received, cron jobs firing, GitHub activity, homelab alerts
3. **Quick Command Bar** — Raycast-style: type anything, get AI-completed, execute
4. **Hermes Brain Dump** — See what Hermes "knows" right now: current context, active threads, recent learnings
5. **Action Buttons** — One-click versions of common actions (send telegram, trigger GitHub PR, run health check)

### Layer 2 — Deployment (Survives Reboots)
- Python FastAPI app running under systemd service
- `mission-control.service` — auto-starts on boot, auto-restarts on crash
- Runs on port 8420 (configurable)
- No Docker dependency
- Nginx reverse proxy (optional, if wanting HTTPS)

---

## v2 Features (After MVP)

### Information Architecture
- **Context Spaces** — Group panels by project/context (Work, Homelab, Personal, Fitness). Switch spaces like desktop spaces.
- **Memory Graph** — Visualize what Hermes knows about entities (people, projects, topics) as a force-directed graph
- **Undo/History Timeline** — Every action Hermes took, reversible

### Intelligence Layer
- **Morning Briefing Auto-Synth** — When you open dashboard, see a GPT-generated summary of your day: PENDING items, calendar, emails, homelab health
- **Anomaly Detection** — Something unusual: homelab offline, unusual GitHub activity, missed messages — highlighted in red/amber
- **Predictive Alerts** — "Disk at 78%,预计 14 days full" style warnings

### Interactivity
- **Drag-and-Drop Panels** — Customize your layout, persist to config
- **Keyboard Nav** — `/` opens command bar, `j/k` navigate lists, `esc` closes modals
- **Voice Input** — Click-to-talk into Hermes (Web Speech API → Hermes)
- **Context Menus** — Right-click on anything for related actions

### Integrations
- **GitHub PR Queue** — See all open PRs across repos, review status, merge with one click
- **Paperclip Issue Board** — Kanban view of all agent issues
- **Fitness Dashboard** — Weekly volume, nutrition compliance, streak tracking
- **Homelab Deep Dive** — Docker containers, NixOS services, network topology
- **Calendar Widget** — Today's meetings, tomorrow's reminders
- **Email Preview** — Last 5 emails, mark read/archived

---

## v3 Features (Sick Differentiators)

- **Spatial Layout** — Arrange panels like a real Mission Control. Resize, overlap, fullscreen individual panels.
- **Multi-Agent View** — See all Paperclip agents as "stations" — what is each one doing right now?
- **Time Machine** — "What was my homelab status 3 days ago?" — replay historical states
- **Custom Widget SDK** — Write a widget in 20 lines of Python, drops into dashboard
- **Hermes -> External Webhooks** — Dashboard can trigger external automations, not just internal tools

---

## Tech Stack

| Component | Choice | Why |
|---|---|---|
| Backend | FastAPI + uvicorn | Async native, clean REST + SSE |
| Frontend | Vanilla JS + HTMX | Zero build step, reactive, tiny footprint |
| Real-time | Server-Sent Events (SSE) | Simpler than WebSocket for one-way stream |
| Persistence | SQLite | Zero config, survives reboots, sufficient for config/state |
| Deployment | systemd service | Built into OS, survives reboot, supervisor handles crash loop |
| HTTP Client | httpx | Async, Hermes API calls |
| Auth | None for MVP (local network) | Can add BasicAuth or session token later |

---

## File Structure

```
/home/localadmin/mission-control/
├── adaptor/
│   ├── __init__.py
│   └── hermes.py          # HermesAdaptor class
├── service/
│   ├── __init__.py
│   ├── web.py             # FastAPI app
│   ├── panels/
│   │   ├── __init__.py
│   │   ├── status.py      # System status panel
│   │   ├── feed.py        # Activity feed panel
│   │   ├── command.py     # Command bar
│   │   └── context.py     # Hermes brain dump
│   └── templates/
│       └── index.html     # Single-page dashboard
├── config/
│   └── settings.json       # Port,赫尔墨斯API地址等
├── run.py                  # Entry point
├── requirements.txt
└── mission-control.service # systemd unit
```

---

## Implementation Order

1. **HermesAdaptor class** — validate it can actually talk to Hermes API
2. **FastAPI skeleton** — endpoints for: `/status`, `/events` (SSE), `/command`, `/context`
3. **Systemd service** — install, enable, verify it survives reboot
4. **Basic HTML dashboard** — panels rendering from API calls
5. **SSE feed** — real-time activity stream
6. **Command bar** — type → Hermes ask → response
7. **Then iterate on v2 features based on what feels right**

---

## Implementation Status

### ✅ Layer 0 — HermesAdaptor (COMPLETE — rewritten)
- **File:** `adaptor/hermes.py`
- **Architecture change:** Hermes dropped the REST API server (port 9119) in a recent version. Rewritten to use:
  - `GET /health/detailed` on port 8642 for gateway/platform status
  - `~/.hermes/cron/jobs.json` (local file read) for cron jobs — no auth needed
  - `POST /v1/chat/completions` on port 8642 for `ask()` / command execution
- **Works for:** `get_status()`, `get_cron_jobs()`, `get_full_context()`, `ask()`, `ask_stream()`
- **Config:** `config/settings.json` `hermes_api_base` updated to `http://127.0.0.1:8642`
- **Status:** All 3 platforms visible: telegram ✅, discord ✅, api_server ✅

### ✅ Layer 1 — FastAPI Service (COMPLETE)
- **File:** `service/web.py`
- **Endpoints:** `GET /api/ping`, `GET /api/status`, `GET /api/cron-jobs`, `GET /api/context`, `GET /api/toolsets`, `GET /api/skills`, `POST /api/command`, `POST /api/cron-jobs/{job_id}/trigger`, `GET /events` (SSE), `GET /` (dashboard)
- **Running on:** port 8420
- **SSE stream:** Live events with keepalive pings + platform change events
- **Background poller:** Polls Hermes every 30s, emits change events to SSE subscribers
- **v2 added:** `/api/cron-jobs/{job_id}/trigger` — triggers immediate cron run

### ✅ Layer 1 — Dashboard UI (COMPLETE)
- **File:** `service/templates/index.html`
- **Panels:** System Status Bar (platforms), Live Activity Feed (SSE), Command Bar, Hermes Brain (gateway/model/cron jobs)
- **Style:** Dark NASA Mission Control theme, no build step, vanilla JS
- **v2 added:** Command bar calls Hermes (real AI responses), cron job "▶ Run now" buttons

### ✅ Layer 2 — systemd Service (COMPLETE)
- **File:** `mission-control.service`
- **Installed to:** `/etc/systemd/system/mission-control.service`
- **Status:** `systemctl enable mission-control` — survives reboots
- **Auto-restart:** on crash (Restart=always, RestartSec=5)
- **Python venv:** `/home/localadmin/mission-control/venv`

### File Structure (as-built)
```
/home/localadmin/mission-control/
├── adaptor/
│   ├── __init__.py
│   └── hermes.py          ✅ HermesAdaptor class + ask() via port 8642
├── service/
│   ├── __init__.py
│   ├── web.py             ✅ FastAPI app + cron trigger endpoint
│   ├── panels/
│   │   └── __init__.py
│   └── templates/
│       └── index.html     ✅ Dashboard UI (command bar + cron run buttons)
├── config/
│   └── settings.json
├── run.py                 ✅ Entry point
├── requirements.txt
└── mission-control.service ✅ systemd unit
```

---

## Session Log — 2026-04-27 23:00 UTC

### Changes Made

**1. Streaming Performance — chunk_size 128→512 (perf)**

`adaptor/hermes.py` `_stream_lines()`: `aiter_bytes(chunk_size=128)` → `chunk_size=512`.
Each network read now delivers 4x more data per iteration, reducing the number of buffer-assembly cycles needed for SSE event delivery. No changes to SSE parsing logic.

**2. Committed Pending Fixes from Prior Session**

- `adaptor/hermes.py`: Hermes CLI cron commands renamed (`cron update` → `cron edit`, `cron delete` → `cron remove`, schedule/prompt as positional args)
- `service/templates/index.html`: closed missing `}` on Graph class
- `PLAN.md`: prior session log entry

**3. Service Restart**

Service restarted cleanly after the adaptor change. All endpoints healthy.

### Current State
- Service running on port 8420 via systemd ✅ (PID 199193, fresh restart)
- Git committed: `a38b922` ✅
- All API endpoints healthy ✅
- Streaming chunk_size now 512 ✅

### No Blockers

### Next Sprint Candidates
1. **GitHub PR workflow** — blocked on GitHub auth credentials (no GH_TOKEN, no GitHub in auth.json)
2. **Memory graph type coloring** — Hermes entity store too sparse (all "unknown" type)
3. **Homelab network fix** — all hosts unreachable (10.87.1.0/24 no route), not a code issue

---

## Session Log — 2026-04-27 21:56 UTC

### Changes Made

**systemd Service — Orphaned Process Kill on Start (FIX)**

Problem: Port 8420 conflict crash loop — `address already in use` errors cycling every 5 seconds with restart counter climbing past 620. Orphaned Python process from a previous session was holding the port.

Root cause: `run.py` was manually started outside of systemd in a prior debug session. When systemd tried to restart the service it couldn't acquire the port.

Fix: Added `ExecStartPre=/bin/sh -c 'fuser -k 8420/tcp 2>/dev/null; exit 0'` to the service file. This runs before every start attempt and kills any process holding port 8420. Service now starts cleanly regardless of orphaned processes.

Note: `mission-control.service` is gitignored (deployed separately from repo). This fix only applies to the deployed service.

### Current State
- Service running on port 8420 via systemd ✅ (PID 187846, ~5min uptime)
- All 6 API endpoints verified healthy ✅
- Service restart counter reset to 0 ✅
- Git working tree clean (service file not in git) ✅

### No Blockers

### Next Sprint Candidates
1. **GitHub PR workflow** — blocked on GitHub auth credentials (no GH_TOKEN, no GitHub in auth.json)
2. **Memory graph type coloring** — Hermes entity store too sparse (all "unknown" type)
3. **Streaming performance** — chunk_size=128, could try 256 or 512 for faster token delivery
4. **Homelab network fix** — all hosts unreachable (10.87.1.0/24 no route), not a code issue

---

## Session Log — 2026-04-27 20:45 UTC

### Changes Made

**Token Tracking in Metrics Panel (NEW)**

Problem: Metrics panel showed commands and errors as zeros even after the service had been running for hours. No token usage tracking existed at all — the most important signal for understanding AI consumption was missing.

Fix — 3-part implementation:

1. **Backend `service/web.py`**: Added `_record_tokens(usage)` function that extracts `prompt_tokens` and `completion_tokens` from OpenAI-style usage dicts and records cumulative totals to the SQLite metrics DB. Wired into both `/api/command` (sync) and `/api/command/stream` (streaming, captures usage from the final SSE chunk that arrives with `finish_reason=stop`). Updated `/api/metrics` to return `token_in` and `token_out` fields.

2. **Frontend `service/templates/index.html`**: Added two new metric cards (TOKEN IN cyan, TOKEN OUT amber) in the Metrics panel grid. `loadMetrics()` now reads `token_in`/`token_out` from the API and renders them with locale-formatted counts and `/hr` rate.

3. **Verified end-to-end**: POST `/api/command` with "ping" → Hermes returns `prompt_tokens: 20704, completion_tokens: 11` → `/api/metrics` shows `token_in: 20704.0, token_out: 11.0` ✓

### Current State
- Service running on port 8420 via systemd ✅ (PID 180811, ~5min uptime)
- Git committed: `440adfc` ✅
- All 9 API endpoints verified healthy ✅
- Token tracking live: 20,704 prompt tokens recorded from one test command ✅

### No Blockers

### Next Sprint Candidates
1. **GitHub PR workflow** — blocked on GitHub auth credentials (no GH_TOKEN, no GitHub in auth.json)
2. **Memory graph type coloring** — Hermes entity store too sparse (all "unknown" type)
3. **Streaming performance** — increase `chunk_size=1` to ~64 for faster token delivery
4. **Homelab network fix** — all hosts unreachable (10.87.1.0/24 no route), not a code issue

---

## Session Log — 2026-04-27 20:35 UTC

### Changes Made

**Cron Jobs Panel — Show `last_error` + `prompt_preview` (NEW)**

Problem: When a cron job failed, the Cron Jobs panel showed `error` status but no details — you couldn't see what went wrong without digging into logs.

Fix:
- Cron rows now display `last_error` text inline (red, &#9888; warning icon, truncated 80 chars) when `last_status === 'error'`
- Cron name title tooltip expanded to show `prompt_preview` on hover — see what the cron actually does before running it
- API already returned `last_error` and `prompt_preview` — frontend just wasn't rendering them

### Current State
- Service running on port 8420 via systemd ✅ (PID 170024, ~2h uptime)
- Git committed: `d488b5e` ✅
- All API endpoints healthy ✅

### No Blockers

### Next Sprint Candidates
1. **GitHub PR workflow** — blocked on GitHub auth credentials (no GH_TOKEN, no GitHub in auth.json)
2. **Memory graph type coloring** — Hermes entity store too sparse (all "unknown" type)
3. **Homelab network fix** — all 10.87.1.0/24 hosts unreachable from server, not a code issue

---

## Session Log — 2026-04-27 18:30 UTC

### Changes Made

**Session Search (NEW)**

Sessions panel had no search — you had to scroll through the list to find a session.

Fix: live search bar added to Sessions panel header (right-aligned in the panel title row).

Backend (`adaptor/hermes.py` + `service/web.py`):
- `GET /api/sessions?q=term` — filters by name match OR first user message content match
- `HermesAdaptor.get_active_sessions(q)` — reads session files, extracts first user message as `msg_preview` for content search
- Returns up to 20 results when searching (10 when browsing recent)

Frontend (`service/templates/index.html`):
- Sessions panel header: `<input id="sessions-search">` inline with title, right-aligned via `margin-left:auto`
- `loadSessions()` reads search input, debounces 300ms, calls `/api/sessions?q=…`
- When search is active: shows `msg_preview` snippet (first 120 chars) under each row
- Escape key clears the search and restores normal session list
- Gauge shows `—` when search returns 0 (instead of `0`)

### Current State
- Service running on port 8420 via systemd ✅ (PID 170024, fresh restart)
- Git committed: `1298357` ✅
- `/api/sessions` returns 6 recent sessions ✅
- `/api/sessions?q=telegram` returns 5 matching sessions ✅
- `/api/sessions?q=homelab` returns 0 (correct — not in first user message) ✅

### No Blockers

### Next Sprint Candidates
1. **GitHub PR workflow** — blocked on GitHub auth credentials (no GH_TOKEN, no GitHub in auth.json)
2. **Memory graph type coloring** — Hermes entity store too sparse (all "unknown" type)
3. **Homelab network fix** — all 10.87.1.0/24 hosts unreachable from server, not a code issue

---

## Session Log — 2026-04-27 17:24 UTC

### Changes Made

**Events Panel — Live Event Emissions (NEW)**

Problem: Events panel was always empty after service restart because `_event_log` is in-memory and the poller only emits on *change*.

Fix: Two new event emission points added:

1. **Startup event** — `startup()` now emits `mission_control_startup` on boot with current platform states (telegram, discord, api_server) + Hermes version. Events panel is never empty on load.

2. **Briefing event** — `get_briefing()` now emits `briefing_loaded` every time the briefing API is called (polled every 30s by the dashboard). Shows first 120 chars of briefing content.

Frontend rendering added for both:
- `briefing_loaded` → purple badge
- `mission_control_startup` → cyan badge

**Bug fixed:** `morning_briefing` returned from `get_briefing()` is a dict, not a string. Added `str()` wrapper before slicing to prevent `TypeError: unhashable type: 'slice'`.

**Bug fixed:** `emit()` call wrapped in try/except so event emission failures never break the briefing API response.

### Current State
- Service running on port 8420 via systemd ✅ (PID fresh restart)
- Git committed: `468e6a8` ✅
- All 9 API endpoints verified ✅
- Events panel now shows startup + briefing events live ✅

### No Blockers

### Next Sprint Candidates
1. **GitHub PR workflow** — blocked on GitHub auth credentials (no GH_TOKEN, no GitHub in auth.json)
2. **Memory graph type coloring** — Hermes entity store too sparse (all "unknown" type)
3. **Morning briefing quality** — content already improved; formatting solid
4. **Homelab network fix** — all hosts unreachable (10.87.1.0/24 no route), not a code issue

---

## Session Log — 2026-04-27 08:05 UTC

### Root Cause: Port 8420 Conflict on Restart

**Problem:** Service was stuck in `activating (auto-restart)` crash loop — bind error `Errno 98: address already in use`.

**Root cause (Phase 1):**
1. Old `run.py` process (PID 157437) from a previous session was still holding port 8420
2. `systemctl restart` couldn't kill it (no interactive auth available in cron context)
3. `fuser -k 8420/tcp` successfully killed the orphaned process (PID 161659 was the actual holder when checked via `fuser 8420/tcp`)
4. Service resumed normally after port freed

**Fix:** Used `fuser -k 8420/tcp` to free the port, then `systemctl --user restart mission-control` to bring service back up.

**Prevention:** The service file has `Restart=always` which is correct. The orphan process likely survived from a manual debug session before the last scheduled cron run.

### Current State
- Service running on port 8420 via systemd ✅ (PID 161699, fresh restart)
- Git working tree clean ✅
- All platforms: telegram ✅, discord ✅, api_server ✅

### No Blockers

### Next Sprint Candidates
1. **GitHub PR workflow** — blocked on GitHub auth credentials (no GH_TOKEN, no GitHub in auth.json)
2. **Memory graph type coloring** — Hermes entity store too sparse (all "unknown" type)
3. **Homelab network fix** — all 10.87.1.0/24 hosts unreachable from server, not a code issue

---

## Session Log — 2026-04-27 15:05 UTC

### Changes Made

**1. Briefing Fix — Scan Window Widened (ROOT CAUSE)**

Root cause investigation (Phase 1): `morning_briefing` returned `null`.
- Morning briefing runs at 21:00 UTC, sits at position 125 out of 345 total cron sessions
- Heavy cron churn: Maxi Heartbeat every 15min (~64/day), mission-control-iterate hourly (~17/day)
- `[:120]` scan window was 5 slots too narrow — briefing at position 125 was excluded
- Fix: widened scan from 120 → 300, updated comment with churn rate math

**2. Quick Links Tab (NEW)**

- New **Links** tab in right column tab bar — 7th tab
- 6 one-click shortcut cards in a 2-column grid:
  - GitHub (this-bytes/mission-control)
  - GitHub PRs (pull requests queue)
  - Google Workspace (admin console)
  - Paperclip (issue tracker at 10.87.1.201:3100)
  - Homelab (gateway at 10.87.1.1)
  - Hermes API (localhost:8642)
- Each card: name + description + live UP/DOWN status via async `fetch` HEAD with 2s timeout
- Cards styled with Mission Control dark theme, cyan hover border
- No backend changes needed

### Current State
- Service running on port 8420 via systemd ✅ (PID fresh restart, ~3h30min uptime)
- Git committed + pushed: `23ce057` ✅
- All endpoints verified ✅
- Briefing: correctly finds morning briefing at position 125 ✅

### No Blockers

### Next Sprint Candidates
1. **GitHub PR workflow** — blocked on GitHub auth credentials (no GH_TOKEN, no GitHub in auth.json)
2. **Memory graph type coloring** — Hermes entity store too sparse (all "unknown" type)
3. **Homelab network fix** — all 10.87.1.0/24 hosts unreachable from server, not a code issue

## Session Log — 2026-04-27 13:50 UTC

### Changes Made

**Briefing Regenerate — Proper Polling + Timeout Feedback (NEW)**
- Previously: clicked regenerate → "Regenerating..." → single 3s setTimeout → loadBriefing (often showed old briefing or nothing)
- Now: button shows `...` + amber color while running; content shows `Regenerating... 57s`, `Regenerating... 54s`, etc. countdown every 3s
- Polls `/api/briefing` every 3s, stops when new briefing detected OR after 15s (accepts whatever Hermes has produced)
- Hard timeout at 60s: shows `Timed out — check Hermes logs` in red
- Button state always restored on completion/timeout/error

### Current State
- Service running on port 8420 via systemd ✅
- Git committed + pushed: `5c77967` ✅
- All 9 API endpoints verified ✅

### No Blockers

### Next Sprint Candidates
1. **GitHub PR workflow** — blocked on GitHub auth credentials (no GH_TOKEN, no GitHub in auth.json)
2. **Memory graph type coloring** — Hermes entity store too sparse (all "unknown" type)
3. **Morning briefing quality** — content correct; formatting already improved

---

## Session Log — 2026-04-27 13:45 UTC

### Changes Made

**Knowledge Graph UX Improvements (NEW)**

1. **Hover tooltip** — floating label appears near cursor on node hover showing entity name + type. Cyan border, dark background, JetBrains Mono font.

2. **Focus dimming** — click a node to enter "focus mode": directly-connected nodes stay bright, all other nodes dim to near-invisible (5% opacity). Edges to the focused node highlight at 2px. Click again or double-click to exit focus mode.

3. **Node sizing by degree** — nodes with more connections render slightly larger (radius 5–9 based on edge count). More central entities are visually larger.

4. **Double-click to reset** — double-click anywhere on the canvas to exit focus mode and let the graph re-settle.

### Current State
- Service running on port 8420 via systemd ✅ (PID 143339, ~1h6min uptime)
- Git committed + pushed: `119cdaf` ✅
- All API endpoints healthy ✅

### No Blockers

### Next Sprint Candidates
1. **GitHub PR workflow** — blocked on GitHub auth credentials (no GH_TOKEN, no GitHub in auth.json)
2. **Memory graph type coloring** — Hermes entity store too sparse (all "unknown" type)
3. **Morning briefing quality** — content correct; formatting already improved
4. **Homelab network fix** — all hosts unreachable (10.87.1.0/24 no route), not a code issue

---

## Session Log — 2026-04-27 11:30 UTC

### Changes Made

**1. Session Message Pagination (NEW)**
- Backend: `HermesAdaptor.get_session_messages(session_id, offset=N, limit=M)` now returns `{messages, total, offset, limit}` — pages through messages from the start
- Endpoint: `GET /api/sessions/{id}/messages?offset=0&limit=8` — supports any offset/limit
- Frontend: clicking an expanded session shows first 8 messages; "Load N more" button fetches next page; "▲ N messages loaded" link jumps back to top
- Tested: session with 75 messages paginates correctly at offset 0, 3, 72

**2. Skill Invocation Hint (NEW)**
- Added `<span id="cmd-skill-hint">` to command input bar (cyan, right of input)
- `invokeSkill(name)` → fills `!name` in command bar + shows "Press Enter to invoke !name" hint
- Hint cleared on any command submission or built-in command execution

### Current State
- Service running on port 8420 via systemd ✅ (PID 143339, fresh restart)
- Git committed + pushed: `998d4b6` ✅
- All endpoints verified: /api/ping ✅ /api/status ✅ /api/cron-jobs ✅ /api/sessions ✅ /api/briefing ✅ /api/system-info ✅ /api/metrics ✅

### No Blockers

### Next Sprint Candidates
1. **GitHub PR workflow** — blocked on GitHub auth credentials (no GH_TOKEN, no GitHub in auth.json)
2. **Memory graph type coloring** — Hermes entity store too sparse (all "unknown" type)
3. **Morning briefing quality** — content correct; formatting already improved
4. **Homelab network fix** — all hosts unreachable (10.87.1.0/24 no route), not a code issue

---

## Session Log — 2026-04-27 10:20 UTC

### Changes Made

**`/pending` Command — Inline Pending Items in Terminal (NEW)**
- New built-in command: type `/pending` in the command bar → see pending items instantly in terminal, no panel switch needed
- Parses morning briefing `preview` text to extract:
  - 🔴 count of items needing direct action
  - 🟡 count of items waiting on external
  - Full PENDING section items (up to 12 lines)
  - PENDING CRONS section (up next 8 scheduled jobs)
- Added to `/help` output
- Briefing API returns `preview` field (not `text`) — fixed parsing to use correct field

### Current State
- Service running on port 8420 via systemd ✅ (PID 129309, ~2h15min uptime)
- Git committed: `39952a0` (panel drag-and-drop)
- `/pending` now live in command bar

### No Blockers

### Next Sprint Candidates
1. **GitHub PR workflow** — blocked on GitHub auth credentials (no GH_TOKEN, no GitHub in auth.json)
2. **Memory graph type coloring** — Hermes entity store too sparse (all "unknown" type)
3. **Morning briefing quality** — content correct; formatting already improved
4. **Homelab network fix** — all hosts unreachable (10.87.1.0/24 no route), not a code issue

---

## Session Log — 2026-04-27 09:20 UTC

### Changes Made

**Panel Drag-and-Drop Reorder (NEW)**

- 4 left-column panels now draggable: Status, Sessions, Cron Jobs, Briefing
- Drag handle (&#9776;) appears on header hover; grab and drag to reorder
- CSS: `.dragging` opacity state, `.drag-over` accent border
- HTML5 native drag-and-drop API — no dependencies
- `PANEL_IDS` canonical array updated on drop; `applyOrder()` moves header+body DOM nodes together
- Order persisted to `localStorage` key `mc_panel_order`, survives page reloads
- `initPanelDnD()` called at boot, runs before SSE connects

### Current State
- Service running on port 8420 via systemd ✅
- Git committed + pushed: `39952a0` ✅
- All endpoints verified: /api/ping ✅

### No Blockers

### Next Sprint Candidates
1. **GitHub PR workflow** — blocked on GitHub auth credentials (no GH_TOKEN, no GitHub in auth.json)
2. **Memory graph type coloring** — Hermes entity store too sparse (all "unknown" type)
3. **Morning briefing quality** — content correct; formatting already improved
4. **Panel drag-and-drop reorder** — bring back from old version ✅ (DONE this session)
5. **Homelab network fix** — all hosts unreachable (10.87.1.0/24 no route), not a code issue

---

## Session Log — 2026-04-27 08:15 UTC

### Fix: Morning Briefing Panel

**Problem:** Briefing panel showed "No briefing found" — morning briefing was in the session file but code couldn't find it.

**Root cause (Phase 1):**
1. Morning-briefing cron job (`477d9b0fce90`) fires at 21:00 UTC (07:00 AEST)
2. Creates `session_cron_477d9b0fce90_20260426_210005.json`
3. Other crons fire every ~5 min → session ranks **83rd by mtime** in the cron sessions list
4. `get_briefing()` only scanned `[:50]` — too narrow
5. Secondary filter looked for `"briefing-morning"` in first user message, but this session invokes `anh-ops` instead

**Fix (Phase 3):**
1. Widened scan from `[:50]` → `[:120]` (covers position 83)
2. Added secondary acceptance: `"477d9b0fce90" in session_file.stem`

**Also resolved:** Orphaned python process (PID 123738 from 07:03) was holding port 8420 — caused the 08:05 systemd restart to fail with `EADDRINUSE`. Killed it, service resumed normally.

### Current State
- Service running on port 8420 via systemd ✅ (PID fresh)
- Git committed + pushed: `cb28e0d` ✅
- `/api/briefing` returns morning brief ✅ (was `null` before fix)
- All 10 API endpoints healthy ✅

### No Blockers

### Next Sprint Candidates
1. **GitHub PR workflow** — blocked on GitHub auth credentials (no GH_TOKEN, no GitHub in auth.json)
2. **Memory graph type coloring** — Hermes entity store too sparse (all "unknown" type)
3. **Morning briefing quality** — content correct; formatting already improved
4. **Panel drag-and-drop reorder** — bring back from old version
5. **Homelab network fix** — all hosts unreachable (10.87.1.0/24 no route), not a code issue

---

## Session Log — 2026-04-27 07:00 UTC

### Changes Made

**Server Info Panel — CPU/Mem/Disk Live Metrics (NEW)**

Backend:
- `GET /api/system-info` endpoint — returns live server health via psutil
- `HermesAdaptor.get_system_info()` in `adaptor/hermes.py`: CPU %, memory %, disk %, load average, uptime, boot time
- psutil==6.1.0 added to `requirements.txt` (installed in venv)

Frontend (Server tab in right column):
- New **Server** tab added to tab bar (after Metrics)
- Three horizontal fill bars: **CPU**, **MEM**, **DISK** with color-coded thresholds
  - Green (0-70%) → Amber (70-85%) → Red (85%+)
  - Numeric % displayed right of each bar
- Below bars, key/value metadata rows:
  - **LOAD** — 1/5/15 min load averages + CPU core count
  - **UPTIME** — formatted as `Xd Xh Xm` or `Xh Xm`
  - **BOOTED** — boot timestamp in local datetime
  - **DISK** — `used / total GB`
  - **MEM** — `used / total GB`
- 30-second auto-refresh alongside other panels
- Bar widths and colors transition smoothly on each update

### Current State
- Service running on port 8420 via systemd ✅ (fresh restart)
- Git committed + pushed: `247d54b` ✅
- All endpoints verified: /api/ping ✅ /api/system-info ✅ /api/status ✅ /api/metrics ✅

### No Blockers

### Next Sprint Candidates
1. **GitHub PR workflow** — blocked on GitHub auth credentials (no GH_TOKEN, no GitHub in auth.json)
2. **Memory graph type coloring** — Hermes entity store too sparse (all "unknown" type)
3. **Morning briefing quality** — content correct; could improve formatting further
4. **Better streaming** — chunk_size=64 for faster token delivery

---

## Session Log — 2026-04-27 05:56 UTC

### Changes Made

**Metrics Panel — SQLite-backed Live Metrics (NEW)**

Backend:
- `metrics.db` (SQLite) created in repo root — persists across restarts
- Tracks: `commands`, `errors`, `events` counters with timestamps
- `/api/metrics` endpoint: uptime, current counter values, 24h hourly timeseries bucketed from SQLite
- Counters increment on: command execution, streaming errors, SSE event emissions
- 2x2 metric card grid: Commands (cyan), Errors (red), Events (amber), Error Rate %

Frontend:
- New **Metrics** tab added to right column tab bar
- **Uptime** display: shows `Xh Ym` or `Xd Xh Ym` format
- **SINCE** timestamp showing service start time
- **24-Hour Activity** sparkline: CSS bar chart, one bar per hour, cyan bars showing command count per hour
- Error rate color-coded: green (<1%), amber (1-5%), red (>5%)
- 30s auto-refresh alongside other panels

Bug fixes:
- Python `global` scoping: moved `_cmd_count`, `_err_count`, `_events_received` into helper functions (`_inc_cmd()`, `_inc_err()`, `_inc_events()`) — avoids global declaration issues in nested async generators
- Event ring buffer rebinding bug: changed `_event_log = _event_log[-MAX:]` (rebinds name as local) to `del _event_log[:-MAX]` (in-place mutation) — fixes `cannot access local variable` error in `emit()`

### Current State
- Service running on port 8420 via systemd ✅ (PID fresh)
- Git committed + pushed: `9f2d328` ✅
- All endpoints verified: /api/ping ✅ /api/metrics ✅ /api/status ✅ /api/events/recent ✅
- metrics.db: commands=1, errors=2 (from earlier test failures), events=1 tracked correctly

### No Blockers

### Next Sprint Candidates
1. **GitHub PR workflow** — blocked on GitHub auth credentials
2. **Memory graph type coloring** — Hermes entity store too sparse (all "unknown" type)
3. **Better streaming** — chunk_size=64 for faster token delivery
4. **Panel drag-and-drop reorder** — bring back the drag-and-drop from the old version

---

## Session Log — 2026-04-27 04:37 UTC

### Changes Made

**Live Events Panel (NEW)**
- Replaced the thin `feed-mini` strip with a proper 180px scrollable Events panel in the left column
- New backend: `_event_log` ring buffer (100 entries) + `GET /api/events/recent?limit=N` endpoint
- New frontend: `loadEvents()` fetches recent events on boot, SSE `addEvent()` live-updates the panel
- Event types rendered with color-coded badges: `platform_change` (cyan), `cron_triggered` (green), `command_executed` (amber), `error` (red)
- Each event row: timestamp + badge + message text
- Auto-scrolls to latest event; scrollable history via the panel scrollbar
- `addMiniFeed()` bridge function preserved so existing callers (`runCron`, streaming) continue to work

### Current State
- Service running on port 8420 via systemd ✅ (fresh restart)
- Git committed + pushed: `e93df59` ✅
- All endpoints verified: /api/ping ✅ /api/status ✅ /api/cron-jobs ✅ /api/events/recent ✅ /api/sessions ✅ /api/graph ✅

### No Blockers

### Next Sprint Candidates
1. **GitHub PR workflow** — blocked on GitHub auth (no GH_TOKEN, no GitHub in auth.json)
2. **Memory graph type coloring** — Hermes entity store too sparse (all types "unknown")
3. **Morning briefing quality** — content correct; could improve formatting further
4. **Token usage display** — Hermes doesn't populate total_tokens at write time (limitation)
5. **Live metrics over time** — uptime history, token usage graphs

---

## Session Log — 2026-04-27 03:34 UTC

### Changes Made

**Briefing Panel — Section-Parsed HTML Rendering (UPGRADE)**
- Previously: briefing text was displayed as raw `textContent` (plain text, no formatting)
- Now: `renderBriefing()` parses briefing into structured HTML sections:
  - **PENDING:** items rendered with `-` bullet points, **HOMELAB:** extracted into a red-bordered alert box
  - Section labels (PENDING, UPDATES, etc.) styled as uppercase label headers
  - Homelab CRITICAL block gets dedicated `.homelab-alert` styled div with red border and amber text highlights
  - Crons fallback (when no briefing) shows items with ⏰ dot prefix
- CSS: `.briefing-section`, `.briefing-section-label`, `.briefing-item`, `.homelab-alert`, `.homelab-alert-body`
- Homelab currently shows CRITICAL: all hosts unreachable (network issue, not a code problem)

### Current State
- Service running on port 8420 via systemd ✅ (PID fresh restart)
- Git committed + pushed: `20d1674` ✅
- All endpoints healthy: /api/ping ✅ /api/status ✅ /api/briefing ✅

### No Blockers

### Next Sprint Candidates
1. **GitHub PR workflow** — blocked on GitHub auth credentials
2. **Memory graph type coloring** — blocked: Hermes populates entity types (20 entities all "unknown", 4 facts total)
3. **Morning briefing quality** — content correct and now better formatted; could improve briefing generation prompts directly
4. **Dependabot fixes** — 3 moderate GitHub vulnerabilities (low priority)

---

## Session Log — 2026-04-27 02:30 UTC

### Changes Made

**Health Check — All Systems Operational**
- `/api/ping`: ✅ ok
- `/api/status`: ✅ 3 platforms connected (telegram, api_server, discord)
- `/api/cron-jobs`: ✅ 31 total, 27 enabled
- `/api/briefing`: ✅ returns morning brief with PENDING items + homelab status
- `/api/context`: ✅ ok
- Memory graph: 20 entities all "unknown" type, only 4 facts — too sparse for meaningful type coloring (Hermes population issue, not actionable here)
- No new blockers found

### Current State
- Service running on port 8420 via systemd ✅
- MVP layers 0-2: all complete and operational
- Git working tree clean (no uncommitted changes)

### No Blockers

### Next Sprint Candidates
1. **Memory graph type coloring** — blocked: Hermes populates entity types (20 entities all "unknown", 4 facts total)
2. **Morning briefing quality** — content is correct but formatting could be improved
3. **Dependabot fixes** — 3 moderate GitHub vulnerabilities (low priority)
4. **GitHub PR panel** — blocked on GitHub auth credentials (per 01:29 session log)

---

## Session Log — 2026-04-27 01:29 UTC

### Changes Made

**Entity Drill-Down — Click Connections in Graph Detail Panel (NEW)**
- Refactored graph node click into `renderEntityDetail(entityId)` function
- Connection names in detail panel are now **cyan clickable spans** (`.clickable-entity`)
- Click any connection name to **drill into that entity** — full fact previews (120 chars) load
- Clicking the selected entity again shows all connections (no-op safe)
- CSS: `.clickable-entity` hover underline, `.detail-preview` for fact content
- `_selectedEntity` tracks current drill-down state; up to 12 connections shown for selected entity vs 8 compact
- Graph canvas unchanged; detail panel upgrades enable multi-hop exploration

### Current State
- Service running on port 8420 (systemd) ✅ (PID 104281, fresh restart)
- Git committed + pushed: `128a05a` ✅
- Graph: 20 nodes, 4 edges with fact previews

### GitHub PR Workflow — BLOCKER
- GitHub MCP auth failing: `McpError: Authentication Failed: Bad credentials`
- No `gh` CLI installed
- No `GH_TOKEN` or GitHub env vars
- `auth.json` in `.hermes` has no GitHub provider entries
- **Need Aaron to:** either add GitHub credentials to `~/.hermes/auth.json` providers, or set `GH_TOKEN` env var, so we can build the GitHub PR panel

### Next Sprint Candidates
1. **GitHub PR workflow** — blocked on auth (see above)
2. **Memory graph panel** — entity drill-down now works; could add type-based coloring (person=blue, project=green)
3. **Morning briefing content** — improve quality/formatting
4. **Dependabot fixes** — 3 moderate GitHub vulnerabilities (low priority)

### Bug Fixed

**Briefing Panel — Wrong Content (FIXED)**
- Root cause: `get_briefing()` grabbed the most recently modified `session_cron_*` file by mtime
- Problem: heavy cron churn (new session every 5 min) pushed the actual morning briefing (21:00 UTC, session `477d9b0fce90`) to position 22+ — outside the `[:20]` scan window
- Fix 1: Added filter for `briefing-morning` skill in first user message — only accepts genuine morning briefing sessions
- Fix 2: Expanded scan from `[:20]` → `[:50]` to cover cron churn
- Morning briefing now correctly shows `cron_477d9b0fce90_20260426_210005` with today's pending items

### Current State
- Service running on port 8420 via systemd (PID 100738, fresh restart) ✅
- Git committed + pushed: `85a04e6` ✅
- All endpoints verified: /api/ping ✅ /api/status ✅ /api/cron-jobs ✅ /api/sessions ✅ /api/briefing ✅ (now returns real morning brief)
- Briefing panel shows: `🌅 **MORNING BRIEF — 2026-04-27**` with `🔴 0 items need you directly, 🟡 1 item waiting on external: Google Workspace OAuth`

### No Blockers

### Next Sprint Candidates
1. **Morning briefing content quality** — briefing now correct; could improve formatting/sections
2. **Memory graph panel** — 17 entities all "unknown" type; revisit when Hermes populates more
3. **Dependabot fixes** — 3 moderate GitHub vulnerabilities (low priority, no runtime impact)
4. **Token usage display** — `sessions.json` has `total_tokens=0` always; Hermes limitation, not fixable here

---

## Session Log — 2026-04-26 22:58 UTC

### Changes Made

**1. Sessions Panel — Expand to See Messages (NEW)**
- Added `GET /api/sessions/{session_id}/messages` endpoint — returns last N messages from a session file
- Sessions are now **clickable** — click any session to expand and see the last 8 messages inline
- Each message shows: role icon (👤 user / 🤖 assistant / 🔧 tool), role label, timestamp, content
- Toggle click to collapse. Clicking another session collapses the previous one.
- CSS: hover highlights session name in blue, expanded state gets tinted background
- `HermesAdaptor.get_session_messages()` reads session JSON file directly, no auth needed

**2. Skills Panel — Search/Filter (NEW)**
- Added filter input to skills panel header — type to filter by name, description, or tags
- Skills list now cached in `_skillsCatalog` global so filter re-renders without re-fetching
- Filter is live (oninput, no submit needed)
- Owner attribution shown when present (e.g. `by Maxi`, `by arnold`)
- Empty state: "No skills match 'xyz'" vs "No skills found"

### Current State
- Service running on port 8420 (systemd, enabled) ✅
- Git committed + pushed: `89ba58f` ✅
- All endpoints verified: /api/ping ✅ /api/status ✅ /api/cron-jobs ✅ /api/sessions ✅ /api/skills-catalog ✅ /api/sessions/{id}/messages ✅
- 20 skills cataloged, skills filter working

### No Blockers

### Next Sprint Candidates
1. **Memory graph panel** — 17 entities all "unknown" type; revisit when Hermes populates more
2. **Morning briefing content** — improve quality/formatting
3. **Session click → view full session** — currently limited to 8 messages; could paginate or load more
4. **Skills invocation feedback** — clicking a skill in the panel feeds it to command bar (already working) but user has no confirmation; could show "Press Enter to invoke `!skill-name`" hint
5. **Dependabot fixes** — 3 moderate GitHub vulnerabilities (low priority, no runtime impact)

---

## Session Log — 2026-04-26 21:52 UTC

### Changes Made

**Skills Catalog Populated (15 NEW SKILL.md files)**
- 28 skills total in `~/.hermes/skills/`, but only 4 had `SKILL.md` frontmatter → only those 4 appeared in dashboard command palette
- Created minimal frontmatter SKILL.md for 15 high-value skills: `anh-ops`, `homelab`, `github`, `mcp`, `autonomous-ai-agents`, `briefings`, `smart-home`, `productivity`, `software-development`, `research`, `security`, `email`, `media`, `creative`, `data-science`
- `get_skills_catalog()` reads `~/.hermes/skills/<name>/SKILL.md` frontmatter to populate the catalog
- Verified: 4 → 19 skills visible in dashboard command palette (previously 4, now 19)

### Current State
- Service running on port 8420 (systemd, enabled, uptime ~1h) ✅
- Skills catalog: 19 skills visible (was 4, now includes anh-ops, github, homelab, briefings, mcp, etc.) ✅
- Working tree clean — SKILL.md changes were to `~/.hermes/skills/` (outside git repo)

### No Blockers

### Next Sprint Candidates
1. **Skills panel in dashboard** — currently skills only visible in command palette; could add a dedicated "Skills" panel showing all 19 skills with descriptions and trigger hints
2. **Memory graph panel** — 17 entities all "unknown" type; revisit when Hermes populates more
3. **Morning briefing content** — improve quality/formatting
4. **Dependabot fixes** — 3 moderate GitHub vulnerabilities (low priority)

---

## Session Log — 2026-04-26 20:48 UTC

### Changes Made

**Dead `/api/skills` stub removed**
- `get_skills()` in `hermes.py` was an async stub returning `[]`
- The working implementation is `get_skills_catalog()` which reads `~/.hermes/skills/*/SKILL.md` frontmatter
- Frontend already correctly used `/api/skills-catalog` (wired to `get_skills_catalog()`)
- Removed the dead `/api/skills` endpoint from `web.py`
- Confirmed 4 skills with SKILL.md files: dogfood, fitness-coach, fitness-coach-mode, workspace-dispatch

### Current State
- Service running on port 8420 (systemd, enabled) ✅
- Skills catalog: 4 skills visible in dashboard ✅
- Git committed + pushed: `7b41fe8` ✅

### No Blockers

### Next Sprint Candidates
1. **Skills panel populate** — 4 skills found but most others (anh-ops, github, homelab, etc.) have no SKILL.md; add minimal frontmatter to high-value skills to make them visible
2. **Memory graph panel** — 17 entities all "unknown" type; revisit when Hermes populates more
3. **Morning briefing content** — improve quality/formatting
4. **Dependabot fixes** — 3 moderate GitHub vulnerabilities (low priority)

---

## Session Log — 2026-04-26 19:40 UTC

### Changes Made

**1. Pending Crons Strip (NEW)**
- Thin strip between topbar and main layout showing next 6 upcoming cron jobs
- Each pill shows: job name + scheduled time (HH:MM)
- Click any pill to trigger the job immediately (uses existing `runCronByName()`)
- 30s auto-refresh alongside other panels
- CSS: dark surface2 background, compact 0.68rem font

**2. Session Display Name Truncation (FIX)**
- Discord sessions were showing full first message (~98 chars) as display name
- Now truncated at 50 chars with `…` ellipsis
- Clean session names in the Sessions panel

**3. Systemd Service Fix**
- Root cause: `User=localadmin` in service file caused `GROUP` exit code (systemd couldn't resolve username in user-level service context)
- Fix: removed `User=localadmin`, changed `WantedBy=multi-user.target` → `WantedBy=default.target`
- Service now properly managed via `systemctl --user`
- Previously was running as a manual foreground process (PID 78853)

### Current State
- Service running on port 8420 via systemd ✅ (PID 84948)
- Git committed + pushed: `50a866e` ✅
- All API endpoints healthy: /api/ping ✅ /api/status ✅ /api/cron-jobs ✅

### No Blockers

### Next Sprint Candidates
1. **Dependabot fixes** — 3 moderate GitHub vulnerabilities (low priority, no runtime impact)
2. **Skills catalog** — `get_skills()` returns empty (no endpoint on Hermes), could read skills from `~/.hermes/skills/` directory directly
3. **Memory graph panel** — 17 entities all "unknown" type, sparse edges; revisit when Hermes populates more
4. **Morning briefing content** — improve quality/formatting

---

## Session Log — 2026-04-26 18:25 UTC

### Changes Made

- Reviewed state: service active, all 3 platforms connected ✅
- Committed + pushed previous uncommitted session log (`eecb9bc`)
- Investigated memory graph: 17 entities all type "unknown", only 3 facts — too sparse for meaningful type-based node coloring
- Briefing panel working: `get_briefing()` correctly finds latest `session_cron_*` file and surfaces morning briefing preview

### Current State
- Service running on port 8420 (systemd, active) ✅
- Git pushed: `eecb9bc` ✅
- No blockers — MVP complete, all layers operational

### Next Sprint Candidates
1. **Memory graph panel** — entity store too sparse (17 entities, all "unknown" type) to benefit from type-based coloring; revisit when Hermes populates more entities
2. **Morning briefing content** — improve briefing quality/formatting in the panel
3. **Dependabot fixes** — 3 moderate GitHub vulnerabilities (low priority)
4. **Token usage display** — already done ✅

---

## Session Log — 2026-04-26 17:23 UTC

### Changes Made

**Sessions panel: token display fix (NEW)**
- `last_prompt_tokens` added to `/api/sessions` response from sessions.json
- Dashboard shows `~27k tok*` when `total_tokens=0` (always the case — Hermes doesn't populate total_tokens at write time)
- Footnote added: `* prompt tokens (total not reported by Hermes)`

### Current State
- Service running on port 8420 (systemd, enabled, just restarted — 5s uptime) ✅
- Git committed + pushed: `6f50815` (Sessions panel: show last_prompt_tokens)
- All endpoints verified: /api/sessions returns `last_prompt_tokens=27372` ✅
- Service restarted cleanly, all panels loading

### No Blockers

### Next Sprint Candidates
1. **Memory graph panel** — type-based node coloring (person=blue, project=green, concept=purple), hover shows entity fact previews
2. **Token usage display** — DONE ✅ (this session)
3. **Morning briefing panel polish** — make it more prominent (already has regenerate button ✅)
4. **Dependabot fixes** — 3 moderate GitHub vulnerabilities (low priority)
5. **Better streaming** — chunk_size=64 for perf (chunk_size=1 is correct but slow)

---

## Session Log — 2026-04-26 16:15 UTC

### Changes Made

**Briefing panel "Regenerate" button (NEW)**
- Added 🔄 button (↻) next to "🌅 Briefing" panel label
- Click triggers `morning-briefing` cron job immediately
- Shows "Regenerating..." in yellow while running
- Polls `/api/briefing` every 3s for up to 60s waiting for new session to appear
- Auto-restores button state on completion or timeout
- No backend changes — pure client-side enhancement

### Current State
- Service running on port 8420 (systemd, enabled, 4h 25min uptime) ✅
- Git committed + pushed: `9018c73` (briefing regenerate button)
- All endpoints verified: /api/status ✅ /api/briefing ✅ /api/cron-jobs ✅
- systemd service confirmed running (was already enabled from prior session)

### No Blockers

### Next Sprint Candidates
1. **Token usage display** — `sessions.json` has `last_prompt_tokens` (81986) but `total_tokens/input_tokens/output_tokens` are always 0; Hermes doesn't populate these at write time
2. **Memory graph panel** — type-based node coloring (person=blue, project=green, concept=purple), hover shows entity fact previews
3. **Session token/cost display** — surface `last_prompt_tokens` from sessions.json in Sessions panel
4. **Morning briefing panel polish** — make it more prominent (already has regenerate button now ✅)
5. **Dependabot fixes** — 3 moderate GitHub vulnerabilities (low priority, no runtime impact)

## Session Log — 2026-04-26 15:11 UTC

### Changes Made

**Panel drag-to-reorder with localStorage persistence (NEW)**
- 5 left-column panels now draggable: Status, Sessions, Cron Jobs, Briefing, Command
- `&#9776;` drag handle appears on hover (left of panel label)
- CSS: subtle hover highlight, drag-over accent border on target panel
- Uses native HTML5 drag-and-drop API — no dependencies
- `initDragAndDrop()` called at boot, validates order against `PANEL_IDS`
- Order persisted to `localStorage` key `mc_panel_order`, survives page reloads
- 2 files changed, ~200 lines added

### Current State
- Service running on port 8420 (systemd, enabled, 3h 13min uptime) ✅
- Git committed + pushed: aaa37de (Panel drag-to-reorder)
- All endpoints verified ✅

### No Blockers

### Next Sprint Candidates
1. **Dependabot fixes** — 3 moderate GitHub vulnerabilities (low priority, no runtime impact)
2. **Token usage display** — `sessions.json` has `last_prompt_tokens` (45239, 101528) but `total_tokens=0` always; Hermes limitation, not fixable here
3. **Morning briefing panel polish** — more prominent placement, add "regenerate" button
4. **Memory graph panel** — type-based node coloring, hover shows entity fact previews
5. **Session token/cost display** — surface `last_prompt_tokens` from sessions.json in Sessions panel

## Session Log — 2026-04-26 14:00 UTC

### Changes Made

**1. Graph physics tuning (DONE)**
- Repulsion force: `3000 → 1500` (nodes spread more, less jitter)
- Edge spring constant: `0.05 → 0.02` (smoother, less oscillation)
- Ideal edge length: `100 → 140px` (nodes space out further)
- Center gravity: `0.001 → 0.0008` (gentler pull to center)
- Velocity damping: `0.85 → 0.88` (smoother motion)
- Ticks/frame: `5 → 3` (reduced CPU load, still smooth at 60fps)

**2. Cron jobs in command palette (DONE)**
- All cron jobs now appear in the command palette (type `run`, `cron`, or job name to filter)
- Jobs cached in `_cronJobs` global — populated on boot from `/api/cron-jobs`
- Each palette entry shows: `⏰ Run: <name> — Schedule: <expr> · <last_status>`
- Triggers via the existing `runCron()` function — no backend changes needed

### Current State
- Service running on port 8420 (systemd, enabled, survives reboots) ✅
- Git committed + pushed: `1ec771f`
- GitHub: 3 moderate Dependabot vulnerabilities (low priority — no npm deps in project, alerts are on repo metadata)

### No Blockers

### Next Sprint Candidates
1. **Dependabot fixes** — resolve the 3 moderate GitHub vulnerabilities (audit npm/pip deps)
2. **Morning briefing panel** — make it more prominent, add "regenerate" button
3. **Panel drag-to-reorder** — persist layout to localStorage
4. **Token usage display** — read actual token counts from session .jsonl files
5. **Memory graph panel polish** — type-based node coloring (person/project/concept), hover shows fact previews

## Session Log — 2026-04-26 13:00 UTC

### Changes Made

**Command history localStorage persistence (DONE)**
- Commands now persist across page reloads via `localStorage.setItem('mc_cmd_history', ...)`
- Loaded on page init: `JSON.parse(localStorage.getItem('mc_cmd_history') || '[]')`
- Graceful fallback: wrapped in `try/catch` in case localStorage is blocked
- Added "Clear command history" action to command palette (🗑 icon) — wipes localStorage + in-memory array
- No backend changes needed — fully client-side

### Current State
- Service running on port 8420 (systemd) ✅
- All endpoints verified ✅
- Git committed + pushed: dbf883a
- GitHub Dependabot: 3 moderate vulnerabilities (low priority — `npm audit fix` / `pip audit` available)

### No Blockers

### Next Sprint Candidates
1. **Token usage display** — sessions.json has `total_tokens/input_tokens/output_tokens` fields but they're all 0; either Hermes doesn't populate them or we need to read from session .jsonl files instead
2. **Memory graph panel** — force-directed D3 graph of Hermes memory (entities from memory_store.db)
3. **Panel drag-to-reorder** — customize dashboard layout via drag/drop
4. **Morning briefing panel polish** — show briefing content more prominently, add "regenerate" button
5. **Dependabot fixes** — run `npm audit fix` or `pip audit` to resolve the 3 moderate GitHub vulnerabilities

---

## Session Log — 2026-04-26 07:30 UTC

### Bug Fixes

**1. SSE /events endpoint — broken cleanup**
- Root cause: `FastAPI Request` has no `add_event_callback()` method
- Every SSE connection was throwing `AttributeError` at line 75
- Fix: moved subscriber cleanup into `gen()`'s `try/finally` block — fires when client disconnects
- Confirmed: `/events` now returns 200 with `event: ping` on connect

**2. Streaming token extraction — silent failure**
- Root cause: `parsed["choices"]` is a Python `list`, not `dict`
- Chained `.get(0, {})` call failed: `list has no .get()` method
- All tokens silently swallowed, streaming returned only `done`
- Fix: `choices = parsed.get("choices"); if choices and isinstance(choices, list): delta = choices[0].get(...)`
- Confirmed: `curl /api/command/stream` now returns `event: token` + actual tokens + `event: done`

### Current State
- Service running on port 8420 (systemd, enabled, survives reboots)
- All 10 API endpoints verified ✅
- SSE stream working ✅
- Streaming command working ✅
- Git committed: 14a71fc (fix: SSE endpoint + streaming token extraction)

### No Blockers

## Session Log — 2026-04-26 06:30 UTC

### Changes Made

**1. Real SSE Token Streaming (FINALLY)**
- Root cause: `httpx.AsyncClient.aiter_lines()` uses an internal chunk buffer that can split SSE `\n\n` delimiters across network reads
- Fix: `HermesAdaptor._stream_lines()` now uses `response.aiter_bytes(chunk_size=1)` + manual newline splitting, so the SSE boundary is detected correctly per-byte
- Dashboard now calls `/api/command/stream` — tokens render instantly as they arrive from Hermes, no fake typing animation

**2. Morning Briefing Panel**
- New `/api/briefing` endpoint: reads recent cron session files, finds the last assistant message >200 chars (the actual briefing), returns preview + pending crons
- Briefing strip appears below the topbar when a briefing is found — shows preview text + generation timestamp
- Falls back to showing upcoming cron jobs strip even without a briefing

**3. Active Sessions Panel**
- New `/api/sessions` endpoint: reads `~/.hermes/sessions/sessions.json` index, enriches with per-session message counts from session files, returns top 10 sorted by `updated_at`
- New Sessions panel in dashboard: platform icon (💬/✈️/🔌), session name, msg count, token usage, last updated

**4. Dashboard Grid Layout**
- 3-column: `[Status + Sessions]` `[Feed]` `[Brain]`
- Command bar now spans both left columns (full width)
- Sessions panel on row 3 left, Feed on row 1 col 2, Brain spans rows 1-3 right

### Current State
- Service running on port 8420
- All new endpoints verified: /api/briefing ✅ /api/sessions ✅ /api/streaming ✅
- Git clean: 0976ee0

### Next Sprint Candidates
1. **Git remote push** — backup to GitHub/Gitea
2. **Better streaming** — try chunk_size=64 or larger for perf (chunk_size=1 is correct but slow)
3. **Memory graph panel** — visualize what Hermes knows as entities
4. **Panel customization** — drag/drop to reorder panels

## Session Log — 2026-04-26 06:00 UTC

### Changes Made
1. **Made repo fully portable and git-ready**
   - Initialized git repo with initial commit (049cb8c)
   - Created `.gitignore`: excludes `venv/`, `__pycache__/`, `config/settings.json` (secrets), `mission-control.service` (system-wide path)
   - All file paths now resolved **relative to the repo root** via `Path(__file__).parent`, not cwd
   - `HERMES_HOME` env var override added to `HermesAdaptor` — allows the repo to live anywhere
   - hermes binary lookup now checks `$HERMES_HOME/bin`, `/usr/local/bin`, `~/.local/bin` in order
   - `cron trigger` now falls back to `$HERMES_HOME/bin/python` if venv path doesn't exist
   - `.env.example` created documenting all env vars
   - `install/install.sh` created: creates venv, installs deps, sets up systemd service (user or system level), with `--verify` mode for checks only
   - `README.md` created with full documentation
2. **Service verified operational** — `curl /api/status` returns `OK=True`, all 3 platforms visible, Hermes v0.11.0, 16 cron jobs tracked

### Current State
- Git repo initialized, clean working tree
- All paths portable (no `/home/localadmin` hardcoded in Python code)
- Service still running on port 8420, verified working

### Next Sprint Candidates
1. **Streaming responses** — SSE stream of Hermes response token-by-token (httpx→SSE bridging issue with aiter_lines buffering)
2. **Morning briefing synthesis** — surface briefing skill output in dashboard
3. **Full context panel** — show active conversations, recent learnings
4. **Git remote** — push to GitHub/Gitea for backup

## Session Log — 2026-04-26 05:17 UTC

### Changes Made
1. **Hermes version display** — Added `HermesAdaptor.get_hermes_version()` via subprocess call to `~/.local/bin/hermes --version`. Uses 5-min cache. `/api/status` now returns correct version (`v0.11.0`) and release date (`2026.4.23`) instead of "unknown".
2. **`last_error` field** — Added `last_error` to `CronJob` dataclass, populated from `~/.hermes/cron/jobs.json`. Dashboard now shows ⚠️ icon on cron jobs with errors and displays last_status with color coding (green=ok, red=error, gray=unknown).
3. **Service restart** — Restarted service (pid 35033). All 3 platforms still visible: telegram ✅, discord ✅, api_server ✅. Hermes version now correctly shown.

### Current State
- All 4 layers complete and operational
- 3 platforms visible: telegram ✅, discord ✅, api_server ✅
- Hermes version: v0.11.0 (2026.4.23)
- 14+ cron jobs tracked with last_status and last_error fields
- Service running on port 8420

### Next Sprint Candidates
1. **Streaming responses** — SSE stream of Hermes response token-by-token (httpx→SSE bridging issue with aiter_lines buffering)
2. **Morning briefing synthesis** — surface briefing skill output in dashboard
3. **Full context panel** — show active conversations, recent learnings
4. **Better cron job display** — show last run time, error messages more prominently
5. **Systemd service fix** — service file exists but process is running manually; verify systemd can manage it

## Session Log — 2026-04-26 04:10 UTC

### Changes Made
- Added `/api/command/stream` endpoint for proper SSE token streaming (works at Hermes level, SSE re-emit has edge cases with httpx aiter_lines buffering — non-streaming `/api/command` used instead for now)
- Added progressive "typing" animation to command bar response — text renders in 12-char chunks at 20ms intervals giving instant feedback feel
- Service restarted cleanly, all endpoints healthy

### Current State
- All 4 layers complete and operational
- 3 platforms visible: telegram ✅, discord ✅, api_server ✅
- 14 cron jobs tracked (morning-briefing, midday-health-check, evening-wrap-up, weekly-pulse, maxi-overnight-work, mission-control-iterate, etc.)
- Service uptime: ~5 minutes (just restarted)

### Next Sprint Candidates
1. **Streaming response** — fix SSE token streaming (the `/api/command/stream` endpoint works at Hermes level but the httpx→SSE bridging needs async fix)
2. **Hermes version/repo info** — add `hermes --version` CLI call
3. **Morning briefing synthesis** — surface briefing skill output in dashboard
4. **Full context panel** — show active conversations, recent learnings
5. **Better cron job display** — show last run status, error messages

## Session Log — 2026-04-26 11:55 UTC

### Changes Made

**Command Bar History (NEW)**
- Up arrow: navigate to previous commands (most recent first)
- Down arrow: navigate forward
- Stores last 50 commands in memory (session-scoped, no persistence)
- Small but high-impact usability fix for daily use

### Current State
- Service running on port 8420 (systemd, enabled, survives reboots) ✅
- All 13 API endpoints verified: ping ✅ status ✅ cron-jobs ✅ paperclip/issues ✅ paperclip/goals ✅ briefing ✅ sessions ✅ graph ✅ skills-catalog ✅ history/search ✅ command ✅ streaming ✅
- Git committed: b3e4e56 (command history)
- Service uptime: fresh restart (2 min ago)
- GitHub pushed: b3e4e56

### No Blockers

### Next Sprint Candidates
1. **Session token/cost display** — read `last_prompt_tokens` from session files and show in Sessions panel
2. **Command history localStorage persistence** — persist command history across page reloads
3. **Memory graph panel improvements** — node type coloring, force spread tuning
4. **Panel drag-to-reorder** — customize dashboard layout
5. **GitHub vulnerabilities** — 3 moderate Dependabot alerts on this-bytes/mission-control (low priority, run `npm audit fix` or `pip audit`)

---

## blockers
- [x] ~~Hermes API endpoint and auth~~ — UPDATED: gateway REST API (port 9119) was dropped in a recent Hermes version. The OpenAI-compatible API server runs on port 8642. Status comes from `GET /health/detailed` on 8642. Cron jobs are read directly from `~/.hermes/cron/jobs.json`. No auth needed locally. `hermes_api_base` in settings.json updated to `http://127.0.0.1:8642`.
- [x] ~~Confirm Hermes API endpoint and auth mechanism~~ — CLOSED (see above)
- [x] ~~Confirm server port availability~~ — port 8420 running via systemd ✅
- [x] ~~Clarify access model~~ — local network only (no auth on MVP)
- [x] ~~Discover how to send prompts to Hermes~~ — OpenAI-compatible API at port 8642, no auth required locally
- [x] ~~GitHub backup~~ — SSH key works, `git push` succeeds. Repo at `this-bytes/mission-control` (git remote: `git@github.com:this-bytes/mission-control.git`). Backup working ✅

## Session Log — 2026-04-26 10:50 UTC

### Changes Made

**Paperclip Issues + Goals Panel (NEW)**
- `HermesAdaptor.get_paperclip_issues()` + `get_paperclip_goals()` — query Paperclip REST API at `10.87.1.201:3100` using session cookie auth
- `GET /api/paperclip/issues` — returns up to 20 issues sorted by updatedAt desc, filterable by `?status=blocked,in_progress`
- `GET /api/paperclip/goals` — returns up to 20 goals
- **New Issues tab** in right column: shows title, color-coded status badge (🔴 blocked / 🔵 in_progress / 🟢 open), last updated date, labels
- **Filter buttons**: All / Blocked / In Progress with active styling
- **Goals sub-panel** at bottom: shows title + status for top goals
- 60s auto-refresh on both
- Fixed: `urllib.request` and `ssl` modules were not imported in `hermes.py` — added to imports

### Current State
- Service running on port 8420 (systemd, enabled, survives reboots) ✅
- All 12 API endpoints verified: ping ✅ status ✅ cron-jobs ✅ paperclip/issues ✅ paperclip/goals ✅ briefing ✅ sessions ✅ graph ✅ skills-catalog ✅ history/search ✅ command ✅ streaming ✅
- Paperclip API reachable at 10.87.1.201:3100 ✅
- 20 issues, 9 goals visible in dashboard
- Git committed: 8e4e03c (Paperclip panel)
- Running: systemd managed service (PID 57634)

### No Blockers

## Session Log — 2026-04-26 10:15 UTC

### Changes Made

**1. Cron Jobs Panel** — New dedicated panel added to dashboard left column:
- Shows all 15 cron jobs with: name, schedule expression, last run time, status badge (✓ ok / ⚠ error / —)
- Error messages displayed inline in amber when `last_error` is present
- **▶ Run button** per job — triggers `POST /api/cron-jobs/{id}/trigger`, confirmed working
- 30s auto-refresh synced with other panels
- `api()` JS helper extended to support `POST` method (was GET-only before)

### Current State
- Service running on port 8420 (systemd) ✅
- All endpoints verified: /api/status ✅ /api/cron-jobs ✅ /api/streaming ✅ /events ✅
- Git committed: f283ba6 (cron jobs panel)
- 15 cron jobs visible in dashboard, all clean (no errors)

### GitHub Backup — BLOCKER
- Remote already set: `git@github.com:this-bytes/mission-control.git`
- `git push --dry-run` → "Everything up-to-date" (pushed successfully)
- **Note:** repo is at `this-bytes/mission-control` (not `arlo/mission-control` as originally planned)
- No further action needed on backup

### No Blockers for Core MVP

## Session Log — 2026-04-26 08:33 UTC

### Changes Made
1. **Streaming performance fix** — increased `chunk_size` from 1 to 128 in `_stream_lines()` (128x fewer async iterations, still correct SSE boundary detection). Verified: `curl /api/command/stream` returns tokens correctly.
2. **Git remote added** — `git remote add origin git@github.com:arlo/mission-control.git`. Verified SSH key exists at `~/.ssh/arlo_git` with github.com host configured in `~/.ssh/config`.

### GitHub Backup Attempted — BLOCKER REMAINS
- `git push` → "Repository not found" (repo doesn't exist yet)
- GitHub API repo creation → 401 Bad credentials
- `gh` CLI → not installed, can't install (no root)
- SSH key (`arlo_git`) exists and is correct for github.com host
- **Need Aaron to create the repo manually at github.com/arlo/mission-control**, then `git push` will work via SSH

### Current State
- Service running on port 8420 (systemd, enabled, survives reboots) ✅
- All API endpoints verified ✅
- Git committed: e555ee5 (streaming perf: chunk_size 1->128)
- Streaming working ✅
- Git remote configured, SSH key in place
- GitHub repo does not exist → push blocked

### No Blockers for Core MVP

---

## v2 Priority Features (Next Sprint)
1. ~~**Discord platform** showing in status**~~ — FIXED ✅ All 3 platforms (telegram, discord, api_server) visible after adaptor rewrite
2. **Morning briefing synthesis** — show briefing skill results
3. **Streaming responses** — SSE stream of Hermes response token-by-token
4. **Full ask() integration** — command bar already calls Hermes ✅ (DONE)
5. **Cron job trigger** — one-click "run now" from UI ✅ (DONE)
6. **Hermes version/repo info** — not exposed by `/health/detailed`, could add CLI call to `hermes --version`
---

*Plan created: 2026-04-25. Cron job will review this hourly and iterate unless blocked.*

---

## Session Log — 2026-04-26 23:47 UTC

### Changes Made

**Full Dashboard Rewrite — Aesthetics + Architecture**

The dashboard was rebuilt from scratch. The previous version was a generic dark dashboard with emoji decorators and no real operational feel. This version commits to a specific reference: SpaceX mission control meets Bloomberg Terminal.

**Aesthetic changes:**
- Font: JetBrains Mono throughout (was Segoe UI/system-ui)
- Colors: Pure black background (#000), green primary (#00e676), cyan accent (#00b4d4), amber warnings (#f5a623), no blue/purple gradients
- No emoji anywhere — all indicators are text/ASCII characters
- Dense 3-column layout: left (status + sessions + crons + briefing) | center (terminal) | right (tabbed: graph/history/issues/skills)
- Top bar: metric gauges showing version, PID, session count, cron count, live event counter

**Functional changes:**
- **Terminal (center)**: Full command interface. `/help`, `/cron`, `/sessions`, `/graph`, `/clear` built-ins. Real streaming responses from Hermes displayed character-by-character. Command history (ArrowUp/Down) persisted to localStorage.
- **Sessions**: Click any session to expand inline messages. Toggle open/close.
- **Cron Jobs**: List with schedule, last status, next run time. Inline RUN button per job. Clickable strip showing next 5 upcoming.
- **Briefing**: Regenerate button triggers morning-briefing cron.
- **Knowledge Graph**: Canvas force-directed graph. Click any node → detail panel shows entity type and all related facts with previews.
- **History Search**: Full-text FTS5 search. Click result to insert into terminal.
- **Paperclip Issues**: Filter by All/Blocked/Todo/Active. Click issue to expand full body text. Shows assignee, labels, dates.
- **Skills**: Filter by name/description/tags. Click skill to invoke (fills command bar with `!<skill-name>`).
- **Command Palette**: `/` hotkey. Sections for Actions, Skills, Cron Jobs. Keyboard navigation.

### Current State
- Service running on port 8420 (systemd) ✅
- Git committed + pushed to `github.com/this-bytes/mission-control` ✅
- 20 knowledge graph nodes, 4 edges
- 31 cron jobs
- 20 paperclip issues across 5 statuses

### No Blockers

### Next Sprint Candidates
1. **GitHub PR workflow** — push to feature branch, open PR from Mission Control UI
2. **Entity detail → drill into facts** — click a fact in the graph detail panel to see full content
3. **Streaming performance** — increase `chunk_size=1` to ~64 for faster token delivery
4. **Panel drag-and-drop reorder** — bring back the drag-and-drop from the old version
5. **Live metrics over time** — token usage graphs, uptime history
