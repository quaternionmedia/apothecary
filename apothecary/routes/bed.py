"""``/bed/{site}/{printer}``: a printer's bed readings and the shims that level it, as the
page's Runs, Differences, Fixes and History windows draw them, and what its shims fit.

``GET`` answers ``apothecary.bed_shims.story``: the readings of the board pinned at the
printer's node, newest first, each with its grid; the shims from its newest heated pair;
that pair's own difference (the repeatability floor), the newest pair less the pair
before it, and what the plane leaves (the bow); the profile's bound for a stored mesh;
and the mount the shims fit, kept or the part's defaults. It reads the state folder and
the printer's profile: no port is opened and nothing is sent.

``PUT .../mount`` keeps what a person measured of the printer's mounts -- the bed screw,
the hole, the mount's outer diameter -- in the state folder
(``apothecary.bed_shims.keep_mount``), and answers what the shims now fit.

``PUT .../where/{what}`` keeps where the printer's nozzle stands over one of its screws
(by name) or a corner of its plate (``plate_front_left``, ``plate_back_right``)
(``apothecary.bed_shims.keep_position``): ``{x, y}`` as given, or ``{here: true}``, where
the board pinned at the printer says its nozzle is now (``M114``), refused until it has
homed X and Y since it started. The shims are taken at the screws kept from then on.
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import bed_shims

router = APIRouter(tags=["bed"])


class MountRequest(BaseModel):
    screw: Optional[Literal["M3", "M4"]] = None
    hole_d: Optional[float] = Field(None, gt=0, le=50)
    outer_d: Optional[float] = Field(None, gt=0, le=100)


class WhereRequest(BaseModel):
    here: bool = False  # where the nozzle stands now, as the pinned board says
    x: Optional[float] = Field(None, ge=-50, le=1000)
    y: Optional[float] = Field(None, ge=-50, le=1000)


def _refused(exc: bed_shims.ShimError) -> HTTPException:
    """A mount no shim fits, or a place that is no screw or corner of the plate, is 422;
    a printer the site has not got, or one with no profile, no screws or no pinned board,
    404."""
    return HTTPException(
        status_code=422 if isinstance(exc, (bed_shims.NotAMount, bed_shims.NotAPosition)) else 404,
        detail=str(exc),
    )


def _nozzle(site: str, printer: str) -> Dict[str, float]:
    """Where the nozzle of the board pinned at ``printer`` stands now: 409 for a board not
    connected, a job holding its port, or X and Y not homed since it started."""
    from ..firmware import devices
    from ..firmware.toolchains import ToolchainError

    board = bed_shims.pinned_board(site, printer)
    port = devices.port_of_board(board)
    if port is None:
        raise HTTPException(
            status_code=409, detail=f"{printer}'s board, {board}, is not connected: plug it in"
        )
    try:
        at = devices.nozzle_at(port)
    except (ToolchainError, ValueError) as exc:  # PortHeld is one: a job holds the port
        raise HTTPException(status_code=409, detail=str(exc)) from None
    if not {"X", "Y"} <= set(at["homed"]):
        raise HTTPException(
            status_code=409,
            detail=f"{printer} has not homed X and Y since its board started, so its position "
            "measures nothing yet: Home all in its Machine, then jog over the place and keep it",
        )
    return at


@router.get("/bed/{site}/{printer}")
def bed_story(site: str, printer: str) -> Dict[str, Any]:
    """The printer's readings, their differences, its shims and its mount: 404 with the
    reason for a printer with no profile, no screws or no pinned board. A board with no
    probe yet answers its readings, and shims that say what they lack."""
    try:
        return bed_shims.story(site, printer)
    except bed_shims.ShimError as exc:
        raise _refused(exc) from None


@router.put("/bed/{site}/{printer}/mount")
def bed_mount(site: str, printer: str, body: MountRequest) -> Dict[str, Any]:
    """Keep what a person measured of the printer's mounts, and say what the shims fit."""
    try:
        kept = bed_shims.keep_mount(
            site, printer, screw=body.screw, hole_d=body.hole_d, outer_d=body.outer_d
        )
    except bed_shims.ShimError as exc:
        raise _refused(exc) from None
    return bed_shims.mount_json(kept)


@router.put("/bed/{site}/{printer}/where/{what}")
def bed_where(site: str, printer: str, what: str, body: WhereRequest) -> Dict[str, Any]:
    """Keep where the nozzle stands over one of the printer's screws or its plate's
    corners: given, or read from its board (``here``)."""
    if body.here:
        at = _nozzle(site, printer)
        x, y = at["x"], at["y"]
    elif body.x is not None and body.y is not None:
        x, y = body.x, body.y
    else:
        raise HTTPException(status_code=422, detail="say where: {here: true}, or x and y in mm")
    try:
        return bed_shims.keep_position(site, printer, what, x, y)
    except bed_shims.ShimError as exc:
        raise _refused(exc) from None
