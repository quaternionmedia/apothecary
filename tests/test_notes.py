"""A whiteboard's notes: its writing kept with what it is about, a person's words
for it, a size offered for the line it is beside (apothecary/vision/notes.py), and
the way out to looksatwords and qmcp (apothecary/finders/words.py). Nothing here leaves this process: the two
that would answer are stood in for."""

from __future__ import annotations

import json
import urllib.error

import pytest
from click.testing import CliRunner
from PIL import Image, ImageDraw, ImageFont

from apothecary.cli.main import cli
from apothecary.finders import words
from apothecary.vision import marks, notes

BLUE, BLACK = (20, 30, 120), (10, 10, 10)


@pytest.fixture
def whiteboard(tmp_path):
    """A plate with its name written in it, a dimension line 450 pixels long of
    a picture 1600 wide with its size written under it, and a remark far off."""
    image = Image.new("RGB", (1600, 1200), (238, 238, 236))
    pen = ImageDraw.Draw(image)
    pen.rectangle((250, 250, 700, 520), outline=BLUE, width=9)
    pen.text((380, 360), "top plate", fill=BLACK, font=ImageFont.load_default(size=40))
    pen.line((250, 590, 700, 590), fill=BLACK, width=5)
    pen.text((400, 605), "120 mm", fill=BLACK, font=ImageFont.load_default(size=44))
    pen.text((900, 1050), "ask about the hinge", fill=BLACK, font=ImageFont.load_default(size=40))
    path = tmp_path / "whiteboard.png"
    image.save(path)
    return path


def _listed(path, answers=None):
    found = marks.marks_in(path, answers)
    return found, notes.notes_of(found, answers, tallness=1200 / 1600)


def _at(found, listed, x, y):
    over = [
        m
        for m in found
        if m.min_point.x <= x / 1600 <= m.max_point.x and m.min_point.y <= y / 1200 <= m.max_point.y
    ]
    mark = min(over, key=lambda m: m.max_point.x - m.min_point.x)
    return mark, next((n for n in listed if n.id == mark.id), None)


def test_each_line_of_writing_is_a_note_about_what_it_is_in_or_nearest(whiteboard):
    found, listed = _listed(whiteboard)
    assert len(listed) == 3 and all(note.words is None and note.offer is None for note in listed)
    plate, _ = _at(found, listed, 252, 400)
    line, _ = _at(found, listed, 475, 590)
    _, name = _at(found, listed, 470, 385)
    _, size = _at(found, listed, 470, 630)
    _, remark = _at(found, listed, 1100, 1075)
    assert (name.about, name.lies) == (plate.id, "inside")
    assert (size.about, size.lies) == (line.id, "beside")
    assert (remark.about, remark.lies) == (None, None)


def test_a_persons_words_are_kept_and_a_size_beside_a_line_is_offered(whiteboard):
    found, listed = _listed(whiteboard)
    line, _ = _at(found, listed, 475, 590)
    size_mark, _ = _at(found, listed, 470, 630)
    name_mark, _ = _at(found, listed, 470, 385)
    answers = marks.Answers(
        words=[
            notes.say(found, size_mark.id, " 120 mm "),
            notes.say(found, name_mark.id, "top plate"),
        ]
    )
    found, listed = _listed(whiteboard, answers)
    _, size = _at(found, listed, 470, 630)
    _, name = _at(found, listed, 470, 385)
    assert (size.words, size.by) == ("120 mm", "you")
    # The line is 450 pixels of 1600: at 120 mm long, the picture is 427 mm across.
    assert size.offer.of == line.id and size.offer.millimetres == 120.0
    assert size.offer.picture_mm == pytest.approx(120 * 1600 / 450, rel=0.03)
    # Words inside a shape state no line's length.
    assert name.words == "top plate" and name.offer is None


@pytest.mark.parametrize(
    "typed, millimetres",
    [
        ("12 cm", 120.0),
        ("0,5 m", 500.0),
        ('4"', 101.6),
        ("4 in", 101.6),
        ("about 120", None),
        ("M3 x 4", None),
    ],
)
def test_a_size_is_a_number_and_a_unit_at_the_start(whiteboard, typed, millimetres):
    found, listed = _listed(whiteboard)
    size_mark, _ = _at(found, listed, 470, 630)
    _, listed = _listed(whiteboard, marks.Answers(words=[notes.say(found, size_mark.id, typed)]))
    offer = next(n for n in listed if n.id == size_mark.id).offer
    assert (offer.millimetres if offer else None) == millimetres


def test_words_are_for_writing_and_are_not_empty(whiteboard):
    found, listed = _listed(whiteboard)
    plate, _ = _at(found, listed, 252, 400)
    size_mark, _ = _at(found, listed, 470, 630)
    with pytest.raises(ValueError, match="is diagram, not writing"):
        notes.say(found, plate.id, "a plate")
    with pytest.raises(ValueError, match="these are empty"):
        notes.say(found, size_mark.id, "   ")
    with pytest.raises(KeyError, match="no mark 'm99'"):
        notes.say(found, "m99", "x")


def _typed(whiteboard):
    found, listed = _listed(whiteboard)
    size_mark, _ = _at(found, listed, 470, 630)
    remark_mark, _ = _at(found, listed, 1100, 1075)
    answers = marks.Answers(
        words=[
            notes.say(found, size_mark.id, "120 mm"),
            notes.say(found, remark_mark.id, "ask about the hinge"),
        ]
    )
    return _listed(whiteboard, answers)[1], size_mark, remark_mark


