"""Headless CLI for tasktree-manager.

Running ``tasktree-manager`` with no arguments starts the TUI; any argument
routes here instead. Built for scripts and automation (e.g. Claude skills
that create a task and then work in its worktrees): plain text on stdout,
errors on stderr, exit code 0 on success and 1 on failure (`epic ask` also uses 3:
the task's session is running, message it instead).
"""

import argparse
import json
import os
import shutil
import sys
from datetime import timezone
from pathlib import Path

from . import __version__
from .services import forge
from .services.agent_sessions import AgentSession, list_agent_sessions
from .services.claude_bg import background_sessions, busy, end_sessions
from .services.config import Config, ConfigError
from .services.epic_ask import (
    ASK_MAX_TURNS,
    ASK_QUESTION_MAX_BYTES,
    ASK_TIMEOUT,
    ASK_TIMEOUT_MAX,
    LOOP_GUARD_ENV,
    AskError,
    AskTarget,
    build_ask_command,
    live_sessions,
    pick_session,
    resolve_ask_task,
    run_ask,
)
from .services.epic_log import (
    EPIC_ROLE,
    FORMER_ROLE,
    EpicLogEntry,
    read_epic_log,
    resolve_log_target,
)
from .services.git_ops import GitOps
from .services.models import (
    CONTROL_CHARS,
    EPIC_KIND,
    TASK_KIND,
    ArchiveResult,
    Task,
    group_by_epic,
    parent_epic_name,
    same_folder,
)
from .services.task_manager import ARCHIVE_NOTES_SHOWN, ArchiveIncompleteError, TaskManager


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the headless CLI."""
    parser = argparse.ArgumentParser(
        prog="tasktree-manager",
        description="Manage git worktree-based tasks (run with no arguments for the TUI).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create a task with worktrees for the given repos")
    create.add_argument("name", help="Task name (also used as the branch name)")
    create.add_argument(
        "--repos",
        required=True,
        help="Comma-separated repo names from REPOS_DIR (e.g. repo-a,repo-b)",
    )
    create.add_argument(
        "--base",
        default=None,
        help="Base branch for the worktrees (default: git.default_base_branch from config)",
    )
    create.add_argument("--epic", default=None, help="Attach the new task to this epic")
    create.set_defaults(func=cmd_create)

    epic = sub.add_parser("epic", help="Group tasks under epics")
    epic_sub = epic.add_subparsers(dest="epic_command", required=True)

    epic_create = epic_sub.add_parser("create", help="Create an epic (repos are optional)")
    epic_create.add_argument("name", help="Epic name (also the branch name of its worktrees)")
    epic_create.add_argument(
        "--repos", default="", help="Comma-separated repo names from REPOS_DIR"
    )
    epic_create.add_argument("--base", default=None, help="Base branch for the worktrees")
    epic_create.set_defaults(func=cmd_epic_create)

    epic_add = epic_sub.add_parser(
        "add", help="Attach tasks to an epic (moves them from another epic)"
    )
    epic_add.add_argument("epic", help="Epic name")
    epic_add.add_argument("tasks", nargs="+", help="Task names")
    epic_add.set_defaults(func=cmd_epic_add)

    epic_remove = epic_sub.add_parser("remove", help="Detach tasks from their epic")
    epic_remove.add_argument("tasks", nargs="+", help="Task names")
    epic_remove.set_defaults(func=cmd_epic_remove)

    epic_mark = epic_sub.add_parser("mark", help="Turn an existing task into an epic")
    epic_mark.add_argument("name", help="Task name")
    epic_mark.set_defaults(func=cmd_epic_mark)

    epic_unmark = epic_sub.add_parser("unmark", help="Turn an epic without tasks back into a task")
    epic_unmark.add_argument("name", help="Epic name")
    epic_unmark.set_defaults(func=cmd_epic_unmark)

    epic_list = epic_sub.add_parser("list", help="List epics and their tasks")
    epic_list.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    epic_list.set_defaults(func=cmd_epic_list)

    epic_note = epic_sub.add_parser("note", help="Add a note to this task's file in the epic log")
    epic_note.add_argument("text", help='Note text ("-" reads it from stdin)')
    epic_note.add_argument(
        "--task", default=None, help="Task that writes the note (default: inferred from $PWD)"
    )
    epic_note.set_defaults(func=cmd_epic_note)

    epic_log = epic_sub.add_parser(
        "log", help="Show the notes and latest session recap of tasks in an epic"
    )
    epic_log.add_argument(
        "task",
        nargs="?",
        default=None,
        help="One task of the epic (default: the epic of $PWD and all its tasks)",
    )
    epic_log.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    epic_log.set_defaults(func=cmd_epic_log)

    epic_ask = epic_sub.add_parser(
        "ask", help="Ask another task of the epic: a read-only copy of its latest session answers"
    )
    epic_ask.add_argument("task", help="Task (or the epic) to ask")
    epic_ask.add_argument("question", help='Question ("-" reads it from stdin)')
    epic_ask.add_argument("--session", default=None, help="Session id to ask (default: the newest)")
    epic_ask.add_argument(
        "--fork",
        action="store_true",
        help="Ask a copy even when the task's session is running (default: exit 3)",
    )
    epic_ask.add_argument("--model", default=None, help="Model for the answer (default: Claude's)")
    epic_ask.add_argument(
        "--timeout",
        type=_ask_timeout,
        default=ASK_TIMEOUT,
        help=f"Seconds to wait for the answer (default {ASK_TIMEOUT})",
    )
    epic_ask.add_argument(
        "--max-turns",
        type=_ask_max_turns,
        default=ASK_MAX_TURNS,
        help=f"Turns the copy may take; each is a model call (default {ASK_MAX_TURNS})",
    )
    epic_ask.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    epic_ask.set_defaults(func=cmd_epic_ask)

    epic_sync = epic_sub.add_parser(
        "sync", help="Refresh the epic block in the CLAUDE.md of epics and their tasks"
    )
    epic_sync.add_argument("name", nargs="?", default=None, help="Epic name (default: all)")
    epic_sync.set_defaults(func=cmd_epic_sync)

    list_parser = sub.add_parser("list", help="List tasks with their repos and dirty state")
    list_parser.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    list_parser.set_defaults(func=cmd_list)

    repos = sub.add_parser("repos", help="List available repos in REPOS_DIR (one per line)")
    repos.set_defaults(func=cmd_repos)

    delete = sub.add_parser("delete", help="Delete a task and its worktrees")
    delete.add_argument("name", help="Task name")
    delete.add_argument(
        "--force",
        action="store_true",
        help="Delete even with uncommitted, unpushed or unmerged work, or task files "
        "that could not be archived (never an epic that still has tasks)",
    )
    delete.set_defaults(func=cmd_delete)

    add_repo = sub.add_parser("add-repo", help="Add a repo worktree to an existing task")
    add_repo.add_argument("name", help="Task name")
    add_repo.add_argument("repo", help="Repo name from REPOS_DIR")
    add_repo.add_argument("--base", default=None, help="Base branch for the worktree")
    add_repo.set_defaults(func=cmd_add_repo)

    finish = sub.add_parser(
        "finish", help="Finish a task: safety sweep, archive its diff and files, then delete"
    )
    finish.add_argument("name", help="Task name")
    finish.add_argument("--push", action="store_true", help="Push unpushed branches first")
    finish.add_argument(
        "--no-archive",
        action="store_true",
        dest="no_archive",
        help="Skip the archive: the diff and the task-folder files are deleted unsaved",
    )
    finish.add_argument(
        "--force",
        action="store_true",
        help="Finish even with unfinished work or task files that could not be archived "
        "(the archive is still written; never an epic that still has tasks)",
    )
    finish.set_defaults(func=cmd_finish)

    status = sub.add_parser("status", help="Show per-worktree status for a task")
    status.add_argument(
        "name", nargs="?", default=None, help="Task name (default: inferred from $PWD)"
    )
    output_group = status.add_mutually_exclusive_group()
    output_group.add_argument("--json", action="store_true", dest="as_json", help="Output JSON")
    output_group.add_argument(
        "--oneline",
        action="store_true",
        help="Single-line summary for statuslines and shell prompts",
    )
    status.add_argument(
        "--forge",
        action="store_true",
        dest="with_forge",
        help="Include MR/CI state from glab/gh (live network call)",
    )
    status.set_defaults(func=cmd_status)

    return parser


def _error(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def _unknown_repos_error(config: Config, repos: list[str]) -> str | None:
    """Return an error message if any repo is not in REPOS_DIR, else None."""
    available = config.get_available_repos()
    unknown = [r for r in repos if r not in available]
    if unknown:
        return (
            f"unknown repo(s): {', '.join(unknown)}; available: {', '.join(available) or '(none)'}"
        )
    return None


def _split_repos(value: str) -> list[str]:
    return [r.strip() for r in value.split(",") if r.strip()]


def cmd_create(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """Create a task with worktrees for the given repos."""
    repos = _split_repos(args.repos)
    if not repos:
        return _error("--repos needs at least one repo name")
    return _create(manager, config, args.name, repos, args.base, epic=args.epic)


def cmd_epic_create(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """Create an epic, with or without worktrees."""
    return _create(manager, config, args.name, _split_repos(args.repos), args.base, kind=EPIC_KIND)


def _create(
    manager: TaskManager,
    config: Config,
    name: str,
    repos: list[str],
    base: str | None,
    *,
    epic: str | None = None,
    kind: str = TASK_KIND,
) -> int:
    """Shared body of `create` and `epic create`."""
    error = _unknown_repos_error(config, repos) if repos else None
    if error:
        return _error(error)
    if manager.get_task(name):
        return _error(f"task already exists: {name}")

    base = base or config.default_base_branch
    task = manager.create_task(name, repos, base, epic=epic, kind=kind)
    # CLI-created tasks may never pass through the TUI's lazy Claude prep,
    # so materialize CLAUDE.md files and worktree settings right away. These
    # are best-effort polish on a task that already exists: a failure here
    # is reported as a warning, not as task-creation failure.
    for step_name, step in (
        ("CLAUDE.md files", manager.ensure_claude_md_files),
        ("worktree settings", manager.ensure_worktree_settings),
    ):
        try:
            step(task)
        except Exception as e:
            print(f"warning: {step_name} setup failed: {e}", file=sys.stderr)

    noun = "epic" if task.is_epic else "task"
    repo_list = ", ".join(wt.name for wt in task.worktrees) or "none"
    line = f"Created {noun} {task.name} at {task.path} ({len(task.worktrees)} repo(s): {repo_list})"
    if task.epic_name is not None:
        line += f" in epic {task.epic_name}"
    print(line)
    _warn_epic_block(manager, task)
    return 0


def _warn_epic_block(manager: TaskManager, task: Task) -> None:
    """Print why the task's CLAUDE.md epic block could not follow a change."""
    problem = manager.sync_epic_block(task)
    if problem:
        print(f"warning: {problem}", file=sys.stderr)


