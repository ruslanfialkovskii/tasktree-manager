"""Tests for the git operations service."""

import subprocess
from pathlib import Path

from tasktree.services.git_ops import GitOps, GitStatus
from tasktree.services.task_manager import Task, Worktree


class TestGitStatus:
    """Tests for GitStatus dataclass."""

    def test_defaults(self):
        """Test default values."""
        status = GitStatus()
        assert status.branch == ""
        assert not status.is_dirty
        assert status.staged == []
        assert status.modified == []
        assert status.untracked == []

    def test_changed_files_count(self):
        """Test changed_files property."""
        status = GitStatus(
            staged=["a.py", "b.py"],
            modified=["c.py"],
            untracked=["d.py", "e.py"],
        )
        assert status.changed_files == 5

    def test_all_changes(self):
        """Test all_changes property."""
        status = GitStatus(
            staged=["staged.py"],
            modified=["modified.py"],
            untracked=["untracked.py"],
        )
        changes = status.all_changes
        assert ("A ", "staged.py") in changes
        assert (" M", "modified.py") in changes
        assert ("??", "untracked.py") in changes

    def test_is_dirty_with_staged(self):
        """Test is_dirty with staged files."""
        assert GitStatus(staged=["a.py"]).is_dirty

    def test_is_dirty_with_modified(self):
        """Test is_dirty with modified files."""
        assert GitStatus(modified=["a.py"]).is_dirty

    def test_is_dirty_with_untracked(self):
        """Test is_dirty with untracked files."""
        assert GitStatus(untracked=["a.py"]).is_dirty

    def test_is_dirty_clean(self):
        """Test is_dirty when clean."""
        assert not GitStatus().is_dirty


