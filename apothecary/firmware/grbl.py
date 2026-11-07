"""GRBL dialect of the G-code machine seam: a CNC router's controller over serial.

``gcode.py`` talks to boards running Marlin's dialect -- a printer's. A desktop
router's controller speaks GRBL's: the garage's AnoleX 4060-Evo Ultra 2 runs
Grbl_ESP32, which reports as ``Grbl 1.3a``, and by the same interface grbl 1.1
on an Arduino, FluidNC and grblHAL. The wire protocol is the one every sender
(UGS, Candle, bCNC, LightBurn) speaks: a line of G-code out, ``ok`` or
``error:N`` back to close it, and a few single characters that the controller
acts on at once, outside the line queue -- ``?`` for a status report, ``!`` to
hold, ``~`` to resume, ``0x18`` to reset. Multiple independent implementations
on both ends, so it passes the replaceability test; the parsers below are
written to grbl 1.1's documented interface and note where Grbl_ESP32 differs.

The held-open link, its log, the control latch and the registry of links are
``gcode.py``'s, shared: a router's port is opened, kept and released exactly as
a printer's is. What differs is here -- how a board is identified (``$I``,
there being no ``M115``), how it is polled (the realtime ``?`` and ``$G``),
which lines may be typed at it while control is armed and what bounds them,
what the emergency stop is (a soft reset), what a streamed job may not carry,
and a pretend controller behind the transport slot for demos and tests. The
site's words for its state are ``example_hierarchy.ROUTER_STATUSES``.
"""

from __future__ import annotations

import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

from . import gcode
from .gcode import GcodeLink, LinkBusy, OutOfBounds, mesh_stats
from .models import GRBL, BedReading, PrinterInfo, PrinterStatus, Spindle, TableGrid
from .toolchains import ToolchainError

DIALECT = GRBL
MACHINE = "router"

# --- parsers: grbl 1.1's documented replies ---------------------------------------

# <Idle|MPos:0.000,0.000,0.000|FS:0,0|WCO:0.000,0.000,0.000>
# <Run|WPos:12.500,-3.000,-1.000|Bf:12,120|FS:800,12000|Pn:XZ|Ov:100,100,100|A:S>
STATUS_RE = re.compile(r"^<([A-Za-z]+)(?::(\d+))?((?:\|[^|>]*)*)>$")
XYZ_RE = re.compile(r"^(-?\d+\.?\d*),(-?\d+\.?\d*),(-?\d+\.?\d*)")
# [VER:1.3a.20230715:]  (grbl 1.1: [VER:1.1h.20190825:]); [OPT:VNMPH,35,1024,3]
VER_RE = re.compile(r"^\[VER:([^:\]]*):?([^\]]*)\]$")
OPT_RE = re.compile(r"^\[OPT:([^\]]*)\]$")
MSG_RE = re.compile(r"^\[MSG:\s*(.*?)\s*\]$")
# [GC:G0 G54 G17 G21 G90 G94 M5 M9 T0 F0 S0]
GC_RE = re.compile(r"^\[GC:(.*)\]$")
# $110=4000.000
SETTING_RE = re.compile(r"^\$(\d+)=(-?\d+\.?\d*)")
ALARM_RE = re.compile(r"^ALARM:(\d+)")
# The controller's objections, `error:N` and `ALARM:N`: what closes an exchange on the
# link (gcode.OBJECTIONS) and what `explain` puts words to.
OBJECTION_RE = re.compile(r"^(error|ALARM):(\d+)")
gcode.OBJECTIONS.append(OBJECTION_RE)
# Grbl 1.3a ['$' for help]
BANNER_RE = re.compile(r"^Grbl (\S+) \[")
# [PRB:-12.000,-20.000,-41.250:1]
PRB_RE = re.compile(r"^\[PRB:(-?\d+\.?\d*),(-?\d+\.?\d*),(-?\d+\.?\d*):([01])\]$")

# The controller's state word, folded to the site's vocabulary
# (example_hierarchy.ROUTER_STATUSES). Hold and Door are a machine stopped with
# a job in it; Check and Sleep move nothing.
STATE_WORDS: Dict[str, str] = {
    "Idle": "idle",
    "Run": "running",
    "Jog": "running",
    "Home": "running",
    "Hold": "hold",
    "Door": "hold",
    "Alarm": "alarm",
    "Check": "idle",
    "Sleep": "idle",
}

# grbl 1.1's alarm codes, by number.
ALARMS: Dict[int, str] = {
    1: "hard limit triggered: machine position is lost",
    2: "a move would go past the soft limits",
    3: "reset while in motion: machine position is lost",
    4: "probe fail: the probe was already triggered",
    5: "probe fail: the probe did not touch within the move",
    6: "homing fail: reset during homing",
    7: "homing fail: the safety door opened",
    8: "homing fail: a limit switch stayed on after pull-off",
    9: "homing fail: no limit switch found within the search distance",
    10: "homing fail: a second limit switch triggered",
}

# grbl 1.1's error codes, the ones a typed line meets.
ERRORS: Dict[int, str] = {
    1: "a G-code word has no number",
    2: "a number is badly formed",
    3: "an unrecognised $ command",
    4: "a negative value where none is allowed",
    5: "homing is not enabled",
    8: "a $ command needs the machine idle",
    9: "G-code locked out: alarm or jog",
    10: "soft limits need homing",
    11: "the line is too long",
    15: "a jog would go past the travel",
    20: "an unsupported or invalid G-code",
    22: "a feed rate is missing",
}


def _xyz(text: str) -> Optional[dict]:
    m = XYZ_RE.match(text)
    if not m:
        return None
    x, y, z = (float(v) for v in m.groups())
    return {"x": x, "y": y, "z": z}


