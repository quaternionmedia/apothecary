"""What a print shows that calipers do not: the faults a person sees on a piece, how
bad each is, and which slicer setting a printer's next slices change for it.

A **fault** is one way a print goes wrong that a person sees (``FAULTS``): stringing,
a first layer that does not hold, corners lifting, too little or too much plastic,
overhangs sagging, layers splitting, ripples beside corners, a layer shifted. Each
names the settings that govern it, in the order they are tried, each with the
direction that takes the fault out, a step and its limits: its **levers**. A fault a
slicer cannot take out (a shifted layer is a belt or a collision) has none, and says
what to look at instead.

A **look** is a piece read by eye: each fault's severity (``SEVERITY``, none to bad),
kept as the next entry of the printer's tuning for its filament and process
(``apothecary.slicer.tuning``). It proposes **one** setting's change, for the worst
fault it saw, so the next look can say what that change did. ``next_step`` decides it
from the looks before:

- a fault seen and never stepped: its first lever that can move, one step;
- a fault stepped, and the piece read now sliced with that step: less than when
  it was stepped, the same lever again; the same or worse, that lever put back where
  it was and the next lever stepped in the same look -- going back to a value
  already printed with adds no second unknown;
- a piece sliced before the last look's change was taken: no change at all -- it
  cannot say what that change did, and a second change before it is read would leave
  two unknowns in the next piece;
- a fault gone: nothing; every lever put back or at its limit: nothing, and what to
  look at instead is said. A step never goes against its lever: a value already past
  its limit is left where it is, and the next lever tried.

A temperature lever stays inside the filament's own printable range as its profile
states it (``nozzle_temperature_range_low`` .. ``_high``) where the slice recorded it.

Pure: no state, no slicer. ``apothecary.slicer.tuning`` keeps what this decides.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

# How bad a fault is, as a person reads a piece.
SEVERITY: Dict[int, str] = {
    0: "none",
    1: "slight: seen up close",
    2: "clear: seen at arm's length",
    3: "bad: the piece is not usable",
}


@dataclass(frozen=True)
class Lever:
    """One OrcaSlicer setting that governs a fault: the step that takes the fault out
    (signed), and the setting's limits."""

    key: str
    kind: str  # the profile that holds it: "filament", "process" or "machine"
    unit: str  # "°C", "mm", "mm/s", "mm³/s", "s", "%", "layers", "" (a ratio)
    step: float
    least: float
    most: float
    why: str  # how it governs the fault, in words
    # The setting whose value stands where this one says nil: a filament's retraction
    # overrides the machine's.
    falls_back_to: Optional[str] = None
    # The profile's own range a value stays inside, where the slice recorded it.
    within: Optional[Tuple[str, str]] = None

    def clamp(self, value: float, used: Mapping[str, Optional[float]]) -> float:
        low, high = self.least, self.most
        if self.within:
            lo, hi = used.get(self.within[0]), used.get(self.within[1])
            if lo is not None:
                low = max(low, lo)
            if hi is not None:
                high = min(high, hi)
        return min(max(value, low), high)

    def step_from(self, was: float, used: Mapping[str, Optional[float]]) -> Optional[float]:
        """One step from ``was`` the lever's way, inside its limits; None where it cannot
        go that way: at its limit, or past it already, where clamping would step back."""
        new = self.clamp(was + self.step, used)
        return new if (new - was) / self.step > 1e-9 else None


NOZZLE_RANGE = ("nozzle_temperature_range_low", "nozzle_temperature_range_high")


def _hotter(why: str, step: float = 5.0, key: str = "nozzle_temperature") -> Lever:
    return Lever(key, "filament", "°C", step, 170, 300, why, within=NOZZLE_RANGE)


@dataclass(frozen=True)
class Fault:
    id: str
    name: str
    looks_like: str  # what a person sees
    levers: Tuple[Lever, ...]
    otherwise: str  # what to look at when no lever takes it out


