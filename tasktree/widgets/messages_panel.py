"""Messages panel widget for displaying activity log."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from rich.text import Text
from textual.widgets import Static


class MessageLevel(Enum):
    """Level/severity of an activity message."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class ActivityMessage:
    """A single activity log message."""

    timestamp: datetime
    message: str
    level: MessageLevel
    task_name: str | None = None

    @classmethod
    def create(
        cls, message: str, level: MessageLevel, task_name: str | None = None
    ) -> "ActivityMessage":
        """Create a new activity message with current timestamp."""
        return cls(
            timestamp=datetime.now(),
            message=message,
            level=level,
            task_name=task_name,
        )


@dataclass
class MessagesStore:
    """Store for activity messages with max capacity."""

    max_messages: int = 100
    messages: list[ActivityMessage] = field(default_factory=list)

    def add(self, message: ActivityMessage) -> None:
        """Add a message, removing oldest if at capacity."""
        self.messages.append(message)
        if len(self.messages) > self.max_messages:
            self.messages.pop(0)

    def clear(self) -> None:
        """Clear all messages."""
        self.messages.clear()


class MessagesPanel(Static):
    """Panel for displaying recent activity messages."""

    # Color mapping for message levels
    LEVEL_COLORS = {
        MessageLevel.INFO: "cyan",
        MessageLevel.SUCCESS: "green",
        MessageLevel.WARNING: "yellow",
        MessageLevel.ERROR: "red",
    }

    LEVEL_LABELS = {
        MessageLevel.INFO: "INFO",
        MessageLevel.SUCCESS: "SUCCESS",
        MessageLevel.WARNING: "WARNING",
        MessageLevel.ERROR: "ERROR",
    }

    def __init__(self, max_messages: int = 100, *args, **kwargs):
        """Initialize the messages panel.

        Args:
            max_messages: Maximum number of messages to keep in memory
        """
        super().__init__(*args, **kwargs)
        self._store = MessagesStore(max_messages=max_messages)

    def add_message(
        self, message: str, level: MessageLevel, task_name: str | None = None
    ) -> None:
        """Add a new message to the activity log.

        Args:
            message: The message text
            level: Message severity level
            task_name: Optional associated task name
        """
        activity_msg = ActivityMessage.create(message, level, task_name)
        self._store.add(activity_msg)
        self._update_display()

    def clear_messages(self) -> None:
        """Clear all messages from the activity log."""
        self._store.clear()
        self._update_display()

    def _update_display(self) -> None:
        """Update the panel display with current messages."""
        if not self._store.messages:
            self.update(Text("No recent activity", style="dim"))
            return

        # Build Rich Text with colored output
        text = Text()

        # Show messages in reverse order (newest first)
        for i, msg in enumerate(reversed(self._store.messages)):
            if i > 0:
                text.append("\n")

            # Format: [HH:MM:SS] [LEVEL] message
            timestamp_str = msg.timestamp.strftime("%H:%M:%S")
            level_color = self.LEVEL_COLORS.get(msg.level, "white")
            level_label = self.LEVEL_LABELS.get(msg.level, "INFO")

            text.append(f"[{timestamp_str}] ", style="dim")
            text.append(f"[{level_label}]", style=f"bold {level_color}")
            text.append(" ")
            text.append(msg.message)

        self.update(text)

    @property
    def message_count(self) -> int:
        """Return the number of messages in the log."""
        return len(self._store.messages)