def test_the_transcript_is_the_typed_notes_in_reading_order(whiteboard):
    listed, size_mark, remark_mark = _typed(whiteboard)
    lines = notes.transcript(listed).splitlines()
    assert len(lines) == 2, "the note nobody typed is left out"
    assert lines[0].startswith(f"{size_mark.id} (beside ") and lines[0].endswith(": 120 mm")
    assert lines[1] == f"{remark_mark.id}: ask about the hinge"


def test_the_words_go_to_looksatwords_on_this_machine_and_nowhere_else(whiteboard):
    listed, _, _ = _typed(whiteboard)
    sent = []

    def post(address, body):
        sent.append((address, body))
        return {"conversation_id": 7}

    base, answer = words.send_to_looksatwords(listed, "whiteboard", post=post)
    assert base == words.LOOKSATWORDS and answer == {"conversation_id": 7}
    ((address, body),) = sent
    assert address == "http://127.0.0.1:1414/api/conversations/analyze"
    assert body == {"text": notes.transcript(listed), "title": "whiteboard"}

    with pytest.raises(words.NotServing, match="is not on this machine"):
        words.send_to_looksatwords(
            listed, "whiteboard", address="http://words.example:1414", post=post
        )
    assert len(sent) == 1, "nothing was posted to an address off this machine"

    def down(address, body):
        raise urllib.error.URLError("connection refused")

    with pytest.raises(words.NotServing, match="looksatwords is not answering.*looksatwords serve"):
        words.send_to_looksatwords(listed, "whiteboard", post=down)
    with pytest.raises(ValueError, match="no note has words yet"):
        words.send_to_looksatwords(_listed(whiteboard)[1], "whiteboard", post=post)


def test_qmcp_is_asked_about_the_notes_nobody_typed_and_its_word_is_kept_beside(whiteboard):
    """qmcp answers which of some given words a region holds. Its answer is a
    note's ``read``; a note a person typed is not asked about and keeps its words."""
    from datetime import datetime, timezone

    from apothecary.evidence.observation import Observation, Origin, Region, Sighting

    listed, size_mark, _ = _typed(whiteboard)
    untyped = [note for note in listed if not note.words]
    assert len(untyped) == 1
    asked = []

    def ask(request):
        asked.append(request)
        when = datetime.now(timezone.utc)
        (region,) = request["regions"]
        seen = Observation(
            subject=Sighting(
                sighting=Region(
                    picture=request["picture"]["sha256"],
                    region=region["id"],
                    box=tuple(region["box"]),
                )
            ),
            property="label",
            value="top plate",
            confidence=0.6,
            origin=Origin(kind="guessed", by={"name": "qmcp", "tool": "vision.observe"}),
            at=when,
            recorded_at=when,
        )
        return [seen], "qmcp answered 1 of 1"

    after, happened = words.ask_qmcp(whiteboard, listed, ["top plate", "lid"], ask=ask)
    assert happened == "qmcp answered 1 of 1"
    (request,) = asked
    assert [r["id"] for r in request["regions"]] == [untyped[0].id]
    assert request["asked"] == [{"property": "label", "among": ["lid", "top plate"]}]
    read = next(n for n in after if n.id == untyped[0].id)
    assert read.read == "top plate" and read.words is None
    typed = next(n for n in after if n.id == size_mark.id)
    assert typed.words == "120 mm" and typed.read is None
    assert "top plate" in notes.transcript(after)
    with pytest.raises(ValueError, match="give the words it may be with --among"):
        words.ask_qmcp(whiteboard, listed, [], ask=ask)


def test_with_no_qmcp_configured_asking_says_so_and_keeps_nothing(whiteboard, monkeypatch):
    from apothecary.finders import qmcp

    monkeypatch.delenv(qmcp.ENV, raising=False)
    listed = _listed(whiteboard)[1]
    after, happened = words.ask_qmcp(whiteboard, listed, ["lid"])
    assert "qmcp is not configured" in happened and all(note.read is None for note in after)


def test_photo_notes_types_lists_offers_and_refuses(whiteboard, monkeypatch):
    found, listed = _listed(whiteboard)
    size_mark, _ = _at(found, listed, 470, 630)
    plate, _ = _at(found, listed, 252, 400)
    done = CliRunner().invoke(
        cli, ["photo", "notes", str(whiteboard), "--say", f"{size_mark.id}=120 mm"]
    )
    assert done.exit_code == 0, done.output
    assert '"120 mm", typed by you' in done.output and "not typed" in done.output
    assert "mm across: photo build --width-mm" in done.output
    kept = json.loads(marks.answers_path(whiteboard).read_text(encoding="utf-8"))
    assert [w["text"] for w in kept["words"]] == ["120 mm"]
    as_json = CliRunner().invoke(cli, ["photo", "notes", str(whiteboard), "--json"])
    assert sum(1 for n in json.loads(as_json.output) if n["words"]) == 1
    refused = CliRunner().invoke(
        cli, ["photo", "notes", str(whiteboard), "--say", f"{plate.id}=a plate"]
    )
    assert refused.exit_code != 0 and "not writing" in refused.output
    monkeypatch.setenv(words.LOOKSATWORDS_ENV, "http://words.example:1414")
    away = CliRunner().invoke(cli, ["photo", "notes", str(whiteboard), "--send"])
    assert away.exit_code != 0 and "is not on this machine" in away.output
    no_words = CliRunner().invoke(cli, ["photo", "notes", str(whiteboard), "--ask"])
    assert no_words.exit_code != 0 and "--among" in no_words.output
