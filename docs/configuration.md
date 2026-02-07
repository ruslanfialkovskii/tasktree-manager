# Configuration Reference

Complete reference for all tasktree-manager configuration options.

## Table of Contents

- [Configuration System Overview](#configuration-system-overview)
- [Configuration File Location](#configuration-file-location)
- [Complete Configuration Example](#complete-configuration-example)
- [Directory Settings](#directory-settings)
- [UI Settings](#ui-settings)
- [Git Settings](#git-settings)
- [External Tools](#external-tools)
- [Symlinks](#symlinks)
- [Keybindings Reference](#keybindings-reference)
- [Environment Variables](#environment-variables)
- [Themes](#themes)
- [Configuration Precedence](#configuration-precedence)

## Configuration System Overview

tasktree-manager uses a **3-tier configuration system** with the following priority:

1. **Environment Variables** (highest priority) - Override everything
2. **Config File** (`config.toml`) - Persistent user preferences
3. **Default Values** (lowest priority) - Built-in sensible defaults

This allows you to:
- Set permanent preferences in `config.toml`
- Override settings per-session with environment variables
- Use defaults without any configuration

## Configuration File Location

### Default Location

```
~/.config/tasktree-manager/config.toml
```

### XDG Base Directory Support

tasktree-manager respects the XDG Base Directory specification. Set `XDG_CONFIG_HOME` to customize:

```bash
export XDG_CONFIG_HOME=~/.myconfig
# Config will be at: ~/.myconfig/tasktree-manager/config.toml
```

### Creating the Config File

On first run, tasktree-manager creates `config.toml` via the setup wizard. To manually create or reset:

```bash
# Remove existing config (optional)
rm ~/.config/tasktree-manager/config.toml

# Run tasktree-manager to trigger setup wizard
tasktree-manager
```

## Complete Configuration Example

Here's a fully annotated `config.toml` with all available options:

```toml
# tasktree-manager configuration
# https://github.com/yourusername/tasktree-manager

# ============================================================================
# Directory Settings
# ============================================================================

# Directory containing your git repositories
# Supports absolute paths and ~ expansion
repos_dir = "/Users/username/repos"

# Directory for task worktrees
# Created automatically if it doesn't exist
tasks_dir = "/Users/username/tasks"

# ============================================================================
# UI Settings
# ============================================================================
[ui]

# Theme to use for the interface
# Options: textual-dark, textual-light, nord, gruvbox, tokyo-night, monokai, dracula
# Default: textual-dark
theme = "textual-dark"

# Show hidden files in file listings
# Default: false
show_hidden_files = false

# ============================================================================
# Git Settings
# ============================================================================
[git]

# Default base branch for new worktrees
# Common values: main, master, develop, trunk
# Default: main
default_base_branch = "main"

# Automatically push after committing
# Not recommended for most workflows - use manual push (p) instead
# Default: false
auto_push = false

# Timeout for git operations in seconds
# Increase for slow connections or large repos
# Default: 30
timeout = 30

# ============================================================================
# External Tools
# ============================================================================
[tools]

# Preferred editor command
# Leave empty to use $EDITOR environment variable
# Examples: "vim", "nvim", "code", "emacs"
# Default: "" (uses $EDITOR, falls back to vi)
editor = ""

# Path to lazygit executable
# Default: "lazygit" (searches PATH)
lazygit_path = "lazygit"

# Preferred shell
# Leave empty to use $SHELL environment variable
# Default: "" (uses $SHELL, falls back to /bin/bash)
shell = ""

# ============================================================================
# Keybindings
# ============================================================================
# Customize keyboard shortcuts
# Uncomment and modify to change defaults
# Available modifiers: ctrl+, shift+, alt+
# Special keys: enter, tab, escape, space, backspace, delete, up, down, left, right
[keybindings]

# Application control
quit = "q"              # Quit application
help = "?"              # Show help modal

# Task management
new_task = "n"          # Create new task
add_repo = "a"          # Add repository to current task
delete_task = "d"       # Delete/finish task

# Git operations
open_lazygit = "g"      # Open lazygit in selected worktree
open_editor = "e"       # Open editor in selected task/worktree
open_folder = "o"       # Open folder in new terminal tab
open_shell = "enter"    # Open shell in selected worktree
push_all = "p"          # Push all worktrees in current task
pull_all = "P"          # Pull all worktrees in current task (shift+p)
refresh = "r"           # Refresh git status

# Navigation
focus_next = "tab"          # Switch to next panel
focus_previous = "shift+tab" # Switch to previous panel
cursor_down = "j"           # Move cursor down
cursor_up = "k"             # Move cursor up

# Sorting and grouping
cycle_sort = "s"            # Cycle task sort mode
toggle_grouping = "S"       # Toggle worktree grouping (shift+s)

# ============================================================================
# Symlinks
# ============================================================================
# When creating worktrees, gitignored files are symlinked from the source repo.
# Blocklist specifies patterns to exclude (e.g., cache files).
[symlinks]
blocklist = [
    "*.pyc",
    "*.pyo",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".coverage",
    "*.log",
]
```

## Directory Settings

| Option     | Type | Default   | Environment Variable | Description                                    |
|------------|------|-----------|---------------------|------------------------------------------------|
| `repos_dir` | path | `~/repos` | `REPOS_DIR`         | Directory containing your git repositories     |
| `tasks_dir` | path | `~/tasks` | `TASKS_DIR`         | Directory where task worktrees will be created |

### Details

**`repos_dir`:**
- Must exist before creating tasks
- Can contain repositories in subdirectories (tasktree-manager scans recursively)
- Supports `~` expansion and absolute paths
- Original repositories are NEVER modified

**`tasks_dir`:**
- Created automatically if it doesn't exist
- Each task creates a subdirectory: `tasks_dir/TASK-NAME/`
- Each worktree within: `tasks_dir/TASK-NAME/repo-name/`

### Examples

```toml
# Single repos directory
repos_dir = "/Users/alice/code"

# Multiple levels (tasktree-manager scans recursively)
repos_dir = "/Users/alice/projects"
# Can contain: projects/work/api, projects/personal/blog, etc.

# Separate SSD for tasks (performance)
tasks_dir = "/Volumes/FastSSD/worktrees"
```

## UI Settings

| Option              | Type    | Default         | Environment Variable  | Description                     |
|--------------------|---------|-----------------|-----------------------|---------------------------------|
| `theme`            | string  | `textual-dark`  | `TASKTREE_THEME`     | Color theme for the interface   |
| `show_hidden_files` | boolean | `false`         | -                     | Show hidden files in listings   |

### `theme`

Available themes (press `Ctrl+P` in app to switch):

- `textual-dark` - Default dark theme with blue accents
- `textual-light` - Light theme with high contrast
- `nord` - Arctic, north-bluish color palette
- `gruvbox` - Retro groove warm color scheme
- `tokyo-night` - Clean, dark theme inspired by Tokyo's night
- `monokai` - Classic dark theme with vibrant colors
- `dracula` - Dark theme with pastel-like colors

### `show_hidden_files`

Currently unused (reserved for future file browser features).

## Git Settings

| Option                | Type    | Default | Environment Variable      | Description                              |
|----------------------|---------|---------|---------------------------|------------------------------------------|
| `default_base_branch` | string  | `main`  | `TASKTREE_DEFAULT_BRANCH` | Default branch for creating worktrees    |
| `auto_push`          | boolean | `false` | -                         | Auto-push after committing (not recommended) |
| `timeout`            | integer | `30`    | -                         | Git operation timeout in seconds         |

### Details

**`default_base_branch`:**
- Used when creating new tasks (can override per-task)
- Must exist in the repository
- Common values: `main`, `master`, `develop`, `trunk`
- Example: If set to `main`, new worktrees branch from `main`

**`auto_push`:**
- **Not recommended** for most workflows
- When `true`, git operations auto-push to remote
- Most users should use manual push (`p` key) for control

**`timeout`:**
- Timeout for git commands (clone, fetch, push, pull)
- Increase for slow networks or large repositories
- Set to `60` or higher for very large repos

## External Tools

| Option         | Type   | Default     | Environment Variable | Description                          |
|---------------|--------|-------------|---------------------|--------------------------------------|
| `editor`      | string | `""`        | `EDITOR`            | Command to launch your editor        |
| `lazygit_path` | string | `"lazygit"` | -                   | Path to lazygit executable           |
| `shell`       | string | `""`        | `SHELL`             | Shell to use when opening terminals  |

### Details

**`editor`:**
- Leave empty (`""`) to use `$EDITOR` environment variable
- Fallback: `vi`
- Examples: `"vim"`, `"nvim"`, `"code"`, `"emacs -nw"`
- Used when pressing `e` to open editor in task/worktree folder

**`lazygit_path`:**
- Default `"lazygit"` searches PATH
- Use absolute path for custom location: `"/opt/homebrew/bin/lazygit"`
- Install lazygit: `brew install lazygit` (macOS), `apt install lazygit` (Ubuntu)

**`shell`:**
- Leave empty (`""`) to use `$SHELL` environment variable
- Fallback: `/bin/bash`
- Examples: `"/bin/zsh"`, `"/bin/fish"`, `"/usr/local/bin/bash"`
- Used when pressing `Enter` to open shell in worktree

## Symlinks

When creating worktrees, tasktree-manager automatically symlinks gitignored files (like `.env`) from the source repository. This allows environment files to be shared without copying.

| Option      | Type       | Default        | Description                                    |
|-------------|------------|----------------|------------------------------------------------|
| `blocklist` | array[str] | (see below)    | Glob patterns for files to exclude from symlinking |

### Default Blocklist

By default, these patterns are excluded from symlinking:

```toml
[symlinks]
blocklist = [
    "*.pyc",
    "*.pyo",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".coverage",
    "*.log",
    "*.egg-info",
    ".eggs",
    "dist",
    "build",
    ".tox",
    ".nox",
    "*.so",
    "*.dylib",
]
```

### How It Works

1. When a worktree is created, tasktree-manager reads the source repo's `.gitignore`
2. For each gitignored file pattern, it finds matching files
3. Files matching the blocklist are skipped
4. Remaining files are symlinked to the worktree

### Customizing the Blocklist

**Allow all gitignored files (empty blocklist):**
```toml
[symlinks]
blocklist = []
```

**Block specific patterns:**
```toml
[symlinks]
blocklist = [
    ".env*",        # Block all .env files
    "*.secret",     # Block secret files
    "credentials*", # Block credential files
]
```

**Add to default blocklist (must include all patterns):**
```toml
[symlinks]
blocklist = [
    # Default patterns
    "*.pyc",
    "*.pyo",
    "__pycache__",
    ".coverage",
    "*.log",
    # Your additions
    "*.tmp",
    ".DS_Store",
]
```

### Common Use Cases

**Symlink environment files, block caches:**
```toml
[symlinks]
blocklist = ["*.pyc", "__pycache__", ".coverage", "*.log"]
```
This allows `.env`, `.mise.toml` to be symlinked while blocking cache files.

**Block everything (disable symlinks):**
```toml
[symlinks]
blocklist = ["*"]
```

## Keybindings Reference

All 18 customizable keybindings with descriptions:

### Application Control

| Action   | Default | Description                             | Customization Example     |
|----------|---------|------------------------------------------|---------------------------|
| `quit`   | `q`     | Quit tasktree-manager                   | `quit = "ctrl+q"`         |
| `help`   | `?`     | Show help modal with keybindings        | `help = "F1"`             |

### Task Management

| Action        | Default | Description                            | Customization Example      |
|---------------|---------|----------------------------------------|----------------------------|
| `new_task`    | `n`     | Create a new task                      | `new_task = "ctrl+n"`      |
| `add_repo`    | `a`     | Add repository to current task         | `add_repo = "ctrl+a"`      |
| `delete_task` | `d`     | Delete/finish current task             | `delete_task = "delete"`   |

### Git Operations

| Action         | Default  | Description                           | Customization Example       |
|----------------|----------|---------------------------------------|-----------------------------|
| `open_lazygit` | `g`      | Open lazygit in selected worktree     | `open_lazygit = "ctrl+g"`   |
| `open_editor`  | `e`      | Open editor in task/worktree folder   | `open_editor = "ctrl+e"`    |
| `open_folder`  | `o`      | Open folder in new terminal tab       | `open_folder = "ctrl+o"`    |
| `open_shell`   | `enter`  | Open shell in selected worktree       | `open_shell = "ctrl+t"`     |
| `push_all`     | `p`      | Push all worktrees in current task    | `push_all = "ctrl+p"`       |
| `pull_all`     | `P`      | Pull all worktrees in current task    | `pull_all = "ctrl+shift+p"` |
| `refresh`      | `r`      | Refresh git status for all worktrees  | `refresh = "F5"`            |

### Navigation

| Action            | Default     | Description                    | Customization Example            |
|-------------------|-------------|--------------------------------|----------------------------------|
| `focus_next`      | `tab`       | Switch to next panel           | `focus_next = "ctrl+]"`          |
| `focus_previous`  | `shift+tab` | Switch to previous panel       | `focus_previous = "ctrl+["`      |
| `cursor_down`     | `j`         | Move cursor down in lists      | `cursor_down = "down"`           |
| `cursor_up`       | `k`         | Move cursor up in lists        | `cursor_up = "up"`               |

### Sorting & Grouping

| Action            | Default | Description                              | Customization Example            |
|-------------------|---------|------------------------------------------|----------------------------------|
| `cycle_sort`      | `s`     | Cycle task sort mode                     | `cycle_sort = "ctrl+s"`          |
| `toggle_grouping` | `S`     | Toggle worktree grouping by dirty/clean  | `toggle_grouping = "ctrl+g"`     |

### Available Key Syntax

**Single characters:**
- Letters: `a-z` (case-insensitive)
- Numbers: `0-9`
- Punctuation: `?`, `/`, `.`, `,`, `;`, `'`, etc.

**Special keys:**
- `enter`, `tab`, `escape`, `space`
- `backspace`, `delete`
- `up`, `down`, `left`, `right`
- `home`, `end`, `pageup`, `pagedown`
- `F1` through `F12`

**Modifiers:**
- `ctrl+key` - Control key combinations
- `shift+key` - Shift key combinations (works with special keys like `tab`)
- `alt+key` - Alt/Option key combinations

**Platform notes:**
- On macOS, `alt+` may not work reliably in all terminals
- Some terminals may intercept certain key combinations (e.g., `ctrl+t`)
- Test your custom bindings to ensure terminal compatibility

### Customization Examples

**Vim-style navigation:**
```toml
[keybindings]
cursor_down = "j"
cursor_up = "k"
focus_next = "l"
focus_previous = "h"
```

**IDE-style shortcuts:**
```toml
[keybindings]
new_task = "ctrl+n"
delete_task = "ctrl+d"
open_shell = "ctrl+t"
refresh = "F5"
quit = "ctrl+q"
```

**Arrow keys navigation:**
```toml
[keybindings]
cursor_down = "down"
cursor_up = "up"
focus_next = "right"
focus_previous = "left"
```

## Environment Variables

Override configuration for a single session using environment variables:

| Variable                  | Config Equivalent      | Example                          |
|---------------------------|------------------------|----------------------------------|
| `REPOS_DIR`               | `repos_dir`            | `export REPOS_DIR=~/code`        |
| `TASKS_DIR`               | `tasks_dir`            | `export TASKS_DIR=~/worktrees`   |
| `TASKTREE_THEME`          | `ui.theme`             | `export TASKTREE_THEME=nord`     |
| `TASKTREE_DEFAULT_BRANCH` | `git.default_base_branch` | `export TASKTREE_DEFAULT_BRANCH=develop` |
| `EDITOR`                  | `tools.editor`         | `export EDITOR=nvim`             |
| `SHELL`                   | `tools.shell`          | `export SHELL=/bin/zsh`          |
| `XDG_CONFIG_HOME`         | (config location)      | `export XDG_CONFIG_HOME=~/.cfg`  |

### Usage Examples

**Temporary different repos directory:**
```bash
REPOS_DIR=~/other-projects tasktree-manager
```

**Try a theme without changing config:**
```bash
TASKTREE_THEME=gruvbox tasktree-manager
```

**Use different config location:**
```bash
XDG_CONFIG_HOME=~/.myconfig tasktree-manager
```

**Multiple overrides:**
```bash
REPOS_DIR=~/work TASKS_DIR=/tmp/tasks TASKTREE_THEME=nord tasktree-manager
```

## Themes

### Switching Themes

**In the app:**
1. Press `Ctrl+P` to open Command Palette
2. Search for "theme"
3. Select your preferred theme
4. Theme is saved automatically to `config.toml`

**Via config file:**
```toml
[ui]
theme = "nord"
```

**Via environment variable:**
```bash
TASKTREE_THEME=dracula tasktree-manager
```

### Theme Descriptions

| Theme           | Style               | Best For                          |
|-----------------|---------------------|-----------------------------------|
| `textual-dark`  | Dark with blue      | Default, general use              |
| `textual-light` | Light with contrast | Bright environments               |
| `nord`          | Arctic blue         | Low-contrast, easy on eyes        |
| `gruvbox`       | Retro warm          | Nostalgic, comfortable            |
| `tokyo-night`   | Modern dark         | Clean, professional               |
| `monokai`       | Vibrant colors      | High contrast, code-focused       |
| `dracula`       | Pastel dark         | Popular, easy to read             |

### Theme Persistence

Theme selection via `Ctrl+P` automatically updates `config.toml`:

```toml
[ui]
theme = "tokyo-night"
```

Your theme persists across sessions unless overridden by `TASKTREE_THEME` environment variable.

## Configuration Precedence

When the same setting is defined in multiple places, this priority order applies:

### Priority Order (Highest to Lowest)

1. **Environment Variables** - Session-specific overrides
2. **Config File** (`~/.config/tasktree-manager/config.toml`) - User preferences
3. **Default Values** - Built-in sensible defaults

### Examples

#### Example 1: repos_dir Resolution

```toml
# config.toml
repos_dir = "/Users/alice/repos"
```

```bash
# Environment variable
export REPOS_DIR=~/work

# Run tasktree-manager
tasktree-manager
```

**Result:** Uses `~/work` (environment variable wins)

#### Example 2: theme Resolution

```toml
# config.toml
[ui]
theme = "nord"
```

```bash
# No environment variable
tasktree-manager
```

**Result:** Uses `nord` from config.toml

#### Example 3: default_base_branch Resolution

```toml
# config.toml has no git.default_base_branch
```

```bash
# No environment variable
tasktree-manager
```

**Result:** Uses `main` (built-in default)

#### Example 4: Multiple Settings

```toml
# config.toml
repos_dir = "/Users/alice/repos"
tasks_dir = "/Users/alice/tasks"

[ui]
theme = "gruvbox"

[git]
default_base_branch = "develop"
```

```bash
export REPOS_DIR=~/work
export TASKTREE_THEME=nord
# TASKS_DIR not set
# TASKTREE_DEFAULT_BRANCH not set

tasktree-manager
```

**Result:**
- `repos_dir`: `~/work` (env var)
- `tasks_dir`: `/Users/alice/tasks` (config file)
- `theme`: `nord` (env var)
- `default_base_branch`: `develop` (config file)

### Debugging Configuration

To see which configuration is being used:

1. Open help modal (`?` key)
2. Bottom shows config location: `Config: ~/.config/tasktree-manager/config.toml`
3. View actual file:
   ```bash
   cat ~/.config/tasktree-manager/config.toml
   ```

4. Check environment variables:
   ```bash
   env | grep -E '(REPOS_DIR|TASKS_DIR|TASKTREE_|EDITOR|SHELL)'
   ```

## Next Steps

- [User Guide](user-guide.md) - Learn workflows and best practices
- [Troubleshooting](troubleshooting.md) - Configuration issues and solutions
- [Installation Guide](installation.md) - Setup and requirements
