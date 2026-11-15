"""The tour's routes: the journeys a stage at a time, each stage with its feedback, and a
person's word on a stage kept (apothecary/tour.py)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import tour

router = APIRouter()


class Feedback(BaseModel):
    stage: str
    verdict: str
    note: str = ""


@router.get("/tour")
async def tour_document():
    """The journeys in their order, each stage with its words, what to try on it and
    the latest feedback on it, and the commit the server runs."""
    return tour.document()


@router.get("/tour/feedback")
async def tour_feedback_kept():
    """Every word kept, oldest first: a stage, ``works`` or ``off`` with what is off,
    the moment, and the commit the server ran."""
    return {"feedback": tour.said()}


@router.post("/tour/feedback", status_code=201)
async def tour_feedback(body: Feedback):
    """A person's word on one stage: ``works``, or ``off`` saying what is off."""
    try:
        return tour.say(body.stage, body.verdict, body.note)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except tour.Refused as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
