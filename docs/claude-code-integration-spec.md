# Claude Code Integration Spec

**Status**: Planned (v0.3.0)
**Created**: 2026-01-28

## Overview

Add two Claude Code integration features to tasktree:

1. **Open Claude Code for Task** (`C` key) - Launch Claude Code in the task directory with access to all worktrees
2. **AI-assisted repo selection** - When creating a task, optionally use Claude to suggest relevant repos based on task description

---

## Feature 1: Open Claude Code for Task

### User Story

As a developer, I want to open Claude Code with context of all worktrees in my current task, so I can get AI assistance for cross-repo work.

### Implementation

#### 1. Config options (`tasktree/services/config.py`)

Add to dataclass fields:
```python
claude_path: str = "claude"
```

Add to DEFAULT_KEYBINDINGS:
```python
"open_claude": "C",
```

Update `load()` to read from config:
```python
claude_path = tools_config.get("claude_path", "claude")
```

Update `save()` to write config:
```python
claude_path = "{self.claude_path}"
```

#### 2. Action and binding (`tasktree/app.py`)

Add binding in `_build_bindings_from_config()`:
```python
Binding(kb.get("open_claude", "C"), "open_claude", "Claude", show=False),
```

Add action method:
```python
def action_open_claude(self) -> None:
    """Open Claude Code in the current task directory."""
    if not self.current_task:
        self.notify("No task selected", severity="warning")
        return

    task_path = self.current_task.path
    if not task_path.exists():
        self.notify("Task directory not found", severity="error")
        return

    self.notify("Opening Claude Code...")

    with self.suspend():
        self._run_external_command(
            [self.config.claude_path],
            cwd=task_path,
            name="Claude Code",
            install_hint="npm install -g @anthropic-ai/claude-code",
        )

    self._load_tasks()
    self._refresh_current_task()
```

#### 3. Help modal (`tasktree/widgets/create_modal.py`)

Add to Git Operations section in `_build_help_content()`:
```python
git_section += self._format_binding("open_claude", "C", "Open Claude Code") + "\n"
```

---

## Feature 2: AI-Assisted Repo Selection

### User Story

As a developer creating a new task, I want Claude to suggest which repos are relevant based on my task description, so I don't have to manually identify all relevant repos.

### Design

When creating a task, user can:
1. Enter task name and optional description
2. Click "Suggest Repos" button
3. Claude analyzes repos (names + README + CLAUDE.md) and suggests relevant ones
4. Suggestions auto-select in the repo list

Uses `claude --print -p "prompt"` for non-interactive analysis.

### Implementation

#### 1. AI service (`tasktree/services/ai_repo_analyzer.py`)

New file with:
- `RepoInfo` dataclass: name, readme_content, claude_md_content
- `RepoSuggestion` dataclass: repo_name, relevance_score, reason
- `AIRepoAnalyzer` class:
  - `gather_repo_info(repos)` - Read README/CLAUDE.md from each repo (parallel)
  - `analyze(description, repo_infos)` - Call Claude CLI with prompt, parse JSON response

#### 2. Enhance CreateTaskModal (`tasktree/widgets/create_modal.py`)

Add to existing `CreateTaskModal`:
- New input field: "Task Description" (optional)
- New button: "Suggest Repos"
- Loading state while AI analyzes
- Auto-select suggested repos in the list

Key changes:
- Add `task_description` Input field
- Add `ai_suggest_btn` Button
- Add `_run_ai_analysis()` async method using `run_worker()`
- Add `_handle_suggestions()` callback to select repos

#### 3. Config option for timeout

```python
claude_timeout: int = 60
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `tasktree/services/config.py` | Add `claude_path`, `claude_timeout`, keybinding |
| `tasktree/app.py` | Add binding, `action_open_claude()` method |
| `tasktree/widgets/create_modal.py` | Add description field, AI suggest button, help entry |
| `tasktree/services/ai_repo_analyzer.py` | **New file**: AI analysis service |

---

## Implementation Order

1. **Phase 1**: Basic Claude Code integration
   - Config: `claude_path` field
   - App: `action_open_claude()` + keybinding
   - Help modal update

2. **Phase 2**: AI-assisted repo selection
   - Create `AIRepoAnalyzer` service
   - Update `CreateTaskModal` with description + suggest button
   - Wire up async analysis with worker

---

## Verification

1. **Feature 1 test**: Select a task, press `C`, verify Claude Code opens in task directory
2. **Feature 2 test**: Create new task, enter description like "auth system refactor", click Suggest, verify relevant repos are selected
3. **Error handling**: Test with Claude Code not installed - should show install hint
4. **Config test**: Verify `claude_path` can be customized in config.toml

---

## Config Example

```toml
[tools]
claude_path = "claude"
claude_timeout = 60

[keybindings]
open_claude = "C"
```
