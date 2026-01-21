# Contributing to tasktree

Thank you for your interest in contributing to tasktree! This document provides guidelines and instructions for contributing.

## Code of Conduct

Be respectful, inclusive, and constructive. We're all here to build something useful together.

## Getting Started

### Prerequisites

- Python 3.13+
- Git
- [mise](https://mise.jdx.dev/) (recommended) or pip

### Development Setup

1. **Fork and clone**
   ```bash
   git clone https://github.com/yourusername/tasktree.git
   cd tasktree
   ```

2. **Install dependencies**
   ```bash
   mise install
   mise run install
   ```

3. **Run tests**
   ```bash
   mise run test
   ```

4. **Run in development mode**
   ```bash
   mise run dev
   ```

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
```

Branch naming:
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation changes
- `refactor/` - Code refactoring
- `test/` - Test additions/changes

### 2. Make Your Changes

- Write clear, commented code
- Follow existing code style (enforced by Ruff)
- Add type hints to all functions
- Update tests as needed
- Update documentation if changing behavior

### 3. Test Your Changes

```bash
# Run all tests
mise run test

# Run specific test
pytest tests/test_app.py::TestTaskTreeApp::test_app_starts -v

# Check coverage
mise run test:cov

# Run linter
mise run lint

# Auto-fix lint issues
mise run lint:fix

# Format code
mise run format
```

### 4. Commit Your Changes

Use clear, descriptive commit messages:

```bash
git add .
git commit -m "feat: add search functionality to task list

- Implement fuzzy search for task names
- Add '/' keybinding to activate search
- Update tests and documentation"
```

Commit message format:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `test:` - Test changes
- `refactor:` - Code refactoring
- `style:` - Code style changes (formatting, etc.)
- `chore:` - Build process, dependencies, etc.

### 5. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Then open a Pull Request on GitHub with:
- Clear title and description
- Reference any related issues
- Screenshots/GIFs for UI changes
- Test results

## Code Style

### Python Style

We use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting:

```bash
# Check style
mise run lint

# Auto-fix
mise run lint:fix
mise run format
```

### Type Hints

All functions must have type hints:

```python
def create_task(name: str, repos: list[str]) -> Task:
    """Create a new task."""
    ...
```

### Documentation

- Add docstrings to all public functions/classes
- Use Google-style docstrings
- Update README.md for user-facing changes
- Update OPENSPEC.md for architecture changes

Example docstring:
```python
def get_status(worktree: Worktree) -> GitStatus:
    """Get git status for a worktree.

    Args:
        worktree: The worktree to check

    Returns:
        GitStatus object with current status

    Raises:
        subprocess.CalledProcessError: If git command fails
    """
```

## Testing

### Writing Tests

- Place tests in `tests/` directory
- Name test files `test_*.py`
- Use pytest fixtures from `conftest.py`
- Aim for >80% coverage

Example test:
```python
def test_create_task(task_manager, sample_repos):
    """Test creating a task with multiple repos."""
    task = task_manager.create_task("test-task", ["repo1", "repo2"])
    assert task.name == "test-task"
    assert len(task.worktrees) == 2
```

### Async Widget Tests

For Textual widgets, use async tests:

```python
async def test_app_starts(app):
    """Test app startup."""
    async with app.run_test() as pilot:
        assert pilot.app.query_one("#task-list")
```

## Project Structure

```
tasktree/
├── tasktree/           # Main package
│   ├── services/       # Business logic
│   ├── widgets/        # UI components
│   ├── themes/         # Color themes
│   └── app.py          # Main app
├── tests/              # Test suite
├── specs/              # Technical specs
└── docs/               # Documentation
```

### Adding New Features

1. **Check specs**: Review existing specs in `specs/`
2. **Create spec**: Write a new spec (SPEC-XXX) if needed
3. **Write tests**: Add tests first (TDD approach)
4. **Implement**: Write the code
5. **Document**: Update README/specs
6. **PR**: Submit for review

## Submitting Issues

### Bug Reports

Include:
- tasktree version (`tasktree --version`)
- Python version (`python --version`)
- OS and terminal
- Steps to reproduce
- Expected vs actual behavior
- Error messages/logs

### Feature Requests

Include:
- Clear description of the feature
- Use case / motivation
- Proposed implementation (optional)
- Mockups/examples (if UI-related)

## Review Process

1. **Automated checks**: Tests, linting must pass
2. **Code review**: Maintainer reviews code
3. **Revisions**: Address feedback
4. **Approval**: Maintainer approves
5. **Merge**: PR is merged

## Release Process

(For maintainers)

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Tag release: `git tag v0.x.0`
4. Push: `git push origin v0.x.0`
5. Build: `python -m build`
6. Publish: `twine upload dist/*`

## Questions?

- Open a [Discussion](https://github.com/yourusername/tasktree/discussions)
- Ask in Pull Request
- Check existing issues

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to tasktree! 🎉
