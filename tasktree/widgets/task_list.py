"""Task list widget for tasktree."""

from rich.text import Text
from textual.message import Message
from textual.widgets import ListItem, ListView, Static

from ..services.task_manager import Task
from ..themes import get_theme


class TaskListItem(ListItem):
    """A task item in the task list."""

    def __init__(self, task_data: Task, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.task_data = task_data

    def _get_theme(self):
        """Get the current theme from the app."""
        if hasattr(self.app, "theme_name"):
            return get_theme(self.app.theme_name)
        return get_theme("default")

    def compose(self):
        """Compose the task item."""
        theme = self._get_theme()
        text = Text()
        if self.task_data.is_dirty:
            text.append("● ", style=theme.error)
        else:
            text.append("  ")
        text.append(self.task_data.name, style=theme.foreground)
        if self.task_data.is_dirty:
            text.append(f" ({self.task_data.dirty_count})", style=theme.error)
        yield Static(text, classes="task-item-text")


class TaskList(ListView):
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

    def load_tasks(self, tasks: list[Task]) -> None:
        """Load tasks into the list."""
        self.tasks = tasks
        self.clear()
        for task in tasks:
            self.append(TaskListItem(task))

        # Select first item if available
        if self.tasks and len(self.children) > 0:
            self.index = 0
            self._emit_highlighted()

    def _emit_highlighted(self) -> None:
        """Emit a TaskHighlighted message for the current item."""
        task = self.get_selected_task()
        self.post_message(self.TaskHighlighted(task))

    def get_selected_task(self) -> Task | None:
        """Get the currently selected task."""
        if self.index is not None and 0 <= self.index < len(self.tasks):
            return self.tasks[self.index]
        return None

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle item highlight."""
        self._emit_highlighted()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle item selection."""
        task = self.get_selected_task()
        self.post_message(self.TaskSelected(task))

    def refresh_tasks(self, tasks: list[Task]) -> None:
        """Refresh the task list while preserving selection."""
        current_index = self.index
        self.load_tasks(tasks)
        if current_index is not None and current_index < len(tasks):
            self.index = current_index
            self._emit_highlighted()
