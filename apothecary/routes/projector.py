"""A projector aimed at a machine's bed, over HTTP (``apothecary/projector.py``).

- ``GET /sites/{s}/machines/{path}/projector``: what the projector draws, as one answer
  (``answer``): the machine's frame, its calibration and the mapping it fixes, what the
  machine is about to make in the bed's millimetres, and what moves with each poll.
- ``PUT /sites/{s}/machines/{path}/projector`` ``{bed, pixels, size}``: four points of
  the bed, the four pixels of the output that light them, and the output's size, kept as
  the machine's calibration; answers as GET does. A bed that carries Y is calibrated
  where its last poll says it stands, and refused while no poll has said.
- ``DELETE /sites/{s}/machines/{path}/projector``: the calibration forgotten.
- ``PUT /sites/{s}/machines/{path}/projector/upper`` ``{pixels, size, height, bed?}``: a
  second plane ``height`` mm above the bed, marked with a flat piece of that thickness on
  it, kept with the calibration (``projector.checked_upper``); ``DELETE`` forgets it alone.
  ``GET ...?height=z`` asks for the plane ``z`` mm above the bed, refusing (422) one the
  calibration does not fix.
- ``GET /projector/sites/{s}/machines/{path}``: the projector's page, black and one canvas,
  for a second display (``templates/projector.html.j2``, ``static/projector.js``).

The answer's parts:

- ``picture``: what is drawn through the mapping and changes only when what is made
  does -- the bed's outline, the toolpath of the file streaming on the machine, else of
  the file its plan names (``machine_plans``), in the bed's millimetres, placed by where
  the file's zero stands (a printer's file is in its bed's coordinates; a router's counts
  from the work zero its controller reports, ``work_origin``), only the moves that make
  something; and a router plan's cuts (``apothecary/cam``), placed the same way. ``key``
  names it, so a reader knows when to ask again.
- ``plane``: which plane the picture is drawn for, and its mapping: the bed plane, or --
  with a second plane marked -- the height of what is drawn on it: a printer's layer the
  stream is in (the file's own height), a router's stock top (the work zero's height as
  the controller reports it). One calibration draws on the bed plane only, and says so.
- ``moving``: what a poll moves -- the tool's place in the frame where a poll said it
  (never a guessed one), where a bed that carries Y stands, the group the streaming job
  is in, and the status band: the machine's state, its job's stage and progress, and
  what it needs, each as the poll said it.

Nothing here asks a port anything: the machine's state is its last poll, kept by
whoever polled it (``api.machine_poll``). Plain ``def``: a long file's toolpath takes
seconds to read the first time.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .. import jobs, machine_plans, projector, sites, surfaces
from ..firmware import devices as firmware_devices
from ..hierarchy import find_node_by_path

router = APIRouter(tags=["projector"])

FORMAT = "apothecary.projected/1"
# The streamed kinds of job a toolpath is drawn for (firmware/devices.STREAMED).
STREAMED = ("print", "cut")
# How closely a circle of a router's cuts is drawn: this many sides.
CIRCLE_SIDES = 48
# Millimetres are given to a hundredth.
PLACES = 2
# What is said where nothing can be drawn: no calibration; a bed whose place is not known.
NOT_CALIBRATED = (
    "not calibrated: four points of the bed are marked on the projector's page (C there)"
)
BED_UNKNOWN = "the bed carries Y and no poll has said where it stands: nothing on it is drawn"


class CalibrationIn(BaseModel):
    """Four points of the bed, in its millimetres; the four pixels of the output that
    light them, from its top left; and the output's size in pixels."""

    bed: List[Tuple[float, float]] = Field(..., min_length=4, max_length=4)
    pixels: List[Tuple[float, float]] = Field(..., min_length=4, max_length=4)
    size: Tuple[int, int]


# What each machine's last answer drew: its picture's key and each of its toolpath's
# groups' first line, so a poll can say which group a job is in without reading the file.
_DRAWN: Dict[Tuple[str, str], Tuple[str, List[int]]] = {}
_DRAWN_LOCK = threading.Lock()


