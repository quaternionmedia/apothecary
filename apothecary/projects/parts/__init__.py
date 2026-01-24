"""Per-part wrappers with metadata and parameter schemas.

Each module in this package corresponds to a .scad file in the
`parts/<part_name>/` directory. Modules expose a `Part` class that inherits from
`BasePart` and a `Params` Pydantic model describing tunable parameters.
"""


from .base import BasePart
from .part_files import FileStatus, PartFile, PartFiles
from .stl_renderer import OpenSCADRenderer, RenderResult, get_renderer, render_stl

__all__ = [
    "BasePart",
    "PartFiles",
    "PartFile",
    "FileStatus",
    "OpenSCADRenderer",
    "RenderResult",
    "get_renderer",
    "render_stl",
]
