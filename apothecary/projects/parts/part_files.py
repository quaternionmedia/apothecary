"""
Data model linking SCAD, JSCAD, and STL files for a part.

This module provides a unified way to track all output formats for a part,
including generation status and timestamps.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, computed_field


class FileStatus(str, Enum):
    """Status of a generated file."""

    MISSING = "missing"  # File doesn't exist
    PRESENT = "present"  # File exists
    STALE = "stale"  # File exists but source is newer
    GENERATING = "generating"  # Currently being generated


class PartFile(BaseModel):
    """Metadata for a single file associated with a part."""

    path: Path
    format: str  # "scad", "jscad", "stl"

    @computed_field
    @property
    def exists(self) -> bool:
        return self.path.exists()

    @computed_field
    @property
    def size_bytes(self) -> Optional[int]:
        if self.path.exists():
            return self.path.stat().st_size
        return None

    @computed_field
    @property
    def modified_at(self) -> Optional[datetime]:
        if self.path.exists():
            return datetime.fromtimestamp(self.path.stat().st_mtime)
        return None

    def read_text(self) -> str:
        """Read file contents as text."""
        return self.path.read_text(encoding="utf-8")

    def read_bytes(self) -> bytes:
        """Read file contents as bytes (for STL)."""
        return self.path.read_bytes()


class PartFiles(BaseModel):
    """
    Links all output files for a single part.

    Organizes files within a part's directory structure:
        parts/<part_name>/
            <part_name>.scad     # Source file
            <part_name>.jscad    # Generated JSCAD (optional)
            <part_name>.stl      # Generated STL (optional)
    """

    part_name: str
    part_dir: Path

    # File references
    scad_file: PartFile
    jscad_file: Optional[PartFile] = None
    stl_file: Optional[PartFile] = None

    # Generation metadata
    last_stl_generation: Optional[datetime] = None
    stl_generation_error: Optional[str] = None

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def from_part_dir(cls, part_dir: Path, part_name: str) -> "PartFiles":
        """
        Create PartFiles from a part directory.

        Args:
            part_dir: Path to the part's directory (e.g., parts/parametric_star/)
            part_name: Name of the part

        Returns:
            PartFiles instance with file references
        """
        # Normalize part name for filenames
        file_base = part_name.replace("-", "_").replace(" ", "_")

        scad_path = part_dir / f"{file_base}.scad"
        jscad_path = part_dir / f"{file_base}.jscad"
        stl_path = part_dir / f"{file_base}.stl"

        return cls(
            part_name=part_name,
            part_dir=part_dir,
            scad_file=PartFile(path=scad_path, format="scad"),
            jscad_file=PartFile(path=jscad_path, format="jscad") if jscad_path.exists() else None,
            stl_file=PartFile(path=stl_path, format="stl") if stl_path.exists() else None,
        )

    @classmethod
    def from_scad_file(cls, scad_path: Path) -> "PartFiles":
        """
        Create PartFiles from an existing SCAD file path.

        Handles both flat structure (parts/foo.scad) and
        folder structure (parts/foo/foo.scad).

        Args:
            scad_path: Path to the SCAD source file

        Returns:
            PartFiles instance
        """
        part_name = scad_path.stem

        # Check if SCAD is in a part-specific folder or flat parts/ dir
        if scad_path.parent.name == part_name:
            # Already in folder structure: parts/foo/foo.scad
            part_dir = scad_path.parent
        else:
            # Flat structure: parts/foo.scad -> treat parts/ as the dir
            part_dir = scad_path.parent

        file_base = part_name.replace("-", "_").replace(" ", "_")
        jscad_path = part_dir / f"{file_base}.jscad"
        stl_path = part_dir / f"{file_base}.stl"

        return cls(
            part_name=part_name,
            part_dir=part_dir,
            scad_file=PartFile(path=scad_path, format="scad"),
            jscad_file=PartFile(path=jscad_path, format="jscad") if jscad_path.exists() else None,
            stl_file=PartFile(path=stl_path, format="stl") if stl_path.exists() else None,
        )

    def get_stl_status(self) -> FileStatus:
        """Check the status of the STL file relative to the source."""
        if self.stl_file is None or not self.stl_file.exists:
            return FileStatus.MISSING

        if not self.scad_file.exists:
            return FileStatus.PRESENT  # No source to compare

        # Check if STL is older than source
        scad_mtime = self.scad_file.modified_at
        stl_mtime = self.stl_file.modified_at

        if scad_mtime and stl_mtime and scad_mtime > stl_mtime:
            return FileStatus.STALE

        return FileStatus.PRESENT

    def ensure_stl_path(self) -> Path:
        """Get the expected STL path, creating parent dirs if needed."""
        file_base = self.part_name.replace("-", "_").replace(" ", "_")
        stl_path = self.part_dir / f"{file_base}.stl"
        stl_path.parent.mkdir(parents=True, exist_ok=True)
        return stl_path

    def to_api_dict(self, base_url: str = "") -> dict:
        """
        Convert to a dictionary suitable for API responses.

        Args:
            base_url: Optional base URL to prepend to download paths

        Returns:
            Dictionary with file metadata and download URLs
        """
        result = {
            "part_name": self.part_name,
            "scad": {
                "exists": self.scad_file.exists,
                "size_bytes": self.scad_file.size_bytes,
                "download_url": f"{base_url}/parts/{self.part_name}/scad",
            },
        }

        if self.jscad_file:
            result["jscad"] = {
                "exists": self.jscad_file.exists,
                "size_bytes": self.jscad_file.size_bytes,
                "download_url": f"{base_url}/parts/{self.part_name}/jscad",
            }

        if self.stl_file:
            result["stl"] = {
                "exists": self.stl_file.exists,
                "size_bytes": self.stl_file.size_bytes,
                "status": self.get_stl_status().value,
                "download_url": f"{base_url}/parts/{self.part_name}/stl",
            }
        else:
            result["stl"] = {
                "exists": False,
                "status": FileStatus.MISSING.value,
                "generate_url": f"{base_url}/parts/{self.part_name}/stl/generate",
            }

        return result
