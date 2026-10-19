"""Data models for tasktree-manager."""

import os
import re
from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path

# Task name validation pattern. No '/': a task is exactly one directory
# level under TASKS_DIR (list_tasks() only reads that level), and a slashed
# name would be surfaced as its parent directory with the wrong branch name.
TASK_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9._\-]+$")

EPIC_KIND = "epic"
TASK_KIND = "task"


def validate_task_name(name: str) -> str | None:
    """Validate a task name, returning an error message or None if valid.

    Task names become a directory under TASKS_DIR and a git branch name, so
    they must be a single path segment that cannot traverse ('.', '..') or
    look like a git option (leading '-').
    """
    if not name:
        return "Task name cannot be empty"
    if name.startswith("-"):
        return "Task name cannot start with '-'"
    if name.startswith("."):
        # list_tasks() hides dot-dirs (so the task would vanish from the
        # list), and the archive dir itself lives at TASKS_DIR/.archive
        return "Task name cannot start with '.'"
    if not TASK_NAME_PATTERN.fullmatch(name):
        return "Task name can only contain letters, numbers, '.', '_', '-'"
    return None


def _read_marker(path: Path) -> str | None:
    """Stripped content of a marker file, or None when missing or empty."""
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return value or None


@dataclass
class Worktree:
    """Represents a git worktree for a task."""

    name: str
    path: Path
    branch: str = ""
    is_dirty: bool = False
    changed_files: int = 0

    @property
    def exists(self) -> bool:
        """Check if the worktree directory exists."""
        return self.path.exists()

    @property
    def has_claude_md(self) -> bool:
        """Check if the worktree has a CLAUDE.md file."""
        return (self.path / "CLAUDE.md").exists()


@dataclass
class Task:
    """Represents a task with associated worktrees."""

    name: str
    path: Path
    worktrees: list[Worktree] = field(default_factory=list)

    @property
    def is_dirty(self) -> bool:
        """Check if any worktree in the task is dirty."""
        return any(wt.is_dirty for wt in self.worktrees)

    @property
    def dirty_count(self) -> int:
        """Count of dirty worktrees."""
        return sum(1 for wt in self.worktrees if wt.is_dirty)

    @property
    def has_claude_md(self) -> bool:
        """Check if the task has a CLAUDE.md file."""
        return (self.path / "CLAUDE.md").exists()

    @property
    def display_name(self) -> str | None:
        """Display alias from <task>/.tasktree_name, or None when unset.

        Read lazily from disk so every Task construction site picks it up
        and a rename is visible on the next render without reloading.
        """
        return _read_marker(self.path / ".tasktree_name")

    @property
    def display_label(self) -> str:
        """What the task list shows: the alias when set, else the real name."""
        return self.display_name or self.name

    @property
    def kind(self) -> str:
        """'epic' when <task>/.tasktree_kind says so, else 'task'."""
        if _read_marker(self.path / ".tasktree_kind") == EPIC_KIND:
            return EPIC_KIND
        return TASK_KIND

    @property
    def is_epic(self) -> bool:
        """True for an epic: a task folder that groups other tasks."""
        return self.kind == EPIC_KIND

    @property
    def epic_name(self) -> str | None:
        """Parent epic from <task>/.tasktree_epic, or None.

        The marker becomes a path, so a value that is not a valid task name
        or names the task itself reads as None. Epics never have a parent.
        """
        value = _read_marker(self.path / ".tasktree_epic")
        if value is None or value == self.name or validate_task_name(value):
            return None
        if self.is_epic:
            return None
        return value


def on_disk_name(path: Path, names: Collection[str] | None = None) -> str:
    """The last path segment as spelled on disk, for an existing path.

    On a case-insensitive disk `epic-1` opens `EPIC-1`; markers, branches and
    the epic checks must all use the real spelling. `names` is the listing of
    path.parent when the caller already has it (one listing per scan).
    """
    if names is None:
        try:
            names = set(os.listdir(path.parent))
        except OSError:
            return path.name
    if path.name in names:
        return path.name
    for name in names:
        if name.casefold() == path.name.casefold() and same_folder(path.parent / name, path):
            return name
    return path.name


