"""Every command a person can type answers --help, and the commands no other test runs
are run here once each, on folders of the test's own: `templategenerate`, `photo
check`, `photo gather-check`, `parts elephant-walk`, `docs clean` and `release`
(with apothecary/release.py's readiness, git's answers stood in for)."""

from __future__ import annotations

import click
import pytest
from click.testing import CliRunner

from apothecary import release as releasing
from apothecary.cli import docs as docs_cli
from apothecary.cli.main import cli


def _commands(group: click.Group, path: tuple = ()):
    for name, command in sorted(group.commands.items()):
        yield (*path, name)
        if isinstance(command, click.Group):
            yield from _commands(command, (*path, name))


EVERY = list(_commands(cli))


@pytest.mark.parametrize("path", EVERY, ids=" ".join)
def test_every_command_answers_help(path):
    done = CliRunner().invoke(cli, [*path, "--help"])
    assert done.exit_code == 0, done.output
    assert done.output.startswith("Usage: ") and " ".join(path) in done.output


def test_the_walk_reaches_every_group_and_its_commands():
    """The walk above is the whole surface: every group's commands are in it."""
    assert ("photo", "check") in EVERY and ("test", "run") in EVERY
    assert len(EVERY) == len(set(EVERY))


def test_templategenerate_writes_what_the_template_makes_of_the_scene(tmp_path):
    out = tmp_path / "templated.scad"
    template = "// {{ scene_name }}: {{ object_count }} objects\n{{ scene_code }}"
    done = CliRunner().invoke(cli, ["templategenerate", "-t", template, "-o", str(out)])
    assert done.exit_code == 0, done.output
    head, code = out.read_text(encoding="utf-8").split("\n", 1)
    name = done.output.split("'")[1]  # "Templated scene 'NAME' -> OUT"
    assert head.startswith(f"// {name}: ") and head.endswith(" objects") and code.strip()
    assert f"-> {out}" in done.output


def test_photo_check_measures_a_finder_on_drawn_pictures():
    done = CliRunner().invoke(cli, ["photo", "check", "--count", "1"])
    assert done.exit_code == 0, done.output
    assert "measuring the 'plain' finder on 1 pictures per row" in done.output
    assert "clear shapes" in done.output and "made up" in done.output
    refused = CliRunner().invoke(cli, ["photo", "check", "--count", "0"])
    assert refused.exit_code != 0 and "at least 1" in refused.output


def test_photo_gather_check_measures_the_sorting():
    done = CliRunner().invoke(cli, ["photo", "gather-check", "--each", "1"])
    assert done.exit_code == 0, done.output
    assert done.output.strip()


def test_parts_elephant_walk_lays_every_part_in_a_line(tmp_path):
    out = tmp_path / "walk.scad"
    done = CliRunner().invoke(cli, ["parts", "elephant-walk", "--no-ensure-stl", "-o", str(out)])
    assert done.exit_code == 0, done.output
    assert "Calculating bounding boxes..." in done.output
    assert out.read_text(encoding="utf-8").strip()


def test_docs_clean_removes_the_generated_pages_and_says_when_there_are_none(tmp_path, monkeypatch):
    generated = tmp_path / "generated"
    (generated / "a-walk").mkdir(parents=True)
    (generated / "a-walk" / "a-walk.md").write_text("# A walk\n", encoding="utf-8")
    monkeypatch.setattr(docs_cli, "GENERATED_DOCS_ROOT", generated)
    done = CliRunner().invoke(cli, ["docs", "clean"])
    assert done.exit_code == 0 and f"Removed {generated}" in done.output
    assert not generated.exists()
    again = CliRunner().invoke(cli, ["docs", "clean"])
    assert again.exit_code == 0 and "Nothing to clean" in again.output


def _git_answers(monkeypatch, *, branch="main", dirty="", tags=""):
    answers = {("rev-parse", "--abbrev-ref", "HEAD"): branch, ("status", "--porcelain"): dirty}
    answers[("tag", "--list")] = tags
    monkeypatch.setattr(releasing, "_git", lambda *args, timeout=30: answers.get(args))


def test_a_clean_main_with_an_untagged_version_may_be_released(monkeypatch):
    _git_answers(monkeypatch)
    report = releasing.readiness()
    assert report.releasable and report.reasons == []
    assert report.version == releasing.declared_version() and report.published == []
    done = CliRunner().invoke(cli, ["release", "--check"])
    assert done.exit_code == 0, done.output
    assert f"this commit could be released as {report.version}" in done.output


@pytest.mark.parametrize(
    "answers, reason",
    [
        ({"branch": "build/a-change"}, "on branch build/a-change, not main"),
        ({"dirty": " M pyproject.toml"}, "uncommitted changes"),
        ({"tags": "v{version}\nnot-a-version"}, "is already tagged; bump it"),
    ],
    ids=["a-branch", "a-dirty-tree", "already-tagged"],
)
def test_what_stands_in_the_way_is_named_and_check_refuses(monkeypatch, answers, reason):
    version = releasing.declared_version()
    answers = {k: v.format(version=version) for k, v in answers.items()}
    _git_answers(monkeypatch, **answers)
    report = releasing.readiness()
    assert not report.releasable and any(reason in r for r in report.reasons), report.reasons
    done = CliRunner().invoke(cli, ["release", "--check"])
    assert done.exit_code == 1 and reason in done.output
    assert CliRunner().invoke(cli, ["release"]).exit_code == 0  # a report, unless --check


def test_only_version_tags_count_as_published(monkeypatch):
    _git_answers(monkeypatch, tags="v0.1.0\nrelease-notes\n1.2.3\nlatest")
    assert releasing.published_versions() == ["1.2.3", "v0.1.0"]
