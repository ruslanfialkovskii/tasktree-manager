# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

tasktree-manager is a TUI application for managing git worktree-based tasks, styled like lazygit. It allows users to create tasks that span multiple repositories, each with their own worktree.

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
- **Epic**: A task folder marked `.tasktree_kind` = `epic` that groups other tasks; a child task names its epic in `.tasktree_epic`. Read lazily by `Task.kind`/`is_epic`/`epic_name` (an invalid or self-naming marker reads as no epic); `models.parent_epic_name` is the one membership rule (marker must name a real, non-symlink epic folder) for the CLI JSON, the TUI tree, the delete guard and the CLAUDE.md block. No nesting, folders never move; `set_task_epic`/`set_task_kind` enforce the rules (`create_task` writes markers only into a folder it creates), and `finish_task` refuses an epic that still has children. `_write_marker` re-syncs the managed `<!-- tasktree:epic -->` block in the task CLAUDE.md (`sync_epic_block`; also run by `ensure_claude_md_files`), and the archive stub check ignores that block. The epic log is `<epic>/epic-log/<task>.md`, one append-only notes file per task (`append_epic_note`, O_APPEND, never through a symlink); `services/epic_log.py` owns the scope rule (`resolve_log_target`) and joins the notes with the recap of the task's newest session across its folder and worktrees (`claude_sessions.latest_session`, which checks the transcript's recorded cwd because Claude project dir names collide: `X/1` = `X-1`, and skips headless `claude -p` runs; the TUI Info-panel recap uses it too)
- **Worktree**: A git worktree within a task, created from a repo in `REPOS_DIR` (~/repos). Branch name matches task name.
- **GitStatus**: Status info for a worktree (branch, staged/modified/untracked files, ahead/behind counts)

### Services Layer (`tasktree_manager/services/`)

- `config.py`: Loads configuration from environment variables (`REPOS_DIR`, `TASKS_DIR`)
- `task_manager.py`: CRUD operations for tasks and worktrees (creates git worktrees via subprocess)
- `git_ops.py`: Git status queries, push/pull operations (all via subprocess)

### Headless CLI (`tasktree_manager/cli.py`)

`tasktree-manager` with any argument routes to the CLI instead of the TUI (dispatch in
`app.py:main`). Subcommands `create`/`list`/`delete`/`add-repo`/`repos`/`epic` are thin wrappers over
the services layer for scripts and AI agents (the `/wtask` skill drives them). `delete` enforces
the same `check_task_safety` gate as the TUI unless `--force`, and always archives the remaining
diff and the task-folder files outside the worktrees first; an incomplete archive stops the delete (the TUI asks again). Task names are a single path
segment (no `/`, no leading `.`); `get_task` validates names because its result is rmtree'd.
`delete`/`finish` refuse an epic with children before the safety sweep, even with `--force`.
`epic note`/`epic log` infer the task from `$PWD`; inside a task, `epic note` writes only its own notes and `epic log` refuses tasks of another epic.
`epic ask` (`services/epic_ask.py`) runs `claude -p --resume ID --fork-session --no-session-persistence` with `disableAllHooks`, `--tools Read,Grep,Glob`, `--strict-mcp-config`, `--disable-slash-commands`, `--max-turns`, `--name epic-ask-<task>` (`parse_agent_sessions` skips that prefix, so a running copy never shows as a live session or a TUI badge) `--no-chrome` (Chrome tools arrive as MCP tools that `--tools` does not remove), and Read deny rules for credential paths, `//**/` forms of `ARCHIVE_SECRET_PATTERNS` and `.env`, and the transcripts under `claude_config_dir()` (`//` = absolute path in rules; a bare `**/x` would be cwd-relative), from the session's start folder and without the asking session's identity env (`ask_env`); `--allowedTools` would only add permissions, not remove tools. It exits 3 when `claude agents --json` shows a running session in the target task, checked before a transcript is required. Scope for both `epic log` and `epic ask` is `epic_log.require_in_scope`.

### Theming

