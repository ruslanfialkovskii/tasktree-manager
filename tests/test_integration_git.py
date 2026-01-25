"""Integration tests for git workflows."""

import subprocess

import pytest

from tasktree.services.config import Config
from tasktree.services.git_ops import GitOps
from tasktree.services.task_manager import TaskManager, Worktree


@pytest.fixture
def integration_config(tmp_path):
    """Create a config for integration testing."""
    repos_dir = tmp_path / "repos"
    tasks_dir = tmp_path / "tasks"
    repos_dir.mkdir()
    tasks_dir.mkdir()
    return Config(
        repos_dir=repos_dir,
        tasks_dir=tasks_dir,
        config_dir=tmp_path / ".config" / "tasktree",
    )


@pytest.fixture
def integration_repo(integration_config):
    """Create a repository with remote for integration testing."""
    # Create bare remote
    remote = integration_config.repos_dir.parent / "remote.git"
    remote.mkdir()
    subprocess.run(["git", "init", "--bare"], cwd=remote, capture_output=True, check=True)

    # Create local repo in repos_dir
    local = integration_config.repos_dir / "test-repo"
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
    subprocess.run(
        ["git", "remote", "add", "origin", str(remote)],
        cwd=local,
        capture_output=True,
        check=True,
    )

    # Initial commit
    readme = local / "README.md"
    readme.write_text("# Test Repo\n")
    subprocess.run(["git", "add", "."], cwd=local, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=local,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "push", "-u", "origin", "HEAD"],
        cwd=local,
        capture_output=True,
        check=True,
    )

    # Get default branch
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=local,
        capture_output=True,
        text=True,
    )
    branch = result.stdout.strip()

    return local, remote, branch


class TestPushWorkflow:
    """Integration tests for push workflow."""

    def test_push_new_commits(self, integration_config, integration_repo):
        """Test pushing new commits to remote."""
        local, remote, branch = integration_repo
        worktree = Worktree(name="test-repo", path=local)

        # Make a change
        test_file = local / "new_file.txt"
        test_file.write_text("new content")
        subprocess.run(["git", "add", "."], cwd=local, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Add new file"],
            cwd=local,
            capture_output=True,
        )

        # Status should show ahead
        status = GitOps.get_status(worktree)
        assert status.ahead >= 1

        # Push
        success, message = GitOps.push(worktree)
        assert success

        # Status should now be synced
        status = GitOps.get_status(worktree)
        assert status.ahead == 0

    def test_push_all_worktrees_in_task(self, integration_config, integration_repo):
        """Test pushing all worktrees in a task."""
        local, remote, branch = integration_repo
        task_manager = TaskManager(integration_config)

        # Create task with worktree
        task = task_manager.create_task("PUSH-TEST", ["test-repo"], branch)

        # Make changes in worktree
        worktree_path = task.worktrees[0].path
        test_file = worktree_path / "push_test.txt"
        test_file.write_text("push test content")
        subprocess.run(["git", "add", "."], cwd=worktree_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Test push"],
            cwd=worktree_path,
            capture_output=True,
        )

        # Push all
        success_repos, failed_repos = task_manager.push_all_branches(task)

        assert "test-repo" in success_repos
        assert failed_repos == []


class TestPullWorkflow:
    """Integration tests for pull workflow."""

    def test_pull_new_commits(self, integration_config, integration_repo):
        """Test pulling new commits from remote."""
        local, remote, branch = integration_repo

        # Clone a second copy and push from there
        second_copy = integration_config.repos_dir.parent / "second_copy"
        subprocess.run(
            ["git", "clone", str(remote), str(second_copy)],
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=second_copy,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=second_copy,
            capture_output=True,
        )

        # Make change in second copy
        test_file = second_copy / "from_remote.txt"
        test_file.write_text("remote content")
        subprocess.run(["git", "add", "."], cwd=second_copy, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Remote commit"],
            cwd=second_copy,
            capture_output=True,
        )
        subprocess.run(["git", "push"], cwd=second_copy, capture_output=True)

        # Fetch in original
        subprocess.run(["git", "fetch"], cwd=local, capture_output=True)

        # Should be behind
        worktree = Worktree(name="test-repo", path=local)
        status = GitOps.get_status(worktree)
        assert status.behind >= 1

        # Pull
        success, message = GitOps.pull(worktree)
        assert success

        # File should now exist
        assert (local / "from_remote.txt").exists()


