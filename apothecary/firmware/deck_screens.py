"""What the deck shows, one screen at a time, and the touches and presses that change it.

``firmware/deck_control.py`` is the layout on a deck; this module is the part of it that
needs no deck, no machine and no clock of its own, so each piece is read and tested from
what it is given:

- **The screens**, in order: ``bench`` (both machines at once), then the chosen
  machine's own -- ``knobs`` (Jog: where the tool is, the step, what the last turn did),
  ``home`` (each axis's switch, and the key that homes them), ``progress`` (the print or
  the cut the machine runs, or ran last), ``status`` (a printer's temperatures as a graph,
  a router's state, pins and spindle) and ``bed`` (the newest reading of a printer's bed
  or a router's table, and the key that probes it). Each machine names them in its own
  words (``LABELS``): a printer's progress is its Print, a router's its Cut. ``Screens``
  holds which one is showing; a swipe moves one along or back and stops at either end, a
  knob pressed moves one along and comes round from the last to the first, and a tap goes
  to the screen whose name is under the finger (``tab_at``).
- **The swipe**, recognised here and nowhere else: ``swipe_of`` reads the strip's touch
  as ``firmware/deck.py`` reports it -- ``{"kind": "drag", "x", "y", "x_out", "y_out"}``,
  where ``x`` and ``y`` are where the finger went down and ``x_out`` and ``y_out`` where
  it came up -- and says forward (the finger moved left, as a page is turned), back, or
  neither. A tap or a long press is neither.
- **What a screen says**, ``bench_strip``, ``home_strip``, ``progress_strip``,
  ``status_strip`` and ``bed_strip``, as pure functions of the job, the machine's last
  status, its readings (``firmware/readings.py``) and its bed's newest reading. Each says
  it twice: in words (``text`` and ``small``, which the Deck window writes under the
  strip's picture) and as the ``body`` the picture is drawn from
  (``firmware/deck_draw.py``). The machines' keys are drawn the same way
  (``machine_tile``), and so is the key each screen has of its own (``screen_key``).
  Nothing here states a number the job record, the status or a reading does not carry: a
  remaining time is not shown, because none carries one.

Nothing here sends a line to a machine, asks one for a reading or touches a port.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

BENCH, KNOBS, HOME, PROGRESS, STATUS, BED = "bench", "knobs", "home", "progress", "status", "bed"
ORDER: Tuple[str, ...] = (BENCH, KNOBS, HOME, PROGRESS, STATUS, BED)
START = KNOBS  # the screen a layout starts on: the one its knobs move a machine on
# What each kind of machine calls each screen, on the strip's tabs and in the Deck window.
LABELS: Dict[str, Dict[str, str]] = {
    "printer": {
        BENCH: "Bench",
        KNOBS: "Jog",
        HOME: "Home",
        PROGRESS: "Print",
        STATUS: "Temps",
        BED: "Bed",
    },
    "router": {
        BENCH: "Bench",
        KNOBS: "Jog",
        HOME: "Home",
        PROGRESS: "Cut",
        STATUS: "Status",
        BED: "Table",
    },
}
STRIP_W = 800  # the strip's width in its own pixels (deck.STRIP_SIZE)
GRAPH_S = 600.0  # the Temps screen's graph: the last ten minutes
SPARK_S = 600.0  # a key's spark line: the same ten minutes

FORWARD, BACK = 1, -1
SWIPE_MIN_PX = 200  # a quarter of the strip's 800: shorter is a slip, not a swipe
READING_FRESH_S = 10.0  # a status older than this is shown with its age

NAME_MAX = 26  # characters of a file's or part's name the strip has room for


def screens_for(kind: str) -> Tuple[str, ...]:
    """The screens of a machine of ``kind`` ("printer" or "router"), in the order a swipe
    walks them. Both have all six: a cut is a job as a print is, a table a bed."""
    return ORDER


def label(kind: str, screen: str) -> str:
    """What a machine of ``kind`` calls ``screen``."""
    return LABELS.get(kind, LABELS["printer"]).get(screen, screen)


def labels_for(kind: str, order: Sequence[str] = ORDER) -> List[str]:
    return [label(kind, screen) for screen in order]


def tab_at(touch: object, count: int) -> Optional[int]:
    """The screen whose name is under a tap or a long press of the strip, as an index
    into ``count`` screens laid out evenly along it; None for any other touch."""
    if not isinstance(touch, dict) or touch.get("kind") not in ("short", "long") or count < 1:
        return None
    try:
        x = int(touch["x"])
    except (KeyError, TypeError, ValueError):
        return None
    return max(0, min(count - 1, x * count // STRIP_W))


def swipe_of(touch: object) -> int:
    """``FORWARD`` or ``BACK`` for the strip's touch if it is a swipe, else 0. A drag of
    at least ``SWIPE_MIN_PX`` along the strip (it is 100 tall, so what is across it never
    outweighs that); a finger moving left is forward."""
    if not isinstance(touch, dict) or touch.get("kind") != "drag":
        return 0
    try:
        dx = int(touch["x_out"]) - int(touch["x"])
    except (KeyError, TypeError, ValueError):
        return 0
    if abs(dx) < SWIPE_MIN_PX:
        return 0
    return FORWARD if dx < 0 else BACK


class Screens:
    """Which of a machine's screens is showing."""

    def __init__(self, order: Sequence[str] = ORDER, start: str = START):
        self.order: Tuple[str, ...] = tuple(order)
        self.index = self.order.index(start) if start in self.order else 0

    @property
    def current(self) -> str:
        return self.order[self.index]

    def swipe(self, direction: int) -> bool:
        """One screen forward (``FORWARD``) or back (``BACK``); False, and nothing moved,
        at the end of the order."""
        wanted = self.index + (1 if direction > 0 else -1)
        if not 0 <= wanted < len(self.order):
            return False
        self.index = wanted
        return True

    def cycle(self) -> None:
        """One screen forward, and from the last round to the first: a knob pressed."""
        self.index = (self.index + 1) % len(self.order)

    def show(self, name: str) -> bool:
        """``name`` brought forward; False when this machine has no such screen."""
        if name not in self.order:
            return False
        self.index = self.order.index(name)
        return True

    def reorder(self, order: Sequence[str]) -> None:
        """A new order, keeping the screen showing when it is still there."""
        kept = self.current
        self.order = tuple(order)
        self.index = self.order.index(kept) if kept in self.order else 0

    @property
    def position(self) -> str:
        return f"{self.index + 1}/{len(self.order)}"


