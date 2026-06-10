"""Tests for the command palette provider."""

from tasktree_manager.app import TaskTreeApp
from tasktree_manager.commands import APP_COMMANDS, TaskTreeCommands


class TestTaskTreeCommands:
    """Tests for the TaskTreeCommands palette provider."""

    async def test_app_registers_provider(self, app):
        """The app exposes the provider alongside the system commands."""
        assert TaskTreeCommands in TaskTreeApp.COMMANDS

    async def test_discover_lists_all_commands(self, app):
        """Opening the palette with an empty query lists every action."""
        async with app.run_test() as pilot:
            await pilot.pause()

            provider = TaskTreeCommands(app.screen)
            hits = [hit async for hit in provider.discover()]

            assert len(hits) == len(APP_COMMANDS)

    async def test_search_finds_action_with_hotkey(self, app):
        """Searching shows the matching command with its hotkey."""
        async with app.run_test() as pilot:
            await pilot.pause()

            provider = TaskTreeCommands(app.screen)
            hits = [hit async for hit in provider.search("lazygit")]

            assert hits
            assert any("(g)" in str(hit.match_display) for hit in hits)

    async def test_search_shows_customized_key(self, app):
        """A remapped keybinding shows the configured key, not the default."""
        app.config.keybindings["push_all"] = "x"

        async with app.run_test() as pilot:
            await pilot.pause()

            provider = TaskTreeCommands(app.screen)
            hits = [hit async for hit in provider.search("push all")]

            assert any("(x)" in str(hit.match_display) for hit in hits)

    async def test_search_no_match_returns_nothing(self, app):
        """A nonsense query yields no hits."""
        async with app.run_test() as pilot:
            await pilot.pause()

            provider = TaskTreeCommands(app.screen)
            hits = [hit async for hit in provider.search("zzz-no-such-command")]

            assert hits == []
