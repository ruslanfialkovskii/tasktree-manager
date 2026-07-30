"""Claude Code agent session discovery via `claude agents --json`.

Probed against claude CLI (July 2026): the payload is a JSON list of
sessions shaped like

    {"pid": 6640, "cwd": "/Users/x/wtasks/TASK/repo", "kind": "interactive",
     "startedAt": 1785237108134, "sessionId": "...", "name": "...",
     "status": "idle"}

with observed ``status`` values "idle" and "busy". Parsing is tolerant:
alternate field names and unknown statuses must not break the poll loop,
and any failure returns None ("source unavailable") rather than raising.

Dispatching uses ``claude --bg -n <name> "<prompt>"`` with cwd set to the
target worktree (the cwd becomes the session's project directory).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Raw status vocabulary -> normalized badge state
_STATUS_MAP = {
    "busy": "working",
    "working": "working",
    "running": "working",
    "in_progress": "working",
    "needs_input": "needs_input",
    "waiting_input": "needs_input",
    "waiting": "needs_input",
    "blocked": "needs_input",
    "permission": "needs_input",
    "idle": "ready",
    "ready": "ready",
    "done": "ready",
    "completed": "ready",
    "finished": "ready",
}

# When several sessions run in one worktree, the most urgent state wins
_STATUS_PRECEDENCE = {"needs_input": 0, "working": 1, "ready": 2}

_DIRECTORY_KEYS = ("cwd", "directory", "workdir", "projectPath", "path")
_STATUS_KEYS = ("status", "state")


@dataclass
class AgentSession:
    """One Claude Code session as reported by `claude agents --json`."""

    directory: Path  # resolved
    status: str  # normalized: "working" | "needs_input" | "ready"
    session_id: str = ""
    name: str = ""


def run_claude_agents(claude_path: str, timeout: float = 5.0) -> str | None:
    """Run `claude agents --json`; stdout on success, None on any failure."""
    try:
        result = subprocess.run(
            [claude_path, "agents", "--json"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def parse_agent_sessions(payload: str) -> list[AgentSession] | None:
    """Parse the agents payload tolerantly; None means unparseable."""
    try:
        data = json.loads(payload)
    except ValueError:
        return None
    if isinstance(data, dict):
        # Accept a future wrapper, but only under a known key — grabbing an
        # arbitrary list-valued key could pick a sibling like "errors": []
        # and silently clear every badge while agents are running
        for key in ("agents", "sessions"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            return None
    if not isinstance(data, list):
        return None

    sessions = []
    for record in data:
        if not isinstance(record, dict):
            continue
        directory = next(
            (record[key] for key in _DIRECTORY_KEYS if isinstance(record.get(key), str)),
            None,
        )
        raw_status = next(
            (record[key] for key in _STATUS_KEYS if isinstance(record.get(key), str)),
            None,
        )
        # Empty cwd would resolve to our own CWD and pin a phantom badge;
        # unknown statuses (dead/exited sessions) must not render as working
        if not directory or raw_status is None:
            continue
        status = _STATUS_MAP.get(raw_status.lower())
        if status is None:
            continue
        sessions.append(
            AgentSession(
                directory=Path(directory).resolve(),
                status=status,
                session_id=str(record.get("sessionId", "")),
                name=str(record.get("name", "")),
            )
        )
    return sessions


def list_agent_sessions(claude_path: str = "claude") -> list[AgentSession] | None:
    """Fetch and parse the current sessions; None = source unavailable."""
    payload = run_claude_agents(claude_path)
    if payload is None:
        return None
    return parse_agent_sessions(payload)


def map_sessions_to_worktrees(
    sessions: list[AgentSession], worktree_paths: list[str]
) -> dict[str, str]:
    """Map worktree path -> normalized session status.

    A session belongs to a worktree when its directory equals the worktree
    path or is nested under it (macOS /tmp vs /private/tmp is handled by
    resolving both sides). Multiple sessions collapse to the most urgent
    state: needs_input > working > ready.
    """
    resolved = {path: Path(path).resolve() for path in worktree_paths}
    states: dict[str, str] = {}
    for session in sessions:
        for original, resolved_path in resolved.items():
            if session.directory == resolved_path or session.directory.is_relative_to(
                resolved_path
            ):
                current = states.get(original)
                if (
                    current is None
                    or _STATUS_PRECEDENCE[session.status] < _STATUS_PRECEDENCE[current]
                ):
                    states[original] = session.status
    return states