@dataclass(frozen=True)
class Strip:
    """What the strip says and is drawn with: a big line and a small one under it, in
    words; a colour; when there is a bar, how full it is (0 to 1); the ``body`` its
    picture is drawn from (``deck_draw.draw_strip``); and the ``footer``, the line under
    the body, where the words say more than the body draws."""

    text: str
    small: Optional[str]
    colour: str
    bar: Optional[float] = None
    body: Optional[dict] = None
    footer: Optional[str] = None


def clock(seconds: float) -> str:
    """``m:ss``, or ``h:mm:ss`` from the hour."""
    whole = max(0, int(seconds))
    hours, rest = divmod(whole, 3600)
    return f"{hours}:{rest // 60:02d}:{rest % 60:02d}" if hours else f"{rest // 60}:{rest % 60:02d}"


def _clip(name: str) -> str:
    return name if len(name) <= NAME_MAX else name[: NAME_MAX - 1] + "…"


def _age(status, now: datetime) -> Optional[float]:
    at = getattr(status, "polled_at", None)
    if at is None:
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return max(0.0, (now - at).total_seconds())


def job_name(job) -> str:
    """The part a job makes, else the file it ran."""
    part = getattr(job, "part", None)
    return _clip(part.name if part is not None else job.input.name)


# stage -> colour while the job runs: a held or ending job is amber, a plain run blue
_STAGE_COLOUR = {"paused": "amber", "cancelling": "amber", "finishing": "blue"}
_ENDED = {
    "done": ("done", "green"),
    "cancelled": ("cancelled", "amber"),
    "failed": ("failed", "red"),
}


