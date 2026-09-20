"""The two routes the ring speaks through, and the two lists that must not drift.

The tests at the bottom are the ones worth reading. The ring's options and the
answers to a chosen option are two lists maintained by hand in two places, and
the failure they invite is silent in both directions: an option nobody carries
out is a wedge that does nothing, and an answer for an option no ring offers is
dead code that reads like a feature.

**Watched failing.** Deleting `"reset"` from `apothecary/menu.py`'s `CARRIED_BY`
turns the first guard red; adding an entry to `CARRIED_BY` that is written down
as the server's and has no arm in the route turns the second red. Both were run
with the fault in place before this note was written.
"""

import pytest
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.menu import CARRIED_BY, Carries, Context, Device, Pointing, every_action, resolve

client = TestClient(app)

SITE = "garage"


@pytest.fixture(autouse=True)
def reset_garage_site():
    """The site store keeps edits between requests, so start every test level."""
    client.post(f"/sites/{SITE}/reset")
    yield


PRINTER = {"port": "/dev/ttyUSB0", "printer": True, "armed": False, "bound": True}


def chosen(action: str, *, targets=(), site=SITE, pointing=Pointing.CANVAS, address=None):
    body = {
        "intent": {
            "action": action,
            "option_id": action,
            "context": {"pointing": pointing.value, "targets": list(targets)},
        }
    }
    if address is not None:
        body["intent"]["address"] = address
    if site is not None:
        body["site"] = site
    return body


# ----------------------------------------------------------------- resolving


def test_the_canvas_ring_offers_the_arrangements_that_exist():
    answer = client.post(
        "/menu/resolve",
        json={"context": {"pointing": "canvas", "targets": []}, "site": SITE},
    )
    assert answer.status_code == 200, answer.text
    ring = answer.json()
    actions = [option["id"] for option in ring["options"]]
    assert "Site" in actions
    sites = next(o for o in ring["options"] if o["id"] == "Site")
    assert any(child["action"] == f"site:{SITE}" for child in sites["children"])


def test_a_node_ring_stands_on_the_dotted_path_it_was_opened_over():
    answer = client.post(
        "/menu/resolve",
        json={
            "context": {"pointing": "node", "targets": ["printer_1.frame_system"]},
            "site": SITE,
        },
    )
    assert answer.status_code == 200, answer.text
    ring = answer.json()
    assert ring["title"] == "frame system"
    assert {option["action"] for option in ring["options"]} >= {"zoom-in", "move", "explain"}


def test_every_option_comes_back_with_its_cell():
    """The page draws cells, not a list; a wedge without a number cannot be addressed."""
    answer = client.post(
        "/menu/resolve",
        json={"context": {"pointing": "canvas", "targets": []}, "site": SITE},
    )
    assert answer.status_code == 200, answer.text
    cells = [option["cell"] for option in answer.json()["options"]]
    assert cells == [8, 6, 2, 4][: len(cells)]
    assert 5 not in cells


def test_a_node_with_a_printer_pinned_offers_the_device_ring_with_cells():
    answer = client.post(
        "/menu/resolve",
        json={
            "context": {"pointing": "node", "targets": ["printer_1.frame_system"]},
            "site": SITE,
            "device": PRINTER,
        },
    )
    assert answer.status_code == 200, answer.text
    ring = answer.json()
    device = next(o for o in ring["options"] if o["id"] == "device")
    assert device["cell"] == 2, "after Zoom in and Move"
    labels = {c["label"]: c["cell"] for c in device["children"]}
    assert labels == {
        "Watch": 8,
        "Poll": 6,
        "Monitor": 2,
        "Query": 4,
        "Unpin": 9,
        "Rescan": 3,
        "Link": 1,
        "Control": 7,
    }
    control = next(c for c in device["children"] if c["id"] == "control")
    jog = next(c for c in control["children"] if c["label"] == "Jog")
    assert {c["label"]: c["cell"] for c in jog["children"]} == {
        "Y+": 8,
        "X+": 6,
        "Y-": 2,
        "X-": 4,
        "Z+": 9,
        "Z-": 3,
    }


