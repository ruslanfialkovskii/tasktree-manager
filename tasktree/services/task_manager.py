"""Task management service for tasktree."""

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config


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


class TaskManager:
    """Manages tasks and worktrees."""

    def __init__(self, config: Config):
        self.config = config

    def list_tasks(self) -> list[Task]:
        """List all tasks in the tasks directory."""
        if not self.config.tasks_dir.exists():
            return []

        tasks = []
        for item in sorted(self.config.tasks_dir.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                task = Task(name=item.name, path=item)
                task.worktrees = self._get_worktrees(task)
                tasks.append(task)
        return tasks

    def _get_worktrees(self, task: Task) -> list[Worktree]:
        """Get all worktrees for a task (recursively scans subdirectories)."""
        worktrees = []
        if not task.path.exists():
            return worktrees

        # Recursively find all directories containing .git
        for git_dir in sorted(task.path.rglob(".git")):
            if git_dir.is_dir() or git_dir.is_file():
                # Get the parent directory (the actual worktree)
                worktree_path = git_dir.parent
                # Get relative path from task directory for the name
                try:
                    rel_path = worktree_path.relative_to(task.path)
                    worktree = Worktree(name=str(rel_path), path=worktree_path)
                    worktrees.append(worktree)
                except ValueError:
                    # Skip if not relative to task path
                    continue

        return worktrees

    def get_task(self, name: str) -> Task | None:
        """Get a specific task by name."""
        task_path = self.config.tasks_dir / name
        if not task_path.exists():
            return None

        task = Task(name=name, path=task_path)
        task.worktrees = self._get_worktrees(task)
        return task

    def create_task(self, name: str, repos: list[str], base_branch: str = "master") -> Task:
        """Create a new task with worktrees for specified repos."""
        task_path = self.config.tasks_dir / name
        task_path.mkdir(parents=True, exist_ok=True)

        task = Task(name=name, path=task_path)

        for repo_name in repos:
            self._create_worktree(task, repo_name, base_branch)

        task.worktrees = self._get_worktrees(task)
        return task

    def _create_worktree(self, task: Task, repo_name: str, base_branch: str) -> None:
        """Create a worktree for a repo within a task."""
        repo_path = self.config.repos_dir / repo_name
        worktree_path = task.path / repo_name

        if not repo_path.exists():
            raise ValueError(f"Repository not found: {repo_name}")

        if worktree_path.exists():
            return  # Already exists

        # Ensure parent directory exists for nested repos
        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if branch already exists
        branch_check = subprocess.run(
            ["git", "rev-parse", "--verify", f"refs/heads/{task.name}"],
            cwd=repo_path,
            capture_output=True,
        )

        # Use -B to reset branch if it exists, -b if it doesn't
        branch_flag = "-B" if branch_check.returncode == 0 else "-b"

        # Create git worktree with task name as branch
        result = subprocess.run(
            ["git", "worktree", "add", branch_flag, task.name, str(worktree_path), base_branch],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            raise ValueError(f"Failed to create worktree for {repo_name}: {error_msg}")

    def add_repo_to_task(self, task: Task, repo_name: str, base_branch: str = "master") -> None:
        """Add a repo worktree to an existing task."""
        self._create_worktree(task, repo_name, base_branch)
        task.worktrees = self._get_worktrees(task)

    def finish_task(self, task: Task) -> None:
        """Finish/delete a task and clean up worktrees."""
        for worktree in task.worktrees:
            self._remove_worktree(worktree, task.name)

        # Remove task directory
        if task.path.exists():
            shutil.rmtree(task.path)

    def _remove_worktree(self, worktree: Worktree, branch_name: str) -> None:
        """Remove a worktree from its main repo.

        Args:
            worktree: The worktree to remove
            branch_name: The branch name to delete (usually the task name)
        """
        main_repo = None

        # Try to find main repo from the worktree itself (if it exists and is valid)
        if worktree.path.exists():
            result = subprocess.run(
                ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                cwd=worktree.path,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                main_git_dir = Path(result.stdout.strip())
                main_repo = main_git_dir.parent if main_git_dir.name == ".git" else main_git_dir

        # Fallback: derive main repo from worktree.name (which is the repo relative path)
        if main_repo is None:
            fallback_repo = self.config.repos_dir / worktree.name
            if fallback_repo.exists() and (fallback_repo / ".git").exists():
                main_repo = fallback_repo

        if main_repo is None:
            # Can't find main repo - just clean up the directory if it exists
            return

        # Remove the worktree using git (if path exists)
        if worktree.path.exists():
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree.path)],
                cwd=main_repo,
                capture_output=True,
                text=True,
            )

        # Prune stale worktree references (handles case where path was already deleted)
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=main_repo,
            capture_output=True,
            text=True,
        )

        # Delete the branch
        subprocess.run(
            ["git", "branch", "-D", branch_name],
            cwd=main_repo,
            capture_output=True,
            text=True,
        )

    def get_repos_not_in_task(self, task: Task) -> list[str]:
        """Get list of repos that are not yet in the task."""
        all_repos = set(self.config.get_available_repos())
        task_repos = {wt.name for wt in task.worktrees}
        return sorted(all_repos - task_repos)

    def check_task_safety(self, task: Task) -> TaskSafetyReport:
        """Check if task is safe to delete.

        Checks for:
        - Unpushed commits (ahead of remote)
        - Unmerged branches (not merged to main/master)
        - Uncommitted changes (dirty working tree)

        Args:
            task: The task to check

        Returns:
            TaskSafetyReport with lists of issues found
        """
        from .git_ops import GitOps

        report = TaskSafetyReport()

        for worktree in task.worktrees:
            if not worktree.path.exists():
                continue

            # Get git status
            status = GitOps.get_status(worktree)

            # Check for uncommitted changes
            if status.is_dirty:
                issue = RepoIssue(
                    repo_name=worktree.name,
                    worktree_path=worktree.path,
                    issue_type="dirty",
                    details=f"{status.changed_files} file{'s' if status.changed_files != 1 else ''} changed",
                )
                report.dirty.append(issue)

            # Check for unpushed commits
            if status.ahead > 0:
                issue = RepoIssue(
                    repo_name=worktree.name,
                    worktree_path=worktree.path,
                    issue_type="unpushed",
                    details=f"{status.ahead} commit{'s' if status.ahead != 1 else ''} ahead",
                )
                report.unpushed.append(issue)

            # Check if branch is merged to default branch
            default_branch = GitOps.get_default_branch(worktree)
            is_merged = GitOps.check_merged(worktree, default_branch)

            if not is_merged:
                issue = RepoIssue(
                    repo_name=worktree.name,
                    worktree_path=worktree.path,
                    issue_type="unmerged",
                    details=f"not merged to {default_branch}",
                )
                report.unmerged.append(issue)

        return report

    def push_all_branches(self, task: Task) -> tuple[list[str], list[str]]:
        """Push all branches for task to origin.

        Args:
            task: The task whose branches to push

        Returns:
            Tuple of (successful_repos, failed_repos) with repo names
        """
        from .git_ops import GitOps

        success_repos = []
        failed_repos = []

        for worktree in task.worktrees:
            if not worktree.path.exists():
                failed_repos.append(worktree.name)
                continue

            success, message = GitOps.push(worktree)
            if success:
                success_repos.append(worktree.name)
            else:
                failed_repos.append(worktree.name)

        return success_repos, failed_repos
