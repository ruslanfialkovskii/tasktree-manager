"""Tests for worktree badge rendering and the agent/forge poll plumbing."""

from tasktree_manager.services.forge import ForgeStatus
from tasktree_manager.widgets.messages_panel import MessagesPanel
from tasktree_manager.widgets.worktree_list import WorktreeList


def _worktree_prompt(worktree_list: WorktreeList, name: str) -> str:
    return str(worktree_list.get_option(name).prompt)


class TestWorktreeBadges:
    async def test_badges_render_in_place(self, app, task_manager, sample_repos):
        _, branch = sample_repos
        task = task_manager.create_task("BADGE-TASK", ["repo-alpha", "repo-beta"], branch)
        alpha_path = str(task.worktrees[0].path)

        async with app.run_test() as pilot:
            await pilot.pause()
            worktree_list = app.query_one("#worktree-list", WorktreeList)

            baseline = _worktree_prompt(worktree_list, "repo-alpha")
            assert "⟳" not in baseline and "●" not in baseline

            worktree_list.refresh_status_badges(
                {alpha_path: "working"},
                {alpha_path: ForgeStatus(provider="gitlab", mr_state="merged", ci_state="failed")},
            )
            prompt = _worktree_prompt(worktree_list, "repo-alpha")
            assert "⟳" in prompt  # session working
            assert "●" in prompt  # MR merged
            assert "✘" in prompt  # CI failed
            # The untouched worktree keeps blank badge cells
            other = _worktree_prompt(worktree_list, "repo-beta")
            assert "⟳" not in other and "●" not in other

    async def test_badges_survive_reload(self, app, task_manager, sample_repos):
        _, branch = sample_repos
        task = task_manager.create_task("RELOAD-TASK", ["repo-alpha"], branch)
        alpha_path = str(task.worktrees[0].path)

        async with app.run_test() as pilot:
            await pilot.pause()
            worktree_list = app.query_one("#worktree-list", WorktreeList)
            worktree_list.refresh_status_badges({alpha_path: "needs_input"}, {})
            assert "!" in _worktree_prompt(worktree_list, "repo-alpha")

            # A full reload rebuilds prompts from the widget-stored dicts
            worktree_list.load_worktrees(task.worktrees)
            assert "!" in _worktree_prompt(worktree_list, "repo-alpha")

    async def test_badges_in_grouped_mode(self, app, task_manager, sample_repos):
        _, branch = sample_repos
        task = task_manager.create_task("GROUP-TASK", ["repo-alpha", "repo-beta"], branch)
        alpha = task.worktrees[0]
        alpha_path = str(alpha.path)
        (alpha.path / "dirty.txt").write_text("x\n")
        alpha.is_dirty = True
        alpha.changed_files = 1

        async with app.run_test() as pilot:
            await pilot.pause()
            worktree_list = app.query_one("#worktree-list", WorktreeList)
            worktree_list.toggle_grouping()
            worktree_list.load_worktrees(task.worktrees)
            worktree_list.refresh_status_badges({alpha_path: "ready"}, {})
            assert "▣" in _worktree_prompt(worktree_list, "repo-alpha")

    async def test_unknown_worktree_paths_ignored(self, app, task_manager, sample_repos):
        _, branch = sample_repos
        task_manager.create_task("IGNORE-TASK", ["repo-alpha"], branch)

        async with app.run_test() as pilot:
            await pilot.pause()
            worktree_list = app.query_one("#worktree-list", WorktreeList)
            # Unrelated keys must not raise or alter rows
            worktree_list.refresh_status_badges({"/no/such/path": "working"}, {})
            assert "⟳" not in _worktree_prompt(worktree_list, "repo-alpha")


