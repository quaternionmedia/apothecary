"""Tests for CLI testing commands."""

import importlib.util
from pathlib import Path

import pytest
from click.testing import CliRunner

from apothecary.cli import cli


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def runner():
    """Provide a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def root_path():
    """Get the project root path."""
    from apothecary.projects.parts.skeleton import ROOT

    return ROOT


# ─────────────────────────────────────────────────────────────────────────────
# CLI Command Tests (parametrized)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "command,expected_text",
    [
        (["test", "--help"], "Commands for testing"),
        (["test", "setup-e2e", "--help"], "Playwright"),
        (["test", "validate-e2e", "--help"], "Validate"),
        (["test", "run-e2e", "--help"], "--headed"),
        (["test", "run", "--help"], "--coverage"),
        (["test", "all", "--help"], "--port"),
    ],
)
def test_cli_command_exists(runner, command, expected_text):
    """Test that CLI commands exist and show expected help text."""
    result = runner.invoke(cli, command)
    assert result.exit_code == 0
    assert expected_text in result.output


@pytest.mark.parametrize(
    "command,options",
    [
        (["test", "run-e2e", "--help"], ["--headed", "--slowmo", "--browser", "--base-url"]),
        (["test", "run", "--help"], ["--e2e", "--coverage"]),
        (["test", "all", "--help"], ["--port", "--coverage", "--headed", "--fail-fast"]),
    ],
)
def test_cli_command_options(runner, command, options):
    """Test that CLI commands have expected options."""
    result = runner.invoke(cli, command)
    assert result.exit_code == 0
    for opt in options:
        assert opt in result.output, f"Missing option: {opt}"


# ─────────────────────────────────────────────────────────────────────────────
# E2E File Structure Tests (parametrized)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "relative_path",
    [
        "tests/e2e/conftest.py",
        "tests/e2e/test_viewer.py",
        "tests/e2e/test_api_e2e.py",
    ],
)
def test_e2e_required_file_exists(root_path, relative_path):
    """Test that required E2E test files exist."""
    file_path = root_path / relative_path
    assert file_path.exists(), f"Missing required file: {relative_path}"


# ─────────────────────────────────────────────────────────────────────────────
# Playwright Setup Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_playwright_installed():
    """Test that playwright package is installed."""
    spec = importlib.util.find_spec("playwright")
    assert spec is not None, "Playwright package not installed. Run: uv sync"


@pytest.mark.slow
def test_chromium_browser_available():
    """Test that Chromium browser is installed for Playwright."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
    except Exception as e:
        pytest.skip(f"Chromium not available: {e}. Run: apothecary test setup-e2e")
