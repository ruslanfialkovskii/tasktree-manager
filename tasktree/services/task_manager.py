"""Task management service for tasktree."""

import subprocess
import shutil
from pathlib import Path
from dataclasses import dataclass, field

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
        """Get all worktrees for a task."""
        worktrees = []
        if not task.path.exists():
            return worktrees

        for item in sorted(task.path.iterdir()):
            if item.is_dir() and (item / ".git").exists():
                worktree = Worktree(name=item.name, path=item)
                worktrees.append(worktree)
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

        # Create git worktree with task name as branch
        subprocess.run(
            ["git", "worktree", "add", "-b", task.name, str(worktree_path), base_branch],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

    def add_repo_to_task(self, task: Task, repo_name: str, base_branch: str = "master") -> None:
        """Add a repo worktree to an existing task."""
        self._create_worktree(task, repo_name, base_branch)
        task.worktrees = self._get_worktrees(task)

    def finish_task(self, task: Task) -> None:
        """Finish/delete a task and clean up worktrees."""
        for worktree in task.worktrees:
            self._remove_worktree(worktree)

        # Remove task directory
        if task.path.exists():
            shutil.rmtree(task.path)

    def _remove_worktree(self, worktree: Worktree) -> None:
        """Remove a worktree from its main repo."""
        if not worktree.path.exists():
            return

        # Find the main repo for this worktree
        git_dir = worktree.path / ".git"
        if git_dir.is_file():
            # Read the gitdir from the .git file
            content = git_dir.read_text().strip()
            if content.startswith("gitdir:"):
                gitdir_path = content[7:].strip()
                # The main repo is typically at the parent of .git/worktrees/
                gitdir = Path(gitdir_path)
                if "worktrees" in gitdir.parts:
                    worktrees_idx = gitdir.parts.index("worktrees")
                    main_repo = Path(*gitdir.parts[:worktrees_idx])

                    # Remove the worktree using git
                    subprocess.run(
                        ["git", "worktree", "remove", "--force", str(worktree.path)],
                        cwd=main_repo,
                        capture_output=True,
                    )

                    # Also try to delete the branch
                    branch_name = worktree.path.parent.name  # task name
                    subprocess.run(
                        ["git", "branch", "-D", branch_name],
                        cwd=main_repo,
                        capture_output=True,
                    )

    def get_repos_not_in_task(self, task: Task) -> list[str]:
        """Get list of repos that are not yet in the task."""
        all_repos = set(self.config.get_available_repos())
        task_repos = {wt.name for wt in task.worktrees}
        return sorted(all_repos - task_repos)