def _said_once(reason: str, word: str) -> str:
    """A job's reason without the word the strip already says before it: a host's cancel
    is recorded "cancelled; heaters and fan off, motors free", which the strip would say
    as "cancelled (cancelled; ...)"."""
    if reason.lower().startswith(word):
        return reason[len(word) :].lstrip(" ;:,-")
    return reason


def _numbers(kind: str, status) -> str:
    """A machine's numbers in a line: a printer's hotends and bed, a router's spindle and
    feed; empty with no reading."""
    if status is None:
        return ""
    if kind == "printer":
        hotends = ", ".join(_heat("hotend", h) for h in status.hotends) or "hotend -"
        return f"{hotends} · {_heat('bed', status.bed)}"
    spindle = getattr(status, "spindle", None)
    speed = f"{spindle.rpm:.0f} rpm" if spindle is not None and spindle.on else "off"
    feed = getattr(status, "feed", None)
    return f"spindle {speed} · feed {feed:g}" if feed is not None else f"spindle {speed}"


def progress_strip(
    machine: str, job, status, now: datetime, position: str, kind: str = "printer"
) -> Strip:
    """The Progress screen of ``machine``: ``job`` is the host's job record (a print, a
    cut) as it stands, running or ended, or None; ``status`` the machine's newest poll,
    whose card print is shown when no job of the host's is. The elapsed time is the job's
    own, from when it began; no remaining time is shown, since no record carries one."""
    numbers = _numbers(kind, status)
    if job is not None:
        percent = int(round(job.progress * 100))
        elapsed = ((job.finished_at or now) - job.started_at).total_seconds()
        fraction = max(0.0, min(1.0, job.progress))
        if job.running:
            stage = str(job.detail.get("stage") or "running")
            colour = _STAGE_COLOUR.get(stage, "blue")
            small = f"{machine} · {stage} · elapsed {clock(elapsed)} · {position}"
            left, right = f"{stage} · elapsed {clock(elapsed)}", numbers
        else:
            word, colour = _ENDED.get(job.outcome, (job.outcome, "grey"))
            reason = _said_once(job.reason or "", word)
            why = f" ({reason})" if reason and job.outcome != "done" else ""
            small = f"{machine} · {word}{why} after {clock(elapsed)} · tap to clear · {position}"
            left, right = f"{word}{why} after {clock(elapsed)}", "tap to clear"
        operation = (job.detail or {}).get("operation")
        title = job_name(job) + (f" · {operation}" if operation else "")
        return Strip(
            f"{job_name(job)} · {percent}%",
            small,
            colour,
            fraction,
            body={
                "kind": "progress",
                "title": title,
                "percent": percent,
                "bar": fraction,
                "left": left,
                "right": right,
            },
        )
    if getattr(status, "sd_printing", False) and status.sd_progress is not None:
        small = f"{machine} · from the card"
        left = "from the card"
        if status.print_time_s is not None:
            small += f" · elapsed {clock(status.print_time_s)}"
            left += f" · elapsed {clock(status.print_time_s)}"
        percent = int(round(status.sd_progress * 100))
        fraction = max(0.0, min(1.0, status.sd_progress))
        return Strip(
            f"card print · {percent}%",
            f"{small} · {position}",
            "blue",
            fraction,
            body={
                "kind": "progress",
                "title": "card print",
                "percent": percent,
                "bar": fraction,
                "left": left,
                "right": numbers,
            },
        )
    word = "printing" if kind == "printer" else "cutting"
    return Strip(
        f"{machine} · no job",
        f"nothing is printing or cutting · {position}",
        "grey",
        body={
            "kind": "lines",
            "text": f"{machine} · no job",
            "small": [f"nothing is {word}", numbers],
        },
    )


