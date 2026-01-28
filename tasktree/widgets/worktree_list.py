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

    class GroupingChanged(Message):
        """Message sent when the grouping mode changes."""

        def __init__(self, enabled: bool):
            self.enabled = enabled
            super().__init__()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.worktrees: list[Worktree] = []
        self._grouping_enabled: bool = False
        # Maps option index to worktree index (for handling headers)
        self._option_to_worktree: dict[int, int] = {}

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
        self._option_to_worktree.clear()
        self.clear_options()

        if not worktrees:
            return

        # Calculate column widths for alignment
        max_name_len = max(len(wt.name) for wt in worktrees)
        max_branch_len = max(len(wt.branch or "unknown") for wt in worktrees)

        if self._grouping_enabled:
            self._load_grouped_worktrees(worktrees, max_name_len, max_branch_len)
        else:
            self._load_flat_worktrees(worktrees, max_name_len, max_branch_len)

        # Select first selectable item if available
        if self.worktrees and self.option_count > 0:
            self.action_first()
            self._emit_highlighted()

    def _load_flat_worktrees(
        self, worktrees: list[Worktree], max_name_len: int, max_branch_len: int
    ) -> None:
        """Load worktrees without grouping."""
        for idx, worktree in enumerate(worktrees):
            option_idx = self.option_count
            self._option_to_worktree[option_idx] = idx
            self._add_worktree_option(worktree, max_name_len, max_branch_len)

    def _load_grouped_worktrees(
        self, worktrees: list[Worktree], max_name_len: int, max_branch_len: int
    ) -> None:
        """Load worktrees grouped by dirty/clean status."""
        dirty = [(i, wt) for i, wt in enumerate(worktrees) if wt.is_dirty]
        clean = [(i, wt) for i, wt in enumerate(worktrees) if not wt.is_dirty]

        # Add dirty section
        if dirty:
            self.add_option(Option("[bold red]Dirty[/]", disabled=True))
            for orig_idx, worktree in dirty:
                option_idx = self.option_count
                self._option_to_worktree[option_idx] = orig_idx
                self._add_worktree_option(worktree, max_name_len, max_branch_len)

        # Add separator between groups if both exist
        if dirty and clean:
            self.add_option(None)  # None creates a separator

        # Add clean section
        if clean:
            self.add_option(Option("[bold green]Clean[/]", disabled=True))
            for orig_idx, worktree in clean:
                option_idx = self.option_count
                self._option_to_worktree[option_idx] = orig_idx
                self._add_worktree_option(worktree, max_name_len, max_branch_len)

    def _add_worktree_option(
        self, worktree: Worktree, max_name_len: int, max_branch_len: int
    ) -> None:
        """Add a single worktree option to the list."""
        branch = worktree.branch or "unknown"
        name_col = f"{worktree.name:<{max_name_len}}"
        branch_col = f"{branch:<{max_branch_len}}"

        if worktree.is_dirty:
            prompt = f"  {name_col}  [cyan]{branch_col}[/]  [red]✗ {worktree.changed_files} files[/]"
        else:
            prompt = f"  {name_col}  [cyan]{branch_col}[/]  [green]✓[/]"
        self.add_option(Option(prompt, id=worktree.name))

    def _emit_highlighted(self) -> None:
        """Emit a WorktreeHighlighted message for the current item."""
        worktree = self.get_selected_worktree()
        self.post_message(self.WorktreeHighlighted(worktree))

    def get_selected_worktree(self) -> Worktree | None:
        """Get the currently selected worktree."""
        if self.highlighted is None:
            return None

        # Use mapping if grouping is enabled
        if self._grouping_enabled:
            worktree_idx = self._option_to_worktree.get(self.highlighted)
            if worktree_idx is not None and 0 <= worktree_idx < len(self.worktrees):
                return self.worktrees[worktree_idx]
            return None

        # Flat mode - direct index mapping
        if 0 <= self.highlighted < len(self.worktrees):
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
        self._option_to_worktree.clear()
        self.clear_options()

    def toggle_grouping(self) -> None:
        """Toggle grouping mode and reload worktrees."""
        self._grouping_enabled = not self._grouping_enabled

        # Reload with current worktrees
        if self.worktrees:
            self.load_worktrees(list(self.worktrees))

        self.post_message(self.GroupingChanged(self._grouping_enabled))
