"""Status panel widget for tasktree."""

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from ..services.git_ops import GitStatus
from ..services.task_manager import Worktree


class StatusPanel(Static):
    """Panel displaying git status for selected worktree."""

    worktree_name: reactive[str] = reactive("")
    status_text: reactive[str] = reactive("")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._status: GitStatus | None = None

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
        if not self.worktree_name or self._status is None:
            self.update(Text("No worktree selected", style="dim"))
            return

        text = Text()

        # Header
        text.append("Status: ", style="cyan")
        text.append(f"{self.worktree_name}\n")

        # Show error state if present
        if self._status.error:
            text.append(f"\nError: {self._status.error}\n", style="red")
            text.append("Press 'r' to refresh", style="dim")
            self.update(text)
            return

        # Branch
        text.append("Branch: ", style="cyan")
        text.append(f"{self._status.branch}\n", style="green")

        # Sync info
        if self._status.ahead or self._status.behind:
            text.append("Sync:   ", style="cyan")
            if self._status.ahead:
                text.append(f"↑{self._status.ahead} ", style="green")
            if self._status.behind:
                text.append(f"↓{self._status.behind}", style="yellow")
            text.append("\n")

        text.append("\n")

        # Status
        if not self._status.is_dirty:
            text.append("Working tree clean", style="green")
        else:
            for status_code, filename in self._status.all_changes:
                if status_code.strip().startswith("?"):
                    text.append(f" {status_code} ", style="red")
                    text.append(f"{filename}\n", style="red")
                elif status_code.strip().startswith("M") or status_code.strip() == "M":
                    text.append(f" {status_code} ", style="yellow")
                    text.append(f"{filename}\n")
                else:
                    text.append(f" {status_code} ", style="green")
                    text.append(f"{filename}\n")

        self.update(text)

    def clear_status(self) -> None:
        """Clear the status display."""
        self.worktree_name = ""
        self.status_text = ""
        self._status = None
        self.update(Text("No worktree selected", style="dim"))
