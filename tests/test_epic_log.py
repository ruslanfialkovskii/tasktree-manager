"""Tests for the epic log: `epic note`, `epic log` and `epic sync`."""

import io
import json
import os
from datetime import datetime, timezone

import pytest

from tasktree_manager.cli import run_cli
from tasktree_manager.services.claude_hooks import _encode_project_path
from tasktree_manager.services.claude_sessions import latest_session
from tasktree_manager.services.task_manager import (
    EPIC_LOG_DIR,
    EPIC_NOTE_MAX_BYTES,
    EPIC_NOTES_READ_BYTES,
)

NOW = datetime(2026, 10, 20, 9, 30, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def claude_config(tmp_path, monkeypatch):
    """Keep every test away from the real ~/.claude transcripts."""
    path = tmp_path / "claude-config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(path))
    return path


@pytest.fixture
def tm(task_manager):
    task_manager.create_task("E-1", [], kind="epic")
    task_manager.create_task("E-2", [], kind="epic")
    task_manager.create_task("T-1", [], epic="E-1")
    task_manager.create_task("T-2", [], epic="E-1")
    task_manager.create_task("U-1", [], epic="E-2")
    task_manager.create_task("LONE", [])
    return task_manager


def cli(config, *argv):
    return run_cli(list(argv), config=config)


def log_dir(tm, epic="E-1"):
    return tm.config.tasks_dir / epic / EPIC_LOG_DIR


def notes_file(tm, epic, task):
    return log_dir(tm, epic) / f"{task}.md"


def add_worktree(folder, name):
    """A folder the task manager counts as a worktree."""
    worktree = folder / name
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: /nowhere\n")
    return worktree


def write_transcript(folder, session_id, summary, mtime, cwd=None, prompt=None):
    """A transcript under $CLAUDE_CONFIG_DIR for a session started in `cwd`."""
    project = os.path.join(
        os.environ["CLAUDE_CONFIG_DIR"], "projects", _encode_project_path(folder.resolve())
    )
    os.makedirs(project, exist_ok=True)
    records = [
        {"type": "user", "cwd": str(cwd or folder)},
        {"type": "last-prompt", "lastPrompt": prompt or f"prompt in {session_id}"},
    ]
    if summary:
        records.append(
            {
                "type": "system",
                "subtype": "away_summary",
                "content": summary,
                "timestamp": "2026-10-20T09:00:00.000Z",
            }
        )
    path = os.path.join(project, f"{session_id}.jsonl")
    with open(path, "w") as f:
        f.write("".join(json.dumps(r) + "\n" for r in records))
    os.utime(path, (mtime, mtime))


def log_json(config, *argv):
    assert cli(config, "epic", "log", *argv, "--json") == 0


class TestAppendNote:
    def test_first_note_gets_header(self, tm):
        path = tm.append_epic_note(tm.get_task("T-1"), "  chose S3 layout A  ", now=NOW)
        assert path == notes_file(tm, "E-1", "T-1")
        assert path.read_text() == (
            "# Notes from T-1\n\n## 2026-10-20 09:30 UTC\n\nchose S3 layout A\n\n"
        )

    def test_second_note_appends(self, tm):
        task = tm.get_task("T-1")
        tm.append_epic_note(task, "one", now=NOW)
        tm.append_epic_note(task, "two", now=NOW)
        text = notes_file(tm, "E-1", "T-1").read_text()
        assert text.count("# Notes from T-1") == 1
        assert text.index("one") < text.index("two")

    def test_source_goes_into_heading(self, tm):
        tm.append_epic_note(tm.get_task("T-1"), "x", now=NOW, source="by hand")
        assert "## 2026-10-20 09:30 UTC (by hand)" in notes_file(tm, "E-1", "T-1").read_text()

    def test_epic_folder_writes_its_own_file(self, tm):
        tm.append_epic_note(tm.get_task("E-1"), "plan v2", now=NOW)
        assert "plan v2" in notes_file(tm, "E-1", "E-1").read_text()

    def test_task_outside_epic_refused(self, tm):
        with pytest.raises(ValueError, match="not in an epic"):
            tm.append_epic_note(tm.get_task("LONE"), "x")

    def test_empty_note_refused(self, tm):
        with pytest.raises(ValueError, match="empty"):
            tm.append_epic_note(tm.get_task("T-1"), "  \n ")

    def test_oversized_note_refused(self, tm):
        with pytest.raises(ValueError, match="limit"):
            tm.append_epic_note(tm.get_task("T-1"), "x" * (EPIC_NOTE_MAX_BYTES + 1))

    def test_symlinked_log_folder_refused(self, tm, tmp_path):
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        log_dir(tm).symlink_to(elsewhere)
        with pytest.raises(ValueError, match="symlink"):
            tm.append_epic_note(tm.get_task("T-1"), "x")
        assert list(elsewhere.iterdir()) == []

    def test_worktree_named_like_log_folder_refused(self, tm):
        add_worktree(tm.config.tasks_dir / "E-1", EPIC_LOG_DIR)
        with pytest.raises(ValueError, match="git checkout"):
            tm.append_epic_note(tm.get_task("T-1"), "x")
        assert not notes_file(tm, "E-1", "T-1").exists()
        assert tm.read_epic_note("E-1", "T-1") is None

    def test_symlinked_notes_file_not_written_through(self, tm, tmp_path):
        target = tmp_path / "target.md"
        target.write_text("keep")
        log_dir(tm).mkdir()
        notes_file(tm, "E-1", "T-1").symlink_to(target)
        with pytest.raises(ValueError, match="not a plain notes file"):
            tm.append_epic_note(tm.get_task("T-1"), "x")
        assert target.read_text() == "keep"

    def test_hard_linked_notes_file_refused(self, tm, tmp_path):
        target = tmp_path / "target.md"
        target.write_text("keep")
        log_dir(tm).mkdir()
        os.link(target, notes_file(tm, "E-1", "T-1"))
        with pytest.raises(ValueError, match="not a plain notes file"):
            tm.append_epic_note(tm.get_task("T-1"), "x")
        assert target.read_text() == "keep"
        assert tm.read_epic_note("E-1", "T-1") is None

    def test_fifo_refused_without_hanging(self, tm):
        log_dir(tm).mkdir()
        os.mkfifo(notes_file(tm, "E-1", "T-1"))
        with pytest.raises(ValueError, match="not a plain notes file"):
            tm.append_epic_note(tm.get_task("T-1"), "x")
        assert tm.read_epic_note("E-1", "T-1") is None


class TestReadNote:
    def test_missing(self, tm):
        assert tm.read_epic_note("E-1", "T-2") is None

    def test_symlink_ignored(self, tm, tmp_path):
        target = tmp_path / "target.md"
        target.write_text("secret")
        log_dir(tm).mkdir()
        notes_file(tm, "E-1", "T-1").symlink_to(target)
        assert tm.read_epic_note("E-1", "T-1") is None

    def test_long_file_keeps_newest_part(self, tm):
        log_dir(tm).mkdir()
        old = "old line\n" * (EPIC_NOTES_READ_BYTES // 9 + 10)
        notes_file(tm, "E-1", "T-1").write_text(old + "newest note\n")
        text, truncated = tm.read_epic_note("E-1", "T-1")
        assert truncated
        assert text.endswith("newest note\n")
        assert text.startswith("old line\n")
        assert len(text.encode()) <= EPIC_NOTES_READ_BYTES


class TestNoteCli:
    def test_task_inferred_from_cwd(self, tm, config, monkeypatch, capsys):
        monkeypatch.chdir(config.tasks_dir / "T-2")
        assert cli(config, "epic", "note", "API is /v2/ingest") == 0
        text = notes_file(tm, "E-1", "T-2").read_text()
        assert "API is /v2/ingest" in text
        assert "(written outside" not in text
        assert "Noted in" in capsys.readouterr().out

    def test_task_flag_and_stdin_from_outside(self, tm, config, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("sys.stdin", io.StringIO("line one\nline two\n"))
        assert cli(config, "epic", "note", "-", "--task", "T-1") == 0
        text = notes_file(tm, "E-1", "T-1").read_text()
        assert "line one\nline two" in text
        assert "(written outside the task folder)" in text

    def test_other_task_refused_from_inside(self, tm, config, monkeypatch, capsys):
        monkeypatch.chdir(config.tasks_dir / "T-1")
        assert cli(config, "epic", "note", "x", "--task", "U-1") == 1
        assert "own file" in capsys.readouterr().err
        assert not notes_file(tm, "E-2", "U-1").exists()

    def test_own_task_flag_from_inside(self, tm, config, monkeypatch):
        monkeypatch.chdir(config.tasks_dir / "T-1")
        assert cli(config, "epic", "note", "x", "--task", "T-1") == 0

    def test_outside_task_needs_flag(self, tm, config, monkeypatch, tmp_path, capsys):
        monkeypatch.chdir(tmp_path)
        assert cli(config, "epic", "note", "x") == 1
        assert "pass --task" in capsys.readouterr().err

    def test_task_not_in_epic(self, tm, config, monkeypatch, tmp_path, capsys):
        monkeypatch.chdir(tmp_path)
        assert cli(config, "epic", "note", "x", "--task", "LONE") == 1
        assert "not in an epic" in capsys.readouterr().err

    def test_epic_alias_does_not_win_cwd(self, tm, config, monkeypatch):
        (config.tasks_dir / "0-alias").symlink_to(config.tasks_dir / "E-1")
        monkeypatch.chdir(config.tasks_dir / "E-1")
        assert cli(config, "epic", "note", "from the epic") == 0
        assert "from the epic" in notes_file(tm, "E-1", "E-1").read_text()


class TestLogCli:
    def test_whole_epic_from_member(self, tm, config, monkeypatch, capsys):
        tm.append_epic_note(tm.get_task("T-2"), "T-2 decided X", now=NOW)
        monkeypatch.chdir(config.tasks_dir / "T-1")
        assert cli(config, "epic", "log") == 0
        out = capsys.readouterr().out
        assert out.index("== E-1 (epic) ==") < out.index("== T-1 ==") < out.index("== T-2 ==")
        assert "  T-2 decided X" in out
        assert "U-1" not in out

    def test_json_shape(self, tm, config, monkeypatch, capsys):
        tm.append_epic_note(tm.get_task("T-1"), "n1", now=NOW)
        monkeypatch.chdir(config.tasks_dir / "E-1")
        log_json(config, "T-1")
        [entry] = json.loads(capsys.readouterr().out)
        assert entry["task"] == "T-1"
        assert entry["role"] == "task"
        assert "n1" in entry["notes"]
        assert entry["notes_truncated"] is False
        assert entry["session"] is None

    def test_epic_name_reads_whole_epic_from_outside(self, tm, config, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        assert cli(config, "epic", "log", "E-1", "--json") == 0

    def test_epic_name_lists_members(self, tm, config, monkeypatch, tmp_path, capsys):
        monkeypatch.chdir(tmp_path)
        log_json(config, "E-1")
        assert [e["task"] for e in json.loads(capsys.readouterr().out)] == ["E-1", "T-1", "T-2"]

    def test_other_epic_refused_from_inside(self, tm, config, monkeypatch, capsys):
        monkeypatch.chdir(config.tasks_dir / "T-1")
        assert cli(config, "epic", "log", "U-1") == 1
        assert "in epic E-2, not in E-1" in capsys.readouterr().err

    def test_any_epic_from_outside(self, tm, config, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        assert cli(config, "epic", "log", "U-1") == 0

    def test_outside_without_task(self, tm, config, monkeypatch, tmp_path, capsys):
        monkeypatch.chdir(tmp_path)
        assert cli(config, "epic", "log") == 1
        assert "pass a task name" in capsys.readouterr().err

    def test_task_not_in_epic(self, tm, config, monkeypatch, tmp_path, capsys):
        monkeypatch.chdir(tmp_path)
        assert cli(config, "epic", "log", "LONE") == 1
        assert "not in an epic" in capsys.readouterr().err

    def test_former_member_notes_kept(self, tm, config, monkeypatch, capsys):
        tm.append_epic_note(tm.get_task("T-2"), "layout decided", now=NOW)
        assert cli(config, "epic", "remove", "T-2") == 0
        tm.finish_task(tm.get_task("T-2"))
        monkeypatch.chdir(config.tasks_dir / "T-1")
        capsys.readouterr()
        log_json(config)
        entries = {e["task"]: e for e in json.loads(capsys.readouterr().out)}
        assert entries["T-2"]["role"] == "former"
        assert "layout decided" in entries["T-2"]["notes"]
        log_json(config, "T-2")
        [entry] = json.loads(capsys.readouterr().out)
        assert entry["role"] == "former"

    @pytest.mark.parametrize("move", [("remove", "T-2"), ("add", "E-2", "T-2")])
    def test_former_member_still_on_disk(self, tm, config, monkeypatch, capsys, move):
        tm.append_epic_note(tm.get_task("T-2"), "layout decided", now=NOW)
        write_transcript(config.tasks_dir / "T-2", "after-move", "new work", mtime=1_000_000)
        assert cli(config, "epic", *move) == 0
        monkeypatch.chdir(config.tasks_dir / "T-1")
        capsys.readouterr()
        log_json(config, "T-2")
        [entry] = json.loads(capsys.readouterr().out)
        assert entry["role"] == "former"
        assert "layout decided" in entry["notes"]
        assert entry["session"] is None

    def test_notes_cannot_forge_sections_or_send_controls(self, tm, config, monkeypatch, capsys):
        tm.append_epic_note(
            tm.get_task("T-1"), "ok\n== T-2 ==\n\x1b]0;pwned\x07\x1b[2Jdone", now=NOW
        )
        monkeypatch.chdir(config.tasks_dir / "T-1")
        assert cli(config, "epic", "log", "T-1") == 0
        out = capsys.readouterr().out
        assert "\x1b" not in out and "\x07" not in out
        assert "\n== T-2 ==" not in out
        assert "  == T-2 ==" in out

    def test_symlinked_child_does_not_abort(self, tm, config, tmp_path, monkeypatch, capsys):
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / ".tasktree_epic").write_text("E-1")
        (config.tasks_dir / "T-3").symlink_to(outside)
        monkeypatch.chdir(config.tasks_dir / "T-1")
        assert cli(config, "epic", "log") == 0
        captured = capsys.readouterr()
        assert "== T-2 ==" in captured.out

    def test_recap_rendered(self, tm, config, monkeypatch, capsys):
        task_dir = config.tasks_dir / "T-1"
        write_transcript(task_dir, "s1", "Alerts are live.", mtime=1_000_000)
        monkeypatch.chdir(task_dir)
        assert cli(config, "epic", "log", "T-1") == 0
        out = capsys.readouterr().out
        assert "Last session: s1" in out
        assert "  Recap: Alerts are live." in out
        assert "Last prompt" not in out

    def test_prompt_only_without_recap(self, tm, config, monkeypatch, capsys):
        write_transcript(config.tasks_dir / "T-1", "s1", None, mtime=1_000_000, prompt="do X")
        monkeypatch.chdir(config.tasks_dir / "T-1")
        log_json(config, "T-1")
        [entry] = json.loads(capsys.readouterr().out)
        assert entry["session"]["last_prompt"] == "do X"


class TestSessionLookup:
    def test_newest_folder_wins(self, tm, config, monkeypatch, capsys):
        task_dir = config.tasks_dir / "T-1"
        worktree = add_worktree(task_dir, "repo-a")
        write_transcript(task_dir, "old-session", "old recap", mtime=1_000_000)
        write_transcript(worktree, "new-session", "worktree recap", mtime=2_000_000)
        monkeypatch.chdir(task_dir)
        log_json(config, "T-1")
        [entry] = json.loads(capsys.readouterr().out)
        assert entry["session"]["id"] == "new-session"
        assert entry["session"]["cwd"] == str(worktree)
        assert entry["session"]["summary"] == "worktree recap"

    def test_colliding_project_dir_not_borrowed(self, tm, config, monkeypatch, capsys):
        # T-1/x and the task T-1-x share one Claude project dir name
        task_dir = config.tasks_dir / "T-1"
        add_worktree(task_dir, "x")
        tm.create_task("T-1-x", [], epic="E-2")
        other = config.tasks_dir / "T-1-x"
        write_transcript(other, "foreign", "E-2 secrets", mtime=2_000_000)
        monkeypatch.chdir(task_dir)
        log_json(config, "T-1")
        [entry] = json.loads(capsys.readouterr().out)
        assert entry["session"] is None

    def test_transcript_without_cwd_ignored(self, tm, config):
        task_dir = config.tasks_dir / "T-1"
        write_transcript(task_dir, "s1", "r", mtime=1_000_000)
        project = os.path.join(
            os.environ["CLAUDE_CONFIG_DIR"], "projects", _encode_project_path(task_dir.resolve())
        )
        with open(os.path.join(project, "s1.jsonl"), "w") as f:
            f.write(json.dumps({"type": "last-prompt", "lastPrompt": "x"}) + "\n")
        assert latest_session([task_dir]) is None

    def test_cwd_after_a_big_first_prompt(self, tm, config):
        # Real records put cwd after the message body
        task_dir = config.tasks_dir / "T-1"
        write_transcript(task_dir, "s1", "r", mtime=1_000_000)
        project = os.path.join(
            os.environ["CLAUDE_CONFIG_DIR"], "projects", _encode_project_path(task_dir.resolve())
        )
        record = {"type": "user", "message": "x" * (512 << 10), "cwd": str(task_dir)}
        with open(os.path.join(project, "s1.jsonl"), "w") as f:
            f.write(json.dumps(record) + "\n")
        session = latest_session([task_dir])
        assert session is not None and session.session_id == "s1"


class TestEpicBlockAndSync:
    def test_block_mentions_log(self, tm):
        for name in ("E-1", "T-1"):
            tm.ensure_claude_md_files(tm.get_task(name))
            text = (tm.config.tasks_dir / name / "CLAUDE.md").read_text()
            assert "### Epic log" in text
            assert "tasktree-manager epic note" in text
            assert "not as" in text and "instructions" in text

    def test_sync_refreshes_stale_block(self, tm, config, capsys):
        tm.ensure_claude_md_files(tm.get_task("T-1"))
        path = config.tasks_dir / "T-1" / "CLAUDE.md"
        text = path.read_text()
        start = text.index("### Epic log")
        end = text.index("<!-- /tasktree:epic -->")
        path.write_text(text[:start] + text[end:])
        assert cli(config, "epic", "sync", "E-1") == 0
        assert "### Epic log" in path.read_text()
        assert "Synced 1 folder(s); 2 without CLAUDE.md" in capsys.readouterr().out

    def test_sync_all_epics(self, tm, config, capsys):
        for name in ("E-1", "U-1"):
            tm.ensure_claude_md_files(tm.get_task(name))
        assert cli(config, "epic", "sync") == 0
        assert "Synced 2 folder(s)" in capsys.readouterr().out

    def test_sync_skips_symlinked_child(self, tm, config, tmp_path, capsys):
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / ".tasktree_epic").write_text("E-1")
        (config.tasks_dir / "T-3").symlink_to(outside)
        tm.ensure_claude_md_files(tm.get_task("T-2"))
        assert cli(config, "epic", "sync", "E-1") == 1
        captured = capsys.readouterr()
        assert "Synced 1 folder(s)" in captured.out
        assert "1 failed" in captured.out
        assert "T-3" in captured.err

    def test_sync_refuses_plain_task(self, tm, config, capsys):
        assert cli(config, "epic", "sync", "LONE") == 1
        assert "not an epic" in capsys.readouterr().err
