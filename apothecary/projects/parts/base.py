from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Type

from pydantic import BaseModel, Field, computed_field

from apothecary.models import (
    GRAY,
    BoundingBox3D,
    Color,
    PrintSettings,
    Vector3D,
)

if TYPE_CHECKING:
    from .part_files import PartFiles


class ContestedValue(BaseModel):
    """One source's answer for a parameter that sources disagree about.

    A number two documents state differently is not a detail to be settled by
    whoever edits last. Recording the candidates with their provenance puts the
    disagreement somewhere a person can see it -- and, through the part
    dashboard, turn instead of argue about.
    """

    value: float
    source: str
    note: str = ""


class BasePart(BaseModel):
    """Base metadata wrapper for a single SCAD part."""

    name: str
    source_file: Path
    description: Optional[str] = None
    params_model: Optional[Type[BaseModel]] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    readme_path: Optional[Path] = None
    module_name: Optional[str] = None
    param_map: Dict[str, str] = Field(default_factory=dict)

    # Geometry metadata
    default_bounds: Optional[BoundingBox3D] = None
    preview_color: Color = Field(default_factory=lambda: GRAY)
    print_settings: Optional[PrintSettings] = None

    # Display orientation: rotation [rx, ry, rz] in degrees to apply
    # for preferred "up" orientation (Z-up, sitting on ground plane)
    display_rotation: Vector3D = Field(default_factory=Vector3D)

    # Parameters whose value is genuinely in dispute, keyed by parameter name.
    # Empty for a part nobody disagrees about, which is most of them.
    contested: Dict[str, List[ContestedValue]] = Field(default_factory=dict)

    @property
    def exists(self) -> bool:
        return self.source_file.exists()

    @property
    def part_dir(self) -> Path:
        """Get the part's directory (parent of source file)."""
        return self.source_file.parent

    @computed_field
    @property
    def stl_file(self) -> Optional[Path]:
        """Get the STL file path if it exists."""
        stl_path = self.get_stl_output_path()
        return stl_path if stl_path.exists() else None

    def get_stl_output_path(self) -> Path:
        """
        Get the path where STL should be written.

        Override in subclasses for custom STL locations (e.g., submodule parts).
        Default is same directory as source file with .stl extension.
        """
        return self.source_file.with_suffix(".stl")

    @computed_field
    @property
    def jscad_file(self) -> Optional[Path]:
        """Get the JSCAD file path if it exists."""
        jscad_path = self.source_file.with_suffix(".jscad")
        return jscad_path if jscad_path.exists() else None

    def get_files(self) -> "PartFiles":
        """Get a PartFiles instance for this part."""
        from .part_files import PartFiles

        return PartFiles.from_scad_file(self.source_file)

    def get_bounds(self, params: Optional[Dict] = None) -> Optional[BoundingBox3D]:
        """
        Calculate bounding box for the part with given parameters.

        Override in subclasses for accurate bounds calculation.
        Falls back to default_bounds if not overridden.
        """
        return self.default_bounds

    def get_center(self, params: Optional[Dict] = None) -> Vector3D:
        """Get the center point of the part."""
        bounds = self.get_bounds(params)
        if bounds:
            return bounds.center
        return Vector3D()

    def get_size(self, params: Optional[Dict] = None) -> Vector3D:
        """Get the size of the part as a vector."""
        bounds = self.get_bounds(params)
        if bounds:
            return bounds.size
        return Vector3D()

    def to_geometry_dict(self, params: Optional[Dict] = None) -> Dict:
        """Export geometry metadata for API/viewer."""
        bounds = self.get_bounds(params)
        return {
            "bounds": (
                {
                    "min": bounds.min_point.to_list() if bounds else None,
                    "max": bounds.max_point.to_list() if bounds else None,
                    "size": bounds.size.to_list() if bounds else None,
                    "center": bounds.center.to_list() if bounds else None,
                }
                if bounds
                else None
            ),
            "color": self.preview_color.to_openscad(),
            "color_hex": self.preview_color.to_hex(),
        }
