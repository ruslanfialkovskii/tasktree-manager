"""Pytest fixtures for tasktree-manager tests."""

import subprocess
from pathlib import Path

import pytest

from tasktree_manager.app import TaskTreeApp
from tasktree_manager.services import forge
from tasktree_manager.services.config import Config
from tasktree_manager.services.git_ops import GitStatus
from tasktree_manager.services.task_manager import TaskManager, Worktree


@pytest.fixture(autouse=True)
def _reset_forge():
    """Reset forge module state — its TTL cache and class attrs leak across tests."""
    forge.clear_cache()
    forge.Forge.glab_path = "glab"
    forge.Forge.gh_path = "gh"
    forge.Forge.enabled = True
    forge.Forge.gitlab_hosts = []
    yield
    forge.clear_cache()


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
        config_dir=repos_dir.parent / ".config" / "tasktree-manager",
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
    config.ensure_dirs()
    # Keep TUI tests hermetic: never poll the real `claude` CLI from on_mount.
    # Badge/dispatch tests drive the poll/apply methods directly instead.
    config.agent_poll_interval = 0
    config.forge_poll_interval = 0
    app = TaskTreeApp()
    app.config = config
    app.task_manager = TaskManager(config)
    return app


@pytest.fixture
def repo_with_remote(tmp_path):
    """Create local repo with bare remote for push/pull testing.

    Returns:
        Tuple of (local_repo_path, remote_repo_path)
    """
    # Create bare "remote" repository
    remote = tmp_path / "remote.git"
    remote.mkdir()
    subprocess.run(["git", "init", "--bare"], cwd=remote, capture_output=True, check=True)

    # Create local repository with initial commit
    local = tmp_path / "local"
    local.mkdir()
    subprocess.run(["git", "init"], cwd=local, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=local,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=local,
        capture_output=True,
        check=True,
    )

    # Add remote
    subprocess.run(
        ["git", "remote", "add", "origin", str(remote)],
        cwd=local,
        capture_output=True,
        check=True,
    )

    # Create initial commit
    readme = local / "README.md"
    readme.write_text("# Test Repo\n")
    subprocess.run(["git", "add", "."], cwd=local, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=local,
        capture_output=True,
        check=True,
    )

    # Push to remote
    subprocess.run(
        ["git", "push", "-u", "origin", "HEAD"],
        cwd=local,
        capture_output=True,
        check=True,
    )

    return local, remote


@pytest.fixture
def repo_with_origin(config, tmp_path):
    """A repo in REPOS_DIR whose branch is pushed to a bare origin remote.

    check_merged() compares HEAD against origin/<base>, so only a repo
    with a remote can ever count as "merged" (and thus safe to delete).
    Returns the default branch name.
    """
    remote = tmp_path / "origin" / "repo-remote.git"
    remote.mkdir(parents=True)
    subprocess.run(["git", "init", "--bare"], cwd=remote, capture_output=True, check=True)

    repo = config.repos_dir / "repo-remote"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=repo, capture_output=True, check=True
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(remote)], cwd=repo, capture_output=True, check=True
    )
    (repo / "README.md").write_text("# repo-remote\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "push", "-u", "origin", "HEAD"], cwd=repo, capture_output=True, check=True
    )
    branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    return branch


@pytest.fixture
def squash_merged_task(config, task_manager, repo_with_origin):
    """A task whose branch was "squash-merged": its commit is pushed, but the
    remote base advanced with a different commit carrying the same change, so
    `git merge-base --is-ancestor` genuinely fails.

    Returns (task, base_branch).
    """
    base = repo_with_origin
    task = task_manager.create_task("TASK-squash", ["repo-remote"], base)
    wt = task.worktrees[0]

    (wt.path / "feature.txt").write_text("feature\n")
    subprocess.run(["git", "add", "."], cwd=wt.path, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "feat"], cwd=wt.path, capture_output=True, check=True)
    subprocess.run(
        ["git", "push", "-u", "origin", "HEAD"], cwd=wt.path, capture_output=True, check=True
    )

    # Simulate the squash merge from a scratch clone: same content lands on
    # base as a brand-new commit that is no descendant of the branch commit
    remote_url = subprocess.run(
        ["git", "remote", "get-url", "origin"], cwd=wt.path, capture_output=True, text=True
    ).stdout.strip()
    scratch = config.repos_dir.parent / "squash-scratch"
    subprocess.run(
        ["git", "clone", "--branch", base, remote_url, str(scratch)],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=scratch,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=scratch, capture_output=True, check=True
    )
    (scratch / "feature.txt").write_text("feature\n")
    subprocess.run(["git", "add", "."], cwd=scratch, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat (squash !42)"], cwd=scratch, capture_output=True, check=True
    )
    subprocess.run(["git", "push", "origin", base], cwd=scratch, capture_output=True, check=True)

    return task, base


@pytest.fixture
def repo_with_forge_url(config):
    """A repo in REPOS_DIR with a fake GitLab https origin (never fetched).

    Provider detection is purely URL-based, so no network is touched as long
    as nothing runs a real glab against it.
    """
    repo_path = config.repos_dir / "forge-repo"
    branch = create_git_repo(repo_path)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://gitlab.example.com/group/project.git"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    return repo_path, branch


@pytest.fixture
def fake_claude_cli(tmp_path):
    """An executable `claude` stub — the suite's process-boundary seam for
    Claude CLI behavior (no unittest.mock; same philosophy as real git repos).

    - `claude agents --json` cats <stub_dir>/agents.json, or exits 1 when the
      file is absent (tests rewrite that file to simulate state transitions).
    - `claude --bg ...` appends "$PWD|<args>" to <stub_dir>/dispatch.log.

    Returns the stub directory; the binary is <stub_dir>/claude.
    """
    stub_dir = tmp_path / "claude-stub"
    stub_dir.mkdir()
    script = stub_dir / "claude"
    script.write_text(
        f"""#!/bin/sh
if [ "$1" = "agents" ]; then
  if [ -f "{stub_dir}/agents.json" ]; then
    cat "{stub_dir}/agents.json"
    exit 0
  fi
  exit 1
fi
case "$1" in
  --bg|--background)
    printf '%s|%s\\n' "$PWD" "$*" >> "{stub_dir}/dispatch.log"
    exit 0
    ;;
esac
exit 0
"""
    )
    script.chmod(0o755)
    return stub_dir


@pytest.fixture
def worktree_from_repo(sample_repo):
    """Create a Worktree object from sample_repo."""
    repo_path, branch = sample_repo
    return Worktree(name="sample-repo", path=repo_path, branch=branch)


@pytest.fixture
def clean_git_status():
    """Create a clean GitStatus."""
    return GitStatus(branch="main")


@pytest.fixture
def dirty_git_status():
    """Create a dirty GitStatus with various changes."""
    return GitStatus(
        branch="feature-branch",
        staged=["staged.py", "added.txt"],
        modified=["modified.py"],
        untracked=["untracked.txt", "temp.log"],
        ahead=2,
        behind=1,
    )


@pytest.fixture
def error_git_status():
    """Create a GitStatus with an error."""
    return GitStatus(branch="", error="Git operation timed out")
