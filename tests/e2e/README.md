# End-to-End Tests

This directory contains Playwright-based end-to-end tests for the Apothecary web interface.

## Important: Server Must Be Running

**These tests require the Apothecary server to be running in a separate terminal.**

The tests do NOT automatically start/stop the server. This approach:
- Allows testing against any server instance (local dev, staging, etc.)
- Makes tests faster by reusing the same server
- Gives you control over server logging and debugging

## Setup

1. Install dependencies (including Playwright):
   ```bash
   uv sync
   ```

2. Install Playwright browsers:
   ```bash
   # Using CLI
   apothecary test setup-e2e
   
   # Or directly with playwright
   uv run playwright install chromium
   ```

3. Validate E2E setup:
   ```bash
   apothecary test validate-e2e
   ```

## Running Tests

### Step 1: Start the Server

In one terminal:
```bash
apothecary serve --port 8765
```

Keep this terminal running while you run tests in another terminal.

### Step 2: Run Tests

In a second terminal:

```bash
# Using CLI (recommended)
apothecary test run-e2e

# With browser visible
apothecary test run-e2e --headed

# Slow motion for debugging
apothecary test run-e2e --headed --slowmo 1000

# Test against different URL
apothecary test run-e2e --base-url http://localhost:8000

# Or use pytest directly
uv run pytest tests/e2e/ -v --base-url http://127.0.0.1:8765
```

### Test Server Connection

The tests will check that the server is accessible before running. If the server isn't running, you'll see:

```
Could not connect to server at http://127.0.0.1:8765.
Please start the server with: apothecary serve --port 8765
```

## Test Structure

- `conftest.py` - Pytest fixtures and configuration
  - `base_url` - Base URL for test server (validates connection)
  - Uses pytest-playwright's built-in `page` fixture
  - `doc_recorder` / `--generate-docs` - see "Doc-workflow tests" below

- `test_api.py` - Tests for API endpoints
  - Parts listing and retrieval
  - SCAD/JSCAD downloads
  - Scene rendering

- `test_viewer.py` - Tests for the fractal zoom viewer interface
  - Page loading and structure
  - Zoom navigation and the minimap
  - The absorbed parts-library part view

- `test_docs_fractal_viewer.py` - doc-workflow test (marked both `e2e` and
  `docs`) — see below

## Doc-workflow tests

`test_docs_*.py` are ordinary E2E tests (they run, and must pass, as part
of any normal `apothecary test all` / CI run) that *also* narrate
themselves: each step calls `doc_recorder(...).step("description")`. That
call is a no-op unless pytest runs with `--generate-docs`, in which case it
takes a screenshot and appends the description to a manifest under
`docs/generated/<workflow>/`.

You won't normally invoke `--generate-docs` by hand — `apothecary docs
generate` (see `docs/README.md`) starts a server, runs just the tests
marked `docs` with the flag on, then assembles a GIF and renders Markdown
from each workflow's manifest. To add a new doc-workflow step, edit the
test: add a `docs.step(...)` call at the point you want a screenshot, and
re-run `apothecary docs generate` — no separate doc file to keep in sync.

## Writing New Tests

```python
import pytest
from playwright.sync_api import Page, expect

@pytest.mark.e2e
def test_my_feature(page: Page, base_url: str):
    """Test description."""
    page.goto(f"{base_url}/my-page")
    
    # Use expect for assertions
    expect(page.locator("h1")).to_have_text("Expected Text")
    
    # Interact with elements
    page.locator("#button").click()
```

## Configuration

- Default test server: `http://127.0.0.1:8765`
- Override with: `--base-url http://your-server:port`
- Playwright config in `pyproject.toml`

## Debugging

Run tests with visible browser:
```bash
apothecary test run-e2e --headed --slowmo 500
```

Or use pytest directly for more options:
```bash
# Generate trace for debugging
uv run pytest tests/e2e/ --tracing on --base-url http://127.0.0.1:8765

# View traces
uv run playwright show-trace test-results/.../trace.zip
```