def parse_status(line: str) -> Optional[dict]:
    """A realtime status report, ``<State|Field:value|...>``, as a dict, or None.

    ``MPos`` or ``WPos`` is reported, by ``$10``; ``WCO`` every few reports.
    Whichever is missing is computed from the other when the offset is known
    (WPos = MPos - WCO).
    """
    m = STATUS_RE.match(line.strip())
    if not m:
        return None
    word, sub, rest = m.group(1), m.group(2), m.group(3)
    out: dict = {
        "machine_state": word,
        "substate": int(sub) if sub else None,
        "mpos": None,
        "wpos": None,
        "wco": None,
        "feed": None,
        "spindle_rpm": None,
        "buffer": None,
        "line": None,
        "pins": [],
        "overrides": None,
        "accessories": [],
    }
    for field in rest.split("|")[1:]:
        key, _, value = field.partition(":")
        if key == "MPos":
            out["mpos"] = _xyz(value)
        elif key == "WPos":
            out["wpos"] = _xyz(value)
        elif key == "WCO":
            out["wco"] = _xyz(value)
        elif key == "FS":
            f, _, s = value.partition(",")
            out["feed"], out["spindle_rpm"] = float(f or 0), float(s or 0)
        elif key == "F":
            out["feed"] = float(value or 0)
        elif key == "Bf":
            planner, _, rx = value.partition(",")
            out["buffer"] = {"planner": int(planner or 0), "rx": int(rx or 0)}
        elif key == "Ln":
            out["line"] = int(value or 0)
        elif key == "Pn":
            out["pins"] = list(value)
        elif key == "Ov":
            parts = value.split(",")
            if len(parts) == 3:
                out["overrides"] = {
                    "feed": int(parts[0]),
                    "rapid": int(parts[1]),
                    "spindle": int(parts[2]),
                }
        elif key == "A":
            out["accessories"] = list(value)
    if out["mpos"] and out["wco"] and not out["wpos"]:
        out["wpos"] = {k: round(out["mpos"][k] - out["wco"][k], 3) for k in "xyz"}
    elif out["wpos"] and out["wco"] and not out["mpos"]:
        out["mpos"] = {k: round(out["wpos"][k] + out["wco"][k], 3) for k in "xyz"}
    return out


def is_status_line(line: str) -> bool:
    return bool(STATUS_RE.match(line.strip()))


def site_state(machine_state: Optional[str]) -> str:
    """The site's word for the controller's: ``idle``, ``running``, ``hold``, ``alarm``."""
    return STATE_WORDS.get(machine_state or "", "idle")


def parse_build_info(lines: List[str]) -> dict:
    """``$I``'s answer: the version, the build, the option letters, and what the
    controller says of itself in ``[MSG:...]`` lines (Grbl_ESP32 names its machine
    there, ``[MSG:Using machine:...]``; grbl 1.1 says nothing)."""
    out: dict = {"version": None, "build": None, "options": "", "messages": [], "machine": None}
    for raw in lines:
        line = raw.strip()
        m = VER_RE.match(line)
        if m:
            version, build = m.group(1), m.group(2)
            if "." in version and version.count(".") >= 2:
                # 1.3a.20230715: the version, then the build date
                version, _, build_date = version.rpartition(".")
                out["build"] = build_date
            out["version"] = version
            if build:
                out["build"] = (out["build"] + " " if out["build"] else "") + build
            continue
        m = OPT_RE.match(line)
        if m:
            out["options"] = m.group(1)
            continue
        m = MSG_RE.match(line)
        if m:
            out["messages"].append(m.group(1))
            lowered = m.group(1).lower()
            for prefix in ("using machine:", "machine:"):
                if lowered.startswith(prefix):
                    out["machine"] = m.group(1)[len(prefix) :].strip()
    return out


def parse_parser_state(lines: List[str]) -> dict:
    """``$G``'s answer: the modal words, and from them whether the spindle is on,
    the programmed speed and feed, the work coordinate system and the units."""
    out: dict = {
        "modes": [],
        "spindle_on": False,
        "spindle_direction": None,
        "s": 0.0,
        "f": 0.0,
        "coordinate_system": None,
        "units": "mm",
        "distance": "absolute",
    }
    for raw in lines:
        m = GC_RE.match(raw.strip())
        if not m:
            continue
        words = m.group(1).split()
        out["modes"] = words
        for w in words:
            if w in ("M3", "M4"):
                out["spindle_on"] = True
                out["spindle_direction"] = "cw" if w == "M3" else "ccw"
            elif w == "M5":
                out["spindle_on"] = False
            elif w.startswith("S"):
                out["s"] = float(w[1:] or 0)
            elif w.startswith("F"):
                out["f"] = float(w[1:] or 0)
            elif re.fullmatch(r"G5[4-9](?:\.\d)?", w):
                out["coordinate_system"] = w
            elif w == "G20":
                out["units"] = "inch"
            elif w == "G21":
                out["units"] = "mm"
            elif w == "G91":
                out["distance"] = "relative"
            elif w == "G90":
                out["distance"] = "absolute"
    return out


def parse_probe(lines: List[str]) -> Optional[dict]:
    """The last ``[PRB:x,y,z:t]`` among ``lines`` -- where a probe stopped, in machine
    coordinates, and whether it touched -- as ``$#`` and a ``G38.2`` report it; None
    for none."""
    for line in reversed(lines):
        m = PRB_RE.match(line.strip())
        if m:
            x, y, z = (float(v) for v in m.groups()[:3])
            return {"x": x, "y": y, "z": z, "touched": m.group(4) == "1"}
    return None


def parse_settings(lines: List[str]) -> Dict[int, float]:
    """``$$``'s answer, ``$N=value`` per line, by number."""
    out: Dict[int, float] = {}
    for line in lines:
        m = SETTING_RE.match(line.strip())
        if m:
            out[int(m.group(1))] = float(m.group(2))
    return out


def travel_of(settings: Dict[int, float]) -> Optional[dict]:
    """The axes' maximum travel from the settings (``$130``, ``$131``, ``$132``, mm):
    the working area, in the controller's own word; None when any is missing."""
    if not all(n in settings for n in (130, 131, 132)):
        return None
    return {"x": settings[130], "y": settings[131], "z": settings[132]}


def parse_alarm(lines: List[str]) -> Optional[int]:
    """The last ``ALARM:N`` among ``lines``, or None."""
    found = None
    for raw in lines:
        m = ALARM_RE.match(raw.strip())
        if m:
            found = int(m.group(1))
    return found


def router_info_from(lines: List[str], baud: int, boot_lines: List[str] = ()) -> PrinterInfo:
    """A ``PrinterInfo`` of the GRBL dialect from ``$I``'s answer; ``ToolchainError``
    when no ``[VER:`` line is in it."""
    info = parse_build_info(lines)
    version = info["version"]
    if not version:
        banner = next(
            (BANNER_RE.match(ln.strip()) for ln in boot_lines if BANNER_RE.match(ln.strip())), None
        )
        if banner is None:
            raise ToolchainError("no [VER: line in the $I reply -- not a GRBL controller?")
        version = banner.group(1)
    return PrinterInfo(
        dialect=DIALECT,
        machine=MACHINE,
        firmware_name=f"Grbl {version}",
        machine_type=info["machine"] or ("Grbl_ESP32" if version.startswith("1.3") else None),
        protocol_version=info["build"],
        extruder_count=0,
        capabilities={letter: True for letter in info["options"].split(",")[0] if letter.isalpha()},
        baud=baud,
        boot_lines=list(boot_lines)[-40:],
        identified_at=datetime.now(timezone.utc),
    )


