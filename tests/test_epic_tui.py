"""TUI tests for epics: the grouped task list, the E picker and the Info panel."""

import json
import os

import pytest

from tasktree_manager.services.models import Task, Worktree, group_by_epic
from tasktree_manager.widgets.create_modal import (
    CreateTaskModal,
    EpicPickerModal,
    NewEpicModal,
)
from tasktree_manager.widgets.status_panel import StatusPanel
from tasktree_manager.widgets.task_list import SortMode, TaskList


def rows(task_list: TaskList) -> list[str]:
    """The plain text of every visible row."""
    return [task_list.get_option_at_index(i).prompt.plain for i in range(task_list.option_count)]


def names(task_list: TaskList) -> list[str]:
    return [task.name for task in task_list.tasks]


@pytest.fixture
def epic_tasks(task_manager):
    """Epic E-1 with children T-2 and T-1, plus plain tasks A-0 and Z-9."""
    task_manager.create_task("E-1", [], kind="epic")
    task_manager.create_task("T-2", [], epic="E-1")
    task_manager.create_task("T-1", [], epic="E-1")
    task_manager.create_task("A-0", [])
    task_manager.create_task("Z-9", [])
    return task_manager


async def select(pilot, task_list: TaskList, name: str) -> None:
    task_list.highlighted = names(task_list).index(name)
    await pilot.pause()


class TestGroupByEpic:
    def test_orphan_and_case_variant(self, config, task_manager):
        task_manager.create_task("E-1", [], kind="epic")
        child = task_manager.create_task("T-1", [], epic="E-1")
        (child.path / ".tasktree_epic").write_text("e-1\n")
        orphan = task_manager.create_task("T-2", [])
        (orphan.path / ".tasktree_epic").write_text("GONE\n")
        top, children = group_by_epic(task_manager.list_tasks())
        # Same rule as the delete guard: a case variant counts only if it opens E-1
        variant_is_child = task_manager.epic_child_names("E-1") == ["T-1"]
        assert variant_is_child == (config.tasks_dir / "e-1").exists()
        if variant_is_child:
            assert [t.name for t in top] == ["E-1", "T-2"]
            assert [t.name for t in children["E-1"]] == ["T-1"]
        else:
            assert [t.name for t in top] == ["E-1", "T-1", "T-2"]


