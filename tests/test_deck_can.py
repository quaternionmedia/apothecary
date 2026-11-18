"""A deck's ``can`` says a control is refused exactly when its route refuses it.

Each case puts the deck in one condition -- the knobs off or running, a deck not found,
a name no deck has, a deck that would not open, one lost on USB and not back, the deck
library missing, a real deck -- asks the deck's answer first (``can`` on
``GET /firmware/decks/{id}/control``, as the Deck window and a Control pad read it), then
sends the control's own request to the real route and compares: ``ok: false`` with a
reason where the route answers 4xx or 5xx, ``ok: true`` where it takes it. The
predicates are the ones the routes raise from (``apothecary/firmware/can.py``, a deck's
answer), so a case that disagrees is a predicate bent in one place.

No HID device and no serial port is opened: the decks are simulated, or a stand-in for the
library's device.
"""

import types

import pytest
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.firmware import deck, deck_control
from apothecary.firmware.deck import DeckUnavailable
from apothecary.simulated import PRINTER

SIMULATED = "SIMDECK0"


class _Device:
    """What python-elgato-streamdeck's StreamDeckPlus offers: enough to be listed and
    opened, nothing behind it."""

    def deck_type(self):
        return "Stream Deck +"

    def id(self):
        return "path/one"

    def open(self):
        pass

    def close(self):
        pass

    def get_serial_number(self):
        return "CL12345"

    def __getattr__(self, name):  # set_poll_frequency, the callbacks, the images
        return lambda *a, **k: None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _WillNotOpen:
    """A simulated deck's link that cannot be opened, as a real one is without its rule."""

    def __init__(self, report):
        raise DeckUnavailable("the Stream Deck + is found but would not open (a test's)")


class Rig:
    def __init__(self, client, monkeypatch):
        self.client, self.monkeypatch = client, monkeypatch
        self.deck, self.port = SIMULATED, PRINTER

    def opened(self):
        """The deck opened, as the Deck window's first look opens it."""
        return self.client.get(f"/firmware/decks/{self.deck}")

    def start(self):
        answer = self.client.post(f"/firmware/decks/{self.deck}/control", json={"on": True})
        assert answer.status_code == 200, answer.text

    def lost_and_not_back(self):
        """The open deck gone from USB, and every opening of it failing until it is back:
        an open deck is opened again by the link it was opened with."""
        one = deck.get_decks().opened(self.deck)
        one._make_link = _WillNotOpen
        one.link.lost = True
        assert not one.alive()

    def real(self, library=True):
        self.monkeypatch.setenv("APOTHECARY_SERIAL_ENGINE", "pyserial")
        if library:
            manager = types.SimpleNamespace(enumerate=lambda: [_Device()])
            self.monkeypatch.setattr(deck, "_manager", lambda: manager)
        else:

            def missing():
                raise DeckUnavailable("the Stream Deck library is not installed (a test's)")

            self.monkeypatch.setattr(deck, "_manager", missing)
        self.deck = "path_one"

    def answer(self) -> dict:
        got = self.client.get(f"/firmware/decks/{self.deck}/control", params={"port": self.port})
        assert got.status_code == 200, got.text
        return got.json()["can"]

    def request(self, verb):
        at = f"/firmware/decks/{self.deck}"
        if verb == "knobs.start":
            return self.client.post(f"{at}/control", json={"on": True})
        if verb == "knobs.stop":
            return self.client.post(f"{at}/control", json={"on": False})
        if verb == "knobs.machine":
            return self.client.put(f"{at}/control", json={"machine": "cnc_router"})
        if verb == "knobs.step":
            return self.client.put(f"{at}/control", json={"step_mm": 10})
        if verb == "knobs.screen":
            return self.client.put(f"{at}/control", json={"screen": "status"})
        if verb == "here":
            return self.client.put(f"{at}/control", json={"port": self.port})
        if verb == "inject":
            return self.client.post(
                f"{at}/events", json={"kind": "knob-press", "index": 0, "value": False}
            )
        raise AssertionError(verb)


