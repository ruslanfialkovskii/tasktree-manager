"""Tests for epics: the markers, the service rules and the `epic` CLI."""

import json

import pytest

from tasktree_manager.cli import run_cli
from tasktree_manager.services.models import Task, validate_task_name


def cli(config, *argv):
    """Run the CLI against the test config."""
    return run_cli(list(argv), config=config)


def make_task(config, name, kind=None, epic=None):
    """A bare task folder with optional raw marker contents."""
    path = config.tasks_dir / name
    path.mkdir()
    if kind is not None:
        (path / ".tasktree_kind").write_text(kind)
    if epic is not None:
        (path / ".tasktree_epic").write_text(epic)
    return Task(name=name, path=path)


class TestMarkers:
    def test_plain_task(self, config):
        task = make_task(config, "t1")
        assert task.kind == "task"
        assert not task.is_epic
        assert task.epic_name is None

    def test_epic_marker(self, config):
        task = make_task(config, "e1", kind="epic\n")
        assert task.kind == "epic"
        assert task.is_epic

    def test_unknown_kind_reads_as_task(self, config):
        assert make_task(config, "t1", kind="saga").kind == "task"

    def test_epic_name(self, config):
        assert make_task(config, "t1", epic="E-1\n").epic_name == "E-1"

    @pytest.mark.parametrize("value", ["../x", ".x", "-x", "a/b", "", "t1"])
    def test_invalid_epic_name_reads_as_none(self, config, value):
        assert make_task(config, "t1", epic=value).epic_name is None

    def test_epic_never_has_a_parent(self, config):
        assert make_task(config, "e1", kind="epic", epic="E-0").epic_name is None


@pytest.fixture
def epic(task_manager):
    return task_manager.create_task("EPIC-1", [], kind="epic")


class TestCreate:
    def test_create_epic_without_repos(self, task_manager, epic):
        assert epic.is_epic
        assert epic.worktrees == []
        assert (epic.path / ".tasktree_kind").read_text() == "epic\n"

    def test_create_child_with_worktree(self, task_manager, epic, sample_repos):
        _, branch = sample_repos
        child = task_manager.create_task("T-1", ["repo-alpha"], branch, epic="EPIC-1")
        assert child.epic_name == "EPIC-1"
        assert [wt.name for wt in child.worktrees] == ["repo-alpha"]

    def test_missing_epic_creates_nothing(self, task_manager, config):
        with pytest.raises(ValueError, match="No such epic"):
            task_manager.create_task("T-1", [], epic="EPIC-404")
        assert not (config.tasks_dir / "T-1").exists()

    def test_non_epic_target_creates_nothing(self, task_manager, config):
        task_manager.create_task("T-0", [])
        with pytest.raises(ValueError, match="not an epic"):
            task_manager.create_task("T-1", [], epic="T-0")
        assert not (config.tasks_dir / "T-1").exists()

    def test_epic_cannot_have_an_epic(self, task_manager, epic, config):
        with pytest.raises(ValueError, match="cannot belong"):
            task_manager.create_task("EPIC-2", [], epic="EPIC-1", kind="epic")
        assert not (config.tasks_dir / "EPIC-2").exists()

    def test_task_cannot_be_its_own_epic(self, task_manager, config):
        with pytest.raises(ValueError, match="its own epic"):
            task_manager.create_task("T-1", [], epic="T-1")
        assert not (config.tasks_dir / "T-1").exists()

    def test_unknown_kind(self, task_manager):
        with pytest.raises(ValueError, match="Unknown task kind"):
            task_manager.create_task("T-1", [], kind="saga")

    def test_marker_failure_rolls_back(self, task_manager, epic, config, monkeypatch):
        def fail(*args):
            raise OSError("disk full")

        monkeypatch.setattr(task_manager, "_write_marker", fail)
        with pytest.raises(OSError):
            task_manager.create_task("T-1", [], epic="EPIC-1")
        assert not (config.tasks_dir / "T-1").exists()


