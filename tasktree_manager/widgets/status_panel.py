"""Status panel widget for tasktree-manager."""

from rich.text import Text
from textual.widgets import Static

from ..services.claude_sessions import ClaudeRecap, format_clock, format_duration
from ..services.models import GitStatus, Task, Worktree

# .claude_status values worth a suffix on the recap line
_LIVE_LABELS = {"running": ("busy", "yellow"), "waiting": ("idle", "green")}


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
        self._loading: bool = False
        # Latest Claude session recap and the task it belongs to
        self._claude_recap: ClaudeRecap | None = None
        self._recap_task_name: str | None = None
        self._claude_live: str | None = None

    def set_claude_recap(
        self, task_name: str, recap: ClaudeRecap | None, live: str | None = None
    ) -> None:
        """Store the Claude recap for a task; re-render if that task is shown.

        A recap that lands while the git summary is still loading is kept
        and drawn with the summary, so it never replaces "Loading...".
        """
        self._claude_recap = recap
        self._recap_task_name = task_name
        self._claude_live = live
        self._rerender_task_view()

    def set_claude_live_status(self, live: str | None) -> None:
        """Update the busy/idle suffix on the recap line."""
        if live != self._claude_live:
            self._claude_live = live
            self._rerender_task_view()

    def _rerender_task_view(self) -> None:
        """Redraw the task summary if the shown task owns the stored recap."""
        if self._mode != "task" or self._loading or self._current_task is None:
            return
        if self._current_task.name == self._recap_task_name:
            self._update_display()

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
        self._loading = False
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

        if self._claude_recap is not None and self._recap_task_name == task.name:
            self._append_claude_recap(text, self._claude_recap)

        self.update(text)

    def _append_claude_recap(self, text: Text, recap: ClaudeRecap) -> None:
        """Append the Claude session block: title, turn line, recap or prompt."""
        text.append("─ claude " + "─" * 17 + "\n", style="dim")
        text.append(f"{recap.title}\n", style="bold")

        turn_parts = []
        if recap.duration_ms is not None:
            turn_parts.append(f"Baked for {format_duration(recap.duration_ms)}")
        if recap.finished_at is not None:
            turn_parts.append(f"done {format_clock(recap.finished_at)}")
        live = _LIVE_LABELS.get(self._claude_live or "")
        if turn_parts or live:
            text.append("✻ ", style="magenta")
            text.append(" · ".join(turn_parts), style="dim")
            if live:
                label, style = live
                text.append(f"{' · ' if turn_parts else ''}{label}", style=style)
            text.append("\n")

        if recap.summary:
            text.append("※ recap: ", style="cyan")
            text.append(f"{recap.summary}\n")
        elif recap.last_prompt:
            text.append(f"last prompt: {recap.last_prompt}\n", style="dim")

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
        self._claude_recap = None
        self._recap_task_name = None
        self.update(Text("No worktree selected", style="dim"))

    def set_loading(self, loading: bool = True) -> None:
        """Show or hide loading indicator.

        Args:
            loading: If True, show loading indicator. If False, restore display.
        """
        self._loading = loading
        if loading:
            self.update(Text("Loading...", style="dim italic"))
        else:
            self._update_display()
