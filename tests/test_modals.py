"""Tests for modal widgets."""

import pytest
from textual.widgets import Button, Input, SelectionList

from tasktree_manager.services.task_manager import RepoIssue, TaskSafetyReport
from tasktree_manager.widgets.create_modal import (
    AddRepoModal,
    ConfirmModal,
    CreateTaskModal,
    HelpModal,
    PushResultModal,
    SafeDeleteModal,
)


def _visible_values(repo_list: SelectionList) -> list[str]:
    """Return the values currently rendered in a SelectionList, in order."""
    return [repo_list.get_option_at_index(i).value for i in range(repo_list.option_count)]


class TestCreateTaskModal:
    """Tests for CreateTaskModal."""

    async def test_modal_compose(self, app, sample_repos):
        """Test that modal composes all expected widgets."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = CreateTaskModal(available_repos=["repo-a", "repo-b", "repo-c"])
            app.push_screen(modal)
            await pilot.pause()

            # Check for expected widgets
            assert modal.query_one("#task-name", Input)
            assert modal.query_one("#base-branch", Input)
            assert modal.query_one("#repo-search", Input)
            assert modal.query_one("#repo-list", SelectionList)
            assert modal.query_one("#create-btn", Button)
            assert modal.query_one("#cancel-btn", Button)

    async def test_search_filter_repos(self, app, sample_repos):
        """Test that search input filters repository list."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = CreateTaskModal(available_repos=["alpha-repo", "beta-repo", "gamma-repo"])
            app.push_screen(modal)
            await pilot.pause()

            # Type in search to filter
            modal._filter_repos("alpha")
            await pilot.pause()

            # Check filtered list
            repo_list = modal.query_one("#repo-list", SelectionList)
            assert repo_list.option_count == 1

    async def test_search_matches_folder_prefix(self, app, sample_repos):
        """Typing a folder name shows every repo under that folder."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = CreateTaskModal(
                available_repos=[
                    "mdp/docs",
                    "mdp/gitops",
                    "mdp/terraform",
                    "ansible/devops_ansible",
                    "data-engineering/market-data-catalog",
                ]
            )
            app.push_screen(modal)
            await pilot.pause()

            # 'mdp' is a folder; all repos under it match, and nothing else does.
            modal._filter_repos("mdp")
            await pilot.pause()

            repo_list = modal.query_one("#repo-list", SelectionList)
            assert _visible_values(repo_list) == ["mdp/docs", "mdp/gitops", "mdp/terraform"]

    async def test_search_via_input_event_filters(self, app, sample_repos):
        """Typing in the search Input drives filtering through the mixin handler."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = CreateTaskModal(available_repos=["mdp/terraform", "ansible-ci", "airflow"])
            app.push_screen(modal)
            await pilot.pause()

            # Set the Input value, which posts Input.Changed -> on_input_changed.
            search = modal.query_one("#repo-search", Input)
            search.value = "mdp"
            await pilot.pause()

            repo_list = modal.query_one("#repo-list", SelectionList)
            assert _visible_values(repo_list) == ["mdp/terraform"]

    async def test_search_preserves_selections(self, app, sample_repos):
        """Test that search preserves previously selected repos."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = CreateTaskModal(available_repos=["alpha-repo", "beta-repo", "gamma-repo"])
            app.push_screen(modal)
            await pilot.pause()

            # Select a repo
            repo_list = modal.query_one("#repo-list", SelectionList)
            repo_list.select("alpha-repo")
            modal.selected_repos.add("alpha-repo")
            await pilot.pause()

            # Filter to different repos
            modal._filter_repos("beta")
            await pilot.pause()

            # Clear filter
            modal._filter_repos("")
            await pilot.pause()

            # alpha-repo should still be in selected_repos
            assert "alpha-repo" in modal.selected_repos

    async def test_select_then_search_then_select_keeps_both(self, app, sample_repos):
        """Selecting a repo, searching, then selecting another keeps both.

        Drives the real SelectionList.SelectedChanged handler (not a manual
        selected_repos mutation) to guard against the filter resetting prior
        selections.
        """
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = CreateTaskModal(available_repos=["ansible", "terraform", "postgres"])
            app.push_screen(modal)
            await pilot.pause()

            repo_list = modal.query_one("#repo-list", SelectionList)

            # Select ansible from the unfiltered list.
            repo_list.select("ansible")
            await pilot.pause()
            assert modal.selected_repos == {"ansible"}

            # Search for terraform, then select it while the list is filtered.
            modal._filter_repos("terraform")
            await pilot.pause()
            repo_list.select("terraform")
            await pilot.pause()

            # Clear the search and confirm both survive.
            modal._filter_repos("")
            await pilot.pause()
            assert modal.selected_repos == {"ansible", "terraform"}

    async def test_deselect_under_filter_is_tracked(self, app, sample_repos):
        """Deselecting a visible repo under a filter removes only that repo."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = CreateTaskModal(
                available_repos=["ansible", "terraform", "postgres"],
                initial_repos=["ansible", "terraform"],
            )
            app.push_screen(modal)
            await pilot.pause()

            repo_list = modal.query_one("#repo-list", SelectionList)

            # Filter to terraform and deselect it.
            modal._filter_repos("terraform")
            await pilot.pause()
            repo_list.deselect("terraform")
            await pilot.pause()

            # ansible (outside the filter) is untouched; terraform is gone.
            modal._filter_repos("")
            await pilot.pause()
            assert modal.selected_repos == {"ansible"}

    async def test_create_task_validates_empty_name(self, app, sample_repos):
        """Test that creating task with empty name shows error."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = CreateTaskModal(available_repos=["repo-a"])
            app.push_screen(modal)
            await pilot.pause()

            # Select a repo but leave name empty
            repo_list = modal.query_one("#repo-list", SelectionList)
            repo_list.select("repo-a")
            modal.selected_repos.add("repo-a")
            await pilot.pause()

            # Try to create (name is empty)
            modal._create_task()
            await pilot.pause()

            # Modal should not have dismissed - it's still in the screen stack
            assert modal in app.screen_stack

    async def test_create_task_validates_no_repos(self, app, sample_repos):
        """Test that creating task with no repos selected shows error."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = CreateTaskModal(available_repos=["repo-a"])
            app.push_screen(modal)
            await pilot.pause()

            # Set name but don't select repos
            name_input = modal.query_one("#task-name", Input)
            name_input.value = "TEST-123"
            await pilot.pause()

            # Try to create
            modal._create_task()
            await pilot.pause()

            # Modal should not have dismissed
            assert modal in app.screen_stack

    async def test_cancel_dismisses_modal(self, app, sample_repos):
        """Test that cancel button dismisses modal."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = CreateTaskModal(available_repos=["repo-a"])
            app.push_screen(modal)
            await pilot.pause()

            # Dismiss via escape key or direct call
            modal.dismiss(None)
            await pilot.pause()

            # Modal should be dismissed
            assert modal not in app.screen_stack


class TestAddRepoModal:
    """Tests for AddRepoModal."""

    async def test_modal_compose(self, app, sample_repos):
        """Test that modal composes expected widgets."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = AddRepoModal(task_name="TEST-TASK", available_repos=["repo-x", "repo-y"])
            app.push_screen(modal)
            await pilot.pause()

            # Check for widgets
            assert modal.query_one("#base-branch", Input)
            assert modal.query_one("#repo-search", Input)
            assert modal.query_one("#repo-list", SelectionList)
            assert modal.query_one("#add-btn", Button)
            assert modal.query_one("#cancel-btn", Button)

    async def test_add_repos_validates_no_selection(self, app, sample_repos):
        """Test that adding with no selection shows error."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = AddRepoModal(task_name="TEST", available_repos=["repo-x"])
            app.push_screen(modal)
            await pilot.pause()

            # Try to add without selecting
            modal._add_repos()
            await pilot.pause()

            # Modal should not have dismissed
            assert modal in app.screen_stack

    async def test_empty_repos_shows_message(self, app, sample_repos):
        """Test that modal with no available repos shows message."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = AddRepoModal(task_name="TEST", available_repos=[])
            app.push_screen(modal)
            await pilot.pause()

            # Modal should compose without error
            assert modal in app.screen_stack

    async def test_search_filters_repos(self, app, sample_repos):
        """Test search filtering in AddRepoModal."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = AddRepoModal(task_name="TEST", available_repos=["alpha", "beta", "gamma"])
            app.push_screen(modal)
            await pilot.pause()

            modal._filter_repos("beta")
            await pilot.pause()

            repo_list = modal.query_one("#repo-list", SelectionList)
            assert repo_list.option_count == 1


class TestConfirmModal:
    """Tests for ConfirmModal."""

    async def test_modal_compose(self, app, sample_repos):
        """Test that modal displays title and message."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = ConfirmModal(title="Delete Item", message="Are you sure?")
            app.push_screen(modal)
            await pilot.pause()

            # Check for confirm and cancel buttons
            assert modal.query_one("#confirm-btn", Button)
            assert modal.query_one("#cancel-btn", Button)

    async def test_confirm_button_dismisses(self, app, sample_repos):
        """Test that confirm button dismisses modal."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = ConfirmModal(title="Confirm", message="Confirm action?")
            app.push_screen(modal)
            await pilot.pause()

            confirm_btn = modal.query_one("#confirm-btn", Button)
            await pilot.click(confirm_btn)
            await pilot.pause()

            assert modal not in app.screen_stack

    async def test_cancel_button_dismisses(self, app, sample_repos):
        """Test that cancel button dismisses modal."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = ConfirmModal(title="Confirm", message="Confirm action?")
            app.push_screen(modal)
            await pilot.pause()

            cancel_btn = modal.query_one("#cancel-btn", Button)
            await pilot.click(cancel_btn)
            await pilot.pause()

            assert modal not in app.screen_stack


