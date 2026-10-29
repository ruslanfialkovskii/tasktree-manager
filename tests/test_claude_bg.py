"""Tests for Claude background sessions behind the `c` tab, the close key and the delete guard."""

import json
import subprocess
from pathlib import Path

import pytest

from tasktree_manager import app as app_module
from tasktree_manager.cli import run_cli
from tasktree_manager.services.agent_sessions import AgentSession, parse_agent_sessions
from tasktree_manager.services.claude_bg import (
    SESSION_ENV,
    BackgroundError,
    attach_command,
    background_sessions,
    end_sessions,
    folder_session,
    foreground_session,
    start_background,
)
from tasktree_manager.services.claude_sessions import SessionRef
from tasktree_manager.widgets.create_modal import ConfirmModal


def record(cwd, status="idle", kind="background", agent_id="0a1b2c3d", started=1, name="T"):
    """One `claude agents --json --all` row; only background rows carry a short id."""
    row = {
        "cwd": str(cwd),
        "kind": kind,
        "status": status,
        "sessionId": f"{agent_id}-full",
        "name": name,
        "startedAt": started,
    }
    if kind == "background":
        row["id"] = agent_id
    return row


def sessions(*rows):
    return parse_agent_sessions(json.dumps(list(rows)))


class TestParse:
    def test_background_fields(self, tmp_path):
        [session] = sessions(record(tmp_path, agent_id="d0063e53", started=42))

        assert (session.kind, session.agent_id, session.started_at) == (
            "background",
            "d0063e53",
            42,
        )


class TestFolderSession:
    def test_only_exact_folder_counts(self, tmp_path):
        found = sessions(record(tmp_path / "repo", agent_id="aaaa1111"))

        assert folder_session(found, tmp_path) is None
        assert folder_session(found, tmp_path / "repo").agent_id == "aaaa1111"

    def test_busy_session_beats_newer_finished_one(self, tmp_path):
        found = sessions(
            record(tmp_path, status="done", agent_id="aaaa1111", started=9),
            record(tmp_path, status="busy", agent_id="bbbb2222", started=1),
        )

        assert folder_session(found, tmp_path).agent_id == "bbbb2222"

    def test_newest_finished_session_otherwise(self, tmp_path):
        found = sessions(
            record(tmp_path, status="done", agent_id="aaaa1111", started=1),
            record(tmp_path, status="done", agent_id="bbbb2222", started=9),
        )

        assert folder_session(found, tmp_path).agent_id == "bbbb2222"

    def test_interactive_session_is_not_background(self, tmp_path):
        found = sessions(record(tmp_path, kind="interactive"))

        assert folder_session(found, tmp_path) is None
        assert foreground_session(found, tmp_path) is not None

    def test_task_sessions_include_worktrees(self, tmp_path):
        found = sessions(
            record(tmp_path, agent_id="aaaa1111"),
            record(tmp_path / "repo", agent_id="bbbb2222"),
            record(tmp_path.parent / "other", agent_id="cccc3333"),
        )

        ids = {s.agent_id for s in background_sessions(found, tmp_path)}
        assert ids == {"aaaa1111", "bbbb2222"}


class FakeRun:
    def __init__(self, returncode=0, stdout="  claude attach 0a1b2c3d    open\n", stderr=""):
        self.calls = []
        self.result = (returncode, stdout, stderr)

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, *self.result)


