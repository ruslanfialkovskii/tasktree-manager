"""Task management service for tasktree-manager."""

import fnmatch
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .claude_hooks import ensure_worktree_claude_settings
from .config import Config
from .models import RepoIssue, Task, TaskSafetyReport, Worktree

# Task name validation pattern
TASK_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9._/\-]+$")


def validate_task_name(name: str) -> str | None:
    """Validate a task name, returning an error message or None if valid.

    Task names become directory paths under TASKS_DIR and git branch names,
    so they must not traverse outside the tasks directory ('..', '.' or
    empty path segments) or look like a git option (leading '-').
    """
    if not name:
        return "Task name cannot be empty"
    if name.startswith("-"):
        return "Task name cannot start with '-'"
    if not TASK_NAME_PATTERN.match(name):
        return "Task name can only contain letters, numbers, '.', '_', '/', '-'"
    parts = name.split("/")
    if "" in parts:
        return "Task name cannot have empty path segments"
    if any(part in (".", "..") for part in parts):
        return "Task name cannot contain '.' or '..' path segments"
    return None


def validate_branch_name(branch: str) -> str | None:
    """Validate a base branch name, returning an error message or None.

    Branch names are passed as positional git arguments; a leading '-'
    would be parsed as a git option (e.g. --upload-pack=<command>).
    """
    if not branch:
        return "Branch name cannot be empty"
    if branch.startswith("-"):
        return "Branch name cannot start with '-'"
    return None