def _heat(name: str, heater) -> str:
    if heater is None:
        return f"{name} -"
    target = f"/{heater.target:g}" if heater.target > 0 else " off"
    return f"{name} {heater.actual:.0f}{target}"


def needs(status) -> Optional[str]:
    """The first thing the machine asks of a person: what ``todo`` lists first, else its
    alarm in the dialect's words."""
    todo = getattr(status, "todo", None) or []
    if todo:
        return str(todo[0])
    alarm = getattr(status, "alarm", None)
    if alarm is not None:
        return str(getattr(status, "alarm_text", None) or f"alarm {alarm}")
    return None


def state_colour(status) -> str:
    """A machine's state as a colour: red in alarm, amber when it asks something of a
    person or a job is held, green while it works, grey idle; grey with no reading."""
    if status is None:
        return "grey"
    need = needs(status)
    held = getattr(status, "job", None) or {}
    stage = held.get("stage") if isinstance(held, dict) else None
    if need and (status.state == "alarm" or getattr(status, "alarm", None) is not None):
        return "red"
    if need:
        return "amber"
    if stage:
        return _STAGE_COLOUR.get(stage, "green")
    if status.state in ("printing", "running"):
        return "green"
    if status.state == "offline":
        return "red"
    return "grey"


def _series(readings: Sequence, field: str) -> List[List[float]]:
    """``(time, as read)`` of one heater (``hotend``, ``bed``) or number (``spindle_rpm``)
    across ``readings``, oldest first."""
    out = []
    for reading in readings:
        value = getattr(reading, field, None)
        if isinstance(value, tuple):
            value = value[0]
        if value is not None:
            out.append([round(reading.at, 2), round(float(value), 1)])
    return _thin(out)


def _thin(points: List[List[float]], most: int = 200) -> List[List[float]]:
    """At most ``most`` points, evenly picked, the newest kept: the strip is 660 pixels
    of graph, and the art is read back from the deck's state."""
    if len(points) <= most:
        return points
    step = len(points) / most
    picked = [points[int(i * step)] for i in range(most - 1)]
    return picked + [points[-1]]


def status_strip(
    machine: str, kind: str, status, now: datetime, position: str, readings: Sequence = ()
) -> Strip:
    """The Status screen of ``machine``: its state; a printer's hotends and bed, or a
    router's spindle and feed; and the first thing it needs of a person. Read from the
    newest poll, its age said when it is old: a deck that asks a machine nothing mid-job
    shows the last reading anyone's poll made. Where a job holds the port its stage is the
    state said -- a print paused is paused -- since a poll made during a job says the
    busy word whatever the job's stage. A printer's is drawn as a graph of its
    ``readings`` (``firmware/readings.py``) over the last ``GRAPH_S``; a router's as
    panels: its state, its pins, its spindle and its work zero."""
    if status is None:
        body = (
            _temps_body(kind, None, (), now)
            if kind == "printer"
            else {"kind": "lines", "text": f"{machine} · no reading", "small": ["not polled yet"]}
        )
        return Strip(
            f"{machine} · no reading",
            f"not polled yet · {position}",
            "grey",
            body=body,
            footer=f"{machine} · not polled yet: a Machine or the Site polls it",
        )
    numbers = _numbers(kind, status)
    need = needs(status)
    parts = [numbers]
    if need:
        parts.append(need)
    age = _age(status, now)
    old = age is not None and age > READING_FRESH_S
    if old:
        parts.append(f"read {clock(age)} ago")
    parts.append(position)
    held = getattr(status, "job", None) or {}
    stage = held.get("stage") if isinstance(held, dict) else None
    colour = state_colour(status)
    said = stage or status.state
    footer = " · ".join(
        [f"{machine} · {said}"]
        + ([need] if need else [])
        + [f"read {clock(age)} ago" if old else "read just now" if age is not None else ""]
    ).rstrip(" ·")
    if kind == "printer":
        body = _temps_body(kind, status, readings, now)
    else:
        body = _router_body(status, need)
    return Strip(f"{machine} · {said}", " · ".join(parts), colour, body=body, footer=footer)


