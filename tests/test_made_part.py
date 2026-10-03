"""A piece made from a picture is a part like any other.

``MadePart`` (apothecary/vision/piece.py) wraps a made piece's record as a
``BasePart``, so the one parameter contract serves it: its fields default to
what it is now, its provenance is offered as candidates, its geometry is what
``piece_from_shape`` builds, and the made routes answer the shapes the parts
routes answer. The fixture is tests/test_views_api.py's: a stated picture 1000
by 500 pinned at ``workbench`` in ``garage``; at 1800 mm across, shape 1 (the
coin) is 54 by 54 mm, its thickness guessed at 8.1, standing at (1080, 50, 780).
"""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient
from test_views_api import _pin, _roots, world  # noqa: F401 - the fixture, used by every test here

from apothecary.api import app
from apothecary.projects.parts.params import ParamsSpec, Validation, params_spec, validate_staged
from apothecary.projects.parts.stl_renderer import geometry_scad
from apothecary.vision import views as viewing
from apothecary.vision.compose import THICKNESS_GUESS, piece_from_shape
from apothecary.vision.piece import MadePart

pytestmark = pytest.mark.usefixtures("world")

COIN = {"width": 54.0, "depth": 54.0, "height": 8.1}
COIN_AT = {"x": 1080.0, "y": 50.0, "z": 780.0}


def _make(c, view, shape=1):
    r = c.post(f"/sites/garage/views/{view['id']}/make", json={"shape": shape})
    assert r.status_code == 200, r.text
    return r.json()["made"][0]


def _record(piece):
    return viewing.store().made_piece("garage", piece)


def _put(c, piece, body):
    return c.put(f"/sites/garage/made/{piece}", json=body)


def _close(a, b):
    """The same numbers, to the tenth of a millimetre a fixture is stated to."""
    return all(math.isclose(a[k], b[k], abs_tol=0.05) for k in b)


# --- the part ------------------------------------------------------------------------------


def test_its_fields_are_its_word_and_sides_defaulting_to_what_it_is():
    c = TestClient(app)
    coin = _make(c, _pin(c, mm_across=1800))
    part = MadePart.of(_record(coin))
    spec = params_spec(part)
    assert spec.part == coin and [f.name for f in spec.fields] == [
        "word",
        "width",
        "depth",
        "height",
    ]
    word = spec.fields[0]
    assert word.type == "enum" and word.default == "disc"
    from apothecary.vocabulary import starter_words

    assert word.pattern == "^(" + "|".join(starter_words().names()) + ")$"
    for field in spec.fields[1:]:
        assert field.type == "number"
        assert field.default == pytest.approx(COIN[field.name])
        assert field.min < field.default < field.max
    assert spec.bounds is not None and spec.bounds.size.x == pytest.approx(54)
    assert part.validate_overrides({"width": 60}) == {"width": 60.0}
    assert part.category == "disc" and not part.exists


def test_height_carries_the_guess_and_a_fresh_piece_has_no_other_candidate():
    c = TestClient(app)
    coin = _make(c, _pin(c, mm_across=1800))
    contested = MadePart.of(_record(coin)).contested
    assert list(contested) == ["height"]
    (guess,) = contested["height"]
    assert guess.value == pytest.approx(54 * THICKNESS_GUESS)
    assert "THICKNESS_GUESS" in guess.source and "shorter side" in guess.source
    assert "cannot see thickness" in guess.note


def test_after_a_stated_size_the_measured_sides_are_one_click_away():
    c = TestClient(app)
    coin = _make(c, _pin(c, mm_across=1800))
    assert _put(c, coin, {"params": {"width": 40, "depth": 30}}).status_code == 200
    contested = MadePart.of(_record(coin)).contested
    assert set(contested) == {"height", "width", "depth"}
    (width,) = contested["width"]
    assert width.value == pytest.approx(54)
    assert "stated" in width.source and "bench_top.png" in width.source
    assert "at 1800 mm across the picture" in width.note
    assert contested["depth"][0].value == pytest.approx(54)


def test_after_a_rescale_a_stated_piece_offers_the_sides_measured_at_its_own_scale():
    c = TestClient(app)
    view = _pin(c, mm_across=1800)
    coin = _make(c, view)
    assert _put(c, coin, {"params": {"width": 40}}).status_code == 200
    r = c.put(f"/sites/garage/views/{view['id']}/scale", json={"mm_across": 900})
    assert r.status_code == 200 and r.json()["rebuilt"] == []
    record = _record(coin)
    assert record.mm_across == 1800 and record.parameters["width"] == 40
    (width,) = MadePart.of(record).contested["width"]
    assert width.value == pytest.approx(54) and "at 1800 mm" in width.note