class TestSafeDeleteModal:
    """Tests for SafeDeleteModal."""

    @pytest.fixture
    def safety_report_with_issues(self, tmp_path):
        """Create a TaskSafetyReport with various issues."""
        return TaskSafetyReport(
            unpushed=[
                RepoIssue(
                    repo_name="repo-a",
                    worktree_path=tmp_path / "repo-a",
                    issue_type="unpushed",
                    details="3 commits ahead",
                )
            ],
            dirty=[
                RepoIssue(
                    repo_name="repo-b",
                    worktree_path=tmp_path / "repo-b",
                    issue_type="dirty",
                    details="2 files changed",
                )
            ],
            unmerged=[
                RepoIssue(
                    repo_name="repo-c",
                    worktree_path=tmp_path / "repo-c",
                    issue_type="unmerged",
                    details="not merged to main",
                )
            ],
        )

    async def test_displays_warnings(self, app, sample_repos, safety_report_with_issues):
        """Test that modal displays warnings."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = SafeDeleteModal(task_name="TEST", safety_report=safety_report_with_issues)
            app.push_screen(modal)
            await pilot.pause()

            # Modal should compose without error
            assert modal in app.screen_stack

    async def test_push_button_dismisses(self, app, sample_repos):
        """Test that Push All button dismisses modal."""
        async with app.run_test() as pilot:
            await pilot.pause()

            report = TaskSafetyReport(unpushed=[], dirty=[], unmerged=[])
            modal = SafeDeleteModal(task_name="TEST", safety_report=report)
            app.push_screen(modal)
            await pilot.pause()

            push_btn = modal.query_one("#push-btn", Button)
            await pilot.click(push_btn)
            await pilot.pause()

            assert modal not in app.screen_stack

    async def test_force_button_dismisses(self, app, sample_repos):
        """Test that Force Delete button dismisses modal."""
        async with app.run_test() as pilot:
            await pilot.pause()

            report = TaskSafetyReport(unpushed=[], dirty=[], unmerged=[])
            modal = SafeDeleteModal(task_name="TEST", safety_report=report)
            app.push_screen(modal)
            await pilot.pause()

            force_btn = modal.query_one("#force-btn", Button)
            await pilot.click(force_btn)
            await pilot.pause()

            assert modal not in app.screen_stack

    async def test_cancel_dismisses(self, app, sample_repos):
        """Test that Cancel button dismisses modal."""
        async with app.run_test() as pilot:
            await pilot.pause()

            report = TaskSafetyReport(unpushed=[], dirty=[], unmerged=[])
            modal = SafeDeleteModal(task_name="TEST", safety_report=report)
            app.push_screen(modal)
            await pilot.pause()

            cancel_btn = modal.query_one("#cancel-btn", Button)
            await pilot.click(cancel_btn)
            await pilot.pause()

            assert modal not in app.screen_stack


class TestPushResultModal:
    """Tests for PushResultModal."""

    async def test_displays_success_repos(self, app, sample_repos):
        """Test that modal displays successfully pushed repos."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = PushResultModal(success_repos=["repo-a", "repo-b"], failed_repos=[])
            app.push_screen(modal)
            await pilot.pause()

            assert modal.query_one("#close-btn", Button)
            assert modal in app.screen_stack

    async def test_displays_failed_repos(self, app, sample_repos):
        """Test that modal displays failed repos."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = PushResultModal(success_repos=[], failed_repos=["repo-c", "repo-d"])
            app.push_screen(modal)
            await pilot.pause()

            assert modal in app.screen_stack

    async def test_close_button_dismisses(self, app, sample_repos):
        """Test that close button dismisses the modal."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = PushResultModal(success_repos=["repo-a"], failed_repos=[])
            app.push_screen(modal)
            await pilot.pause()

            close_btn = modal.query_one("#close-btn", Button)
            await pilot.click(close_btn)
            await pilot.pause()

            assert modal not in app.screen_stack


