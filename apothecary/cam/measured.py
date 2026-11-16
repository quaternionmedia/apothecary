"""A router's correction, fed back from a piece it cut: measured by a person with
calipers, checked against what the toolpath was written to, and held for that
router's next toolpaths. The printer's is ``slicer/measured.py``.

A toolpath records what a person measures of the piece it cuts (``CutRecord.features``):
each named operation that was cut, inside (a pocket, a hole bored) or outside (an
outline, a disc), at its size as designed. The piece made for it is
``parts/router_emoji``, a 😮: its face a disc cut around from outside, its eyes and
its mouth holes bored inside. A measurement is checked before anything is kept: each
size is within ``WITHIN`` of the size designed, or it is not of that piece and is
refused, saying so.

What is fed back is the tool's allowance: what every offset adds to the tool's
diameter, since a tool that runs out, or bends, cuts wider than it is. An inside size
comes out over by what the tool cuts wider than its offsets took, an outside one under
by as much; a scale the steps per millimetre are off by moves both the same way, in
proportion to their size. Measured inside and out, the two are told apart: the tool's
share is fed back and the scale's is said and recorded, not applied, since it is the
controller's ``$100`` and ``$101``, which nothing here changes. Measured on one side
alone, the error is taken as the tool's. An allowance past ``MOST`` is refused: that
far off is the tool chosen, or the steps per millimetre.

The correction is the router's, and its tool's: it is kept per machine node in the
state folder (``corrections/<site>/<node>.json``, beside a printer's) with the tool's
diameter it was measured with and every measurement that made it, newest last. A
toolpath names the node its board is pinned to (the router's controller); the router
is the nearest node up that path that carries a status, as the polls find it. Every
later toolpath for that router with a tool of that diameter takes it (``applied``),
as an ``Allowance`` whose origin is ``measured`` and whose source names the
measurement; one with another tool takes none, and says so.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from .. import sites
from ..hierarchy import find_node_by_path
from ..state_folder import state_dir, write_whole
from .models import Allowance, CutRecord

SETTING = "tool_allowance"
# A size measured further than this share from the size designed is not that piece's.
WITHIN = 0.05
# Millimetres on the tool's diameter: further than this is not the tool's running out.
MOST = 0.5
NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,199}$")
EPS = 1e-6


class Refused(ValueError):
    """A measurement that is not kept, and why."""


class Measured(BaseModel):
    """One feature of the piece: its size as designed, and as measured."""

    name: str
    side: Literal["inside", "outside"]
    designed: float  # mm
    measured: float  # mm


class Measurement(BaseModel):
    """One piece measured: what was cut, what was measured, and what came of it."""

    at: datetime
    file_id: str  # the kept toolpath that cut the piece
    part: str
    tool: float  # the tool's diameter, mm
    sizes: List[Measured]
    used: float  # the allowance the measured toolpath was written with, mm
    correction: float  # the allowance after it, mm
    scale: Optional[float] = None  # the share every size is off by, where inside and out tell it


class Correction(BaseModel):
    """A router's allowance for one tool, and the measurements that made it, newest last."""

    site: str
    router: str  # the router's node in the site
    setting: str = SETTING
    tool: float  # the diameter of the tool it was measured with, mm
    value: float
    measurements: List[Measurement] = Field(default_factory=list)


def router_node(site: str, path: str) -> str:
    """The router ``path`` is part of in ``site``: ``path`` itself if it carries a
    status, else its nearest ancestor that does (the router above its controller);
    ``path`` where nothing up it does, or the site is not kept."""
    try:
        at = sites.store.get(site)
    except KeyError:
        return path
    parts = path.split(".")
    for depth in range(len(parts), 0, -1):
        candidate = ".".join(parts[:depth])
        node = find_node_by_path(at, candidate)
        if node is not None and node.status is not None:
            return candidate
    return path


def _kept_at(site: str, router: str) -> Path:
    if not NAME.match(site) or not NAME.match(router):
        raise Refused(f"no correction can be kept for {site!r}, {router!r}")
    return state_dir() / "corrections" / site / f"{router}.json"


def load(site: Optional[str], router: Optional[str]) -> Optional[Correction]:
    """The correction kept for the router ``router`` of ``site`` is part of, or None."""
    if not site or not router:
        return None
    try:
        path = _kept_at(site, router_node(site, router))
    except Refused:
        return None
    if not path.is_file():
        return None
    return Correction.model_validate_json(path.read_text(encoding="utf-8"))


