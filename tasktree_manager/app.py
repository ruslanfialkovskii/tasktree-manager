"""Main application for tasktree-manager."""

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from rich.markup import escape
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Static
from textual.worker import get_current_worker

from . import __version__
from .commands import TaskTreeCommands
from .services.agent_sessions import AgentSession, list_agent_sessions, map_sessions_to_worktrees
from .services.claude_bg import (
    BackgroundError,
    attach_command,
    background_sessions,
    busy,
    end_sessions,
    folder_session,
    foreground_session,
    launch_env,
    start_background,
)
from .services.claude_hooks import ensure_claude_hooks, has_claude_session
from .services.claude_sessions import (
    ClaudeRecap,
    latest_session,
    read_claude_recap,
    transcript_key,
)
from .services.config import Config, ConfigError
from .services.forge import Forge, ForgeStatus, get_forge_status
from .services.git_ops import GitOps
from .services.models import EPIC_KIND, ArchiveResult, GitStatus, Task, TaskSafetyReport, Worktree
from .services.task_manager import ARCHIVE_NOTES_SHOWN, TaskManager
from .themes import ALL_THEMES, THEME_CYCLE
from .widgets.app_header import AppHeader
from .widgets.create_modal import (
    AddRepoModal,
    ConfirmModal,
    CreateTaskModal,
    DispatchAgentModal,
    EpicPickerModal,
    HelpModal,
    NewEpicModal,
    PushResultModal,
    RenameTaskModal,
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
        Binding("E", "set_epic", "Epic", show=False),
        Binding("g", "open_lazygit", "Lazygit", show=False),
        Binding("h", "show_diff", "Diff", show=False),
        Binding("e", "open_editor", "Editor", show=False),
        Binding("o", "open_folder", "Open", show=False),
        Binding("c", "open_claude_resume", "Claude", show=False),
        Binding("x", "close_claude_tab", "Close Tab", show=False),
        Binding("p", "push_all", "Push", show=False),
        Binding("t", "cycle_theme", "Theme"),
        Binding("r", "refresh", "Refresh"),
        Binding("m", "toggle_messages", "Messages", show=False),
        Binding("?", "help", "Help"),
        Binding("q", "quit", "Quit"),
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
        Forge.configure(self.config)

        # Build bindings from config
        self._custom_bindings = self._build_bindings_from_config()

        super().__init__()
        self._install_custom_bindings()
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
        # Transcript identity (path, mtime, size) behind the recap shown in
        # the Info panel; None until the highlighted task has been scanned
        self._recap_key: tuple[Path, int, int] | None = None
        # Agent session states from `claude agents --json`: worktree path -> state
        self._agent_sessions: dict[str, str] = {}
        # Forge MR/CI statuses: worktree path -> ForgeStatus
        self._forge_statuses: dict[str, ForgeStatus] = {}
        # Agent poll auto-disable after consecutive failures
        self._agent_poll_failures: int = 0
        self._agent_poll_disabled: bool = False
        # Snapshot of last loaded task state, used to skip no-op UI reloads
        self._last_tasks_fingerprint: tuple | None = None
        # Serializes the Ghostty clipboard/keystroke sequence across workers
        self._ghostty_lock = threading.Lock()
        # Serializes the zellij tab lookup and open across workers
        self._zellij_lock = threading.Lock()
        # Two quick `c` presses must not start two background sessions
        self._claude_bg_lock = threading.Lock()
        # App-lifetime pool for forge lookups (a fresh executor per poll
        # would rebuild threads every tick)
        self._forge_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="forge")

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
            Binding(kb.get("rename_task", "R"), "rename_task", "Rename", show=False),
            Binding(kb.get("set_epic", "E"), "set_epic", "Epic", show=False),
            Binding(kb.get("open_lazygit", "g"), "open_lazygit", "Lazygit", show=False),
            Binding(kb.get("show_diff", "h"), "show_diff", "Diff", show=False),
            Binding(kb.get("open_editor", "e"), "open_editor", "Editor", show=False),
            Binding(kb.get("open_folder", "o"), "open_folder", "Open", show=False),
            Binding(kb.get("open_claude_resume", "c"), "open_claude_resume", "Claude", show=False),
            Binding(kb.get("close_claude_tab", "x"), "close_claude_tab", "Close Tab", show=False),
            Binding(kb.get("dispatch_agent", "b"), "dispatch_agent", "Agent", show=False),
            Binding(kb.get("push_all", "p"), "push_all", "Push", show=False),
            Binding(kb.get("cycle_theme", "t"), "cycle_theme", "Theme"),
            Binding(kb.get("refresh", "r"), "refresh", "Refresh"),
            Binding(kb.get("toggle_messages", "m"), "toggle_messages", "Messages", show=False),
            Binding(kb.get("help", "?"), "help", "Help"),
            Binding(kb.get("quit", "q"), "quit", "Quit"),
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

    def _install_custom_bindings(self) -> None:
        """Replace the class-level BINDINGS with the config-driven set.

        Textual copies the class BINDINGS into ``self._bindings`` during
        ``super().__init__()``; the instance map is what key dispatch and the
        footer consult, so the configured keys have to be installed there.
        Default keys are dropped first so a remapped action does not keep
        responding to its old key as well. App-inherited bindings (ctrl+q,
        ctrl+c, ctrl+p) stay untouched.
        """
        for binding in self.BINDINGS:
            self._bindings.key_to_bindings.pop(binding.key, None)
        for binding in self._custom_bindings:
            self._bindings.key_to_bindings.pop(binding.key, None)
        for binding in self._custom_bindings:
            self._bindings.bind(
                binding.key,
                binding.action,
                binding.description,
                show=binding.show,
                key_display=binding.key_display,
                priority=binding.priority,
            )

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
            (kb.get("rename_task", "R"), "rename_task", "Rename"),
            (kb.get("set_epic", "E"), "set_epic", "Epic"),
            (kb.get("show_diff", "h"), "show_diff", "Diff"),
            (kb.get("open_claude_resume", "c"), "open_claude_resume", "Claude"),
            (kb.get("close_claude_tab", "x"), "close_claude_tab", "Close Tab"),
            (kb.get("cycle_sort", "s"), "cycle_sort", "Sort"),
        ]
        worktree_panel_bindings = [
            (kb.get("open_lazygit", "g"), "open_lazygit", "Lazygit"),
            (kb.get("show_diff", "h"), "show_diff", "Diff"),
            (kb.get("open_editor", "e"), "open_editor", "Editor"),
            (kb.get("open_folder", "o"), "open_folder", "Open"),
            (kb.get("dispatch_agent", "b"), "dispatch_agent", "Agent"),
            (kb.get("open_claude_resume", "c"), "open_claude_resume", "Claude"),
            (kb.get("close_claude_tab", "x"), "close_claude_tab", "Close Tab"),
            (kb.get("push_all", "p"), "push_all", "Push"),
            (kb.get("delete_worktree", "D"), "delete_worktree", "Del WT"),
        ]

        # Every key a configured action uses ("s,space" binds two keys)
        claimed_keys = {key.strip() for keys in kb.values() for key in keys.split(",")}

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
                    yield TaskList(
                        id="task-list",
                        context_bindings=task_panel_bindings,
                        # A fold key bound to any action in config stays that action
                        fold_keys=tuple(k for k in ("enter", "space") if k not in claimed_keys),
                    )
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

        # Poll `claude agents --json` for per-worktree session badges; fire
        # once right away so badges appear without waiting a full interval
        if self.config.agent_poll_interval > 0:
            self.set_interval(self.config.agent_poll_interval, self._poll_agent_sessions_tick)
            self._poll_agent_sessions_tick()

        # Poll forge (glab/gh) MR/CI state for the current task's worktrees;
        # task highlighting also triggers this, so no immediate fire needed
        if self.config.forge_poll_interval > 0 and self.config.forge_enabled:
            self.set_interval(self.config.forge_poll_interval, self._poll_forge_tick)

    def watch_theme(self, theme: str) -> None:
        """Save theme to config and show it in the header when changed."""
        if hasattr(self, "config") and self.config.theme != theme:
            self.config.theme = theme
            try:
                self.config.save()
            except OSError as e:
                # A read-only (dotfile-managed) config must not crash the
                # app on a theme switch; the theme still applies this session
                self.notify(escape(f"Could not save config: {e}"), severity="warning")
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
                # Update config (and persist even when the env overrode them)
                self.config.set_persistent("repos_dir", repos_dir)
                self.config.set_persistent("tasks_dir", tasks_dir)
                # Create the directories BEFORE saving: a tasks path that
                # cannot be created must not be persisted, or every later
                # launch would crash in ensure_dirs() with no way back here
                try:
                    self.config.ensure_dirs()
                    self.config.save()
                except OSError as e:
                    self.push_screen(
                        SetupModal(error_message=escape(f"Could not set up directories: {e}")),
                        handle_setup,
                    )
                    return

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
        self._carry_over_statuses(tasks)
        self._apply_refreshed_tasks(
            tasks, force_ui=True, select_task=select_task, select_worktree=select_worktree
        )
        # The follow-up scan applies with preserve-current-selection semantics
        # (no select override): re-forcing the selection here would yank the
        # highlight back if the user navigates while the scan runs.
        self._run_periodic_refresh()

    def _carry_over_statuses(self, tasks: list[Task]) -> None:
        """Seed a freshly listed task set with the last known git statuses.

        The synchronous list pass renders before the background git scan
        completes; carrying over the previous branch/dirty state avoids a
        flash of unknown/clean rows and keeps the fingerprint accurate so the
        follow-up scan can skip its UI reload when nothing actually changed.
        """
        try:
            previous = self.query_one("#task-list", TaskList).all_tasks
        except Exception:
            return
        known = {(task.name, wt.name): wt for task in previous for wt in task.worktrees}
        for task in tasks:
            for wt in task.worktrees:
                prev = known.get((task.name, wt.name))
                if prev is not None:
                    wt.branch = prev.branch
                    wt.is_dirty = prev.is_dirty
                    wt.changed_files = prev.changed_files

    def _load_tasks_with_selection(self, task_name: str | None, worktree_name: str | None) -> None:
        """Load tasks and restore selection by explicit names.

        This is used after suspend/resume to restore exact selection state.
        """
        self._load_tasks(select_task=task_name, select_worktree=worktree_name)

    def _worker_running(self, group: str) -> bool:
        """True while any worker in the given group is still running."""
        return any(worker.group == group and not worker.is_finished for worker in self.workers)

    def _mutation_in_flight(self) -> bool:
        """True while a task create/add/delete worker is still running."""
        return self._worker_running("task_mutation")

    def _begin_mutation(self, *loading_widget_ids: str) -> bool:
        """Guard a task mutation, refusing while another is still running.

        Overlapping mutations would race git worktree add/remove/prune (and
        rmtree) against each other in the same repos. Returns True when the
        mutation may proceed, with loading indicators set on the given widgets.
        """
        if self._mutation_in_flight():
            self.notify("Another task operation is still running", severity="warning")
            return False
        # A periodic scan already in flight would otherwise apply its
        # pre-mutation snapshot after this mutation finishes, clobbering the
        # loading indicators set below (see the worker check in
        # _apply_refreshed_tasks, its belt-and-suspenders counterpart).
        self.workers.cancel_group(self, "auto_refresh")
        for widget_id in loading_widget_ids:
            self.query_one(f"#{widget_id}").loading = True
        return True

    def _poll_claude_statuses(self) -> None:
        """Check .claude_status files and update task indicators."""
        try:
            task_list = self.query_one("#task-list", TaskList)
        except Exception:
            return

        statuses: dict[str, str] = {}
        # all_tasks: a folded child still feeds its epic row rollup
        for task in task_list.all_tasks:
            status_file = task.path / ".claude_status"
            if not status_file.exists():
                continue
            try:
                data = json.loads(status_file.read_text())
            except (OSError, UnicodeDecodeError, ValueError):
                # ValueError also catches json.JSONDecodeError (a subclass);
                # UnicodeDecodeError covers a non-UTF-8 status file
                continue
            if not isinstance(data, dict):
                # Valid JSON but not an object (e.g. "[]") - .get() below
                # would raise AttributeError and kill the poll interval
                continue
            status = data.get("status", "unknown")
            if isinstance(status, str):
                statuses[task.name] = status

        if statuses != self._claude_statuses:
            finished = [
                name
                for name, status in statuses.items()
                if status == "waiting" and self._claude_statuses.get(name) == "running"
            ]
            if finished and self.config.claude_background and os.environ.get("ZELLIJ_SESSION_NAME"):
                self._notify_closed_claude_tabs(finished)
            self._claude_statuses = statuses
            task_list.refresh_claude_indicators(statuses)
            if self.current_task:
                try:
                    status_panel = self.query_one("#status-display", StatusPanel)
                except Exception:
                    return
                status_panel.set_claude_live_status(statuses.get(self.current_task.name))
                if self.current_task.is_epic:
                    children, _ = self._epic_context(self.current_task, task_list)
                    status_panel.set_epic_children(self.current_task.name, children or [])

        # Same tick keeps the recap fresh: a stat per poll, a read only on change
        if self.config.claude_recap and self.current_task and task_list.has_focus:
            self._update_claude_recap(self.current_task, self._recap_key)

    @work(thread=True, exclusive=True, group="claude_recap_update")
    def _update_claude_recap(self, task: Task, known_key: tuple[Path, int, int] | None) -> None:
        """Read the task's latest Claude transcript tail when it changed.

        ``known_key`` is passed in from the main thread so the worker never
        reads mutable app state. The session is picked like `epic log` picks
        it: newest across the task folder and its worktrees, by recorded cwd.
        """
        folders = [task.path, *(wt.path for wt in task.worktrees)]
        key = transcript_key(*folders)
        if key == known_key:
            return
        session = latest_session(folders) if key else None
        recap = read_claude_recap(session.path) if session else None
        if get_current_worker().is_cancelled:
            return
        self.call_from_thread(self._apply_claude_recap, task, key, recap)

    def _apply_claude_recap(
        self, task: Task, key: tuple[Path, int, int] | None, recap: ClaudeRecap | None
    ) -> None:
        """Push a fetched recap to the Info panel (main thread)."""
        if not (self.current_task and self.current_task.name == task.name):
            return
        self._recap_key = key
        try:
            status_panel = self.query_one("#status-display", StatusPanel)
        except Exception:
            return
        status_panel.set_claude_recap(task.name, recap, self._claude_statuses.get(task.name))

    def _request_claude_recap(self, task: Task) -> None:
        """Start a fresh recap read for a newly shown task."""
        self._recap_key = None
        if self.config.claude_recap:
            self._update_claude_recap(task, None)

    def _poll_agent_sessions_tick(self) -> None:
        """Dispatch an agent-session poll worker (never subprocess on UI thread)."""
        if self.config.agent_poll_interval <= 0:
            return  # 0 = disabled, including dispatch-triggered calls
        if self._agent_poll_disabled or self._worker_running("agent_poll"):
            return
        try:
            task_list = self.query_one("#task-list", TaskList)
        except Exception:
            return
        paths = [str(wt.path) for task in task_list.all_tasks for wt in task.worktrees]
        if paths:
            self._run_agent_poll(paths)

    @work(thread=True, exclusive=True, group="agent_poll")
    def _run_agent_poll(self, worktree_paths: list[str]) -> None:
        """Fetch `claude agents --json` off-thread and map onto worktrees."""
        sessions = list_agent_sessions(self.config.claude_path)
        if get_current_worker().is_cancelled:
            return
        if sessions is None:
            self.call_from_thread(self._note_agent_poll_failure)
            return
        states = map_sessions_to_worktrees(sessions, worktree_paths)
        self.call_from_thread(self._apply_agent_sessions, states)

    def _apply_agent_sessions(self, states: dict[str, str]) -> None:
        self._agent_poll_failures = 0
        if states == self._agent_sessions:
            return
        self._agent_sessions = states
        self._push_badges_to_worktree_list()

    def _note_agent_poll_failure(self) -> None:
        """Auto-disable the agent poll after repeated failures (old CLI, no CLI)."""
        self._agent_poll_failures += 1
        if self._agent_poll_failures >= 3 and not self._agent_poll_disabled:
            self._agent_poll_disabled = True
            self._log_activity(
                "Claude agent polling disabled ('claude agents' unavailable)",
                MessageLevel.INFO,
            )

    def _poll_forge_tick(self) -> None:
        """Dispatch a forge MR/CI poll for the current task's worktrees.

        No skip-if-running guard: task highlighting fires this, and dropping
        the tick would leave the newly highlighted task without badges until
        the next interval; exclusive=True replaces the stale worker instead.
        """
        if not self.config.forge_enabled or self.config.forge_poll_interval <= 0:
            return  # 0 = disabled, including highlight-triggered calls
        task = self.current_task
        if not task:
            return
        pairs = [
            (str(wt.path), wt.branch or task.name) for wt in task.worktrees if wt.path.exists()
        ]
        if pairs:
            self._run_forge_poll(pairs)

    @work(thread=True, exclusive=True, group="forge_poll")
    def _run_forge_poll(self, pairs: list[tuple[str, str]]) -> None:
        """Query forge status per worktree in parallel (TTL-cached in forge).

        Uses the app-lifetime executor and checks cancellation between
        futures, so a superseded/cancelled poll stops consuming results
        instead of joining every glab/gh call first. Already-running calls
        cannot be interrupted (subprocesses), but their results feed the TTL
        cache, so nothing is wasted.
        """
        worker = get_current_worker()
        if worker.is_cancelled:
            return
        futures = {
            self._forge_executor.submit(get_forge_status, Path(path), branch): path
            for path, branch in pairs
        }
        results: dict[str, ForgeStatus | None] = {}
        pending = set(futures)
        # Poll with a short timeout instead of blocking in as_completed: a
        # superseded worker must release its default-executor thread right
        # away, not after the first glab/gh call returns
        while pending:
            if worker.is_cancelled:
                for future in pending:
                    future.cancel()
                return
            done, pending = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
            for future in done:
                path = futures[future]
                try:
                    results[path] = future.result()
                except Exception:
                    results[path] = None
        self.call_from_thread(self._apply_forge_statuses, results)

    def _apply_forge_statuses(self, statuses: dict[str, ForgeStatus | None]) -> None:
        # Merge rather than replace so cached entries for other tasks
        # survive — but a None result evicts: the MR may be gone or auth
        # expired, and keeping the old entry would render stale badges
        # for the rest of the session
        merged = dict(self._forge_statuses)
        for path, status in statuses.items():
            if status is None:
                merged.pop(path, None)
            else:
                merged[path] = status
        if merged == self._forge_statuses:
            return
        self._forge_statuses = merged
        self._push_badges_to_worktree_list()

    def _push_badges_to_worktree_list(self) -> None:
        """Re-render worktree badge cells in place (no full list reload)."""
        try:
            worktree_list = self.query_one("#worktree-list", WorktreeList)
        except Exception:
            # Widgets not mounted (e.g. setup wizard is showing)
            return
        worktree_list.refresh_status_badges(self._agent_sessions, self._forge_statuses)

    def _periodic_git_refresh(self) -> None:
        """Trigger a background git status refresh."""
        # Skip the tick while a mutation runs: refreshing mid-create/delete
        # would clear the loading overlay and render half-mutated state
        if self._mutation_in_flight():
            return
        # Skip while the previous scan is still running: exclusive=True would
        # cancel it, and a scan slower than the interval would then never
        # finish (livelock) and the dirty state would never reach the UI
        if self._worker_running("auto_refresh"):
            return
        self._run_periodic_refresh()

    @staticmethod
    def _tasks_fingerprint(tasks: list[Task]) -> tuple:
        """Cheap comparable snapshot of task/worktree state for change detection."""
        return tuple(
            (
                task.name,
                task.kind,
                task.epic_name,
                tuple((wt.name, wt.branch, wt.is_dirty, wt.changed_files) for wt in task.worktrees),
            )
            for task in tasks
        )

    @work(thread=True, exclusive=True, group="auto_refresh")
    def _run_periodic_refresh(self, force_ui: bool = False) -> None:
        """Refresh git status in a background thread, then update the UI.

        Args:
            force_ui: If True, reload the UI even when nothing changed
                (used by manual refresh)
        """
        tasks = self.task_manager.list_tasks()
        all_worktrees = [wt for task in tasks for wt in task.worktrees]
        GitOps.update_all_worktree_statuses(all_worktrees)
        # Cancellation of thread workers is cooperative: when a newer refresh
        # superseded this one, applying our now-stale snapshot would overwrite
        # fresher UI state, so bail out instead. The worker is passed along
        # because the cancel can also land after this callback is queued.
        worker = get_current_worker()
        if worker.is_cancelled:
            return
        self.call_from_thread(self._apply_refreshed_tasks, tasks, force_ui, worker=worker)

    def _apply_refreshed_tasks(
        self,
        tasks: list[Task],
        force_ui: bool = False,
        select_task: str | None = None,
        select_worktree: str | None = None,
        worker=None,
    ) -> None:
        """Apply a (re)loaded task list to the UI (runs on the main thread).

        The selection is read here, at apply time, so navigation that happened
        while a background scan was running is not reverted; select_task /
        select_worktree override it (used after suspend/resume and creation).
        When nothing changed since the last load, the UI reload is skipped
        entirely to avoid selection/status-panel flicker. A snapshot from a
        scan that was superseded while this call sat in the queue is dropped.
        """
        # `worker` is only passed by the background auto_refresh scan. Skip
        # its apply if it was cancelled, or if a mutation started after the
        # scan's git calls finished but before this callback reached the
        # main thread - either way this is a pre-mutation snapshot that
        # must not clobber the mutation's own loading state and reload.
        if worker is not None and (worker.is_cancelled or self._mutation_in_flight()):
            return
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
        self._update_header_stats(tasks)

        # Prune forge entries for worktrees that no longer exist — a deleted
        # task recreated at the same path must not inherit the old MR badge
        valid_paths = {str(wt.path) for task in tasks for wt in task.worktrees}
        self._forge_statuses = {
            path: status for path, status in self._forge_statuses.items() if path in valid_paths
        }

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
                self._last_tasks_fingerprint = fingerprint
                return

            # The worktree list is (re)loaded by the TaskHighlighted handler
            # that load_tasks triggers, using _preserved_worktree_name; doing
            # it here as well rebuilt the list twice per refresh. Only the
            # task reference is refreshed eagerly so actions see fresh data.
            if current_task_name:
                for t in tasks:
                    if t.name == current_task_name:
                        self.current_task = t
                        break
            self._push_badges_to_worktree_list()
            self._last_tasks_fingerprint = fingerprint
        except Exception as e:
            # A worker error would exit the app; refresh glitches are not
            # fatal. Deliberately leave _last_tasks_fingerprint at its prior
            # value: the UI never actually reflected this data, so a later
            # refresh with the same (still-unapplied) snapshot must retry
            # instead of being skipped as a no-op.
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
                self._request_claude_recap(self.current_task)
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
            # The previous task's worktree must not survive the switch: the
            # worktree list re-emits its highlight (None for an empty task),
            # but worktree-scoped actions could fire before that lands
            self.current_worktree = None
            self.current_status = None
            # Use preserved worktree name if set (during reload after lazygit/shell)
            preserved = self._preserved_worktree_name
            self._preserved_worktree_name = None  # Clear after use
            worktree_list.load_worktrees(event.task.worktrees, preserve_selection=preserved)
            self._push_badges_to_worktree_list()
            # Fetch fresh forge state for the newly highlighted task
            self._poll_forge_tick()

            # Show task summary if task list is focused
            if task_list.has_focus:
                self._set_info_title(event.task.name)
                status_panel.set_loading(True)
                self._update_task_summary(event.task)
                self._request_claude_recap(event.task)
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
                    children, parent = self._epic_context(task, task_list)
                    status_panel.update_task_summary(
                        task, statuses, epic_children=children, epic_label=parent
                    )
            except Exception:
                pass

    def _epic_context(
        self, task: Task, task_list: TaskList
    ) -> tuple[list[tuple[str, bool, str | None]] | None, str | None]:
        """The Info panel epic block (children) or parent line for a task."""
        if task.is_epic:
            children = [
                (child.display_label, child.is_dirty, self._claude_statuses.get(child.name))
                for child in task_list.epic_children(task.name)
            ]
            return children, None
        epic_name = task_list.epic_of(task.name)
        if epic_name is None:
            return None, None
        parent = next(t for t in task_list.all_tasks if t.name == epic_name)
        return None, parent.display_label

    def _epic_choices(self) -> list[tuple[str, str]]:
        """(label, name) of every loaded epic, sorted by label."""
        try:
            tasks = self.query_one("#task-list", TaskList).all_tasks
        except Exception:
            return []
        # A symlink alias is not an epic of its own: set_task_epic refuses it
        epics = [
            (task.display_label, task.name)
            for task in tasks
            if task.is_epic and not task.path.is_symlink()
        ]
        return sorted(epics, key=lambda pair: pair[0].lower())

    def _epic_of(self, task: Task | None) -> str | None:
        """The epic a new task next to `task` should join: itself or its parent."""
        if task is None:
            return None
        if task.is_epic:
            return None if task.path.is_symlink() else task.name
        return self.query_one("#task-list", TaskList).epic_of(task.name)

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit()

    def on_unmount(self) -> None:
        """Release the forge executor and kill in-flight git/gh children.

        asyncio.run() joins the default executor on shutdown, so a thread
        worker blocked in `git fetch` or `gh pr list` would keep the process
        alive (terminal already restored) until its timeout expired.
        """
        self._forge_executor.shutdown(wait=False, cancel_futures=True)
        GitOps.terminate_all()

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
            if result and self._begin_mutation("task-list"):
                name, repos, base_branch, epic = result
                self._create_task_worker(name, repos, base_branch, verb="created", epic=epic)

        self.push_screen(
            CreateTaskModal(
                available_repos,
                initial_base_branch=self.config.default_base_branch,
                epics=self._epic_choices(),
                initial_epic=self._epic_of(self.current_task),
            ),
            handle_result,
        )

    @work(thread=True, group="task_mutation")
    def _create_task_worker(
        self, name: str, repos: list[str], base_branch: str, verb: str, epic: str | None = None
    ) -> None:
        """Create a task in a background thread.

        Creation fetches the base branch from origin for every repo, so it
        can block on the network for a long time - never run it on the UI
        thread.
        """
        error: str | None = None
        try:
            self.task_manager.create_task(name, repos, base_branch, epic=epic)
        except FileNotFoundError as e:
            error = f"Repository not found: {e}"
        except PermissionError:
            error = "Permission denied: check directory permissions"
        except ValueError as e:
            # ValueError from task_manager has good messages
            error = str(e)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
        self.call_from_thread(self._apply_create_task_result, name, len(repos), verb, error, epic)

    def _apply_create_task_result(
        self, name: str, repo_count: int, verb: str, error: str | None, epic: str | None = None
    ) -> None:
        """Report the create/clone outcome and reload (runs on the main thread)."""
        if error:
            self.notify(escape(f"Failed to create task: {error}"), severity="error")
            self._log_activity(f"Failed to create task: {error}", MessageLevel.ERROR, name)
            self._load_tasks()
        else:
            self.notify(escape(f"Created task: {name}"))
            in_epic = f" in epic '{epic}'" if epic else ""
            self._log_activity(
                f"Task '{name}' {verb} with {repo_count} repo(s){in_epic}",
                MessageLevel.SUCCESS,
                name,
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
            if result and self._begin_mutation("task-list"):
                name, repos, base_branch, epic = result
                self._create_task_worker(name, repos, base_branch, verb="cloned", epic=epic)

        self.push_screen(
            CreateTaskModal(
                available_repos,
                initial_repos=source_repos,
                initial_base_branch=self.config.default_base_branch,
                title=f"Clone Task: {self.current_task.name}",
                epics=self._epic_choices(),
                # A clone joins the source task's epic; a clone of an epic joins none
                initial_epic=self.query_one("#task-list", TaskList).epic_of(self.current_task.name),
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
            if result and self.current_task and self._begin_mutation("task-list", "worktree-list"):
                repos, base_branch = result
                self._add_repos_worker(self.current_task, repos, base_branch)

        self.push_screen(
            AddRepoModal(
                self.current_task.name,
                available_repos,
                initial_base_branch=self.config.default_base_branch,
            ),
            handle_result,
        )

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
        if self.current_task.is_epic:
            children = self.task_manager.epic_child_names(self.current_task.name)
            if children:
                self.notify(
                    escape(
                        f"Epic '{self.current_task.name}' still has tasks: {', '.join(children)}"
                    ),
                    severity="warning",
                )
                return

        # Safety checks hit the network (git fetch per worktree), so run them
        # in a background thread and show the dialog when they complete
        self.notify(escape(f"Checking '{self.current_task.name}' before delete..."))
        self._check_task_safety_worker(self.current_task)

    @work(thread=True, exclusive=True, group="safety_check")
    def _check_task_safety_worker(self, task: Task) -> None:
        """Run task safety checks in a background thread."""
        safety_report = self.task_manager.check_task_safety(task)
        claude_busy = busy(self._background_sessions(task) or [])
        if get_current_worker().is_cancelled:
            return
        self.call_from_thread(self._show_delete_task_dialog, task, safety_report, claude_busy)

    def _show_delete_task_dialog(
        self,
        task: Task,
        safety_report: TaskSafetyReport,
        claude_busy: list[AgentSession] | None = None,
    ) -> None:
        """Show the appropriate delete dialog for the safety report.

        Background Claude sessions working or waiting in the task are confirmed
        first; the delete itself stops them.
        """
        if claude_busy:
            ids = ", ".join(session.agent_id for session in claude_busy)
            message = f"Claude is still active in '{task.name}' ({ids}). Stop it and continue?"

            def handle_busy(confirmed):
                if confirmed:
                    self._show_delete_task_dialog(task, safety_report)

            self.push_screen(ConfirmModal("Claude Still Running", escape(message)), handle_busy)
            return
        if safety_report.is_safe():
            # When the verdict rests on a remote MR lookup (squash/rebase
            # merge), say so — the user deserves a chance to sanity-check it
            message = f"Delete task '{task.name}' and all its worktrees?"
            if safety_report.merged_via_forge:
                notes = "\n".join(
                    f"  * {issue.repo_name}: {issue.details}"
                    for issue in safety_report.merged_via_forge
                )
                message = f"Merged remotely (squash/rebase):\n{notes}\n\n{message}"
            self._confirm_and_finish_task(task, escape(message))
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

    def action_rename_task(self) -> None:
        """Set a display alias for the current task (folder/branch unchanged)."""
        if not self.current_task:
            self.notify("No task selected", severity="warning")
            return
        task = self.current_task

        def handle_rename(new_name: str | None) -> None:
            if new_name is None:
                return
            try:
                self.task_manager.set_task_display_name(task, new_name)
            except (OSError, ValueError) as e:
                self.notify(escape(f"Rename failed: {e}"), severity="error")
                return
            label = task.display_label
            self.notify(escape(f"Task '{task.name}' shown as '{label}'"))
            self._log_activity(f"Task '{task.name}' renamed to '{label}'", MessageLevel.INFO)
            self._run_periodic_refresh(force_ui=True)

        self.push_screen(RenameTaskModal(task.name, task.display_name), handle_rename)

    def action_set_epic(self) -> None:
        """Attach the current task to an epic, detach it, or make it an epic."""
        task = self.current_task
        if not task:
            self.notify("No task selected", severity="warning")
            return
        if task.is_epic:
            self.notify("Epics don't nest: an epic can't join another epic", severity="warning")
            return
        epics = [(label, name) for label, name in self._epic_choices() if name != task.name]
        parent = self.query_one("#task-list", TaskList).epic_of(task.name)

        def handle_choice(choice: tuple[str, str | None] | None) -> None:
            if choice is None:
                return
            action, epic = choice
            if action == "new":
                self.push_screen(
                    NewEpicModal(task.name),
                    lambda name: self._apply_epic_choice(task, "new", name) if name else None,
                )
            else:
                self._apply_epic_choice(task, action, epic)

        self.push_screen(
            EpicPickerModal(
                task.display_label,
                epics,
                parent,
                parent is None,
            ),
            handle_choice,
        )

    def _apply_epic_choice(self, task: Task, action: str, epic: str | None) -> None:
        """Write the picked epic change; marker writes are local and fast."""
        if self._mutation_in_flight():
            # A delete worker may be rmtree-ing the very folders written here
            self.notify("Another task operation is still running", severity="warning")
            return
        previous = task.epic_name
        try:
            if action == "new" and epic:
                self.task_manager.create_task(epic, [], kind=EPIC_KIND)
                try:
                    epic = self.task_manager.set_task_epic(task, epic)
                except (ValueError, OSError) as e:
                    # The epic exists now; show it and say what did not happen
                    self.notify(
                        escape(f"Created epic '{epic}' but could not add '{task.name}': {e}"),
                        severity="warning",
                    )
                    self._load_tasks(select_task=epic)
                    return
                message = f"Created epic '{epic}' and added '{task.name}' to it"
            elif action == "set" and epic:
                epic = self.task_manager.set_task_epic(task, epic)
                if previous == epic:
                    message = f"Task '{task.name}' already in epic '{epic}'"
                elif previous:
                    message = f"Moved '{task.name}' from epic '{previous}' to '{epic}'"
                else:
                    message = f"Added '{task.name}' to epic '{epic}'"
            elif action == "none":
                self.task_manager.set_task_epic(task, None)
                message = (
                    f"Removed '{task.name}' from epic '{previous}'"
                    if previous
                    else f"Task '{task.name}' is not in an epic"
                )
            elif action == "mark":
                self.task_manager.set_task_kind(task, EPIC_KIND)
                message = f"Task '{task.name}' is an epic now"
            else:
                return
        except (ValueError, OSError) as e:
            self.notify(escape(f"Epic change failed: {e}"), severity="error")
            return
        self.notify(escape(message))
        self._log_activity(message, MessageLevel.INFO, task.name)
        problem = self.task_manager.sync_epic_block(task)
        if problem:
            self.notify(escape(problem), severity="warning")
            self._log_activity(problem, MessageLevel.WARNING, task.name)
        self._load_tasks(select_task=task.name)

    def _finish_task(self, task: Task, force: bool = False, skip_archive: bool = False) -> None:
        """Kick off task deletion in a background thread."""
        if not self._begin_mutation("task-list"):
            return
        self._finish_task_worker(task, force, skip_archive)

    @work(thread=True, group="task_mutation")
    def _finish_task_worker(self, task: Task, force: bool, skip_archive: bool = False) -> None:
        """Delete the task in a background thread.

        Removing worktrees runs git per repo and rmtree over trees that can
        be huge (node_modules etc.) - never block the UI thread on it.
        The task's remaining diff (committed-but-unmerged + uncommitted) and
        its task-folder files are archived first — finish_task rmtrees the
        task directory. An incomplete archive stops the delete and asks
        again, as the CLI refuses without --force; `skip_archive` is the
        confirmed second pass.
        """
        error: str | None = None
        archive: ArchiveResult | None = None
        # Stopped first, so no session writes into the folder being archived;
        # one that would not stop keeps the task
        sessions = self._background_sessions(task)
        if sessions is None:
            message = f"Could not check Claude sessions of '{task.name}'; none were stopped"
            self.call_from_thread(self.notify, escape(message), severity="warning")
            self.call_from_thread(self._log_activity, message, MessageLevel.WARNING, task.name)
        failed = end_sessions(self.config.claude_path, sessions or [])
        if failed:
            error = f"could not stop Claude session(s) {', '.join(failed)}; run `claude stop ID`"
            self.call_from_thread(self._apply_finish_task_result, task.name, force, error)
            return
        if not skip_archive:
            problem: str | None = None
            try:
                archive = self.task_manager.archive_task(task)
            except Exception as e:
                # ArchiveIncompleteError's message names the partial archive,
                # and its result the files saved and left out
                problem = f"Archive failed for '{task.name}': {type(e).__name__}: {e}"
                archive = getattr(e, "result", None)
            if problem is None and archive is not None and archive.failed:
                problem = (
                    f"{len(archive.failed)} task file(s) of '{task.name}' could not be archived"
                )
            if problem is not None:
                self.call_from_thread(
                    self._confirm_delete_after_archive_problem, task, force, problem, archive
                )
                return
        try:
            self.task_manager.finish_task(task)
        except ValueError as e:
            # finish_task raises ValueError (nothing removed) when worktrees
            # on disk no longer match task.worktrees - the task changed
            # during the confirm dialog. Its message is already clear.
            error = str(e)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
        self.call_from_thread(self._apply_finish_task_result, task.name, force, error, archive)

    def _confirm_delete_after_archive_problem(
        self, task: Task, force: bool, problem: str, archive: ArchiveResult | None
    ) -> None:
        """Report an incomplete archive and ask before deleting (main thread)."""
        self.query_one("#task-list", TaskList).loading = False
        self.notify(escape(problem), severity="warning", timeout=10)
        self._log_activity(problem, MessageLevel.ERROR, task.name)
        if archive is not None:
            self._log_archive(task.name, archive)
        message = (
            escape(problem)
            + "\n\nThe task folder may hold the only copy of what was not archived"
            + " (see messages). Delete anyway?"
        )

        def handle_confirm(confirmed):
            if confirmed:
                self._finish_task(task, force=force, skip_archive=True)

        self.push_screen(ConfirmModal("Archive Incomplete", message), handle_confirm)

    def _apply_finish_task_result(
        self,
        task_name: str,
        force: bool,
        error: str | None,
        archive: ArchiveResult | None = None,
    ) -> None:
        """Report the delete outcome and reload (runs on the main thread)."""
        if error:
            self.notify(escape(f"Failed to delete task: {error}"), severity="error")
            self._log_activity(f"Failed to delete task: {error}", MessageLevel.ERROR, task_name)
            if archive is not None:
                # The archive succeeded before the delete itself failed - the
                # user's work is not lost, but they should know where it is
                self._log_archive(task_name, archive, " before the failed delete")
        else:
            self.notify(escape(f"Deleted task: {task_name}"))
            suffix = " (force)" if force else ""
            self._log_activity(
                f"Task '{task_name}' deleted{suffix}", MessageLevel.SUCCESS, task_name
            )
            if archive is not None:
                self._log_archive(task_name, archive)
        self._load_tasks()

    def _log_archive(self, task_name: str, archive: ArchiveResult, context: str = "") -> None:
        """Log where a task's work was archived and warn about files left out.

        The left-out notes come first and are capped, so the archive
        location stays among the latest entries of the bounded panel.
        """
        notes = [f"Not archived: {item}" for item in archive.skipped]
        notes += [f"Could not archive: {item}" for item in archive.failed]
        for note in notes[:ARCHIVE_NOTES_SHOWN]:
            self._log_activity(note, MessageLevel.WARNING, task_name)
        if len(notes) > ARCHIVE_NOTES_SHOWN:
            self._log_activity(
                f"... and {len(notes) - ARCHIVE_NOTES_SHOWN} more not archived",
                MessageLevel.WARNING,
                task_name,
            )
        if archive.patch is not None:
            self._log_activity(
                f"Archived diff to {archive.patch}{context}", MessageLevel.INFO, task_name
            )
        if archive.files_dir is not None:
            self._log_activity(
                f"Archived {len(archive.files)} task file(s) to {archive.files_dir}{context}",
                MessageLevel.INFO,
                task_name,
            )
        if notes:
            self.notify(
                f"{len(notes)} task file note(s) - see messages",
                severity="warning",
                timeout=10,
            )

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
        if get_current_worker().is_cancelled:
            return
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
        """Delete a single worktree from the current task, with safety checks.

        Runs the same sweep, dialog and archive as task deletion, scoped to
        the one worktree: removal force-deletes the tree and the task branch
        in that repo, so unpushed or uncommitted work would otherwise vanish
        behind a plain confirm.
        """
        if not self.current_task:
            self.notify("No task selected", severity="warning")
            return
        if not self.current_worktree:
            self.notify("No worktree selected", severity="warning")
            return

        worktree = self.current_worktree
        self.notify(escape(f"Checking '{worktree.name}' before delete..."))
        self._check_worktree_safety_worker(self.current_task, worktree)

    @staticmethod
    def _worktree_view(task: Task, worktree: Worktree) -> Task:
        """A Task limited to one worktree, for the task-level safety helpers."""
        return Task(name=task.name, path=task.path, worktrees=[worktree])

    @work(thread=True, exclusive=True, group="safety_check")
    def _check_worktree_safety_worker(self, task: Task, worktree: Worktree) -> None:
        """Run the safety check for a single worktree in a background thread."""
        report = self.task_manager.check_task_safety(self._worktree_view(task, worktree))
        if get_current_worker().is_cancelled:
            return
        self.call_from_thread(self._show_delete_worktree_dialog, task, worktree, report)

    def _show_delete_worktree_dialog(
        self, task: Task, worktree: Worktree, report: TaskSafetyReport
    ) -> None:
        """Show the confirm or safe-delete dialog for one worktree."""
        if report.is_safe():
            message = f"Delete worktree '{worktree.name}' from task '{task.name}'?"
            if report.merged_via_forge:
                notes = "\n".join(
                    f"  * {i.repo_name}: {i.details}" for i in report.merged_via_forge
                )
                message = f"Merged remotely (squash/rebase):\n{notes}\n\n{message}"
            self._confirm_and_remove_worktree(task, worktree, escape(message))
        else:
            self.push_screen(
                SafeDeleteModal(f"{task.name} / {worktree.name}", report),
                lambda action: self._handle_safe_delete_worktree_action(
                    task, worktree, report, action
                ),
            )

    def _handle_safe_delete_worktree_action(
        self, task: Task, worktree: Worktree, report: TaskSafetyReport, action: str | None
    ) -> None:
        """Handle the user's choice from the worktree safe-delete modal."""
        if action == "push":
            self.notify(escape(f"Pushing {worktree.name}..."))
            self._push_worktree_for_delete_worker(task, worktree)
        elif action == "lazygit":
            # Open lazygit in the worktree, then re-run the check
            self._open_lazygit_for_task(self._worktree_view(task, worktree), report)
            self._check_worktree_safety_worker(task, worktree)
        elif action == "force":
            self._confirm_and_remove_worktree(
                task,
                worktree,
                escape(f"Really delete worktree '{worktree.name}'?")
                + "\n\nYou may lose unpushed work!",
                title="Force Delete",
                force=True,
            )
        # else: cancelled, do nothing

    @work(thread=True, exclusive=True, group="safety_check")
    def _push_worktree_for_delete_worker(self, task: Task, worktree: Worktree) -> None:
        """Push one worktree's branch and re-run its safety check."""
        view = self._worktree_view(task, worktree)
        success, failed = self.task_manager.push_all_branches(view)
        report = self.task_manager.check_task_safety(view)
        if get_current_worker().is_cancelled:
            return
        self.call_from_thread(
            self._apply_worktree_push_result, task, worktree, success, failed, report
        )

    def _apply_worktree_push_result(
        self,
        task: Task,
        worktree: Worktree,
        success: list[str],
        failed: list[str],
        report: TaskSafetyReport,
    ) -> None:
        """Continue the worktree delete flow after pushing (main thread)."""
        if failed:
            self.push_screen(
                PushResultModal(success, failed),
                lambda _: self._show_delete_worktree_dialog(task, worktree, report),
            )
        else:
            self.notify(escape(f"Pushed {worktree.name}"))
            self._show_delete_worktree_dialog(task, worktree, report)

    def _confirm_and_remove_worktree(
        self,
        task: Task,
        worktree: Worktree,
        message: str,
        title: str = "Delete Worktree",
        force: bool = False,
    ) -> None:
        """Push a confirmation modal and remove the worktree if confirmed."""

        def handle_confirm(confirmed):
            if confirmed and self._begin_mutation("worktree-list"):
                self._remove_worktree_worker(task, worktree, force)

        self.push_screen(ConfirmModal(title, message), handle_confirm)

    @work(thread=True, group="task_mutation")
    def _remove_worktree_worker(self, task: Task, worktree: Worktree, force: bool = False) -> None:
        """Remove a single worktree in a background thread (archive, git, rmtree)."""
        error: str | None = None
        archive: ArchiveResult | None = None
        try:
            try:
                # Diff only: the task folder and its files stay in place
                archive = self.task_manager.archive_task(
                    self._worktree_view(task, worktree), include_files=False
                )
            except Exception as e:
                # Loud but non-blocking, same policy as task deletion
                detail = f"Archive failed for '{worktree.name}': {type(e).__name__}: {e}"
                self.call_from_thread(self.notify, escape(detail), severity="warning", timeout=10)
                self.call_from_thread(self._log_activity, detail, MessageLevel.ERROR, task.name)
            self.task_manager.remove_worktree_from_task(task, worktree)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
        self.call_from_thread(
            self._apply_remove_worktree_result, task.name, worktree.name, force, error, archive
        )

    def _apply_remove_worktree_result(
        self,
        task_name: str,
        worktree_name: str,
        force: bool,
        error: str | None,
        archive: ArchiveResult | None = None,
    ) -> None:
        """Report the worktree removal outcome and reload (main thread)."""
        if error:
            self.notify(escape(f"Failed to delete worktree: {error}"), severity="error")
            self._log_activity(
                f"Failed to delete worktree '{worktree_name}': {error}",
                MessageLevel.ERROR,
                task_name,
            )
            if archive is not None:
                self._log_archive(task_name, archive, " before the failed delete")
        else:
            self.notify(escape(f"Deleted worktree: {worktree_name}"))
            suffix = " (force)" if force else ""
            self._log_activity(
                f"Worktree '{worktree_name}' deleted from '{task_name}'{suffix}",
                MessageLevel.SUCCESS,
                task_name,
            )
            if archive is not None:
                self._log_archive(task_name, archive)
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
        elif safety_report.errors:
            # Status unreadable / wrong branch checked out: lazygit is the
            # right place to inspect and fix that too
            first_issue_worktree = safety_report.errors[0].worktree_path

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
        if not self.current_task:
            self.notify("No task selected", severity="warning")
            return

        task = self.current_task
        if not task.worktrees:
            self.notify("Task has no worktrees", severity="information")
            return

        # Building the combined diff is local git work, but it scales with
        # the size of the trees (one add + diff per worktree), so it runs in
        # a thread worker; the suspend/hunk step happens in the callback
        self.notify("Preparing diff...")
        self._build_task_diff_worker(task)

    @work(thread=True, exclusive=True, group="task_diff")
    def _build_task_diff_worker(self, task: Task) -> None:
        """Build the task's combined patch off the UI thread."""
        try:
            diff = GitOps.build_task_diff(task)
        except Exception as e:
            self.call_from_thread(
                self.notify, escape(f"Could not build diff: {e}"), severity="error"
            )
            return
        if get_current_worker().is_cancelled:
            return
        self.call_from_thread(self._open_task_diff, task, diff)

    def _open_task_diff(self, task: Task, diff: str) -> None:
        """Write the patch to a temp file and open hunk on it (main thread)."""
        import tempfile

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

    def action_open_editor(self) -> None:
        """Open editor in a new terminal tab at the current folder.

        Same mechanism as open_folder: the TUI keeps running instead of
        suspending, so the editor session and the dashboard live side by
        side (matches the `o`/`c` new-tab behavior).
        """
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

        editor = self.config.get_editor()
        self._open_terminal_tab(
            folder_path, command=f"{editor} .", kind="editor", notice=f"Opened {editor} in new tab"
        )

    def _prepare_claude_session(self, task: Task) -> None:
        """Refresh CLAUDE.md files, worktree settings, and hooks before launching Claude.

        Must run off the UI thread: ensure_claude_md_files can shell out to
        git (symbolic-ref/show, each with a 10s timeout) once per worktree
        missing a CLAUDE.md. Every caller runs this inside a
        @work(thread=True) worker and passes the task explicitly rather than
        reading self.current_task, which is not safe to read from a thread.
        """
        fresh_task = self.task_manager.get_task(task.name)
        if fresh_task:
            problem = self.task_manager.ensure_claude_md_files(fresh_task)
            if problem:
                self.call_from_thread(self.notify, escape(problem), severity="warning")
            self.task_manager.ensure_worktree_settings(fresh_task)
        ensure_claude_hooks(task.path, self.config.claude_memory_dir)

    def action_open_claude_resume(self) -> None:
        """Open Claude Code in a new terminal tab.

        With `claude_background` the session runs in the background and the
        tab only shows it (see _open_claude_background). Otherwise the tab
        runs Claude itself, resuming the folder's session if one exists.
        """
        if not self.current_task:
            self.notify("No task selected", severity="warning")
            return

        task = self.current_task
        if not task.path.exists():
            self.notify("Task directory not found", severity="error")
            return

        worktree = self.current_worktree if isinstance(self.focused, WorktreeList) else None
        self._open_claude_resume_worker(task, worktree)

    @work(thread=True, group="claude_prep")
    def _open_claude_resume_worker(self, task: Task, worktree: Worktree | None = None) -> None:
        """Prepare the session off the UI thread, then open the terminal tab.

        A prep failure is reported but does not block the launch - stale
        CLAUDE.md content is not worth failing the session over. When no
        background session can start, Claude runs inside the tab as before.
        """
        try:
            self._prepare_claude_session(task)
        except Exception as e:
            self.call_from_thread(
                self.notify,
                escape(f"Claude session prep failed for '{task.name}': {type(e).__name__}: {e}"),
                severity="warning",
            )
        if self.config.claude_background:
            try:
                with self._claude_bg_lock:
                    self._open_claude_background(task, worktree)
                return
            except BackgroundError as e:
                self.call_from_thread(
                    self.notify,
                    escape(f"No background Claude session ({e}); running Claude in the tab"),
                    severity="warning",
                )
        resume = has_claude_session(task.path)
        if get_current_worker().is_cancelled:
            return
        self.call_from_thread(self._open_claude_resume_tab, task.path, resume)

    def _open_claude_background(self, task: Task, worktree: Worktree | None) -> None:
        """Show the background Claude session in a tab, starting one if needed.

        Runs in the claude_prep worker. An open tab is reused before asking
        Claude anything. A dispatched agent of the focused worktree wins over
        the task folder's session. With no session the folder's last
        transcript is resumed; Claude open in another terminal is left alone.
        Raises BackgroundError when no session can be found or started.
        """
        claude = self.config.claude_path
        tabs = self._zellij_tab_names()
        sessions: list[AgentSession] | None = None
        for folder in [*([worktree.path] if worktree else []), task.path]:
            if self._zellij_tab_name(folder, "claude") in tabs:
                self.call_from_thread(self._open_terminal_tab, folder, kind="claude")
                return
            if sessions is None:
                sessions = list_agent_sessions(claude, include_done=True)
                if sessions is None:
                    raise BackgroundError("'claude agents' is unavailable")
            session = folder_session(sessions, folder)
            if session:
                self._show_background_session(
                    folder, session.agent_id, f"Opened Claude session {session.agent_id}"
                )
                return
        if foreground_session(sessions or [], task.path):
            self.call_from_thread(
                self.notify,
                escape(f"Claude is already open in '{task.name}' in another terminal"),
                severity="warning",
            )
            return
        latest = latest_session([task.path])
        resume_id = latest.session_id if latest else None
        try:
            agent_id = start_background(claude, task.path, task.name, resume_id)
        except BackgroundError:
            # A timed-out start may still have come up: attach to it, never start a second Claude
            started = folder_session(
                list_agent_sessions(claude, include_done=True) or [], task.path
            )
            if started is None:
                raise
            agent_id = started.agent_id
        verb = "Resumed the last" if resume_id else "Started a"
        self._show_background_session(
            task.path, agent_id, f"{verb} Claude session in the background ({agent_id})"
        )

    def _show_background_session(self, folder: Path, agent_id: str, notice: str) -> None:
        """Open the tab that attaches to a background session (from a worker)."""
        command = attach_command(self.config.claude_path, agent_id)
        self.call_from_thread(
            self._open_terminal_tab, folder, command=command, kind="claude", notice=notice
        )

    def _background_sessions(self, task: Task) -> list[AgentSession] | None:
        """The task's background Claude sessions; None when `claude agents` fails.

        Without the claude CLI there are no sessions to find, so that is not a failure.
        """
        sessions = list_agent_sessions(self.config.claude_path, include_done=True)
        if sessions is None:
            return None if shutil.which(self.config.claude_path) else []
        return background_sessions(sessions, task.path)

    def action_close_claude_tab(self) -> None:
        """Close the zellij Claude tab of the focused task or worktree."""
        if not os.environ.get("ZELLIJ_SESSION_NAME"):
            self.notify("Closing a Claude tab works inside zellij only", severity="warning")
            return
        if isinstance(self.focused, WorktreeList) and self.current_worktree:
            folder = self.current_worktree.path
        elif self.current_task:
            folder = self.current_task.path
        else:
            self.notify("No task selected", severity="warning")
            return
        self._close_claude_tab_worker(folder)

    @work(thread=True, group="terminal_tab")
    def _close_claude_tab_worker(self, folder: Path) -> None:
        """Close the folder's Claude tab when it only runs `claude attach`.

        A tab that runs Claude itself would take Claude with it, so it stays.
        """
        name = self._zellij_tab_name(folder, "claude")
        try:
            tab_id = self._zellij_attach_tab_id(name)
        except LookupError as e:
            self.call_from_thread(self.notify, escape(str(e)), severity="warning")
            return
        try:
            result = self._run_zellij(
                [self.config.zellij_path, "action", "close-tab-by-id", tab_id]
            )
        except (subprocess.SubprocessError, OSError) as e:
            result = subprocess.CompletedProcess([], 1, stdout="", stderr=str(e))
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown error").strip()[:200]
            self.call_from_thread(
                self.notify, escape(f"Could not close '{name}': {detail}"), severity="warning"
            )
            return
        self.call_from_thread(
            self.notify, escape(f"Closed '{name}'; Claude keeps running in the background")
        )

    @work(thread=True, group="claude_notice")
    def _notify_closed_claude_tabs(self, task_names: list[str]) -> None:
        """Say which tasks' Claude finished a turn while no tab shows it."""
        tabs = self._zellij_tab_names()
        key = self.config.keybindings.get("open_claude_resume", "c")
        for name in task_names:
            if self._zellij_tab_name(self.config.tasks_dir / name, "claude") in tabs:
                continue
            message = f"Claude is waiting in '{name}' (tab closed): press {key} to open it"
            self.call_from_thread(self.notify, escape(message))
            self.call_from_thread(self._log_activity, message, MessageLevel.INFO, name)

    def _open_claude_resume_tab(self, task_path: Path, resume: bool) -> None:
        """Open the terminal tab for a prepared Claude session (main thread)."""
        if resume:
            self._open_terminal_tab(
                task_path,
                command=f"{self.config.claude_path} -r",
                kind="claude",
                notice="Opened Claude Code in new tab (resume)",
            )
        else:
            self._open_terminal_tab(
                task_path,
                command=self.config.claude_path,
                kind="claude",
                notice="Opened new Claude Code session in new tab",
            )

    def action_dispatch_agent(self) -> None:
        """Dispatch a background Claude agent in the selected worktree."""
        if not self.current_task or not self.current_worktree:
            self.notify("No worktree selected", severity="warning")
            return
        worktree = self.current_worktree
        task = self.current_task
        if not worktree.path.exists():
            self.notify("Worktree directory not found", severity="error")
            return

        session_name = f"{task.name}/{worktree.name}"

        def handle_prompt(prompt: str | None) -> None:
            if not prompt:
                return
            self.notify(escape(f"Dispatching agent in '{worktree.name}'…"))
            self._dispatch_agent_worker(
                task, session_name, worktree.name, str(worktree.path), prompt
            )

        self.push_screen(DispatchAgentModal(session_name), handle_prompt)

    @work(thread=True, group="agent_dispatch")
    def _dispatch_agent_worker(
        self, task: Task, session_name: str, wt_name: str, wt_path: str, prompt: str
    ) -> None:
        """Prepare the session, then run `claude --bg` in the worktree.

        Deliberately not exclusive: dispatching agents to different worktrees
        in parallel is legitimate. `--bg` detaches and returns promptly; the
        30s timeout only guards against a hung CLI. Session prep can shell
        out to git per worktree, so it belongs in this thread worker too -
        never on the UI thread. A prep failure is reported but does not
        block dispatch.
        """
        try:
            self._prepare_claude_session(task)
        except Exception as e:
            self.call_from_thread(
                self.notify,
                escape(f"Claude session prep failed for '{wt_name}': {type(e).__name__}: {e}"),
                severity="warning",
            )
        try:
            # "--" terminates option parsing: a prompt starting with "-"
            # must reach claude as the prompt, not be eaten as CLI flags
            result = subprocess.run(
                [self.config.claude_path, "--bg", "-n", session_name, "--", prompt],
                cwd=wt_path,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=30,
                env=launch_env(),
            )
        except FileNotFoundError:
            self.call_from_thread(
                self._apply_dispatch_result,
                wt_name,
                wt_path,
                False,
                "claude CLI not found (set [tools] claude_path)",
            )
            return
        except subprocess.TimeoutExpired:
            self.call_from_thread(
                self._apply_dispatch_result, wt_name, wt_path, False, "claude --bg timed out"
            )
            return
        except (subprocess.SubprocessError, OSError) as e:
            self.call_from_thread(self._apply_dispatch_result, wt_name, wt_path, False, str(e))
            return
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown error").strip()[:200]
            self.call_from_thread(self._apply_dispatch_result, wt_name, wt_path, False, detail)
            return
        self.call_from_thread(self._apply_dispatch_result, wt_name, wt_path, True, "")

    def _apply_dispatch_result(self, wt_name: str, wt_path: str, ok: bool, detail: str) -> None:
        """Report the dispatch outcome and set an optimistic session badge."""
        if ok:
            self.notify(escape(f"Dispatched Claude agent in '{wt_name}'"))
            self._log_activity(f"Dispatched Claude agent in '{wt_name}'", MessageLevel.SUCCESS)
            # Optimistic badge until the next interval poll reports real
            # state. No immediate poll: `claude agents` often lags the new
            # session and would wipe the badge right back. Skipped entirely
            # when polling is disabled — an uncorrectable badge would stick
            # forever.
            if self.config.agent_poll_interval > 0:
                self._agent_sessions[wt_path] = "working"
                self._push_badges_to_worktree_list()
        else:
            self.notify(escape(f"Agent dispatch failed: {detail}"), severity="error")
            self._log_activity(
                f"Agent dispatch failed in '{wt_name}': {detail}", MessageLevel.ERROR
            )

    def action_open_claude_gui_code(self) -> None:
        """Open Claude desktop app on the Code page in the current task folder."""
        if not self.current_task:
            self.notify("No task selected", severity="warning")
            return

        task = self.current_task
        if not task.path.exists():
            self.notify("Task directory not found", severity="error")
            return

        self._open_claude_gui_code_worker(task)

    @work(thread=True, group="claude_prep")
    def _open_claude_gui_code_worker(self, task: Task) -> None:
        """Prepare the session, then open Claude desktop, off the UI thread."""
        from urllib.parse import quote

        try:
            self._prepare_claude_session(task)
        except Exception as e:
            self.call_from_thread(
                self.notify,
                escape(f"Claude session prep failed for '{task.name}': {type(e).__name__}: {e}"),
                severity="warning",
            )

        encoded_path = quote(str(task.path), safe="")
        url = f"claude://code/new?folder={encoded_path}"
        try:
            result = subprocess.run(["open", url], capture_output=True, text=True)
        except FileNotFoundError:
            self.call_from_thread(
                self.notify, "'open' command not found (macOS only)", severity="error"
            )
            return
        except Exception as e:
            self.call_from_thread(
                self.notify, escape(f"Failed to open Claude desktop: {e}"), severity="error"
            )
            return

        if get_current_worker().is_cancelled:
            return

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown error").strip()
            self.call_from_thread(
                self.notify, escape(f"Failed to open Claude desktop: {detail}"), severity="error"
            )
            self.call_from_thread(
                self._log_activity,
                f"Failed to open Claude desktop for '{task.name}': {detail}",
                MessageLevel.ERROR,
                task.name,
            )
            return
        self.call_from_thread(self.notify, "Opened Claude desktop on Code page")

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
        self._open_terminal_tab(folder_path)

    def _open_terminal_tab(
        self, path, command: str | None = None, kind: str = "shell", notice: str | None = None
    ) -> None:
        """Open a terminal tab at the given path, optionally running a command.

        Inside zellij (ZELLIJ_SESSION_NAME is set) the tab is a zellij tab,
        which keeps running when the terminal window closes, and an open tab
        of the same folder and kind is reused. Elsewhere it is a Ghostty tab
        driven via AppleScript, which works only on macOS.

        Args:
            path: Directory to open the new tab in
            command: Optional shell command to run there (e.g., "claude -r")
            kind: What the tab is for ("shell", "editor", "claude"); part of
                the zellij tab name
            notice: Message shown once a new tab is opened
        """
        if os.environ.get("ZELLIJ_SESSION_NAME"):
            self._open_zellij_tab_worker(Path(path), command, kind, notice)
            return
        safe_path = str(path).replace("'", "'\\''")
        if command:
            shell_cmd = f"cd '{safe_path}' && clear && {command}"
        else:
            shell_cmd = f"cd '{safe_path}' && clear"
        self._open_ghostty_tab_worker(shell_cmd)
        if notice:
            self.notify(escape(notice))

    def _zellij_tab_name(self, path: Path, kind: str) -> str:
        """Tab name: TASK or TASK/repo, then the kind (e.g. "DIC-1/api · claude")."""
        try:
            # The folder name alone is ambiguous for worktrees
            where = str(path.relative_to(self.config.tasks_dir))
        except ValueError:
            where = path.name
        return f"{where} · {kind}"

    def _zellij_tab_argv(self, path: Path, command: str | None, name: str) -> list[str]:
        """Build the `zellij action new-tab` argv for _open_zellij_tab_worker."""
        zellij = self.config.zellij_path
        argv = [zellij, "action", "new-tab", "--name", name, "--cwd", str(path)]
        if command:
            # The tab closes with its command, so a tab found by name still runs it
            argv += ["--close-on-exit", "--", "sh", "-c", command]
        return argv

    @work(thread=True, group="terminal_tab")
    def _open_zellij_tab_worker(
        self, path: Path, command: str | None, kind: str, notice: str | None
    ) -> None:
        """Switch to the open zellij tab of this folder and kind, or open one.

        `go-to-tab-name` exits 0 for a missing name too, so the tab names are
        queried first. The lock keeps two quick key presses from both missing
        the tab and opening it twice.
        """
        name = self._zellij_tab_name(path, kind)
        zellij = self.config.zellij_path
        with self._zellij_lock:
            try:
                query = self._run_zellij([zellij, "action", "query-tab-names"])
                if query.returncode == 0 and name in query.stdout.splitlines():
                    argv = [zellij, "action", "go-to-tab-name", name]
                    done = f"Switched to open tab '{name}'"
                else:
                    argv = self._zellij_tab_argv(path, command, name)
                    done = notice
                result = self._run_zellij(argv)
            except (subprocess.SubprocessError, OSError) as e:
                self.call_from_thread(
                    self.notify, escape(f"Could not open a zellij tab: {e}"), severity="warning"
                )
                return
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown error").strip()[:200]
            self.call_from_thread(
                self.notify, escape(f"Could not open a zellij tab: {detail}"), severity="warning"
            )
        elif done:
            self.call_from_thread(self.notify, escape(done))

    @staticmethod
    def _run_zellij(argv: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10
        )

    def _zellij_tab_names(self) -> list[str]:
        """Names of the open zellij tabs; empty outside zellij or when the query fails."""
        if not os.environ.get("ZELLIJ_SESSION_NAME"):
            return []
        try:
            result = self._run_zellij([self.config.zellij_path, "action", "query-tab-names"])
        except (subprocess.SubprocessError, OSError):
            return []
        return result.stdout.splitlines() if result.returncode == 0 else []

    def _zellij_attach_tab_id(self, name: str) -> str:
        """Stable id (for close-tab-by-id) of the tab `name` whose panes all run `claude attach`.

        Raises LookupError, with the message to show, when the panes cannot
        be listed, the tab is not open, or it runs anything else.
        """
        argv = [self.config.zellij_path, "action", "list-panes", "--all", "--json"]
        try:
            result = self._run_zellij(argv)
            panes = json.loads(result.stdout) if result.returncode == 0 else None
        except (subprocess.SubprocessError, OSError, ValueError):
            panes = None
        if not isinstance(panes, list):
            raise LookupError("Could not list the zellij panes")
        # terminal_command is the pane's launch command, e.g. "sh -c claude attach ID"
        tab = [
            pane
            for pane in panes
            if isinstance(pane, dict) and pane.get("tab_name") == name and not pane.get("is_plugin")
        ]
        if not tab:
            raise LookupError(f"No open tab '{name}'")
        if not all(" attach " in str(pane.get("terminal_command") or "") for pane in tab):
            raise LookupError(f"'{name}' runs Claude itself: closing it would stop Claude")
        return str(tab[0].get("tab_id"))

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

        The lock serializes concurrent invocations: two overlapping runs
        would overwrite each other's clipboard mid-paste and execute a
        command in the wrong tab.
        """
        if sys.platform != "darwin":
            # pbpaste/pbcopy/osascript are macOS-only; a missing binary
            # would raise inside the worker and take the whole app down
            self.call_from_thread(
                self.notify,
                "Opening a terminal tab is only supported with Ghostty on macOS",
                severity="warning",
            )
            return
        with self._ghostty_lock:
            try:
                self._drive_ghostty_tab(shell_cmd)
            except OSError as e:
                self.call_from_thread(
                    self.notify,
                    escape(f"Could not open a Ghostty tab: {e}"),
                    severity="warning",
                )

    def _drive_ghostty_tab(self, shell_cmd: str) -> None:
        """Clipboard/keystroke sequence for _open_ghostty_tab_worker (macOS)."""
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
        if result.returncode != 0 or "not-frontmost" in result.stdout:
            # osascript failed (commonly: missing Automation/Accessibility
            # permission) or Ghostty never came frontmost - keystrokes were
            # not delivered. Leave the command in the clipboard so the user
            # can paste it themselves.
            self.call_from_thread(
                self.notify,
                "Could not drive Ghostty - command left in clipboard, paste to run",
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
        if self._mutation_in_flight():
            # A delete worker can be rmtree'ing these same worktrees right
            # now; pushing into that race would run git against a tree
            # that's disappearing under it.
            self.notify("Another task operation is still running", severity="warning")
            return
        if not self.current_task.worktrees:
            self.notify("Task has no worktrees", severity="information")
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
        if self._mutation_in_flight():
            self.notify("Another task operation is still running", severity="warning")
            return
        if not self.current_task.worktrees:
            self.notify("Task has no worktrees", severity="information")
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


def zellij_autostart_argv(config: Config) -> list[str] | None:
    """The `zellij attach` argv that re-runs this TUI inside zellij, or None to run here.

    Only an interactive start outside zellij re-launches. The command after
    `--` runs only when the session is created; attaching to a running
    session lands on the TUI already in it.
    """
    if not config.zellij_autostart or os.environ.get("ZELLIJ_SESSION_NAME"):
        return None
    if not (os.isatty(0) and os.isatty(1)):
        return None
    zellij = shutil.which(config.zellij_path)
    if zellij is None:
        print(
            f"warning: zellij_autostart is on but {config.zellij_path} is not found",
            file=sys.stderr,
        )
        return None
    me = [sys.executable, "-m", "tasktree_manager.app"]
    return [zellij, "attach", "--create", config.zellij_session, "--", *me]


def main():
    """Entry point: TUI with no arguments, headless CLI otherwise."""
    if len(sys.argv) > 1:
        from .cli import run_cli

        raise SystemExit(run_cli(sys.argv[1:]))
    try:
        argv = zellij_autostart_argv(Config.load())
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None
    if argv:
        try:
            os.execv(argv[0], argv)
        except OSError as e:
            print(f"warning: could not start zellij: {e}", file=sys.stderr)
    try:
        app = TaskTreeApp()
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None
    app.run()


if __name__ == "__main__":
    main()
