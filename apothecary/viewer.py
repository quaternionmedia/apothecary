"""
Viewer module for the Apothecary 3D parts browser.

This module provides the HTML-based viewer for browsing and previewing
OpenSCAD parts. It uses Three.js for 3D rendering with placeholder geometry.

Architecture Notes:
-------------------
The viewer displays placeholder 3D shapes because OpenSCAD files cannot be
directly rendered in a browser. To render actual geometry, you would need:

1. Server-side: Run OpenSCAD to export STL/OBJ, then serve the mesh
2. Client-side: Parse OpenSCAD syntax and recreate geometry (complex)
3. Hybrid: Use a WASM-compiled OpenSCAD (not yet mature)

The current approach provides a functional preview experience while keeping
the architecture simple and ready for future enhancements.
"""

import html
from pathlib import Path
from typing import List, Optional

from jinja2 import Environment, FileSystemLoader

from .projects.parts.skeleton import ROOT

# Template directory
TEMPLATES_DIR = ROOT / "templates"


class ViewerRenderer:
    """Renders the HTML viewer using Jinja2 templates."""

    def __init__(self, templates_dir: Optional[Path] = None):
        """
        Initialize the viewer renderer.

        Args:
            templates_dir: Path to templates directory. Defaults to project templates/
        """
        self.templates_dir = templates_dir or TEMPLATES_DIR
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=False,  # We handle escaping manually for HTML attributes
        )

    def render_viewer(
        self, part_names: List[str], base_url: str, default_part: Optional[str] = None
    ) -> str:
        """
        Render the viewer HTML page.

        Args:
            part_names: List of available part names
            base_url: Base URL for API calls (e.g., "http://localhost:8765")
            default_part: Part to auto-load on page load

        Returns:
            Complete HTML page as a string
        """
        template = self.env.get_template("viewer.html.j2")

        # Build the options HTML with optional selected default
        if part_names:
            options_html = "\n".join(
                f'<option value="{html.escape(name)}"{" selected" if name == default_part else ""}>{html.escape(name)}</option>'
                for name in part_names
            )
            select_disabled = ""
            button_disabled = ""
        else:
            options_html = '<option value="" disabled>No parts found</option>'
            select_disabled = " disabled"
            button_disabled = " disabled"

        return template.render(
            part_options=options_html,
            select_disabled=select_disabled,
            button_disabled=button_disabled,
            base_url=base_url.rstrip("/"),
            default_part=default_part or "",
        )


# Module-level singleton for convenience
_renderer: Optional[ViewerRenderer] = None


def get_viewer_renderer() -> ViewerRenderer:
    """Get or create the viewer renderer singleton."""
    global _renderer
    if _renderer is None:
        _renderer = ViewerRenderer()
    return _renderer


def render_viewer_page(
    part_names: List[str], base_url: str, default_part: Optional[str] = None
) -> str:
    """
    Convenience function to render the viewer page.

    Args:
        part_names: List of available part names
        base_url: Base URL for API calls
        default_part: Part to auto-load on page load

    Returns:
        Complete HTML page as a string
    """
    return get_viewer_renderer().render_viewer(part_names, base_url, default_part)
