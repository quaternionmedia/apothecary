"""
Viewer module for the Apothecary fractal zoom viewer.

Renders one HTML-based viewer that navigates any registered site's
``Assembly`` tree (see ``apothecary.hierarchy``) at any depth with the same
controls at every level -- it absorbs both the former standalone parts
browser and the former Site/Structure hierarchy viewer; the registered
``parts/`` library is reached by zooming down to a leaf, not a separate page.

Architecture Notes:
-------------------
Nodes render as bounding-box wireframes today because OpenSCAD/STL geometry
cannot be directly rendered in a browser without a render round-trip. The
per-node geometry loader is architected as an async seam (see
``fractal_viewer.html.j2``'s ``loadNodeGeometry``) so real geometry (Three.js
primitives translated client-side, or OpenSCAD-rendered STL) can be plugged
in later without restructuring the navigation code around it.
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

    def render_fractal_viewer(
        self,
        site_names: List[str],
        base_url: str,
        default_site: Optional[str] = None,
        focus_path: str = "",
    ) -> str:
        """Render the fractal zoom viewer HTML page (prototype).

        Absorbs the previous parts browser and Site/Structure hierarchy
        viewer into one page: navigates any registered site's Assembly tree
        at any depth with the same controls at every level.

        Args:
            site_names: List of available site names (see apothecary.api's site registry)
            base_url: Base URL for API calls
            default_site: Site to auto-load on page load
            focus_path: Optional dotted path (e.g. "workbench.frame_system")
                to open the view already zoomed to that node

        Returns:
            Complete HTML page as a string
        """
        template = self.env.get_template("fractal_viewer.html.j2")

        if site_names:
            options_html = "\n".join(
                f'<option value="{html.escape(name)}"{" selected" if name == default_site else ""}>{html.escape(name)}</option>'
                for name in site_names
            )
            select_disabled = ""
        else:
            options_html = '<option value="" disabled>No sites found</option>'
            select_disabled = " disabled"

        return template.render(
            site_options=options_html,
            select_disabled=select_disabled,
            base_url=base_url.rstrip("/"),
            default_site=default_site or "",
            focus_path=focus_path or "",
        )


# Module-level singleton for convenience
_renderer: Optional[ViewerRenderer] = None


def get_viewer_renderer() -> ViewerRenderer:
    """Get or create the viewer renderer singleton."""
    global _renderer
    if _renderer is None:
        _renderer = ViewerRenderer()
    return _renderer


def render_fractal_viewer_page(
    site_names: List[str],
    base_url: str,
    default_site: Optional[str] = None,
    focus_path: str = "",
) -> str:
    """
    Convenience function to render the fractal zoom viewer page (prototype).

    Args:
        site_names: List of available site names
        base_url: Base URL for API calls
        default_site: Site to auto-load on page load
        focus_path: Optional dotted path to open the view already zoomed to

    Returns:
        Complete HTML page as a string
    """
    return get_viewer_renderer().render_fractal_viewer(
        site_names, base_url, default_site, focus_path
    )
