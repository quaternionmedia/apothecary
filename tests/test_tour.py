"""The tour (apothecary/tour.py): the journeys in their order, each stage with its own
words and what it names to try, read back from the walkthrough's pages; and a person's
word on a stage kept, given back by the box's routes. The box that shows it is
tests/e2e/test_tour.py's."""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from apothecary import journeys, tour
from apothecary.api import app
from apothecary.cli.main import cli
from apothecary.docs_site import WALKTHROUGH_ROOT

ROUTER = "31-what-the-router-needs.md"
SHAPE = "make/shape"
BY = "Ada"


@pytest.fixture
def kept(tmp_path, monkeypatch):
    """A state folder of the test's own: the feedback it keeps is its."""
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state" / "tour" / "feedback.jsonl"


# --- the reader -------------------------------------------------------------------------


def test_every_page_a_module_writes_is_its_steps_with_the_pictures_kept_with_them():
    """Each page a module writes is read back as every numbered step it holds, in order,
    each with its words, and its picture where it has one, a file that is there."""
    written = [p for p in tour.pages() if p.written_by]
    assert written
    for page in written:
        text = (WALKTHROUGH_ROOT / page.page).read_text(encoding="utf-8")
        assert len(page.steps) == len(re.findall(r"^## \d+\. ", text, re.MULTILINE)), page.page
        assert [s.index for s in page.steps] == list(range(1, len(page.steps) + 1)), page.page
        assert page.intro and all(s.heading and s.words for s in page.steps), page.page
        pictures = [s.picture for s in page.steps if s.picture]
        assert len(pictures) == text.count("](screenshots/"), page.page
        for picture in pictures:
            assert (WALKTHROUGH_ROOT / picture).is_file(), (page.page, picture)


def test_a_step_is_its_heading_words_picture_and_what_it_showed():
    first = tour.page(ROUTER).steps[0]
    assert first.heading == "In alarm, Needs you says what clears it"
    assert first.words.startswith("cnc_router selected in Site, Open in its Device line")
    assert first.picture == "screenshots/31-01-in-alarm-needs-you-says-what-clears-it.png"
    pins = tour.page("32-a-quiet-board-and-a-router-s-pins.md").steps[1]
    assert pins.picture is None and pins.shown == "pins\tX · Z\tmeasured by its poll\tnow"


def test_a_page_written_by_hand_is_read_whole_from_its_first_words():
    part = tour.page("07-a-part.md")
    assert part.written_by is None and part.steps == ()
    assert part.intro.startswith("A part is a folder, a SCAD file named after it")
    assert tour.page("00-getting-started.md").intro.startswith("Four steps take a fresh clone")
    assert tour.page("99-nowhere.md") is None


# --- the stages -------------------------------------------------------------------------


def test_the_tour_is_the_journeys_in_the_chain_s_order_a_stage_at_a_time():
    """The document the box reads: every journey in the registry's order -- a part
    designed, made, cut, its board, hands on it, the site brought up and watched, and a
    drawing to pieces last -- each stage with the rail's own words."""
    doc = tour.document()
    assert [j["id"] for j in doc["journeys"]] == [j.id for j in journeys.JOURNEYS]
    assert doc["journeys"][0]["id"] == "design" and doc["journeys"][-1]["id"] == "drawing"
    make = next(j for j in doc["journeys"] if j["id"] == "make")
    assert make["name"] == "Print a part"
    assert [(s["id"], s["stage"], s["title"], s["words"]) for s in make["stages"]] == [
        (f"make/{s.id}", s.id, s.label, s.hint) for s in journeys.MAKE.steps
    ]
    assert tour.stage_ids() == [s["id"] for j in doc["journeys"] for s in j["stages"]]
    assert doc["commit"] == tour.running()["commit"]


def test_a_stage_carries_what_it_names_to_try():
    """Print a part's Shape: what to try on it is the two steps of page 04 it names,
    each with its heading and its picture."""
    make = next(j for j in tour.document()["journeys"] if j["id"] == "make")
    shape = next(s for s in make["stages"] if s["id"] == SHAPE)
    assert shape["words"] == "its numbers, in Parameters"
    assert [(t["page"], t["index"]) for t in shape["tries"]] == [
        ("04-designing-a-part.md", 2),
        ("04-designing-a-part.md", 3),
    ]
    assert shape["tries"][0]["heading"] == "A size dragged is checked once the slider rests"
    assert shape["tries"][0]["picture"].startswith("screenshots/04-02-")


def test_every_stage_names_steps_and_pages_there_are():
    for journey in journeys.JOURNEYS:
        for stage in journey.steps:
            tries = tour._tries(stage.shown_by, WALKTHROUGH_ROOT)
            assert len(tries) == len(stage.shown_by), (journey.id, stage.id)
            assert len(set(stage.shown_by)) == len(stage.shown_by), (journey.id, stage.id)


