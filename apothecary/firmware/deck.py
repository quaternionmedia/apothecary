"""The Elgato Stream Deck +: found on USB, drawn from here, heard.

A Stream Deck + has eight LCD keys in two rows of four, a touch strip under them
and four knobs under that. This module is the one place apothecary speaks to it:

- **Finding** is the HID library's enumeration: Elgato's vendor id ``0x0fd9`` and
  the Stream Deck +'s product id ``0x0084`` (``python-elgato-streamdeck``'s
  ``ProductIDs.py``). Nothing is opened to make the list.
- **Drawing** is Pillow: a label on a colour, 120 by 120 pixels a key and 800 by
  100 the strip, as JPEG, the form the device takes. What was sent is kept
  (``Deck.keys``, ``Deck.strip``), since a deck cannot be asked what it shows.
- **Hearing** is the deck's reports read as ``DeckEvent``s: a key pressed or
  released, a knob turned by so many steps or pressed, the strip tapped, held or
  dragged. Each is kept in a short log with a sequence number and handed to the
  listeners registered with ``Deck.listen`` (``firmware/deck_control.py`` is one).

The transport is ``python-elgato-streamdeck`` (``StreamDeck``, MIT, no Python
dependency of its own), the optional dependency ``deck``; it loads the system's
hidapi with ctypes and reaches no host. With it or hidapi missing, ``decks()``
says what to install and nothing else here fails.

With ``APOTHECARY_SERIAL_ENGINE=simulated`` no HID device is touched: the decks
listed are the ones ``APOTHECARY_SIMULATED_DECK`` names (comma-separated), each a
pretend Stream Deck + that keeps the images it is sent and hears the events a
route gives it (``Deck.inject``), as ``gcode.SimulatedPrinter`` stands in for the
Ender.

A real deck is opened only by what acts on it (a key set, the log read, a
controller started), never by listing; one open stays open until released.
"""

from __future__ import annotations

import io
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, List, Optional, Protocol

from pydantic import BaseModel, Field

from .toolchains import ToolchainError

ELGATO = 0x0FD9
STREAM_DECK_PLUS = 0x0084  # python-elgato-streamdeck, ProductIDs.USB_PID_STREAMDECK_PLUS
MODEL = "Stream Deck +"
KEY_COLS, KEY_ROWS = 4, 2
KEY_COUNT = KEY_COLS * KEY_ROWS
KNOB_COUNT = 4
KEY_SIZE = (120, 120)
STRIP_SIZE = (800, 100)
SIMULATED_DECK_ENV = "APOTHECARY_SIMULATED_DECK"
EVENT_LOG = 200  # events kept per deck

KEY, KNOB_TURN, KNOB_PRESS, TOUCH = "key", "knob-turn", "knob-press", "touch"
EVENT_KINDS = (KEY, KNOB_TURN, KNOB_PRESS, TOUCH)
TOUCHES = ("short", "long", "drag")

ID_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,80}$")

COLOURS = {
    "black": "#000000",
    "grey": "#3a3f47",
    "blue": "#1f5fbf",
    "green": "#1f8a4c",
    "amber": "#b8860b",
    "red": "#b3261e",
}


class DeckUnavailable(ToolchainError):
    """The Python package or the HID library is not there, or the deck is gone."""


class DeckInfo(BaseModel):
    """One deck found, none of them opened."""

    id: str
    model: str = MODEL
    vid: str = f"0x{ELGATO:04x}"
    pid: str = f"0x{STREAM_DECK_PLUS:04x}"
    simulated: bool = False
    keys: int = KEY_COUNT
    knobs: int = KNOB_COUNT
    strip: List[int] = Field(default_factory=lambda: list(STRIP_SIZE))
    serial: Optional[str] = None  # only a deck that is open says it


@dataclass(frozen=True)
class DeckEvent:
    """What the deck reported: ``index`` is the key or the knob, ``value`` a key's
    pressed state, a knob's pressed state or its steps (negative counter-clockwise),
    a touch's ``{"kind", "x", "y"}`` with ``x_out`` and ``y_out`` for a drag."""

    seq: int
    kind: str
    index: int
    value: object
    at: float = field(default_factory=time.time)

    def to_json(self) -> dict:
        return {
            "seq": self.seq,
            "kind": self.kind,
            "index": self.index,
            "value": self.value,
            "at": self.at,
        }


