"""Tests for the main tasktree application."""

from tasktree.widgets.status_panel import StatusPanel
from tasktree.widgets.task_list import TaskList
from tasktree.widgets.worktree_list import WorktreeList


class TestTaskTreeApp:
    """Tests for TaskTreeApp class."""

    async def test_app_starts(self, app):
        """Test that the app starts without errors."""
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.is_running

    async def test_app_has_task_list(self, app):
        """Test that app has a task list widget."""
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            assert task_list is not None

    async def test_app_has_worktree_list(self, app):
        """Test that app has a worktree list widget."""
        async with app.run_test() as pilot:
            await pilot.pause()
            worktree_list = app.query_one("#worktree-list", WorktreeList)
            assert worktree_list is not None

    async def test_app_has_status_panel(self, app):
        """Test that app has a status panel widget."""
        async with app.run_test() as pilot:
            await pilot.pause()
            status_panel = app.query_one("#status-display", StatusPanel)
            assert status_panel is not None

    async def test_quit_action(self, app):
        """Test that q quits the app."""
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("q")
            assert not app.is_running

    async def test_help_modal(self, app):
        """Test that ? opens help modal."""
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("?")
            await pilot.pause()
            # Check that help modal is shown
            from tasktree.widgets.create_modal import HelpModal

            help_screens = [s for s in app.screen_stack if isinstance(s, HelpModal)]
            assert len(help_screens) == 1

    async def test_help_modal_shows_keybindings(self, app):
        """Test that help modal displays keybindings from config."""
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("?")
            await pilot.pause()

            from tasktree.widgets.create_modal import HelpModal

            help_screens = [s for s in app.screen_stack if isinstance(s, HelpModal)]
            assert len(help_screens) == 1

            help_modal = help_screens[0]
            # Verify keybindings were passed
            assert help_modal.keybindings is not None
            assert "quit" in help_modal.keybindings
            assert "new_task" in help_modal.keybindings

    async def test_navigation_j_k(self, app, sample_repos, task_manager):
        """Test j/k navigation in task list."""
        repos, branch = sample_repos
        # Create some tasks
        task_manager.create_task("TASK-1", ["repo-alpha"], branch)
        task_manager.create_task("TASK-2", ["repo-beta"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Check initial task
            task_list = app.query_one("#task-list", TaskList)
            assert task_list.index == 0

            # Navigate down
            await pilot.press("j")
            await pilot.pause()
            assert task_list.index == 1

            # Navigate up
            await pilot.press("k")
            await pilot.pause()
            assert task_list.index == 0

    async def test_tab_switches_focus(self, app):
        """Test that tab switches focus between panels."""
        async with app.run_test() as pilot:
            await pilot.pause()

            # Initial focus should be on task list
            task_list = app.query_one("#task-list", TaskList)
            assert app.focused == task_list

            # Tab to worktree list
            await pilot.press("tab")
            await pilot.pause()

            worktree_list = app.query_one("#worktree-list", WorktreeList)
            assert app.focused == worktree_list

    async def test_refresh_action(self, app):
        """Test that r refreshes the app."""
        async with app.run_test() as pilot:
            await pilot.pause()
            # Just verify it doesn't crash
            await pilot.press("r")
            await pilot.pause()
            assert app.is_running


class TestTaskListWidget:
    """Tests for TaskList widget."""

    async def test_empty_task_list(self, app):
        """Test task list with no tasks."""
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            assert len(task_list.tasks) == 0

    async def test_task_list_loads_tasks(self, app, sample_repo, task_manager):
        """Test that task list loads created tasks."""
        repo_path, branch = sample_repo
        task_manager.create_task("LOADED-TASK", ["sample-repo"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            assert len(task_list.tasks) == 1
            assert task_list.tasks[0].name == "LOADED-TASK"


class TestWorktreeListWidget:
    """Tests for WorktreeList widget."""

    async def test_worktree_list_updates_on_task_select(self, app, sample_repos, task_manager):
        """Test worktree list updates when task is selected."""
        repos, branch = sample_repos
        task_manager.create_task("WT-TEST", ["repo-alpha", "repo-beta"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()

            worktree_list = app.query_one("#worktree-list", WorktreeList)
            assert len(worktree_list.worktrees) == 2
