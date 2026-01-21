"""Pytest fixtures for tasktree tests."""

import subprocess
from pathlib import Path

import pytest

from tasktree.app import TaskTreeApp
from tasktree.services.config import Config
from tasktree.services.task_manager import TaskManager


def get_default_branch(repo_path: Path) -> str:
    """Get the default branch name of a git repo."""
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or "main"


def create_git_repo(repo_path: Path) -> str:
    """Create a git repository and return the default branch name."""
    repo_path.mkdir(exist_ok=True)

    subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    # Create initial commit
    readme = repo_path / "README.md"
    readme.write_text(f"# {repo_path.name}\n")
    subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    return get_default_branch(repo_path)


@pytest.fixture
def temp_dirs(tmp_path):
    """Create temporary repos and tasks directories."""
    repos_dir = tmp_path / "repos"
    tasks_dir = tmp_path / "wtasks"
    repos_dir.mkdir()
    tasks_dir.mkdir()
    return repos_dir, tasks_dir


@pytest.fixture
def config(temp_dirs):
    """Create a Config with temporary directories."""
    repos_dir, tasks_dir = temp_dirs
    return Config(
        repos_dir=repos_dir,
        tasks_dir=tasks_dir,
        config_dir=repos_dir.parent / ".config" / "tasktree",
    )


@pytest.fixture
def task_manager(config):
    """Create a TaskManager with test config."""
    return TaskManager(config)


@pytest.fixture
def sample_repo(temp_dirs):
    """Create a sample git repository."""
    repos_dir, _ = temp_dirs
    repo_path = repos_dir / "sample-repo"
    branch = create_git_repo(repo_path)
    return repo_path, branch


@pytest.fixture
def sample_repos(temp_dirs):
    """Create multiple sample git repositories."""
    repos_dir, _ = temp_dirs
    repo_names = ["repo-alpha", "repo-beta", "repo-gamma"]
    repos = []
    branch = None

    for name in repo_names:
        repo_path = repos_dir / name
        branch = create_git_repo(repo_path)
        repos.append(repo_path)

    return repos, branch


@pytest.fixture
def app(config):
    """Create app with test config."""
    app = TaskTreeApp()
    app.config = config
    app.task_manager = TaskManager(config)
    return app
