"""Tests for the task manager service."""

import pytest

from tasktree.services.task_manager import Task, Worktree


class TestTaskManager:
    """Tests for TaskManager class."""

    def test_list_tasks_empty(self, task_manager):
        """Test listing tasks when none exist."""
        tasks = task_manager.list_tasks()
        assert tasks == []

    def test_create_task(self, task_manager, sample_repo):
        """Test creating a new task."""
        repo_path, branch = sample_repo
        task = task_manager.create_task("TEST-123", ["sample-repo"], branch)

        assert task.name == "TEST-123"
        assert task.path.exists()
        assert len(task.worktrees) == 1
        assert task.worktrees[0].name == "sample-repo"
        assert task.worktrees[0].path.exists()

    def test_create_task_multiple_repos(self, task_manager, sample_repos):
        """Test creating a task with multiple repos."""
        repos, branch = sample_repos
        task = task_manager.create_task("MULTI-REPO", ["repo-alpha", "repo-beta"], branch)

        assert task.name == "MULTI-REPO"
        assert len(task.worktrees) == 2
        worktree_names = [wt.name for wt in task.worktrees]
        assert "repo-alpha" in worktree_names
        assert "repo-beta" in worktree_names

    def test_list_tasks_after_create(self, task_manager, sample_repo):
        """Test listing tasks after creation."""
        repo_path, branch = sample_repo
        task_manager.create_task("TASK-1", ["sample-repo"], branch)

        tasks = task_manager.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].name == "TASK-1"

    def test_get_task(self, task_manager, sample_repo):
        """Test getting a specific task."""
        repo_path, branch = sample_repo
        task_manager.create_task("GET-TEST", ["sample-repo"], branch)

        task = task_manager.get_task("GET-TEST")
        assert task is not None
        assert task.name == "GET-TEST"

    def test_get_task_nonexistent(self, task_manager):
        """Test getting a task that doesn't exist."""
        task = task_manager.get_task("NONEXISTENT")
        assert task is None

    def test_add_repo_to_task(self, task_manager, sample_repos):
        """Test adding a repo to an existing task."""
        repos, branch = sample_repos
        task = task_manager.create_task("ADD-REPO", ["repo-alpha"], branch)
        assert len(task.worktrees) == 1

        task_manager.add_repo_to_task(task, "repo-beta", branch)
        assert len(task.worktrees) == 2

    def test_finish_task(self, task_manager, sample_repo):
        """Test finishing/deleting a task."""
        repo_path, branch = sample_repo
        task = task_manager.create_task("FINISH-ME", ["sample-repo"], branch)
        task_path = task.path
        assert task_path.exists()

        task_manager.finish_task(task)
        assert not task_path.exists()

    def test_get_repos_not_in_task(self, task_manager, sample_repos):
        """Test getting repos not yet in a task."""
        repos, branch = sample_repos
        task = task_manager.create_task("PARTIAL", ["repo-alpha"], branch)

        available = task_manager.get_repos_not_in_task(task)
        assert "repo-alpha" not in available
        assert "repo-beta" in available
        assert "repo-gamma" in available

    def test_create_task_nonexistent_repo(self, task_manager):
        """Test creating a task with a nonexistent repo."""
        with pytest.raises(ValueError, match="Repository not found"):
            task_manager.create_task("FAIL-TASK", ["nonexistent-repo"], "main")


class TestTask:
    """Tests for Task dataclass."""

    def test_is_dirty_clean(self):
        """Test is_dirty when all worktrees are clean."""
        task = Task(
            name="test",
            path=None,
            worktrees=[
                Worktree(name="a", path=None, is_dirty=False),
                Worktree(name="b", path=None, is_dirty=False),
            ],
        )
        assert not task.is_dirty

    def test_is_dirty_with_dirty_worktree(self):
        """Test is_dirty when some worktrees are dirty."""
        task = Task(
            name="test",
            path=None,
            worktrees=[
                Worktree(name="a", path=None, is_dirty=False),
                Worktree(name="b", path=None, is_dirty=True),
            ],
        )
        assert task.is_dirty

    def test_dirty_count(self):
        """Test dirty_count property."""
        task = Task(
            name="test",
            path=None,
            worktrees=[
                Worktree(name="a", path=None, is_dirty=True),
                Worktree(name="b", path=None, is_dirty=False),
                Worktree(name="c", path=None, is_dirty=True),
            ],
        )
        assert task.dirty_count == 2


class TestWorktree:
    """Tests for Worktree dataclass."""

    def test_exists_false(self, tmp_path):
        """Test exists property when path doesn't exist."""
        wt = Worktree(name="test", path=tmp_path / "nonexistent")
        assert not wt.exists

    def test_exists_true(self, tmp_path):
        """Test exists property when path exists."""
        path = tmp_path / "exists"
        path.mkdir()
        wt = Worktree(name="test", path=path)
        assert wt.exists