# --- the realtime characters -------------------------------------------------------------

# Named, so a request, a ring cell and a log line can carry one; written as the
# one byte each is. The controller acts on them as they arrive, outside the line
# queue: a hold decelerates at once, a reset halts everything and turns the
# spindle off. The soft reset is this dialect's emergency stop.
REALTIME: Dict[str, bytes] = {
    "STATUS": b"?",
    "HOLD": b"!",
    "RESUME": b"~",
    "RESET": b"\x18",
    "JOG-CANCEL": b"\x85",
}
EMERGENCY_STOP = "RESET"

# --- queries: report-only lines a person may type at an idle or busy controller ---

QUERY_CODES: Dict[str, str] = {
    "$$": "settings",
    "$#": "work offsets, the probe's last touch",
    "$G": "parser state: the modal words",
    "$I": "build info",
    "$N": "startup lines",
    "?": "status report",
}


def normalise_query(command: str) -> str:
    cmd = " ".join(command.strip().upper().split())
    if cmd not in QUERY_CODES:
        raise ValueError(f"not a report-only GRBL query: {command!r}")
    return cmd


# --- control: lines that move the machine or run the spindle, only while armed ---------

# Bounded here, for the garage's router: a jog or a move no longer than the
# longest axis, a feed no faster than the maker's figure for X and Y, a spindle no
# faster than the trim router turns, a probe no deeper than the Z travel. Operator
# controls only: no settings writes, no startup lines, no firmware configuration.
# A job streams a whole file past this list; what it may not carry is checked once,
# before the first line, by check_gcode below. Extend deliberately.
JOG_MAX_MM = 600
FEED_MAX = 4000
SPINDLE_MAX_RPM = 24000  # the trim router's: what M3 may ask, typed or in a file
PROBE_MAX_MM = 80
PROBE_FEED_MAX = 500
_AXES = r"(?: [XYZ]-?\d{1,3}(?:\.\d{1,3})?)"
CONTROL_CODES: List[tuple] = [
    (re.compile(r"^\$H(?:[XYZ])?$"), "home all, or one axis"),
    (re.compile(r"^\$X$"), "unlock after an alarm"),
    (re.compile(rf"^\$J=G91 G21{_AXES}{{1,3}} F\d{{1,5}}$"), "jog, relative, in mm"),
    (re.compile(r"^G90$"), "absolute positioning"),
    (re.compile(r"^G91$"), "relative positioning"),
    (re.compile(r"^G21$"), "millimetres"),
    (re.compile(rf"^G[01]{_AXES}{{1,3}}(?: F\d{{1,5}})?$"), "move"),
    (
        re.compile(rf"^G53 G0{_AXES}{{1,3}}$"),
        "a move in machine coordinates: the top of Z, a table map's points",
    ),
    (re.compile(r"^M3 S\d{1,5}$"), "spindle on, clockwise, at a speed"),
    (re.compile(r"^M5$"), "spindle off"),
    (re.compile(r"^G10 L20 P1(?: [XYZ]0){1,3}$"), "work zero here, for the named axes"),
    (re.compile(r"^G38\.2 Z-\d{1,3}(?:\.\d{1,2})? F\d{1,4}$"), "probe down to the plate"),
]


def normalise_control(command: str) -> str:
    """Upper-cased, single-spaced control line or realtime name; ValueError if not
    allowed, ``OutOfBounds`` if allowed but over a bound."""
    cmd = " ".join(command.strip().upper().split())
    if cmd in REALTIME and cmd != "STATUS":
        return cmd
    for pattern, _ in CONTROL_CODES:
        m = pattern.match(cmd)
        if not m:
            continue
        for axis_val in re.findall(r" [XYZ](-?\d+(?:\.\d+)?)", cmd):
            if abs(float(axis_val)) > JOG_MAX_MM and not cmd.startswith("G38.2"):
                raise OutOfBounds(f"move beyond {JOG_MAX_MM} mm: {command!r}")
        feed = re.search(r" F(\d+)", cmd)
        if cmd.startswith("G38.2"):
            depth = re.search(r" Z-(\d+(?:\.\d+)?)", cmd)
            if depth and float(depth.group(1)) > PROBE_MAX_MM:
                raise OutOfBounds(f"probe deeper than {PROBE_MAX_MM} mm: {command!r}")
            if feed and int(feed.group(1)) > PROBE_FEED_MAX:
                raise OutOfBounds(f"probe feed above {PROBE_FEED_MAX}: {command!r}")
        elif feed and int(feed.group(1)) > FEED_MAX:
            raise OutOfBounds(f"feedrate above {FEED_MAX}: {command!r}")
        if cmd.startswith("M3"):
            rpm = int(cmd.split("S")[1])
            if rpm > SPINDLE_MAX_RPM:
                raise OutOfBounds(f"spindle above {SPINDLE_MAX_RPM} rpm: {command!r}")
        return cmd
    raise ValueError(f"not an allowed GRBL control: {command!r}")


# What a person may still send while a cut holds the port: the hold, the resume and
# the spindle; motion is the cut's.
JOB_ALLOWS = re.compile(r"^(HOLD|RESUME|M5|M3 S\d+)$")


# --- a streamed job: what a file may carry, and how long a line may take -------------------

# The M codes a GRBL controller takes (Grbl 1.1's, and Grbl_ESP32's outputs). Any other
# in a file kept for a router is a printer's: the controller answers it error:20, and
# the cut stops at that line.
M_CODES = {0, 1, 2, 3, 4, 5, 7, 8, 9, 30, 56, 62, 63, 67}
# Longest a dwell may ask, in GRBL's unit, seconds: Marlin counts G4 P in milliseconds,
# so a printer's half-second pause is eight minutes on a router.
DWELL_MAX_S = 60.0
CODE_RE = re.compile(r"^([GM])0*(\d+)(?:\.\d+)?$")
DWELL_P_RE = re.compile(r"\bP(\d+(?:\.\d+)?)")
SPINDLE_CODES = ("M3", "M4")
SPINDLE_ARG_RE = re.compile(r"S(\d+(?:\.\d+)?)")


