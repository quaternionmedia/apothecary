"""What the slicer seam answers: a slicer's status, a value and where it came from,
and the record a slice leaves beside the G-code it kept."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field

# Where a value of a slice came from: the part or piece declared it, the
# printer's profile set it (OrcaSlicer's own, or what the profile kept with the
# printer's part holds over it), or apothecary set it for every slice.
Origin = Literal["declared", "printer", "apothecary"]


class SlicerTool(BaseModel):
    """The program a slicer module runs, and what found it."""

    name: str
    path: Optional[str] = None
    found_by: Optional[str] = None  # the variable's name, "tools dir" or "PATH"
    version: Optional[str] = None
    ok: bool = False


class SlicerStatus(BaseModel):
    """One slicer module: what it slices, whether it is installed, and the release
    pinned for an install."""

    id: str
    label: str
    technology: str  # "FFF": what kind of printer it slices for
    inputs: List[str]  # the model files it takes
    writes: List[str]  # the files it writes
    install: str  # the command that installs it
    pinned: str  # the release an install fetches
    tool: SlicerTool
    profiles: Optional[str] = None  # where its own printer profiles are, beside it
    installed: Optional[str] = None  # the release `install` put in the tools dir, if any
    chosen: bool = False  # the one a slice uses
    problems: List[str] = Field(default_factory=list)  # why a slice cannot run
    notes: List[str] = Field(default_factory=list)  # what is worth knowing, and does not stop one

    @property
    def ok(self) -> bool:
        return self.tool.ok and self.profiles is not None and not self.problems


class Setting(BaseModel):
    """One value a slice used, and where it came from."""

    name: str  # the slicer's own name for it (a part's, where the slicer has none)
    value: Any
    origin: Origin
    source: str  # in words: which part, which profile, which measurement
    note: Optional[str] = None  # how it was applied, when that is not plain


class Estimate(BaseModel):
    """What the slicer said the print will take, as it wrote it into the G-code."""

    time: Optional[str] = None  # its own words: "8m 56s"
    seconds: Optional[int] = None
    first_layer: Optional[str] = None
    filament_mm: Optional[float] = None
    filament_cm3: Optional[float] = None
    filament_g: Optional[float] = None
    layers: Optional[int] = None


class SlicerMessage(BaseModel):
    """An error or a warning the slicer gave, and the line of its output it was on."""

    level: Literal["error", "warning"]
    line: Optional[int] = None  # of the slicer's output, from 1; None for its result file
    text: str


class Bounds(BaseModel):
    """Where the extruding moves of a G-code file reach, in the printer's coordinates."""

    min: List[float]  # x, y, z
    max: List[float]


class Made(BaseModel):
    """What was sliced: a part, or a piece made from a picture."""

    kind: Literal["part", "piece"]
    name: str  # the part's name, or the piece's
    site: Optional[str] = None
    path: Optional[str] = None  # its node's path in the site, when it stands in one
    word: Optional[str] = None  # a piece's word


class SlicedFor(BaseModel):
    """The printer a slice was for: its part, and where it stands."""

    part: str  # the printer's part ("ender3"), which keeps its profile
    name: str  # what it is called: its node's name, or its part's
    site: Optional[str] = None
    path: Optional[str] = None
    port: Optional[str] = None


class SliceRecord(BaseModel):
    """A slice, kept beside the G-code it wrote: the file is the Print card's
    (``file_id``), and this is what made it."""

    file_id: str
    name: str  # the kept file's name
    at: datetime
    slicer: str  # the module's id
    slicer_label: Optional[str] = None  # what a person reads: "OrcaSlicer"
    slicer_version: Optional[str] = None
    made: Made
    printer: SlicedFor
    settings: List[Setting]
    estimate: Optional[Estimate] = None
    messages: List[SlicerMessage] = Field(default_factory=list)
    bounds: Optional[Bounds] = None
    lines: int = 0  # the lines the Print card would send
    problems: List[str] = Field(default_factory=list)  # the Print card's: why it may not be sent
