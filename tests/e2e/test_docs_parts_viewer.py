"""Doc-workflow E2E test for the parts viewer.

A normal `apothecary test all` / CI run exercises this test like any other
(`@pytest.mark.e2e`) but takes no screenshots -- the `doc_recorder` fixture
is a no-op unless run with `--generate-docs`. `apothecary docs generate`
(apothecary/cli/docs.py) is what runs it with that flag on and turns the
resulting manifest into docs/generated/parts-viewer/parts-viewer.md.
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
@pytest.mark.docs
def test_parts_viewer_workflow(page: Page, base_url: str, doc_recorder):
    """Load the parts viewer, pick a part, and inspect its generated OpenSCAD source."""
    docs = doc_recorder(
        "parts-viewer",
        title="Parts Viewer",
        intro=(
            "Apothecary's parts viewer (`/viewer`) browses the curated parts library, "
            "previews each part's geometry in the browser via Three.js, and shows the "
            "generated OpenSCAD source alongside it."
        ),
    )

    page.goto(f"{base_url}/viewer")
    expect(page.locator(".toolbar h1")).to_contain_text("Apothecary")
    docs.step("Open the parts viewer")

    select = page.locator("#part-select")
    select.select_option(index=1)  # first real part; index 0 is the placeholder
    chosen_name = select.evaluate("el => el.options[el.selectedIndex].text")
    docs.step(f"Select the '{chosen_name}' part")

    page.locator("#load-btn").click()
    page.wait_for_timeout(800)
    docs.step("Load its preview and OpenSCAD source")

    code_content = page.locator("#code-content")
    expect(code_content).not_to_have_text("Select a part to view its source code")
    docs.step("Inspect the generated OpenSCAD source")
