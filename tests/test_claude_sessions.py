"""Tests for reading Claude Code session recaps from transcripts."""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tasktree_manager.services.claude_sessions import (
    TAIL_WINDOW,
    format_clock,
    format_duration,
    read_claude_recap,
    strip_recap_suffix,
    transcript_key,
)

TURN = {
    "type": "system",
    "subtype": "turn_duration",
    "durationMs": 45857,
    "timestamp": "2026-09-11T14:27:13.422Z",
    "slug": "lets-do-lively-tide",
}
RECAP = {
    "type": "system",
    "subtype": "away_summary",
    "content": "Fulfilling ACCESS2-7180, RBAC edits sit unstaged. (disable recaps in /config)",
    "timestamp": "2026-09-11T14:30:22.323Z",
}
PROMPT = {"type": "last-prompt", "lastPrompt": "is it   a good\napproach?"}
TITLE = {"type": "custom-title", "customTitle": "access-m2"}
FOLDER = Path("/Users/x/wtasks/TASK-1")


@pytest.fixture
def project_dir(tmp_path, monkeypatch):
    """Claude config dir with an empty project dir for FOLDER."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    project = tmp_path / "cfg" / "projects" / "-Users-x-wtasks-TASK-1"
    project.mkdir(parents=True)
    return project


def _write(path: Path, records: list[dict], tail: bytes = b"") -> None:
    data = b"".join(json.dumps(r).encode() + b"\n" for r in records)
    path.write_bytes(data + tail)


def _read(folder: Path):
    """Pick the newest transcript for a folder and read it, as the app does."""
    key = transcript_key(folder)
    return read_claude_recap(key[0]) if key else None


class TestReadClaudeRecap:
    def test_recap_present(self, project_dir):
        _write(project_dir / "s1.jsonl", [PROMPT, TURN, TITLE, RECAP])

        recap = _read(FOLDER)

        assert recap is not None
        assert recap.title == "access-m2"
        assert recap.summary == "Fulfilling ACCESS2-7180, RBAC edits sit unstaged."
        assert recap.duration_ms == 45857
        assert recap.finished_at == datetime(2026, 9, 11, 14, 27, 13, 422000, tzinfo=timezone.utc)
        assert recap.last_prompt == "is it a good approach?"

    def test_no_recap_keeps_last_prompt(self, project_dir):
        _write(project_dir / "s1.jsonl", [TURN, PROMPT])

        recap = _read(FOLDER)

        assert recap is not None
        assert recap.summary is None
        assert recap.last_prompt == "is it a good approach?"
        assert recap.duration_ms == 45857

    def test_recap_older_than_latest_turn_is_dropped(self, project_dir):
        """A recap written before a newer turn describes a state that moved on."""
        _write(project_dir / "s1.jsonl", [RECAP, TURN, PROMPT])

        recap = _read(FOLDER)

        assert recap is not None
        assert recap.summary is None
        assert recap.last_prompt is not None

    def test_truncated_last_line_is_skipped(self, project_dir):
        partial = b'{"type":"system","subtype":"away_summary","content":"half writ'
        _write(project_dir / "s1.jsonl", [TURN, RECAP], tail=partial)

        recap = _read(FOLDER)

        assert recap is not None
        assert recap.summary.startswith("Fulfilling ACCESS2-7180")

    def test_huge_tool_result_line_inside_window(self, project_dir):
        blob = {"type": "user", "toolUseResult": "x" * 200_000}
        _write(project_dir / "s1.jsonl", [TURN, blob, RECAP])

        recap = _read(FOLDER)

        assert recap is not None
        assert recap.summary is not None
        assert recap.duration_ms == 45857

    def test_retries_with_bigger_window(self, project_dir):
        """A turn record pushed past the 1 MiB window is still found."""
        blob = {"type": "user", "toolUseResult": "x" * (TAIL_WINDOW + 1000)}
        _write(project_dir / "s1.jsonl", [PROMPT, TURN, blob])

        recap = _read(FOLDER)

        assert recap is not None
        assert recap.duration_ms == 45857
        assert recap.last_prompt is not None

    def test_missing_project_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
        assert _read(FOLDER) is None

    def test_transcript_without_useful_records(self, project_dir):
        _write(project_dir / "s1.jsonl", [{"type": "user", "message": "hi"}])
        assert _read(FOLDER) is None

    def test_bad_values_are_ignored(self, project_dir):
        bad_turn = {"type": "system", "subtype": "turn_duration", "durationMs": "45s"}
        _write(
            project_dir / "s1.jsonl",
            [bad_turn, {"type": "custom-title", "customTitle": " "}, PROMPT],
        )

        recap = _read(FOLDER)

        assert recap is not None
        assert recap.duration_ms is None
        assert recap.finished_at is None
        assert recap.title == "s1"  # falls back to the transcript stem

    @pytest.mark.parametrize(
        ("records", "expected"),
        [
            (
                [
                    TURN,
                    {"type": "ai-title", "aiTitle": "AI name"},
                    {"type": "agent-name", "agentName": "ag"},
                ],
                "AI name",
            ),
            ([TURN, {"type": "agent-name", "agentName": "ag"}], "ag"),
            ([TURN], "lets-do-lively-tide"),
            ([TURN, TITLE, {"type": "ai-title", "aiTitle": "AI name"}], "access-m2"),
        ],
    )
    def test_title_precedence(self, project_dir, records, expected):
        _write(project_dir / "s1.jsonl", records)
        recap = _read(FOLDER)
        assert recap is not None
        assert recap.title == expected

    def test_legacy_project_dir_is_found(self, tmp_path, monkeypatch):
        """Dirs created by an older CLI (underscore kept) still resolve."""
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
        legacy = tmp_path / "cfg" / "projects" / "-Users-x-my_dir"
        legacy.mkdir(parents=True)
        _write(legacy / "s1.jsonl", [TURN])

        recap = _read(Path("/Users/x/my_dir"))

        assert recap is not None
        assert recap.duration_ms == 45857


class TestTranscriptSelection:
    def test_newest_jsonl_wins_and_noise_is_ignored(self, project_dir):
        old = project_dir / "old.jsonl"
        new = project_dir / "new.jsonl"
        _write(old, [TURN])
        _write(new, [TURN])
        os.utime(old, ns=(1_000_000_000, 1_000_000_000))
        os.utime(new, ns=(2_000_000_000, 2_000_000_000))
        # Sidecar dir and stale index must not be picked
        (project_dir / "abc").mkdir()
        _write(project_dir / "abc" / "agent.jsonl", [TURN])
        (project_dir / "sessions-index.json").write_text("{}")

        assert transcript_key(FOLDER)[0] == new

    def test_transcript_key_tracks_growth(self, project_dir):
        path = project_dir / "s1.jsonl"
        _write(path, [TURN])
        before = transcript_key(FOLDER)
        with path.open("ab") as fh:
            fh.write(json.dumps(RECAP).encode() + b"\n")
        after = transcript_key(FOLDER)

        assert before is not None and after is not None
        assert before[0] == after[0] == path
        assert after[2] > before[2]

    def test_no_transcripts(self, project_dir):
        assert transcript_key(FOLDER) is None


class TestFormatting:
    @pytest.mark.parametrize(
        ("ms", "expected"),
        [
            (0, "0s"),
            (45857, "45s"),
            (192_000, "3m 12s"),
            (3_600_000, "60m 0s"),
            (683_042_555, ">1h"),
        ],
    )
    def test_format_duration(self, ms, expected):
        assert format_duration(ms) == expected

    def test_format_clock(self):
        dt = datetime(2026, 9, 11, 14, 27, tzinfo=timezone.utc)
        assert format_clock(dt, tz=timezone.utc) == "2:27 PM"

    def test_strip_recap_suffix(self):
        assert strip_recap_suffix("Done. (disable recaps in /config)") == "Done."
        assert strip_recap_suffix("  Done.  ") == "Done."


class TestTerminalSafety:
    def test_control_characters_are_stripped(self, project_dir):
        hostile = {
            "type": "system",
            "subtype": "away_summary",
            "content": "Done\x1b]52;c;ZXZpbA==\x07 with\x00 it\r\n(disable recaps in /config)",
        }
        title = {"type": "custom-title", "customTitle": "acc\x1b[31mess\x9b"}
        _write(project_dir / "s1.jsonl", [PROMPT, TURN, title, hostile])

        recap = _read(FOLDER)

        assert recap is not None
        assert recap.summary == "Done]52;c;ZXZpbA== with it"
        assert recap.title == "acc[31mess"
        for text in (recap.summary, recap.title, recap.last_prompt):
            assert not re.search(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", text)