class TestTaskListTree:
    async def test_no_epics_rows_unchanged(self, app, task_manager):
        task_manager.create_task("T-1", [])
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            # The pre-epic format: dirty slot, CLAUDE.md slot, label
            assert rows(task_list) == ["   T-1"]
            assert task_list.check_action("toggle_epic", ()) is False

    async def test_grouped_order(self, app, epic_tasks):
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            assert names(task_list) == ["A-0", "E-1", "T-1", "T-2", "Z-9"]
            assert rows(task_list) == [
                "     A-0",
                "▾    E-1 · 2",
                "├    T-1",
                "└    T-2",
                "     Z-9",
            ]
            task_list.cycle_sort_mode()  # NAME_DESC applies at both levels
            await pilot.pause()
            assert names(task_list) == ["Z-9", "E-1", "T-2", "T-1", "A-0"]

    async def test_fold_keeps_selection(self, app, epic_tasks):
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            task_list.focus()
            await select(pilot, task_list, "E-1")
            await pilot.press("enter")
            await pilot.pause()
            assert names(task_list) == ["A-0", "E-1", "Z-9"]
            assert rows(task_list)[1].startswith("▸")
            assert app.current_task.name == "E-1"
            await pilot.press("space")
            await pilot.pause()
            assert names(task_list) == ["A-0", "E-1", "T-1", "T-2", "Z-9"]
            assert app.current_task.name == "E-1"

    async def test_fold_from_child_moves_to_epic(self, app, epic_tasks):
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            task_list.focus()
            await select(pilot, task_list, "T-2")
            await pilot.press("enter")
            await pilot.pause()
            assert names(task_list) == ["A-0", "E-1", "Z-9"]
            assert app.current_task.name == "E-1"

    async def test_sort_after_fold_keeps_hidden_children(self, app, epic_tasks):
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            task_list.focus()
            await select(pilot, task_list, "E-1")
            await pilot.press("enter")
            await pilot.pause()
            task_list.cycle_sort_mode()
            await pilot.pause()
            assert len(task_list.all_tasks) == 5
            await select(pilot, task_list, "E-1")
            await pilot.press("enter")
            await pilot.pause()
            assert {"T-1", "T-2"} <= set(names(task_list))

    async def test_selecting_hidden_child_unfolds(self, app, epic_tasks):
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            task_list.focus()
            await select(pilot, task_list, "E-1")
            await pilot.press("enter")
            await pilot.pause()
            app._load_tasks(select_task="T-2")
            await pilot.pause()
            await pilot.pause()
            assert "T-2" in names(task_list)
            assert task_list.get_selected_task().name == "T-2"

    async def test_date_sort_uses_newest_member(self, app, epic_tasks, config):
        now = 2_000_000_000
        for name, age in (("A-0", 50), ("E-1", 100), ("T-1", 1), ("T-2", 100), ("Z-9", 10)):
            os.utime(config.tasks_dir / name, (now - age, now - age))
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            task_list._sort_mode = SortMode.DATE_NEWEST
            task_list.load_tasks(task_list.all_tasks)
            await pilot.pause()
            # E-1 counts as touched when T-1 was: it leads, its children sorted inside
            assert names(task_list) == ["E-1", "T-1", "T-2", "Z-9", "A-0"]

    async def test_dirty_rollup(self, app, epic_tasks):
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            tasks = task_list.all_tasks
            child = next(t for t in tasks if t.name == "T-1")
            child.worktrees = [Worktree(name="r", path=child.path / "r", is_dirty=True)]
            task_list._sort_mode = SortMode.STATUS_DIRTY
            task_list.load_tasks(tasks)
            await pilot.pause()
            assert names(task_list)[:3] == ["E-1", "T-1", "T-2"]
            assert rows(task_list)[0] == "▾ ● E-1 · 2 (1)"

    async def test_claude_rollup_covers_folded_children(self, app, epic_tasks, config):
        (config.tasks_dir / "T-2" / ".claude_status").write_text(json.dumps({"status": "waiting"}))
        (config.tasks_dir / "E-1" / ".claude_status").write_text(json.dumps({"status": "running"}))
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            task_list.focus()
            await select(pilot, task_list, "E-1")
            await pilot.press("enter")
            await pilot.pause()
            app._poll_claude_statuses()
            await pilot.pause()
            # T-2 is folded away but still polled; waiting beats running
            assert app._claude_statuses.get("T-2") == "waiting"
            assert rows(task_list)[1].endswith(" !")

    async def test_marker_change_outside_tui_regroups(self, app, epic_tasks, task_manager):
        async with app.run_test() as pilot:
            await pilot.pause()
            await app.workers.wait_for_complete()
            task_list = app.query_one("#task-list", TaskList)
            task_manager.set_task_epic(task_manager.get_task("Z-9"), "E-1")
            app._run_periodic_refresh()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert names(task_list) == ["A-0", "E-1", "T-1", "T-2", "Z-9"]
            assert rows(task_list)[4].startswith("└")


class TestEpicPicker:
    async def test_e_on_task_opens_picker(self, app, epic_tasks):
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            await select(pilot, task_list, "A-0")
            await pilot.press("E")
            await pilot.pause()
            assert isinstance(app.screen, EpicPickerModal)
            assert app.screen.epics == [("E-1", "E-1")]
            assert app.screen.can_become_epic

    async def test_e_on_epic_is_refused(self, app, epic_tasks):
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            await select(pilot, task_list, "E-1")
            await pilot.press("E")
            await pilot.pause()
            assert not isinstance(app.screen, EpicPickerModal)

    async def test_picker_choice_attaches(self, app, epic_tasks, task_manager):
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            await select(pilot, task_list, "A-0")
            await pilot.press("E")
            await pilot.pause()
            app.screen.dismiss(("set", "E-1"))
            await pilot.pause()
            await pilot.pause()
            assert task_manager.get_task("A-0").epic_name == "E-1"
            assert names(task_list)[:4] == ["E-1", "A-0", "T-1", "T-2"]
            assert task_list.get_selected_task().name == "A-0"

    async def test_detach_new_and_mark(self, app, epic_tasks, task_manager):
        async with app.run_test() as pilot:
            await pilot.pause()
            child = task_manager.get_task("T-1")
            app._apply_epic_choice(child, "none", None)
            assert child.epic_name is None
            app._apply_epic_choice(child, "new", "E-2")
            assert task_manager.get_task("E-2").is_epic
            assert child.epic_name == "E-2"
            plain = task_manager.get_task("Z-9")
            app._apply_epic_choice(plain, "mark", None)
            assert plain.is_epic

    async def test_new_epic_name_taken(self, app, epic_tasks, task_manager):
        async with app.run_test() as pilot:
            await pilot.pause()
            plain = task_manager.get_task("Z-9")
            app._apply_epic_choice(plain, "new", "A-0")
            assert not task_manager.get_task("A-0").is_epic
            assert plain.epic_name is None


