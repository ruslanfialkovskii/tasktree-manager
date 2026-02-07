# Product Requirements Document: tasktree-manager

## Overview

**Product**: tasktree-manager
**Version**: 0.1.0
**Last Updated**: 2026-01-22
**Status**: Active Development

## Executive Summary

tasktree-manager is a TUI (Terminal User Interface) application for managing git worktree-based development tasks. It provides a lazygit-inspired interface for organizing work across multiple repositories within a single task context.

## Problem Statement

Developers working on features that span multiple repositories face challenges:
- Managing multiple git worktrees manually is cumbersome
- Context switching between repositories is time-consuming
- No unified view of task progress across repositories
- Difficult to track dirty state across multiple worktrees

## Target Users

- Backend/fullstack developers working with microservices
- Developers managing monorepo-adjacent architectures
- Teams using feature-branch workflows across multiple repos
- Engineers who prefer terminal-based tools

## Goals

### Primary Goals
1. Simplify multi-repository worktree management
2. Provide instant visibility into task status across repos
3. Reduce context-switching overhead
4. Integrate seamlessly with existing git workflows

### Secondary Goals
1. Match lazygit's UX quality and aesthetics
2. Support common git operations (push/pull/status)
3. Enable theme customization
4. Provide keyboard-first interface

## Features

### Core Features (MVP)

#### 1. Task Management
- **Create Task**: Create named tasks with associated worktrees
- **Delete Task**: Remove tasks and clean up worktrees
- **List Tasks**: View all tasks with dirty indicators
- **Task Status**: Visual indicators for uncommitted changes

#### 2. Worktree Management
- **Add Worktree**: Add repositories to existing tasks
- **List Worktrees**: View all worktrees within a task
- **Worktree Status**: Branch name, sync status, change counts
- **Auto-branch**: Worktrees use task name as branch name

#### 3. Git Operations
- **Status Display**: Real-time git status for selected worktree
- **Push/Pull**: Bulk operations across all worktrees in task
- **Lazygit Integration**: Open lazygit for detailed operations
- **Shell Access**: Open shell in worktree directory

#### 4. UI/UX
- **3-Panel Layout**: Tasks | Worktrees | Status
- **Keyboard Navigation**: j/k, tab, enter for navigation
- **Visual Feedback**: Color-coded status indicators
- **Theme Support**: 4 built-in themes (default, vscode-dark, vscode-light, catppuccin)

### Future Features (Post-MVP)

#### Phase 2
- Worktree templates (start tasks from template branches)
- Task archiving (preserve completed tasks)
- Search/filter tasks and worktrees
- Custom keybindings configuration

#### Phase 3
- Task metadata (JIRA ticket IDs, descriptions, due dates)
- Team collaboration (share task configs)
- Git hooks integration (pre-commit, pre-push)
- Multiple task directory support

#### Phase 4
- Remote worktree management (SSH)
- CI/CD status integration
- Pull request status tracking
- Task analytics and reporting

## User Stories

### As a developer, I want to...
1. Create a task spanning multiple repos so I can organize my work
2. See which repos have uncommitted changes at a glance
3. Open lazygit in a specific worktree to commit changes
4. Push all worktrees at once when my feature is ready
5. Delete a task and clean up all worktrees when work is complete
6. Switch between tasks without losing context
7. Customize the theme to match my terminal setup

## Technical Requirements

### Performance
- Start time: < 1 second
- Task list refresh: < 200ms
- Git status update: < 100ms per worktree
- Support 100+ tasks, 10+ repos per task

### Compatibility
- Python 3.13+
- Cross-platform (macOS, Linux, Windows with WSL)
- Git 2.0+
- Works in standard terminals (no GUI required)

### Dependencies
- Textual (TUI framework)
- Rich (text rendering)
- Python standard library (subprocess, pathlib)

### Configuration
- Environment variables: `REPOS_DIR`, `TASKS_DIR`
- Default directories: `~/repos`, `~/.wtasks`
- Themes: Stored in code, switchable at runtime

## Success Metrics

### Adoption
- GitHub stars: 100+ in first 3 months
- Weekly active users: 50+ in first 6 months

### Usage
- Average tasks per user: 5+
- Average session time: 10+ minutes
- Task creation to deletion time: 2+ days (indicates real use)

### Quality
- Test coverage: >80%
- Bug reports: <5 per month after v1.0
- User satisfaction: 4.5+ stars

## Out of Scope (V1)

- GUI version
- Cloud sync
- Mobile app
- Integration with non-git VCS
- Built-in code review
- Conflict resolution UI

## Open Questions

1. Should we support tasks with different branch names per repo?
2. How to handle worktree conflicts (branch already exists)?
3. Should we auto-fetch on status refresh?
4. Config file format (TOML vs YAML vs JSON)?

## Dependencies & Risks

### Dependencies
- Git must be installed and in PATH
- Repositories must exist in REPOS_DIR
- User must have filesystem permissions for TASKS_DIR

### Risks
1. **Git worktree limitations**: Some git operations don't work in worktrees
2. **Disk space**: Worktrees consume significant disk space
3. **Complexity**: Managing multiple repos increases cognitive load
4. **Performance**: Large repos slow down git operations

### Mitigation
1. Document worktree limitations, provide lazygit escape hatch
2. Warn users about disk usage, provide cleanup tools
3. Excellent UX and visual design to reduce cognitive load
4. Async operations, caching, progress indicators

## Timeline

- **v0.1.0** (Current): Core features, 4 themes
- **v0.2.0** (Week 2): Bug fixes, polish, documentation
- **v0.3.0** (Month 1): Search/filter, templates
- **v1.0.0** (Month 2): Stable release, comprehensive docs

## Appendix

### Glossary
- **Worktree**: Git feature allowing multiple working directories per repository
- **Task**: Named collection of worktrees across multiple repositories
- **TUI**: Terminal User Interface

### References
- [Git Worktree Documentation](https://git-scm.com/docs/git-worktree)
- [Textual Framework](https://textual.textualize.io/)
- [lazygit](https://github.com/jesseduffield/lazygit)