def _temps_body(kind: str, status, readings: Sequence, now: datetime) -> dict:
    """A printer's hotend and bed over the last ``GRAPH_S``: each as read, what it was
    asked to reach dashed, and its newest written at the right."""
    series = []
    for name, field, heater in (
        (
            "hotend",
            "hotend",
            (status.hotends[0] if status is not None and status.hotends else None),
        ),
        ("bed", "bed", getattr(status, "bed", None)),
    ):
        points = _series(readings, field)
        if heater is None and not points:
            continue
        target = float(heater.target) if heater is not None and heater.target > 0 else None
        value = f"{heater.actual:.0f}°" if heater is not None else None
        aim = f"{name} {target:g}" if target else f"{name} off"
        series.append(
            {
                "label": name,
                "colour": name,
                "points": points,
                "target": target,
                "value": value,
                "aim": aim,
            }
        )
    return {
        "kind": "graph",
        "now": round(now.timestamp(), 2),
        "window_s": GRAPH_S,
        "window_label": f"last {int(GRAPH_S // 60)} min",
        "lo": 0,
        "series": series,
        "empty": "no readings yet: a Machine or the Site polls it",
    }


_PINS = (
    ("X", "limit X"),
    ("Y", "limit Y"),
    ("Z", "limit Z"),
    ("P", "probe"),
    ("D", "door"),
    ("H", "hold"),
)


def _router_body(status, need: Optional[str]) -> dict:
    """A router's state, its pins, its spindle and feed, and its work zero, a panel each."""
    state = getattr(status, "machine_state", None) or status.state
    on = set(getattr(status, "pins", None) or [])
    lit = [name for pin, name in _PINS if pin in on]
    spindle = getattr(status, "spindle", None)
    feed = getattr(status, "feed", None)
    origin = getattr(status, "work_offset", None) or {}
    zero = " ".join(f"{k.upper()} {v:g}" for k, v in origin.items() if k in "xyz" and v is not None)
    return {
        "kind": "panels",
        "panels": [
            {"label": "state", "value": state, "colour": state_colour(status), "small": need or ""},
            {
                "label": "pins",
                "value": " ".join(pin for pin, _ in _PINS if pin in on) or "none",
                "colour": "amber" if lit else None,
                "small": ", ".join(lit) or "no switch on",
            },
            {
                "label": "spindle",
                "value": f"{spindle.rpm:.0f}" if spindle is not None and spindle.on else "off",
                "small": f"rpm · feed {feed:g}"
                if feed is not None and spindle is not None and spindle.on
                else f"feed {feed:g}"
                if feed is not None
                else "",
            },
            {"label": "work zero", "value": "G54" if zero else "-", "small": zero or "not read"},
        ],
    }


def held_words(kind: str, words: str) -> str:
    """What the knobs of a machine a job holds say: ``words``, the server's own refusal of
    a jog (``PortHeld``), and what the knobs still do. The strip's small line, and the Deck
    window's line for the knobs."""
    can = "knob 4 still turns the spindle" if kind == "router" else "no knob moves it"
    return f"{words} · jogs refused, {can}"


