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

import itertools
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


class LayoutViolation(BaseModel):
    """One concrete way a Site's Structures fail to coexist in space."""

    kind: str
    message: str
    structures: List[str] = Field(default_factory=list)


class LayoutReport(BaseModel):
    """The result of checking a Site's Structures against each other."""

    violations: List[LayoutViolation] = Field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.violations


def _penetrates(a: BoundingBox3D, b: BoundingBox3D) -> bool:
    """True only for a genuine positive-volume overlap, not boundary contact.

    ``BoundingBox3D.intersects`` is inclusive of touching faces (``<=``/``>=``),
    which is the right general contract for that method (e.g. "does this
    point's box touch that one") but wrong for *this* check: a Structure
    resting exactly on another's surface — the normal case for anything
    placed on a Site — shares a boundary plane by design, not by defect.
    """
    return (
        a.min_point.x < b.max_point.x
        and a.max_point.x > b.min_point.x
        and a.min_point.y < b.max_point.y
        and a.max_point.y > b.min_point.y
        and a.min_point.z < b.max_point.z
        and a.max_point.z > b.min_point.z
    )


def check_no_overlaps(structures: List["Structure"]) -> List[LayoutViolation]:
    """Pairwise overlap check between every Structure that carries a footprint.

    A Structure without a ``footprint`` is skipped, not treated as
    non-overlapping by assumption — it simply isn't checked. Structures that
    merely touch (e.g. one resting on another's surface) are not violations;
    see :func:`_penetrates`.
    """
    bounded = [(s, s.world_bounds()) for s in structures]
    bounded = [(s, b) for s, b in bounded if b is not None]

    violations: List[LayoutViolation] = []
    for (structure_a, bounds_a), (structure_b, bounds_b) in itertools.combinations(bounded, 2):
        if _penetrates(bounds_a, bounds_b):
            violations.append(
                LayoutViolation(
                    kind="overlap",
                    message=f"{structure_a.name} and {structure_b.name} overlap",
                    structures=[structure_a.name, structure_b.name],
                )
            )
    return violations


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

    def validate(self) -> LayoutReport:
        """Generic layout check: no two Structures physically overlap.

        Site-specific rules (e.g. "must rest on this other Structure's
        surface") are not this method's job — see, for example,
        ``example_hierarchy.validate_garage_layout``, which builds on this.
        """
        return LayoutReport(violations=check_no_overlaps(self.structures))
