# Roadmap: tasktree

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
- [x] Config file support (`~/.config/tasktree/config.toml`)
- [x] Custom keybindings configuration
- [x] Improved error messages
- [ ] Loading indicators for slow operations
- [x] Help text improvements

#### Improvements
- [ ] Optimize git status queries (parallel execution)
- [ ] Better theme switching (instant without reload)
- [ ] Improved modal animations
- [ ] Status panel scrolling for large diffs

#### Documentation
- [ ] User guide (README expansion)
- [ ] Installation guide (PyPI, Homebrew, pipx)
- [ ] Configuration reference
- [ ] Troubleshooting guide
- [ ] Video demo/walkthrough

#### Quality
- [ ] Increase test coverage to 85%
- [ ] Add integration tests for git workflows
- [ ] Performance benchmarks
- [ ] Memory leak testing

---

### v0.3.0 - Enhanced Workflows

**Focus**: Productivity features, search/filter

#### Features
- [ ] Search tasks by name (/)
- [ ] Filter worktrees by status (dirty/clean)
- [ ] Task templates (create from existing tasks)
- [ ] Task archiving (preserve history)
- [ ] Recent tasks list (quick switch)

#### Git Operations
- [ ] Stash management
- [ ] Branch comparison (diff between worktrees)
- [ ] Commit history view
- [ ] Cherry-pick support

#### UI/UX
- [ ] Sort tasks (by name, date, status)
- [ ] Worktree groups (by repo, status)
- [ ] Quick actions menu (?)
- [ ] Contextual help tooltips

---

### v0.4.0 - Advanced Features

**Focus**: Metadata, collaboration, automation

#### Task Metadata
- [ ] Task descriptions
- [ ] JIRA/GitHub issue linking
- [ ] Tags/labels
- [ ] Due dates
- [ ] Custom fields

#### Collaboration
- [ ] Export/import task configs
- [ ] Team templates repository
- [ ] Shared task definitions
- [ ] Task handoff workflow

#### Automation
- [ ] Git hooks integration (pre-commit, pre-push)
- [ ] Auto-cleanup stale tasks
- [ ] Scheduled pulls/pushes
- [ ] Custom scripts per task

---

### v1.0.0 - Stable Release

**Focus**: Production-ready, comprehensive docs

#### Stability
- [ ] API stability guarantee
- [ ] Comprehensive error handling
- [ ] Graceful degradation
- [ ] Backup/restore functionality

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

### Phase 4: Collaboration

- Remote worktree management (SSH)
- Shared team dashboard
- Real-time collaboration indicators
- Code review integration
- CI/CD status tracking

### Phase 5: Enterprise

- LDAP/SSO integration
- Audit logging
- Compliance features
- Multi-tenant support
- Enterprise deployment guides

---

## Success Metrics

### Adoption Goals

| Metric | v0.3 | v0.5 | v1.0 |
|--------|------|------|------|
| GitHub Stars | 100 | 250 | 500 |
| PyPI Downloads/month | 500 | 2000 | 5000 |
| Active Contributors | 3 | 5 | 10 |
| Issues Closed | 20 | 50 | 100 |

### Quality Goals

| Metric | Target |
|--------|--------|
| Test Coverage | >85% |
| Bug Reports/month | <10 |
| Response Time | <48h |
| User Satisfaction | 4.5+/5 |

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
1. Theme switching requires list reload (v0.2.0)
2. No async git operations (v0.3.0)
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

| Dependency | Current | Notes |
|------------|---------|-------|
| Textual | 0.89.1 | Breaking changes possible |
| Rich | 13.9.4 | Stable |
| Python | 3.13+ | New features to leverage |

---

## Breaking Changes Policy

- **Pre-1.0**: Breaking changes allowed with migration guide
- **Post-1.0**: Semantic versioning strictly followed
- **Deprecation**: 2 minor versions notice before removal

---

## Alternatives & Competition

### Similar Tools
- **lazygit**: Git TUI (single repo focus)
- **tig**: Git browser (read-only focus)
- **gh**: GitHub CLI (cloud integration)
- **git-machete**: Branch management

### Our Differentiators
1. Multi-repository focus
2. Worktree-first design
3. Task-oriented workflow
4. Aesthetic excellence
5. Keyboard-first UX

---

## Research & Exploration

### Features Under Investigation
- [ ] Native Windows support (without WSL)
- [ ] Web-based remote UI
- [ ] Mobile app for monitoring
- [ ] VS Code extension integration
- [ ] tmux/screen session management

### Technical Experiments
- [ ] Rust rewrite for performance
- [ ] Web assembly for browser support
- [ ] GraphQL API for extensibility
- [ ] Real-time collaboration via WebRTC

---

## Notes

- Community feedback heavily influences priorities
- Security issues prioritized regardless of roadmap
- Performance regressions block releases
