from typing import TYPE_CHECKING, ClassVar, List, Literal

from pydantic import Field

from .core import OpenSCADObject

if TYPE_CHECKING:
    from .objects import SceneObject


class BooleanOperation(OpenSCADObject):
    """Base class for boolean operations"""

    children: List["SceneObject"] = Field(default_factory=list)
    keyword: ClassVar[str] = ""

    def render(self, *_, **__) -> str:
        return self._block(f"{self.keyword}()", self.children)


class Union(BooleanOperation):
    """OpenSCAD union operation"""

    type: Literal["union"] = "union"
    keyword: ClassVar[str] = "union"


class Difference(BooleanOperation):
    """OpenSCAD difference operation"""

    type: Literal["difference"] = "difference"
    keyword: ClassVar[str] = "difference"


class Intersection(BooleanOperation):
    """OpenSCAD intersection operation"""

    type: Literal["intersection"] = "intersection"
    keyword: ClassVar[str] = "intersection"


class Hull(BooleanOperation):
    """OpenSCAD hull operation.

    The convex hull of its children. Four corner cylinders hulled together is
    the standard way to get a rounded rectangular prism, which is what an
    enclosure shell actually is -- a plain cube would misreport the corner
    radius everything else is fitted around.
    """

    type: Literal["hull"] = "hull"
    keyword: ClassVar[str] = "hull"