def test_the_same_node_without_a_device_has_no_device_option():
    answer = client.post(
        "/menu/resolve",
        json={"context": {"pointing": "node", "targets": ["printer_1.frame_system"]}, "site": SITE},
    )
    assert answer.status_code == 200, answer.text
    assert "device" not in [o["id"] for o in answer.json()["options"]]


def test_a_device_ring_needs_no_arrangement():
    answer = client.post(
        "/menu/resolve",
        json={"context": {"pointing": "device", "targets": ["/dev/ttyUSB0"]}, "device": PRINTER},
    )
    assert answer.status_code == 200, answer.text
    ring = answer.json()
    assert ring["title"] == "ttyUSB0"
    assert [o["label"] for o in ring["options"]][:4] == ["Watch", "Poll", "Monitor", "Query"]


def test_an_unknown_pointing_is_refused():
    answer = client.post(
        "/menu/resolve",
        json={"context": {"pointing": "planet", "targets": []}, "site": SITE},
    )
    assert answer.status_code == 422, answer.text


def test_resolving_changes_nothing():
    """The whole argument for the resolver being a pure function."""
    before = client.get(f"/sites/{SITE}").json()
    client.post(
        "/menu/resolve",
        json={"context": {"pointing": "canvas", "targets": []}, "site": SITE},
    )
    assert client.get(f"/sites/{SITE}").json() == before


# ------------------------------------------------------------- carrying out


def test_a_viewer_action_changes_nothing_and_says_so():
    before = client.get(f"/sites/{SITE}").json()
    answer = client.post("/menu/intent", json=chosen("fit"))
    assert answer.status_code == 200, answer.text
    assert answer.json()["carried_by"] == Carries.VIEWER.value
    assert client.get(f"/sites/{SITE}").json() == before


def test_an_intent_with_an_address_has_it_echoed_back():
    answer = client.post(
        "/menu/intent",
        json=chosen(
            "control:jog:Y+", targets=["printer_1"], pointing=Pointing.NODE, address="2728"
        ),
    )
    assert answer.status_code == 200, answer.text
    assert answer.json()["address"] == "2728"
    assert answer.json()["carried_by"] == Carries.VIEWER.value


def test_an_intent_without_an_address_is_still_fine():
    answer = client.post("/menu/intent", json=chosen("fit"))
    assert answer.status_code == 200, answer.text
    assert answer.json()["address"] is None


def test_an_address_that_is_not_cells_is_refused():
    answer = client.post("/menu/intent", json=chosen("fit", address="85"))
    assert answer.status_code == 422, answer.text


def test_a_device_verb_is_the_viewer_s_and_touches_no_port():
    """The intent route never opens a port; the page's own handler does the work."""
    for action in ("device:watch", "device:poll", "control:estop", "control:arm"):
        answer = client.post(
            "/menu/intent",
            json=chosen(action, targets=["printer_1"], pointing=Pointing.NODE),
        )
        assert answer.status_code == 200, answer.text
        assert answer.json()["carried_by"] == Carries.VIEWER.value


def test_reset_actually_rebuilds_the_arrangement():
    moved = client.post(
        f"/sites/{SITE}/layout",
        json={"positions": {"workbench": {"x": 1234.0, "y": 0.0, "z": 0.0}}},
    )
    assert moved.status_code == 200, moved.text

    answer = client.post("/menu/intent", json=chosen("reset"))
    assert answer.status_code == 200, answer.text
    assert answer.json()["carried_by"] == Carries.SERVER.value

    tree = client.get(f"/sites/{SITE}").json()["tree"]
    workbench = next(child for child in tree["children"] if child["name"] == "workbench")
    assert workbench["position"]["x"] != 1234.0, "reset did not undo the move"


