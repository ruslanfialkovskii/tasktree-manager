"""Tests for the config service."""

from pathlib import Path

from tasktree.services.config import Config


class TestConfig:
    """Tests for Config class."""

    def test_default_paths(self):
        """Test default configuration paths."""
        config = Config()
        assert config.repos_dir == Path.home() / "repos"
        assert config.tasks_dir == Path.home() / "tasks"

    def test_custom_paths(self, temp_dirs):
        """Test configuration with custom paths."""
        repos_dir, tasks_dir = temp_dirs
        config = Config(repos_dir=repos_dir, tasks_dir=tasks_dir)
        assert config.repos_dir == repos_dir
        assert config.tasks_dir == tasks_dir

    def test_load_from_environment(self, temp_dirs, monkeypatch):
        """Test loading config from environment variables."""
        repos_dir, tasks_dir = temp_dirs
        monkeypatch.setenv("REPOS_DIR", str(repos_dir))
        monkeypatch.setenv("TASKS_DIR", str(tasks_dir))

        config = Config.load()
        assert config.repos_dir == repos_dir
        assert config.tasks_dir == tasks_dir

    def test_ensure_dirs_creates_directories(self, temp_dirs):
        """Test that ensure_dirs creates necessary directories."""
        repos_dir, tasks_dir = temp_dirs
        config_dir = repos_dir.parent / ".config" / "tasktree"

        config = Config(
            repos_dir=repos_dir,
            tasks_dir=tasks_dir,
            config_dir=config_dir,
        )

        # Remove tasks_dir to test creation
        tasks_dir.rmdir()
        assert not tasks_dir.exists()

        config.ensure_dirs()
        assert tasks_dir.exists()
        assert config_dir.exists()

    def test_get_available_repos_empty(self, config):
        """Test getting repos when directory is empty."""
        repos = config.get_available_repos()
        assert repos == []

    def test_get_available_repos_with_repos(self, config, sample_repos):
        """Test getting available repos."""
        repos = config.get_available_repos()
        assert len(repos) == 3
        assert "repo-alpha" in repos
        assert "repo-beta" in repos
        assert "repo-gamma" in repos

    def test_get_available_repos_ignores_non_git_dirs(self, config):
        """Test that non-git directories are ignored."""
        # Create a non-git directory
        non_git_dir = config.repos_dir / "not-a-repo"
        non_git_dir.mkdir()

        repos = config.get_available_repos()
        assert "not-a-repo" not in repos

    def test_get_available_repos_nonexistent_dir(self):
        """Test getting repos when directory doesn't exist."""
        config = Config(repos_dir=Path("/nonexistent/path"))
        repos = config.get_available_repos()
        assert repos == []

    def test_get_available_repos_nested(self, config):
        """Test getting nested repositories."""
        # Create nested git repos
        backend_dir = config.repos_dir / "backend" / "api"
        backend_dir.mkdir(parents=True)
        (backend_dir / ".git").mkdir()

        frontend_dir = config.repos_dir / "frontend" / "web"
        frontend_dir.mkdir(parents=True)
        (frontend_dir / ".git").mkdir()

        # Also create a top-level repo
        top_level = config.repos_dir / "infra"
        top_level.mkdir()
        (top_level / ".git").mkdir()

        repos = config.get_available_repos()
        assert len(repos) == 3
        assert "backend/api" in repos
        assert "frontend/web" in repos
        assert "infra" in repos

    def test_default_new_options(self):
        """Test default values for new configuration options."""
        config = Config()
        assert config.theme == "textual-dark"
        assert config.show_hidden_files is False
        assert config.default_base_branch == "main"
        assert config.auto_push is False
        assert config.git_timeout == 30
        assert config.editor == ""
        assert config.lazygit_path == "lazygit"
        assert config.shell == ""

    def test_load_theme_from_environment(self, temp_dirs, monkeypatch):
        """Test loading theme from environment variable."""
        repos_dir, tasks_dir = temp_dirs
        monkeypatch.setenv("REPOS_DIR", str(repos_dir))
        monkeypatch.setenv("TASKS_DIR", str(tasks_dir))
        monkeypatch.setenv("TASKTREE_THEME", "nord")

        config = Config.load()
        assert config.theme == "nord"

    def test_load_default_branch_from_environment(self, temp_dirs, monkeypatch):
        """Test loading default branch from environment variable."""
        repos_dir, tasks_dir = temp_dirs
        monkeypatch.setenv("REPOS_DIR", str(repos_dir))
        monkeypatch.setenv("TASKS_DIR", str(tasks_dir))
        monkeypatch.setenv("TASKTREE_DEFAULT_BRANCH", "develop")

        config = Config.load()
        assert config.default_base_branch == "develop"

    def test_load_from_config_file(self, temp_dirs):
        """Test loading configuration from TOML file."""
        repos_dir, tasks_dir = temp_dirs
        config_dir = repos_dir.parent / ".config" / "tasktree"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file = config_dir / "config.toml"

        config_content = f'''
repos_dir = "{repos_dir}"
tasks_dir = "{tasks_dir}"

[ui]
theme = "gruvbox"
show_hidden_files = true

[git]
default_base_branch = "master"
auto_push = true
timeout = 60

[tools]
editor = "nvim"
lazygit_path = "/usr/local/bin/lazygit"
shell = "/bin/zsh"
'''
        config_file.write_text(config_content)

        # Use a custom XDG_CONFIG_HOME to point to our test config
        import os
        old_xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = str(config_dir.parent)
        try:
            config = Config.load()
            assert config.repos_dir == repos_dir
            assert config.tasks_dir == tasks_dir
            assert config.theme == "gruvbox"
            assert config.show_hidden_files is True
            assert config.default_base_branch == "master"
            assert config.auto_push is True
            assert config.git_timeout == 60
            assert config.editor == "nvim"
            assert config.lazygit_path == "/usr/local/bin/lazygit"
            assert config.shell == "/bin/zsh"
        finally:
            if old_xdg is not None:
                os.environ["XDG_CONFIG_HOME"] = old_xdg
            else:
                os.environ.pop("XDG_CONFIG_HOME", None)

    def test_get_shell_from_config(self):
        """Test get_shell returns config value when set."""
        config = Config(shell="/bin/zsh")
        assert config.get_shell() == "/bin/zsh"

    def test_get_shell_fallback_to_env(self, monkeypatch):
        """Test get_shell falls back to environment."""
        monkeypatch.setenv("SHELL", "/bin/fish")
        config = Config(shell="")
        assert config.get_shell() == "/bin/fish"

    def test_get_editor_from_config(self):
        """Test get_editor returns config value when set."""
        config = Config(editor="nvim")
        assert config.get_editor() == "nvim"

    def test_get_editor_fallback_to_env(self, monkeypatch):
        """Test get_editor falls back to environment."""
        monkeypatch.setenv("EDITOR", "code")
        config = Config(editor="")
        assert config.get_editor() == "code"

    def test_save_and_load_roundtrip(self, temp_dirs):
        """Test that saving and loading config preserves values."""
        repos_dir, tasks_dir = temp_dirs
        config_dir = repos_dir.parent / ".config" / "tasktree"

        original = Config(
            repos_dir=repos_dir,
            tasks_dir=tasks_dir,
            config_dir=config_dir,
            theme="tokyo-night",
            show_hidden_files=True,
            default_base_branch="develop",
            auto_push=True,
            git_timeout=45,
            editor="vim",
            lazygit_path="/opt/bin/lazygit",
            shell="/bin/zsh",
        )
        original.save()

        # Load using custom XDG_CONFIG_HOME
        import os
        old_xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = str(config_dir.parent)
        try:
            loaded = Config.load()
            assert loaded.repos_dir == repos_dir
            assert loaded.tasks_dir == tasks_dir
            assert loaded.theme == "tokyo-night"
            assert loaded.show_hidden_files is True
            assert loaded.default_base_branch == "develop"
            assert loaded.auto_push is True
            assert loaded.git_timeout == 45
            assert loaded.editor == "vim"
            assert loaded.lazygit_path == "/opt/bin/lazygit"
            assert loaded.shell == "/bin/zsh"
        finally:
            if old_xdg is not None:
                os.environ["XDG_CONFIG_HOME"] = old_xdg
            else:
                os.environ.pop("XDG_CONFIG_HOME", None)
