"""The documentation served by the viewer's server: /docs and /walkthrough."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from apothecary import docs_site
from apothecary.api import app
from apothecary.projects.parts.skeleton import ROOT


def test_the_renderer_covers_what_the_docs_use():
    text = (
        "# A title with `code`\n\n"
        "Some *emphasis*, **strong**, a [link](other.md#control-behind-a-latch), "
        "an image ![alt](pic.png) and <b>raw html</b>.\n\n"
        "## Control, behind a latch\n\n"
        "- one\n- two\n  - nested\n- [ ] a task\n- [x] done\n\n"
        "1. first\n2. second\n\n"
        "| Route | Purpose |\n|---|---|\n| `GET /x` | the x |\n\n"
        "```bash\nuv run apothecary serve\n```\n\n"
        "> a quote\n\n---\n\nlast line  \nbroken here\n"
    )
    body, title = docs_site.render_markdown(text)
    assert title == "A title with code"
    assert '<h1 id="a-title-with-code">A title with <code>code</code></h1>' in body
    assert '<h2 id="control-behind-a-latch">' in body
    assert "<em>emphasis</em>" in body and "<strong>strong</strong>" in body
    assert '<a href="other.md#control-behind-a-latch">link</a>' in body
    assert '<img src="pic.png" alt="alt">' in body
    away, _ = docs_site.render_markdown("![a face](https://elsewhere.example/face.png)")
    assert "<img" not in away and "[picture elsewhere: a face]" in away
    # A link is a link when a person may click it: relative, http(s), mailto.
    # Any other scheme is shown as the text it was, never as something that runs.
    links, _ = docs_site.render_markdown(
        "[go](javascript:alert(1)) [d](data:text/html,x) [v](vbscript:x) "
        "[ok](https://example.org/) [mail](mailto:a@b.c) [rel](../x.md)"
    )
    assert "javascript:" not in links.replace("go (javascript:alert(1))", "")
    assert "go (javascript:alert(1))" in links and "d (data:text/html,x)" in links
    assert '<a href="https://example.org/">ok</a>' in links
    assert '<a href="mailto:a@b.c">mail</a>' in links and '<a href="../x.md">rel</a>' in links
    assert "&lt;b&gt;raw html&lt;/b&gt;" in body  # shown, not run
    assert "<ul><li>one</li><li>two<ul><li>nested</li></ul></li>" in body
    assert '<input type="checkbox" disabled> a task' in body
    assert '<input type="checkbox" disabled checked> done' in body
    assert "<ol><li>first</li><li>second</li></ol>" in body
    assert "<table><thead><tr><th>Route</th><th>Purpose</th></tr></thead>" in body
    assert "<td><code>GET /x</code></td>" in body
    assert '<pre><code class="language-bash">uv run apothecary serve</code></pre>' in body
    assert "<blockquote><p>a quote</p></blockquote>" in body
    assert "<hr>" in body and "last line<br>" in body


def test_every_page_renders_and_its_links_resolve():
    """Every Markdown page under docs/ and walkthrough/ renders, and every relative
    link between pages points at a file that exists (the URL is the path)."""
    c = TestClient(app)
    missing = []
    for url in docs_site.pages():
        r = c.get(url)
        assert r.status_code == 200, url
        assert "<main>" in r.text
        root = docs_site.DOCS_ROOT if url.startswith("/docs/") else docs_site.WALKTHROUGH_ROOT
        here = (root / url.split("/", 2)[2]).parent
        text = (root / url.split("/", 2)[2]).read_text(encoding="utf-8")
        for target in docs_site.LINK.findall(text):
            href = target[1]
            if "://" in href or href.startswith(("#", "mailto:")):
                continue
            rel = href.split("#", 1)[0]
            if not rel:
                continue
            path = (here / rel).resolve()
            if not path.exists() and "generated/" not in rel:
                missing.append(f"{url} -> {href}")
    assert not missing, "\n".join(missing)


ROOT_DOCS = ["README.md", "QUICKSTART.md", "CONTRIBUTING.md", "AGENTS.md", "CHANGELOG.md"]
FENCE = re.compile(r"^```.*?^```", re.M | re.S)
REMOVED = re.compile(r"^### Removed$.*?(?=^#|\Z)", re.M | re.S)  # names what is gone
HTML_LINK = re.compile(r'\b(?:src|href)="([^"]+)"')
CODE_SPAN = re.compile(r"`([^`\n]+)`")
TOP = ["governance", "apothecary", "docs", "parts", "tests", "walkthrough", "templates", "examples"]
REPO_DIRS = tuple(f"{d}/" for d in TOP)


def _names_a_repo_path(span: str) -> bool:
    """A code span that names a file or folder here: under a top-level directory,
    or a Markdown file or folder anywhere. A placeholder or wildcard is a pattern,
    and a route, a home-relative or dot path, or docs/generated/ is not committed."""
    if any(c in span for c in " <>*{}\\") or span.startswith(("/", "~", ".", "docs/generated/")):
        return False
    return span.startswith(REPO_DIRS) or span.endswith((".md", "/"))


def test_the_root_docs_name_only_files_that_exist():
    """README, QUICKSTART, CONTRIBUTING, AGENTS and CHANGELOG link to, and name in
    code, only files and folders this checkout has."""
    governance = (ROOT / "governance" / "qm" / "README.md").exists()
    missing = []
    for name in ROOT_DOCS:
        text = (ROOT / name).read_text(encoding="utf-8")
        hrefs = [href for _, href in docs_site.LINK.findall(text)] + HTML_LINK.findall(text)
        for href in hrefs:
            rel = href.split("#", 1)[0]
            if "://" in href or href.startswith("mailto:") or not rel:
                continue
            if not (ROOT / rel).exists():
                missing.append(f"{name} -> {href}")
        for span in CODE_SPAN.findall(REMOVED.sub("", FENCE.sub("", text))):
            if not _names_a_repo_path(span):
                continue
            if span.startswith("governance/") and not governance:
                continue  # the submodule is not checked out: git submodule update --init
            if not (ROOT / span).exists():
                missing.append(f"{name} -> `{span}`")
    assert not missing, "\n".join(missing)


def test_the_parts_authoring_wrapper_builds_a_part():
    """The wrapper docs/parts-authoring.md gives, run as a module of the parts
    package, builds a part whose bounds follow its parameters."""
    text = (ROOT / "docs" / "parts-authoring.md").read_text(encoding="utf-8")
    source = re.search(r"^## A wrapper$.*?^```python\n(.*?)^```", text, re.M | re.S).group(1)
    module = {
        "__name__": "apothecary.projects.parts.my_part",
        "__package__": "apothecary.projects.parts",
    }
    exec(compile(source, "docs/parts-authoring.md", "exec"), module)
    part = module["DEFAULT"]
    assert part.name == "my_part"
    assert part.source_file == ROOT / "parts" / "my_part" / "my_part.scad"
    assert part.get_bounds({"size": 30}).size.x == 30
    with pytest.raises(ValueError, match="unknown parameter"):
        part.validate_overrides({"sizee": 30})


def test_docs_routes_serve_pages_and_files_and_refuse_the_rest(tmp_path, monkeypatch):
    c = TestClient(app)
    assert c.get("/docs", follow_redirects=False).status_code in (302, 307)
    r = c.get("/docs/README.md")
    assert r.status_code == 200 and "Apothecary" in r.text and 'href="/openapi.json"' in r.text
    r = c.get("/docs/firmware.md")
    assert 'id="control-behind-a-latch"' in r.text
    r = c.get("/docs/validation/dry-run-square.gcode")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert c.get("/docs/../pyproject.toml").status_code in (404, 422)
    assert c.get("/docs/no-such-page.md").status_code == 404
    assert c.get("/walkthrough/01-a-part.md").status_code == 200
    # The API is described by /openapi.json; FastAPI's Swagger and ReDoc pages are off,
    # since each would load its script from a public CDN.
    assert c.get("/openapi.json").status_code == 200
    assert c.get("/api/docs").status_code == 404 and c.get("/docs/../api/docs").status_code in (
        404,
        422,
    )


def test_the_bar_says_what_the_last_refresh_did(tmp_path, monkeypatch):
    monkeypatch.setattr(docs_site, "GENERATED_ROOT", tmp_path)
    monkeypatch.setattr(docs_site, "REFRESH_STATE", tmp_path / ".refresh.json")
    assert docs_site.refresh_note()[1] == "generated docs: not refreshed yet"
    docs_site.note_refresh(started="2026-09-20T13:00:00+00:00", finished=None, ok=None)
    cls, text, _ = docs_site.refresh_note()
    assert cls == "running" and text.startswith("generated docs: refreshing since")
    docs_site.note_refresh(finished="2026-09-20T13:02:00+00:00", ok=False, error="no browser")
    cls, text, tip = docs_site.refresh_note()
    assert cls == "failed" and "failed" in text and tip == "no browser"
    docs_site.note_refresh(finished="2026-09-20T13:03:00+00:00", ok=True, error=None)
    cls, text, _ = docs_site.refresh_note()
    assert cls == "" and text.startswith("generated docs: refreshed")
    assert json.loads((tmp_path / ".refresh.json").read_text())["ok"] is True
    c = TestClient(app)
    assert "generated docs: refreshed" in c.get("/docs/README.md").text
