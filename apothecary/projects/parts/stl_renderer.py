"""
STL rendering service using OpenSCAD CLI.

This module provides functionality to generate STL files from OpenSCAD source
files using the OpenSCAD command-line interface.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .part_files import PartFile, PartFiles


@dataclass
class RenderResult:
    """Result of an STL render operation."""

    success: bool
    stl_path: Optional[Path] = None
    error_message: Optional[str] = None
    render_time_seconds: float = 0.0
    stdout: str = ""
    stderr: str = ""


class OpenSCADRenderer:
    """
    Renders SCAD files to STL using OpenSCAD CLI.

    Automatically detects OpenSCAD installation on common paths.
    """

    # Common OpenSCAD installation paths
    OPENSCAD_PATHS = [
        # Windows
        r"C:\Program Files\OpenSCAD\openscad.exe",
        r"C:\Program Files (x86)\OpenSCAD\openscad.exe",
        # macOS
        "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD",
        # Linux
        "/usr/bin/openscad",
        "/usr/local/bin/openscad",
        "/snap/bin/openscad",
    ]

    def __init__(self, openscad_path: Optional[str] = None):
        """
        Initialize the renderer.

        Args:
            openscad_path: Explicit path to OpenSCAD executable.
                          If None, auto-detects from common paths.
        """
        self._openscad_path = openscad_path
        self._detected_path: Optional[Path] = None

    @property
    def openscad_path(self) -> Optional[Path]:
        """Get the path to OpenSCAD executable."""
        if self._openscad_path:
            return Path(self._openscad_path)

        if self._detected_path is None:
            self._detected_path = self._detect_openscad()

        return self._detected_path

    def _detect_openscad(self) -> Optional[Path]:
        """Auto-detect OpenSCAD installation."""
        # First try 'which' / 'where' command
        which_cmd = "where" if shutil.which("where") else "which"
        try:
            result = subprocess.run(
                [which_cmd, "openscad"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                path = Path(result.stdout.strip().split("\n")[0])
                if path.exists():
                    return path
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Continue to next search method if command fails
            pass

        # Check common paths
        for path_str in self.OPENSCAD_PATHS:
            path = Path(path_str)
            if path.exists():
                return path

        return None

    @property
    def is_available(self) -> bool:
        """Check if OpenSCAD is available."""
        return self.openscad_path is not None and self.openscad_path.exists()

    def get_version(self) -> Optional[str]:
        """Get OpenSCAD version string."""
        if not self.is_available:
            return None

        try:
            result = subprocess.run(
                [str(self.openscad_path), "--version"], capture_output=True, text=True, timeout=10
            )
            # Version is usually in stderr for OpenSCAD
            version = result.stderr.strip() or result.stdout.strip()
            return version if version else None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

    def render_stl(
        self,
        scad_path: Path,
        stl_path: Optional[Path] = None,
        timeout: float = 120.0,
        extra_args: Optional[list] = None,
    ) -> RenderResult:
        """
        Render a SCAD file to STL.

        Args:
            scad_path: Path to the source SCAD file
            stl_path: Output STL path. If None, uses same directory as SCAD
            timeout: Maximum render time in seconds
            extra_args: Additional arguments to pass to OpenSCAD

        Returns:
            RenderResult with success status and file path
        """
        if not self.is_available:
            return RenderResult(
                success=False, error_message="OpenSCAD not found. Please install OpenSCAD."
            )

        if not scad_path.exists():
            return RenderResult(success=False, error_message=f"Source file not found: {scad_path}")

        # Determine output path
        if stl_path is None:
            stl_path = scad_path.with_suffix(".stl")

        # Ensure output directory exists
        stl_path.parent.mkdir(parents=True, exist_ok=True)

        # Build command
        cmd = [str(self.openscad_path), "-o", str(stl_path), str(scad_path)]

        if extra_args:
            cmd.extend(extra_args)

        # Execute render
        start_time = datetime.now()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(scad_path.parent),  # Run in source directory for includes
            )

            elapsed = (datetime.now() - start_time).total_seconds()

            if result.returncode != 0:
                return RenderResult(
                    success=False,
                    error_message=f"OpenSCAD failed with code {result.returncode}",
                    render_time_seconds=elapsed,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )

            if not stl_path.exists():
                return RenderResult(
                    success=False,
                    error_message="OpenSCAD completed but STL file was not created",
                    render_time_seconds=elapsed,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )

            return RenderResult(
                success=True,
                stl_path=stl_path,
                render_time_seconds=elapsed,
                stdout=result.stdout,
                stderr=result.stderr,
            )

        except subprocess.TimeoutExpired:
            return RenderResult(
                success=False, error_message=f"Render timed out after {timeout} seconds"
            )
        except Exception as e:
            return RenderResult(success=False, error_message=f"Render failed: {str(e)}")

    def render_stl_with_rotation(
        self,
        scad_path: Path,
        stl_path: Optional[Path] = None,
        rotation: Optional[List[float]] = None,
        timeout: float = 120.0,
    ) -> RenderResult:
        """
        Render a SCAD file to STL with optional rotation applied.

        This is a two-step process:
        1. Render the original SCAD to a temporary STL
        2. Create a wrapper that imports and rotates the STL, then render to final output

        Args:
            scad_path: Path to the source SCAD file
            stl_path: Output STL path. If None, uses same directory as SCAD
            rotation: [rx, ry, rz] rotation in degrees to apply
            timeout: Maximum render time in seconds

        Returns:
            RenderResult with success status and file path
        """
        # If no rotation, use standard render
        if rotation is None or rotation == [0, 0, 0]:
            return self.render_stl(scad_path, stl_path, timeout)

        if not self.is_available:
            return RenderResult(
                success=False, error_message="OpenSCAD not found. Please install OpenSCAD."
            )

        if not scad_path.exists():
            return RenderResult(success=False, error_message=f"Source file not found: {scad_path}")

        # Determine output path
        if stl_path is None:
            stl_path = scad_path.with_suffix(".stl")

        # Ensure output directory exists
        stl_path.parent.mkdir(parents=True, exist_ok=True)

        # Step 1: Render original SCAD to temp STL
        temp_stl = scad_path.parent / f"_temp_{scad_path.stem}.stl"

        try:
            # First render without rotation
            result1 = self.render_stl(scad_path, temp_stl, timeout)
            if not result1.success:
                return result1

            # Step 2: Create wrapper that imports and rotates the temp STL
            wrapper_content = f"""// Auto-generated wrapper for rotation
