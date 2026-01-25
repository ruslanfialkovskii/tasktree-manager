# OpenSpec: tasktree

## Metadata

- **Project**: tasktree
- **Version**: 0.1.0
- **Spec Format**: OpenSpec 1.0
- **Last Updated**: 2026-01-22
- **Status**: Draft
- **Owner**: @ruslan

## System Overview

### Purpose
tasktree is a terminal-based task management system for developers working with git worktrees across multiple repositories.

### Architecture
```
┌─────────────────────────────────────────────────────┐
│                   TaskTreeApp                       │
│                  (Textual App)                      │
├─────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌───────────────┐  ┌──────────────┐ │
│  │  Tasks   │  │   Worktrees   │  │    Status    │ │
│  │  List    │  │     List      │  │    Panel     │ │
│  └──────────┘  └───────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────┘
           │                  │                │
           ▼                  ▼                ▼
┌──────────────────────────────────────────────────────┐
│              Services Layer                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │  Config  │  │   Task   │  │    Git Ops       │  │
│  │          │  │ Manager  │  │                  │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
└──────────────────────────────────────────────────────┘
           │                  │                │
           ▼                  ▼                ▼
     ┌──────────┐      ┌──────────┐    ┌──────────┐
     │   ENV    │      │   File   │    │   Git    │
     │  Vars    │      │  System  │    │  (CLI)   │
     └──────────┘      └──────────┘    └──────────┘
```

## Components

### 1. Core Data Models

#### Task
```python
@dataclass
class Task:
    name: str
    worktrees: list[Worktree]
    path: Path

    @property
    def is_dirty(self) -> bool

    @property
    def dirty_count(self) -> int
```

**Responsibilities:**
- Represent a named development task
- Track associated worktrees
- Aggregate dirty state across worktrees

**Storage:**
- Directory: `~/.wtasks/{task_name}/`
- Contains: Worktree subdirectories

#### Worktree
```python
@dataclass
class Worktree:
    name: str
    path: Path
    repo_name: str
    branch: str | None

    @property
    def is_dirty(self) -> bool

    @property
    def changed_files(self) -> int
```

**Responsibilities:**
- Represent a git worktree
- Track git status
- Provide access to worktree path

**Storage:**
- Directory: `~/.wtasks/{task_name}/{repo_name}/`
- Git worktree linked to `~/repos/{repo_name}`

#### GitStatus
```python
@dataclass
class GitStatus:
    branch: str
    ahead: int
    behind: int
    staged: list[tuple[str, str]]
    modified: list[tuple[str, str]]
    untracked: list[tuple[str, str]]

    @property
    def is_dirty(self) -> bool

    @property
    def changed_files(self) -> int

    @property
    def all_changes(self) -> list[tuple[str, str]]
```

**Responsibilities:**
- Parse and store git status output
- Compute derived properties
- Provide structured access to git state

### 2. Services

#### Config Service
```python
class Config:
    repos_dir: Path
    tasks_dir: Path
    config_dir: Path

    @classmethod
    def load() -> Config

    def ensure_dirs() -> None
    def get_available_repos() -> list[str]
```

**Responsibilities:**
- Load configuration from environment
- Ensure required directories exist
- Discover available repositories

**Environment Variables:**
- `REPOS_DIR`: Directory containing git repositories (default: `~/repos`)
- `TASKS_DIR`: Directory for task worktrees (default: `~/.wtasks`)

#### TaskManager Service
```python
class TaskManager:
    def __init__(config: Config)

    def list_tasks() -> list[Task]
    def get_task(name: str) -> Task | None
    def create_task(name: str, repos: list[str], base_branch: str) -> Task
    def add_repo_to_task(task: Task, repo: str, base_branch: str) -> None
    def finish_task(task: Task) -> None
    def get_repos_not_in_task(task: Task) -> list[str]
```

**Responsibilities:**
- CRUD operations for tasks
- Create/remove git worktrees
- Manage task directory structure

**Implementation:**
- Uses `subprocess` to call `git worktree add/remove`
- Creates directories in `TASKS_DIR`
- Reads filesystem to discover tasks

#### GitOps Service
```python
class GitOps:
    @staticmethod
    def get_status(worktree: Worktree) -> GitStatus

    @staticmethod
    def update_worktree_status(worktree: Worktree) -> None

    @staticmethod
    def push_all(task: Task) -> list[tuple[str, bool, str]]

    @staticmethod
    def pull_all(task: Task) -> list[tuple[str, bool, str]]
```

**Responsibilities:**
- Execute git commands
- Parse git output
- Update worktree objects with status

**Implementation:**
- Uses `subprocess` to call git CLI
- Parses `git status --porcelain=v1`
- Handles errors gracefully

### 3. UI Components

#### TaskList Widget
```python
class TaskList(ListView):
    def load_tasks(tasks: list[Task]) -> None
    def get_selected_task() -> Task | None

    # Messages
    TaskHighlighted(task: Task | None)
    TaskSelected(task: Task | None)
```

**Responsibilities:**
- Display list of tasks
- Highlight selected task
- Emit events on selection change

**Visual Elements:**
- Dirty indicator: `●` (red if dirty)
- Task name
- Dirty count: `(N)` if dirty

#### WorktreeList Widget
```python
class WorktreeList(ListView):
    def load_worktrees(worktrees: list[Worktree]) -> None
    def get_selected_worktree() -> Worktree | None

    # Messages
    WorktreeHighlighted(worktree: Worktree | None)
    WorktreeSelected(worktree: Worktree | None)
```