def _objections(n: int, cmd: str, code: str) -> List[str]:
    """Why a line of a router's file asks more of the spindle than the bound, or is
    not GRBL's, if it does or is not."""
    if code in SPINDLE_CODES:
        m = SPINDLE_ARG_RE.search(cmd[len(code) :])
        if m and float(m.group(1)) > SPINDLE_MAX_RPM:
            return [f"line {n}: {code} asks for {m.group(1)} rpm, above {SPINDLE_MAX_RPM}"]
    m = CODE_RE.match(code)
    if m is None:
        return []
    letter, number = m.group(1), int(m.group(2))
    if letter == "M" and number not in M_CODES:
        return [
            f"line {n}: {code} is not a GRBL code: the controller answers error:20 and the cut stops there"
        ]
    if letter == "G" and number == 29:
        return [f"line {n}: {code} is a printer's bed probe, not a GRBL code"]
    if letter == "G" and number == 4:
        p = DWELL_P_RE.search(cmd[len(code) :])
        if p and float(p.group(1)) > DWELL_MAX_S:
            return [
                f"line {n}: {code} P{p.group(1)} dwells {p.group(1)} s on GRBL, whose P is "
                "seconds; a printer's file counts it in milliseconds"
            ]
    return []


def check_gcode(text: str) -> Tuple[int, List[str]]:
    """A router's file, checked in GRBL's terms (``gcode.check_file``): what every
    dialect refuses, a spindle over the bound, a code GRBL does not take, a printer's
    bed probe, and a dwell over a minute in GRBL's unit."""
    return gcode.check_file(text, _objections)


# A move is answered when it is queued, and the queue is fifteen moves deep: a
# roughing pass of long slow moves holds the fifteenth's `ok` for as long as the
# fourteen before it take. A poll meanwhile goes round the queue (the realtime `?`).
JOB_MOVE_TIMEOUT_S = 900.0
JOB_LINE_TIMEOUT_S = 30.0
MOVE_CODES = {"G0", "G1", "G2", "G3", "G38.2", "G38.3", "G38.4", "G38.5", "G4", "$H"}
# The lines that take a block of the planner: a sender counts its room for these.
PLANNED = {"G0", "G00", "G1", "G01", "G2", "G02", "G3", "G03", "G4", "G53"}
# The blocks an idle controller's planner holds, the smallest Grbl builds with: what a
# sender may queue before the next report says how many are free.
PLANNER_BLOCKS = 15


# A move written without a space before its first word (`G1X10`), as a post may.
UNSPACED_MOVE_RE = re.compile(r"^G0?[0-3](?![0-9.])")


def line_timeout(cmd: str) -> float:
    code = cmd.split(" ", 1)[0] if cmd else ""
    moves = code in MOVE_CODES or UNSPACED_MOVE_RE.match(code) is not None
    return JOB_MOVE_TIMEOUT_S if moves else JOB_LINE_TIMEOUT_S


def busy(status: dict) -> bool:
    """Whether the report says the controller still has a job in it: running, homing,
    jogging, or held; idle, in alarm and the rest are not."""
    return STATE_WORDS.get(status["machine_state"]) in ("running", "hold")


class PlannerRoom:
    """The planner's room as a streamed job counts it: what the controller's last
    status report said (``Bf:``, blocks free), counted down a line at a time between
    reports. A sender that counts the planner's blocks never blocks the port on a
    full one, so a hold and a poll go through meanwhile. None when the controller
    does not say (grbl 1.1 reports it only when $10 asks), and the line's ``ok`` is
    the flow control then, as a printer's is."""

    def __init__(self) -> None:
        self.free: Optional[int] = None
        self.known = False

    def wait(self, link: GcodeLink, cmd: str, abandoned: Callable[[], bool]) -> bool:
        """Wait, with the link free, until the planner has room for ``cmd``; False
        when ``abandoned()`` says the job was paused or stopped meanwhile, or a move's
        time ran out."""
        if cmd.split(" ", 1)[0] not in PLANNED:
            return True
        if not self.known or (self.free is not None and self.free <= 1):
            end = time.monotonic() + JOB_MOVE_TIMEOUT_S
            while True:
                try:
                    status, _lines = report(link, wait=1.0)
                except (LinkBusy, ToolchainError):
                    status = None
                if status is not None:
                    self.known = True
                    buffer = status["buffer"]
                    if buffer:
                        self.free = buffer["planner"]
                    elif status["machine_state"] == "Idle":
                        self.free = PLANNER_BLOCKS  # idle: the whole planner is free
                    else:
                        self.free = None  # busy and not saying: the `ok` is the flow control
                    if self.free is None or self.free >= 1:
                        break
                if abandoned() or time.monotonic() > end:
                    return False
                time.sleep(0.05)
        if self.free is not None:
            self.free -= 1
        return True


def await_idle(link: GcodeLink, abandoned: Callable[[], bool]) -> None:
    """Poll the controller until it is idle, in alarm or offline, or ``abandoned()``
    says the job was cancelled, or a move's time runs out; a held controller is
    waited for. A cut's last line is answered when it is queued, not when it is done."""
    end = time.monotonic() + JOB_MOVE_TIMEOUT_S
    while time.monotonic() < end and not abandoned():
        try:
            status, _lines = report(link, wait=1.0)
        except LinkBusy:
            time.sleep(0.2)
            continue
        if not busy(status):
            return
        time.sleep(0.3)


# --- the simulated controller ---------------------------------------------------------

# Ports the simulated engine answers as a router rather than as a printer.
SIMULATED_PORTS_ENV = "APOTHECARY_SIMULATED_ROUTER"


def simulated_ports() -> List[str]:
    return [p.strip() for p in os.environ.get(SIMULATED_PORTS_ENV, "").split(",") if p.strip()]


