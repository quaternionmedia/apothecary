"""
Apothecary: OpenSCAD modular framework packaged.

Public API surface re-exported for convenience.
"""

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
