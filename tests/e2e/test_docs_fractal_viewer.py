"""Doc-workflow E2E test for the fractal zoom viewer.

Same on-demand pattern as the rest of tests/e2e: a plain test run takes no
screenshots; `apothecary docs generate` runs this with `--generate-docs` and
turns the manifest into docs/generated/fractal-viewer/fractal-viewer.md.

Resets the garage site's layout and job queue first so the workflow (and its
screenshots) don't depend on whatever a previous test left behind in the
process-lifetime SiteStore/JobStore (see apothecary/site_store.py).
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
@pytest.mark.docs
def test_fractal_viewer_workflow(page: Page, base_url: str, doc_recorder):
    """Zoom from the garage's Structures down to a Feature, then switch to
    the parts library and zoom to a part -- the absorbed part view -- and
    run a job through the queue at the root.
    """
    page.request.post(f"{base_url}/sites/garage/reset")

    docs = doc_recorder(
        "fractal-viewer",
        title="Fractal Zoom Viewer (prototype, unratified)",
        intro=(
            "The fractal zoom viewer (`/viewer/sites/{name}`) navigates any "
            "registered site's Assembly tree -- Site/Structure/Substructure/"
            "Feature, to unbounded depth -- with the same click/double-click/"
            "scroll controls at every level. It absorbs both the former "
            "Site/Structure hierarchy viewer and the former standalone parts "
            "browser: the registered parts library is reached by zooming "
            "down to a leaf, not a separate page."
        ),
    )

    page.goto(f"{base_url}/viewer/sites/garage")
    expect(page.locator(".toolbar h1")).to_contain_text("Apothecary")
    page.wait_for_timeout(600)
    docs.step("Open the garage site at its root -- four Structures")

    page.locator("#contents-list .contents-item", has_text="printer_1").dblclick()
    page.wait_for_timeout(300)
    docs.step("Double-click printer_1 to zoom in -- its Substructures appear")

    page.locator("#contents-list .contents-item", has_text="gantry_system").dblclick()
    page.wait_for_timeout(300)
    docs.step("Zoom into gantry_system -- a Substructure nested inside a Substructure")

    expect(page.locator("#minimap .minimap-tick.filled")).to_have_count(3)
    docs.step("The abstract minimap shows the current depth")

    page.locator("#zoom-out-btn").click()
    page.wait_for_timeout(300)
    page.locator("#zoom-out-btn").click()
    page.wait_for_timeout(300)
    expect(page.locator("#contents-list")).to_contain_text("workbench")
    docs.step("Zoom back out to the root -- same control at every level")

    printer_1 = page.locator("#contents-list .contents-item", has_text="printer_1")
    printer_1.click()
    x_input = page.locator("#pos-x")
    expect(x_input).to_be_visible()
    x_input.fill("650")
    x_input.press("Tab")
    expect(page.locator("#validity-indicator")).to_contain_text("violation")
    docs.step("Select printer_1 at the root and move it to overlap printer_2 -- caught")

    x_input.fill("100")
    x_input.press("Tab")
    expect(page.locator("#validity-indicator")).to_contain_text("valid")
    docs.step("Move it back -- the layout is valid again")

    page.locator("#job-name").fill("small_bracket")
    page.locator("#job-x").fill("50")
    page.locator("#job-y").fill("50")
    page.locator("#job-z").fill("20")
    page.locator("#job-form button[type=submit]").click()
    page.wait_for_timeout(400)
    docs.step("Queue a print job -- the Jobs panel is site-wide, not tied to zoom depth")

    page.locator(".job-assign-btn").first.click()
    page.wait_for_timeout(500)
    docs.step("Assign it to a compatible, idle printer")

    page.goto(f"{base_url}/viewer/sites/parts_library")
    page.wait_for_timeout(600)
    docs.step("Switch to the parts_library site")

    page.locator("#contents-list .contents-item").first.click()
    page.wait_for_timeout(800)
    expect(page.locator("#part-scad-content")).to_be_visible()
    docs.step("Select a part leaf -- its real SCAD source is the absorbed part view")