class SimulatedRouter:
    """A pretend Grbl_ESP32 behind the transport slot: no port, no hardware.

    Answers ``$I``, ``?``, ``$G``, ``$$``, ``$#``, homing, unlocking, jogs and
    moves, the spindle, work zero and a probe, and the realtime characters. Moves
    and dwells go into a planner queue fifteen deep, as Grbl's does: a line is
    answered ``ok`` once queued, the queue runs in its own time (each move the
    time its distance and feed say), and a line that finds the queue full waits
    for room, as a sender counting characters would. Homing answers when it is
    done, as Grbl's does. Its machine coordinates are negative from the home
    corner at the back right and the top of Z, as a Grbl machine homed to its
    maximum switches has them, so the tool stands in the working area at
    ``mpos + travel``. It starts idle with the tool over the middle of the
    table, as the part draws it; ``APOTHECARY_SIMULATED_ROUTER_STATE=alarm``
    starts it as a real one powers up with homing enabled, in alarm until
    homed. Any other line gets ``ok``.
    """

    FIRMWARE = "1.3a"
    BUILD = "20230715"
    MACHINE_NAME = "Apothecary simulated router"
    TRAVEL = {"x": 400.0, "y": 600.0, "z": 80.0}
    RAPID = 4000.0  # mm/min, the maker's figure for X and Y
    PLATE = 20.0  # mm under the tool, wherever it stands: what a probe touches
    PULL_OFF = 3.0  # mm back from the switches after homing
    PLANNER = PLANNER_BLOCKS  # blocks the queue holds before a line waits for room
    REALTIME_BYTES = tuple(b[0] for b in REALTIME.values())
    QUEUED = PLANNED

    def __init__(self, port: str, baud: int):
        self.port, self.baud = port, baud
        self._pending = b""
        self._lock = threading.Lock()
        starts = os.environ.get("APOTHECARY_SIMULATED_ROUTER_STATE", "idle").strip().lower()
        self.state = "Alarm" if starts == "alarm" else "Idle"
        self.alarm: Optional[int] = None
        self.homed = starts != "alarm"
        # Powered up: the banner, and in alarm the hint a real one prints with it.
        if starts == "alarm":
            self._pending = (
                f"Grbl {self.FIRMWARE} ['$' for help]\n[MSG:'$H'|'$X' to unlock]\n".encode()
            )
        # Where the tool stands, in machine coordinates: the middle of the table,
        # 40 mm up, as the part's defaults draw it.
        self.pos = {"x": -200.0, "y": -300.0, "z": -40.0}
        self.wco = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.relative = False
        self.spindle_on = False
        self.s = 0.0
        self.f = 0.0
        self.feed_override = 100
        # The planner: blocks waiting to run, each a target and a feed (a move) or a
        # length of time (a dwell), and the one running: its start, its end, when it
        # began, how long it takes, and what it is (a move, a jog, homing, a dwell).
        self._queue: List[tuple] = []
        self._current: Optional[Tuple[dict, dict, float, float, str]] = None
        self._held_at: Optional[float] = None  # the fraction of the current block done when held
        # Every block run, in work coordinates: where it began and ended, at what feed,
        # and whether it was a rapid. What a cut did, for apothecary.cam.measure.
        self.trace: List[dict] = []
        # Multiplies every block's time: 1 is real time, 0 skips them.
        self.time_scale = float(os.environ.get("APOTHECARY_SIMULATED_SPEED", "1"))
        self.probe: Optional[dict] = None
        self.settings = {
            0: 10, 1: 255, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 10: 1, 11: 0.010, 12: 0.002,
            13: 0, 20: 1, 21: 0, 22: 1, 23: 3, 24: 200.000, 25: 2000.000, 26: 250,
            27: 3.000, 30: 24000, 31: 0, 32: 0, 100: 800.000, 101: 800.000, 102: 800.000,
            110: 4000.000, 111: 4000.000, 112: 2000.000, 120: 200.000, 121: 200.000,
            122: 100.000, 130: 400.000, 131: 600.000, 132: 80.000,
        }  # fmt: skip

    # -- the planner, as time passes -----------------------------------------------------
    def _settle(self) -> None:
        """Run the queue up to now: finish the blocks whose time has passed, start the next."""
        if self._held_at is not None:
            return
        while True:
            if self._current is None:
                if not self._queue:
                    if self.state in ("Run", "Jog", "Home"):
                        self.state = "Idle"
                    return
                target, feed, kind = self._queue.pop(0)
                start = dict(self.pos)
                if kind == "dwell":
                    length = feed * self.time_scale  # a dwell's "feed" is its seconds
                else:
                    dist = sum((target[k] - start[k]) ** 2 for k in "xyz") ** 0.5
                    length = (dist / max(feed, 1.0)) * 60.0 * self.time_scale
                self._current = (start, dict(target), time.monotonic(), length, kind)
                self.state = {"jog": "Jog", "home": "Home"}.get(kind, "Run")
            start, end, since, length, kind = self._current
            if time.monotonic() - since < length:
                return
            self.pos = dict(end)
            self._current = None
            if kind in ("move", "rapid"):
                self.trace.append(
                    {
                        "start": {k: round(start[k] - self.wco[k], 3) for k in "xyz"},
                        "end": {k: round(end[k] - self.wco[k], 3) for k in "xyz"},
                        "rapid": kind == "rapid",
                    }
                )
            if kind == "home":
                self.homed = True
                self.alarm = None

    def _where(self) -> dict:
        if self._current is None:
            return dict(self.pos)
        start, end, since, length, _ = self._current
        done = self._held_at if self._held_at is not None else self._fraction_done()
        return {k: round(start[k] + (end[k] - start[k]) * done, 3) for k in "xyz"}

    def _end_of_queue(self) -> dict:
        """Where the tool will be once every queued block has run."""
        if self._queue:
            return dict(self._queue[-1][0])
        return dict(self._current[1]) if self._current is not None else dict(self.pos)

    def _enqueue(self, target: dict, feed: float, kind: str = "move") -> None:
        self._queue.append((dict(target), feed, kind))
        self._settle()

    def _target(self, args: Dict[str, str], relative: bool) -> dict:
        here = self._end_of_queue()
        target = dict(here)
        for axis in "xyz":
            if axis.upper() in args:
                v = float(args[axis.upper()])
                target[axis] = (here[axis] + v) if relative else (v + self.wco[axis])
        return target

    def _busy(self) -> bool:
        self._settle()
        return self._current is not None or bool(self._queue)

    # -- the realtime characters ------------------------------------------------------
    def _realtime(self, byte: int) -> None:
        self._settle()
        if byte == ord("?"):
            self._pending += (self._status() + "\n").encode()
        elif byte == ord("!"):
            if self.state in ("Run", "Jog", "Home", "Idle") and self._held_at is None:
                self._held_at = self._fraction_done() if self._current is not None else None
                self.state = "Hold"
        elif byte == ord("~"):
            if self.state == "Hold":
                if self._current is not None and self._held_at is not None:
                    start, end, _since, length, kind = self._current
                    left = length * (1.0 - self._held_at)
                    self._current = (self._where(), end, time.monotonic(), left, kind)
                    self._held_at = None
                    self.state = {"jog": "Jog", "home": "Home"}.get(kind, "Run")
                else:
                    self._held_at = None
                    self.state = "Idle" if not self._queue else "Run"
        elif byte == 0x18:
            moving = self._current is not None and self._held_at is None
            self.pos = self._where()
            self._queue.clear()
            self._current, self._held_at = None, None
            self.spindle_on, self.s = False, 0.0
            if moving:
                self.state, self.alarm, self.homed = "Alarm", 3, False
                self._pending += b"ALARM:3\n"
            elif self.state != "Alarm":
                self.state = "Idle"
            self._pending += f"\r\nGrbl {self.FIRMWARE} ['$' for help]\n".encode()
            if self.state == "Alarm":
                self._pending += b"[MSG:'$H'|'$X' to unlock]\n"
        elif byte == 0x85:
            if self.state == "Jog":
                self.pos = self._where()
                self._queue.clear()
                self._current, self.state = None, "Idle"

    def _fraction_done(self) -> float:
        start, end, since, length, _ = self._current  # type: ignore[misc]
        return 1.0 if length <= 0 else min(1.0, (time.monotonic() - since) / length)

    def _status(self) -> str:
        where = self._where()
        mpos = ",".join(f"{where[k]:.3f}" for k in "xyz")
        state = self.state
        if state == "Hold":
            state = (
                "Hold:1" if (self._current is not None and self._held_at is not None) else "Hold:0"
            )
        rpm = self.s if self.spindle_on else 0.0
        feed = self.f if self._current is not None and self._current[4] == "move" else 0.0
        fields = [state, f"MPos:{mpos}", f"FS:{feed:.0f},{rpm:.0f}"]
        if self._current is not None or self._queue:
            fields.append(f"Bf:{self.PLANNER - len(self._queue)},127")
        fields.append("WCO:" + ",".join(f"{self.wco[k]:.3f}" for k in "xyz"))
        fields.append(f"Ov:{self.feed_override},100,100")
        if self.spindle_on:
            fields.append("A:S")
        return "<" + "|".join(fields) + ">"

    # -- lines ----------------------------------------------------------------------------
    def _reply(self, cmd: str) -> List[str]:
        """The reply lines to one line; ``[]`` for homing, which answers when done."""
        self._settle()
        upper = cmd.upper()
        if upper == "$I":
            return [
                f"[VER:{self.FIRMWARE}.{self.BUILD}:]",
                "[OPT:VNMPH,35,1024,3]",
                f"[MSG:Using machine:{self.MACHINE_NAME}]",
                "ok",
            ]
        if upper == "$$":
            return [f"${k}={v}" for k, v in sorted(self.settings.items())] + ["ok"]
        if upper == "$#":
            out = ["[G54:" + ",".join(f"{self.wco[k]:.3f}" for k in "xyz") + "]"]
            out += [f"[G5{n}:0.000,0.000,0.000]" for n in range(5, 10)]
            out += ["[G28:0.000,0.000,0.000]", "[G30:0.000,0.000,0.000]", "[G92:0.000,0.000,0.000]"]
            out += ["[TLO:0.000]"]
            p = self.probe or {"x": 0.0, "y": 0.0, "z": 0.0, "touched": False}
            out.append(f"[PRB:{p['x']:.3f},{p['y']:.3f},{p['z']:.3f}:{1 if p['touched'] else 0}]")
            return out + ["ok"]
        if upper == "$G":
            return [
                f"[GC:G{'1' if self.f else '0'} G54 G17 G21 {'G91' if self.relative else 'G90'} G94 "
                f"{'M3' if self.spindle_on else 'M5'} M9 T0 F{self.f:.0f} S{self.s:.0f}]",
                "ok",
            ]
        if upper == "$N":
            return ["$N0=", "$N1=", "ok"]
        if self.state == "Alarm" and not upper.startswith(("$X", "$H", "$", "G4")):
            return ["error:9"]
        if upper.startswith("$H"):
            if self._busy():
                return ["error:8"]  # a $ command needs the machine idle
            home = {"x": -self.PULL_OFF, "y": -self.PULL_OFF, "z": -self.PULL_OFF}
            self.alarm = None
            self._enqueue(home, self.RAPID / 2, "home")
            return []  # ok once it is done: _answer waits
        if upper == "$X":
            if self.state == "Alarm":
                self.state, self.alarm = "Idle", None
                return ["[MSG:Caution: Unlocked]", "ok"]
            return ["ok"]
        if upper.startswith("$J="):
            if self.state not in ("Idle", "Jog"):
                return ["error:8"]
            args = self._args(upper[3:])
            target = self._target(args, "G91" in upper)
            if any(target[k] > 0 or target[k] < -self.TRAVEL[k] for k in "xyz"):
                return ["error:15"]
            self._enqueue(target, float(args.get("F", self.RAPID)), "jog")
            return ["ok"]
        if upper.startswith("$"):
            m = SETTING_RE.match(upper)
            if m:
                self.settings[int(m.group(1))] = float(m.group(2))
                return ["ok"]
            return ["error:3"]
        parts = upper.split()
        code = parts[0] if parts else ""
        args = self._args(upper)
        if code == "G90":
            self.relative = False
        elif code == "G91":
            self.relative = True
        elif code in ("G0", "G1", "G00", "G01", "G2", "G3", "G02", "G03"):
            if "F" in args:
                self.f = float(args["F"])
            if code not in ("G0", "G00") and not self.f:
                return ["error:22"]
            # A line that only sets modes (G1 F800) moves nothing.
            if any(a in args for a in "XYZ"):
                target = self._target(args, self.relative)
                if self.settings.get(20) and any(
                    target[k] > 0.001 or target[k] < -self.TRAVEL[k] - 0.001 for k in "xyz"
                ):
                    self.state, self.alarm = "Alarm", 2
                    # The line is neither accepted nor refused: the controller alarms,
                    # and says it wants a reset.
                    return ["ALARM:2", "[MSG:Reset to continue]"]
                rapid = code in ("G0", "G00")
                feed = self.RAPID if rapid else self.f * self.feed_override / 100
                self._enqueue(target, feed, "rapid" if rapid else "move")
        elif code == "G53":
            # A rapid in machine coordinates, whatever the work offset: G53 G0 Z0 is the
            # top of Z travel, G53 G0 X Y a table map's point. Past the travel it alarms
            # as any move does.
            target = self._end_of_queue()
            for axis in "xyz":
                if axis.upper() in args:
                    target[axis] = float(args[axis.upper()])
            if self.settings.get(20) and any(
                target[k] > 0.001 or target[k] < -self.TRAVEL[k] - 0.001 for k in "xyz"
            ):
                self.state, self.alarm = "Alarm", 2
                return ["ALARM:2", "[MSG:Reset to continue]"]
            self._enqueue(target, self.RAPID, "rapid")
        elif code == "G4":
            secs = float(args.get("P", 0)) or 0.0
            self._enqueue(self._end_of_queue(), min(2.0, secs), "dwell")
        elif code in ("M3", "M4"):
            if "S" in args:
                self.s = float(args["S"])
            self.spindle_on = self.s > 0
        elif code == "M5":
            self.spindle_on = False
        elif code == "G10" and args.get("L") == "20":
            here = self._end_of_queue()
            for axis in "xyz":
                if axis.upper() in args:
                    self.wco[axis] = round(here[axis] - float(args[axis.upper()]), 3)
        elif code == "G38.2":
            # The plate is PLATE mm below where the tool stands, or the move ends short.
            here = self._end_of_queue()
            depth = float(args.get("Z", 0))
            plate = here["z"] - self.PLATE
            touched = here["z"] + depth <= plate
            z = plate if touched else here["z"] + depth
            self.pos = {**here, "z": z}
            self._queue.clear()
            self._current = None
            self.probe = {"x": here["x"], "y": here["y"], "z": z, "touched": touched}
            if not touched:
                self.state, self.alarm = "Alarm", 5
                return [f"[PRB:{here['x']:.3f},{here['y']:.3f},{z:.3f}:0]", "ALARM:5"]
            return [f"[PRB:{here['x']:.3f},{here['y']:.3f},{z:.3f}:1]", "ok"]
        elif code in ("M2", "M30"):
            self.spindle_on, self.f = False, 0.0
        elif code in (
            "M7",
            "M8",
            "M9",
            "G17",
            "G20",
            "G21",
            "G54",
            "G94",
            "G40",
            "G49",
            "M0",
            "M1",
        ):
            pass
        elif code.startswith(("S", "F")):
            if code.startswith("S"):
                self.s = float(code[1:] or 0)
            else:
                self.f = float(code[1:] or 0)
        elif code.startswith("M"):
            return ["error:20"]  # a tool change, M115, M105: not this dialect's
        return ["ok"]

    def _answer(self, cmd: str) -> None:
        """Reply to one line: wait for room in the planner as a counting sender would
        (the lock let go meanwhile, so a realtime character still gets through),
        and for homing to finish before its ``ok``."""
        code = cmd.upper().split()[0] if cmd.split() else ""
        while True:
            with self._lock:
                self._settle()
                if code not in self.QUEUED or len(self._queue) < self.PLANNER:
                    reply = self._reply(cmd)
                    if reply:
                        self._pending += "".join(ln + "\n" for ln in reply).encode()
                        return
                    break  # homing: ok when done
            time.sleep(0.005)
        while True:
            with self._lock:
                if not self._busy() or self.state in ("Alarm", "Hold"):
                    self._pending += b"ok\n"
                    return
            time.sleep(0.005)

    @staticmethod
    def _args(text: str) -> Dict[str, str]:
        return {m.group(1): m.group(2) for m in re.finditer(r"([A-Z])(-?\d+\.?\d*)", text)}

    # -- the transport ---------------------------------------------------------------
    def write(self, data: bytes) -> None:
        text = b""
        for byte in data:
            if byte in self.REALTIME_BYTES:
                with self._lock:
                    self._realtime(byte)
            else:
                text += bytes([byte])
        for cmd in text.decode("utf-8", "replace").split("\n"):
            if cmd.strip():
                self._answer(cmd.strip())

    def read(self, timeout: float) -> bytes:
        with self._lock:
            out, self._pending = self._pending, b""
        if not out:
            time.sleep(min(timeout, 0.02))
        return out

    def pulse_reset(self) -> None:
        with self._lock:
            self._realtime(0x18)

    def close(self) -> None:
        pass