class TestCreateWithEpic:
    async def test_new_task_preselects_epic_of_child(self, app, epic_tasks, sample_repos):
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            await select(pilot, task_list, "T-1")
            await pilot.press("n")
            await pilot.pause()
            modal = app.screen
            assert isinstance(modal, CreateTaskModal)
            assert modal.initial_epic == "E-1"
            assert modal.epics == [("E-1", "E-1")]

    async def test_modal_dismisses_with_epic(self, app, epic_tasks, sample_repos):
        dismissed = []
        async with app.run_test() as pilot:
            await pilot.pause()
            modal = CreateTaskModal(["repo-alpha"], epics=[("E-1", "E-1")], initial_epic="E-1")
            await app.push_screen(modal, dismissed.append)
            await pilot.pause()
            modal.query_one("#task-name").value = "T-3"
            modal.selected_repos = {"repo-alpha"}
            modal._create_task()
            await pilot.pause()
            assert dismissed == [("T-3", ["repo-alpha"], "main", "E-1")]

    async def test_modal_without_epics_has_no_selector(self, app, sample_repos):
        dismissed = []
        async with app.run_test() as pilot:
            await pilot.pause()
            modal = CreateTaskModal(["repo-alpha"])
            await app.push_screen(modal, dismissed.append)
            await pilot.pause()
            assert not modal.query("#epic-select")
            modal.query_one("#task-name").value = "T-3"
            modal.selected_repos = {"repo-alpha"}
            modal._create_task()
            await pilot.pause()
            assert dismissed == [("T-3", ["repo-alpha"], "main", None)]


class TestInfoPanel:
    async def test_epic_block_and_child_line(self, app, tmp_path):
        task = Task(name="E-1", path=tmp_path / "E-1")
        async with app.run_test() as pilot:
            await pilot.pause()
            panel = app.query_one("#status-display", StatusPanel)
            panel.update_task_summary(
                task, epic_children=[("T-1", True, "waiting"), ("T-2", False, None)]
            )
            text = str(panel.content)
            assert "Epic · 2 task(s)" in text
            assert "● T-1 !" in text
            assert "✓ T-2" in text
            assert "no worktrees" in text
            panel.update_task_summary(task, epic_label="Big Epic")
            text = str(panel.content)
            assert "Epic: Big Epic" in text
            assert "Epic ·" not in text

    async def test_epic_context_from_app(self, app, epic_tasks):
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            epic = next(t for t in task_list.all_tasks if t.name == "E-1")
            child = next(t for t in task_list.all_tasks if t.name == "T-1")
            children, parent = app._epic_context(epic, task_list)
            assert [label for label, _, _ in children] == ["T-1", "T-2"]
            assert parent is None
            assert app._epic_context(child, task_list) == (None, "E-1")


class TestEmptyTaskActions:
    @pytest.mark.parametrize("key", ["p", "P"])
    async def test_push_pull_on_empty_task(self, app, task_manager, key, monkeypatch):
        task_manager.create_task("E-1", [], kind="epic")
        started = []
        monkeypatch.setattr(app, "_push_all_worker", started.append)
        monkeypatch.setattr(app, "_pull_all_worker", started.append)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press(key)
            await pilot.pause()
            assert started == []


class TestInfoPanelLive:
    async def test_epic_block_follows_claude_poll(self, app, epic_tasks, config):
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            task_list.focus()
            await select(pilot, task_list, "E-1")
            await app.workers.wait_for_complete()
            await pilot.pause()
            panel = app.query_one("#status-display", StatusPanel)
            assert "Epic · 2 task(s)" in str(panel.content)
            (config.tasks_dir / "T-1" / ".claude_status").write_text(
                json.dumps({"status": "waiting"})
            )
            app._poll_claude_statuses()
            await pilot.pause()
            assert "T-1 !" in str(panel.content)


class TestModalFits:
    async def test_create_modal_scrolls_on_short_terminal(self, app, sample_repos):
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            modal = CreateTaskModal(["repo-alpha"], epics=[("E-1", "E-1")])
            await app.push_screen(modal)
            await pilot.pause()
            container = modal.query_one("Container")
            button = modal.query_one("#create-btn")
            container.scroll_to_widget(button, animate=False)
            await pilot.pause()
            assert button.region.bottom <= app.size.height


