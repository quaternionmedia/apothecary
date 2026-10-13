"""
Apothecary: OpenSCAD modular framework packaged.

Public API surface re-exported for convenience.

The geometry library reads nothing personal and installs no network guard: a
program that imports it for its shapes keeps its network. The guard
(apothecary/stays_local.py) goes on at the first statement of each module
through which apothecary runs or reads personal data -- the application
module, the command line, and the vision, gathering, firmware and routes
packages -- and at the root conftest.py for the tests.
"""

from . import objects as _objects  # noqa: F401  -- tags every shape before anything builds one
from .booleans import Difference, Hull, Intersection, Union
from .core import OpenSCADObject
from .models.vectors import Vector3D
from .primitives import Cube, Cylinder, Import, Sphere
from .scene import Scene
from .templates import TemplateRenderer
from .transforms import Rotate, Scale, Translate

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