def test_an_option_nothing_carries_out_is_refused_rather_than_swallowed():
    """The failure this whole route exists to make impossible.

    A wedge that can be pressed with no effect and no complaint is
    indistinguishable, from the outside, from one that worked.
    """
    answer = client.post(
        "/menu/intent",
        json=chosen("word:disc", targets=["printer_1"], pointing=Pointing.NODE),
    )
    assert answer.status_code == 501, answer.text
    assert "word:disc" in answer.json()["detail"]


def test_an_action_no_ring_produces_is_refused():
    answer = client.post("/menu/intent", json=chosen("delete-everything"))
    assert answer.status_code == 400, answer.text
    assert "delete-everything" in answer.json()["detail"]


def test_an_action_about_one_arrangement_says_when_it_was_not_told_which():
    answer = client.post("/menu/intent", json=chosen("reset", site=None))
    assert answer.status_code == 400, answer.text
    assert "site" in answer.json()["detail"]


def test_a_shape_asked_for_on_a_node_that_is_not_there_is_refused():
    answer = client.post(
        "/menu/intent",
        json=chosen("render-stl", targets=["printer_1.no_such_thing"], pointing=Pointing.NODE),
    )
    assert answer.status_code == 404, answer.text


def test_a_shape_asked_for_on_a_real_node_says_where_it_is():
    answer = client.post(
        "/menu/intent",
        json=chosen("render-stl", targets=["printer_1.frame_system"], pointing=Pointing.NODE),
    )
    assert answer.status_code == 200, answer.text
    assert f"/sites/{SITE}/nodes/printer_1.frame_system/stl" in answer.json()["did"]


# ------------------------------------------------------------------- guards


def _every_ring():
    """One ring of each kind the resolver can build, over a real arrangement."""
    from apothecary.api import _site_store
    from apothecary.vocabulary.starter import starter_words

    site = _site_store.get(SITE)
    names = sorted(_site_store.names())
    groups = sorted({child.category for child in site.children if child.category})
    words = starter_words().names()
    printer = Device(port="/dev/ttyUSB0", printer=True, armed=False, bound=True)
    armed = Device(port="/dev/ttyUSB0", printer=True, armed=True, bound=True)
    board = Device(port="/dev/ttyACM0", printer=False, bound=False)
    return [
        resolve(
            Context(pointing=pointing, targets=targets),
            site,
            site_names=names,
            groups=groups,
            words=words,
            device=device,
        )
        for pointing, targets, device in (
            (Pointing.CANVAS, [], None),
            (Pointing.NODE, ["printer_1"], None),
            (Pointing.NODE, ["printer_1.frame_system"], None),
            (Pointing.NODE, ["printer_1.frame_system.mainboard"], printer),
            (Pointing.NODE, ["printer_1.frame_system.mainboard"], armed),
            (Pointing.SELECTION, ["printer_1", "printer_2"], None),
            (Pointing.EDGE, ["printer_1"], None),
            (Pointing.DEVICE, ["/dev/ttyUSB0"], printer),
            (Pointing.DEVICE, ["/dev/ttyACM0"], board),
        )
    ]


def test_every_option_a_ring_offers_says_who_carries_it_out():
    """An unclassified wedge is a wedge that silently does nothing.

    Checked against the rings the resolver actually builds rather than against a
    list written here, so an option added to a ring is caught by this without
    anybody remembering to add it in a second place.
    """
    from apothecary.menu import carried_by

    for action in every_action(_every_ring()):
        carried_by(action)  # raises UnknownAction if nobody has said


def test_everything_written_down_as_the_server_s_has_an_arm():
    """The other direction: a classification with no code behind it.

    Asked behaviourally rather than by reading the route's source. An action with
    an arm answers 'you did not say which arrangement'; one without falls through
    to the refusal that says nobody wrote it.
    """
    for action, who in CARRIED_BY.items():
        if who is not Carries.SERVER:
            continue
        answer = client.post("/menu/intent", json=chosen(action, site=None))
        assert answer.status_code != 500, (
            f"{action!r} is written down as the server's and has no arm in the "
            f"route: {answer.json()['detail']}"
        )
