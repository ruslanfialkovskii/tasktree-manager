"""Tests for the managed epic block in task CLAUDE.md files."""

import os

import pytest

from tasktree_manager.cli import run_cli
from tasktree_manager.services.task_manager import EPIC_BLOCK_END, EPIC_BLOCK_START


@pytest.fixture
def tm(task_manager):
    task_manager.create_task("E-1", [], kind="epic")
    task_manager.create_task("E-2", [], kind="epic")
    return task_manager


def claude_md(tm, name):
    return (tm.config.tasks_dir / name / "CLAUDE.md").read_text()


def prepare(tm, name):
    tm.ensure_claude_md_files(tm.get_task(name))
    return tm.get_task(name)


class TestEpicBlock:
    def test_child_block_backfilled(self, tm):
        tm.create_task("T-1", [], epic="E-1")
        prepare(tm, "T-1")
        text = claude_md(tm, "T-1")
        assert text.startswith("# Task: T-1")
        assert text.count(EPIC_BLOCK_START) == 1
        assert "belongs to the epic `E-1`" in text
        assert str(tm.config.tasks_dir / "E-1") in text

    def test_epic_block(self, tm):
        prepare(tm, "E-1")
        assert "This folder is the epic `E-1`" in claude_md(tm, "E-1")

    def test_sync_twice_changes_nothing(self, tm):
        tm.create_task("T-1", [], epic="E-1")
        task = prepare(tm, "T-1")
        first = claude_md(tm, "T-1")
        tm.sync_epic_block(task)
        tm.ensure_claude_md_files(task)
        assert claude_md(tm, "T-1") == first

    def test_move_and_detach_keep_user_text(self, tm):
        task = tm.create_task("T-1", [], epic="E-1")
        path = task.path / "CLAUDE.md"
        path.write_text("# My notes\n\nkeep this\n")
        tm.sync_epic_block(task)
        path.write_text(path.read_text() + "\n## After\n\nand this\n")
        tm.set_task_epic(task, "E-2")
        text = path.read_text()
        assert "epic `E-2`" in text and "epic `E-1`" not in text
        assert text.startswith("# My notes\n\nkeep this\n")
        assert text.endswith("## After\n\nand this\n")
        tm.set_task_epic(task, None)
        assert path.read_text() == "# My notes\n\nkeep this\n\n## After\n\nand this\n"

    def test_unmark_removes_epic_block(self, tm):
        epic = prepare(tm, "E-2")
        tm.set_task_kind(epic, "task")
        assert EPIC_BLOCK_START not in claude_md(tm, "E-2")

    @pytest.mark.parametrize(
        "broken",
        [
            EPIC_BLOCK_START + "\nhalf",
            EPIC_BLOCK_END + "\n" + EPIC_BLOCK_START,
            (EPIC_BLOCK_START + "\nx\n" + EPIC_BLOCK_END + "\n") * 2,
        ],
    )
    def test_mismatched_markers_left_alone(self, tm, broken):
        task = tm.create_task("T-1", [], epic="E-1")
        path = task.path / "CLAUDE.md"
        path.write_text("notes\n" + broken)
        tm.sync_epic_block(task)
        assert path.read_text() == "notes\n" + broken

    def test_stub_with_block_is_not_archived(self, tm):
        tm.create_task("T-1", [], epic="E-1")
        task = prepare(tm, "T-1")
        assert tm.archive_task(task) is None

    def test_edited_file_with_block_is_archived(self, tm):
        tm.create_task("T-1", [], epic="E-1")
        task = prepare(tm, "T-1")
        path = task.path / "CLAUDE.md"
        path.write_text(path.read_text() + "\nmy plan\n")
        result = tm.archive_task(task)
        assert result is not None and "CLAUDE.md" in result.files

    def test_missing_file_not_created_by_epic_change(self, tm):
        task = tm.create_task("T-1", [])
        tm.set_task_epic(task, "E-1")
        assert not (task.path / "CLAUDE.md").exists()

    def test_cli_epic_add_updates_block(self, tm, config, capsys):
        tm.create_task("T-1", [])
        prepare(tm, "T-1")
        assert run_cli(["epic", "add", "E-1", "T-1"], config=config) == 0
        assert "epic `E-1`" in claude_md(tm, "T-1")


class TestEpicBlockRobustness:
    def test_crlf_file_round_trips(self, tm):
        task = tm.create_task("T-1", [])
        path = task.path / "CLAUDE.md"
        original = b"# Notes\r\n\r\nline\r\n"
        path.write_bytes(original)
        tm.set_task_epic(task, "E-1")
        data = path.read_bytes()
        assert data.startswith(original)
        assert b"\n" not in data.replace(b"\r\n", b"")
        tm.set_task_epic(task, None)
        assert path.read_bytes() == original

    def test_non_utf8_file_keeps_bytes_and_prep_runs(self, tm):
        task = tm.create_task("T-1", [], epic="E-1")
        path = task.path / "CLAUDE.md"
        path.write_bytes(b"caf\xe9 notes\n")
        tm.ensure_claude_md_files(task)  # must not raise
        data = path.read_bytes()
        assert data.startswith(b"caf\xe9 notes\n")
        assert b"epic `E-1`" in data

    def test_read_only_file_is_reported_not_raised(self, tm):
        task = tm.create_task("T-1", [])
        path = task.path / "CLAUDE.md"
        path.write_text("notes\n")
        os.chmod(path, 0o444)
        try:
            tm.set_task_epic(task, "E-1")
            problem = tm.sync_epic_block(task)
            tm.ensure_claude_md_files(task)
        finally:
            os.chmod(path, 0o644)
        assert "read-only" in problem
        assert path.read_text() == "notes\n"

    def test_failed_write_keeps_original(self, tm, monkeypatch):
        task = tm.create_task("T-1", [])
        path = task.path / "CLAUDE.md"
        path.write_text("notes\n" * 50)

        def full_disk(src, dst):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(os, "replace", full_disk)
        tm.set_task_epic(task, "E-1")
        assert path.read_text() == "notes\n" * 50
        assert "No space left" in tm.sync_epic_block(task)
        assert [p.name for p in task.path.iterdir() if p.name.endswith(".tmp")] == []

    def test_unmark_with_planted_parent_marker(self, tm):
        epic = prepare(tm, "E-2")
        (epic.path / ".tasktree_epic").write_text("E-1\n")
        tm.set_task_kind(epic, "task")
        assert EPIC_BLOCK_START not in claude_md(tm, "E-2")

    def test_broken_markers_count_as_edited_for_archive(self, tm):
        tm.create_task("T-1", [], epic="E-1")
        task = prepare(tm, "T-1")
        path = task.path / "CLAUDE.md"
        path.write_text(path.read_text() + EPIC_BLOCK_START + "\n")
        result = tm.archive_task(task)
        assert result is not None and "CLAUDE.md" in result.files

    def test_cli_warns_on_mismatched_markers(self, tm, config, capsys):
        task = tm.create_task("T-1", [])
        (task.path / "CLAUDE.md").write_text(EPIC_BLOCK_START + "\n")
        assert run_cli(["epic", "add", "E-1", "T-1"], config=config) == 0
        assert "mismatched tasktree:epic markers" in capsys.readouterr().err
