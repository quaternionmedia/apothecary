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
  Pillow. The controller below draws more than a label: a key as a tile (a title on a
  band of colour, a number, a line under it and a spark line or a bar at its foot) and
  the strip as a screen (the screens' names along its top, and a body of four panels,
  a graph, a progress bar, a bed's mesh or two machines side by side), each from an
  `art`, a plain description kept with the words it says (`firmware/deck_draw.py`). A
  deck cannot be asked what it shows, so what was sent is kept -- its words, its art
  and a short digest of the picture, `v` -- and `GET /firmware/decks/{id}/keys/{n}/image`
  and `.../strip/image` serve it.
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

The **Deck** window (⊞ Windows › Deck, the ring's Panels › Tools › Deck › Deck, or **Open Deck** on the
`stream_deck` piece of the garage, its ring's Deck) shows the first deck found: its eight keys and its
strip as the images last sent to them, `–` where nothing has been drawn from here, its
four knobs, and the events it has heard, newest first, in a list that scrolls. It follows
the deck every second and a half while it is in front, which opens the deck, and asks for
its events four times a second between, so what is heard is shown where it happened as it
happens: a key or a knob held is marked for as long as it is down, and a press, the way a
knob turned and the place the strip was touched are each lit for a moment. A real deck's
keys and strip are drawn as bright as a simulated one's. A simulated deck is pressed from
it -- a key, a knob turned a step either way or pressed, the strip tapped -- each the
event a real deck reports, posted to the deck's routes; a real deck is pressed by hand
and the window's controls are off. Under the strip's picture its two lines are written
as the server drew them, as text to read and select, and the line under its screen where
that says more (what the layout said last, a refusal): the picture's small lines are too
small to read at the window's width, and the picture stays what the deck was sent.
[Walkthrough 26](../walkthrough/26-the-stream-deck.md) goes round it, written by
`tests/e2e/test_deck.py`.

### What the Deck window would be refused

The knobs' state (`GET /firmware/decks/{id}/control`, and each running layout's in `GET
/firmware/decks/control`) carries `can`: for each of the window's controls, whether its
route would take it now, as `{"ok", "why", "kind"}`, in the shape a port's answer has
([firmware.md](firmware.md#what-a-command-would-be-refused-for)). The controls are
`knobs.start` and `knobs.stop` (▶ Knobs), `knobs.machine`, `knobs.step` and
`knobs.screen` (a machine, a step, a screen chosen), `inject` (a simulated deck's key,
knob or strip) and, asked with `?port=`, `here` (a Control pad's Knobs here for that
port's machine). `kind` says what stands in the way: `name` (no deck's name), `found`
(no such deck), `offline` (the deck library or the HID library missing, the deck's last
opening failed, or it is lost on USB and not back), `idle` (the knobs are not started),
`kind` (a real deck, which reports for itself) and `machine` (no machine of the deck's
has its board on that port). Each is a predicate in `firmware/can.py` that the deck's
routes raise from, so the answer and the refusal are one check;
`tests/test_deck_can.py` puts the deck in each condition and requires `ok: false`
exactly where the route answers 4xx or 5xx. Asking opens no deck: a deck not yet opened
is judged by its listing, and one whose opening failed by that failure until it opens
(the window's own look at the deck tries it again every beat); an open deck lost on USB is
opened again if it is back, as every route that names it does first.

The window greys each control the answer refuses, with the reason in its title
(`static/can.js`); with no deck found, or no answer yet, every control is refused for
that. A Control pad's 🎛 Knobs here is greyed from the same answer for its port.

## The controller

The knobs jog the garage's two machines. `apothecary/firmware/deck_control.py` runs one
layout on a deck:

- **The top row's keys**: 0 **PRINTER** and 1 **ROUTER** choose the machine (held twice,
  they arm its control, below). Each is drawn as a tile of what its machine is doing, on
  every screen: the printer's hotend as read, its bed under it and a spark line of both
  over the last ten minutes; the router's state and its spindle; a job's bar in place of
  the spark line; the band along its top in its state's colour (red in alarm, amber
  when it asks something of a person or a job is held, green while it works or its
  control is armed), the time its control has left under the number while it is armed,
  and the chosen machine framed in white. Key 2 is the screen's own (below). 3 **DISARM**
  lets go of every machine's control at one press, red while any is armed and grey when
  none is. It stops nothing -- a move under way finishes -- and the stop keys are the
  stops.
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
- **The knobs**, on the Jog screen alone (below): one to three jog X, Y and Z by their
  steps of the chosen size; the fourth turns the router's spindle speed in steps of 1000
  rpm, or extrudes 1 mm a step on the printer. The spindle is turned only from a reading a few seconds old at most, and never
  down to nothing: off is the Machine's, or a stop. A turn made while the machine was
  busy with something else, a home or a probe, is dropped once it is two seconds old and
  the strip says so: it is never sent when the machine comes free.

**The machines are found by where they are pinned.** The printer and the router are the
boards pinned to the garage's `printer_1` and `cnc_router`. With nothing pinned there and
plugged in, each is the one board of its kind this server knows, wherever it is pinned.
Two of a kind and no pin is no machine for the knobs, and both of them for that kind's
stop key.

The Jog screen says which machine, whether its control is armed and for how long, the
chosen machine's newest poll, the deck's own or anyone's (X, Y, Z and the fourth
quantity, each over its knob), the step, and what the last turn did or why it did
nothing.

## The screens

The deck has six screens, named along the top of its strip, each name a sixth of the
strip (`apothecary/firmware/deck_screens.py` holds what each says and how a touch moves
between them; `deck_control.py` holds which is showing). The first is both machines'; the
other five are the chosen machine's, each named as that machine calls it:

| Screen | printer_1 | cnc_router | Key 2 | What it shows |
|---|---|---|---|---|
| `bench` | Bench | Bench | a readout | Both machines, half the strip each: its state, its numbers and its job's bar. |
| `knobs` | Jog | Jog | **STEP** | X, Y, Z and the fourth quantity over their knobs, the step, what the last turn did. The one the deck starts on. |
| `home` | Home | Home | **HOME** | Each axis where it stands and its switch: a printer's endstop as its last poll read it, a router's homing as its controller says it will seek, and whether the server has seen its switch. |
| `progress` | Print | Cut | the job's number | The job, how far it is, its stage and how long it has run. |
| `status` | Temps | Status | the hotend's, or the spindle's | A printer's hotend and bed as a graph of the last ten minutes; a router's state, pins, spindle and work zero. |
| `bed` | Bed | Table | **PROBE** | The newest reading of the bed or the table: its mesh as coloured cells, its range, when it was taken and how warm the bed was; a reading under way, its stage. |

**Moving between them.** A **tap** (or a long press) on a name shows that screen. A
**knob pressed** shows the next, and from the last, the first. A **swipe** is the strip's
drag event (`{"kind": "drag", "x", "y", "x_out", "y_out"}`, where `x` and `y` are where
the finger went down and `x_out` and `y_out` where it came up) of 200 pixels or more along
the strip's 800: a finger moving left shows the next screen, right the one before. It
stops at either end and does not come round. A shorter drag moves nothing. None of it
sends a line to a machine or asks one for a poll, and every key but key 2 is the same
on every screen: the machines, DISARM and the stops never move. Choosing the other
machine keeps the screen: from the printer's Temps, **ROUTER** shows the router's Status.

**The knobs move a machine on Jog alone**, where the strip shows what each one moves. On
any other screen a turn sends nothing, and the strip says the knobs move nothing there; the
one exception is a router's fourth knob on Cut, which turns its spindle there too, since a
cut's speed is what a person turns while watching it. Pressing a knob moves on to the next
screen, and moves no machine.

**Key 2 is the screen's.** On Jog it is **STEP**, cycling 0.1, 1 and 10 mm. On Home it is
**HOME**, and on Bed **PROBE**: each is held a second (`LONG_PRESS_S`) and let go to act, on
the screen it was pressed on; a shorter press says to hold it and sends nothing. HOME
sends the dialect's home of every axis (`G28`, `$H`) through `devices.printer_control`, the
function behind the Machine's ⌂, so the latch, a router's home not yet proved and a job
holding the port refuse it as they refuse the page; it is sent on a thread of its own, and
the strip says *homed*, or why not, when the machine has answered. PROBE begins a reading
through `devices.start_leveling` with the route's defaults (`POST /firmware/printers/level`:
a printer's bed probed as it stands, a router's table mapped three by three), refused while
the latch is down, a job holds the port or a task writes to it. On the other screens key 2
shows the screen's number -- the job's per cent, the hotend's temperature, the spindle's
speed -- and a press of it does nothing.

