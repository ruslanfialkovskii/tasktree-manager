"""Modal widgets for creating tasks and adding repos."""

from typing import TypeVar

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, SelectionList, Static
from textual.widgets.selection_list import Selection

T = TypeVar("T")


class ThemedModalScreen(ModalScreen[T]):
    """Base class for themed modal screens with typed dismiss results."""

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


class CreateTaskModal(ThemedModalScreen[tuple[str, list[str], str] | None]):
    """Modal for creating a new task.

    Dismisses with: (name, repos, branch) tuple or None if cancelled.
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


class AddRepoModal(ThemedModalScreen[tuple[list[str], str] | None]):
    """Modal for adding repos to an existing task.

    Dismisses with: (repos, branch) tuple or None if cancelled.
    """

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


class ConfirmModal(ThemedModalScreen[bool]):
    """Modal for confirming an action.

    Dismisses with: True if confirmed, False if cancelled.
    """

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


class SafeDeleteModal(ThemedModalScreen[str | None]):
    """Modal for safely deleting a task with safety warnings.

    Dismisses with: "push", "lazygit", "force", or None if cancelled.
    """

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


class PushResultModal(ThemedModalScreen[None]):
    """Modal showing results of push operation.

    Dismisses with: None (informational only).
    """

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


class HelpModal(ThemedModalScreen[None]):
    """Modal showing keybindings help and application info.

    Dismisses with: None (informational only).
    """

    DEFAULT_CSS = ThemedModalScreen.DEFAULT_CSS + """
    HelpModal > Container {
        width: 70;
        max-height: 90%;
    }

    HelpModal .help-section {
        margin-bottom: 1;
    }

    HelpModal .help-section-title {
        color: $primary;
        text-style: bold;
        margin-bottom: 0;
    }

    HelpModal .help-content {
        color: $text;
        margin-left: 2;
    }

    HelpModal .help-key {
        color: $accent;
        text-style: bold;
    }

    HelpModal .help-desc {
        color: $text-muted;
    }

    HelpModal .help-info {
        color: $text-muted;
        text-style: italic;
        margin-top: 1;
        border-top: solid $primary;
        padding-top: 1;
    }

    HelpModal .scrollable-help {
        height: auto;
        max-height: 35;
        overflow-y: auto;
    }
    """

    def __init__(self, keybindings: dict[str, str] | None = None, config_path: str = "", *args, **kwargs):
        """Initialize help modal.

        Args:
            keybindings: Dictionary of action -> key mappings from config
            config_path: Path to config file for display
        """
        super().__init__(*args, **kwargs)
        self.keybindings = keybindings or {}
        self.config_path = config_path

    def _get_key(self, action: str, default: str) -> str:
        """Get the keybinding for an action, with formatting."""
        key = self.keybindings.get(action, default)
        # Format special keys for display
        key = key.replace("ctrl+", "Ctrl+").replace("shift+", "Shift+").replace("alt+", "Alt+")
        return key

    def _format_binding(self, action: str, default: str, description: str) -> str:
        """Format a single keybinding line."""
        key = self._get_key(action, default)
        # Pad key to align descriptions
        return f"  [bold cyan]{key:<12}[/] {description}"

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("tasktree Help", classes="modal-title")

            # Build help content with actual keybindings
            help_content = self._build_help_content()

            with Container(classes="scrollable-help"):
                yield Static(help_content, classes="help-text")

            # Show config info at bottom
            info_text = self._build_info_text()
            yield Static(info_text, classes="help-info")

            with Horizontal(classes="button-row"):
                yield Button("Close", variant="primary", id="close-btn")

    def _build_help_content(self) -> str:
        """Build the help content with current keybindings."""
        sections = []

        # Navigation section
        nav_section = "[bold $primary]Navigation[/]\n"
        nav_section += self._format_binding("cursor_down", "j", "Move cursor down") + "\n"
        nav_section += self._format_binding("cursor_up", "k", "Move cursor up") + "\n"
        nav_section += self._format_binding("focus_next", "tab", "Switch to next panel") + "\n"
        nav_section += self._format_binding("focus_previous", "shift+tab", "Switch to previous panel")
        sections.append(nav_section)

        # Task management section
        task_section = "[bold $primary]Task Management[/]\n"
        task_section += self._format_binding("new_task", "n", "Create a new task") + "\n"
        task_section += self._format_binding("add_repo", "a", "Add repository to current task") + "\n"
        task_section += self._format_binding("delete_task", "d", "Delete/finish current task")
        sections.append(task_section)

        # Git operations section
        git_section = "[bold $primary]Git Operations[/]\n"
        git_section += self._format_binding("open_lazygit", "g", "Open lazygit in worktree") + "\n"
        git_section += self._format_binding("open_shell", "enter", "Open shell in worktree") + "\n"
        git_section += self._format_binding("push_all", "p", "Push all worktrees in task") + "\n"
        git_section += self._format_binding("pull_all", "P", "Pull all worktrees in task") + "\n"
        git_section += self._format_binding("refresh", "r", "Refresh git status")
        sections.append(git_section)

        # General section
        general_section = "[bold $primary]General[/]\n"
        general_section += "  [bold cyan]Ctrl+P      [/] Open command palette (themes)\n"
        general_section += self._format_binding("help", "?", "Show this help") + "\n"
        general_section += self._format_binding("quit", "q", "Quit tasktree")
        sections.append(general_section)

        # Tips section
        tips_section = "[bold $primary]Tips[/]\n"
        tips_section += "  • Use [bold]Ctrl+P[/] to quickly switch themes\n"
        tips_section += "  • Keybindings can be customized in config.toml\n"
        tips_section += "  • Press [bold]g[/] to resolve conflicts with lazygit\n"
        tips_section += "  • Tasks are stored in your tasks directory"
        sections.append(tips_section)

        return "\n\n".join(sections)

    def _build_info_text(self) -> str:
        """Build the info text showing config location."""
        info = "Config: "
        if self.config_path:
            info += f"{self.config_path}"
        else:
            info += "~/.config/tasktree/config.toml"
        return info

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        self.dismiss()
