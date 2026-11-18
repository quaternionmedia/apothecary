"""What a part needs that is not printed: bought, counted and sized.

A part's wrapper lists them (``BasePart.bought``): a dowel, a bearing, a pin, an insert
for a pocket -- each with how many, its size in millimetres, and the part's interfaces
it goes in, by name, where the part has a socket for it. Nothing listed here is in the
part's STL: the SCAD cuts the hole and the list says what goes in it.

``material`` is said only where the part's geometry depends on one; an insert whose
material is the owner's choice says None, and its ``notes`` say what the choice is for.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

# How much wider a printed pocket is drawn than the round insert it takes, mm across:
# a 6 mm disc in a 6.2 mm pocket.
INSERT_FIT = 0.2


class Bought(BaseModel):
    """One kind of thing a part needs and does not print: ``count`` of them, each
    ``diameter`` across and ``length`` along its axis (a disc's thickness, a bearing's
    width), a bearing's ``bore``; ``goes_in`` the part's interfaces it sits in, one
    each, where it has any."""

    name: str = Field(..., min_length=1)
    count: int = Field(..., ge=1)
    diameter: float = Field(..., gt=0, description="across, mm: a bearing's outside")
    length: Optional[float] = Field(
        None, gt=0, description="along its axis, mm; None where the part does not set it"
    )
    bore: Optional[float] = Field(None, gt=0, description="a bearing's bore, mm")
    goes_in: List[str] = Field(
        default_factory=list, description="the interfaces it sits in, by name, one each"
    )
    material: Optional[str] = Field(
        None, description="what it is made of, where the part depends on it; None: not chosen"
    )
    notes: str = ""

    @model_validator(mode="after")
    def _one_in_each(self) -> "Bought":
        if self.goes_in and len(self.goes_in) != self.count:
            raise ValueError(
                f"{self.count} of {self.name} go in {len(self.goes_in)} places: one in each"
            )
        if len(set(self.goes_in)) != len(self.goes_in):
            raise ValueError(f"{self.name} names a place twice: {self.goes_in}")
        return self


__all__ = ["INSERT_FIT", "Bought"]
