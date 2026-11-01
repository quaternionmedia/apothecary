"""Image models through qmcp, always optional: each way qmcp can be missing gives
the answer apothecary gives without it and says which; a guess is never trusted
unchecked; a person's word comes first; an origin switched off is not asked.

The simulated qmcp (apothecary/finders/simulated.py) stands in for qmcp, in
process, so no qmcp and no socket is needed.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from apothecary.evidence.observation import Observation, Origin, Ref, Region, Sighting
from apothecary.finders import kept, qmcp


@pytest.fixture
def client(world, monkeypatch):
    from apothecary.api import app

    monkeypatch.delenv(qmcp.ENV, raising=False)
    kept.forget_all()
    # A red block, and a blue block with a yellow patch in it: the plain reader's
    # median reads the second blue, and the simulated model's mean guesses grey.
    img = Image.new("RGB", (400, 200), (245, 245, 245))
    pen = ImageDraw.Draw(img)
    pen.rectangle((40, 40, 140, 140), fill=(200, 30, 30))
    pen.rectangle((220, 40, 340, 140), fill=(30, 60, 200))
    pen.rectangle((250, 60, 310, 120), fill=(250, 220, 40))
    out = io.BytesIO()
    img.save(out, format="PNG")
    (world / "colours.png").write_bytes(out.getvalue())
    with TestClient(app) as c:
        r = c.post("/sites/garage/views", json={"host": "workbench", "picture": "colours.png"})
        assert r.status_code == 201, r.text
        view = r.json()["id"]
        r = c.post(f"/sites/garage/views/{view}/find", json={"finder": "plain"})
        assert r.status_code == 200, r.text
        c.view = view
        c.shapes = r.json()["shapes"]
        yield c
    kept.forget_all()


def _red(c):
    """The red block's index: the shape whose box starts left of the middle."""
    return next(s["index"] for s in c.shapes if s["min"][0] < 0.3)


def _ask(c, index, asked=("colour", "material", "label")):
    r = c.post(f"/sites/garage/views/{c.view}/shapes/{index}/ask", json={"asked": list(asked)})
    assert r.status_code == 200, r.text
    return r.json()


def _row(answer, prop):
    return next(row for row in answer["about"]["rows"] if row["property"] == prop)


def test_with_qmcp_unset_nothing_is_asked_and_the_plain_reader_still_reads(client):
    status = client.get("/vision").json()
    assert status["state"] == qmcp.NOT_CONFIGURED
    assert [o["origin"] for o in status["origins"]] == ["plain/colour"]
    answer = _ask(client, _red(client))
    assert "qmcp is not configured" in answer["said"]
    colour = _row(answer, "colour")
    assert colour["reading"]["value"] == "red" and colour["reading"]["rgb"].startswith("#")
    assert colour["guesses"] == []
    assert _row(answer, "material") == {
        **_row(answer, "material"),
        "reading": None,
        "guesses": [],
        "person": None,
    }


def test_the_simulated_qmcp_guesses_and_no_guess_is_trusted(client, monkeypatch):
    monkeypatch.setenv(qmcp.ENV, "simulated")
    status = client.get("/vision").json()
    assert status["state"] == qmcp.ANSWERING
    assert "qmcp/simulated-vlm@0" in [o["origin"] for o in status["origins"]]
    answer = _ask(client, _red(client))
    guess = _row(answer, "colour")["guesses"][0]
    assert guess["value"] == "red" and guess["agrees"] is True
    assert guess["trusted"] is False and guess["kind"] == "guessed"
    assert _row(answer, "material")["guesses"][0]["value"] in ("plastic", "metal")


def test_a_word_outside_the_list_is_unread_with_the_word(client, monkeypatch):
    monkeypatch.setenv(qmcp.ENV, "simulated")
    label = _row(_ask(client, _red(client), ["label"]), "label")["guesses"][0]
    assert label["value"] is None
    assert "outside the words asked among" in label["why"] and "'block'" in label["why"]


def test_a_mixed_region_reads_one_colour_and_is_guessed_another(client, monkeypatch):
    monkeypatch.setenv(qmcp.ENV, "simulated")
    mixed = next(s["index"] for s in client.shapes if s["min"][0] > 0.5)
    colour = _row(_ask(client, mixed, ["colour"]), "colour")
    assert colour["reading"]["value"] != colour["guesses"][0]["value"]
    assert colour["guesses"][0]["agrees"] is False


