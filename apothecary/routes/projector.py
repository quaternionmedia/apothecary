"""A projector aimed at a machine's bed, over HTTP (``apothecary/projector.py``).

- ``GET /sites/{s}/machines/{path}/projector``: what the projector draws, as one answer
  (``answer``): the machine's frame, its calibration and the mapping it fixes, what the
  machine is about to make in the bed's millimetres, and what moves with each poll.
- ``PUT /sites/{s}/machines/{path}/projector`` ``{bed, pixels, size}``: four points of
  the bed, the four pixels of the output that light them, and the output's size, kept as
  the machine's calibration; answers as GET does. A bed that carries Y is calibrated
  where its last poll says it stands, and refused while no poll has said.
- ``DELETE /sites/{s}/machines/{path}/projector``: the calibration forgotten.

The answer's parts:

- ``picture``: what is drawn through the mapping and changes only when what is made
  does -- the bed's outline, the toolpath of the file streaming on the machine, else of
  the file its plan names (``machine_plans``), in the bed's millimetres, placed by where
  the file's zero stands (a printer's file is in its bed's coordinates; a router's counts
  from the work zero its controller reports, ``work_origin``), only the moves that make
  something; and a router plan's cuts (``apothecary/cam``), placed the same way. ``key``
  names it, so a reader knows when to ask again.
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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import machine_plans, projector, sites
from ..hierarchy import find_node_by_path

router = APIRouter(tags=["projector"])

FORMAT = "apothecary.projected/1"
# The streamed kinds of job a toolpath is drawn for (firmware/devices.STREAMED).
STREAMED = ("print", "cut")
# How closely a circle of a router's cuts is drawn: this many sides.
CIRCLE_SIDES = 48
# Millimetres are given to a hundredth.
PLACES = 2


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


# --- what is about to be made ----------------------------------------------------------------


def _toolpath(file_id: str, kind: str, origin: Dict[str, float]) -> Optional[Dict[str, Any]]:
    """A kept file's toolpath in the bed's millimetres: each move that makes something,
    seen from above, from where it starts to where it ends, with the groups a person
    scrubs through; None for a file no longer kept."""
    from ..firmware import devices
    from ..preview import for_machine

    preview = devices.print_preview(file_id, kind)
    if preview is None:
        return None
    air = {i for i, name in enumerate(preview.kinds) if name in for_machine(kind).air}
    ox, oy = origin["x"], origin["y"]
    segments: List[float] = []
    groups: List[Dict[str, Any]] = []
    sents: List[int] = []
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
    return {
        "process": preview.process,
        "word": preview.word,
        "origin": origin,
        "segments": segments,
        "groups": groups,
        "within_mm": preview.within_mm,
        "left_out": [name for name in preview.kinds if name in for_machine(kind).air],
        "sents": sents,
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


def _picture(site_name, site, path, kind, frame, status, calibration) -> Dict[str, Any]:
    """What is drawn through the mapping: the bed's outline, the toolpath and the cuts."""
    from ..firmware import devices

    vx, vy = frame["volume"][0], frame["volume"][1]
    job = _job(status)
    plan = machine_plans.load(site_name, path)
    origin = _file_origin(kind, status)
    said: List[str] = []
    source, file = None, None
    if job and job.get("file_id"):
        source, file = "job", {"id": job["file_id"], "name": job.get("name")}
    elif plan is not None and plan.file_id:
        kept = devices.print_file(plan.file_id)
        source = "plan"
        file = {"id": plan.file_id, "name": kept.name if kept is not None else None}
    else:
        said.append("nothing streams on this machine, and no plan names a file")
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
    named = [source, file, origin, plan.part if plan else None, picture["calibrated_at"]]
    key = hashlib.sha256(json.dumps(named, sort_keys=True).encode()).hexdigest()[:16]
    picture["key"] = key
    with _DRAWN_LOCK:
        _DRAWN[(site_name, path)] = (key, sents)
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


def moving(site_name: str, path: str, frame: Dict[str, Any], status) -> Dict[str, Any]:
    """What a poll moves: the tool in the frame (a bed that carries Y standing still
    under it, the tool's Y the bed's ``bed_moves_y``), where the bed stands, the group
    the job is in and the band."""
    tool = _tool(status)
    at = None
    if tool is not None:
        y = frame["bed_moves_y"] if _carries_y(frame) else tool["y"]
        at = [_mm(tool["x"]), _mm(y)]
    return {
        "tool": at,
        "bed_offset": bed_offset(frame, status),
        "current": _current(site_name, path, status),
        "status": band(status),
    }


def answer(site_name: str, path: str) -> Dict[str, Any]:
    """Everything the projector's page draws for the machine at ``path``, as one answer."""
    from ..api import describe_for_view, machine_poll
    from ..homography import Degenerate
    from ..vision.projection import as_lists

    site, node, kind = _machine(site_name, path)
    polled = machine_poll(site_name, path)
    port, status = polled if polled is not None else (None, None)
    frame = describe_for_view(site, path, node, is_printer=True, controller=status)["frame"]
    calibration = projector.load(site_name, path)
    try:
        matrix = as_lists(projector.mapping(calibration)) if calibration is not None else None
    except Degenerate:
        matrix = None
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
        "size": list(calibration.size) if calibration is not None else None,
        "picture": _picture(site_name, site, path, kind, frame, status, calibration),
        "moving": moving(site_name, path, frame, status),
    }


@router.get("/sites/{name}/machines/{path}/projector")
def projected(name: str, path: str):
    return answer(name, path)


@router.put("/sites/{name}/machines/{path}/projector")
def calibrate(name: str, path: str, body: CalibrationIn):
    """Keep four points of the bed and the pixels lighting them as the machine's
    calibration. A bed that carries Y is marked where its last poll says it stands."""
    from ..api import describe_for_view, machine_poll

    site, node, _ = _machine(name, path)
    polled = machine_poll(name, path)
    status = polled[1] if polled is not None else None
    frame = describe_for_view(site, path, node, is_printer=True, controller=status)["frame"]
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
    return answer(name, path)


@router.delete("/sites/{name}/machines/{path}/projector")
def forget(name: str, path: str):
    _machine(name, path)
    return {"forgotten": projector.clear(name, path)}


__all__ = ["CalibrationIn", "answer", "band", "bed_offset", "moving", "router"]
