"""Task list widget for tasktree."""

from enum import Enum, auto

from textual.message import Message
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from ..services.task_manager import Task


class SortMode(Enum):
    """Sort modes for the task list."""

    NAME_ASC = auto()
    NAME_DESC = auto()
    DATE_NEWEST = auto()
    DATE_OLDEST = auto()
    STATUS_DIRTY = auto()
    STATUS_CLEAN = auto()


class TaskList(OptionList):
    """List of tasks widget."""

    class TaskSelected(Message):
        """Message sent when a task is selected."""

        def __init__(self, task: Task | None):
            self.task = task
            super().__init__()

    class TaskHighlighted(Message):
        """Message sent when a task is highlighted."""

        def __init__(self, task: Task | None):
            self.task = task
            super().__init__()

    class SortModeChanged(Message):
        """Message sent when the sort mode changes."""

        def __init__(self, mode: SortMode, label: str):
            self.mode = mode
            self.label = label
            super().__init__()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tasks: list[Task] = []
        self._sort_mode: SortMode = SortMode.NAME_ASC

    @property
    def index(self) -> int | None:
        """Compatibility property - returns highlighted index."""
        return self.highlighted

    @index.setter
    def index(self, value: int | None) -> None:
        """Compatibility property - sets highlighted index."""
        self.highlighted = value

    def load_tasks(self, tasks: list[Task]) -> None:
        """Load tasks into the list."""
        sorted_tasks = self._sort_tasks(tasks)
        self.tasks = sorted_tasks
        self.clear_options()
        for task in sorted_tasks:
            # Build display text with dirty indicator
            if task.is_dirty:
                prompt = f"[red]●[/] {task.name} [red]({task.dirty_count})[/]"
            else:
                prompt = f"  {task.name}"
            self.add_option(Option(prompt, id=task.name))

        # Select first item if available
        if self.tasks and self.option_count > 0:
            self.action_first()
            self._emit_highlighted()

    def _emit_highlighted(self) -> None:
        """Emit a TaskHighlighted message for the current item."""
        task = self.get_selected_task()
        self.post_message(self.TaskHighlighted(task))

    def get_selected_task(self) -> Task | None:
        """Get the currently selected task."""
        if self.highlighted is not None and 0 <= self.highlighted < len(self.tasks):
            return self.tasks[self.highlighted]
        return None

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Handle item highlight."""
        self._emit_highlighted()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle item selection."""
        task = self.get_selected_task()
        self.post_message(self.TaskSelected(task))

    def refresh_tasks(self, tasks: list[Task]) -> None:
        """Refresh the task list while preserving selection."""
        current_index = self.highlighted
        self.load_tasks(tasks)
        if current_index is not None and current_index < len(tasks):
            self.highlighted = current_index
            self._emit_highlighted()

    def cycle_sort_mode(self) -> None:
        """Cycle through sort modes and reload tasks."""
        modes = list(SortMode)
        current_idx = modes.index(self._sort_mode)
        self._sort_mode = modes[(current_idx + 1) % len(modes)]

        # Re-sort and reload with current tasks
        if self.tasks:
            sorted_tasks = self._sort_tasks(self.tasks)
            self.tasks = sorted_tasks
            self.clear_options()
            for task in sorted_tasks:
                if task.is_dirty:
                    prompt = f"[red]●[/] {task.name} [red]({task.dirty_count})[/]"
                else:
                    prompt = f"  {task.name}"
                self.add_option(Option(prompt, id=task.name))

            if self.tasks and self.option_count > 0:
                self.action_first()
                self._emit_highlighted()

        self.post_message(self.SortModeChanged(self._sort_mode, self.get_sort_label()))

    def get_sort_label(self) -> str:
        """Get display label for current sort mode."""
        match self._sort_mode:
            case SortMode.NAME_ASC:
                return "by name ↑"
            case SortMode.NAME_DESC:
                return "by name ↓"
            case SortMode.DATE_NEWEST:
                return "by date ↓"
            case SortMode.DATE_OLDEST:
                return "by date ↑"
            case SortMode.STATUS_DIRTY:
                return "dirty first"
            case SortMode.STATUS_CLEAN:
                return "clean first"

    def _sort_tasks(self, tasks: list[Task]) -> list[Task]:
        """Sort tasks according to current sort mode."""
        match self._sort_mode:
            case SortMode.NAME_ASC:
                return sorted(tasks, key=lambda t: t.name.lower())
            case SortMode.NAME_DESC:
                return sorted(tasks, key=lambda t: t.name.lower(), reverse=True)
            case SortMode.DATE_NEWEST:
                return sorted(
                    tasks,
                    key=lambda t: t.path.stat().st_mtime if t.path.exists() else 0,
                    reverse=True,
                )
            case SortMode.DATE_OLDEST:
                return sorted(
                    tasks,
                    key=lambda t: t.path.stat().st_mtime if t.path.exists() else 0,
                )
            case SortMode.STATUS_DIRTY:
                return sorted(tasks, key=lambda t: (not t.is_dirty, t.name.lower()))
            case SortMode.STATUS_CLEAN:
                return sorted(tasks, key=lambda t: (t.is_dirty, t.name.lower()))
