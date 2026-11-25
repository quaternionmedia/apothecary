"""parts/badge: a face or a word engraved in a plate, composed in the Badge window.

A face is made on either machine, its cuts the strokes and holes its SCAD draws; a word
is printed alone, its toolpath refused in words. The faces and the word are the part's
presets. Walkthrough page 57 goes through the same at the command line."""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.cam import toolpath
from apothecary.cam.models import Disc, Groove, Hole
from apothecary.machine_plans import kinds_that_make
from apothecary.projects.parts import badge
from apothecary.projects.parts.badge import DEFAULT, FACES, FONTS, PRESETS, Params, Refused
from apothecary.projects.parts.base import scad_variables

client = TestClient(app)


def test_the_model_and_the_scad_name_the_same_variables_and_start_in_the_same_place():
    """Every field is a variable of the SCAD's, and the SCAD as saved is the model's default
    (`apothecary problems` names any value where they disagree)."""
    declared = scad_variables(DEFAULT.source_file)
    assert set(Params.model_fields) <= declared
    text = DEFAULT.source_file.read_text(encoding="utf-8")
    defaults = Params()
    for name in ("diameter", "width", "height", "text_size", "thickness", "depth", "stroke"):
        assert re.search(rf"^{name} = {getattr(defaults, name):g};", text, re.M), name
    for name in ("kind", "face", "text", "font"):
        assert f'{name} = "{getattr(defaults, name)}";' in text, name
    # The SCAD's shares of the radius are the wrapper's, and so are its arcs' angles.
    shares = ("EYE_OUT", "EYE_UP", "EYE", "MOUTH_DOWN", "MOUTH", "ARC", "ARC_SEGMENTS")
    for share in (*shares, "FROWN_DOWN", "LINE_HALF", "LINE_DOWN"):
        assert re.search(rf"\b{share} = {getattr(badge, share):g};", text), share
    wrapper = Path(badge.__file__).read_text(encoding="utf-8")
    assert _arcs(text) == _arcs(wrapper) and len(_arcs(text)) == 3


def _arcs(source: str) -> list:
    """Each arc's two angles, as a SCAD or its wrapper writes them."""
    return sorted(re.findall(r"arc\([^;\n]*?(\d+), (\d+)\)", source))


def test_its_presets_are_each_face_and_the_word():
    assert list(PRESETS) == [*FACES, "word"]
    for face, emoji in FACES.items():
        preset = PRESETS[face]
        assert preset.params == {"kind": "face", "face": face}
        assert preset.label.startswith(emoji) and len(preset.label) <= 12
    assert PRESETS["word"].params == {"kind": "word"}
    assert DEFAULT.preset("wink") == {"kind": "face", "face": "wink"}


def test_a_word_is_written_in_one_of_openscad_s_own_fonts_and_quoted_safely():
    assert Params().font in FONTS
    with pytest.raises(ValueError):
        Params(font="Comic Sans MS")
    for bad in ('say "hi"', "back\\slash", "two\nlines", ""):
        with pytest.raises(ValueError):
            Params(text=bad)


def test_engraved_never_through_the_plate():
    with pytest.raises(ValueError, match="goes through it"):
        Params(depth=6, thickness=6)


def test_its_envelope_is_the_face_or_the_word_s_plate():
    face = DEFAULT.get_bounds({"diameter": 90, "thickness": 5})
    assert (face.max_point.x, face.max_point.y, face.max_point.z) == (90, 90, 5)
    word = DEFAULT.get_bounds({"kind": "word", "width": 150, "height": 50})
    assert (word.max_point.x, word.max_point.y) == (150, 50)


def test_a_printer_and_a_router_make_it():
    assert kinds_that_make("badge") == ("printer", "router")


