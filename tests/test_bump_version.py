"""Tests for scripts/bump_version.py.

Covers the pure functions only (calculate_new_version, update_pyproject_version,
update_changelog) via tmp_path fixtures. The script is not an installed package
module, so it's loaded directly from its file path.
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "bump_version.py"
_spec = importlib.util.spec_from_file_location("bump_version", _SCRIPT_PATH)
bump_version = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bump_version)


class TestCalculateNewVersion:
    def test_patch(self):
        assert bump_version.calculate_new_version("1.2.3", "patch") == "1.2.4"

    def test_minor(self):
        assert bump_version.calculate_new_version("1.2.3", "minor") == "1.3.0"

    def test_major(self):
        assert bump_version.calculate_new_version("1.2.3", "major") == "2.0.0"

    def test_unknown_bump_type_raises(self):
        with pytest.raises(ValueError):
            bump_version.calculate_new_version("1.2.3", "bogus")


@pytest.fixture
def pyproject_file(tmp_path, monkeypatch):
    """Point the module's PYPROJECT_PATH at a throwaway file."""
    path = tmp_path / "pyproject.toml"
    path.write_text(
        "[project]\n"
        'name = "demo"\n'
        "\n"
        "[tool.semantic_release]\n"
        'version = "1.2.3"\n'
        'tag_format = "v{version}"\n'
    )
    monkeypatch.setattr(bump_version, "PYPROJECT_PATH", path)
    return path


class TestUpdatePyprojectVersion:
    def test_changes_version_and_reports_changed(self, pyproject_file):
        changed = bump_version.update_pyproject_version("1.2.3", "1.3.0")
        assert changed is True
        assert 'version = "1.3.0"' in pyproject_file.read_text()

    def test_same_version_is_not_reported_as_changed(self, pyproject_file):
        """`--set` to the version that's already current (e.g. a retried
        release re-run against an already-bumped commit) must not report
        changed=True just because the regex matched the line — the text on
        disk is identical."""
        before = pyproject_file.read_text()
        changed = bump_version.update_pyproject_version("1.2.3", "1.2.3")
        assert changed is False
        assert pyproject_file.read_text() == before

    def test_dry_run_does_not_write(self, pyproject_file):
        before = pyproject_file.read_text()
        changed = bump_version.update_pyproject_version("1.2.3", "1.3.0", dry_run=True)
        assert changed is True
        assert pyproject_file.read_text() == before

    def test_version_outside_semantic_release_section_untouched(self, tmp_path, monkeypatch):
        path = tmp_path / "pyproject.toml"
        path.write_text(
            '[project]\nversion = "1.2.3"\n\n[tool.semantic_release]\nversion = "9.9.9"\n'
        )
        monkeypatch.setattr(bump_version, "PYPROJECT_PATH", path)
        changed = bump_version.update_pyproject_version("1.2.3", "1.3.0")
        assert changed is False
        content = path.read_text()
        assert '[project]\nversion = "1.2.3"' in content
        assert 'version = "9.9.9"' in content


@pytest.fixture
def changelog_file(tmp_path, monkeypatch):
    path = tmp_path / "CHANGELOG.md"
    path.write_text(
        "# Changelog\n\n"
        "All notable changes...\n\n"
        "## [Unreleased]\n\n"
        "## [1.2.3] - 2026-01-01\n\n- initial\n\n"
    )
    monkeypatch.setattr(bump_version, "CHANGELOG_PATH", path)
    return path


class TestUpdateChangelog:
    def test_inserts_new_section_before_previous_version(self, changelog_file):
        updated = bump_version.update_changelog("1.3.0", message="- did a thing")
        assert updated is True
        content = changelog_file.read_text()
        assert "## [1.3.0]" in content
        assert content.index("## [1.3.0]") < content.index("## [1.2.3]")

    def test_skips_duplicate_section_for_existing_version(self, changelog_file):
        """Re-running for a version that already has a CHANGELOG section
        (e.g. a retried release after tag-release failed partway) must not
        insert a second copy of it."""
        before = changelog_file.read_text()
        updated = bump_version.update_changelog("1.2.3", message="- duplicate?")
        assert updated is False
        assert changelog_file.read_text() == before
        assert before.count("## [1.2.3]") == 1

    def test_dry_run_still_detects_duplicate(self, changelog_file):
        updated = bump_version.update_changelog("1.2.3", message="- duplicate?", dry_run=True)
        assert updated is False

    def test_dry_run_does_not_write(self, changelog_file):
        before = changelog_file.read_text()
        updated = bump_version.update_changelog("1.3.0", message="- did a thing", dry_run=True)
        assert updated is True
        assert changelog_file.read_text() == before

    def test_recovery_path_leaves_both_files_untouched(self, pyproject_file, changelog_file):
        """Full recovery scenario: tag-release already bumped pyproject and
        the CHANGELOG on a previous (failed) run, and this run re-applies
        the same --set version against that already-bumped commit. Neither
        file should be reported as changed, and the retry becomes a no-op
        that only needs the tag push to succeed."""
        pyproject_updated = bump_version.update_pyproject_version("1.2.3", "1.2.3")
        changelog_updated = bump_version.update_changelog("1.2.3", message="- initial")
        assert pyproject_updated is False
        assert changelog_updated is False
