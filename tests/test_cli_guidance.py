"""What the command line tells a person about where to start and what comes next:
`apothecary --help`'s order and closing steps, `check`'s last line, and toolchain
reports that say each thing once (the onboarding plan, 2026-10-11)."""

from click.testing import CliRunner

from apothecary.cli import cli
from apothecary.cli.main import REPOSITORY_COMMANDS


def _sections(text: str) -> dict:
    """A help page's sections by title, each a list of its first words."""
    found: dict = {}
    current = None
    for line in text.splitlines():
        if line and not line.startswith(" ") and line.endswith(":"):
            current = found.setdefault(line[:-1], [])
        elif current is not None and line.startswith("  ") and line.strip():
            current.append(line.split()[0])
        elif not line.strip():
            current = None
    return found


def test_the_help_lists_a_person_s_commands_before_the_repository_s_own():
    shown = CliRunner().invoke(cli, ["--help"]).output
    sections = _sections(shown)
    commands, own = sections["Commands"], sections["Working on Apothecary itself"]
    assert {"check", "serve", "openscad", "parts", "firmware", "slicer"} <= set(commands)
    assert set(own) == REPOSITORY_COMMANDS
    assert not set(commands) & REPOSITORY_COMMANDS
    assert shown.index("Commands:") < shown.index("Working on Apothecary itself:")


def test_the_help_ends_with_the_three_steps_and_the_page_that_says_them():
    shown = CliRunner().invoke(cli, ["--help"]).output
    tail = shown[shown.index("Start here:") :]
    steps = [tail.index(f"apothecary {step}") for step in ("check", "openscad install")]
    steps.append(tail.index("apothecary serve --demo"))
    assert steps == sorted(steps)
    assert "walkthrough/00-getting-started.md" in tail


def test_check_ends_with_the_next_step(monkeypatch):
    from apothecary.cli import system

    monkeypatch.setattr(system, "has_manifold", lambda exe: False)
    without = CliRunner().invoke(cli, ["check"]).output.rstrip().splitlines()[-1]
    assert without.startswith("next: apothecary openscad install, then apothecary serve --demo")
    monkeypatch.setattr(system, "has_manifold", lambda exe: True)
    monkeypatch.setattr(system.OpenSCADRenderer, "is_available", True)
    monkeypatch.setattr(system.OpenSCADRenderer, "get_version", lambda self: "2026.01.01")
    done = CliRunner().invoke(cli, ["check"]).output.rstrip().splitlines()[-1]
    assert done == "next: apothecary serve --demo (walkthrough/00-getting-started.md)"


def test_firmware_validate_says_each_missing_tool_once(no_arduino_cli):
    shown = CliRunner().invoke(cli, ["firmware", "validate"]).output
    for tool in ("arduino-cli", "esptool", "cargo", "espflash"):
        lines = [line for line in shown.splitlines() if f" {tool}" in f" {line.strip()}"]
        said = [line for line in lines if line.strip().lstrip("✗•! ").startswith(tool)]
        assert len(said) == 1, (tool, said)


def test_slicer_status_puts_its_stubs_under_planned(fake_orcaslicer):
    shown = CliRunner().invoke(cli, ["slicer", "status"]).output
    built, planned = shown.split("Planned, not built:")
    assert "start home:" in built.split("A slice is composed from:")[1]
    assert "start stored-mesh:" in planned and "stored-mesh" not in built
    assert "(a stub)" not in shown
