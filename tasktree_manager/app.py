"""Main application for tasktree-manager."""

import json
import subprocess
import time
from pathlib import Path

from rich.markup import escape
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Static

from . import __version__
from .commands import TaskTreeCommands
from .services.claude_hooks import ensure_claude_hooks, has_claude_session
from .services.config import Config
from .services.git_ops import GitOps
from .services.models import GitStatus, Task, TaskSafetyReport, Worktree
from .services.task_manager import TaskManager
from .themes import ALL_THEMES, THEME_CYCLE
from .widgets.app_header import AppHeader
from .widgets.create_modal import (
    AddRepoModal,
    ConfirmModal,
    CreateTaskModal,
    HelpModal,
    PushResultModal,
    SafeDeleteModal,
)
from .widgets.messages_panel import MessageLevel, MessagesPanel
from .widgets.setup_modal import SetupModal
from .widgets.status_panel import StatusPanel
from .widgets.task_list import TaskList
from .widgets.worktree_list import WorktreeList


class TaskTreeApp(App):
    """TUI application for managing worktree-based tasks."""

    TITLE = "tasktree-manager"

    # System commands plus all keybound tasktree actions (searchable by
    # name, displayed with their configured hotkey)
    COMMANDS = App.COMMANDS | {TaskTreeCommands}

    # Layered-panel look from the TaskTree design system, driven entirely
    # by design tokens so every theme restyles the whole UI: panel bodies
    # ($panel) sit darker than the screen ground ($background), title bars
    # carry a [n] number + context and a right-aligned counter above a
    # hairline, the focused panel swaps $border-blurred for $border, and
    # list selection uses the theme's $block-cursor-* variables.
    CSS = """
    /* Main layout */
    Screen {
        background: $background;
    }

    #main-container {
        height: 100%;
        width: 100%;
        background: $background;
        layout: horizontal;
    }

    /* Left column - Tasks and Worktrees stacked */
    #left-column {
        width: 35%;
        min-width: 25;
        height: 100%;
    }

    /* Right column - Info/Status panel */
    #right-column {
        width: 65%;
        height: 100%;
    }

    /* Panels */
    #task-panel, #worktree-panel {
        height: 1fr;
        min-height: 8;
    }

    #task-panel, #worktree-panel, #status-panel, #messages-panel {
        border: round $border-blurred;
        background: $panel;
        padding: 0;
    }

    #task-panel:focus-within, #worktree-panel:focus-within {
        border: round $border;
    }

    #status-panel, #messages-panel {
        height: 100%;
    }

    /* Panel title bars: [n] Name · context ......... counter */
    .panel-title-bar {
        height: 2;
        width: 100%;
        border-bottom: solid $border-blurred;
        background: transparent;
    }

    .panel-title {
        width: 1fr;
        padding: 0 1;
        color: $text;
        text-align: left;
    }

    .panel-counter {
        width: auto;
        padding: 0 1;
        color: $text-muted;
    }

    #task-panel:focus-within .panel-title,
    #worktree-panel:focus-within .panel-title {
        color: $accent;
    }

    /* Task/worktree lists (OptionList): the panel supplies border and
       background; selection styling comes from $block-cursor-* tokens */
    #task-list, #worktree-list {
        height: 1fr;
        background: transparent;
        scrollbar-gutter: stable;
        border: none;
        padding: 0;

        &:focus {
            border: none;
        }
    }

    /* Status panel styling */
    #status-display {
        height: 100%;
        padding: 1 1 0 1;
        background: transparent;
        color: $text;
        overflow-y: auto;
        scrollbar-gutter: stable;
    }

    /* Status panel hidden state */
    #status-panel.-hidden {
        display: none;
    }

    /* Messages panel */
    #messages-panel {
        display: none;
    }

    #messages-panel.-visible {
        display: block;
    }

    #messages-display {
        height: 100%;
        padding: 0 1;
        background: transparent;
        color: $text;
        overflow-y: auto;
        scrollbar-gutter: stable;
    }

    /* Scrollbar */
    ScrollBar > .scrollbar--bar {
        background: $panel;
    }

    ScrollBar > .scrollbar--bar:hover {
        background: $foreground-muted;
    }
    """

    # Default bindings - will be overridden in __init__ with config values.
    # The footer is context-sensitive: app-level bindings keep every key
    # working globally but stay hidden, except the always-visible globals
    # (refresh/help/quit). The focused panel contributes its own visible
    # bindings (see compose), lazygit-style.
    BINDINGS = [
        Binding("n", "new_task", "New", show=False),
        Binding("y", "clone_task", "Clone", show=False),
        Binding("a", "add_repo", "Add Repo", show=False),
        Binding("d", "delete_task", "Delete", show=False),
        Binding("g", "open_lazygit", "Lazygit", show=False),
        Binding("h", "show_diff", "Diff", show=False),
        Binding("e", "open_editor", "Editor", show=False),
        Binding("o", "open_folder", "Open", show=False),
        Binding("c", "open_claude_resume", "Claude", show=False),
        Binding("p", "push_all", "Push", show=False),
        Binding("t", "cycle_theme", "Theme"),
        Binding("r", "refresh", "Refresh"),
        Binding("m", "toggle_messages", "Messages", show=False),
        Binding("?", "help", "Help"),
        Binding("q", "quit", "Quit"),
        Binding("enter", "open_shell", "Shell", show=False),
        Binding("C", "open_claude_gui_code", "Claude GUI", show=False),
        Binding("P", "pull_all", "Pull All", show=False),
        Binding("S", "toggle_grouping", "Group", show=False),
        Binding("D", "delete_worktree", "Del WT", show=False),
        Binding("tab", "focus_next", "Next Panel", show=False),
        Binding("shift+tab", "focus_previous", "Prev Panel", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("s", "cycle_sort", "Sort", show=False),
    ]

    def __init__(self):
        # Load config before calling super().__init__() so we can set up bindings
        self.config = Config.load()
        self.config.ensure_dirs()

        # Apply the configured [git] timeout to network git operations
        GitOps.network_timeout = self.config.git_timeout

        # Build bindings from config
        self._custom_bindings = self._build_bindings_from_config()

        super().__init__()
        self.task_manager = TaskManager(self.config)
        self.current_task: Task | None = None
        self.current_worktree: Worktree | None = None
        self.current_status: GitStatus | None = None
        self._show_messages_panel: bool = False
        # Mirrors the worktree list's grouping mode for the panel title
        self._worktrees_grouped: bool = False
        # Used to preserve worktree selection during task list reload
        self._preserved_worktree_name: str | None = None
        # Claude session statuses: task_name -> status string
        self._claude_statuses: dict[str, str] = {}
        # Snapshot of last loaded task state, used to skip no-op UI reloads
        self._last_tasks_fingerprint: tuple | None = None

    def _build_bindings_from_config(self) -> list[Binding]:
        """Build app-level keybindings from config.

        Every key works globally regardless of focus, but only the global
        actions (refresh/help/quit) are shown in the footer; the focused
        panel contributes its own visible bindings (see compose).

        Returns:
            List of Binding objects with keys from config
        """
        kb = self.config.keybindings
        return [
            Binding(kb.get("new_task", "n"), "new_task", "New", show=False),
            Binding(kb.get("clone_task", "y"), "clone_task", "Clone", show=False),
            Binding(kb.get("add_repo", "a"), "add_repo", "Add Repo", show=False),
            Binding(kb.get("delete_task", "d"), "delete_task", "Delete", show=False),
            Binding(kb.get("open_lazygit", "g"), "open_lazygit", "Lazygit", show=False),
            Binding(kb.get("show_diff", "h"), "show_diff", "Diff", show=False),
            Binding(kb.get("open_editor", "e"), "open_editor", "Editor", show=False),
            Binding(kb.get("open_folder", "o"), "open_folder", "Open", show=False),
            Binding(kb.get("open_claude_resume", "c"), "open_claude_resume", "Claude", show=False),
            Binding(kb.get("push_all", "p"), "push_all", "Push", show=False),
            Binding(kb.get("cycle_theme", "t"), "cycle_theme", "Theme"),
            Binding(kb.get("refresh", "r"), "refresh", "Refresh"),
            Binding(kb.get("toggle_messages", "m"), "toggle_messages", "Messages", show=False),
            Binding(kb.get("help", "?"), "help", "Help"),
            Binding(kb.get("quit", "q"), "quit", "Quit"),
            Binding(kb.get("open_shell", "enter"), "open_shell", "Shell", show=False),
            Binding(
                kb.get("open_claude_gui_code", "C"),
                "open_claude_gui_code",
                "Claude GUI",
                show=False,
            ),
            Binding(kb.get("pull_all", "P"), "pull_all", "Pull All", show=False),
            Binding(kb.get("toggle_grouping", "S"), "toggle_grouping", "Group", show=False),
            Binding(kb.get("delete_worktree", "D"), "delete_worktree", "Del WT", show=False),
            Binding(kb.get("focus_next", "tab"), "focus_next", "Next Panel", show=False),
            Binding(
                kb.get("focus_previous", "shift+tab"), "focus_previous", "Prev Panel", show=False
            ),
            Binding(kb.get("cursor_down", "j"), "cursor_down", "Down", show=False),
            Binding(kb.get("cursor_up", "k"), "cursor_up", "Up", show=False),
            Binding(kb.get("cycle_sort", "s"), "cycle_sort", "Sort", show=False),
        ]

    @property
    def _binding_list(self) -> list[Binding]:
        """Override to use custom bindings from config."""
        return self._custom_bindings

    def compose(self) -> ComposeResult:
        """Compose the app layout."""
        kb = self.config.keybindings
        # Footer bindings shown only while the respective panel has focus.
        # The keys themselves also exist app-level (hidden) so they work
        # regardless of focus; these entries only add footer visibility.
        task_panel_bindings = [
            (kb.get("new_task", "n"), "new_task", "New"),
            (kb.get("clone_task", "y"), "clone_task", "Clone"),
            (kb.get("add_repo", "a"), "add_repo", "Add Repo"),
            (kb.get("delete_task", "d"), "delete_task", "Delete"),
            (kb.get("show_diff", "h"), "show_diff", "Diff"),
            (kb.get("open_claude_resume", "c"), "open_claude_resume", "Claude"),
            (kb.get("cycle_sort", "s"), "cycle_sort", "Sort"),
        ]
        worktree_panel_bindings = [
            (kb.get("open_lazygit", "g"), "open_lazygit", "Lazygit"),
            (kb.get("show_diff", "h"), "show_diff", "Diff"),
            (kb.get("open_editor", "e"), "open_editor", "Editor"),
            (kb.get("open_folder", "o"), "open_folder", "Open"),
            (kb.get("open_shell", "enter"), "open_shell", "Shell"),
            (kb.get("push_all", "p"), "push_all", "Push"),
            (kb.get("delete_worktree", "D"), "delete_worktree", "Del WT"),
        ]

        yield AppHeader()
        with Horizontal(id="main-container"):
            # Left column: Tasks (top) and Worktrees (bottom)
            with Vertical(id="left-column"):
                with Vertical(id="task-panel"):
                    with Horizontal(classes="panel-title-bar"):
                        yield Static(
                            self._panel_title(1, "Tasks", "by name ↑"),
                            classes="panel-title",
                            id="task-panel-title",
                        )
                        yield Static("", classes="panel-counter", id="task-panel-counter")
                    yield TaskList(id="task-list", context_bindings=task_panel_bindings)
                with Vertical(id="worktree-panel"):
                    with Horizontal(classes="panel-title-bar"):
                        yield Static(
                            self._panel_title(2, "Worktrees"),
                            classes="panel-title",
                            id="worktree-panel-title",
                        )
                        yield Static("", classes="panel-counter", id="worktree-panel-counter")
                    yield WorktreeList(id="worktree-list", context_bindings=worktree_panel_bindings)
            # Right column: Info/Status panel
            with Vertical(id="right-column"):
                with Vertical(id="status-panel"):
                    with Horizontal(classes="panel-title-bar"):
                        yield Static(
                            self._panel_title(3, "Info"),
                            classes="panel-title",
                            id="status-panel-title",
                        )
                        yield Static(
                            f"tasktree-manager {__version__.split('+')[0]}",
                            classes="panel-counter",
                            id="status-panel-counter",
                        )
                    yield StatusPanel(id="status-display")
                with Vertical(id="messages-panel"):
                    yield MessagesPanel(id="messages-display")
        yield Footer()

    @staticmethod
    def _panel_title(number: int, name: str, context: str | None = None) -> str:
        """Format a panel title: dim [n] number, bold name, dim context suffix."""
        title = f"[dim]\\[{number}][/dim] [b]{name}[/b]"
        if context:
            # Context is often a task/worktree name from the filesystem;
            # escape so brackets in a name cannot inject markup
            title += f"[dim] · {escape(context)}[/dim]"
        return title

    def _set_counter(self, counter_id: str, text: str) -> None:
        """Update a panel title-bar counter."""
        try:
            counter = self.query_one(f"#{counter_id}", Static)
        except Exception:
            return
        counter.update(text)

    def _set_info_title(self, context: str | None) -> None:
        """Update the Info panel title's context suffix."""
        try:
            title = self.query_one("#status-panel-title", Static)
        except Exception:
            return
        title.update(self._panel_title(3, "Info", context))

    def _update_worktree_panel_title(self) -> None:
        """Update the Worktrees panel title from current task and grouping."""
        try:
            title = self.query_one("#worktree-panel-title", Static)
        except Exception:
            return
        if self._worktrees_grouped:
            context = "grouped"
        else:
            context = self.current_task.name if self.current_task else None
        title.update(self._panel_title(2, "Worktrees", context))

    def _update_header_stats(self, tasks: list[Task]) -> None:
        """Refresh the header bar's task/dirty counts."""
        try:
            header = self.query_one(AppHeader)
        except Exception:
            return
        dirty_count = sum(1 for task in tasks if task.is_dirty)
        tasks_dir = str(self.config.tasks_dir)
        home = str(Path.home())
        if tasks_dir.startswith(home):
            tasks_dir = "~" + tasks_dir[len(home) :]
        header.update_stats(len(tasks), dirty_count, tasks_dir)

    def on_mount(self) -> None:
        """Handle app mount."""
        # Register the design-system themes (the five popular palettes
        # override Textual built-ins of the same name), then apply the
        # configured one
        for theme in ALL_THEMES:
            self.register_theme(theme)
        if self.config.theme:
            try:
                self.theme = self.config.theme
            except Exception:
                # Invalid theme name, use default
                pass
        self.query_one(AppHeader).set_theme(self.theme)

        # Check if configuration is valid
        if not self.config.is_configured():
            self._show_setup_wizard()
        else:
            self._load_tasks()
            # Focus the task list initially
            task_list = self.query_one("#task-list", TaskList)
            task_list.focus()

        # Poll Claude session status files every 5 seconds
        self.set_interval(5, self._poll_claude_statuses)

        # Periodic auto-refresh of git status
        if self.config.refresh_interval > 0:
            self.set_interval(self.config.refresh_interval, self._periodic_git_refresh)

    def watch_theme(self, theme: str) -> None:
        """Save theme to config and show it in the header when changed."""
        if hasattr(self, "config") and self.config.theme != theme:
            self.config.theme = theme
            self.config.save()
        try:
            self.query_one(AppHeader).set_theme(theme)
        except Exception:
            # Header not mounted yet during startup
            pass

    def action_cycle_theme(self) -> None:
        """Cycle through the design-system theme list."""
        try:
            index = THEME_CYCLE.index(self.theme)
        except ValueError:
            index = -1
        self.theme = THEME_CYCLE[(index + 1) % len(THEME_CYCLE)]

    def _show_setup_wizard(self) -> None:
        """Show setup wizard for first-time configuration."""

        def handle_setup(result):
            if result:
                repos_dir, tasks_dir = result
                # Update config
                self.config.repos_dir = repos_dir
                self.config.tasks_dir = tasks_dir
                self.config.save()
                self.config.ensure_dirs()

                # Reload task manager with new config
                self.task_manager = TaskManager(self.config)

                # Load tasks
                self._load_tasks()

                # Focus task list
                task_list = self.query_one("#task-list", TaskList)
                task_list.focus()

                self.notify("Configuration saved!")
            else:
                # User cancelled - exit app
                self.exit()

        self.push_screen(SetupModal(), handle_setup)

    def _load_tasks(
        self, select_task: str | None = None, select_worktree: str | None = None
    ) -> None:
        """Load tasks into the UI, then refresh git status in the background.

        Listing tasks is a fast directory walk, so it runs synchronously for
        an instantly responsive UI. Git status is one subprocess per worktree
        and can be slow, so it fills in asynchronously via the auto_refresh
        worker (dirty indicators and branches appear as the scan completes).

        Args:
            select_task: Task name to select instead of the current selection
            select_worktree: Worktree name to select instead of the current one
        """
        tasks = self.task_manager.list_tasks()
        self._apply_refreshed_tasks(
            tasks, force_ui=True, select_task=select_task, select_worktree=select_worktree
        )
        self._run_periodic_refresh(select_task=select_task, select_worktree=select_worktree)

    def _load_tasks_with_selection(self, task_name: str | None, worktree_name: str | None) -> None:
        """Load tasks and restore selection by explicit names.

        This is used after suspend/resume to restore exact selection state.
        """
        self._load_tasks(select_task=task_name, select_worktree=worktree_name)

    def _poll_claude_statuses(self) -> None:
        """Check .claude_status files and update task indicators."""
        try:
            task_list = self.query_one("#task-list", TaskList)
        except Exception:
            return

        statuses: dict[str, str] = {}
        for task in task_list.tasks:
            status_file = task.path / ".claude_status"
            if status_file.exists():
                try:
                    data = json.loads(status_file.read_text())
                    statuses[task.name] = data.get("status", "unknown")
                except (json.JSONDecodeError, OSError):
                    pass

        if statuses != self._claude_statuses:
            self._claude_statuses = statuses
            task_list.refresh_claude_indicators(statuses)

    def _periodic_git_refresh(self) -> None:
        """Trigger a background git status refresh."""
        self._run_periodic_refresh()

    @staticmethod
    def _tasks_fingerprint(tasks: list[Task]) -> tuple:
        """Cheap comparable snapshot of task/worktree state for change detection."""
        return tuple(
            (
                task.name,
                tuple((wt.name, wt.branch, wt.is_dirty, wt.changed_files) for wt in task.worktrees),
            )
            for task in tasks
        )

    @work(thread=True, exclusive=True, group="auto_refresh")
    def _run_periodic_refresh(
        self,
        force_ui: bool = False,
        select_task: str | None = None,
        select_worktree: str | None = None,
    ) -> None:
        """Refresh git status in a background thread, then update the UI.

        Args:
            force_ui: If True, reload the UI even when nothing changed
                (used by manual refresh)
            select_task: Task name to select instead of the current selection
            select_worktree: Worktree name to select instead of the current one
        """
        tasks = self.task_manager.list_tasks()
        all_worktrees = [wt for task in tasks for wt in task.worktrees]
        GitOps.update_all_worktree_statuses(all_worktrees)
        self.call_from_thread(
            self._apply_refreshed_tasks, tasks, force_ui, select_task, select_worktree
        )

    def _apply_refreshed_tasks(
        self,
        tasks: list[Task],
        force_ui: bool = False,
        select_task: str | None = None,
        select_worktree: str | None = None,
    ) -> None:
        """Apply a (re)loaded task list to the UI (runs on the main thread).

        The selection is read here, at apply time, so navigation that happened
        while a background scan was running is not reverted; select_task /
        select_worktree override it (used after suspend/resume and creation).
        When nothing changed since the last load, the UI reload is skipped
        entirely to avoid selection/status-panel flicker.
        """
        try:
            task_list = self.query_one("#task-list", TaskList)
            worktree_list = self.query_one("#worktree-list", WorktreeList)
            status_panel = self.query_one("#status-display", StatusPanel)
        except Exception:
            # Widgets not mounted (e.g. setup wizard is showing)
            return

        task_list.loading = False
        worktree_list.loading = False

        fingerprint = self._tasks_fingerprint(tasks)
        if not force_ui and fingerprint == self._last_tasks_fingerprint:
            return
        self._last_tasks_fingerprint = fingerprint
        self._update_header_stats(tasks)

        try:
            current_task_name = select_task or (
                self.current_task.name if self.current_task else None
            )
            current_worktree_name = select_worktree or (
                self.current_worktree.name if self.current_worktree else None
            )

            if current_worktree_name:
                self._preserved_worktree_name = current_worktree_name
            task_list.load_tasks(tasks, preserve_selection=current_task_name)

            if not tasks:
                # Last task disappeared - clear the dependent panels
                self.current_task = None
                self.current_worktree = None
                self.current_status = None
                worktree_list.clear_worktrees()
                status_panel.clear_status()
                self._set_counter("task-panel-counter", "")
                self._set_counter("worktree-panel-counter", "")
                return

            if current_task_name:
                for t in tasks:
                    if t.name == current_task_name:
                        self.current_task = t
                        worktree_list.load_worktrees(
                            t.worktrees, preserve_selection=current_worktree_name
                        )
                        break
        except Exception as e:
            # A worker error would exit the app; refresh glitches are not fatal
            self.log.error(f"Failed to apply refreshed tasks: {e}")

    def _run_external_command(
        self, cmd: list[str], cwd, name: str, install_hint: str | None = None
    ) -> bool:
        """Run external command with proper error handling.

        Args:
            cmd: Command and arguments to run
            cwd: Working directory for the command
            name: Human-readable name of the command (for error messages)
            install_hint: Optional hint for installing the command (e.g., "brew install lazygit")

        Returns:
            True if command ran successfully, False otherwise
        """
        hint = f" Install with: {install_hint}" if install_hint else ""
        try:
            subprocess.run(cmd, cwd=cwd)
            return True
        except FileNotFoundError:
            self.notify(f"{name} not found.{hint}", severity="error")
            return False
        except PermissionError:
            self.notify(f"Permission denied running {name}", severity="error")
            return False
        except Exception as e:
            self.notify(escape(f"Failed to run {name}: {e}"), severity="error")
            return False

    def on_descendant_focus(self, event) -> None:
        """Handle focus changes to update info panel mode."""
        try:
            status_panel = self.query_one("#status-display", StatusPanel)
        except Exception:
            return

        if isinstance(event.widget, TaskList):
            # Task list focused → show task changed files
            if self.current_task:
                self._set_info_title(self.current_task.name)
                status_panel.set_loading(True)
                self._update_task_summary(self.current_task)
        elif isinstance(event.widget, WorktreeList):
            # Worktree list focused → show worktree details
            if self.current_worktree:
                self._set_info_title(self.current_worktree.name)
            if self.current_worktree and self.current_status:
                status_panel.update_status(self.current_worktree, self.current_status)
            elif self.current_worktree:
                status_panel.set_loading(True)
                self._update_worktree_status(self.current_worktree)

    def on_task_list_task_highlighted(self, event: TaskList.TaskHighlighted) -> None:
        """Handle task highlight in task list."""
        self.current_task = event.task
        try:
            task_list = self.query_one("#task-list", TaskList)
            worktree_list = self.query_one("#worktree-list", WorktreeList)
            status_panel = self.query_one("#status-display", StatusPanel)
        except Exception:
            # Widgets not mounted yet during app startup
            return

        self._update_worktree_panel_title()
        if event.task and task_list.highlighted is not None:
            self._set_counter(
                "task-panel-counter", f"{task_list.highlighted + 1} of {len(task_list.tasks)}"
            )
        else:
            self._set_counter("task-panel-counter", "")
        if event.task:
            # Use preserved worktree name if set (during reload after lazygit/shell)
            preserved = self._preserved_worktree_name
            self._preserved_worktree_name = None  # Clear after use
            worktree_list.load_worktrees(event.task.worktrees, preserve_selection=preserved)

            # Show task summary if task list is focused
            if task_list.has_focus:
                self._set_info_title(event.task.name)
                status_panel.set_loading(True)
                self._update_task_summary(event.task)
        else:
            worktree_list.clear_worktrees()
            status_panel.clear_status()
            self._set_info_title(None)

    def on_worktree_list_worktree_highlighted(
        self, event: WorktreeList.WorktreeHighlighted
    ) -> None:
        """Handle worktree highlight in worktree list."""
        self.current_worktree = event.worktree
        try:
            status_panel = self.query_one("#status-display", StatusPanel)
        except Exception:
            # Widget not mounted yet during app startup
            return

        # Only update status panel if worktree list is focused
        worktree_list = self.query_one("#worktree-list", WorktreeList)
        if event.worktree:
            try:
                index = worktree_list.worktrees.index(event.worktree)
                self._set_counter(
                    "worktree-panel-counter",
                    f"{index + 1} of {len(worktree_list.worktrees)}",
                )
            except ValueError:
                self._set_counter("worktree-panel-counter", "")
            if worktree_list.has_focus:
                self._set_info_title(event.worktree.name)
                status_panel.set_loading(True)
                self._update_worktree_status(event.worktree)
            else:
                # Still fetch status in background for when user switches focus
                self._update_worktree_status(event.worktree)
        else:
            self.current_status = None
            self._set_counter("worktree-panel-counter", "")
            if worktree_list.has_focus:
                status_panel.clear_status()

    @work(thread=True, exclusive=True, group="status_update")
    def _update_worktree_status(self, worktree: Worktree) -> None:
        """Fetch git status in background thread."""
        status = GitOps.get_status(worktree)
        # Call back to main thread to update UI
        self.call_from_thread(self._apply_worktree_status, worktree, status)

    def _apply_worktree_status(self, worktree: Worktree, status: GitStatus) -> None:
        """Apply fetched status to the UI (called on main thread)."""
        # Only update if this worktree is still selected
        if self.current_worktree and self.current_worktree.path == worktree.path:
            self.current_status = status
            try:
                status_panel = self.query_one("#status-display", StatusPanel)
                # Only show worktree status if worktree list is focused
                worktree_list = self.query_one("#worktree-list", WorktreeList)
                if worktree_list.has_focus:
                    status_panel.update_status(worktree, status)
            except Exception:
                pass

    @work(thread=True, exclusive=True, group="task_summary_update")
    def _update_task_summary(self, task: Task) -> None:
        """Fetch git status for all dirty worktrees in background thread."""
        dirty_worktrees = [wt for wt in task.worktrees if wt.is_dirty]
        statuses = GitOps.get_statuses_parallel(dirty_worktrees)
        self.call_from_thread(self._apply_task_summary, task, statuses)

    def _apply_task_summary(self, task: Task, statuses: dict[str, GitStatus]) -> None:
        """Apply fetched task summary to the UI (called on main thread)."""
        # Only update if this task is still selected and task list is focused
        if self.current_task and self.current_task.name == task.name:
            try:
                status_panel = self.query_one("#status-display", StatusPanel)
                task_list = self.query_one("#task-list", TaskList)
                if task_list.has_focus:
                    status_panel.update_task_summary(task, statuses)
            except Exception:
                pass

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()

    def action_help(self) -> None:
        """Show help modal with current keybindings."""
        config_path = str(self.config.config_dir / "config.toml")
        self.push_screen(
            HelpModal(
                keybindings=self.config.keybindings,
                config_path=config_path,
            )
        )

    def action_new_task(self) -> None:
        """Create a new task."""
        available_repos = self.config.get_available_repos()
        if not available_repos:
            self.notify("No repositories found in REPOS_DIR", severity="warning")
            return

        def handle_result(result):
            if result:
                name, repos, base_branch = result
                self.query_one("#task-list", TaskList).loading = True
                self._create_task_worker(name, repos, base_branch, verb="created")

        self.push_screen(CreateTaskModal(available_repos), handle_result)

    @work(thread=True, group="task_mutation")
    def _create_task_worker(self, name: str, repos: list[str], base_branch: str, verb: str) -> None:
        """Create a task in a background thread.

        Creation fetches the base branch from origin for every repo, so it
        can block on the network for a long time - never run it on the UI
        thread.
        """
        error: str | None = None
        try:
            self.task_manager.create_task(name, repos, base_branch)
        except FileNotFoundError as e:
            error = f"Repository not found: {e}"
        except PermissionError:
            error = "Permission denied: check directory permissions"
        except ValueError as e:
            # ValueError from task_manager has good messages
            error = str(e)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
        self.call_from_thread(self._apply_create_task_result, name, len(repos), verb, error)

    def _apply_create_task_result(
        self, name: str, repo_count: int, verb: str, error: str | None
    ) -> None:
        """Report the create/clone outcome and reload (runs on the main thread)."""
        if error:
            self.notify(escape(f"Failed to create task: {error}"), severity="error")
            self._log_activity(f"Failed to create task: {error}", MessageLevel.ERROR, name)
            self._load_tasks()
        else:
            self.notify(escape(f"Created task: {name}"))
            self._log_activity(
                f"Task '{name}' {verb} with {repo_count} repo(s)", MessageLevel.SUCCESS, name
            )
            self._load_tasks(select_task=name)

    def action_clone_task(self) -> None:
        """Create a new task pre-populated with the current task's repos."""
        if not self.current_task:
            self.notify("No task selected", severity="warning")
            return

        available_repos = self.config.get_available_repos()
        if not available_repos:
            self.notify("No repositories found in REPOS_DIR", severity="warning")
            return

        source_repos = [wt.name for wt in self.current_task.worktrees]

        def handle_result(result):
            if result:
                name, repos, base_branch = result
                self.query_one("#task-list", TaskList).loading = True
                self._create_task_worker(name, repos, base_branch, verb="cloned")

        self.push_screen(
            CreateTaskModal(
                available_repos,
                initial_repos=source_repos,
                title=f"Clone Task: {self.current_task.name}",
            ),
            handle_result,
        )

    def action_add_repo(self) -> None:
        """Add repos to the current task."""
        if not self.current_task:
            self.notify("No task selected", severity="warning")
            return

        available_repos = self.task_manager.get_repos_not_in_task(self.current_task)
        if not available_repos:
            self.notify("All repositories already in task", severity="information")
            return

        def handle_result(result):
            if result and self.current_task:
                repos, base_branch = result
                self.query_one("#task-list", TaskList).loading = True
                self.query_one("#worktree-list", WorktreeList).loading = True
                self._add_repos_worker(self.current_task, repos, base_branch)

        self.push_screen(AddRepoModal(self.current_task.name, available_repos), handle_result)

    @work(thread=True, group="task_mutation")
    def _add_repos_worker(self, task: Task, repos: list[str], base_branch: str) -> None:
        """Add repos to a task in a background thread (fetches per repo)."""
        added: list[str] = []
        failed: list[tuple[str, str]] = []
        for repo in repos:
            try:
                self.task_manager.add_repo_to_task(task, repo, base_branch)
                added.append(repo)
            except Exception as e:
                failed.append((repo, str(e)))
        self.call_from_thread(self._apply_add_repos_result, task.name, added, failed)

    def _apply_add_repos_result(
        self, task_name: str, added: list[str], failed: list[tuple[str, str]]
    ) -> None:
        """Report add-repo outcomes and reload (runs on the main thread)."""
        if added:
            self.notify(f"Added {len(added)} repo(s) to task")
            self._log_activity(
                f"Added {len(added)} repo(s) to task '{task_name}'",
                MessageLevel.SUCCESS,
                task_name,
            )
        for repo, err in failed:
            self.notify(escape(f"Failed to add {repo}: {err}"), severity="error")
            self._log_activity(f"Failed to add {repo}: {err}", MessageLevel.ERROR, task_name)
        self._load_tasks()

    def action_delete_task(self) -> None:
        """Delete/finish the current task with safety checks."""
        if not self.current_task:
            self.notify("No task selected", severity="warning")
            return

        # Safety checks hit the network (git fetch per worktree), so run them
        # in a background thread and show the dialog when they complete
        self.notify(escape(f"Checking '{self.current_task.name}' before delete..."))
        self._check_task_safety_worker(self.current_task)

    @work(thread=True, exclusive=True, group="safety_check")
    def _check_task_safety_worker(self, task: Task) -> None:
        """Run task safety checks in a background thread."""
        safety_report = self.task_manager.check_task_safety(task)
        self.call_from_thread(self._show_delete_task_dialog, task, safety_report)

    def _show_delete_task_dialog(self, task: Task, safety_report: TaskSafetyReport) -> None:
        """Show the appropriate delete dialog for the safety report."""
        if safety_report.is_safe():
            self._confirm_and_finish_task(
                task, escape(f"Delete task '{task.name}' and all its worktrees?")
            )
        else:
            self.push_screen(
                SafeDeleteModal(task.name, safety_report),
                lambda action: self._handle_safe_delete_action(task, safety_report, action),
            )

    def _confirm_and_finish_task(
        self, task: Task, message: str, title: str = "Delete Task", force: bool = False
    ) -> None:
        """Push a confirmation modal and delete the task if confirmed."""

        def handle_confirm(confirmed):
            if confirmed:
                self._finish_task(task, force=force)

        self.push_screen(ConfirmModal(title, message), handle_confirm)

    def _finish_task(self, task: Task, force: bool = False) -> None:
        """Kick off task deletion in a background thread."""
        try:
            self.query_one("#task-list", TaskList).loading = True
        except Exception:
            pass
        self._finish_task_worker(task, force)

    @work(thread=True, group="task_mutation")
    def _finish_task_worker(self, task: Task, force: bool) -> None:
        """Delete the task in a background thread.

        Removing worktrees runs git per repo and rmtree over trees that can
        be huge (node_modules etc.) - never block the UI thread on it.
        """
        error: str | None = None
        try:
            self.task_manager.finish_task(task)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
        self.call_from_thread(self._apply_finish_task_result, task.name, force, error)

    def _apply_finish_task_result(self, task_name: str, force: bool, error: str | None) -> None:
        """Report the delete outcome and reload (runs on the main thread)."""
        if error:
            self.notify(escape(f"Failed to delete task: {error}"), severity="error")
            self._log_activity(f"Failed to delete task: {error}", MessageLevel.ERROR, task_name)
        else:
            self.notify(escape(f"Deleted task: {task_name}"))
            suffix = " (force)" if force else ""
            self._log_activity(
                f"Task '{task_name}' deleted{suffix}", MessageLevel.SUCCESS, task_name
            )
        self._load_tasks()

    def _handle_safe_delete_action(
        self, task: Task, safety_report: TaskSafetyReport, action: str | None
    ) -> None:
        """Handle the user's choice from the safe-delete modal."""
        if action == "push":
            self.notify(escape(f"Pushing all branches for {task.name}..."))
            self._push_branches_for_delete_worker(task)
        elif action == "lazygit":
            # Open lazygit in the first problematic worktree, then re-run checks
            self._open_lazygit_for_task(task, safety_report)
            self.action_delete_task()
        elif action == "force":
            self._confirm_and_finish_task(
                task,
                escape(f"Really delete task '{task.name}'?") + "\n\nYou may lose unpushed work!",
                title="Force Delete",
                force=True,
            )
        # else: cancelled, do nothing

    @work(thread=True, exclusive=True, group="safety_check")
    def _push_branches_for_delete_worker(self, task: Task) -> None:
        """Push all branches and re-run safety checks in a background thread."""
        success_repos, failed_repos = self.task_manager.push_all_branches(task)
        new_report = self.task_manager.check_task_safety(task)
        self.call_from_thread(
            self._apply_delete_push_results, task, success_repos, failed_repos, new_report
        )

    def _apply_delete_push_results(
        self,
        task: Task,
        success_repos: list[str],
        failed_repos: list[str],
        new_report: TaskSafetyReport,
    ) -> None:
        """Continue the delete flow after pushing branches (main thread)."""
        if failed_repos:
            self.push_screen(
                PushResultModal(success_repos, failed_repos),
                lambda _: self._continue_delete_after_push(task, new_report),
            )
        else:
            self.notify(f"Pushed {len(success_repos)} branch(es) successfully")
            self._continue_delete_after_push(task, new_report)

    def _continue_delete_after_push(self, task: Task, report: TaskSafetyReport) -> None:
        """Ask to delete if the task became safe, otherwise show the issues again."""
        if report.is_safe():
            self._confirm_and_finish_task(task, escape(f"Delete task '{task.name}'?"))
        else:
            self.push_screen(
                SafeDeleteModal(task.name, report),
                lambda action: self._handle_safe_delete_action(task, report, action),
            )

    def action_delete_worktree(self) -> None:
        """Delete a single worktree from the current task."""
        if not self.current_task:
            self.notify("No task selected", severity="warning")
            return
        if not self.current_worktree:
            self.notify("No worktree selected", severity="warning")
            return

        task = self.current_task
        worktree = self.current_worktree
        message = escape(f"Delete worktree '{worktree.name}' from task '{task.name}'?")

        def handle_confirm(confirmed):
            if confirmed:
                self.query_one("#worktree-list", WorktreeList).loading = True
                self._remove_worktree_worker(task, worktree)

        self.push_screen(ConfirmModal("Delete Worktree", message), handle_confirm)

    @work(thread=True, group="task_mutation")
    def _remove_worktree_worker(self, task: Task, worktree: Worktree) -> None:
        """Remove a single worktree in a background thread (git + rmtree)."""
        error: str | None = None
        try:
            self.task_manager.remove_worktree_from_task(task, worktree)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
        self.call_from_thread(self._apply_remove_worktree_result, task.name, worktree.name, error)

    def _apply_remove_worktree_result(
        self, task_name: str, worktree_name: str, error: str | None
    ) -> None:
        """Report the worktree removal outcome and reload (main thread)."""
        if error:
            self.notify(escape(f"Failed to delete worktree: {error}"), severity="error")
            self._log_activity(
                f"Failed to delete worktree '{worktree_name}': {error}",
                MessageLevel.ERROR,
                task_name,
            )
        else:
            self.notify(escape(f"Deleted worktree: {worktree_name}"))
            self._log_activity(
                f"Worktree '{worktree_name}' deleted from '{task_name}'",
                MessageLevel.SUCCESS,
                task_name,
            )
        self._load_tasks()

    def _open_lazygit_for_task(self, task: Task, safety_report: TaskSafetyReport) -> None:
        """Open lazygit in the first worktree with issues.

        Args:
            task: The task whose worktrees to check
            safety_report: Pre-computed safety report (computing one here
                would block the UI thread on network git)
        """
        # Save selection state BEFORE suspend (as local variables)
        saved_task_name = self.current_task.name if self.current_task else None
        saved_worktree_name = self.current_worktree.name if self.current_worktree else None

        # Find first worktree with any issues
        first_issue_worktree = None
        if safety_report.unpushed:
            first_issue_worktree = safety_report.unpushed[0].worktree_path
        elif safety_report.unmerged:
            first_issue_worktree = safety_report.unmerged[0].worktree_path
        elif safety_report.dirty:
            first_issue_worktree = safety_report.dirty[0].worktree_path

        if first_issue_worktree and first_issue_worktree.exists():
            # Suspend app and run lazygit
            with self.suspend():
                self._run_external_command(
                    [self.config.lazygit_path],
                    cwd=first_issue_worktree,
                    name="lazygit",
                    install_hint="brew install lazygit",
                )

            # Refresh status after lazygit exits, restoring saved selection
            self._load_tasks_with_selection(saved_task_name, saved_worktree_name)
            # Restore focus to worktree list
            self.query_one("#worktree-list", WorktreeList).focus()
        else:
            self.notify("No problematic worktree found", severity="warning")

    def action_open_lazygit(self) -> None:
        """Open lazygit in the current worktree."""
        if not self.current_worktree:
            self.notify("No worktree selected", severity="warning")
            return

        worktree_path = self.current_worktree.path
        if not worktree_path.exists():
            self.notify("Worktree directory not found", severity="error")
            return

        # Save selection state BEFORE suspend (as local variables)
        saved_task_name = self.current_task.name if self.current_task else None
        saved_worktree_name = self.current_worktree.name

        self.notify("Opening lazygit...")

        # Suspend app and run lazygit
        with self.suspend():
            self._run_external_command(
                [self.config.lazygit_path],
                cwd=worktree_path,
                name="lazygit",
                install_hint="brew install lazygit",
            )

        # Refresh status after lazygit exits, restoring saved selection
        self._load_tasks_with_selection(saved_task_name, saved_worktree_name)
        # Restore focus to worktree list
        self.query_one("#worktree-list", WorktreeList).focus()

    def action_show_diff(self) -> None:
        """Open the hunk diff viewer, scoped by which panel is focused.

        From the task panel, shows a combined diff across all the task's repos.
        From the worktree panel, shows the diff for the selected worktree only.
        """
        focused = self.focused
        if isinstance(focused, TaskList):
            self._show_task_diff()
        elif isinstance(focused, WorktreeList):
            self._show_worktree_diff()
        else:
            self.notify("Select a task or worktree first", severity="warning")

    def _show_worktree_diff(self) -> None:
        """Open hunk on the selected worktree's working-tree changes."""
        if not self.current_worktree:
            self.notify("No worktree selected", severity="warning")
            return

        worktree_path = self.current_worktree.path
        if not worktree_path.exists():
            self.notify("Worktree directory not found", severity="error")
            return

        # Save selection state BEFORE suspend (as local variables)
        saved_task_name = self.current_task.name if self.current_task else None
        saved_worktree_name = self.current_worktree.name

        self.notify("Opening hunk...")

        # Suspend app and run hunk on this worktree's changes
        with self.suspend():
            self._run_external_command(
                [self.config.hunk_path, "diff"],
                cwd=worktree_path,
                name="hunk",
                install_hint="brew install hunk",
            )

        # Refresh status after hunk exits, restoring saved selection
        self._load_tasks_with_selection(saved_task_name, saved_worktree_name)
        # Restore focus to worktree list
        self.query_one("#worktree-list", WorktreeList).focus()

    def _show_task_diff(self) -> None:
        """Open hunk on a combined diff across all of the task's repos."""
        import os
        import tempfile

        if not self.current_task:
            self.notify("No task selected", severity="warning")
            return

        task = self.current_task

        # Building the diff runs local git commands only (no network), so a
        # brief synchronous call before suspend is fine. The fresh git read
        # also makes the "no changes" check accurate regardless of stale UI.
        diff = GitOps.build_task_diff(task)
        if not diff.strip():
            self.notify("No changes to show", severity="information")
            return

        # Save selection state BEFORE suspend (as local variables)
        saved_task_name = task.name
        saved_worktree_name = self.current_worktree.name if self.current_worktree else None

        # hunk reads the combined patch from a file, so keyboard input stays on
        # the terminal (a stdin pipe would fight the interactive TUI for it).
        with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False, encoding="utf-8") as f:
            f.write(diff)
            patch_path = f.name

        self.notify("Opening hunk...")

        try:
            with self.suspend():
                self._run_external_command(
                    [self.config.hunk_path, "patch", patch_path],
                    cwd=task.path,
                    name="hunk",
                    install_hint="brew install hunk",
                )
        finally:
            try:
                os.unlink(patch_path)
            except OSError:
                pass

        # Refresh status after hunk exits, restoring saved selection
        self._load_tasks_with_selection(saved_task_name, saved_worktree_name)
        # Restore focus to task list
        self.query_one("#task-list", TaskList).focus()

    def action_open_shell(self) -> None:
        """Open a shell in the current worktree."""
        if not self.current_worktree:
            self.notify("No worktree selected", severity="warning")
            return

        worktree_path = self.current_worktree.path
        if not worktree_path.exists():
            self.notify("Worktree directory not found", severity="error")
            return

        # Save selection state BEFORE suspend (as local variables)
        saved_task_name = self.current_task.name if self.current_task else None
        saved_worktree_name = self.current_worktree.name

        # Get shell from config
        shell = self.config.get_shell()

        self.notify("Opening shell...")

        # Suspend app and open shell
        with self.suspend():
            self._run_external_command([shell], cwd=worktree_path, name="shell")

        # Refresh status after shell exits, restoring saved selection
        self._load_tasks_with_selection(saved_task_name, saved_worktree_name)
        # Restore focus to worktree list
        self.query_one("#worktree-list", WorktreeList).focus()

    def action_open_editor(self) -> None:
        """Open editor in the current folder (task or worktree based on focus)."""
        focused = self.focused

        # Determine folder based on focus (like open_folder does)
        folder_path: Path | None = None
        if isinstance(focused, TaskList) and self.current_task:
            folder_path = self.current_task.path
        elif isinstance(focused, WorktreeList) and self.current_worktree:
            folder_path = self.current_worktree.path
        else:
            self.notify("No folder selected", severity="warning")
            return

        if not folder_path.exists():
            self.notify("Folder not found", severity="error")
            return

        # Save selection state BEFORE suspend
        saved_task_name = self.current_task.name if self.current_task else None
        saved_worktree_name = self.current_worktree.name if self.current_worktree else None

        editor = self.config.get_editor()
        self.notify(escape(f"Opening {editor}..."))

        # Suspend app and run editor with "." to open directory
        with self.suspend():
            self._run_external_command([editor, "."], cwd=folder_path, name="editor")

        # Refresh status after editor exits, restoring saved selection
        self._load_tasks_with_selection(saved_task_name, saved_worktree_name)
        # Restore focus to the panel that was focused
        if isinstance(focused, TaskList):
            self.query_one("#task-list", TaskList).focus()
        else:
            self.query_one("#worktree-list", WorktreeList).focus()

    def _prepare_claude_session(self, task_path: Path) -> None:
        """Refresh CLAUDE.md files, worktree settings, and hooks before launching Claude."""
        fresh_task = self.task_manager.get_task(self.current_task.name)
        if fresh_task:
            self.task_manager.ensure_claude_md_files(fresh_task)
            self.task_manager.ensure_worktree_settings(fresh_task)
        ensure_claude_hooks(task_path, self.config.claude_memory_dir)

    def action_open_claude_resume(self) -> None:
        """Open Claude Code in a new Ghostty tab.

        Resumes an existing session for the task folder if one exists,
        otherwise starts a fresh session.
        """
        if not self.current_task:
            self.notify("No task selected", severity="warning")
            return

        task_path = self.current_task.path
        if not task_path.exists():
            self.notify("Task directory not found", severity="error")
            return

        self._prepare_claude_session(task_path)
        if has_claude_session(task_path):
            self._open_ghostty_tab(task_path, command=f"{self.config.claude_path} -r")
            self.notify("Opened Claude Code in new tab (resume)")
        else:
            self._open_ghostty_tab(task_path, command=self.config.claude_path)
            self.notify("Opened new Claude Code session in new tab")

    def action_open_claude_gui_code(self) -> None:
        """Open Claude desktop app on the Code page in the current task folder."""
        from urllib.parse import quote

        if not self.current_task:
            self.notify("No task selected", severity="warning")
            return

        task_path = self.current_task.path
        if not task_path.exists():
            self.notify("Task directory not found", severity="error")
            return

        self._prepare_claude_session(task_path)
        encoded_path = quote(str(task_path), safe="")
        url = f"claude://code/new?folder={encoded_path}"
        try:
            subprocess.run(["open", url], check=False)
            self.notify("Opened Claude desktop on Code page")
        except FileNotFoundError:
            self.notify("'open' command not found (macOS only)", severity="error")
        except Exception as e:
            self.notify(escape(f"Failed to open Claude desktop: {e}"), severity="error")

    def action_open_folder(self) -> None:
        """Open current folder in a new terminal tab."""
        focused = self.focused

        # Determine which folder to open based on focus
        folder_path: Path | None = None
        if isinstance(focused, TaskList) and self.current_task:
            folder_path = self.current_task.path
        elif isinstance(focused, WorktreeList) and self.current_worktree:
            folder_path = self.current_worktree.path
        else:
            self.notify("No folder selected", severity="warning")
            return

        if not folder_path.exists():
            self.notify("Folder not found", severity="error")
            return

        # Open in new terminal tab
        self._open_ghostty_tab(folder_path)

    def _open_ghostty_tab(self, path, command: str | None = None) -> None:
        """Open a new terminal tab at the given path, optionally running a command.

        NOTE: This implementation is specific to the Ghostty terminal emulator
        on macOS, using AppleScript. It will silently fail on other terminals.

        Args:
            path: Directory to cd into in the new tab
            command: Optional command to run after cd (e.g., "claude -r")
        """
        safe_path = str(path).replace("'", "'\\''")
        if command:
            shell_cmd = f"cd '{safe_path}' && clear && {command}"
        else:
            shell_cmd = f"cd '{safe_path}' && clear"
        self._open_ghostty_tab_worker(shell_cmd)

    @work(thread=True, group="ghostty_tab")
    def _open_ghostty_tab_worker(self, shell_cmd: str) -> None:
        """Drive Ghostty via clipboard paste in a background thread.

        The command is delivered via clipboard paste rather than typed
        keystrokes: tasktree-manager itself runs inside Ghostty, so typed
        keystrokes can arrive before focus transitions to the new tab and end
        up triggering Textual bindings (e.g. the 'D' in '/Documents/' would
        fire delete_worktree). Cmd+T and Cmd+V are caught by Ghostty's NSMenu
        before reaching the focused child app, so they cannot leak as
        bindings. The scripted delays are why this runs off the UI thread.
        """
        prev_clipboard = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
        subprocess.run(["pbcopy"], input=shell_cmd, text=True)
        # Keystrokes always go to the frontmost app, so send them only if
        # Ghostty actually took focus - otherwise they would land in (and
        # possibly execute in) whatever application is in front.
        script = """
        tell application "Ghostty" to activate
        delay 0.1
        tell application "System Events"
            if frontmost of process "Ghostty" then
                keystroke "t" using command down
                delay 0.3
                keystroke "v" using command down
                delay 0.05
                key code 36
            else
                return "not-frontmost"
            end if
        end tell
        """
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if "not-frontmost" in result.stdout:
            # Leave the command in the clipboard so the user can paste it
            self.call_from_thread(
                self.notify,
                "Ghostty did not take focus - command left in clipboard, paste to run",
                severity="warning",
            )
            return
        # Give the paste time to complete, then restore the user's previous
        # clipboard - but only if it still holds our command (the user may
        # have copied something else in the meantime).
        time.sleep(0.6)
        current = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
        if current == shell_cmd:
            subprocess.run(["pbcopy"], input=prev_clipboard, text=True)

    def action_push_all(self) -> None:
        """Push all worktrees in the current task."""
        if not self.current_task:
            self.notify("No task selected", severity="warning")
            return

        worktree_list = self.query_one("#worktree-list", WorktreeList)
        worktree_list.loading = True
        self.notify(escape(f"Pushing all worktrees in {self.current_task.name}..."))
        self._push_all_worker(self.current_task)

    @work(thread=True, exclusive=True, group="push_pull")
    def _push_all_worker(self, task: Task) -> None:
        """Push all worktrees in a background thread."""
        try:
            results = GitOps.push_all_parallel(task)
        except Exception as e:
            results = [(task.name, False, f"{type(e).__name__}: {e}")]
        self.call_from_thread(self._apply_push_pull_results, "Push", task.name, results)

    def action_pull_all(self) -> None:
        """Pull all worktrees in the current task."""
        if not self.current_task:
            self.notify("No task selected", severity="warning")
            return

        worktree_list = self.query_one("#worktree-list", WorktreeList)
        worktree_list.loading = True
        self.notify(escape(f"Pulling all worktrees in {self.current_task.name}..."))
        self._pull_all_worker(self.current_task)

    @work(thread=True, exclusive=True, group="push_pull")
    def _pull_all_worker(self, task: Task) -> None:
        """Pull all worktrees in a background thread."""
        try:
            results = GitOps.pull_all_parallel(task)
        except Exception as e:
            results = [(task.name, False, f"{type(e).__name__}: {e}")]
        self.call_from_thread(self._apply_push_pull_results, "Pull", task.name, results)

    def _apply_push_pull_results(
        self, verb: str, task_name: str, results: list[tuple[str, bool, str]]
    ) -> None:
        """Report push/pull results and refresh (runs on the main thread)."""
        try:
            worktree_list = self.query_one("#worktree-list", WorktreeList)
            worktree_list.loading = False
        except Exception:
            return

        success_count = sum(1 for _, success, _ in results if success)
        fail_count = len(results) - success_count
        past = f"{verb}ed"

        if fail_count == 0:
            self.notify(f"{past} {success_count} worktree(s) successfully")
            self._log_activity(
                f"{past} {success_count} worktree(s) for '{task_name}'",
                MessageLevel.SUCCESS,
                task_name,
            )
        else:
            self.notify(f"{past} {success_count}, failed {fail_count}", severity="warning")
            self._log_activity(
                f"{verb}: {success_count} succeeded, {fail_count} failed for '{task_name}'",
                MessageLevel.WARNING,
                task_name,
            )

        self._run_periodic_refresh(force_ui=True)

    def action_refresh(self) -> None:
        """Refresh all status in the background."""
        self.notify("Refreshing...")
        self._run_periodic_refresh(force_ui=True)

    def action_toggle_messages(self) -> None:
        """Toggle between status and messages panel."""
        self._show_messages_panel = not self._show_messages_panel

        status_panel = self.query_one("#status-panel")
        messages_panel = self.query_one("#messages-panel")

        if self._show_messages_panel:
            status_panel.add_class("-hidden")
            messages_panel.add_class("-visible")
        else:
            status_panel.remove_class("-hidden")
            messages_panel.remove_class("-visible")

    def _log_activity(
        self, message: str, level: MessageLevel, task_name: str | None = None
    ) -> None:
        """Log an activity message to the messages panel.

        Args:
            message: The message to log
            level: Message severity level
            task_name: Optional associated task name
        """
        messages_panel = self.query_one("#messages-display", MessagesPanel)
        messages_panel.add_message(message, level, task_name)

    def action_cursor_down(self) -> None:
        """Move cursor down in the focused list."""
        focused = self.focused
        if isinstance(focused, (TaskList, WorktreeList)):
            focused.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in the focused list."""
        focused = self.focused
        if isinstance(focused, (TaskList, WorktreeList)):
            focused.action_cursor_up()

    def action_cycle_sort(self) -> None:
        """Cycle through task sort modes."""
        task_list = self.query_one("#task-list", TaskList)
        task_list.cycle_sort_mode()

    def on_task_list_sort_mode_changed(self, event: TaskList.SortModeChanged) -> None:
        """Handle sort mode change in task list."""
        title = self.query_one("#task-panel-title", Static)
        title.update(self._panel_title(1, "Tasks", event.label))

    def action_toggle_grouping(self) -> None:
        """Toggle worktree grouping mode."""
        worktree_list = self.query_one("#worktree-list", WorktreeList)
        worktree_list.toggle_grouping()

    def on_worktree_list_grouping_changed(self, event: WorktreeList.GroupingChanged) -> None:
        """Handle grouping mode change in worktree list."""
        self._worktrees_grouped = event.enabled
        self._update_worktree_panel_title()


def main():
    """Entry point for the tasktree-manager application."""
    app = TaskTreeApp()
    app.run()


if __name__ == "__main__":
    main()