class TestStartBackground:
    def test_new_session_is_named_and_gets_no_prompt(self, tmp_path, monkeypatch):
        fake = FakeRun()
        monkeypatch.setattr(subprocess, "run", fake)

        assert start_background("claude", tmp_path, "T-1") == "0a1b2c3d"
        [(argv, kwargs)] = fake.calls
        assert argv == ["claude", "--bg", "-n", "T-1"]
        assert kwargs["cwd"] == tmp_path

    def test_resume_takes_no_other_flag(self, tmp_path, monkeypatch):
        # Any extra flag would start a copy under a new session ID
        fake = FakeRun()
        monkeypatch.setattr(subprocess, "run", fake)

        start_background("claude", tmp_path, "T-1", resume_id="abc-123")
        assert fake.calls[0][0] == ["claude", "--bg", "--resume", "abc-123"]

    def test_launching_session_identity_is_dropped(self, tmp_path, monkeypatch):
        for name in SESSION_ENV:
            monkeypatch.setenv(name, "1")
        monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
        fake = FakeRun()
        monkeypatch.setattr(subprocess, "run", fake)

        start_background("claude", tmp_path, "T-1")
        env = fake.calls[0][1]["env"]
        assert not set(SESSION_ENV) & set(env)
        assert env["CLAUDE_CODE_USE_BEDROCK"] == "1"

    def test_failure_reports_the_cli_reason(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run", FakeRun(returncode=1, stdout="", stderr="Workspace not trusted\n")
        )

        with pytest.raises(BackgroundError, match="Workspace not trusted"):
            start_background("claude", tmp_path, "T-1")

    def test_missing_cli(self, tmp_path):
        with pytest.raises(BackgroundError, match="could not run"):
            start_background(str(tmp_path / "no-claude"), tmp_path, "T-1")


def test_attach_command_quotes_the_path():
    assert (
        attach_command("/opt/my tools/claude", "0a1b2c3d")
        == "'/opt/my tools/claude' attach 0a1b2c3d"
    )


class TestEndSessions:
    def test_stops_then_removes(self, fake_claude_cli, tmp_path):
        found = sessions(record(tmp_path, agent_id="aaaa1111"))

        assert end_sessions(str(fake_claude_cli / "claude"), found) == []
        assert (fake_claude_cli / "control.log").read_text() == "stop aaaa1111\nrm aaaa1111\n"

    def test_failed_remove_is_reported(self, fake_claude_cli, tmp_path):
        (fake_claude_cli / "rm-fails").touch()
        found = sessions(record(tmp_path, agent_id="aaaa1111"))

        assert end_sessions(str(fake_claude_cli / "claude"), found) == ["aaaa1111"]


@pytest.fixture
def bg_task(app, task_manager, sample_repo, fake_claude_cli, monkeypatch):
    """A task, the app on the fake claude CLI, and recorders for tabs and notices."""
    _, branch = sample_repo
    task = task_manager.create_task("BG-TASK", ["sample-repo"], branch)
    app.config.claude_path = str(fake_claude_cli / "claude")
    app.current_task = task
    monkeypatch.delenv("ZELLIJ_SESSION_NAME", raising=False)
    monkeypatch.setattr(app, "_prepare_claude_session", lambda task: None)
    monkeypatch.setattr(app_module, "latest_session", lambda folders: None)
    tabs, notices = [], []
    monkeypatch.setattr(app, "_open_terminal_tab", lambda *a, **k: tabs.append((a, k)))
    monkeypatch.setattr(app, "notify", lambda msg, **kw: notices.append((msg, kw)))
    return task, tabs, notices


def agents(stub_dir, *rows):
    (stub_dir / "agents.json").write_text(json.dumps(list(rows)))


async def run_claude_key(app, task, worktree=None):
    async with app.run_test() as pilot:
        await pilot.pause()
        app._open_claude_resume_worker(task, worktree)
        await app.workers.wait_for_complete()
        await pilot.pause()