**Responsibilities:**
- Display worktrees for selected task
- Show branch and status
- Emit events on selection change

**Visual Elements:**
- Repo name (20 chars)
- Branch name (15 chars, blue)
- Status indicator: `✓` (green) or `✗ N files` (red)

#### StatusPanel Widget
```python
class StatusPanel(Static):
    def update_status(worktree: Worktree, status: GitStatus) -> None
    def clear_status() -> None
```

**Responsibilities:**
- Display detailed git status
- Show branch, sync info, changes
- Update colors based on theme

**Visual Elements:**
- Header: "Status: {worktree_name}"
- Branch: "Branch: {branch_name}"
- Sync: "↑{ahead} ↓{behind}"
- Changes: Status code + filename per line

#### Modal Widgets
- `CreateTaskModal`: Create new task
- `AddRepoModal`: Add repo to task
- `ConfirmModal`: Confirm dangerous actions
- `HelpModal`: Show keybindings

### 4. Theme System

#### Theme Definition
```python
@dataclass
class Theme:
    name: str
    background: str
    foreground: str
    border: str
    border_focused: str
    highlight_unfocused: str
    highlight_focused: str
    accent: str
    success: str
    warning: str
    error: str
    # ... more colors
```

**Built-in Themes:**
1. `default`: Lazygit-inspired (#111111 bg, #00d700 focused)
2. `vscode-dark`: VS Code Dark
3. `vscode-light`: VS Code Light
4. `catppuccin`: Catppuccin Mocha

**Theme Application:**
- App CSS generated from theme
- Widgets query theme colors at runtime
- Modals apply theme on mount

## Workflows

### Create Task
```
1. User presses 'n'
2. CreateTaskModal opens
3. User enters task name
4. User selects repositories
5. User sets base branch
6. TaskManager.create_task()
   - Creates task directory
   - For each repo:
     - git worktree add {tasks_dir}/{task}/{repo} -b {task} {base_branch}
7. Task list refreshes
8. New task appears with worktrees
```

### Delete Task
```
1. User selects task
2. User presses 'd'
3. ConfirmModal shows warning
4. User confirms
5. TaskManager.finish_task()
   - For each worktree:
     - cd {repo_dir}
     - git worktree remove {worktree_path}
   - rm -rf {task_dir}
6. Task list refreshes
7. Task removed from list
```

### Push All Worktrees
```
1. User selects task
2. User presses 'p'
3. GitOps.push_all()
   - For each worktree:
     - cd {worktree_path}
     - git push
4. Results collected
5. Notification shows success/fail count
```

### Cycle Theme
```
1. User presses 't'
2. app.action_cycle_theme()
3. Next theme selected
4. app._apply_theme()
   - Updates container styles
5. app._apply_theme_to_lists()
   - Reloads task/worktree lists
   - Recreates items with new colors
6. Notification shows theme name
```

## Data Flow

### Task Loading
```
User opens app
  → on_mount()
    → _load_tasks()
      → task_manager.list_tasks()
        → Scans TASKS_DIR
        → For each task directory:
          → For each worktree:
            → GitOps.get_status()
              → git status --porcelain
              → Parse output
            → Update worktree.branch, is_dirty
      → task_list.load_tasks()
        → Creates TaskListItem for each task
        → First task auto-selected
          → TaskHighlighted event
            → worktree_list.load_worktrees()
              → Creates WorktreeListItem for each
              → First worktree auto-selected
                → WorktreeHighlighted event
                  → status_panel.update_status()
```

### Status Update
```
User presses 'r'
  → action_refresh()
    → _load_tasks() (same as above)
    → _refresh_current_task()
      → Updates current task from disk
      → Reloads worktree list
```

## Security Considerations

1. **Command Injection**
   - Risk: User-provided task/repo names in shell commands
   - Mitigation: Input validation, subprocess with list args

2. **Path Traversal**
   - Risk: Malicious task names (`../../../etc`)
   - Mitigation: Path validation, canonicalization

3. **Disk Space**
   - Risk: Worktrees consume significant space
   - Mitigation: User awareness, cleanup tools

## Performance Targets

- App startup: < 1s
- Task list refresh: < 200ms (10 tasks, 5 worktrees each)
- Git status per worktree: < 100ms
- Theme switch: < 100ms
- Memory usage: < 50MB

## Error Handling

1. **Git Command Failures**
   - Capture stderr
   - Show error notification
   - Log to file (future)

2. **Missing Directories**
   - Auto-create on Config.ensure_dirs()
   - Fail gracefully if no permissions

3. **Invalid Git State**
   - Show status as "unknown"
   - Allow lazygit escape hatch

## Testing Strategy

- **Unit Tests**: Services (config, task_manager, git_ops)
- **Integration Tests**: End-to-end workflows
- **Widget Tests**: Textual async testing
- **Coverage Target**: >80%

## Future Enhancements

### Phase 2
- Task templates
- Search/filter
- Config file

### Phase 3
- Task metadata (JIRA IDs)
- Git hooks
- Custom keybindings

### Phase 4
- Remote worktrees
- CI/CD status
- Analytics

## References

- [PRD](./PRD.md)
- [ROADMAP](./ROADMAP.md)
- [CLAUDE.md](./CLAUDE.md)
- [Textual Docs](https://textual.textualize.io/)
- [Git Worktree](https://git-scm.com/docs/git-worktree)
