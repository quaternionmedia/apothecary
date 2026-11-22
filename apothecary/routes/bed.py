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


def _refused(exc: bed_shims.ShimError) -> HTTPException:
    """A mount no shim fits is 422; a printer the site has not got, or one with no profile,
    no screws or no pinned board, 404."""
    return HTTPException(
        status_code=422 if isinstance(exc, bed_shims.NotAMount) else 404, detail=str(exc)
    )


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
