"""Tests for the headless CLI (tasktree_manager/cli.py)."""

import json
import subprocess

import pytest

from tasktree_manager.cli import run_cli


def cli(config, *argv):
    """Run the CLI against the test config."""
    return run_cli(list(argv), config=config)


@pytest.fixture
def repo_with_origin(config, tmp_path):
    """A repo in REPOS_DIR whose branch is pushed to a bare origin remote.

    check_merged() compares HEAD against origin/<base>, so only a repo
    with a remote can ever count as "merged" (and thus safe to delete).
    Returns the default branch name.
    """
    remote = tmp_path / "origin" / "repo-remote.git"
    remote.mkdir(parents=True)
    subprocess.run(["git", "init", "--bare"], cwd=remote, capture_output=True, check=True)

    repo = config.repos_dir / "repo-remote"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=repo, capture_output=True, check=True
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(remote)], cwd=repo, capture_output=True, check=True
    )
    (repo / "README.md").write_text("# repo-remote\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "push", "-u", "origin", "HEAD"], cwd=repo, capture_output=True, check=True
    )
    branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    return branch


class TestCreate:
    def test_create_task(self, config, sample_repos, capsys):
        repos, branch = sample_repos
        code = cli(config, "create", "DIC-1901-argocd-tls", "--repos", "repo-alpha,repo-beta")
        assert code == 0
        out = capsys.readouterr().out
        assert "Created task DIC-1901-argocd-tls" in out
        assert "2 repo(s)" in out

        task_path = config.tasks_dir / "DIC-1901-argocd-tls"
        assert (task_path / "repo-alpha" / ".git").exists()
        assert (task_path / "repo-beta" / ".git").exists()
        # Branch name matches task name
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=task_path / "repo-alpha",
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == "DIC-1901-argocd-tls"
        # Task CLAUDE.md is materialized at create time (no TUI lazy prep)
        assert (task_path / "CLAUDE.md").exists()

    def test_create_with_base(self, config, sample_repos, capsys):
        _, branch = sample_repos
        code = cli(config, "create", "task-x", "--repos", "repo-alpha", "--base", branch)
        assert code == 0

    def test_create_unknown_repo(self, config, sample_repos, capsys):
        code = cli(config, "create", "task-x", "--repos", "no-such-repo")
        assert code == 1
        err = capsys.readouterr().err
        assert "unknown repo(s): no-such-repo" in err
        assert "repo-alpha" in err  # lists available repos
        assert not (config.tasks_dir / "task-x").exists()

    def test_create_duplicate(self, config, sample_repos, capsys):
        assert cli(config, "create", "task-x", "--repos", "repo-alpha") == 0
        capsys.readouterr()
        code = cli(config, "create", "task-x", "--repos", "repo-beta")
        assert code == 1
        assert "task already exists" in capsys.readouterr().err

    def test_create_invalid_name(self, config, sample_repos, capsys):
        code = cli(config, "create", "../escape", "--repos", "repo-alpha")
        assert code == 1
        assert "error:" in capsys.readouterr().err

    def test_create_empty_repos(self, config, sample_repos, capsys):
        code = cli(config, "create", "task-x", "--repos", " , ")
        assert code == 1
        assert "at least one repo" in capsys.readouterr().err


class TestList:
    def test_list_empty(self, config, capsys):
        assert cli(config, "list") == 0
        assert "No tasks" in capsys.readouterr().out

    def test_list_plain(self, config, sample_repos, capsys):
        cli(config, "create", "task-x", "--repos", "repo-alpha,repo-beta")
        capsys.readouterr()
        assert cli(config, "list") == 0
        out = capsys.readouterr().out
        assert "task-x" in out
        assert "clean" in out
        assert "repo-alpha, repo-beta" in out

    def test_list_json(self, config, sample_repos, capsys):
        cli(config, "create", "task-x", "--repos", "repo-alpha")
        capsys.readouterr()
        assert cli(config, "list", "--json") == 0
        payload = json.loads(capsys.readouterr().out)
        assert len(payload) == 1
        assert payload[0]["name"] == "task-x"
        assert payload[0]["repos"] == ["repo-alpha"]
        assert payload[0]["dirty"] is False
        assert payload[0]["path"] == str(config.tasks_dir / "task-x")

    def test_list_json_empty(self, config, capsys):
        assert cli(config, "list", "--json") == 0
        assert json.loads(capsys.readouterr().out) == []

    def test_list_dirty(self, config, sample_repos, capsys):
        cli(config, "create", "task-x", "--repos", "repo-alpha")
        (config.tasks_dir / "task-x" / "repo-alpha" / "dirty.txt").write_text("x\n")
        capsys.readouterr()
        assert cli(config, "list", "--json") == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload[0]["dirty"] is True


