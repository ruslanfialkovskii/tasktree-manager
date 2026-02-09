"""Status panel widget for tasktree-manager."""

from rich.text import Text
from textual.widgets import Static

from ..services.models import GitStatus, Task, Worktree


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
        """Render the task summary view — changed files grouped by repo."""
        if self._current_task is None:
            self.update(Text("No task selected", style="dim"))
            return

        task = self._current_task
        text = Text()

        dirty_worktrees = [wt for wt in task.worktrees if wt.is_dirty]

        if not dirty_worktrees:
            text.append("All repos clean", style="green")
            self.update(text)
            return

        for wt in dirty_worktrees:
            # Repo header
            text.append(f"{wt.name}", style="bold")
            text.append("\n")

            status = self._task_statuses.get(wt.name)
            if status:
                for status_code, filename in status.all_changes:
                    if status_code.strip().startswith("?"):
                        text.append(f" {status_code} ", style="red")
                        text.append(f"{filename}\n", style="red")
                    elif status_code.strip().startswith("M") or status_code.strip() == "M":
                        text.append(f" {status_code} ", style="yellow")
                        text.append(f"{filename}\n")
                    else:
                        text.append(f" {status_code} ", style="green")
                        text.append(f"{filename}\n")
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