def _machine(site_name: str, path: str):
    """The site, the machine node at ``path`` and its kind (None for a part that names no
    kind of machine); 404 for no such node, 400 for one with no working volume."""
    site = sites.store.get(site_name)
    node = find_node_by_path(site, path)
    if node is None:
        raise HTTPException(status_code=404, detail=f"no node {path!r} in {site_name}")
    if node.build_volume is None:
        raise HTTPException(
            status_code=400,
            detail=f"{path} in {site_name} is no machine: it has no working volume to project onto",
        )
    kind = machine_plans.kind_of_part(node.part_ref) if node.part_ref else None
    return site, node, kind


def _mm(value: float) -> float:
    return round(float(value), PLACES)


def _carries_y(frame: Dict[str, Any]) -> bool:
    return isinstance(frame.get("bed_moves_y"), (int, float))


def _tool(status) -> Optional[Dict[str, float]]:
    """Where a poll put the tool in the volume, when it said X and Y; else None."""
    place = status.tool_position if status is not None else None
    if not place or not all(isinstance(place.get(k), (int, float)) for k in "xy"):
        return None
    return place


def bed_offset(frame: Dict[str, Any], status) -> Optional[float]:
    """How far a bed that carries Y stands along Y from where the frame's origin has it,
    as the poll's tool says (frames.js bedOffsetAt); 0 for a bed that stays; None for a
    bed that carries Y while no poll has said where the tool is."""
    if not _carries_y(frame):
        return 0.0
    tool = _tool(status)
    return None if tool is None else _mm(frame["bed_moves_y"] - tool["y"])


def _job(status) -> Optional[Dict[str, Any]]:
    """The streamed job a poll says is running, or None."""
    job = status.job if status is not None else None
    if not job or job.get("kind") not in STREAMED or not job.get("running", True):
        return None
    return job


def _file_origin(kind: Optional[str], status) -> Optional[Dict[str, float]]:
    """Where a file's (0, 0, 0) stands in the volume: a printer's file is in its bed's
    coordinates; a router's counts from the work zero, as its controller reports it
    (``work_origin``), and None while no poll has said (machine_marks.js fileOrigin)."""
    if kind != "router":
        return {"x": 0.0, "y": 0.0, "z": 0.0}
    origin = status.work_origin if status is not None else None
    if not origin or not all(isinstance(origin.get(k), (int, float)) for k in "xyz"):
        return None
    return {k: float(origin[k]) for k in "xyz"}


# --- the status band ---------------------------------------------------------------------


def band(status) -> Dict[str, Any]:
    """The machine's state, its job's stage and progress, and what it needs, each as its
    last poll said it, and in words a projector can light; no figure the poll lacks."""
    if status is None:
        return {
            "state": None,
            "polled_at": None,
            "job": None,
            "needs": [],
            "lines": ["no poll kept: this machine's state is not known here"],
        }
    job = status.job or None
    needs = list(status.todo or [])
    if status.alarm_text:
        needs.append(status.alarm_text)
    if status.refused:
        said = status.refused.get("said") or "refused"
        needs.append(f"{status.refused.get('command') or 'a line'}: {said}")
    if status.filament_present is False:
        needs.append("no filament at the runout sensor")
    lines = [status.state]
    shown: Optional[Dict[str, Any]] = None
    if job:
        shown = {k: job.get(k) for k in ("kind", "name", "stage", "progress", "sent", "total")}
        words = [job.get("kind") or "job"]
        if job.get("name"):
            words.append(str(job["name"]))
        if job.get("stage"):
            words.append(str(job["stage"]))
        lines.append(" · ".join(words))
        if job.get("kind") in STREAMED and job.get("total"):
            lines.append(
                f"{job.get('progress', 0.0):.0%} · line {job.get('sent', 0)} of {job['total']}"
            )
    lines.extend(needs)
    return {
        "state": status.state,
        "polled_at": status.polled_at.isoformat(),
        "job": shown,
        "needs": needs,
        "lines": lines,
    }


# --- the plane the picture is drawn for ------------------------------------------------------