def held_strip(
    machine: str, kind: str, words: str, position: str, panels: Sequence[dict] = ()
) -> Strip:
    """The knobs screen of a machine a job holds: not live. ``words`` is what the server
    itself says when it refuses a jog (``PortHeld``). A cut still takes a spindle speed,
    which the dialect lets through; a print takes nothing from the knobs. ``panels`` are
    the knobs' own, greyed, but for a router's fourth."""
    shown = [{**panel, "off": not (kind == "router" and i == 3)} for i, panel in enumerate(panels)]
    return Strip(
        f"{machine} · held",
        held_words(kind, words),
        "amber",
        body={"kind": "panels", "panels": shown} if shown else None,
        footer=held_words(kind, words),
    )


def knob_panels(
    kind: str, where: Dict[str, str], step_mm: str, fourth: Tuple[str, str]
) -> List[dict]:
    """The Jog screen's four panels, one over each knob: X, Y and Z where the tool is and
    the step a click moves; the fourth, a printer's extruder or a router's spindle."""
    panels = [
        {
            "label": f"{axis}  knob {i + 1}",
            "value": where.get(axis, "-"),
            "small": f"step {step_mm} mm",
        }
        for i, axis in enumerate(("X", "Y", "Z"))
    ]
    name, small = fourth
    if kind == "printer":
        panels.append({"label": f"{name}  knob 4", "value": "1 mm", "small": "a step, extruded"})
    else:
        on = small != "off"
        panels.append(
            {
                "label": f"{name}  knob 4",
                "value": small.replace(" rpm", "") if on else "off",
                "small": "rpm, 1000 a step" if on else "start it in the Machine",
                "off": not on,
            }
        )
    return panels


def bench_strip(machines: Sequence[dict], now: datetime, position: str) -> Strip:
    """Both machines at once, half the strip each: its name, its state, its numbers and
    its job's bar. Each of ``machines`` is ``{"name", "kind", "status", "job", "armed_s"}``
    as the layout has it."""
    columns, words = [], []
    for one in machines:
        name, kind, status, job = one["name"], one["kind"], one.get("status"), one.get("job")
        armed = float(one.get("armed_s") or 0)
        held = getattr(status, "job", None) or {}
        stage = held.get("stage") if isinstance(held, dict) else None
        state = "no reading" if status is None else (stage or status.state)
        line = _numbers(kind, status) or "not polled yet"
        column = {
            "name": name,
            "state": state + (f" · armed {clock(armed)}" if armed > 0 else ""),
            "colour": "green"
            if armed > 0 and state_colour(status) == "grey"
            else state_colour(status),
            "line": line,
        }
        if job is not None and job.running:
            column["bar"] = max(0.0, min(1.0, job.progress))
            column["bar_label"] = f"{job_name(job)} · {int(round(job.progress * 100))}%"
        words.append(f"{name} {column['state']}")
        columns.append(column)
    return Strip(
        "Bench · " + " · ".join(words),
        " · ".join(f"{c['name']}: {c['line']}" for c in columns) + f" · {position}",
        "grey",
        body={"kind": "machines", "machines": columns},
        footer="the knobs move nothing here: Jog is where they do",
    )


def home_strip(machine: str, kind: str, status, now: datetime, position: str) -> Strip:
    """The Home screen: each axis where it stands and its switch -- a printer's endstop as
    its last poll read it, a router's homing as its controller says it will seek and
    whether this server has seen its switch -- and the key that homes them all."""
    line = "G28" if kind == "printer" else "$H"
    panels, words = [], []
    where = (
        (getattr(status, "work_position", None) or getattr(status, "position", None) or {})
        if status
        else {}
    )
    homing = {h.get("axis"): h for h in (getattr(status, "homing", None) or [])} if status else {}
    ends = (getattr(status, "endstops", None) or {}) if status else {}
    pins = set(getattr(status, "pins", None) or []) if status else set()
    for axis in ("X", "Y", "Z"):
        value = where.get(axis.lower())
        if kind == "printer":
            switch = ends.get(f"{axis.lower()}_min")
            small = f"min {switch.lower()}" if switch else "endstop not read"
            hot = bool(switch) and switch.upper() == "TRIGGERED"
        else:
            how = homing.get(axis)
            if how is None:
                small = "homing not read"
            else:
                small = f"seeks {how.get('way', '?')}" + (
                    " · proved" if how.get("ready") else " · not proved"
                )
            hot = axis in pins
        panels.append(
            {
                "label": f"{axis}  switch" + (" on" if hot else ""),
                "value": "-" if value is None else f"{value:.1f}",
                "colour": "amber" if hot else None,
                "small": small,
            }
        )
        words.append(f"{axis} {small}")
    panels.append(
        {
            "label": "home all",
            "value": line,
            "small": "hold HOME a second",
        }
    )
    state = "no reading" if status is None else status.state
    return Strip(
        f"{machine} · home",
        " · ".join(words) + f" · {position}",
        state_colour(status) if status is not None else "grey",
        body={"kind": "panels", "panels": panels},
        footer=f"{machine} · {state} · hold HOME a second to home every axis ({line}), control armed",
    )


