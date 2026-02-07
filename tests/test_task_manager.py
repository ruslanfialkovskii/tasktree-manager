"""Tests for the task manager service."""

import pytest

from tasktree_manager.services.task_manager import RepoIssue, Task, TaskSafetyReport, Worktree


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

    def test_default_values(self, tmp_path):
        """Test default values for worktree."""
        wt = Worktree(name="test", path=tmp_path)
        assert wt.branch == ""
        assert not wt.is_dirty
        assert wt.changed_files == 0


class TestTaskSafetyReport:
    """Tests for TaskSafetyReport dataclass."""

    def test_is_safe_true(self):
        """Test is_safe returns True when no issues."""
        report = TaskSafetyReport()
        assert report.is_safe()

    def test_is_safe_false_unpushed(self, tmp_path):
        """Test is_safe returns False with unpushed commits."""
        report = TaskSafetyReport(
            unpushed=[
                RepoIssue(
                    repo_name="repo",
                    worktree_path=tmp_path,
                    issue_type="unpushed",
                    details="2 commits ahead",
                )
            ]
        )
        assert not report.is_safe()

    def test_is_safe_false_dirty(self, tmp_path):
        """Test is_safe returns False with dirty worktree."""
        report = TaskSafetyReport(
            dirty=[
                RepoIssue(
                    repo_name="repo",
                    worktree_path=tmp_path,
                    issue_type="dirty",
                    details="3 files changed",
                )
            ]
        )
        assert not report.is_safe()

    def test_is_safe_false_unmerged(self, tmp_path):
        """Test is_safe returns False with unmerged branch."""
        report = TaskSafetyReport(
            unmerged=[
                RepoIssue(
                    repo_name="repo",
                    worktree_path=tmp_path,
                    issue_type="unmerged",
                    details="not merged to main",
                )
            ]
        )
        assert not report.is_safe()

    def test_has_unpushed(self, tmp_path):
        """Test has_unpushed method."""
        empty = TaskSafetyReport()
        assert not empty.has_unpushed()

        with_unpushed = TaskSafetyReport(
            unpushed=[
                RepoIssue(
                    repo_name="repo",
                    worktree_path=tmp_path,
                    issue_type="unpushed",
                    details="1 commit",
                )
            ]
        )
        assert with_unpushed.has_unpushed()

    def test_has_dirty(self, tmp_path):
        """Test has_dirty method."""
        empty = TaskSafetyReport()
        assert not empty.has_dirty()

        with_dirty = TaskSafetyReport(
            dirty=[
                RepoIssue(
                    repo_name="repo",
                    worktree_path=tmp_path,
                    issue_type="dirty",
                    details="1 file",
                )
            ]
        )
        assert with_dirty.has_dirty()

    def test_has_unmerged(self, tmp_path):
        """Test has_unmerged method."""
        empty = TaskSafetyReport()
        assert not empty.has_unmerged()

        with_unmerged = TaskSafetyReport(
            unmerged=[
                RepoIssue(
                    repo_name="repo",
                    worktree_path=tmp_path,
                    issue_type="unmerged",
                    details="not merged",
                )
            ]
        )
        assert with_unmerged.has_unmerged()


class TestRepoIssue:
    """Tests for RepoIssue dataclass."""

    def test_create_repo_issue(self, tmp_path):
        """Test creating a RepoIssue."""
        issue = RepoIssue(
            repo_name="my-repo",
            worktree_path=tmp_path / "my-repo",
            issue_type="unpushed",
            details="5 commits ahead",
        )
        assert issue.repo_name == "my-repo"
        assert issue.issue_type == "unpushed"
        assert "5 commits" in issue.details


class TestSafetyChecks:
    """Tests for safety check methods in TaskManager."""

    def test_check_task_safety_clean(self, task_manager, sample_repo):
        """Test check_task_safety on clean task."""
        repo_path, branch = sample_repo
        task = task_manager.create_task("CLEAN-TASK", ["sample-repo"], branch)

        report = task_manager.check_task_safety(task)

        # Clean task should be safe (though may have unmerged)
        # Just check that it returns a valid report
        assert isinstance(report, TaskSafetyReport)

    def test_check_task_safety_dirty_worktree(self, task_manager, sample_repo):
        """Test check_task_safety with dirty worktree."""
        repo_path, branch = sample_repo
        task = task_manager.create_task("DIRTY-TASK", ["sample-repo"], branch)

        # Make worktree dirty
        worktree_path = task.worktrees[0].path
        test_file = worktree_path / "dirty.txt"
        test_file.write_text("uncommitted changes")

        report = task_manager.check_task_safety(task)

        assert report.has_dirty()
        assert not report.is_safe()

    def test_check_task_safety_nonexistent_worktree(self, task_manager, sample_repo, tmp_path):
        """Test check_task_safety skips nonexistent worktrees."""
        repo_path, branch = sample_repo
        task = Task(
            name="GHOST-TASK",
            path=tmp_path / "ghost",
            worktrees=[Worktree(name="ghost", path=tmp_path / "nonexistent")],
        )

        report = task_manager.check_task_safety(task)
        # Should not crash, just skip the worktree
        assert isinstance(report, TaskSafetyReport)


