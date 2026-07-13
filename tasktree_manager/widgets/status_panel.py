"""Status panel widget for tasktree-manager."""

from rich.text import Text
from textual.widgets import Static

from ..services.models import GitStatus, Task, Worktree


def _style_for_code(status_code: str) -> str:
    """Pick a display style for a git XY status code."""
    if "U" in status_code or status_code in ("AA", "DD"):
        return "bold red"  # merge conflicts
    if status_code.strip().startswith("?"):
        return "red"  # untracked
    if "D" in status_code:
        return "red"  # deletions
    if "M" in status_code or "T" in status_code:
        return "yellow"  # modifications
    return "green"  # additions, renames, copies


class StatusPanel(Static):
    """Panel displaying git status for selected worktree or task summary."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._worktree_name: str = ""
        self._status: GitStatus | None = None
        self._current_task: Task | None = None
        self._task_statuses: dict[str, GitStatus] = {}
        self._mode: str = "worktree"  # "worktree" or "task"

    def update_status(self, worktree: Worktree | None, status: GitStatus | None) -> None:
        """Update the status display for a worktree."""
        self._mode = "worktree"
        if worktree is None or status is None:
            self._worktree_name = ""
            self._status = None
            self._update_display()
            return

        self._worktree_name = worktree.name
        self._status = status
        self._update_display()

    def update_task_summary(
        self, task: Task | None, statuses: dict[str, GitStatus] | None = None
    ) -> None:
        """Update the display with a task summary.

        Args:
            task: The task to display
            statuses: Optional dict of worktree_name -> GitStatus with file details
        """
        self._mode = "task"
        self._current_task = task
        self._task_statuses = statuses or {}
        self._update_display()

    def _update_display(self) -> None:
        """Update the display content."""
        if self._mode == "task":
            self._render_task_summary()
        else:
            self._render_worktree_status()

    def _render_task_summary(self) -> None:
        """Render the task summary view — every repo with its changes or 'clean'."""
        if self._current_task is None:
            self.update(Text("No task selected", style="dim"))
            return

        task = self._current_task
        text = Text()

        for wt in task.worktrees:
            # Repo header
            text.append(f"{wt.name}", style="bold")
            text.append("\n")

            if not wt.is_dirty:
                text.append("clean\n", style="dim")
            else:
                status = self._task_statuses.get(wt.name)
                if status:
                    self._append_changes(text, status)
                else:
                    text.append(f"  {wt.changed_files} files changed\n", style="dim italic")

            text.append("\n")

        self.update(text)

    def _render_worktree_status(self) -> None:
        """Render the worktree-specific status view."""
        if not self._worktree_name or self._status is None:
            self.update(Text("No worktree selected", style="dim"))
            return

        text = Text()

        # Header
        text.append("Repository: ", style="cyan")
        text.append(f"{self._worktree_name}\n")

        # Show error state if present
        if self._status.error:
            text.append(f"\nError: {self._status.error}\n", style="red")
            text.append("Press 'r' to refresh", style="dim")
            self.update(text)
            return

        # Branch
        text.append("Branch: ", style="cyan")
        text.append(f"{self._status.branch}\n", style="green")

        # Sync info — always shown; "up to date" when not ahead/behind
        text.append("Sync:   ", style="cyan")
        if self._status.ahead or self._status.behind:
            if self._status.ahead:
                text.append(f"↑{self._status.ahead} ", style="green")
            if self._status.behind:
                text.append(f"↓{self._status.behind}", style="yellow")
            text.append("\n")
        else:
            text.append("up to date\n", style="dim")

        text.append("\n")

        # Status
        if not self._status.is_dirty:
            text.append("working tree clean", style="dim")
        else:
            self._append_changes(text, self._status)

        self.update(text)

    @staticmethod
    def _append_changes(text: Text, status: GitStatus) -> None:
        """Append the status entries with per-code styling."""
        for status_code, filename in status.all_changes:
            style = _style_for_code(status_code)
            text.append(f" {status_code} ", style=style)
            text.append(f"{filename}\n", style="red" if "red" in style else "")

    def clear_status(self) -> None:
        """Clear the status display."""
        self._worktree_name = ""
        self._status = None
        self._current_task = None
        self._mode = "worktree"
        self.update(Text("No worktree selected", style="dim"))

    def set_loading(self, loading: bool = True) -> None:
        """Show or hide loading indicator.

        Args:
            loading: If True, show loading indicator. If False, restore display.
        """
        if loading:
            self.update(Text("Loading...", style="dim italic"))
        else:
            self._update_display()
