"""The Stream Deck + as a controller for the garage's two machines.

One layout, on every deck it is started for (``Deck`` in ``firmware/deck.py``):

- the top row's keys choose the machine (0 printer_1, 1 cnc_router), cycle the jog
  step through 0.1, 1 and 10 mm (2), and disarm every machine's control (3), lit while
  any is armed;
- key 6 is UNLOCK while the chosen router is in alarm, and dark otherwise: it sends the
  router's ``$X`` through the latch, and a turn refused in alarm says to press it;
- the bottom row holds the stops: 4 stops printer_1 and 5 cnc_router, each by its own
  dialect's stop, and 7, bright red and last, nearest a hand on the knobs, stops every
  machine, each by its own; none needs control armed, and each disarms the machine it
  stops;
- the strip says which machine, whether its control is armed and for how long, the
  chosen machine's newest poll (X, Y, Z and the fourth quantity), the step, and what the
  last turn did or why it did nothing;
- knobs one to three jog X, Y and Z by so many steps; the fourth turns the spindle's
  speed in steps of 1000 rpm (only while it turns) or extrudes 1 mm a step;
- a machine's key held (``LONG_PRESS_S``) twice in a row, the second begun within
  ``ARM_WINDOW_S`` of the first let go, arms that machine's control for the latch's own five
  minutes, as the Machine's Control does; one long press alone, a second after the
  window, or anything pressed between them arms nothing, and the strip says what the
  first did and what the second will.

**Nothing here moves a machine by a way of its own.** Every line goes through
``devices.printer_control``, the function behind ``POST /firmware/printers/command``:
the port's ``ControlLatch`` must be armed (by the Machine window, or by the two long
presses above, which arm the same latch), the line is normalised in the port's dialect
and refused out of its bounds (``grbl.JOG_MAX_MM``, ``gcode.JOG_MAX_MM``,
``grbl.SPINDLE_MAX_RPM``, ``EXTRUDE_MAX_MM``), and a job holding the port refuses it. A stop
key sends ``devices.emergency_stop_for(port)``, the one line that always goes; the
everything key sends each machine's own, one after another, whatever one of them
answers. The machine's own red button is faster, and stays the stop to reach for.

**Nothing a hand does on the deck waits behind anything else.** The deck's reader only
hands an event over (``hear``); a thread of the layout's own acts on them in order
(``handle``), so a machine's answer or a redrawn strip never holds up the next report or
the time it is stamped with. Turns of one knob that arrive while an earlier one is being
sent go as one jog of their sum. A stop key is the exception to the order: it is sent
from ``hear`` itself, ahead of everything waiting, and what was waiting is dropped; the
disarm key is acted on the same way. No
key or knob starts a scan for ports (two seconds): the newest scan is read however old,
and the layout's tick looks for a board that is not found.

It starts for a deck only when ``APOTHECARY_DECK_CONTROL`` is set (the demo sets it) or
a person asks (``POST /firmware/decks/{id}/control``): opening a real deck takes the
device from any other program that has it.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Deque, Dict, List, Optional, Tuple

from . import deck as decks
from . import devices, gcode, grbl
from .toolchains import PortHeld, ToolchainError

CONTROL_ENV = "APOTHECARY_DECK_CONTROL"
SITE = "garage"
STEPS_MM = (0.1, 1.0, 10.0)
AXES = ("X", "Y", "Z")
KEY_MACHINE = (0, 1)
KEY_STEP = 2
# Two classes of stop: one key per machine, each sending that machine's
# own stop, and one that stops every machine at once. The everything key is the bottom
# row's last, nearest a hand resting on the knobs, bright red where the per-machine stops
# are dark; none needs control armed, as the page's E-STOP does not.
KEY_STOP_MACHINE = (4, 5)  # printer_1's and cnc_router's, in MACHINES' order
KEY_STOP_ALL = 7
STOP_KEYS = (*KEY_STOP_MACHINE, KEY_STOP_ALL)
KEY_DISARM = 3  # every machine's control let go: what two long presses armed, one press undoes
KEY_UNLOCK = 6  # the chosen router out of its alarm ($X): there only while it is in one
AT_ONCE_KEYS = (*STOP_KEYS, KEY_DISARM)  # acted on ahead of whatever is waiting
STOP_ALL_COLOUR, STOP_ONE_COLOUR = "red", "#7a2a22"
KNOB_FOURTH = 3
FEED = {"printer": 3000, "router": 1000}  # the page's jog feeds (machine_words.js)
EXTRUDE_MM_PER_STEP = 1.0
EXTRUDE_FEED = 200  # under gcode.EXTRUDE_FEED_MAX
SPINDLE_RPM_PER_STEP = 1000
TICK_S = 2.0
LOOK_S = 10.0  # a board not found is looked for with a scan this often, by the tick alone
SETTLE_S = 10.0  # the longest a simulated deck's event waits to have been acted on
MEND_S = 0.5  # how often a deck is looked at, and a lost one looked for
STOP_S = 15.0  # the longest stop waits for a tick's scan or an event's poll to end
LONG_PRESS_S = 0.8  # a machine's key held this long is a long press
ARM_WINDOW_S = 5.0  # the second long press of two must begin within this of the first let go


@dataclass(frozen=True)
class Machine:
    name: str  # the garage's node, as the keys say it
    kind: str  # "printer" or "router": the dialect's machine kind
    node: str  # the node its board is pinned to


MACHINES = (
    Machine("printer_1", "printer", "printer_1.frame_system.mainboard"),
    Machine("cnc_router", "router", "cnc_router.frame_system.controller"),
)


def enabled() -> bool:
    return os.environ.get(CONTROL_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def pinned_port(machine: Machine) -> Optional[str]:
    """The port the board pinned to ``machine``'s node is on now, or None. Read from the
    newest scan however old, less what the serial engine no longer lists: a key or a knob
    never waits two seconds on a scan (``look`` is what starts one)."""
    from .bindings import device_for_identity

    state = devices.get_state()
    pin = next((b for b in state.bindings(SITE) if b.path == machine.node), None)
    if pin is None:
        return None
    try:
        found = devices.detected_devices(state=state, any_age=True)
    except ToolchainError:
        return None
    device = device_for_identity(pin.identity, found, pin.kind)
    return device.port if device is not None else None


def look() -> None:
    """A scan for ports, unless one was made within its own short life: how a board
    plugged in since the last is found when no page is asking."""
    try:
        devices.scan_ports()
    except ToolchainError:
        pass


def _mm(value: float) -> str:
    return f"{round(value, 2):g}"


class DeckController:
    """The layout on one deck: its events in, its keys and strip out, a machine's
    control lines between. The seams (``resolve``, ``send``, ``poll``, ``armed``, ``disarm``) are
    what the machines' own functions are, so a test can stand its own in their place."""

    def __init__(
        self,
        deck: decks.Deck,
        resolve: Callable[[Machine], Optional[str]] = pinned_port,
        send: Optional[Callable[[str, str], object]] = None,
        poll: Optional[Callable[[str], object]] = None,
        armed: Optional[Callable[[str], float]] = None,
        disarm: Optional[Callable[[str], None]] = None,
    ):
        self.deck = deck
        self.resolve = resolve
        self.send = send or (lambda port, line: devices.printer_control(port, line))
        self.poll = poll or (lambda port: devices.printer_status(port))
        # Seconds of control left on a port, 0 when it is not armed.
        self.armed = armed or (lambda port: gcode.get_printer_links().control.seconds_left(port))
        self.disarm = disarm or (lambda port: gcode.get_printer_links().control.disarm(port))
        self.machine = MACHINES[0]
        self.step = 1  # an index into STEPS_MM
        self.said: Tuple[str, str] = ("ready", "grey")
        self.last: Optional[object] = None  # the chosen machine's last poll
        self.sent: List[str] = []  # every line this controller sent, for what a person reads back
        self._down: Dict[int, float] = {}  # when each machine key went down
        self._first_long: Optional[Tuple[int, float]] = None  # the first of two long presses
        self._drawn: Dict[object, tuple] = {}
        self._lock = threading.RLock()
        self._stop_listening: Optional[Callable[[], None]] = None
        self._ticker: Optional[threading.Thread] = None
        self._worker: Optional[threading.Thread] = None
        self._waiting: Deque[decks.DeckEvent] = deque()  # heard, not yet acted on
        self._acting = False
        self._turn = threading.Condition()
        self._redraw = False
        self._stops = 0  # stop keys heard
        self._epoch = 0  # how many had been when the event being acted on was taken up
        self._looked = 0.0
        self._alive = threading.Event()
        self._stopped = threading.Event()

    # -- life -----------------------------------------------------------------------

    def start(self) -> "DeckController":
        self._alive.set()
        self._stopped.clear()
        self._worker = threading.Thread(target=self._work, name="deck-events", daemon=True)
        self._worker.start()
        self._stop_listening = self.deck.listen(self.hear, self.settle)
        self.draw()
        self._ticker = threading.Thread(target=self._tick, name="deck-control", daemon=True)
        self._ticker.start()
        return self

    def stop(self) -> None:
        self._alive.clear()
        self._stopped.set()
        if self._stop_listening:
            self._stop_listening()
            self._stop_listening = None
        with self._turn:
            self._waiting.clear()
            self._turn.notify_all()
        # Stopped is stopped: a tick part way through a scan or a poll, or an event being
        # acted on, ends before this returns, and touches nothing after.
        for thread in (self._ticker, self._worker):
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=STOP_S)

    def _look(self) -> None:
        """A machine whose board is not found is looked for, here and nowhere else."""
        if self.resolve is not pinned_port or time.monotonic() - self._looked < LOOK_S:
            return
        if any(pinned_port(machine) is None for machine in MACHINES):
            self._looked = time.monotonic()
            look()

    def _refresh(self) -> None:
        """While the chosen machine's control is armed it is in use: its readouts follow it
        (a poll is a read, as the Machine's own auto-poll is); disarmed, nothing is asked."""
        port = self._port_quiet()
        if port and self.armed(port) > 0:
            with self._lock:
                self._after(port)

    def _tick(self) -> None:
        while not self._stopped.wait(TICK_S):
            try:
                self._look()
                self._refresh()
                self.draw()
            except Exception:  # noqa: BLE001 -- a deck that went away: the next tick tries again
                pass

    @property
    def step_mm(self) -> float:
        return STEPS_MM[self.step]

    # -- events ---------------------------------------------------------------------

    def hear(self, event: decks.DeckEvent) -> None:
        """An event as the deck's reader reports it, on the reader's own thread: handed
        over, and the reader is free for the next. A stop key is sent from here, before
        anything waiting, and what was waiting is not sent after it; the disarm key the
        same."""
        if event.kind == decks.KEY and event.value and event.index in AT_ONCE_KEYS:
            with self._turn:
                self._waiting.clear()
                self._stops += 1
            self._first_long = None
            try:
                self._key(event.index)
            except Exception as exc:  # noqa: BLE001 -- said on the strip, as in handle
                self.said = (f"{type(exc).__name__}: {exc}", "red")
            event = None  # the strip is drawn in its turn, not on the reader's thread
        with self._turn:
            if event is None:
                self._redraw = True
            else:
                last = self._waiting[-1] if self._waiting else None
                if (
                    event.kind == decks.KNOB_TURN
                    and last is not None
                    and last.kind == decks.KNOB_TURN
                    and last.index == event.index
                ):
                    # Turns of one knob with nothing between them are one turn of their sum.
                    self._waiting[-1] = decks.DeckEvent(
                        event.seq,
                        event.kind,
                        event.index,
                        int(last.value) + int(event.value),
                        at=event.at,
                    )
                else:
                    self._waiting.append(event)
            self._turn.notify_all()

    def _work(self) -> None:
        while True:
            with self._turn:
                while not self._waiting and not self._redraw and not self._stopped.is_set():
                    self._turn.wait(MEND_S)
                    if not self._waiting and not self._redraw and not self.deck.alive():
                        break  # the deck is lost: mend it, below
                if self._stopped.is_set():
                    self._turn.notify_all()
                    return
                event = self._waiting.popleft() if self._waiting else None
                self._redraw = False
                self._acting = True
            try:
                if not self.deck.alive():
                    self._mend()
                if event is None:
                    self.draw()
                elif not (event.kind == decks.KNOB_TURN and int(event.value) == 0):
                    self.handle(event)
            except Exception:  # noqa: BLE001 -- a deck that went away: the next event tries again
                pass
            finally:
                with self._turn:
                    self._acting = False
                    self._turn.notify_all()

    def _mend(self) -> None:
        """A deck lost from USB opened again as soon as it is back, drawn as it was. A key
        held or a first long press when it went is forgotten: nothing is armed by half a
        gesture."""
        self._down.clear()
        self._first_long = None
        try:
            if self.deck.mend():
                self.said = ("the deck was lost on USB, and is back", "amber")
        except decks.DeckUnavailable:
            time.sleep(MEND_S)  # not back yet: looked for again on the next turn

    def settle(self, timeout: float = SETTLE_S) -> bool:
        """Returns when everything heard has been acted on; False if ``timeout`` came first."""
        until = time.monotonic() + timeout
        with self._turn:
            while self._waiting or self._redraw or self._acting:
                left = until - time.monotonic()
                if left <= 0 or self._stopped.is_set() or not self._alive.is_set():
                    return not (self._waiting or self._acting)
                self._turn.wait(min(left, 0.5))
        return True

    def handle(self, event: decks.DeckEvent) -> None:
        """What the deck reported, as the layout reads it. Never raises: what could not be
        done is said on the strip."""
        with self._lock:
            self._epoch = self._stops
            try:
                if event.kind == decks.KEY and event.index in KEY_MACHINE:
                    self._machine_key(event)
                elif event.kind == decks.KEY and event.value:
                    self._first_long = None
                    self._key(event.index)
                elif event.kind == decks.KNOB_TURN:
                    self._first_long = None
                    if event.index < len(AXES):
                        self._jog(AXES[event.index], int(event.value))
                    elif event.index == KNOB_FOURTH:
                        self._fourth(int(event.value))
            except Exception as exc:  # noqa: BLE001 -- the strip says it, the loop goes on
                self.said = (f"{type(exc).__name__}: {exc}", "red")
            self.draw()

    def _choose(self, index: int) -> None:
        self.machine = MACHINES[KEY_MACHINE.index(index)]
        self.last = None

    # -- chosen from the page -----------------------------------------------------------

    def choose(self, machine: Optional[str] = None, port: Optional[str] = None) -> None:
        """The machine the knobs move, named or found by the port its board is on, as its
        key on the deck chooses it: the Deck window's machines, a Control pad's Knobs here
        and the ring's Knobs choose this way. Nothing is armed."""
        with self._lock:
            if machine is not None:
                found = next((m for m in MACHINES if m.name == machine), None)
                if found is None:
                    names = ", ".join(m.name for m in MACHINES)
                    raise ValueError(
                        f"no machine {machine!r} on the deck: its machines are {names}"
                    )
            else:
                found = next((m for m in MACHINES if port and self.resolve(m) == port), None)
                if found is None:
                    raise ValueError(f"{port}: no machine of the deck's has its board there")
            self._first_long = None
            self._choose(KEY_MACHINE[MACHINES.index(found)])
            self.said = (f"{found.name} chosen", "grey")
            self.draw()

    def set_step(self, mm: float) -> None:
        """The knobs' step, one of the deck's own, as its STEP key cycles it."""
        with self._lock:
            if mm not in STEPS_MM:
                steps = ", ".join(_mm(s) for s in STEPS_MM)
                raise ValueError(f"a step of {_mm(mm)} mm: the deck's steps are {steps} mm")
            self.step = STEPS_MM.index(mm)
            self.said = (f"step {_mm(self.step_mm)} mm", "grey")
            self.draw()

    def _machine_key(self, event: decks.DeckEvent) -> None:
        """A machine's key: pressed down, or let go. A short press chooses the machine; a
        long one chooses it too, and two in a row arm its control."""
        index = event.index
        if event.value:
            self._down[index] = event.at
            return
        down = self._down.pop(index, event.at)
        held = event.at - down
        self._choose(index)
        if held < LONG_PRESS_S:
            self._first_long = None
            self.said = (f"{self.machine.name} chosen", "grey")
            return
        first = self._first_long
        # The window runs from the first press let go to the second begun: however long
        # the second is held, it was begun in time.
        if first is not None and first[0] == index and down - first[1] <= ARM_WINDOW_S:
            self._first_long = None
            self._arm()
            return
        self._first_long = (index, event.at)
        self.said = (
            f"long press {self.machine.name} again within {ARM_WINDOW_S:g} s to arm its control",
            "amber",
        )

    def _arm(self) -> None:
        """The chosen machine's control armed, as the Machine's Control arms it."""
        port = self._port()
        if port is None or not self._ready(port):
            return
        gcode.get_printer_links().control.arm(port)
        self.said = (f"{self.machine.name} control armed", "green")

    def _armed_machines(self) -> List[Tuple[Machine, str]]:
        """Each machine whose control is armed now, with the port its board is on."""
        found = []
        for machine in MACHINES:
            try:
                port = self.resolve(machine)
            except Exception:  # noqa: BLE001 -- nothing pinned has nothing armed
                port = None
            if port is not None and self.armed(port) > 0:
                found.append((machine, port))
        return found

    def _disarm(self) -> None:
        """Every machine's control disarmed, as the Machine's Disarm does for its own. It
        stops nothing: a move under way finishes, and the stop keys are the stops."""
        were = self._armed_machines()
        for _, port in were:
            self.disarm(port)
        names = ", ".join(machine.name for machine, _ in were)
        self.said = (f"{names} disarmed" if were else "nothing was armed", "grey")

    def _newest(self) -> Optional[object]:
        """The chosen machine's newest poll, this layout's or anyone's. The layout asks
        nothing while the machine's control is let go, and a stop lets it go, so what it
        last asked can be older than what the machine's Machine or a program has asked
        since: a reset mid-move leaves a router in alarm."""
        mine = self.last
        theirs = devices.last_statuses().get(self._port_quiet() or "")
        if mine is None or theirs is None:
            return mine or theirs
        at = (getattr(theirs, "polled_at", None), getattr(mine, "polled_at", None))
        return theirs if None not in at and at[0] > at[1] else mine

    def _alarmed(self) -> bool:
        """Whether the chosen machine's newest poll had it in alarm."""
        status = self._newest()
        return getattr(status, "state", None) == "alarm"

    def _unlock(self) -> None:
        """The chosen router unlocked from its alarm (``$X``), as the Machine's Unlock does:
        it moves nothing, keeps the position the controller believes, and needs control
        armed as any line but a stop does."""
        if self.machine.kind != "router":
            self.said = (f"{self.machine.name} has no alarm to unlock", "grey")
            return
        port = self._port()
        if port is None or not self._ready(port):
            return
        if self._lines(port, ["$X"]):
            self.said = (f"{self.machine.name} unlocked", "grey")
            self._after(port)

    def _key(self, index: int) -> None:
        if index == KEY_STEP:
            self.step = (self.step + 1) % len(STEPS_MM)
            self.said = (f"step {_mm(self.step_mm)} mm", "grey")
        elif index in KEY_STOP_MACHINE:
            self._stop([MACHINES[KEY_STOP_MACHINE.index(index)]])
        elif index == KEY_STOP_ALL:
            self._stop(list(MACHINES))
        elif index == KEY_DISARM:
            self._disarm()
        elif index == KEY_UNLOCK:
            self._unlock()

    # -- what is sent -----------------------------------------------------------------

    def _port(self) -> Optional[str]:
        port = self.resolve(self.machine)
        if port is None:
            self.said = (f"{self.machine.name}: no board pinned and plugged in", "red")
        return port

    def _ready(self, port: str) -> bool:
        """The chosen machine is a machine of its kind, polled. A deck's key for a printer
        never moves a router that took the printer's port."""
        try:
            self.last = self.poll(port)
        except ToolchainError as exc:
            self.said = (f"{self.machine.name}: {exc}", "red")
            return False
        kind = devices.machine_kind(devices.known_device(port))
        if kind != self.machine.kind:
            self.said = (f"{port} is not a {self.machine.kind}", "red")
            return False
        return True

    def _lines(self, port: str, lines: List[str], *, last: Optional[str] = None) -> bool:
        """``lines`` in order through the machine's own control function; ``last`` is sent
        whatever happens after the first went (a jog's return to absolute positioning).
        False, the reason on the strip, when one was refused."""
        went = 0
        try:
            for line in lines:
                if self._stops != self._epoch:
                    return False  # a stop key since: what was turned before it is not sent
                self.send(port, line)
                self.sent.append(line)
                went += 1
            return True
        except gcode.ControlNotArmed:
            self.said = (
                "disarmed: arm it in the Machine, or long press the machine's key twice",
                "red",
            )
        except PortHeld as exc:
            self.said = (str(exc), "red")
        except (ValueError, ToolchainError) as exc:
            self.said = (f"refused: {exc}", "red")
            if self._alarmed() or "error:8" in str(exc) or "error:9" in str(exc):
                self.said = (f"{self.machine.name} is in alarm: UNLOCK it, then turn", "red")
        finally:
            if went and last is not None and self._stops == self._epoch:
                try:
                    self.send(port, last)
                    self.sent.append(last)
                except (ValueError, ToolchainError):
                    pass
        return False

    def _jog(self, axis: str, steps: int) -> None:
        port = self._port()
        if port is None or not self._ready(port):
            return
        distance = _mm(steps * self.step_mm)
        feed = FEED[self.machine.kind]
        if self.machine.kind == "router":
            lines, last = [f"$J=G91 G21 {axis}{distance} F{feed}"], None
        else:
            lines, last = ["G91", f"G1 {axis}{distance} F{feed}"], "G90"
        if self._lines(port, lines, last=last):
            self.said = (
                f"{axis} {'+' if steps > 0 else '-'}{_mm(abs(steps) * self.step_mm)} mm",
                "grey",
            )
            self._after(port)

    def _fourth(self, steps: int) -> None:
        port = self._port()
        if port is None or not self._ready(port):
            return
        if self.machine.kind == "printer":
            lines = ["M83", f"G1 E{_mm(steps * EXTRUDE_MM_PER_STEP)} F{EXTRUDE_FEED}"]
            if self._lines(port, lines):
                self.said = (f"E {_mm(steps * EXTRUDE_MM_PER_STEP)} mm", "grey")
                self._after(port)
            return
        spindle = getattr(self.last, "spindle", None)
        if spindle is None or not spindle.on:
            self.said = ("spindle off: start it in the Machine first", "red")
            return
        now = spindle.target or spindle.rpm
        rpm = int(min(max(now + steps * SPINDLE_RPM_PER_STEP, 0), grbl.SPINDLE_MAX_RPM))
        if self._lines(port, [f"M3 S{rpm}"]):
            self.said = (f"spindle {rpm} rpm", "grey")
            self._after(port)

    def _stop(self, machines: List[Machine]) -> None:
        """Each of ``machines`` sent its own dialect's stop, one after another, whatever one of
        them answers: a stop never waits on the latch, a poll or another machine."""
        stopped, failed = [], []
        for machine in machines:
            port = self.resolve(machine)
            if port is None:
                failed.append(f"{machine.name} (no board pinned)")
                continue
            try:
                self.send(port, devices.emergency_stop_for(port))
                self.sent.append(f"stop {machine.name}")
                stopped.append(machine.name)
            except (ValueError, ToolchainError) as exc:
                failed.append(f"{machine.name} ({exc})")
        said = f"STOP sent to {', '.join(stopped)}" if stopped else "STOP reached nothing"
        if failed:
            said += f"; not {', '.join(failed)}"
        self.said = (said, "red")

    def _after(self, port: str) -> None:
        """What the machine says now, for the readouts: a poll never moves anything."""
        try:
            self.last = self.poll(port)
        except ToolchainError:
            pass

    # -- drawing ------------------------------------------------------------------------

    def _readout(self, axis: str) -> str:
        status = self._newest()
        where = getattr(status, "work_position", None) or getattr(status, "position", None) or {}
        value = where.get(axis.lower())
        return "-" if value is None else f"{value:.1f}"

    def _port_quiet(self) -> Optional[str]:
        try:
            return self.resolve(self.machine)
        except Exception:  # noqa: BLE001 -- nothing pinned is a dash on a key
            return None

    def _fourth_readout(self) -> Tuple[str, str]:
        if self.machine.kind == "printer":
            return "E", "1 mm a step"
        status = self._newest()
        spindle = getattr(status, "spindle", None)
        return "S", (f"{spindle.rpm:.0f} rpm" if spindle is not None and spindle.on else "off")

    def _put(self, slot, text: str, colour: str, small: Optional[str]) -> None:
        wanted = (text, colour, small)
        if self._drawn.get(slot) == wanted:
            return
        if slot == "strip":
            self.deck.set_strip(text, colour, small)
        else:
            self.deck.set_key(slot, text, colour, small)
        self._drawn[slot] = wanted

    def draw(self) -> None:
        """Every key and the strip as the layout has them; what was drawn already is not sent
        again."""
        with self._lock:
            for index, machine in zip(KEY_MACHINE, MACHINES, strict=True):
                chosen = machine is self.machine
                self._put(index, machine.kind.upper(), "green" if chosen else "grey", machine.name)
            self._put(KEY_STEP, "STEP", "amber", f"{_mm(self.step_mm)} mm")
            for index, machine in zip(KEY_STOP_MACHINE, MACHINES, strict=True):
                self._put(index, "STOP", STOP_ONE_COLOUR, machine.name)
            self._put(KEY_STOP_ALL, "STOP ALL", STOP_ALL_COLOUR, "every machine")
            any_armed = bool(self._armed_machines())
            self._put(
                KEY_DISARM,
                "DISARM",
                "blue" if any_armed else "grey",
                "every machine" if any_armed else "nothing armed",
            )
            if self.machine.kind == "router" and self._alarmed():
                self._put(KEY_UNLOCK, "UNLOCK", "amber", self.machine.name)
            else:
                self._put(KEY_UNLOCK, "", "black", None)
            name, small = self._fourth_readout()
            readout = (
                "  ".join(f"{axis} {self._readout(axis)}" for axis in AXES) + f"  {name} {small}"
            )
            port = self._port_quiet()
            left = self.armed(port) if port else 0.0
            armed = f"armed {int(left) // 60}:{int(left) % 60:02d}" if left > 0 else "disarmed"
            text, colour = self.said
            self._put(
                "strip",
                f"{self.machine.name} · {armed}",
                "green" if left > 0 else "grey",
                f"{readout} · {_mm(self.step_mm)} mm · {text}" if colour != "red" else text,
            )

    def state(self) -> dict:
        with self._lock:
            port = self._port_quiet()
            return {
                "running": self._alive.is_set(),
                "deck": self.deck.info.id,
                "machines": [machine.name for machine in MACHINES],
                "steps_mm": list(STEPS_MM),
                "machine": self.machine.name,
                "port": port,
                "step_mm": self.step_mm,
                "armed_s": self.armed(port) if port else 0.0,
                "said": self.said[0],
                "sent": list(self.sent[-20:]),
                "deck_alive": self.deck.alive(),
                "deck_mended": self.deck.mended,
            }


