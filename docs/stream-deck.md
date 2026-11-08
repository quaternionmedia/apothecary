# The Stream Deck +

An Elgato Stream Deck + has eight LCD keys in two rows of four, a touch strip under
them and four knobs under those. Apothecary finds one on USB, draws its keys and its
strip, and hears its keys, knobs and touches. The part that stands on the garage's
workbench is [parts/stream_deck_plus](../parts/stream_deck_plus/README.md); the code
that speaks to the device is `apothecary/firmware/deck.py`.

## Setting up

The Python package is an optional dependency and the HID library is the system's:

```bash
uv sync --extra deck                    # python-elgato-streamdeck (MIT, no Python dependency of its own)
sudo apt install libhidapi-libusb0      # Debian and Ubuntu: the hidapi the package loads with ctypes
uv run apothecary firmware decks        # the decks found; none is opened
```

`apothecary check` and the Bench's toolchain card list the module, **Stream Deck +**,
with its two tools as found and what each missing one needs. Its Install is refused
and says the same: nothing here fetches a package or a system library. Without
either, the module is not installed, every other part of apothecary works as before,
and `GET /firmware/decks` answers `{"decks": [], "problem": "..."}` naming what to
install.

A person who is not root on the machine usually needs a udev rule to open a HID
device; Elgato's vendor id is `0x0fd9` and the Stream Deck +'s product id `0x0084`.
The library's own README gives the rule.

Apothecary connects to nothing off this machine for this: the library enumerates and
reads HID reports through the system's hidapi, and the process stays under the guard
of `apothecary/stays_local.py`.

## What is found, drawn and heard

- **Found.** Elgato's vendor id and the Stream Deck +'s product id, by the library's
  enumeration. A deck of another model is not listed. Listing opens nothing; a deck
  is opened by the first thing that acts on it (a key set, the events read, a
  controller started) and stays open until `POST /firmware/decks/{id}/release`.
- **Drawn.** A key is 120 by 120 pixels and the strip 800 by 100, each a JPEG, as the
  device takes them: a line of text on a colour (`black`, `grey`, `blue`, `green`,
  `amber`, `red` or `#rrggbb`) with an optional smaller line under it, drawn with
  Pillow. A deck cannot be asked what it shows, so what was sent is kept, and
  `GET /firmware/decks/{id}/keys/{n}/image` and `.../strip/image` serve it.
- **Heard.** Each report becomes an event with a sequence number: `key` (a key's
  index 0 to 7, pressed or released), `knob-turn` (a knob's index 0 to 3, so many
  steps, negative counter-clockwise), `knob-press` (pressed or released) and `touch`
  (the strip tapped, held or dragged, with its coordinates in strip pixels, and the
  drag's end). The last two hundred are kept; `GET /firmware/decks/{id}/events?since=N`
  reads the ones after N.

```
GET  /firmware/decks                           → the decks found (nothing is opened)
GET  /firmware/decks/{id}                      → one as drawn: keys, strip, brightness, last event
PUT  /firmware/decks/{id}/keys/{n}             {"text": "X+", "small": "1 mm", "colour": "blue"}
PUT  /firmware/decks/{id}/strip                {"text": "cnc_router", "colour": "green"}
PUT  /firmware/decks/{id}/brightness           {"percent": 60}
GET  /firmware/decks/{id}/keys/{n}/image       → the JPEG last sent to a key
GET  /firmware/decks/{id}/strip/image
GET  /firmware/decks/{id}/events?since=N       → what was heard
POST /firmware/decks/{id}/events               a simulated deck's event, given (a real deck: 409)
POST /firmware/decks/{id}/release              → let go of the device
```

## In the page

The **Deck** window (⊞ Windows › Deck, the ring's Panels › Deck, or **Open Deck** on the
`stream_deck` piece of the garage) shows the first deck found: its eight keys and its
strip as the images last sent to them, `–` where nothing has been drawn from here, its
four knobs, and the events it has heard, newest first. It follows the deck every second
and a half while it is in front, which opens the deck. A simulated deck is pressed from
it -- a key, a knob turned a step either way or pressed, the strip tapped -- each the
event a real deck reports, posted to the deck's routes; a real deck is pressed by hand
and the window's controls are off.
[Walkthrough 26](../walkthrough/26-the-stream-deck.md) goes round it, written by
`tests/e2e/test_deck.py`.

## Simulated

With `APOTHECARY_SERIAL_ENGINE=simulated` no HID device is listed or opened. The decks
found are the ones `APOTHECARY_SIMULATED_DECK` names (comma-separated), each a pretend
Stream Deck + that keeps the images it is sent and hears the events
`POST /firmware/decks/{id}/events` gives it, validated as a real deck's reports could
be: a knob turns by a whole number of steps, a touch is a tap, a hold or a drag. The
demo (`apothecary serve --demo`) has one, `DEMODECK`.

`tests/test_firmware_deck.py` holds the seam against the simulated deck, against a
stand-in for the library's device that counts what is opened, and against the
library's own dummy transport, which enumerates every model it knows with nothing
behind it. It skips that last test, saying so, where the optional package is not
installed. No test opens a HID device. What only a deck shows is a row of
[the bench checklist](bench-checklist.md).
