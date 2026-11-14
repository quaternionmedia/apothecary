"""The tour (apothecary/tour.py): the roadmap's lines in its order, each naming a journey
whose stages are stops or walkthrough pages that are; every page a test writes read back
as the steps it recorded; and a person's word on a stop kept, read back by the box and by
`apothecary tour`. The box that shows it is tests/e2e/test_tour.py's."""

from __future__ import annotations

import json
import re

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from apothecary import journeys, tour
from apothecary.api import app
from apothecary.cli.main import cli
from apothecary.docs_site import WALKTHROUGH_ROOT

ROUTER = "31-what-the-router-needs.md"
SHAPE = "journey:make/shape"


@pytest.fixture
def kept(tmp_path, monkeypatch):
    """A state folder of the test's own: the answers it keeps are its."""
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state" / "tour" / "answers.jsonl"


# --- the reader -------------------------------------------------------------------------


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
    part = tour.stop("07-a-part.md")
    assert part.written_by is None and part.steps == ()
    assert part.intro.startswith("A part is a folder, a SCAD file named after it")
    assert tour.stop("00-getting-started.md").intro.startswith("Four steps take a fresh clone")


# --- the roadmap ------------------------------------------------------------------------


def test_the_roadmap_names_every_page_once_and_only_what_is_there():
    """Every walkthrough page is named by one line of the roadmap, no page twice, and
    every journey and page a line names is one there is."""
    lines = tour.roadmap()
    named = [page for line in lines for page in line.pages]
    pages = sorted(p.name for p in WALKTHROUGH_ROOT.glob("[0-9][0-9]-*.md"))
    assert sorted(named) == pages
    assert tour.document()["not_on_the_roadmap"] == []
    known = {j.id for j in journeys.JOURNEYS}
    assert {line.journey for line in lines if line.journey} <= known
    assert all(line.journey or line.pages for line in lines)  # none shown by nothing


def test_the_roadmap_orders_the_tour_and_photographs_are_last():
    """The tour's stops are the roadmap's lines in its order: a part designed before a
    thing made, and the photographs after everything else."""
    doc = tour.document()
    groups = [line["group"] for line in doc["lines"]]
    assert list(dict.fromkeys(groups)) == [
        "Starting",
        "Designing a part",
        "Making a thing",
        "The site and the page",
        "Photographs",
    ]
    ids = tour.stop_ids()
    assert ids[0] == "page:00-getting-started.md"
    photographs = [s["id"] for line in doc["lines"] if line["group"] == "Photographs" for s in line["stops"]]
    assert "page:01-photographs-into-pieces.md" in photographs
    assert ids[-len(photographs) :] == photographs
    assert ids.index("page:04-designing-a-part.md") < ids.index(SHAPE) < ids.index(photographs[0])


def test_a_line_that_names_a_journey_has_its_stages_as_stops_with_what_to_try():
    """Make a thing's line: each stage a stop, its words the rail's own, and what to try
    on it the recorded steps the stage names."""
    make = next(line for line in tour.document()["lines"] if line["text"].startswith("A part is chosen"))
    assert [(s["kind"], s["stage"], s["title"]) for s in make["stops"]] == [
        ("stage", s.id, s.label) for s in journeys.MAKE.steps
    ]
    shape = next(s for s in make["stops"] if s["id"] == SHAPE)
    assert shape["words"] == "its numbers, in Parameters" and shape["put_on"] is True
    assert [(t["page"], t["index"]) for t in shape["tries"]] == [
        ("04-designing-a-part.md", 2),
        ("04-designing-a-part.md", 3),
    ]
    assert shape["tries"][0]["heading"] == "A size dragged is checked once the slider rests"
    # Every step a stage names is one a page has.
    for stage in journeys.MAKE.steps:
        assert len(tour._tries(stage.shown_by, WALKTHROUGH_ROOT)) == len(stage.shown_by), stage.id