class TaskManager:
    """Manages tasks and worktrees."""

    def __init__(self, config: Config):
        self.config = config

    def _validate_task_name(self, name: str) -> None:
        """Validate task name for safety.

        Raises:
            ValueError: If task name is invalid
        """
        error = validate_task_name(name)
        if error:
            raise ValueError(error)
        # Belt and braces: the segment checks make escapes impossible, but
        # a task path must never resolve outside the tasks directory —
        # finish_task() runs rmtree on it.
        task_path = (self.config.tasks_dir / name).resolve()
        if not task_path.is_relative_to(self.config.tasks_dir.resolve()):
            raise ValueError("Task name resolves outside the tasks directory")

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
        """Get all worktrees for a task (with directory pruning)."""
        worktrees = []
        if not task.path.exists():
            return worktrees

        for dirpath, dirnames, filenames in os.walk(task.path):
            # Prune ignored directories in-place
            dirnames[:] = [d for d in dirnames if d not in self.IGNORED_PATHS]

            # Check if this directory has .git (file or directory)
            if ".git" in dirnames or ".git" in filenames:
                worktree_path = Path(dirpath)
                # Don't descend into .git directories
                if ".git" in dirnames:
                    dirnames[:] = [d for d in dirnames if d != ".git"]

                try:
                    rel_path = worktree_path.relative_to(task.path)
                    # Skip the task root itself if it has .git
                    if str(rel_path) == ".":
                        continue
                    worktrees.append(Worktree(name=str(rel_path), path=worktree_path))
                except ValueError:
                    continue

        return sorted(worktrees, key=lambda w: w.name)

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
        # Validate task name
        self._validate_task_name(name)

        task_path = self.config.tasks_dir / name
        task_path.mkdir(parents=True, exist_ok=True)

        task = Task(name=name, path=task_path)

        for repo_name in repos:
            self._create_worktree(task, repo_name, base_branch)

        task.worktrees = self._get_worktrees(task)
        return task

    def _create_worktree(self, task: Task, repo_name: str, base_branch: str) -> None:
        """Create a worktree for a repo within a task."""
        error = validate_branch_name(base_branch)
        if error:
            raise ValueError(error)

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
            timeout=10,
        )

        # Use -B to reset branch if it exists, -b if it doesn't
        branch_flag = "-B" if branch_check.returncode == 0 else "-b"

        # Fetch the base branch and base the worktree on the remote-tracking
        # ref directly. The local base branch is not trustworthy: the main
        # checkout may sit on another branch or be behind origin, and pulling
        # it (the old approach) silently did nothing in those cases, creating
        # worktrees from stale code. Falls back to the local branch when the
        # fetch fails (offline, or a repo without an "origin" remote).
        network_timeout = self.config.git_timeout
        fetch = subprocess.run(
            ["git", "fetch", "origin", base_branch],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=network_timeout,
        )

        start_point = base_branch
        if fetch.returncode == 0:
            remote_ref = subprocess.run(
                ["git", "rev-parse", "--verify", f"refs/remotes/origin/{base_branch}"],
                cwd=repo_path,
                capture_output=True,
                timeout=10,
            )
            if remote_ref.returncode == 0:
                start_point = f"origin/{base_branch}"

        # Create git worktree with task name as branch. --no-track keeps the
        # task branch from tracking origin/<base>; push sets its own upstream
        # (git push -u origin HEAD).
        result = subprocess.run(
            [
                "git",
                "worktree",
                "add",
                "--no-track",
                branch_flag,
                task.name,
                str(worktree_path),
                start_point,
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=network_timeout,
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            raise ValueError(f"Failed to create worktree for {repo_name}: {error_msg}")

        # Create symlinks for gitignored files
        self._create_gitignore_symlinks(repo_path, worktree_path)

        # Point Claude auto-memory at the repo's own memory dir so it
        # survives worktree deletion (sessions may start here manually,
        # before any launch-time backfill runs)
        if self.config.claude_repo_memory:
            ensure_worktree_claude_settings(worktree_path, repo_path, task.path / ".claude_status")

    def _list_gitignored_files(self, repo_path: Path) -> list[str]:
        """List gitignored files in a repo, relative to the repo root.

        Delegates to git so full gitignore semantics apply (nested
        .gitignore files, directory-wide patterns like ``*.log``).
        ``--directory`` collapses wholly-ignored directories into single
        (later skipped) entries, so huge ignored trees like node_modules
        are never walked or symlinked file-by-file.
        """
        try:
            result = subprocess.run(
                [
                    "git",
                    "ls-files",
                    "--others",
                    "--ignored",
                    "--exclude-standard",
                    "--directory",
                    "-z",
                ],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.SubprocessError, OSError):
            return []
        if result.returncode != 0:
            return []
        return [f for f in result.stdout.split("\0") if f and not f.endswith("/")]

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
        symlink_blocklist in config are excluded, as is anything under .git or
        .claude (tasktree writes its own worktree .claude settings; a symlink
        there would redirect writes into the main checkout).

        Args:
            source_repo: Path to the source repository
            worktree_path: Path to the new worktree
        """
        blocklist = self.config.symlink_blocklist

        for rel_name in self._list_gitignored_files(source_repo):
            match = source_repo / rel_name
            if not match.is_file():
                continue
            rel_path = Path(rel_name)
            if ".git" in rel_path.parts or ".claude" in rel_path.parts:
                continue
            # Skip files matching the blocklist
            if self._matches_blocklist(match.name, blocklist):
                continue
            link_path = worktree_path / rel_path
            # is_symlink() check catches broken symlinks, for which
            # exists() returns False but symlink_to() would still fail
            if not (link_path.exists() or link_path.is_symlink()):
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
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                    cwd=worktree.path,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except (subprocess.SubprocessError, OSError):
                result = None
            if result and result.returncode == 0:
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

        # Remove the worktree using git (if path exists). This deletes the
        # worktree's file tree, so give it the (longer) configured timeout.
        if worktree.path.exists():
            self._run_cleanup_git(
                ["git", "worktree", "remove", "--force", str(worktree.path)],
                cwd=main_repo,
                timeout=self.config.git_timeout,
            )

        # Prune stale worktree references (handles case where path was already deleted)
        self._run_cleanup_git(["git", "worktree", "prune"], cwd=main_repo, timeout=10)

        # Delete the branch
        self._run_cleanup_git(["git", "branch", "-D", branch_name], cwd=main_repo, timeout=10)

    @staticmethod
    def _run_cleanup_git(cmd: list[str], cwd: Path, timeout: int) -> None:
        """Run a best-effort git cleanup command, ignoring failures.

        The timeout keeps a hung git (e.g. a repo on an unreachable network
        mount) from blocking task deletion forever; anything git leaves
        behind is caught by the caller's rmtree or the next worktree prune.
        """
        try:
            subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout)
        except (subprocess.SubprocessError, OSError):
            pass

    def remove_worktree_from_task(self, task: Task, worktree: Worktree) -> None:
        """Remove a single worktree from a task.

        Args:
            task: The task the worktree belongs to
            worktree: The worktree to remove
        """
        self._remove_worktree(worktree, task.name)
        if worktree.path.exists():
            shutil.rmtree(worktree.path)
        task.worktrees = self._get_worktrees(task)

    def get_repos_not_in_task(self, task: Task) -> list[str]:
        """Get list of repos that are not yet in the task."""
        all_repos = set(self.config.get_available_repos())
        task_repos = {wt.name for wt in task.worktrees}
        return sorted(all_repos - task_repos)

    def check_task_safety(self, task: Task) -> TaskSafetyReport:
        """Check if task is safe to delete (parallel version).

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
        valid_worktrees = [wt for wt in task.worktrees if wt.path.exists()]

        if not valid_worktrees:
            return report

        def _check_worktree(worktree: Worktree) -> list[RepoIssue]:
            """Check a single worktree and return list of issues."""
            issues = []

            # Get fresh git status
            status = GitOps.get_status(worktree)

            # Check for uncommitted changes
            if status.is_dirty:
                issues.append(
                    RepoIssue(
                        repo_name=worktree.name,
                        worktree_path=worktree.path,
                        issue_type="dirty",
                        details=f"{status.changed_files} file{'s' if status.changed_files != 1 else ''} changed",
                    )
                )

            if status.ahead > 0:
                issues.append(
                    RepoIssue(
                        repo_name=worktree.name,
                        worktree_path=worktree.path,
                        issue_type="unpushed",
                        details=f"{status.ahead} commit{'s' if status.ahead != 1 else ''} ahead",
                    )
                )

            default_branch = GitOps.get_default_branch(worktree)
            if not GitOps.check_merged(worktree, default_branch):
                issues.append(
                    RepoIssue(
                        repo_name=worktree.name,
                        worktree_path=worktree.path,
                        issue_type="unmerged",
                        details=f"not merged to {default_branch}",
                    )
                )

            return issues

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(_check_worktree, wt): wt for wt in valid_worktrees}
            for future in as_completed(futures):
                for issue in future.result():
                    if issue.issue_type == "dirty":
                        report.dirty.append(issue)
                    elif issue.issue_type == "unpushed":
                        report.unpushed.append(issue)
                    elif issue.issue_type == "unmerged":
                        report.unmerged.append(issue)

        return report

    def push_all_branches(self, task: Task) -> tuple[list[str], list[str]]:
        """Push all branches for task to origin (parallel).

        Args:
            task: The task whose branches to push

        Returns:
            Tuple of (successful_repos, failed_repos) with repo names
        """
        from .git_ops import GitOps

        success_repos = []
        failed_repos = []

        # Handle nonexistent worktrees
        valid_worktrees = []
        for wt in task.worktrees:
            if wt.path.exists():
                valid_worktrees.append(wt)
            else:
                failed_repos.append(wt.name)

        if valid_worktrees:
            # Use parallel push for valid worktrees
            results = GitOps.push_all_parallel(
                Task(name=task.name, path=task.path, worktrees=valid_worktrees)
            )
            for name, success, _ in results:
                if success:
                    success_repos.append(name)
                else:
                    failed_repos.append(name)

        return success_repos, failed_repos

    def ensure_worktree_settings(self, task: Task) -> None:
        """Backfill per-worktree Claude settings for existing worktrees.

        Covers worktrees created before repo memory support (or outside
        tasktree). New worktrees get their settings at creation time.
        """
        if not self.config.claude_repo_memory:
            return

        status_file = task.path / ".claude_status"
        for worktree in task.worktrees:
            repo_path = self.config.repos_dir / worktree.name
            if repo_path.exists() and worktree.path.exists():
                ensure_worktree_claude_settings(worktree.path, repo_path, status_file)

    def ensure_claude_md_files(self, task: Task) -> None:
        """Create the task CLAUDE.md and backfill worktree ones from the repo.

        The task-level file is generated (the task dir is not a git repo).
        Worktree-level files are never generated: when a worktree's branch
        predates the repo's own CLAUDE.md, the repo's file is copied in;
        when the repo has none, the worktree gets none.

        Args:
            task: The task to create CLAUDE.md files for
        """
        task_claude_md = task.path / "CLAUDE.md"
        if not task_claude_md.exists():
            self._create_task_claude_md(task)

        for worktree in task.worktrees:
            wt_claude_md = worktree.path / "CLAUDE.md"
            if not wt_claude_md.exists():
                self._copy_repo_claude_md(worktree)

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

    def _copy_repo_claude_md(self, worktree: Worktree) -> None:
        """Copy the source repo's CLAUDE.md into a worktree that lacks one.

        Happens when the worktree's branch predates the repo's CLAUDE.md.
        Prefers the committed file on the remote default branch (the main
        checkout may be stale or on another branch); falls back to the main
        checkout's working-tree file. Does nothing when the repo has no
        CLAUDE.md — tasktree never generates stub content for repos.

        Args:
            worktree: The worktree to backfill
        """
        repo_path = self.config.repos_dir / worktree.name
        if not repo_path.exists():
            return

        content: str | None = None
        try:
            head = subprocess.run(
                ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if head.returncode == 0:
                show = subprocess.run(
                    ["git", "show", f"{head.stdout.strip()}:CLAUDE.md"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if show.returncode == 0:
                    content = show.stdout
        except (OSError, subprocess.SubprocessError):
            pass

        if content is None:
            repo_claude_md = repo_path / "CLAUDE.md"
            if repo_claude_md.exists():
                content = repo_claude_md.read_text()

        if content:
            (worktree.path / "CLAUDE.md").write_text(content)
