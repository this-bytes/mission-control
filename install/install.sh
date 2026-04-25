#!/usr/bin/env bash
# ─── Mission Control — Install Script ─────────────────────────────────────────
# Sets up the Mission Control dashboard as a systemd service.
# Supports both system-wide and user-level installation.
#
# Usage:
#   ./install/install.sh            # interactive
#   ./install/install.sh --user     # user-level service (no sudo)
#   ./install/install.sh --system   # system-wide (requires sudo)
#   ./install/install.sh --verify   # just verify deps and paths, don't install
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
INSTALL_MODE=""

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RESET='\033[0m'

info()    { echo -e "${GREEN}[+]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[!]${RESET} $*"; }
err()     { echo -e "${RED}[✗]${RESET} $*" >&2; }
confirm() { echo -en "${YELLOW}[?]${RESET} $* [y/N] "; read -r reply; [[ $reply =~ ^[Yy]$ ]]; }

# ── Helpers ───────────────────────────────────────────────────────────────────
has() { command -v "$1" >/dev/null 2>&1; }

need() {
    for cmd in "$@"; do
        if ! has "$cmd"; then
            err "Missing required command: $cmd"
            MISSING_DEPS=1
        fi
    done
}

# ── Parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --user)   INSTALL_MODE=user; shift ;;
        --system) INSTALL_MODE=system; shift ;;
        --verify) INSTALL_MODE=verify; shift ;;
        *)        err "Unknown option: $1"; exit 1 ;;
    esac
done

# ── Pre-flight checks ─────────────────────────────────────────────────────────
info "Mission Control — Install"
echo ""
echo "  Project: $PROJECT_DIR"
echo "  hermes home: ${HERMES_HOME:-$HOME/.hermes}"
echo ""

need python3 git

if [[ ! -d "$PROJECT_DIR/config" ]]; then
    err "config/ directory not found. Are you in the right place?"
    exit 1
fi

if [[ ! -f "$PROJECT_DIR/requirements.txt" ]]; then
    err "requirements.txt not found."
    exit 1
fi

# Detect install mode if not specified
if [[ -z "$INSTALL_MODE" ]]; then
    if has sudo && [[ $(id -u) -ne 0 ]]; then
        echo ""
        echo "How should I install the systemd service?"
        echo ""
        echo "  [1] User-level service  — no sudo needed, lives in ~/.config/systemd/"
        echo "  [2] System-wide service — requires sudo, lives in /etc/systemd/system/"
        echo ""
        echo -n "Choose [1]: "
        read -r choice
        INSTALL_MODE=$([[ $choice == "2" ]] && echo "system" || echo "user")
    else
        INSTALL_MODE=user
    fi
fi

# ── Verify mode ───────────────────────────────────────────────────────────────
if [[ "$INSTALL_MODE" == "verify" ]]; then
    info "Verification only — no changes made."
    echo ""

    # Python venv
    if [[ -d "$PROJECT_DIR/venv" ]]; then
        info "venv/ found at $PROJECT_DIR/venv"
    else
        warn "venv/ not found — run './install/install.sh' to create it"
    fi

    # Python deps
    PY_DEPS_OK=1
    for pkg in fastapi uvicorn httpx sse_starlette jinja2; do
        if "$PROJECT_DIR/venv/bin/python" -c "import $pkg" 2>/dev/null; then
            info "  $pkg: installed"
        else
            warn "  $pkg: MISSING"
            PY_DEPS_OK=0
        fi
    done

    if [[ $PY_DEPS_OK -eq 0 ]]; then
        warn "Some Python packages are missing — run './install/install.sh' to install"
    fi

    # Hermes reachable
    HERMES_API="${HERMES_API_BASE:-http://127.0.0.1:8642}"
    if curl -sf "$HERMES_API/health/detailed" > /dev/null 2>&1; then
        info "Hermes API reachable at $HERMES_API"
    else
        warn "Hermes API not reachable at $HERMES_API — is Hermes running?"
    fi

    # Cron jobs file
    HERMES_HOME_DIR="${HERMES_HOME:-$HOME/.hermes}"
    if [[ -f "$HERMES_HOME_DIR/cron/jobs.json" ]]; then
        info "Cron jobs file: $HERMES_HOME_DIR/cron/jobs.json"
    else
        warn "Cron jobs file not found at $HERMES_HOME_DIR/cron/jobs.json"
    fi

    exit 0
fi

# ── Create venv + install deps ────────────────────────────────────────────────
info "Setting up Python virtual environment..."
if [[ ! -d "$PROJECT_DIR/venv" ]]; then
    python3 -m venv "$PROJECT_DIR/venv"
    info "Created venv at $PROJECT_DIR/venv"
else
    info "venv already exists"
fi

info "Installing Python dependencies..."
"$PROJECT_DIR/venv/bin/pip" install --quiet -r "$PROJECT_DIR/requirements.txt"
info "Dependencies installed"

# ── Install systemd service ───────────────────────────────────────────────────
SERVICE_NAME="mission-control"
SERVICE_FILE="$PROJECT_DIR/mission-control.service"

if [[ ! -f "$SERVICE_FILE" ]]; then
    err "Service file not found: $SERVICE_FILE"
    exit 1
fi

info "Installing systemd service..."
if [[ "$INSTALL_MODE" == "user" ]]; then
    USER_DIR="$HOME/.config/systemd/user"
    mkdir -p "$USER_DIR"
    sed "s|/home/localadmin|$HOME|g" "$SERVICE_FILE" > "$USER_DIR/$SERVICE_NAME.service"
    systemctl --user daemon-reload
    systemctl --user enable "$SERVICE_NAME"
    systemctl --user start "$SERVICE_NAME"
    info "User service installed: systemctl --user $INSTALL_MODE $SERVICE_NAME"
else
    sudo cp "$SERVICE_FILE" "/etc/systemd/system/$SERVICE_NAME.service"
    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME"
    sudo systemctl start "$SERVICE_NAME"
    info "System service installed: sudo systemctl $INSTALL_MODE $SERVICE_NAME"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
PORT=$(python3 -c "import json; d=json.load(open('$PROJECT_DIR/config/settings.json')); print(d.get('mission_control_port',8420))")
info "Installation complete!"
info "Dashboard: http://localhost:$PORT/"
info ""
info "Useful commands:"
if [[ "$INSTALL_MODE" == "user" ]]; then
    echo "  View logs:  journalctl --user -u $SERVICE_NAME -f"
    echo "  Restart:    systemctl --user restart $SERVICE_NAME"
    echo "  Stop:       systemctl --user stop $SERVICE_NAME"
else
    echo "  View logs:  sudo journalctl -u $SERVICE_NAME -f"
    echo "  Restart:    sudo systemctl restart $SERVICE_NAME"
    echo "  Stop:       sudo systemctl stop $SERVICE_NAME"
fi
echo ""
info "To update after pulling new code: cd $PROJECT_DIR && ./install/install.sh"
