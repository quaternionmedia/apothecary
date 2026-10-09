"""Every object a scene can hold, as one union tagged by ``type``.

A field typed as the base class (``OpenSCADObject``) validates JSON into the
base and drops every field of the shape it described; the tag is what lets
``{"type": "cube", "size": ...}`` come back as a cube, and a dump go back out
with its tag. Every field that holds scene geometry is typed ``SceneObject``.
"""

import typing
from typing import Annotated

from pydantic import Field

from .booleans import BooleanOperation, Difference, Hull, Intersection, Union
from .primitives import Cube, Cylinder, Import, Sphere
from .transforms import Rotate, Scale, Transform, Translate

SceneObject = Annotated[
    typing.Union[
        Cube,
        Sphere,
        Cylinder,
        Import,
        Union,
        Difference,
        Intersection,
        Hull,
        Translate,
        Rotate,
        Scale,
    ],
    Field(discriminator="type"),
]

for _holder in (
    BooleanOperation,
    Union,
    Difference,
    Intersection,
    Hull,
    Transform,
    Translate,
    Rotate,
    Scale,
):
    _holder.model_rebuild(_types_namespace={"SceneObject": SceneObject})

__all__ = ["SceneObject"]