class TestReviewFixesTui:
    @pytest.mark.parametrize("key", ["enter", "space"])
    async def test_configured_fold_key_stays_the_users(self, app, epic_tasks, key):
        app.config.keybindings["cycle_sort"] = key
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            task_list.focus()
            await select(pilot, task_list, "E-1")
            await pilot.press(key)
            await pilot.pause()
            assert task_list._sort_mode is SortMode.NAME_DESC
            assert "T-1" in names(task_list)

    async def test_picker_keyboard_attach(self, app, epic_tasks, task_manager):
        async with app.run_test() as pilot:
            await pilot.pause()
            await select(pilot, app.query_one("#task-list", TaskList), "A-0")
            await pilot.press("E")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert task_manager.get_task("A-0").epic_name == "E-1"

    async def test_picker_new_epic_flow(self, app, epic_tasks, task_manager):
        async with app.run_test() as pilot:
            await pilot.pause()
            await select(pilot, app.query_one("#task-list", TaskList), "A-0")
            await pilot.press("E")
            await pilot.pause()
            await pilot.press("down", "down", "enter")
            await pilot.pause()
            assert isinstance(app.screen, NewEpicModal)
            await pilot.press(".", "x", "enter")
            await pilot.pause()
            assert isinstance(app.screen, NewEpicModal)  # invalid name refused
            app.screen.query_one("#epic-name").value = "E-2"
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert task_manager.get_task("E-2").is_epic
            assert task_manager.get_task("A-0").epic_name == "E-2"

    async def test_new_epic_attach_failure_keeps_epic_visible(
        self, app, epic_tasks, task_manager, monkeypatch
    ):
        def refuse(task, epic):
            raise ValueError("nope")

        async with app.run_test() as pilot:
            await pilot.pause()
            monkeypatch.setattr(app.task_manager, "set_task_epic", refuse)
            app._apply_epic_choice(task_manager.get_task("Z-9"), "new", "E-NEW")
            await pilot.pause()
            await pilot.pause()
            assert "E-NEW" in names(app.query_one("#task-list", TaskList))

    async def test_picker_blocked_during_mutation(self, app, epic_tasks, task_manager, monkeypatch):
        async with app.run_test() as pilot:
            await pilot.pause()
            monkeypatch.setattr(app, "_mutation_in_flight", lambda: True)
            plain = task_manager.get_task("Z-9")
            app._apply_epic_choice(plain, "mark", None)
            assert not plain.is_epic

    async def test_picker_does_not_render_alias_markup(self, app, epic_tasks, task_manager):
        task_manager.set_task_display_name(
            task_manager.get_task("A-0"), "[$accent @click=app.bell()]X"
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            await select(pilot, app.query_one("#task-list", TaskList), "A-0")
            await pilot.press("E")
            await pilot.pause()
            message = app.screen.query_one(".modal-message")
            assert "[$accent @click=app.bell()]X" in str(message.render())

    async def test_non_string_claude_status_ignored(self, app, epic_tasks, config):
        (config.tasks_dir / "T-1" / ".claude_status").write_text(json.dumps({"status": []}))
        async with app.run_test() as pilot:
            await pilot.pause()
            app._poll_claude_statuses()
            assert "T-1" not in app._claude_statuses

    async def test_task_diff_on_empty_task(self, app, epic_tasks, monkeypatch):
        started = []
        monkeypatch.setattr(app, "_build_task_diff_worker", started.append)
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            task_list.focus()
            await select(pilot, task_list, "E-1")
            await pilot.press("h")
            await pilot.pause()
            assert started == []


class TestCumulativeReviewTui:
    async def test_comma_separated_binding_keeps_space(self, app, epic_tasks):
        app.config.keybindings["cycle_sort"] = "s,space"
        async with app.run_test() as pilot:
            await pilot.pause()
            task_list = app.query_one("#task-list", TaskList)
            task_list.focus()
            await select(pilot, task_list, "E-1")
            await pilot.press("space")
            await pilot.pause()
            assert task_list._sort_mode is SortMode.NAME_DESC

    @pytest.mark.parametrize(("row", "expected"), [("E-1", None), ("T-1", "E-1")])
    async def test_clone_preselects_source_parent(
        self, app, epic_tasks, sample_repos, row, expected
    ):
        async with app.run_test() as pilot:
            await pilot.pause()
            await select(pilot, app.query_one("#task-list", TaskList), row)
            await pilot.press("y")
            await pilot.pause()
            assert isinstance(app.screen, CreateTaskModal)
            assert app.screen.initial_epic == expected
