from apothecary import Cube, Rotate, Vector3D

class SnowplowBlade:
    """
    Parametric snowplow blade for RC car.
    """
    def __init__(self, width=120.0, height=45.0, thickness=3.0, angle=10.0):
        self.width = width
        self.height = height
        self.thickness = thickness
        self.angle = angle

    def geometry(self):
        return Rotate(
            a=self.angle,
            v=Vector3D(x=1, y=0, z=0),
            children=[
                Cube(
                    size=Vector3D(x=self.width, y=self.thickness, z=self.height),
                    center=True,
                    comment="Snowplow blade",
                )
            ],
        )
