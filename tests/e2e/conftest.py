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
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

# tests/ itself, for helpers shared with the unit tests (firmware_helpers).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from doc_capture import GENERATED_DOCS_ROOT, DocRecorder, Walkthrough  # noqa: E402


@pytest.fixture(scope="session")
def server_port(request):
    """Get the server port from command line or default."""
    return request.config.getoption("--server-port")


@pytest.fixture(scope="session")
def _picture_folder_if_known(request, tmp_path_factory):
    """The picture folder, or None if nobody has said which one it is.

    Kept separate from `picture_folder` on purpose. Starting the server must not
    depend on a fixture that can skip: `test_server` is upstream of `base_url`,
    which is upstream of every browser test, so a skip here would silently take
    the whole browser suite with it — which is exactly what it did once.
    """
    already = os.environ.get("APOTHECARY_PICTURE_ROOT")
    if already:
        folder = Path(already)
        folder.mkdir(parents=True, exist_ok=True)
        return folder
    if request.config.getoption("--start-server"):
        return tmp_path_factory.mktemp("pictures")
    return None


@pytest.fixture(scope="session")
def picture_folder(_picture_folder_if_known):
    """The one folder the test server may read pictures from.

    The server refuses any path outside a single folder, so a test that wants it
    to look at a picture has to say where that folder is. Naming it here rather
    than letting the server read anything is the point: the refusal is real, and
    the first run of these tests hit it.

    When something else started the server — `apothecary docs generate` does —
    it has already chosen the folder and said so, and both sides have to agree.

    Only tests that ask for this fixture are skipped when nobody said. Tests that
    never show the server a picture run either way.
    """
    if _picture_folder_if_known is None:
        pytest.skip(
            "This test asks the server to look at a picture, and the server reads "
            "pictures from one folder only. Nothing said which folder. Either run "
            "with --start-server, or start the server yourself with "
            "APOTHECARY_PICTURE_ROOT set to a folder and set the same value here."
        )
    return _picture_folder_if_known


@pytest.fixture(scope="session")
def test_server(request, server_port, _picture_folder_if_known):
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
    if _picture_folder_if_known is not None:
        env["APOTHECARY_PICTURE_ROOT"] = str(_picture_folder_if_known)

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

    # DEVNULL, not PIPE: nothing here ever reads server_proc.stdout/stderr,
    # and an unread PIPE deadlocks once its OS buffer fills (confirmed by
    # direct reproduction against this same server-launch pattern in
    # apothecary/cli/testing.py -- see the comment there).
    server_proc = subprocess.Popen(
        server_cmd,
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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


@pytest.fixture(scope="session")
def docs_enabled(request) -> bool:
    return request.config.getoption("--generate-docs")


@pytest.fixture
def browser_context_args(browser_context_args, docs_enabled, request):
    """Record video for doc-workflow tests only, one subdirectory per test.

    Overrides pytest-playwright's own fixture of the same name -- a
    documented extension point. Playwright only assigns the actual .webm
    its final filename once the context closes, well after this test's own
    body (and doc_recorder's finalizer, below) has already run -- so rather
    than guess which file belongs to which workflow afterward, each test
    gets its own directory (named for the test itself, which pytest
    guarantees is unique within a run) with exactly one video in it.
    `apothecary docs generate` matches that video back to a workflow via
    the marker file doc_recorder's finalizer writes alongside it.
    """
    if not docs_enabled:
        return browser_context_args
    video_dir = GENERATED_DOCS_ROOT / "_videos_raw" / _slugify_test_name(request.node.name)
    video_dir.mkdir(parents=True, exist_ok=True)
    return {
        **browser_context_args,
        "record_video_dir": str(video_dir),
        "record_video_size": {"width": 1280, "height": 800},
    }


def _slugify_test_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-")


@pytest.fixture
def doc_recorder(page, docs_enabled, request):
    """Factory: doc_recorder(workflow, title, intro) -> DocRecorder.

    Every DocRecorder created through this fixture is finalized (manifest
    written) automatically at teardown. Also drops a marker file naming
    every workflow this test recorded into that test's own video directory
    (see browser_context_args) -- the video itself isn't written until the
    context closes, after this fixture's teardown runs, so the marker is
    how `apothecary docs generate` later finds which workflow(s) a given
    .webm belongs to.
    """
    recorders = []

    def _make(workflow: str, title: str, intro: str) -> DocRecorder:
        recorder = DocRecorder(
            page=page, workflow=workflow, title=title, intro=intro, enabled=docs_enabled
        )
        recorders.append(recorder)
        return recorder

    yield _make

    for recorder in recorders:
        recorder.finalize()

    if docs_enabled and recorders:
        video_dir = GENERATED_DOCS_ROOT / "_videos_raw" / _slugify_test_name(request.node.name)
        video_dir.mkdir(parents=True, exist_ok=True)
        marker = video_dir / "workflows.txt"
        marker.write_text("\n".join(r.workflow for r in recorders) + "\n", encoding="utf-8")


@pytest.fixture
def walkthrough(page):
    """The one demonstration's recorder, written out however the run ends.

    Deliberately not gated on --generate-docs, which is what the screenshot
    machinery above still uses. The walkthrough is the page a newcomer meets;
    producing it only when somebody remembers a flag is what made it a second
    description of behaviour rather than a record of a run.
    """
    made: list[Walkthrough] = []

    def _make(ordinal, slug, title, intro, runtime, does_not_show):
        recorder = Walkthrough(
            page=page,
            ordinal=ordinal,
            slug=slug,
            title=title,
            intro=intro,
            runtime=runtime,
            does_not_show=does_not_show,
        )
        made.append(recorder)
        return recorder

    yield _make

    for recorder in made:
        recorder.write()
