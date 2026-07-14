"""Claude Code hook configuration for status monitoring."""

import json
from pathlib import Path


def _encode_project_path(folder: Path) -> str:
    """Encode a path the way Claude CLI names ~/.claude/projects/ entries.

    The encoding replaces "/" and "." with "-".
    """
    return str(folder).replace("/", "-").replace(".", "-")


def has_claude_session(folder: Path) -> bool:
    """Return True if Claude Code has a recorded session for the given folder.

    Claude CLI stores transcripts at ~/.claude/projects/<encoded-path>/*.jsonl.
    """
    project_dir = Path.home() / ".claude" / "projects" / _encode_project_path(folder)
    if not project_dir.is_dir():
        return False
    return any(project_dir.glob("*.jsonl"))


def repo_memory_dir(repo_path: Path) -> Path:
    """Return the main repo's own Claude auto-memory directory.

    Sessions running in the main checkout use this directory by default,
    so pointing worktree sessions here gives every worktree of a repo —
    and the main checkout itself — one shared memory that outlives any
    single worktree.
    """
    return Path.home() / ".claude" / "projects" / _encode_project_path(repo_path) / "memory"


def _make_hook(status: str, status_file: str) -> dict:
    """Create a single hook entry that writes status to the given file path."""
    safe_path = status_file.replace("'", "'\\''")
    return {
        "type": "command",
        "command": f'printf \'{{"status":"{status}","ts":%d}}\' $(date +%s) > \'{safe_path}\'',
        "async": True,
    }


def _build_hooks_config(status_file: str) -> dict:
    """Build hooks config with absolute path to status file."""
    return {
        "SessionStart": [{"hooks": [_make_hook("running", status_file)]}],
        "UserPromptSubmit": [{"hooks": [_make_hook("running", status_file)]}],
        "Stop": [{"hooks": [_make_hook("waiting", status_file)]}],
        "SessionEnd": [{"hooks": [_make_hook("ended", status_file)]}],
    }


def _load_settings(settings_file: Path) -> dict:
    """Read existing settings JSON, tolerating a missing or corrupt file."""
    if settings_file.exists():
        try:
            return json.loads(settings_file.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _is_tasktree_hook_group(group: object) -> bool:
    """True if a hook group was written by tasktree (targets .claude_status)."""
    if not isinstance(group, dict):
        return False
    hooks = group.get("hooks", [])
    if not isinstance(hooks, list):
        return False
    # The command value is user-editable JSON, so never assume it is a string
    return any(
        isinstance(hook, dict)
        and isinstance(hook.get("command"), str)
        and ".claude_status" in hook["command"]
        for hook in hooks
    )


def _merge_hooks(existing_hooks: object, new_hooks: dict) -> dict:
    """Merge tasktree's status hooks into an existing hooks config.

    User-defined hook groups are preserved untouched (settings.local.json
    holds executable configuration the user may have written by hand);
    only groups previously written by tasktree are replaced, so repeated
    calls do not stack duplicates.
    """
    merged = dict(existing_hooks) if isinstance(existing_hooks, dict) else {}
    for event, groups in new_hooks.items():
        current = merged.get(event)
        kept = (
            [g for g in current if not _is_tasktree_hook_group(g)]
            if isinstance(current, list)
            else []
        )
        merged[event] = kept + groups
    return merged


def ensure_claude_hooks(task_path: Path, memory_dir: str = "") -> None:
    """Create .claude/settings.local.json with status-reporting hooks.

    Merges with existing settings if the file already exists, preserving
    user's own configuration while adding/updating the status hooks.

    Task folders are not git repositories, so Claude Code keys its auto
    memory to the task path — memory that becomes orphaned when the task
    is deleted. When memory_dir is set, autoMemoryDirectory redirects all
    task sessions to one shared pool that persists across tasks.
    """
    claude_dir = task_path / ".claude"
    claude_dir.mkdir(exist_ok=True)

    settings_file = claude_dir / "settings.local.json"
    existing = _load_settings(settings_file)

    # Merge hooks into existing settings, preserving user-defined groups
    existing["hooks"] = _merge_hooks(
        existing.get("hooks"), _build_hooks_config(str(task_path / ".claude_status"))
    )

    if memory_dir:
        existing["autoMemoryDirectory"] = str(Path(memory_dir).expanduser())

    settings_file.write_text(json.dumps(existing, indent=2) + "\n")


def _exclude_settings_from_git(repo_path: Path) -> None:
    """Hide .claude/settings.local.json from git status in the repo.

    Appends the path to <repo>/.git/info/exclude, which worktrees share
    with the main checkout, so the generated settings file never shows
    up as an untracked change in any of them.
    """
    git_dir = repo_path / ".git"
    if not git_dir.is_dir():
        return

    entry = ".claude/settings.local.json"
    exclude_file = git_dir / "info" / "exclude"
    try:
        existing = exclude_file.read_text().splitlines() if exclude_file.exists() else []
        if entry in existing:
            return
        exclude_file.parent.mkdir(parents=True, exist_ok=True)
        with exclude_file.open("a") as f:
            f.write(entry + "\n")
    except OSError:
        return


def ensure_worktree_claude_settings(
    worktree_path: Path, repo_path: Path, status_file: Path
) -> None:
    """Create .claude/settings.local.json inside a worktree.

    Points autoMemoryDirectory at the main repo's own memory directory, so
    memory saved while working in any worktree of a repo persists after the
    worktree is deleted and is shared with future worktrees and with
    sessions in the main checkout. Also installs the status-reporting hooks
    (writing to the task's status file) so sessions started manually inside
    a worktree light up the task indicator.
    """
    claude_dir = worktree_path / ".claude"
    claude_dir.mkdir(exist_ok=True)

    settings_file = claude_dir / "settings.local.json"
    existing = _load_settings(settings_file)

    # Merge, preserving user-defined hook groups (same policy as task hooks)
    existing["hooks"] = _merge_hooks(existing.get("hooks"), _build_hooks_config(str(status_file)))
    existing["autoMemoryDirectory"] = str(repo_memory_dir(repo_path))

    settings_file.write_text(json.dumps(existing, indent=2) + "\n")
    _exclude_settings_from_git(repo_path)