def bed_strip(machine: str, kind: str, record, job, now: datetime, position: str) -> Strip:
    """The Bed screen: the newest reading of the machine's bed (a printer's mesh, a
    router's table map) as coloured cells, its range, when it was taken and how warm the
    bed was; a reading under way says its stage instead. The key that probes it is said."""
    what = "the bed" if kind == "printer" else "the table"
    running = job is not None and job.get("running")
    lines: List[str] = []
    mesh = getattr(record, "mesh", None) or []
    if record is not None and mesh:
        stats = getattr(record, "stats", None) or {}
        rows, cols = stats.get("rows") or len(mesh), stats.get("cols") or len(mesh[0])
        span = stats.get("range")
        lines.append(f"range {span:.3f} mm" if span is not None else "range -")
        at = record.at if record.at.tzinfo else record.at.replace(tzinfo=timezone.utc)
        ago = max(0.0, (now - at).total_seconds())
        warm = f" · bed {record.bed_c:.0f}°" if getattr(record, "bed_c", None) is not None else ""
        lines.append(f"{rows}x{cols} probed {_ago(ago)} ago{warm}")
        on = getattr(record, "leveling_on", None)
        if on is not None:
            lines.append("levelling on" if on else "levelling off")
    else:
        lines.append(f"no reading of {what}")
    colour = "grey"
    if running:
        lines.insert(0, f"probing · {job.get('stage') or 'starting'}")
        colour = "amber"
    elif job is not None and job.get("error"):
        lines.insert(0, "last probe failed")
        lines.insert(1, str(job.get("error")))
        colour = "red"
    verb = "probe the bed" if kind == "printer" else "map the table"
    return Strip(
        f"{machine} · {lines[0]}",
        " · ".join(lines[1:]) + f" · {position}",
        colour,
        body={"kind": "mesh", "mesh": mesh, "lines": lines[:4]},
        footer=f"{machine} · hold PROBE a second to {verb}, control armed",
    )


def _ago(seconds: float) -> str:
    if seconds < 60:
        return "under a minute"
    if seconds < 3600:
        return clock(seconds)
    hours = seconds / 3600
    return f"{hours:.0f} h" if hours < 48 else f"{hours / 24:.0f} days"


# --- the keys -------------------------------------------------------------------------


