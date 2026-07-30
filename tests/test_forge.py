"""Tests for the forge service (MR/PR state via glab/gh).

The real glab/gh CLIs never run here. Parsing and provider detection are
pure functions; process-boundary behavior is covered by monkeypatching the
module-level runner and, once, by a PATH-shimmed fake glab executable —
the suite's first fake binary (there is no unittest.mock precedent).
"""

import json
import stat

import pytest

from tasktree_manager.services import forge
from tasktree_manager.services.config import Config
from tasktree_manager.services.forge import (
    Forge,
    ForgeStatus,
    _parse_gh_payload,
    _parse_glab_payload,
    _parse_host,
    detect_provider,
    get_forge_status,
)


class TestParseHost:
    @pytest.mark.parametrize(
        ("url", "host"),
        [
            ("https://gitlab.example.com/group/project.git", "gitlab.example.com"),
            ("http://gitlab.local/g/p.git", "gitlab.local"),
            ("https://user:token@gitlab.example.com/g/p.git", "gitlab.example.com"),
            ("ssh://git@gitlab.example.com:2222/group/project.git", "gitlab.example.com"),
            ("git@gitlab.advsys.work:data-engineering/airflow-hpc.git", "gitlab.advsys.work"),
            ("git@github.com:user/repo.git", "github.com"),
            ("HTTPS://GitHub.com/User/Repo.git", "github.com"),
        ],
    )
    def test_remote_urls(self, url, host):
        assert _parse_host(url) == host

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "/tmp/origin/repo-remote.git",
            "./relative/repo.git",
            "~/repos/repo.git",
            "file:///tmp/repo.git",
            "C:\\repos\\repo.git",
            "just-a-directory",
        ],
    )
    def test_local_paths_and_garbage(self, url):
        assert _parse_host(url) is None


class TestDetectProvider:
    def test_github(self):
        assert detect_provider("git@github.com:user/repo.git") == "github"

    def test_gitlab_in_hostname(self):
        assert detect_provider("git@gitlab.advsys.work:group/repo.git") == "gitlab"

    def test_configured_gitlab_host(self):
        Forge.gitlab_hosts = ["Git.Example.com"]
        assert detect_provider("git@git.example.com:group/repo.git") == "gitlab"

    def test_unknown_host(self):
        assert detect_provider("git@bitbucket.org:user/repo.git") is None

    def test_local_path(self):
        assert detect_provider("/tmp/origin/repo.git") is None


# Trimmed from a real `glab mr list --all -F json` payload (glab 1.107).
GLAB_MERGED_MR = {
    "iid": 7,
    "state": "merged",
    "source_branch": "docs/collapse-mkdocs-navigation",
    "web_url": "https://gitlab.example.com/g/p/-/merge_requests/7",
    "references": {"short": "!7", "full": "g/p!7"},
    "squash_commit_sha": "7b1f7ac58d4881ec723af03c6f5ce9407b862aa9",
}


class TestParseGlabPayload:
    def test_merged(self):
        status = _parse_glab_payload(json.dumps([GLAB_MERGED_MR]))
        assert status == ForgeStatus(
            provider="gitlab",
            mr_state="merged",
            mr_url="https://gitlab.example.com/g/p/-/merge_requests/7",
            mr_ref="!7",
            ci_state=None,
        )

    def test_opened_maps_to_open(self):
        payload = json.dumps([{"iid": 3, "state": "opened", "web_url": "u"}])
        status = _parse_glab_payload(payload)
        assert status is not None
        assert status.mr_state == "open"
        assert status.mr_ref == "!3"  # falls back to iid without references

    def test_merged_preferred_over_closed(self):
        payload = json.dumps([{"iid": 1, "state": "closed"}, {"iid": 2, "state": "merged"}])
        status = _parse_glab_payload(payload)
        assert status is not None
        assert status.mr_state == "merged"
        assert status.mr_ref == "!2"

    def test_open_preferred_over_stale_merged(self):
        """A reused branch: the current open MR must outrank the old merged one,
        or safety checks would delete unmerged in-flight work."""
        payload = json.dumps([{"iid": 10, "state": "merged"}, {"iid": 20, "state": "opened"}])
        status = _parse_glab_payload(payload)
        assert status is not None
        assert status.mr_state == "open"
        assert status.mr_ref == "!20"

    def test_pipeline_status_when_present(self):
        payload = json.dumps(
            [{"iid": 4, "state": "opened", "head_pipeline": {"status": "running"}}]
        )
        status = _parse_glab_payload(payload)
        assert status is not None
        assert status.ci_state == "running"

    def test_empty_list_means_no_mr(self):
        assert _parse_glab_payload("[]") == ForgeStatus(provider="gitlab", mr_state="none")

    def test_unknown_states_only(self):
        payload = json.dumps([{"iid": 9, "state": "weird"}])
        assert _parse_glab_payload(payload) == ForgeStatus(provider="gitlab", mr_state="none")

    @pytest.mark.parametrize("payload", ["not json", '{"a": 1}', '"string"', "42"])
    def test_garbage(self, payload):
        assert _parse_glab_payload(payload) is None


