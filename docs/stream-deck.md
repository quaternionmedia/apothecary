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

A person who is not root on the machine needs a udev rule to open the deck: the
library opens it through libusb, and its USB device is root's to write. Elgato's
vendor id is `0x0fd9` and the Stream Deck +'s product id `0x0084`; the library's
documentation gives this rule, for every Elgato deck:

```bash
printf 'SUBSYSTEMS=="usb", ATTRS{idVendor}=="0fd9", GROUP="users", TAG+="uaccess"\n' | sudo tee /etc/udev/rules.d/10-streamdeck.rules
sudo udevadm control --reload-rules     # then unplug the deck and plug it in again
```

Without it the deck is listed and not opened: `GET /firmware/decks/{id}` answers 503
naming the rule, and the Deck window says the same.

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

## A deck lost and found

A deck that leaves USB for a moment -- a lead knocked, a hub that dropped it -- comes back
as another device at the same place. `Deck.mend` opens it again and sends it every key,
the strip and the brightness as they were last drawn, and what listened to it goes on
listening. The layout looks at its deck twice a second and mends it as soon as it is back;
a draw that fails mends and is sent once more; and `GET /firmware/decks/{id}` mends a deck
no layout runs on. While it is gone the deck's state says `"alive": false` with when it was
lost, a draw answers 503 in words, and the Deck window says the deck is not answering.
`"mended"` counts the times. A key held, or a first long press, when it went is forgotten.

## In the page

The **Deck** window (⊞ Windows › Deck, the ring's Panels › Machine › Knobs › Deck, or **Open Deck** on the
`stream_deck` piece of the garage) shows the first deck found: its eight keys and its
strip as the images last sent to them, `–` where nothing has been drawn from here, its
four knobs, and the events it has heard, newest first, in a list that scrolls. It follows
the deck every second and a half while it is in front, which opens the deck, and asks for
its events four times a second between, so what is heard is shown where it happened as it
happens: a key or a knob held is marked for as long as it is down, and a press, the way a
knob turned and the place the strip was touched are each lit for a moment. A real deck's
keys and strip are drawn as bright as a simulated one's. A simulated deck is pressed from
it -- a key, a knob turned a step either way or pressed, the strip tapped -- each the
event a real deck reports, posted to the deck's routes; a real deck is pressed by hand
and the window's controls are off.
[Walkthrough 26](../walkthrough/26-the-stream-deck.md) goes round it, written by
`tests/e2e/test_deck.py`.

## The controller

The knobs jog the garage's two machines. `apothecary/firmware/deck_control.py` runs one
layout on a deck:

- **The top row's keys**: 0 **PRINTER** and 1 **ROUTER** choose the machine (held twice,
  they arm its control, below), 2 **STEP** cycles 0.1, 1 and 10 mm, and 3 **DISARM** lets go
  of every machine's control at one press, blue while any is armed and grey when none is.
  It stops nothing -- a move under way finishes -- and the stop keys are the stops.
- **Key 6** is **UNLOCK**, amber, while the chosen router is in alarm:
  it sends the router's `$X` through the latch, moves nothing, and keeps the position the
  controller believes. A knob turned while the router is in alarm says to press it. The
  deck asks a machine nothing while its control is let go, and a stop lets it go, so after
  a stop mid-move UNLOCK lights from the next poll by anyone: the router's Machine, a
  program, or the deck once armed again. Out of alarm the key stops the move under way
  and no more: **STOP JOG** on the router (GRBL's jog cancel, which keeps the position)
  and **QUICKSTOP** on the printer (`M410`). Neither needs control armed, and each is
  sent at once, ahead of any turn still waiting, which is then not sent.
- **The bottom row's keys** are the stops, two classes of them: 4 **STOP printer_1** and
  5 **STOP cnc_router**, dark red, each stopping that machine alone, and 7 **STOP ALL**,
  bright red and last, nearest a hand resting on the knobs, stopping every machine this
  server knows of, each by its own dialect's stop and all at once: the garage's two, and
  any other board that answered as a printer or a router.
- **The knobs**: one to three jog X, Y and Z by their steps of the chosen size; the fourth
  turns the router's spindle speed in steps of 1000 rpm, or extrudes 1 mm a step on the
  printer. The spindle is turned only from a reading a few seconds old at most, and never
  down to nothing: off is the Machine's, or a stop. A turn made while the machine was
  busy with something else, a home or a probe, is dropped once it is two seconds old and
  the strip says so: it is never sent when the machine comes free.

**The machines are found by where they are pinned.** The printer and the router are the
boards pinned to the garage's `printer_1` and `cnc_router`. With nothing pinned there and
plugged in, each is the one board of its kind this server knows, wherever it is pinned.
Two of a kind and no pin is no machine for the knobs, and both of them for that kind's
stop key.

The strip's first screen, the knobs', says which machine, whether its control is armed and for how long, the chosen
machine's newest poll, the deck's own or anyone's (X, Y, Z and the fourth quantity), the
step, and what the last turn did or why it did nothing.

## The strip's screens

The strip has three screens, in this order, and a swipe along it walks them
(`apothecary/firmware/deck_screens.py` holds what each says and the swipe; `deck_control.py`
holds which is showing):

- **Knobs**, the one above, which the strip starts on. While a job holds the chosen
  machine's port -- a print or a cut the host streams, or a bed reading a poll saw a moment
  ago -- it says so in the words the server refuses a jog with (`PortHeld`) and that the
  jogs are refused; on a router it adds that knob 4 still turns the spindle, since a cut's
  dialect lets that through.
- **Progress**: the part the job makes, else the file it ran, how far it is as a number
  and as a bar, its stage and how long it has run. Where no job of the host's is running
  but the printer's card is, it shows the card's progress and the time the card reports.
  No remaining time is drawn, because neither the job's record nor a poll carries one.
- **Status**: the machine's state; a printer's hotends and bed, or a router's spindle and
  feed; and the first thing it asks of a person, from its `todo`, else its alarm. It reads
  the newest status anyone's poll made, and says how old it is when it is over ten seconds.

A **swipe** is the strip's drag event (`{"kind": "drag", "x", "y", "x_out", "y_out"}`,
where `x` and `y` are where the finger went down and `x_out` and `y_out` where it came up)
of 200 pixels or more along the strip's 800: a finger moving left shows the next screen,
right the one before. It stops at either end and does not wrap. A tap or a long press
moves nothing. Switching screens draws the strip and nothing more: no line goes to a
machine, no poll is asked, and no key changes (the stops and the machine keys are the same
on every screen).