BED_ONLY = "bed plane only: one calibration, so what stands above the bed is lit displaced"


def _wanted(site_name: str, path: str, kind: Optional[str], status) -> Optional[Dict[str, Any]]:
    """The height above the bed of what is drawn, as the plan or the stream says it, or None:
    a printer's layer the streaming file is in (the file's own Z, so far as a poll's
    lines sent place it), a router's stock top (the work zero's height, as its controller
    reports it -- the work zero stands at the stock's top, ``cam/models.py``)."""
    if kind == "router":
        origin = _file_origin(kind, status)
        if origin is None:
            return None
        return {"z": _mm(origin["z"]), "for": "the stock's top"}
    layer = _layer(site_name, path, status)
    return None if layer is None else {"z": _mm(layer[1]), "for": layer[0]}


def _how(calibration, z: float) -> str:
    upper = calibration.upper
    if z <= 1e-9:
        return "measured at the bed plane"
    if abs(z - upper.height) <= 1e-9:
        return "measured at the second plane"
    if z < upper.height:
        return "between the two calibrated planes"
    return "beyond the second plane: extrapolated, weaker"


def plane(
    site_name: str,
    path: str,
    kind: Optional[str],
    frame: Dict[str, Any],
    status,
    calibration,
    height: Optional[float] = None,
) -> Dict[str, Any]:
    """Which plane the picture is drawn for, and the mapping that is true there. ``height``
    asks for one by its height (``projector.Refused`` when the calibration fixes none
    there); else it is the height of what is drawn (``_wanted``) when the calibration fixes
    it, and the bed plane with the reason when it does not or when no second plane
    is marked."""
    wanted = {"z": _mm(height), "for": "the height asked"} if height is not None else None
    wanted = wanted or _wanted(site_name, path, kind, status)
    base: Dict[str, Any] = {
        "z": 0.0,
        "for": "the bed plane",
        "wanted": wanted,
        "heights": [],
        "how": None,
        "mapping": None,
        "line": None,
        "said": [],
    }
    if calibration is None:
        return base
    from ..vision.projection import as_lists

    base["heights"] = [0.0] + ([calibration.upper.height] if calibration.upper else [])
    bed = as_lists(projector.mapping(calibration))
    if calibration.upper is None:
        if height is not None and abs(height) > 1e-9:
            projector.mapping_at(calibration, height)  # refuses, saying why
        base.update(mapping=bed, how="bed plane only", line=f"drawn for the bed plane -- {BED_ONLY}")
        if wanted and wanted["z"] > 1e-9:
            base["said"].append(
                f"{wanted['for']} stands {wanted['z']:g} mm above the bed: lit displaced "
                "from where it is, until a second plane is marked at a known height"
            )
        return base
    offset = bed_offset(frame, status) or 0.0
    vx, vy = frame["volume"][0], frame["volume"][1]
    floor = [(0.0, offset), (vx, offset), (vx, vy + offset), (0.0, vy + offset)]
    z = wanted["z"] if wanted else 0.0
    try:
        matrix = projector.mapping_at(calibration, z, over=floor)
    except projector.Refused as exc:
        if height is not None:
            raise
        base.update(
            mapping=bed,
            how="bed plane: the height is refused",
            line="drawn for the bed plane: the height of what is drawn is refused",
        )
        base["said"].append(f"{wanted['for']} at {z:g} mm: {exc}")
        return base
    how = _how(calibration, z)
    what = wanted["for"] if wanted and z > 1e-9 else "the bed plane"
    spans = " and ".join(f"{h:g}" for h in base["heights"])
    base.update(
        z=z,
        mapping=as_lists(matrix),
        how=how,
        line=f"drawn for {what}, {z:g} mm above the bed ({how}; planes calibrated at {spans} mm)"
        if z > 1e-9
        else f"drawn for the bed plane ({how}; planes calibrated at {spans} mm)",
    )
    base["for"] = what
    if z > calibration.upper.height + 1e-9:
        base["said"].append(
            f"{z:g} mm is past the second plane's {calibration.upper.height:g} mm: what "
            f"was marked wrong there is carried {z / calibration.upper.height:.2g} times over"
        )
    return base


