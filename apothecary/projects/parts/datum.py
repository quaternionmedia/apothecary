"""datum — a modular control-surface enclosure.

A tray carrying one board, opening on one edge for USB-C and thinned over the
antenna. It is parametric in the board it carries, so the defaults render a
coherent object with no knowledge of any particular PCB — which is the datum
project's own requirement for parts that live here.

The board's numbers come from a
:class:`~apothecary.models.blackbox.BlackBoxProvider`, so the same part serves
a hand-entered stub today and a real KiCad outline later without any change
here. :func:`params_for` is the whole adapter.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from apothecary.models import PrintSettings, Vector3D
from apothecary.models.blackbox import BlackBox, BlackBoxProvider

from .base import BasePart
from .skeleton import ROOT

# Follows parts/footpedal/button.scad, per the datum project's record on
# enclosure parts: house constants are inherited, not restated per part.
HOUSE_WALL = 2.4
HOUSE_TOLERANCE = 0.2
HOUSE_CAP_RADIUS = 2.0


class DatumParams(BaseModel):
    """Parameters for the datum enclosure.

    Defaults describe a generic small-board tray. They are deliberately not
    "the T1-Core enclosure": a part that only makes sense as one project's
    accessory belongs in that project.
    """

    board_w: float = Field(40.0, gt=0, description="Board width (X) in mm")
    board_d: float = Field(30.0, gt=0, description="Board depth (Y) in mm")
    board_h: float = Field(1.6, gt=0, description="Bare board thickness (Z) in mm")
    mount_inset: float = Field(3.5, gt=0, description="Mounting hole inset from board edge, mm")
    mount_hole: float = Field(2.2, gt=0, description="Nominal mounting hole diameter, mm")

    wall: float = Field(HOUSE_WALL, gt=0, description="Wall thickness, mm")
    tol: float = Field(HOUSE_TOLERANCE, ge=0, description="Fit clearance per side, mm")
    r_cap: float = Field(HOUSE_CAP_RADIUS, ge=0, description="Corner radius, mm")

    standoff: float = Field(3.0, ge=0, description="Board underside to floor, mm")
    headroom: float = Field(8.0, ge=0, description="Clear height above the board, mm")
    usb_w: float = Field(10.0, gt=0, description="USB-C opening width, mm")
    usb_h: float = Field(4.0, gt=0, description="USB-C opening height, mm")
    antenna_band: float = Field(8.0, ge=0, description="Height of the thinned antenna strip, mm")
    antenna_wall: float = Field(0.8, gt=0, description="Wall thickness over the antenna, mm")

    @property
    def outer_w(self) -> float:
        return self.board_w + 2 * self.tol + 2 * self.wall

    @property
    def outer_d(self) -> float:
        return self.board_d + 2 * self.tol + 2 * self.wall

    @property
    def outer_h(self) -> float:
        return self.standoff + self.board_h + self.headroom + self.wall

    def to_scad_overrides(self) -> dict[str, float]:
        """The `-D name=value` set for rendering this iteration."""
        return {k: float(v) for k, v in self.model_dump().items()}


def params_for(board: BlackBox, **overrides: float) -> DatumParams:
    """Derive enclosure parameters from a black box.

    This is the entire adapter between "something described the board" and
    "the enclosure fits it". A provider swap is invisible past this line.
    """
    env = board.envelope
    inset = (
        min(
            min(m.position.x, env.width - m.position.x, m.position.y, env.height - m.position.y)
            for m in board.mounts
        )
        if board.mounts
        else DatumParams.model_fields["mount_inset"].default
    )
    hole = (
        board.mounts[0].hole_diameter
        if board.mounts
        else DatumParams.model_fields["mount_hole"].default
    )

    values: dict[str, float] = {
        "board_w": env.width,
        "board_d": env.height,  # this library's height is the Y extent
        "board_h": env.depth,  # and depth is Z
        "mount_inset": inset,
        "mount_hole": hole,
    }

    for keepout in board.keepouts:
        if keepout.name == "usb-c-mating":
            values["usb_w"] = keepout.box.width
            values["usb_h"] = keepout.box.depth
        elif keepout.name == "antenna":
            values["antenna_band"] = keepout.box.depth

    values.update(overrides)
    return DatumParams(**values)


def create(metadata_root: Path) -> BasePart:
    """Create the datum part instance."""
    scad = metadata_root / "parts" / "datum" / "datum.scad"
    return BasePart(
        name="datum",
        source_file=scad,
        description=(
            "Parametric enclosure for a small control-surface board: USB-C edge "
            "opening, thinned antenna wall, four self-tapping standoffs. Signal "
            "only — never a barrier between a person and a conductor."
        ),
        params_model=DatumParams,
        category="electronics",
        tags=["enclosure", "control-surface", "usb-c", "esp", "datum", "parametric"],
        print_settings=PrintSettings(
            nozzle_diameter=0.4,
            layer_height=0.2,
            wall_thickness=HOUSE_WALL,
            tolerance=HOUSE_TOLERANCE,
        ),
        display_rotation=Vector3D(),
    )


def create_for(
    metadata_root: Path,
    provider: BlackBoxProvider,
    board_name: str = "t1-core",
) -> tuple[BasePart, DatumParams]:
    """The part plus the parameters that fit a named board.

    Returned together because an iteration is the pair: geometry alone does not
    say which board it was cut for.
    """
    return create(metadata_root), params_for(provider.get(board_name))


DEFAULT = create(ROOT)
