"""Setup wizard for first-time configuration."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


class SetupModal(ModalScreen[tuple[Path, Path] | None]):
    """Modal for first-time setup configuration.

    Dismisses with: (repos_dir, tasks_dir) tuple or None if cancelled.
    """

    DEFAULT_CSS = """
    SetupModal {
        align: center middle;
    }

    SetupModal > Container {
        width: 80;
        height: auto;
        border: round $primary;
        background: $surface;
        padding: 1 2;
    }

    SetupModal .modal-title {
        text-align: center;
        text-style: bold;
        color: $text;
        margin-bottom: 1;
    }

    SetupModal .welcome-text {
        color: $text;
        margin-bottom: 1;
    }

    SetupModal .section-label {
        color: $foreground-muted;
        margin-top: 1;
        margin-bottom: 0;
    }

    SetupModal .help-text {
        color: $foreground-muted;
        margin-bottom: 1;
        text-style: italic;
    }

    SetupModal Input {
        background: $background;
        border: round $primary;
        color: $text;
        margin-bottom: 1;
    }

    SetupModal Input:focus {
        border: round $accent;
    }

    SetupModal .button-row {
        align: center middle;
        margin-top: 1;
    }

    SetupModal Button {
        margin: 0 1;
        min-width: 12;
    }

    SetupModal .error-message {
        color: $text-error;
        text-align: center;
        margin-top: 1;
    }
    """

    WELCOME_TEXT = """Welcome to tasktree!

Before you start, please configure the following directories:

1. REPOS_DIR: Where your git repositories are located
2. TASKS_DIR: Where task worktrees will be created

These settings will be saved to ~/.config/tasktree/config.toml
"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.error_message = ""

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("tasktree Setup", classes="modal-title")
            yield Static(self.WELCOME_TEXT, classes="welcome-text")

            yield Label("Repositories Directory:", classes="section-label")
            yield Static(
                "Directory containing your git repositories (e.g., ~/repos, ~/code)",
                classes="help-text",
            )
            yield Input(
                placeholder="e.g., /Users/username/repos",
                value=str(Path.home() / "repos"),
                id="repos-dir",
            )

            yield Label("Tasks Directory:", classes="section-label")
            yield Static(
                "Directory where task worktrees will be created (e.g., ~/tasks)",
                classes="help-text",
            )
            yield Input(
                placeholder="e.g., /Users/username/tasks",
                value=str(Path.home() / "tasks"),
                id="tasks-dir",
            )

            if self.error_message:
                yield Static(self.error_message, classes="error-message")

            with Horizontal(classes="button-row"):
                yield Button("Save & Continue", variant="primary", id="save-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id == "save-btn":
            self._save_config()

    def _save_config(self) -> None:
        """Validate and save configuration."""
        repos_input = self.query_one("#repos-dir", Input)
        tasks_input = self.query_one("#tasks-dir", Input)

        repos_dir = Path(repos_input.value.strip()).expanduser()
        tasks_dir = Path(tasks_input.value.strip()).expanduser()

        # Validate
        errors = []

        if not repos_dir.exists():
            errors.append(f"Repositories directory does not exist: {repos_dir}")
        elif not repos_dir.is_dir():
            errors.append(f"Repositories path is not a directory: {repos_dir}")

        if not tasks_dir.parent.exists():
            errors.append(f"Parent directory does not exist: {tasks_dir.parent}")

        if errors:
            self.error_message = "\n".join(errors)
            self.refresh(recompose=True)
            return

        # Save and dismiss
        self.dismiss((repos_dir, tasks_dir))