class TestClaudeKey:
    async def test_new_session_starts_in_background_and_tab_attaches(
        self, app, bg_task, fake_claude_cli
    ):
        task, tabs, notices = bg_task
        agents(fake_claude_cli)

        await run_claude_key(app, task)

        assert (fake_claude_cli / "dispatch.log").read_text() == f"{task.path}|--bg -n BG-TASK\n"
        [(args, kwargs)] = tabs
        assert args == (task.path,)
        assert kwargs["command"] == f"{app.config.claude_path} attach 0a1b2c3d"
        assert kwargs["kind"] == "claude"
        assert "Started a Claude session in the background" in kwargs["notice"]

    async def test_running_session_is_attached_without_starting_one(
        self, app, bg_task, fake_claude_cli
    ):
        task, tabs, _ = bg_task
        agents(fake_claude_cli, record(task.path, status="busy", agent_id="feed0001"))

        await run_claude_key(app, task)

        assert not (fake_claude_cli / "dispatch.log").exists()
        assert tabs[0][1]["command"].endswith("attach feed0001")

    async def test_last_transcript_is_resumed(self, app, bg_task, fake_claude_cli, monkeypatch):
        task, tabs, _ = bg_task
        agents(fake_claude_cli)
        ref = SessionRef(path=Path("/x/abc-123.jsonl"), cwd=task.path, mtime_ns=1)
        monkeypatch.setattr(app_module, "latest_session", lambda folders: ref)

        await run_claude_key(app, task)

        assert (
            fake_claude_cli / "dispatch.log"
        ).read_text() == f"{task.path}|--bg --resume abc-123\n"
        assert "Resumed the last Claude session" in tabs[0][1]["notice"]

    async def test_claude_open_in_another_terminal_is_left_alone(
        self, app, bg_task, fake_claude_cli
    ):
        task, tabs, notices = bg_task
        agents(fake_claude_cli, record(task.path, kind="interactive"))

        await run_claude_key(app, task)

        assert tabs == [] and not (fake_claude_cli / "dispatch.log").exists()
        assert notices == [
            ("Claude is already open in 'BG-TASK' in another terminal", {"severity": "warning"})
        ]

    async def test_focused_worktree_agent_opens_in_its_folder(self, app, bg_task, fake_claude_cli):
        task, tabs, _ = bg_task
        worktree = task.worktrees[0]
        agents(fake_claude_cli, record(worktree.path, status="busy", agent_id="feed0002"))

        await run_claude_key(app, task, worktree)

        [(args, kwargs)] = tabs
        assert args == (worktree.path,)
        assert kwargs["command"].endswith("attach feed0002")

    async def test_open_zellij_tab_is_reused_without_asking_claude(
        self, app, bg_task, fake_claude_cli, monkeypatch
    ):
        task, tabs, _ = bg_task
        monkeypatch.setenv("ZELLIJ_SESSION_NAME", "tasktree")
        monkeypatch.setattr(app, "_zellij_tab_names", lambda: ["Tab #1", "BG-TASK · claude"])

        await run_claude_key(app, task)

        # No agents.json: asking claude would have failed over to a plain tab
        assert tabs == [((task.path,), {"kind": "claude"})]

    async def test_unavailable_background_falls_back_to_plain_tab(
        self, app, bg_task, fake_claude_cli
    ):
        task, tabs, notices = bg_task  # no agents.json: `claude agents` exits 1

        await run_claude_key(app, task)

        assert notices[0][0].startswith("No background Claude session")
        assert tabs[0][1]["command"] == app.config.claude_path

    async def test_background_off_runs_claude_in_the_tab(self, app, bg_task, fake_claude_cli):
        task, tabs, notices = bg_task
        app.config.claude_background = False
        agents(fake_claude_cli)

        await run_claude_key(app, task)

        assert not (fake_claude_cli / "dispatch.log").exists()
        assert tabs[0][1]["command"] == app.config.claude_path
        assert notices == []

    async def test_timed_out_start_attaches_to_the_session_it_made(
        self, app, bg_task, fake_claude_cli, monkeypatch
    ):
        task, tabs, _ = bg_task
        agents(fake_claude_cli)

        def slow_start(*args):
            # The CLI gave up waiting, but the session came up
            agents(fake_claude_cli, record(task.path, status="busy", agent_id="feed0003"))
            raise app_module.BackgroundError("claude --bg timed out")

        monkeypatch.setattr(app_module, "start_background", slow_start)

        await run_claude_key(app, task)

        [(_, kwargs)] = tabs
        assert kwargs["command"].endswith("attach feed0003")


def pane(tab_id, tab_name, command, is_plugin=False):
    """One `zellij action list-panes --all --json` row."""
    return {
        "tab_id": tab_id,
        "tab_name": tab_name,
        "terminal_command": command,
        "is_plugin": is_plugin,
    }


class FakeZellij:
    def __init__(self, panes=None, list_rc=0, close_rc=0):
        self.panes = (
            [
                pane(0, "Tab #1", None),
                pane(0, "Tab #1", None, is_plugin=True),
                pane(3, "BG-TASK · claude", "sh -c claude attach 0a1b2c3d"),
            ]
            if panes is None
            else panes
        )
        self.list_rc, self.close_rc, self.calls = list_rc, close_rc, []

    def __call__(self, argv):
        self.calls.append(argv)
        if argv[1:3] == ["action", "list-panes"]:
            stdout = json.dumps(self.panes)
            return subprocess.CompletedProcess(argv, self.list_rc, stdout=stdout, stderr="")
        return subprocess.CompletedProcess(argv, self.close_rc, stdout="", stderr="")


