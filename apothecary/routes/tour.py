"""The tour's routes: the walkthrough as stops and steps, each with its answer, and a
person's verdict on a step kept (apothecary/tour.py)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import tour

router = APIRouter()


class Verdict(BaseModel):
    page: str
    step: int
    verdict: str
    note: str = ""


@router.get("/tour")
async def tour_document():
    """Every walkthrough page as a stop, its steps as its test recorded them, each
    step's latest verdict, and the commit the server runs."""
    return tour.document()


@router.post("/tour/verdicts", status_code=201)
async def tour_verdict(body: Verdict):
    """A person's word on one step: ``as shown``, or ``off`` saying what is off."""
    try:
        return tour.say(body.page, body.step, body.verdict, body.note)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except tour.Refused as e:
        raise HTTPException(status_code=422, detail=str(e)) from None


class StageVerdict(BaseModel):
    journey: str
    stage: str
    verdict: str
    note: str = ""


@router.get("/tour/journeys")
async def tour_journeys():
    """Each journey's stages, each with a person's latest word on it."""
    return tour.staged()


@router.post("/tour/stages", status_code=201)
async def tour_stage(body: StageVerdict):
    """A person's word on one stage of a journey."""
    try:
        return tour.say_stage(body.journey, body.stage, body.verdict, body.note)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except tour.Refused as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
