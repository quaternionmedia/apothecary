from .blade import SnowplowBlade
from .mount import SnowplowMount

from apothecary import Union, Translate, Vector3D

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
    return Union(children=[
        Translate(v=Vector3D(x=0, y=0, z=blade_height / 2), children=[blade]),
        Translate(v=Vector3D(x=0, y=-blade_thickness, z=mount_height / 2), children=[mount]),
    ])

# For registry: expose DEFAULT and name
class PartWrapper:
    # Registry/CLI name for discovery (dotted for internal, display for UI)
    name = "rc.snowplow"
    display_name = "RC Snowplow"
    @staticmethod
    def params_model():
        from apothecary.projects.parts.rc_snowplow import Params
        return Params

DEFAULT = PartWrapper()
