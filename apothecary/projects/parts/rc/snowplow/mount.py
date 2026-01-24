from apothecary import Cube, Cylinder, Translate, Union, Difference, Vector3D

class SnowplowMount:
    """
    Mount plate for snowplow blade, with bolt holes.
    """
    def __init__(self, width=40.0, height=12.0, thickness=4.0, bolt_diameter=3.0, bolt_spacing=24.0):
        self.width = width
        self.height = height
        self.thickness = thickness
        self.bolt_diameter = bolt_diameter
        self.bolt_spacing = bolt_spacing

    def geometry(self):
        mount_plate = Cube(
            size=Vector3D(x=self.width, y=self.thickness, z=self.height),
            center=True,
            comment="Chassis mount plate",
        )
        bolt_holes = Union(children=[
            Translate(
                v=Vector3D(x=-self.bolt_spacing / 2, y=0, z=0),
                children=[Cylinder(d=self.bolt_diameter, h=20, center=True)],
            ),
            Translate(
                v=Vector3D(x=self.bolt_spacing / 2, y=0, z=0),
                children=[Cylinder(d=self.bolt_diameter, h=20, center=True)],
            ),
        ])
        return Difference(children=[mount_plate, bolt_holes])