def machine_tile(
    name: str,
    kind: str,
    status,
    job,
    readings: Sequence,
    armed_s: float,
    chosen: bool,
) -> dict:
    """A machine's key as a tile: its kind along the top, on its state's colour (green
    while its control is armed); a printer's hotend as read, a router's state word; under
    it its bed or its spindle, or how long its control has left; and at its foot its job's
    bar, else a printer's hotend and bed over the last ``SPARK_S``. Framed while chosen."""
    art: dict = {"kind": "tile", "title": kind.upper(), "chosen": chosen}
    colour = state_colour(status)
    art["accent"] = "green" if armed_s > 0 and colour in ("grey", "green") else colour
    if kind == "printer":
        hot = status.hotends[0] if status is not None and status.hotends else None
        art["value"] = f"{hot.actual:.0f}°" if hot is not None else "-"
        bed = getattr(status, "bed", None)
        art["small"] = f"bed {bed.actual:.0f}°" if bed is not None else "no reading"
        points = [_series(readings, "hotend"), _series(readings, "bed")]
        if any(points):
            art["spark"] = {
                "series": [
                    {"colour": "hotend", "points": points[0]},
                    {"colour": "bed", "points": points[1]},
                ],
                "lo": 0,
            }
    else:
        state = getattr(status, "machine_state", None) or getattr(status, "state", None)
        art["value"] = (state or "-").split(":")[0]
        spindle = getattr(status, "spindle", None)
        art["small"] = (
            (f"{spindle.rpm:.0f} rpm" if spindle is not None and spindle.on else "spindle off")
            if status is not None
            else "no reading"
        )
    if armed_s > 0:
        art["small"] = f"armed {clock(armed_s)}"
    if job is not None and job.running:
        art["bar"] = max(0.0, min(1.0, job.progress))
        art.pop("spark", None)
        art["small"] = f"{int(round(job.progress * 100))}% · " + art["small"]
    return art


def screen_key(
    screen: str, kind: str, status, job, step_mm: str, readings: Sequence = ()
) -> Tuple[str, str, str, Optional[dict]]:
    """The key each screen has of its own, key 2: ``(text, small, colour, art)``. Jog's
    is STEP, Home's HOME and Bed's PROBE, each a key to press; Print's, Temps' and the
    others' show that screen's number, and a press of them does nothing."""
    if screen == KNOBS:
        return ("STEP", f"{step_mm} mm", "amber", None)
    if screen == HOME:
        return ("HOME", "hold: G28" if kind == "printer" else "hold: $H", "amber", None)
    if screen == BED:
        return ("PROBE", "hold: the bed" if kind == "printer" else "hold: the table", "amber", None)
    if screen == PROGRESS:
        title = "PRINT" if kind == "printer" else "CUT"
        if job is None:
            return (
                title,
                "no job",
                "grey",
                {"kind": "tile", "title": title, "value": "-", "small": "no job", "accent": "grey"},
            )
        percent = int(round(job.progress * 100))
        word = "running" if job.running else job.outcome
        art = {
            "kind": "tile",
            "title": title,
            "value": f"{percent}%",
            "small": word,
            "accent": "blue" if job.running else _ENDED.get(job.outcome, (word, "grey"))[1],
            "bar": max(0.0, min(1.0, job.progress)),
        }
        return (title, f"{percent}%", art["accent"], art)
    if screen == STATUS and kind == "printer":
        hot = status.hotends[0] if status is not None and status.hotends else None
        art = {
            "kind": "tile",
            "title": "HOTEND",
            "value": f"{hot.actual:.0f}°" if hot is not None else "-",
            "small": (f"to {hot.target:g}°" if hot.target > 0 else "off")
            if hot is not None
            else "no reading",
            "accent": "hotend",
        }
        points = _series(readings, "hotend")
        if points:
            art["spark"] = {"series": [{"colour": "hotend", "points": points}], "lo": 0}
        return ("HOTEND", art["value"], "hotend", art)
    if screen == STATUS:
        spindle = getattr(status, "spindle", None)
        on = spindle is not None and spindle.on
        art = {
            "kind": "tile",
            "title": "SPINDLE",
            "value": f"{spindle.rpm / 1000:.1f}k" if on else "off",
            "small": "rpm" if on else "not turning",
            "accent": "spindle",
        }
        return ("SPINDLE", art["value"], "spindle", art)
    return (
        "BENCH",
        "both machines",
        "grey",
        {"kind": "tile", "title": "BENCH", "value": "", "small": "both machines", "accent": "grey"},
    )
