"""The Stream Deck +: found, drawn and heard (apothecary/firmware/deck.py), its module and
its routes, against the simulated deck, a stand-in for the HID library and the library's
own dummy transport. No HID device is opened and nothing reaches the network."""

from __future__ import annotations

import io
import sys
import types

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from apothecary.api import app
from apothecary.firmware import deck
from apothecary.firmware.deck import DeckUnavailable
from apothecary.firmware.modules import get_module, modules
from apothecary.firmware.toolchains import ToolchainError


@pytest.fixture(autouse=True)
def simulated_deck(monkeypatch):
    monkeypatch.setenv("APOTHECARY_SERIAL_ENGINE", "simulated")
    monkeypatch.setenv(deck.SIMULATED_DECK_ENV, "SIMDECK0")
    deck.reset_decks()
    yield
    deck.reset_decks()


@pytest.fixture
def client():
    return TestClient(app)


def _size(jpeg: bytes):
    img = Image.open(io.BytesIO(jpeg))
    return img.format, img.size


# --- what the device is -------------------------------------------------------------


def test_the_deck_is_elgatos_vendor_id_and_the_plus_s_product_id():
    """python-elgato-streamdeck's ProductIDs.py: USB_VID_ELGATO and USB_PID_STREAMDECK_PLUS."""
    assert (deck.ELGATO, deck.STREAM_DECK_PLUS) == (0x0FD9, 0x0084)
    info = deck.DeckInfo(id="x")
    assert (info.vid, info.pid) == ("0x0fd9", "0x0084")
    assert (info.keys, info.knobs, info.strip) == (8, 4, [800, 100])
    assert (deck.KEY_COLS, deck.KEY_ROWS) == (4, 2)


def test_a_key_and_the_strip_are_drawn_as_the_jpegs_the_device_takes():
    assert _size(deck.render_key("X+", "blue", "1 mm")) == ("JPEG", (120, 120))
    assert _size(deck.render_strip("cnc_router", "green")) == ("JPEG", (800, 100))
    with pytest.raises(ValueError, match="not a colour"):
        deck.render_key("x", "plaid")


# --- the simulated deck ---------------------------------------------------------------


def test_listing_names_the_simulated_decks_and_opens_none(monkeypatch):
    monkeypatch.setattr(deck, "_manager", lambda: pytest.fail("the HID library was asked"))
    found = deck.get_decks().list()
    assert [(d.id, d.simulated, d.model) for d in found] == [("SIMDECK0", True, "Stream Deck +")]
    assert deck.get_decks()._open == {}


def test_a_simulated_deck_keeps_what_it_is_sent():
    one = deck.get_decks().get("SIMDECK0")
    jpeg = one.set_key(3, "Y+", "blue", "1 mm")
    one.set_strip("cnc_router", "green", "armed")
    assert one.keys[3]["jpeg"] == jpeg and one.keys[3]["text"] == "Y+"
    assert one.strip["small"] == "armed"
    assert one.link.sent == [("key", 3, len(jpeg)), ("strip", 0, len(one.strip["jpeg"]))]
    with pytest.raises(ValueError, match="no key 8"):
        one.set_key(8, "x")
    with pytest.raises(ValueError, match="0 to 100"):
        one.set_brightness(101)


def test_events_are_kept_in_order_and_told_to_a_listener_until_it_stops():
    one = deck.get_decks().get("SIMDECK0")
    heard = []
    stop = one.listen(heard.append)
    one.inject("key", 2, True)
    one.inject("knob-turn", 1, -3)
    one.inject("knob-press", 0, True)
    one.inject("touch", 0, {"kind": "drag", "x": 10, "y": 20, "x_out": 400, "y_out": 22})
    stop()
    one.inject("key", 2, False)
    assert [(e.seq, e.kind, e.index) for e in heard] == [
        (1, "key", 2),
        (2, "knob-turn", 1),
        (3, "knob-press", 0),
        (4, "touch", 0),
    ]
    assert [e.seq for e in one.events(since=3)] == [4, 5]
    assert one.events()[1].value == -3


@pytest.mark.parametrize(
    "kind, index, value, says",
    [
        ("shake", 0, True, "not an event"),
        ("key", 8, True, "no key 8"),
        ("knob-turn", 4, 1, "no knob 4"),
        ("knob-turn", 0, 0, "whole number of steps"),
        ("knob-turn", 0, True, "whole number of steps"),
        ("key", 0, 1, "true, a release false"),
        ("touch", 0, {"kind": "poke", "x": 1, "y": 1}, "a touch is"),
        ("touch", 0, {"kind": "short", "x": 1}, "whole-number x and y"),
    ],
)
def test_an_event_a_deck_could_not_report_is_refused(kind, index, value, says):
    with pytest.raises(ValueError, match=says):
        deck.get_decks().get("SIMDECK0").inject(kind, index, value)


