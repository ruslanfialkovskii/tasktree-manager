# tasktree-manager

> A beautiful TUI for managing git worktrees across multiple repositories

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-pytest-green.svg)](./tests/)

**tasktree-manager** is a terminal user interface (TUI) application for managing development tasks that span multiple git repositories. Create tasks, organize worktrees, and track status across your entire codebase—all from a beautiful, keyboard-driven interface inspired by [lazygit](https://github.com/jesseduffield/lazygit).

## ✨ Features

- 🎯 **Task-Based Workflow** - Group related worktrees across multiple repositories
- 🌳 **Git Worktree Management** - Create, delete, and manage worktrees seamlessly
- 📊 **Real-Time Status** - See uncommitted changes, branch info, and sync status at a glance
- 🔀 **Sorting & Grouping** - Sort tasks by name/date/status, group worktrees by dirty/clean
- 🎨 **Beautiful Themes** - lazygit-inspired default plus 20+ themes (Catppuccin, Tokyo Night, Nord, ...) via Command Palette (Ctrl+P)
- ⌨️ **Keyboard-First** - Navigate and control everything without touching the mouse
- 🚀 **Fast & Responsive** - Parallel git operations with loading indicators
- 🔧 **Flexible Configuration** - TOML config file, custom keybindings, environment variables
- 🤖 **Headless CLI** - Create, list, inspect, finish, and delete tasks from scripts and AI agents without opening the TUI
- 🛰️ **Agent Dashboard** - Live Claude Code session state per worktree (from `claude agents`), plus one-key background-agent dispatch — the multi-repo agent view Claude Code lacks natively
- ✻ **Session Recap** - The Info panel shows each task's latest Claude Code session: title, last turn duration, and Claude's own idle recap of what was done and what comes next — read straight from the transcript, no CLI call
- 🔀 **Forge-Aware Safety** - MR/PR and CI state via `glab`/`gh`; squash- and rebase-merged branches count as merged instead of blocking deletion forever
- 🗂️ **Epics** - Group related tasks under an epic: a foldable row with rolled-up dirty and Claude state, `E` to attach tasks, and an epic log and `epic ask` so the Claude sessions of one epic share what they know
- 🧷 **zellij Tabs** - Run the TUI inside zellij (or set `zellij_autostart`) and `o`/`e`/`c` open zellij tabs that keep running across a terminal restart; pressing the key again jumps to the open tab ([details](docs/user-guide.md#zellij))
- 📦 **Finish Flow with Archives** - Ending a task saves its combined diff (committed-but-unmerged + uncommitted) and the task-folder files outside the worktrees (plans, ADRs, notes) to an archive before deleting

## 📊 Status Indicators

| Indicator | Meaning |
|-----------|---------|
| `●` red | Uncommitted changes |
| `◆` blue | Has CLAUDE.md file |
| `⟳` magenta | Claude Code session running / agent working |
| `!` yellow | Claude Code session waiting for input |
| `▣` green | Agent session ready (idle) |
| `✓` green | Clean worktree / Claude session ended |
| `✗ N` red | N files changed |
| `↑N` green | N commits ahead of remote |
| `↓N` yellow | N commits behind remote |
| `○` green / `●` magenta / `×` red | MR open / merged / closed |
| `◐` yellow / `✔` green / `✘` red | CI running / passed / failed |
| `▾` / `▸` | Epic, unfolded / folded (`· N` = its task count) |
| `├` / `└` | Task inside the epic above |

## 🚀 Quick Start

### Installation

```bash
# Using pipx (recommended)
pipx install tasktree-manager
```

See the [Installation Guide](docs/installation.md) for other methods and platform-specific instructions.

### First Run

```bash
tasktree-manager
```

On first run, you'll configure:
- **Repositories Directory**: Where your git repos live (e.g., `~/repos`)
- **Tasks Directory**: Where worktrees will be created (e.g., `~/tasks`)

### Basic Workflow

1. **Create a task** - Press `n`, enter task name, select repositories
2. **Work on code** - Press `e` for editor, `g` for lazygit, or `o` for a shell in a new terminal tab
3. **Review changes** - Press `h` to view the diff in [hunk](https://github.com/modem-dev/hunk) (all repos from the task panel, one repo from the worktree panel)
4. **Push changes** - Press `p` to push all worktrees
5. **Delete task** - Press `d` when finished

For detailed workflows and examples, see the [User Guide](docs/user-guide.md).

### Headless CLI

Running `tasktree-manager` with arguments skips the TUI. Use it from scripts and AI agents,
for example a skill that creates a Jira ticket and then the matching task.

#### Tasks

```bash
tasktree-manager create DIC-1901-argocd-tls --repos backend,frontend  # --base sets the base branch
tasktree-manager add-repo DIC-1901-argocd-tls infra
tasktree-manager list --json        # tasks, repos and state: clean / dirty / error
tasktree-manager repos              # repos available in REPOS_DIR
tasktree-manager status             # task of the current folder; --json, --oneline, --forge
tasktree-manager finish DIC-1901-argocd-tls   # safety check, archive, delete; --push, --no-archive
tasktree-manager delete DIC-1901-argocd-tls   # archive, delete; refuses unfinished work
```

`status --oneline` prints a compact `TASK repoA✓ repoB●2↑1` line for a Claude Code
statusline or a shell prompt.

#### Epics

An epic groups related tasks, for example a Jira epic and its child tasks. It is a task
folder too, so it can hold notes, a Claude session and worktrees. Tasks stay in their own
folders; a marker file names their epic. Epics don't nest.

```bash
tasktree-manager epic create DIC-2466-pcaps-epic     # repos are optional for an epic
tasktree-manager create DIC-2861-pcaps-logs --repos infra --epic DIC-2466-pcaps-epic
tasktree-manager epic add DIC-2466-pcaps-epic DIC-2862-pcaps-s3   # attach or move tasks
tasktree-manager epic remove DIC-2862-pcaps-s3      # detach
tasktree-manager epic mark DIC-2466-pcaps-epic      # make an existing task an epic; unmark reverts
tasktree-manager epic list                          # epics and their tasks; --json
```

`list --json` and `status --json` show each task's `kind` (`task` or `epic`) and its `epic`.
`delete` and `finish` refuse an epic that still has tasks, even with `--force`.

#### Sharing context inside an epic

The Claude sessions of one epic can learn from each other:

| Command | What it does |
| --- | --- |
| `epic note "text"` | Adds a note to this task's file in the epic log (`-` reads stdin) |
| `epic log [TASK]` | Shows each task's notes and the recap of its latest Claude session; `--json` |
| `epic ask TASK "question"` | A read-only copy of that task's latest session answers |
| `epic sync` | Refreshes the epic block in existing tasks' `CLAUDE.md` after an upgrade |

Each task's `CLAUDE.md` gets a managed block that explains these commands to its session.

- **Scope:** inside a task folder, the commands reach only that task's epic.
- **Running sessions:** `epic ask` exits with code 3 when the task's session is running and
  prints its name; the asking session then sends it a message with SendMessage.
- **Read-only:** the copy that answers can read files but not change them, can't read
  credential files, and leaves the asked task's session untouched.
- **Cost:** each turn of the copy is a model call on that session's context, 8 turns at
  most (`--max-turns`); `--model sonnet` makes it cheaper.

The [User Guide](docs/user-guide.md#epics) has the details.

#### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Failure; the reason is on stderr |
| 3 | `epic ask` only: the task's session is running; its name is on stdout |

#### Safe delete and archive

`delete` and `finish` run the same safety check as the TUI: uncommitted, unpushed or
unmerged work blocks deletion unless `--force`. With `glab` or `gh` installed, squash and
rebase merges count as merged.

Before deleting, the CLI archives the task's remaining diff as a patch and copies the files
in the task folder outside the worktrees to `<task>-<timestamp>.files/` next to it
(`finish --no-archive` skips both):

- **Skipped:** hidden files, symlinks, `node_modules`, `vendor` and `.terraform` folders,
  and an unedited generated `CLAUDE.md`.
- **Left out with a warning:** key material (`*.pem`, `*.key`, `id_rsa`, kubeconfigs,
  `*.tfstate`, `credentials*.json`), files over 10 MB, and files past 100 MB in total.
- **Always stops the delete:** a diff that cannot be archived; the CLI prints the partial
  archive's path.
- **Stops the delete unless `--force`:** a task file that cannot be read or copied.

In both cases the TUI stops too, names what was left out in the messages panel, and asks
again before it deletes.

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
| `a` | Add repo | `h` | Show diff (hunk) |
| `d` | Delete task | `e` | Open editor |
| `p` | Push all | `o` | Open folder |
| `P` | Pull all | `y` | Clone task |
| `c` | Claude (resume) | `C` | Claude (new) |
| `b` | Dispatch agent | `D` | Delete worktree |
| `r` | Refresh | `s` | Sort tasks |
| `S` | Group worktrees | `m` | Messages |
| `t` | Cycle theme | `Tab` | Next panel |
| `R` | Rename task | `E` | Set epic |
| `enter` | Fold epic | | |
| `?` | Show help | `q` | Quit |

**Themes:** The default `tasktree` theme pairs a lazygit-classic ANSI palette with layered panels, numbered title bars, green focus borders, and a keycap footer. Five more design-system palettes ship tuned to the same shape — tokyo-night, catppuccin-mocha, gruvbox, dracula, nord — and every other Textual built-in theme works too (`Ctrl+P` to switch); the whole UI is styled with Textual design tokens, so any theme restyles it consistently.

## 🏗️ How It Works

tasktree-manager uses [git worktrees](https://git-scm.com/docs/git-worktree) to create isolated working directories for each task. Work on multiple branches simultaneously without stashing or context switching.

**Directory Structure:**
```
~/repos/                    # Your git repositories (never modified)
  ├── backend/
  └── frontend/

~/tasks/                    # Task worktrees (managed by tasktree-manager)
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
git clone https://github.com/ruslanfialkovskii/tasktree-manager.git
cd tasktree-manager
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
- Unix-like OS (macOS, Linux, WSL2). Opening a folder, editor or Claude session in a
  new terminal tab (`o`, `e`, `c`) opens a zellij tab when the TUI runs inside zellij,
  on any OS. Otherwise it drives Ghostty via AppleScript and is macOS-only; elsewhere
  those keys show a notice

See [Installation Guide](docs/installation.md) for detailed requirements and setup.

## 🐛 Troubleshooting

Common issues and quick fixes:

- **"No repositories found"** - Check `repos_dir` in config contains git repos
- **"Worktree creation failed"** - Verify base branch exists and you have permissions
- **Theme not changing** - Use `Ctrl+P` to select theme, or check config file permissions
- **Command not found** - Run `pipx ensurepath` and restart terminal

For comprehensive troubleshooting, see the [Troubleshooting Guide](docs/troubleshooting.md).

## 🗺️ Roadmap

Recently shipped: agent dashboard (per-worktree Claude session badges + background dispatch),
forge-aware merged detection (glab/gh, squash/rebase merges), MR/CI status badges,
guided `finish` flow that archives the diff and the task-folder files, `status` subcommand
for scripts and statuslines, Claude session recap in the Info panel, epics in the CLI, the
task list and each task's CLAUDE.md.

Ideas and bugs go to [GitHub Issues](https://github.com/ruslanfialkovskii/tasktree-manager/issues).

See [CHANGELOG.md](CHANGELOG.md) for the release history.

## 📄 License

MIT License - see [LICENSE](./LICENSE) for details.

## 🙏 Acknowledgments

- Inspired by [lazygit](https://github.com/jesseduffield/lazygit)
- Built with [Textual](https://github.com/Textualize/textual)
- Themes adapted from VS Code and Catppuccin

## 💬 Support & Community

- 🐛 [Bug Reports](https://github.com/ruslanfialkovskii/tasktree-manager/issues)
- 💡 [Feature Requests](https://github.com/ruslanfialkovskii/tasktree-manager/issues)
- 💬 [Discussions](https://github.com/ruslanfialkovskii/tasktree-manager/discussions)
- 📖 [Documentation](docs/)

---

**Made with ❤️ by developers, for developers** | [⭐ Star this repo](https://github.com/ruslanfialkovskii/tasktree-manager)
