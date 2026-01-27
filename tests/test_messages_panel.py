"""Tests for MessagesPanel widget."""

import pytest
from datetime import datetime

from tasktree.widgets.messages_panel import (
    ActivityMessage,
    MessageLevel,
    MessagesPanel,
    MessagesStore,
)
from tasktree.app import TaskTreeApp


class TestMessageLevel:
    """Tests for MessageLevel enum."""

    def test_info_value(self):
        """Test INFO level has correct value."""
        assert MessageLevel.INFO.value == "info"

    def test_success_value(self):
        """Test SUCCESS level has correct value."""
        assert MessageLevel.SUCCESS.value == "success"

    def test_warning_value(self):
        """Test WARNING level has correct value."""
        assert MessageLevel.WARNING.value == "warning"

    def test_error_value(self):
        """Test ERROR level has correct value."""
        assert MessageLevel.ERROR.value == "error"


class TestActivityMessage:
    """Tests for ActivityMessage dataclass."""

    def test_create_with_all_fields(self):
        """Test creating message with all fields."""
        timestamp = datetime.now()
        msg = ActivityMessage(
            timestamp=timestamp,
            message="Test message",
            level=MessageLevel.INFO,
            task_name="test-task",
        )
        assert msg.timestamp == timestamp
        assert msg.message == "Test message"
        assert msg.level == MessageLevel.INFO
        assert msg.task_name == "test-task"

    def test_create_without_task_name(self):
        """Test creating message without task name."""
        timestamp = datetime.now()
        msg = ActivityMessage(
            timestamp=timestamp,
            message="Test message",
            level=MessageLevel.SUCCESS,
        )
        assert msg.task_name is None

    def test_create_factory_method(self):
        """Test the create factory method."""
        msg = ActivityMessage.create(
            message="Factory created",
            level=MessageLevel.WARNING,
            task_name="my-task",
        )
        assert msg.message == "Factory created"
        assert msg.level == MessageLevel.WARNING
        assert msg.task_name == "my-task"
        assert isinstance(msg.timestamp, datetime)

    def test_create_factory_method_no_task(self):
        """Test the create factory method without task name."""
        msg = ActivityMessage.create(
            message="No task",
            level=MessageLevel.ERROR,
        )
        assert msg.task_name is None


class TestMessagesStore:
    """Tests for MessagesStore."""

    def test_add_message(self):
        """Test adding a message to store."""
        store = MessagesStore(max_messages=10)
        msg = ActivityMessage.create("Test", MessageLevel.INFO)
        store.add(msg)
        assert len(store.messages) == 1
        assert store.messages[0] == msg

    def test_add_multiple_messages(self):
        """Test adding multiple messages."""
        store = MessagesStore(max_messages=10)
        for i in range(5):
            msg = ActivityMessage.create(f"Message {i}", MessageLevel.INFO)
            store.add(msg)
        assert len(store.messages) == 5

    def test_max_messages_limit(self):
        """Test that oldest messages are removed when at capacity."""
        store = MessagesStore(max_messages=3)
        for i in range(5):
            msg = ActivityMessage.create(f"Message {i}", MessageLevel.INFO)
            store.add(msg)
        assert len(store.messages) == 3
        # Should have messages 2, 3, 4 (oldest removed)
        assert store.messages[0].message == "Message 2"
        assert store.messages[1].message == "Message 3"
        assert store.messages[2].message == "Message 4"

    def test_clear_messages(self):
        """Test clearing all messages."""
        store = MessagesStore(max_messages=10)
        for i in range(5):
            msg = ActivityMessage.create(f"Message {i}", MessageLevel.INFO)
            store.add(msg)
        store.clear()
        assert len(store.messages) == 0


