"""The hub's table as a person lists and changes it (``apothecary family``), and the
token each member writes with: made once, kept only as a hash, shown nowhere after."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from apothecary.cli import cli
from apothecary.family import hub, roster, tokens


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path))
    hub.close()
    yield tmp_path
    hub.close()


def _run(*args):
    return CliRunner().invoke(cli, ["family", *args])


def _table(state) -> dict:
    return json.loads((state / hub.TABLE).read_text(encoding="utf-8"))


def test_add_names_a_member_makes_a_token_and_shows_it_once(state):
    added = _run("add", "alfred", "http://127.0.0.1:7001/")
    assert added.exit_code == 0, added.output
    assert _table(state) == {"members": {"alfred": "http://127.0.0.1:7001"}}
    token = added.output.split("shown once: ", 1)[1].strip()
    assert tokens.check("alfred", token) and token not in (state / tokens.FILE).read_text()
    listed = _run("members")
    assert listed.exit_code == 0
    assert "alfred" in listed.output and "http://127.0.0.1:7001" in listed.output
    assert token not in listed.output and token not in _run("members", "--json").output
    row = next(r for r in json.loads(_run("members", "--json").output) if r["name"] == "alfred")
    assert row == {
        "name": "alfred",
        "address": "http://127.0.0.1:7001",
        "via": "push",
        "capabilities": [],
        "token": True,
    }
    hosted = next(r for r in json.loads(_run("members", "--json").output) if r["name"] == "machine")
    assert hosted["via"] == "local" and "run" in hosted["capabilities"] and hosted["token"] is False


def test_a_member_is_on_this_machine_and_named_well_and_not_one_the_hub_hosts(state):
    for args, says in [
        (("alfred", "http://192.168.1.9:7001"), "not on this machine"),
        (("alfred", "https://127.0.0.1:7001"), "not on this machine"),
        (("a b", "http://127.0.0.1:7001"), "no member name"),
        (("machine", "http://127.0.0.1:7001"), "the hub's own members"),
        (("camera", "http://127.0.0.1:7001"), "the hub's own members"),
    ]:
        refused = _run("add", *args)
        assert refused.exit_code != 0 and says in refused.output, (args, refused.output)
    assert not (state / hub.TABLE).exists() and not (state / tokens.FILE).exists()


def test_a_table_that_does_not_read_is_never_written_over(state):
    (state / hub.TABLE).write_text("{ not json", encoding="utf-8")
    refused = _run("add", "alfred", "http://127.0.0.1:7001")
    assert refused.exit_code != 0 and "does not read" in refused.output
    assert (state / hub.TABLE).read_text(encoding="utf-8") == "{ not json"
    assert not (state / tokens.FILE).exists()


def test_remove_takes_a_member_out_and_revokes_its_token(state):
    _run("add", "alfred", "http://127.0.0.1:7001")
    (state / hub.TABLE).write_text(
        json.dumps({"members": {"alfred": "http://127.0.0.1:7001"}, "pull": ["joe"], "timeout": 3}),
        encoding="utf-8",
    )
    token = _run("token", "joe").output.split("shown once: ", 1)[1].strip()
    assert tokens.check("joe", token)
    assert _run("remove", "alfred").exit_code == 0 and not tokens.has("alfred")
    assert _run("remove", "joe").exit_code == 0 and not tokens.has("joe")
    assert _table(state) == {"members": {}, "pull": [], "timeout": 3}  # the rest as it was
    gone = _run("remove", "joe")
    assert gone.exit_code != 0 and "named nowhere" in gone.output
    assert _run("remove", "machine").exit_code != 0


def test_token_re_keys_a_named_member_and_no_other(state):
    _run("add", "alfred", "http://127.0.0.1:7001")
    old = tokens.make("alfred")
    new = _run("token", "alfred").output.split("shown once: ", 1)[1].strip()
    assert tokens.check("alfred", new) and not tokens.check("alfred", old)
    for name in ("mallory", "machine"):
        assert _run("token", name).exit_code != 0
    assert not tokens.has("mallory")


def test_the_list_says_a_member_without_a_token_has_none(state):
    (state / hub.TABLE).write_text(json.dumps({"pull": ["joe"]}), encoding="utf-8")
    row = next(r for r in roster.listing() if r["name"] == "joe")
    assert row["token"] is False and row["via"] == "pull"
