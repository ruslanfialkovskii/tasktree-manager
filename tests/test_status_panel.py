"""Tests for the StatusPanel widget."""

import pytest

from tasktree.services.git_ops import GitStatus
from tasktree.services.task_manager import Worktree
from tasktree.widgets.status_panel import StatusPanel


class TestStatusPanel:
    """Tests for StatusPanel widget."""

    @pytest.fixture
    def sample_worktree(self, tmp_path):
        """Create a sample Worktree."""
        path = tmp_path / "worktree"
        path.mkdir()
        return Worktree(name="test-worktree", path=path, branch="feature-branch")

    def test_initial_state(self):
        """Test panel initial state."""
        panel = StatusPanel()
        assert panel._worktree_name == ""
        assert panel._status is None

    async def test_update_status_with_worktree(self, app, sample_worktree):
        """Test updating status with a worktree."""
        async with app.run_test() as pilot:
            await pilot.pause()

            panel = app.query_one("#status-display", StatusPanel)
            status = GitStatus(
                branch="feature-branch",
                staged=["file1.py"],
                modified=["file2.py"],
                untracked=["file3.txt"],
            )

            panel.update_status(sample_worktree, status)

            assert panel._worktree_name == "test-worktree"
            assert panel._status == status

    async def test_update_status_none_worktree(self, app, sample_worktree):
        """Test updating status with None worktree clears display."""
        async with app.run_test() as pilot:
            await pilot.pause()

            panel = app.query_one("#status-display", StatusPanel)
            # First set some status
            status = GitStatus(branch="main")
            panel.update_status(sample_worktree, status)

            # Then clear it
            panel.update_status(None, None)

            assert panel._worktree_name == ""
            assert panel._status is None

    async def test_display_clean_status(self, app, sample_worktree):
        """Test display of clean worktree status."""
        async with app.run_test() as pilot:
            await pilot.pause()

            panel = app.query_one("#status-display", StatusPanel)
            status = GitStatus(branch="main", staged=[], modified=[], untracked=[])

            panel.update_status(sample_worktree, status)

            assert panel._worktree_name == "test-worktree"
            assert not panel._status.is_dirty

    async def test_display_dirty_status(self, app, sample_worktree):
        """Test display of dirty worktree status."""
        async with app.run_test() as pilot:
            await pilot.pause()

            panel = app.query_one("#status-display", StatusPanel)
            status = GitStatus(
                branch="feature",
                staged=["added.py"],
                modified=["changed.py"],
                untracked=["new.txt"],
            )

            panel.update_status(sample_worktree, status)

            assert panel._status.is_dirty

    async def test_display_sync_info_ahead(self, app, sample_worktree):
        """Test display with ahead commits."""
        async with app.run_test() as pilot:
            await pilot.pause()

            panel = app.query_one("#status-display", StatusPanel)
            status = GitStatus(branch="feature", ahead=3, behind=0)

            panel.update_status(sample_worktree, status)

            assert panel._status.ahead == 3

    async def test_display_sync_info_behind(self, app, sample_worktree):
        """Test display with behind commits."""
        async with app.run_test() as pilot:
            await pilot.pause()

            panel = app.query_one("#status-display", StatusPanel)
            status = GitStatus(branch="feature", ahead=0, behind=2)

            panel.update_status(sample_worktree, status)

            assert panel._status.behind == 2

    async def test_display_sync_info_ahead_behind(self, app, sample_worktree):
        """Test display with both ahead and behind commits."""
        async with app.run_test() as pilot:
            await pilot.pause()

            panel = app.query_one("#status-display", StatusPanel)
            status = GitStatus(branch="feature", ahead=2, behind=1)

            panel.update_status(sample_worktree, status)

            assert panel._status.ahead == 2
            assert panel._status.behind == 1

    async def test_display_error_status(self, app, sample_worktree):
        """Test display of error status."""
        async with app.run_test() as pilot:
            await pilot.pause()

            panel = app.query_one("#status-display", StatusPanel)
            status = GitStatus(branch="", error="Git operation timed out")

            panel.update_status(sample_worktree, status)

            assert panel._status.error == "Git operation timed out"

    async def test_clear_status(self, app, sample_worktree):
        """Test clearing the status display."""
        async with app.run_test() as pilot:
            await pilot.pause()

            panel = app.query_one("#status-display", StatusPanel)
            # First set some status
            status = GitStatus(branch="main", staged=["file.py"])
            panel.update_status(sample_worktree, status)

            # Clear it
            panel.clear_status()

            assert panel._worktree_name == ""
            assert panel._status is None

    async def test_set_loading_true(self, app):
        """Test showing loading indicator."""
        async with app.run_test() as pilot:
            await pilot.pause()

            panel = app.query_one("#status-display", StatusPanel)
            panel.set_loading(True)
            # Panel should show loading state without errors

    async def test_set_loading_false(self, app, sample_worktree):
        """Test hiding loading indicator restores display."""
        async with app.run_test() as pilot:
            await pilot.pause()

            panel = app.query_one("#status-display", StatusPanel)
            # Set status first
            status = GitStatus(branch="main")
            panel.update_status(sample_worktree, status)

            # Show loading
            panel.set_loading(True)

            # Hide loading
            panel.set_loading(False)

            # Should restore the previous status display
            assert panel._worktree_name == "test-worktree"

    async def test_display_various_status_codes(self, app, sample_worktree):
        """Test display handles various git status codes."""
        async with app.run_test() as pilot:
            await pilot.pause()

            panel = app.query_one("#status-display", StatusPanel)
            status = GitStatus(
                branch="feature",
                staged=["added.py", "renamed.py"],
                modified=["modified.py"],
                untracked=["untracked.txt", "temp/"],
            )

            panel.update_status(sample_worktree, status)

            # All changes should be accounted for
            assert panel._status.changed_files == 5

    async def test_update_display_no_worktree(self, app):
        """Test _update_display with no worktree set."""
        async with app.run_test() as pilot:
            await pilot.pause()

            panel = app.query_one("#status-display", StatusPanel)
            panel._worktree_name = ""
            panel._status = None

            # Should not raise
            panel._update_display()

    async def test_update_status_none_status(self, app, sample_worktree):
        """Test update_status with None status."""
        async with app.run_test() as pilot:
            await pilot.pause()

            panel = app.query_one("#status-display", StatusPanel)
            panel.update_status(sample_worktree, None)

            assert panel._worktree_name == ""
            assert panel._status is None