@pytest.fixture
def rig(family_bench, monkeypatch):
    monkeypatch.setenv(deck.SIMULATED_DECK_ENV, SIMULATED)
    monkeypatch.delenv(deck_control.CONTROL_ENV, raising=False)
    deck_control.stop_all()
    deck.reset_decks()
    yield Rig(TestClient(app), monkeypatch)
    deck_control.stop_all()
    deck.reset_decks()


def idle(rig):
    rig.opened()


def running(rig):
    rig.opened()
    rig.start()


def elsewhere(rig):
    running(rig)
    rig.port = "/dev/ttyNOPE"


def not_found(rig):
    rig.deck = "NOPE"


def not_a_name(rig):
    rig.deck = "no!deck"


def would_not_open(rig):
    rig.monkeypatch.setattr(deck, "SimulatedLink", _WillNotOpen)
    assert rig.opened().status_code == 503  # the window's first look: refused, and learned


def lost(rig):
    rig.opened()
    rig.lost_and_not_back()


def lost_running(rig):
    running(rig)
    rig.lost_and_not_back()


def a_real_deck(rig):
    rig.real()
    rig.opened()


def no_library(rig):
    rig.real(library=False)


KNOBS = ["knobs.start", "knobs.stop", "knobs.machine", "knobs.step", "knobs.screen", "here"]
EVERY = [*KNOBS, "inject"]
# Each condition: how the rig is put in it, and the controls asked of it. A real deck's
# knobs are not started here: the layout would look for its machines' boards.
CONDITIONS = {
    "knobs-off": (idle, EVERY),
    "knobs-running": (running, EVERY),
    "here-is-no-machine-of-the-decks": (elsewhere, ["here"]),
    "no-such-deck": (not_found, EVERY),
    "not-a-decks-name": (not_a_name, EVERY),
    "it-would-not-open": (would_not_open, EVERY),
    "lost-on-usb-knobs-off": (lost, EVERY),
    "lost-on-usb-knobs-running": (lost_running, EVERY),
    "a-real-deck": (a_real_deck, ["inject", "knobs.stop", "knobs.machine", "here"]),
    "no-deck-library": (no_library, ["knobs.start", "knobs.stop", "inject"]),
}
CASES = [
    pytest.param(name, verb, id=f"{name}:{verb}")
    for name, (_, verbs) in CONDITIONS.items()
    for verb in verbs
]


@pytest.mark.parametrize("condition,verb", CASES)
def test_the_decks_answer_agrees_with_the_route(rig, condition, verb):
    CONDITIONS[condition][0](rig)
    verdict = rig.answer()[verb]
    answer = rig.request(verb)
    said = f"{condition}/{verb}: can said {verdict}, route said {answer.status_code} {answer.text[:200]}"
    if verdict["ok"]:
        assert answer.status_code < 400, said
        assert verdict["why"] is None and verdict["kind"] is None, said
    else:
        assert answer.status_code >= 400, said
        assert verdict["why"] and verdict["kind"], said
        assert verdict["why"] in answer.json()["detail"], said  # in the route's own words


def test_the_answer_says_what_stands_in_the_way(rig):
    idle(rig)
    off = rig.answer()
    assert off["knobs.start"]["ok"] and off["inject"]["ok"]
    assert off["knobs.machine"]["kind"] == "idle" and "not started" in off["knobs.machine"]["why"]
    rig.start()
    on = rig.answer()
    assert on["knobs.machine"]["ok"] and on["here"]["ok"]
    rig.port = "/dev/ttyNOPE"
    assert rig.answer()["here"]["kind"] == "machine"
    # Asked without a port, the knobs' answer has no Here: the page has none to ask for.
    plain = rig.client.get(f"/firmware/decks/{SIMULATED}/control").json()["can"]
    assert "here" not in plain
    # Every running layout's, with the port, for a Control pad.
    [knobs] = rig.client.get("/firmware/decks/control", params={"port": PRINTER}).json()["controls"]
    assert knobs["deck"] == SIMULATED and knobs["can"]["here"]["ok"]


def test_asking_opens_no_deck(rig):
    """The answer is read from what is known: a deck nobody has opened stays closed."""
    rig.client.get(f"/firmware/decks/{SIMULATED}/control")
    assert deck.get_decks().opened(SIMULATED) is None
