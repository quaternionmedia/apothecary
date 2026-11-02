"""The root README, served at /README.md the way /docs serves its pages."""

import re

import pytest
from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.projects.parts.skeleton import ROOT

HREF = re.compile(r'<a href="([^"]+)"')


@pytest.fixture(scope="module")
def page():
    return TestClient(app).get("/README.md")


def _first_heading() -> str:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    return re.search(r"^# (.+)$", text, re.MULTILINE).group(1).strip().strip("`*")


def test_the_readme_page_answers_with_the_readmes_first_heading(page):
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert "<h1" in page.text and _first_heading() in page.text
    assert "<title>" in page.text and 'href="/openapi.json"' in page.text


def test_a_link_the_map_carries_goes_to_a_page_the_app_answers(page):
    client = TestClient(app)
    section = page.text.split('id="what-it-does-and-how-to-see-it"', 1)[1].split("<h2", 1)[0]
    served = [h for h in HREF.findall(section) if h.startswith(("/docs/", "/walkthrough/"))]
    assert served, "the map links no page the app serves"
    for href in served:
        assert client.get(href.split("#", 1)[0]).status_code == 200, href


def test_a_file_the_app_does_not_serve_is_a_plain_link_to_the_repository(page):
    hrefs = HREF.findall(page.text)
    assert any(h.endswith("/blob/main/CONTRIBUTING.md") for h in hrefs)
    assert any(h.endswith("/blob/main/LICENSE") for h in hrefs)
    assert not [h for h in hrefs if h in ("CONTRIBUTING.md", "LICENSE", "examples/README.md")]


def test_no_link_points_at_a_markdown_path_the_app_does_not_serve(page):
    client = TestClient(app)
    for href in HREF.findall(page.text):
        path = href.split("#", 1)[0]
        if re.match(r"^[a-z][a-z0-9+.-]*:", path) or not path:
            continue  # elsewhere: the repository's own page, or another site
        assert path.startswith("/"), f"{href} is relative, to nothing the app serves"
        if path.endswith(".md"):
            assert client.get(path).status_code == 200, href


def test_the_docs_pages_reach_the_readme():
    client = TestClient(app)
    assert 'href="/README.md"' in client.get("/docs/README.md").text
    index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert "../README.md" in index
