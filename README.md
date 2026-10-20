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

Running `tasktree-manager` with arguments skips the TUI — useful for scripts and AI-agent
workflows (e.g. a skill that creates a Jira ticket and then the matching task):

```bash
tasktree-manager create DIC-1901-argocd-tls --repos backend,frontend  # --base overrides the default base branch
tasktree-manager list --json     # tasks with repos and state: clean / dirty / error (plain text without --json)
tasktree-manager repos           # available repos in REPOS_DIR
tasktree-manager add-repo DIC-1901-argocd-tls infra
tasktree-manager status                       # current task inferred from $PWD; also --json / --oneline / --forge
tasktree-manager finish DIC-1901-argocd-tls   # safety sweep -> archive diff + task files -> delete; --push / --no-archive / --force
tasktree-manager delete DIC-1901-argocd-tls   # archive diff + task files -> delete; refuses on unfinished work; --force overrides
```

Epics group related tasks, for example a Jira epic and its child tasks. An epic is a task
folder with a `.tasktree_kind` marker. It can hold its own notes, Claude session and
worktrees. A child task names its epic in `.tasktree_epic`. Folders never move:

```bash
tasktree-manager epic create DIC-2466-pcaps-epic             # --repos is optional for an epic
tasktree-manager create DIC-2861-pcaps-logs --repos infra --epic DIC-2466-pcaps-epic
tasktree-manager epic add DIC-2466-pcaps-epic DIC-2862-pcaps-s3  # attach or move existing tasks
tasktree-manager epic remove DIC-2862-pcaps-s3                # detach
tasktree-manager epic mark DIC-2466-pcaps-epic                # turn an existing task into an epic; unmark reverts
tasktree-manager epic list                                    # epics and their tasks; also --json
tasktree-manager epic note "chose layout A for the S3 keys"   # add a note to this task's file in the epic log
tasktree-manager epic log                                     # notes and latest session recap of every task in the epic
tasktree-manager epic log DIC-2862-pcaps-s3 --json            # one task (or a whole epic by its name), as JSON
tasktree-manager epic ask DIC-2862-pcaps-s3 "which bucket?"    # a read-only copy of that task's latest session answers
tasktree-manager epic sync                                    # refresh the CLAUDE.md epic block after an upgrade
```

Each task's `CLAUDE.md` gets a managed block naming its epic and how to find sibling
tasks; it follows every epic change and leaves the rest of the file alone. The block
also tells the session about the epic log: one notes file per task in `epic-log/` in the
epic folder, written with `epic note` and read with `epic log`, which adds the recap of each
task's latest Claude session (in the task folder or one of its worktrees). Inside a task
folder, `epic note` writes only that task's notes and `epic log` reads only its epic;
`epic note -` reads the text from stdin. Notes of a task that left the epic stay readable.
`epic ask TASK "question"` resumes a copy of that task's latest Claude session to answer:
forked and not saved, hooks off, only the Read/Grep/Glob tools, no MCP servers, so the
task's own session and status stay untouched; credential files (`~/.ssh`, `~/.aws`, `.env`
and similar) are denied to it. It exits 3 without asking when the task's session is
running; the calling session then messages it with SendMessage (`--fork` asks a copy
anyway). Each turn of the copy is a model call on that session's context, at most
`--max-turns` (default 8); `--model sonnet` makes it cheaper.
Epics don't
nest. `list --json` and `status --json` carry `kind` (`task` or `epic`) and
`epic` (the parent epic or `null`). `delete` and `finish` refuse an epic that still has
tasks, even with `--force`.

Exit code is 0 on success, 1 on failure with the reason on stderr, and 3 from `epic ask`
when the task's session is running (its name goes to stdout). `delete` and `finish` run
the same safety check as the TUI (uncommitted, unpushed, or unmerged work blocks deletion);
with `glab`/`gh` installed, squash/rebase-merged branches are recognized as merged. If the
diff cannot be archived for any repo, the CLI stops before deleting and prints the path of
the partial archive; the TUI warns and deletes anyway. Files in the task folder outside the
worktrees are copied to `<task>-<timestamp>.files/` next to the patch:

- Skipped silently: hidden files, symlinks, `node_modules`/`vendor`/`.terraform` folders and
  an unedited generated `CLAUDE.md`.
- Left out with a warning: key material (`*.pem`, `*.key`, `id_rsa`, kubeconfigs,
  `*.tfstate`, `credentials*.json`), files over 10 MB and files past 100 MB in total.
- A file that cannot be read or copied stops `delete`/`finish` before anything is removed,
  unless `--force`; the TUI warns and deletes anyway.
`status --oneline` emits a compact `TASK repoA✓ repoB●2↑1` summary that slots straight into
a Claude Code statusline or shell prompt.

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
  new terminal tab (`o`, `e`, `c`) drives Ghostty via AppleScript and is macOS-only;
  elsewhere those keys show a notice

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
