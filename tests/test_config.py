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