# --- what is about to be made ----------------------------------------------------------------


def _toolpath(file_id: str, kind: str, origin: Dict[str, float]) -> Optional[Dict[str, Any]]:
    """A kept file's toolpath in the bed's millimetres: each move that makes something,
    seen from above, from where it starts to where it ends, with the groups a person
    scrubs through; None for a file no longer kept."""
    from ..preview import for_machine

    preview = firmware_devices.print_preview(file_id, kind)
    if preview is None:
        return None
    air = {i for i, name in enumerate(preview.kinds) if name in for_machine(kind).air}
    ox, oy, oz = origin["x"], origin["y"], origin["z"]
    segments: List[float] = []
    groups: List[Dict[str, Any]] = []
    sents: List[int] = []
    heights: List[Optional[float]] = []
    for group in preview.groups:
        first = len(segments) // 4
        for i in range(group.first, group.first + group.count):
            if preview.kind_of[i] in air:
                continue
            at = i * 6
            x0, y0 = preview.points[at], preview.points[at + 1]
            x1, y1 = preview.points[at + 3], preview.points[at + 4]
            if (x0, y0) == (x1, y1):
                continue  # straight down or up: nothing to see from above
            segments.extend((_mm(ox + x0), _mm(oy + y0), _mm(ox + x1), _mm(oy + y1)))
        groups.append({"label": group.label, "first": first, "count": len(segments) // 4 - first})
        sents.append(group.sent)
        heights.append(None if group.z is None else _mm(oz + group.z))
    return {
        "process": preview.process,
        "word": preview.word,
        "origin": origin,
        "segments": segments,
        "groups": groups,
        "within_mm": preview.within_mm,
        "left_out": [name for name in preview.kinds if name in for_machine(kind).air],
        "sents": sents,
        "heights": heights,
    }


def _circle(x: float, y: float, r: float) -> List[List[float]]:
    turns = (2 * math.pi * k / CIRCLE_SIDES for k in range(CIRCLE_SIDES + 1))
    return [[_mm(x + r * math.cos(a)), _mm(y + r * math.sin(a))] for a in turns]


def _rectangle(x: float, y: float, w: float, h: float) -> List[List[float]]:
    corners = ((x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y))
    return [[_mm(cx), _mm(cy)] for cx, cy in corners]


def _cuts(site, plan, origin: Optional[Dict[str, float]]) -> Optional[Dict[str, Any]]:
    """A router plan's part's cuts as outlines in the bed's millimetres: its stock, then
    each operation, placed at the work zero the controller reports. None for no plan
    naming a part that says how it is cut; ``why`` where it cannot be placed."""
    if plan is None or not plan.part:
        return None
    from ..cam.service import CamError, part_cuts

    node = find_node_by_path(site, plan.part)
    name = node.part_ref if node is not None and node.part_ref else plan.part
    try:
        _, _, cuts = part_cuts(name)
    except (CamError, KeyError, ValueError):
        return None
    if origin is None:
        return {"part": name, "shapes": [], "why": "no poll has said where the work zero stands"}
    ox, oy = origin["x"], origin["y"]
    shapes = [{"what": "stock", "points": _rectangle(ox, oy, cuts.stock.x, cuts.stock.y)}]
    for op in cuts.operations:
        if op.kind in ("pocket", "outline"):
            points = _rectangle(ox + op.x, oy + op.y, op.w, op.h)
        else:
            points = _circle(ox + op.x, oy + op.y, op.diameter / 2)
        shapes.append({"what": op.name or op.kind, "points": points})
    return {"part": name, "shapes": shapes, "why": None}


def _hull(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """The convex outline of ``points``, counter-clockwise from the lowest left one."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def half(seq):
        out: List[Tuple[float, float]] = []
        for q in seq:
            while len(out) >= 2 and (
                (out[-1][0] - out[-2][0]) * (q[1] - out[-2][1])
                - (out[-1][1] - out[-2][1]) * (q[0] - out[-2][0])
            ) <= 0:
                out.pop()
            out.append(q)
        return out

    return half(pts)[:-1] + half(reversed(pts))[:-1]


def _first_layer(toolpath: Optional[Dict[str, Any]]) -> Optional[List[List[float]]]:
    """The toolpath's first layer that lays anything, as the convex outline of where it
    lays it (closed), or None: a printer's file is additive, and a part's first layer is
    where it stands on the bed."""
    if not toolpath or toolpath["process"] != "additive":
        return None
    group = next((g for g in toolpath["groups"] if g["count"] > 0), None)
    if group is None:
        return None
    flat = toolpath["segments"][group["first"] * 4 : (group["first"] + group["count"]) * 4]
    hull = _hull([(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)])
    if len(hull) < 3:
        return None
    return [[_mm(x), _mm(y)] for x, y in [*hull, hull[0]]]


def _planned_footprint(site, plan, frame: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
    """A printer plan's part as it will stand on the bed, before any file is sliced: its
    declared bounds at its defaults (``BasePart.get_bounds``: the way up it prints), its
    X and Y extent as a rectangle centred on the bed, where OrcaSlicer's arrange puts one
    part (``--arrange 1``, ``--orient 0``: not turned). None, and why, for a part that
    declares no bounds or does not load."""
    from ..projects.parts.skeleton import ROOT
    from ..projects.registry import PartLoadError, part_named

    node = find_node_by_path(site, plan.part)
    name = node.part_ref if node is not None and node.part_ref else plan.part
    try:
        bounds = part_named(name, ROOT).get_bounds()
    except (KeyError, PartLoadError):
        return None, f"the planned part {name} does not load: no footprint is drawn"
    if bounds is None:
        return None, f"the planned part {name} declares no bounds: no footprint is drawn"
    sx = bounds.max_point.x - bounds.min_point.x
    sy = bounds.max_point.y - bounds.min_point.y
    cx, cy = frame["volume"][0] / 2, frame["volume"][1] / 2
    said = (
        f"planned footprint of {name}: its bounds at its defaults, {_mm(sx):g} by {_mm(sy):g} mm, "
        "centred on the bed as the slicer arranges one part -- not sliced yet"
    )
    if sx > frame["volume"][0] or sy > frame["volume"][1]:
        said += "; it is larger than the bed"
    return {
        "points": _rectangle(cx - sx / 2, cy - sy / 2, sx, sy),
        "source": "plan",
        "part": name,
        "size": [_mm(sx), _mm(sy)],
    }, said


def _footprint(
    site, plan, kind: Optional[str], frame: Dict[str, Any], toolpath, said: List[str]
) -> Optional[Dict[str, Any]]:
    """Where the part will stand on a printer's bed: the first layer's own outline once a
    file is drawn (``source`` "toolpath"), else the plan's part's planned footprint
    (``source`` "plan", and said so); None for a router, whose cuts are its shapes, and for
    a plan that names no part."""
    if kind == "router":
        return None
    outline = _first_layer(toolpath)
    if outline is not None:
        return {"points": outline, "source": "toolpath", "part": None, "size": None}
    if plan is None or not plan.part:
        return None
    found, words = _planned_footprint(site, plan, frame)
    said.append(words)
    return found


def _intent(site_name: str, path: str, kind: Optional[str], status):
    """Which file is about to be made, and why: the one streaming, else the plan's;
    where its zero stands; the plan; and what is said of what cannot be drawn."""
    job = _job(status)
    plan = machine_plans.load(site_name, path)
    origin = _file_origin(kind, status)
    said: List[str] = []
    source, file = None, None
    if job and job.get("file_id"):
        source, file = "job", {"id": job["file_id"], "name": job.get("name")}
    elif plan is not None and plan.file_id:
        kept = firmware_devices.print_file(plan.file_id)
        source = "plan"
        file = {"id": plan.file_id, "name": kept.name if kept is not None else None}
    else:
        said.append("nothing streams on this machine, and no plan names a file")
    return source, file, origin, plan, said


def _key(source, file, origin, plan, calibration, volume=None) -> str:
    """What names a picture: it is drawn again when any of these changes."""
    calibrated = calibration.at.isoformat() if calibration is not None else None
    if calibration is not None and calibration.upper is not None:
        calibrated = f"{calibrated}+{calibration.upper.at.isoformat()}"
    named = [source, file, origin, plan.part if plan else None, calibrated, volume]
    return hashlib.sha256(json.dumps(named, sort_keys=True).encode()).hexdigest()[:16]


def _picture(site_name, site, path, kind, frame, status, calibration) -> Dict[str, Any]:
    """What is drawn through the mapping: the bed's outline, the toolpath and the cuts."""
    vx, vy = frame["volume"][0], frame["volume"][1]
    source, file, origin, plan, said = _intent(site_name, path, kind, status)
    toolpath = None
    if file is not None and kind is None:
        said.append("this machine's part names no kind of machine, so no toolpath is read")
    elif file is not None and origin is None:
        said.append("no poll has said where the work zero stands, so the toolpath is not placed")
    elif file is not None:
        toolpath = _toolpath(file["id"], kind, origin)
        if toolpath is None:
            said.append(f"{file['name'] or file['id']} is no longer kept")
    cuts = _cuts(site, plan, origin) if kind == "router" else None
    if calibration is None:
        said.append(NOT_CALIBRATED)
    picture = {
        "bed": {
            "outline": [[0.0, 0.0], [vx, 0.0], [vx, vy], [0.0, vy]],
            "carries_y": _carries_y(frame),
        },
        "source": source,
        "file": file,
        "toolpath": toolpath,
        "cuts": cuts,
        "said": said,
        "calibrated_at": calibration.at.isoformat() if calibration is not None else None,
    }
    sents = toolpath.pop("sents") if toolpath else []
    heights = toolpath.pop("heights") if toolpath else []
    footprint = _footprint(site, plan, kind, frame, toolpath, said)
    picture["footprint"] = footprint
    key = _key(source, file, origin, plan, calibration, frame["volume"])
    picture["key"] = key
    labels = [g["label"] for g in toolpath["groups"]] if toolpath else []
    with _DRAWN_LOCK:
        _DRAWN[(site_name, path)] = (key, sents, heights, labels)
    return picture


def _current(site_name: str, path: str, status) -> Optional[int]:
    """The group of the drawn toolpath the streaming job is in, by the lines it has sent."""
    job = _job(status)
    with _DRAWN_LOCK:
        drawn = _DRAWN.get((site_name, path))
    if job is None or drawn is None or not isinstance(job.get("sent"), int):
        return None
    begun = [i for i, sent in enumerate(drawn[1]) if sent <= job["sent"]]
    return begun[-1] if begun else None


def _layer(site_name: str, path: str, status) -> Optional[Tuple[str, float]]:
    """The label and the height above the bed of the group the streaming job is in, as the
    file says it (a layer's own Z), or None while no job, no drawn file or no height."""
    current = _current(site_name, path, status)
    with _DRAWN_LOCK:
        drawn = _DRAWN.get((site_name, path))
    if current is None or drawn is None or current >= len(drawn[2]) or drawn[2][current] is None:
        return None
    return drawn[3][current], drawn[2][current]


def moving(site_name: str, path: str, frame: Dict[str, Any], status) -> Dict[str, Any]:
    """What a poll moves: the tool in the frame (a bed that carries Y standing still
    under it, the tool's Y the bed's ``bed_moves_y``), where the bed stands, the group
    the job is in and the band."""
    tool = _tool(status)
    at = None
    if tool is not None:
        y = frame["bed_moves_y"] if _carries_y(frame) else tool["y"]
        at = [_mm(tool["x"]), _mm(y)]
    offset = bed_offset(frame, status)
    return {
        "tool": at,
        "bed_offset": offset,
        "current": _current(site_name, path, status),
        "status": band(status),
        "said": [BED_UNKNOWN] if offset is None else [],
    }


def _now_at(site_name: str, path: str):
    """The machine as its last poll has it: the site, its node and kind, the port and the
    poll (None and None while none is kept), and its frame with the controller's word."""
    from ..api import describe_for_view, machine_poll

    site, node, kind = _machine(site_name, path)
    polled = machine_poll(site_name, path)
    port, status = polled if polled is not None else (None, None)
    frame = describe_for_view(site, path, node, is_printer=True, controller=status)["frame"]
    return site, kind, port, status, frame


def moved(site_name: str, path: str) -> Dict[str, Any]:
    """What a change of the machine's says, without reading its toolpath: its picture's
    key, so a reader holding another asks again, what moves, and -- once calibrated -- the
    plane it is drawn for, which a layer climbing moves."""
    _, kind, _, status, frame = _now_at(site_name, path)
    source, file, origin, plan, _ = _intent(site_name, path, kind, status)
    calibration = projector.load(site_name, path)
    key = _key(source, file, origin, plan, calibration, frame["volume"])
    said = {"key": key, "moving": moving(site_name, path, frame, status)}
    if calibration is not None:  # a machine not calibrated has no plane to say
        said["plane"] = plane(site_name, path, kind, frame, status, calibration)
    return said


def answer(site_name: str, path: str, height: Optional[float] = None) -> Dict[str, Any]:
    """Everything the projector's page draws for the machine at ``path``, as one answer;
    ``height``, a plane's height above the bed, asks for that plane's mapping (422 for one
    the calibration does not fix)."""
    from ..homography import Degenerate
    from ..vision.projection import as_lists

    site, kind, port, status, frame = _now_at(site_name, path)
    calibration = projector.load(site_name, path)
    try:
        matrix = as_lists(projector.mapping(calibration)) if calibration is not None else None
    except Degenerate:
        matrix = None
    picture = _picture(site_name, site, path, kind, frame, status, calibration)
    try:
        drawn_for = plane(site_name, path, kind, frame, status, calibration, height)
    except projector.Refused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    upper = projector.upper_mapping(calibration) if calibration is not None else None
    return {
        "format": FORMAT,
        "site": site_name,
        "path": path,
        "kind": kind,
        "port": port,
        "made_at": datetime.now(timezone.utc).isoformat(),
        "frame": frame,
        "calibration": calibration.model_dump(mode="json") if calibration is not None else None,
        "starting_points": [list(p) for p in projector.starting_points(frame["volume"])],
        "mapping": matrix,
        "upper_mapping": as_lists(upper) if upper is not None else None,
        "plane": drawn_for,
        "size": list(calibration.size) if calibration is not None else None,
        "picture": picture,
        "moving": moving(site_name, path, frame, status),
    }


@router.get("/sites/{name}/machines/{path}/projector")
def projected(name: str, path: str, height: Optional[float] = None):
    return answer(name, path, height)


@router.put("/sites/{name}/machines/{path}/projector")
def calibrate(name: str, path: str, body: CalibrationIn):
    """Keep four points of the bed and the pixels lighting them as the machine's
    calibration. A bed that carries Y is marked where its last poll says it stands."""
    _, _, _, status, frame = _now_at(name, path)
    offset = bed_offset(frame, status)
    if offset is None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{path}'s bed carries Y, and no poll has said where it stands: poll the "
                "machine, then mark the four points"
            ),
        )
    try:
        calibration = projector.checked(name, path, body.bed, body.pixels, body.size, offset)
    except projector.Refused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    projector.save(calibration)
    _say_moved(name, path)
    return answer(name, path)


class UpperIn(BaseModel):
    """The second plane: the pixels of the output that light four points of a plane
    ``height`` mm above the bed (the bed's four, unless ``bed`` names others), and the size of
    the canvas they were marked on."""

    pixels: List[Tuple[float, float]] = Field(..., min_length=4, max_length=4)
    size: Tuple[int, int]
    height: float
    bed: Optional[List[Tuple[float, float]]] = Field(None, min_length=4, max_length=4)


@router.put("/sites/{name}/machines/{path}/projector/upper")
def calibrate_upper(name: str, path: str, body: UpperIn):
    """Keep a second plane, ``height`` mm above the bed, with the machine's calibration; a
    bed that carries Y is marked where its last poll says it stands."""
    _, _, _, status, frame = _now_at(name, path)
    calibration = projector.load(name, path)
    if calibration is None:
        raise HTTPException(
            status_code=409,
            detail=f"{path} has no calibration of the bed plane: mark its four points first",
        )
    offset = bed_offset(frame, status)
    if offset is None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{path}'s bed carries Y, and no poll has said where it stands: poll the "
                "machine, then mark the four points"
            ),
        )
    try:
        both = projector.checked_upper(
            calibration, body.pixels, body.size, body.height, body.bed, offset
        )
    except projector.Refused as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    projector.save(both)
    _say_moved(name, path)
    return answer(name, path)


