"""
HermesAdaptor — connects Mission Control to the Hermes Agent API.

Architecture (as of Hermes Agent v0.11+):
- Gateway runs as user service (hermes-gateway.service)
- OpenAI-compatible API server on port 8642 — chat completions, health checks
- Gateway status available at GET /health/detailed on port 8642
- Cron jobs stored in ~/.hermes/cron/jobs.json (local file, no auth needed)
- ask() via POST /v1/chat/completions on port 8642

Path resolution (in priority order):
1. HERMES_HOME env var (allows repo to live anywhere)
2. hermes_home in config/settings.json
3. ~/.hermes (default)
"""
import httpx
import json
import os
import ssl
import subprocess
import urllib.request
from pathlib import Path
from datetime import datetime
from typing import Any, Optional

from dataclasses import dataclass, asdict


def _resolve_hermes_home() -> Path:
    """Find Hermes home directory, in priority order."""
    if hermes_home := os.environ.get("HERMES_HOME"):
        return Path(hermes_home).expanduser()
    # Fallback: try to load from config (will be Path if not yet loaded)
    cfg_path = Path(__file__).parent.parent / "config" / "settings.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text())
            if hm := cfg.get("hermes_home"):
                return Path(hm).expanduser()
        except Exception:
            pass
    return Path.home() / ".hermes"


@dataclass
class PlatformStatus:
    name: str
    state: str  # connected, disconnected, error
    error: Optional[str] = None
    extra: Optional[dict] = None


@dataclass
class HermesStatus:
    version: str
    release_date: str
    hermes_home: str
    gateway_running: bool
    gateway_pid: int
    gateway_state: str
    platforms: dict[str, PlatformStatus]
    model: str
    model_provider: str
    checked_at: str


@dataclass
class CronJob:
    id: str
    name: str
    prompt_preview: str
    schedule: str
    next_run: Optional[str]
    enabled: bool
    last_run: Optional[str] = None
    last_status: Optional[str] = None
    last_error: Optional[str] = None


