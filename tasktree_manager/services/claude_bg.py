"""Claude Code background sessions behind the TUI's Claude tabs.

The `c` key runs Claude as a `claude --bg` session and opens a tab that only
runs `claude attach ID`. Closing that tab ends the attach client, not the
session: Claude keeps working, and the next `c` attaches again with the same
conversation. A finished or stopped session reopens the same way.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path

from .agent_sessions import AgentSession, runs_in

BACKGROUND_KIND = "background"
# Ties a process to the Claude session that started it. A session launched
# with them counts as that session's child and saves no transcript
SESSION_ENV = (
    "CLAUDECODE",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_CHILD_SESSION",
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_MESSAGING_SOCKET",
    "CLAUDE_CODE_MESSAGING_TOKEN",
    "CLAUDE_CODE_SESSION_ATTENDED",
    "CLAUDE_CODE_EXECPATH",
    "CLAUDE_PLUGIN_DATA",
    "CLAUDE_PID",
    "CLAUDE_EFFORT",
)
_ATTACH_ID = re.compile(r"claude attach ([0-9a-f]{6,})")
_LAUNCH_TIMEOUT = 30
_CONTROL_TIMEOUT = 10


class BackgroundError(Exception):
    """`claude --bg` did not start a session; the message says why."""


def launch_env() -> dict[str, str]:
    """The user's environment without the launching Claude session's identity."""
    return {key: value for key, value in os.environ.items() if key not in SESSION_ENV}


def background_sessions(sessions: list[AgentSession], folder: Path) -> list[AgentSession]:
    """Background sessions in `folder` or below it, newest first."""
    root = folder.resolve()
    found = [s for s in sessions if s.kind == BACKGROUND_KIND and s.agent_id and runs_in(s, root)]
    return sorted(found, key=lambda s: s.started_at, reverse=True)


def folder_session(sessions: list[AgentSession], folder: Path) -> AgentSession | None:
    """The background session started in exactly `folder`: a busy one first, else the newest."""
    root = folder.resolve()
    exact = [s for s in background_sessions(sessions, root) if s.directory == root]
    return next((s for s in exact if s.status != "ready"), exact[0] if exact else None)


def foreground_session(sessions: list[AgentSession], folder: Path) -> AgentSession | None:
    """An ordinary (not background) session open in exactly `folder`."""
    root = folder.resolve()
    return next((s for s in sessions if s.kind != BACKGROUND_KIND and s.directory == root), None)


def busy(sessions: list[AgentSession]) -> list[AgentSession]:
    """Sessions working or waiting for an answer."""
    return [s for s in sessions if s.status != "ready"]


def start_background(
    claude_path: str, folder: Path, name: str, resume_id: str | None = None
) -> str:
    """Start a background session in `folder`, or resume `resume_id`; return its short id.

    No prompt is passed, so nothing runs until the user types. A resume takes
    no other flag: with one, Claude starts a copy under a new session ID.
    """
    argv = [claude_path, "--bg", *(["--resume", resume_id] if resume_id else ["-n", name])]
    try:
        result = subprocess.run(
            argv,
            cwd=folder,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=_LAUNCH_TIMEOUT,
            env=launch_env(),
        )
    except subprocess.TimeoutExpired as e:
        raise BackgroundError("claude --bg timed out") from e
    except OSError as e:
        raise BackgroundError(f"could not run {claude_path}: {e}") from e
    match = _ATTACH_ID.search(result.stdout)
    if result.returncode != 0 or not match:
        lines = (result.stderr.strip() or result.stdout.strip() or "no output").splitlines()
        raise BackgroundError(lines[-1][:200])
    return match.group(1)


def attach_command(claude_path: str, agent_id: str) -> str:
    """Shell command for a tab that shows the session; closing it leaves Claude running."""
    return f"{shlex.quote(claude_path)} attach {shlex.quote(agent_id)}"


def end_sessions(claude_path: str, sessions: list[AgentSession]) -> list[str]:
    """Stop and remove background sessions; return the ids that failed.

    Transcripts stay on disk, so a later `c` in the same folder can resume them.
    """
    failed = []
    for session in sessions:
        # A finished session may refuse `stop`; `rm` decides whether it is gone
        _control(claude_path, "stop", session.agent_id)
        if not _control(claude_path, "rm", session.agent_id):
            failed.append(session.agent_id)
    return failed


def _control(claude_path: str, command: str, agent_id: str) -> bool:
    """Run `claude stop|rm ID`; True on success."""
    try:
        result = subprocess.run(
            [claude_path, command, agent_id],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=_CONTROL_TIMEOUT,
            env=launch_env(),
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return result.returncode == 0
