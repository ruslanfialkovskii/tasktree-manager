"""Data models for tasktree."""

from dataclasses import dataclass, field
from pathlib import Path


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


@dataclass
class GitStatus:
    """Represents the git status of a worktree."""

    branch: str = ""
    staged: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)
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
        return len(self.staged) + len(self.modified) + len(self.untracked)

    @property
    def all_changes(self) -> list[tuple[str, str]]:
        """All changes as (status, filename) tuples."""
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
    issue_type: str  # "unpushed", "unmerged", "dirty"
    details: str  # "3 commits ahead", "not merged to main", "2 files changed"


@dataclass
class TaskSafetyReport:
    """Report of safety issues for a task."""

    unpushed: list[RepoIssue] = field(default_factory=list)
    unmerged: list[RepoIssue] = field(default_factory=list)
    dirty: list[RepoIssue] = field(default_factory=list)

    def is_safe(self) -> bool:
        """True if no issues found."""
        return not (self.unpushed or self.unmerged or self.dirty)

    def has_unpushed(self) -> bool:
        """True if there are unpushed commits."""
        return bool(self.unpushed)

    def has_unmerged(self) -> bool:
        """True if there are unmerged branches."""
        return bool(self.unmerged)

    def has_dirty(self) -> bool:
        """True if there are uncommitted changes."""
        return bool(self.dirty)
