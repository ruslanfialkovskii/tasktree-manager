# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

tasktree is a TUI application for managing git worktree-based tasks, styled like lazygit. It allows users to create tasks that span multiple repositories, each with their own worktree.

## Commands

All commands use mise. Run `mise install` first to set up the environment.

```bash
mise run install       # Install dependencies (uses uv pip)
mise run test          # Run all tests
mise run test:cov      # Run tests with coverage
mise run lint          # Run ruff linter
mise run lint:fix      # Auto-fix lint issues
mise run format        # Format code with ruff
mise run dev           # Run app in Textual dev mode with console
mise run run           # Run the app normally
```

Run a single test:
```bash
pytest tests/test_app.py::TestTaskTreeApp::test_app_starts -v
```

## Architecture

### Core Data Model

- **Task**: A named task (e.g., "DIC-1813") containing multiple worktrees, stored as a directory in `TASKS_DIR` (~/.wtasks)
- **Worktree**: A git worktree within a task, created from a repo in `REPOS_DIR` (~/repos). Branch name matches task name.
- **GitStatus**: Status info for a worktree (branch, staged/modified/untracked files, ahead/behind counts)

### Services Layer (`tasktree/services/`)

- `config.py`: Loads configuration from environment variables (`REPOS_DIR`, `TASKS_DIR`)
- `task_manager.py`: CRUD operations for tasks and worktrees (creates git worktrees via subprocess)
- `git_ops.py`: Git status queries, push/pull operations (all via subprocess)

### Themes (`tasktree/themes/`)

Dynamic theming system with 3 built-in themes:
- **vscode-dark**: VS Code Dark theme (default)
- **vscode-light**: VS Code Light theme
- **catppuccin**: Catppuccin Mocha theme

Themes are defined as `Theme` dataclass with colors for: background, foreground, borders, highlights, accent, success/warning/error.

The `generate_css()` function creates Textual CSS from a theme. Press `t` to cycle themes at runtime.

### Widgets Layer (`tasktree/widgets/`)

All widgets extend Textual's `ListView` or `Static`:
- `task_list.py`: Left panel showing tasks with dirty indicators
- `worktree_list.py`: Right panel showing worktrees for selected task
- `status_panel.py`: Bottom panel showing git status for selected worktree
- `create_modal.py`: Modal dialogs (all extend `ThemedModalScreen` base class)

Widgets get theme colors via `_get_theme()` helper that reads `app.theme_name`.

### App (`tasktree/app.py`)

`TaskTreeApp` is the main Textual App. It:
- Composes the 3-panel layout
- Handles message events from list widgets (`TaskHighlighted`, `WorktreeHighlighted`)
- Implements actions for keybindings (n=new task, d=delete, g=lazygit, t=theme, etc.)
- Uses `app.suspend()` to shell out to lazygit or $SHELL
- Provides `css` property that returns dynamically generated CSS from current theme

### Styling Pattern

CSS is generated dynamically from `Theme` objects in `tasktree/themes/__init__.py`:
- `generate_css(theme)` creates main app CSS
- Modals use `DEFAULT_CSS` class attribute with hardcoded colors, then `_apply_theme_styles()` updates widget styles on mount
- List items need `.--highlight` styling for both the ListItem and its child Static widget

## Testing

Tests use pytest-asyncio for async Textual widget testing. The `conftest.py` creates:
- Temporary repos/tasks directories
- Real git repos with initial commits for integration tests
- Fixtures: `config`, `task_manager`, `sample_repo`, `sample_repos`, `app`

Example test pattern for Textual apps:
```python
async def test_app_starts():
    async with TaskTreeApp().run_test() as pilot:
        assert pilot.app.query_one("#task-list")
```
