"""Worktree list widget for tasktree."""

from textual.message import Message
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from ..services.task_manager import Worktree


class WorktreeList(OptionList):
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

    @property
    def index(self) -> int | None:
        """Compatibility property - returns highlighted index."""
        return self.highlighted

    @index.setter
    def index(self, value: int | None) -> None:
        """Compatibility property - sets highlighted index."""
        self.highlighted = value

    def load_worktrees(self, worktrees: list[Worktree]) -> None:
        """Load worktrees into the list."""
        self.worktrees = worktrees
        self.clear_options()
        for worktree in worktrees:
            branch = worktree.branch or "unknown"
            # Build display text
            if worktree.is_dirty:
                prompt = f"  {worktree.name:<20} [cyan]{branch:<15}[/] [red]✗ {worktree.changed_files} files[/]"
            else:
                prompt = f"  {worktree.name:<20} [cyan]{branch:<15}[/] [green]✓[/]"
            self.add_option(Option(prompt, id=worktree.name))

        # Select first item if available
        if self.worktrees and self.option_count > 0:
            self.action_first()
            self._emit_highlighted()

    def _emit_highlighted(self) -> None:
        """Emit a WorktreeHighlighted message for the current item."""
        worktree = self.get_selected_worktree()
        self.post_message(self.WorktreeHighlighted(worktree))

    def get_selected_worktree(self) -> Worktree | None:
        """Get the currently selected worktree."""
        if self.highlighted is not None and 0 <= self.highlighted < len(self.worktrees):
            return self.worktrees[self.highlighted]
        return None

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Handle item highlight."""
        self._emit_highlighted()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle item selection."""
        worktree = self.get_selected_worktree()
        self.post_message(self.WorktreeSelected(worktree))

    def clear_worktrees(self) -> None:
        """Clear the worktree list."""
        self.worktrees = []
        self.clear_options()