def test_a_line_that_names_nothing_is_shown_by_nothing(tmp_path):
    road = tmp_path / "ROADMAP.md"
    road.write_text(
        "## Later\n\n- [ ] A thing nobody can see yet.\n"
        "- [x] The router. [31](../walkthrough/31-what-the-router-needs.md)\n",
        encoding="utf-8",
    )
    lines = tour.document(road)["lines"]
    assert [(line["text"], line["ticked"], line["shown_by_nothing"]) for line in lines] == [
        ("A thing nobody can see yet.", False, True),
        ("The router.", True, False),
    ]
    assert [s["id"] for s in lines[1]["stops"]] == [f"page:{ROUTER}"]
    assert lines[1]["stops"][0]["kind"] == "page" and len(lines[1]["stops"][0]["tries"]) == 7


# --- answers ----------------------------------------------------------------------------


def test_an_answer_is_kept_with_the_commit_and_the_latest_is_the_stop_s(kept):
    client = TestClient(app)
    said = client.post("/tour/answers", json={"stop": SHAPE, "verdict": "as shown"})
    assert said.status_code == 201
    first = said.json()
    assert first["stop"] == SHAPE and first["verdict"] == "as shown"
    assert first["commit"] == tour.running()["commit"] and first["at"]
    again = {"stop": SHAPE, "verdict": "off", "note": "the slider is below the fold"}
    assert client.post("/tour/answers", json=again).status_code == 201
    lines = kept.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["verdict"] for line in lines] == ["as shown", "off"]  # both kept
    doc = client.get("/tour").json()
    stops = {s["id"]: s for line in doc["lines"] for s in line["stops"]}
    assert stops[SHAPE]["answer"]["verdict"] == "off"
    assert stops[SHAPE]["answer"]["note"] == "the slider is below the fold"
    assert [i for i, s in stops.items() if s["answer"]] == [SHAPE]
    assert doc["commit"] == tour.running()["commit"]


def test_a_page_is_one_stop_answered_whole(kept):
    said = {"stop": f"page:{ROUTER}", "verdict": "as shown"}
    assert TestClient(app).post("/tour/answers", json=said).status_code == 201
    assert tour.answers()[f"page:{ROUTER}"]["verdict"] == "as shown"


@pytest.mark.parametrize(
    "said, status, why",
    [
        ({"stop": "page:99-nowhere.md", "verdict": "as shown"}, 404, "has no stop"),
        ({"stop": "journey:make/polish", "verdict": "as shown"}, 404, "has no stop"),
        ({"stop": SHAPE, "verdict": "fine"}, 422, "an answer is one of"),
        ({"stop": SHAPE, "verdict": "off", "note": "  "}, 422, "say what is off"),
    ],
)
def test_what_the_tour_does_not_keep_is_refused_saying_why(kept, said, status, why):
    answered = TestClient(app).post("/tour/answers", json=said)
    assert answered.status_code == status
    assert why in answered.json()["detail"]
    assert not kept.exists()


def test_a_line_that_does_not_read_is_left_out(kept):
    tour.say(SHAPE, "as shown")
    with kept.open("a", encoding="utf-8") as out:
        out.write("not an answer\n" + json.dumps({"stop": SHAPE}) + "\n")
    assert [r["stop"] for r in tour.said()] == [SHAPE]


def test_apothecary_tour_reads_back_what_was_said(kept):
    tour.say(SHAPE, "as shown")
    tour.say("journey:make/see", "off", "the path is drawn under the bed")
    shown = CliRunner().invoke(cli, ["tour"])
    assert shown.exit_code == 0, shown.output
    lines = shown.output.splitlines()
    at = lines.index("Making a thing")
    assert lines[at + 1] == (
        "  A part is chosen, shaped, sliced, seen and printed on a machine. "
        "1 as shown, 1 off, 3 not yet"
    )
    assert lines[at + 2].startswith("    ✓ Shape (")
    assert lines[at + 3].startswith("    ✗ See: the path is drawn under the bed (")
    assert lines.index("Photographs") > at
    off = CliRunner().invoke(cli, ["tour", "--off"])
    assert [line for line in off.output.splitlines() if line.startswith("    ")] == [lines[at + 3]]
    assert "Designing a part" not in off.output