def test_a_page_a_stage_names_whole_is_a_link_to_the_page():
    """Cut a part's Choose names page 20, which no module writes: what to try there is
    the page itself, by its title, with no step and no picture."""
    (whole,) = tour._tries(journeys.CUT.steps[0].shown_by, WALKTHROUGH_ROOT)
    assert (whole["page"], whole["index"], whole["picture"]) == (
        "20-a-part-through-the-router.md",
        None,
        None,
    )
    assert whole["heading"].startswith("20 — ") and whole["words"]


# --- feedback ---------------------------------------------------------------------------


def test_a_word_is_kept_with_the_commit_and_the_latest_is_the_stage_s(kept):
    client = TestClient(app)
    said = client.post("/tour/feedback", json={"stage": SHAPE, "verdict": "works", "by": BY})
    assert said.status_code == 201
    first = said.json()
    assert (first["stage"], first["verdict"], first["by"]) == (SHAPE, "works", BY)
    assert first["commit"] == tour.running()["commit"] and first["at"]
    again = {"stage": SHAPE, "verdict": "off", "note": "the slider is below the fold", "by": BY}
    assert client.post("/tour/feedback", json=again).status_code == 201
    lines = kept.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["verdict"] for line in lines] == ["works", "off"]  # both kept
    doc = client.get("/tour").json()
    stages = {s["id"]: s for j in doc["journeys"] for s in j["stages"]}
    assert stages[SHAPE]["feedback"]["verdict"] == "off"
    assert stages[SHAPE]["feedback"]["note"] == "the slider is below the fold"
    assert [i for i, s in stages.items() if s["feedback"]] == [SHAPE]


def test_every_word_kept_is_given_back_oldest_first(kept):
    client = TestClient(app)
    assert client.get("/tour/feedback").json() == {"feedback": []}
    tour.say(SHAPE, "works", by=BY)
    tour.say("make/see", "off", "the path is drawn under the bed", by=BY)
    tour.say(SHAPE, "off", "the slider is below the fold", by="  Grace  ")
    given = client.get("/tour/feedback").json()["feedback"]
    assert [(r["stage"], r["verdict"], r["note"]) for r in given] == [
        (SHAPE, "works", ""),
        ("make/see", "off", "the path is drawn under the bed"),
        (SHAPE, "off", "the slider is below the fold"),
    ]
    assert [r["by"] for r in given] == [BY, BY, "Grace"]
    assert all(
        set(r) == {"stage", "verdict", "note", "by", "at", "commit", "changed"} for r in given
    )


@pytest.mark.parametrize(
    "said, status, why",
    [
        ({"stage": "make/polish", "verdict": "works", "by": BY}, 404, "no journey has a stage"),
        (
            {"stage": "33-windows-kept-over-a-reload.md", "verdict": "works", "by": BY},
            404,
            "no journey",
        ),
        ({"stage": SHAPE, "verdict": "fine", "by": BY}, 422, "feedback is one of"),
        ({"stage": SHAPE, "verdict": "off", "note": "  ", "by": BY}, 422, "say what is off"),
        ({"stage": SHAPE, "verdict": "works"}, 422, "say who is saying it"),
        ({"stage": SHAPE, "verdict": "works", "by": "   "}, 422, "say who is saying it"),
    ],
)
def test_what_the_tour_does_not_keep_is_refused_saying_why(kept, said, status, why):
    answered = TestClient(app).post("/tour/feedback", json=said)
    assert answered.status_code == status
    assert why in answered.json()["detail"]
    assert not kept.exists()


def test_a_line_that_does_not_read_is_left_out(kept):
    tour.say(SHAPE, "works", by=BY)
    with kept.open("a", encoding="utf-8") as out:
        out.write("not feedback\n" + json.dumps({"stage": SHAPE}) + "\n")
    assert [r["stage"] for r in tour.said()] == [SHAPE]


def test_a_word_is_of_the_build_it_was_said_of(kept, monkeypatch):
    """A word said while the server ran another commit is still the stage's latest, and
    is not current: the stage waits for a word again. One said of this commit is. A
    server that cannot say its commit ties no word to a build, and each counts."""
    tour.say(SHAPE, "works", by=BY)
    earlier = {**tour.said()[0], "stage": "make/see", "commit": "0000000"}
    with kept.open("a", encoding="utf-8") as out:
        out.write(json.dumps(earlier) + "\n")

    def latest():
        make = next(j for j in tour.document()["journeys"] if j["id"] == "make")
        return {s["stage"]: s["feedback"] for s in make["stages"]}

    assert latest()["shape"]["current"] is True
    assert latest()["see"]["current"] is False and latest()["see"]["commit"] == "0000000"
    assert latest()["choose"] is None
    assert "current" not in tour.said()[1]  # reckoned when read, never kept
    monkeypatch.setattr(tour, "running", lambda: {"commit": None, "changed": None})
    assert latest()["see"]["current"] is True


def test_what_a_roadmap_claims_is_not_read_here():
    """The app keeps journeys and feedback; the roadmap is the project's, on its branch
    of the governance corpus, and its review is `qmcp tour`, so there is no
    `apothecary tour`."""
    assert "tour" not in cli.commands
    assert not hasattr(tour, "roadmap")
