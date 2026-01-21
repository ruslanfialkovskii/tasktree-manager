"""Configuration management for tasktree."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    """Configuration for tasktree application."""

    repos_dir: Path = field(default_factory=lambda: Path.home() / "repos")
    tasks_dir: Path = field(default_factory=lambda: Path.home() / "tasks")
    config_dir: Path = field(default_factory=lambda: Path.home() / ".config" / "tasktree")

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from config file and environment variables.

        Priority: Environment variables > Config file > Defaults
        """
        config_dir = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "tasktree"
        config_file = config_dir / "config.toml"

        # Start with defaults
        repos_dir = Path.home() / "repos"
        tasks_dir = Path.home() / "tasks"

        # Load from config file if it exists
        if config_file.exists():
            try:
                # Simple TOML parsing (key = "value" format)
                with open(config_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("#") or not line or "=" not in line:
                            continue
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")

                        if key == "repos_dir":
                            repos_dir = Path(value).expanduser()
                        elif key == "tasks_dir":
                            tasks_dir = Path(value).expanduser()
            except Exception:
                # If config file is malformed, use defaults
                pass

        # Environment variables override config file
        if "REPOS_DIR" in os.environ:
            repos_dir = Path(os.environ["REPOS_DIR"])
        if "TASKS_DIR" in os.environ:
            tasks_dir = Path(os.environ["TASKS_DIR"])

        return cls(
            repos_dir=repos_dir,
            tasks_dir=tasks_dir,
            config_dir=config_dir,
        )

    def save(self) -> None:
        """Save configuration to config file."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        config_file = self.config_dir / "config.toml"

        config_content = f"""# tasktree configuration
# Edit this file to change default directories

# Directory containing your git repositories
repos_dir = "{self.repos_dir}"

# Directory for task worktrees
tasks_dir = "{self.tasks_dir}"
"""
        config_file.write_text(config_content)

    def is_configured(self) -> bool:
        """Check if configuration is valid and directories exist."""
        return (
            self.repos_dir.exists()
            and self.repos_dir.is_dir()
            and self.tasks_dir.parent.exists()
        )

    def ensure_dirs(self) -> None:
        """Ensure required directories exist."""
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def get_available_repos(self) -> list[str]:
        """Get list of available repositories in REPOS_DIR."""
        if not self.repos_dir.exists():
            return []

        repos = []
        for item in self.repos_dir.iterdir():
            if item.is_dir() and (item / ".git").exists():
                repos.append(item.name)
        return sorted(repos)