def test_get_bounds_is_the_box_it_occupies_turned_as_its_shape_was_seen():
    c = TestClient(app)
    coin = _make(c, _pin(c, mm_across=1800))
    record = _record(coin)
    flat = MadePart.of(record).get_bounds({"width": 40, "depth": 10, "height": 3})
    assert (flat.size.x, flat.size.y, flat.size.z) == pytest.approx((40, 10, 3))
    assert flat.min_point.z == 0 and flat.center.x == 0 and flat.center.y == 0
    turned = MadePart.of(
        record.model_copy(update={"shape": record.shape.model_copy(update={"turned_degrees": 90})})
    ).get_bounds({"width": 40, "depth": 10, "height": 3})
    assert (turned.size.x, turned.size.y) == pytest.approx((10, 40))
    tilted = MadePart.of(
        record.model_copy(update={"shape": record.shape.model_copy(update={"turned_degrees": 30})})
    ).get_bounds({"width": 40, "depth": 10, "height": 3})
    c30, s30 = math.cos(math.radians(30)), math.sin(math.radians(30))
    assert tilted.size.x == pytest.approx(40 * c30 + 10 * s30)
    assert tilted.size.y == pytest.approx(40 * s30 + 10 * c30)


def test_a_turned_pieces_footprint_is_the_box_get_bounds_gives():
    """The overlap check reads the footprint; the editor reads get_bounds. A bar
    lying at 35 degrees fills one box, and both say it."""
    from apothecary.vocabulary import WordShape

    c = TestClient(app)
    coin = _make(c, _pin(c, mm_across=1800))
    record = _record(coin)
    record = record.model_copy(
        update={"shape": record.shape.model_copy(update={"turned_degrees": 35})}
    )
    sides = {"width": 40.0, "depth": 10.0, "height": 3.0}
    piece, _about = piece_from_shape(
        record.shape,
        name=record.piece,
        word="plate",
        reason=record.reason,
        per_unit=record.mm_across,
        tallness=record.pixel_height / record.pixel_width,
        finder=record.finder,
        size=WordShape(**sides),
    )
    box = MadePart.of(record).get_bounds(sides)
    assert box.size.x > 40 * math.cos(math.radians(35))  # the turned box, not 40 x 10
    for corner in ("min_point", "max_point"):
        got, want = getattr(piece.footprint, corner), getattr(box, corner)
        assert (got.x, got.y, got.z) == pytest.approx((want.x, want.y, want.z))


def test_its_geometry_is_what_piece_from_shape_builds_and_follows_the_parameters():
    c = TestClient(app)
    coin = _make(c, _pin(c, mm_across=1800))
    part = MadePart.of(_record(coin))
    text = geometry_scad(part, {})
    assert text is not None and "cylinder" in text and "translate" in text
    assert "r=27" in text.replace(" ", "") or "r = 27" in text
    wider = geometry_scad(part, {"width": 60})
    assert wider != text and ("r=30" in wider.replace(" ", ""))
    assert "cube" in geometry_scad(part, {"word": "plate"})
    # Served as a few lines, the same text.
    r = c.get(f"/sites/garage/made/{coin}/scad")
    assert r.status_code == 200 and r.text == text and len(text.strip().splitlines()) < 12


def test_validate_refuses_an_unknown_field_a_side_of_nothing_and_a_word_not_in_the_vocabulary():
    c = TestClient(app)
    coin = _make(c, _pin(c, mm_across=1800))
    part = MadePart.of(_record(coin))
    unknown = validate_staged(part, {"nozzle": 0.4})
    assert not unknown.valid and unknown.errors[0].field == "nozzle"
    for bad in ({"width": 0}, {"depth": -1}, {"height": 0}):
        report = validate_staged(part, bad)
        assert not report.valid and report.errors[0].field == next(iter(bad)), bad
    assert not validate_staged(part, {"word": "nope"}).valid
    good = validate_staged(part, {"width": 60})
    assert good.valid and good.params == {"width": 60.0}
    assert good.bounds is not None and good.bounds.size.x == pytest.approx(60)


# --- the routes ----------------------------------------------------------------------------


def test_the_made_routes_answer_the_parts_routes_shapes():
    c = TestClient(app)
    coin = _make(c, _pin(c, mm_across=1800))
    spec = c.get(f"/sites/garage/made/{coin}/params")
    assert spec.status_code == 200, spec.text
    reference = c.get("/parts/datum_core/params").json()
    assert list(spec.json()) == list(reference)
    assert list(spec.json()["fields"][0]) == list(reference["fields"][0])
    assert ParamsSpec(**spec.json()).part == coin
    checked = c.post(f"/sites/garage/made/{coin}/validate", json={"params": {"width": 60}})
    assert checked.status_code == 200, checked.text
    assert list(checked.json()) == ["valid", "params", "errors", "bounds"]
    assert Validation(**checked.json()).valid
    refused = c.post(f"/sites/garage/made/{coin}/validate", json={"params": {"width": 0}}).json()
    assert refused["valid"] is False and refused["errors"][0]["field"] == "width"
    for missing in ("workbench", "no_such_piece"):
        assert c.get(f"/sites/garage/made/{missing}/params").status_code == 404
        assert (
            c.post(f"/sites/garage/made/{missing}/validate", json={"params": {}}).status_code == 404
        )
        assert c.get(f"/sites/garage/made/{missing}/scad").status_code == 404


