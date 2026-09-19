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
from apothecary.menu import CARRIED_BY, Carries, Context, Pointing, every_action, resolve

client = TestClient(app)

SITE = "garage"


@pytest.fixture(autouse=True)
def reset_garage_site():
    """The site store keeps edits between requests, so start every test level."""
    client.post(f"/sites/{SITE}/reset")
    yield


def chosen(action: str, *, targets=(), site=SITE, pointing=Pointing.CANVAS):
    body = {
        "intent": {
            "action": action,
            "option_id": action,
            "context": {"pointing": pointing.value, "targets": list(targets)},
        }
    }
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
    return [
        resolve(
            Context(pointing=pointing, targets=targets),
            site,
            site_names=names,
            groups=groups,
            words=words,
        )
        for pointing, targets in (
            (Pointing.CANVAS, []),
            (Pointing.NODE, ["printer_1"]),
            (Pointing.NODE, ["printer_1.frame_system"]),
            (Pointing.SELECTION, ["printer_1", "printer_2"]),
            (Pointing.EDGE, ["printer_1"]),
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