Uses Textual's theming system with design tokens (`$panel`, `$surface`, `$border`, `$border-blurred`, `$block-cursor-*`, `$footer-key-*`, etc.) so all styling adapts to any theme. `tasktree_manager/themes.py` registers six themes from the design system: the default `tasktree` (lazygit-classic ANSI palette) plus tuned `tokyo-night`, `catppuccin-mocha`, `gruvbox`, `dracula`, and `nord` (these override Textual's built-ins of the same name so the design's panel layering and selection colors apply). Panels sit darker than the screen ground; title bars carry a `[n]` number, dim context, and a right-aligned counter. Switch themes via the Command Palette (`Ctrl+P`); other Textual built-ins also work. The design source of truth is the "TaskTree-Manager design system" Claude Design project (tokens, component specs, full-app mockup).

### Widgets Layer (`tasktree_manager/widgets/`)

All widgets extend Textual's `ListView` or `Static`:
- `task_list.py`: Left panel showing tasks with dirty indicators. Epics render as foldable rows (`enter`/`space`) with their children below; `all_tasks` holds every loaded task, `tasks` only the visible rows (row index = task). Reloads and Claude polls must use `all_tasks`, or folded children drop out
- `worktree_list.py`: Right panel showing worktrees for selected task
- `status_panel.py`: Bottom panel showing git status for selected worktree
- `create_modal.py`: Modal dialogs (all extend `ThemedModalScreen` base class)

### App (`tasktree_manager/app.py`)

`TaskTreeApp` is the main Textual App. It:
- Composes the 3-panel layout
- Handles message events from list widgets (`TaskHighlighted`, `WorktreeHighlighted`)
- Implements actions for keybindings (n=new task, d=delete, g=lazygit, etc.)
- Uses `app.suspend()` to shell out to lazygit or $SHELL
- Opens terminal tabs (`o`/`e`/`c`) via `_open_terminal_tab`: inside zellij (`ZELLIJ_SESSION_NAME` set) it switches to an open tab named `<folder> · <kind>` (`query-tab-names` first: `go-to-tab-name` exits 0 for a missing name) or runs `zellij action new-tab`; else the Ghostty AppleScript clipboard paste. `main()` execs `zellij attach --create <zellij_session>` first when `[tools] zellij_autostart` is on and the start is interactive
- `c` with `[tools] claude_background` (default on, `services/claude_bg.py`): the tab runs `claude attach ID` of a `claude --bg` session, so closing the tab (`x` = `close-tab-by-id`, only when every pane's `terminal_command` in `list-panes --all --json` is a `claude attach`) leaves Claude working. Order: open tab, focused worktree's agent, task folder's background session (`claude agents --json --all`, exact cwd), else `--bg --resume <latest_session>` with no other flag (a flag forks a copy) or `--bg -n TASK`; Claude open in another terminal there is left alone; any failure falls back to Claude inside the tab. Launches drop the launching session's env (`claude_bg.SESSION_ENV`: `CLAUDE_CODE_CHILD_SESSION` turns transcripts off). Delete (TUI and CLI) confirms or refuses while a background session works in the task, then `claude stop` + `claude rm` its sessions; one that will not go keeps the task (CLI: unless `--force`). The agents parser reads `state` before `status` (a working background row says `status: idle`), and an unknown `state` falls back to `status`
- Uses static `CSS` class variable with Textual design tokens

### Styling Pattern

CSS uses Textual's design tokens (e.g., `$primary`, `$background`, `$surface`, `$error`) for theme-aware styling:
- Main app CSS is defined in `TaskTreeApp.CSS` class variable
- Modals use `DEFAULT_CSS` class attribute with design tokens
- List items use `.--highlight` styling for both the ListItem and its child Static widget

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

## Development Preferences

- **Documentation lookup**: Use Context7 MCP tool when needing up-to-date library documentation (Textual, Rich, etc.)
- **Code intelligence**: Use Python LSP for type checking and diagnostics
- **Documentation updates**: After implementing tasks or plans, update README.md and other relevant markdown files to reflect changes
