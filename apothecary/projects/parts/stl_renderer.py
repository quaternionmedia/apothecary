"""STL rendering through the OpenSCAD CLI, and ``build_stl``: the one way a
part's STL is built, whichever command or route asks for it."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from .base import BasePart


def scad_literal(value: object) -> str:
    """Render a Python value as an OpenSCAD literal for ``-D``.

    Strings carry their quotes into the argument: OpenSCAD parses ``-D`` values
    as source, so an unquoted word is an identifier and almost always an
    unhelpful error rather than the string that was meant.
    """
    # An Enum's repr (<TabStyle.LEFT: 2>) is not source; its value is.
    if isinstance(value, Enum):
        return scad_literal(value.value)
    # bool before int -- bool is a subclass of it, and true/false are not 1/0.
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            raise ValueError(f"{value!r} has no OpenSCAD literal")
        return repr(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(scad_literal(v) for v in value) + "]"
    if isinstance(value, BaseModel):
        raise TypeError(
            f"{type(value).__name__} is a nested parameter model; -D takes numbers, strings, "
            "booleans and lists, so pass its fields as parameters of their own"
        )
    raise TypeError(f"no OpenSCAD literal for {type(value).__name__}: {value!r}")


def scad_definitions(params: Optional[dict] = None) -> List[str]:
    """``-D name=value`` arguments for a parameter mapping."""
    if not params:
        return []
    args: List[str] = []
    for name, value in params.items():
        args.extend(["-D", f"{name}={scad_literal(value)}"])
    return args


@dataclass
class RenderResult:
    """Result of an STL render operation."""

    success: bool
    stl_path: Optional[Path] = None
    error_message: Optional[str] = None
    render_time_seconds: float = 0.0
    stdout: str = ""
    stderr: str = ""
    # What OpenSCAD dropped on the way ("ERROR:" lines with exit code 0): a
    # mesh it could not read back into a boolean. The file is written and
    # the render succeeded as far as OpenSCAD is concerned; a caller that
    # needs the whole thing (a machine with its body) treats this as failure.
    dropped: List[str] = field(default_factory=list)
    # Why build_stl rendered nothing: "fresh" (the STL on disk already answers
    # the request) or "refused" (the part cannot be built on this machine).
    skipped: Optional[str] = None


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

    # Nightly/development build paths (newer features)
    OPENSCAD_NIGHTLY_PATHS = [
        # Windows
        r"C:\Program Files\OpenSCAD (Nightly)\openscad.exe",
        r"C:\Program Files (x86)\OpenSCAD (Nightly)\openscad.exe",
        # macOS
        "/Applications/OpenSCAD (Nightly).app/Contents/MacOS/OpenSCAD",
        # Linux (common nightly locations)
        "/usr/local/bin/openscad-nightly",
        "/opt/openscad-nightly/bin/openscad",
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
        """OpenSCAD on PATH, else at one of the usual install locations."""
        found = shutil.which("openscad")
        if found:
            return Path(found)
        for path_str in self.OPENSCAD_PATHS:
            path = Path(path_str)
            if path.exists():
                return path
        return None

    @property
    def is_available(self) -> bool:
        """Check if OpenSCAD is available."""
        return self.openscad_path is not None and self.openscad_path.exists()

    def find_nightly(self) -> Optional[Path]:
        """
        Find OpenSCAD Nightly/development build.

        Returns:
            Path to nightly OpenSCAD executable if found, None otherwise.
        """
        for path_str in self.OPENSCAD_NIGHTLY_PATHS:
            path = Path(path_str)
            if path.exists():
                return path
        return None

    def get_nightly_version(self) -> Optional[str]:
        """
        Get version string of the nightly build if available.

        Returns:
            Version string or None if nightly not found.
        """
        nightly = self.find_nightly()
        if not nightly:
            return None

        try:
            result = subprocess.run(
                [str(nightly), "--version"], capture_output=True, text=True, timeout=10
            )
            version = result.stderr.strip() or result.stdout.strip()
            return version if version else None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

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
        params: Optional[dict] = None,
    ) -> RenderResult:
        """Render a SCAD file to STL, with ``params`` passed as ``-D name=value``.

        ``stl_path`` defaults to the SCAD's own name. OpenSCAD writes a temporary
        file beside it that replaces it only on success, so a failed or killed
        render leaves the previous STL, or none, never a partial one.
        """
        if not self.is_available:
            return RenderResult(
                success=False, error_message="OpenSCAD not found. Please install OpenSCAD."
            )

        if not scad_path.exists():
            return RenderResult(success=False, error_message=f"Source file not found: {scad_path}")

        if stl_path is None:
            stl_path = scad_path.with_suffix(".stl")

        # The render runs in the source directory so includes resolve, which
        # would otherwise silently reinterpret a relative output path against
        # it and then report the file as missing.
        scad_path = scad_path.resolve()
        stl_path = stl_path.resolve()
        stl_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            definitions = scad_definitions(params)
        except (TypeError, ValueError) as exc:
            return RenderResult(success=False, error_message=str(exc))

        # The .stl suffix picks OpenSCAD's export format; the leading dot and
        # the suffix keep a file orphaned by a killed process hidden and out of git.
        partial = stl_path.with_name(f".{stl_path.stem}.{uuid.uuid4().hex[:12]}.stl")

        # Definitions precede the source file, which is where OpenSCAD
        # documents them and the only order that is safe to assume.
        cmd = [str(self.openscad_path), "-o", str(partial), *definitions, str(scad_path)]

        start = time.monotonic()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                # OpenSCAD resolves a relative import() against the source
                # file's own directory, so this is for the process, not paths.
                cwd=str(scad_path.parent),
            )
            elapsed = time.monotonic() - start

            if result.returncode != 0:
                return RenderResult(
                    success=False,
                    error_message=f"OpenSCAD failed with code {result.returncode}",
                    render_time_seconds=elapsed,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )

            if not partial.exists():
                return RenderResult(
                    success=False,
                    error_message="OpenSCAD completed but STL file was not created",
                    render_time_seconds=elapsed,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )

            os.replace(partial, stl_path)

            # OpenSCAD 2021.01 exits 0 after dropping an unreadable import
            # ("The given mesh is not closed", a CGAL assertion) from a
            # boolean, and writes what is left. It is reported, so a caller
            # who needs the whole thing can refuse it.
            dropped = [
                line.strip()
                for line in (result.stderr or "").splitlines()
                if line.startswith("ERROR:")
            ]
            return RenderResult(
                success=True,
                stl_path=stl_path,
                render_time_seconds=elapsed,
                stdout=result.stdout,
                stderr=result.stderr,
                dropped=dropped,
            )

        except subprocess.TimeoutExpired:
            return RenderResult(
                success=False, error_message=f"Render timed out after {timeout} seconds"
            )
        except Exception as e:
            return RenderResult(success=False, error_message=f"Render failed: {str(e)}")
        finally:
            partial.unlink(missing_ok=True)

    async def render_stl_async(
        self,
        scad_path: Path,
        stl_path: Optional[Path] = None,
        timeout: float = 120.0,
        params: Optional[dict] = None,
    ) -> RenderResult:
        """render_stl on a worker thread, so the event loop keeps serving."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: self.render_stl(scad_path, stl_path, timeout, params)
        )


