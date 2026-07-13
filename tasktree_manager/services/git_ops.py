"""Git operations service for tasktree-manager."""

import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

from .models import GitStatus, Task, Worktree

# Matches the "[ahead 1, behind 2]" suffix of a porcelain branch header
_AHEAD_BEHIND_RE = re.compile(r"\[(?:ahead (\d+))?(?:, )?(?:behind (\d+))?\]")


class GitOps:
    """Git operations for worktrees."""

    # Timeout for local-only git commands (status, rev-parse) in seconds
    LOCAL_TIMEOUT = 5
    # Timeout for commands that may hit the network (push/pull/fetch).
    # Overridden at app startup from the [git] timeout config setting.
    network_timeout: int = 30

    @staticmethod
    def get_status(worktree: Worktree) -> GitStatus:
        """Get the git status of a worktree.

        Uses a single `git status --porcelain --branch -z` call to read the
        branch name, ahead/behind counts and changed files at once. The -z
        format is NUL-separated and unquoted, so exotic filenames (quotes,
        spaces, newlines) come through verbatim.
        """
        status = GitStatus()

        if not worktree.path.exists():
            return status

        try:
            result = subprocess.run(
                ["git", "status", "--porcelain", "--branch", "-z"],
                cwd=worktree.path,
                capture_output=True,
                text=True,
                timeout=GitOps.LOCAL_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            status.error = "Git status timed out"
            return status
        except (subprocess.SubprocessError, OSError) as e:
            status.error = f"Git status error: {e}"
            return status

        if result.returncode != 0:
            status.error = f"Git status failed: {result.stderr.strip() or 'unknown error'}"
            return status

        # Rename/copy entries are followed by the original path as an
        # extra NUL-separated token, hence the manual index walk
        tokens = result.stdout.split("\0")
        index = 0
        while index < len(tokens):
            token = tokens[index]
            index += 1
            if len(token) < 4:
                continue
            if token.startswith("## "):
                GitOps._parse_branch_header(token[3:], status)
                continue
            status_code = token[:2]
            filename = token[3:]

            if "R" in status_code or "C" in status_code:
                if index < len(tokens) and tokens[index]:
                    filename = f"{tokens[index]} -> {filename}"
                    index += 1

            if status_code == "??":
                status.untracked.append(filename)
            elif "U" in status_code or status_code in ("AA", "DD"):
                # Unmerged (conflict) entries - count as modified so the
                # worktree shows as dirty and safety checks block deletion
                status.modified.append(filename)
            elif status_code[0] in "MADRCT":
                status.staged.append(filename)
            elif status_code[1] in "MADRCT":
                status.modified.append(filename)
            else:
                continue
            status.entries.append((status_code, filename))

        return status

    @staticmethod
    def _parse_branch_header(header: str, status: GitStatus) -> None:
        """Parse the `## ...` header of `git status --porcelain --branch`.

        Handles the formats:
            HEAD (no branch)                      <- detached, branch stays ""
            No commits yet on <branch>
            <branch>
            <branch>...<upstream>
            <branch>...<upstream> [ahead 1, behind 2]
        """
        if header.startswith("HEAD"):
            return
        if header.startswith("No commits yet on "):
            status.branch = header[len("No commits yet on ") :]
            return

        status.branch = header.split("...", 1)[0]

        match = _AHEAD_BEHIND_RE.search(header)
        if match:
            status.ahead = int(match.group(1) or 0)
            status.behind = int(match.group(2) or 0)

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
                timeout=GitOps.network_timeout,
            )
            if result.returncode == 0:
                return True, result.stdout or "Pushed successfully"
            return False, result.stderr or "Push failed"
        except subprocess.TimeoutExpired:
            return False, "Push timed out"
        except (subprocess.SubprocessError, OSError) as e:
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
                timeout=GitOps.network_timeout,
            )
            if result.returncode == 0:
                return True, result.stdout or "Pulled successfully"
            return False, result.stderr or "Pull failed"
        except subprocess.TimeoutExpired:
            return False, "Pull timed out"
        except (subprocess.SubprocessError, OSError) as e:
            return False, str(e)

    @staticmethod
    def _git_stdout(worktree: Worktree, args: list[str]) -> str:
        """Run a local read-only git command in the worktree, returning stdout.

        Returns "" on any failure. The exit code is intentionally ignored:
        ``git diff --no-index`` returns non-zero whenever files differ, and a
        failed command leaves stdout empty anyway.
        """
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=worktree.path,
                capture_output=True,
                text=True,
                timeout=GitOps.LOCAL_TIMEOUT,
            )
        except (subprocess.SubprocessError, OSError):
            return ""
        return result.stdout

    @staticmethod
    def _list_untracked(worktree: Worktree) -> list[str]:
        """List untracked (but not ignored) files in a worktree."""
        out = GitOps._git_stdout(worktree, ["ls-files", "--others", "--exclude-standard", "-z"])
        return [f for f in out.split("\0") if f]

    @staticmethod
    def get_worktree_diff(worktree: Worktree, label: str | None = None) -> str:
        """Return a unified diff of all uncommitted changes in a worktree.

        Combines staged and unstaged tracked changes (``git diff HEAD``) with
        untracked files, so the result mirrors what a working-tree review shows.
        When *label* is given, every file path is prefixed with ``<label>/`` so
        diffs from several repos can be concatenated into one view without
        colliding on identical relative paths.

        Returns an empty string when the worktree is clean or missing.
        """
        if not worktree.path.exists():
            return ""

        # Without a label, git's default a/ b/ prefixes are used.
        prefixes = [f"--src-prefix=a/{label}/", f"--dst-prefix=b/{label}/"] if label else []
        parts: list[str] = []

        # Tracked changes (staged + unstaged) relative to HEAD.
        parts.append(GitOps._git_stdout(worktree, ["diff", "HEAD", "--no-color", *prefixes]))

        # Untracked files, rendered as additions against /dev/null.
        for untracked in GitOps._list_untracked(worktree):
            parts.append(
                GitOps._git_stdout(
                    worktree,
                    ["diff", "--no-index", "--no-color", *prefixes, "--", "/dev/null", untracked],
                )
            )

        return "".join(parts)

    @staticmethod
    def build_task_diff(task: Task) -> str:
        """Build a combined diff across all of a task's worktrees.

        Each worktree's changes are labelled with its repo name so a single
        review shows every repo without path collisions. Returns an empty
        string when nothing in the task has changed.
        """
        parts = [GitOps.get_worktree_diff(wt, label=wt.name) for wt in task.worktrees]
        return "".join(p for p in parts if p)

    @staticmethod
    def get_default_branch(worktree: Worktree) -> str:
        """Get the default branch (main/master) for a worktree's repo.

        Returns:
            The default branch name, or "main" as fallback.
        """
        try:
            # Try to get the default branch from origin/HEAD
            result = subprocess.run(
                ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
                cwd=worktree.path,
                capture_output=True,
                text=True,
                timeout=GitOps.LOCAL_TIMEOUT,
            )
            if result.returncode == 0:
                # Output is like "refs/remotes/origin/main"
                ref = result.stdout.strip()
                return ref.split("/")[-1]
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass

        # Fallback: check which of main/master exists
        for branch in ["main", "master"]:
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--verify", f"refs/remotes/origin/{branch}"],
                    cwd=worktree.path,
                    capture_output=True,
                    timeout=GitOps.LOCAL_TIMEOUT,
                )
                if result.returncode == 0:
                    return branch
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                pass

        # Final fallback
        return "main"

    @staticmethod
    def check_merged(worktree: Worktree, base_branch: str) -> bool:
        """Check if the current branch is merged into base_branch.

        Args:
            worktree: The worktree to check
            base_branch: The base branch to check against (e.g., "main", "master")

        Returns:
            True if current branch is merged into base_branch, False otherwise.
        """
        try:
            # Fetch latest remote refs so we detect merges done via GitLab/GitHub UI
            subprocess.run(
                ["git", "fetch", "origin", base_branch],
                cwd=worktree.path,
                capture_output=True,
                timeout=GitOps.network_timeout,
            )
            # Use git merge-base --is-ancestor to check if HEAD is reachable from base
            # This checks if the current branch has been merged
            result = subprocess.run(
                ["git", "merge-base", "--is-ancestor", "HEAD", f"origin/{base_branch}"],
                cwd=worktree.path,
                capture_output=True,
                timeout=GitOps.LOCAL_TIMEOUT,
            )
            # Exit code 0 means HEAD is an ancestor of base (merged)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            # If we can't determine, assume not merged (safer)
            return False

    @staticmethod
    def update_all_worktree_statuses(worktrees: list[Worktree], max_workers: int = 8) -> None:
        """Update status for multiple worktrees in parallel.

        Args:
            worktrees: List of worktrees to update
            max_workers: Maximum number of parallel workers
        """
        if not worktrees:
            return

        workers = min(max_workers, len(worktrees))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(GitOps.update_worktree_status, wt): wt for wt in worktrees}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    # One failing worktree must not abort the whole refresh
                    continue

    @staticmethod
    def get_statuses_parallel(
        worktrees: list[Worktree], max_workers: int = 8
    ) -> dict[str, GitStatus]:
        """Get full statuses for multiple worktrees in parallel, keyed by name.

        Args:
            worktrees: List of worktrees to query
            max_workers: Maximum number of parallel workers

        Returns:
            Dict mapping worktree name to its GitStatus
        """
        statuses: dict[str, GitStatus] = {}
        if not worktrees:
            return statuses

        workers = min(max_workers, len(worktrees))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(GitOps.get_status, wt): wt for wt in worktrees}
            for future in as_completed(futures):
                wt = futures[future]
                try:
                    statuses[wt.name] = future.result()
                except Exception:
                    continue
        return statuses

    @staticmethod
    def push_all_parallel(task: Task, max_workers: int = 3) -> list[tuple[str, bool, str]]:
        """Push all worktrees in a task in parallel.

        Args:
            task: The task containing worktrees to push
            max_workers: Maximum number of parallel workers

        Returns:
            List of (worktree_name, success, message) tuples
        """
        if not task.worktrees:
            return []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(GitOps.push, wt): wt for wt in task.worktrees}
            results = []
            for future in as_completed(futures):
                wt = futures[future]
                success, message = future.result()
                results.append((wt.name, success, message))
            return results

    @staticmethod
    def pull_all_parallel(task: Task, max_workers: int = 3) -> list[tuple[str, bool, str]]:
        """Pull all worktrees in a task in parallel.

        Args:
            task: The task containing worktrees to pull
            max_workers: Maximum number of parallel workers

        Returns:
            List of (worktree_name, success, message) tuples
        """
        if not task.worktrees:
            return []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(GitOps.pull, wt): wt for wt in task.worktrees}
            results = []
            for future in as_completed(futures):
                wt = futures[future]
                success, message = future.result()
                results.append((wt.name, success, message))
            return results
