# tasktree

> A beautiful TUI for managing git worktrees across multiple repositories

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-64%20passed-green.svg)](./tests/)

**tasktree** is a terminal user interface (TUI) application for managing development tasks that span multiple git repositories. Create tasks, organize worktrees, and track status across your entire codebase—all from a beautiful, keyboard-driven interface inspired by [lazygit](https://github.com/jesseduffield/lazygit).

## ✨ Features

- 🎯 **Task-Based Workflow** - Group related worktrees across multiple repositories
- 🌳 **Git Worktree Management** - Create, delete, and manage worktrees seamlessly
- 📊 **Real-Time Status** - See uncommitted changes, branch info, and sync status at a glance
- 🎨 **Beautiful Themes** - 7 built-in themes via Command Palette (Ctrl+P)
- ⌨️ **Keyboard-First** - Navigate and control everything without touching the mouse
- 🚀 **Fast & Responsive** - Parallel git operations with loading indicators
- 🔧 **Flexible Configuration** - TOML config file, custom keybindings, environment variables

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
  n New task  d Delete  g Lazygit  p Push  r Refresh  ? Help  q Quit
```

## 🚀 Quick Start

### Installation

```bash
# Using pipx (recommended)
pipx install tasktree
```

See the [Installation Guide](docs/installation.md) for other methods and platform-specific instructions.

### First Run

```bash
tasktree
```

On first run, you'll configure:
- **Repositories Directory**: Where your git repos live (e.g., `~/repos`)
- **Tasks Directory**: Where worktrees will be created (e.g., `~/tasks`)

### Basic Workflow

1. **Create a task** - Press `n`, enter task name, select repositories
2. **Work on code** - Press `g` for lazygit or `Enter` for shell
3. **Push changes** - Press `p` to push all worktrees
4. **Delete task** - Press `d` when finished

For detailed workflows and examples, see the [User Guide](docs/user-guide.md).

## 📖 Documentation

**Complete guides:**
- [Installation Guide](docs/installation.md) - Platform-specific setup, system requirements, troubleshooting
- [User Guide](docs/user-guide.md) - Workflows, keyboard shortcuts, tips and best practices
- [Configuration Reference](docs/configuration.md) - All config options, keybindings, themes
- [Troubleshooting Guide](docs/troubleshooting.md) - Common issues and solutions

**Quick Reference:**

| Key | Action | Key | Action |
|-----|--------|-----|--------|
| `n` | New task | `g` | Open lazygit |
| `a` | Add repo | `Enter` | Open shell |
| `d` | Delete task | `p` | Push all |
| `r` | Refresh | `?` | Show help |
| `Tab` | Next panel | `q` | Quit |

**Themes:** Press `Ctrl+P` to switch between 7 built-in themes (textual-dark, nord, gruvbox, tokyo-night, monokai, dracula, textual-light).

## 🏗️ How It Works

tasktree uses [git worktrees](https://git-scm.com/docs/git-worktree) to create isolated working directories for each task. Work on multiple branches simultaneously without stashing or context switching.

**Directory Structure:**
```
~/repos/                    # Your git repositories (never modified)
  ├── backend/
  └── frontend/

~/tasks/                    # Task worktrees (managed by tasktree)
  ├── FEAT-123/
  │   ├── backend/          # Worktree on branch FEAT-123
  │   └── frontend/         # Worktree on branch FEAT-123
  └── BUG-456/
      └── backend/
```

Learn more in the [User Guide](docs/user-guide.md#core-concepts).

## 🛠️ Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed development setup and guidelines.

**Quick Start:**
```bash
git clone https://github.com/yourusername/tasktree.git
cd tasktree
mise install
mise run install
mise run test
```

**Common Commands:**
```bash
mise run dev           # Run with dev console
mise run test          # Run tests
mise run lint:fix      # Auto-fix lint issues
```

## 🤝 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Quick contribution steps:**
1. Fork and create feature branch
2. Make changes and add tests
3. Run `mise run test` and `mise run lint`
4. Submit pull request

## 📋 Requirements

- Python 3.10+ (3.13+ recommended)
- Git 2.0+
- 256-color terminal
- Unix-like OS (macOS, Linux, WSL2)

See [Installation Guide](docs/installation.md) for detailed requirements and setup.

## 🐛 Troubleshooting

Common issues and quick fixes:

- **"No repositories found"** - Check `repos_dir` in config contains git repos
- **"Worktree creation failed"** - Verify base branch exists and you have permissions
- **Theme not changing** - Use `Ctrl+P` to select theme, or check config file permissions
- **Command not found** - Run `pipx ensurepath` and restart terminal

For comprehensive troubleshooting, see the [Troubleshooting Guide](docs/troubleshooting.md).

## 🗺️ Roadmap

Current: **v0.2.0** - Configuration system, themes, comprehensive documentation

Upcoming:
- **v0.3.0** - Search/filter, task templates, archiving
- **v0.4.0** - JIRA integration, git hooks, automation
- **v1.0.0** - Stable release

See [ROADMAP.md](ROADMAP.md) and [CHANGELOG.md](CHANGELOG.md) for details.

## 📄 License

MIT License - see [LICENSE](./LICENSE) for details.

## 🙏 Acknowledgments

- Inspired by [lazygit](https://github.com/jesseduffield/lazygit)
- Built with [Textual](https://github.com/Textualize/textual)
- Themes adapted from VS Code and Catppuccin

## 💬 Support & Community

- 🐛 [Bug Reports](https://github.com/yourusername/tasktree/issues)
- 💡 [Feature Requests](https://github.com/yourusername/tasktree/issues)
- 💬 [Discussions](https://github.com/yourusername/tasktree/discussions)
- 📖 [Documentation](docs/)

---

**Made with ❤️ by developers, for developers** | [⭐ Star this repo](https://github.com/yourusername/tasktree)
