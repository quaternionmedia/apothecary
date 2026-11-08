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

## The controller

The knobs jog the garage's two machines. `apothecary/firmware/deck_control.py` runs one
layout on a deck:

- **The top row's keys**: 0 **PRINTER** and 1 **ROUTER** choose the machine (held twice,
  they arm its control, below), 2 **STEP** cycles 0.1, 1 and 10 mm.
- **The bottom row's keys** are the stops, two classes of them: 4 **STOP printer_1** and
  5 **STOP cnc_router**, dark red, each stopping that machine alone, and 7 **STOP ALL**,
  bright red and last, nearest a hand resting on the knobs, stopping every machine, each
  by its own dialect's stop. Key 6 is dark.
- **The knobs**: one to three jog X, Y and Z by their steps of the chosen size; the fourth
  turns the router's spindle speed in steps of 1000 rpm, or extrudes 1 mm a step on the
  printer.

The strip says which machine, whether its control is armed and for how long, the chosen
machine's last poll (X, Y, Z and the fourth quantity), the step, and what the last turn did
or why it did nothing.

**Nothing the deck sends bypasses what bounds a person's jog.** Every line goes through
`devices.printer_control`, the function behind `POST /firmware/printers/command`:

- the port's control latch must be armed, and it is armed the page's way (⚙ Control in the
  Machine window) or by **two sequential long presses** of the machine's key: a press held
  0.8 s chooses the machine and says on the strip that a second will arm its control; the
  second, of the same key, within 5 s of the first being let go, arms it for the latch's own
  five minutes through the same `ControlLatch`. One long press alone, a second after the
  window, a short press, another key or a knob turned between them, or a long press of the
  other machine's key arms nothing. A turn while disarmed sends nothing and the strip says
  *disarmed*;
- the line is normalised in the port's dialect and refused outside its bounds before it
  reaches the port: a router's jog is `$J=G91 G21 X.. F1000` and at most 600 mm, a
  printer's is `G91`, `G1 X.. F3000` and `G90`, at most 300 mm, with the return to
  absolute positioning sent even when the move was refused; the spindle is clamped to
  `SPINDLE_MAX_RPM` and turned only while it turns; an extrude is the one bounded line of
  [the firmware guide](firmware.md#control-behind-a-latch), 10 mm at most and 300 mm/min,
  with `M83` before it;
- a job holding the port refuses a line its dialect does not allow a job;
- a key for one kind of machine never moves a board of another: the port is polled and its
  kind checked before a line goes;
- a stop key sends the port's dialect's own stop, `devices.emergency_stop_for(port)`: a
  printer's `M112`, a router's soft reset. It goes whatever the latch says, as the pad's
  E-STOP does, and waits on no poll. The everything key sends each machine's own, one
  after another, and goes on to the next when one cannot be reached; the strip names
  which it reached.

**The machine's own red button is faster than any of this**, and stays the stop to reach
for: the deck's stop keys are a USB report, a host process, a link and a queue away from the
controller. Keep a hand on the machine's own switch, as the bench checklist says.

The layout starts on a deck when `APOTHECARY_DECK_CONTROL` is set (the demo sets it), or
when `POST /firmware/decks/{id}/control` with `{"on": true}` asks; `GET` on the same route
says whether it runs, the machine chosen, the step, the control's seconds left, what it
said last and the lines it sent. A real deck is opened by it, which takes the device from
any other program that has it, so it is started on purpose.
[Walkthrough 27](../walkthrough/27-the-deck-jogging-the-machines.md) goes round it on the
simulated bench, written by `tests/e2e/test_deck_jog.py`.

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
