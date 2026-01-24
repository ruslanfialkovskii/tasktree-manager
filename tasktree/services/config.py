"""Configuration management for tasktree."""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Use tomllib (Python 3.11+) or fall back to tomli
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None  # type: ignore


@dataclass
class Config:
    """Configuration for tasktree application.

    Configuration is loaded from (in order of priority):
    1. Environment variables (highest priority)
    2. Config file (~/.config/tasktree/config.toml)
    3. Default values (lowest priority)
    """

    # Directory settings
    repos_dir: Path = field(default_factory=lambda: Path.home() / "repos")
    tasks_dir: Path = field(default_factory=lambda: Path.home() / "tasks")
    config_dir: Path = field(default_factory=lambda: Path.home() / ".config" / "tasktree")

    # UI settings
    theme: str = "textual-dark"
    show_hidden_files: bool = False

    # Git settings
    default_base_branch: str = "main"
    auto_push: bool = False
    git_timeout: int = 30

    # External tools
    editor: str = ""
    lazygit_path: str = "lazygit"
    shell: str = ""

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from config file and environment variables.

        Priority: Environment variables > Config file > Defaults
        """
        config_dir = Path(
            os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        ) / "tasktree"
        config_file = config_dir / "config.toml"

        # Start with defaults
        config_data: dict = {}

        # Load from config file if it exists
        if config_file.exists():
            config_data = cls._load_toml(config_file)

        # Build config with file values or defaults
        repos_dir = Path(config_data.get("repos_dir", Path.home() / "repos")).expanduser()
        tasks_dir = Path(config_data.get("tasks_dir", Path.home() / "tasks")).expanduser()

        # UI settings
        ui_config = config_data.get("ui", {})
        theme = ui_config.get("theme", "textual-dark")
        show_hidden_files = ui_config.get("show_hidden_files", False)

        # Git settings
        git_config = config_data.get("git", {})
        default_base_branch = git_config.get("default_base_branch", "main")
        auto_push = git_config.get("auto_push", False)
        git_timeout = git_config.get("timeout", 30)

        # External tools
        tools_config = config_data.get("tools", {})
        editor = tools_config.get("editor", "")
        lazygit_path = tools_config.get("lazygit_path", "lazygit")
        shell = tools_config.get("shell", "")

        # Environment variables override config file
        if "REPOS_DIR" in os.environ:
            repos_dir = Path(os.environ["REPOS_DIR"])
        if "TASKS_DIR" in os.environ:
            tasks_dir = Path(os.environ["TASKS_DIR"])
        if "TASKTREE_THEME" in os.environ:
            theme = os.environ["TASKTREE_THEME"]
        if "TASKTREE_DEFAULT_BRANCH" in os.environ:
            default_base_branch = os.environ["TASKTREE_DEFAULT_BRANCH"]
        if "EDITOR" in os.environ and not editor:
            editor = os.environ["EDITOR"]
        if "SHELL" in os.environ and not shell:
            shell = os.environ["SHELL"]

        return cls(
            repos_dir=repos_dir,
            tasks_dir=tasks_dir,
            config_dir=config_dir,
            theme=theme,
            show_hidden_files=show_hidden_files,
            default_base_branch=default_base_branch,
            auto_push=auto_push,
            git_timeout=git_timeout,
            editor=editor,
            lazygit_path=lazygit_path,
            shell=shell,
        )

    @staticmethod
    def _load_toml(config_file: Path) -> dict:
        """Load TOML config file.

        Uses tomllib (Python 3.11+) or tomli, with fallback to manual parsing.
        """
        if tomllib is not None:
            try:
                with open(config_file, "rb") as f:
                    return tomllib.load(f)
            except Exception:
                return {}

        # Fallback: simple manual TOML parsing for basic key = "value" format
        config_data: dict = {}
        try:
            with open(config_file, "r") as f:
                current_section = config_data
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or not line:
                        continue
                    # Handle sections [section]
                    if line.startswith("[") and line.endswith("]"):
                        section_name = line[1:-1].strip()
                        if section_name not in config_data:
                            config_data[section_name] = {}
                        current_section = config_data[section_name]
                        continue
                    # Handle key = value
                    if "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip()
                        # Parse value type
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                        elif value.lower() == "true":
                            value = True
                        elif value.lower() == "false":
                            value = False
                        elif value.isdigit():
                            value = int(value)
                        current_section[key] = value
        except Exception:
            pass
        return config_data

    def save(self) -> None:
        """Save configuration to config file."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        config_file = self.config_dir / "config.toml"

        config_content = f'''# tasktree configuration
# https://github.com/yourusername/tasktree

# ============================================================================
# Directory Settings
# ============================================================================

# Directory containing your git repositories
repos_dir = "{self.repos_dir}"

# Directory for task worktrees
tasks_dir = "{self.tasks_dir}"

# ============================================================================
# UI Settings
# ============================================================================
[ui]

# Theme to use (textual-dark, textual-light, nord, gruvbox, tokyo-night, monokai, dracula)
theme = "{self.theme}"

# Show hidden files in file listings
show_hidden_files = {str(self.show_hidden_files).lower()}

# ============================================================================
# Git Settings
# ============================================================================
[git]

# Default base branch for new worktrees (main, master, develop, etc.)
default_base_branch = "{self.default_base_branch}"

# Automatically push after committing (not recommended for most workflows)
auto_push = {str(self.auto_push).lower()}

# Timeout for git operations in seconds
timeout = {self.git_timeout}

# ============================================================================
# External Tools
# ============================================================================
[tools]

# Preferred editor (leave empty to use $EDITOR)
editor = "{self.editor}"

# Path to lazygit executable
lazygit_path = "{self.lazygit_path}"

# Preferred shell (leave empty to use $SHELL)
shell = "{self.shell}"
'''
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
        """Get list of available repositories in REPOS_DIR (recursively scans subdirectories)."""
        if not self.repos_dir.exists():
            return []

        repos = []
        # Recursively find all directories containing .git
        for git_dir in self.repos_dir.rglob(".git"):
            if git_dir.is_dir():
                # Get the parent directory (the actual repo)
                repo_path = git_dir.parent
                # Get relative path from repos_dir
                try:
                    rel_path = repo_path.relative_to(self.repos_dir)
                    repos.append(str(rel_path))
                except ValueError:
                    # Skip if not relative to repos_dir
                    continue

        return sorted(repos)

    def get_shell(self) -> str:
        """Get the shell to use, with fallback to environment or /bin/bash."""
        if self.shell:
            return self.shell
        return os.environ.get("SHELL", "/bin/bash")

    def get_editor(self) -> str:
        """Get the editor to use, with fallback to environment or vi."""
        if self.editor:
            return self.editor
        return os.environ.get("EDITOR", "vi")
