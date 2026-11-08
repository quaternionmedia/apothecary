"""A procedure step's node and a family member's name, where they lead somewhere other
than a Machine: a camera's node opens its Pictures, a node at another site says which
site it is in and opens nothing, and a member beside the hub opens its own page in a
new tab. The Family view says when nothing has been delivered and when the hub cannot
be asked.

Runs against a server of its own: the simulated Ender idle, a camera added above the
workbench, and a procedure under the garage whose steps name those nodes. The hub's
own members are hosted here or read by a page, so the member beside it is added to
what the page is told; no process is started for it. No serial port is opened and
nothing reaches the network.
"""

from __future__ import annotations

import json
import re

import httpx
import pytest
import rings
import windows
from garage import open_garage, status
from playwright.sync_api import Page, expect

PROCEDURE = ".panel[data-panel='procedure']"
WITHIN = 15_000
ELSEWHERE = "apothecary:ender3"


@pytest.fixture(scope="module")
def bench(start_server):
    """The server's address and the camera's name."""
    url = start_server({"APOTHECARY_SIMULATED_PRINTER": "idle"})
    with httpx.Client(base_url=url, timeout=15.0) as http:
        added = http.post("/sites/garage/cameras", json={"host": "workbench"})
        added.raise_for_status()
        camera = added.json()["camera"]["name"]
        steps = [
            {
                "number": "1",
                "name": "Look at the bench",
                "discipline": "mechanical",
                "node": f"garage:{camera}",
            },
            {
                "number": "2",
                "name": "Fetch the spare Ender",
                "discipline": "mechanical",
                "node": ELSEWHERE,
            },
        ]
        http.put("/sites/garage/procedures/doors", json={"steps": steps}).raise_for_status()
    return url, camera


def _node(page: Page, number: str):
    return page.locator(f'{PROCEDURE} .procedure-step[data-number="{number}"] .procedure-node')


def _family_view(page: Page, url: str):
    open_garage(page, url)
    expect(page.locator(PROCEDURE)).to_be_visible(timeout=WITHIN)
    rings.on_world(page, "Panels", "Windows", "Family view")
    return windows.panel(page, "family-members"), windows.panel(page, "family-deliveries")


@pytest.mark.e2e
def test_a_cameras_node_opens_its_pictures(page: Page, bench):
    """A step's node that is a camera selects it and opens Pictures, not a Machine."""
    url, camera = bench
    open_garage(page, url)
    expect(page.locator(PROCEDURE)).to_be_visible(timeout=WITHIN)
    windows.close(page, "pictures")  # open in this layout: the door must open it
    expect(windows.panel(page, "pictures")).to_have_count(0)
    _node(page, "1").click()
    expect(windows.panel(page, "pictures")).to_be_visible(timeout=WITHIN)
    page.wait_for_function(f"() => window.fractalViewer.selectedName === '{camera}'")
    expect(page.locator(windows.MACHINE_WINDOWS)).to_have_count(0)


@pytest.mark.e2e
def test_a_node_at_another_site_says_where_it_is_and_opens_nothing(page: Page, bench):
    """A step's node at another site: the status line says which site it is in and how to
    get there, as an error, and no window opens."""
    url, _ = bench
    open_garage(page, url)
    expect(page.locator(PROCEDURE)).to_be_visible(timeout=WITHIN)
    windows.close(page, "pictures")
    expect(windows.panel(page, "pictures")).to_have_count(0)
    _node(page, "2").click()
    expect(status(page)).to_have_text(
        f"{ELSEWHERE} is in apothecary, not garage: the banner's ▾ opens apothecary"
    )
    expect(status(page)).to_have_class(re.compile(r"\berror\b"))
    expect(page.locator(windows.MACHINE_WINDOWS)).to_have_count(0)
    expect(windows.panel(page, "pictures")).to_have_count(0)
    assert page.evaluate("() => window.fractalViewer.selectedName") in (None, "")


@pytest.mark.e2e
def test_a_member_beside_the_hub_opens_its_page_in_a_new_tab(page: Page, bench):
    """A member reached beside the hub is a door to its own page, opened in a new tab;
    with nothing fired yet, Deliveries says nothing has been delivered."""
    url, _ = bench
    beside = f"{url}/openapi.json"

    def with_one_beside(route):
        response = route.fetch()
        body = response.json()
        body["members"]["joe"] = {"via": "push", "url": beside}
        route.fulfill(response=response, json=body)

    page.route(re.compile(r".*/family/$"), with_one_beside)
    members, deliveries = _family_view(page, url)
    joe = members.locator("button.family-member[data-member='joe']")
    expect(joe).to_be_visible(timeout=WITHIN)
    expect(joe).to_have_attribute("title", f"beside the hub; opens {beside} in a new tab")
    expect(deliveries.locator(".family-deliveries")).to_have_text("nothing delivered yet")
    with page.context.expect_page() as opened:
        joe.click()
    assert opened.value.url == beside


@pytest.mark.e2e
def test_the_members_window_says_when_the_hub_cannot_be_asked(page: Page, bench):
    """The hub's members asked and refused: Members says so in the hub's words."""
    url, _ = bench
    page.route(
        re.compile(r".*/family/beside$"),
        lambda route: route.fulfill(
            status=503,
            content_type="application/json",
            body=json.dumps({"detail": "the hub is not running"}),
        ),
    )
    members, _ = _family_view(page, url)
    expect(members.locator(".family-members")).to_have_text(
        "Family: the hub is not running", timeout=WITHIN
    )
