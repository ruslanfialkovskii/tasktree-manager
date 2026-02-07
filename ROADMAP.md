# Roadmap: tasktree-manager

## Vision

Build the most intuitive TUI for managing git worktrees across multiple repositories, with a focus on developer productivity and aesthetic excellence.

## Current Status: v0.1.0 (MVP Complete)

✅ Core task management
✅ Worktree operations
✅ Git status display
✅ Theme system (4 themes)
✅ Keyboard navigation
✅ Lazygit integration
✅ Comprehensive test suite

---

## Release Timeline

### v0.2.0 - Polish & Stability

**Focus**: Bug fixes, UX improvements, documentation

#### Features

- [x] Config file support (`~/.config/tasktree-manager/config.toml`)
- [x] Custom keybindings configuration
- [x] Improved error messages
- [x] Loading indicators for slow operations
- [x] Help text improvements
- [x] Open folder in terminal (Ghostty support)

#### Improvements

- [x] Optimize git status queries (parallel execution)
- [x] Better theme switching (Textual built-in themes via Command Palette)
- [x] Improved modal animations
- [x] Status panel scrolling for large diffs

#### Documentation

- [x] User guide (README expansion + docs/user-guide.md)
- [x] Installation guide (docs/installation.md - pipx, pip, from source)
- [x] Configuration reference (docs/configuration.md)
- [x] Troubleshooting guide (docs/troubleshooting.md)
- [x] CHANGELOG.md for version tracking

#### Quality

- [x] Increase test coverage to 85%
- [x] Add integration tests for git workflows
- [x] Memory leak testing

#### CI/CD

- [x] Linting pipeline (ruff check + format)
- [x] Test pipeline (multi-Python matrix)
- [x] Coverage reporting (Codecov)
- [x] Build verification pipeline
- [x] Automated semantic releases (python-semantic-release + hatch-vcs)

---

### v0.3.0 - Enhanced Workflows

**Focus**: Productivity features, search/filter

#### Features

- [x] Recent messages
- [x] Claude code integration

#### UI/UX

- [x] Sort tasks (by name, date, status) - press `s` to cycle
- [x] Worktree groups (by dirty/clean status) - press `S` to toggle

---

### v0.4.0 - Advanced Features

**Focus**: Metadata, collaboration, automation

#### Task Metadata

- [ ] Task descriptions
- [ ] JIRA/GitLab issue linking
- [ ] Tags/labels
- [ ] Due dates

#### Automation

- [ ] Git hooks integration (pre-commit, pre-push)
- [ ] Auto-cleanup stale tasks
- [ ] Scheduled pulls/pushes
- [ ] Custom scripts per task

#### Quality

- [ ] Performance benchmarks

---

### v1.0.0 - Stable Release

**Focus**: Production-ready, comprehensive docs

#### Stability

- [ ] API stability guarantee
- [ ] Comprehensive error handling
- [ ] Graceful degradation

#### Performance

- [ ] < 500ms startup on 100+ tasks
- [ ] Lazy loading for large task lists
- [ ] Caching layer for git status
- [ ] Incremental updates

#### Documentation

- [ ] Complete API reference
- [ ] Architecture deep-dive
- [ ] Contributing guide
- [ ] Plugin system docs

#### Distribution

- [ ] PyPI package
- [ ] Homebrew formula
- [ ] Arch AUR package
- [ ] Debian/Ubuntu package

---

## Future Phases (Post-1.0)

### Phase 2: Extensibility

- Plugin system for custom commands
- External tool integrations (Slack, Discord)
- Custom themes from config files
- Webhook support for notifications
- API for programmatic control

### Phase 3: Intelligence

- AI-powered task suggestions
- Smart worktree cleanup recommendations
- Conflict prediction
- Dependency detection across repos
- Usage analytics and insights

---

## Community & Contribution

### Open Source Strategy

- Weekly releases during active development
- Public roadmap updates
- Community voting on features
- Contributor recognition program

### Communication Channels

- GitHub Discussions for Q&A
- Discord server for real-time chat
- Monthly dev updates blog
- YouTube tutorials

---

## Technical Debt

### Known Issues

1. ~~Theme switching requires list reload~~ - Fixed (uses Textual built-in themes)
2. ~~No async git operations~~ - Fixed (parallel execution with ThreadPoolExecutor)
3. Limited error recovery (v0.4.0)
4. No logging system (v0.2.0)
5. Hardcoded paths in tests (v0.2.0)

### Architectural Improvements

1. Extract git layer to interface (testability)
2. Add event bus for widget communication
3. Implement command pattern for undo/redo
4. Create plugin architecture
5. Add telemetry framework (opt-in)

---

## Dependencies to Watch

| Dependency | Current | Notes                    |
| ---------- | ------- | ------------------------ |
| Textual    | 7.3.0   | Latest stable            |
| Rich       | 13.9.4  | Stable                   |
| Python     | 3.13+   | New features to leverage |

---

## Breaking Changes Policy

- **Pre-1.0**: Breaking changes allowed with migration guide
- **Post-1.0**: Semantic versioning strictly followed
- **Deprecation**: 2 minor versions notice before removal

---

## Competition

1. Multi-repository focus
2. Worktree-first design
3. Task-oriented workflow
4. Aesthetic excellence
5. Keyboard-first UX

---

## Research & Exploration

### Features Under Investigation

- [ ] Native Windows support (without WSL)

### Technical Experiments

- [ ] Golang rewrite for performance
- [ ] Web assembly for browser support
- [ ] GraphQL API for extensibility
- [ ] Real-time collaboration via WebRTC

---

## Notes

- Community feedback heavily influences priorities
- Security issues prioritized regardless of roadmap
- Performance regressions block releases
