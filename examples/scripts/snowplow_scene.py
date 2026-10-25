"""The RC snowplow's assembly in a scene: a part whose geometry is Python, used from a script.

`snowplow_assembly()` builds the blade and its mount from `apothecary`'s objects, as the
`snowplow` part's wrapper does for the viewer; here it is placed in a `Scene` and printed as
OpenSCAD, so the same geometry can be laid out beside other things or rendered on its own:

    uv run python examples/scripts/snowplow_scene.py > snowplow.scad
"""

from apothecary import Scene
from apothecary.projects.parts.rc.snowplow import snowplow_assembly

scene = Scene(
    name="rc_car_snowplow_demo",
    objects=[snowplow_assembly()],
)

if __name__ == "__main__":
    print(scene.render())