def test_a_listener_that_fails_does_not_stop_the_others():
    one = deck.get_decks().get("SIMDECK0")
    heard = []

    def bad(event):
        raise RuntimeError("boom")

    one.listen(bad)
    one.listen(heard.append)
    one.inject("key", 0, True)
    assert len(heard) == 1


def test_an_unknown_or_malformed_deck_is_refused():
    with pytest.raises(KeyError):
        deck.get_decks().get("OTHER")
    with pytest.raises(ValueError, match="not a deck's name"):
        deck.get_decks().get("../x")


# --- the routes -----------------------------------------------------------------------


def test_the_routes_list_draw_and_hear(client):
    assert client.get("/firmware/decks").json() == {
        "decks": [deck.DeckInfo(id="SIMDECK0", simulated=True).model_dump()],
        "problem": None,
    }
    put = client.put(
        "/firmware/decks/SIMDECK0/keys/0", json={"text": "X+", "colour": "blue", "small": "1 mm"}
    )
    assert put.status_code == 200 and put.json()["text"] == "X+"
    image = client.get("/firmware/decks/SIMDECK0/keys/0/image")
    assert image.headers["content-type"] == "image/jpeg" and _size(image.content)[1] == (120, 120)
    assert client.get("/firmware/decks/SIMDECK0/keys/1/image").status_code == 404
    assert client.put("/firmware/decks/SIMDECK0/strip", json={"text": "hello"}).status_code == 200
    assert _size(client.get("/firmware/decks/SIMDECK0/strip/image").content)[1] == (800, 100)
    assert client.put("/firmware/decks/SIMDECK0/brightness", json={"percent": 40}).json() == {
        "brightness": 40
    }
    sent = client.post(
        "/firmware/decks/SIMDECK0/events", json={"kind": "knob-turn", "index": 2, "value": 4}
    )
    assert sent.status_code == 201 and sent.json()["seq"] == 1
    heard = client.get("/firmware/decks/SIMDECK0/events", params={"since": 0}).json()
    assert [(e["kind"], e["index"], e["value"]) for e in heard["events"]] == [("knob-turn", 2, 4)]
    state = client.get("/firmware/decks/SIMDECK0").json()
    assert state["keys_drawn"]["0"]["text"] == "X+" and state["strip_drawn"]["text"] == "hello"
    assert "jpeg" not in state["keys_drawn"]["0"] and state["last_event"] == 1
    assert client.post("/firmware/decks/SIMDECK0/release").json() == {"released": True}
    assert client.post("/firmware/decks/SIMDECK0/release").json() == {"released": False}


def test_the_routes_refuse_what_the_deck_could_not_take(client):
    assert client.get("/firmware/decks/NOPE").status_code == 404
    assert client.put("/firmware/decks/SIMDECK0/keys/9", json={"text": "x"}).status_code == 422
    assert (
        client.put(
            "/firmware/decks/SIMDECK0/keys/0", json={"text": "x", "colour": "plaid"}
        ).status_code
        == 422
    )
    assert (
        client.put("/firmware/decks/SIMDECK0/brightness", json={"percent": 101}).status_code == 422
    )
    bad = client.post(
        "/firmware/decks/SIMDECK0/events", json={"kind": "key", "index": 9, "value": True}
    )
    assert bad.status_code == 422 and "no key 9" in bad.json()["detail"]


def test_with_no_library_the_list_says_what_to_install(client, monkeypatch):
    monkeypatch.setenv("APOTHECARY_SERIAL_ENGINE", "pyserial")
    monkeypatch.setitem(sys.modules, "StreamDeck", None)  # an import of it fails
    body = client.get("/firmware/decks").json()
    assert body["decks"] == [] and "uv sync --extra deck" in body["problem"]
    assert client.get("/firmware/decks/anything").status_code == 503


# --- the module -----------------------------------------------------------------------


def test_the_module_stands_beside_arduino_and_rust_and_builds_nothing():
    assert [m.id for m in modules()] == ["arduino", "rust-esp32", "stream-deck"]
    module = get_module("stream-deck")
    assert module.sketch_in(None, {}, None) is None
    for refusal in (
        lambda: module.build(None, None, None),
        lambda: module.flash(None, None, "/dev/x", None),
        lambda: module.install(print),
    ):
        with pytest.raises(ToolchainError):
            refusal()
    assert module.artifact(None, None) is None and module.ports() is None


