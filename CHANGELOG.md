# Changelog

All notable changes to tasktree will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Search and filter functionality
- Task templates
- Task archiving
- JIRA/Linear integration
- Git hooks support
- Custom task metadata

## [0.2.0] - TBD

### Added
- Config file support (`~/.config/tasktree/config.toml`)
- Custom keybindings configuration (14 customizable actions)
- Parallel git operations (push/pull all worktrees simultaneously)
- Loading indicators for async operations
- 7 built-in themes (textual-dark, textual-light, nord, gruvbox, tokyo-night, monokai, dracula)
- Theme switcher via Command Palette (Ctrl+P)
- Environment variable overrides for configuration
- XDG Base Directory support for config location
- Comprehensive documentation:
  - Installation guide with platform-specific instructions
  - Configuration reference with all options documented
  - User guide with workflows and best practices
  - Troubleshooting guide with common issues and solutions
- CHANGELOG.md for version history tracking

### Changed
- Migrated from custom theming to Textual's built-in design tokens
- Improved modal animations with entrance effects
- Enhanced safety checks before task deletion
- Better error handling and user feedback
- Recursive repository scanning in REPOS_DIR

### Fixed
- Theme persistence across sessions
- Configuration precedence (env vars → config file → defaults)
- Modal rendering performance

## [0.1.0] - 2026-01-XX

### Added
- Initial release
- Task-based worktree management
- 3-panel TUI interface (tasks, worktrees, status)
- Create/delete tasks with multiple repositories
- Add repositories to existing tasks
- Git status display for worktrees
- Integration with lazygit
- Shell access in worktrees
- Push/pull operations
- Safety checks for task deletion
- Dirty task indicators
- Real-time status updates
- Basic configuration (REPOS_DIR, TASKS_DIR)
- Setup wizard for first-time configuration
- 64 test suite with pytest

### Technical
- Built with Textual 7.0+
- Python 3.10+ support
- Git 2.0+ integration
- Cross-platform (macOS, Linux, WSL2)

---

## Version History

- **0.2.0** - Configuration system, custom keybindings, themes, comprehensive documentation
- **0.1.0** - Initial release with core functionality

## Upgrade Notes

### From 0.1.0 to 0.2.0

**Configuration:**
- Old: Configuration via environment variables only
- New: Config file at `~/.config/tasktree/config.toml` (auto-created on first run)
- Migration: Environment variables still work and override config file

**Themes:**
- Old: Single default theme
- New: 7 themes available via Ctrl+P
- Theme preference saved to config file

**Keybindings:**
- Old: Hardcoded keybindings
- New: Customizable via `[keybindings]` section in config.toml
- Default keybindings unchanged

**No breaking changes** - 0.1.0 workflows continue to work in 0.2.0.

## Links

- [Repository](https://github.com/yourusername/tasktree)
- [Documentation](docs/)
- [Issue Tracker](https://github.com/yourusername/tasktree/issues)
- [Roadmap](ROADMAP.md)