class TestHierarchy:
    def test_attach_move_detach(self, task_manager, epic):
        task_manager.create_task("EPIC-2", [], kind="epic")
        task = task_manager.create_task("T-1", [])
        task_manager.set_task_epic(task, "EPIC-1")
        assert task.epic_name == "EPIC-1"
        task_manager.set_task_epic(task, "EPIC-2")
        assert task.epic_name == "EPIC-2"
        task_manager.set_task_epic(task, None)
        assert task.epic_name is None
        assert not (task.path / ".tasktree_epic").exists()

    def test_epic_cannot_join_an_epic(self, task_manager, epic):
        other = task_manager.create_task("EPIC-2", [], kind="epic")
        with pytest.raises(ValueError, match="cannot belong"):
            task_manager.set_task_epic(other, "EPIC-1")

    def test_attach_to_non_epic(self, task_manager):
        target = task_manager.create_task("T-0", [])
        task = task_manager.create_task("T-1", [])
        with pytest.raises(ValueError, match="not an epic"):
            task_manager.set_task_epic(task, target.name)
        assert task.epic_name is None

    def test_attach_to_invalid_name(self, task_manager):
        task = task_manager.create_task("T-1", [])
        with pytest.raises(ValueError):
            task_manager.set_task_epic(task, "../x")

    def test_child_cannot_become_epic(self, task_manager, epic):
        task = task_manager.create_task("T-1", [], epic="EPIC-1")
        with pytest.raises(ValueError, match="belongs to epic"):
            task_manager.set_task_kind(task, "epic")
        assert not task.is_epic

    def test_mark_drops_invalid_parent_marker(self, task_manager, config):
        task = make_task(config, "T-1", epic="../x")
        task_manager.set_task_kind(task, "epic")
        assert task.is_epic
        assert not (task.path / ".tasktree_epic").exists()

    def test_unmark_refused_with_children(self, task_manager, epic):
        task_manager.create_task("T-1", [], epic="EPIC-1")
        with pytest.raises(ValueError, match="still has 1 task"):
            task_manager.set_task_kind(epic, "task")
        assert epic.is_epic

    def test_unmark_without_children(self, task_manager, epic):
        task_manager.set_task_kind(epic, "task")
        assert not epic.is_epic
        assert not (epic.path / ".tasktree_kind").exists()

    def test_epic_children(self, task_manager, epic):
        task_manager.create_task("T-2", [], epic="EPIC-1")
        task_manager.create_task("T-1", [], epic="EPIC-1")
        task_manager.create_task("T-3", [])
        assert task_manager.epic_child_names("EPIC-1") == ["T-1", "T-2"]
        assert [t.name for t in task_manager.epic_children(epic)] == ["T-1", "T-2"]

    def test_finish_refuses_epic_with_children(self, task_manager, epic):
        child = task_manager.create_task("T-1", [], epic="EPIC-1")
        with pytest.raises(ValueError, match="still has 1 task.*T-1"):
            task_manager.finish_task(epic)
        assert epic.path.exists()
        task_manager.finish_task(child)
        task_manager.finish_task(epic)
        assert not epic.path.exists()


@pytest.fixture
def cli_config(config, sample_repos):
    _, branch = sample_repos
    config.default_base_branch = branch
    return config