def test_the_module_says_what_is_missing_and_what_installs_it(monkeypatch):
    from apothecary.firmware.modules import stream_deck

    module = get_module("stream-deck")
    monkeypatch.setattr(stream_deck, "package_version", lambda: None)
    monkeypatch.setattr(stream_deck, "hidapi", lambda: None)
    status = module.status()
    assert not status.ok and not status.installable
    assert [t.ok for t in status.tools] == [False, False]
    assert any("uv sync --extra deck" in p for p in status.problems)
    assert any("libhidapi-libusb0" in p for p in status.problems)
    monkeypatch.setattr(stream_deck, "package_version", lambda: "0.10.0")
    monkeypatch.setattr(stream_deck, "hidapi", lambda: "libhidapi-libusb.so.0")
    status = module.status()
    assert status.ok and status.problems == [] and status.tools[0].version == "0.10.0"
    assert set(status.can) == set(module.can) and "hear keys, knobs and touches" in status.can


def test_validate_says_each_tool_found_with_what_it_has(fake_arduino_cli, monkeypatch):
    """The package is found by its version and hidapi by its file, neither having the
    other: each is said with what it has, and `firmware validate` runs to its end."""
    from click.testing import CliRunner

    from apothecary.cli import cli
    from apothecary.firmware.modules import stream_deck

    monkeypatch.setattr(stream_deck, "package_version", lambda: "0.10.0")
    monkeypatch.setattr(stream_deck, "hidapi", lambda: "libhidapi-libusb.so.0")
    result = CliRunner().invoke(cli, ["firmware", "validate"])
    assert result.exit_code == 0, result.output
    assert "  ✓ python-elgato-streamdeck 0.10.0\n" in result.output
    assert "  ✓ hidapi: libhidapi-libusb.so.0\n" in result.output


def test_the_decks_command_lists_what_is_found_and_says_when_none_is(monkeypatch):
    import json

    from click.testing import CliRunner

    from apothecary.cli import cli

    listed = CliRunner().invoke(cli, ["firmware", "decks"])
    assert listed.exit_code == 0, listed.output
    assert "SIMDECK0  Stream Deck +  0x0fd9:0x0084  8 keys, 4 knobs  (simulated)" in listed.output
    as_json = CliRunner().invoke(cli, ["firmware", "decks", "--json-out"])
    assert [d["id"] for d in json.loads(as_json.output)] == ["SIMDECK0"]
    monkeypatch.setenv(deck.SIMULATED_DECK_ENV, "")
    assert CliRunner().invoke(cli, ["firmware", "decks"]).output == "No Stream Deck + found.\n"
    monkeypatch.setenv("APOTHECARY_SERIAL_ENGINE", "pyserial")
    monkeypatch.setitem(sys.modules, "StreamDeck", None)  # an import of it fails
    missing = CliRunner().invoke(cli, ["firmware", "decks"])
    assert missing.exit_code != 0 and "uv sync --extra deck" in missing.output


def test_the_toolchains_route_and_the_bench_carry_it(client):
    ids = [m["id"] for m in client.get("/firmware/toolchains").json()]
    assert ids == ["arduino", "rust-esp32", "stream-deck"]
    status = client.get("/firmware/status").json()
    assert "stream-deck" in [m["id"] for m in status["toolchains"]]


# --- the real library's wiring, with a stand-in for it -----------------------------------


class _Device:
    """What python-elgato-streamdeck's StreamDeckPlus offers, counting what is asked."""

    def __init__(self, name, kind="Stream Deck +"):
        self.name, self.kind, self.opened, self.closed = name, kind, 0, 0
        self.images, self.strip, self.callbacks = {}, [], {}

    def deck_type(self):
        return self.kind

    def id(self):
        return self.name

    def open(self):
        self.opened += 1

    def close(self):
        self.closed += 1

    def get_serial_number(self):
        return "CL12345"

    def set_key_callback(self, cb):
        self.callbacks["key"] = cb

    def set_dial_callback(self, cb):
        self.callbacks["dial"] = cb

    def set_touchscreen_callback(self, cb):
        self.callbacks["touch"] = cb

    def set_key_image(self, key, image):
        self.images[key] = image

    def set_touchscreen_image(self, image, x, y, w, h):
        self.strip.append((len(image), x, y, w, h))

    def set_brightness(self, percent):
        self.brightness = percent

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Event(types.SimpleNamespace):
    pass


