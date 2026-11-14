"""The tour's routes: the roadmap's lines as stops, each with its answer, and a person's
word on a stop kept (apothecary/tour.py)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import tour

router = APIRouter()


class Answer(BaseModel):
    stop: str
    verdict: str
    note: str = ""


@router.get("/tour")
async def tour_document():
    """The roadmap's lines in order, each with its stops -- a journey's stages, a
    walkthrough page -- each stop's latest answer, and the commit the server runs."""
    return tour.document()


@router.post("/tour/answers", status_code=201)
async def tour_answer(body: Answer):
    """A person's word on one stop: ``as shown``, or ``off`` saying what is off."""
    try:
        return tour.say(body.stop, body.verdict, body.note)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except tour.Refused as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
