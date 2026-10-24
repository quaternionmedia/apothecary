"""What the step-through tests share (tests/e2e/test_steps_*.py): a loop as named steps, each
first checking that the page is where the step before it leaves it.

Under ``--steps`` a step-through test runs every step, in order, on a server of its own in
its own browser; with neither flag it skips, since each walks a loop another browser test
holds end to end, and the weekly steps workflow (.github/workflows/steps.yml) passes
``--steps``. Given ``--step N`` and ``--base-url`` naming the demo (``apothecary serve
--demo``), it runs only step N, on the demo, in the visible Chromium answering DevTools at
127.0.0.1:9222 (started with ``--remote-debugging-port=9222``), in its tab named
``apothecary-walk``, opened if there is none. The tab is left where the step leaves it, to
be looked at, its picture in ``.cache/walk/<loop>-step-N.png``; a step whose page is not
where the step before leaves it does nothing and says why. A breakpoint in a step, under a
debugger, stops there with the page live.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Sequence, Tuple

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


# The walk tab's window by Chrome's own capture, in a process of its own: a window that is
# covered or minimised paints nothing, and the capture then waits for ever.
CAPTURE = """
import base64, sys
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    pages = p.chromium.connect_over_cdp(sys.argv[1]).contexts[0].pages
    page = next(pg for pg in pages if pg.evaluate("() => window.name") == sys.argv[2])
    data = page.context.new_cdp_session(page).send("Page.captureScreenshot", {"format": "png"})["data"]
    open(sys.argv[3], "wb").write(base64.b64decode(data))
"""


def picture(name: str, wait: float = 15.0) -> Optional[Path]:
    """The walk tab's window as it is, or None when Chrome gives none within ``wait``
    seconds."""
    PICTURES.mkdir(parents=True, exist_ok=True)
    shot = PICTURES / f"{name}.png"
    try:
        subprocess.run(
            [sys.executable, "-c", CAPTURE, DEVTOOLS, WALK_TAB, str(shot)],
            timeout=wait,
            check=True,
            capture_output=True,
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return None
    return shot


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
    shot = picture(f"{loop}-step-{n}")
    taken = shot or "none: Chrome gave none (is the window covered or minimised?)"
    print(f"\nstep {n} ({steps[n - 1][0]}): {said}\npicture: {taken}")