class TestMessagesPanel:
    """Tests for MessagesPanel widget."""

    @pytest.fixture
    def panel(self):
        """Create a MessagesPanel instance."""
        return MessagesPanel(max_messages=10)

    def test_init_default_max(self):
        """Test default max messages."""
        panel = MessagesPanel()
        assert panel._store.max_messages == 100

    def test_init_custom_max(self, panel):
        """Test custom max messages."""
        assert panel._store.max_messages == 10

    def test_add_message_to_store(self, panel):
        """Test adding a message directly to store (avoids UI update)."""
        msg = ActivityMessage.create("Test message", MessageLevel.SUCCESS, "task-1")
        panel._store.add(msg)
        assert panel.message_count == 1

    def test_add_message_without_task_to_store(self, panel):
        """Test adding a message without task name to store."""
        msg = ActivityMessage.create("No task message", MessageLevel.INFO)
        panel._store.add(msg)
        assert panel.message_count == 1

    def test_store_clear(self, panel):
        """Test clearing messages via store."""
        msg1 = ActivityMessage.create("Message 1", MessageLevel.INFO)
        msg2 = ActivityMessage.create("Message 2", MessageLevel.SUCCESS)
        panel._store.add(msg1)
        panel._store.add(msg2)
        panel._store.clear()
        assert panel.message_count == 0

    def test_message_count_property(self, panel):
        """Test message_count property."""
        assert panel.message_count == 0
        msg = ActivityMessage.create("Test", MessageLevel.INFO)
        panel._store.add(msg)
        assert panel.message_count == 1
        msg2 = ActivityMessage.create("Test 2", MessageLevel.SUCCESS)
        panel._store.add(msg2)
        assert panel.message_count == 2

    def test_level_colors(self):
        """Test that level colors are defined."""
        assert MessageLevel.INFO in MessagesPanel.LEVEL_COLORS
        assert MessageLevel.SUCCESS in MessagesPanel.LEVEL_COLORS
        assert MessageLevel.WARNING in MessagesPanel.LEVEL_COLORS
        assert MessageLevel.ERROR in MessagesPanel.LEVEL_COLORS

    def test_level_labels(self):
        """Test that level labels are defined."""
        assert MessagesPanel.LEVEL_LABELS[MessageLevel.INFO] == "INFO"
        assert MessagesPanel.LEVEL_LABELS[MessageLevel.SUCCESS] == "SUCCESS"
        assert MessagesPanel.LEVEL_LABELS[MessageLevel.WARNING] == "WARNING"
        assert MessagesPanel.LEVEL_LABELS[MessageLevel.ERROR] == "ERROR"


class TestMessagesPanelIntegration:
    """Integration tests for MessagesPanel within the app."""

    @pytest.fixture
    def app(self, config):
        """Create app instance with test config."""
        app = TaskTreeApp()
        app.config = config
        app.config.ensure_dirs()
        return app

    async def test_app_has_messages_panel(self, app):
        """Test that the app has a messages panel."""
        async with app.run_test() as pilot:
            messages_panel = pilot.app.query_one("#messages-panel")
            assert messages_panel is not None

    async def test_app_has_messages_display(self, app):
        """Test that the app has a messages display widget."""
        async with app.run_test() as pilot:
            messages_display = pilot.app.query_one("#messages-display", MessagesPanel)
            assert messages_display is not None

    async def test_toggle_messages_action(self, app):
        """Test toggling between status and messages panel."""
        async with app.run_test() as pilot:
            status_panel = pilot.app.query_one("#status-panel")
            messages_panel = pilot.app.query_one("#messages-panel")

            # Initially, status panel is visible, messages panel hidden
            assert "-hidden" not in status_panel.classes
            assert "-visible" not in messages_panel.classes

            # Toggle to show messages
            await pilot.press("m")
            assert "-hidden" in status_panel.classes
            assert "-visible" in messages_panel.classes

            # Toggle back to status
            await pilot.press("m")
            assert "-hidden" not in status_panel.classes
            assert "-visible" not in messages_panel.classes

    async def test_log_activity_method(self, app):
        """Test the _log_activity helper method."""
        async with app.run_test() as pilot:
            messages_display = pilot.app.query_one("#messages-display", MessagesPanel)

            # Log a message
            pilot.app._log_activity("Test activity", MessageLevel.INFO, "test-task")

            assert messages_display.message_count == 1

    async def test_log_activity_multiple_levels(self, app):
        """Test logging messages with different levels."""
        async with app.run_test() as pilot:
            messages_display = pilot.app.query_one("#messages-display", MessagesPanel)

            pilot.app._log_activity("Info message", MessageLevel.INFO)
            pilot.app._log_activity("Success message", MessageLevel.SUCCESS)
            pilot.app._log_activity("Warning message", MessageLevel.WARNING)
            pilot.app._log_activity("Error message", MessageLevel.ERROR)

            assert messages_display.message_count == 4