FAULTS: Tuple[Fault, ...] = (
    Fault(
        "stringing",
        "Stringing",
        "fine threads or wisps between parts of a layer, where the nozzle travelled",
        (
            Lever(
                "filament_retraction_length",
                "filament",
                "mm",
                0.5,
                0.0,
                8.0,
                "more filament drawn back before a travel, so less oozes on the way",
                falls_back_to="retraction_length",
            ),
            _hotter("cooler plastic is thicker and oozes less", step=-5.0),
            Lever(
                "travel_speed",
                "process",
                "mm/s",
                20.0,
                80.0,
                250.0,
                "a quicker travel leaves less time to ooze",
            ),
        ),
        "wet filament strings whatever the settings: dry the spool",
    ),
    Fault(
        "first_layer",
        "First layer does not hold",
        "the first layer peels, lines do not stick to each other or the bed, or the "
        "piece comes off the bed during the print",
        (
            Lever(
                "cool_plate_temp_initial_layer",
                "filament",
                "°C",
                5.0,
                0.0,
                110.0,
                "a warmer bed holds the first layer",
            ),
            _hotter(
                "a hotter first layer flows into the bed's surface",
                key="nozzle_temperature_initial_layer",
            ),
        ),
        "the nozzle's height over the bed (the Z offset on the printer's screen, the "
        "bench checklist's F) and a clean bed: neither is a slicer's",
    ),
    Fault(
        "warping",
        "Corners lift",
        "the corners or ends of the piece curl up off the bed as it grows",
        (
            Lever(
                "cool_plate_temp",
                "filament",
                "°C",
                5.0,
                0.0,
                110.0,
                "a warmer bed keeps the lower layers from shrinking as they cool",
            ),
            Lever(
                "brim_width",
                "process",
                "mm",
                3.0,
                0.0,
                10.0,
                "a brim holds the corners down",
            ),
            Lever(
                "close_fan_the_first_x_layers",
                "filament",
                "layers",
                1.0,
                1.0,
                5.0,
                "the fan off for more of the first layers, so they cool slower",
            ),
        ),
        "a draught over the printer, or a cold room: an enclosure",
    ),
    Fault(
        "under_extrusion",
        "Too little plastic",
        "gaps between lines, thin or weak walls, holes in the top surface",
        (
            Lever(
                "filament_flow_ratio",
                "filament",
                "",
                0.02,
                0.85,
                1.15,
                "more plastic for the same line",
            ),
            _hotter("hotter plastic flows faster through the nozzle"),
            Lever(
                "filament_max_volumetric_speed",
                "filament",
                "mm³/s",
                -2.0,
                4.0,
                30.0,
                "the slicer slows moves that would ask more plastic than the hot end melts",
            ),
        ),
        "a partial clog, a slipping extruder gear or the e-steps (bench checklist F: "
        "100 mm of filament extruded and measured)",
    ),
    Fault(
        "over_extrusion",
        "Too much plastic",
        "blobs, a rough or ridged top, walls bulging past where they should be",
        (
            Lever(
                "filament_flow_ratio",
                "filament",
                "",
                -0.02,
                0.85,
                1.15,
                "less plastic for the same line",
            ),
            _hotter("cooler plastic spreads less", step=-5.0),
        ),
        "the e-steps (bench checklist F) and the filament's real diameter",
    ),
    Fault(
        "overhangs",
        "Overhangs sag",
        "overhangs and bridges droop, or their edges curl up",
        (
            _hotter("cooler plastic sets sooner under an overhang", step=-5.0),
            Lever(
                "slow_down_layer_time",
                "filament",
                "s",
                2.0,
                2.0,
                20.0,
                "each small layer given longer to cool before the next",
            ),
        ),
        "the part's fan and its duct; or supports, the part's own",
    ),
    Fault(
        "weak_layers",
        "Layers split",
        "layers separate along a line, or the piece breaks between layers under a little force",
        (
            _hotter("hotter layers bond into the one below"),
            Lever(
                "fan_max_speed",
                "filament",
                "%",
                -10.0,
                30.0,
                100.0,
                "less cooling leaves each layer warm for the next",
            ),
        ),
        "a draught over the printer, or wet filament",
    ),
    Fault(
        "ringing",
        "Ripples beside corners",
        "faint waves on a wall just after a sharp corner or a hole",
        (
            Lever(
                "outer_wall_speed",
                "process",
                "mm/s",
                -10.0,
                15.0,
                120.0,
                "a slower outer wall shakes the printer less at each corner",
            ),
        ),
        "a loose belt or wheel, or the printer standing on something that sways",
    ),
    Fault(
        "layer_shift",
        "A layer shifted",
        "the piece is stepped sideways from one layer up: everything above is offset",
        (
            Lever(
                "travel_speed",
                "process",
                "mm/s",
                -30.0,
                80.0,
                250.0,
                "a slower travel skips no steps",
            ),
        ),
        "a belt's tension, a pulley's grub screw, the nozzle hitting a curled corner "
        "(see corners lift) or a driver running hot: a slicer cannot take a shift out",
    ),
)
BY_ID: Dict[str, Fault] = {f.id: f for f in FAULTS}
# Every setting a lever moves, and the profile values a lever reads: what a slice records.
LEVER_KEYS: Tuple[str, ...] = tuple(dict.fromkeys(lv.key for f in FAULTS for lv in f.levers))
READ_KEYS: Tuple[str, ...] = tuple(
    dict.fromkeys(
        [*LEVER_KEYS, *(lv.falls_back_to for f in FAULTS for lv in f.levers if lv.falls_back_to)]
        + list(NOZZLE_RANGE)
    )
)


def fault(fault_id: str) -> Fault:
    try:
        return BY_ID[fault_id]
    except KeyError:
        raise KeyError(
            f"no fault {fault_id!r}: there are {', '.join(f.id for f in FAULTS)}"
        ) from None


def lever(fault_id: str, key: str) -> Lever:
    for lv in fault(fault_id).levers:
        if lv.key == key:
            return lv
    raise KeyError(f"{fault_id} has no lever {key!r}")


