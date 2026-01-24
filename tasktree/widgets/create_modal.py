"""Modal widgets for creating tasks and adding repos."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, SelectionList, Static
from textual.widgets.selection_list import Selection


class ThemedModalScreen(ModalScreen):
    """Base class for themed modal screens."""

    DEFAULT_CSS = """
    ThemedModalScreen {
        align: center middle;
    }

    ThemedModalScreen > Container {
        width: 70;
        height: auto;
        max-height: 80%;
        border: round $primary;
        background: $surface;
        padding: 1 2;
    }

    ThemedModalScreen .modal-title {
        text-align: center;
        text-style: bold;
        color: $text;
        margin-bottom: 1;
    }

    ThemedModalScreen .section-label {
        color: $foreground-muted;
        margin-top: 1;
        margin-bottom: 0;
    }

    ThemedModalScreen Input {
        background: $background;
        border: round $primary;
        color: $text;
        margin-bottom: 1;
    }

    ThemedModalScreen Input:focus {
        border: round $accent;
    }

    ThemedModalScreen SelectionList {
        height: 12;
        margin-bottom: 1;
        background: $background;
        border: round $primary;
    }

    ThemedModalScreen .button-row {
        align: center middle;
        margin-top: 1;
    }

    ThemedModalScreen Button {
        margin: 0 1;
        min-width: 12;
    }

    ThemedModalScreen .help-text {
        color: $text;
        margin-bottom: 1;
    }

    ThemedModalScreen .modal-message {
        text-align: center;
        color: $text;
        margin-bottom: 1;
    }
    """


class CreateTaskModal(ThemedModalScreen):
    """Modal for creating a new task."""

    class TaskCreated(Message):
        """Message sent when a task is created."""

        def __init__(self, name: str, repos: list[str], base_branch: str):
            self.name = name
            self.repos = repos
            self.base_branch = base_branch
            super().__init__()

    def __init__(self, available_repos: list[str], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.available_repos = available_repos
        self.selected_repos: set[str] = set()

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("Create New Task", classes="modal-title")
            yield Label("Task Name:", classes="section-label")
            yield Input(placeholder="e.g., FEAT-123-new-feature", id="task-name")
            yield Label("Base Branch:", classes="section-label")
            yield Input(value="master", placeholder="master", id="base-branch")
            yield Label("Search Repositories:", classes="section-label")
            yield Input(placeholder="Type to filter (e.g., ansible, postgres)...", id="repo-search")
            yield Label("Select Repositories:", classes="section-label")
            yield SelectionList[str](
                *[Selection(repo, repo) for repo in self.available_repos],
                id="repo-list",
            )
            with Horizontal(classes="button-row"):
                yield Button("Create", variant="primary", id="create-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "repo-search":
            self._filter_repos(event.value)

    def _filter_repos(self, search_term: str) -> None:
        """Filter repository list based on search term."""
        repo_list = self.query_one("#repo-list", SelectionList)

        # Save current selections
        self.selected_repos.update(repo_list.selected)

        # Filter repos (case-insensitive substring match)
        search_lower = search_term.lower()
        if search_lower:
            filtered = [repo for repo in self.available_repos if search_lower in repo.lower()]
        else:
            filtered = self.available_repos

        # Clear and rebuild the list
        repo_list.clear_options()
        for repo in filtered:
            # Restore selection state
            repo_list.add_option(Selection(repo, repo, initial_state=repo in self.selected_repos))

    def on_selection_list_selected_changed(self, event: SelectionList.SelectedChanged) -> None:
        """Track selections across filter changes."""
        if event.selection_list.id == "repo-list":
            self.selected_repos = set(event.selection_list.selected)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id == "create-btn":
            self._create_task()

    def _create_task(self) -> None:
        """Create the task and dismiss modal."""
        name_input = self.query_one("#task-name", Input)
        branch_input = self.query_one("#base-branch", Input)

        name = name_input.value.strip()
        base_branch = branch_input.value.strip() or "master"
        selected_repos = list(self.selected_repos)

        if not name:
            self.notify("Task name is required", severity="error")
            return

        if not selected_repos:
            self.notify("Select at least one repository", severity="error")
            return

        self.dismiss((name, selected_repos, base_branch))


class AddRepoModal(ThemedModalScreen):
    """Modal for adding repos to an existing task."""

    def __init__(self, task_name: str, available_repos: list[str], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.task_name = task_name
        self.available_repos = available_repos
        self.selected_repos: set[str] = set()

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(f"Add Repos to: {self.task_name}", classes="modal-title")
            yield Label("Base Branch:", classes="section-label")
            yield Input(value="master", placeholder="master", id="base-branch")
            if self.available_repos:
                yield Label("Search Repositories:", classes="section-label")
                yield Input(placeholder="Type to filter (e.g., ansible, postgres)...", id="repo-search")
                yield Label("Select Repositories to Add:", classes="section-label")
                yield SelectionList[str](
                    *[Selection(repo, repo) for repo in self.available_repos],
                    id="repo-list",
                )
            else:
                yield Static("No more repositories available to add")
            with Horizontal(classes="button-row"):
                yield Button("Add", variant="primary", id="add-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "repo-search":
            self._filter_repos(event.value)

    def _filter_repos(self, search_term: str) -> None:
        """Filter repository list based on search term."""
        repo_list = self.query_one("#repo-list", SelectionList)

        # Save current selections
        self.selected_repos.update(repo_list.selected)

        # Filter repos (case-insensitive substring match)
        search_lower = search_term.lower()
        if search_lower:
            filtered = [repo for repo in self.available_repos if search_lower in repo.lower()]
        else:
            filtered = self.available_repos

        # Clear and rebuild the list
        repo_list.clear_options()
        for repo in filtered:
            # Restore selection state
            repo_list.add_option(Selection(repo, repo, initial_state=repo in self.selected_repos))

    def on_selection_list_selected_changed(self, event: SelectionList.SelectedChanged) -> None:
        """Track selections across filter changes."""
        if event.selection_list.id == "repo-list":
            self.selected_repos = set(event.selection_list.selected)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id == "add-btn":
            self._add_repos()

    def _add_repos(self) -> None:
        """Add repos and dismiss modal."""
        if not self.available_repos:
            self.dismiss(None)
            return

        branch_input = self.query_one("#base-branch", Input)

        base_branch = branch_input.value.strip() or "master"
        selected_repos = list(self.selected_repos)

        if not selected_repos:
            self.notify("Select at least one repository", severity="error")
            return

        self.dismiss((selected_repos, base_branch))


class ConfirmModal(ThemedModalScreen):
    """Modal for confirming an action."""

    DEFAULT_CSS = ThemedModalScreen.DEFAULT_CSS + """
    ConfirmModal > Container {
        width: 60;
        border: round $error;
    }

    ConfirmModal .modal-title {
        color: $text-error;
    }
    """

    def __init__(self, title: str, message: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title_text = title
        self.message_text = message

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(self.title_text, classes="modal-title")
            yield Static(self.message_text, classes="modal-message")
            with Horizontal(classes="button-row"):
                yield Button("Confirm", variant="error", id="confirm-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "cancel-btn":
            self.dismiss(False)
        elif event.button.id == "confirm-btn":
            self.dismiss(True)


class SafeDeleteModal(ThemedModalScreen):
    """Modal for safely deleting a task with safety warnings."""

    DEFAULT_CSS = ThemedModalScreen.DEFAULT_CSS + """
    SafeDeleteModal > Container {
        width: 70;
        height: auto;
        max-height: 90%;
        border: round $error;
    }

    SafeDeleteModal .modal-title {
        color: $text-error;
    }

    SafeDeleteModal .warning-section {
        margin-top: 1;
        margin-bottom: 1;
    }

    SafeDeleteModal .warning-header {
        color: $text-error;
        text-style: bold;
        margin-bottom: 0;
    }

    SafeDeleteModal .warning-item {
        color: $text;
        margin-left: 2;
    }

    SafeDeleteModal .scrollable-content {
        height: auto;
        max-height: 30;
        overflow-y: auto;
    }
    """

    def __init__(self, task_name: str, safety_report, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.task_name = task_name
        self.safety_report = safety_report

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(f"Delete Task: {self.task_name}", classes="modal-title")
            yield Static("WARNING: Issues detected", classes="modal-message")

            # Build warnings content
            warnings_content = ""

            if self.safety_report.has_unpushed():
                warnings_content += "\n[bold red]Unpushed commits:[/]\n"
                for issue in self.safety_report.unpushed:
                    warnings_content += f"  * {issue.repo_name} ({issue.details})\n"

            if self.safety_report.has_unmerged():
                warnings_content += "\n[bold red]Unmerged branches:[/]\n"
                for issue in self.safety_report.unmerged:
                    warnings_content += f"  * {issue.repo_name} ({issue.details})\n"

            if self.safety_report.has_dirty():
                warnings_content += "\n[bold red]Uncommitted changes:[/]\n"
                for issue in self.safety_report.dirty:
                    warnings_content += f"  * {issue.repo_name} ({issue.details})\n"

            yield Static(warnings_content.strip(), classes="scrollable-content")

            with Horizontal(classes="button-row"):
                yield Button("Push All", variant="primary", id="push-btn")
                yield Button("Open Lazygit", variant="default", id="lazygit-btn")
                yield Button("Force Delete", variant="error", id="force-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id == "push-btn":
            self.dismiss("push")
        elif event.button.id == "lazygit-btn":
            self.dismiss("lazygit")
        elif event.button.id == "force-btn":
            self.dismiss("force")


class PushResultModal(ThemedModalScreen):
    """Modal showing results of push operation."""

    DEFAULT_CSS = ThemedModalScreen.DEFAULT_CSS + """
    PushResultModal > Container {
        width: 60;
    }
    """

    def __init__(self, success_repos: list[str], failed_repos: list[str], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.success_repos = success_repos
        self.failed_repos = failed_repos

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("Push Results", classes="modal-title")

            result_text = ""
            if self.success_repos:
                result_text += "[bold green]Successfully pushed:[/]\n"
                for repo in self.success_repos:
                    result_text += f"  [green]✓[/] {repo}\n"

            if self.failed_repos:
                if result_text:
                    result_text += "\n"
                result_text += "[bold red]Failed to push:[/]\n"
                for repo in self.failed_repos:
                    result_text += f"  [red]✗[/] {repo}\n"

            yield Static(result_text.strip(), classes="modal-message")

            with Horizontal(classes="button-row"):
                yield Button("Close", variant="primary", id="close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        self.dismiss()


class HelpModal(ThemedModalScreen):
    """Modal showing keybindings help."""

    DEFAULT_CSS = ThemedModalScreen.DEFAULT_CSS + """
    HelpModal > Container {
        width: 60;
    }
    """

    HELP_TEXT = """
Navigation:
  j/down  Move down
  k/up    Move up
  Tab     Switch panels
  Enter   Open shell in worktree

Actions:
  n       New task
  a       Add repo to task
  d       Finish/delete task
  g       Open lazygit in worktree
  p       Push all worktrees
  P       Pull all worktrees
  r       Refresh status

General:
  Ctrl+P  Command palette (themes)
  ?       Show this help
  q       Quit
"""

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("Keybindings", classes="modal-title")
            yield Static(self.HELP_TEXT, classes="help-text")
            with Horizontal(classes="button-row"):
                yield Button("Close", variant="primary", id="close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        self.dismiss()
