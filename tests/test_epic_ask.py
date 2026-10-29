"""Tests for `epic ask`: scope, live sessions and the read-only copy command."""

import io
import json
import os
import subprocess
from pathlib import Path

import pytest

from tasktree_manager.cli import run_cli
from tasktree_manager.services.agent_sessions import AgentSession, parse_agent_sessions
from tasktree_manager.services.claude_hooks import _encode_project_path
from tasktree_manager.services.claude_sessions import find_session
from tasktree_manager.services.epic_ask import (
    ASK_MAX_TURNS,
    ASK_QUESTION_MAX_BYTES,
    ASK_TIMEOUT,
    LOOP_GUARD_ENV,
)

T2 = "22222222-2222-4222-8222-222222222222"
OLDER = "33333333-3333-4333-8333-333333333333"
WT = "44444444-4444-4444-8444-444444444444"
EPIC = "55555555-5555-4555-8555-555555555555"
U1 = "66666666-6666-4666-8666-666666666666"
MINE = "77777777-7777-4777-8777-777777777777"
ANSWER = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "result": "We chose layout A.\n\x1b[2Jdone",
    "usage": {"input_tokens": 3, "output_tokens": 9},
}


@pytest.fixture(autouse=True)
def claude_config(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-config"))
    monkeypatch.delenv(LOOP_GUARD_ENV, raising=False)


@pytest.fixture
def tm(task_manager):
    task_manager.create_task("E-1", [], kind="epic")
    task_manager.create_task("E-2", [], kind="epic")
    task_manager.create_task("T-1", [], epic="E-1")
    task_manager.create_task("T-2", [], epic="E-1")
    task_manager.create_task("U-1", [], epic="E-2")
    task_manager.create_task("LONE", [])
    return task_manager


def project_dir(folder):
    return os.path.join(
        os.environ["CLAUDE_CONFIG_DIR"], "projects", _encode_project_path(folder.resolve())
    )


def write_transcript(folder, session_id, mtime=1_000_000, cwd=None):
    os.makedirs(project_dir(folder), exist_ok=True)
    path = os.path.join(project_dir(folder), f"{session_id}.jsonl")
    with open(path, "w") as f:
        f.write(json.dumps({"type": "user", "cwd": str(cwd or folder)}) + "\n")
    os.utime(path, (mtime, mtime))


class FakeClaude:
    """Records `claude -p` calls and answers with canned output."""

    def __init__(self, stdout=None, returncode=0, raises=None, stderr=""):
        self.calls = []
        self.stdout = json.dumps(ANSWER) if stdout is None else stdout
        self.returncode = returncode
        self.raises = raises
        self.stderr = stderr

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if self.raises:
            raise self.raises
        return subprocess.CompletedProcess(command, self.returncode, self.stdout, self.stderr)


@pytest.fixture
def claude(monkeypatch):
    fake = FakeClaude()
    monkeypatch.setattr("tasktree_manager.services.epic_ask.subprocess.run", fake)
    return fake


@pytest.fixture
def live(monkeypatch):
    """The sessions `claude agents --json` reports; None = unavailable."""
    state = {"sessions": []}
    monkeypatch.setattr("tasktree_manager.cli.list_agent_sessions", lambda _path: state["sessions"])
    return state


def ask(config, *argv):
    return run_cli(["epic", "ask", *argv], config=config)


def flag(command, name):
    return command[command.index(name) + 1]


@pytest.fixture
def in_t1(config, monkeypatch, tm):
    write_transcript(config.tasks_dir / "T-2", T2)
    monkeypatch.chdir(config.tasks_dir / "T-1")


class TestCommand:
    def test_read_only_fork(self, tm, config, in_t1, claude, live, capsys):
        assert ask(config, "T-2", "which layout?") == 0
        [(command, kwargs)] = claude.calls
        assert command[:4] == ["claude", "-p", "--resume", T2]
        for name in (
            "--fork-session",
            "--no-session-persistence",
            "--strict-mcp-config",
            "--disable-slash-commands",
        ):
            assert name in command
        assert flag(command, "--tools") == "Read,Grep,Glob"
        assert flag(command, "--max-turns") == str(ASK_MAX_TURNS)
        assert flag(command, "--name") == "epic-ask-T-2"
        assert "--allowedTools" not in command
        settings = json.loads(flag(command, "--settings"))
        assert settings["disableAllHooks"] is True
        assert "Read(~/.ssh/**)" in settings["permissions"]["deny"]
        assert "Read(//**/.env)" in settings["permissions"]["deny"]
        projects = Path(os.environ["CLAUDE_CONFIG_DIR"]).absolute() / "projects"
        assert f"Read(/{projects}/**)" in settings["permissions"]["deny"]
        assert "--no-chrome" in command
        prompt = command[-1]
        assert "task T-1 in epic E-1" in prompt
        assert prompt.endswith("<question>\nwhich layout?\n</question>")
        assert kwargs["cwd"] == config.tasks_dir / "T-2"
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["timeout"] == ASK_TIMEOUT
        out = capsys.readouterr().out
        # Indented like notes, so an answer cannot forge a "== task ==" header
        assert "  We chose layout A." in out.splitlines()
        assert "\x1b" not in out

    def test_env_drops_asking_session_identity(self, tm, config, in_t1, claude, live, monkeypatch):
        for name in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_PID"):
            monkeypatch.setenv(name, "secret")
        monkeypatch.setenv("CLAUDE_CONFIG_DIR_EXTRA", "kept")
        assert ask(config, "T-2", "q") == 0
        env = claude.calls[0][1]["env"]
        assert env[LOOP_GUARD_ENV] == "1"
        assert "CLAUDE_CODE_SESSION_ID" not in env
        assert "CLAUDE_CODE_MESSAGING_TOKEN" not in env
        assert "CLAUDE_PID" not in env
        assert env["CLAUDE_CONFIG_DIR_EXTRA"] == "kept"

    def test_json_output(self, tm, config, in_t1, claude, live, capsys):
        assert ask(config, "T-2", "q", "--json") == 0
        data = json.loads(capsys.readouterr().out)
        assert data["status"] == "answered"
        assert data["session_id"] == T2
        assert data["cwd"] == str(config.tasks_dir / "T-2")
        assert data["usage"]["output_tokens"] == 9

    def test_options_passed(self, tm, config, in_t1, claude, live):
        assert (
            ask(config, "T-2", "q", "--model", "sonnet", "--max-turns", "3", "--timeout", "90") == 0
        )
        command, kwargs = claude.calls[0]
        assert flag(command, "--model") == "sonnet"
        assert flag(command, "--max-turns") == "3"
        assert kwargs["timeout"] == 90

    @pytest.mark.parametrize(
        "option, value", [("--timeout", "0"), ("--timeout", "nan"), ("--max-turns", "0")]
    )
    def test_bad_limits_refused(self, tm, config, in_t1, claude, live, option, value):
        with pytest.raises(SystemExit):
            ask(config, "T-2", "q", option, value)
        assert claude.calls == []

    def test_question_from_stdin(self, tm, config, in_t1, claude, live, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO("multi\nline\n"))
        assert ask(config, "T-2", "-") == 0
        assert "<question>\nmulti\nline\n</question>" in claude.calls[0][0][-1]

    def test_verbose_array_output(self, tm, config, in_t1, live, monkeypatch, capsys):
        stdout = json.dumps([{"type": "system", "subtype": "init"}, ANSWER])
        monkeypatch.setattr(
            "tasktree_manager.services.epic_ask.subprocess.run", FakeClaude(stdout=stdout)
        )
        assert ask(config, "T-2", "q") == 0
        assert "We chose layout A." in capsys.readouterr().out


class TestSessions:
    def test_session_in_worktree(self, tm, config, claude, live, monkeypatch):
        worktree = config.tasks_dir / "T-2" / "repo-a"
        worktree.mkdir()
        (worktree / ".git").write_text("gitdir: /nowhere\n")
        write_transcript(worktree, WT)
        monkeypatch.chdir(config.tasks_dir / "T-1")
        assert ask(config, "T-2", "q") == 0
        command, kwargs = claude.calls[0]
        assert command[3] == WT
        assert kwargs["cwd"] == worktree

    def test_pick_session(self, tm, config, in_t1, claude, live):
        write_transcript(config.tasks_dir / "T-2", OLDER, mtime=500)
        assert ask(config, "T-2", "q", "--session", OLDER) == 0
        assert claude.calls[0][0][3] == OLDER

    def test_unknown_session(self, tm, config, in_t1, claude, live, capsys):
        assert ask(config, "T-2", "q", "--session", OLDER) == 1
        assert f"no session {OLDER}" in capsys.readouterr().err
        assert claude.calls == []

    def test_session_id_must_be_uuid(self, tm, config, in_t1, claude, live, capsys):
        assert ask(config, "T-2", "q", "--session=--tools=Bash") == 1
        assert "not a session id" in capsys.readouterr().err
        assert claude.calls == []

    def test_planted_transcript_name_refused(self, tm, config, claude, live, monkeypatch, capsys):
        write_transcript(config.tasks_dir / "T-2", "--tools=Bash")
        monkeypatch.chdir(config.tasks_dir / "T-1")
        assert ask(config, "T-2", "q") == 1
        assert "not a session transcript" in capsys.readouterr().err
        assert claude.calls == []

    def test_find_session_checks_recorded_cwd(self, tm, config):
        # T-2/x and the task T-2-x share one Claude project dir name
        tm.create_task("T-2-x", [], epic="E-2")
        other = config.tasks_dir / "T-2-x"
        write_transcript(other, U1)
        folder = config.tasks_dir / "T-2" / "x"
        assert find_session([folder], U1) is None
        assert find_session([other], U1) is not None

    def test_epic_folder_can_be_asked(self, tm, config, claude, live, monkeypatch):
        write_transcript(config.tasks_dir / "E-1", EPIC)
        monkeypatch.chdir(config.tasks_dir / "T-1")
        assert ask(config, "E-1", "q") == 0

    def test_from_outside_any_task(self, tm, config, claude, live, monkeypatch, tmp_path):
        write_transcript(config.tasks_dir / "U-1", U1)
        monkeypatch.chdir(tmp_path)
        assert ask(config, "U-1", "q") == 0
        assert "outside the task folders" in claude.calls[0][0][-1]


class TestRefusals:
    def test_other_epic(self, tm, config, in_t1, claude, live, capsys):
        write_transcript(config.tasks_dir / "U-1", U1)
        assert ask(config, "U-1", "q") == 1
        assert "in epic E-2, not in E-1" in capsys.readouterr().err
        assert claude.calls == []

    def test_caller_outside_any_epic(self, tm, config, claude, live, monkeypatch, capsys):
        write_transcript(config.tasks_dir / "T-2", T2)
        monkeypatch.chdir(config.tasks_dir / "LONE")
        assert ask(config, "T-2", "q") == 1
        assert "LONE is not in an epic" in capsys.readouterr().err
        assert claude.calls == []
        assert run_cli(["epic", "log", "T-2"], config=config) == 1

    def test_not_in_epic(self, tm, config, in_t1, claude, live, capsys):
        assert ask(config, "LONE", "q") == 1
        assert "not in an epic" in capsys.readouterr().err

    def test_own_task(self, tm, config, in_t1, claude, live, capsys):
        write_transcript(config.tasks_dir / "T-1", MINE)
        assert ask(config, "T-1", "q") == 1
        assert "your own task" in capsys.readouterr().err

    def test_no_session(self, tm, config, claude, live, monkeypatch, capsys):
        monkeypatch.chdir(config.tasks_dir / "T-1")
        assert ask(config, "T-2", "q") == 1
        assert "no Claude session" in capsys.readouterr().err

    def test_empty_question(self, tm, config, in_t1, claude, live, capsys):
        assert ask(config, "T-2", "  ") == 1
        assert "empty" in capsys.readouterr().err

    def test_oversized_question(self, tm, config, in_t1, claude, live, capsys):
        assert ask(config, "T-2", "x" * (ASK_QUESTION_MAX_BYTES + 1)) == 1
        assert "limit" in capsys.readouterr().err

    def test_loop_guard(self, tm, config, in_t1, claude, live, monkeypatch, capsys):
        monkeypatch.setenv(LOOP_GUARD_ENV, "1")
        assert ask(config, "T-2", "q") == 1
        assert "inside another epic ask" in capsys.readouterr().err
        assert claude.calls == []


class TestLiveSessions:
    def session(self, config, folder, name="t2-live"):
        return AgentSession(
            directory=(config.tasks_dir / folder).resolve(),
            status="ready",
            session_id=T2,
            name=name,
        )

    def test_live_session_exits_3(self, tm, config, in_t1, claude, live, capsys):
        live["sessions"] = [self.session(config, "T-2")]
        assert ask(config, "T-2", "q") == 3
        out = capsys.readouterr().out
        assert '"t2-live"' in out and "SendMessage" in out and "--fork" in out
        assert claude.calls == []

    def test_live_before_transcript(self, tm, config, claude, live, monkeypatch):
        # A running session in a subfolder, with no saved transcript to fork
        sub = config.tasks_dir / "T-2" / "docs"
        sub.mkdir()
        live["sessions"] = [self.session(config, "T-2/docs")]
        monkeypatch.chdir(config.tasks_dir / "T-1")
        assert ask(config, "T-2", "q") == 3

    def test_unnamed_session_shows_id(self, tm, config, in_t1, claude, live, capsys):
        live["sessions"] = [self.session(config, "T-2", name="")]
        assert ask(config, "T-2", "q") == 3
        assert f'"{T2}"' in capsys.readouterr().out

    def test_live_session_json(self, tm, config, in_t1, claude, live, capsys):
        live["sessions"] = [self.session(config, "T-2")]
        assert ask(config, "T-2", "q", "--json") == 3
        data = json.loads(capsys.readouterr().out)
        assert data["status"] == "running"
        assert data["sessions"][0]["name"] == "t2-live"

    def test_session_in_other_task_is_not_live(self, tm, config, in_t1, claude, live):
        # T-2 must not match T-2-x by prefix
        tm.create_task("T-2-x", [], epic="E-1")
        live["sessions"] = [self.session(config, "T-2-x")]
        assert ask(config, "T-2", "q") == 0

    def test_fork_skips_live_check(self, tm, config, in_t1, claude, live):
        live["sessions"] = [self.session(config, "T-2")]
        assert ask(config, "T-2", "q", "--fork") == 0
        assert len(claude.calls) == 1

    def test_agents_unavailable_still_asks(self, tm, config, in_t1, claude, live, capsys):
        live["sessions"] = None
        assert ask(config, "T-2", "q") == 0
        assert "could not list" in capsys.readouterr().err


class TestFailures:
    @pytest.mark.parametrize(
        "fake, message",
        [
            (FakeClaude(stdout="not json", returncode=1, stderr="boom\n"), "exited with 1: boom"),
            (FakeClaude(stdout="not json", returncode=1, stderr="  \n"), "exited with 1: not json"),
            (FakeClaude(stdout="[1, 2]"), "exited with 0"),
            (
                FakeClaude(stdout=json.dumps({"subtype": "error_max_turns", "is_error": True})),
                "turn limit",
            ),
            (
                FakeClaude(
                    stdout=json.dumps({"subtype": "success", "is_error": True, "result": "API 529"})
                ),
                "API 529",
            ),
            (FakeClaude(raises=subprocess.TimeoutExpired("claude", 5)), "no answer within"),
            (FakeClaude(raises=FileNotFoundError("claude")), "could not run"),
        ],
    )
    def test_errors_reported(self, tm, config, in_t1, live, monkeypatch, capsys, fake, message):
        monkeypatch.setattr("tasktree_manager.services.epic_ask.subprocess.run", fake)
        assert ask(config, "T-2", "q") == 1
        err = capsys.readouterr().err
        assert "T-2 did not answer" in err and message in err

    def test_error_text_sanitized_and_short(self, tm, config, in_t1, live, monkeypatch, capsys):
        fake = FakeClaude(stdout="", returncode=1, stderr="\x1b]0;pwned\x07" + "x" * 1000)
        monkeypatch.setattr("tasktree_manager.services.epic_ask.subprocess.run", fake)
        assert ask(config, "T-2", "q") == 1
        err = capsys.readouterr().err
        assert "\x1b" not in err and "\x07" not in err
        assert len(err) < 500


def test_ask_copies_not_listed_as_sessions():
    payload = json.dumps(
        [
            {"cwd": "/w/T-2", "status": "busy", "name": "epic-ask-T-2", "sessionId": "a"},
            {"cwd": "/w/T-2", "status": "idle", "name": "t2-work", "sessionId": "b"},
        ]
    )
    assert [s.name for s in parse_agent_sessions(payload)] == ["t2-work"]


def test_block_explains_asking(tm):
    tm.ensure_claude_md_files(tm.get_task("T-1"))
    text = Path(tm.config.tasks_dir / "T-1" / "CLAUDE.md").read_text()
    assert "### Asking another task" in text
    assert "tasktree-manager epic ask TASK" in text
    assert "SendMessage" in text and "--fork" in text
