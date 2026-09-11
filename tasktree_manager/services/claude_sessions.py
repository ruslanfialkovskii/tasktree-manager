"""Read the recap of a task's latest Claude Code session from its transcript.

Claude Code appends to ``<config>/projects/<encoded cwd>/<session>.jsonl`` as
a session runs. The tail of that file carries what the terminal shows after
a turn: a ``system/turn_duration`` record ("Baked for 45s · done 5:27 PM")
and, when the session idles long enough, a ``system/away_summary`` record
(the "※ recap:" line). Title latches (``custom-title``, ``ai-title``,
``agent-name``) and ``last-prompt`` are rewritten near the end on every turn.

Only the tail is read, newest line first, so a multi-megabyte transcript
costs one bounded read regardless of its length.
"""

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, tzinfo
from pathlib import Path

from .claude_hooks import project_dir_candidates

RECAP_SUFFIX = "(disable recaps in /config)"
TAIL_WINDOW = 1 << 20
TAIL_WINDOW_RETRY = 4 << 20
# Turns that span a laptop sleep report days of "duration"; anything above
# an hour is noise rather than work time
DURATION_CAP_MS = 3_600_000
LAST_PROMPT_MAX = 200

# Cheap substring gate so multi-hundred-KB tool-result lines are never parsed
_NEEDLES = (
    b'"turn_duration"',
    b'"away_summary"',
    b'"custom-title"',
    b'"ai-title"',
    b'"agent-name"',
    b'"last-prompt"',
)
_TITLE_KEYS = {
    "custom-title": ("custom_title", "customTitle"),
    "ai-title": ("ai_title", "aiTitle"),
    "agent-name": ("agent_name", "agentName"),
    "last-prompt": ("last_prompt", "lastPrompt"),
}


@dataclass(frozen=True)
class ClaudeRecap:
    """What the latest Claude session in a folder last did."""

    title: str
    duration_ms: int | None
    finished_at: datetime | None  # tz-aware UTC
    summary: str | None  # away_summary content, marketing suffix stripped
    last_prompt: str | None


def transcript_key(folder: Path) -> tuple[Path, int, int] | None:
    """Return ``(path, mtime_ns, size)`` of the newest transcript for a folder.

    One ``scandir`` per candidate project dir and no file reads, so callers
    can poll it to detect changes cheaply.
    """
    newest: tuple[int, int, Path] | None = None
    for project_dir in project_dir_candidates(folder):
        try:
            entries = list(os.scandir(project_dir))
        except OSError:
            continue
        for entry in entries:
            try:
                if not entry.name.endswith(".jsonl") or not entry.is_file():
                    continue
                stat = entry.stat()
            except OSError:
                # Claude prunes old transcripts at startup; one can vanish
                # between the scandir and the stat
                continue
            candidate = (stat.st_mtime_ns, stat.st_size, Path(entry.path))
            if newest is None or candidate[0] > newest[0]:
                newest = candidate
    if newest is None:
        return None
    mtime_ns, size, path = newest
    return path, mtime_ns, size


def read_claude_recap(path: Path) -> ClaudeRecap | None:
    """Read the recap from one transcript (see ``transcript_key`` to pick it)."""
    try:
        lines, truncated = _tail_lines(path, TAIL_WINDOW)
        found = _scan(lines)
        if "duration_ms" not in found and truncated:
            lines, _ = _tail_lines(path, TAIL_WINDOW_RETRY)
            found = _scan(lines)
    except OSError:
        return None

    summary = found.get("summary")
    last_prompt = found.get("last_prompt")
    duration_ms = found.get("duration_ms")
    if summary is None and last_prompt is None and duration_ms is None:
        return None

    title = (
        found.get("custom_title")
        or found.get("ai_title")
        or found.get("agent_name")
        or found.get("slug")
        or path.stem[:8]
    )
    return ClaudeRecap(
        title=title,
        duration_ms=duration_ms,
        finished_at=_parse_timestamp(found.get("finished_at")),
        summary=summary,
        last_prompt=last_prompt,
    )


def format_duration(ms: int) -> str:
    """Render a turn duration the way Claude's terminal does: 45s, 3m 12s."""
    if ms > DURATION_CAP_MS:
        return ">1h"
    seconds = max(0, ms // 1000)
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60}s"


def format_clock(dt: datetime, tz: tzinfo | None = None) -> str:
    """Render a wall-clock time as 5:27 PM in ``tz`` (local time by default)."""
    # %-I is not portable (Windows); strip the pad by hand instead
    return dt.astimezone(tz).strftime("%I:%M %p").lstrip("0")


def strip_recap_suffix(text: str) -> str:
    """Drop the "(disable recaps in /config)" hint Claude appends to recaps."""
    return text.strip().removesuffix(RECAP_SUFFIX).rstrip()


def _tail_lines(path: Path, window: int) -> tuple[list[bytes], bool]:
    """Return the last ``window`` bytes as whole lines, newest first.

    The second element says whether the file extends beyond the window
    (so a caller can retry with a bigger one).
    """
    with path.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        offset = max(0, fh.tell() - window)
        fh.seek(offset)
        data = fh.read()
    lines = data.split(b"\n")
    if offset > 0:
        # The first chunk is a partial line cut by the seek
        lines = lines[1:]
    # The final line may be one Claude is still writing; it fails to parse
    # and is skipped like any other bad line
    return [line for line in reversed(lines) if line.strip()], offset > 0


def _scan(lines: list[bytes]) -> dict:
    """Collect recap fields from transcript lines ordered newest first."""
    found: dict = {}
    turn_seen = False
    for raw in lines:
        if not any(needle in raw for needle in _NEEDLES):
            continue
        try:
            record = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue

        rtype = record.get("type")
        if rtype == "system":
            subtype = record.get("subtype")
            if subtype == "turn_duration":
                if "duration_ms" not in found:
                    found["duration_ms"] = _as_int(record.get("durationMs"))
                    found["finished_at"] = _as_text(record.get("timestamp"))
                turn_seen = True
            elif subtype == "away_summary" and not turn_seen and "summary" not in found:
                # A recap older than the latest turn describes a state that
                # has since moved on; only accept one newer than the turn
                content = _as_text(record.get("content"))
                if content:
                    found["summary"] = strip_recap_suffix(content)
        elif rtype in _TITLE_KEYS:
            field, source = _TITLE_KEYS[rtype]
            value = _as_text(record.get(source))
            if value and field not in found:
                found[field] = _shorten_prompt(value) if field == "last_prompt" else value

        slug = _as_text(record.get("slug"))
        if slug and "slug" not in found:
            found["slug"] = slug

        if all(key in found for key in ("duration_ms", "last_prompt", "custom_title")):
            break
    return found


def _as_int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _as_text(value) -> str | None:
    """Return transcript text made safe for the terminal, or None if empty.

    Transcript strings are model- or user-authored: control characters
    (ESC and friends) would reach the terminal verbatim through Rich, so
    they are dropped and whitespace is folded to single spaces.
    """
    if not isinstance(value, str):
        return None
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", "", value)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _shorten_prompt(text: str) -> str:
    if len(text) > LAST_PROMPT_MAX:
        text = text[: LAST_PROMPT_MAX - 1].rstrip() + "…"
    return text


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
