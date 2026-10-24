"""JSCAD renderer for Apothecary scenes.

Produces JavaScript modules compatible with the OpenJSCAD standard API.

The generated module exports a `main` function which returns geometry
constructed from the scene's objects using the functional API, e.g.:

    import { cube, cuboid, sphere, cylinder } from '@jscad/modeling/src/primitives'
    import { union, difference, intersection } from '@jscad/modeling/src/booleans'
    import { translate, rotate, scale } from '@jscad/modeling/src/transforms'

For now we generate a minimal module; consumers are responsible for
configuring their bundler/CLI according to the OpenJSCAD docs.
"""

from __future__ import annotations

from typing import List

from .booleans import Difference, Intersection, Union
from .core import OpenSCADObject
from .models.vectors import Vector3D
from .primitives import Cube, Cylinder, Import, Sphere
from .scene import Scene
from .transforms import Rotate, Scale, Translate


def _vec_to_array(v: Vector3D) -> str:
    return f"[{v.x}, {v.y}, {v.z}]"


def _render_primitive(obj: OpenSCADObject) -> str:
    if isinstance(obj, Cube):
        if isinstance(obj.size, Vector3D):
            size_str = _vec_to_array(obj.size)
        else:
            # JSCAD cube(size) accepts number or [x,y,z]
            size_str = str(obj.size)
        return f"cube({{ size: {size_str}, center: {str(obj.center).lower()} }})"

    if isinstance(obj, Sphere):
        # JSCAD sphere({ radius, segments })
        seg_str = f", segments: {obj.fn}" if obj.fn else ""
        return f"sphere({{ radius: {obj.r}{seg_str} }})"

    if isinstance(obj, Cylinder):
        # Map to cylinder({ height, radius, startRadius, endRadius, segments, center })
        parts = [f"height: {obj.h}"]
        if obj.r is not None:
            parts.append(f"radius: {obj.r}")
        if obj.r1 is not None:
            parts.append(f"startRadius: {obj.r1}")
        if obj.r2 is not None:
            parts.append(f"endRadius: {obj.r2}")
        if obj.fn is not None:
            parts.append(f"segments: {obj.fn}")
        parts.append(f"center: {str(obj.center).lower()}")
        return f"cylinder({{ {', '.join(parts)} }})"

    raise TypeError(f"Unsupported primitive type for JSCAD rendering: {type(obj)!r}")


def _render_node(obj: OpenSCADObject) -> str:
    # Named features (apothecary.hierarchy.Feature) unwrap to their geometry:
    # JSCAD has no notion of the name, only the shape it renders to.
    from .hierarchy import Feature  # local import: hierarchy is a prototype module

    if isinstance(obj, Feature):
        return _render_node(obj.geometry)

    # Primitives
    if isinstance(obj, (Cube, Sphere, Cylinder)):
        return _render_primitive(obj)

    # A mesh file: JSCAD's modeling library builds geometry in code and has no
    # import() of its own, so the file is named in the script and stands in as
    # the box it fits, which keeps a site with a placed mesh renderable here.
    if isinstance(obj, Import):
        try:
            box = obj.bounds()
        except Exception:  # a file that is not there yet, or not a mesh: an empty union
            return f"union() /* import {obj.file!r}: not read */"
        size = box.max_point - box.min_point
        centre = Vector3D(
            x=(box.min_point.x + box.max_point.x) / 2,
            y=(box.min_point.y + box.max_point.y) / 2,
            z=(box.min_point.z + box.max_point.z) / 2,
        )
        return (
            f"cuboid({{size: {_vec_to_array(size)}, center: {_vec_to_array(centre)}}})"
            f" /* import {obj.file!r}: its bounds */"
        )

    # Booleans
    if isinstance(obj, Union):
        children = ", ".join(_render_node(c) for c in obj.children)
        return f"union({children})"
    if isinstance(obj, Difference):
        children = ", ".join(_render_node(c) for c in obj.children)
        return f"difference({children})"
    if isinstance(obj, Intersection):
        children = ", ".join(_render_node(c) for c in obj.children)
        return f"intersection({children})"

    # Transforms
    if isinstance(obj, Translate):
        children = ", ".join(_render_node(c) for c in obj.children)
        return f"translate({_vec_to_array(obj.v)}, [{children}])"

    if isinstance(obj, Rotate):
        # Normalize angle parameter to [x,y,z]
        if isinstance(obj.a, Vector3D):
            a_str = _vec_to_array(obj.a)
        else:
            a_str = f"[{obj.a}, 0, 0]"  # simple heuristic
        children = ", ".join(_render_node(c) for c in obj.children)
        return f"rotate({a_str}, [{children}])"

    if isinstance(obj, Scale):
        children = ", ".join(_render_node(c) for c in obj.children)
        return f"scale({_vec_to_array(obj.v)}, [{children}])"

    raise TypeError(f"Unsupported object type for JSCAD rendering: {type(obj)!r}")


class JSCADRenderer:
    """Render a :class:`Scene` into a JSCAD module string.

    The generated module:

    - imports primitives/booleans/transforms from `@jscad/modeling`
    - exports a `main` function which returns an array of geometries
    """

    def render_scene(self, scene: Scene) -> str:
        body_nodes: List[str] = []
        for obj in scene.objects:
            body_nodes.append(_render_node(obj))

        geometries = ",\n    ".join(body_nodes) if body_nodes else "[]"

        header = """// Generated by Apothecary -> JSCAD
        import { cube, cuboid, sphere, cylinder } from '@jscad/modeling/src/primitives'
        import { union, difference, intersection } from '@jscad/modeling/src/booleans'
        import { translate, rotate, scale } from '@jscad/modeling/src/transforms'

"""

        main_fn = f"""export const main = () => {{
  return [
    {geometries}
  ]
}}
"""

        return header + main_fn