@router.delete("/sites/{name}/machines/{path}/projector/upper")
def forget_upper(name: str, path: str):
    """The second plane forgotten, the bed plane's calibration kept."""
    _machine(name, path)
    calibration = projector.load(name, path)
    if calibration is None or calibration.upper is None:
        return {"forgotten": False}
    projector.save(calibration.model_copy(update={"upper": None}))
    _say_moved(name, path)
    return {"forgotten": True}


@router.delete("/sites/{name}/machines/{path}/projector")
def forget(name: str, path: str):
    _machine(name, path)
    forgotten = projector.clear(name, path)
    _say_moved(name, path)
    return {"forgotten": forgotten}


@router.get("/projector/sites/{name}/machines/{path}", include_in_schema=False)
def projector_page(name: str, path: str, request: Request):
    """The projector's page: black, one canvas, for a second display aimed at the machine's
    bed (static/projector.js). 404 for no such node, 400 for one with no working volume."""
    from ..viewer import render_projector_page

    _machine(name, path)
    return HTMLResponse(render_projector_page(name, path, str(request.base_url)))


# --- the projector's picture, as a surface ----------------------------------------------------

# Read as GET .../projector answers it; said changed as the server learns of what moves it --
# a poll of the machine's board, whoever made it, a job of it begun or ended, a calibration
# kept or forgotten -- with its picture's key and what moves, never the toolpath itself.
PROJECTOR = "projector"