class TestParseGhPayload:
    def test_merged(self):
        payload = json.dumps(
            [{"state": "MERGED", "number": 12, "url": "https://github.com/u/r/pull/12"}]
        )
        status = _parse_gh_payload(payload)
        assert status == ForgeStatus(
            provider="github",
            mr_state="merged",
            mr_url="https://github.com/u/r/pull/12",
            mr_ref="#12",
            ci_state=None,
        )

    def test_check_rollup_failure_wins(self):
        rollup = [
            {"status": "COMPLETED", "conclusion": "SUCCESS"},
            {"state": "FAILURE"},
            {"status": "IN_PROGRESS", "conclusion": None},
        ]
        payload = json.dumps([{"state": "OPEN", "number": 5, "statusCheckRollup": rollup}])
        status = _parse_gh_payload(payload)
        assert status is not None
        assert status.ci_state == "failed"

    def test_check_rollup_running_beats_success(self):
        rollup = [
            {"status": "COMPLETED", "conclusion": "SUCCESS"},
            {"status": "IN_PROGRESS", "conclusion": None},
        ]
        payload = json.dumps([{"state": "OPEN", "number": 5, "statusCheckRollup": rollup}])
        status = _parse_gh_payload(payload)
        assert status is not None
        assert status.ci_state == "running"

    def test_check_rollup_all_success(self):
        rollup = [{"conclusion": "SUCCESS"}, {"state": "SUCCESS"}]
        payload = json.dumps([{"state": "OPEN", "number": 5, "statusCheckRollup": rollup}])
        status = _parse_gh_payload(payload)
        assert status is not None
        assert status.ci_state == "success"

    def test_empty_list_means_no_pr(self):
        assert _parse_gh_payload("[]") == ForgeStatus(provider="github", mr_state="none")

    def test_garbage(self):
        assert _parse_gh_payload("nope") is None


