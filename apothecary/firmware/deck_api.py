"""Routes for the Stream Deck + (``firmware/deck.py``): the decks found, one as it is
drawn, a key or the strip set, the events heard, and a simulated deck's events given.

Listing opens nothing. Every other route opens the deck it names, once, and keeps it
open until ``POST /firmware/decks/{id}/release``.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import deck as decks
from . import deck_control
from .deck import DeckUnavailable

router = APIRouter(prefix="/firmware/decks", tags=["firmware"])


class DrawRequest(BaseModel):
    text: str = Field(max_length=40)
    small: Optional[str] = Field(None, max_length=40)
    colour: Optional[str] = Field(None, max_length=9)


class BrightnessRequest(BaseModel):
    percent: int = Field(ge=0, le=100)


class ControlRequest(BaseModel):
    on: bool


class EventRequest(BaseModel):
    kind: str
    index: int = Field(0, ge=0)
    value: object


def _deck(deck_id: str):
    try:
        return decks.get_decks().get(deck_id)
    except KeyError:
        raise HTTPException(
            404, f"no deck {deck_id!r}: GET /firmware/decks lists what is found"
        ) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except DeckUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


def _said(exc: ValueError) -> HTTPException:
    return HTTPException(422, str(exc))


@router.get("")
def list_decks():
    try:
        found = decks.get_decks().list()
    except DeckUnavailable as exc:
        return {"decks": [], "problem": str(exc)}
    return {"decks": [d.model_dump() for d in found], "problem": None}


@router.get("/{deck_id}")
def deck_state(deck_id: str):
    return _deck(deck_id).state()


@router.put("/{deck_id}/keys/{index}")
def set_key(deck_id: str, index: int, body: DrawRequest):
    deck = _deck(deck_id)
    try:
        deck.set_key(index, body.text, body.colour, body.small)
    except ValueError as exc:
        raise _said(exc) from exc
    return deck.state()["keys_drawn"][str(index)]


@router.put("/{deck_id}/strip")
def set_strip(deck_id: str, body: DrawRequest):
    deck = _deck(deck_id)
    try:
        deck.set_strip(body.text, body.colour, body.small)
    except ValueError as exc:
        raise _said(exc) from exc
    return deck.state()["strip_drawn"]


@router.put("/{deck_id}/brightness")
def set_brightness(deck_id: str, body: BrightnessRequest):
    deck = _deck(deck_id)
    deck.set_brightness(body.percent)
    return {"brightness": deck.brightness}


def _jpeg(drawn: Optional[dict], what: str) -> Response:
    if drawn is None:
        raise HTTPException(404, f"{what} has not been drawn from here")
    return Response(drawn["jpeg"], media_type="image/jpeg")


@router.get("/{deck_id}/keys/{index}/image")
def key_image(deck_id: str, index: int):
    return _jpeg(_deck(deck_id).keys.get(index), f"key {index}")


@router.get("/{deck_id}/strip/image")
def strip_image(deck_id: str):
    return _jpeg(_deck(deck_id).strip, "the strip")


@router.get("/{deck_id}/events")
def events(deck_id: str, since: int = Query(0, ge=0)):
    deck = _deck(deck_id)
    return {"events": [e.to_json() for e in deck.events(since)], "last": deck.state()["last_event"]}


@router.post("/{deck_id}/events", status_code=201)
def give_event(deck_id: str, body: EventRequest):
    deck = _deck(deck_id)
    try:
        return deck.inject(body.kind, body.index, body.value).to_json()
    except DeckUnavailable as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise _said(exc) from exc


@router.post("/{deck_id}/release")
def release(deck_id: str):
    return {"released": decks.get_decks().release(deck_id)}


@router.get("/{deck_id}/control")
def control_state(deck_id: str):
    """Whether the layout that jogs the machines runs on this deck, and what it last did."""
    controller = deck_control.running(deck_id)
    return controller.state() if controller else {"running": False}


@router.post("/{deck_id}/control")
def control(deck_id: str, body: ControlRequest):
    """Start the layout on this deck (opening it) or stop it. The deck arms nothing: a
    machine's control is armed in its Machine window."""
    _deck(deck_id)  # a deck that is not there, or cannot be opened, says so first
    if not body.on:
        deck_control.stop(deck_id)
        return {"running": False}
    return deck_control.start(deck_id).state()