class TestEpicCli:
    def test_epic_create_without_repos(self, cli_config, capsys):
        assert cli(cli_config, "epic", "create", "EPIC-1") == 0
        out = capsys.readouterr().out
        assert "Created epic EPIC-1" in out
        assert "0 repo(s): none" in out
        epic_path = cli_config.tasks_dir / "EPIC-1"
        assert (epic_path / ".tasktree_kind").read_text() == "epic\n"
        assert (epic_path / "CLAUDE.md").exists()

    def test_epic_create_with_repos(self, cli_config, capsys):
        assert cli(cli_config, "epic", "create", "EPIC-1", "--repos", "repo-alpha") == 0
        assert (cli_config.tasks_dir / "EPIC-1" / "repo-alpha" / ".git").exists()

    def test_create_with_epic(self, cli_config, capsys):
        cli(cli_config, "epic", "create", "EPIC-1")
        capsys.readouterr()
        code = cli(cli_config, "create", "T-1", "--repos", "repo-alpha", "--epic", "EPIC-1")
        assert code == 0
        assert "in epic EPIC-1" in capsys.readouterr().out
        assert (cli_config.tasks_dir / "T-1" / ".tasktree_epic").read_text() == "EPIC-1\n"

    def test_create_with_missing_epic(self, cli_config, capsys):
        code = cli(cli_config, "create", "T-1", "--repos", "repo-alpha", "--epic", "EPIC-404")
        assert code == 1
        assert "No such epic: EPIC-404" in capsys.readouterr().err
        assert not (cli_config.tasks_dir / "T-1").exists()

    def test_add_move_and_repeat(self, cli_config, capsys):
        cli(cli_config, "epic", "create", "EPIC-1")
        cli(cli_config, "epic", "create", "EPIC-2")
        cli(cli_config, "create", "T-1", "--repos", "repo-alpha")
        cli(cli_config, "create", "T-2", "--repos", "repo-beta")
        capsys.readouterr()
        assert cli(cli_config, "epic", "add", "EPIC-1", "T-1", "T-2") == 0
        out = capsys.readouterr().out
        assert "Added T-1 to epic EPIC-1" in out
        assert "Added T-2 to epic EPIC-1" in out
        assert cli(cli_config, "epic", "add", "EPIC-2", "T-1") == 0
        assert "Moved T-1 from epic EPIC-1 to epic EPIC-2" in capsys.readouterr().out
        assert cli(cli_config, "epic", "add", "EPIC-2", "T-1") == 0
        assert "already in epic EPIC-2" in capsys.readouterr().out

    def test_add_missing_task_writes_nothing(self, cli_config, capsys):
        cli(cli_config, "epic", "create", "EPIC-1")
        cli(cli_config, "create", "T-1", "--repos", "repo-alpha")
        capsys.readouterr()
        assert cli(cli_config, "epic", "add", "EPIC-1", "T-1", "T-404") == 1
        assert "no such task: T-404" in capsys.readouterr().err
        assert not (cli_config.tasks_dir / "T-1" / ".tasktree_epic").exists()

    def test_add_to_non_epic(self, cli_config, capsys):
        cli(cli_config, "create", "T-0", "--repos", "repo-alpha")
        cli(cli_config, "create", "T-1", "--repos", "repo-beta")
        capsys.readouterr()
        assert cli(cli_config, "epic", "add", "T-0", "T-1") == 1
        assert "'T-0' is not an epic" in capsys.readouterr().err

    def test_remove(self, cli_config, capsys):
        cli(cli_config, "epic", "create", "EPIC-1")
        cli(cli_config, "create", "T-1", "--repos", "repo-alpha", "--epic", "EPIC-1")
        cli(cli_config, "create", "T-2", "--repos", "repo-beta")
        capsys.readouterr()
        assert cli(cli_config, "epic", "remove", "T-1", "T-2") == 0
        out = capsys.readouterr().out
        assert "Removed T-1 from epic EPIC-1" in out
        assert "Task T-2 is not in an epic" in out
        assert not (cli_config.tasks_dir / "T-1" / ".tasktree_epic").exists()

    def test_mark_and_unmark(self, cli_config, capsys):
        cli(cli_config, "create", "T-1", "--repos", "repo-alpha")
        capsys.readouterr()
        assert cli(cli_config, "epic", "mark", "T-1") == 0
        assert "Marked T-1 as an epic" in capsys.readouterr().out
        assert cli(cli_config, "epic", "mark", "T-1") == 0
        assert "already an epic" in capsys.readouterr().out
        assert cli(cli_config, "epic", "unmark", "T-1") == 0
        assert "plain task now" in capsys.readouterr().out
        assert cli(cli_config, "epic", "unmark", "T-1") == 0
        assert "is not an epic" in capsys.readouterr().out

    def test_unmark_refused_with_children(self, cli_config, capsys):
        cli(cli_config, "epic", "create", "EPIC-1")
        cli(cli_config, "create", "T-1", "--repos", "repo-alpha", "--epic", "EPIC-1")
        capsys.readouterr()
        assert cli(cli_config, "epic", "unmark", "EPIC-1") == 1
        assert "still has 1 task(s): T-1" in capsys.readouterr().err

    def test_mark_child_refused(self, cli_config, capsys):
        cli(cli_config, "epic", "create", "EPIC-1")
        cli(cli_config, "create", "T-1", "--repos", "repo-alpha", "--epic", "EPIC-1")
        capsys.readouterr()
        assert cli(cli_config, "epic", "mark", "T-1") == 1
        assert "belongs to epic 'EPIC-1'" in capsys.readouterr().err

    def test_epic_list(self, cli_config, capsys):
        assert cli(cli_config, "epic", "list") == 0
        assert "No epics" in capsys.readouterr().out
        cli(cli_config, "epic", "create", "EPIC-1")
        cli(cli_config, "epic", "create", "EPIC-2")
        cli(cli_config, "create", "T-1", "--repos", "repo-alpha", "--epic", "EPIC-1")
        capsys.readouterr()
        assert cli(cli_config, "epic", "list") == 0
        out = capsys.readouterr().out
        assert "EPIC-1\t1 task(s)\tT-1" in out
        assert "EPIC-2\t0 task(s)\t(no tasks)" in out
        assert cli(cli_config, "epic", "list", "--json") == 0
        payload = json.loads(capsys.readouterr().out)
        assert [(e["name"], e["tasks"], e["repos"]) for e in payload] == [
            ("EPIC-1", ["T-1"], []),
            ("EPIC-2", [], []),
        ]

    def test_list_json_fields(self, cli_config, capsys):
        cli(cli_config, "epic", "create", "EPIC-1")
        cli(cli_config, "create", "T-1", "--repos", "repo-alpha", "--epic", "EPIC-1")
        cli(cli_config, "create", "T-2", "--repos", "repo-beta")
        capsys.readouterr()
        assert cli(cli_config, "list", "--json") == 0
        payload = {t["name"]: t for t in json.loads(capsys.readouterr().out)}
        assert (payload["EPIC-1"]["kind"], payload["EPIC-1"]["epic"]) == ("epic", None)
        assert (payload["T-1"]["kind"], payload["T-1"]["epic"]) == ("task", "EPIC-1")
        assert (payload["T-2"]["kind"], payload["T-2"]["epic"]) == ("task", None)

    def test_status_json_epic(self, cli_config, capsys):
        cli(cli_config, "epic", "create", "EPIC-1")
        cli(cli_config, "create", "T-1", "--repos", "repo-alpha", "--epic", "EPIC-1")
        capsys.readouterr()
        assert cli(cli_config, "status", "T-1", "--json") == 0
        payload = json.loads(capsys.readouterr().out)
        assert (payload["kind"], payload["epic"]) == ("task", "EPIC-1")

    @pytest.mark.parametrize("verb", ["delete", "finish"])
    def test_delete_and_finish_refuse_epic_with_children(
        self, cli_config, capsys, monkeypatch, verb
    ):
        cli(cli_config, "epic", "create", "EPIC-1")
        cli(cli_config, "create", "T-1", "--repos", "repo-alpha", "--epic", "EPIC-1")
        capsys.readouterr()

        def no_sweep(*args):
            raise AssertionError("the refusal must come before the safety sweep")

        monkeypatch.setattr(
            "tasktree_manager.services.task_manager.TaskManager.check_task_safety", no_sweep
        )
        assert cli(cli_config, verb, "EPIC-1", "--force") == 1
        err = capsys.readouterr().err
        assert f"cannot {verb} epic EPIC-1" in err
        assert "T-1" in err
        assert (cli_config.tasks_dir / "EPIC-1").exists()

    def test_finish_empty_epic(self, cli_config, capsys):
        cli(cli_config, "epic", "create", "EPIC-1")
        (cli_config.tasks_dir / "EPIC-1" / "PLAN.md").write_text("plan\n")
        capsys.readouterr()
        assert cli(cli_config, "finish", "EPIC-1") == 0
        out = capsys.readouterr().out
        assert "Archived 1 task file(s)" in out
        assert not (cli_config.tasks_dir / "EPIC-1").exists()


