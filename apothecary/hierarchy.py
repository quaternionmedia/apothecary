"""Site / Structure / Substructure / Feature hierarchy.

PROTOTYPE — not ratified. This module exists to let the design in
``governance/qm/adr/DRAFT-site-structure-substructure-feature-hierarchy.md``
be evaluated against real geometry before that ADR is ratified. It is
additive: ``Scene`` and every existing primitive/boolean/transform are
untouched, and nothing here is imported by the CLI, API, or ``parts/``
registry yet.

Vocabulary (outermost to innermost), per the ADR:

- ``Site`` — one coherent physical build; compiles down to a ``Scene``.
- ``Structure`` — an independently-manufactured or independently-sourced
  rigid grouping within a Site.
- ``Substructure`` — a named *system* within a Structure (mounting,
  cable-routing, ventilation, ...) — the level that makes "multiple systems
  in one subassembly" concrete.
- ``Feature`` — a single named, parameterized local modification (hole,
  boss, ...), addressable and reusable rather than an anonymous boolean.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from .booleans import Difference, Union
from .core import OpenSCADObject
from .models.bounds import BoundingBox3D
from .models.units import PrintSettings
from .models.vectors import Vector3D
from .primitives import Cylinder
from .scene import Scene
from .transforms import Translate


class Feature(OpenSCADObject):
    """A single named, parameterized local modification.

    Wraps arbitrary geometry behind a name so it is addressable and
    reusable, instead of an anonymous boolean/primitive combination.
    """

    name: str
    geometry: OpenSCADObject

    def render(self, *_, **__) -> str:
        tag = self.comment or f"Feature: {self.name}"
        return f"// {tag}\n{self.geometry.render()}"

    @classmethod
    def clearance_hole(
        cls,
        name: str,
        *,
        position: Vector3D,
        nominal_diameter: float,
        depth: float,
        print_settings: Optional[PrintSettings] = None,
    ) -> "Feature":
        """A through-hole sized for clearance around a given hardware diameter.

        Uses :meth:`PrintSettings.clearance_hole` so the tolerance math lives
        in one place instead of being hand-coded at each use site.
        """
        ps = print_settings or PrintSettings()
        radius = ps.clearance_hole(nominal_diameter) / 2
        geometry = Translate(v=position, children=[Cylinder(h=depth, r=radius, center=False)])
        return cls(name=name, geometry=geometry)

    @classmethod
    def boss(
        cls,
        name: str,
        *,
        position: Vector3D,
        diameter: float,
        height: float,
    ) -> "Feature":
        """A cylindrical boss (a positive standoff, e.g. for a self-tapping screw)."""
        geometry = Translate(v=position, children=[Cylinder(h=height, r=diameter / 2, center=False)])
        return cls(name=name, geometry=geometry)


class Substructure(BaseModel):
    """A named system within a Structure (mounting, cable-routing, ...).

    Composes a ``base`` (optional existing geometry), ``additions`` (bosses,
    ribs — unioned in), ``subtractions`` (holes, slots — differenced out),
    and nested child Substructures, into one addressable, named node.
    """

    name: str
    position: Vector3D = Field(default_factory=Vector3D)
    footprint: Optional[BoundingBox3D] = None
    base: Optional[OpenSCADObject] = None
    additions: List[Feature] = Field(default_factory=list)
    subtractions: List[Feature] = Field(default_factory=list)
    children: List["Substructure"] = Field(default_factory=list)

    def world_bounds(self) -> Optional[BoundingBox3D]:
        """This node's ``footprint``, offset by ``position`` into the parent's frame.

        Returns ``None`` if no ``footprint`` was given — bounds are opt-in
        metadata, not derived from the rendered geometry.
        """
        if self.footprint is None:
            return None
        return BoundingBox3D(
            min_point=self.footprint.min_point + self.position,
            max_point=self.footprint.max_point + self.position,
        )

    def to_scad_object(self) -> OpenSCADObject:
        positives: List[OpenSCADObject] = []
        if self.base is not None:
            positives.append(self.base)
        positives.extend(self.additions)
        positives.extend(child.to_scad_object() for child in self.children)

        if not positives:
            raise ValueError(f"Substructure {self.name!r} has no base, additions, or children")

        label = f"Substructure: {self.name}"
        positive = Union(children=positives)

        body: OpenSCADObject
        if self.subtractions:
            body = Difference(children=[positive, *self.subtractions], comment=label)
        else:
            positive.comment = label
            body = positive

        if self.position != Vector3D():
            return Translate(v=self.position, children=[body])
        return body


Substructure.model_rebuild()


class Structure(BaseModel):
    """An independently-manufactured or independently-sourced rigid grouping within a Site."""

    name: str
    position: Vector3D = Field(default_factory=Vector3D)
    footprint: Optional[BoundingBox3D] = None
    material: Optional[str] = None
    substructures: List[Substructure] = Field(default_factory=list)

    def world_bounds(self) -> Optional[BoundingBox3D]:
        """This node's ``footprint``, offset by ``position`` into the Site's frame."""
        if self.footprint is None:
            return None
        return BoundingBox3D(
            min_point=self.footprint.min_point + self.position,
            max_point=self.footprint.max_point + self.position,
        )

    def to_scad_object(self) -> OpenSCADObject:
        if not self.substructures:
            raise ValueError(f"Structure {self.name!r} has no substructures")

        label = f"Structure: {self.name}" + (f" ({self.material})" if self.material else "")
        body: OpenSCADObject = Union(
            children=[s.to_scad_object() for s in self.substructures],
            comment=label,
        )
        if self.position != Vector3D():
            return Translate(v=self.position, children=[body])
        return body


class Site(BaseModel):
    """The root of one coherent physical build. Compiles down to a :class:`Scene`."""

    name: str = "untitled_site"
    structures: List[Structure] = Field(default_factory=list)

    def to_scene(self) -> Scene:
        return Scene(name=self.name, objects=[s.to_scad_object() for s in self.structures])

    def render(self) -> str:
        return self.to_scene().render()

    def render_jscad(self) -> str:
        return self.to_scene().render_jscad()
