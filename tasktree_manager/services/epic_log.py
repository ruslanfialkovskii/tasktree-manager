"""The epic log: each task's notes plus the recap of its latest Claude session.

Sessions of one epic read it to learn what the other tasks decided. The scope
rule lives here so every reader applies it the same way: from inside a task of
an epic, only that epic can be read.
"""

from dataclasses import dataclass
from pathlib import Path

from .claude_sessions import ClaudeRecap, SessionRef, latest_session, read_claude_recap
from .models import Task
from .task_manager import TaskManager

EPIC_ROLE = "epic"
MEMBER_ROLE = "task"
# A notes file left by a task that is no longer in the epic (finished, moved)
FORMER_ROLE = "former"


@dataclass(frozen=True)
class EpicLogEntry:
    """One task's part of the epic log."""

    task: str
    role: str
    notes_path: Path
    notes: str | None
    notes_truncated: bool
    session: SessionRef | None
    recap: ClaudeRecap | None
    problem: str | None = None  # why the task's sessions could not be read


def caller_epic(manager: TaskManager, caller: Task | None) -> str | None:
    """The epic of the task the command runs in, or None outside an epic."""
    return manager.epic_of(caller) if caller is not None else None


def resolve_log_target(
    manager: TaskManager, caller: Task | None, name: str | None
) -> tuple[str, str | None]:
    """``(epic, task)`` to read: `task` None means the whole epic.

    Raises ValueError for a task outside any epic, or outside the caller's.
    """
    scope = caller_epic(manager, caller)
    if name is None:
        if scope is None:
            raise ValueError("not inside a task of an epic; pass a task name")
        return scope, None
    target = manager.get_task(name)
    if target is None:
        # Notes outlive their task: read them by name from inside the epic
        if scope is not None and name in manager.epic_note_names(scope):
            return scope, name
        raise ValueError(f"no such task: {name}")
    epic = manager.epic_of(target)
    if scope is not None and epic != scope and target.name in manager.epic_note_names(scope):
        # It left the caller's epic: its notes there are still readable
        return scope, target.name
    epic = require_in_scope(manager, caller, target)
    return epic, None if target.is_epic else target.name


def require_in_scope(manager: TaskManager, caller: Task | None, target: Task) -> str:
    """The target's epic, if the caller may reach it; ValueError says why not.

    From inside a task folder only the same epic is reachable, and only when
    that task is in an epic; from outside every task folder, any epic.
    """
    epic = manager.epic_of(target)
    if epic is None:
        raise ValueError(f"task {target.name} is not in an epic")
    if caller is None:
        return epic
    scope = caller_epic(manager, caller)
    if scope is None:
        raise ValueError(
            f"task {caller.name} is not in an epic; run this from a task of {epic} "
            "or from outside the task folders"
        )
    if epic != scope:
        raise ValueError(f"task {target.name} is in epic {epic}, not in {scope}")
    return epic


def task_session(task: Task) -> SessionRef | None:
    """The newest session of a task, run in its folder or one of its worktrees."""
    return latest_session([task.path, *(wt.path for wt in task.worktrees)])


def read_epic_log(manager: TaskManager, epic: str, only: str | None = None) -> list[EpicLogEntry]:
    """The log of the whole epic, or of the one task `only`."""
    members = [epic, *manager.epic_child_names(epic)]
    roles = {name: MEMBER_ROLE for name in members}
    roles[epic] = EPIC_ROLE
    for name in manager.epic_note_names(epic):
        roles.setdefault(name, FORMER_ROLE)
    names = [only] if only is not None else [*members, *sorted(set(roles) - set(members))]
    return [_entry(manager, epic, name, roles.get(name, FORMER_ROLE)) for name in names]


def _entry(manager: TaskManager, epic: str, name: str, role: str) -> EpicLogEntry:
    session = recap = problem = None
    if role != FORMER_ROLE:
        try:
            task = manager.get_task(name)
        except (OSError, ValueError) as e:
            task, problem = None, str(e)
        if task is not None:
            session = task_session(task)
            recap = read_claude_recap(session.path) if session else None
    notes = manager.read_epic_note(epic, name)
    return EpicLogEntry(
        task=name,
        role=role,
        notes_path=manager.epic_note_path(epic, name),
        notes=notes[0] if notes else None,
        notes_truncated=bool(notes and notes[1]),
        session=session,
        recap=recap,
        problem=problem,
    )