# --- the controllers, one per deck ---------------------------------------------------------

_RUNNING: Dict[str, DeckController] = {}
_LOCK = threading.Lock()


def start(deck_id: str) -> DeckController:
    """The layout started on ``deck_id`` (opening it), or the one already running."""
    with _LOCK:
        if deck_id in _RUNNING:
            return _RUNNING[deck_id]
        controller = DeckController(decks.get_decks().get(deck_id)).start()
        _RUNNING[deck_id] = controller
        return controller


def stop(deck_id: str) -> bool:
    with _LOCK:
        controller = _RUNNING.pop(deck_id, None)
    if controller is None:
        return False
    controller.stop()
    return True


def controls() -> List[dict]:
    """Every layout running, one per deck: what its knobs move, their step, the control's
    seconds left. The Deck window and each Machine's Control pad read it."""
    with _LOCK:
        running = list(_RUNNING.values())
    return [controller.state() for controller in running]


def running(deck_id: str) -> Optional[DeckController]:
    return _RUNNING.get(deck_id)


def start_all() -> List[str]:
    """The layout on every deck found, when ``APOTHECARY_DECK_CONTROL`` asks; the ids."""
    if not enabled():
        return []
    try:
        found = decks.get_decks().list()
    except decks.DeckUnavailable:
        return []
    started = []
    for info in found:
        try:
            start(info.id)
            started.append(info.id)
        except (decks.DeckUnavailable, ToolchainError, KeyError):
            continue
    return started


def stop_all() -> None:
    for deck_id in list(_RUNNING):
        stop(deck_id)