def _split(
    record: CutRecord, measured: Dict[str, Optional[float]]
) -> Tuple[List[Measured], List[Measured]]:
    """The sizes measured, each checked against the feature it names: inside, outside."""
    features = {f.name: f for f in record.features}
    if not features:
        raise Refused(
            f"{record.part} names nothing to measure: cut parts/router_emoji, whose face, "
            "eyes and mouth are measured"
        )
    sizes = {name: value for name, value in measured.items() if value is not None}
    if not sizes:
        raise Refused(
            "measure one of " + ", ".join(features) + f": what {record.part} names to measure"
        )
    for name in sizes:
        if name not in features:
            raise Refused(
                f"{record.part} has no {name!r} to measure: it names " + ", ".join(features)
            )
    inside: List[Measured] = []
    outside: List[Measured] = []
    for name, feature in features.items():
        if name not in sizes:
            continue
        value = sizes[name]
        if not value > 0:
            raise Refused(f"{name} {value} mm is no size")
        if abs(value - feature.size) > WITHIN * feature.size:
            raise Refused(
                f"{name} {value:g} mm against {feature.size:g} mm designed is more than "
                f"{WITHIN:.0%} off: not this toolpath's piece, or measured across something "
                "else -- measure it again, or choose the file it was cut from"
            )
        one = Measured(name=name, side=feature.side, designed=feature.size, measured=value)
        (inside if feature.side == "inside" else outside).append(one)
    return inside, outside


def _mean(values: List[float]) -> float:
    return sum(values) / len(values)


def found(inside: List[Measured], outside: List[Measured]) -> Tuple[float, Optional[float]]:
    """What the sizes say: what the tool cuts wider than its offsets took (mm on its
    diameter), and the share every size is off by, where inside and out tell it."""
    if inside and outside:
        # Inside: error = tool + scale x size; outside: error = -tool + scale x size.
        e_in = _mean([m.measured - m.designed for m in inside])
        e_out = _mean([m.measured - m.designed for m in outside])
        s_in = _mean([m.designed for m in inside])
        s_out = _mean([m.designed for m in outside])
        scale = (e_in + e_out) / (s_in + s_out)
        return e_in - scale * s_in, scale
    if inside:
        return _mean([m.measured - m.designed for m in inside]), None
    return -_mean([m.measured - m.designed for m in outside]), None


def used_by(record: CutRecord) -> float:
    """The allowance a toolpath was written with; 0 where none."""
    return record.allowance.value if record.allowance else 0.0


def measure(record: CutRecord, measured: Dict[str, Optional[float]]) -> Correction:
    """``measured`` (a size for each feature measured, by its name) checked against
    ``record``'s features, and the allowance it makes kept for the router the toolpath
    was written for. ``Refused`` says why, and nothing is kept."""
    at = record.router
    if not at.site or not at.path:
        raise Refused(
            f"{record.name} was written for {at.name}, a router of no site: "
            "a correction is kept for a router standing in one"
        )
    inside, outside = _split(record, measured)
    tool, scale = found(inside, outside)
    used = used_by(record)
    correction = round(used + tool, 3)
    if abs(correction) > MOST:
        raise Refused(
            f"an allowance of {correction:+.3f} mm is past {MOST} mm: that far off is the "
            "tool chosen, or the steps per millimetre, which an allowance does not correct"
        )
    node = router_node(at.site, at.path)
    kept = load(at.site, node)
    if kept is None or abs(kept.tool - record.tool.diameter) > EPS:
        kept = Correction(site=at.site, router=node, tool=record.tool.diameter, value=0.0)
    kept.value = correction
    kept.measurements.append(
        Measurement(
            at=datetime.now(timezone.utc),
            file_id=record.file_id,
            part=record.part,
            tool=record.tool.diameter,
            sizes=inside + outside,
            used=used,
            correction=correction,
            scale=None if scale is None else round(scale, 6),
        )
    )
    write_whole(_kept_at(at.site, node), kept.model_dump_json(indent=2))
    return kept


def said(measurement: Measurement) -> str:
    """What a measurement found, in words: each size's error, the scale where it was
    told, and the allowance."""
    parts = [f"{m.name} {m.measured - m.designed:+.2f}" for m in measurement.sizes]
    scale = (
        ""
        if measurement.scale is None
        else f"; scale {measurement.scale:+.2%}, the steps per millimetre's, not applied"
    )
    return (
        f"{measurement.part} measured {', '.join(parts)} mm against what was designed{scale}; "
        f"{SETTING} {measurement.used:+.3f} -> {measurement.correction:+.3f} mm"
    )


def applied(
    site: Optional[str], router: Optional[str], tool: float
) -> Tuple[Optional[Allowance], Optional[str]]:
    """The allowance a toolpath for the router node ``router`` of ``site`` takes with a
    tool of ``tool`` mm, and what is said where one is kept for another tool. None,
    None where none is kept."""
    kept = load(site, router)
    if kept is None:
        return None, None
    if abs(kept.tool - tool) > EPS:
        return None, (
            f"{kept.router}'s allowance was measured with a {kept.tool:g} mm tool: "
            f"this toolpath's {tool:g} mm tool takes none"
        )
    newest = kept.measurements[-1] if kept.measurements else None
    source = f"{site}'s {kept.router}, measured: " + (
        said(newest) + f" ({newest.at:%Y-%m-%d})" if newest else "kept"
    )
    return Allowance(value=kept.value, source=source), None
