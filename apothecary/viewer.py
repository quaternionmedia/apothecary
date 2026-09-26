"""The fractal viewer page: one template that navigates any registered site's tree.

Every node draws as a box at once; real geometry replaces it in the background
(see ``scheduleWaveLoad`` in ``templates/fractal_viewer.html.j2``): a plain
primitive is built in the browser, a part fetches its STL, and a composite node
fetches the STL the server renders from its subtree.
"""

from typing import List, Optional

from jinja2 import Environment, FileSystemLoader

from .projects.parts.skeleton import ROOT

_ENV = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=True)


def render_fractal_viewer_page(
    site_names: List[str],
    base_url: str,
    default_site: Optional[str] = None,
    focus_path: str = "",
    three_is_vendored: bool = True,
) -> str:
    """The viewer page, opened on ``default_site`` and, when ``focus_path`` names a
    node (``workbench.frame_system``), already zoomed to it."""
    return _ENV.get_template("fractal_viewer.html.j2").render(
        site_names=site_names,
        base_url=base_url.rstrip("/"),
        default_site=default_site or "",
        focus_path=focus_path or "",
        three_is_vendored=three_is_vendored,
    )
