"""What a part says of how it is cut, and what a toolpath records.

Everything is in millimetres, with the work zero at the stock's front-left top
corner: X to the right, Y to the back, Z up, so every cut goes to a negative Z.
That is where a person zeroes the router before a cut (``docs/cam.md``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from ..firmware import grbl
from ..firmware.gcode import SPINDLE_MAX_RPM


class Tool(BaseModel):
    """One end mill, the only tool a toolpath here uses."""

    diameter: float = Field(6.0, gt=0, le=25)
    flutes: int = Field(2, ge=1, le=4)
    label: str = "6 mm two-flute end mill"


class Feeds(BaseModel):
    """Feeds and speed, each within the router's bounds (``grbl.FEED_MAX``,
    ``gcode.SPINDLE_MAX_RPM``): what the toolpath writes on every move."""

    cut: float = Field(800.0, gt=0, le=grbl.FEED_MAX)  # mm/min along a cut
    plunge: float = Field(300.0, gt=0, le=grbl.FEED_MAX)  # mm/min straight down
    rpm: int = Field(12000, gt=0, le=SPINDLE_MAX_RPM)


class Stock(BaseModel):
    """The blank the part is cut from, its front-left top corner the work zero."""

    x: float = Field(..., gt=0)
    y: float = Field(..., gt=0)
    thickness: float = Field(..., gt=0)


class Pocket(BaseModel):
    """A rectangular pocket, its front-left corner at (x, y), cut ``depth`` down."""

    kind: Literal["pocket"] = "pocket"
    x: float
    y: float
    w: float = Field(..., gt=0)
    h: float = Field(..., gt=0)
    depth: float = Field(..., gt=0)


class Hole(BaseModel):
    """A round hole at (x, y): bored in circles when it is wider than the tool,
    plunged when it is the tool's size."""

    kind: Literal["hole"] = "hole"
    x: float
    y: float
    diameter: float = Field(..., gt=0)
    depth: float = Field(..., gt=0)


class Outline(BaseModel):
    """The part's outline, a ``w`` by ``h`` rectangle with its front-left corner at
    (x, y), cut around from outside ``depth`` down: through the stock when the depth
    reaches its thickness."""

    kind: Literal["outline"] = "outline"
    x: float = 0.0
    y: float = 0.0
    w: float = Field(..., gt=0)
    h: float = Field(..., gt=0)
    depth: float = Field(..., gt=0)


Operation = Union[Pocket, Hole, Outline]


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
