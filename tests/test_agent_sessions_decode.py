"""Regression test: run_claude_agents must not raise on non-UTF-8 output.

`subprocess.run(..., text=True)` without `errors="replace"` raises
UnicodeDecodeError on invalid UTF-8 stdout instead of the documented
None/"unknown source" result. Uses a fake `claude` executable (same
PATH-shim pattern as test_forge.py's fake glab) so no real CLI is needed.
"""

import stat

from tasktree_manager.services.agent_sessions import run_claude_agents


class TestRunClaudeAgentsNonUtf8:
    def test_non_utf8_stdout_does_not_raise(self, tmp_path):
        fake_claude = tmp_path / "claude"
        # \xff\xfe is not valid UTF-8; printf writes it raw to stdout
        fake_claude.write_text("#!/bin/sh\nprintf '\\377\\376[]\\n'\n")
        fake_claude.chmod(fake_claude.stat().st_mode | stat.S_IXUSR)

        result = run_claude_agents(str(fake_claude))

        assert isinstance(result, str)
        assert "�" in result

    def test_non_utf8_stdout_on_failure_returns_none(self, tmp_path):
        fake_claude = tmp_path / "claude"
        fake_claude.write_text("#!/bin/sh\nprintf '\\377\\376broken\\n' >&2\nexit 1\n")
        fake_claude.chmod(fake_claude.stat().st_mode | stat.S_IXUSR)

        assert run_claude_agents(str(fake_claude)) is None