class TestCloseClaudeTab:
    async def _close(self, app, folder, fake, monkeypatch):
        monkeypatch.setattr(app, "_run_zellij", fake)
        async with app.run_test() as pilot:
            await pilot.pause()
            app._close_claude_tab_worker(folder)
            await app.workers.wait_for_complete()
            await pilot.pause()

    async def test_attach_tab_is_closed_by_id(self, app, bg_task, monkeypatch):
        task, _, notices = bg_task
        fake = FakeZellij()

        await self._close(app, task.path, fake, monkeypatch)

        assert fake.calls[-1] == [app.config.zellij_path, "action", "close-tab-by-id", "3"]
        assert notices == [
            ("Closed 'BG-TASK · claude'; Claude keeps running in the background", {})
        ]

    async def test_tab_running_claude_itself_stays_open(self, app, bg_task, monkeypatch):
        # e.g. claude_background = false, even with a finished background session around
        task, _, notices = bg_task
        fake = FakeZellij(panes=[pane(3, "BG-TASK · claude", "sh -c claude -r")])

        await self._close(app, task.path, fake, monkeypatch)

        assert all(call[2] != "close-tab-by-id" for call in fake.calls)
        assert "closing it would stop Claude" in notices[0][0]

    async def test_missing_tab(self, app, bg_task, monkeypatch):
        task, _, notices = bg_task
        fake = FakeZellij(panes=[pane(0, "Tab #1", None)])

        await self._close(app, task.path, fake, monkeypatch)

        assert notices == [("No open tab 'BG-TASK · claude'", {"severity": "warning"})]

    async def test_failed_listing_is_not_reported_as_missing_tab(self, app, bg_task, monkeypatch):
        task, _, notices = bg_task
        fake = FakeZellij(list_rc=1)

        await self._close(app, task.path, fake, monkeypatch)

        assert notices == [("Could not list the zellij panes", {"severity": "warning"})]

    def test_key_needs_zellij(self, app, bg_task, monkeypatch):
        _, _, notices = bg_task
        closed = []
        monkeypatch.setattr(app, "_close_claude_tab_worker", closed.append)

        app.action_close_claude_tab()

        assert closed == []
        assert notices[0][1] == {"severity": "warning"}


class TestFinishedTurnNotice:
    async def _finish_turn(self, app, task, tabs, monkeypatch):
        monkeypatch.setenv("ZELLIJ_SESSION_NAME", "tasktree")
        monkeypatch.setattr(app, "_zellij_tab_names", lambda: tabs)
        # The recap worker restarts on every poll; only the notice is under test
        app.config.claude_recap = False
        status_file = task.path / ".claude_status"
        async with app.run_test() as pilot:
            await pilot.pause()
            status_file.write_text(json.dumps({"status": "running"}))
            app._poll_claude_statuses()
            status_file.write_text(json.dumps({"status": "waiting"}))
            app._poll_claude_statuses()
            await app.workers.wait_for_complete()
            await pilot.pause()

    async def test_waiting_task_without_tab_is_announced(self, app, bg_task, monkeypatch):
        task, _, notices = bg_task
        await self._finish_turn(app, task, ["Tab #1"], monkeypatch)

        assert ("Claude is waiting in 'BG-TASK' (tab closed): press c to open it", {}) in notices

    async def test_open_tab_needs_no_notice(self, app, bg_task, monkeypatch):
        task, _, notices = bg_task
        await self._finish_turn(app, task, ["BG-TASK · claude"], monkeypatch)

        assert not any("waiting in" in msg for msg, _ in notices)