class TestPushAllBranches:
    """Tests for push_all_branches method."""

    def test_push_all_branches_no_worktrees(self, task_manager, tmp_path):
        """Test push_all_branches with no worktrees."""
        task = Task(name="EMPTY", path=tmp_path / "empty", worktrees=[])

        success_repos, failed_repos = task_manager.push_all_branches(task)

        assert success_repos == []
        assert failed_repos == []

    def test_push_all_branches_nonexistent_worktree(self, task_manager, tmp_path):
        """Test push_all_branches with nonexistent worktree."""
        task = Task(
            name="GHOST",
            path=tmp_path / "ghost",
            worktrees=[Worktree(name="ghost", path=tmp_path / "nonexistent")],
        )

        success_repos, failed_repos = task_manager.push_all_branches(task)

        assert "ghost" in failed_repos
        assert success_repos == []


class TestTaskManagerEdgeCases:
    """Edge case tests for TaskManager."""

    def test_list_tasks_nonexistent_dir(self, config):
        """Test list_tasks when tasks_dir doesn't exist."""
        import shutil

        from tasktree_manager.services.task_manager import TaskManager

        # Remove tasks dir
        shutil.rmtree(config.tasks_dir)

        manager = TaskManager(config)
        tasks = manager.list_tasks()

        assert tasks == []

    def test_get_task_nonexistent(self, task_manager):
        """Test get_task returns None for nonexistent task."""
        task = task_manager.get_task("DOES-NOT-EXIST")
        assert task is None

    def test_create_task_existing_branch(self, task_manager, sample_repo):
        """Test creating task when branch already exists."""
        repo_path, branch = sample_repo

        # Create task to make the branch
        task1 = task_manager.create_task("BRANCH-TEST", ["sample-repo"], branch)
        task_manager.finish_task(task1)

        # Create again - should use -B to reset
        task2 = task_manager.create_task("BRANCH-TEST", ["sample-repo"], branch)
        assert task2.name == "BRANCH-TEST"

    def test_add_existing_repo_to_task(self, task_manager, sample_repos):
        """Test adding a repo that already exists in task."""
        repos, branch = sample_repos
        task = task_manager.create_task("DUP-TEST", ["repo-alpha"], branch)

        # Adding same repo should not create duplicate
        initial_count = len(task.worktrees)
        task_manager.add_repo_to_task(task, "repo-alpha", branch)

        # Should still have same number (already exists)
        assert len(task.worktrees) == initial_count

    def test_finish_task_cleans_worktrees(self, task_manager, sample_repos):
        """Test that finish_task removes worktrees properly."""
        repos, branch = sample_repos
        task = task_manager.create_task("FINISH-TEST", ["repo-alpha", "repo-beta"], branch)

        # Verify worktrees exist
        for wt in task.worktrees:
            assert wt.path.exists()

        # Finish task
        task_manager.finish_task(task)

        # Verify task directory is gone
        assert not task.path.exists()

    def test_get_repos_not_in_task_all_used(self, task_manager, sample_repo):
        """Test get_repos_not_in_task when all repos are used."""
        repo_path, branch = sample_repo
        task = task_manager.create_task("FULL", ["sample-repo"], branch)

        available = task_manager.get_repos_not_in_task(task)
        assert "sample-repo" not in available


