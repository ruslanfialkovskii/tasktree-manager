"""Claude Code hook configuration for status monitoring."""

import json
from pathlib import Path


def _make_hook(status: str, status_file: str) -> dict:
    """Create a single hook entry that writes status to the given file path."""
    safe_path = status_file.replace("'", "'\\''")
    return {
        "type": "command",
        "command": f"printf '{{\"status\":\"{status}\",\"ts\":%d}}' $(date +%s) > '{safe_path}'",
        "async": True,
    }


def _build_hooks_config(task_path: Path) -> dict:
    """Build hooks config with absolute path to status file."""
    status_file = str(task_path / ".claude_status")
    return {
        "SessionStart": [{"hooks": [_make_hook("running", status_file)]}],
        "UserPromptSubmit": [{"hooks": [_make_hook("running", status_file)]}],
        "Stop": [{"hooks": [_make_hook("waiting", status_file)]}],
        "SessionEnd": [{"hooks": [_make_hook("ended", status_file)]}],
    }


def ensure_claude_hooks(task_path: Path) -> None:
    """Create .claude/settings.local.json with status-reporting hooks.

    Merges with existing settings if the file already exists, preserving
    user's own configuration while adding/updating the status hooks.
    """
    claude_dir = task_path / ".claude"
    claude_dir.mkdir(exist_ok=True)

    settings_file = claude_dir / "settings.local.json"

    if settings_file.exists():
        try:
            existing = json.loads(settings_file.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}
    else:
        existing = {}

    # Merge hooks into existing settings
    existing["hooks"] = _build_hooks_config(task_path)

    settings_file.write_text(json.dumps(existing, indent=2) + "\n")