def test_a_black_disc_is_read_black_and_guessed_another_colour(client, world, monkeypatch):
    """The models checklist's black disc: on a light ground it is read black, its box's
    median, and guessed another colour, its box's mean, which the ground in the box's
    corners draws lighter; the guess disagrees."""
    monkeypatch.setenv(qmcp.ENV, "simulated")
    img = Image.new("RGB", (200, 200), (245, 245, 245))
    ImageDraw.Draw(img).ellipse((50, 50, 150, 150), fill=(30, 30, 30))
    out = io.BytesIO()
    img.save(out, format="PNG")
    (world / "disc.png").write_bytes(out.getvalue())
    r = client.post("/sites/garage/views", json={"host": "workbench", "picture": "disc.png"})
    assert r.status_code == 201, r.text
    client.view = r.json()["id"]
    r = client.post(f"/sites/garage/views/{client.view}/find", json={"finder": "plain"})
    assert r.status_code == 200, r.text
    (disc,) = r.json()["shapes"]
    colour = _row(_ask(client, disc["index"], ["colour"]), "colour")
    assert colour["reading"]["value"] == "black"
    guess = colour["guesses"][0]
    assert guess["value"] != "black" and guess["agrees"] is False, guess


def test_a_persons_word_overrules_a_guess_which_is_kept(client, monkeypatch):
    monkeypatch.setenv(qmcp.ENV, "simulated")
    index = _red(client)
    _ask(client, index)
    r = client.put(
        f"/sites/garage/views/{client.view}/shapes/{index}/observations/material",
        json={"value": "wood"},
    )
    assert r.status_code == 200, r.text
    material = _row(r.json(), "material")
    assert material["person"]["value"] == "wood" and material["person"]["kind"] == "stated"
    assert material["guesses"][0]["overruled"] is True
    r = client.put(
        f"/sites/garage/views/{client.view}/shapes/{index}/observations/colour",
        json={"value": "teal"},
    )
    assert r.status_code == 400 and "a colour is one of black, white, grey" in r.json()["detail"]
    # A person's label overrules the model's, unread as it is.
    r = client.put(
        f"/sites/garage/views/{client.view}/shapes/{index}/observations/label",
        json={"value": "spacer"},
    )
    assert _row(r.json(), "label")["guesses"][0]["overruled"] is True


def test_a_model_switched_off_is_not_asked_and_its_guesses_leave_the_view(client, monkeypatch):
    monkeypatch.setenv(qmcp.ENV, "simulated")
    index = _red(client)
    _ask(client, index)
    r = client.put("/vision/origins/qmcp/simulated-vlm@0", json={"on": False})
    assert r.status_code == 200
    seen = client.get(f"/sites/garage/views/{client.view}/shapes/{index}/observations").json()
    colour = next(row for row in seen["rows"] if row["property"] == "colour")
    assert colour["guesses"] == [] and colour["hidden"] == 1  # the one guess, not the reading
    assert "every model is switched off" in _ask(client, index)["said"]
    assert client.put("/vision/origins/person", json={"on": False}).status_code == 400


def test_a_model_with_no_version_is_switched_off_by_the_origin_it_is_listed_as(client, monkeypatch):
    """A model qmcp lists with no version has one origin: the one GET /vision lists it
    as is the one its guesses carry, so switched off by it, its guesses leave the view."""
    from apothecary.finders import simulated

    monkeypatch.setenv(qmcp.ENV, "simulated")
    monkeypatch.setattr(simulated, "MODEL", {**simulated.MODEL, "version": None})
    index = _red(client)
    guess = _row(_ask(client, index), "colour")["guesses"][0]
    [listed] = [o["origin"] for o in client.get("/vision").json()["origins"][1:]]
    assert guess["origin"] == listed
    # Sent as the Models window sends it, each part of the path encoded.
    switched = client.put(f"/vision/origins/{quote(listed, safe='/')}", json={"on": False})
    assert switched.status_code == 200
    seen = client.get(f"/sites/garage/views/{client.view}/shapes/{index}/observations").json()
    colour = next(row for row in seen["rows"] if row["property"] == "colour")
    assert colour["guesses"] == [] and colour["hidden"] == 1


def test_the_plain_reader_switched_off_reads_nothing(client):
    client.put("/vision/origins/plain/colour", json={"on": False})
    answer = _ask(client, _red(client), ["colour"])
    assert "plain/colour is switched off" in answer["said"]
    assert _row(answer, "colour")["reading"] is None


@pytest.mark.parametrize("word", ["off", "on"])
def test_a_persons_word_is_not_switched_from_the_command_line(world, word):
    from click.testing import CliRunner

    from apothecary.cli.main import cli

    result = CliRunner().invoke(cli, ["vision", word, "person"])
    assert result.exit_code == 2, result.output
    assert "a person's word is never switched off" in result.output