@pytest.fixture
def real(monkeypatch):
    monkeypatch.setenv("APOTHECARY_SERIAL_ENGINE", "pyserial")
    plus, xl = _Device("path/one"), _Device("path/two", "Stream Deck XL")
    manager = types.SimpleNamespace(enumerate=lambda: [plus, xl])
    monkeypatch.setattr(deck, "_manager", lambda: manager)
    return plus, xl


def test_a_real_deck_is_listed_unopened_and_only_a_plus(real):
    plus, xl = real
    found = deck.get_decks().list()
    assert [(d.id, d.simulated) for d in found] == [("path_one", False)]
    assert plus.opened == xl.opened == 0


def test_a_real_deck_is_opened_by_what_acts_on_it_and_its_reports_are_events(real):
    plus, _ = real
    one = deck.get_decks().get("path_one")
    assert plus.opened == 1 and one.info.serial == "CL12345"
    assert deck.get_decks().get("path_one") is one and plus.opened == 1
    one.set_key(0, "X+")
    one.set_strip("hi")
    one.set_brightness(30)
    assert (
        set(plus.images) == {0} and plus.strip[0][1:] == (0, 0, 800, 100) and plus.brightness == 30
    )
    plus.callbacks["key"](plus, 5, True)
    plus.callbacks["dial"](plus, 2, _Event(name="TURN"), -2)
    plus.callbacks["dial"](plus, 2, _Event(name="PUSH"), True)
    plus.callbacks["touch"](plus, _Event(name="SHORT"), (400, 50))
    plus.callbacks["touch"](plus, _Event(name="DRAG"), (10, 20, 300, 25))
    assert [(e.kind, e.index, e.value) for e in one.events()] == [
        ("key", 5, True),
        ("knob-turn", 2, -2),
        ("knob-press", 2, True),
        ("touch", 0, {"kind": "short", "x": 400, "y": 50}),
        ("touch", 0, {"kind": "drag", "x": 10, "y": 20, "x_out": 300, "y_out": 25}),
    ]
    with pytest.raises(DeckUnavailable, match="real deck"):
        one.inject("key", 0, True)
    assert deck.get_decks().release("path_one") and plus.closed == 1
    assert plus.callbacks["key"] is None


def test_a_real_deck_that_will_not_open_says_why_and_is_tried_again(real, client):
    """The library's open fails as it does when this account may not write the deck's
    USB device: the deck is refused naming the udev rule, the route answers 503 with it,
    and nothing is kept, so the same deck opens on the next try once the rule is in."""
    plus, _ = real

    def will_not_open():
        raise RuntimeError("Could not open HID device.")

    plus.open = will_not_open
    with pytest.raises(DeckUnavailable, match="udev rule"):
        deck.get_decks().get("path_one")
    answer = client.get("/firmware/decks/path_one")
    assert answer.status_code == 503, answer.text
    assert "would not open (Could not open HID device.)" in answer.json()["detail"]
    del plus.open  # the rule in place
    assert deck.get_decks().get("path_one").info.serial == "CL12345" and plus.opened == 1


def test_without_the_hid_library_a_real_listing_says_so(monkeypatch):
    monkeypatch.setenv("APOTHECARY_SERIAL_ENGINE", "pyserial")

    def broken():
        raise RuntimeError("No suitable LibUSB HIDAPI library found on this system.")

    monkeypatch.setattr(deck, "_manager", lambda: types.SimpleNamespace(enumerate=broken))
    with pytest.raises(DeckUnavailable, match="libhidapi-libusb0"):
        deck.get_decks().list()


def test_the_real_library_drives_the_adapter_over_its_own_dummy_transport(monkeypatch):
    """python-elgato-streamdeck's dummy transport: enumerates every model it knows with
    nothing behind them and reads zeros, so no device and no HID library is needed."""
    pytest.importorskip("StreamDeck")
    from StreamDeck.DeviceManager import DeviceManager

    monkeypatch.setenv("APOTHECARY_SERIAL_ENGINE", "pyserial")
    monkeypatch.setattr(deck, "_manager", lambda: DeviceManager(transport="dummy"))
    found = deck.get_decks().list()
    assert len(found) >= 1 and all(d.model == "Stream Deck +" and not d.simulated for d in found)
    one = deck.get_decks().get(found[0].id)
    one.set_key(0, "X+", "blue")
    one.set_strip("cnc_router", "green")
    one.set_brightness(50)
    assert one.events() == []  # the dummy reads zeros: no key, knob or touch
    assert deck.get_decks().release(found[0].id)
