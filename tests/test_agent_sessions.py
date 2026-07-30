"""Tests for the agent_sessions service (`claude agents --json` discovery)."""

import json

from tasktree_manager.services.agent_sessions import (
    list_agent_sessions,
    map_sessions_to_worktrees,
    parse_agent_sessions,
)

# Pinned from a real `claude agents --json` run (July 2026)
REAL_PAYLOAD = [
    {
        "pid": 6640,
        "cwd": "/Users/x/wtasks/TASK-1/repo-a",
        "kind": "interactive",
        "startedAt": 1785237108134,
        "sessionId": "12ab898b-4554-438e-855a-cec59df21833",
        "name": "task-one",
        "status": "idle",
    },
    {
        "pid": 66541,
        "cwd": "/Users/x/wtasks/TASK-1/repo-b",
        "kind": "interactive",
        "startedAt": 1785412921026,
        "sessionId": "4d04646b-2e66-4cb1-93a2-eea93c8897e9",
        "name": "task-two",
        "status": "busy",
    },
]


class TestParseAgentSessions:
    def test_real_payload(self):
        sessions = parse_agent_sessions(json.dumps(REAL_PAYLOAD))
        assert sessions is not None
        assert len(sessions) == 2
        assert sessions[0].status == "ready"  # idle -> ready
        assert sessions[1].status == "working"  # busy -> working
        assert sessions[0].session_id == "12ab898b-4554-438e-855a-cec59df21833"
        assert sessions[0].name == "task-one"
        assert str(sessions[0].directory).endswith("wtasks/TASK-1/repo-a")

    def test_alternate_field_names(self):
        payload = json.dumps([{"directory": "/tmp/x", "state": "busy"}])
        sessions = parse_agent_sessions(payload)
        assert sessions is not None
        assert len(sessions) == 1
        assert sessions[0].status == "working"

    def test_dict_wrapper(self):
        payload = json.dumps({"agents": [{"cwd": "/tmp/x", "status": "idle"}]})
        sessions = parse_agent_sessions(payload)
        assert sessions is not None
        assert len(sessions) == 1

    def test_dict_wrapper_ignores_sibling_lists(self):
        """A sibling list like "errors": [] must not shadow the agents key."""
        payload = json.dumps({"errors": [], "agents": [{"cwd": "/tmp/x", "status": "busy"}]})
        sessions = parse_agent_sessions(payload)
        assert sessions is not None
        assert len(sessions) == 1
        assert sessions[0].status == "working"

    def test_dict_wrapper_unknown_key_is_failure(self):
        """An unrecognized wrapper is a schema change — report unavailable
        (feeding auto-disable) instead of silently clearing all badges."""
        assert (
            parse_agent_sessions(json.dumps({"things": [{"cwd": "/x", "status": "busy"}]})) is None
        )

    def test_unknown_status_skipped(self):
        """Dead/exited sessions must not render as a working spinner."""
        payload = json.dumps(
            [
                {"cwd": "/tmp/x", "status": "exited"},
                {"cwd": "/tmp/y", "status": "busy"},
            ]
        )
        sessions = parse_agent_sessions(payload)
        assert sessions is not None
        assert len(sessions) == 1
        assert sessions[0].status == "working"

    def test_empty_cwd_skipped(self):
        """An empty cwd would resolve to our own CWD and pin a phantom badge."""
        payload = json.dumps([{"cwd": "", "status": "busy"}])
        assert parse_agent_sessions(payload) == []

    def test_records_missing_fields_skipped(self):
        payload = json.dumps(
            [
                {"cwd": "/tmp/x"},  # no status
                {"status": "busy"},  # no directory
                "not-a-dict",
                {"cwd": "/tmp/ok", "status": "busy"},
            ]
        )
        sessions = parse_agent_sessions(payload)
        assert sessions is not None
        assert len(sessions) == 1
        assert str(sessions[0].directory) == "/tmp/ok" or str(sessions[0].directory).endswith("ok")

    def test_empty_list(self):
        assert parse_agent_sessions("[]") == []

    def test_garbage(self):
        assert parse_agent_sessions("not json") is None
        assert parse_agent_sessions('{"no_list": 1}') is None
        assert parse_agent_sessions("42") is None


class TestMapSessionsToWorktrees:
    def _sessions(self, *pairs):
        payload = json.dumps([{"cwd": cwd, "status": status} for cwd, status in pairs])
        sessions = parse_agent_sessions(payload)
        assert sessions is not None
        return sessions

    def test_exact_match(self, tmp_path):
        wt = tmp_path / "task" / "repo"
        wt.mkdir(parents=True)
        sessions = self._sessions((str(wt), "busy"))
        assert map_sessions_to_worktrees(sessions, [str(wt)]) == {str(wt): "working"}

    def test_nested_session_dir(self, tmp_path):
        wt = tmp_path / "task" / "repo"
        nested = wt / "src" / "deep"
        nested.mkdir(parents=True)
        sessions = self._sessions((str(nested), "idle"))
        assert map_sessions_to_worktrees(sessions, [str(wt)]) == {str(wt): "ready"}

    def test_unrelated_session_ignored(self, tmp_path):
        wt = tmp_path / "task" / "repo"
        other = tmp_path / "elsewhere"
        wt.mkdir(parents=True)
        other.mkdir()
        sessions = self._sessions((str(other), "busy"))
        assert map_sessions_to_worktrees(sessions, [str(wt)]) == {}

    def test_precedence_needs_input_wins(self, tmp_path):
        wt = tmp_path / "task" / "repo"
        wt.mkdir(parents=True)
        sessions = self._sessions((str(wt), "busy"), (str(wt), "needs_input"), (str(wt), "idle"))
        assert map_sessions_to_worktrees(sessions, [str(wt)]) == {str(wt): "needs_input"}

    def test_symlinked_tmp_resolution(self, tmp_path):
        """macOS reports /tmp sessions under /private/tmp — resolve() bridges it."""
        real = tmp_path / "real-wt"
        real.mkdir()
        link = tmp_path / "link-wt"
        link.symlink_to(real)
        sessions = self._sessions((str(link), "busy"))
        assert map_sessions_to_worktrees(sessions, [str(real)]) == {str(real): "working"}


class TestListAgentSessions:
    def test_with_stub(self, fake_claude_cli):
        (fake_claude_cli / "agents.json").write_text(json.dumps(REAL_PAYLOAD))
        sessions = list_agent_sessions(str(fake_claude_cli / "claude"))
        assert sessions is not None
        assert len(sessions) == 2

    def test_missing_binary(self, tmp_path):
        assert list_agent_sessions(str(tmp_path / "no-such-claude")) is None

    def test_stub_failure_exit(self, fake_claude_cli):
        # No agents.json -> the stub exits 1 -> source unavailable
        assert list_agent_sessions(str(fake_claude_cli / "claude")) is None