def value_of(lv: Lever, used: Mapping[str, Optional[float]]) -> Optional[float]:
    """The lever's value as the slice used it: its own, else the one it falls back to."""
    v = used.get(lv.key)
    if v is None and lv.falls_back_to:
        v = used.get(lv.falls_back_to)
    return v


# ---- one look's step -----------------------------------------------------------------------


@dataclass(frozen=True)
class Stepped:
    """A change a look made for a fault: its lever, from what to what, and the fault's
    severity when it was made."""

    look: str
    fault: str
    key: str
    before: float
    after: float
    severity: int
    back: bool = False  # a lever put back where it was, not a step


@dataclass(frozen=True)
class Past:
    """A look before this one: what it saw, and what it applied."""

    id: str
    seen: Mapping[str, int]
    applied: Sequence[Stepped]


@dataclass(frozen=True)
class Move:
    fault: str
    key: str
    kind: str
    unit: str
    used: Optional[float]
    new: float
    back: bool
    why: str


@dataclass(frozen=True)
class Decision:
    moves: List[Move]
    said: List[str]


def _word(severity: int) -> str:
    return SEVERITY[severity].split(":")[0]


def _fmt(v: Optional[float], unit: str) -> str:
    if v is None:
        return "-"
    text = f"{round(v, 3):g}"
    return text + (f" {unit}" if unit and unit != "%" else ("%" if unit == "%" else ""))


def next_step(
    seen: Mapping[str, int], used: Mapping[str, Optional[float]], past: Sequence[Past]
) -> Decision:
    """The one fault this look changes a setting for, and the change: see the module's
    words. ``seen`` is this look's severities by fault, ``used`` what its slice used,
    ``past`` the looks before it, oldest first."""
    said: List[str] = []
    order = [f.id for f in FAULTS]
    worst = sorted((f for f, s in seen.items() if s > 0), key=lambda f: (-seen[f], order.index(f)))
    waiting = next((p for p in reversed(past) if p.applied), None)
    if waiting is not None:
        for st in waiting.applied:
            lv = lever(st.fault, st.key)
            now = value_of(lv, used)
            if now is None or abs(now - st.after) > 1e-6:
                return Decision(
                    [],
                    [
                        f"this piece was sliced with {st.key} {_fmt(now, lv.unit)}, not "
                        f"{_fmt(st.after, lv.unit)} as {waiting.id} set it: print one sliced "
                        "since, to see what that change did"
                    ],
                )
    if not worst:
        return Decision([], ["nothing seen: no change"])
    for fid in worst:
        f = fault(fid)
        stepped = [s for p in past for s in p.applied if s.fault == fid]
        ruled_out = {s.key for s in stepped if s.back}
        last = next((s for s in reversed(stepped) if not s.back), None)
        current: Optional[Lever] = None
        moves: List[Move] = []
        if last is not None and last.key not in ruled_out:
            lv = lever(fid, last.key)
            now = value_of(lv, used)
            sev = seen[fid]
            if sev < last.severity:
                current = lv
                said.append(
                    f"{f.name.lower()}: {_word(last.severity)} -> "
                    f"{_word(sev)} after {last.key} "
                    f"{_fmt(last.before, lv.unit)} -> {_fmt(last.after, lv.unit)}: it governs it"
                )
            else:
                moves.append(
                    Move(
                        fid,
                        lv.key,
                        lv.kind,
                        lv.unit,
                        now,
                        last.before,
                        True,
                        f"put back: {f.name.lower()} was {_word(last.severity)} "
                        f"and is {_word(sev)} after {last.key} "
                        f"{_fmt(last.before, lv.unit)} -> {_fmt(last.after, lv.unit)}, "
                        "so it does not govern it here",
                    )
                )
                ruled_out.add(lv.key)
        candidates = ([current] if current else []) + [
            lv for lv in f.levers if lv.key not in ruled_out and lv is not current
        ]
        for lv in candidates:
            # A lever put back in this same look stands at what it is put back to.
            was = next((m.new for m in moves if m.key == lv.key), value_of(lv, used))
            if was is None:
                said.append(f"{f.name.lower()}: {lv.key} is not in what the slice recorded")
                continue
            new = lv.step_from(was, used)
            if new is None:
                past = abs(lv.clamp(was, used) - was) > 1e-9
                said.append(
                    f"{f.name.lower()}: {lv.key} is {'past' if past else 'at'} its limit, "
                    f"{_fmt(was, lv.unit)}"
                )
                continue
            moves.append(
                Move(
                    fid,
                    lv.key,
                    lv.kind,
                    lv.unit,
                    was,
                    round(new, 4),
                    False,
                    f"{f.name} ({_word(seen[fid])}): {lv.why}",
                )
            )
            return Decision(moves, said)
        if moves:
            return Decision(moves, said + [f"{f.name.lower()}: no lever left; {f.otherwise}"])
        said.append(f"{f.name.lower()}: no lever left to try; {f.otherwise}")
    return Decision([], said)