# --- over a held link: identify, poll, control, query -------------------------------------


def identify_router(link: GcodeLink, reset: bool = False) -> PrinterInfo:
    """``$I`` over an open link; with ``reset`` the board is rebooted first for its
    banner. Raises ``ToolchainError`` if nothing GRBL answers."""
    if reset:
        link.reset()
    boot = list(link.unsolicited)
    lines = link.command("$I", timeout=8.0, origin="identify")
    return router_info_from(lines, link.baud, boot)


def report(
    link: GcodeLink, wait: Optional[float] = None, timeout: float = 3.0, origin: str = "poll"
) -> Tuple[dict, List[str]]:
    """One realtime status report, and every line read for it. ``origin`` tags it in
    the log: a poll's is hidden with the poll traffic, a person's query is kept."""
    lines = link.realtime(
        REALTIME["STATUS"], until=STATUS_RE, timeout=timeout, wait=wait, origin=origin
    )
    status = next((parse_status(ln) for ln in reversed(lines) if is_status_line(ln)), None)
    if status is None:
        raise ToolchainError(f"{link.port}: no status report for `?` within {timeout:.0f}s")
    return status, lines


def poll_router(link: GcodeLink, wait: Optional[float] = None) -> PrinterStatus:
    """The status report and the parser state in one exchange each."""
    raw: List[str] = []
    status, lines = report(link, wait=wait)
    raw += lines
    gc_lines = link.command("$G", wait=wait, timeout=5.0)
    raw += gc_lines
    parser = parse_parser_state(gc_lines)
    mstate = status["machine_state"]
    # The report says the controller is in alarm, not which: the link keeps the last
    # ALARM line it read. Out of alarm, that line is spent.
    if mstate == "Alarm":
        alarm = parse_alarm(raw) or parse_alarm([link.alarm] if link.alarm else [])
    else:
        alarm = None
        link.alarm = None
    return PrinterStatus(
        port=link.port,
        polled_at=datetime.now(timezone.utc),
        dialect=DIALECT,
        state=site_state(mstate),
        machine_state=mstate + (f":{status['substate']}" if status["substate"] is not None else ""),
        position=status["mpos"],
        work_position=status["wpos"],
        work_offset=status["wco"],
        spindle=Spindle(
            rpm=status["spindle_rpm"] or 0.0,
            target=parser["s"],
            on=parser["spindle_on"] or bool(status["spindle_rpm"]),
        ),
        feed=status["feed"],
        pins=list(status["pins"]),
        alarm=alarm,
        alarm_text=alarm_text(alarm),
        overrides=status["overrides"],
        raw=raw,
    )