class TestHelpModal:
    """Tests for HelpModal."""

    async def test_displays_keybindings(self, app, sample_repos):
        """Test that modal displays keybindings."""
        async with app.run_test() as pilot:
            await pilot.pause()

            keybindings = {
                "quit": "q",
                "help": "?",
                "new_task": "n",
            }
            modal = HelpModal(keybindings=keybindings, config_path="/path/to/config.toml")
            app.push_screen(modal)
            await pilot.pause()

            assert modal.query_one("#close-btn", Button)
            assert modal in app.screen_stack

    def test_format_binding_method(self):
        """Test the _format_binding helper method."""
        keybindings = {"quit": "ctrl+q", "help": "F1"}
        modal = HelpModal(keybindings=keybindings)

        result = modal._format_binding("quit", "q", "Quit application")
        assert "Ctrl+" in result
        assert "Quit application" in result

    def test_get_key_method(self):
        """Test the _get_key helper method."""
        keybindings = {"quit": "ctrl+shift+q"}
        modal = HelpModal(keybindings=keybindings)

        key = modal._get_key("quit", "q")
        assert "Ctrl+" in key
        assert "Shift+" in key

        key = modal._get_key("unknown", "x")
        assert key == "x"

    def test_build_info_text(self):
        """Test that _build_info_text works correctly."""
        modal = HelpModal(config_path="/custom/path/config.toml")
        info_text = modal._build_info_text()
        assert "/custom/path/config.toml" in info_text

    def test_default_config_path(self):
        """Test default config path when not specified."""
        modal = HelpModal(config_path="")
        info_text = modal._build_info_text()
        assert "~/.config/tasktree-manager/config.toml" in info_text

    async def test_close_button_dismisses(self, app, sample_repos):
        """Test that close button dismisses the modal."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = HelpModal()
            app.push_screen(modal)
            await pilot.pause()

            # Dismiss directly
            modal.dismiss()
            await pilot.pause()

            assert modal not in app.screen_stack

    def test_help_content_sections(self):
        """Test that help content includes all sections."""
        modal = HelpModal()
        content = modal._build_help_content()

        assert "Navigation" in content
        assert "Task Management" in content
        assert "Git Operations" in content
        assert "General" in content
        assert "Tips" in content


class TestEscapeDismissesModals:
    """Escape cancels modals with the same result as the Cancel button."""

    async def test_escape_dismisses_create_task_modal(self, app, sample_repos):
        """Escape closes CreateTaskModal with a None (cancelled) result."""
        async with app.run_test() as pilot:
            await pilot.pause()

            results = []
            modal = CreateTaskModal(available_repos=["repo-a"])
            app.push_screen(modal, results.append)
            await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()

            assert modal not in app.screen_stack
            assert results == [None]

    async def test_escape_dismisses_while_input_focused(self, app, sample_repos):
        """Escape works even when a text input inside the modal has focus."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = CreateTaskModal(available_repos=["repo-a"])
            app.push_screen(modal)
            await pilot.pause()

            modal.query_one("#task-name", Input).focus()
            await pilot.pause()
            await pilot.press("t", "escape")
            await pilot.pause()

            assert modal not in app.screen_stack

    async def test_escape_cancels_confirm_modal_with_false(self, app, sample_repos):
        """Escape on ConfirmModal dismisses with False, not None."""
        async with app.run_test() as pilot:
            await pilot.pause()

            results = []
            modal = ConfirmModal(title="Confirm", message="Confirm action?")
            app.push_screen(modal, results.append)
            await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()

            assert modal not in app.screen_stack
            assert results == [False]

