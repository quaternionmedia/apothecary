"""The documentation served by the viewer's server: /docs and /walkthrough."""

import json

from fastapi.testclient import TestClient

from apothecary import docs_site
from apothecary.api import app


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
            if not path.exists() and "generated/" not in rel and ".placeholder" not in rel:
                missing.append(f"{url} -> {href}")
    assert not missing, "\n".join(missing)


def test_docs_routes_serve_pages_and_files_and_refuse_the_rest(tmp_path, monkeypatch):
    c = TestClient(app)
    assert c.get("/docs", follow_redirects=False).status_code in (302, 307)
    r = c.get("/docs/README.md")
    assert r.status_code == 200 and "Apothecary" in r.text and 'href="/api/docs"' in r.text
    r = c.get("/docs/firmware.md")
    assert 'id="control-behind-a-latch"' in r.text
    r = c.get("/docs/validation/dry-run-square.gcode")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert c.get("/docs/../pyproject.toml").status_code in (404, 422)
    assert c.get("/docs/no-such-page.md").status_code == 404
    assert c.get("/walkthrough/01-a-part.md").status_code == 200
    # The API's own docs moved to make room.
    assert c.get("/api/docs").status_code == 200
    assert c.get("/openapi.json").status_code == 200


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
