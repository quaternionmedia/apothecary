import math

from apothecary import Translate, Union, Vector3D

from .blade import SnowplowBlade
from .mount import SnowplowMount

# How far the plate's front face goes into the blade, as a share of
# blade_thickness: the two share volume, so they render as one solid even where
# the plate's face and the blade's back face would otherwise only touch.
MOUNT_INTO_BLADE = 0.1


def mount_front_y(blade_height, blade_thickness, blade_angle, mount_height):
    """Where snowplow_assembly puts the front face of the mount plate along Y.

    The plate stands on the bed behind the blade, which blade_angle turns
    about its centre. Over the heights the plate shares with the blade's back
    face, its front face meets that face where it is furthest forward, and
    goes MOUNT_INTO_BLADE of blade_thickness further in: at the blade's base
    while the blade leans back over the plate (blade_angle of 0 or more), at
    the plate's top once it leans forward. So the plate and the blade are one
    solid whatever blade_angle and blade_thickness are, while the back face
    comes down past the plate's top: turned about its centre, a steep blade
    lifts its back face off the bed, higher than a plate on the bed reaches.
    A steep angle on a thin blade shows the plate's top corner through the
    blade's front. The bolt holes, open at the plate's back, stop at the blade.
    """
    a = math.radians(blade_angle)
    half_t, half_h = blade_thickness / 2, blade_height / 2
    # The heights of the back face's bottom and top edges, once turned.
    bottom = half_h - half_t * math.sin(a) - half_h * math.cos(a)
    top = half_h - half_t * math.sin(a) + half_h * math.cos(a)
    z = max(0.0, bottom) if blade_angle >= 0 else min(mount_height, top)
    back_face = -half_t / math.cos(a) - (z - half_h) * math.tan(a)
    return back_face + MOUNT_INTO_BLADE * blade_thickness


def snowplow_assembly(
    blade_width=120.0,
    blade_height=45.0,
    blade_thickness=3.0,
    blade_angle=10.0,
    mount_width=40.0,
    mount_height=12.0,
    mount_thickness=4.0,
    bolt_diameter=3.0,
    bolt_spacing=24.0,
):
    blade = SnowplowBlade(
        width=blade_width,
        height=blade_height,
        thickness=blade_thickness,
        angle=blade_angle,
    ).geometry()
    mount = SnowplowMount(
        width=mount_width,
        height=mount_height,
        thickness=mount_thickness,
        bolt_diameter=bolt_diameter,
        bolt_spacing=bolt_spacing,
    ).geometry()
    front = mount_front_y(blade_height, blade_thickness, blade_angle, mount_height)
    return Union(
        children=[
            Translate(v=Vector3D(x=0, y=0, z=blade_height / 2), children=[blade]),
            Translate(
                v=Vector3D(x=0, y=front - mount_thickness / 2, z=mount_height / 2),
                children=[mount],
            ),
        ]
    )


# Registry wrapper: the BasePart lives in rc_snowplow.py; re-export it here so
# parts/rc/snowplow/snowplow.scad resolves to this package.
from apothecary.projects.parts.rc_snowplow import DEFAULT, Params, SnowplowPart  # noqa: E402

__all__ = ["DEFAULT", "Params", "SnowplowPart", "mount_front_y", "snowplow_assembly"]
