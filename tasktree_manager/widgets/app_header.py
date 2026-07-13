"""Application header bar: app name on the left, live metadata on the right."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


class AppHeader(Horizontal):
    """Slim single-row header: `⊶ tasktree` + `n tasks · m dirty · dir · theme x`."""

    DEFAULT_CSS = """
    AppHeader {
        dock: top;
        height: 1;
        background: $panel;
        padding: 0 1;
    }

    AppHeader #header-app-name {
        width: auto;
        color: $accent;
        text-style: bold;
    }

    AppHeader #header-stats {
        width: 1fr;
        color: $text-muted;
        text-align: right;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._task_count: int = 0
        self._dirty_count: int = 0
        self._tasks_dir: str = ""
        self._theme: str = ""

    def compose(self) -> ComposeResult:
        yield Static("⊶ tasktree", id="header-app-name", markup=False)
        yield Static("", id="header-stats", markup=False)

    def update_stats(self, task_count: int, dirty_count: int, tasks_dir: str) -> None:
        """Refresh the task counts and tasks directory."""
        self._task_count = task_count
        self._dirty_count = dirty_count
        self._tasks_dir = tasks_dir
        self._render_meta()

    def set_theme(self, theme: str) -> None:
        """Refresh the displayed theme name."""
        self._theme = theme
        self._render_meta()

    def _render_meta(self) -> None:
        parts = []
        if self._task_count:
            parts.append(f"{self._task_count} tasks")
            parts.append(f"{self._dirty_count} dirty")
        if self._tasks_dir:
            parts.append(self._tasks_dir)
        if self._theme:
            parts.append(f"theme {self._theme}")
        self.query_one("#header-stats", Static).update(" · ".join(parts))
