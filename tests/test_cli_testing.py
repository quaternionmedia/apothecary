"""`apothecary test` exits with the code pytest exits with."""

import subprocess

import pytest
from click.testing import CliRunner

from apothecary.cli import cli, testing


@pytest.fixture
def pytest_exits(monkeypatch):
    """Stand in for pytest: each run returns the next code given, and its argv is kept."""

    def exits_with(*codes: int) -> list[list[str]]:
        ran, remaining = [], list(codes)

        def run(argv, **kwargs):
            ran.append(argv)
            return subprocess.CompletedProcess(argv, remaining.pop(0))

        monkeypatch.setattr(testing.subprocess, "run", run)
        return ran

    return exits_with


@pytest.mark.parametrize("code", [0, 1, 2, 5])
def test_run_exits_with_pytests_code(pytest_exits, code):
    ran = pytest_exits(code)
    result = CliRunner().invoke(cli, ["test", "run", "-x"])
    assert result.exit_code == code
    assert ran == [testing.run_command() + ["-x"]]


@pytest.mark.parametrize(("unit", "browser", "code"), [(0, 0, 0), (1, 0, 1), (0, 5, 5), (2, 1, 2)])
def test_all_runs_both_phases_and_exits_with_the_first_failure(pytest_exits, unit, browser, code):
    ran = pytest_exits(unit, browser)
    result = CliRunner().invoke(cli, ["test", "all"])
    assert result.exit_code == code
    assert [argv[3:] for argv in ran] == [
        ["walkthrough", "tests", "--ignore=tests/e2e"],
        ["tests/e2e", "--start-server"],
    ]


@pytest.mark.parametrize("name", ["setup-e2e", "validate-e2e", "run-e2e"])
def test_a_retired_subcommand_names_its_replacement_and_fails(name):
    result = CliRunner().invoke(cli, ["test", name, "--headed"])
    assert result.exit_code == 1
    assert "is retired; use `" in result.output
