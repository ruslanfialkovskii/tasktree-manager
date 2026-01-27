"""Main application for tasktree."""

import shutil
import subprocess

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer, Header, Static

from .services.config import Config
from .services.git_ops import GitOps, GitStatus
from .services.task_manager import Task, TaskManager, Worktree
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

    TITLE = "tasktree"

    CSS = """
    /* Main layout */
    Screen {
        background: $background;
    }

    #main-container {
        height: 100%;
        width: 100%;
        background: $background;
    }

    #top-panels {
        height: 1fr;
        min-height: 10;
    }

    /* Task panel */
    #task-panel {
        width: 30%;
        min-width: 20;
        border: round $primary;
        background: $background;
        padding: 0;
    }

    #task-panel:focus-within {
        border: round $accent;
    }

    /* Worktree panel */
    #worktree-panel {
        width: 70%;
        border: round $primary;
        background: $background;
        padding: 0;
    }

    #worktree-panel:focus-within {
        border: round $accent;
    }

    /* Status panel */
    #status-panel {
        height: auto;
        min-height: 6;
        max-height: 12;
        border: round $primary;
        background: $background;
        padding: 0;
    }

    /* Panel titles */
    .panel-title {
        text-style: bold;
        color: $text;
        background: transparent;
        text-align: left;
        width: 100%;
        padding: 0 1;
    }

    /* Task list */
    #task-list {
        height: 1fr;
        background: $background;
        scrollbar-gutter: stable;
        padding: 0;

        & > ListItem {
            padding: 0 1;
            height: 1;
            background: $background;
            color: $text;

            &.--highlight {
                background: $surface;

                & .task-item-text {
                    background: $surface;
                }
            }
        }

        &:focus > ListItem.--highlight {
            background: $accent;

            & .task-item-text {
                background: $accent;
            }
        }
    }

    .task-item-text {
        width: 100%;
        background: transparent;
    }

    /* Worktree list */
    #worktree-list {
        height: 1fr;
        background: $background;
        scrollbar-gutter: stable;
        padding: 0;

        & > ListItem {
            padding: 0 1;
            height: 1;
            background: $background;
            color: $text;

            &.--highlight {
                background: $surface;

                & .worktree-item-text {
                    background: $surface;
                }
            }
        }

        &:focus > ListItem.--highlight {
            background: $accent;

            & .worktree-item-text {
                background: $accent;
            }
        }
    }

    .worktree-item-text {
        width: 100%;
        background: transparent;
    }

    /* Status panel styling */
    #status-display {
        height: 100%;
        padding: 0 1;
        background: $background;
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
        height: auto;
        min-height: 6;
        max-height: 12;
        border: round $primary;
        background: $background;
        padding: 0;
        display: none;
    }

    #messages-panel.-visible {
        display: block;
    }

    #messages-display {
        height: 100%;
        padding: 0 1;
        background: $background;
        color: $text;
        overflow-y: auto;
        scrollbar-gutter: stable;
    }

    /* Header */
    Header {
        background: $surface;
        color: $text;
        text-style: bold;
        dock: top;
        height: 1;
    }

    /* Footer */
    Footer {
        background: $surface;
    }

    /* Scrollbar */
    Scrollbar {
        background: $background;
    }

    ScrollBar > .scrollbar--bar {
        background: $panel;
    }

    ScrollBar > .scrollbar--bar:hover {
        background: $foreground-muted;
    }

    ListItem {
        height: 1;
    }
    """

    # Default bindings - will be overridden in __init__ with config values
    # Footer order: n, a, d, g, o, p, r, m, q, ?
    BINDINGS = [
        Binding("n", "new_task", "New Task"),
        Binding("a", "add_repo", "Add Repo"),
        Binding("d", "delete_task", "Delete Task"),
        Binding("g", "open_lazygit", "Lazygit"),
        Binding("o", "open_folder", "Open"),
        Binding("p", "push_all", "Push All"),
        Binding("r", "refresh", "Refresh"),
        Binding("m", "toggle_messages", "Messages"),
        Binding("q", "quit", "Quit"),
        Binding("?", "help", "Help"),
        Binding("enter", "open_shell", "Shell", show=False),
        Binding("P", "pull_all", "Pull All", show=False),
        Binding("tab", "focus_next", "Next Panel", show=False),
        Binding("shift+tab", "focus_previous", "Prev Panel", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def __init__(self):
        # Load config before calling super().__init__() so we can set up bindings
        self.config = Config.load()
        self.config.ensure_dirs()

        # Build bindings from config
        self._custom_bindings = self._build_bindings_from_config()

        super().__init__()
        self.task_manager = TaskManager(self.config)
        self.current_task: Task | None = None
        self.current_worktree: Worktree | None = None
        self.current_status: GitStatus | None = None
        self._show_messages_panel: bool = False

    def _build_bindings_from_config(self) -> list[Binding]:
        """Build keybindings list from config.

        Returns:
            List of Binding objects with keys from config
        """
        kb = self.config.keybindings
        # Footer order: n, a, d, g, o, p, r, m, q, ?
        return [
            Binding(kb.get("new_task", "n"), "new_task", "New Task"),
            Binding(kb.get("add_repo", "a"), "add_repo", "Add Repo"),
            Binding(kb.get("delete_task", "d"), "delete_task", "Delete Task"),
            Binding(kb.get("open_lazygit", "g"), "open_lazygit", "Lazygit"),
            Binding(kb.get("open_folder", "o"), "open_folder", "Open"),
            Binding(kb.get("push_all", "p"), "push_all", "Push All"),
            Binding(kb.get("refresh", "r"), "refresh", "Refresh"),
            Binding(kb.get("toggle_messages", "m"), "toggle_messages", "Messages"),
            Binding(kb.get("quit", "q"), "quit", "Quit"),
            Binding(kb.get("help", "?"), "help", "Help"),
            Binding(kb.get("open_shell", "enter"), "open_shell", "Shell", show=False),
            Binding(kb.get("pull_all", "P"), "pull_all", "Pull All", show=False),
            Binding(kb.get("focus_next", "tab"), "focus_next", "Next Panel", show=False),
            Binding(
                kb.get("focus_previous", "shift+tab"), "focus_previous", "Prev Panel", show=False
            ),
            Binding(kb.get("cursor_down", "j"), "cursor_down", "Down", show=False),
            Binding(kb.get("cursor_up", "k"), "cursor_up", "Up", show=False),
        ]

    @property
    def _binding_list(self) -> list[Binding]:
        """Override to use custom bindings from config."""
        return self._custom_bindings

    def compose(self) -> ComposeResult:
        """Compose the app layout."""
        yield Header()
        with Container(id="main-container"):
            with Horizontal(id="top-panels"):
                with Vertical(id="task-panel"):
                    yield Static("Tasks", classes="panel-title")
                    yield TaskList(id="task-list")
                with Vertical(id="worktree-panel"):
                    yield Static("Worktrees", classes="panel-title")
                    yield WorktreeList(id="worktree-list")
            with Vertical(id="status-panel"):
                yield StatusPanel(id="status-display")
            with Vertical(id="messages-panel"):
                yield MessagesPanel(id="messages-display")
        yield Footer()

    def on_mount(self) -> None:
        """Handle app mount."""
        # Apply theme from config
        if self.config.theme:
            try:
                self.theme = self.config.theme
            except Exception:
                # Invalid theme name, use default
                pass

        # Check if configuration is valid
        if not self.config.is_configured():
            self._show_setup_wizard()
        else:
            self._load_tasks()
            # Focus the task list initially
            task_list = self.query_one("#task-list", TaskList)
            task_list.focus()

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

    def _load_tasks(self) -> None:
        """Load tasks and update git status."""
        task_list = self.query_one("#task-list", TaskList)
        task_list.loading = True
        try:
            tasks = self.task_manager.list_tasks()

            # Collect all worktrees and update in parallel
            all_worktrees = [wt for task in tasks for wt in task.worktrees]
            GitOps.update_all_worktree_statuses(all_worktrees)

            task_list.load_tasks(tasks)
        finally:
            task_list.loading = False

    def _refresh_current_task(self) -> None:
        """Refresh the current task's worktrees and status."""
        if self.current_task:
            task = self.task_manager.get_task(self.current_task.name)
            if task:
                GitOps.update_all_worktree_statuses(task.worktrees)
                self.current_task = task
                worktree_list = self.query_one("#worktree-list", WorktreeList)
                worktree_list.load_worktrees(task.worktrees)

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
        if not shutil.which(cmd[0]):
            hint = f" Install with: {install_hint}" if install_hint else ""
            self.notify(f"{name} not found.{hint}", severity="error")
            return False
        try:
            subprocess.run(cmd, cwd=cwd)
            return True
        except FileNotFoundError:
            hint = f" Install with: {install_hint}" if install_hint else ""
            self.notify(f"{name} not found.{hint}", severity="error")
            return False
        except PermissionError:
            self.notify(f"Permission denied running {name}", severity="error")
            return False
        except Exception as e:
            self.notify(f"Failed to run {name}: {e}", severity="error")
            return False

    def on_task_list_task_highlighted(self, event: TaskList.TaskHighlighted) -> None:
        """Handle task highlight in task list."""
        self.current_task = event.task
        worktree_list = self.query_one("#worktree-list", WorktreeList)
        status_panel = self.query_one("#status-display", StatusPanel)

        if event.task:
            worktree_list.load_worktrees(event.task.worktrees)
        else:
            worktree_list.clear_worktrees()
            status_panel.clear_status()

    def on_worktree_list_worktree_highlighted(
        self, event: WorktreeList.WorktreeHighlighted
    ) -> None:
        """Handle worktree highlight in worktree list."""
        self.current_worktree = event.worktree
        status_panel = self.query_one("#status-display", StatusPanel)

        if event.worktree:
            status_panel.set_loading(True)
            status = GitOps.get_status(event.worktree)
            self.current_status = status
            status_panel.update_status(event.worktree, status)
        else:
            self.current_status = None
            status_panel.clear_status()

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
                task_list = self.query_one("#task-list", TaskList)
                task_list.loading = True
                try:
                    self.task_manager.create_task(name, repos, base_branch)
                    self._load_tasks()
                    self.notify(f"Created task: {name}")
                    self._log_activity(
                        f"Task '{name}' created with {len(repos)} repo(s)",
                        MessageLevel.SUCCESS,
                        name,
                    )
                except FileNotFoundError as e:
                    self.notify(f"Repository not found: {e}", severity="error")
                    self._log_activity(
                        f"Failed to create task: {e}", MessageLevel.ERROR, name
                    )
                except PermissionError:
                    self.notify("Permission denied: check directory permissions", severity="error")
                    self._log_activity(
                        "Failed to create task: permission denied", MessageLevel.ERROR, name
                    )
                except ValueError as e:
                    # ValueError from task_manager has good messages
                    self.notify(str(e), severity="error")
                    self._log_activity(f"Failed to create task: {e}", MessageLevel.ERROR, name)
                except Exception as e:
                    self.notify(f"Failed to create task: {type(e).__name__}: {e}", severity="error")
                    self._log_activity(f"Failed to create task: {e}", MessageLevel.ERROR, name)
                finally:
                    task_list.loading = False

        self.push_screen(CreateTaskModal(available_repos), handle_result)

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
                task_list = self.query_one("#task-list", TaskList)
                worktree_list = self.query_one("#worktree-list", WorktreeList)
                task_list.loading = True
                worktree_list.loading = True
                task_name = self.current_task.name
                try:
                    for repo in repos:
                        self.task_manager.add_repo_to_task(self.current_task, repo, base_branch)
                    self._load_tasks()
                    self._refresh_current_task()
                    self.notify(f"Added {len(repos)} repo(s) to task")
                    self._log_activity(
                        f"Added {len(repos)} repo(s) to task '{task_name}'",
                        MessageLevel.SUCCESS,
                        task_name,
                    )
                except FileNotFoundError as e:
                    self.notify(f"Repository not found: {e}", severity="error")
                    self._log_activity(
                        f"Failed to add repos: {e}", MessageLevel.ERROR, task_name
                    )
                except PermissionError:
                    self.notify("Permission denied: check directory permissions", severity="error")
                    self._log_activity(
                        "Failed to add repos: permission denied", MessageLevel.ERROR, task_name
                    )
                except ValueError as e:
                    # ValueError from task_manager has good messages
                    self.notify(str(e), severity="error")
                    self._log_activity(f"Failed to add repos: {e}", MessageLevel.ERROR, task_name)
                except Exception as e:
                    self.notify(f"Failed to add repos: {type(e).__name__}: {e}", severity="error")
                    self._log_activity(f"Failed to add repos: {e}", MessageLevel.ERROR, task_name)
                finally:
                    task_list.loading = False
                    worktree_list.loading = False

        self.push_screen(AddRepoModal(self.current_task.name, available_repos), handle_result)

    def action_delete_task(self) -> None:
        """Delete/finish the current task with safety checks."""
        if not self.current_task:
            self.notify("No task selected", severity="warning")
            return

        task = self.current_task

        # Run safety checks
        safety_report = self.task_manager.check_task_safety(task)

        if safety_report.is_safe():
            # No issues - show simple confirm
            message = f"Delete task '{task.name}' and all its worktrees?"

            def handle_confirm(confirmed):
                if confirmed:
                    try:
                        self.task_manager.finish_task(task)
                        self._load_tasks()
                        self.notify(f"Deleted task: {task.name}")
                        self._log_activity(
                            f"Task '{task.name}' deleted", MessageLevel.SUCCESS, task.name
                        )
                    except Exception as e:
                        self.notify(f"Failed to delete task: {e}", severity="error")
                        self._log_activity(
                            f"Failed to delete task: {e}", MessageLevel.ERROR, task.name
                        )

            self.push_screen(ConfirmModal("Delete Task", message), handle_confirm)
        else:
            # Issues found - show detailed safe delete modal
            def handle_safe_delete(action):
                if action == "push":
                    # Push all branches
                    self.notify(f"Pushing all branches for {task.name}...")
                    success_repos, failed_repos = self.task_manager.push_all_branches(task)

                    # Show results
                    if failed_repos:

                        def handle_push_result(_):
                            # Re-check safety after push
                            new_report = self.task_manager.check_task_safety(task)
                            if new_report.is_safe():
                                # Now safe, ask to delete
                                def final_confirm(confirmed):
                                    if confirmed:
                                        try:
                                            self.task_manager.finish_task(task)
                                            self._load_tasks()
                                            self.notify(f"Deleted task: {task.name}")
                                            self._log_activity(
                                                f"Task '{task.name}' deleted",
                                                MessageLevel.SUCCESS,
                                                task.name,
                                            )
                                        except Exception as e:
                                            self.notify(
                                                f"Failed to delete task: {e}", severity="error"
                                            )
                                            self._log_activity(
                                                f"Failed to delete task: {e}",
                                                MessageLevel.ERROR,
                                                task.name,
                                            )

                                self.push_screen(
                                    ConfirmModal("Delete Task", f"Delete task '{task.name}'?"),
                                    final_confirm,
                                )
                            else:
                                # Still has issues, show modal again
                                self.push_screen(
                                    SafeDeleteModal(task.name, new_report), handle_safe_delete
                                )

                        self.push_screen(
                            PushResultModal(success_repos, failed_repos), handle_push_result
                        )
                    else:
                        # All pushed successfully
                        self.notify(f"Pushed {len(success_repos)} branch(es) successfully")
                        # Re-check safety
                        new_report = self.task_manager.check_task_safety(task)
                        if new_report.is_safe():
                            # Now safe, ask to delete
                            def final_confirm(confirmed):
                                if confirmed:
                                    try:
                                        self.task_manager.finish_task(task)
                                        self._load_tasks()
                                        self.notify(f"Deleted task: {task.name}")
                                        self._log_activity(
                                            f"Task '{task.name}' deleted",
                                            MessageLevel.SUCCESS,
                                            task.name,
                                        )
                                    except Exception as e:
                                        self.notify(f"Failed to delete task: {e}", severity="error")
                                        self._log_activity(
                                            f"Failed to delete task: {e}",
                                            MessageLevel.ERROR,
                                            task.name,
                                        )

                            self.push_screen(
                                ConfirmModal("Delete Task", f"Delete task '{task.name}'?"),
                                final_confirm,
                            )
                        else:
                            # Still has issues, show modal again
                            self.push_screen(
                                SafeDeleteModal(task.name, new_report), handle_safe_delete
                            )

                elif action == "lazygit":
                    # Open lazygit in first problematic worktree
                    self._open_lazygit_for_task(task)
                    # After return, refresh and offer to try deletion again
                    self.action_delete_task()

                elif action == "force":
                    # Final confirmation before force delete
                    message = f"Really delete task '{task.name}'?\n\nYou may lose unpushed work!"

                    def handle_force_confirm(confirmed):
                        if confirmed:
                            try:
                                self.task_manager.finish_task(task)
                                self._load_tasks()
                                self.notify(f"Deleted task: {task.name}")
                                self._log_activity(
                                    f"Task '{task.name}' deleted (force)",
                                    MessageLevel.SUCCESS,
                                    task.name,
                                )
                            except Exception as e:
                                self.notify(f"Failed to delete task: {e}", severity="error")
                                self._log_activity(
                                    f"Failed to delete task: {e}",
                                    MessageLevel.ERROR,
                                    task.name,
                                )

                    self.push_screen(ConfirmModal("Force Delete", message), handle_force_confirm)

                # else: cancelled, do nothing

            self.push_screen(SafeDeleteModal(task.name, safety_report), handle_safe_delete)

    def _open_lazygit_for_task(self, task: Task) -> None:
        """Open lazygit in the first worktree with issues.

        Args:
            task: The task whose worktrees to check
        """
        # Get safety report to find first problematic worktree
        safety_report = self.task_manager.check_task_safety(task)

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

            # Refresh status after lazygit exits
            self._load_tasks()
            self._refresh_current_task()
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

        self.notify("Opening lazygit...")

        # Suspend app and run lazygit
        with self.suspend():
            self._run_external_command(
                [self.config.lazygit_path],
                cwd=worktree_path,
                name="lazygit",
                install_hint="brew install lazygit",
            )

        # Refresh status after lazygit exits
        self._load_tasks()
        self._refresh_current_task()

    def action_open_shell(self) -> None:
        """Open a shell in the current worktree."""
        if not self.current_worktree:
            self.notify("No worktree selected", severity="warning")
            return

        worktree_path = self.current_worktree.path
        if not worktree_path.exists():
            self.notify("Worktree directory not found", severity="error")
            return

        # Get shell from config
        shell = self.config.get_shell()

        self.notify("Opening shell...")

        # Suspend app and open shell
        with self.suspend():
            self._run_external_command([shell], cwd=worktree_path, name="shell")

        # Refresh status after shell exits
        self._load_tasks()
        self._refresh_current_task()

    def action_open_folder(self) -> None:
        """Open current folder in a new terminal tab."""
        from pathlib import Path

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

    def _open_terminal_tab(self, path) -> None:
        """Open a new terminal tab at the given path (Ghostty)."""
        # Ghostty: Use AppleScript to activate and open new tab, then cd
        script = f'''
        tell application "Ghostty"
            activate
        end tell
        tell application "System Events"
            tell process "Ghostty"
                keystroke "t" using command down
                delay 0.1
                keystroke "cd '{path}' && clear"
                key code 36
            end tell
        end tell
        '''
        subprocess.run(["osascript", "-e", script], capture_output=True)

    def action_push_all(self) -> None:
        """Push all worktrees in the current task."""
        if not self.current_task:
            self.notify("No task selected", severity="warning")
            return

        task_name = self.current_task.name
        worktree_list = self.query_one("#worktree-list", WorktreeList)
        worktree_list.loading = True
        try:
            self.notify(f"Pushing all worktrees in {task_name}...")
            results = GitOps.push_all_parallel(self.current_task)

            success_count = sum(1 for _, success, _ in results if success)
            fail_count = len(results) - success_count

            if fail_count == 0:
                self.notify(f"Pushed {success_count} worktree(s) successfully")
                self._log_activity(
                    f"Pushed {success_count} worktree(s) for '{task_name}'",
                    MessageLevel.SUCCESS,
                    task_name,
                )
            else:
                self.notify(f"Pushed {success_count}, failed {fail_count}", severity="warning")
                self._log_activity(
                    f"Push: {success_count} succeeded, {fail_count} failed for '{task_name}'",
                    MessageLevel.WARNING,
                    task_name,
                )

            self._refresh_current_task()
        finally:
            worktree_list.loading = False

    def action_pull_all(self) -> None:
        """Pull all worktrees in the current task."""
        if not self.current_task:
            self.notify("No task selected", severity="warning")
            return

        task_name = self.current_task.name
        worktree_list = self.query_one("#worktree-list", WorktreeList)
        worktree_list.loading = True
        try:
            self.notify(f"Pulling all worktrees in {task_name}...")
            results = GitOps.pull_all_parallel(self.current_task)

            success_count = sum(1 for _, success, _ in results if success)
            fail_count = len(results) - success_count

            if fail_count == 0:
                self.notify(f"Pulled {success_count} worktree(s) successfully")
                self._log_activity(
                    f"Pulled {success_count} worktree(s) for '{task_name}'",
                    MessageLevel.SUCCESS,
                    task_name,
                )
            else:
                self.notify(f"Pulled {success_count}, failed {fail_count}", severity="warning")
                self._log_activity(
                    f"Pull: {success_count} succeeded, {fail_count} failed for '{task_name}'",
                    MessageLevel.WARNING,
                    task_name,
                )

            self._refresh_current_task()
        finally:
            worktree_list.loading = False

    def action_refresh(self) -> None:
        """Refresh all status."""
        self._load_tasks()
        self._refresh_current_task()
        self.notify("Refreshed")

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


def main():
    """Entry point for the tasktree application."""
    app = TaskTreeApp()
    app.run()


if __name__ == "__main__":
    main()
