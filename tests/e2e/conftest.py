"""Playwright fixtures: the servers the browser tests run against, and the doc recorders.

pytest tests/e2e --start-server          # a scripted server for the session
pytest tests/e2e --base-url URL          # a server you started yourself
"""

import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

import apothecary  # noqa: F401  -- the guard, before base_url connects anywhere

# tests/ itself, for helpers shared with the unit tests (firmware_helpers).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from doc_capture import GENERATED_DOCS_ROOT, DocRecorder, Walkthrough  # noqa: E402
from firmware_helpers import write_fake_arduino_cli  # noqa: E402
from ports import refuse_a_held_port  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EXTERNAL_PORT = 8765  # a server you started, when neither --start-server nor --base-url is given


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def start_server(tmp_path_factory):
    """Factory: ``start_server(env_overrides=None, port=None) -> url``.

    Each server runs the scripted arduino-cli (the Uno on /dev/ttyFAKE0, /dev/ttyFAKE1
    unmatched) and the simulated printer mid-print, keeps its firmware state and pictures
    in temp folders of its own, and listens on a free port unless one is named. So no
    test opens a real serial port, reads ``~/.apothecary``, or sees a real board. All of
    them stop when the session ends.
    """
    started: list[subprocess.Popen] = []

    def _start(env_overrides: dict | None = None, port: int | str | None = None) -> str:
        tmp = tmp_path_factory.mktemp("server")
        (tmp / "pictures").mkdir()
        env = os.environ.copy()
        env.update(
            {
                "ARDUINO_CLI": str(write_fake_arduino_cli(tmp / "arduino-cli")),
                "APOTHECARY_TOOLS_DIR": str(tmp / "tools"),
                "APOTHECARY_STATE_DIR": str(tmp / "state"),
                "APOTHECARY_PICTURE_ROOT": str(tmp / "pictures"),
                "APOTHECARY_SERIAL_ENGINE": "simulated",
                "APOTHECARY_SIMULATED_PRINTER": "printing",
                **(env_overrides or {}),
            }
        )
        if port is None:
            port = _free_port()
        else:
            refuse_a_held_port(port)
        url = f"http://127.0.0.1:{port}"
        proc = subprocess.Popen(
            [
                *(sys.executable, "-m", "uvicorn", "apothecary.api:app"),
                *("--host", "127.0.0.1", "--port", str(port)),
                # Let go of idle keep-alive connections quickly on SIGTERM.
                *("--timeout-graceful-shutdown", "1"),
            ],
            cwd=ROOT,
            env=env,
            # DEVNULL: an unread PIPE fills and blocks the server mid-run.
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        started.append(proc)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                pytest.exit(f"the test server for {url} exited at start: is the port held?", 1)
            try:
                if httpx.get(f"{url}/health", timeout=1.0).status_code == 200:
                    return url
            except httpx.TransportError:
                pass
            time.sleep(0.2)
        pytest.exit(f"the test server for {url} did not answer within 20 s", 1)

    yield _start
    for proc in started:
        proc.terminate()
    for proc in started:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


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
def test_server(request, start_server, _picture_folder_if_known):
    """The session's scripted server under --start-server (its url), else None."""
    if not request.config.getoption("--start-server"):
        return None
    return start_server(
        {"APOTHECARY_PICTURE_ROOT": str(_picture_folder_if_known)},
        port=request.config.getoption("--server-port"),
    )


@pytest.fixture(scope="session")
def base_url(request, test_server):
    """Base URL for the test server."""
    # pytest-playwright provides --base-url option automatically
    url = request.config.getoption("--base-url", default=None)
    if not url and test_server:
        return test_server
    if not url:
        url = f"http://127.0.0.1:{request.config.getoption('--server-port') or EXTERNAL_PORT}"
    try:
        response = httpx.get(f"{url}/health", timeout=2.0)
    except (httpx.ConnectError, httpx.TimeoutException):
        # A plain `pytest` is the unit run: the browser tests say why they did not run.
        pytest.skip(f"browser tests need a server: pass --start-server (or serve on {url})")
    if response.status_code != 200:
        pytest.exit(f"Server at {url} returned status {response.status_code}.", returncode=1)
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


# Chromium's fake camera: a synthetic picture with colour bars and a moving
# mark, so there is a camera to allow, see live, capture from and place in the
# world on every machine, and no real camera is ever opened by a test.
FAKE_CAMERA = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"]


@pytest.fixture
def camera_page(browser_type, base_url):
    """A page in a browser of its own, launched with the fake camera and the
    permission to use it already granted."""
    browser = browser_type.launch(args=FAKE_CAMERA)
    context = browser.new_context(viewport={"width": 1280, "height": 800}, base_url=base_url)
    context.grant_permissions(["camera"], origin=base_url)
    page = context.new_page()
    yield page
    context.close()
    browser.close()


@pytest.fixture
def walkthrough(page):
    """The one demonstration's recorder, written out however the run ends.

    Deliberately not gated on --generate-docs, which is what the screenshot
    machinery above still uses. The walkthrough is the page a newcomer meets;
    producing it only when somebody remembers a flag is what made it a second
    description of behaviour rather than a record of a run.
    """
    made: list[Walkthrough] = []

    def _make(ordinal, slug, title, intro, runtime, does_not_show, page=page):
        # `page` may be another browser's -- the one launched with a fake
        # camera, for the page that places one -- and its screenshots are then
        # of that browser.
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
