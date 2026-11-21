"""``GET /parts/{name}/motion``: a part's motion as the table the page plays.

A part that declares a motion (``BasePart.motion``) is answered with ``motion/1``
(``apothecary.motion.table``): the wrapper's own pose function sampled at its step, each
gap it names measured at each sample, and how far the page's way between two samples
can stray. Nothing here runs OpenSCAD; the page draws each piece once through ``POST
/parts/{name}/stl/generate`` with the piece parameter the table names.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError

from ..motion import table

router = APIRouter(tags=["parts"])


@router.get("/parts/{name}/motion")
def part_motion(
    name: str,
    params: Optional[str] = Query(
        None,
        description="The part's values as JSON, as Parameters stages them; its own where "
        "left out. The motion's parameter and the piece parameter are not read.",
    ),
) -> Dict[str, Any]:
    """The part's motion, sampled: 404 for a part that declares none, 422 for values its
    model refuses."""
    from ..api import load_part_wrapper

    part = load_part_wrapper(name)
    if not part.has_motion or part.params_model is None:
        raise HTTPException(status_code=404, detail=f"{part.name} declares no motion")
    try:
        given = json.loads(params) if params else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"params is not JSON: {exc}") from None
    if not isinstance(given, dict):
        raise HTTPException(status_code=400, detail="params is a JSON object of the part's values")
    known = set(part.params_model.model_fields)
    unknown = sorted(set(given) - known)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"unknown parameter(s): {', '.join(unknown)}. {part.name} declares: "
            f"{', '.join(sorted(known))}",
        )
    motion = None
    try:
        values = part.params_model(**given).model_dump()
        motion = part.motion(values)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if motion is None:
        raise HTTPException(status_code=404, detail=f"{part.name} has no motion with these values")
    return table(motion, values)