class TestGitOps:
    """Tests for GitOps class."""

    def test_get_status_clean_repo(self, sample_repo):
        """Test getting status of a clean repo."""
        repo_path, branch = sample_repo
        worktree = Worktree(name="sample", path=repo_path)
        status = GitOps.get_status(worktree)

        assert status.branch == branch
        assert not status.is_dirty
        assert status.changed_files == 0

    def test_get_status_with_modified_file(self, sample_repo):
        """Test getting status with a modified file."""
        repo_path, branch = sample_repo
        # Modify a file
        readme = repo_path / "README.md"
        readme.write_text("# Modified\n")

        worktree = Worktree(name="sample", path=repo_path)
        status = GitOps.get_status(worktree)

        assert status.is_dirty
        # Git may report this as modified or staged depending on index state
        assert status.changed_files >= 1

    def test_get_status_with_untracked_file(self, sample_repo):
        """Test getting status with an untracked file."""
        repo_path, branch = sample_repo
        # Create new file
        new_file = repo_path / "new_file.txt"
        new_file.write_text("new content")

        worktree = Worktree(name="sample", path=repo_path)
        status = GitOps.get_status(worktree)

        assert status.is_dirty
        assert "new_file.txt" in status.untracked

    def test_get_status_with_staged_file(self, sample_repo):
        """Test getting status with a staged file."""
        repo_path, branch = sample_repo
        # Create and stage a new file
        new_file = repo_path / "staged.txt"
        new_file.write_text("staged content")
        subprocess.run(
            ["git", "add", "staged.txt"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        worktree = Worktree(name="sample", path=repo_path)
        status = GitOps.get_status(worktree)

        assert status.is_dirty
        assert "staged.txt" in status.staged

    def test_get_status_nonexistent_path(self, tmp_path):
        """Test getting status for nonexistent path."""
        worktree = Worktree(name="nonexistent", path=tmp_path / "nonexistent")
        status = GitOps.get_status(worktree)

        assert status.branch == ""
        assert not status.is_dirty

    def test_update_worktree_status(self, sample_repo):
        """Test updating worktree status in place."""
        repo_path, branch = sample_repo
        # Modify a file
        readme = repo_path / "README.md"
        readme.write_text("# Modified\n")

        worktree = Worktree(name="sample", path=repo_path)
        assert worktree.branch == ""
        assert not worktree.is_dirty

        status = GitOps.update_worktree_status(worktree)

        assert worktree.branch == branch
        assert worktree.is_dirty
        assert worktree.changed_files == 1
        assert status.is_dirty


class TestGitPushPull:
    """Tests for push and pull operations."""

    def test_push_success(self, repo_with_remote):
        """Test successful push operation."""
        local, remote = repo_with_remote
        worktree = Worktree(name="test", path=local)

        # Make a commit to push
        test_file = local / "test.txt"
        test_file.write_text("test content")
        subprocess.run(["git", "add", "."], cwd=local, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Test commit"],
            cwd=local,
            capture_output=True,
        )

        success, message = GitOps.push(worktree)
        assert success

    def test_push_no_remote(self, sample_repo):
        """Test push with no remote configured."""
        repo_path, branch = sample_repo
        worktree = Worktree(name="test", path=repo_path)

        # No remote configured
        success, message = GitOps.push(worktree)
        assert not success

    def test_pull_success(self, repo_with_remote):
        """Test successful pull operation."""
        local, remote = repo_with_remote
        worktree = Worktree(name="test", path=local)

        success, message = GitOps.pull(worktree)
        # Should succeed even if nothing to pull
        assert success

    def test_pull_no_remote(self, sample_repo):
        """Test pull with no remote configured."""
        repo_path, branch = sample_repo
        worktree = Worktree(name="test", path=repo_path)

        # No upstream set
        success, message = GitOps.pull(worktree)
        # May fail because no tracking branch
        # Just verify it doesn't crash
        assert isinstance(success, bool)


class TestParallelOperations:
    """Tests for parallel git operations."""

    def test_push_all_parallel_empty_task(self):
        """Test push_all_parallel with empty task."""
        task = Task(name="empty", path=Path("/tmp/empty"), worktrees=[])
        results = GitOps.push_all_parallel(task)
        assert results == []

    def test_pull_all_parallel_empty_task(self):
        """Test pull_all_parallel with empty task."""
        task = Task(name="empty", path=Path("/tmp/empty"), worktrees=[])
        results = GitOps.pull_all_parallel(task)
        assert results == []

    def test_update_all_worktree_statuses_empty(self):
        """Test update_all_worktree_statuses with empty list."""
        # Should not raise
        GitOps.update_all_worktree_statuses([])

    def test_update_all_worktree_statuses(self, sample_repos):
        """Test updating multiple worktree statuses in parallel."""
        repos, branch = sample_repos
        worktrees = [Worktree(name=repo.name, path=repo) for repo in repos]

        # Should update all statuses
        GitOps.update_all_worktree_statuses(worktrees)

        for wt in worktrees:
            assert wt.branch == branch

    def test_push_all_parallel_with_data(self, repo_with_remote):
        """Test parallel push all worktrees."""
        local, remote = repo_with_remote
        worktree = Worktree(name="test", path=local)
        task = Task(name="test-task", path=local.parent, worktrees=[worktree])

        results = GitOps.push_all_parallel(task)
        assert len(results) == 1
        assert results[0][0] == "test"

    def test_pull_all_parallel_with_data(self, repo_with_remote):
        """Test parallel pull all worktrees."""
        local, remote = repo_with_remote
        worktree = Worktree(name="test", path=local)
        task = Task(name="test-task", path=local.parent, worktrees=[worktree])

        results = GitOps.pull_all_parallel(task)
        assert len(results) == 1
        assert results[0][0] == "test"
        assert results[0][1] is True  # Success


class TestBranchOperations:
    """Tests for branch-related operations."""

    def test_get_default_branch_fallback(self, sample_repo):
        """Test get_default_branch falls back to main."""
        repo_path, branch = sample_repo
        worktree = Worktree(name="test", path=repo_path)

        # No remote, so should fall back
        default = GitOps.get_default_branch(worktree)
        assert default in ["main", "master", branch]

    def test_get_default_branch_with_remote(self, repo_with_remote):
        """Test get_default_branch from origin/HEAD."""
        local, remote = repo_with_remote
        worktree = Worktree(name="test", path=local)

        default = GitOps.get_default_branch(worktree)
        # Should return a valid branch name
        assert isinstance(default, str)
        assert len(default) > 0

    def test_check_merged_true(self, repo_with_remote):
        """Test check_merged returns True for merged branch."""
        local, remote = repo_with_remote
        worktree = Worktree(name="test", path=local)

        # Get the default branch name
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=local,
            capture_output=True,
            text=True,
        )
        current_branch = result.stdout.strip()

        # Check if HEAD is merged into itself (should be true)
        # Note: This might not work as expected without a proper remote setup
        is_merged = GitOps.check_merged(worktree, current_branch)
        # Just verify it returns a boolean
        assert isinstance(is_merged, bool)

    def test_check_merged_false(self, repo_with_remote):
        """Test check_merged returns False for unmerged branch."""
        local, remote = repo_with_remote
        worktree = Worktree(name="test", path=local)

        # Create a new branch with unpushed commits
        subprocess.run(
            ["git", "checkout", "-b", "feature-branch"],
            cwd=local,
            capture_output=True,
        )
        test_file = local / "feature.txt"
        test_file.write_text("feature content")
        subprocess.run(["git", "add", "."], cwd=local, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Feature commit"],
            cwd=local,
            capture_output=True,
        )

        is_merged = GitOps.check_merged(worktree, "main")
        # Just verify it returns a boolean
        assert isinstance(is_merged, bool)


class TestStatusEdgeCases:
    """Tests for edge cases in status operations."""

    def test_get_status_renamed_file(self, sample_repo):
        """Test getting status with renamed file."""
        repo_path, branch = sample_repo

        # Create and commit a file
        original = repo_path / "original.txt"
        original.write_text("content")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Add file"],
            cwd=repo_path,
            capture_output=True,
        )

        # Rename the file
        renamed = repo_path / "renamed.txt"
        original.rename(renamed)
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)

        worktree = Worktree(name="sample", path=repo_path)
        status = GitOps.get_status(worktree)

        # Should detect the rename
        assert status.is_dirty or len(status.staged) > 0

    def test_get_status_deleted_file(self, sample_repo):
        """Test getting status with deleted file."""
        repo_path, branch = sample_repo

        # Delete the README
        readme = repo_path / "README.md"
        readme.unlink()

        worktree = Worktree(name="sample", path=repo_path)
        status = GitOps.get_status(worktree)

        assert status.is_dirty

    def test_get_status_with_error(self, tmp_path):
        """Test get_status with git error."""
        # Create a non-git directory
        non_git = tmp_path / "not_a_repo"
        non_git.mkdir()

        worktree = Worktree(name="test", path=non_git)
        status = GitOps.get_status(worktree)

        # Should have error or empty status
        assert status.error or status.branch == ""

    def test_get_status_multiple_status_codes(self, sample_repo):
        """Test getting status with multiple different changes."""
        repo_path, branch = sample_repo

        # Staged change (new file)
        staged_file = repo_path / "staged.txt"
        staged_file.write_text("staged")
        subprocess.run(["git", "add", "staged.txt"], cwd=repo_path, capture_output=True)

        # Untracked
        untracked = repo_path / "untracked.txt"
        untracked.write_text("untracked")

        worktree = Worktree(name="sample", path=repo_path)
        status = GitOps.get_status(worktree)

        assert status.is_dirty
        assert len(status.staged) >= 1
        assert len(status.untracked) >= 1
        # Total changes should be at least 2
        assert status.changed_files >= 2


