"""What the step-through tests share (tests/e2e/test_steps_*.py): a loop as named steps, each
first checking that the page is where the step before it leaves it.

In the suite a step-through test runs every step, in order, on a server of its own in its
own browser. Given ``--step N`` and ``--base-url`` naming the demo (``apothecary serve
--demo``), it runs only step N, on the demo, in the visible Chromium answering DevTools at
127.0.0.1:9222 (started with ``--remote-debugging-port=9222``), in its tab named
``apothecary-walk``, opened if there is none. The tab is left where the step leaves it, to
be looked at, its picture in ``.cache/walk/<loop>-step-N.png``; a step whose page is not
where the step before leaves it does nothing and says why. A breakpoint in a step, under a
debugger, stops there with the page live.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Callable, Iterator, List, Sequence, Tuple

import pytest
from playwright.sync_api import Page

ROOT = Path(__file__).resolve().parents[2]
DEVTOOLS = os.environ.get("APOTHECARY_WALK_DEVTOOLS", "http://127.0.0.1:9222")
WALK_TAB = "apothecary-walk"
PICTURES = ROOT / ".cache" / "walk"

Steps = Sequence[Tuple[str, Callable]]


def where(step: str, leaves: str, holds: bool) -> None:
    """Stop, having done nothing, unless the page is where the step before leaves it."""
    if not holds:
        pytest.fail(f"{step}: not where the step before leaves it ({leaves}), so nothing done")


def picture(page: Page, name: str) -> Path:
    """The window as it is, by Chrome's own capture: Playwright's screenshot can wait
    forever on a browser it reached over DevTools."""
    PICTURES.mkdir(parents=True, exist_ok=True)
    session = page.context.new_cdp_session(page)
    try:
        data = session.send("Page.captureScreenshot", {"format": "png"})["data"]
        shot = PICTURES / f"{name}.png"
        shot.write_bytes(base64.b64decode(data))
        return shot
    finally:
        session.detach()


def walk_tab(request, base_url: str) -> Page:
    """The demo's walk tab in the visible Chromium, opened on the garage if there is none,
    brought to the front."""
    browser = request.getfixturevalue("playwright").chromium.connect_over_cdp(DEVTOOLS)
    context = browser.contexts[0]
    page = next((pg for pg in context.pages if pg.evaluate("() => window.name") == WALK_TAB), None)
    if page is None:
        page = context.new_page()
        page.goto(f"{base_url}/viewer/sites/garage")
        page.evaluate(f"() => {{ window.name = '{WALK_TAB}'; }}")
    page.bring_to_front()
    return page


def chosen(
    request, base_url: str, loop: str, steps: Steps, own: Callable[[], Tuple[Page, str]]
) -> Iterator[Tuple[Page, str, bool, List[int]]]:
    """For a step-through test's fixture: the page, its server, whether it is the demo's
    tab, and the steps to run there -- one on the demo under --step, every one on the
    test's own (``own``) otherwise. Under --step, the step's words and picture after it."""
    n = request.config.getoption("--step")
    if n is None:
        page, url = own()
        yield page, url, False, list(range(1, len(steps) + 1))
        return
    if not 1 <= n <= len(steps):
        pytest.fail(f"--step {n}: this test has steps 1 to {len(steps)}")
    page = walk_tab(request, base_url)
    yield page, base_url, True, [n]
    said = page.locator("#status").inner_text()
    print(f"\nstep {n} ({steps[n - 1][0]}): {said}\npicture: {picture(page, f'{loop}-step-{n}')}")
