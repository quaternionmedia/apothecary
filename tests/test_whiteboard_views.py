"""A photograph pinned at the garage's whiteboard: squared to it, as wide as its
surface, laid on the floor in front of it, its shapes made there, and its corners
moved by a person (apothecary/routes/views.py, apothecary/vision/whiteboard.py)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from whiteboards_helpers import LEANING, WIDE
from whiteboards_helpers import photograph as _photograph

from apothecary.api import app
from apothecary.example_hierarchy import WHITEBOARD_POSITION, WHITEBOARD_SIZE
from apothecary.vision.views import IN_FRONT_GAP_MM


@pytest.fixture
def client(tmp_path, monkeypatch):
    _photograph(tmp_path / "leaning.png")
    monkeypatch.setenv("APOTHECARY_PICTURE_ROOT", str(tmp_path))
    client = TestClient(app)
    yield client, tmp_path
    for view in client.get("/sites/garage/attached").json()["views"]:
        client.delete(f"/sites/garage/views/{view['id']}")
    client.post("/sites/garage/reset")


def _pin(client):
    made = client.post("/sites/garage/views", json={"host": "whiteboard", "picture": "leaning.png"})
    assert made.status_code == 201, made.text
    return made.json()


def test_it_is_squared_sized_by_the_whiteboard_and_laid_on_the_floor_in_front(client):
    client, root = client
    view = _pin(client)
    assert view["in_front"] and view["mm_across"] == 1200.0
    assert view["picture"].startswith("squared/") and (root / view["picture"]).is_file()
    assert (view["pixel_width"], view["pixel_height"]) == (1600, 1200)
    squared = view["squared"]
    assert squared["source"] == "leaning.png" and squared["by"] == "finder"
    for (x, y), (want_x, want_y) in zip(squared["corners"], LEANING, strict=True):
        assert (x, y) == pytest.approx((want_x / WIDE, want_y / 1200), abs=0.012)
    x, y, z = view["mat"]["centre"]
    middle = WHITEBOARD_POSITION.x + WHITEBOARD_SIZE.x / 2
    assert z == 0 and x == pytest.approx(middle)
    assert y == pytest.approx(WHITEBOARD_POSITION.y - IN_FRONT_GAP_MM - 450)
    assert view["mat"]["width"] == 1200 and view["mat"]["depth"] == pytest.approx(900)


def test_its_shapes_are_made_on_the_floor_in_front_where_they_were_drawn(client):
    client, _ = client
    view = _pin(client)["id"]
    found = client.post(f"/sites/garage/views/{view}/find", json={"finder": "outline"}).json()
    assert sorted(s["kind"] for s in found["shapes"]) == ["disc", "rect", "tri"]
    made = client.post(f"/sites/garage/views/{view}/make", json={"all": True})
    assert made.status_code == 200, made.text
    site = client.get("/sites/garage").json()["tree"]
    pieces = [c for c in site["children"] if c["name"] in made.json()["made"]]
    assert len(pieces) == 3
    near = WHITEBOARD_POSITION.y - IN_FRONT_GAP_MM
    for piece in pieces:
        assert piece["position"]["z"] == 0
        assert near - 900 < piece["position"]["y"] < near
    # The plate drawn at 0.15 to 0.45 across a whiteboard 1200 wide is 360 mm long.
    record = next(
        r
        for r in client.get("/sites/garage/attached").json()["made"].values()
        if r["word"] == "plate"
    )
    assert record["parameters"]["width"] == pytest.approx(360, abs=14)


def test_a_person_moves_a_corner_and_it_is_squared_and_searched_again(client):
    client, root = client
    view = _pin(client)
    client.post(
        f"/sites/garage/views/{view['id']}/find", json={"finder": "outline"}
    ).raise_for_status()
    corners = client.get(f"/sites/garage/views/{view['id']}/corners").json()
    assert corners["by"] == "finder" and corners["pixel_width"] == 1600 and corners["made"] == 0
    moved = [list(c) for c in corners["corners"]]
    moved[1] = [moved[1][0] - 0.05, moved[1][1]]
    said = client.put(f"/sites/garage/views/{view['id']}/corners", json={"corners": moved})
    assert said.status_code == 200, said.text
    again = said.json()
    assert again["picture"] != view["picture"] and (root / again["picture"]).is_file()
    assert again["squared"]["by"] == "you" and again["squared"]["guess"] == corners["corners"]
    assert again["finder"] == "outline" and len(again["shapes"]) == 3


def test_corners_are_refused_past_the_photograph_and_once_a_piece_is_made(client):
    client, _ = client
    view = _pin(client)["id"]
    corners = client.get(f"/sites/garage/views/{view}/corners").json()["corners"]
    out = [list(c) for c in corners]
    out[0] = [-0.1, 0.1]
    assert (
        client.put(f"/sites/garage/views/{view}/corners", json={"corners": out}).status_code == 422
    )
    assert (
        client.put(f"/sites/garage/views/{view}/corners", json={"corners": corners[:3]}).status_code
        == 422
    )
    client.post(f"/sites/garage/views/{view}/find", json={"finder": "outline"}).raise_for_status()
    client.post(f"/sites/garage/views/{view}/make", json={"shape": 0}).raise_for_status()
    refused = client.put(f"/sites/garage/views/{view}/corners", json={"corners": corners})
    assert refused.status_code == 409 and "drop them first" in refused.json()["detail"]


def test_a_view_elsewhere_has_no_corners_and_a_dark_photograph_is_refused(client):
    client, root = client
    elsewhere = client.post(
        "/sites/garage/views", json={"host": "workbench", "picture": "leaning.png"}
    ).json()
    assert elsewhere["squared"] is None and not elsewhere["in_front"]
    assert client.get(f"/sites/garage/views/{elsewhere['id']}/corners").status_code == 404
    Image.new("RGB", (800, 600), (30, 30, 30)).save(root / "dark.png")
    refused = client.post("/sites/garage/views", json={"host": "whiteboard", "picture": "dark.png"})
    assert refused.status_code == 400 and "whiteboard" in refused.json()["detail"]
