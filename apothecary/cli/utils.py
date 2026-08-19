"""Shared utilities for CLI commands."""

import struct
from importlib import import_module
from pathlib import Path

import click


def _safe_echo(message: str, **style):
    """Echo message with safe encoding handling for Windows.

    Accepts the same styling keywords as ``click.secho``; with none it behaves
    as ``click.echo``. A console on a legacy code page -- cp1252 is still the
    default on Windows -- raises rather than dropping the glyph, so every line
    carrying one has to come through here.
    """
    try:
        click.secho(message, **style)
    except UnicodeEncodeError:
        # Fallback: replace special characters with ASCII equivalents
        message = message.replace("✓", "[OK]").replace("✗", "[X]").replace("⚠️", "[!]")
        message = message.replace("•", "-")
        click.secho(message, **style)


def _load_part_wrapper(name: str):
    """Import a part wrapper by part name (stem)."""
    module_name = name.lower().replace("-", "_").replace(" ", "_").replace(".", "_")
    full = f"apothecary.projects.parts.{module_name}"
    try:
        mod = import_module(full)
    except ModuleNotFoundError as e:
        raise click.ClickException(
            f"No wrapper module found for part '{name}'. Tried module '{full}'. "
            "Run 'apothecary parts list' to see available parts."
        ) from e
    if not hasattr(mod, "DEFAULT"):
        raise click.ClickException(f"Wrapper module '{full}' has no DEFAULT instance")
    return mod


def _get_stl_bounding_box(stl_path: Path) -> tuple[float, float, float, float, float, float] | None:
    """Parse an STL file and return its bounding box (min_x, max_x, min_y, max_y, min_z, max_z)."""
    if not stl_path.exists():
        return None

    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")

    try:
        with open(stl_path, "rb") as f:
            # Check if binary or ASCII STL
            f.read(80)  # Skip 80-byte header
            num_triangles = struct.unpack("<I", f.read(4))[0]

            # Binary STL: 80 byte header + 4 byte count + 50 bytes per triangle
            expected_size = 84 + (num_triangles * 50)
            f.seek(0, 2)  # Seek to end
            actual_size = f.tell()

            if actual_size == expected_size:
                # Binary STL
                f.seek(84)  # Skip header and count
                for _ in range(num_triangles):
                    # Skip normal (12 bytes), read 3 vertices (36 bytes), skip attribute (2 bytes)
                    f.read(12)  # normal
                    for _ in range(3):  # 3 vertices
                        x, y, z = struct.unpack("<fff", f.read(12))
                        min_x, max_x = min(min_x, x), max(max_x, x)
                        min_y, max_y = min(min_y, y), max(max_y, y)
                        min_z, max_z = min(min_z, z), max(max_z, z)
                    f.read(2)  # attribute byte count
            else:
                # ASCII STL - parse text
                f.seek(0)
                content = f.read().decode("utf-8", errors="ignore")
                import re

                for match in re.finditer(
                    r"vertex\s+([-\d.e+]+)\s+([-\d.e+]+)\s+([-\d.e+]+)", content, re.IGNORECASE
                ):
                    x, y, z = float(match.group(1)), float(match.group(2)), float(match.group(3))
                    min_x, max_x = min(min_x, x), max(max_x, x)
                    min_y, max_y = min(min_y, y), max(max_y, y)
                    min_z, max_z = min(min_z, z), max(max_z, z)

        if min_x == float("inf"):
            return None

        return (min_x, max_x, min_y, max_y, min_z, max_z)
    except Exception:
        return None