class TestDeleteGuard:
    async def test_busy_session_is_confirmed_first(self, app, bg_task):
        task, _, _ = bg_task
        working = AgentSession(directory=task.path, status="working", agent_id="feed0001")
        async with app.run_test() as pilot:
            await pilot.pause()
            app._show_delete_task_dialog(task, app_module.TaskSafetyReport(), [working])
            await pilot.pause()

            modal = app.screen_stack[-1]
            assert isinstance(modal, ConfirmModal)
            assert modal.title_text == "Claude Still Running"
            assert "feed0001" in modal.message_text

    async def test_delete_stops_and_removes_task_sessions(self, app, bg_task, fake_claude_cli):
        task, _, _ = bg_task
        agents(
            fake_claude_cli,
            record(task.path, agent_id="aaaa1111"),
            record(task.worktrees[0].path, status="busy", agent_id="bbbb2222"),
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            app._finish_task(task, force=True)
            await app.workers.wait_for_complete()
            await pilot.pause()

        log = (fake_claude_cli / "control.log").read_text().splitlines()
        assert sorted(log) == ["rm aaaa1111", "rm bbbb2222", "stop aaaa1111", "stop bbbb2222"]
        assert not task.path.exists()

    async def test_session_that_will_not_stop_keeps_the_task(self, app, bg_task, fake_claude_cli):
        task, _, notices = bg_task
        agents(fake_claude_cli, record(task.path, status="busy", agent_id="aaaa1111"))
        (fake_claude_cli / "rm-fails").touch()
        async with app.run_test() as pilot:
            await pilot.pause()
            app._finish_task(task, force=True)
            await app.workers.wait_for_complete()
            await pilot.pause()

        assert task.path.exists()
        assert any("could not stop Claude session(s) aaaa1111" in msg for msg, _ in notices)


class TestCliDeleteGuard:
    @pytest.fixture
    def cli_task(self, config, task_manager, repo_with_origin, fake_claude_cli):
        # A pushed, merged branch: only the Claude session can block the delete
        run_cli(
            ["create", "CLI-BG", "--repos", "repo-remote", "--base", repo_with_origin],
            config=config,
        )
        config.claude_path = str(fake_claude_cli / "claude")
        return task_manager.get_task("CLI-BG")

    def test_working_session_refuses_without_force(self, config, cli_task, fake_claude_cli, capsys):
        agents(fake_claude_cli, record(cli_task.path, status="busy", agent_id="feed0001"))

        assert run_cli(["delete", "CLI-BG"], config=config) == 1
        assert (
            "Claude is still active (working or waiting for you) in task CLI-BG: feed0001"
            in capsys.readouterr().err
        )
        assert cli_task.path.exists()
        assert not (fake_claude_cli / "control.log").exists()

    def test_force_stops_the_session(self, config, cli_task, fake_claude_cli):
        agents(fake_claude_cli, record(cli_task.path, status="busy", agent_id="feed0001"))

        assert run_cli(["delete", "CLI-BG", "--force"], config=config) == 0
        assert (fake_claude_cli / "control.log").read_text() == "stop feed0001\nrm feed0001\n"
        assert not cli_task.path.exists()

    def test_finished_session_is_removed_quietly(self, config, cli_task, fake_claude_cli):
        agents(fake_claude_cli, record(cli_task.path, status="done", agent_id="feed0001"))

        assert run_cli(["delete", "CLI-BG"], config=config) == 0
        assert "rm feed0001" in (fake_claude_cli / "control.log").read_text()

    def test_session_that_will_not_stop_keeps_the_task(
        self, config, cli_task, fake_claude_cli, capsys
    ):
        agents(fake_claude_cli, record(cli_task.path, status="done", agent_id="feed0001"))
        (fake_claude_cli / "rm-fails").touch()

        assert run_cli(["delete", "CLI-BG"], config=config) == 1
        assert "could not stop Claude session feed0001" in capsys.readouterr().err
        assert cli_task.path.exists()

    def test_finish_refuses_busy_claude_before_pushing(
        self, config, cli_task, fake_claude_cli, monkeypatch, capsys
    ):
        agents(fake_claude_cli, record(cli_task.path, status="busy", agent_id="feed0001"))
        pushed = []
        monkeypatch.setattr(
            "tasktree_manager.services.task_manager.TaskManager.push_all_branches",
            lambda self, task: pushed.append(task) or ([], []),
        )

        assert run_cli(["finish", "CLI-BG", "--push"], config=config) == 1
        assert pushed == []
        assert "Claude is still active" in capsys.readouterr().err