class HermesAdaptor:
    """Talk to Hermes Agent via its OpenAI-compatible API server."""

    def __init__(self, api_base: str = "http://127.0.0.1:8642"):
        self.api_base = api_base.rstrip("/")
        self._hermes_home = _resolve_hermes_home()
        self._cron_file = self._hermes_home / "cron" / "jobs.json"

    async def _get(self, path: str) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(self.api_base + path)
            resp.raise_for_status()
            return resp.json()

    # ── Status ──────────────────────────────────────────────────────────────────

    async def get_status(self) -> HermesStatus:
        """
        Full Hermes gateway + platform status.
        Source: GET /health/detailed on the OpenAI API server (port 8642).
        """
        data = await self._get("/health/detailed")
        platforms = {}
        for name, info in data.get("platforms", {}).items():
            platforms[name] = PlatformStatus(
                name=name,
                state=info.get("state", "unknown"),
                error=info.get("error_message"),
                extra={k: v for k, v in info.items() if k not in ("state", "error_message")},
            )

        # model info is not in /health/detailed; leave blank — ask() works fine
        return HermesStatus(
            version="unknown",  # not exposed by /health/detailed
            release_date="unknown",
            hermes_home=str(self._hermes_home),
            gateway_running=data.get("gateway_state") == "running",
            gateway_pid=data.get("pid", 0),
            gateway_state=data.get("gateway_state", "unknown"),
            platforms=platforms,
            model="MiniMax-M2.7",  # hardcoded from config.yaml — not exposed by API
            model_provider="minimax",
            checked_at=datetime.now().isoformat(),
        )

    # ── Cron Jobs ──────────────────────────────────────────────────────────────

    async def get_cron_jobs(self) -> list[CronJob]:
        """
        List all scheduled cron jobs.
        Source: ~/.hermes/cron/jobs.json (same machine, no auth needed).
        """
        if not self._cron_file.exists():
            return []

        data = json.loads(self._cron_file.read_text())
        jobs = []
        for j in data.get("jobs", []):
            sched = j.get("schedule", {})
            if isinstance(sched, dict):
                schedule_expr = sched.get("expr", "unknown")
            else:
                schedule_expr = str(sched)

            jobs.append(CronJob(
                id=j.get("id", ""),
                name=j.get("name", "unnamed"),
                prompt_preview=j.get("prompt", "")[:120],
                schedule=schedule_expr,
                next_run=j.get("next_run_at"),
                enabled=j.get("enabled", True),
                last_run=j.get("last_run_at"),
                last_status=j.get("last_status"),
                last_error=j.get("last_error"),
            ))
        return jobs

    async def trigger_cron_run(self, job_id: str) -> dict:
        """Trigger an immediate cron job run via the hermes CLI."""
        # Find the venv python in HERMES_HOME
        venv_python = self._hermes_home / "hermes-agent" / "venv" / "bin" / "python"
        if not venv_python.exists():
            # Try system python
            venv_python = self._hermes_home / "bin" / "python"
        result = subprocess.run(
            [str(venv_python), "-m", "hermes_cli.main", "cron", "run", job_id],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Cron run failed: {result.stderr.strip()}")
        return {"ok": True, "job_id": job_id, "output": result.stdout.strip()}

    # ── Toolsets / Skills ───────────────────────────────────────────────────────
    # These endpoints don't exist on the current API server port.
    # Returning empty lists — can be extended if Hermes adds these endpoints.

    async def get_toolsets(self) -> list[dict]:
        """List all available toolsets. (Not currently exposed by API server.)"""
        return []

    async def get_skills(self) -> list[dict]:
        """List all skills. (Not currently exposed by API server.)"""
        return []

    async def get_model_info(self) -> dict:
        """Model info — not exposed, return placeholder."""
        return {"model": "MiniMax-M2.7", "provider": "minimax"}

    async def get_hermes_version(self) -> dict:
        """
        Get Hermes version via CLI subprocess.
        Caches result to avoid repeated subprocess calls.
        """
        import time
        now = time.time()
        if hasattr(self, '_version_cache') and (now - self._version_cache_time) < 300:
            return self._version_cache
        try:
            # Find hermes binary — check HERMES_HOME/bin, then PATH
            hermes_home_bin = self._hermes_home / "bin"
            hermes_bin = None
            for candidate in [hermes_home_bin / "hermes", Path("/usr/local/bin/hermes"),
                               Path.home() / ".local" / "bin" / "hermes"]:
                if candidate.exists():
                    hermes_bin = str(candidate)
                    break
            if not hermes_bin:
                raise FileNotFoundError("hermes binary not found")
            result = subprocess.run(
                [hermes_bin, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                # Parse "Hermes Agent v0.11.0 (2026.4.23)" — first line only
                version_line = result.stdout.strip().split('\n')[0]
                import re
                # Format: "Hermes Agent vVERSION (DATE)" — date is inside ()
                m = re.search(r'Hermes Agent v(.+?) \((.+?)\)', version_line)
                if m:
                    self._version_cache = {"version": m.group(1).strip(), "release_date": m.group(2).strip()}
                else:
                    self._version_cache = {"version": version_line, "release_date": "unknown"}
            else:
                self._version_cache = {"version": "unknown", "release_date": "unknown"}
        except Exception:
            self._version_cache = {"version": "unknown", "release_date": "unknown"}
        self._version_cache_time = now
        return self._version_cache

    async def get_full_context(self) -> dict:
        """Aggregate everything Hermes knows as a single context dump."""
        try:
            status = await self.get_status()
        except Exception:
            status = None
        try:
            crons = await self.get_cron_jobs()
        except Exception:
            crons = []
        try:
            sessions = await self.get_active_sessions()
        except Exception:
            sessions = []
        return {
            "status": asdict(status) if status else {},
            "cron_jobs": [asdict(j) for j in crons],
            "toolsets": [],
            "skills": [],
            "model": {"model": "MiniMax-M2.7", "provider": "minimax"},
            "sessions": sessions,
        }

    async def get_active_sessions(self) -> list[dict]:
        """
        Return the most recent sessions across all platforms.
        Reads sessions.json as the index, then enriches with recent message count.
        """
        sessions_file = self._hermes_home / "sessions" / "sessions.json"
        if not sessions_file.exists():
            return []

        try:
            index = json.loads(sessions_file.read_text())
        except Exception:
            return []

        result = []
        for key, info in index.items():
            # Parse key: 'agent:main:platform:channel_type:channel_id'
            parts = key.split(":")
            platform = parts[2] if len(parts) >= 3 else "?"
            session_id = info.get("session_id", "")
            # Find the session file
            session_file = self._hermes_home / "sessions" / f"session_{session_id}.json"
            msg_count = 0
            if session_file.exists():
                try:
                    with session_file.open() as f:
                        s = json.load(f)
                        msg_count = s.get("message_count", 0)
                except Exception:
                    pass
            result.append({
                "key": key,
                "platform": platform,
                "session_id": session_id,
                "display_name": info.get("display_name", key),
                "created_at": info.get("created_at", ""),
                "updated_at": info.get("updated_at", ""),
                "message_count": msg_count,
                "total_tokens": info.get("total_tokens", 0),
                "input_tokens": info.get("input_tokens", 0),
                "output_tokens": info.get("output_tokens", 0),
            })

        # Sort by updated_at desc
        result.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return result[:10]  # top 10 recent

    async def get_briefing(self) -> dict:
        """
        Morning briefing: get the latest morning briefing cron run output
        and the most recent conversations across platforms.
        Returns a synthesized summary of what's been happening.
        """
        briefing = {
            "morning_briefing": None,
            "recent_conversations": [],
            "pending_crons": [],
            "system_state": {},
        }

        # Find most recent morning briefing session
        sessions_dir = self._hermes_home / "sessions"
        if sessions_dir.exists():
            cron_sessions = [
                f for f in sessions_dir.iterdir()
                if f.is_file() and f.name.startswith("session_cron_")
            ]
            # Sort by mtime desc
            cron_sessions.sort(key=lambda x: x.stat().st_mtime, reverse=True)

            # Look for morning briefing in recent cron sessions
            for session_file in cron_sessions[:8]:
                try:
                    with session_file.open() as f:
                        data = json.load(f)
                        msgs = data.get("messages", [])
                        if msgs:
                            # Get last assistant message as the briefing
                            for m in reversed(msgs):
                                if m.get("role") == "assistant":
                                    content = m.get("content", "")
                                    # Skip very short messages (likely not a briefing)
                                    if len(content) > 200:
                                        briefing["morning_briefing"] = {
                                            "session_id": data.get("session_id", session_file.stem),
                                            "message_count": data.get("message_count", 0),
                                            "preview": content[:500],
                                        }
                                        break
                    if briefing["morning_briefing"]:
                        break
                except Exception:
                    continue

        # Get pending cron jobs (enabled + next_run is soon)
        try:
            crons = await self.get_cron_jobs()
            now = datetime.now()
            briefing["pending_crons"] = [
                {"id": j.id, "name": j.name, "next_run": j.next_run, "schedule": j.schedule}
                for j in crons
                if j.enabled and j.next_run
            ]
        except Exception:
            pass

        return briefing

    # ── OpenAI-compatible API server (port 8642) ────────────────────────────────

    def _api_server_base(self) -> str:
        """OpenAI-compatible API server base URL."""
        return self.api_base

    async def ask(self, prompt: str, stream: bool = False) -> dict:
        """
        Send a prompt to Hermes via the OpenAI-compatible API server.
        Returns the full response dict. If stream=True, returns the chunks iterator.
        """
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                self._api_server_base() + "/v1/chat/completions",
                json={
                    "model": "hermes-agent",
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": stream,
                },
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            if stream:
                # Use aiter_bytes() + manual decoding to avoid httpx's aiter_lines()
                # buffering issue (it chunks reads, which can split SSE \n\n delimiters).
                return self._stream_lines(resp)
            return resp.json()

    async def _stream_lines(self, response):
        """
        Yield individual lines from a streaming HTTP response, properly handling
        SSE delimiters across network chunk boundaries.

        SSE events are separated by double newlines (\n\n).
        Each event line starts with "data: ". The final event is "data: [DONE]".
        """
        buffer = b""
        async for chunk in response.aiter_bytes(chunk_size=128):
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                decoded = line.decode("utf-8", errors="replace")
                yield decoded

    async def ask_stream(self, prompt: str):
        """Yield SSE chunks from the API server for a streaming response."""
        async for line in await self.ask(prompt, stream=True):
            if line.startswith("data: "):
                yield line[6:]
            elif line.strip() == "data: [DONE]":
                break

    # ── Knowledge Graph ─────────────────────────────────────────────────────────
    # Reads the SQLite memory_store to construct a force-directed graph of
    # entities and facts. Powers the 🧠 Knowledge Graph panel.

    def get_knowledge_graph(self) -> dict:
        """
        Build nodes + edges from memory_store.db.
        Nodes = entities. Edges = facts linking entities.
        Returns {nodes: [{id, name, type}], edges: [{source, target, label}]}
        """
        db_path = self._hermes_home / "memory_store.db"
        if not db_path.exists():
            return {"nodes": [], "edges": []}

        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()

            # Nodes: all entities
            cur.execute("SELECT entity_id, name, entity_type FROM entities")
            nodes = [
                {"id": str(row[0]), "name": row[1], "type": row[2] or "concept"}
                for row in cur.fetchall()
            ]

            # Edges: facts link entity pairs
            # Each fact may reference multiple entities — build edge per pair
            cur.execute("""
                SELECT fe.fact_id, fe.entity_id, e.name, f.content, f.category
                FROM fact_entities fe
                JOIN entities e ON fe.entity_id = e.entity_id
                JOIN facts f ON fe.fact_id = f.fact_id
                ORDER BY fe.fact_id
            """)
            rows = cur.fetchall()

            # Group by fact_id to find entity pairs within each fact
            from collections import defaultdict
            fact_to_entities = defaultdict(list)
            fact_meta = {}
            for fact_id, entity_id, entity_name, content, category in rows:
                fact_to_entities[fact_id].append((str(entity_id), entity_name))
                if fact_id not in fact_meta:
                    fact_meta[fact_id] = (content[:120], category)

            edges = []
            for fact_id, entities in fact_to_entities.items():
                if len(entities) >= 2:
                    # Connect consecutive entity pairs in this fact
                    for i in range(len(entities) - 1):
                        src, src_name = entities[i]
                        dst, dst_name = entities[i + 1]
                        content_preview, category = fact_meta.get(fact_id, ("", ""))
                        edges.append({
                            "source": src,
                            "target": dst,
                            "label": category or "related",
                            "fact_preview": content_preview,
                        })
                elif len(entities) == 1:
                    # Single entity self-link (for orphan facts)
                    src, src_name = entities[0]
                    content_preview, category = fact_meta.get(fact_id, ("", ""))
                    edges.append({
                        "source": src,
                        "target": src,
                        "label": category or "mentioned",
                        "fact_preview": content_preview,
                    })

            conn.close()
            return {"nodes": nodes, "edges": edges}
        except Exception as e:
            return {"nodes": [], "edges": [], "error": str(e)}

    # ── Paperclip Integration ──────────────────────────────────────────────────
    # Queries the Paperclip API directly for issues + goals.
    # Paperclip API runs at http://10.87.1.201:3100 (this machine is ai-ass).
    # Auth: session cookie from the skill (read-only, no key needed).

    def _paperclip_request(self, path: str) -> dict:
        """Make a request to the Paperclip API."""
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        cookie = "better-auth.session_token=iJW6zFDvP0jX7z1vVufpinFMwxkOqi3X.0LUSgbjWxBgwpKKtF8xTRdNE5gqD6ek5aOHOWs8wDM4%3D"
        base_ip = "10.87.1.201"
        url = f"http://{base_ip}:3100{path}"
        req = urllib.request.Request(url)
        req.add_header("Origin", f"http://{base_ip}:3100")
        req.add_header("Cookie", cookie)
        try:
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            return {"error": str(e)}

    def get_paperclip_issues(self, status: str = "") -> list[dict]:
        """
        Get issues from Paperclip API.
        status param: "open", "blocked", "in_progress" or comma-separated list.
        Returns list of issues sorted by updated_at desc.
        """
        company_id = "b4eab370-3bf1-4b21-8272-89b2157d9068"
        if status:
            path = f"/api/companies/{company_id}/issues?status={status}&limit=50"
        else:
            path = f"/api/companies/{company_id}/issues?limit=50"
        data = self._paperclip_request(path)
        if isinstance(data, dict) and "error" in data:
            return []
        # API returns a JSON list directly
        if not isinstance(data, list):
            return []
        # Sort by updatedAt desc
        data.sort(key=lambda x: x.get("updatedAt", ""), reverse=True)
        return data[:20]

    def get_paperclip_goals(self) -> list[dict]:
        """
        Get goals from Paperclip API.
        Returns list of goals with their current status.
        """
        company_id = "b4eab370-3bf1-4b21-8272-89b2157d9068"
        data = self._paperclip_request(f"/api/companies/{company_id}/goals")
        if isinstance(data, dict) and "error" in data:
            return []
        if not isinstance(data, list):
            return []
        return data[:20]

    # ── Skills Catalog ─────────────────────────────────────────────────────────
    # Scans ~/.hermes/skills/<name>/SKILL.md for metadata + descriptions.
    # Used by the Command Palette to surface all available actions.

    def get_skills_catalog(self) -> list[dict]:
        """
        Return all skills as [{name, description, tags, trigger, owner}].
        Reads frontmatter from each SKILL.md.
        """
        skills_dir = self._hermes_home / "skills"
        if not skills_dir.exists():
            return []

        catalog = []
        for skill_path in skills_dir.iterdir():
            if not skill_path.is_dir():
                continue
            skill_md = skill_path / "SKILL.md"
            if not skill_md.exists():
                continue

            try:
                content = skill_md.read_text(errors="replace")
                meta = {}
                lines = content.split("\n")
                in_fm = False
                fm_lines = []
                for line in lines:
                    if line.strip() == "---":
                        if in_fm:
                            for fl in fm_lines:
                                if ":" in fl:
                                    k, v = fl.split(":", 1)
                                    meta[k.strip()] = v.strip()
                            break
                        in_fm = True
                    elif in_fm:
                        fm_lines.append(line)

                # Extract description: first non-frontmatter line after ## name heading
                desc = meta.get("description", "")
                # Try to find the first trigger section
                trigger = ""
                if "## Trigger" in content:
                    trig_section = content.split("## Trigger")[1].split("##")[0]
                    # Get first 200 chars of trigger section
                    trigger = trig_section.strip()[:200].replace("\n", " ")

                catalog.append({
                    "name": skill_path.name,
                    "description": desc,
                    "tags": meta.get("tags", ""),
                    "trigger": trigger,
                    "owner": meta.get("owner", ""),
                    "version": meta.get("version", ""),
                })
            except Exception:
                continue

        catalog.sort(key=lambda x: x["name"])
        return catalog

    # ── Session History Search ─────────────────────────────────────────────────
    # Uses Hermes's own FTS5 index on state.db for full-text search.
    # Returns matching messages with session context.

    def search_history(self, query: str, limit: int = 10) -> list[dict]:
        """
        Full-text search across all conversation history.
        Uses FTS5 on state.db — the same index Hermes uses.
        Returns top matches with session context and timestamp.
        """
        db_path = self._hermes_home / "state.db"
        if not db_path.exists() or not query.strip():
            return []

        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()

            # FTS5 search across messages
            # Use the FTS5 virtual table (messages_fts)
            cur.execute("""
                SELECT m.id, m.session_id, m.role, m.content, m.timestamp,
                       s.source, s.title
                FROM messages_fts f
                JOIN messages m ON m.id = f.rowid
                LEFT JOIN sessions s ON m.session_id = s.id
                WHERE messages_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (query + "*", limit))

            results = []
            for row in cur.fetchall():
                msg_id, session_id, role, content, timestamp, source, title = row
                if content and len(content) > 500:
                    # Truncate long content
                    content = content[:400] + "..."
                results.append({
                    "id": msg_id,
                    "session_id": session_id,
                    "role": role,
                    "content": content,
                    "timestamp": timestamp,
                    "source": source or "unknown",
                    "title": title or session_id or "",
                })

            conn.close()
            return results
        except Exception as e:
            return [{"error": str(e), "query": query}]
