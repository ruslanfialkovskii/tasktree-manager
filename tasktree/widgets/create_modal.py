"""Modal widgets for creating tasks and adding repos."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, SelectionList, Static
from textual.widgets.selection_list import Selection

from ..themes import get_theme


class ThemedModalScreen(ModalScreen):
    """Base class for themed modal screens."""

    # Default CSS using lazygit-inspired theme colors
    DEFAULT_CSS = """
    ThemedModalScreen {
        align: center middle;
    }

    ThemedModalScreen > Container {
        width: 70;
        height: auto;
        max-height: 80%;
        border: round #444444;
        background: #1c1c1c;
        padding: 1 2;
    }

    ThemedModalScreen .modal-title {
        text-align: center;
        text-style: bold;
        color: #ffffff;
        margin-bottom: 1;
    }

    ThemedModalScreen .section-label {
        color: #808080;
        margin-top: 1;
        margin-bottom: 0;
    }

    ThemedModalScreen Input {
        background: #111111;
        border: round #444444;
        color: #ffffff;
        margin-bottom: 1;
    }

    ThemedModalScreen Input:focus {
        border: round #00d700;
    }

    ThemedModalScreen SelectionList {
        height: 12;
        margin-bottom: 1;
        background: #111111;
        border: round #444444;
    }

    ThemedModalScreen .button-row {
        align: center middle;
        margin-top: 1;
    }

    ThemedModalScreen Button {
        margin: 0 1;
        min-width: 12;
        background: #444444;
        color: #ffffff;
        border: none;
    }

    ThemedModalScreen Button:hover {
        background: #303030;
    }

    ThemedModalScreen Button.-primary {
        background: #005faf;
        color: #ffffff;
    }

    ThemedModalScreen Button.-primary:hover {
        background: #0087ff;
    }

    ThemedModalScreen Button.-error {
        background: #ff5f5f;
        color: #ffffff;
    }

    ThemedModalScreen .help-text {
        color: #ffffff;
        margin-bottom: 1;
    }

    ThemedModalScreen .modal-message {
        text-align: center;
        color: #ffffff;
        margin-bottom: 1;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._theme_name = "default"

    def on_mount(self) -> None:
        """Apply theme on mount."""
        if hasattr(self.app, "theme_name"):
            self._theme_name = self.app.theme_name
        self._apply_theme_styles()

    def _apply_theme_styles(self) -> None:
        """Apply theme colors to container and children."""
        theme = get_theme(self._theme_name)

        # Apply styles to the container
        try:
            container = self.query_one(Container)
            container.styles.background = theme.background_alt
            container.styles.border = ("round", theme.border)
        except Exception:
            pass

        # Apply styles to buttons
        for button in self.query(Button):
            if button.variant == "primary":
                button.styles.background = theme.accent
                button.styles.color = theme.highlight_text
            elif button.variant == "error":
                button.styles.background = theme.error
                button.styles.color = theme.highlight_text
            else:
                button.styles.background = theme.border
                button.styles.color = theme.foreground

        # Apply styles to inputs
        for input_widget in self.query(Input):
            input_widget.styles.background = theme.background
            input_widget.styles.border = ("round", theme.border)

        # Apply styles to selection lists
        for sel_list in self.query(SelectionList):
            sel_list.styles.background = theme.background
            sel_list.styles.border = ("round", theme.border)


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


class AddRepoModal(ThemedModalScreen):
    """Modal for adding repos to an existing task."""

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


class ConfirmModal(ThemedModalScreen):
    """Modal for confirming an action."""

    DEFAULT_CSS = ThemedModalScreen.DEFAULT_CSS + """
    ConfirmModal > Container {
        width: 60;
        border: round #ff5f5f;
    }

    ConfirmModal .modal-title {
        color: #ff5f5f;
    }
    """

    def __init__(self, title: str, message: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title_text = title
        self.message_text = message

    def _apply_theme_styles(self) -> None:
        """Apply theme colors including error styling."""
        super()._apply_theme_styles()
        theme = get_theme(self._theme_name)

        # Override container border with error color
        try:
            container = self.query_one(Container)
            container.styles.border = ("round", theme.error)
        except Exception:
            pass

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


class HelpModal(ThemedModalScreen):
    """Modal showing keybindings help."""

    DEFAULT_CSS = ThemedModalScreen.DEFAULT_CSS + """
    HelpModal > Container {
        width: 60;
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

Themes:
  t       Cycle theme

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
