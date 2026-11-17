# A gap that travels

**Hermetic.** Nothing here runs OpenSCAD; the parts' mirrors and
`apothecary.gap_geometry` compute.

The `airgap` part's gap is one number: its rotor turns rigidly about the one
axis inside a bore solved so the closest approach is the nominal gap
([page 17](17-a-part-that-computes-itself.md)). Once the rotor rolls, or its
bearing is a bend in the same piece as its stator, the gap is a function of
where round the machine it is read and of the pose of what moves, and the
place where it is least travels. This page measures that from geometry
alone; [docs/airgap.md](../docs/airgap.md#a-gap-that-is-not-one-number) is
the reference.

## One gap, and a gap that varies

Two concentric circles stand one gap apart all round:

    >>> from apothecary.gap_geometry import Pose, circle, clearance, follow, radial_gap
    >>> g = radial_gap(circle(30, 360), circle(27, 360))
    >>> round(g.minimum, 6), round(g.maximum, 6)
    (3.0, 3.0)

Move the rotor's centre 1.2 off the axis and the gap along the rays from the
axis runs from 1.8 where it stands nearest to 4.2 opposite:

    >>> rotor = Pose(1.2, 0).place(circle(27, 720))
    >>> radial = radial_gap(circle(30, 720), rotor, 360)
    >>> round(radial.minimum, 3), radial.where, round(radial.maximum, 3)
    (1.8, 0.0, 4.2)

Along a ray is not the shortest way across. A quarter turn round, the ray
from the axis runs to the rotor at `30 - sqrt(27^2 - 1.2^2)`, while the
rotor's nearest point is `sqrt(30^2 + 1.2^2) - 27` from the bore. The first is
what a winding-function model reads; the second is what closes at a contact.

    >>> near = clearance(circle(30, 720), rotor)
    >>> near.angles[180], round(radial.gaps[90], 3), round(near.gaps[180], 3)
    (90.0, 3.027, 3.024)

## Where the least goes: a cam

The airgap's own eccentric rotor, a plain circle offset by 0.05 of `r0` in a
round bore, turns rigidly about the axis. Followed through a turn, its closest
approach goes once round the bore and stays at one place on the rotor: it
*sweeps*, as a cam does.

    >>> import math
    >>> from apothecary.projects.parts.airgap import Params, build_surfaces
    >>> p = Params(rotor_spiral_b=0, rotor_rib_k=0, rotor_off_x=0.05, stator_teeth_n=0)
    >>> surfaces = build_surfaces(p, nt=360, m=1440)
    >>> def outline(radii):
    ...     return [(v * p.r0 * math.cos(math.radians(i)), v * p.r0 * math.sin(math.radians(i)))
    ...             for i, v in enumerate(radii)]
    >>> cam = follow(outline(surfaces.bore_r), outline(surfaces.rotor_r),
    ...              [Pose(0, 0, phi) for phi in range(0, 361, 10)])
    >>> cam.kind, round(cam.turns_outer, 2), round(cam.turns_inner, 2), round(min(cam.gaps), 2)
    ('sweeping', 1.0, 0.0, 1.5)

## A rotor that rolls

`rolling_rotor` takes the shaft away: a disc of radius 29 in a track of radius
30, its centre 1 off the axis, rolling. Under a tooth the poles stand `gap`
from it; with the rotor touching the track at a slot's middle, the nearest
poles are the corners of the teeth either side, a little farther.

    >>> from apothecary.projects.parts import rolling_rotor as rr
    >>> rp = rr.Params()
    >>> rp.bore, rp.eccentricity, rp.rotor_r, rp.gap, rp.poles
    (30.0, 1.0, 29.0, 0.5, 8)
    >>> under_a_tooth = rr.pole_gap(rp, 0)
    >>> round(under_a_tooth.minimum, 2), under_a_tooth.where
    (0.5, 0.0)
    >>> round(rr.pole_gap(rp, 22.5).minimum, 2)
    0.54

Each orbit turns the rotor back by `eccentricity / rotor radius` of a turn,
rolled without slip, which is the pose's assumption. Read back from the
outlines, the contact with the track goes once round the track and 30/29
times round the rotor, the same distance along each: it *rolls*.

    >>> round(rr.turn(rp, 360), 2)
    -12.41
    >>> track = rr.track_travel(rp)
    >>> track.kind, round(track.turns_outer, 2), round(track.turns_inner, 2)
    ('rolling', 1.0, 1.03)
    >>> round(track.path_outer / (2 * math.pi * rp.bore), 2), round(track.path_inner / (2 * math.pi * rp.bore), 2)
    (1.0, 1.0)

Through a whole orbit the rotor stays inside the track and inside the poles:

    >>> from apothecary.gap_geometry import contained
    >>> rotor = rr.rotor_outline(rp)
    >>> all(contained(rr.pose(rp, a).place(rotor), rr.bore_outline(rp)) for a in rr.orbits(30))
    True

## A rotor on leaves

`flexure_rotor` prints the bearing in: the hub turns by bending the leaves
that join it to the ring. Each lobe's post stands `stop` degrees round, and
the gap between their flanks is `post_r * sin(stop - swing)`, measured from
the outlines and from the closed form alike, until it closes at the stop:

    >>> from apothecary.projects.parts import flexure_rotor as fr
    >>> fp = fr.Params()
    >>> fp.post_r, fp.stop
    (14.0, 8.0)
    >>> [round(fr.flank_gap(fp, s), 3) for s in (0, 4, 7.5)]
    [1.948, 0.977, 0.122]
    >>> [round(fr.flank_gap_closed_form(fp, s), 3) for s in (0, 4, 7.5)]
    [1.948, 0.977, 0.122]
    >>> round(fr.stop_reached(fp), 4)
    8.0

Swung out and back, the closest approach stands at the post's corner and
slides along the lobe's flank, going round neither: it *rocks*. A leaf turned
one degree bends sharpest at its root, and its surface strain is the small-turn
closed form of a beam built in at both ends, in percent:

    >>> fr.hub_travel(fp, 6).kind
    'rocking'
    >>> round(100 * fr.leaf_strain(fp, 1), 3), round(100 * fr.leaf_strain_small(fp, 1), 3)
    (0.189, 0.189)

Whether a leaf of the filament it is printed in takes that strain, how stiff
the leaves are and how the hub rings are a bench's to say
([docs/airgap.md](../docs/airgap.md#at-the-bench)).

## Recipes

| | |
|---|---|
| Render the rolling rotor | `apothecary parts generate-stl rolling_rotor` |
| Render the flexure rotor swung | `apothecary parts generate-stl flexure_rotor -p swing=6` |
| Check an envelope and its holes are true | `apothecary parts verify rolling_rotor`, `apothecary parts verify flexure_rotor` |
| See each move | `/viewer/parts/rolling_rotor`, Part › Edit, its `orbit`; `/viewer/parts/flexure_rotor`, its `swing` |
