"""Task list widget for tasktree."""

from textual.message import Message
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from ..services.task_manager import Task


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tasks: list[Task] = []

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
        self.tasks = tasks
        self.clear_options()
        for task in tasks:
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