// Source: {scad_path.name}
// Rotation: {rotation}

rotate([{rotation[0]}, {rotation[1]}, {rotation[2]}])
    import("{temp_stl.name}");
"""
            wrapper_path = scad_path.parent / f"_wrapper_{scad_path.stem}.scad"
            wrapper_path.write_text(wrapper_content, encoding="utf-8")

            try:
                # Render the rotated version
                result2 = self.render_stl(wrapper_path, stl_path, timeout)

                # Combine timing
                result2.render_time_seconds += result1.render_time_seconds

                return result2

            finally:
                # Clean up wrapper
                if wrapper_path.exists():
                    wrapper_path.unlink()

        finally:
            # Clean up temp STL
            if temp_stl.exists():
                temp_stl.unlink()

    async def render_stl_async(
        self,
        scad_path: Path,
        stl_path: Optional[Path] = None,
        timeout: float = 120.0,
        extra_args: Optional[list] = None,
    ) -> RenderResult:
        """
        Async version of render_stl.

        Runs the OpenSCAD process in a thread pool to avoid blocking.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self.render_stl(scad_path, stl_path, timeout, extra_args)
        )

    def render_part_files(
        self, part_files: PartFiles, force: bool = False, timeout: float = 120.0
    ) -> Tuple[PartFiles, RenderResult]:
        """
        Render STL for a PartFiles instance.

        Args:
            part_files: The part files to render
            force: If True, regenerate even if STL exists and is fresh
            timeout: Maximum render time

        Returns:
            Tuple of (updated PartFiles, RenderResult)
        """
        from .part_files import FileStatus

        status = part_files.get_stl_status()

        # Skip if already up-to-date (unless forced)
        if status == FileStatus.PRESENT and not force:
            return part_files, RenderResult(
                success=True,
                stl_path=part_files.stl_file.path if part_files.stl_file else None,
                error_message="STL already up-to-date (use force=True to regenerate)",
            )

        # Render
        stl_path = part_files.ensure_stl_path()
        result = self.render_stl(part_files.scad_file.path, stl_path, timeout)

        # Update part_files with new STL reference
        if result.success and result.stl_path:
            part_files.stl_file = PartFile(path=result.stl_path, format="stl")
            part_files.last_stl_generation = datetime.now()
            part_files.stl_generation_error = None
        else:
            part_files.stl_generation_error = result.error_message

        return part_files, result


# Module-level singleton
_renderer: Optional[OpenSCADRenderer] = None


def get_renderer() -> OpenSCADRenderer:
    """Get or create the OpenSCAD renderer singleton."""
    global _renderer
    if _renderer is None:
        _renderer = OpenSCADRenderer()
    return _renderer


def render_stl(scad_path: Path, stl_path: Optional[Path] = None) -> RenderResult:
    """Convenience function to render a SCAD file to STL."""
    return get_renderer().render_stl(scad_path, stl_path)


async def render_stl_async(scad_path: Path, stl_path: Optional[Path] = None) -> RenderResult:
    """Convenience async function to render a SCAD file to STL."""
    return await get_renderer().render_stl_async(scad_path, stl_path)
