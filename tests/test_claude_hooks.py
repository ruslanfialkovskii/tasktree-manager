"""Tests for Claude Code hook and settings configuration."""

import json
from pathlib import Path

from tasktree_manager.services.claude_hooks import ensure_claude_hooks, has_claude_session


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
        assert settings["autoMemoryDirectory"] == str(
            Path.home() / ".claude" / "tasktree-memory"
        )

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
        """Test that invalid JSON in existing settings is replaced, not fatal."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "settings.local.json"
        settings_file.write_text("{not json")

        ensure_claude_hooks(tmp_path, "~/.claude/tasktree-memory")

        settings = json.loads(settings_file.read_text())
        assert "hooks" in settings
        assert "autoMemoryDirectory" in settings


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