A job begun on the chosen machine brings Progress forward once, for that job: a swipe
away from it is never undone, and the next job is another. A job begun on the other
machine brings nothing forward. A job that has ended stays on Progress, saying how it
ended (done, cancelled or failed, and after how long), until a touch of that screen clears
it; a touch on another screen leaves it. The screens follow the job's own thread, not a
poller of their own, and the layout's two-second tick draws the elapsed time.

The Deck window says which screen the strip shows. Dragged along its strip by the mouse,
a quarter of its length or more, a simulated deck is swiped; a real deck's strip is a
person's to swipe.

**Nothing the deck sends bypasses what bounds a person's jog.** A jog goes through
`devices.printer_jog`, the function behind `POST /firmware/printers/jog` and the page's
pad, so it is one act on the port whoever makes it; every other line goes through
`devices.printer_control`, the function behind `POST /firmware/printers/command`:

- the port's control latch must be armed, and it is armed the page's way (⚙ Control in the
  Machine window) or by **two sequential long presses** of the machine's key: a press held
  0.8 s chooses the machine and says on the strip that a second will arm its control; the
  second, of the same key, begun within 5 s of the first being let go and held as long as it
  likes, arms it for the latch's own
  five minutes through the same `ControlLatch`. One long press alone, a second after the
  window, a short press, another key or a knob turned between them, or a long press of the
  other machine's key arms nothing. Armed this way, the machine's badge in the world and
  its row in Site say so with the time left, its Machine open or not. A turn while
  disarmed sends nothing and the strip says *disarmed*;
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
  E-STOP does, waits on no poll, and disarms the machine it stops: the next turn moves
  nothing until its control is armed again. The everything key sends each machine's own, one
  after another, and goes on to the next when one cannot be reached; the strip names
  which it reached.

**The machine's own red button is faster than any of this**, and stays the stop to reach
for: the deck's stop keys are a USB report, a host process, a link and a queue away from the
controller. Keep a hand on the machine's own switch, as the bench checklist says.

The layout starts on a deck when `APOTHECARY_DECK_CONTROL` is set (`serve --simulated` sets it), or
when `POST /firmware/decks/{id}/control` with `{"on": true}` asks; `GET` on the same route
says whether it runs, the machine chosen, the step, the control's seconds left, what it
said last and the lines it sent. A real deck is opened by it, which takes the device from
any other program that has it, so it is started on purpose.

The knobs are one state, the server's: whether the layout runs, the machine its knobs
move and their step. The Deck window shows it under the deck's name and changes it --
**▶ Knobs** starts or stops the layout, a machine's name chooses what the knobs move and
a step theirs, as the deck's own keys do -- and shows what the deck's keys or anything
else chose. Each Machine's Control pad, while its control is armed, says where the knobs
are and their step, and its **🎛 Knobs here** points them at its machine. The ring's
Panels › Machine › Knobs holds the same verbs, **Here** being the open Machine's machine,
and the Deck window. None of them arms anything: the knobs move a machine only while its
control is armed, in its Machine or by two long presses of its key. `GET
/firmware/decks/control` lists every running layout's state, and `PUT
/firmware/decks/{id}/control` with a `machine`, a `port` or a `step_mm` chooses.
[Walkthrough 27](../walkthrough/27-the-deck-jogging-the-machines.md) goes round it on the
simulated bench, written by `tests/e2e/test_deck_jog.py`.

## Simulated

With `APOTHECARY_SERIAL_ENGINE=simulated` no HID device is listed or opened. The decks
found are the ones `APOTHECARY_SIMULATED_DECK` names (comma-separated), each a pretend
Stream Deck + that keeps the images it is sent and hears the events
`POST /firmware/decks/{id}/events` gives it, validated as a real deck's reports could
be: a knob turns by a whole number of steps, a touch is a tap, a hold or a drag.
`apothecary serve --simulated` has one, `SIMDECK`.

`tests/test_firmware_deck.py` holds the seam against the simulated deck, against a
stand-in for the library's device that counts what is opened, and against the
library's own dummy transport, which enumerates every model it knows with nothing
behind it. It skips that last test, saying so, where the optional package is not
installed. No test opens a HID device. What only a deck shows is a row of
[the bench checklist](bench-checklist.md).