@pytest.mark.parametrize("face", list(FACES))
def test_each_face_s_cuts_are_its_eyes_its_mouth_and_its_strokes_then_the_face_around(face):
    cuts = DEFAULT.cuts({"face": face})
    ops = cuts.operations
    assert (
        isinstance(ops[-1], Disc)
        and ops[-1].diameter == 80
        and ops[-1].depth > cuts.stock.thickness
    )
    holes = [o for o in ops if isinstance(o, Hole)]
    grooves = [o for o in ops if isinstance(o, Groove)]
    assert len(holes) == (1 if face == "wink" else 2) + (1 if face == "open" else 0)
    assert (
        len(grooves)
        == {"open": 0, "smile": 1, "neutral": 1, "wink": 2, "frown": 1, "grin": 1}[face]
    )
    # Everything engraved lies inside the face, a stroke's half width in from its edge.
    r, cx = 40.0, cuts.stock.x / 2
    for g in grooves:
        assert g.depth == 2.0
        for x, y in g.points:
            assert math.hypot(x - cx, y - cx) + 3.0 < r
    for h in holes:
        assert h.diameter > cuts.tool.diameter  # bored, not plunged
        assert math.hypot(h.x - cx, h.y - cx) + h.diameter / 2 < r


def test_a_grin_is_closed_and_its_toolpath_goes_round_it():
    (grin,) = [o for o in DEFAULT.cuts({"face": "grin"}).operations if isinstance(o, Groove)]
    assert grin.points[0] == grin.points[-1]
    written = toolpath.write(DEFAULT.cuts({"face": "grin"}), "badge")
    assert written.messages == [] and [o.kind for o in written.operations] == [
        "hole",
        "hole",
        "groove",
        "disc",
    ]


def test_a_word_and_a_stroke_not_the_tool_s_width_are_refused_by_the_router():
    with pytest.raises(Refused, match="a word is printed, not cut"):
        DEFAULT.cuts({"kind": "word"})
    with pytest.raises(Refused, match="stroke 6 to cut it"):
        DEFAULT.cuts({"stroke": 4})


def test_a_face_s_toolpath_is_written_and_a_word_s_refused_in_its_words(tmp_path, monkeypatch):
    """Over HTTP: the badge at its defaults, a smile, is cut; a variant of it drawn as a
    word is refused, the part's own words in the answer. A badge is no calibration piece:
    its toolpath names nothing to measure."""
    from apothecary.projects.parts import variants

    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    face = client.post("/cam/cut", json={"part": "badge", "site": "garage", "router": "cnc_router"})
    assert face.status_code == 200, face.text
    assert [o["kind"] for o in face.json()["operations"]] == ["hole", "hole", "groove", "disc"]
    assert face.json()["features"] == []
    word = "0123456789abcdef01234567"
    monkeypatch.setattr(
        variants,
        "read_variant",
        lambda part, key, *a, **k: {"params": {"kind": "word"}} if key == word else None,
    )
    refused = client.post(
        "/cam/cut",
        json={"part": "badge", "site": "garage", "router": "cnc_router", "variant": word},
    )
    assert refused.status_code == 400
    assert refused.json()["detail"].startswith("badge: a word is printed, not cut")


def test_a_variant_drawn_from_its_text_is_cut_at_the_text_s_numbers(tmp_path, monkeypatch):
    """The page edits the badge through its SCAD text, so a variant it draws carries its
    numbers in that text and none on the side: the toolpath reads them from the draft, a
    frown drawn is a frown cut, and a word drawn is refused."""
    from apothecary.cam import service
    from apothecary.projects.parts import variants

    own = DEFAULT.source_file.read_text(encoding="utf-8")
    drafts = {
        "0123456789abcdef01234567": own.replace('face = "smile";', 'face = "frown";'),
        "76543210fedcba9876543210": own.replace('kind = "face";', 'kind = "word";'),
    }
    monkeypatch.setenv("APOTHECARY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(variants, "read_variant", lambda part, key, *a, **k: {"params": {}})
    monkeypatch.setattr(variants, "read_variant_draft", lambda part, key, *a, **k: drafts.get(key))
    _, params, cuts = service.part_cuts("badge", "0123456789abcdef01234567")
    assert params["face"] == "frown"
    (frown,) = [o for o in cuts.operations if isinstance(o, Groove)]
    assert (
        frown.points
        == [o for o in DEFAULT.cuts({"face": "frown"}).operations if isinstance(o, Groove)][
            0
        ].points
    )
    assert frown.points != [o for o in DEFAULT.cuts().operations if isinstance(o, Groove)][0].points
    with pytest.raises(service.CamError, match="badge: a word is printed, not cut"):
        service.part_cuts("badge", "76543210fedcba9876543210")
