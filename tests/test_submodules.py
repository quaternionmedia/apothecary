"""Tests for submodules CLI command."""

import subprocess
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from apothecary.cli.main import cli
from apothecary.cli.system import _get_submodule_status


class TestSubmodulesCommand:
    """Tests for apothecary submodules command."""

    def test_submodules_help(self):
        """Test submodules --help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["submodules", "--help"])
        assert result.exit_code == 0
        assert "submodule" in result.output.lower()

    def test_submodules_status_flag(self):
        """Test submodules --status shows info only."""
        runner = CliRunner()
        result = runner.invoke(cli, ["submodules", "--status"])
        # Should not fail even if git not available
        assert result.exit_code in [0, 1]

    def test_submodules_no_git(self):
        """Test graceful handling when git not available."""
        runner = CliRunner()

        with patch("shutil.which", return_value=None):
            result = runner.invoke(cli, ["submodules"])
            assert result.exit_code == 1
            assert "git" in result.output.lower()

    def test_submodules_init_does_not_pass_recursive(self):
        """`git submodule init` does not support --recursive."""
        runner = CliRunner()
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch("apothecary.cli.system.subprocess.run", side_effect=fake_run):
            with patch(
                "apothecary.cli.system._get_submodule_status",
                return_value=[
                    {
                        "name": "governance/qm",
                        "path": "governance/qm",
                        "url": "https://github.com/quaternionmedia/qm.git",
                        "initialized": True,
                    }
                ],
            ):
                result = runner.invoke(cli, ["submodules"])

        assert result.exit_code == 0
        assert calls[0] == ["git", "submodule", "init"]
        assert calls[1] == ["git", "submodule", "update", "--recursive", "--init"]


class TestGetSubmoduleStatus:
    """Tests for _get_submodule_status helper."""

    def test_no_gitmodules_file(self, tmp_path):
        """Test handling when .gitmodules doesn't exist."""
        result = _get_submodule_status(tmp_path)
        assert result == []

    def test_parses_gitmodules(self, tmp_path):
        """Test parsing .gitmodules file."""
        gitmodules = tmp_path / ".gitmodules"
        gitmodules.write_text(
            """[submodule "parts/gridfinity/gridfinity-rebuilt-openscad"]
	path = parts/gridfinity/gridfinity-rebuilt-openscad
	url = https://github.com/kennetek/gridfinity-rebuilt-openscad.git
"""
        )

        result = _get_submodule_status(tmp_path)

        assert len(result) == 1
        assert result[0]["name"] == "parts/gridfinity/gridfinity-rebuilt-openscad"
        assert "gridfinity" in result[0]["url"]

    def test_detects_initialized_status(self, tmp_path):
        """Test detection of initialized vs not initialized."""
        gitmodules = tmp_path / ".gitmodules"
        gitmodules.write_text(
            """[submodule "test-sub"]
	path = test-sub
	url = https://example.com/test.git
"""
        )

        # Uninitialized - directory doesn't exist
        result = _get_submodule_status(tmp_path)
        assert result[0]["initialized"] is False

        # Create directory with content
        sub_dir = tmp_path / "test-sub"
        sub_dir.mkdir()
        (sub_dir / "file.txt").write_text("content")

        result = _get_submodule_status(tmp_path)
        assert result[0]["initialized"] is True

    def test_ignores_git_only_directory(self, tmp_path):
        """Test that directory with only .git is not considered initialized."""
        gitmodules = tmp_path / ".gitmodules"
        gitmodules.write_text(
            """[submodule "test-sub"]
	path = test-sub
	url = https://example.com/test.git
"""
        )

        # Create directory with only .git
        sub_dir = tmp_path / "test-sub"
        sub_dir.mkdir()
        (sub_dir / ".git").write_text("gitdir: ../../../.git/modules/test-sub")

        result = _get_submodule_status(tmp_path)
        # Only .git file, no other content
        assert result[0]["initialized"] is False


class TestNightlyDetection:
    """Tests for OpenSCAD nightly detection in renderer."""

    def test_nightly_paths_defined(self):
        """Test nightly paths are defined."""
        from apothecary.projects.parts.stl_renderer import OpenSCADRenderer

        renderer = OpenSCADRenderer()
        assert hasattr(renderer, "OPENSCAD_NIGHTLY_PATHS")
        assert len(renderer.OPENSCAD_NIGHTLY_PATHS) > 0

    def test_find_nightly_returns_path_or_none(self):
        """Test find_nightly returns Path or None."""
        from apothecary.projects.parts.stl_renderer import OpenSCADRenderer

        renderer = OpenSCADRenderer()
        result = renderer.find_nightly()
        assert result is None or isinstance(result, Path)

    def test_get_nightly_version(self):
        """Test get_nightly_version returns string or None."""
        from apothecary.projects.parts.stl_renderer import OpenSCADRenderer

        renderer = OpenSCADRenderer()
        result = renderer.get_nightly_version()
        assert result is None or isinstance(result, str)

    def test_windows_nightly_path(self):
        """Test Windows nightly path is in list."""
        from apothecary.projects.parts.stl_renderer import OpenSCADRenderer

        assert any("OpenSCAD (Nightly)" in p for p in OpenSCADRenderer.OPENSCAD_NIGHTLY_PATHS)
