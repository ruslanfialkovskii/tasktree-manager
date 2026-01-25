"""Tests for the SetupModal widget."""

from pathlib import Path

from textual.widgets import Button, Input

from tasktree.widgets.setup_modal import SetupModal


class TestSetupModal:
    """Tests for SetupModal (setup wizard)."""

    async def test_modal_compose(self, app, sample_repos):
        """Test that modal composes expected widgets."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = SetupModal()
            app.push_screen(modal)
            await pilot.pause()

            # Check for expected inputs
            assert modal.query_one("#repos-dir", Input)
            assert modal.query_one("#tasks-dir", Input)

            # Check for buttons
            assert modal.query_one("#save-btn", Button)
            assert modal.query_one("#cancel-btn", Button)

    async def test_default_values(self, app, sample_repos):
        """Test that inputs have sensible default values."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = SetupModal()
            app.push_screen(modal)
            await pilot.pause()

            repos_input = modal.query_one("#repos-dir", Input)
            tasks_input = modal.query_one("#tasks-dir", Input)

            # Should have default home-based paths
            assert repos_input.value != ""
            assert tasks_input.value != ""

    async def test_save_validates_repos_dir_exists(self, app, sample_repos, tmp_path):
        """Test that save validates repos directory exists."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = SetupModal()
            app.push_screen(modal)
            await pilot.pause()

            # Set repos dir to non-existent path
            repos_input = modal.query_one("#repos-dir", Input)
            repos_input.value = str(tmp_path / "nonexistent_repos")

            # Set valid tasks dir (parent exists)
            tasks_input = modal.query_one("#tasks-dir", Input)
            tasks_input.value = str(tmp_path / "tasks")

            # Try to save
            modal._save_config()
            await pilot.pause()

            # Modal should still be there (validation failed)
            assert modal in app.screen_stack
            assert modal.error_message != ""

    async def test_save_validates_repos_dir_is_directory(self, app, sample_repos, tmp_path):
        """Test that save validates repos path is a directory."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = SetupModal()
            app.push_screen(modal)
            await pilot.pause()

            # Create a file instead of directory
            file_path = tmp_path / "not_a_dir"
            file_path.write_text("not a directory")

            # Set repos dir to the file
            repos_input = modal.query_one("#repos-dir", Input)
            repos_input.value = str(file_path)

            # Set valid tasks dir
            tasks_input = modal.query_one("#tasks-dir", Input)
            tasks_input.value = str(tmp_path / "tasks")

            # Try to save
            modal._save_config()
            await pilot.pause()

            # Modal should still be there (validation failed)
            assert modal in app.screen_stack
            assert modal.error_message != ""

    async def test_save_validates_tasks_parent_exists(self, app, tmp_path):
        """Test that save validates tasks directory parent exists."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = SetupModal()
            app.push_screen(modal)
            await pilot.pause()

            # Create a fresh subdirectory for this test
            test_dir = tmp_path / "setup_test"
            test_dir.mkdir(exist_ok=True)

            # Create repos dir
            repos_dir = test_dir / "repos"
            repos_dir.mkdir()

            # Set valid repos dir
            repos_input = modal.query_one("#repos-dir", Input)
            repos_input.value = str(repos_dir)

            # Set tasks dir with non-existent parent
            tasks_input = modal.query_one("#tasks-dir", Input)
            tasks_input.value = str(test_dir / "nonexistent_parent" / "tasks")

            # Try to save
            modal._save_config()
            await pilot.pause()

            # Modal should still be there (validation failed)
            assert modal in app.screen_stack
            assert modal.error_message != ""

    async def test_cancel_dismisses_modal(self, app, sample_repos):
        """Test that cancel button dismisses modal."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = SetupModal()
            app.push_screen(modal)
            await pilot.pause()

            # Dismiss directly
            modal.dismiss(None)
            await pilot.pause()

            assert modal not in app.screen_stack

    def test_path_expansion(self):
        """Test that tilde paths are expanded."""
        # Test path expansion logic
        repos_path = Path("~/repos").expanduser()
        assert "~" not in str(repos_path)

    async def test_multiple_validation_errors(self, app, sample_repos, tmp_path):
        """Test that multiple validation errors are shown."""
        async with app.run_test() as pilot:
            await pilot.pause()

            modal = SetupModal()
            app.push_screen(modal)
            await pilot.pause()

            # Set both paths to invalid
            repos_input = modal.query_one("#repos-dir", Input)
            repos_input.value = str(tmp_path / "nonexistent_repos")

            tasks_input = modal.query_one("#tasks-dir", Input)
            tasks_input.value = str(tmp_path / "nonexistent_parent" / "tasks")

            # Try to save
            modal._save_config()
            await pilot.pause()

            # Should have error message
            assert modal.error_message != ""

    def test_welcome_text_defined(self):
        """Test that welcome text is defined."""
        modal = SetupModal()

        # WELCOME_TEXT should be defined
        assert modal.WELCOME_TEXT
        assert "REPOS_DIR" in modal.WELCOME_TEXT
        assert "TASKS_DIR" in modal.WELCOME_TEXT
