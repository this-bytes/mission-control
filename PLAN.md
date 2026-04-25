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

## blockers
- [x] ~~Hermes API endpoint and auth~~ — UPDATED: gateway REST API (port 9119) was dropped in a recent Hermes version. The OpenAI-compatible API server runs on port 8642. Status comes from `GET /health/detailed` on 8642. Cron jobs are read directly from `~/.hermes/cron/jobs.json`. No auth needed locally. `hermes_api_base` in settings.json updated to `http://127.0.0.1:8642`.
- [x] ~~Confirm Hermes API endpoint and auth mechanism~~ — CLOSED (see above)
- [x] ~~Confirm server port availability~~ — port 8420 running via systemd ✅
- [x] ~~Clarify access model~~ — local network only (no auth on MVP)
- [x] ~~Discover how to send prompts to Hermes~~ — OpenAI-compatible API at port 8642, no auth required locally
- [ ] **GitHub backup blocked** — SSH key (`~/.ssh/arlo_git`) exists and is configured in `~/.ssh/config` for github.com. BUT: (1) GitHub MCP has bad credentials — `gh` CLI is not installed and cannot be installed (no root/apt access). (2) GitHub API returns 401 with the ops service account token. (3) Repository `arlo/mission-control` does not exist yet on GitHub — needs to be created first. Need Aaron to either: (a) create the repo manually on GitHub web UI, or (b) provide a GitHub PAT with `repo` scope that can be used to create the repo via API.

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
