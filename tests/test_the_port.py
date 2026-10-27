"""The viewer's port: one constant that every command starting the server, or talking
to a running one, takes; that $APOTHECARY_PORT moves; that every page sending a person
to the server names; and the banner's addresses, each answered. `docs generate` runs
its server on a free port of its own."""

import re
from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from apothecary.cli.main import cli
from apothecary.cli.server import DEFAULT_PORT, PORT_ENV, free_port
from apothecary.projects.parts.skeleton import ROOT

# The pages a person reads to reach the server. Dated records (docs/validation/) and
# plans (docs/plans/) say what was so on their day, at the address it had then.
PAGES = (
    [ROOT / name for name in ("README.md", "AGENTS.md", "CONTRIBUTING.md")]
    + sorted((ROOT / "walkthrough").glob("*.md"))
    + sorted((ROOT / "docs").glob("*.md"))
)
ADDRESS = re.compile(r"\b(?:127\.0\.0\.1|localhost):(\d{2,5})\b")


def test_every_page_sends_a_person_to_the_port_the_server_listens_on():
    elsewhere = sorted(
        (page.relative_to(ROOT).as_posix(), port)
        for page in PAGES
        for port in ADDRESS.findall(page.read_text(encoding="utf-8"))
        if int(port) != DEFAULT_PORT
    )
    assert elsewhere == []


@pytest.mark.parametrize(
    "argv", [["serve"], ["photo", "view"], ["photo", "gather"], ["slicer", "slice"]]
)
def test_each_command_on_the_viewers_port_names_it_and_its_variable(argv):
    said = CliRunner().invoke(cli, [*argv, "--help"], terminal_width=200).output
    assert f"[env var: {PORT_ENV}; default: {DEFAULT_PORT}]" in said


def test_the_variable_moves_serve_and_every_address_its_banner_prints_answers():
    port = free_port()
    with patch("uvicorn.run") as started:
        said = CliRunner().invoke(cli, ["serve"], env={PORT_ENV: str(port)})
    assert said.exit_code == 0, said.output
    assert started.call_args.kwargs["port"] == port
    printed = re.findall(rf"http://127\.0\.0\.1:{port}(/\S+)", said.output)
    assert {"/viewer", "/docs", "/openapi.json"} <= set(printed)
    assert "/walkthrough/00-getting-started.md" in printed and "/docs/dev-loop.md" in printed
    from apothecary.api import app

    here = TestClient(app)
    assert [path for path in printed if here.get(path).status_code != 200] == []


def test_lighting_finds_the_server_on_the_same_port(monkeypatch):
    from apothecary.cli.lighting import simulate

    (url,) = [param for param in simulate.params if param.name == "url"]
    assert url.get_default(click.Context(simulate)) == f"http://127.0.0.1:{DEFAULT_PORT}"
    monkeypatch.setenv(PORT_ENV, "6300")
    assert url.get_default(click.Context(simulate)) == "http://127.0.0.1:6300"


def test_docs_generate_runs_its_server_on_a_free_port_unless_one_is_named(monkeypatch, tmp_path):
    """A fixed port another server held would answer the doc server's /health for it,
    and the doc tests would drive that server instead."""
    import apothecary.docs_site as site
    from apothecary.cli import docs as docs_cli

    asked = []

    def stop_there(host, port, simulated_devices=True):
        asked.append(port)
        raise RuntimeError("stopped before the browser tests")

    monkeypatch.setattr(docs_cli, "_start_server", stop_there)
    monkeypatch.setattr(docs_cli, "GENERATED_DOCS_ROOT", tmp_path)
    monkeypatch.setattr(site, "note_refresh", lambda **_: None)
    for argv in ([], ["--port", "7001"]):
        CliRunner().invoke(cli, ["docs", "generate", *argv])
    (picked, named) = asked
    assert isinstance(picked, int) and picked not in (DEFAULT_PORT, 7001)
    assert named == 7001
