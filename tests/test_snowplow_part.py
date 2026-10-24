from apothecary.projects.parts.rc.snowplow import snowplow_assembly
from apothecary import Scene

def test_snowplow_assembly_renders():
    scene = Scene(name="test_snowplow", objects=[snowplow_assembly()])
    scad = scene.render()
    assert "cube" in scad.lower() and "cylinder" in scad.lower()
    assert "union" in scad.lower() and "difference" in scad.lower()
