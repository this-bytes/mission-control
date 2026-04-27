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
        result = self._run_hermes(["cron", "run", job_id], timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"Cron run failed: {result.stderr.strip()}")
        return {"ok": True, "job_id": job_id, "output": result.stdout.strip()}

    # ── Cron CRUD ─────────────────────────────────────────────────────────────

    def create_cron(self, name: str, prompt: str, schedule: str,
                    skills: list[str] = None, deliver: str = "origin") -> dict:
        """
        Create a new cron job via hermes CLI.
        Returns {ok, job_id, name} or raises RuntimeError.
        """
        skills = skills or []
        cmd = ["cron", "create",
               "--name", name,
               "--schedule", schedule,
               "--deliver", deliver,
               "--prompt", prompt]
        for s in skills:
            cmd += ["--skill", s]
        result = self._run_hermes(cmd, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"Cron create failed: {result.stderr.strip()}")
        # Parse job ID from output: "Created cron job: ID NAME"
        output = result.stdout.strip()
        job_id = ""
        for line in output.splitlines():
            line = line.strip()
            # Look for a hex ID like "abc123def..."
            import re
            m = re.search(r'\b([0-9a-f]{10,})\b', line)
            if m:
                job_id = m.group(1)
                break
        return {"ok": True, "job_id": job_id, "name": name, "output": output}

    def update_cron(self, job_id: str, enabled: bool = None,
                    name: str = None, schedule: str = None,
                    prompt: str = None, deliver: str = None,
                    skills: list[str] = None) -> dict:
        """
        Update an existing cron job via hermes CLI.
        At least one field must be provided.
        """
        cmd = ["cron", "update", job_id]
        if enabled is not None:
            cmd += ["--enabled" if enabled else "--disabled"]
        if name is not None:
            cmd += ["--name", name]
        if schedule is not None:
            cmd += ["--schedule", schedule]
        if prompt is not None:
            cmd += ["--prompt", prompt]
        if deliver is not None:
            cmd += ["--deliver", deliver]
        if skills is not None:
            cmd += ["--skills", ",".join(skills)]
        result = self._run_hermes(cmd, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"Cron update failed: {result.stderr.strip()}")
        return {"ok": True, "job_id": job_id, "output": result.stdout.strip()}

    def delete_cron(self, job_id: str) -> dict:
        """Delete a cron job via hermes CLI."""
        result = self._run_hermes(["cron", "delete", job_id], timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"Cron delete failed: {result.stderr.strip()}")
        return {"ok": True, "job_id": job_id}

    def _run_hermes(self, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
        """Run a hermes CLI command and return the result."""
        # Find hermes binary
        hermes_bin = self._find_hermes_bin()
        return subprocess.run(
            [hermes_bin] + args,
            capture_output=True, text=True, timeout=timeout,
            env={**subprocess.os.environ, "HERMES_HOME": str(self._hermes_home)}
        )

    def _find_hermes_bin(self) -> str:
        """Locate the hermes binary."""
        candidates = [
            self._hermes_home / "bin" / "hermes",
            Path("/usr/local/bin/hermes"),
            Path.home() / ".local" / "bin" / "hermes",
            Path("/usr/bin/hermes"),
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        # Fallback: trust it's on PATH
        return "hermes"

    # ── Cron Intelligence ─────────────────────────────────────────────────────
    # Gap analysis, coverage scoring, topology mapping, recommendations.
    # Adapted from gap-finder-cron-evolver.py logic but returns structured data.

    # Category schema: what good ops coverage looks like (fitness excluded — Arnold's domain)
    CATEGORY_SCHEMAS = {
        "ops": {
            "description": "Homelab / infrastructure monitoring",
            "required_slots": [
                ("morning_health",      "weekday_morning",    "0 5,6 * * 1-5"),
                ("midday_health",       "any_midday",          "0 14,15 * * *"),
                ("evening_health",       "evening",             "0 20,21 * * *"),
                ("weekend_health",       "weekend_morning",     "0 9,10 * * 0,6"),
            ],
        },
        "memory": {
            "description": "Memory, context, and wiki maintenance",
            "required_slots": [
                ("context_maintenance", "regular_interval",  "0 */4 * * *"),
                ("conversation_arch",   "three_times_daily", "0 6,14,22 * * *"),
                ("memory_absorber",     "regular_interval",  "0 */3 * * *"),
                ("wiki_archaeology",    "weekly",            "0 10 * * 0"),
            ],
        },
        "creative": {
            "description": "Creative inspiration, blog, and learning",
            "required_slots": [
                ("daily_surprise",    "daily_morning",     "0 9 * * *"),
                ("blog_pipeline",     "evening",           "0 20 * * *"),
                ("weekly_project",    "friday_afternoon",   "0 15 * * 5"),
            ],
        },
        "self_improvement": {
            "description": "Maxi's own capability improvement",
            "required_slots": [
                ("iterate_pulse",          "regular",      "0 */4 * * *"),
                ("mission_control_iter",   "hourly",       "every 60m"),
                ("proactive_discovery",    "six_hour",     "0 */6 * * *"),
                ("skill_health",            "three_times_daily", "0 8,12,18 * * *"),
                ("gap_finder",              "daily",        "0 7 * * *"),
            ],
        },
        "paperclip": {
            "description": "Paperclip AI company agent orchestration",
            "required_slots": [
                ("paperclip_morning_health", "morning", "0 9 * * *"),
                ("paperclip_evening_health", "evening", "0 21 * * *"),
            ],
        },
        "briefings": {
            "description": "Aaron's daily briefings",
            "required_slots": [
                ("morning_briefing", "morning_early", "0 21 * * *"),
                ("evening_wrapup",  "late_night",    "0 1 * * *"),
                ("weekly_pulse",    "monday",        "0 0 * * 1"),
            ],
        },
    }

    def _slot_to_hours(self, slot_expr: str) -> list[int]:
        """Convert cron expr to list of integer hours."""
        if slot_expr in ("every 60m", "every 15m"):
            return list(range(24))
        parts = slot_expr.split()
        if len(parts) < 2:
            return []
        hour_part = parts[1]
        hours = []
        for seg in hour_part.split(","):
            if "-" in seg:
                start, end = map(int, seg.split("-"))
                hours.extend(range(start, end + 1))
            elif seg == "*":
                hours.extend(range(24))
            else:
                try:
                    hours.append(int(seg))
                except ValueError:
                    pass
        return sorted(set(hours))

    def _job_matches_slot(self, job: dict, slot_hours: list,
                          weekdays_required: list[int] = None) -> bool:
        """Check if a cron job covers a required time slot."""
        sched = job.get("schedule", "")
        if sched in ("every 60m", "every 15m", "every 30m"):
            return True
        hours = self._slot_to_hours(sched)
        if not hours or not set(hours) & set(slot_hours):
            return False
        if weekdays_required:
            day_part = sched.split()[3] if len(sched.split()) > 3 else "*"
            if day_part == "*":
                return True
            job_days = set()
            for seg in day_part.split(","):
                if "-" in seg:
                    s, e = map(int, seg.split("-"))
                    job_days.update(range(s, e + 1))
                else:
                    try:
                        job_days.add(int(seg))
                    except ValueError:
                        pass
            if not job_days & set(weekdays_required):
                return False
        return True

    def _infer_category(self, job: dict) -> str:
        """Infer the operational category of a cron job from its name + prompt."""
        name = job.get("name", "").lower()
        prompt = job.get("prompt_preview", "").lower()

        signals = {
            "ops": ["health", "homelab", "disk", "docker", "server", "uptime", "ping"],
            "memory": ["memory", "session", "context", "wiki", "fact", "learn"],
            "creative": ["blog", "creative", "ideation", "surprise", "project"],
            "self_improvement": ["iterate", "improve", "gap", "skill", "pulse", "mission-control"],
            "paperclip": ["paperclip", "agent", "ceo", "gilfoyle", "dinesh", "jarvis"],
            "briefings": ["briefing", "wrapup", "morning", "evening", "weekly", "pulse"],
        }

        text = f"{name} {prompt}"
        scores = {}
        for cat, keywords in signals.items():
            scores[cat] = sum(1 for kw in keywords if kw in text)

        if max(scores.values()) == 0:
            return "other"
        return max(scores, key=scores.get)

    def _infer_edges(self, jobs: list[dict]) -> list[dict]:
        """
        Build adjacency edges between crons by analyzing prompt cross-references
        and temporal firing patterns (crons that fire within 60s of each other).
        Returns list of {source, target, label, type}.
        """
        edges = []
        name_map = {j["name"].lower(): j["id"] for j in jobs}

        for job in jobs:
            prompt = job.get("prompt_preview", "").lower()
            # Look for other cron names mentioned in prompt
            for other_job in jobs:
                if other_job["id"] == job["id"]:
                    continue
                other_name = other_job["name"].lower()
                # Skip very short names (too generic)
                if len(other_name) < 4:
                    continue
                if other_name in prompt:
                    edges.append({
                        "source": job["id"],
                        "target": other_job["id"],
                        "label": "calls",
                        "type": "explicit",
                    })

        # Deduplicate
        seen = set()
        deduped = []
        for e in edges:
            key = (e["source"], e["target"])
            if key not in seen:
                seen.add(key)
                deduped.append(e)
        return deduped

    def _generate_recommendations(self, jobs: list[dict], gaps: list[dict],
                                  orphans: list[dict], never_run: list[dict]) -> list[dict]:
        """Generate actionable recommendations based on analysis."""
        recs = []

        # HIGH: unfilled critical slots
        critical_slots = {"morning_health", "midday_health", "evening_health",
                          "weekend_health", "morning_briefing"}
        for gap in gaps:
            if gap["slot_key"] in critical_slots:
                recs.append({
                    "priority": "high",
                    "category": gap["category"],
                    "slot_key": gap["slot_key"],
                    "slot_desc": gap["slot_desc"],
                    "slot_expr": gap["slot_expr"],
                    "recommendation": f"No coverage for {gap['slot_desc']} ({gap['slot_expr']}).",
                    "action": "create",
                    "proposal": self._proposal_for_gap(gap),
                })

        # MEDIUM: non-critical gaps
        for gap in gaps:
            if gap["slot_key"] not in critical_slots:
                recs.append({
                    "priority": "medium",
                    "category": gap["category"],
                    "slot_key": gap["slot_key"],
                    "slot_desc": gap["slot_desc"],
                    "slot_expr": gap["slot_expr"],
                    "recommendation": f"Missing coverage: {gap['slot_desc']}.",
                    "action": "create",
                    "proposal": self._proposal_for_gap(gap),
                })

        # MEDIUM: orphans
        for orphan in orphans:
            recs.append({
                "priority": "medium",
                "category": "ops",
                "slot_key": "orphan",
                "slot_desc": orphan.get("name", "unnamed"),
                "slot_expr": orphan.get("schedule", ""),
                "recommendation": f"Orphaned cron '{orphan.get('name', '')}' has no skills attached — may fire without proper context.",
                "action": "attach_skills",
                "job_id": orphan.get("id"),
            })

        # MEDIUM: never-run
        for nr in never_run:
            recs.append({
                "priority": "medium",
                "category": "ops",
                "slot_key": "never_run",
                "slot_desc": nr.get("name", "unnamed"),
                "slot_expr": nr.get("schedule", ""),
                "recommendation": f"'{nr.get('name', '')}' is enabled but has never run — check schedule syntax or trigger it manually.",
                "action": "inspect",
                "job_id": nr.get("id"),
            })

        # LOW: delivery issues
        for job in jobs:
            deliver = job.get("deliver", "origin")
            if deliver == "origin":
                recs.append({
                    "priority": "low",
                    "category": "ops",
                    "slot_key": "delivery",
                    "slot_desc": job.get("name", ""),
                    "slot_expr": "",
                    "recommendation": f"'{job.get('name', '')}' delivers to 'origin' — consider routing to Telegram for async visibility.",
                    "action": "update_delivery",
                    "job_id": job.get("id"),
                })

        return recs

    def _proposal_for_gap(self, gap: dict) -> dict:
        """Generate a cron job proposal to fill a gap."""
        proposals = {
            "weekend_health":        {"name": "Weekend Morning Health Check", "schedule": "0 10 * * 0,6", "skills": ["anh-ops", "anh-ops-health", "anh-ops-wiki"], "deliver": "telegram:7705898692", "prompt": "Run the weekend morning health check. Load skills: anh-ops, anh-ops-health, anh-ops-wiki. Check homelab services, disk, Docker containers. Deliver a SHORT summary to Telegram — weekend edition."},
            "evening_health":        {"name": "Evening Ops Report", "schedule": "0 21 * * *", "skills": ["anh-ops", "anh-ops-health", "anh-ops-paperclip"], "deliver": "telegram:7705898692", "prompt": "Run the evening ops summary. Load skills: anh-ops, anh-ops-health, anh-ops-paperclip. Report homelab health, Paperclip agent status, any anomalies. Keep it brief."},
            "midday_health":         {"name": "Midday Health Check", "schedule": "0 14 * * *", "skills": ["anh-ops", "anh-ops-health"], "deliver": "telegram:7705898692", "prompt": "Run midday health check. Load skills: anh-ops, anh-ops-health. Check homelab services are healthy. Report a one-line status to Telegram."},
            "memory_absorber":       {"name": "Proactive Memory Absorber", "schedule": "0 */3 * * *", "skills": ["session_search"], "deliver": "origin", "prompt": "You are Maxi. Read the last 2 hours of your session history. Extract new facts about Aaron (preferences, projects, people, habits). Store important facts using the memory tool. Report what you absorbed."},
            "pending_digest":        {"name": "Pending Items Proactive Digest", "schedule": "0 10 * * *", "skills": ["anh-ops-wiki"], "deliver": "telegram:7705898692", "prompt": "Read /mnt/nas/software/docs/PENDING.md. Find items older than 3 days — flag as stale. Nudge Aaron if any item has been waiting >7 days. Format: brief stale items list with ages."},
            "paperclip_morning_health": {"name": "Paperclip Morning Health", "schedule": "0 9 * * *", "skills": ["anh-ops-paperclip", "paperclip-api-access"], "deliver": "telegram:7705898692", "prompt": "Check Paperclip agent team health. Use paperclip-api-access skill. Verify all agents are responding. Report any stuck agents to Telegram."},
            "weekly_project":         {"name": "Weekly Project Exploration", "schedule": "0 15 * * 5", "skills": ["session_search"], "deliver": "telegram:7705898692", "prompt": "You are Maxi. It's Friday afternoon. Review session history from this week — find unresolved ideas, half-finished projects, or creative threads. Present 2-3 actionable follow-ups."},
            "gap_finder":            {"name": "Gap-Finder & Cron Evolver", "schedule": "0 7 * * *", "skills": [], "deliver": "telegram:7705898692", "prompt": "Run gap-finder-cron-evolver: ~/.hermes/scripts/gap-finder-cron-evolver.py. Analyze all cron jobs, find coverage gaps, orphaned jobs, never-run jobs. Propose and auto-create high-confidence missing jobs."},
            "context_maintenance":    {"name": "Context Maintenance", "schedule": "0 */4 * * *", "skills": ["session_search"], "deliver": "origin", "prompt": "You are Maxi. Review recent sessions, update entity memory for any new facts about Aaron's projects or preferences. Use the memory tool to store notable findings."},
            "wiki_archaeology":      {"name": "Wiki Archaeology", "schedule": "0 10 * * 0", "skills": ["anh-ops-wiki"], "deliver": "telegram:7705898692", "prompt": "You are Maxi. Audit the wiki at /mnt/nas/software/docs/. Find outdated pages, broken links, or sections that need expansion. Report findings to Telegram."},
            "daily_surprise":        {"name": "Daily Creative Surprise", "schedule": "0 9 * * *", "skills": ["session_search"], "deliver": "telegram:7705898692", "prompt": "You are Maxi. Review recent sessions and facts. Find one specific, cool idea relevant to Aaron's current projects — something novel, not generic. Share it on Telegram."},
            "blog_pipeline":          {"name": "Blog Pipeline", "schedule": "0 20 * * *", "skills": ["session_search"], "deliver": "telegram:7705898692", "prompt": "You are Maxi. Run the blog pipeline. Find any half-written posts or new ideas in session history. Advance the most promising one. Report progress to Telegram."},
        }
        key = gap.get("slot_key", "")
        # Try exact match then partial
        if key in proposals:
            return proposals[key]
        for prefix in ("morning_", "midday_", "evening_", "weekend_"):
            if key.startswith(prefix) and prefix + "health" in proposals:
                return proposals[prefix + "health"]
        return {"name": f"Suggested: {gap['slot_key']}", "schedule": gap.get("slot_expr", "0 9 * * *"), "skills": [], "deliver": "telegram:7705898692", "prompt": f"Fill gap: {gap.get('slot_desc', gap['slot_key'])}"}

    async def get_cron_intel(self) -> dict:
        """
        Full cron intelligence: jobs, gaps, coverage, topology, recommendations.
        Combines gap-finder analysis with Mission Control's own topology mapping.
        """
        jobs = await self.get_cron_jobs()
        jobs_data = [j.__dict__ for j in jobs]

        # ── Gap Analysis ───────────────────────────────────────────────────────
        gaps = []
        for cat, schema in self.CATEGORY_SCHEMAS.items():
            for slot_key, slot_desc, slot_expr in schema["required_slots"]:
                slot_hours = self._slot_to_hours(slot_expr)
                weekdays_required = None
                if "1-5" in slot_expr:
                    weekdays_required = [1, 2, 3, 4, 5]
                elif "0,6" in slot_expr:
                    weekdays_required = [0, 6]

                covered = any(
                    self._job_matches_slot(j, slot_hours, weekdays_required)
                    for j in jobs_data
                    if j.get("enabled", False)
                )
                if not covered:
                    gaps.append({
                        "category": cat,
                        "slot_key": slot_key,
                        "slot_desc": slot_desc,
                        "slot_expr": slot_expr,
                        "reason": f"No job covers {slot_desc} ({slot_expr}) for {cat}",
                    })

        # ── Orphan & Never-Run Detection ──────────────────────────────────────
        orphans = [j for j in jobs_data if j.get("enabled") and not j.get("skills")]
        never_run = [j for j in jobs_data if j.get("enabled") and not j.get("last_run")]

        # ── Coverage Score ────────────────────────────────────────────────────
        total_slots = sum(len(s["required_slots"]) for s in self.CATEGORY_SCHEMAS.values())
        filled = total_slots - len(gaps)
        coverage_pct = round(filled / total_slots * 100) if total_slots > 0 else 100

        # ── Topology (nodes + edges) ──────────────────────────────────────────
        nodes = []
        for j in jobs_data:
            category = self._infer_category(j)
            # Size based on recency
            last_run = j.get("last_run", "")
            size = 6
            if last_run:
                try:
                    from datetime import datetime
                    lr = datetime.fromisoformat(last_run)
                    age_h = (datetime.now() - lr).total_seconds() / 3600
                    size = max(4, min(12, 10 - age_h * 0.3))
                except Exception:
                    size = 5

            nodes.append({
                "id": j["id"],
                "name": j["name"],
                "category": category,
                "size": size,
                "enabled": j.get("enabled", False),
                "last_status": j.get("last_status", ""),
                "schedule": j.get("schedule", ""),
            })

        edges = self._infer_edges(jobs_data)

        # ── Recommendations ────────────────────────────────────────────────────
        recommendations = self._generate_recommendations(jobs_data, gaps, orphans, never_run)

        # ── Category breakdown ────────────────────────────────────────────────
        categories = {}
        for cat, schema in self.CATEGORY_SCHEMAS.items():
            cat_jobs = [j for j in jobs_data if self._infer_category(j) == cat]
            cat_gaps = [g for g in gaps if g["category"] == cat]
            categories[cat] = {
                "description": schema["description"],
                "jobs": [{"id": j["id"], "name": j["name"], "last_status": j.get("last_status", ""),
                          "enabled": j.get("enabled", False)} for j in cat_jobs],
                "gaps": [g["slot_key"] for g in cat_gaps],
                "filled": len(schema["required_slots"]) - len(cat_gaps),
                "total": len(schema["required_slots"]),
            }

        return {
            "jobs": jobs_data,
            "coverage_pct": coverage_pct,
            "gaps": gaps,
            "orphans": [{"id": j["id"], "name": j["name"], "schedule": j.get("schedule", "")} for j in orphans],
            "never_run": [{"id": j["id"], "name": j["name"], "schedule": j.get("schedule", "")} for j in never_run],
            "nodes": nodes,
            "edges": edges,
            "recommendations": recommendations,
            "categories": categories,
        }

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

    async def get_active_sessions(self, q: str = "") -> list[dict]:
        """
        Return the most recent sessions across all platforms.
        Reads sessions.json as the index, then enriches with recent message count.
        If q is provided, filters by name (display_name/key) or message preview content.
        Returns up to 20 results (10 when no search, all matches when searching).
        """
        sessions_file = self._hermes_home / "sessions" / "sessions.json"
        if not sessions_file.exists():
            return []

        try:
            index = json.loads(sessions_file.read_text())
        except Exception:
            return []

        q_lower = q.lower().strip() if q else ""
        result = []
        for key, info in index.items():
            # Parse key: 'agent:main:platform:channel_type:channel_id'
            parts = key.split(":")
            platform = parts[2] if len(parts) >= 3 else "?"
            session_id = info.get("session_id", "")
            # Find the session file
            session_file = self._hermes_home / "sessions" / f"session_{session_id}.json"
            msg_count = 0
            msg_preview = ""
            if session_file.exists():
                try:
                    with session_file.open() as f:
                        s = json.load(f)
                        msg_count = s.get("message_count", 0)
                        # Grab first user message as preview for search
                        msgs = s.get("messages", [])
                        for m in msgs:
                            if m.get("role") == "user":
                                msg_preview = m.get("content", "")[:300]
                                break
                except Exception:
                    pass

            display_name = info.get("display_name", key)

            # Apply search filter
            if q_lower:
                name_match = q_lower in display_name.lower() or q_lower in key.lower()
                content_match = q_lower in msg_preview.lower()
                if not (name_match or content_match):
                    continue

            result.append({
                "key": key,
                "platform": platform,
                "session_id": session_id,
                "display_name": display_name,
                "created_at": info.get("created_at", ""),
                "updated_at": info.get("updated_at", ""),
                "message_count": msg_count,
                "total_tokens": info.get("total_tokens", 0),
                "input_tokens": info.get("input_tokens", 0),
                "output_tokens": info.get("output_tokens", 0),
                "last_prompt_tokens": info.get("last_prompt_tokens", 0),
                "msg_preview": msg_preview,  # included for search transparency
            })

        # Sort by updated_at desc
        result.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return result[:20 if q else 10]

    async def get_session_messages(self, session_id: str, limit: int = 8, offset: int = 0) -> dict:
        """
        Return 'limit' messages from a session file starting at 'offset'.
        Returns: {messages: [...], total: int}
        Each message: {role, content, timestamp}
        """
        session_file = self._hermes_home / "sessions" / f"session_{session_id}.json"
        if not session_file.exists():
            return {"messages": [], "total": 0}

        try:
            with session_file.open() as f:
                data = json.load(f)
            messages = data.get("messages", [])
            total = len(messages)
            # Slice from offset
            slice_ = messages[offset:offset + limit]
            recent = []
            for m in slice_:
                content = m.get("content", "")
                recent.append({
                    "role": m.get("role", "?"),
                    "content": content[:500] + ("..." if len(content) > 500 else ""),
                    "timestamp": m.get("timestamp", ""),
                })
            return {"messages": recent, "total": total, "offset": offset, "limit": limit}
        except Exception:
            return {"messages": [], "total": 0}

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

            # Look for morning briefing in recent cron sessions.
            # Scan up to 300 to handle heavy cron churn:
            # - Maxi Heartbeat fires every 15 min (~64 new sessions/day)
            # - mission-control-iterate fires hourly (~17 new sessions/day)
            # - Other crons fire every 5 min (~288 new sessions/day)
            # At 14:00 AEST the morning briefing (21:00 UTC prior day) sits at
            # position ~125 out of ~345 total cron sessions. 300 covers all cases.
            for session_file in cron_sessions[:300]:
                try:
                    with session_file.open() as f:
                        data = json.load(f)
                        msgs = data.get("messages", [])
                        if not msgs:
                            continue
                        # Root-cause fix: only accept sessions where the first user
                        # prompt explicitly invokes the morning-briefing skill.
                        # This excludes other crons (e.g. mission-control-iterate)
                        # whose sessions get a newer mtime.
                        first_user = next(
                            (m.get("content", "") for m in msgs if m.get("role") == "user"),
                            ""
                        )
                        # Accept if first user message invokes briefing-morning skill,
                        # OR if the session file belongs to the morning-briefing cron job.
                        is_briefing_session = (
                            '"briefing-morning"' in first_user
                            or "477d9b0fce90" in session_file.stem  # morning-briefing cron job
                        )
                        if not is_briefing_session:
                            continue
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

    # ── System Info ────────────────────────────────────────────────────────────
    # Returns live server metrics: CPU, memory, disk. Uses psutil.

    def get_system_info(self) -> dict:
        """
        Live server health: CPU %, memory %, disk %, uptime, load average.
        """
        import psutil
        from datetime import datetime

        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime_sec = (datetime.now() - boot_time).total_seconds()

        return {
            "cpu_percent": psutil.cpu_percent(interval=0.5),
            "cpu_count": psutil.cpu_count(),
            "load_avg": list(psutil.getloadavg()) if hasattr(psutil, "getloadavg") else [0, 0, 0],
            "memory_total_gb": round(mem.total / (1024 ** 3), 1),
            "memory_used_gb": round(mem.used / (1024 ** 3), 1),
            "memory_percent": mem.percent,
            "disk_total_gb": round(disk.total / (1024 ** 3), 1),
            "disk_used_gb": round(disk.used / (1024 ** 3), 1),
            "disk_percent": disk.percent,
            "uptime_sec": uptime_sec,
            "boot_time": boot_time.isoformat(),
        }

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