def control_router(link: GcodeLink, command: str, timeout: float = 60.0) -> List[str]:
    """Send one allowlisted control line, or a realtime character. The reset is
    written at once, ahead of the link's queue; a hold and a resume too, since
    each is for a machine in motion."""
    cmd = normalise_control(command)
    if cmd in REALTIME:
        settle = 1.0 if cmd == EMERGENCY_STOP else 0.3
        return link.realtime(
            REALTIME[cmd], until=None, timeout=settle, label=cmd, now=True, origin="control"
        )
    return link.command(cmd, timeout=timeout, origin="control")


def query_router(link: GcodeLink, command: str, timeout: float = 15.0) -> List[str]:
    cmd = normalise_query(command)
    if cmd == "?":
        _status, lines = report(link, timeout=timeout, origin="query")
        return lines
    return link.command(cmd, timeout=timeout, origin="query")


# --- the table map: the router's bed reading, Z probed at a grid of points ----------------


def table_grid(travel: dict, rows: int, cols: int, inset: float) -> List[List[dict]]:
    """The points of a table map, in machine coordinates: ``rows`` by ``cols``, spread
    over the working area ``inset`` mm in from its edges. Machine coordinates run
    negative from the home corner at the back right, so the front-left point is the
    most negative in both axes; the rows run front to back and each left to right,
    as Marlin prints its mesh and ``mesh_stats`` names the corners. ValueError when
    the grid does not fit."""
    if rows < 2 or cols < 2:
        raise ValueError(f"a table map is at least two by two: {rows}x{cols}")
    if inset < 0 or 2 * inset >= travel["x"] or 2 * inset >= travel["y"]:
        raise ValueError(
            f"an inset of {inset} mm leaves no room on a {travel['x']}x{travel['y']} table"
        )
    xs = [-travel["x"] + inset + i * (travel["x"] - 2 * inset) / (cols - 1) for i in range(cols)]
    ys = [-travel["y"] + inset + j * (travel["y"] - 2 * inset) / (rows - 1) for j in range(rows)]
    return [[{"x": round(x, 3), "y": round(y, 3)} for x in xs] for y in ys]


