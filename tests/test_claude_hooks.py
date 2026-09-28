"""Tests for Claude Code hook and settings configuration."""

import json
from pathlib import Path

import pytest

from tasktree_manager.services.claude_hooks import (
    ensure_claude_hooks,
    ensure_worktree_claude_settings,
    has_claude_session,
    migrate_legacy_memory_dir,
    project_dir_candidates,
    repo_memory_dir,
)


class TestEnsureClaudeHooks:
    """Tests for ensure_claude_hooks."""

    def test_creates_settings_with_hooks(self, tmp_path):
        """Test that settings.local.json is created with status hooks."""
        ensure_claude_hooks(tmp_path)

        settings_file = tmp_path / ".claude" / "settings.local.json"
        assert settings_file.exists()

        settings = json.loads(settings_file.read_text())
        for event in ("SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"):
            assert event in settings["hooks"]
        assert str(tmp_path / ".claude_status") in json.dumps(settings["hooks"])

    def test_no_memory_dir_by_default(self, tmp_path):
        """Test that autoMemoryDirectory is not written when memory_dir is empty."""
        ensure_claude_hooks(tmp_path)

        settings_file = tmp_path / ".claude" / "settings.local.json"
        settings = json.loads(settings_file.read_text())
        assert "autoMemoryDirectory" not in settings

    def test_memory_dir_written_expanded(self, tmp_path):
        """Test that memory_dir is written as an expanded absolute path."""
        ensure_claude_hooks(tmp_path, "~/.claude/tasktree-memory")

        settings_file = tmp_path / ".claude" / "settings.local.json"
        settings = json.loads(settings_file.read_text())
        assert settings["autoMemoryDirectory"] == str(Path.home() / ".claude" / "tasktree-memory")

    def test_preserves_existing_settings(self, tmp_path):
        """Test that unrelated existing settings keys survive a rewrite."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "settings.local.json"
        settings_file.write_text(json.dumps({"permissions": {"allow": ["Bash(ls *)"]}}))

        ensure_claude_hooks(tmp_path, "~/.claude/tasktree-memory")

        settings = json.loads(settings_file.read_text())
        assert settings["permissions"] == {"allow": ["Bash(ls *)"]}
        assert "hooks" in settings
        assert "autoMemoryDirectory" in settings

    def test_empty_memory_dir_leaves_existing_value(self, tmp_path):
        """Test that an existing autoMemoryDirectory is kept when memory_dir is empty."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "settings.local.json"
        settings_file.write_text(json.dumps({"autoMemoryDirectory": "/custom/memory"}))

        ensure_claude_hooks(tmp_path, "")

        settings = json.loads(settings_file.read_text())
        assert settings["autoMemoryDirectory"] == "/custom/memory"

    def test_memory_dir_overrides_existing_value(self, tmp_path):
        """Test that a configured memory_dir replaces a previously written one."""
        ensure_claude_hooks(tmp_path, "/old/memory")
        ensure_claude_hooks(tmp_path, "/new/memory")

        settings_file = tmp_path / ".claude" / "settings.local.json"
        settings = json.loads(settings_file.read_text())
        assert settings["autoMemoryDirectory"] == "/new/memory"

    def test_recovers_from_corrupt_settings(self, tmp_path):
        """Invalid JSON is moved aside (it may hold the user's permissions),
        then a fresh settings file is written."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "settings.local.json"
        settings_file.write_text("{not json")

        ensure_claude_hooks(tmp_path, "~/.claude/tasktree-memory")

        settings = json.loads(settings_file.read_text())
        assert "hooks" in settings
        assert "autoMemoryDirectory" in settings
        backups = list(claude_dir.glob("settings.local.json.broken-*"))
        assert len(backups) == 1
        assert backups[0].read_text() == "{not json"

    def test_recovers_from_non_utf8_settings(self, tmp_path):
        """Bytes that fail to decode are quarantined like unparseable JSON
        (UnicodeDecodeError is a ValueError, not an OSError)."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "settings.local.json"
        settings_file.write_bytes(b"\xff\xfe{not utf8")

        ensure_claude_hooks(tmp_path, "~/.claude/tasktree-memory")

        settings = json.loads(settings_file.read_text())
        assert "hooks" in settings
        assert "autoMemoryDirectory" in settings
        backups = list(claude_dir.glob("settings.local.json.broken-*"))
        assert len(backups) == 1
        assert backups[0].read_bytes() == b"\xff\xfe{not utf8"

    def test_recovers_from_non_dict_json(self, tmp_path):
        """Valid JSON that is not an object (e.g. an array) is quarantined
        too, not silently discarded in place."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "settings.local.json"
        settings_file.write_text("[1, 2, 3]")

        ensure_claude_hooks(tmp_path, "~/.claude/tasktree-memory")

        settings = json.loads(settings_file.read_text())
        assert "hooks" in settings
        assert "autoMemoryDirectory" in settings
        backups = list(claude_dir.glob("settings.local.json.broken-*"))
        assert len(backups) == 1
        assert backups[0].read_text() == "[1, 2, 3]"

    def test_write_leaves_no_temp_file_behind(self, tmp_path):
        """A successful write cleans up after the temp-file + rename dance."""
        ensure_claude_hooks(tmp_path)

        assert list((tmp_path / ".claude").glob("settings.local.json.tmp")) == []

    def test_write_failure_leaves_existing_settings_untouched(self, tmp_path, monkeypatch):
        """A crash between the temp-file write and the rename (os.replace)
        must not corrupt the settings already on disk."""
        ensure_claude_hooks(tmp_path)
        settings_file = tmp_path / ".claude" / "settings.local.json"
        original = settings_file.read_text()

        def boom(*_args, **_kwargs):
            raise OSError("disk full")

        monkeypatch.setattr("tasktree_manager.services.claude_hooks.os.replace", boom)

        with pytest.raises(OSError):
            ensure_claude_hooks(tmp_path, "~/.claude/tasktree-memory")

        assert settings_file.read_text() == original

    def test_preserves_user_hooks(self, tmp_path):
        """User-written hook groups survive: settings.local.json holds
        executable config the user may have added by hand."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "settings.local.json"
        user_stop_hook = {"hooks": [{"type": "command", "command": "echo user-stop"}]}
        user_post_tool = {"hooks": [{"type": "command", "command": "echo post-tool"}]}
        settings_file.write_text(
            json.dumps({"hooks": {"Stop": [user_stop_hook], "PostToolUse": [user_post_tool]}})
        )

        ensure_claude_hooks(tmp_path)

        settings = json.loads(settings_file.read_text())
        # Untouched event survives entirely
        assert settings["hooks"]["PostToolUse"] == [user_post_tool]
        # Shared event keeps the user group and gains the tasktree group
        stop_commands = json.dumps(settings["hooks"]["Stop"])
        assert "echo user-stop" in stop_commands
        assert ".claude_status" in stop_commands

    def test_rerun_does_not_duplicate_hooks(self, tmp_path):
        """Repeated calls replace tasktree's own groups instead of stacking."""
        ensure_claude_hooks(tmp_path)
        ensure_claude_hooks(tmp_path)

        settings_file = tmp_path / ".claude" / "settings.local.json"
        settings = json.loads(settings_file.read_text())
        for event in ("SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"):
            assert len(settings["hooks"][event]) == 1

    def test_tolerates_non_string_hook_command(self, tmp_path):
        """A user hook whose command is not a string must not crash merging."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "settings.local.json"
        weird_group = {"hooks": [{"type": "command", "command": None}]}
        settings_file.write_text(json.dumps({"hooks": {"Stop": [weird_group]}}))

        ensure_claude_hooks(tmp_path)

        settings = json.loads(settings_file.read_text())
        # The malformed group is treated as user-owned and preserved
        assert weird_group in settings["hooks"]["Stop"]
        assert ".claude_status" in json.dumps(settings["hooks"]["Stop"])


class TestRepoMemoryDir:
    """Tests for repo_memory_dir."""

    def test_encodes_repo_path(self, tmp_path, monkeypatch):
        """Test that the repo path is encoded like Claude project dirs."""
        monkeypatch.setenv("HOME", str(tmp_path))
        result = repo_memory_dir(Path("/repos/work.3"))
        assert result == tmp_path / ".claude" / "projects" / "-repos-work-3" / "memory"


class TestEnsureWorktreeClaudeSettings:
    """Tests for ensure_worktree_claude_settings."""

    @staticmethod
    def _make_repo_and_worktree(tmp_path):
        repo_path = tmp_path / "repos" / "work3"
        (repo_path / ".git" / "info").mkdir(parents=True)
        worktree_path = tmp_path / "tasks" / "TASK-1" / "work3"
        worktree_path.mkdir(parents=True)
        status_file = tmp_path / "tasks" / "TASK-1" / ".claude_status"
        return repo_path, worktree_path, status_file

    def test_points_memory_at_repo(self, tmp_path, monkeypatch):
        """Test that autoMemoryDirectory targets the main repo's memory dir."""
        monkeypatch.setenv("HOME", str(tmp_path))
        repo_path, worktree_path, status_file = self._make_repo_and_worktree(tmp_path)

        ensure_worktree_claude_settings(worktree_path, repo_path, status_file)

        settings = json.loads((worktree_path / ".claude" / "settings.local.json").read_text())
        assert settings["autoMemoryDirectory"] == str(repo_memory_dir(repo_path))

    def test_writes_status_hooks(self, tmp_path, monkeypatch):
        """Test that status hooks write to the task's status file."""
        monkeypatch.setenv("HOME", str(tmp_path))
        repo_path, worktree_path, status_file = self._make_repo_and_worktree(tmp_path)

        ensure_worktree_claude_settings(worktree_path, repo_path, status_file)

        settings = json.loads((worktree_path / ".claude" / "settings.local.json").read_text())
        for event in ("SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"):
            assert event in settings["hooks"]
        assert str(status_file) in json.dumps(settings["hooks"])

    def test_preserves_existing_settings(self, tmp_path, monkeypatch):
        """Test that unrelated existing settings keys survive a rewrite."""
        monkeypatch.setenv("HOME", str(tmp_path))
        repo_path, worktree_path, status_file = self._make_repo_and_worktree(tmp_path)
        claude_dir = worktree_path / ".claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "settings.local.json"
        settings_file.write_text(json.dumps({"permissions": {"allow": ["Bash(ls *)"]}}))

        ensure_worktree_claude_settings(worktree_path, repo_path, status_file)

        settings = json.loads(settings_file.read_text())
        assert settings["permissions"] == {"allow": ["Bash(ls *)"]}
        assert "autoMemoryDirectory" in settings

    def test_excludes_settings_from_git(self, tmp_path, monkeypatch):
        """Test that the settings file is added to the repo's git exclude."""
        monkeypatch.setenv("HOME", str(tmp_path))
        repo_path, worktree_path, status_file = self._make_repo_and_worktree(tmp_path)

        ensure_worktree_claude_settings(worktree_path, repo_path, status_file)

        exclude = (repo_path / ".git" / "info" / "exclude").read_text()
        assert ".claude/settings.local.json" in exclude

    def test_exclude_entry_is_idempotent(self, tmp_path, monkeypatch):
        """Test that repeated calls do not duplicate the exclude entry."""
        monkeypatch.setenv("HOME", str(tmp_path))
        repo_path, worktree_path, status_file = self._make_repo_and_worktree(tmp_path)

        ensure_worktree_claude_settings(worktree_path, repo_path, status_file)
        ensure_worktree_claude_settings(worktree_path, repo_path, status_file)

        lines = (repo_path / ".git" / "info" / "exclude").read_text().splitlines()
        assert lines.count(".claude/settings.local.json") == 1

    def test_preserves_user_hooks(self, tmp_path, monkeypatch):
        """User-written hook groups in a worktree's settings survive, and
        reruns do not stack duplicate tasktree groups."""
        monkeypatch.setenv("HOME", str(tmp_path))
        repo_path, worktree_path, status_file = self._make_repo_and_worktree(tmp_path)
        claude_dir = worktree_path / ".claude"
        claude_dir.mkdir()
        user_stop_hook = {"hooks": [{"type": "command", "command": "echo user-stop"}]}
        (claude_dir / "settings.local.json").write_text(
            json.dumps({"hooks": {"Stop": [user_stop_hook]}})
        )

        ensure_worktree_claude_settings(worktree_path, repo_path, status_file)
        ensure_worktree_claude_settings(worktree_path, repo_path, status_file)

        settings = json.loads((claude_dir / "settings.local.json").read_text())
        stop_groups = settings["hooks"]["Stop"]
        assert user_stop_hook in stop_groups
        assert len(stop_groups) == 2  # user group + one tasktree group, no dupes

    def test_git_file_instead_of_dir(self, tmp_path, monkeypatch):
        """Test that a .git file (linked worktree/submodule) is skipped safely."""
        monkeypatch.setenv("HOME", str(tmp_path))
        repo_path = tmp_path / "repos" / "work3"
        repo_path.mkdir(parents=True)
        (repo_path / ".git").write_text("gitdir: /elsewhere\n")
        worktree_path = tmp_path / "tasks" / "TASK-1" / "work3"
        worktree_path.mkdir(parents=True)

        ensure_worktree_claude_settings(
            worktree_path, repo_path, tmp_path / "tasks" / "TASK-1" / ".claude_status"
        )

        assert (worktree_path / ".claude" / "settings.local.json").exists()


