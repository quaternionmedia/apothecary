from typing import List

from pydantic import Field

from .core import OpenSCADObject


class BooleanOperation(OpenSCADObject):
    """Base class for boolean operations"""

    # Simplicity over enforcement; validation happens logically by usage
    children: List[OpenSCADObject] = Field(default_factory=list)


class Union(BooleanOperation):
    """OpenSCAD union operation"""

    def render(self, *_, **__) -> str:
        comment_str = f"// {self.comment}\n" if self.comment else ""
        children_str = "\n".join(f"  {child.render()}" for child in self.children)
        return f"{comment_str}union() {{\n{children_str}\n}}"


class Difference(BooleanOperation):
    """OpenSCAD difference operation"""

    def render(self, *_, **__) -> str:
        comment_str = f"// {self.comment}\n" if self.comment else ""
        children_str = "\n".join(f"  {child.render()}" for child in self.children)
        return f"{comment_str}difference() {{\n{children_str}\n}}"


class Intersection(BooleanOperation):
    """OpenSCAD intersection operation"""

    def render(self, *_, **__) -> str:
        comment_str = f"// {self.comment}\n" if self.comment else ""
        children_str = "\n".join(f"  {child.render()}" for child in self.children)
        return f"{comment_str}intersection() {{\n{children_str}\n}}"


class Hull(BooleanOperation):
    """OpenSCAD hull operation.

    The convex hull of its children. Four corner cylinders hulled together is
    the standard way to get a rounded rectangular prism, which is what an
    enclosure shell actually is -- a plain cube would misreport the corner
    radius everything else is fitted around.
    """

    def render(self, *_, **__) -> str:
        comment_str = f"// {self.comment}\n" if self.comment else ""
        children_str = "\n".join(f"  {child.render()}" for child in self.children)
        return f"{comment_str}hull() {{\n{children_str}\n}}"
