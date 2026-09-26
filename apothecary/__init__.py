"""
Apothecary: OpenSCAD modular framework packaged.

Public API surface re-exported for convenience.
"""

# Before anything else in the package runs: this process reaches nothing but
# this machine (apothecary/stays_local.py). Not a setting; the package's shape.
from .stays_local import install_guard as _install_guard

_install_guard()

from .booleans import Difference, Hull, Intersection, Union  # noqa: E402
from .core import OpenSCADObject  # noqa: E402
from .models.vectors import Vector3D  # noqa: E402
from .primitives import Cube, Cylinder, Import, Sphere  # noqa: E402
from .scene import Scene  # noqa: E402
from .templates import TemplateRenderer  # noqa: E402
from .transforms import Rotate, Scale, Translate  # noqa: E402

__all__ = [
    "Vector3D",
    "OpenSCADObject",
    "Cube",
    "Sphere",
    "Cylinder",
    "Import",
    "Translate",
    "Rotate",
    "Scale",
    "Union",
    "Difference",
    "Intersection",
    "Hull",
    "Scene",
    "TemplateRenderer",
]
