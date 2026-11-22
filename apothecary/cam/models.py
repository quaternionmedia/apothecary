"""What a part says of how it is cut, and what a toolpath records.

Everything is in millimetres, with the work zero at the stock's front-left top
corner: X to the right, Y to the back, Z up, so every cut goes to a negative Z.
That is where a person zeroes the router before a cut (``docs/cam.md``).

An operation may carry a ``name``: what a person calls it, and measures it by. A
named operation that is cut is a feature of the part a person measures with
calipers (``Feature``), and what it measures is fed back as the router's tool
allowance (``measured.py``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, Field

from ..firmware import grbl

# An operation's name, as a person calls it: a word or two, as typed in the page.
FEATURE_NAME = r"^[a-z][a-z ]{0,23}$"


class Tool(BaseModel):
    """One end mill, the only tool a toolpath here uses."""

    diameter: float = Field(6.0, gt=0, le=25)
    flutes: int = Field(2, ge=1, le=4)
    label: str = "6 mm two-flute end mill"


class Feeds(BaseModel):
    """Feeds and speed, each within the router's bounds (``grbl.FEED_MAX``,
    ``grbl.SPINDLE_MAX_RPM``): what the toolpath writes on every move."""

    cut: float = Field(800.0, gt=0, le=grbl.FEED_MAX)  # mm/min along a cut
    plunge: float = Field(300.0, gt=0, le=grbl.FEED_MAX)  # mm/min straight down
    rpm: int = Field(12000, gt=0, le=grbl.SPINDLE_MAX_RPM)


class Stock(BaseModel):
    """The blank the part is cut from, its front-left top corner the work zero."""

    x: float = Field(..., gt=0)
    y: float = Field(..., gt=0)
    thickness: float = Field(..., gt=0)


class Pocket(BaseModel):
    """A rectangular pocket, its front-left corner at (x, y), cut ``depth`` down: an
    inside size, measured along X."""

    kind: Literal["pocket"] = "pocket"
    x: float
    y: float
    w: float = Field(..., gt=0)
    h: float = Field(..., gt=0)
    depth: float = Field(..., gt=0)
    name: Optional[str] = Field(None, pattern=FEATURE_NAME)


class Hole(BaseModel):
    """A round hole at (x, y): bored in circles when it is wider than the tool,
    plunged when it is the tool's size. Bored, an inside size, measured across."""

    kind: Literal["hole"] = "hole"
    x: float
    y: float
    diameter: float = Field(..., gt=0)
    depth: float = Field(..., gt=0)
    name: Optional[str] = Field(None, pattern=FEATURE_NAME)


class Outline(BaseModel):
    """The part's outline, a ``w`` by ``h`` rectangle with its front-left corner at
    (x, y), cut around from outside ``depth`` down: through the stock when the depth
    reaches its thickness: an outside size, measured along X."""

    kind: Literal["outline"] = "outline"
    x: float = 0.0
    y: float = 0.0
    w: float = Field(..., gt=0)
    h: float = Field(..., gt=0)
    depth: float = Field(..., gt=0)
    name: Optional[str] = Field(None, pattern=FEATURE_NAME)


class Disc(BaseModel):
    """The part's outline as a circle of ``diameter`` centred at (x, y), cut around from
    outside ``depth`` down: an outside size, measured across."""

    kind: Literal["disc"] = "disc"
    x: float
    y: float
    diameter: float = Field(..., gt=0)
    depth: float = Field(..., gt=0)
    name: Optional[str] = Field(None, pattern=FEATURE_NAME)


class Groove(BaseModel):
    """A groove the tool's width, its centre along ``points`` -- two or more (x, y), a
    closed one ending where it began -- cut ``depth`` down: a stroke engraved, a smile's
    or a line's. Its width is the tool's whatever the router's allowance, so it is never
    a size a person measures."""

    kind: Literal["groove"] = "groove"
    points: List[Tuple[float, float]] = Field(..., min_length=2)
    depth: float = Field(..., gt=0)
    name: Optional[str] = Field(None, pattern=FEATURE_NAME)


Operation = Union[Pocket, Hole, Outline, Disc, Groove]


class Cuts(BaseModel):
    """The cuts that make a part from its stock, in the order they are made."""

    stock: Stock
    tool: Tool = Field(default_factory=Tool)
    feeds: Feeds = Field(default_factory=Feeds)
    operations: List[Operation] = Field(default_factory=list)
    step_down: float = Field(2.0, gt=0)  # the most a pass takes, in Z
    stepover: float = Field(0.5, gt=0, le=1)  # of the tool's diameter, between raster lines
    safe_z: float = Field(5.0, gt=0)  # where the tool travels between cuts


class OperationSaid(BaseModel):
    """One operation as the toolpath wrote it: its words, its passes, its lines."""

    index: int
    kind: str
    words: str
    passes: int
    lines: int
    cut: bool  # False when it was left out, with why in the toolpath's messages


class Feature(BaseModel):
    """A size of the part as cut that a person measures: a named operation's, inside
    (a pocket, a hole bored) or outside (an outline, a disc), as designed."""

    name: str
    side: Literal["inside", "outside"]
    size: float  # mm, as designed: across a hole or a disc, along X for a rectangle
    words: str  # what to measure, as a person reads it


class Allowance(BaseModel):
    """What the toolpath added to the tool's diameter in every offset it made, and
    where that came from: the router's measured correction (``measured.py``)."""

    value: float  # mm, on the tool's diameter
    origin: Literal["measured"] = "measured"
    source: str


class Bounds(BaseModel):
    """Where the tool goes, work coordinates, the tool's radius included."""

    min: List[float]
    max: List[float]


class Toolpath(BaseModel):
    """What ``toolpath.write`` made of a part's cuts."""

    lines: List[str]
    operations: List[OperationSaid]
    length_mm: float  # along every cut, feeds and plunges
    rapid_mm: float  # along every rapid
    time_s: float  # at the feeds written, rapids at the router's own rapid
    bounds: Optional[Bounds] = None
    messages: List[str] = Field(default_factory=list)  # what was left out or changed, and why
    features: List[Feature] = Field(default_factory=list)  # what a person measures of it


class CutFor(BaseModel):
    """The router a toolpath was written for: its node, and the port it was pinned to."""

    name: str
    site: Optional[str] = None
    path: Optional[str] = None
    port: Optional[str] = None


class CutRecord(BaseModel):
    """A toolpath kept beside the file the Cut card streams (``file_id``): what made it."""

    file_id: str
    name: str
    at: datetime
    part: str
    variant: Optional[str] = None  # the cached variant the page drew, when it was one
    params: Dict[str, object] = Field(default_factory=dict)
    router: CutFor
    stock: Stock
    tool: Tool
    feeds: Feeds
    operations: List[OperationSaid]
    lines: int  # the lines the Cut card would send
    length_mm: float
    time_s: float
    bounds: Optional[Bounds] = None
    messages: List[str] = Field(default_factory=list)
    problems: List[str] = Field(default_factory=list)  # the Cut card's: why it may not be sent
    features: List[Feature] = Field(default_factory=list)  # what a person measures of the piece
    allowance: Optional[Allowance] = None  # the router's correction it was written with
