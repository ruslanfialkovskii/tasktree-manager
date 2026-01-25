"""Memory leak tests for tasktree.

Uses tracemalloc to detect memory leaks in repeated operations.
"""

import gc
import tracemalloc

import pytest

from tasktree.services.config import Config
from tasktree.services.git_ops import GitOps
from tasktree.services.task_manager import TaskManager, Worktree


def get_memory_usage():
    """Get current memory usage in bytes."""
    gc.collect()
    current, peak = tracemalloc.get_traced_memory()
    return current


@pytest.fixture
def memory_config(tmp_path):
    """Create a config for memory testing."""
    repos_dir = tmp_path / "repos"
    tasks_dir = tmp_path / "tasks"
    repos_dir.mkdir()
    tasks_dir.mkdir()
    return Config(
        repos_dir=repos_dir,
        tasks_dir=tasks_dir,
        config_dir=tmp_path / ".config" / "tasktree",
    )


class TestMemoryLeaks:
    """Tests for memory leaks in repeated operations."""

    async def test_repeated_task_selection_no_leak(self, app, sample_repos, task_manager):
        """Test that repeated task selection doesn't leak memory."""
        repos, branch = sample_repos
        # Create multiple tasks
        for i in range(5):
            task_manager.create_task(f"MEMORY-{i}", [repos[i % len(repos)].name], branch)

        tracemalloc.start()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Get baseline memory
            baseline = get_memory_usage()

            # Repeatedly select different tasks
            for _ in range(20):
                await pilot.press("j")
                await pilot.pause()
                await pilot.press("k")
                await pilot.pause()

            # Check memory growth
            final = get_memory_usage()
            growth = final - baseline

            # Allow some growth but not excessive (< 5MB)
            assert growth < 5 * 1024 * 1024, f"Memory grew by {growth / 1024 / 1024:.2f} MB"

        tracemalloc.stop()

    async def test_repeated_refresh_no_leak(self, app, sample_repo, task_manager):
        """Test that repeated refresh doesn't leak memory."""
        repo_path, branch = sample_repo
        task_manager.create_task("REFRESH-TEST", ["sample-repo"], branch)

        tracemalloc.start()

        async with app.run_test() as pilot:
            await pilot.pause()

            baseline = get_memory_usage()

            # Repeatedly refresh
            for _ in range(15):
                await pilot.press("r")
                await pilot.pause()

            final = get_memory_usage()
            growth = final - baseline

            # Allow some growth but not excessive
            assert growth < 5 * 1024 * 1024, f"Memory grew by {growth / 1024 / 1024:.2f} MB"

        tracemalloc.stop()

    def test_repeated_status_checks_no_leak(self, sample_repo):
        """Test that repeated status checks don't leak memory."""
        repo_path, branch = sample_repo
        worktree = Worktree(name="test", path=repo_path)

        tracemalloc.start()
        baseline = get_memory_usage()

        # Repeatedly check status
        for _ in range(100):
            GitOps.get_status(worktree)

        final = get_memory_usage()
        growth = final - baseline

        tracemalloc.stop()

        # Allow some growth but not excessive (< 2MB)
        assert growth < 2 * 1024 * 1024, f"Memory grew by {growth / 1024 / 1024:.2f} MB"

    def test_repeated_task_creation_deletion_no_leak(self, memory_config, tmp_path):
        """Test that repeated task creation/deletion doesn't leak memory."""
        import subprocess

        # Create a test repo
        repo_path = memory_config.repos_dir / "leak-test-repo"
        repo_path.mkdir()
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo_path,
            capture_output=True,
        )
        readme = repo_path / "README.md"
        readme.write_text("# Test\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial"],
            cwd=repo_path,
            capture_output=True,
        )

        task_manager = TaskManager(memory_config)

        tracemalloc.start()
        baseline = get_memory_usage()

        # Repeatedly create and delete tasks
        for i in range(10):
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )
            branch = result.stdout.strip()
            task = task_manager.create_task(f"LEAK-{i}", ["leak-test-repo"], branch)
            task_manager.finish_task(task)

        final = get_memory_usage()
        growth = final - baseline

        tracemalloc.stop()

        # Allow some growth but not excessive (< 3MB)
        assert growth < 3 * 1024 * 1024, f"Memory grew by {growth / 1024 / 1024:.2f} MB"

    def test_worktree_status_update_parallel_no_leak(self, sample_repos):
        """Test parallel status updates don't leak memory."""
        repos, branch = sample_repos
        worktrees = [Worktree(name=repo.name, path=repo) for repo in repos]

        tracemalloc.start()
        baseline = get_memory_usage()

        # Repeatedly update all statuses in parallel
        for _ in range(20):
            GitOps.update_all_worktree_statuses(worktrees)

        final = get_memory_usage()
        growth = final - baseline

        tracemalloc.stop()

        # Allow some growth but not excessive (< 2MB)
        assert growth < 2 * 1024 * 1024, f"Memory grew by {growth / 1024 / 1024:.2f} MB"


class TestLongRunningStability:
    """Tests for long-running session stability."""

    async def test_long_session_stability(self, app, sample_repos, task_manager):
        """Test that app remains stable during extended use."""
        repos, branch = sample_repos
        task_manager.create_task("STABILITY-TEST", ["repo-alpha", "repo-beta"], branch)

        tracemalloc.start()

        async with app.run_test() as pilot:
            await pilot.pause()

            baseline = get_memory_usage()

            # Simulate extended use
            for cycle in range(5):
                # Navigate tasks
                await pilot.press("j")
                await pilot.pause()
                await pilot.press("k")
                await pilot.pause()

                # Switch to worktree list
                await pilot.press("tab")
                await pilot.pause()

                # Navigate worktrees
                await pilot.press("j")
                await pilot.pause()

                # Switch back to task list
                await pilot.press("shift+tab")
                await pilot.pause()

                # Refresh
                await pilot.press("r")
                await pilot.pause()

            final = get_memory_usage()
            growth = final - baseline

            # Memory should stay bounded
            assert growth < 10 * 1024 * 1024, f"Memory grew by {growth / 1024 / 1024:.2f} MB"

        tracemalloc.stop()

    def test_many_worktrees_memory_bounded(self, memory_config, tmp_path):
        """Test that many worktrees don't cause excessive memory usage."""
        import subprocess

        # Create multiple repos
        for i in range(5):
            repo_path = memory_config.repos_dir / f"repo-{i}"
            repo_path.mkdir()
            subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=repo_path,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=repo_path,
                capture_output=True,
            )
            readme = repo_path / "README.md"
            readme.write_text(f"# Repo {i}\n")
            subprocess.run(["git", "add", "."], cwd=repo_path, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial"],
                cwd=repo_path,
                capture_output=True,
            )

        task_manager = TaskManager(memory_config)

        tracemalloc.start()
        baseline = get_memory_usage()

        # Create task with all repos
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=memory_config.repos_dir / "repo-0",
            capture_output=True,
            text=True,
        )
        branch = result.stdout.strip()
        repo_names = [f"repo-{i}" for i in range(5)]
        task = task_manager.create_task("MANY-REPOS", repo_names, branch)

        # Update all statuses
        GitOps.update_all_worktree_statuses(task.worktrees)

        # Check safety
        task_manager.check_task_safety(task)

        final = get_memory_usage()
        growth = final - baseline

        tracemalloc.stop()

        # Memory should stay reasonable
        assert growth < 5 * 1024 * 1024, f"Memory grew by {growth / 1024 / 1024:.2f} MB"