@pytest.mark.parametrize(
    "address, state, says",
    [
        ("simulated:empty", qmcp.NO_MODEL, "with no model"),
        ("simulated:down", qmcp.NOT_ANSWERING, "is not answering"),
        ("http://192.0.2.7:3141/mcp", qmcp.REFUSED_ADDRESS, "personal data stays on the device"),
        ("http://127.0.0.1:3141/mcp", qmcp.NOT_REACHABLE, "the qmcp extra is not installed"),
        ("simulated:sideways", qmcp.REFUSED_ADDRESS, "no simulated qmcp mode"),
    ],
)
def test_each_way_qmcp_is_missing_says_which(client, monkeypatch, address, state, says):
    monkeypatch.setenv(qmcp.ENV, address)
    status = client.get("/vision").json()
    assert status["state"] == state and says in status["says"]
    answer = _ask(client, _red(client), ["colour"])
    assert _row(answer, "colour")["reading"]["value"] == "red"


def test_a_model_with_no_answer_for_a_property_leaves_it_unread(client, monkeypatch):
    monkeypatch.setenv(qmcp.ENV, "simulated:empty")
    guess = _row(_ask(client, _red(client), ["material"]), "material")["guesses"][0]
    assert guess["value"] is None and "no model that answers material" in guess["why"]


def test_an_answer_past_the_deadline_is_given_up_and_unread(client, monkeypatch):
    monkeypatch.setenv(qmcp.ENV, "simulated:slow")
    monkeypatch.setattr(qmcp, "DEADLINE_MS", 200)
    answer = _ask(client, _red(client), ["colour"])
    assert "did not answer within" in answer["said"]
    colour = _row(answer, "colour")
    assert colour["reading"]["value"] == "red"
    assert colour["guesses"][0]["why"] == "the deadline passed"


def test_a_malformed_answer_is_refused_whole_and_nothing_kept(client, monkeypatch):
    monkeypatch.setenv(qmcp.ENV, "simulated:broken")
    answer = _ask(client, _red(client), ["colour"])
    assert "refused" in answer["said"] and "observations are not a list" in answer["said"]
    assert _row(answer, "colour")["guesses"] == []


def _request(tmp_path):
    picture = tmp_path / "p.png"
    Image.new("RGB", (10, 10), (200, 30, 30)).save(picture)
    return qmcp.request(
        picture,
        "d" * 64,
        "2026-10-31T00:00:00+00:00",
        [("shape 0", (0.0, 0.0, 1.0, 1.0))],
        ["colour"],
    )


def _answer(req, **change):
    one = {
        "subject": {
            "sighting": {
                "picture": req["picture"]["sha256"],
                "region": "shape 0",
                "box": [0, 0, 1, 1],
            }
        },
        "property": "colour",
        "value": "red",
        "unit": "qm.colours/1",
        "confidence": 0.9,
        "origin": {"kind": "guessed", "by": {"model": "m", "version": "1"}},
        "at": "2026-10-31T00:00:00+00:00",
        "recorded_at": "2026-10-31T00:00:01+00:00",
    }
    one.update(change.pop("observation", {}))
    return {
        "contract": "qm.vision",
        "version": 1,
        "picture": req["picture"]["sha256"],
        "observations": [one],
        **change,
    }


def test_parse_takes_a_well_formed_answer(tmp_path):
    req = _request(tmp_path)
    (seen,) = qmcp.parse(_answer(req), req)
    assert seen.value == "red" and seen.block.trusted is False
    assert seen.origin.key() == "qmcp/m@1"


@pytest.mark.parametrize(
    "change, refusal",
    [
        ({"version": 2}, "not qm.vision version 1"),
        ({"picture": "e" * 64}, "another picture"),
        (
            {
                "observation": {
                    "subject": {
                        "sighting": {"picture": "a" * 64, "region": "shape 9", "box": [0, 0, 1, 1]}
                    }
                }
            },
            "region not asked",
        ),
        ({"observation": {"property": "material"}}, "which was not asked"),
        ({"observation": {"origin": {"kind": "stated", "by": {}}}}, "a model's answer is a guess"),
        ({"observations": []}, "leaves a question unanswered"),
        ({"observation": {"value": None}}, "does not validate"),
    ],
)
def test_parse_refuses_a_malformed_answer_whole(tmp_path, change, refusal):
    req = _request(tmp_path)
    with pytest.raises(qmcp.Refused, match=refusal):
        qmcp.parse(_answer(req, **change), req)


