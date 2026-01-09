from .booleans import Difference, Union
from .models.vectors import Vector3D
from .primitives import Cube, Cylinder
from .scene import Scene
from .transforms import Rotate, Translate


def create_example_scene() -> Scene:
    """Create an example scene demonstrating the framework"""

    # Create a simple house shape
    base = Cube(size=Vector3D(x=10, y=10, z=5), center=False, comment="House base")

    roof = Translate(
        v=Vector3D(x=5, y=5, z=10),
        children=[
            Rotate(
                a=Vector3D(x=0, y=0, z=45),
                children=[Cylinder(h=10, r1=7, r2=0, center=True, fn=4, comment="Roof")],
            )
        ],
    )

    door = Translate(
        v=Vector3D(x=4, y=-0.1, z=0),
        children=[Cube(size=Vector3D(x=2, y=0.2, z=3), comment="Door cutout")],
    )

    house = Difference(
        children=[Union(children=[base, roof], comment="House shell"), door],
        comment="Final house with door",
    )

    return Scene(name="Simple House", objects=[house])
