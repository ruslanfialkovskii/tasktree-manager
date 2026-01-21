"""Main application for tasktree."""

import os
import subprocess

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer, Header, Static

from .services.config import Config
from .services.git_ops import GitOps, GitStatus
from .services.task_manager import Task, TaskManager, Worktree
from .widgets.create_modal import AddRepoModal, ConfirmModal, CreateTaskModal, HelpModal
from .widgets.status_panel import StatusPanel
from .widgets.task_list import TaskList
from .widgets.worktree_list import WorktreeList


class TaskTreeApp(App):
    """TUI application for managing worktree-based tasks."""

    CSS_PATH = "styles/app.tcss"
    TITLE = "tasktree"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("?", "help", "Help"),
        Binding("n", "new_task", "New Task"),
        Binding("a", "add_repo", "Add Repo"),
        Binding("d", "delete_task", "Delete Task"),
        Binding("g", "open_lazygit", "Lazygit"),
        Binding("enter", "open_shell", "Shell", show=False),
        Binding("p", "push_all", "Push All"),
        Binding("P", "pull_all", "Pull All", show=False),
        Binding("r", "refresh", "Refresh"),
        Binding("tab", "focus_next", "Next Panel", show=False),
        Binding("shift+tab", "focus_previous", "Prev Panel", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.config = Config.load()
        self.config.ensure_dirs()
        self.task_manager = TaskManager(self.config)
        self.current_task: Task | None = None
        self.current_worktree: Worktree | None = None
        self.current_status: GitStatus | None = None

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
        yield Footer()

    def on_mount(self) -> None:
        """Handle app mount."""
        self._load_tasks()
        # Focus the task list initially
        task_list = self.query_one("#task-list", TaskList)
        task_list.focus()

    def _load_tasks(self) -> None:
        """Load tasks and update git status."""
        tasks = self.task_manager.list_tasks()

        # Update git status for all worktrees
        for task in tasks:
            for worktree in task.worktrees:
                GitOps.update_worktree_status(worktree)

        task_list = self.query_one("#task-list", TaskList)
        task_list.load_tasks(tasks)

    def _refresh_current_task(self) -> None:
        """Refresh the current task's worktrees and status."""
        if self.current_task:
            task = self.task_manager.get_task(self.current_task.name)
            if task:
                for worktree in task.worktrees:
                    GitOps.update_worktree_status(worktree)
                self.current_task = task
                worktree_list = self.query_one("#worktree-list", WorktreeList)
                worktree_list.load_worktrees(task.worktrees)

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
        """Show help modal."""
        self.push_screen(HelpModal())

    def action_new_task(self) -> None:
        """Create a new task."""
        available_repos = self.config.get_available_repos()
        if not available_repos:
            self.notify("No repositories found in REPOS_DIR", severity="warning")
            return

        def handle_result(result):
            if result:
                name, repos, base_branch = result
                try:
                    self.task_manager.create_task(name, repos, base_branch)
                    self._load_tasks()
                    self.notify(f"Created task: {name}")
                except Exception as e:
                    self.notify(f"Failed to create task: {e}", severity="error")

        self.push_screen(CreateTaskModal(available_repos), handle_result)

    def action_add_repo(self) -> None:
        """Add repos to the current task."""
        if not self.current_task:
            self.notify("No task selected", severity="warning")
            return

        available_repos = self.task_manager.get_repos_not_in_task(self.current_task)
        if not available_repos:
            self.notify("All repositories already in task", severity="info")
            return

        def handle_result(result):
            if result and self.current_task:
                repos, base_branch = result
                try:
                    for repo in repos:
                        self.task_manager.add_repo_to_task(self.current_task, repo, base_branch)
                    self._load_tasks()
                    self._refresh_current_task()
                    self.notify(f"Added {len(repos)} repo(s) to task")
                except Exception as e:
                    self.notify(f"Failed to add repos: {e}", severity="error")

        self.push_screen(AddRepoModal(self.current_task.name, available_repos), handle_result)

    def action_delete_task(self) -> None:
        """Delete/finish the current task."""
        if not self.current_task:
            self.notify("No task selected", severity="warning")
            return

        task = self.current_task
        dirty_warning = ""
        if task.is_dirty:
            dirty_warning = f"\n\nWARNING: {task.dirty_count} worktree(s) have uncommitted changes!"

        message = f"Delete task '{task.name}' and all its worktrees?{dirty_warning}"

        def handle_result(confirmed):
            if confirmed:
                try:
                    self.task_manager.finish_task(task)
                    self._load_tasks()
                    self.notify(f"Deleted task: {task.name}")
                except Exception as e:
                    self.notify(f"Failed to delete task: {e}", severity="error")

        self.push_screen(ConfirmModal("Delete Task", message), handle_result)

    def action_open_lazygit(self) -> None:
        """Open lazygit in the current worktree."""
        if not self.current_worktree:
            self.notify("No worktree selected", severity="warning")
            return

        worktree_path = self.current_worktree.path
        if not worktree_path.exists():
            self.notify("Worktree directory not found", severity="error")
            return

        # Suspend app and run lazygit
        with self.suspend():
            subprocess.run(["lazygit"], cwd=worktree_path)

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

        # Get user's shell
        shell = os.environ.get("SHELL", "/bin/bash")

        # Suspend app and open shell
        with self.suspend():
            subprocess.run([shell], cwd=worktree_path)

        # Refresh status after shell exits
        self._load_tasks()
        self._refresh_current_task()

    def action_push_all(self) -> None:
        """Push all worktrees in the current task."""
        if not self.current_task:
            self.notify("No task selected", severity="warning")
            return

        self.notify(f"Pushing all worktrees in {self.current_task.name}...")
        results = GitOps.push_all(self.current_task)

        success_count = sum(1 for _, success, _ in results if success)
        fail_count = len(results) - success_count

        if fail_count == 0:
            self.notify(f"Pushed {success_count} worktree(s) successfully")
        else:
            self.notify(f"Pushed {success_count}, failed {fail_count}", severity="warning")

        self._refresh_current_task()

    def action_pull_all(self) -> None:
        """Pull all worktrees in the current task."""
        if not self.current_task:
            self.notify("No task selected", severity="warning")
            return

        self.notify(f"Pulling all worktrees in {self.current_task.name}...")
        results = GitOps.pull_all(self.current_task)

        success_count = sum(1 for _, success, _ in results if success)
        fail_count = len(results) - success_count

        if fail_count == 0:
            self.notify(f"Pulled {success_count} worktree(s) successfully")
        else:
            self.notify(f"Pulled {success_count}, failed {fail_count}", severity="warning")

        self._refresh_current_task()

    def action_refresh(self) -> None:
        """Refresh all status."""
        self._load_tasks()
        self._refresh_current_task()
        self.notify("Refreshed")

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
