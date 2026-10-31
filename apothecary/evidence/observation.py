"""One thing said about one subject at one moment: ``apothecary.observation``.

The format is the family's, ``qm.observation`` version 1, tightened here: a
reader of the generic format reads every field below but the ``apothecary``
block, which is this instance's own and drops out cleanly. Tightened, never
relaxed: a property from a closed list, an origin from five kinds, a value or
the reason there is none, and never both.

| Field | Holds |
|---|---|
| ``subject`` | an address (``garage:printer_1``, ``garage:printer_1#heater:bed``) or a sighting (``usb:A106ZTEU``) |
| ``property``, ``value``, ``unit`` | what is said; ``value`` null is unread, and ``why`` says why |
| ``confidence`` | from 0 to 1 as the source gave it; null where it gives none |
| ``origin`` | ``stated``, ``measured``, ``read``, ``guessed`` or ``derived``, and ``by``, what produced it |
| ``at``, ``recorded_at`` | when it held, and when it was written |
| ``evidence`` | references to what it rests on, never the bytes: a poll, a pin, a frame |

The image models' plan (``docs/plans/image-models-through-qmcp-2026-10-30.md``)
reads and writes the same format; its properties join the list when it is built.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

GENERIC = "qm.observation"
FORMAT = "apothecary.observation"
VERSION = 1

Kind = Literal["stated", "measured", "read", "guessed", "derived"]

# Every property a subject may be said to have. A source with something new to
# say adds it here, where a test sees it.
PROPERTIES = frozenset(
    {
        "present",
        "state",
        "firmware",
        "plugged",
        "value",
        "temperature",
        "target",
        "progress",
        "position",
        "layer",
        "endstop",
        "filament",
        "moving",
        "clear",
    }
)

# ``site:node.path``, a facet after ``#`` (``#heater:bed``); or a source's own
# name for something nothing has said what it is (``usb:A106ZTEU``).
SUBJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*:[^\s#]+(?:#[a-z]+:[^\s#]+)?$")

RefKind = Literal["poll", "pin", "frame", "observation", "record"]


class Origin(BaseModel):
    """Where an observation came from: its kind, and what produced it."""

    model_config = ConfigDict(extra="forbid")

    kind: Kind
    by: str = Field(min_length=1)


class Ref(BaseModel):
    """One piece of evidence, by reference: a poll's id, a pin's address, a frame's
    path under the picture root."""

    model_config = ConfigDict(extra="forbid")

    kind: RefKind
    id: str = Field(min_length=1)


class Instance(BaseModel):
    """What apothecary's instance adds to the generic format."""

    model_config = ConfigDict(extra="forbid")

    # A reading off a picture: the camera, and how well it sees the subject.
    view: Optional[dict] = None
    # A guess: whether its model has passed its check for this property.
    trusted: Optional[bool] = None


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str
    property: str
    value: Any = None
    unit: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    origin: Origin
    at: datetime
    recorded_at: datetime
    evidence: List[Ref] = Field(default_factory=list)
    why: Optional[str] = None
    apothecary: Optional[Instance] = None

    @model_validator(mode="after")
    def _tightened(self) -> "Observation":
        if not SUBJECT.match(self.subject):
            raise ValueError(f"{self.subject!r} is not an address or a sighting")
        if self.property not in PROPERTIES:
            raise ValueError(f"{self.property!r} is not a property an observation may have")
        if self.value is None and not self.why:
            raise ValueError("an unread observation says why it is unread")
        if self.value is not None and self.why:
            raise ValueError("an observation with a value has no why")
        if self.at.tzinfo is None or self.recorded_at.tzinfo is None:
            raise ValueError("an observation's moments carry their time zone")
        return self

    @property
    def node(self) -> str:
        """The subject without its facet: ``garage:printer_1`` for ``…#heater:bed``."""
        return self.subject.split("#", 1)[0]