def params_sidecar_path(stl_path: Path) -> Path:
    """Where the record of an STL's parameters sits: beside the STL."""
    return stl_path.with_suffix(".params.json")


def _recordable(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"{type(value).__name__} cannot be recorded in a params sidecar")


def write_params_sidecar(stl_path: Path, params: dict) -> Path:
    """Record what produced an STL, next to the STL.

    Without this the file on disk is indistinguishable from a default render,
    and a viewer showing a variant looks exactly like one showing the part.
    """
    sidecar = params_sidecar_path(stl_path)
    sidecar.write_text(
        json.dumps(
            {"params": params, "generated": datetime.now().isoformat(timespec="seconds")},
            indent=2,
            sort_keys=True,
            default=_recordable,
        )
        + chr(10),
        encoding="utf-8",
    )
    return sidecar


def read_params_sidecar(stl_path: Path) -> dict | None:
    """The parameters an existing STL was rendered with, if recorded."""
    sidecar = params_sidecar_path(stl_path)
    if not sidecar.exists():
        return None
    try:
        return json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# Module-level singleton
_renderer: Optional[OpenSCADRenderer] = None


def get_renderer() -> OpenSCADRenderer:
    """Get or create the OpenSCAD renderer singleton."""
    global _renderer
    if _renderer is None:
        _renderer = OpenSCADRenderer()
    return _renderer