# --- drawing -----------------------------------------------------------------------


def _font(size: int):
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # a Pillow before 10.1 has the one size
        return ImageFont.load_default()


def _colour(name: Optional[str]) -> str:
    if not name:
        return COLOURS["grey"]
    if name in COLOURS:
        return COLOURS[name]
    if re.fullmatch(r"#[0-9a-fA-F]{6}", name):
        return name
    raise ValueError(f"not a colour: {name!r} (one of {', '.join(COLOURS)}, or #rrggbb)")


def render(size, text: str, colour: Optional[str] = None, small: Optional[str] = None) -> bytes:
    """``text`` centred on ``colour`` as a JPEG of ``size``; ``small`` a line under it."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", size, _colour(colour))
    pen = ImageDraw.Draw(img)
    big = max(12, min(size[1] // 3, size[0] // max(2, len(text) or 1)))
    pen.text(
        (size[0] / 2, size[1] / 2 - (size[1] // 10 if small else 0)),
        text,
        fill="white",
        font=_font(big),
        anchor="mm",
    )
    if small:
        pen.text(
            (size[0] / 2, size[1] * 0.82),
            small,
            fill="#dddddd",
            font=_font(max(10, size[1] // 7)),
            anchor="mm",
        )
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue()


def render_key(text: str, colour: Optional[str] = None, small: Optional[str] = None) -> bytes:
    return render(KEY_SIZE, text, colour, small)


def render_strip(text: str, colour: Optional[str] = None, small: Optional[str] = None) -> bytes:
    return render(STRIP_SIZE, text, colour, small)


# --- links: the deck itself, simulated or real --------------------------------------


class Link(Protocol):
    def set_key(self, index: int, jpeg: bytes) -> None: ...
    def set_strip(self, jpeg: bytes) -> None: ...
    def set_brightness(self, percent: int) -> None: ...
    def serial(self) -> Optional[str]: ...
    def close(self) -> None: ...


Report = Callable[[str, int, object], None]


class SimulatedLink:
    """A pretend Stream Deck +: it keeps what it is sent and says nothing by itself."""

    def __init__(self, report: Report):
        self.report = report
        self.brightness = 100
        self.sent: List[tuple] = []

    def set_key(self, index: int, jpeg: bytes) -> None:
        self.sent.append(("key", index, len(jpeg)))

    def set_strip(self, jpeg: bytes) -> None:
        self.sent.append(("strip", 0, len(jpeg)))

    def set_brightness(self, percent: int) -> None:
        self.brightness = percent

    def serial(self) -> Optional[str]:
        return None

    def close(self) -> None:
        pass


class HidLink:
    """The real deck, through ``python-elgato-streamdeck``: opened once, its reader
    thread's callbacks turned into ``DeckEvent`` reports."""

    def __init__(self, device, report: Report):
        self.device, self.report = device, report
        device.open()
        device.set_key_callback(self._key)
        device.set_dial_callback(self._dial)
        device.set_touchscreen_callback(self._touch)

    def _key(self, deck, key, state) -> None:
        self.report(KEY, int(key), bool(state))

    def _dial(self, deck, dial, event, value) -> None:
        name = getattr(event, "name", str(event)).upper()
        if name == "TURN":
            self.report(KNOB_TURN, int(dial), int(value))
        else:
            self.report(KNOB_PRESS, int(dial), bool(value))

    def _touch(self, deck, event, value) -> None:
        name = getattr(event, "name", str(event)).lower()
        kind = {"short": "short", "long": "long", "drag": "drag"}.get(name, name)
        point = dict(zip(("x", "y", "x_out", "y_out"), (value or ()), strict=False))
        self.report(TOUCH, 0, {"kind": kind, **{k: int(v) for k, v in point.items()}})

    def set_key(self, index: int, jpeg: bytes) -> None:
        with self.device:
            self.device.set_key_image(index, jpeg)

    def set_strip(self, jpeg: bytes) -> None:
        with self.device:
            self.device.set_touchscreen_image(jpeg, 0, 0, STRIP_SIZE[0], STRIP_SIZE[1])

    def set_brightness(self, percent: int) -> None:
        with self.device:
            self.device.set_brightness(percent)

    def serial(self) -> Optional[str]:
        try:
            return self.device.get_serial_number()
        except Exception:  # noqa: BLE001 -- a deck that went away says nothing
            return None

    def close(self) -> None:
        try:
            self.device.set_key_callback(None)
            self.device.set_dial_callback(None)
            self.device.set_touchscreen_callback(None)
            self.device.close()
        except Exception:  # noqa: BLE001 -- unplugged: nothing more to let go of
            pass


