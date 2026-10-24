from apothecary import Cube, Cylinder, Difference, Rotate, Translate, Union, Vector3D


class SnowplowMount:
    """
    Mount plate for snowplow blade, with bolt holes.

    The plate's thickness runs along Y, and so do the holes: snowplow.yaml's
    mount_left and mount_right, bolt_spacing apart about the plate's centre.
    """

    def __init__(
        self, width=40.0, height=12.0, thickness=4.0, bolt_diameter=3.0, bolt_spacing=24.0
    ):
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
        bolt_holes = Union(
            children=[
                Translate(v=Vector3D(x=x, y=0, z=0), children=[self._bolt_hole()])
                for x in (-self.bolt_spacing / 2, self.bolt_spacing / 2)
            ]
        )
        return Difference(children=[mount_plate, bolt_holes])

    def _bolt_hole(self):
        """A bolt_diameter hole through the plate along Y, 1 mm proud of each face."""
        return Rotate(
            a=Vector3D(x=90, y=0, z=0),
            children=[Cylinder(r=self.bolt_diameter / 2, h=self.thickness + 2, center=True)],
        )