def same_folder(a: Path, b: Path) -> bool:
    """True when two paths open the same file or folder."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def parent_epic_name(task: Task, names: Collection[str] | None = None) -> str | None:
    """The epic a task belongs to, spelled as on disk, or None.

    The one membership rule for the CLI, the TUI, the delete guard and the
    CLAUDE.md block: the marker must name a real epic folder next to the
    task. A symlink alias, a missing folder or a plain task makes it an orphan.
    `names` is the TASKS_DIR listing, passed by callers that resolve many tasks.
    """
    marker = task.epic_name
    if marker is None:
        return None
    path = task.path.parent / marker
    if path.is_symlink() or not path.is_dir():
        return None
    name = on_disk_name(path, names)
    if not Task(name=name, path=path.parent / name).is_epic:
        return None
    return name


def resolve_epic(
    task: Task, epics: dict[str, Task], names: Collection[str] | None = None
) -> str | None:
    """The epic in `epics` the task belongs to (see parent_epic_name), or None."""
    parent = parent_epic_name(task, names)
    return parent if parent in epics else None


def group_by_epic(tasks: list[Task]) -> tuple[list[Task], dict[str, list[Task]]]:
    """Split tasks into top-level rows and the children of each epic.

    A task is a child when its marker names an epic in `tasks`, by the same
    rule as TaskManager.epic_child_names (the delete guard). Anything else, an
    orphan included, is top-level. Order within both is kept.
    """
    # A symlinked folder never counts as an epic: it would alias a real one
    epics = {task.name: task for task in tasks if task.is_epic and not task.path.is_symlink()}
    children: dict[str, list[Task]] = {name: [] for name in epics}
    top: list[Task] = []
    listings: dict[Path, set[str]] = {}
    for task in tasks:
        folder = task.path.parent
        if folder not in listings:
            try:
                listings[folder] = set(os.listdir(folder))
            except OSError:
                listings[folder] = set()
        names = listings[folder]
        parent = None if task.name in epics else resolve_epic(task, epics, names)
        if parent is None:
            top.append(task)
        else:
            children[parent].append(task)
    return top, children


@dataclass
class GitStatus:
    """Represents the git status of a worktree."""

    branch: str = ""
    staged: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)
    # Actual (XY code, display path) pairs in git's output order
    entries: list[tuple[str, str]] = field(default_factory=list)
    ahead: int = 0
    behind: int = 0
    error: str | None = None  # Error message if status fetch failed

    @property
    def is_dirty(self) -> bool:
        """Check if there are any uncommitted changes."""
        return bool(self.staged or self.modified or self.untracked)

    @property
    def changed_files(self) -> int:
        """Total number of changed files."""
        # A partially staged file (MM, AM) sits in both staged and modified;
        # count it once
        return len(set(self.staged) | set(self.modified) | set(self.untracked))

    @property
    def all_changes(self) -> list[tuple[str, str]]:
        """All changes as (status code, filename) tuples.

        Prefers the actual git status codes recorded during parsing so
        renames, conflicts etc. display truthfully. Falls back to
        reconstructed codes for manually built instances.
        """
        if self.entries:
            return list(self.entries)
        changes = []
        for f in self.staged:
            changes.append(("A ", f))
        for f in self.modified:
            changes.append((" M", f))
        for f in self.untracked:
            changes.append(("??", f))
        return changes


@dataclass
class RepoIssue:
    """Represents an issue with a specific repo."""

    repo_name: str
    worktree_path: Path
    issue_type: str  # "unpushed", "unmerged", "dirty", "merged", "error"
    details: str  # "3 commits ahead", "not merged to main", "2 files changed"
    branch: str = ""
    mr_url: str | None = None
    mr_state: str | None = None  # "open" | "merged" | "closed" | "none"


@dataclass(frozen=True)
class ArchiveResult:
    """What archive_task saved before a task folder is deleted."""

    patch: Path | None = None  # combined diff of every worktree
    files_dir: Path | None = None  # copies of task-folder files outside worktrees
    files: tuple[str, ...] = ()  # archived files, relative to the task folder
    skipped: tuple[str, ...] = ()  # "name (reason)": left out by policy (caps, keys)
    failed: tuple[str, ...] = ()  # "name (reason)": could not be read or copied

    @property
    def saved(self) -> bool:
        """True when anything was written to the archive directory."""
        return self.patch is not None or self.files_dir is not None


@dataclass
class TaskSafetyReport:
    """Report of safety issues for a task."""

    unpushed: list[RepoIssue] = field(default_factory=list)
    unmerged: list[RepoIssue] = field(default_factory=list)
    dirty: list[RepoIssue] = field(default_factory=list)
    # Worktrees whose `git status` itself failed (lock, timeout): the state
    # is unknown, so these always block is_safe() — deleting on unknown
    # state is exactly what safety checks exist to prevent.
    errors: list[RepoIssue] = field(default_factory=list)
    # Branches whose ancestor check failed but whose MR/PR is merged
    # (squash/rebase merges). Informational — never blocks is_safe().
    merged_via_forge: list[RepoIssue] = field(default_factory=list)

    def is_safe(self) -> bool:
        """True if no issues found."""
        return not (self.unpushed or self.unmerged or self.dirty or self.errors)

    def has_errors(self) -> bool:
        """True if any worktree's git status could not be read."""
        return bool(self.errors)

    def has_unpushed(self) -> bool:
        """True if there are unpushed commits."""
        return bool(self.unpushed)

    def has_unmerged(self) -> bool:
        """True if there are unmerged branches."""
        return bool(self.unmerged)

    def has_dirty(self) -> bool:
        """True if there are uncommitted changes."""
        return bool(self.dirty)