class TestHasClaudeSession:
    """Tests for has_claude_session."""

    def test_no_project_dir(self, tmp_path, monkeypatch):
        """Test False when no project directory exists."""
        monkeypatch.setenv("HOME", str(tmp_path))
        assert has_claude_session(Path("/some/task")) is False

    def test_project_dir_with_transcript(self, tmp_path, monkeypatch):
        """Test True when the encoded project directory holds a transcript."""
        monkeypatch.setenv("HOME", str(tmp_path))
        task_path = Path("/some/task.dir")
        encoded = "-some-task-dir"
        project_dir = tmp_path / ".claude" / "projects" / encoded
        project_dir.mkdir(parents=True)
        (project_dir / "abc.jsonl").touch()

        assert has_claude_session(task_path) is True


class TestProjectDirCandidates:
    """Tests for project_dir_candidates and the encoder rules behind it."""

    def test_current_rule_replaces_every_non_alnum(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
        current, legacy = project_dir_candidates(Path("/Users/x/my_dir/a b"))
        assert current == tmp_path / "projects" / "-Users-x-my-dir-a-b"
        assert legacy == tmp_path / "projects" / "-Users-x-my_dir-a b"

    def test_single_candidate_when_rules_agree(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
        assert project_dir_candidates(Path("/some/task.dir")) == [
            tmp_path / "projects" / "-some-task-dir"
        ]

    def test_has_claude_session_finds_legacy_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
        legacy = tmp_path / "projects" / "-Users-x-my_dir"
        legacy.mkdir(parents=True)
        (legacy / "abc.jsonl").touch()
        assert has_claude_session(Path("/Users/x/my_dir")) is True


class TestMigrateLegacyMemoryDir:
    """Memory saved under an old-rule project dir moves to the current one."""

    REPO = Path("/Users/x/my_dir")

    def test_moves_legacy_memory_when_current_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
        legacy = tmp_path / "projects" / "-Users-x-my_dir" / "memory"
        legacy.mkdir(parents=True)
        (legacy / "MEMORY.md").write_text("remember")

        assert migrate_legacy_memory_dir(self.REPO) is True
        assert not legacy.exists()
        assert (repo_memory_dir(self.REPO) / "MEMORY.md").read_text() == "remember"

    def test_keeps_both_when_current_exists(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
        legacy = tmp_path / "projects" / "-Users-x-my_dir" / "memory"
        legacy.mkdir(parents=True)
        repo_memory_dir(self.REPO).mkdir(parents=True)

        assert migrate_legacy_memory_dir(self.REPO) is False
        assert legacy.is_dir()

    def test_noop_when_rules_agree(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
        assert migrate_legacy_memory_dir(Path("/some/task.dir")) is False

    def test_worktree_settings_trigger_migration(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
        repo_path = tmp_path / "repos" / "my_repo"
        (repo_path / ".git" / "info").mkdir(parents=True)
        worktree_path = tmp_path / "tasks" / "TASK-1" / "my_repo"
        worktree_path.mkdir(parents=True)
        legacy = tmp_path / "cfg" / "projects" / project_dir_candidates(repo_path)[1].name
        (legacy / "memory").mkdir(parents=True)
        (legacy / "memory" / "MEMORY.md").write_text("kept")

        ensure_worktree_claude_settings(
            worktree_path, repo_path, tmp_path / "tasks" / "TASK-1" / ".claude_status"
        )

        settings = json.loads((worktree_path / ".claude" / "settings.local.json").read_text())
        assert settings["autoMemoryDirectory"] == str(repo_memory_dir(repo_path))
        assert (repo_memory_dir(repo_path) / "MEMORY.md").read_text() == "kept"


class TestSymlinkedRepoPath:
    """Claude CLI keys a session to the OS-resolved cwd, so a symlinked
    repos/tasks dir must encode to the same project dir as the resolved
    path — otherwise repo-memory sharing, session-resume detection, and
    recap all miss (regression tests for the resolve-before-encode fix)."""

    def test_repo_memory_dir_matches_resolved_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
        real_repo = tmp_path / "real" / "repo"
        real_repo.mkdir(parents=True)
        link_root = tmp_path / "link"
        link_root.symlink_to(tmp_path / "real")

        assert repo_memory_dir(link_root / "repo") == repo_memory_dir(real_repo)

    def test_has_claude_session_finds_resolved_project_dir(self, tmp_path, monkeypatch):
        """A transcript filed under the resolved path is found through the
        symlink, matching where the real Claude CLI would write it."""
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
        real_task = tmp_path / "real" / "task"
        real_task.mkdir(parents=True)
        link_root = tmp_path / "link"
        link_root.symlink_to(tmp_path / "real")

        resolved_dir = project_dir_candidates(real_task)[0]
        resolved_dir.mkdir(parents=True)
        (resolved_dir / "s1.jsonl").touch()

        assert has_claude_session(link_root / "task") is True

    def test_has_claude_session_still_finds_raw_symlink_dir(self, tmp_path, monkeypatch):
        """Backwards compatibility: a dir a pre-fix tasktree wrote, keyed to
        the raw (unresolved) symlinked path, must remain discoverable so
        existing sessions are not orphaned by this change."""
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
        real_task = tmp_path / "real" / "task"
        real_task.mkdir(parents=True)
        link_root = tmp_path / "link"
        link_root.symlink_to(tmp_path / "real")
        raw_folder = link_root / "task"

        resolved_candidates = project_dir_candidates(real_task)
        raw_only = [c for c in project_dir_candidates(raw_folder) if c not in resolved_candidates]
        assert raw_only, "test setup requires the raw and resolved paths to differ"
        raw_only[0].mkdir(parents=True)
        (raw_only[0] / "s1.jsonl").touch()

        assert has_claude_session(raw_folder) is True

    def test_migrate_legacy_memory_dir_keys_off_resolved_path(self, tmp_path, monkeypatch):
        """migrate_legacy_memory_dir must resolve independently of
        project_dir_candidates' now-larger candidate list."""
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
        real_repo = tmp_path / "real" / "my_repo"
        real_repo.mkdir(parents=True)
        link_root = tmp_path / "link"
        link_root.symlink_to(tmp_path / "real")

        legacy_dir = project_dir_candidates(real_repo)[1] / "memory"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "MEMORY.md").write_text("kept")

        assert migrate_legacy_memory_dir(link_root / "my_repo") is True
        assert (repo_memory_dir(real_repo) / "MEMORY.md").read_text() == "kept"

    def test_ensure_worktree_claude_settings_symlinked_repo(self, tmp_path, monkeypatch):
        """A worktree of a symlinked repo shares memory with the main
        checkout's own (resolved-path) memory dir, not a raw-path one."""
        monkeypatch.setenv("HOME", str(tmp_path))
        real_repo = tmp_path / "real" / "repo3"
        (real_repo / ".git" / "info").mkdir(parents=True)
        link_root = tmp_path / "link"
        link_root.symlink_to(tmp_path / "real")
        worktree_path = tmp_path / "tasks" / "TASK-1" / "repo3"
        worktree_path.mkdir(parents=True)
        status_file = tmp_path / "tasks" / "TASK-1" / ".claude_status"

        ensure_worktree_claude_settings(worktree_path, link_root / "repo3", status_file)

        settings = json.loads((worktree_path / ".claude" / "settings.local.json").read_text())
        assert settings["autoMemoryDirectory"] == str(repo_memory_dir(real_repo))
