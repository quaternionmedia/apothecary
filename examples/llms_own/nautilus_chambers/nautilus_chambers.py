"""A nautilus of hulled chambers along a logarithmic spiral: the curve the airgap's rotor steps along.

The spiral is r = r0 * growth ** (theta / 360): every turn the radius grows by ``growth``.
Along it stand ``chambers`` cylinders whose radius and height grow with r, each hulled with
the next into one chamber; the chambers' union is the shell. The same chain at ``hollow`` of
the size, standing on a ``floor`` and out through the top, is cut from it, and a ``wall``
across the tube at every post is put back, clipped to the shell: a tray of open chambers
with the septa between them standing. With ``hollow`` 0 the shell is solid.

    uv run python examples/llms_own/nautilus_chambers/nautilus_chambers.py > nautilus_chambers.scad
    uv run python examples/llms_own/nautilus_chambers/nautilus_chambers.py --json > nautilus_chambers.json

Tools: Claude Code (Anthropic) drafted this contribution; a human ratifies before merge.
"""

from __future__ import annotations

import argparse
import json
import math

from apothecary import (
    Cube,
    Cylinder,
    Difference,
    Hull,
    Intersection,
    Rotate,
    Scene,
    Translate,
    Union,
    Vector3D,
)


def post(r0: float, growth: float, theta: float, size: float, z0: float, tall: float) -> Translate:
    """A cylinder standing on the spiral at angle ``theta``: its radius a ``size`` of r there,
    ``tall`` times the chamber's height, its foot at ``z0``."""
    r = r0 * growth ** (theta / 360)
    column = Cylinder(h=max(0.4, tall * 0.6 * r), r=max(0.2, 0.42 * r * size), center=False, fn=24)
    return Translate(
        v=Vector3D(x=r * math.cos(math.radians(theta)), y=r * math.sin(math.radians(theta)), z=z0),
        children=[column],
    )


def shell(r0: float, growth: float, turns: float, chambers: int) -> Union:
    """The chambers end to end: each the hull of the post at its start and the post at its end."""
    step = 360 * turns / chambers
    return Union(
        children=[
            Hull(
                children=[
                    post(r0, growth, i * step, 1.0, 0.0, 1.0),
                    post(r0, growth, (i + 1) * step, 1.0, 0.0, 1.0),
                ],
                comment=f"chamber {i}",
            )
            for i in range(chambers)
        ]
    )


def hollows(
    r0: float, growth: float, turns: float, chambers: int, hollow: float, floor: float
) -> Union:
    """What is cut from the shell: the same chain at ``hollow`` of the size, standing on the
    floor and out through the top."""
    step = 360 * turns / chambers
    return Union(
        children=[
            Hull(
                children=[
                    post(r0, growth, i * step, hollow, floor, 2.0),
                    post(r0, growth, (i + 1) * step, hollow, floor, 2.0),
                ],
                comment=f"chamber {i}, opened",
            )
            for i in range(chambers)
        ]
    )


def septa(r0: float, growth: float, turns: float, chambers: int, wall: float) -> Union:
    """A wall across the tube at every post but the first and the last, square to the
    spiral (whose tangent leans atan(ln(growth) / 2 pi) ahead of a circle's)."""
    step = 360 * turns / chambers
    lean = math.degrees(math.atan(math.log(growth) / (2 * math.pi)))
    walls = []
    for i in range(1, chambers):
        theta = i * step
        r = r0 * growth ** (theta / 360)
        plate = Cube(size=Vector3D(x=wall, y=1.2 * r, z=0.6 * r), center=False)
        centred = Translate(v=Vector3D(x=-wall / 2, y=-0.6 * r, z=0), children=[plate])
        turned = Rotate(a=Vector3D(x=0, y=0, z=theta + lean), children=[centred])
        walls.append(
            Translate(
                v=Vector3D(
                    x=r * math.cos(math.radians(theta)), y=r * math.sin(math.radians(theta)), z=0
                ),
                children=[turned],
                comment=f"septum {i}",
            )
        )
    return Union(children=walls)


def nautilus(
    r0: float = 6.0,
    growth: float = 2.6,
    turns: float = 1.75,
    chambers: int = 28,
    hollow: float = 0.72,
    floor: float = 1.2,
    wall: float = 0.8,
) -> Scene:
    """The shell as a scene: the chain cut open from above, the septa put back across it,
    clipped to the shell so none stands proud of it."""
    body = shell(r0, growth, turns, chambers)
    if hollow > 0:
        opened = Difference(
            children=[body, hollows(r0, growth, turns, chambers, hollow, floor)],
            comment="the chambers cut open",
        )
        walls = Intersection(
            children=[septa(r0, growth, turns, chambers, wall), body],
            comment="the septa, inside the shell",
        )
        body = Union(children=[opened, walls])
    return Scene(name="nautilus_chambers", objects=[body])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--r0", type=float, default=6.0, help="radius at the first chamber [mm]")
    ap.add_argument("--growth", type=float, default=2.6, help="growth of the radius per turn")
    ap.add_argument("--turns", type=float, default=1.75, help="turns of the spiral")
    ap.add_argument("--chambers", type=int, default=28, help="chambers along it")
    ap.add_argument(
        "--hollow", type=float, default=0.72, help="the cut chain's size as a fraction; 0 is solid"
    )
    ap.add_argument("--floor", type=float, default=1.2, help="the floor's thickness [mm]")
    ap.add_argument("--wall", type=float, default=0.8, help="a septum's thickness [mm]")
    ap.add_argument(
        "--json", action="store_true", help="print the scene as a document instead of OpenSCAD"
    )
    args = ap.parse_args()
    scene = nautilus(
        args.r0, args.growth, args.turns, args.chambers, args.hollow, args.floor, args.wall
    )
    if args.json:
        print(
            json.dumps(
                scene.model_dump(mode="json", exclude_none=True, exclude={"version"}), indent=1
            )
        )
    else:
        print(scene.render())


if __name__ == "__main__":
    main()
