"""Status panel widget for tasktree."""

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from ..services.git_ops import GitStatus
from ..services.task_manager import Worktree
from ..themes import get_theme


class StatusPanel(Static):
    """Panel displaying git status for selected worktree."""

    worktree_name: reactive[str] = reactive("")
    status_text: reactive[str] = reactive("")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._status: GitStatus | None = None

    def _get_theme(self):
        """Get the current theme from the app."""
        if hasattr(self.app, "theme_name"):
            return get_theme(self.app.theme_name)
        return get_theme("default")

    def update_status(self, worktree: Worktree | None, status: GitStatus | None) -> None:
        """Update the status display for a worktree."""
        if worktree is None or status is None:
            self.worktree_name = ""
            self.status_text = "No worktree selected"
            self._status = None
            self._update_display()
            return

        self.worktree_name = worktree.name
        self._status = status
        self._update_display()

    def _update_display(self) -> None:
        """Update the display content."""
        theme = self._get_theme()

        if not self.worktree_name or self._status is None:
            self.update(Text("No worktree selected", style=theme.foreground_muted))
            return

        text = Text()

        # Header
        text.append("Status: ", style=theme.accent)
        text.append(f"{self.worktree_name}\n", style=theme.foreground)

        # Branch
        text.append("Branch: ", style=theme.accent)
        text.append(f"{self._status.branch}\n", style=theme.success)

        # Sync info
        if self._status.ahead or self._status.behind:
            text.append("Sync:   ", style=theme.accent)
            if self._status.ahead:
                text.append(f"↑{self._status.ahead} ", style=theme.success)
            if self._status.behind:
                text.append(f"↓{self._status.behind}", style=theme.warning)
            text.append("\n")

        text.append("\n")

        # Status
        if not self._status.is_dirty:
            text.append("Working tree clean", style=theme.success)
        else:
            for status_code, filename in self._status.all_changes:
                if status_code.strip().startswith("?"):
                    text.append(f" {status_code} ", style=theme.error)
                    text.append(f"{filename}\n", style=theme.error)
                elif status_code.strip().startswith("M") or status_code.strip() == "M":
                    text.append(f" {status_code} ", style=theme.warning)
                    text.append(f"{filename}\n", style=theme.foreground)
                else:
                    text.append(f" {status_code} ", style=theme.success)
                    text.append(f"{filename}\n", style=theme.foreground)

        self.update(text)

    def clear_status(self) -> None:
        """Clear the status display."""
        self.worktree_name = ""
        self.status_text = ""
        self._status = None
        theme = self._get_theme()
        self.update(Text("No worktree selected", style=theme.foreground_muted))
