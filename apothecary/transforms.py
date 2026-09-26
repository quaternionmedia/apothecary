from typing import TYPE_CHECKING, List, Literal, Optional, Union

from pydantic import Field

from .core import OpenSCADObject
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
        comment_str = f"// {self.comment}\n" if self.comment else ""
        children_str = "\n".join(f"  {child.render()}" for child in self.children)
        return (
            f"{comment_str}translate([{self.v.x}, {self.v.y}, {self.v.z}]) {{\n{children_str}\n}}"
        )


class Rotate(Transform):
    """OpenSCAD rotate transformation"""

    type: Literal["rotate"] = "rotate"

    a: Union[float, Vector3D]
    v: Optional[Vector3D] = None

    def render(self, *_, **__) -> str:
        comment_str = f"// {self.comment}\n" if self.comment else ""

        if isinstance(self.a, Vector3D):
            rotate_str = f"rotate([{self.a.x}, {self.a.y}, {self.a.z}])"
        elif self.v:
            rotate_str = f"rotate(a={self.a}, v=[{self.v.x}, {self.v.y}, {self.v.z}])"
        else:
            rotate_str = f"rotate({self.a})"

        children_str = "\n".join(f"  {child.render()}" for child in self.children)
        return f"{comment_str}{rotate_str} {{\n{children_str}\n}}"


class Scale(Transform):
    """OpenSCAD scale transformation"""

    type: Literal["scale"] = "scale"

    v: Vector3D

    def render(self, *_, **__) -> str:
        comment_str = f"// {self.comment}\n" if self.comment else ""
        children_str = "\n".join(f"  {child.render()}" for child in self.children)
        return f"{comment_str}scale([{self.v.x}, {self.v.y}, {self.v.z}]) {{\n{children_str}\n}}"
