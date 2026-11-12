"""The tour (apothecary/tour.py): every walkthrough page read back as a stop, each page a
test writes as the steps it recorded, and a person's word on a step kept, read back by
the page and by `apothecary tour`. The window that shows it is tests/e2e/test_tour.py's."""

from __future__ import annotations

import json
import re

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from apothecary import tour
from apothecary.api import app
from apothecary.cli.main import cli
from apothecary.docs_site import WALKTHROUGH_ROOT

ROUTER = "31-what-the-router-needs.md"


@pytest.fixture
def kept(tmp_path, monkeypatch):
    """A state folder of the test's own: the verdicts it keeps are its."""
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state" / "tour" / "verdicts.jsonl"


def test_every_page_a_test_writes_is_its_steps_with_the_pictures_it_recorded():
    """Each page a test writes is read back as every numbered step it holds, in order,
    each with its words, and its picture where it has one, a file that is there."""
    written = [s for s in tour.stops() if s.written_by]
    assert written
    for stop in written:
        text = (WALKTHROUGH_ROOT / stop.page).read_text(encoding="utf-8")
        assert len(stop.steps) == len(re.findall(r"^## \d+\. ", text, re.MULTILINE)), stop.page
        assert [s.index for s in stop.steps] == list(range(1, len(stop.steps) + 1)), stop.page
        assert stop.intro and all(s.heading and s.words for s in stop.steps), stop.page
        pictures = [s.picture for s in stop.steps if s.picture]
        assert len(pictures) == text.count("](screenshots/"), stop.page
        for picture in pictures:
            assert (WALKTHROUGH_ROOT / picture).is_file(), (stop.page, picture)


def test_a_step_is_its_heading_words_picture_and_what_it_showed():
    first = tour.stop(ROUTER).steps[0]
    assert first.heading == "In alarm, Needs you says what clears it"
    assert first.words.startswith("cnc_router selected in Site, Open in its Device line")
    assert first.picture == "screenshots/31-01-in-alarm-needs-you-says-what-clears-it.png"
    pins = tour.stop("32-a-quiet-board-and-a-router-s-pins.md").steps[1]
    assert pins.picture is None and pins.shown == "pins\tX · Z\tmeasured by its poll\tnow"


def test_a_page_written_by_hand_is_read_whole_from_its_first_words():
    """A page no test writes has no steps; its words are its first paragraph past the
    one saying how it runs."""
    part = tour.stop("07-a-part.md")
    assert part.written_by is None and part.steps == ()
    assert part.intro.startswith("A part is a folder, a SCAD file named after it")
    assert tour.stop("00-getting-started.md").intro.startswith("Four steps take a fresh clone")


def test_every_page_is_a_stop_in_order():
    pages = sorted(p.name for p in WALKTHROUGH_ROOT.glob("[0-9][0-9]-*.md"))
    assert [s.page for s in tour.stops()] == pages


def test_a_verdict_is_kept_with_the_commit_and_the_latest_is_the_step_s_answer(kept):
    client = TestClient(app)
    said = client.post("/tour/verdicts", json={"page": ROUTER, "step": 2, "verdict": "as shown"})
    assert said.status_code == 201
    first = said.json()
    assert first["page"] == ROUTER and first["step"] == 2 and first["verdict"] == "as shown"
    assert first["commit"] == tour.running()["commit"] and first["at"]
    again = {"page": ROUTER, "step": 2, "verdict": "off", "note": "the card is below the fold"}
    assert client.post("/tour/verdicts", json=again).status_code == 201
    lines = kept.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["verdict"] for line in lines] == ["as shown", "off"]  # both kept
    doc = client.get("/tour").json()
    router = next(s for s in doc["stops"] if s["page"] == ROUTER)
    assert router["answers"]["2"]["verdict"] == "off"
    assert router["answers"]["2"]["note"] == "the card is below the fold"
    assert set(router["answers"]) == {"2"}
    assert doc["commit"] == tour.running()["commit"]


def test_a_page_read_whole_is_answered_as_its_step_0(kept):
    client = TestClient(app)
    said = {"page": "07-a-part.md", "step": 0, "verdict": "as shown"}
    assert client.post("/tour/verdicts", json=said).status_code == 201
    assert tour.answers()[("07-a-part.md", 0)]["verdict"] == "as shown"


@pytest.mark.parametrize(
    "said, status, why",
    [
        ({"page": "99-nowhere.md", "step": 1, "verdict": "as shown"}, 404, "no walkthrough page"),
        ({"page": ROUTER, "step": 99, "verdict": "as shown"}, 422, "has no step 99"),
        ({"page": ROUTER, "step": 0, "verdict": "as shown"}, 422, "has no step 0"),
        ({"page": ROUTER, "step": 1, "verdict": "fine"}, 422, "a verdict is one of"),
        ({"page": ROUTER, "step": 1, "verdict": "off", "note": "  "}, 422, "say what is off"),
    ],
)
def test_what_the_tour_does_not_keep_is_refused_saying_why(kept, said, status, why):
    answered = TestClient(app).post("/tour/verdicts", json=said)
    assert answered.status_code == status
    assert why in answered.json()["detail"]
    assert not kept.exists()


def test_a_line_that_does_not_read_is_left_out(kept):
    tour.say(ROUTER, 1, "as shown")
    with kept.open("a", encoding="utf-8") as out:
        out.write("not a verdict\n" + json.dumps({"page": ROUTER}) + "\n")
    assert [r["step"] for r in tour.said()] == [1]


def test_apothecary_tour_reads_back_what_was_said(kept):
    tour.say(ROUTER, 1, "as shown")
    tour.say(ROUTER, 3, "off", "Z's line is cut off")
    shown = CliRunner().invoke(cli, ["tour", "--page", "31"])
    assert shown.exit_code == 0, shown.output
    lines = shown.output.splitlines()
    assert lines[0] == "31 What the router needs: 1 as shown, 1 off, 5 not yet"
    assert lines[1].startswith("  ✓ 1. In alarm, Needs you says what clears it (")
    assert lines[2].startswith(
        "  ✗ 3. Each axis's home, beside its button: not proved, and what to do first: "
        "Z's line is cut off ("
    )
    off = CliRunner().invoke(cli, ["tour", "--off"])
    assert [line for line in off.output.splitlines() if line.startswith("  ")] == [lines[2]]
    nowhere = CliRunner().invoke(cli, ["tour", "--page", "99"])
    assert nowhere.exit_code != 0 and "no walkthrough page 99" in nowhere.output