class TestGetForgeStatus:
    def test_local_origin_never_invokes_cli(self, repo_with_origin, config, monkeypatch):
        def boom(cmd, cwd):
            raise AssertionError("forge CLI must not run for local-path origins")

        monkeypatch.setattr(forge, "_run_forge_command", boom)
        repo_path = config.repos_dir / "repo-remote"
        assert get_forge_status(repo_path, repo_with_origin) is None

    def test_disabled(self, repo_with_forge_url):
        repo_path, branch = repo_with_forge_url
        Forge.enabled = False
        assert get_forge_status(repo_path, branch) is None

    def test_empty_branch(self, repo_with_forge_url):
        repo_path, _ = repo_with_forge_url
        assert get_forge_status(repo_path, "") is None

    def test_missing_binary(self, repo_with_forge_url, monkeypatch):
        repo_path, branch = repo_with_forge_url
        monkeypatch.setattr(forge.shutil, "which", lambda path: None)
        assert get_forge_status(repo_path, branch) is None

    def test_ttl_cache_hits(self, repo_with_forge_url, monkeypatch):
        repo_path, branch = repo_with_forge_url
        calls = []

        def fake_fetch(path, br):
            calls.append((path, br))
            return ForgeStatus(provider="gitlab", mr_state="open")

        monkeypatch.setattr(forge, "_fetch_status", fake_fetch)
        first = get_forge_status(repo_path, branch)
        second = get_forge_status(repo_path, branch)
        assert first == second
        assert len(calls) == 1

    def test_ttl_expiry_refetches(self, repo_with_forge_url, monkeypatch):
        repo_path, branch = repo_with_forge_url
        calls = []
        monkeypatch.setattr(forge, "_fetch_status", lambda p, b: calls.append(1))
        monkeypatch.setattr(Forge, "CACHE_TTL", 0.0)
        get_forge_status(repo_path, branch)
        get_forge_status(repo_path, branch)
        assert len(calls) == 2

    def test_negative_results_cached(self, repo_with_forge_url, monkeypatch):
        repo_path, branch = repo_with_forge_url
        calls = []

        def fake_fetch(path, br):
            calls.append(1)
            return None

        monkeypatch.setattr(forge, "_fetch_status", fake_fetch)
        assert get_forge_status(repo_path, branch) is None
        assert get_forge_status(repo_path, branch) is None
        assert len(calls) == 1

    def test_clear_cache(self, repo_with_forge_url, monkeypatch):
        repo_path, branch = repo_with_forge_url
        calls = []
        monkeypatch.setattr(forge, "_fetch_status", lambda p, b: calls.append(1))
        get_forge_status(repo_path, branch)
        forge.clear_cache()
        get_forge_status(repo_path, branch)
        assert len(calls) == 2

    def test_configure_applies_and_invalidates(self, repo_with_forge_url):
        repo_path, branch = repo_with_forge_url
        config = Config(
            glab_path="/opt/glab",
            gh_path="/opt/gh",
            forge_enabled=False,
            forge_gitlab_hosts=["git.internal"],
        )
        Forge.configure(config)
        assert Forge.glab_path == "/opt/glab"
        assert Forge.gh_path == "/opt/gh"
        assert Forge.enabled is False
        assert Forge.gitlab_hosts == ["git.internal"]
        assert get_forge_status(repo_path, branch) is None


class TestPathShimEndToEnd:
    """One real subprocess round-trip through a fake glab executable."""

    def test_fake_glab_pipeline(self, repo_with_forge_url, tmp_path):
        repo_path, branch = repo_with_forge_url
        payload = json.dumps([GLAB_MERGED_MR])
        fake_glab = tmp_path / "bin" / "glab"
        fake_glab.parent.mkdir(parents=True, exist_ok=True)
        fake_glab.write_text(f"#!/bin/sh\nprintf '%s' '{payload}'\n")
        fake_glab.chmod(fake_glab.stat().st_mode | stat.S_IXUSR)

        Forge.glab_path = str(fake_glab)
        status = get_forge_status(repo_path, branch)
        assert status is not None
        assert status.provider == "gitlab"
        assert status.mr_state == "merged"
        assert status.mr_ref == "!7"

    def test_fake_glab_nonzero_exit(self, repo_with_forge_url, tmp_path):
        repo_path, branch = repo_with_forge_url
        fake_glab = tmp_path / "bin" / "glab"
        fake_glab.parent.mkdir(parents=True, exist_ok=True)
        fake_glab.write_text("#!/bin/sh\necho 'auth required' >&2\nexit 1\n")
        fake_glab.chmod(fake_glab.stat().st_mode | stat.S_IXUSR)

        Forge.glab_path = str(fake_glab)
        assert get_forge_status(repo_path, branch) is None


class TestBranchWithSlash:
    def test_slash_branch_passed_through(self, repo_with_forge_url, monkeypatch):
        """Branch names with slashes (release/1.0) must reach the CLI intact."""
        repo_path, _ = repo_with_forge_url
        seen = {}

        def fake_run(cmd, cwd):
            seen["cmd"] = cmd
            return "[]"

        monkeypatch.setattr(forge, "_run_forge_command", fake_run)
        monkeypatch.setattr(forge.shutil, "which", lambda path: "/usr/bin/glab")
        status = get_forge_status(repo_path, "release/1.0")
        assert status == ForgeStatus(provider="gitlab", mr_state="none")
        assert "release/1.0" in seen["cmd"]