def test_an_answer_naming_no_picture_says_so(tmp_path):
    req = _request(tmp_path)
    answer = _answer(req)
    del answer["picture"]
    with pytest.raises(qmcp.Refused, match="names no picture"):
        qmcp.parse(answer, req)


def test_an_observation_unread_says_why_and_its_generic_form_drops_apothecarys_block():
    when = datetime(2026, 10, 31, tzinfo=timezone.utc)
    common = dict(subject="garage:printer_1", property="colour", at=when, recorded_at=when)
    with pytest.raises(ValueError, match="says why"):
        Observation(origin=Origin(kind="read", by="plain/colour"), **common)
    seen = Observation(value="red", origin=Origin(kind="read", by="plain/colour"), **common)
    assert seen.format == "apothecary.observation"
    assert "apothecary" not in seen.generic() and seen.generic()["format"] == "qm.observation"


def test_the_one_module_holds_a_region_a_models_origin_a_pictures_reference_and_its_words():
    """What the image models add to the working space's module: a subject that is a
    region of a picture, ``by`` as a record a model's switch and trust look up, a
    picture's and an invocation's references, and their properties."""
    when = datetime(2026, 10, 31, tzinfo=timezone.utc)
    digest = "b" * 64
    region = Sighting(sighting=Region(picture=digest, region="shape 1", box=(0.1, 0.2, 0.3, 0.4)))
    model = Origin(kind="guessed", by={"name": "m", "version": "1", "tool": "vision.observe"})
    seen = Observation(
        subject=region,
        property="material",
        value="plastic",
        origin=model,
        at=when,
        recorded_at=when,
        evidence=[
            Ref(kind="picture", id=digest, path="bench.png", box=(0.1, 0.2, 0.3, 0.4)),
            Ref(kind="invocation", id="42"),
        ],
    )
    assert seen.region.region == "shape 1" and seen.node is None
    assert model.key() == "qmcp/m@1"
    assert Origin(kind="guessed", by={"name": "qmcp", "tool": "vision.observe"}).key() == "qmcp"
    assert Origin(kind="measured", by="printer poll").by.name == "printer poll"
    assert Origin(kind="stated", by="a person").key() == "person"
    assert seen.model_dump(mode="json")["evidence"][1] == {"kind": "invocation", "id": "42"}
    for bad in (
        lambda: Region(picture="x", region="r", box=(0, 0, 1, 1)),
        lambda: Region(picture=digest, region="r", box=(0.5, 0, 0.2, 1)),
        lambda: Ref(kind="picture", id="not a digest"),
        lambda: Ref(kind="poll", id="p", path="a.png"),
    ):
        with pytest.raises(ValueError):
            bad()


def _stated(key, value="red"):
    return Observation(
        subject=Sighting(
            sighting=Region(picture="a" * 64, region=kept.region(key[2]), box=(0, 0, 1, 1))
        ),
        property="colour",
        value=value,
        origin=Origin(kind="stated", by={"name": "a person, on the page"}),
        at="2026-10-31T00:00:00+00:00",
        recorded_at=datetime(2026, 10, 31, tzinfo=timezone.utc),
    )


def _holds(key):
    return any(row["person"] for row in kept.about(key)["rows"])


def test_the_kept_observations_are_bounded_and_the_least_recently_used_key_goes_first(monkeypatch):
    kept.forget_all()
    monkeypatch.setattr(kept, "KEPT_MOST", 3)
    keys = [("garage", "v", i) for i in range(5)]
    for key in keys[:3]:
        kept._keep(key, [_stated(key)])
    assert _holds(keys[0])  # read again: now the newest
    kept._keep(keys[3], [_stated(keys[3])])
    kept._keep(keys[4], [_stated(keys[4])])
    assert [_holds(k) for k in keys] == [True, False, False, True, True]
    kept.forget_all()
    assert not any(_holds(k) for k in keys)


def test_a_qmcp_that_hangs_costs_one_deadline_and_one_call(client, monkeypatch):
    import time

    from apothecary.finders.simulated import SimulatedQmcp

    calls = []

    def hang(self, tool, arguments):
        calls.append(tool)
        time.sleep(1.5)
        return {}

    monkeypatch.setattr(SimulatedQmcp, "call", hang)
    monkeypatch.setenv(qmcp.ENV, "simulated")
    monkeypatch.setattr(qmcp, "DEADLINE_MS", 200)
    started = time.monotonic()
    answer = _ask(client, _red(client), ["colour"])
    elapsed = time.monotonic() - started
    assert "not answering" in answer["said"]
    assert len(calls) == 1
    assert elapsed < 0.2 + 0.15