class TestAgentPollPlumbing:
    async def test_apply_agent_sessions_pushes_badges(self, app, task_manager, sample_repos):
        _, branch = sample_repos
        task = task_manager.create_task("POLL-TASK", ["repo-alpha"], branch)
        alpha_path = str(task.worktrees[0].path)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._apply_agent_sessions({alpha_path: "working"})
            worktree_list = app.query_one("#worktree-list", WorktreeList)
            assert "⟳" in _worktree_prompt(worktree_list, "repo-alpha")
            assert app._agent_poll_failures == 0

    async def test_agent_poll_auto_disable_after_three_failures(self, app):
        async with app.run_test() as pilot:
            await pilot.pause()
            for _ in range(3):
                app._note_agent_poll_failure()
            assert app._agent_poll_disabled is True
            # Exactly one message logged
            messages_panel = app.query_one("#messages-display", MessagesPanel)
            texts = [m.message for m in messages_panel._store.messages]
            disabled = [t for t in texts if "agent polling disabled" in t]
            assert len(disabled) == 1
            # Further failures stay silent
            app._note_agent_poll_failure()
            texts = [m.message for m in messages_panel._store.messages]
            assert len([t for t in texts if "agent polling disabled" in t]) == 1

    async def test_apply_forge_statuses_merges(self, app, task_manager, sample_repos):
        _, branch = sample_repos
        task = task_manager.create_task("FORGE-TASK", ["repo-alpha"], branch)
        alpha_path = str(task.worktrees[0].path)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._apply_forge_statuses(
                {"/other/task/repo": ForgeStatus(provider="github", mr_state="open")}
            )
            app._apply_forge_statuses({alpha_path: ForgeStatus(provider="gitlab", mr_state="open")})
            # Merge keeps entries from earlier applies
            assert "/other/task/repo" in app._forge_statuses
            worktree_list = app.query_one("#worktree-list", WorktreeList)
            assert "○" in _worktree_prompt(worktree_list, "repo-alpha")

    async def test_apply_forge_statuses_none_evicts(self, app, task_manager, sample_repos):
        """A None result (MR gone, auth expired) clears the stale badge."""
        _, branch = sample_repos
        task = task_manager.create_task("EVICT-TASK", ["repo-alpha"], branch)
        alpha_path = str(task.worktrees[0].path)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._apply_forge_statuses({alpha_path: ForgeStatus(provider="gitlab", mr_state="open")})
            worktree_list = app.query_one("#worktree-list", WorktreeList)
            assert "○" in _worktree_prompt(worktree_list, "repo-alpha")

            app._apply_forge_statuses({alpha_path: None})
            assert alpha_path not in app._forge_statuses
            assert "○" not in _worktree_prompt(worktree_list, "repo-alpha")

    async def test_agent_poll_worker_with_stub(
        self, app, task_manager, sample_repos, fake_claude_cli
    ):
        """End-to-end: stub CLI payload -> worker -> badge state on the app."""
        import json

        _, branch = sample_repos
        task = task_manager.create_task("STUB-TASK", ["repo-alpha"], branch)
        alpha_path = str(task.worktrees[0].path)
        (fake_claude_cli / "agents.json").write_text(
            json.dumps([{"cwd": alpha_path, "status": "busy"}])
        )
        app.config.claude_path = str(fake_claude_cli / "claude")
        # The tick no-ops when polling is disabled (fixture default)
        app.config.agent_poll_interval = 10

        async with app.run_test() as pilot:
            await pilot.pause()
            app._poll_agent_sessions_tick()
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app._agent_sessions == {alpha_path: "working"}


class TestDispatchAgent:
    async def test_dispatch_via_keybinding(self, app, task_manager, sample_repos, fake_claude_cli):
        """Press b -> modal -> prompt -> stub `claude --bg` logs the dispatch."""
        from tasktree_manager.widgets.create_modal import DispatchAgentModal

        _, branch = sample_repos
        task = task_manager.create_task("DISPATCH-TASK", ["repo-alpha"], branch)
        alpha_path = str(task.worktrees[0].path)
        app.config.claude_path = str(fake_claude_cli / "claude")
        # Optimistic badges require polling enabled (they'd stick forever otherwise)
        app.config.agent_poll_interval = 10

        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#worktree-list").focus()
            await pilot.pause()
            await pilot.press("b")
            await pilot.pause()
            assert isinstance(app.screen_stack[-1], DispatchAgentModal)

            await pilot.press(*"fix the tests")
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()

            dispatch_log = (fake_claude_cli / "dispatch.log").read_text()
            assert alpha_path in dispatch_log
            assert "fix the tests" in dispatch_log
            assert "--bg" in dispatch_log
            assert "DISPATCH-TASK/repo-alpha" in dispatch_log
            # Optimistic badge set until the next poll corrects it
            assert app._agent_sessions.get(alpha_path) == "working"

    async def test_dispatch_cancelled_modal_does_nothing(
        self, app, task_manager, sample_repos, fake_claude_cli
    ):
        _, branch = sample_repos
        task_manager.create_task("CANCEL-TASK", ["repo-alpha"], branch)
        app.config.claude_path = str(fake_claude_cli / "claude")

        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#worktree-list").focus()
            await pilot.pause()
            await pilot.press("b")
            await pilot.pause()
            await pilot.press("escape")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert not (fake_claude_cli / "dispatch.log").exists()

    async def test_dispatch_failure_reported(self, app, task_manager, sample_repos, tmp_path):
        """A missing claude binary surfaces as an error message, not a crash."""
        from tasktree_manager.widgets.messages_panel import MessagesPanel

        _, branch = sample_repos
        task = task_manager.create_task("FAIL-TASK", ["repo-alpha"], branch)
        alpha_path = str(task.worktrees[0].path)
        app.config.claude_path = str(tmp_path / "no-such-claude")

        async with app.run_test() as pilot:
            await pilot.pause()
            app._dispatch_agent_worker("FAIL-TASK/repo-alpha", "repo-alpha", alpha_path, "hi")
            await app.workers.wait_for_complete()
            await pilot.pause()
            messages_panel = app.query_one("#messages-display", MessagesPanel)
            texts = [m.message for m in messages_panel._store.messages]
            assert any("dispatch failed" in t for t in texts)
            assert app._agent_sessions.get(alpha_path) is None
