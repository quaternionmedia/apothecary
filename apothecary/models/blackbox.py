"""Black boxes: things apothecary places but does not author.

A PCB comes out of KiCad. A USB-C receptacle comes from a manufacturer. A
Wi-Fi module has a datasheet. Apothecary needs none of those tools to put a
hole in the right place — it needs the *envelope* the artifact occupies, the
points it fastens at, and the space that must stay clear around it.

So a black box is described by its interface, and where that description comes
from is a separate, replaceable question. `StubProvider` returns hand-entered
numbers from a datasheet, which is enough to get a scaffold together and is
what every artifact starts as. A `KiCadProvider` reading a real board outline
is the same interface with a better source behind it, and swapping it changes
no geometry code.

That split is deliberate: the seam is the `BlackBoxProvider` protocol, which
has more than one possible implementation, rather than a KiCad file format
this library would then be married to.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from .bounds import BoundingBox3D
from .vectors import Vector3D


class MountPoint(BaseModel):
    """A place the artifact is fastened, in the artifact's own frame."""

    name: str
    position: Vector3D
    hole_diameter: float = Field(
        2.2, gt=0, description="Nominal fastener hole; clearance is applied by the consumer"
    )
    depth: Optional[float] = Field(
        None, gt=0, description="Boss depth if the mount is a post rather than a through-hole"
    )


class Keepout(BaseModel):
    """Volume that must stay clear — a connector's mating space, an antenna."""

    name: str
    box: BoundingBox3D
    reason: str = Field(
        ...,
        description="Why this space is reserved. A keepout nobody can explain gets deleted "
        "by the next person who needs the room.",
    )


class BlackBox(BaseModel):
    """An artifact apothecary places without authoring.

    Coordinates are the artifact's own, origin at the envelope's minimum
    corner unless the provider says otherwise. Consumers position the whole
    box; they do not reach inside it.

    Note this library's axis naming on BoundingBox3D: `width` is X, `height`
    is Y and `depth` is Z. Board outlines are usually quoted width x height in
    that same order, so they line up — but it is worth reading twice.
    """

    name: str
    envelope: BoundingBox3D
    mounts: List[MountPoint] = Field(default_factory=list)
    keepouts: List[Keepout] = Field(default_factory=list)
    source: str = Field(
        "stub",
        description="Where this description came from: 'stub', 'kicad', 'datasheet'. "
        "Carried so a reader can tell a measured envelope from a guessed one.",
    )
    notes: Optional[str] = None

    @property
    def is_stub(self) -> bool:
        return self.source == "stub"


@runtime_checkable
class BlackBoxProvider(Protocol):
    """Source of black-box descriptions.

    Implementations available today: :class:`StubProvider`. A KiCad-backed
    provider reading a real board outline satisfies this same protocol, which
    is the point — geometry code depends on the protocol, never on the tool.
    """

    def get(self, name: str) -> BlackBox:  # pragma: no cover - protocol
        ...

    def names(self) -> List[str]:  # pragma: no cover - protocol
        ...


class StubProvider:
    """Hand-entered envelopes, good enough to build a scaffold against.

    Every entry is a stub until something measures it. `BlackBox.source` says
    so on each one, so a scene can report how much of itself is guessed.
    """

    def __init__(self, boxes: Optional[Dict[str, BlackBox]] = None) -> None:
        self._boxes: Dict[str, BlackBox] = dict(boxes or {})

    def register(self, box: BlackBox) -> "StubProvider":
        self._boxes[box.name] = box
        return self

    def get(self, name: str) -> BlackBox:
        try:
            return self._boxes[name]
        except KeyError:
            raise KeyError(
                f"No black box named {name!r}. Known: {sorted(self._boxes)}. "
                "Register one with StubProvider.register(), or point the consumer "
                "at a provider that can supply it."
            ) from None

    def names(self) -> List[str]:
        return sorted(self._boxes)
