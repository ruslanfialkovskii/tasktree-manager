"""Status panel widget for tasktree."""

from textual.widgets import Static
from textual.reactive import reactive

from ..services.task_manager import Worktree
from ..services.git_ops import GitStatus


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
            self.update("No worktree selected")
            return

        lines = [f"Status: {self.worktree_name}"]
        lines.append(f"Branch: {self._status.branch}")

        if self._status.ahead or self._status.behind:
            sync = []
            if self._status.ahead:
                sync.append(f"↑{self._status.ahead}")
            if self._status.behind:
                sync.append(f"↓{self._status.behind}")
            lines.append(f"Sync: {' '.join(sync)}")

        lines.append("")

        if not self._status.is_dirty:
            lines.append("Working tree clean")
        else:
            for status_code, filename in self._status.all_changes:
                lines.append(f" {status_code} {filename}")

        self.update("\n".join(lines))

    def clear_status(self) -> None:
        """Clear the status display."""
        self.worktree_name = ""
        self.status_text = ""
        self._status = None
        self.update("No worktree selected")
