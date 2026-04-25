#!/usr/bin/env python3
"""Mission Control — entry point.

Can be run from anywhere. Resolves paths relative to this file's location.
"""
import uvicorn
import json
from pathlib import Path

_ROOT_DIR = Path(__file__).parent
CONFIG = json.loads((_ROOT_DIR / "config" / "settings.json").read_text())
PORT = CONFIG.get("mission_control_port", 8420)


LOG_LEVEL = CONFIG.get("log_level", "info").lower()

if __name__ == "__main__":
    uvicorn.run(
        "service.web:app",
        host="0.0.0.0",
        port=PORT,
        log_level=LOG_LEVEL,
        reload=False,
    )
