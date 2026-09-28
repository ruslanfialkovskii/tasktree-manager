"""Regression tests for selection-preserving reloads in TaskList/WorktreeList.

Covers two bugs: TaskList.cycle_sort_mode() used to snap back to the first
task and emit TaskHighlighted twice; WorktreeList.toggle_grouping() used to
snap back to the first worktree.
"""

from tasktree_manager.widgets.task_list import TaskList
from tasktree_manager.widgets.worktree_list import WorktreeList


class TestCycleSortModePreservesSelection:
    """Tests for TaskList.cycle_sort_mode()."""

    async def test_selection_follows_task_across_resort(self, app, task_manager, sample_repos):
        """The highlighted task stays highlighted even though its index moves."""
        _, branch = sample_repos
        task_manager.create_task("AAA-task", ["repo-alpha"], branch)
        task_manager.create_task("BBB-task", ["repo-beta"], branch)
        task_manager.create_task("ZZZ-task", ["repo-gamma"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)

            # Default sort mode is NAME_ASC
            assert [t.name for t in task_list.tasks] == ["AAA-task", "BBB-task", "ZZZ-task"]
            task_list.highlighted = 0
            await pilot.pause()
            assert task_list.get_selected_task().name == "AAA-task"

            # Cycle to NAME_DESC: AAA-task moves from index 0 to index 2
            task_list.cycle_sort_mode()
            await pilot.pause()
            await pilot.pause()

            assert [t.name for t in task_list.tasks] == ["ZZZ-task", "BBB-task", "AAA-task"]
            assert task_list.get_selected_task().name == "AAA-task"
            assert task_list.highlighted == 2

    async def test_emits_task_highlighted_exactly_once(
        self, app, task_manager, sample_repos, monkeypatch
    ):
        """cycle_sort_mode() must not double-post TaskHighlighted."""
        _, branch = sample_repos
        task_manager.create_task("AAA-task", ["repo-alpha"], branch)
        task_manager.create_task("BBB-task", ["repo-beta"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            assert task_list.get_selected_task().name == "AAA-task"

            received: list[str | None] = []
            original_post_message = task_list.post_message

            def spy(message):
                if isinstance(message, TaskList.TaskHighlighted):
                    received.append(message.task.name if message.task else None)
                return original_post_message(message)

            monkeypatch.setattr(task_list, "post_message", spy)

            task_list.cycle_sort_mode()
            await pilot.pause()
            await pilot.pause()

            assert received == ["AAA-task"]

    async def test_worktree_panel_follows_preserved_task(self, app, task_manager, sample_repos):
        """The right-hand worktree panel stays in sync with the preserved task.

        on_task_list_task_highlighted (app.py) reloads the worktree list from
        event.task on every TaskHighlighted - a stray extra emission for the
        wrong task would flash the wrong worktrees into that panel.
        """
        _, branch = sample_repos
        task_manager.create_task("AAA-task", ["repo-alpha"], branch)
        task_manager.create_task("BBB-task", ["repo-beta"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            worktree_list = app.query_one("#worktree-list", WorktreeList)
            assert task_list.get_selected_task().name == "AAA-task"

            task_list.cycle_sort_mode()
            await pilot.pause()
            await pilot.pause()

            assert app.current_task is not None
            assert app.current_task.name == "AAA-task"
            assert [wt.name for wt in worktree_list.worktrees] == ["repo-alpha"]


class TestToggleGroupingPreservesSelection:
    """Tests for WorktreeList.toggle_grouping()."""

    async def test_selection_survives_grouping_toggle(self, app, task_manager, sample_repos):
        """Toggling grouping must not snap the highlight back to the first row."""
        _, branch = sample_repos
        task = task_manager.create_task("GROUP-SEL", ["repo-alpha", "repo-beta"], branch)
        beta = task.worktrees[1]
        (beta.path / "dirty.txt").write_text("x\n")
        beta.is_dirty = True
        beta.changed_files = 1

        async with app.run_test() as pilot:
            await pilot.pause()
            worktree_list = app.query_one("#worktree-list", WorktreeList)
            worktree_list.load_worktrees(task.worktrees)
            await pilot.pause()

            # Flat mode: select repo-beta (index 1)
            worktree_list.highlighted = 1
            await pilot.pause()
            assert worktree_list.get_selected_worktree().name == "repo-beta"

            # Grouped mode buries repo-beta under a "Dirty" header row, so its
            # option index changes.
            worktree_list.toggle_grouping()
            await pilot.pause()
            await pilot.pause()
            assert worktree_list.get_selected_worktree().name == "repo-beta"

            # Toggling back to flat mode should also keep the selection.
            worktree_list.toggle_grouping()
            await pilot.pause()
            await pilot.pause()
            assert worktree_list.get_selected_worktree().name == "repo-beta"
