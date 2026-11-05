"""Launching the browser the tests run in, and saying in one line when it is missing."""

from typing import Callable, TypeVar

import pytest
from playwright.sync_api import BrowserType
from playwright.sync_api import Error as PlaywrightError

CHROMIUM_MISSING = (
    "the browser tests need Chromium, which Playwright has not installed here: "
    "run `uv run playwright install chromium`"
)

Launched = TypeVar("Launched")


def launched(start: Callable[[], Launched]) -> Launched:
    """What ``start()`` launches; with no browser installed, the run stops on one line
    saying how to install it, rather than on Playwright's box of advice under every
    test."""
    try:
        return start()
    except PlaywrightError as exc:
        if "Executable doesn't exist" in str(exc):
            pytest.exit(CHROMIUM_MISSING, returncode=1)
        raise


def launch(browser_type: BrowserType, **options):
    """``browser_type.launch(**options)``, stopping the run in one line if there is no browser."""
    return launched(lambda: browser_type.launch(**options))
