"""Command palette provider for tasktree-manager actions."""

from functools import partial

from textual.command import DiscoveryHit, Hit, Hits, Provider

# (action, title, help) for every keybound app action. The key for each
# action is looked up from the app's config at search time so customized
# keybindings display correctly.
APP_COMMANDS: list[tuple[str, str, str]] = [
    ("new_task", "New Task", "Create a new task with worktrees"),
    ("clone_task", "Clone Task", "Create a new task with the same repos as the current one"),
    ("add_repo", "Add Repo", "Add repositories to the current task"),
    ("delete_task", "Delete Task", "Delete the current task (with safety checks)"),
    ("delete_worktree", "Delete Worktree", "Delete the selected worktree from the task"),
    ("open_lazygit", "Open Lazygit", "Open lazygit in the selected worktree"),
    ("open_editor", "Open Editor", "Open your editor in the focused task/worktree folder"),
    ("open_folder", "Open Folder", "Open the focused folder in a new terminal tab"),
    ("open_shell", "Open Shell", "Open a shell in the selected worktree"),
    ("open_claude_resume", "Open Claude", "Open Claude Code for the task (resume if possible)"),
    (
        "open_claude_gui_code",
        "Open Claude Desktop",
        "Open the Claude desktop app on the Code page",
    ),
    ("push_all", "Push All", "Push all worktrees in the current task"),
    ("pull_all", "Pull All", "Pull all worktrees in the current task"),
    ("refresh", "Refresh", "Refresh git status for all tasks"),
    ("toggle_messages", "Toggle Messages", "Show or hide the activity messages panel"),
    ("toggle_grouping", "Toggle Grouping", "Group worktrees by dirty/clean status"),
    ("cycle_sort", "Cycle Sort", "Cycle through task sort modes"),
    ("help", "Help", "Show the keybinding reference"),
    ("quit", "Quit", "Exit tasktree-manager"),
]


class TaskTreeCommands(Provider):
    """Expose all keybound tasktree actions in the command palette."""

    def _entries(self):
        """Yield (display title with hotkey, action, help) tuples."""
        config = getattr(self.app, "config", None)
        keybindings = config.keybindings if config else {}
        for action, title, help_text in APP_COMMANDS:
            key = keybindings.get(action, "")
            display = f"{title} ({key})" if key else title
            yield display, action, help_text

    async def discover(self) -> Hits:
        """List all commands when the palette opens with an empty query."""
        for display, action, help_text in self._entries():
            yield DiscoveryHit(
                display,
                partial(self.app.run_action, action),
                help=help_text,
            )

    async def search(self, query: str) -> Hits:
        """Fuzzy-match commands against the query."""
        matcher = self.matcher(query)
        for display, action, help_text in self._entries():
            score = matcher.match(display)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(display),
                    partial(self.app.run_action, action),
                    help=help_text,
                )
