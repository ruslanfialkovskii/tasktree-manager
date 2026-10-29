"""Tests for opening terminal tabs: zellij tabs inside zellij, Ghostty tabs elsewhere."""

import subprocess
import sys

import pytest

from tasktree_manager import app as app_module
from tasktree_manager.app import zellij_autostart_argv
from tasktree_manager.services.config import Config


class TestZellijTabArgv:
    def test_command_runs_in_shell_after_separator(self, app, config):
        path = config.tasks_dir / "TASK-1" / "repo-a"
        argv = app._zellij_tab_argv(path, "claude -r", "TASK-1/repo-a · claude")

        assert argv[:3] == [config.zellij_path, "action", "new-tab"]
        assert argv[argv.index("--name") + 1] == "TASK-1/repo-a · claude"
        assert argv[argv.index("--cwd") + 1] == str(path)
        # The tab closes with its command, so a tab found by name still runs it
        assert "--close-on-exit" in argv
        # Everything after "--" is the pane command, so "-r" never reaches zellij
        assert argv[argv.index("--") + 1 :] == ["sh", "-c", "claude -r"]

    def test_no_command_opens_plain_shell_tab(self, app, config):
        argv = app._zellij_tab_argv(config.tasks_dir / "TASK-1", None, "TASK-1 · shell")

        assert "--" not in argv
        assert "--close-on-exit" not in argv

    def test_tab_name_is_folder_below_tasks_dir_and_kind(self, app, config, tmp_path):
        assert (
            app._zellij_tab_name(config.tasks_dir / "T-1" / "api", "claude") == "T-1/api · claude"
        )
        assert app._zellij_tab_name(config.tasks_dir / "T-1", "shell") == "T-1 · shell"
        assert app._zellij_tab_name(tmp_path / "elsewhere", "editor") == "elsewhere · editor"


class TestTerminalTabRouting:
    def test_inside_zellij_opens_zellij_tab(self, app, config, monkeypatch):
        monkeypatch.setenv("ZELLIJ_SESSION_NAME", "tasktree")
        zellij, ghostty = [], []
        monkeypatch.setattr(app, "_open_zellij_tab_worker", lambda *a: zellij.append(a))
        monkeypatch.setattr(app, "_open_ghostty_tab_worker", lambda *a: ghostty.append(a))

        app._open_terminal_tab(config.tasks_dir / "TASK-1", "claude -r", "claude", "Opened")

        assert zellij == [(config.tasks_dir / "TASK-1", "claude -r", "claude", "Opened")]
        assert ghostty == []

    def test_outside_zellij_opens_ghostty_tab(self, app, config, monkeypatch):
        monkeypatch.delenv("ZELLIJ_SESSION_NAME", raising=False)
        zellij, ghostty, notices = [], [], []
        monkeypatch.setattr(app, "_open_zellij_tab_worker", lambda *a: zellij.append(a))
        monkeypatch.setattr(app, "_open_ghostty_tab_worker", lambda *a: ghostty.append(a))
        monkeypatch.setattr(app, "notify", lambda msg, **kw: notices.append(msg))

        app._open_terminal_tab(config.tasks_dir / "TASK-1", "claude -r", "claude", "Opened")

        assert zellij == []
        assert ghostty == [(f"cd '{config.tasks_dir / 'TASK-1'}' && clear && claude -r",)]
        assert notices == ["Opened"]


class FakeZellij:
    """Stands in for subprocess.run: answers query-tab-names, records the rest."""

    def __init__(self, tabs=(), query_rc=0, action_rc=0, stderr=""):
        self.tabs, self.query_rc, self.action_rc, self.stderr = tabs, query_rc, action_rc, stderr
        self.calls = []

    def __call__(self, argv, *args, **kwargs):
        self.calls.append(argv)
        if argv[1:3] == ["action", "query-tab-names"]:
            stdout = "".join(f"{tab}\n" for tab in self.tabs)
            return subprocess.CompletedProcess(argv, self.query_rc, stdout=stdout, stderr="")
        return subprocess.CompletedProcess(argv, self.action_rc, stdout="", stderr=self.stderr)