**What is drawn is what anyone's polls read.** Every poll that lands in
`devices.notify_status`, whoever made it -- a Machine's auto-poll, the Site, a loop, the
deck while a machine's control is armed -- leaves its numbers in
`apothecary/firmware/readings.py`: a printer's hotend and bed, each as read and as asked
for, and a router's spindle and feed, half an hour of them per port, at most two a second.
The Temps graph and the printer's spark line are drawn from them, and the Bench and every
key from the newest poll. The deck asks a machine for nothing to draw: a machine no one
polls is drawn as it was last read, and Temps says how long ago that was.

A job begun on the chosen machine brings Print (or Cut) forward once, for that job: a tap
or a swipe away from it is never undone, and the next job is another. A job begun on the
other machine brings nothing forward. A job that has ended stays on Print, saying how it
ended (done, cancelled or failed, and after how long), until a touch of that screen clears
it; a touch on another screen leaves it. The screens follow the job's own thread, not a
poller of their own, and the layout's two-second tick draws the elapsed time.

Under each screen's body is its footer: what the screen says of itself, or for a few
seconds what the layout said last -- a refusal, in red, until something else is said.

The Deck window says which screen the deck shows, and changes it, a real deck's as a
simulated one's: a button for each screen beside it, named as the chosen machine names
it, and the ring's Panels › Tools › Deck › Screen (Jog, Progress, Status, Back and Next,
then Bench, Home and Bed), are `PUT /firmware/decks/{id}/control` with a `screen`, its
name or `next` or `previous`. Chosen this way it is as a swipe is: it stops at either end,
draws the strip and nothing more, and sends nothing to a machine; unlike a touch, it clears
no ended job from Print. Clicked on its strip, a simulated deck is tapped where the mouse
is, which shows the screen named there; dragged a quarter of its length or more, it is
swiped. A real deck's strip is a person's to touch.

While a job holds the chosen machine's port, the window's line under the knobs says
*held* in the words the Jog screen says it (`screens.held_words`: the server's own
refusal of a jog, and what the knobs still do), whichever screen the deck shows, not
the last thing the knobs did.

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
Panels › Tools › Deck holds the same verbs, **Here** being the open Machine's machine,
and the Deck window, each greyed as the deck answers for it (with no deck found, every
one but the Deck window). None of them arms anything: the knobs move a machine only while its
control is armed, in its Machine or by two long presses of its key. `GET
/firmware/decks/control` lists every running layout's state, and `PUT
/firmware/decks/{id}/control` with a `machine`, a `port`, a `step_mm` or a `screen`
chooses.
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
