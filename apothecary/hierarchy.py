"""Fractal Site/Structure/Substructure/Feature hierarchy.

PROTOTYPE — not ratified. This module exists to let the design in
``governance/qm/adr/DRAFT-site-structure-substructure-feature-hierarchy.md``
be evaluated against real geometry before that ADR is ratified. It is
additive: ``Scene`` and every existing primitive/boolean/transform are
untouched. The API (``apothecary/api.py``) and a prototype migration of the
``parts/`` registry (``apothecary/example_parts_library.py``) do import and
build on this module now, feeding the fractal zoom viewer -- but both are
themselves explicitly labeled prototype/unratified, evaluating this shape
rather than treating it as ratified.

The model is one generic, self-similar recursive node, :class:`Assembly` —
not four separate classes. A build is a tree of ``Assembly`` nodes of
unbounded depth; ``role`` is a free-form label ("site", "structure",
"substructure", "feature", or anything a project invents) used only for
render comments and human legibility, not a type distinction. This is the
fractal reading of the ADR's vocabulary: "one coherent build made of parts,
each potentially decomposable the same way" recurs at every level, so hard-
coding exactly four levels would just be an arbitrary depth limit waiting to
be hit by the first project that needs a fifth.

``Site``, ``Structure``, ``Substructure``, and ``Feature`` remain as the
vocabulary — the ADR's named levels are this project's *worked example* of
configuring the fractal model, not gone. ``Site``/``Structure``/
``Substructure`` are thin factory functions that build a role-tagged
``Assembly``; ``Feature`` is a small namespace of constructors for common
leaf geometry (``clearance_hole``, ``boss``). Every one of them returns a
plain ``Assembly`` — there is exactly one class walking the tree, one
``to_scad_object()``, and one recursive overlap-check, reachable at any
depth including a single ``Feature``.
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


class Assembly(BaseModel):
    """One generic, self-similar recursive node — the fractal core.

    ``role`` is free-form metadata (used for the render comment and for
    future revision/diff messages), not a type constraint: nothing here
    stops a "feature"-role node from having ``children`` or a "site"-role
    node from having ``additions`` — the same shape applies uniformly at
    every depth, which is exactly the point.

    ``part_ref``, when set, names a registered ``parts/`` entry this leaf
    mirrors, letting a viewer fetch real geometry on demand (e.g. ``GET
    /parts/{part_ref}/stl``) instead of only this node's ``footprint``
    bounding box — None everywhere except leaves built from the parts
    registry (see ``example_parts_library.py``).

    ``category``, when set, names the subsystem this node belongs to (a
    viewer's domain, e.g. "wall"/"furniture"/"mechanical"/"fluid"/
    "electrical" -- a project invents its own vocabulary, same as ``role``).
    Unset on most nodes: a viewer resolves the *effective* category by
    walking up to the nearest ancestor that set one (see api.py's
    ``_assembly_tree``), so tagging a handful of top-level Structures is
    enough for every Substructure/Feature beneath them to inherit it.
    """

    name: str
    role: str = "assembly"
    position: Vector3D = Field(default_factory=Vector3D)
    footprint: Optional[BoundingBox3D] = None
    material: Optional[str] = None
    build_volume: Optional[Vector3D] = None
    status: Optional[str] = None
    base: Optional[OpenSCADObject] = None
    additions: List["Assembly"] = Field(default_factory=list)
    subtractions: List["Assembly"] = Field(default_factory=list)
    children: List["Assembly"] = Field(default_factory=list)
    comment: Optional[str] = None
    part_ref: Optional[str] = None
    category: Optional[str] = None

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
        """Compile this node (and everything beneath it) to one OpenSCAD object.

        The single algorithm that replaces what the four fixed classes used
        to need three separate implementations for: gather positives (``base``
        + rendered ``additions`` + rendered ``children``), union them into a
        fresh wrapper (always -- even for exactly one item, since ``base`` or
        an already-rendered addition/child may already carry its own comment,
        and reusing it directly would silently overwrite that inner label
        instead of nesting around it), subtract ``subtractions`` if any, tag
        the result with a ``"Role: name"`` comment, and wrap in a translate if
        ``position`` is non-zero.
        """
        positives: List[OpenSCADObject] = []
        if self.base is not None:
            positives.append(self.base)
        positives.extend(addition.to_scad_object() for addition in self.additions)
        positives.extend(child.to_scad_object() for child in self.children)

        if not positives:
            raise ValueError(
                f"{self.role.capitalize()} {self.name!r} has no base, additions, or children"
            )

        label = f"{self.role.capitalize()}: {self.name}" + (
            f" ({self.material})" if self.material else ""
        )
        positive: OpenSCADObject = Union(children=positives)

        body: OpenSCADObject
        if self.subtractions:
            subtraction_objs = [s.to_scad_object() for s in self.subtractions]
            body = Difference(
                children=[positive, *subtraction_objs], comment=self.comment or label
            )
        else:
            positive.comment = self.comment or label
            body = positive

        if self.position != Vector3D():
            return Translate(v=self.position, children=[body])
        return body

    def to_scene(self) -> Scene:
        """Compile this node's ``children`` to a :class:`Scene`, treating this node as the root."""
        return Scene(name=self.name, objects=[child.to_scad_object() for child in self.children])

    def render(self) -> str:
        return self.to_scene().render()

    def render_jscad(self) -> str:
        return self.to_scene().render_jscad()

    def validate(self) -> "LayoutReport":
        """Recursive layout check: no two sibling nodes physically overlap, at any depth.

        Generalizes what used to be Site-only overlap-checking (Site's
        direct Structure children) to every level of the tree — a
        Structure's Substructure children, a Substructure's nested
        Substructure children, and so on — for free, from one recursive
        function. Scenario-specific rules (e.g. "must rest on this other
        node's surface") are not this method's job — see, for example,
        ``example_hierarchy.validate_garage_layout``, which builds on this.
        """
        return _validate_tree(self)


