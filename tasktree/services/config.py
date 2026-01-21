"""Configuration management for tasktree."""

import os
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class Config:
    """Configuration for tasktree application."""

    repos_dir: Path = field(default_factory=lambda: Path.home() / "repos")
    tasks_dir: Path = field(default_factory=lambda: Path.home() / "wtasks")
    config_dir: Path = field(default_factory=lambda: Path.home() / ".config" / "tasktree")

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from environment variables and config file."""
        repos_dir = Path(os.environ.get("REPOS_DIR", str(Path.home() / "repos")))
        tasks_dir = Path(os.environ.get("TASKS_DIR", str(Path.home() / "wtasks")))
        config_dir = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "tasktree"

        return cls(
            repos_dir=repos_dir,
            tasks_dir=tasks_dir,
            config_dir=config_dir,
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
