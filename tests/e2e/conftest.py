"""
Playwright test configuration and fixtures.

Note: These tests assume the Apothecary server is running separately.
Start the server before running tests:
    apothecary serve --port 8765
"""
import pytest
from playwright.sync_api import Page
import httpx


@pytest.fixture(scope="session")
def base_url(request):
    """Base URL for the test server."""
    # pytest-playwright provides --base-url option automatically
    url = request.config.getoption("--base-url", default=None)
    if not url:
        url = "http://127.0.0.1:8765"
    
    # Check if server is accessible
    try:
        response = httpx.get(f"{url}/health", timeout=2.0)
        if response.status_code != 200:
            pytest.exit(
                f"Server at {url} returned status {response.status_code}. "
                f"Please start the server with: apothecary serve --port {url.split(':')[-1]}",
                returncode=1
            )
    except (httpx.ConnectError, httpx.TimeoutException):
        pytest.exit(
            f"Could not connect to server at {url}. "
            f"Please start the server with: apothecary serve --port {url.split(':')[-1]}",
            returncode=1
        )
    
    return url