Assembly.model_rebuild()


class LayoutViolation(BaseModel):
    """One concrete way a set of sibling Assembly nodes fail to coexist in space."""

    kind: str
    message: str
    structures: List[str] = Field(default_factory=list)


class LayoutReport(BaseModel):
    """The result of checking a set of Assembly nodes against each other."""

    violations: List[LayoutViolation] = Field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.violations


def _penetrates(a: BoundingBox3D, b: BoundingBox3D) -> bool:
    """True only for a genuine positive-volume overlap, not boundary contact.

    ``BoundingBox3D.intersects`` is inclusive of touching faces (``<=``/``>=``),
    which is the right general contract for that method (e.g. "does this
    point's box touch that one") but wrong for *this* check: a node resting
    exactly on another's surface — the normal case for anything placed on a
    Site — shares a boundary plane by design, not by defect.
    """
    return (
        a.min_point.x < b.max_point.x
        and a.max_point.x > b.min_point.x
        and a.min_point.y < b.max_point.y
        and a.max_point.y > b.min_point.y
        and a.min_point.z < b.max_point.z
        and a.max_point.z > b.min_point.z
    )


def check_no_overlaps(nodes: List["Assembly"]) -> List[LayoutViolation]:
    """Pairwise overlap check between every sibling node that carries a footprint.

    A node without a ``footprint`` is skipped, not treated as
    non-overlapping by assumption — it simply isn't checked. Nodes that
    merely touch (e.g. one resting on another's surface) are not violations;
    see :func:`_penetrates`.
    """
    bounded = [(n, n.world_bounds()) for n in nodes]
    bounded = [(n, b) for n, b in bounded if b is not None]

    violations: List[LayoutViolation] = []
    for (node_a, bounds_a), (node_b, bounds_b) in itertools.combinations(bounded, 2):
        if _penetrates(bounds_a, bounds_b):
            violations.append(
                LayoutViolation(
                    kind="overlap",
                    message=f"{node_a.name} and {node_b.name} overlap",
                    structures=[node_a.name, node_b.name],
                )
            )
    return violations


def _validate_tree(assembly: "Assembly") -> LayoutReport:
    violations = list(check_no_overlaps(assembly.children))
    for child in assembly.children:
        violations.extend(_validate_tree(child).violations)
    return LayoutReport(violations=violations)