class TestSyncStatusWorkflow:
    """Integration tests for sync status detection."""

    def test_detect_ahead_commits(self, integration_repo):
        """Test detecting when local is ahead of remote."""
        local, remote, branch = integration_repo
        worktree = Worktree(name="test", path=local)

        # Make local commit without pushing
        test_file = local / "ahead.txt"
        test_file.write_text("ahead content")
        subprocess.run(["git", "add", "."], cwd=local, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Local only"],
            cwd=local,
            capture_output=True,
        )

        status = GitOps.get_status(worktree)
        assert status.ahead >= 1
        assert status.behind == 0

    def test_detect_behind_commits(self, integration_config, integration_repo):
        """Test detecting when local is behind remote."""
        local, remote, branch = integration_repo

        # Create and push from second copy
        second = integration_config.repos_dir.parent / "second"
        subprocess.run(
            ["git", "clone", str(remote), str(second)],
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=second,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=second,
            capture_output=True,
        )

        test_file = second / "behind.txt"
        test_file.write_text("behind content")
        subprocess.run(["git", "add", "."], cwd=second, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Remote ahead"],
            cwd=second,
            capture_output=True,
        )
        subprocess.run(["git", "push"], cwd=second, capture_output=True)

        # Fetch in original
        subprocess.run(["git", "fetch"], cwd=local, capture_output=True)

        worktree = Worktree(name="test", path=local)
        status = GitOps.get_status(worktree)
        assert status.behind >= 1

    def test_detect_ahead_and_behind(self, integration_config, integration_repo):
        """Test detecting diverged state (ahead AND behind)."""
        local, remote, branch = integration_repo

        # Push from second copy
        second = integration_config.repos_dir.parent / "second"
        subprocess.run(
            ["git", "clone", str(remote), str(second)],
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=second,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=second,
            capture_output=True,
        )

        second_file = second / "second.txt"
        second_file.write_text("from second")
        subprocess.run(["git", "add", "."], cwd=second, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Second commit"],
            cwd=second,
            capture_output=True,
        )
        subprocess.run(["git", "push"], cwd=second, capture_output=True)

        # Make local commit without pushing
        local_file = local / "local.txt"
        local_file.write_text("local only")
        subprocess.run(["git", "add", "."], cwd=local, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Local commit"],
            cwd=local,
            capture_output=True,
        )

        # Fetch to update tracking
        subprocess.run(["git", "fetch"], cwd=local, capture_output=True)

        worktree = Worktree(name="test", path=local)
        status = GitOps.get_status(worktree)

        assert status.ahead >= 1
        assert status.behind >= 1


class TestTaskLifecycleWorkflow:
    """Integration tests for complete task lifecycle."""

    def test_create_task_make_changes_push_delete(self, integration_config, integration_repo):
        """Test full task lifecycle: create -> change -> push -> delete."""
        local, remote, branch = integration_repo
        task_manager = TaskManager(integration_config)

        # 1. Create task
        task = task_manager.create_task("LIFECYCLE-TEST", ["test-repo"], branch)
        assert task.path.exists()
        assert len(task.worktrees) == 1

        # 2. Make changes in worktree
        worktree_path = task.worktrees[0].path
        test_file = worktree_path / "lifecycle.txt"
        test_file.write_text("lifecycle test")
        subprocess.run(["git", "add", "."], cwd=worktree_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Lifecycle commit"],
            cwd=worktree_path,
            capture_output=True,
        )

        # 3. Check safety (should be unsafe - unpushed)
        report = task_manager.check_task_safety(task)
        assert report.has_unpushed() or report.has_unmerged()

        # 4. Push changes
        success_repos, failed_repos = task_manager.push_all_branches(task)
        assert "test-repo" in success_repos

        # 5. Delete task
        task_manager.finish_task(task)
        assert not task.path.exists()

    def test_task_with_unpushed_changes_reports_unsafe(self, integration_config, integration_repo):
        """Test that unpushed changes are reported as unsafe."""
        local, remote, branch = integration_repo
        task_manager = TaskManager(integration_config)

        task = task_manager.create_task("UNSAFE-TEST", ["test-repo"], branch)

        # Make unpushed changes
        worktree_path = task.worktrees[0].path
        test_file = worktree_path / "unpushed.txt"
        test_file.write_text("unpushed")
        subprocess.run(["git", "add", "."], cwd=worktree_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Unpushed"],
            cwd=worktree_path,
            capture_output=True,
        )

        report = task_manager.check_task_safety(task)
        # Task is unsafe because it has unpushed commits or unmerged branches
        assert not report.is_safe()
        # Should have either unpushed or unmerged (depends on tracking setup)
        assert report.has_unpushed() or report.has_unmerged()

    def test_task_with_dirty_worktree_reports_unsafe(self, integration_config, integration_repo):
        """Test that dirty worktree is reported as unsafe."""
        local, remote, branch = integration_repo
        task_manager = TaskManager(integration_config)

        task = task_manager.create_task("DIRTY-TEST", ["test-repo"], branch)

        # Make uncommitted changes
        worktree_path = task.worktrees[0].path
        test_file = worktree_path / "dirty.txt"
        test_file.write_text("uncommitted")

        report = task_manager.check_task_safety(task)
        assert report.has_dirty()
        assert not report.is_safe()


class TestParallelGitOperations:
    """Integration tests for parallel git operations."""

    def test_parallel_status_update(self, integration_config, integration_repo):
        """Test parallel status updates across multiple worktrees."""
        local, remote, branch = integration_repo
        task_manager = TaskManager(integration_config)

        task = task_manager.create_task("PARALLEL-STATUS", ["test-repo"], branch)

        # Update all statuses in parallel
        GitOps.update_all_worktree_statuses(task.worktrees)

        # All worktrees should have branch set
        for wt in task.worktrees:
            assert wt.branch != "" or wt.branch == "PARALLEL-STATUS"