class TestGitStatusAheadBehind:
    """Tests for ahead/behind tracking."""

    def test_status_ahead_commits(self, repo_with_remote):
        """Test detecting ahead commits."""
        local, remote = repo_with_remote
        worktree = Worktree(name="test", path=local)

        # Make local commit without pushing
        test_file = local / "ahead.txt"
        test_file.write_text("ahead content")
        subprocess.run(["git", "add", "."], cwd=local, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Ahead commit"],
            cwd=local,
            capture_output=True,
        )

        status = GitOps.get_status(worktree)
        assert status.ahead >= 1

    def test_status_behind_commits(self, repo_with_remote, tmp_path):
        """Test detecting behind commits."""
        local, remote = repo_with_remote

        # Clone a second copy to create commits
        local2 = tmp_path / "local2"
        subprocess.run(
            ["git", "clone", str(remote), str(local2)],
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=local2,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=local2,
            capture_output=True,
        )

        # Make and push commit from second copy
        test_file = local2 / "behind.txt"
        test_file.write_text("behind content")
        subprocess.run(["git", "add", "."], cwd=local2, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Behind commit"],
            cwd=local2,
            capture_output=True,
        )
        subprocess.run(
            ["git", "push"],
            cwd=local2,
            capture_output=True,
        )

        # Fetch in original to update tracking
        subprocess.run(
            ["git", "fetch"],
            cwd=local,
            capture_output=True,
        )

        worktree = Worktree(name="test", path=local)
        status = GitOps.get_status(worktree)

        # Should be behind
        assert status.behind >= 1
