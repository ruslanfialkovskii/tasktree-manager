"""Modal widgets for creating tasks and adding repos."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, SelectionList, Static
from textual.widgets.selection_list import Selection


class CreateTaskModal(ModalScreen):
    """Modal for creating a new task."""

    CSS = """
    CreateTaskModal {
        align: center middle;
    }

    CreateTaskModal > Container {
        width: 70;
        height: auto;
        max-height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    CreateTaskModal .modal-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    CreateTaskModal Input {
        margin-bottom: 1;
    }

    CreateTaskModal .section-label {
        margin-top: 1;
        margin-bottom: 0;
    }

    CreateTaskModal SelectionList {
        height: 12;
        margin-bottom: 1;
    }

    CreateTaskModal .button-row {
        align: center middle;
        margin-top: 1;
    }

    CreateTaskModal Button {
        margin: 0 1;
    }
    """

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

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("Create New Task", classes="modal-title")
            yield Label("Task Name:", classes="section-label")
            yield Input(placeholder="e.g., FEAT-123-new-feature", id="task-name")
            yield Label("Base Branch:", classes="section-label")
            yield Input(value="master", placeholder="master", id="base-branch")
            yield Label("Select Repositories:", classes="section-label")
            yield SelectionList[str](
                *[Selection(repo, repo) for repo in self.available_repos],
                id="repo-list",
            )
            with Horizontal(classes="button-row"):
                yield Button("Create", variant="primary", id="create-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

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
        repo_list = self.query_one("#repo-list", SelectionList)

        name = name_input.value.strip()
        base_branch = branch_input.value.strip() or "master"
        selected_repos = list(repo_list.selected)

        if not name:
            self.notify("Task name is required", severity="error")
            return

        if not selected_repos:
            self.notify("Select at least one repository", severity="error")
            return

        self.dismiss((name, selected_repos, base_branch))


class AddRepoModal(ModalScreen):
    """Modal for adding repos to an existing task."""

    CSS = """
    AddRepoModal {
        align: center middle;
    }

    AddRepoModal > Container {
        width: 70;
        height: auto;
        max-height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    AddRepoModal .modal-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    AddRepoModal Input {
        margin-bottom: 1;
    }

    AddRepoModal .section-label {
        margin-top: 1;
        margin-bottom: 0;
    }

    AddRepoModal SelectionList {
        height: 12;
        margin-bottom: 1;
    }

    AddRepoModal .button-row {
        align: center middle;
        margin-top: 1;
    }

    AddRepoModal Button {
        margin: 0 1;
    }
    """

    def __init__(self, task_name: str, available_repos: list[str], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.task_name = task_name
        self.available_repos = available_repos

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(f"Add Repos to: {self.task_name}", classes="modal-title")
            yield Label("Base Branch:", classes="section-label")
            yield Input(value="master", placeholder="master", id="base-branch")
            yield Label("Select Repositories to Add:", classes="section-label")
            if self.available_repos:
                yield SelectionList[str](
                    *[Selection(repo, repo) for repo in self.available_repos],
                    id="repo-list",
                )
            else:
                yield Static("No more repositories available to add")
            with Horizontal(classes="button-row"):
                yield Button("Add", variant="primary", id="add-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

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
        repo_list = self.query_one("#repo-list", SelectionList)

        base_branch = branch_input.value.strip() or "master"
        selected_repos = list(repo_list.selected)

        if not selected_repos:
            self.notify("Select at least one repository", severity="error")
            return

        self.dismiss((selected_repos, base_branch))


class ConfirmModal(ModalScreen):
    """Modal for confirming an action."""

    CSS = """
    ConfirmModal {
        align: center middle;
    }

    ConfirmModal > Container {
        width: 60;
        height: auto;
        border: thick $error;
        background: $surface;
        padding: 1 2;
    }

    ConfirmModal .modal-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    ConfirmModal .modal-message {
        text-align: center;
        margin-bottom: 1;
    }

    ConfirmModal .button-row {
        align: center middle;
        margin-top: 1;
    }

    ConfirmModal Button {
        margin: 0 1;
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


class HelpModal(ModalScreen):
    """Modal showing keybindings help."""

    CSS = """
    HelpModal {
        align: center middle;
    }

    HelpModal > Container {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    HelpModal .modal-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    HelpModal .help-text {
        margin-bottom: 1;
    }

    HelpModal .button-row {
        align: center middle;
        margin-top: 1;
    }
    """

    HELP_TEXT = """
Navigation:
  j/↓     Move down
  k/↑     Move up
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