def _say_moved(site_name: str, path: str) -> None:
    surfaces.changed(PROJECTOR, key=f"{site_name}/{path}", body=lambda: moved(site_name, path))


def _relay_on_port(port: str) -> None:
    """Said of the machine the board on ``port`` drives, while anyone follows; nothing
    said of a board that drives no machine. Never raises into the poll or the job."""
    if not surfaces.listening(PROJECTOR):
        return
    from ..api import machine_on_port

    try:
        found = machine_on_port(port)
        if found is None:
            return
        node = find_node_by_path(sites.store.get(found[0]), found[1])
    except Exception:  # a site forgotten meanwhile: nothing of it to say
        return
    if node is not None and node.build_volume is not None:
        _say_moved(*found)


def _relay_poll(status) -> list:
    _relay_on_port(status.port)
    return []


def _relay_job(job) -> None:
    _relay_on_port(job.machine.port)


surfaces.register(
    surfaces.Surface(
        name=PROJECTOR,
        frame="bed_mm",
        about="what a projector aimed at a machine's bed draws: its calibration, what is about "
        "to be made, and what a poll moves",
        snapshot=lambda words: answer(words["site"], words["path"]),
        takes=("site", "path"),
        needs=("site", "path"),
        tells=True,
        owner=__name__,
    )
)


def _listen(listeners: list, listener) -> None:
    """``listener`` among ``listeners`` once, however often this module is imported: one
    of the same name an earlier import of it left there is taken out first."""
    same = (listener.__module__, listener.__qualname__)
    listeners[:] = [
        f
        for f in listeners
        if (getattr(f, "__module__", None), getattr(f, "__qualname__", None)) != same
    ]
    listeners.append(listener)


_listen(firmware_devices.STATUS_LISTENERS, _relay_poll)
_listen(jobs.LISTENERS, _relay_job)


__all__ = [
    "CalibrationIn",
    "PROJECTOR",
    "UpperIn",
    "answer",
    "band",
    "bed_offset",
    "moved",
    "moving",
    "plane",
    "router",
]
