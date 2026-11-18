"""What the command line tells a person about where to start and what comes next:
`apothecary --help`'s order and closing steps, `check`'s last line, toolchain
reports that say each thing once, and that a command the page or the docs name is
one."""

import re
from pathlib import Path

import click
from click.testing import CliRunner

from apothecary.cli import cli
from apothecary.cli.main import REPOSITORY_COMMANDS
from apothecary.projects.parts.skeleton import ROOT


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
    steps.append(tail.index("apothecary serve --simulated"))
    assert steps == sorted(steps)
    assert "walkthrough/00-getting-started.md" in tail
    assert (ROOT / "walkthrough" / "00-getting-started.md").is_file()


def test_check_ends_with_the_next_step(monkeypatch):
    from apothecary.cli import system

    monkeypatch.setattr(system, "has_manifold", lambda exe: False)
    without = CliRunner().invoke(cli, ["check"]).output.rstrip().splitlines()[-1]
    assert without.startswith(
        "next: apothecary openscad install, then apothecary serve --simulated"
    )
    monkeypatch.setattr(system, "has_manifold", lambda exe: True)
    monkeypatch.setattr(system.OpenSCADRenderer, "is_available", True)
    monkeypatch.setattr(system.OpenSCADRenderer, "get_version", lambda self: "2026.01.01")
    done = CliRunner().invoke(cli, ["check"]).output.rstrip().splitlines()[-1]
    assert done == "next: apothecary serve --simulated (walkthrough/00-getting-started.md)"


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
    assert "start stored-mesh:" in built and "start probe-each-print:" in built
    assert "start first-layer-offset:" in planned and "first-layer-offset" not in built
    assert "(a stub)" not in shown


# Where a person reads a command's name: the page's words and the docs. The plans and
# the dated validation records are left out: they name the commands they would build,
# and those that were run then.
NAMING = (
    "apothecary/static/**/*.js",
    "templates/*.j2",
    "docs/**/*.md",
    "walkthrough/*.md",
    "README.md",
    "CONTRIBUTING.md",
)
NOT_NAMING = ("plans", "validation")
# `apothecary` and the words after it, in code (a backtick before it, or `uv run`) or
# not; a word running on into `_` or `:` is no command's ("apothecary esp32_blink:").
NAMED = re.compile(r"((?:`|<code>|<kbd>)(?:uv run )?)?\bapothecary((?: [a-z][a-z0-9-]*)+)(?![\w:])")
# A fenced block, and a line of it that starts with the command: after a prompt, a
# variable or `uv run` and its options. Such a line is read as code, as a command in
# backticks is, and ends where the line does.
FENCE = re.compile(r"^([ \t]*)(```|~~~)[^\n]*\n(.*?)^\1\2[ \t]*$", re.M | re.S)
COMMAND_LINE = re.compile(
    r"^([ \t]*(?:\$\s+)?(?:[A-Z_]+=\S+\s+)*(?:uv run(?:\s+--?[\w-]+(?:[ =][^\s-]\S*)?)*\s+)?)"
    r"apothecary\b([^\n]*)$",
    re.M,
)


def _fenced_as_code(text: str) -> str:
    """The text with each fenced line that runs `apothecary` marked as code, its end a stop."""
    return FENCE.sub(
        lambda m: m.group(0).replace(
            m.group(3), COMMAND_LINE.sub(r"\1`apothecary\2 ;", m.group(3))
        ),
        text,
    )


def _not_commands(text: str) -> list:
    """Each command a text names, read across its line breaks, that the command line
    does not have: in code, a first word that is no command; anywhere, a word after a
    group that is not one of its commands. Out of code, a first word that is no
    command is prose ("apothecary reads without it"), and after a command the words
    are its arguments."""
    out = []
    for m in NAMED.finditer(re.sub(r"\s+", " ", _fenced_as_code(text))):
        code, words = m.group(1), m.group(2).split()
        if words[0] not in cli.commands:
            if code:
                out.append(words[0])
            continue
        command, depth = cli, 0
        while depth < len(words) and isinstance(command, click.Group):
            if words[depth] not in command.commands:
                break
            command, depth = command.commands[words[depth]], depth + 1
        if isinstance(command, click.Group) and depth < len(words):
            out.append(" ".join(words[: depth + 1]))
    return out


def test_a_command_the_command_line_has_not_is_found():
    assert _not_commands("none is trusted until apothecary vision\n  check has passed") == [
        "vision check"
    ]
    assert _not_commands("run `apothecary visions status` first") == ["visions"]
    assert _not_commands("run `uv run apothecary photos` first") == ["photos"]
    said = (
        "apothecary reads without it; apothecary vision ask a.png; `apothecary serve --simulated`;"
        " `uv run apothecary vision status`; it prints `apothecary esp32_blink: hello`"
    )
    assert _not_commands(said) == []


def test_a_fenced_command_and_one_in_code_markup_are_read_as_code():
    """The docs show most commands in fenced blocks, and the page in <code>: a first word
    there that is no command is found, as one in backticks is. A fenced line that only
    mentions the package -- a folder, a path, an import -- runs no command."""
    fenced = (
        "```bash\nuv run --group preflight apothecary frobnicate\n"
        "APOTHECARY_PORT=7000 apothecary serve\n$ apothecary verify\ncd apothecary\n"
        "ruff check apothecary tests\nfrom apothecary import cli\n```\n"
    )
    assert _not_commands(fenced) == ["frobnicate", "verify"]
    assert _not_commands("run <code>apothecary airgapp metrics</code> first") == ["airgapp"]
    assert _not_commands("<kbd>uv run apothecary frobnicate</kbd>") == ["frobnicate"]


def test_every_command_the_page_and_the_docs_name_is_one():
    root = Path(__file__).resolve().parents[1]
    files = {
        path
        for pattern in NAMING
        for path in root.glob(pattern)
        if not set(NOT_NAMING) & set(path.relative_to(root).parts)
    }
    named = {
        f"{path.relative_to(root)}: apothecary {words}"
        for path in sorted(files)
        for words in _not_commands(path.read_text(encoding="utf-8"))
    }
    assert named == set()