def _machine_position(link: GcodeLink, reports: int = 12) -> dict:
    """Where the tool stands in machine coordinates, from the status report: a
    controller set to report the work position says the offset only every few
    reports, so a few are asked for."""
    for _ in range(reports):
        status, _lines = report(link, origin="control")
        if status["mpos"] is not None:
            return status["mpos"]
        time.sleep(0.2)
    raise ToolchainError(f"{link.port}: the status report never said the machine position")


def probe_table(
    link: GcodeLink,
    *,
    probe: bool = True,
    grid: Optional[TableGrid] = None,
    stage: Callable[..., None] = lambda word, points=None: None,
) -> BedReading:
    """The router's bed reading: its table mapped, Z probed with the touch plate at
    each point of ``grid`` (three by three, left out) over the working area.

    The working area is the controller's own word, its maximum travel (``$$``).
    The spindle is turned off and the machine homed, so machine coordinates mean
    the working area and the tool stands at the top of Z. Then, at each point from
    the front-left: a rapid there in machine coordinates (``G53 G0``, so a person's
    work zero is neither used nor moved), a probe down (``G38.2``) as far as the
    travel allows and no deeper than the dialect's bound, at the grid's feed, and
    the lift back to the top. A touch is read from the ``[PRB:...]`` line; a probe
    that does not touch within the move alarms the controller and ends the map
    there. The touches are the mesh, in machine coordinates, rows from the front;
    the controller's own word on the last touch (``$#``) is kept with the lines.
    ``stage`` is told each step and, while probing, the points done of the total.
    This dialect's ``Dialect.bed_reading``; a stored mesh (``probe=False``) it has
    none of, and ``devices.start_leveling`` refuses before the port.

    The probe's lead must close at every point: clipped to the table, or the
    plate's whole surface under the grid. A plate held at one point is the pad's
    Probe Z, not this.
    """
    if not probe:
        raise ValueError("a router keeps no mesh to read: its reading probes the table")
    grid = grid or TableGrid()
    lines: List[str] = []
    settings_lines = query_router(link, "$$")
    lines += settings_lines
    travel = travel_of(parse_settings(settings_lines))
    if travel is None:
        raise ToolchainError(f"{link.port}: the controller does not say its travel ($130-$132)")
    points = table_grid(travel, grid.rows, grid.cols, grid.inset)
    total = grid.rows * grid.cols
    feed = min(grid.feed, PROBE_FEED_MAX)
    stage("homing")
    lines += control_router(link, "M5", timeout=10.0)
    lines += control_router(link, "$H", timeout=120.0)
    top = _machine_position(link)["z"]
    # From the top of Z the probe may go the rest of the travel, and no further than the
    # dialect lets a probe go.
    depth = min(PROBE_MAX_MM, top + travel["z"])
    if depth <= 0:
        raise ToolchainError(
            f"{link.port}: no travel under the tool to probe (Z {top} of {travel['z']})"
        )
    probe_line = f"G38.2 Z-{depth:.2f} F{feed}"
    probe_timeout = depth / feed * 60.0 * 2 + 30.0
    lines += control_router(link, "G91", timeout=10.0)  # a probe's Z is a distance
    mesh: List[List[float]] = []
    try:
        done = 0
        for row in points:
            heights: List[float] = []
            for point in row:
                stage("probing", {"done": done, "total": total})
                lines += control_router(
                    link, f"G53 G0 X{point['x']:.3f} Y{point['y']:.3f}", timeout=120.0
                )
                said = control_router(link, probe_line, timeout=probe_timeout)
                lines += said
                touch = parse_probe(said)
                if touch is None or not touch["touched"]:
                    raise ToolchainError(
                        f"{link.port}: no touch at X{point['x']} Y{point['y']}: {said[-1] if said else 'nothing said'}"
                    )
                heights.append(round(touch["z"], 3))
                lines += control_router(link, f"G53 G0 Z{top:.3f}", timeout=120.0)
                done += 1
            mesh.append(heights)
        stage("reading", {"done": done, "total": total})
        lines += query_router(link, "$#")
    finally:
        try:
            lines += control_router(link, "G90", timeout=10.0)
        except (ToolchainError, LinkBusy):
            pass  # the controller in alarm keeps its parser; the alarm is what is said
    return BedReading(
        method="G38.2",
        mesh=mesh,
        stats=mesh_stats(mesh),
        area={
            "min": {"x": grid.inset, "y": grid.inset},
            "max": {"x": travel["x"] - grid.inset, "y": travel["y"] - grid.inset},
        },
        lines=lines[-400:],
    )


def alarm_text(code: Optional[int]) -> Optional[str]:
    if code is None:
        return None
    return ALARMS.get(code, f"alarm {code}")


def explain(line: str) -> Optional[str]:
    """The words for a controller's ``error:N`` or ``ALARM:N``, kept beside the line
    in the port's log and said in a refusal; None for any other line."""
    m = OBJECTION_RE.match(line.strip())
    if not m:
        return None
    code = int(m.group(2))
    if m.group(1) == "error":
        return ERRORS.get(code, f"error {code}")
    return alarm_text(code)