# ---------------------------------------------------------------------------
# Vocabulary: Site / Structure / Substructure / Feature as ergonomic
# constructors over the one generic Assembly class. These are functions (and,
# for Feature, a namespace of staticmethods), not types — the ADR's four
# names describe *roles* in this worked example, not four distinct classes.
# ---------------------------------------------------------------------------


def Site(name: str = "untitled_site", *, structures: Optional[List[Assembly]] = None) -> Assembly:
    """The root of one coherent physical build. Compiles down to a :class:`Scene`."""
    return Assembly(name=name, role="site", children=structures or [])


def Structure(
    name: str,
    *,
    position: Optional[Vector3D] = None,
    footprint: Optional[BoundingBox3D] = None,
    material: Optional[str] = None,
    build_volume: Optional[Vector3D] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    substructures: Optional[List[Assembly]] = None,
) -> Assembly:
    """An independently-manufactured or independently-sourced rigid grouping within a Site."""
    return Assembly(
        name=name,
        role="structure",
        position=position or Vector3D(),
        footprint=footprint,
        material=material,
        build_volume=build_volume,
        status=status,
        category=category,
        children=substructures or [],
    )


def Substructure(
    name: str,
    *,
    position: Optional[Vector3D] = None,
    footprint: Optional[BoundingBox3D] = None,
    base: Optional[OpenSCADObject] = None,
    additions: Optional[List[Assembly]] = None,
    subtractions: Optional[List[Assembly]] = None,
    children: Optional[List[Assembly]] = None,
) -> Assembly:
    """A named system within a Structure (mounting, cable-routing, ...).

    Composes a ``base`` (optional existing geometry), ``additions`` (bosses,
    ribs — unioned in), ``subtractions`` (holes, slots — differenced out),
    and nested child Substructures, into one addressable, named node.
    """
    return Assembly(
        name=name,
        role="substructure",
        position=position or Vector3D(),
        footprint=footprint,
        base=base,
        additions=additions or [],
        subtractions=subtractions or [],
        children=children or [],
    )


class Feature:
    """Constructors for common leaf geometry: a single named, parameterized
    local modification, addressable and reusable rather than an anonymous
    boolean/primitive combination.

    Not a Pydantic model — a plain namespace, directly constructible as
    ``Feature(name=..., geometry=...)`` for arbitrary geometry (via
    ``__new__``, so this returns an ``Assembly`` rather than a ``Feature``
    instance) as well as via the named constructors below. Every constructor
    here returns an ``Assembly(role="feature", base=...)``, the same class as
    every other level, so a Feature can itself carry ``children`` (a sub-feature, a
    relief cut on a boss) the same way a Substructure always could.
    """

    def __new__(cls, name: str, *, geometry: OpenSCADObject) -> Assembly:
        return Assembly(name=name, role="feature", base=geometry)

    @staticmethod
    def clearance_hole(
        name: str,
        *,
        position: Vector3D,
        nominal_diameter: float,
        depth: float,
        print_settings: Optional[PrintSettings] = None,
    ) -> Assembly:
        """A through-hole sized for clearance around a given hardware diameter.

        Uses :meth:`PrintSettings.clearance_hole` so the tolerance math lives
        in one place instead of being hand-coded at each use site.
        """
        ps = print_settings or PrintSettings()
        radius = ps.clearance_hole(nominal_diameter) / 2
        geometry = Translate(v=position, children=[Cylinder(h=depth, r=radius, center=False)])
        return Assembly(name=name, role="feature", base=geometry)

    @staticmethod
    def boss(
        name: str,
        *,
        position: Vector3D,
        diameter: float,
        height: float,
    ) -> Assembly:
        """A cylindrical boss (a positive standoff, e.g. for a self-tapping screw)."""
        geometry = Translate(v=position, children=[Cylinder(h=height, r=diameter / 2, center=False)])
        return Assembly(name=name, role="feature", base=geometry)


__all__ = [
    "Assembly",
    "LayoutViolation",
    "LayoutReport",
    "check_no_overlaps",
    "Site",
    "Structure",
    "Substructure",
    "Feature",
]
