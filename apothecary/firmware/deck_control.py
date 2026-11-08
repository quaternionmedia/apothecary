"""The Stream Deck + as a controller for the garage's two machines.

One layout, on every deck it is started for (``Deck`` in ``firmware/deck.py``):

- the top row's keys choose the machine (0 printer_1, 1 cnc_router) and cycle the jog
  step through 0.1, 1 and 10 mm (2);
- the bottom row holds the stops: 4 stops printer_1 and 5 cnc_router, each by its own
  dialect's stop, and 7, bright red and last, nearest a hand on the knobs, stops every
  machine, each by its own; none needs control armed;
- the strip says which machine, whether its control is armed and for how long, the
  chosen machine's last poll (X, Y, Z and the fourth quantity), the step, and what the
  last turn did or why it did nothing;
- knobs one to three jog X, Y and Z by so many steps; the fourth turns the spindle's
  speed in steps of 1000 rpm (only while it turns) or extrudes 1 mm a step;
- a machine's key held (``LONG_PRESS_S``) twice in a row, the second within
  ``ARM_WINDOW_S`` of the first, arms that machine's control for the latch's own five
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

It starts for a deck only when ``APOTHECARY_DECK_CONTROL`` is set (the demo sets it) or
a person asks (``POST /firmware/decks/{id}/control``): opening a real deck takes the
device from any other program that has it.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from . import deck as decks
from . import devices, gcode, grbl
from .toolchains import PortHeld, ToolchainError

CONTROL_ENV = "APOTHECARY_DECK_CONTROL"
SITE = "garage"
STEPS_MM = (0.1, 1.0, 10.0)
AXES = ("X", "Y", "Z")
KEY_MACHINE = (0, 1)
KEY_STEP = 2
# Two classes of stop, the owner's word: one key per machine, each sending that machine's
# own stop, and one that stops every machine at once. The everything key is the bottom
# row's last, nearest a hand resting on the knobs, bright red where the per-machine stops
# are dark; none needs control armed, as the page's E-STOP does not.
KEY_STOP_MACHINE = (4, 5)  # printer_1's and cnc_router's, in MACHINES' order
KEY_STOP_ALL = 7
STOP_ALL_COLOUR, STOP_ONE_COLOUR = "red", "#7a2a22"
KNOB_FOURTH = 3
FEED = {"printer": 3000, "router": 1000}  # the page's jog feeds (machine_words.js)
EXTRUDE_MM_PER_STEP = 1.0
EXTRUDE_FEED = 200  # under gcode.EXTRUDE_FEED_MAX
SPINDLE_RPM_PER_STEP = 1000
TICK_S = 2.0
LONG_PRESS_S = 0.8  # a machine's key held this long is a long press
ARM_WINDOW_S = 5.0  # the second long press of two must follow the first within this


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
    """The port the board pinned to ``machine``'s node is on now, or None."""
    from .bindings import device_for_identity

    state = devices.get_state()
    pin = next((b for b in state.bindings(SITE) if b.path == machine.node), None)
    if pin is None:
        return None
    try:
        found = devices.detected_devices(state=state)
    except ToolchainError:
        return None
    device = device_for_identity(pin.identity, found, pin.kind)
    return device.port if device is not None else None


def _mm(value: float) -> str:
    return f"{round(value, 2):g}"


class DeckController:
    """The layout on one deck: its events in, its keys and strip out, a machine's
    control lines between. The seams (``resolve``, ``send``, ``poll``, ``armed``) are
    what the machines' own functions are, so a test can stand its own in their place."""

    def __init__(
        self,
        deck: decks.Deck,
        resolve: Callable[[Machine], Optional[str]] = pinned_port,
        send: Optional[Callable[[str, str], object]] = None,
        poll: Optional[Callable[[str], object]] = None,
        armed: Optional[Callable[[str], float]] = None,
    ):
        self.deck = deck
        self.resolve = resolve
        self.send = send or (lambda port, line: devices.printer_control(port, line))
        self.poll = poll or (lambda port: devices.printer_status(port))
        # Seconds of control left on a port, 0 when it is not armed.
        self.armed = armed or (lambda port: gcode.get_printer_links().control.seconds_left(port))
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
        self._alive = threading.Event()
        self._stopped = threading.Event()

    # -- life -----------------------------------------------------------------------

    def start(self) -> "DeckController":
        self._alive.set()
        self._stopped.clear()
        self._stop_listening = self.deck.listen(self.handle)
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
                self._refresh()
                self.draw()
            except Exception:  # noqa: BLE001 -- a deck that went away: the next tick tries again
                pass

    @property
    def step_mm(self) -> float:
        return STEPS_MM[self.step]

    # -- events ---------------------------------------------------------------------

    def handle(self, event: decks.DeckEvent) -> None:
        """What the deck reported, as the layout reads it. Never raises: what could not be
        done is said on the strip."""
        with self._lock:
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
        held = event.at - self._down.pop(index, event.at)
        self._choose(index)
        if held < LONG_PRESS_S:
            self._first_long = None
            self.said = (f"{self.machine.name} chosen", "grey")
            return
        first = self._first_long
        if first is not None and first[0] == index and event.at - first[1] <= ARM_WINDOW_S:
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

    def _key(self, index: int) -> None:
        if index == KEY_STEP:
            self.step = (self.step + 1) % len(STEPS_MM)
            self.said = (f"step {_mm(self.step_mm)} mm", "grey")
        elif index in KEY_STOP_MACHINE:
            self._stop([MACHINES[KEY_STOP_MACHINE.index(index)]])
        elif index == KEY_STOP_ALL:
            self._stop(list(MACHINES))

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
        finally:
            if went and last is not None:
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
        status = self.last or devices.last_statuses().get(self._port_quiet() or "")
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
        status = self.last or devices.last_statuses().get(self._port_quiet() or "")
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
            self._put(3, "", "black", None)
            self._put(6, "", "black", None)
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
