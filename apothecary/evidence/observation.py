"""One thing said about one subject at one moment: ``apothecary.observation``.

The format is the family's, ``qm.observation`` version 1, tightened here: a
reader of the generic format reads every field below but the ``apothecary``
block, which is this instance's own and drops out cleanly (``generic()``).
Tightened, never relaxed: a property from a closed list, an origin from five
kinds, a value or the reason there is none, and never both.

| Field | Holds |
|---|---|
| ``format``, ``version`` | ``apothecary.observation`` 1; ``generic()`` names ``qm.observation`` |
| ``subject`` | an address (``garage:printer_1``, ``garage:printer_1#heater:bed``) or a sighting (``usb:A106ZTEU``); or a region of a picture nothing has said what it is (``{"sighting": {picture, region, box}}``) |
| ``property``, ``value``, ``unit`` | what is said; ``value`` null is unread, and ``why`` says why |
| ``confidence`` | from 0 to 1 as the source gave it; null where it gives none |
| ``origin`` | ``stated``, ``measured``, ``read``, ``guessed`` or ``derived``, and ``by``, what produced it: a reader's or an instrument's name, or a model's name, version and weights |
| ``at``, ``recorded_at`` | when it held, and when it was written |
| ``evidence`` | references to what it rests on, never the bytes: a poll, a pin, a frame, a picture's region, a model's invocation |

The image models' plan (``docs/plans/image-models-through-qmcp-2026-10-30.md``)
reads and writes the same format; a region of a picture, the models' properties
and ``overruled`` are its.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)

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
        # The image models' (docs/plans/image-models-through-qmcp-2026-10-30.md), and
        # rgb, a colour's measured sRGB, which only a reader of pixels gives.
        "label",
        "quantity",
        "size",
        "shape",
        "material",
        "colour",
        "covered",
        "match",
        "rgb",
    }
)

# ``site:node.path``, a facet after ``#`` (``#heater:bed``); or a source's own
# name for something nothing has said what it is (``usb:A106ZTEU``).
SUBJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*:[^\s#]+(?:#[a-z]+:[^\s#]+)?$")

DIGEST = re.compile(r"^[0-9a-f]{64}$")

RefKind = Literal["poll", "pin", "frame", "observation", "record", "picture", "invocation"]

Box = Tuple[float, float, float, float]


def now() -> datetime:
    """This moment, in UTC, as an observation's times are written."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def _without_nones(dumped: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in dumped.items() if v is not None}


def _a_box(box: Optional[Box]) -> Optional[Box]:
    """Fractions of the picture as it is seen: left, top, right, bottom, from 0 at the
    top left to 1 at the bottom right."""
    if box is not None:
        left, top, right, bottom = box
        if not (0 <= left <= right <= 1 and 0 <= top <= bottom <= 1):
            raise ValueError(f"{list(box)} is not a box in fractions of the picture")
    return box


class By(BaseModel):
    """What produced an observation: a reader's or an instrument's name, or a model's
    name, version and weights' digest, with qmcp's tool and the engine that ran it.
    No model answering is ``qmcp`` by that tool."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    version: Optional[str] = None
    weights_sha256: Optional[str] = None
    tool: Optional[str] = None
    engine: Optional[str] = None

    @model_serializer(mode="wrap")
    def _dumped(self, handler):
        return _without_nones(handler(self))


class Origin(BaseModel):
    """Where an observation came from: its kind, and what produced it."""

    model_config = ConfigDict(extra="forbid")

    kind: Kind
    by: By

    @field_validator("by", mode="before")
    @classmethod
    def _a_name_is_a_record(cls, by: Any) -> Any:
        # A name alone is the record of it: what a log written as ``by: "…"`` holds.
        return {"name": by} if isinstance(by, str) else by

    def key(self) -> str:
        """The origin's name, which switching it off and trusting it look up: a
        reader's (``plain/colour``) or an instrument's, ``qmcp/<model>@<version>``
        for a model through qmcp, ``qmcp`` when none answered, and ``person``."""
        if self.kind == "stated":
            return "person"
        if self.by.tool is not None:
            if self.by.name == "qmcp":
                return "qmcp"
            return model_key(self.by.name, self.by.version)
        return self.by.name


def model_key(name: str, version: Optional[str]) -> str:
    """A model's origin through qmcp, as its guesses carry it and qmcp lists it."""
    return f"qmcp/{name}@{version or '?'}"


class Ref(BaseModel):
    """One piece of evidence, by reference: a poll's id, a pin's address, a frame's
    path under the picture root, a picture's digest with its path and the region's
    box, a model's invocation in qmcp."""

    model_config = ConfigDict(extra="forbid")

    kind: RefKind
    id: str = Field(min_length=1)
    path: Optional[str] = None
    box: Optional[Box] = None

    @model_validator(mode="after")
    def _a_picture_by_its_digest(self) -> "Ref":
        if self.kind == "picture":
            if not DIGEST.match(self.id):
                raise ValueError("a picture is referred to by its SHA-256")
            _a_box(self.box)
        elif self.path is not None or self.box is not None:
            raise ValueError("only a picture's reference has a path and a box")
        return self

    @model_serializer(mode="wrap")
    def _dumped(self, handler):
        return _without_nones(handler(self))


class Region(BaseModel):
    """A region of a picture: the picture's SHA-256, the asker's name for the region,
    and its box."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    picture: str = Field(pattern=DIGEST.pattern)
    region: str = Field(min_length=1)
    box: Box

    @field_validator("box")
    @classmethod
    def _in_the_picture(cls, box: Box) -> Box:
        return _a_box(box)


class Sighting(BaseModel):
    """A subject that is a region of a picture nothing has said what it is. A link
    -- a person's pin, a face pinned by its corners -- attributes it to an address;
    a model's label never does."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sighting: Region


class Instance(BaseModel):
    """What apothecary's instance adds to the generic format."""

    model_config = ConfigDict(extra="forbid")

    # A reading off a picture: the camera, and how well it sees the subject.
    view: Optional[dict] = None
    # A guess: whether its model has passed its check for this property.
    trusted: Optional[bool] = None
    # A guess: whether a person's word on the same subject and property overruled it.
    overruled: Optional[bool] = None


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["apothecary.observation"] = FORMAT
    version: Literal[1] = VERSION
    subject: Union[str, Sighting]
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
        if isinstance(self.subject, str) and not SUBJECT.match(self.subject):
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
    def node(self) -> Optional[str]:
        """The subject without its facet: ``garage:printer_1`` for ``…#heater:bed``;
        none for a region of a picture."""
        return self.subject.split("#", 1)[0] if isinstance(self.subject, str) else None

    @property
    def region(self) -> Optional[Region]:
        """The region of a picture the subject is, or none for an address."""
        return self.subject.sighting if isinstance(self.subject, Sighting) else None

    @property
    def unread(self) -> bool:
        return self.value is None

    @property
    def block(self) -> Instance:
        """The ``apothecary`` block, empty when there is none."""
        return self.apothecary or Instance()

    def generic(self) -> Dict[str, Any]:
        """The family's fields alone, as any family app reads them: ``qm.observation``,
        without the ``apothecary`` block."""
        dumped = self.model_dump(mode="json", exclude={"apothecary"})
        dumped["format"] = GENERIC
        return dumped