def _sources(part: BasePart) -> List[Path]:
    """What a part's STL is built from: its SCAD, and the module (a described
    part's part.json) that sets its rotation and output path.

    The module is found as the loaded wrapper whose DEFAULT is this part.
    """
    sources = [part.source_file]
    for name, module in list(sys.modules.items()):
        if name.startswith("apothecary.projects.parts.") and (
            getattr(module, "DEFAULT", None) is part
        ):
            if getattr(module, "__file__", None):
                sources.append(Path(module.__file__))
            break
    return sources


def _is_fresh(part: BasePart, stl_path: Path, params: dict) -> bool:
    """The STL on disk was rendered with these parameters and is newer than
    everything it was built from."""
    if not stl_path.exists():
        return False
    record = read_params_sidecar(stl_path) or {}
    asked = json.loads(json.dumps(params, default=_recordable))
    if record.get("params", {}) != asked:
        return False
    built = stl_path.stat().st_mtime
    return all(src.stat().st_mtime <= built for src in _sources(part) if src.exists())


def _render_rotated(
    renderer: OpenSCADRenderer,
    scad_path: Path,
    stl_path: Path,
    rotation: List[float],
    timeout: float,
    params: dict,
) -> RenderResult:
    """Render upright into a scratch directory, then turn it with a one-line wrapper.

    Nothing is written beside the source, so two renders of one part cannot collide.
    """
    with tempfile.TemporaryDirectory(prefix="apothecary-rotate-") as tmp:
        upright = Path(tmp) / "upright.stl"
        first = renderer.render_stl(scad_path, upright, timeout, params=params or None)
        if not first.success:
            return first
        wrapper = Path(tmp) / "rotate.scad"
        wrapper.write_text(
            f'rotate({scad_literal(rotation)}) import("{upright.name}");\n', encoding="utf-8"
        )
        second = renderer.render_stl(wrapper, stl_path, timeout)
    second.render_time_seconds += first.render_time_seconds
    second.dropped = first.dropped + second.dropped
    return second


def build_stl(
    part: BasePart,
    params: Optional[dict] = None,
    force: bool = False,
    timeout: float = 120.0,
    renderer: Optional[OpenSCADRenderer] = None,
) -> RenderResult:
    """Build a part's STL at the part's own output path.

    Overrides are checked against the part's ``params_model`` (ValueError on a
    bad one). The STL on disk is kept (``skipped="fresh"``) unless ``force``, a
    newer SCAD or wrapper, or different recorded parameters say otherwise. A
    part that cannot be built here is refused (``skipped="refused"``). The
    render is turned by ``display_rotation``; non-default parameters are
    recorded in the params sidecar, and a default build removes it.
    ``renderer`` overrides the OpenSCAD the part would choose for itself.
    """
    params = part.validate_overrides(params)
    stl_path = part.get_stl_output_path()
    if not force and _is_fresh(part, stl_path, params):
        return RenderResult(success=True, stl_path=stl_path, skipped="fresh")

    can_build, reason = part.can_generate_stl()
    if not can_build:
        return RenderResult(success=False, error_message=reason, skipped="refused")

    if renderer is None:
        own = part.get_openscad_path()
        renderer = OpenSCADRenderer(str(own)) if own else get_renderer()

    rotation = part.display_rotation.to_list()
    if any(rotation):
        result = _render_rotated(renderer, part.source_file, stl_path, rotation, timeout, params)
    else:
        result = renderer.render_stl(part.source_file, stl_path, timeout, params=params or None)

    if result.success:
        if params:
            write_params_sidecar(stl_path, params)
        else:
            params_sidecar_path(stl_path).unlink(missing_ok=True)
    return result
