# Mission Control — AI OS Dashboard

Bloomberg Terminal meets NASA Mission Control — a unified web dashboard that sits on top of Hermes Agent. See everything, trigger anything, get AI synthesis of your entire digital life.

![Status](https://img.shields.io/badge/status-operational-green) ![Hermes](https://img.shields.io/badge/hermes-v0.11-blue)

---

## Features

- **System Status Bar** — All connected platforms (Telegram, Discord, API) in one glance
- **Live Activity Feed** — Real-time SSE stream of events: messages, cron jobs, alerts
- **Command Bar** — Raycast-style: type anything, get AI-completed from Hermes
- **Hermes Brain** — See what Hermes knows: gateway state, model, cron jobs
- **Cron Job Trigger** — One-click "run now" on any scheduled job
- **Streaming Responses** — Watch Hermes think token by token

---

## Requirements

- **Hermes Agent** running with its OpenAI-compatible API server on port 8642
  (the gateway's `POST /v1/chat/completions` endpoint)
- Python 3.10+
- Linux (systemd) — probably works on macOS with minor tweaks

---

## Quick Start

```bash
# 1. Clone / navigate to the repo
cd mission-control

# 2. Install dependencies and set up the systemd service
./install/install.sh

# 3. Open the dashboard
open http://localhost:8420
```

The install script will:
- Create a Python virtual environment (`venv/`)
- Install all required Python packages
- Install the systemd service (user-level, no sudo required)
- Start Mission Control immediately

---

## Configuration

All configuration lives in `config/settings.json`:

```json
{
  "hermes_api_base": "http://127.0.0.1:8642",
  "hermes_home": "~/.hermes",
  "mission_control_port": 8420,
  "log_level": "info"
}
```

Or override with environment variables (useful for CI / containerized setups):

```bash
export HERMES_HOME=~/.hermes
export HERMES_API_BASE=http://127.0.0.1:8642
./venv/bin/python run.py
```

See `.env.example` for all available env vars.

---

## File Structure

```
mission-control/
├── adaptor/
│   ├── __init__.py
│   └── hermes.py          # HermesAdaptor — talks to Hermes API
├── service/
│   ├── __init__.py
│   ├── web.py             # FastAPI app + all endpoints
│   └── templates/
│       └── index.html     # Single-page dashboard (vanilla JS, no build)
├── config/
│   └── settings.json       # All configuration (git-tracked, no secrets)
├── scripts/               # Utility scripts
├── install/
│   └── install.sh         # Install + update script
├── run.py                 # Entry point
├── requirements.txt
├── mission-control.service # systemd unit template
├── .env.example           # Env var documentation
├── .gitignore
└── README.md
```

---

## Updating

```bash
cd mission-control
git pull
./install/install.sh   # reinstalls deps + restarts service
```

---

## Development

Run the web server directly (no systemd):

```bash
cd mission-control
./venv/bin/python run.py
# → http://localhost:8420
```

Verify all dependencies are correct:

```bash
./install/install.sh --verify
```

---

## Architecture

```
Browser  ←→  FastAPI (port 8420)  ←→  Hermes API Server (port 8642)
                  ↑
            HermesAdaptor
                  ↑
            hermes.py  +  ~/.hermes/cron/jobs.json
```

**HermesAdaptor** is the single integration point. It handles:
- Gateway + platform status via `GET /health/detailed`
- Cron jobs from local file `~/.hermes/cron/jobs.json`
- AI commands via `POST /v1/chat/completions`
- Hermes version via `hermes --version` CLI

---

## License

Private — Aaron's homelab setup.
