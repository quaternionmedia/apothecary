"""Doc-workflow E2E test for the Site/Structure/Substructure/Feature viewer.

Same on-demand pattern as test_docs_parts_viewer.py: a plain test run takes
no screenshots; `apothecary docs generate` runs this with `--generate-docs`
and turns the manifest into docs/generated/site-viewer/site-viewer.md.

Resets the garage site's layout and job queue first so the workflow (and
its screenshots) don't depend on whatever a previous test left behind in
the process-lifetime SiteStore/JobStore (see apothecary/site_store.py).
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
@pytest.mark.docs
def test_site_viewer_workflow(page: Page, base_url: str, doc_recorder):
    """Inspect a printer, trigger and fix a layout violation, run a job through the queue."""
    page.request.post(f"{base_url}/sites/garage/reset")

    docs = doc_recorder(
        "site-viewer",
        title="Site / Structure Viewer (prototype, unratified)",
        intro=(
            "The Site/Structure/Substructure/Feature viewer (`/viewer/sites/{name}`) is "
            "an unratified prototype for laying out and manufacturing-planning a "
            "physical site. This worked example is a garage workbench with a fleet of "
            "3D printers on it -- each Structure renders as a box derived from its "
            "footprint, draggable, with every move re-validated by the server."
        ),
    )

    page.goto(f"{base_url}/viewer/sites/garage")
    expect(page.locator(".toolbar h1")).to_contain_text("Apothecary")
    page.wait_for_timeout(600)
    docs.step("Open the garage site")

    page.locator(".tree-structure-label", has_text="printer_1").click()
    page.wait_for_timeout(300)
    docs.step("Select printer_1 to inspect its position, material, and build volume")

    x_input = page.locator("#pos-x")
    expect(x_input).to_be_visible()
    x_input.fill("650")
    x_input.press("Tab")
    expect(page.locator("#validity-indicator")).to_contain_text("violation")
    docs.step("Move it to overlap printer_2 -- the layout gate catches it")

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
    docs.step("Queue a print job")

    page.locator(".job-assign-btn").first.click()
    page.wait_for_timeout(500)
    docs.step("Assign it to a compatible, idle printer")

    page.locator(".job-complete-btn").first.click()
    page.wait_for_timeout(400)
    docs.step("Mark the job done -- the printer frees back up")