class TestZellijTabWorker:
    async def _run(self, app, monkeypatch, fake, path, command="claude -r", kind="claude"):
        notices = []
        async with app.run_test() as pilot:
            await pilot.pause()
            monkeypatch.setattr(subprocess, "run", fake)
            monkeypatch.setattr(app, "notify", lambda msg, **kw: notices.append((msg, kw)))
            app._open_zellij_tab_worker(path, command, kind, "Opened Claude")
            await app.workers.wait_for_complete()
            await pilot.pause()
        return notices

    async def test_open_tab_of_same_kind_is_reused(self, app, config, monkeypatch):
        fake = FakeZellij(tabs=("Tab #1", "TASK-1 · claude"))
        notices = await self._run(app, monkeypatch, fake, config.tasks_dir / "TASK-1")

        assert fake.calls[-1] == [config.zellij_path, "action", "go-to-tab-name", "TASK-1 · claude"]
        assert notices == [("Switched to open tab 'TASK-1 · claude'", {})]

    async def test_missing_tab_is_opened(self, app, config, monkeypatch):
        fake = FakeZellij(tabs=("Tab #1", "TASK-1 · shell"))
        notices = await self._run(app, monkeypatch, fake, config.tasks_dir / "TASK-1")

        assert fake.calls[-1][1:3] == ["action", "new-tab"]
        assert notices == [("Opened Claude", {})]

    async def test_failed_query_still_opens_a_tab(self, app, config, monkeypatch):
        fake = FakeZellij(tabs=("TASK-1 · claude",), query_rc=1)
        await self._run(app, monkeypatch, fake, config.tasks_dir / "TASK-1")

        assert fake.calls[-1][1:3] == ["action", "new-tab"]

    async def test_nonzero_exit_notifies(self, app, config, monkeypatch):
        fake = FakeZellij(action_rc=1, stderr="There is no active session!")
        notices = await self._run(app, monkeypatch, fake, config.tasks_dir / "TASK-1")

        assert notices == [
            ("Could not open a zellij tab: There is no active session!", {"severity": "warning"})
        ]

    async def test_missing_binary_notifies(self, app, config, monkeypatch):
        def fake_run(argv, *args, **kwargs):
            raise FileNotFoundError(2, "No such file or directory", "zellij")

        notices = await self._run(app, monkeypatch, fake_run, config.tasks_dir / "TASK-1")

        assert len(notices) == 1
        assert notices[0][0].startswith("Could not open a zellij tab:")
        assert notices[0][1] == {"severity": "warning"}


class TestZellijAutostart:
    @pytest.fixture
    def interactive(self, monkeypatch):
        monkeypatch.delenv("ZELLIJ_SESSION_NAME", raising=False)
        monkeypatch.setattr(app_module.os, "isatty", lambda fd: True)
        monkeypatch.setattr(app_module.shutil, "which", lambda name: f"/opt/bin/{name}")

    def test_relaunches_inside_session(self, interactive):
        config = Config(zellij_autostart=True, zellij_session="work")

        assert zellij_autostart_argv(config) == [
            "/opt/bin/zellij",
            "attach",
            "--create",
            "work",
            "--",
            sys.executable,
            "-m",
            "tasktree_manager.app",
        ]

    def test_off_by_default(self, interactive):
        assert zellij_autostart_argv(Config()) is None

    def test_not_inside_zellij(self, interactive, monkeypatch):
        monkeypatch.setenv("ZELLIJ_SESSION_NAME", "work")
        assert zellij_autostart_argv(Config(zellij_autostart=True)) is None

    def test_not_for_a_piped_run(self, interactive, monkeypatch):
        monkeypatch.setattr(app_module.os, "isatty", lambda fd: fd != 1)
        assert zellij_autostart_argv(Config(zellij_autostart=True)) is None

    def test_missing_zellij_warns_and_runs_here(self, capsys, interactive, monkeypatch):
        monkeypatch.setattr(app_module.shutil, "which", lambda name: None)
        assert zellij_autostart_argv(Config(zellij_autostart=True)) is None
        assert "zellij_autostart is on but zellij is not found" in capsys.readouterr().err

    def test_main_execs_zellij(self, interactive, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["tasktree-manager"])
        monkeypatch.setattr(Config, "load", classmethod(lambda cls: Config(zellij_autostart=True)))
        execs = []

        def fake_execv(path, argv):
            execs.append(argv)
            raise SystemExit(0)

        monkeypatch.setattr(app_module.os, "execv", fake_execv)
        with pytest.raises(SystemExit):
            app_module.main()
        assert execs[0][:4] == ["/opt/bin/zellij", "attach", "--create", "tasktree"]


class TestZellijConfig:
    def test_load_and_save_roundtrip(self, temp_dirs, monkeypatch):
        repos_dir, tasks_dir = temp_dirs
        config_dir = repos_dir.parent / ".config" / "tasktree-manager"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.toml").write_text(
            f'''
repos_dir = "{repos_dir}"
tasks_dir = "{tasks_dir}"

[tools]
zellij_path = "~/bin/zellij"
zellij_autostart = true
zellij_session = "work.1"
'''
        )
        monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
        monkeypatch.delenv("REPOS_DIR", raising=False)
        monkeypatch.delenv("TASKS_DIR", raising=False)

        config = Config.load()
        assert config.zellij_autostart is True
        assert config.zellij_session == "work.1"
        assert not config.zellij_path.startswith("~")

        config.save()
        reloaded = Config.load()
        assert (reloaded.zellij_autostart, reloaded.zellij_session) == (True, "work.1")

    def test_bad_session_name_falls_back(self, temp_dirs, monkeypatch):
        repos_dir, tasks_dir = temp_dirs
        config_dir = repos_dir.parent / ".config" / "tasktree-manager"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.toml").write_text(
            f'repos_dir = "{repos_dir}"\ntasks_dir = "{tasks_dir}"\n\n'
            '[tools]\nzellij_session = "two words; rm"\n'
        )
        monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir.parent))
        monkeypatch.delenv("REPOS_DIR", raising=False)
        monkeypatch.delenv("TASKS_DIR", raising=False)

        assert Config.load().zellij_session == "tasktree"
