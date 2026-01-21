"""Tests for the git operations service."""

import subprocess

from tasktree.services.git_ops import GitOps, GitStatus
from tasktree.services.task_manager import Worktree


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