def test_put_params_rebuilds_states_the_sides_and_keeps_name_and_position():
    c = TestClient(app)
    coin = _make(c, _pin(c, mm_across=1800))
    r = _put(c, coin, {"params": {"word": "disc", "width": 40, "depth": 54, "height": 8.1}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["piece"] == coin
    made = body["provenance"]
    assert _close(made["parameters"], {"width": 40, "depth": 54, "height": 8.1})
    assert made["parameters_stated"] is True
    assert made["word"] == "disc" and made["word_stated"] is False  # the word did not change
    assert _close(made["found"], COIN)
    assert body["bounds"]["size"]["x"] == pytest.approx(40)
    after = _roots(c)[coin]
    assert _close(after["position"], COIN_AT)
    fp = after["footprint"]
    assert [fp["max"][i] - fp["min"][i] for i in range(3)] == pytest.approx([40, 54, 8.1])
    assert coin in {s["name"] for s in body["site"]["structures"]}


def test_a_word_through_params_states_the_word_and_not_the_sides():
    c = TestClient(app)
    coin = _make(c, _pin(c, mm_across=1800))
    r = _put(c, coin, {"params": {"word": "post"}})
    assert r.status_code == 200, r.text
    made = r.json()["provenance"]
    assert made["word"] == "post" and made["word_stated"] is True
    assert made["parameters_stated"] is False and _close(made["parameters"], COIN)
    assert _close(_roots(c)[coin]["position"], COIN_AT)
    assert _put(c, coin, {"params": {"word": "nope"}}).status_code == 422
    assert _put(c, coin, {"params": {"nozzle": 0.4}}).status_code == 422
    assert _put(c, coin, {"params": {"width": 0}}).status_code == 422
    assert _put(c, coin, {}).status_code == 422
    # A set that changes nothing rebuilds nothing, and still answers the piece.
    r = _put(c, coin, {"params": {"word": "post", "width": 54}})
    assert r.status_code == 200 and r.json()["provenance"]["parameters_stated"] is False


def test_the_found_candidate_returns_a_piece_to_as_found():
    c = TestClient(app)
    coin = _make(c, _pin(c, mm_across=1800))
    assert _put(c, coin, {"params": {"width": 40}}).json()["provenance"]["parameters_stated"]
    found = MadePart.of(_record(coin)).contested["width"][0].value
    made = _put(c, coin, {"params": {"width": found}}).json()["provenance"]
    assert made["parameters_stated"] is False and _close(made["parameters"], COIN)
    assert "width" not in MadePart.of(_record(coin)).contested


def test_a_rescale_rebuilds_unstated_pieces_and_leaves_stated_and_moved_ones():
    c = TestClient(app)
    view = _pin(c, mm_across=1800)
    block, coin, bar = (_make(c, view, shape=i) for i in range(3))
    before = _roots(c)
    # The coin's sides are a person's; the bar was moved by hand.
    assert _put(c, coin, {"params": {"width": 40}}).status_code == 200
    moved = {**before[bar]["position"], "x": before[bar]["position"]["x"] + 100}
    r = c.post("/sites/garage/layout", json={"positions": {bar: moved}})
    assert r.status_code == 200, r.text

    r = c.put(f"/sites/garage/views/{view['id']}/scale", json={"mm_across": 900})
    assert r.status_code == 200, r.text
    assert r.json()["rebuilt"] == sorted([block, bar])
    assert r.json()["site"] is not None
    after = _roots(c)
    made = c.get("/sites/garage/attached").json()["made"]

    # The block: half the size, laid on its shape where it now lies.
    block_size = [
        after[block]["footprint"]["max"][i] - after[block]["footprint"]["min"][i] for i in range(3)
    ]
    assert block_size == pytest.approx([90, 45, 6.75])
    shape = view["shapes"][0]
    cx = (shape["min"][0] + shape["max"][0]) / 2
    cy = (shape["min"][1] + shape["max"][1]) / 2
    assert after[block]["position"]["x"] == pytest.approx(900 + (cx - 0.5) * 900)
    assert after[block]["position"]["y"] == pytest.approx(300 + (0.5 - cy) * 0.5 * 900)
    assert made[block]["mm_across"] == 900 and made[block]["parameters_stated"] is False
    assert made[block]["placed_at"] == after[block]["position"]
    # The bar: rebuilt at the new width, standing where it was moved to.
    bar_size = [
        after[bar]["footprint"]["max"][i] - after[bar]["footprint"]["min"][i] for i in range(3)
    ]
    assert bar_size == pytest.approx([18, 18, 2.7])
    assert after[bar]["position"] == moved and made[bar]["mm_across"] == 900
    # The coin: a person's sides, untouched, its provenance at the scale it was made.
    assert _close(after[coin]["position"], COIN_AT)
    assert _close(made[coin]["parameters"], {"width": 40, "depth": 54, "height": 8.1})
    assert made[coin]["mm_across"] == 1800


def test_a_rescale_answer_without_a_rebuild_carries_no_site():
    c = TestClient(app)
    view = _pin(c, mm_across=1800)
    r = c.put(f"/sites/garage/views/{view['id']}/scale", json={"mm_across": 900})
    assert r.status_code == 200 and r.json()["rebuilt"] == [] and r.json()["site"] is None
    assert r.json()["mm_across"] == 900
