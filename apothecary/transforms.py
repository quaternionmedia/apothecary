from typing import TYPE_CHECKING, List, Literal, Optional, Union

from pydantic import Field

from .core import OpenSCADObject, scad_vec
from .models.vectors import Vector3D

if TYPE_CHECKING:
    from .objects import SceneObject


class Transform(OpenSCADObject):
    """Base class for transformations"""

    children: List["SceneObject"] = Field(default_factory=list)


class Translate(Transform):
    """OpenSCAD translate transformation"""

    type: Literal["translate"] = "translate"

    v: Vector3D

    def render(self, *_, **__) -> str:
        return self._block(f"translate({scad_vec(self.v)})", self.children)


class Rotate(Transform):
    """OpenSCAD rotate transformation"""

    type: Literal["rotate"] = "rotate"

    a: Union[float, Vector3D]
    v: Optional[Vector3D] = None

    def render(self, *_, **__) -> str:
        if isinstance(self.a, Vector3D):
            head = f"rotate({scad_vec(self.a)})"
        elif self.v:
            head = f"rotate(a={self.a}, v={scad_vec(self.v)})"
        else:
            head = f"rotate({self.a})"
        return self._block(head, self.children)


class Scale(Transform):
    """OpenSCAD scale transformation"""

    type: Literal["scale"] = "scale"

    v: Vector3D

    def render(self, *_, **__) -> str:
        return self._block(f"scale({scad_vec(self.v)})", self.children)