# --- a deck: what was sent, what was heard -------------------------------------------


Listener = Callable[[DeckEvent], None]


class Deck:
    """One open deck: the keys and the strip as last drawn, and the events heard."""

    def __init__(self, info: DeckInfo, make_link: Callable[[Report], Link]):
        self.info = info
        self.keys: Dict[int, dict] = {}
        self.strip: Optional[dict] = None
        self.brightness = 100
        self._events: Deque[DeckEvent] = deque(maxlen=EVENT_LOG)
        self._seq = 0
        self._listeners: List[Listener] = []
        self._lock = threading.Lock()
        self.link = make_link(self._heard)
        serial = self.link.serial()
        if serial:
            self.info = info.model_copy(update={"serial": serial})

    # drawing
    def set_key(
        self, index: int, text: str, colour: Optional[str] = None, small: Optional[str] = None
    ) -> bytes:
        if not 0 <= index < self.info.keys:
            raise ValueError(
                f"no key {index}: a {self.info.model} has keys 0 to {self.info.keys - 1}"
            )
        jpeg = render_key(text, colour, small)
        self.link.set_key(index, jpeg)
        with self._lock:
            self.keys[index] = {"text": text, "small": small, "colour": colour, "jpeg": jpeg}
        return jpeg

    def set_strip(
        self, text: str, colour: Optional[str] = None, small: Optional[str] = None
    ) -> bytes:
        jpeg = render_strip(text, colour, small)
        self.link.set_strip(jpeg)
        with self._lock:
            self.strip = {"text": text, "small": small, "colour": colour, "jpeg": jpeg}
        return jpeg

    def set_brightness(self, percent: int) -> None:
        if not 0 <= percent <= 100:
            raise ValueError("brightness is 0 to 100 per cent")
        self.link.set_brightness(percent)
        self.brightness = percent

    # hearing
    def _heard(self, kind: str, index: int, value: object) -> None:
        with self._lock:
            self._seq += 1
            event = DeckEvent(self._seq, kind, index, value)
            self._events.append(event)
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:  # noqa: BLE001 -- one listener's fault is not the deck's
                pass

    def inject(self, kind: str, index: int, value: object) -> DeckEvent:
        """An event as the deck would report it: a simulated deck's only source."""
        if not self.info.simulated:
            raise DeckUnavailable(f"{self.info.id} is a real deck: it reports for itself")
        _check_event(kind, index, value, self.info)
        self._heard(kind, index, value)
        return self._events[-1]

    def events(self, since: int = 0) -> List[DeckEvent]:
        with self._lock:
            return [e for e in self._events if e.seq > since]

    def listen(self, listener: Listener) -> Callable[[], None]:
        """``listener`` told of each event from now on; the call that stops it."""
        with self._lock:
            self._listeners.append(listener)

        def stop() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return stop

    def close(self) -> None:
        self.link.close()

    def state(self) -> dict:
        with self._lock:
            return {
                **self.info.model_dump(),
                "brightness": self.brightness,
                "keys_drawn": {
                    str(i): {k: v for k, v in key.items() if k != "jpeg"}
                    for i, key in sorted(self.keys.items())
                },
                "strip_drawn": None
                if self.strip is None
                else {k: v for k, v in self.strip.items() if k != "jpeg"},
                "last_event": self._seq,
            }


def _check_event(kind: str, index: int, value: object, info: DeckInfo) -> None:
    if kind not in EVENT_KINDS:
        raise ValueError(f"not an event: {kind!r} (one of {', '.join(EVENT_KINDS)})")
    if kind == KEY and not 0 <= index < info.keys:
        raise ValueError(f"no key {index}")
    if kind in (KNOB_TURN, KNOB_PRESS) and not 0 <= index < info.knobs:
        raise ValueError(f"no knob {index}")
    if kind == KNOB_TURN and (not isinstance(value, int) or isinstance(value, bool) or value == 0):
        raise ValueError("a knob turns by a whole number of steps, not zero")
    if kind in (KEY, KNOB_PRESS) and not isinstance(value, bool):
        raise ValueError("a press is true, a release false")
    if kind == TOUCH:
        if not isinstance(value, dict) or value.get("kind") not in TOUCHES:
            raise ValueError(f"a touch is {{kind: one of {', '.join(TOUCHES)}, x, y}}")
        if not all(isinstance(value.get(k), int) for k in ("x", "y")):
            raise ValueError("a touch has whole-number x and y")


