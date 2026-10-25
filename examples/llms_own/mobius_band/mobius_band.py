"""A Möbius band swept from slabs: the solid form of the ribbon the airgap part wears.

The band is a ring of radius ``R`` whose cross-section, ``width`` by ``thickness``, turns
about the ring's tangent by ``half_twists * 180`` degrees in one trip round. With an odd
count it has one side and one edge; with an even one, two of each, and the band is a
twisted belt. It is built from ``segments`` thin slabs, each placed and turned by the
scene's own transforms, and hulled with its neighbour -- one convex hull per segment, so
OpenSCAD renders it without a slow boolean.

    uv run python examples/llms_own/mobius_band/mobius_band.py > mobius_band.scad
    uv run python examples/llms_own/mobius_band/mobius_band.py --json > mobius_band.json

Tools: Claude Code (Anthropic) drafted this contribution; a human ratifies before merge.
"""

from __future__ import annotations

import argparse
import json
import math

from apothecary import Cube, Hull, Rotate, Scene, Translate, Union, Vector3D


def slab(radius: float, width: float, thickness: float, angle: float, twist: float) -> Translate:
    """One rib of the band at ring angle ``angle``, its section turned by ``twist``
    about the tangent: a thin cube, turned, stood on the ring, carried to its place."""
    rib = Cube(size=Vector3D(x=width, y=0.6, z=thickness), center=True)
    turned = Rotate(a=Vector3D(x=0, y=twist, z=0), children=[rib])
    stood = Rotate(a=Vector3D(x=0, y=0, z=angle), children=[turned])
    return Translate(
        v=Vector3D(
            x=radius * math.cos(math.radians(angle)), y=radius * math.sin(math.radians(angle)), z=0
        ),
        children=[stood],
    )


def mobius_band(
    radius: float = 40.0,
    width: float = 14.0,
    thickness: float = 2.0,
    half_twists: int = 1,
    segments: int = 72,
) -> Scene:
    """The band as a scene: ``segments`` hulls, each of two neighbouring slabs."""
    ribs = [
        slab(radius, width, thickness, 360 * i / segments, 180 * half_twists * i / segments)
        for i in range(segments)
    ]
    pieces = [
        Hull(children=[ribs[i], ribs[(i + 1) % segments]], comment=f"segment {i}")
        for i in range(segments)
    ]
    sides = "one side and one edge" if half_twists % 2 else "two sides and two edges"
    return Scene(
        name=f"mobius_band_{half_twists}",
        objects=[
            Union(
                children=pieces,
                comment=f"a band of {segments} segments, {half_twists} half-twist(s): {sides}",
            )
        ],
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--radius", type=float, default=40.0, help="ring radius [mm]")
    ap.add_argument("--width", type=float, default=14.0, help="band width [mm]")
    ap.add_argument("--thickness", type=float, default=2.0, help="band thickness [mm]")
    ap.add_argument(
        "--half-twists",
        type=int,
        default=1,
        help="half-twists in one trip round; odd is a Möbius band",
    )
    ap.add_argument("--segments", type=int, default=72, help="slabs round the ring")
    ap.add_argument(
        "--json", action="store_true", help="print the scene as a document instead of OpenSCAD"
    )
    args = ap.parse_args()
    scene = mobius_band(args.radius, args.width, args.thickness, args.half_twists, args.segments)
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
