"""Git operations service for tasktree."""

import subprocess
from dataclasses import dataclass

from .task_manager import Task, Worktree


@dataclass
class GitStatus:
    """Represents the git status of a worktree."""

    branch: str = ""
    staged: list[str] = None
    modified: list[str] = None
    untracked: list[str] = None
    ahead: int = 0
    behind: int = 0

    def __post_init__(self):
        if self.staged is None:
            self.staged = []
        if self.modified is None:
            self.modified = []
        if self.untracked is None:
            self.untracked = []

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


class GitOps:
    """Git operations for worktrees."""

    @staticmethod
    def get_status(worktree: Worktree) -> GitStatus:
        """Get the git status of a worktree."""
        status = GitStatus()

        if not worktree.path.exists():
            return status

        # Get current branch
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=worktree.path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            status.branch = result.stdout.strip()
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass

        # Get status
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=worktree.path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                status_code = line[:2]
                filename = line[3:]

                if status_code == "??":
                    status.untracked.append(filename)
                elif status_code[0] in "MADRCT":
                    status.staged.append(filename)
                elif status_code[1] in "MADRCT":
                    status.modified.append(filename)
                elif status_code[0] == " " and status_code[1] == "M":
                    status.modified.append(filename)

        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass

        # Get ahead/behind info
        try:
            result = subprocess.run(
                ["git", "rev-list", "--left-right", "--count", f"{status.branch}...@{{upstream}}"],
                cwd=worktree.path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split()
                if len(parts) == 2:
                    status.ahead = int(parts[0])
                    status.behind = int(parts[1])
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, ValueError):
            pass

        return status

    @staticmethod
    def update_worktree_status(worktree: Worktree) -> GitStatus:
        """Update a worktree's status fields and return the full status."""
        status = GitOps.get_status(worktree)
        worktree.branch = status.branch
        worktree.is_dirty = status.is_dirty
        worktree.changed_files = status.changed_files
        return status

    @staticmethod
    def push(worktree: Worktree) -> tuple[bool, str]:
        """Push changes in a worktree."""
        try:
            result = subprocess.run(
                ["git", "push", "-u", "origin", "HEAD"],
                cwd=worktree.path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                return True, result.stdout or "Pushed successfully"
            return False, result.stderr or "Push failed"
        except subprocess.TimeoutExpired:
            return False, "Push timed out"
        except subprocess.SubprocessError as e:
            return False, str(e)

    @staticmethod
    def pull(worktree: Worktree) -> tuple[bool, str]:
        """Pull changes in a worktree."""
        try:
            result = subprocess.run(
                ["git", "pull"],
                cwd=worktree.path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                return True, result.stdout or "Pulled successfully"
            return False, result.stderr or "Pull failed"
        except subprocess.TimeoutExpired:
            return False, "Pull timed out"
        except subprocess.SubprocessError as e:
            return False, str(e)

    @staticmethod
    def push_all(task: Task) -> list[tuple[str, bool, str]]:
        """Push all worktrees in a task."""
        results = []
        for worktree in task.worktrees:
            success, message = GitOps.push(worktree)
            results.append((worktree.name, success, message))
        return results

    @staticmethod
    def pull_all(task: Task) -> list[tuple[str, bool, str]]:
        """Pull all worktrees in a task."""
        results = []
        for worktree in task.worktrees:
            success, message = GitOps.pull(worktree)
            results.append((worktree.name, success, message))
        return results
