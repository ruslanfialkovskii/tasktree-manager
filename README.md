# tasktree

> A beautiful TUI for managing git worktrees across multiple repositories

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-48%20passed-green.svg)](./tests/)

**tasktree** is a terminal user interface (TUI) application for managing development tasks that span multiple git repositories. Create tasks, organize worktrees, and track status across your entire codebase—all from a beautiful, keyboard-driven interface inspired by [lazygit](https://github.com/jesseduffield/lazygit).

## ✨ Features

- 🎯 **Task-Based Workflow**: Group related worktrees across multiple repositories
- 🌳 **Git Worktree Management**: Create, delete, and manage worktrees seamlessly
- 📊 **Real-Time Status**: See uncommitted changes, branch info, and sync status at a glance
- 🎨 **Beautiful Themes**: 4 built-in themes (default, VS Code Dark/Light, Catppuccin)
- ⌨️ **Keyboard-First**: Navigate and control everything without touching the mouse
- 🚀 **Fast & Lightweight**: Built with Python and [Textual](https://textual.textualize.io/)
- 🔧 **Flexible Configuration**: TOML config file or environment variables

## 📸 Screenshots

```
┌─ tasktree ──────────────────────────────────────────────────────────────┐
│  Tasks                    │  Worktrees                                   │
│  ● DIC-1813 (2)          │    gitops-hpc         DIC-1813        ✗ 3   │
│    DIC-1770-env          │    hpc                DIC-1813        ✓     │
│                          │                                              │
│                          │                                              │
├──────────────────────────────────────────────────────────────────────────┤
│  Status: gitops-hpc                                                      │
│  Branch: DIC-1813                                                        │
│  Sync:   ↑2 ↓1                                                          │
│                                                                          │
│   M  src/main.py                                                        │
│   ?? README.md                                                          │
│   M  tests/test_app.py                                                  │
└──────────────────────────────────────────────────────────────────────────┘
  n New task  d Delete  g Lazygit  r Refresh  t Theme  ? Help  q Quit
```

## 🚀 Quick Start

### Installation

```bash
# Using pipx (recommended)
pipx install tasktree

# Using pip
pip install tasktree

# From source
git clone https://github.com/yourusername/tasktree.git
cd tasktree
mise install  # or: pip install -e .
```

### First Run

```bash
tasktree
```

On first run, you'll be prompted to configure:
- **Repositories Directory**: Where your git repos live (e.g., `~/repos`)
- **Tasks Directory**: Where worktrees will be created (e.g., `~/tasks`)

Configuration is saved to `~/.config/tasktree/config.toml`.

### Basic Workflow

1. **Create a task**: Press `n`, enter task name, select repositories
2. **Navigate**: Use `j/k` or arrow keys, `Tab` to switch panels
3. **View status**: Select a worktree to see detailed git status
4. **Open lazygit**: Press `g` to open lazygit in the selected worktree
5. **Push/Pull**: Press `p` to push all worktrees, `P` to pull
6. **Delete task**: Press `d` and confirm to remove task and worktrees

## 📖 Documentation

### Keyboard Shortcuts

#### Navigation
- `j` / `↓` - Move down
- `k` / `↑` - Move up
- `Tab` - Switch between panels
- `Enter` - Open shell in selected worktree

#### Actions
- `n` - Create new task
- `a` - Add repository to current task
- `d` - Delete current task
- `g` - Open lazygit in selected worktree
- `p` - Push all worktrees in task
- `P` - Pull all worktrees in task
- `r` - Refresh status

#### General
- `t` - Cycle theme
- `?` - Show help
- `q` - Quit

### Configuration

#### Config File

Edit `~/.config/tasktree/config.toml`:

```toml
# Directory containing your git repositories
repos_dir = "/Users/username/repos"

# Directory for task worktrees
tasks_dir = "/Users/username/tasks"
```

#### Environment Variables

Override config file with environment variables:

```bash
export REPOS_DIR=~/code
export TASKS_DIR=~/worktrees
tasktree
```

### Themes

Press `t` to cycle through themes:

1. **default** - Lazygit-inspired dark theme (green/blue)
2. **vscode-dark** - VS Code Dark theme
3. **vscode-light** - VS Code Light theme
4. **catppuccin** - Catppuccin Mocha theme

## 🏗️ How It Works

### Git Worktrees

tasktree uses [git worktrees](https://git-scm.com/docs/git-worktree) to allow multiple working directories per repository. This means you can work on multiple branches simultaneously without stashing or switching contexts.

### Directory Structure

```
~/repos/                    # Your git repositories
  ├── backend/
  ├── frontend/
  └── infrastructure/

~/tasks/                    # Task worktrees
  ├── FEAT-123/
  │   ├── backend/          # Worktree on branch FEAT-123
  │   ├── frontend/         # Worktree on branch FEAT-123
  │   └── infrastructure/   # Worktree on branch FEAT-123
  └── BUG-456/
      └── backend/          # Worktree on branch BUG-456
```

### Task Workflow

1. **Create task** → Creates worktrees in `~/tasks/{task-name}/{repo}` on branch `{task-name}`
2. **Work on code** → Each worktree is a full git working directory
3. **Commit/push** → Use lazygit (`g`) or shell (`Enter`) for git operations
4. **Delete task** → Removes all worktrees and cleans up directories

## 🛠️ Development

### Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/tasktree.git
cd tasktree

# Install mise (if not already installed)
curl https://mise.run | sh

# Install dependencies
mise install
mise run install

# Run tests
mise run test

# Run with dev console
mise run dev
```

### Commands

```bash
mise run install       # Install dependencies
mise run test          # Run tests
mise run test:cov      # Run tests with coverage
mise run lint          # Run linter
mise run lint:fix      # Auto-fix lint issues
mise run format        # Format code
mise run dev           # Run in dev mode with console
mise run run           # Run normally
```

### Project Structure

```
tasktree/
├── tasktree/
│   ├── services/          # Business logic
│   │   ├── config.py      # Configuration management
│   │   ├── task_manager.py# Task/worktree CRUD
│   │   └── git_ops.py     # Git operations
│   ├── widgets/           # UI components
│   │   ├── task_list.py   # Task list widget
│   │   ├── worktree_list.py
│   │   ├── status_panel.py
│   │   ├── create_modal.py
│   │   └── setup_modal.py
│   ├── themes/            # Color themes
│   │   └── __init__.py
│   └── app.py             # Main application
├── tests/                 # Test suite (48 tests)
├── specs/                 # Technical specifications
├── PRD.md                 # Product requirements
├── OPENSPEC.md           # Architecture documentation
└── ROADMAP.md            # Development roadmap
```

### Running Tests

```bash
# All tests
mise run test

# Single test
pytest tests/test_app.py::TestTaskTreeApp::test_app_starts -v

# With coverage
mise run test:cov
```

## 🤝 Contributing

Contributions are welcome! Please see our [Contributing Guide](./CONTRIBUTING.md) for details.

### Development Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`mise run test`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Code Style

- Python 3.13+
- Type hints required
- Follow PEP 8 (enforced by Ruff)
- Test coverage >80%

## 📋 Requirements

- Python 3.13 or higher
- Git 2.0 or higher
- Terminal with 256-color support
- Unix-like OS (macOS, Linux, WSL on Windows)

## 🐛 Troubleshooting

### "No repositories found"

Ensure your `repos_dir` contains git repositories:
```bash
ls ~/repos
# Should show directories with .git folders
```

### "Worktree creation failed"

- Check that the base branch exists in the repository
- Ensure you have write permissions to the tasks directory
- Verify git is installed and in your PATH

### Theme not changing

Press `t` to cycle themes. If issues persist, delete `~/.config/tasktree/config.toml` and reconfigure.

### Config not found

Run the setup wizard:
```bash
rm ~/.config/tasktree/config.toml
tasktree  # Will show setup wizard
```

## 📚 Resources

- [Git Worktree Documentation](https://git-scm.com/docs/git-worktree)
- [Textual Framework](https://textual.textualize.io/)
- [Project Roadmap](./ROADMAP.md)
- [Technical Specs](./specs/)

## 🗺️ Roadmap

See [ROADMAP.md](./ROADMAP.md) for detailed plans.

### Upcoming Features

- **v0.2.0**: Config file support, custom keybindings, performance optimizations
- **v0.3.0**: Search/filter, task templates, task archiving
- **v0.4.0**: Task metadata (JIRA integration), git hooks, automation
- **v1.0.0**: Stable release, comprehensive documentation

## 📄 License

MIT License - see [LICENSE](./LICENSE) for details.

## 🙏 Acknowledgments

- Inspired by [lazygit](https://github.com/jesseduffield/lazygit)
- Built with [Textual](https://github.com/Textualize/textual)
- Themes adapted from VS Code and Catppuccin

## 💬 Support

- 🐛 [Report a bug](https://github.com/yourusername/tasktree/issues)
- 💡 [Request a feature](https://github.com/yourusername/tasktree/issues)
- 💬 [Discussions](https://github.com/yourusername/tasktree/discussions)

---

**Made with ❤️ by developers, for developers**

*Star ⭐ this repo if you find it useful!*