def _get_tasks(manager: TaskManager, names: list[str]) -> list[Task] | None:
    """Resolve task names, printing an error for each missing one (None if any)."""
    tasks = []
    missing = False
    for name in names:
        task = manager.get_task(name)
        if task is None:
            _error(f"no such task: {name}")
            missing = True
        else:
            tasks.append(task)
    return None if missing else tasks


def cmd_epic_add(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """Attach tasks to an epic; a task in another epic moves."""
    tasks = _get_tasks(manager, args.tasks)
    if tasks is None:
        return 1
    code = 0
    for task in tasks:
        previous = task.epic_name
        try:
            # Always through the setter: it re-checks that the epic still exists
            epic = manager.set_task_epic(task, args.epic)
        except ValueError as e:
            code = _error(str(e))
            continue
        if previous == epic:
            print(f"Task {task.name} already in epic {epic}")
        elif previous is None:
            print(f"Added {task.name} to epic {epic}")
        else:
            print(f"Moved {task.name} from epic {previous} to epic {epic}")
        _warn_epic_block(manager, task)
    return code


def cmd_epic_remove(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """Detach tasks from their epic."""
    tasks = _get_tasks(manager, args.tasks)
    if tasks is None:
        return 1
    code = 0
    for task in tasks:
        previous = task.epic_name
        try:
            manager.set_task_epic(task, None)
        except ValueError as e:
            code = _error(str(e))
            continue
        if previous is None:
            print(f"Task {task.name} is not in an epic")
        else:
            print(f"Removed {task.name} from epic {previous}")
        _warn_epic_block(manager, task)
    return code


def cmd_epic_mark(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """Turn an existing task into an epic."""
    task = manager.get_task(args.name)
    if not task:
        return _error(f"no such task: {args.name}")
    if task.is_epic:
        print(f"Task {args.name} is already an epic")
        return 0
    manager.set_task_kind(task, EPIC_KIND)
    print(f"Marked {args.name} as an epic")
    _warn_epic_block(manager, task)
    return 0


def cmd_epic_unmark(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """Turn an epic without tasks back into a plain task."""
    task = manager.get_task(args.name)
    if not task:
        return _error(f"no such task: {args.name}")
    if not task.is_epic:
        print(f"Task {args.name} is not an epic")
        return 0
    manager.set_task_kind(task, TASK_KIND)
    print(f"Unmarked {args.name}: it is a plain task now")
    _warn_epic_block(manager, task)
    return 0


def cmd_epic_list(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """List epics and the tasks attached to each (no git calls)."""
    tasks = manager.list_tasks()
    # One pass by the TUI tree's rule: a symlink alias is never an epic of its own
    _, members = group_by_epic(tasks)
    epics = [task for task in tasks if task.name in members]
    children = {name: [task.name for task in group] for name, group in members.items()}

    if args.as_json:
        payload = [
            {
                "name": epic.name,
                "display_name": epic.display_name,
                "path": str(epic.path),
                "repos": [wt.name for wt in epic.worktrees],
                "tasks": children[epic.name],
            }
            for epic in epics
        ]
        print(json.dumps(payload, indent=2))
        return 0

    if not epics:
        print("No epics")
        return 0
    for epic in epics:
        names = children[epic.name]
        print(f"{epic.name}\t{len(names)} task(s)\t{', '.join(names) or '(no tasks)'}")
    return 0


def cmd_epic_note(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """Append a note to the task's file in its epic log.

    Inside a task folder a session writes only its own notes; from outside
    any task, `--task` writes and the heading records that.
    """
    caller = _find_task_by_cwd(manager)
    source = None
    if args.task:
        task = manager.get_task(args.task)
        if task is None:
            return _error(f"no such task: {args.task}")
        if caller is None:
            source = "written outside the task folder"
        elif not same_folder(caller.path, task.path):
            return _error(f"inside task {caller.name}: notes go to its own file, not {task.name}")
    elif caller is None:
        return _error("not inside a task directory; pass --task")
    else:
        task = caller
    text = sys.stdin.read() if args.text == "-" else args.text
    path = manager.append_epic_note(task, text, source=source)
    print(f"Noted in {path}")
    return 0


def cmd_epic_log(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """Show notes and the latest session recap of one task or a whole epic."""
    epic, only = resolve_log_target(manager, _find_task_by_cwd(manager), args.task)
    entries = read_epic_log(manager, epic, only)
    for entry in entries:
        if entry.problem:
            print(f"warning: {entry.task}: {entry.problem}", file=sys.stderr)
    if args.as_json:
        print(json.dumps([_epic_log_json(entry) for entry in entries], indent=2))
        return 0
    for index, entry in enumerate(entries):
        if index:
            print()
        _print_epic_log_entry(entry)
    return 0


def _epic_log_json(entry: EpicLogEntry) -> dict:
    session = None
    if entry.session is not None:
        recap = entry.recap
        session = {
            "id": entry.session.session_id,
            "cwd": str(entry.session.cwd),
            "title": recap.title if recap else None,
            "finished_at": recap.finished_at.isoformat() if recap and recap.finished_at else None,
            "summary": recap.summary if recap else None,
            # The typed prompt only stands in for a missing recap, as in the TUI
            "last_prompt": recap.last_prompt if recap and not recap.summary else None,
        }
    return {
        "task": entry.task,
        "role": entry.role,
        "notes_path": str(entry.notes_path),
        "notes": entry.notes,
        "notes_truncated": entry.notes_truncated,
        "session": session,
        "problem": entry.problem,
    }


def _print_epic_log_entry(entry: EpicLogEntry) -> None:
    role = {EPIC_ROLE: " (epic)", FORMER_ROLE: " (no longer in the epic)"}.get(entry.role, "")
    print(f"== {entry.task}{role} ==")
    recap = entry.recap
    if entry.role == FORMER_ROLE:
        pass
    elif recap is None:
        print("Last session: none recorded")
    else:
        when = "time unknown"
        if recap.finished_at:
            when = recap.finished_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        print(f"Last session: {recap.title} ({when})")
        if recap.summary:
            print(f"  Recap: {recap.summary}")
        elif recap.last_prompt:
            print(f"  Last prompt: {recap.last_prompt}")
    if not entry.notes:
        print("Notes: none yet")
        return
    cut = ", older notes cut" if entry.notes_truncated else ""
    print(f"Notes ({entry.notes_path}{cut}):")
    # Indented, so a note cannot forge a "== task ==" line; controls dropped
    for line in _safe_lines(entry.notes.rstrip()):
        print(f"  {line}" if line else "")


def _safe_lines(text: str) -> list[str]:
    return [CONTROL_CHARS.sub("", line) for line in text.split("\n")]


def _one_line(text: str) -> str:
    return " ".join(_safe_lines(text))


def cmd_epic_ask(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """Ask another task of the epic; exit 3 when its session is running.

    A running session is asked with SendMessage by the calling agent: only
    a fork is asked here, unless --fork.
    """
    if os.environ.get(LOOP_GUARD_ENV):
        return _error("epic ask cannot run inside another epic ask")
    question = (sys.stdin.read() if args.question == "-" else args.question).strip()
    if not question:
        return _error("the question is empty")
    size = len(question.encode())
    if size > ASK_QUESTION_MAX_BYTES:
        return _error(f"the question is {size} bytes; the limit is {ASK_QUESTION_MAX_BYTES}")
    caller = _find_task_by_cwd(manager)
    epic, task = resolve_ask_task(manager, caller, args.task)

    # Before the session lookup: a running session may not have a transcript yet
    if not args.fork:
        sessions = list_agent_sessions(config.claude_path)
        if sessions is None:
            print("warning: could not list running Claude sessions", file=sys.stderr)
        live = live_sessions(task, sessions or [])
        if live:
            _print_live_sessions(task, live, args.as_json)
            return 3

    target = AskTarget(epic=epic, task=task, session=pick_session(task, args.session))
    command = build_ask_command(
        config.claude_path,
        target,
        question,
        caller.name if caller else None,
        args.model,
        args.max_turns,
    )
    try:
        answer = run_ask(command, target.session.cwd, args.timeout)
    except AskError as e:
        return _error(_one_line(f"{task.name} did not answer: {e}"))
    if args.as_json:
        payload = {
            "task": task.name,
            "status": "answered",
            "session_id": target.session.session_id,
            "cwd": str(target.session.cwd),
            "answer": answer.text,
            "usage": answer.usage,
        }
        print(json.dumps(payload, indent=2))
        return 0
    print(f"== {task.name} (copy of session {target.session.session_id}) ==")
    # Indented like notes, so the answer cannot forge a "== task ==" line
    for line in _safe_lines(answer.text.rstrip()):
        print(f"  {line}" if line else "")
    return 0


def _print_live_sessions(task: Task, live: list[AgentSession], as_json: bool) -> None:
    if as_json:
        rows = [
            {
                "name": s.name,
                "session_id": s.session_id,
                "status": s.status,
                "cwd": str(s.directory),
            }
            for s in live
        ]
        print(json.dumps({"task": task.name, "status": "running", "sessions": rows}, indent=2))
        return
    # SendMessage addresses a session by name; an unnamed one only by its id
    names = ", ".join(f'"{_one_line(s.name or s.session_id)}" ({s.status})' for s in live)
    print(f"{task.name} has a running Claude session: {names}.")
    print("Message it with SendMessage (to: that name); the answer arrives later as a message.")
    print("If the message is held or refused, pass --fork to ask a read-only copy instead.")


def _ask_timeout(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError:
        seconds = float("nan")
    if not 1 <= seconds <= ASK_TIMEOUT_MAX:
        raise argparse.ArgumentTypeError(f"must be between 1 and {ASK_TIMEOUT_MAX} seconds")
    return seconds


def _ask_max_turns(value: str) -> int:
    try:
        turns = int(value)
    except ValueError:
        turns = 0
    if not 1 <= turns <= 50:
        raise argparse.ArgumentTypeError("must be between 1 and 50")
    return turns


def cmd_epic_sync(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """Refresh the CLAUDE.md epic block of epics and their tasks."""
    if args.name:
        epic = manager.get_task(args.name)
        if epic is None:
            return _error(f"no such epic: {args.name}")
        if manager.epic_of(epic) != epic.name:
            return _error(f"{epic.name} is not an epic")
        epics = [epic.name]
    else:
        epics = [task.name for task in manager.list_tasks() if manager.epic_of(task) == task.name]
    synced = missing = failed = 0
    for name in epics:
        for member in [name, *manager.epic_child_names(name)]:
            try:
                task = manager.get_task(member)
            except (OSError, ValueError) as e:
                print(f"warning: {member}: {e}", file=sys.stderr)
                failed += 1
                continue
            if task is None:
                continue
            if not (task.path / "CLAUDE.md").is_file():
                missing += 1
                continue
            problem = manager.sync_epic_block(task)
            if problem:
                print(f"warning: {problem}", file=sys.stderr)
                failed += 1
            else:
                synced += 1
    print(
        f"Synced {synced} folder(s); {missing} without CLAUDE.md "
        f"(written when a Claude session starts there from the TUI); {failed} failed"
    )
    return 1 if failed else 0


def _refuse_epic_with_children(manager: TaskManager, task: Task, verb: str) -> bool:
    """Print an error and return True if `task` is an epic that still has tasks.

    Checked before the safety sweep: --force covers git state, not hierarchy.
    """
    if not task.is_epic:
        return False
    children = manager.epic_child_names(task.name)
    if not children:
        return False
    _error(
        f"cannot {verb} epic {task.name}: it still has {len(children)} task(s): "
        f"{', '.join(children)}; finish them or run: tasktree-manager epic remove TASK"
    )
    return True


def cmd_list(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """List tasks with their repos and dirty state."""
    tasks = manager.list_tasks()
    # One TASKS_DIR listing for every parent_epic_name lookup below
    listing = set(os.listdir(config.tasks_dir)) if config.tasks_dir.is_dir() else set()
    dirty: dict[str, bool] = {}
    errored: dict[str, bool] = {}
    for task in tasks:
        statuses = GitOps.get_statuses_parallel(task.worktrees)
        dirty[task.name] = any(s.is_dirty for s in statuses.values())
        # A worktree whose git status failed has unknown state, not clean
        # state; is_dirty is False by default and must not be read as "ok"
        errored[task.name] = any(s.error for s in statuses.values())

    if args.as_json:
        payload = [
            {
                "name": task.name,
                "display_name": task.display_name,
                "kind": task.kind,
                "epic": parent_epic_name(task, listing),
                "path": str(task.path),
                "repos": [wt.name for wt in task.worktrees],
                "dirty": dirty[task.name],
                "error": errored[task.name],
            }
            for task in tasks
        ]
        print(json.dumps(payload, indent=2))
        return 0

    if not tasks:
        print("No tasks")
        return 0
    for task in tasks:
        if errored[task.name]:
            state = "error"
        elif dirty[task.name]:
            state = "dirty"
        else:
            state = "clean"
        repos = ", ".join(wt.name for wt in task.worktrees) or "(no repos)"
        print(f"{task.name}\t{state}\t{repos}")
    return 0


def cmd_repos(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """List available repos (handles nested repos, unlike a plain ls)."""
    for repo in config.get_available_repos():
        print(repo)
    return 0


def _print_archive(archive: ArchiveResult | None) -> bool:
    """Report where a task's work was archived; True if anything was saved."""
    if archive is None:
        return False
    notes = [f"not archived: {item}" for item in archive.skipped]
    notes += [f"could not archive: {item}" for item in archive.failed]
    for note in notes[:ARCHIVE_NOTES_SHOWN]:
        print(f"warning: {note}", file=sys.stderr)
    if len(notes) > ARCHIVE_NOTES_SHOWN:
        print(f"warning: ... and {len(notes) - ARCHIVE_NOTES_SHOWN} more", file=sys.stderr)
    if archive.patch is not None:
        print(f"Archived diff to {archive.patch}")
    if archive.files_dir is not None:
        print(f"Archived {len(archive.files)} task file(s) to {archive.files_dir}")
    return archive.saved


def _archive_for_delete(
    manager: TaskManager, task: Task, force: bool, verb: str, notes: list[str] | None = None
) -> tuple[bool, bool]:
    """Archive a task about to be deleted; returns (may delete, anything saved).

    Any archive error stops the delete. Task files that could not be read or
    copied stop it too unless --force: the task folder is their only copy.
    """
    try:
        archive = manager.archive_task(task, notes=notes)
    except ArchiveIncompleteError as e:
        _print_archive(e.result)
        _error(f"archive failed: {e}")
        return False, False
    except Exception as e:
        _error(f"archive failed: {e}")
        return False, False
    saved = _print_archive(archive)
    if archive is not None and archive.failed and not force:
        _error(
            f"{len(archive.failed)} task file(s) could not be archived; "
            f"use --force to {verb} anyway"
        )
        return False, saved
    return True, saved


def _claude_sessions_to_end(
    config: Config, task: Task, force: bool, verb: str
) -> list[AgentSession] | None:
    """The task's background Claude sessions; None (after an error) when busy without --force."""
    found = list_agent_sessions(config.claude_path, include_done=True)
    if found is None and shutil.which(config.claude_path):
        print(f"warning: could not check Claude sessions of task {task.name}", file=sys.stderr)
    sessions = background_sessions(found or [], task.path)
    working = busy(sessions)
    if working and not force:
        ids = ", ".join(session.agent_id for session in working)
        print(
            f"error: Claude is still active (working or waiting for you) in task {task.name}: {ids}",
            file=sys.stderr,
        )
        print(f"use --force to stop it and {verb} anyway", file=sys.stderr)
        return None
    return sessions


def _end_claude_sessions(config: Config, sessions: list[AgentSession], force: bool) -> bool:
    """Stop and remove sessions; one that will not stop keeps the task unless --force."""
    failed = end_sessions(config.claude_path, sessions)
    for agent_id in failed:
        level = "warning" if force else "error"
        print(f"{level}: could not stop Claude session {agent_id}", file=sys.stderr)
    if failed and not force:
        print("stop it with `claude stop ID`, or use --force", file=sys.stderr)
        return False
    return True


def cmd_delete(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """Delete a task after a safety check (bypass with --force)."""
    task = manager.get_task(args.name)
    if not task:
        return _error(f"no such task: {args.name}")
    if _refuse_epic_with_children(manager, task, "delete"):
        return 1

    report = manager.check_task_safety(task)
    if not report.is_safe() and not args.force:
        print(f"error: task {args.name} has unfinished work:", file=sys.stderr)
        for issue in report.errors + report.dirty + report.unpushed + report.unmerged:
            print(f"  {issue.repo_name}: {issue.details}", file=sys.stderr)
        print("use --force to delete anyway", file=sys.stderr)
        return 1
    sessions = _claude_sessions_to_end(config, task, args.force, "delete")
    if sessions is None or not _end_claude_sessions(config, sessions, args.force):
        return 1

    # Same safety net as the TUI: the remaining diff and the task files are
    # archived before the worktrees and branches are removed, --force included
    may_delete, _ = _archive_for_delete(manager, task, args.force, "delete")
    if not may_delete:
        return 1
    manager.finish_task(task)
    print(f"Deleted task {args.name}")
    return 0


def cmd_finish(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """Guided task finish: sweep -> optional push -> archive -> delete."""
    task = manager.get_task(args.name)
    if not task:
        return _error(f"no such task: {args.name}")
    if _refuse_epic_with_children(manager, task, "finish"):
        return 1
    # Before --push: a busy Claude refuses the finish without touching the remote
    sessions = _claude_sessions_to_end(config, task, args.force, "finish")
    if sessions is None:
        return 1

    # Push unconditionally when asked (TUI parity: `git push -u origin HEAD`).
    # Gating on has_unpushed() would skip never-pushed --no-track branches,
    # whose missing upstream makes ahead read as 0.
    if args.push:
        success, failed = manager.push_all_branches(task)
        for repo in success:
            print(f"Pushed {repo}")
        for repo in failed:
            print(f"error: push failed: {repo}", file=sys.stderr)

    report = manager.check_task_safety(task)

    # Squash/rebase merges detected via the forge are worth surfacing even
    # when everything is fine — they explain why the branch counts as merged
    for issue in report.merged_via_forge:
        print(f"{issue.repo_name}: {issue.details}")

    if not report.is_safe() and not args.force:
        print(f"error: task {args.name} has unfinished work:", file=sys.stderr)
        for issue in report.errors + report.dirty + report.unpushed + report.unmerged:
            print(f"  {issue.repo_name}: {issue.details}", file=sys.stderr)
        if not args.push and (report.has_unpushed() or report.has_unmerged()):
            print("use --push to push branches first", file=sys.stderr)
        print("use --force to finish anyway", file=sys.stderr)
        return 1
    if not _end_claude_sessions(config, sessions, args.force):
        return 1

    if not args.no_archive:
        notes = [f"{issue.repo_name}: {issue.details}" for issue in report.merged_via_forge]
        may_delete, saved = _archive_for_delete(
            manager, task, args.force, "finish", notes=notes or None
        )
        if not may_delete:
            return 1
        if not saved:
            print("Nothing to archive")

    manager.finish_task(task)
    print(f"Finished task {args.name}")
    return 0


def cmd_add_repo(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """Add a repo worktree to an existing task."""
    task = manager.get_task(args.name)
    if not task:
        return _error(f"no such task: {args.name}")
    error = _unknown_repos_error(config, [args.repo])
    if error:
        return _error(error)
    if any(wt.name == args.repo for wt in task.worktrees):
        print(f"Repo {args.repo} already in task {args.name}")
        return 0

    base = args.base or config.default_base_branch
    manager.add_repo_to_task(task, args.repo, base)
    print(f"Added {args.repo} to task {args.name}")
    return 0


def _find_task_by_cwd(manager: TaskManager) -> Task | None:
    """Find the task whose directory contains the current working directory."""
    return manager.task_containing(Path.cwd())


def _read_claude_status(task: Task) -> dict | None:
    """Read the task's hook-written .claude_status file, or None."""
    status_file = task.path / ".claude_status"
    try:
        data = json.loads(status_file.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return {"status": data.get("status", "unknown"), "ts": data.get("ts")}


def _oneline_status(task: Task, rows: list[tuple], claude: dict | None) -> str:
    """Compact one-line summary for statuslines and shell prompts.

    Per repo: ✓ = clean, in sync and merged; ●N (dirty), ↑N/↓N
    (ahead/behind); ○ = clean and in sync but not merged (work in flight);
    ! on a status error. Matches the TUI glyph vocabulary.
    """
    parts = [task.name]
    for worktree, status, _base, merged_via, _forge_status in rows:
        repo = worktree.name.split("/")[-1]
        if status.error:
            flags = "!"
        else:
            flags = ""
            if status.is_dirty:
                flags += f"●{status.changed_files}"
            if status.ahead:
                flags += f"↑{status.ahead}"
            if status.behind:
                flags += f"↓{status.behind}"
            if not flags:
                # Every glyph earns its cell: a truly done branch gets ✓,
                # a clean-but-unmerged one gets ○ so unfinished work never
                # renders as a bare (invisible) repo name
                flags = "✓" if merged_via is not None else "○"
        parts.append(f"{repo}{flags}")
    if claude is not None:
        parts.append(f"claude:{claude['status']}")
    return " ".join(parts)


def cmd_status(manager: TaskManager, config: Config, args: argparse.Namespace) -> int:
    """Show per-worktree status for a task (fast/offline by default)."""
    if args.name:
        task = manager.get_task(args.name)
        if not task:
            return _error(f"no such task: {args.name}")
    else:
        task = _find_task_by_cwd(manager)
        if not task:
            return _error("not inside a task directory; pass a task name")

    statuses = GitOps.get_statuses_parallel(task.worktrees)
    claude = _read_claude_status(task)

    rows: list[tuple] = []
    for worktree in task.worktrees:
        status = statuses.get(worktree.name)
        if status is None:
            continue
        base = GitOps.get_default_branch(worktree)
        # fetch=False keeps the default path offline-fast; origin/<base> may
        # be slightly stale, which is fine for a prompt/statusline
        merged_via = "ancestor" if GitOps.check_merged(worktree, base, fetch=False) else None
        forge_status = None
        if args.with_forge:
            branch = status.branch or task.name
            forge_status = forge.get_forge_status(worktree.path, branch)
            if (
                merged_via is None
                and forge_status is not None
                and forge_status.mr_state == "merged"
            ):
                merged_via = "forge"
        rows.append((worktree, status, base, merged_via, forge_status))

    if args.oneline:
        print(_oneline_status(task, rows, claude))
        return 0

    if args.as_json:
        payload = {
            "task": task.name,
            "kind": task.kind,
            "epic": parent_epic_name(task),
            "path": str(task.path),
            "claude": claude,
            "worktrees": [
                {
                    "repo": worktree.name,
                    "branch": status.branch,
                    "ahead": status.ahead,
                    "behind": status.behind,
                    "staged": len(status.staged),
                    "modified": len(status.modified),
                    "untracked": len(status.untracked),
                    "dirty": status.is_dirty,
                    "merged": merged_via is not None,
                    "merged_via": merged_via,
                    "forge": (
                        {
                            "provider": forge_status.provider,
                            "mr_state": forge_status.mr_state,
                            "mr_url": forge_status.mr_url,
                            "mr_ref": forge_status.mr_ref,
                            "ci_state": forge_status.ci_state,
                        }
                        if forge_status is not None
                        else None
                    ),
                    "error": status.error or None,
                }
                for worktree, status, _base, merged_via, forge_status in rows
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0

    claude_state = claude["status"] if claude else "-"
    print(f"Task: {task.name}\tclaude: {claude_state}")
    for worktree, status, base, merged_via, forge_status in rows:
        if status.error:
            print(f"{worktree.name}\t{status.branch or '?'}\terror: {status.error}")
            continue
        state = f"dirty ({status.changed_files} files)" if status.is_dirty else "clean"
        sync = f"ahead {status.ahead}, behind {status.behind}"
        merged = f"merged ({merged_via})" if merged_via else f"not merged to {base}"
        line = f"{worktree.name}\t{status.branch}\t{state}\t{sync}\t{merged}"
        if forge_status is not None and forge_status.mr_state != "none":
            mr = f"MR {forge_status.mr_ref or '?'} {forge_status.mr_state}"
            if forge_status.ci_state:
                mr += f" (CI {forge_status.ci_state})"
            line += f"\t{mr}"
        print(line)
    return 0


def run_cli(argv: list[str], config: Config | None = None) -> int:
    """Parse argv and run the matching subcommand, returning an exit code."""
    args = build_parser().parse_args(argv)
    try:
        if config is None:
            config = Config.load()
        # Setup shares the same error handling as the subcommand itself: a
        # PermissionError from ensure_dirs() (or any other startup failure)
        # must print "error: ..." like everything else, not a raw traceback
        config.ensure_dirs()
        GitOps.network_timeout = config.git_timeout
        forge.Forge.configure(config)
        manager = TaskManager(config)
        return args.func(manager, config, args)
    except FileNotFoundError as e:
        # subprocess sets .filename to the executable it tried to exec
        # (argv[0]); that's how a missing `git` binary is told apart from a
        # missing repo/worktree directory, which raises the same exception
        # type with the missing path as .filename instead
        if e.filename == "git" or shutil.which("git") is None:
            return _error("git executable not found on PATH")
        return _error(f"repository not found: {e}")
    except ConfigError as e:
        return _error(str(e))
    except PermissionError:
        return _error("permission denied: check directory permissions")
    except ValueError as e:
        return _error(str(e))
    except Exception as e:  # same taxonomy as the TUI worker: keep output clean
        return _error(f"{type(e).__name__}: {e}")