# --- finding them ---------------------------------------------------------------------


def simulated_ids() -> List[str]:
    raw = os.environ.get(SIMULATED_DECK_ENV, "")
    ids = [p.strip() for p in raw.split(",") if p.strip()]
    for one in ids:
        if not ID_RE.match(one):
            raise ValueError(f"{SIMULATED_DECK_ENV}: not a deck's name: {one!r}")
    return ids


def _engine() -> str:
    from .gcode import serial_engine

    return serial_engine()


def _manager():
    """The HID library's manager, or why there is none."""
    try:
        from StreamDeck.DeviceManager import DeviceManager
    except ImportError as exc:
        raise DeckUnavailable(
            "the Stream Deck library is not installed: `uv sync --extra deck` "
            f"(python-elgato-streamdeck; {exc})"
        ) from exc
    return DeviceManager()


def _safe_id(raw: object) -> str:
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    return re.sub(r"[^A-Za-z0-9_.:\-]+", "_", text).strip("_")[:80] or "deck"


def _real_devices() -> List[tuple]:
    """``(DeckInfo, device)`` for each Stream Deck + the HID library enumerates; no device is
    opened. Raises ``DeckUnavailable`` with the install when the package or hidapi is missing."""
    try:
        found = _manager().enumerate()
    except DeckUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 -- the library's TransportError: no hidapi
        raise DeckUnavailable(
            f"the HID library cannot be used: {exc} (on Debian and Ubuntu: `sudo apt install libhidapi-libusb0`)"
        ) from exc
    out = []
    for device in found:
        try:
            if device.deck_type() != MODEL:
                continue
            name = _safe_id(device.id())
        except Exception:  # noqa: BLE001 -- a device that will not say what it is is not ours
            continue
        out.append((DeckInfo(id=name), device))
    return out


class Decks:
    """The decks found, opened on first use and kept open until released."""

    def __init__(self):
        self._open: Dict[str, Deck] = {}
        self._lock = threading.RLock()

    def list(self) -> List[DeckInfo]:
        """Every deck found, simulated or real, none of them opened. Raises
        ``DeckUnavailable`` when a real deck cannot be looked for."""
        if _engine() == "simulated":
            return [DeckInfo(id=i, simulated=True) for i in simulated_ids()]
        with self._lock:
            opened = {i: d.info for i, d in self._open.items()}
        found = [info for info, _ in _real_devices()]
        return [opened.get(info.id, info) for info in found]

    def get(self, deck_id: str) -> Deck:
        if not ID_RE.match(deck_id):
            raise ValueError(f"not a deck's name: {deck_id!r}")
        with self._lock:
            if deck_id in self._open:
                return self._open[deck_id]
            if _engine() == "simulated":
                if deck_id not in simulated_ids():
                    raise KeyError(deck_id)
                deck = Deck(DeckInfo(id=deck_id, simulated=True), SimulatedLink)
            else:
                device = next((d for info, d in _real_devices() if info.id == deck_id), None)
                if device is None:
                    raise KeyError(deck_id)
                deck = Deck(DeckInfo(id=deck_id), lambda report: HidLink(device, report))
            self._open[deck_id] = deck
            return deck

    def release(self, deck_id: str) -> bool:
        with self._lock:
            deck = self._open.pop(deck_id, None)
        if deck is None:
            return False
        deck.close()
        return True

    def release_all(self) -> None:
        for deck_id in list(self._open):
            self.release(deck_id)


_DECKS: Optional[Decks] = None


def get_decks() -> Decks:
    global _DECKS
    if _DECKS is None:
        _DECKS = Decks()
    return _DECKS


def reset_decks() -> None:
    """Let go of every deck and forget them: between tests, or after an install."""
    global _DECKS
    if _DECKS is not None:
        _DECKS.release_all()
    _DECKS = None
