"""Worktree list widget for tasktree."""

from textual.widgets import ListItem, ListView, Static
from textual.message import Message

from ..services.task_manager import Worktree


class WorktreeListItem(ListItem):
    """A worktree item in the worktree list."""

    def __init__(self, worktree: Worktree, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.worktree = worktree

    def compose(self):
        """Compose the worktree item."""
        dirty_indicator = "✗" if self.worktree.is_dirty else "✓"
        dirty_info = f" {self.worktree.changed_files} files" if self.worktree.is_dirty else ""
        branch = self.worktree.branch or "unknown"

        text = f"  {self.worktree.name:<20} {branch:<15} {dirty_indicator}{dirty_info}"
        yield Static(text, classes="worktree-item-text")


class WorktreeList(ListView):
    """List of worktrees widget."""

    class WorktreeSelected(Message):
        """Message sent when a worktree is selected."""

        def __init__(self, worktree: Worktree | None):
            self.worktree = worktree
            super().__init__()

    class WorktreeHighlighted(Message):
        """Message sent when a worktree is highlighted."""

        def __init__(self, worktree: Worktree | None):
            self.worktree = worktree
            super().__init__()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.worktrees: list[Worktree] = []

    def load_worktrees(self, worktrees: list[Worktree]) -> None:
        """Load worktrees into the list."""
        self.worktrees = worktrees
        self.clear()
        for worktree in worktrees:
            self.append(WorktreeListItem(worktree))

        # Select first item if available
        if self.worktrees and len(self.children) > 0:
            self.index = 0
            self._emit_highlighted()

    def _emit_highlighted(self) -> None:
        """Emit a WorktreeHighlighted message for the current item."""
        worktree = self.get_selected_worktree()
        self.post_message(self.WorktreeHighlighted(worktree))

    def get_selected_worktree(self) -> Worktree | None:
        """Get the currently selected worktree."""
        if self.index is not None and 0 <= self.index < len(self.worktrees):
            return self.worktrees[self.index]
        return None

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle item highlight."""
        self._emit_highlighted()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle item selection."""
        worktree = self.get_selected_worktree()
        self.post_message(self.WorktreeSelected(worktree))

    def clear_worktrees(self) -> None:
        """Clear the worktree list."""
        self.worktrees = []
        self.clear()