class TestDelete:
    def test_delete_clean(self, config, repo_with_origin, capsys):
        cli(config, "create", "task-x", "--repos", "repo-remote", "--base", repo_with_origin)
        capsys.readouterr()
        assert cli(config, "delete", "task-x") == 0
        assert "Deleted task task-x" in capsys.readouterr().out
        assert not (config.tasks_dir / "task-x").exists()

    def test_delete_unmerged_refuses(self, config, sample_repos, capsys):
        # Repos without a remote can never verify a merge -> treated as unmerged
        cli(config, "create", "task-x", "--repos", "repo-alpha")
        capsys.readouterr()
        assert cli(config, "delete", "task-x") == 1
        assert "unfinished work" in capsys.readouterr().err
        assert (config.tasks_dir / "task-x").exists()

    def test_delete_missing(self, config, capsys):
        assert cli(config, "delete", "nope") == 1
        assert "no such task" in capsys.readouterr().err

    def test_delete_dirty_refuses(self, config, sample_repos, capsys):
        cli(config, "create", "task-x", "--repos", "repo-alpha")
        (config.tasks_dir / "task-x" / "repo-alpha" / "dirty.txt").write_text("x\n")
        capsys.readouterr()
        assert cli(config, "delete", "task-x") == 1
        err = capsys.readouterr().err
        assert "unfinished work" in err
        assert "--force" in err
        assert (config.tasks_dir / "task-x").exists()

    def test_delete_dirty_force(self, config, sample_repos, capsys):
        cli(config, "create", "task-x", "--repos", "repo-alpha")
        (config.tasks_dir / "task-x" / "repo-alpha" / "dirty.txt").write_text("x\n")
        capsys.readouterr()
        assert cli(config, "delete", "task-x", "--force") == 0
        assert not (config.tasks_dir / "task-x").exists()


class TestAddRepo:
    def test_add_repo(self, config, sample_repos, capsys):
        cli(config, "create", "task-x", "--repos", "repo-alpha")
        capsys.readouterr()
        assert cli(config, "add-repo", "task-x", "repo-beta") == 0
        assert "Added repo-beta to task task-x" in capsys.readouterr().out
        assert (config.tasks_dir / "task-x" / "repo-beta" / ".git").exists()

    def test_add_repo_already_present(self, config, sample_repos, capsys):
        cli(config, "create", "task-x", "--repos", "repo-alpha")
        capsys.readouterr()
        assert cli(config, "add-repo", "task-x", "repo-alpha") == 0
        assert "already in task" in capsys.readouterr().out

    def test_add_repo_missing_task(self, config, sample_repos, capsys):
        assert cli(config, "add-repo", "nope", "repo-alpha") == 1
        assert "no such task" in capsys.readouterr().err

    def test_add_repo_unknown_repo(self, config, sample_repos, capsys):
        cli(config, "create", "task-x", "--repos", "repo-alpha")
        capsys.readouterr()
        assert cli(config, "add-repo", "task-x", "no-such-repo") == 1
        assert "unknown repo(s)" in capsys.readouterr().err


class TestRepos:
    def test_repos(self, config, sample_repos, capsys):
        assert cli(config, "repos") == 0
        assert capsys.readouterr().out.splitlines() == ["repo-alpha", "repo-beta", "repo-gamma"]

    def test_repos_empty(self, config, capsys):
        assert cli(config, "repos") == 0
        assert capsys.readouterr().out == ""


class TestParser:
    def test_no_command_exits(self, config):
        with pytest.raises(SystemExit):
            run_cli([], config=config)

    def test_version_exits(self, config, capsys):
        with pytest.raises(SystemExit) as exc_info:
            run_cli(["--version"], config=config)
        assert exc_info.value.code == 0
