"""
Playwright test configuration and fixtures.

The server can either be:
1. Started automatically by pytest (--start-server flag)
2. Running separately before tests (default behavior)

Usage:
    # Auto-start server:
    pytest tests/e2e/ --start-server

    # With external server:
    apothecary serve --port 8765
    pytest tests/e2e/
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


def pytest_addoption(parser):
    """Add custom pytest options for E2E tests."""
    parser.addoption(
        "--start-server",
        action="store_true",
        default=False,
        help="Automatically start the test server before E2E tests",
    )
    parser.addoption(
        "--server-port",
        action="store",
        default="8765",
        help="Port for the test server (default: 8765)",
    )


@pytest.fixture(scope="session")
def server_port(request):
    """Get the server port from command line or default."""
    return request.config.getoption("--server-port")


@pytest.fixture(scope="session")
def test_server(request, server_port):
    """Start a test server if --start-server is passed.

    This fixture manages the server lifecycle for the entire test session.
    """
    should_start = request.config.getoption("--start-server")

    if not should_start:
        yield None
        return

    # Get project root
    root = Path(__file__).resolve().parents[2]

    # Set environment for faster startup
    env = os.environ.copy()
    env["APOTHECARY_VIEWER_PATH"] = ""

    server_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "apothecary.api:app",
        "--host",
        "127.0.0.1",
        "--port",
        server_port,
    ]

    server_proc = subprocess.Popen(
        server_cmd,
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    base_url = f"http://127.0.0.1:{server_port}"

    # Wait for server to be ready
    for _attempt in range(30):
        try:
            response = httpx.get(f"{base_url}/health", timeout=1.0)
            if response.status_code == 200:
                break
        except (httpx.ConnectError, httpx.TimeoutException):
            time.sleep(0.5)
    else:
        server_proc.terminate()
        pytest.exit("Server failed to start within 15 seconds", returncode=1)

    yield server_proc

    # Cleanup
    server_proc.terminate()
    try:
        server_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server_proc.kill()


@pytest.fixture(scope="session")
def base_url(request, test_server, server_port):
    """Base URL for the test server."""
    # pytest-playwright provides --base-url option automatically
    url = request.config.getoption("--base-url", default=None)
    if not url:
        url = f"http://127.0.0.1:{server_port}"

    # Check if server is accessible
    try:
        response = httpx.get(f"{url}/health", timeout=2.0)
        if response.status_code != 200:
            pytest.exit(
                f"Server at {url} returned status {response.status_code}. "
                f"Please start the server with: apothecary serve --port {url.split(':')[-1]}",
                returncode=1,
            )
    except (httpx.ConnectError, httpx.TimeoutException):
        pytest.exit(
            f"Could not connect to server at {url}. "
            f"Please start the server with: apothecary serve --port {url.split(':')[-1]}\n"
            f"Or run with --start-server to auto-start the server.",
            returncode=1,
        )

    return url
