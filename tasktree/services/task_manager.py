"""Task management service for tasktree."""

import fnmatch
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

    # Directories to skip when scanning for worktrees
    IGNORED_PATHS = {".terraform", "node_modules", "vendor", ".git"}

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

                # Skip if path contains ignored directories
                path_parts = worktree_path.relative_to(task.path).parts
                if any(part in self.IGNORED_PATHS for part in path_parts):
                    continue

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

        # Fetch and pull base branch to ensure worktree starts from latest code
        subprocess.run(
            ["git", "fetch", "origin", base_branch],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Pull to fast-forward the local base branch if possible
        subprocess.run(
            ["git", "pull", "--ff-only", "origin", base_branch],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60,
        )

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

        # Create symlinks for gitignored files
        self._create_gitignore_symlinks(repo_path, worktree_path)

    def _parse_gitignore(self, gitignore_path: Path) -> list[str]:
        """Parse .gitignore and return glob patterns for files (not directories).

        Args:
            gitignore_path: Path to the .gitignore file

        Returns:
            List of glob patterns to match files
        """
        patterns = []
        for line in gitignore_path.read_text().splitlines():
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            # Skip negation patterns
            if line.startswith("!"):
                continue
            # Skip directory-only patterns (ending with /)
            if line.endswith("/"):
                continue
            # Convert to glob pattern
            patterns.append(line)
        return patterns

    def _matches_blocklist(self, filename: str, blocklist: list[str]) -> bool:
        """Check if filename matches any blocklist pattern.

        Args:
            filename: The filename to check
            blocklist: List of glob patterns to match against

        Returns:
            True if the filename matches any blocklist pattern
        """
        return any(fnmatch.fnmatch(filename, pattern) for pattern in blocklist)

    def _create_gitignore_symlinks(self, source_repo: Path, worktree_path: Path) -> None:
        """Create symlinks for gitignored files from source repo to worktree.

        This allows gitignored files like .env to be shared between the main repo
        and worktrees without having to manually copy them. Files matching the
        symlink_blocklist in config are excluded.

        Args:
            source_repo: Path to the source repository
            worktree_path: Path to the new worktree
        """
        gitignore_path = source_repo / ".gitignore"
        if not gitignore_path.exists():
            return

        # Parse .gitignore patterns
        patterns = self._parse_gitignore(gitignore_path)
        blocklist = self.config.symlink_blocklist

        # Find matching files in source repo (not directories, not nested in .git)
        for pattern in patterns:
            for match in source_repo.glob(pattern):
                if match.is_file() and ".git" not in match.parts:
                    # Skip files matching the blocklist
                    if self._matches_blocklist(match.name, blocklist):
                        continue
                    # Create symlink in worktree
                    rel_path = match.relative_to(source_repo)
                    link_path = worktree_path / rel_path
                    if not link_path.exists():
                        link_path.parent.mkdir(parents=True, exist_ok=True)
                        link_path.symlink_to(match)

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

    def ensure_claude_md_files(self, task: Task) -> None:
        """Create CLAUDE.md files if they don't exist (never overwrite).

        Args:
            task: The task to create CLAUDE.md files for
        """
        task_claude_md = task.path / "CLAUDE.md"
        if not task_claude_md.exists():
            self._create_task_claude_md(task)

        for worktree in task.worktrees:
            wt_claude_md = worktree.path / "CLAUDE.md"
            if not wt_claude_md.exists():
                self._create_worktree_claude_md(task, worktree)

    def _create_task_claude_md(self, task: Task) -> None:
        """Generate task CLAUDE.md with task name + worktree paths.

        Args:
            task: The task to create CLAUDE.md for
        """
        content = f"""# Task: {task.name}

## Worktrees

"""
        for wt in task.worktrees:
            content += f"- **{wt.name}**: `{wt.path}`\n"
            if wt.branch:
                content += f"  - Branch: `{wt.branch}`\n"

        content += "\n## Notes\n\nAdd task-specific context here.\n"
        (task.path / "CLAUDE.md").write_text(content)

    def _create_worktree_claude_md(self, task: Task, worktree: Worktree) -> None:
        """Generate worktree CLAUDE.md with branch/path info.

        Args:
            task: The parent task
            worktree: The worktree to create CLAUDE.md for
        """
        content = f"""# Worktree: {worktree.name}

- **Path**: `{worktree.path}`
- **Branch**: `{worktree.branch or 'unknown'}`
- **Task**: {task.name}

## Notes

Add worktree-specific context here.
"""
        (worktree.path / "CLAUDE.md").write_text(content)