class TestGitignoreSymlinks:
    """Tests for gitignore symlink functionality."""

    def test_create_symlinks_for_gitignored_files(self, task_manager, sample_repo):
        """Test that gitignored files are symlinked to worktree."""
        repo_path, branch = sample_repo

        # Create .gitignore and a file to be ignored
        gitignore = repo_path / ".gitignore"
        gitignore.write_text(".env\n")

        env_file = repo_path / ".env"
        env_file.write_text("SECRET=value\n")

        # Create task (worktree)
        task = task_manager.create_task("SYMLINK-TEST", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        # Verify symlink was created
        worktree_env = worktree_path / ".env"
        assert worktree_env.exists()
        assert worktree_env.is_symlink()
        assert worktree_env.resolve() == env_file.resolve()
        assert worktree_env.read_text() == "SECRET=value\n"

    def test_no_symlinks_when_no_gitignore(self, task_manager, sample_repo):
        """Test that no symlinks are created when .gitignore doesn't exist."""
        repo_path, branch = sample_repo

        # Remove .gitignore if it exists
        gitignore = repo_path / ".gitignore"
        if gitignore.exists():
            gitignore.unlink()

        # Create a random file
        some_file = repo_path / "some_file.txt"
        some_file.write_text("content\n")

        # Create task (worktree)
        task = task_manager.create_task("NO-GITIGNORE", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        # Verify no symlinks were created for the file
        worktree_file = worktree_path / "some_file.txt"
        # The file may or may not exist depending on git behavior,
        # but if it exists it should not be a symlink
        if worktree_file.exists():
            assert not worktree_file.is_symlink()

    def test_symlinks_for_multiple_gitignored_files(self, task_manager, sample_repo):
        """Test that multiple gitignored files are symlinked."""
        repo_path, branch = sample_repo

        # Create .gitignore with multiple patterns
        gitignore = repo_path / ".gitignore"
        gitignore.write_text(".env\nconfig.local.json\n*.secret\n")

        # Create matching files
        (repo_path / ".env").write_text("ENV=value\n")
        (repo_path / "config.local.json").write_text('{"key": "value"}\n')
        (repo_path / "api.secret").write_text("api_key=123\n")

        # Create task (worktree)
        task = task_manager.create_task("MULTI-SYMLINK", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        # Verify all symlinks were created
        for filename in [".env", "config.local.json", "api.secret"]:
            worktree_file = worktree_path / filename
            assert worktree_file.exists(), f"{filename} should exist"
            assert worktree_file.is_symlink(), f"{filename} should be a symlink"

    def test_skip_directory_patterns(self, task_manager, sample_repo):
        """Test that directory patterns (ending with /) are skipped."""
        repo_path, branch = sample_repo

        # Create .gitignore with directory pattern
        gitignore = repo_path / ".gitignore"
        gitignore.write_text("node_modules/\nbuild/\n.env\n")

        # Create the directories and a file
        (repo_path / "node_modules").mkdir()
        (repo_path / "node_modules" / "package.json").write_text("{}\n")
        (repo_path / ".env").write_text("test\n")

        # Create task (worktree)
        task = task_manager.create_task("DIR-SKIP", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        # .env should be symlinked
        assert (worktree_path / ".env").is_symlink()

        # node_modules directory should not be symlinked (we only symlink files)
        # and directory patterns are skipped
        if (worktree_path / "node_modules").exists():
            assert not (worktree_path / "node_modules").is_symlink()

    def test_skip_negation_patterns(self, task_manager, sample_repo):
        """Test that negation patterns (starting with !) are skipped."""
        repo_path, branch = sample_repo

        # Create .gitignore with negation pattern
        gitignore = repo_path / ".gitignore"
        gitignore.write_text(".env\n!.env.example\n")

        # Create .env
        (repo_path / ".env").write_text("SECRET\n")

        # Create task (worktree)
        task = task_manager.create_task("NEG-SKIP", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        # Only .env should be symlinked (negation patterns are ignored)
        assert (worktree_path / ".env").is_symlink()

    def test_skip_comments_and_empty_lines(self, task_manager, sample_repo):
        """Test that comments and empty lines in .gitignore are skipped."""
        repo_path, branch = sample_repo

        # Create .gitignore with comments and empty lines
        gitignore = repo_path / ".gitignore"
        gitignore.write_text("# This is a comment\n\n.env\n   # indented comment\n\n")

        # Create .env
        (repo_path / ".env").write_text("test\n")

        # Create task (worktree)
        task = task_manager.create_task("COMMENTS", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        # .env should be symlinked
        assert (worktree_path / ".env").is_symlink()

    def test_parse_gitignore_method(self, task_manager, sample_repo):
        """Test the _parse_gitignore method directly."""
        repo_path, branch = sample_repo

        gitignore = repo_path / ".gitignore"
        gitignore.write_text("""# Comment
.env
!negation

node_modules/
*.log
config.local.json
""")

        patterns = task_manager._parse_gitignore(gitignore)

        # Should include file patterns, exclude comments, negations, and directory patterns
        assert ".env" in patterns
        assert "*.log" in patterns
        assert "config.local.json" in patterns
        assert "# Comment" not in patterns
        assert "!negation" not in patterns
        assert "node_modules/" not in patterns

    def test_symlinks_skip_blocklisted_files(self, task_manager, sample_repo):
        """Test that files matching blocklist patterns are not symlinked."""
        repo_path, branch = sample_repo

        # Create .gitignore with both wanted and blocklisted patterns
        gitignore = repo_path / ".gitignore"
        gitignore.write_text(".env\n*.pyc\n.coverage\n*.log\n")

        # Create files - some should be linked, some blocked
        (repo_path / ".env").write_text("SECRET=value\n")
        (repo_path / "test.pyc").write_text("compiled\n")
        (repo_path / ".coverage").write_text("coverage data\n")
        (repo_path / "app.log").write_text("log content\n")

        # Create task (worktree)
        task = task_manager.create_task("BLOCKLIST-TEST", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        # .env should be symlinked (not in default blocklist)
        assert (worktree_path / ".env").exists()
        assert (worktree_path / ".env").is_symlink()

        # Blocklisted files should NOT be symlinked
        assert not (worktree_path / "test.pyc").exists()
        assert not (worktree_path / ".coverage").exists()
        assert not (worktree_path / "app.log").exists()

    def test_symlinks_with_empty_blocklist(self, temp_dirs, sample_repo):
        """Test that empty blocklist allows all files to be symlinked."""
        from tasktree_manager.services.config import Config
        from tasktree_manager.services.task_manager import TaskManager

        repos_dir, tasks_dir = temp_dirs
        repo_path, branch = sample_repo

        # Create config with empty blocklist
        config = Config(
            repos_dir=repos_dir,
            tasks_dir=tasks_dir,
            config_dir=repos_dir.parent / ".config" / "tasktree-manager",
            symlink_blocklist=[],  # Empty blocklist
        )
        manager = TaskManager(config)

        # Create .gitignore with patterns that would normally be blocked
        gitignore = repo_path / ".gitignore"
        gitignore.write_text(".env\n*.pyc\n.coverage\n")

        # Create files
        (repo_path / ".env").write_text("SECRET=value\n")
        (repo_path / "test.pyc").write_text("compiled\n")
        (repo_path / ".coverage").write_text("coverage data\n")

        # Create task (worktree)
        task = manager.create_task("EMPTY-BLOCKLIST", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        # All files should be symlinked with empty blocklist
        assert (worktree_path / ".env").is_symlink()
        assert (worktree_path / "test.pyc").is_symlink()
        assert (worktree_path / ".coverage").is_symlink()

    def test_symlinks_custom_blocklist(self, temp_dirs, sample_repo):
        """Test that custom blocklist patterns are respected."""
        from tasktree_manager.services.config import Config
        from tasktree_manager.services.task_manager import TaskManager

        repos_dir, tasks_dir = temp_dirs
        repo_path, branch = sample_repo

        # Create config with custom blocklist (block .env but allow *.pyc)
        config = Config(
            repos_dir=repos_dir,
            tasks_dir=tasks_dir,
            config_dir=repos_dir.parent / ".config" / "tasktree-manager",
            symlink_blocklist=[".env*", "*.secret"],  # Custom blocklist
        )
        manager = TaskManager(config)

        # Create .gitignore
        gitignore = repo_path / ".gitignore"
        gitignore.write_text(".env\n.env.local\ntest.pyc\napi.secret\n")

        # Create files
        (repo_path / ".env").write_text("blocked\n")
        (repo_path / ".env.local").write_text("also blocked\n")
        (repo_path / "test.pyc").write_text("allowed now\n")
        (repo_path / "api.secret").write_text("blocked\n")

        # Create task (worktree)
        task = manager.create_task("CUSTOM-BLOCKLIST", ["sample-repo"], branch)
        worktree_path = task.worktrees[0].path

        # .env files should be blocked
        assert not (worktree_path / ".env").exists()
        assert not (worktree_path / ".env.local").exists()
        assert not (worktree_path / "api.secret").exists()

        # .pyc should be allowed with this custom blocklist
        assert (worktree_path / "test.pyc").is_symlink()

    def test_matches_blocklist_method(self, task_manager):
        """Test the _matches_blocklist helper method."""
        blocklist = ["*.pyc", ".coverage", "__pycache__", "*.log"]

        # These should match
        assert task_manager._matches_blocklist("test.pyc", blocklist)
        assert task_manager._matches_blocklist(".coverage", blocklist)
        assert task_manager._matches_blocklist("__pycache__", blocklist)
        assert task_manager._matches_blocklist("app.log", blocklist)
        assert task_manager._matches_blocklist("debug.log", blocklist)

        # These should not match
        assert not task_manager._matches_blocklist(".env", blocklist)
        assert not task_manager._matches_blocklist("config.json", blocklist)
        assert not task_manager._matches_blocklist(".mise.toml", blocklist)
        assert not task_manager._matches_blocklist("README.md", blocklist)