class TestTuiDeleteGuard:
    async def test_delete_epic_with_children_refused(self, app, task_manager, monkeypatch):
        task_manager.create_task("A-EPIC", [], kind="epic")
        task_manager.create_task("Z-CHILD", [], epic="A-EPIC")
        swept = []
        monkeypatch.setattr(app, "_check_task_safety_worker", lambda task: swept.append(task))
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.current_task.name == "A-EPIC"
            await pilot.press("d")
            await pilot.pause()
            assert swept == []
            assert (task_manager.config.tasks_dir / "A-EPIC").exists()


def case_insensitive_fs(path):
    probe = path / "CaseProbe"
    probe.mkdir()
    try:
        return (path / "caseprobe").exists()
    finally:
        probe.rmdir()


class TestReviewFixes:
    def test_name_with_trailing_newline_is_invalid(self):
        assert validate_task_name("EPIC-1\n") is not None

    def test_create_refuses_epic_options_on_existing_folder(self, task_manager, epic):
        task_manager.create_task("T-1", [], epic="EPIC-1")
        with pytest.raises(ValueError, match="already exists"):
            task_manager.create_task("T-1", [], kind="epic")
        task_manager.create_task("T-2", [])
        with pytest.raises(ValueError, match="already exists"):
            task_manager.create_task("T-2", [], epic="EPIC-1")
        assert not task_manager.get_task("T-1").is_epic
        assert task_manager.get_task("T-2").epic_name is None

    def test_epic_rechecked_after_worktrees(self, task_manager, epic, config, monkeypatch):
        def unmark_meanwhile(task, repo, base):
            task_manager.set_task_kind(epic, "task")
            return False

        monkeypatch.setattr(task_manager, "_create_worktree", unmark_meanwhile)
        with pytest.raises(ValueError, match="not an epic"):
            task_manager.create_task("T-1", ["repo"], epic="EPIC-1")
        assert not (config.tasks_dir / "T-1").exists()

    def test_unmark_clears_hidden_parent_marker(self, task_manager, epic):
        (epic.path / ".tasktree_epic").write_text("EPIC-0\n")
        task_manager.set_task_kind(epic, "task")
        assert epic.epic_name is None
        assert not (epic.path / ".tasktree_epic").exists()

    def test_add_rechecks_epic_when_already_attached(self, cli_config, capsys):
        cli(cli_config, "epic", "create", "EPIC-1")
        cli(cli_config, "create", "T-1", "--repos", "repo-alpha", "--epic", "EPIC-1")
        (cli_config.tasks_dir / "EPIC-1" / ".tasktree_kind").unlink()
        capsys.readouterr()
        assert cli(cli_config, "epic", "add", "EPIC-1", "T-1") == 1
        assert "not an epic" in capsys.readouterr().err

    def test_case_variant_names_use_disk_spelling(self, task_manager, epic, config):
        if not case_insensitive_fs(config.tasks_dir):
            pytest.skip("needs a case-insensitive filesystem")
        task = task_manager.create_task("T-1", [])
        assert task_manager.set_task_epic(task, "epic-1") == "EPIC-1"
        assert task.epic_name == "EPIC-1"
        variant = task_manager.get_task("epic-1")
        assert variant.name == "EPIC-1"
        with pytest.raises(ValueError, match="still has 1 task"):
            task_manager.finish_task(variant)

    def test_case_variant_marker_still_counts_as_child(self, task_manager, epic, config):
        if not case_insensitive_fs(config.tasks_dir):
            pytest.skip("needs a case-insensitive filesystem")
        make_task(config, "T-1", epic="epic-1")
        assert task_manager.epic_child_names("EPIC-1") == ["T-1"]

    def test_cli_delete_case_variant_refused(self, cli_config, capsys):
        if not case_insensitive_fs(cli_config.tasks_dir):
            pytest.skip("needs a case-insensitive filesystem")
        cli(cli_config, "epic", "create", "EPIC-1")
        cli(cli_config, "create", "T-1", "--repos", "repo-alpha", "--epic", "EPIC-1")
        capsys.readouterr()
        assert cli(cli_config, "delete", "epic-1", "--force") == 1
        assert "cannot delete epic EPIC-1" in capsys.readouterr().err
        assert (cli_config.tasks_dir / "EPIC-1").exists()


class TestMarkerSymlink:
    def test_marker_write_does_not_follow_symlink(self, task_manager, epic, tmp_path):
        outside = tmp_path / "outside.txt"
        outside.write_text("keep\n")
        task = task_manager.create_task("T-1", [])
        (task.path / ".tasktree_epic").symlink_to(outside)
        task_manager.set_task_epic(task, "EPIC-1")
        assert outside.read_text() == "keep\n"
        assert not (task.path / ".tasktree_epic").is_symlink()
        assert task.epic_name == "EPIC-1"
