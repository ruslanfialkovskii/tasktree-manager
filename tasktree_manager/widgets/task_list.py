"""Task list widget for tasktree-manager."""

from enum import Enum, auto

from textual.content import Content
from textual.message import Message
from textual.widgets import OptionList
from textual.widgets.option_list import Option, OptionDoesNotExist

from ..services.models import Task, group_by_epic

# Claude states rolled up on an epic row, most urgent first
_CLAUDE_URGENCY = ("waiting", "running", "ended")


class SortMode(Enum):
    """Sort modes for the task list."""

    NAME_ASC = auto()
    NAME_DESC = auto()
    DATE_NEWEST = auto()
    DATE_OLDEST = auto()
    STATUS_DIRTY = auto()
    STATUS_CLEAN = auto()


class TaskList(OptionList):
    """List of tasks widget.

    Epics render as foldable rows with their child tasks indented below.
    `all_tasks` holds every loaded task; `tasks` holds the visible rows in
    render order, so a row index maps straight to a task.
    """

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

    def __init__(
        self,
        *args,
        context_bindings: list[tuple[str, str, str]] | None = None,
        fold_keys: tuple[str, ...] = ("enter", "space"),
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.all_tasks: list[Task] = []
        self.tasks: list[Task] = []
        self._sort_mode: SortMode = SortMode.NAME_ASC
        # Last known Claude session statuses, kept so indicators survive reloads
        self._claude_statuses: dict[str, str] = {}
        # Epic name -> child tasks, child name -> epic name, folded epics
        self._kids: dict[str, list[Task]] = {}
        self._child_epic: dict[str, str] = {}
        self._collapsed: set[str] = set()
        # Child name -> True when it is the last row under its epic
        self._last_in_epic: dict[str, bool] = {}
        # Footer-visible (key, app action, description) bindings shown while
        # this panel has focus; the keys also exist app-level (hidden) so
        # they keep working regardless of focus
        for key, action, description in context_bindings or []:
            # Drop any inherited binding on the same key - dispatch and the
            # footer both use the first binding found, so an OptionList
            # default (e.g. "enter") would otherwise shadow the app action
            self._bindings.key_to_bindings.pop(key, None)
            self._bindings.bind(key, f"app.{action}", description, show=True)
        # Enter folds an epic instead of OptionList's select (a click still
        # selects); a fold key the user bound to an action stays theirs
        claimed = {key for key, _, _ in context_bindings or []}
        for i, key in enumerate(k for k in fold_keys if k not in claimed):
            self._bindings.key_to_bindings.pop(key, None)
            self._bindings.bind(key, "toggle_epic", "Fold", show=i == 0)

    @property
    def index(self) -> int | None:
        """Compatibility property - returns highlighted index."""
        return self.highlighted

    @index.setter
    def index(self, value: int | None) -> None:
        """Compatibility property - sets highlighted index."""
        self.highlighted = value

    @property
    def has_epics(self) -> bool:
        """True when any loaded task is an epic."""
        return bool(self._kids)

    def epic_of(self, task_name: str) -> str | None:
        """The epic a loaded task is grouped under, or None."""
        return self._child_epic.get(task_name)

    def epic_children(self, epic_name: str) -> list[Task]:
        """The loaded children of an epic, collapsed ones included."""
        return list(self._kids.get(epic_name, []))

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Hide the fold key while there is nothing to fold."""
        if action == "toggle_epic":
            return self.has_epics
        return super().check_action(action, parameters)

    def _format_task_option(self, task: Task, claude_status: str | None = None) -> Option:
        """Format a task as an Option for display.

        The prompt is assembled as Content, not a markup string: task
        directory names and aliases may contain brackets ("[WIP] fix"),
        which Textual's markup parser would consume as style tags. Without
        epics the row looks exactly as it did before epics existed.
        """
        parts: list[str | tuple[str, str]] = []
        members = [task]
        if task.name in self._kids:
            members += self._kids[task.name]
            parts.append("▸ " if task.name in self._collapsed else "▾ ")
            claude_status = self._rollup_claude(members)
        elif task.name in self._child_epic:
            parts.append(("└ " if self._last_in_epic.get(task.name) else "├ ", "dim"))
        elif self.has_epics:
            parts.append("  ")

        dirty_count = sum(member.dirty_count for member in members)
        parts.append(("●", "red") if dirty_count else "  ")
        parts.append(("◆", "blue") if task.has_claude_md else " ")
        parts.append(task.display_label)
        if task.name in self._kids:
            parts.append((f" · {len(members) - 1}", "dim"))
        if dirty_count:
            parts.append((f" ({dirty_count})", "red"))
        if claude_status == "running":
            parts.append((" ⟳", "magenta"))
        elif claude_status == "waiting":
            parts.append((" !", "yellow"))
        elif claude_status == "ended":
            parts.append((" ✓", "green"))
        return Option(Content.assemble(*parts), id=task.name)

    def _rollup_claude(self, members: list[Task]) -> str | None:
        """The most urgent Claude state across an epic and its children."""
        states = [self._claude_statuses.get(member.name) for member in members]
        return next((state for state in _CLAUDE_URGENCY if state in states), None)

    def load_tasks(
        self,
        tasks: list[Task],
        preserve_selection: str | None = None,
        claude_statuses: dict[str, str] | None = None,
    ) -> None:
        """Load tasks into the list.

        Args:
            tasks: List of tasks to load
            preserve_selection: Optional task name to preserve selection for
            claude_statuses: Optional dict of task_name -> claude status string
        """
        self.all_tasks = list(tasks)
        top, self._kids = group_by_epic(self.all_tasks)
        self._child_epic = {
            child.name: epic for epic, children in self._kids.items() for child in children
        }
        self._collapsed &= set(self._kids)
        # A selection target hidden in a folded epic would fall back to row 0
        if preserve_selection in self._child_epic:
            self._collapsed.discard(self._child_epic[preserve_selection])

        self.tasks = []
        self._last_in_epic = {}
        for task in self._sort_tasks(top):
            self.tasks.append(task)
            if task.name in self._collapsed:
                continue
            children = self._sort_tasks(self._kids.get(task.name, []))
            for i, child in enumerate(children):
                self._last_in_epic[child.name] = i == len(children) - 1
                self.tasks.append(child)

        self.clear_options()
        if claude_statuses is not None:
            self._claude_statuses = claude_statuses
        for task in self.tasks:
            self.add_option(self._format_task_option(task, self._claude_statuses.get(task.name)))
        self.refresh_bindings()

        # Select item - preserve previous selection if specified
        if self.tasks and self.option_count > 0:
            if preserve_selection:
                try:
                    # Use option ID to find the correct index
                    idx = self.get_option_index(preserve_selection)

                    # Defer highlight setting to next event loop cycle.
                    # Setting `highlighted` fires OptionHighlighted, whose
                    # handler emits TaskHighlighted exactly once.
                    def set_highlight():
                        self.highlighted = idx
                        self.scroll_to_highlight()

                    self.call_later(set_highlight)
                    return
                except OptionDoesNotExist:
                    self.action_first()
            else:
                self.action_first()

    def action_toggle_epic(self) -> None:
        """Fold or unfold the highlighted epic; on a child, fold its epic."""
        task = self.get_selected_task()
        if task is None:
            return
        if task.name in self._kids:
            epic = task.name
            if epic in self._collapsed:
                self._collapsed.discard(epic)
            else:
                self._collapsed.add(epic)
        elif task.name in self._child_epic:
            epic = self._child_epic[task.name]
            self._collapsed.add(epic)
        else:
            return
        self.load_tasks(self.all_tasks, preserve_selection=epic)

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

    def refresh_claude_indicators(self, statuses: dict[str, str]) -> None:
        """Update Claude status indicators without full reload.

        Re-renders every visible row; an epic row also rolls up the states
        of its children, folded ones included.
        """
        self._claude_statuses = statuses
        for task in self.tasks:
            new_option = self._format_task_option(task, statuses.get(task.name))
            self.replace_option_prompt(task.name, new_option.prompt)

    def cycle_sort_mode(self) -> None:
        """Cycle through sort modes and reload tasks."""
        modes = list(SortMode)
        current_idx = modes.index(self._sort_mode)
        self._sort_mode = modes[(current_idx + 1) % len(modes)]

        # Keep the highlighted task (no snap to row 0, one TaskHighlighted);
        # reload from all_tasks because folded children are not in self.tasks
        if self.all_tasks:
            current_task = self.get_selected_task()
            self.load_tasks(
                self.all_tasks,
                preserve_selection=current_task.name if current_task else None,
            )

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

    def _members(self, task: Task) -> list[Task]:
        """A task plus, for an epic, its children: what its sort keys cover."""
        return [task, *self._kids.get(task.name, [])]

    @staticmethod
    def _mtime(task: Task) -> float:
        return task.path.stat().st_mtime if task.path.exists() else 0

    def _sort_tasks(self, tasks: list[Task]) -> list[Task]:
        """Sort tasks according to current sort mode.

        An epic sorts by its newest member and counts as dirty when any
        member is dirty.
        """

        def newest(t: Task) -> float:
            return max(self._mtime(m) for m in self._members(t))

        def dirty(t: Task) -> bool:
            return any(m.is_dirty for m in self._members(t))

        match self._sort_mode:
            case SortMode.NAME_ASC:
                return sorted(tasks, key=lambda t: t.display_label.lower())
            case SortMode.NAME_DESC:
                return sorted(tasks, key=lambda t: t.display_label.lower(), reverse=True)
            case SortMode.DATE_NEWEST:
                return sorted(tasks, key=newest, reverse=True)
            case SortMode.DATE_OLDEST:
                return sorted(tasks, key=newest)
            case SortMode.STATUS_DIRTY:
                return sorted(tasks, key=lambda t: (not dirty(t), t.name.lower()))
            case SortMode.STATUS_CLEAN:
                return sorted(tasks, key=lambda t: (dirty(t), t.name.lower()))
