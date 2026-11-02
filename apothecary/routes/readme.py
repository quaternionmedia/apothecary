"""The root README, served at ``/README.md`` the way ``/docs`` serves its pages.

The URL is the file's path, so a link to ``docs/x.md`` or ``walkthrough/x.md`` is
already the page the app serves for it. A link to a file the app does not serve
(CONTRIBUTING.md, LICENSE, a folder of examples) goes to that file in the
repository, where it is a page rather than a 404 here.
"""

from __future__ import annotations

import html
import posixpath
import re

from fastapi import APIRouter

from .. import docs_site
from ..projects.parts.skeleton import ROOT

REPOSITORY = "https://github.com/quaternionmedia/apothecary"

router = APIRouter()

HREF = re.compile(r'<a href="([^"#?]*)([#?][^"]*)?">')


def _target(path: str) -> str:
    """Where a relative link in the README goes."""
    clean = posixpath.normpath(path)
    first = clean.split("/", 1)[0]
    root = {"docs": docs_site.DOCS_ROOT, "walkthrough": docs_site.WALKTHROUGH_ROOT}.get(first)
    if clean == "README.md":
        return "/README.md"
    if root is not None:
        rest = clean.split("/", 1)[1] if "/" in clean else ""
        if (root / rest).is_file():
            return f"/{first}/{rest}"
        if docs_site._generated(root / rest):  # made here, not committed: kept, and marked
            return f"/{first}/{rest}"
    if (ROOT / clean).is_dir():
        return f"{REPOSITORY}/tree/main/{clean}"
    return f"{REPOSITORY}/blob/main/{clean}"


def rewrite_links(body: str) -> str:
    """Every relative link in ``body``, made to go where the app serves its file."""

    def one(m: re.Match) -> str:
        path = html.unescape(m.group(1))
        if not path or not docs_site._local(path) or path.startswith("/"):
            return m.group(0)
        if re.match(r"^[a-z][a-z0-9+.-]*:", path, re.I):
            return m.group(0)
        return f'<a href="{html.escape(_target(path), quote=True)}{m.group(2) or ""}">'

    return HREF.sub(one, body)


@router.get("/README.md")
async def readme_page():
    body, title = docs_site.render_markdown((ROOT / "README.md").read_text(encoding="utf-8"))
    body = docs_site._mark_absent(rewrite_links(body), ROOT)
    return docs_site._page(body, title or "README", "README.md")
