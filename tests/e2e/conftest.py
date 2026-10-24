"""Playwright fixtures: the servers the browser tests run against, and the doc recorders.

pytest tests/e2e --start-server          # a scripted server for the session
pytest tests/e2e --base-url URL          # a server you started yourself
"""

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Error as PlaywrightError

# tests/ itself, for helpers shared with the unit tests (firmware_helpers, views_helpers).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import garage  # noqa: E402
from browsers import launch, launched  # noqa: E402
from doc_capture import GENERATED_DOCS_ROOT, DocRecorder, Walkthrough  # noqa: E402
from firmware_helpers import write_fake_arduino_cli  # noqa: E402
from parts_built import described  # noqa: E402
from ports import refuse_a_held_port  # noqa: E402
from shards import shard_of  # noqa: E402
from views_helpers import HIGH, SHAPES, WIDE  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

# The app under uvicorn, with the simulated boards answering at once, as the unit
# suite's do (tests/conftest.py): a real board's silences -- 1.5 s after every link
# opens, 0.6 s after a reset -- would otherwise cost each browser test that opens one.
# Its builds go to a folder of its own (argv[2]): a scripted build is not the
# checkout's, and a real flash record must never be compared with one.
SERVE = """
import sys, uvicorn
from pathlib import Path
from apothecary.firmware import bindings, service
from apothecary.firmware.gcode import GcodeLink
GcodeLink.time_scale = 0.02
service.BUILD_ROOT = bindings.BUILD_ROOT = Path(sys.argv[2])
uvicorn.run("apothecary.api:app", host="127.0.0.1", port=int(sys.argv[1]),
            timeout_graceful_shutdown=1)  # let go of idle keep-alive connections quickly
"""


DURATIONS = Path(__file__).with_name("durations.json")


def _keep_this_shard(config, items) -> None:
    spec = config.getoption("--shard")
    if not spec:
        return
    k, n = (int(part) for part in spec.split("/"))
    if not 1 <= k <= n:
        raise pytest.UsageError(f"--shard {spec}: K must be between 1 and N")
    known = json.loads(DURATIONS.read_text()) if DURATIONS.exists() else {}
    average = sum(known.values()) / len(known) if known else 1.0
    files: dict = {}
    for item in items:
        path = item.nodeid.split("::", 1)[0]
        files[path] = files.get(path, 0.0) + known.get(item.nodeid, average)
    placed = shard_of(files, n)
    keep = [item for item in items if placed[item.nodeid.split("::", 1)[0]] == k - 1]
    config.hook.pytest_deselected(items=[item for item in items if item not in keep])
    items[:] = keep


# Each browser test's time this run, for --record-durations: its setup, call and
# teardown. Under xdist the reports come back to the controller, which writes the file.
_timed: dict = {}


def pytest_runtest_logreport(report):
    if report.nodeid.startswith("tests/e2e/"):
        _timed[report.nodeid] = _timed.get(report.nodeid, 0.0) + report.duration


def pytest_sessionfinish(session):
    config = session.config
    if not config.getoption("--record-durations") or hasattr(config, "workerinput"):
        return
    if not _timed:
        return
    ran = {nodeid.split("::", 1)[0] for nodeid in _timed}
    known = json.loads(DURATIONS.read_text()) if DURATIONS.exists() else {}
    kept = {k: v for k, v in known.items() if k.split("::", 1)[0] not in ran}
    kept.update({k: round(v, 2) for k, v in _timed.items()})
    DURATIONS.write_text(json.dumps(dict(sorted(kept.items())), indent=1) + "\n")


def pytest_collection_modifyitems(config, items):
    """Keep this shard's files; tests marked docs run only with --generate-docs."""
    _keep_this_shard(config, items)
    if config.getoption("--generate-docs"):
        return
    skip = pytest.mark.skip(reason="doc capture: runs with --generate-docs (`apothecary docs`)")
    for item in items:
        if item.get_closest_marker("docs"):
            item.add_marker(skip)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def every_stl_built(tmp_path_factory):
    """Call it: every part's STL built, once a session, by the OpenSCAD the servers run
    (tests/e2e/parts_built.py), before the first server starts or the first picture is
    taken; what it found -- that OpenSCAD's version and ``path``, and what a page records
    of it, ``said``. Nothing is built until it is called, so a run with no server to
    drive builds nothing."""
    said: list[dict] = []

    def _built() -> dict:
        if not said:
            env = {**os.environ, "APOTHECARY_TOOLS_DIR": str(tmp_path_factory.mktemp("tools"))}
            done = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("parts_built.py"))],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
            )
            if done.returncode != 0:
                pytest.exit(f"building every part's STL failed:\n{done.stderr[-3000:]}", 1)
            found = json.loads(done.stdout.strip().splitlines()[-1])
            said.append({**found, "said": described(found)})
        return said[0]

    return _built


@pytest.fixture(scope="session")
def start_server(tmp_path_factory, every_stl_built):
    """Factory: ``start_server(env_overrides=None, port=None) -> url``.

    Each server runs the scripted arduino-cli (the Uno on /dev/ttyFAKE0, /dev/ttyFAKE1
    unmatched) and the simulated printer mid-print, keeps its firmware state, pictures
    and render cache in temp folders of its own, and listens on a free port unless one
    is named. So no
    test opens a real serial port, reads ``~/.apothecary``, or sees a real board. All of
    them stop when the session ends.
    """
    started: list[subprocess.Popen] = []

    def _start(env_overrides: dict | None = None, port: int | str | None = None) -> str:
        tmp = tmp_path_factory.mktemp("server")
        (tmp / "pictures").mkdir()
        # A variant saved from the page is a ref in git (projects/parts/saved.py):
        # each server saves into a clone of this checkout of its own, sharing its
        # objects and never writing its refs (tests/conftest.py checks the refs).
        variants = tmp / "variants.git"
        cloned = subprocess.run(
            ["git", "clone", "-q", "--bare", "--shared", str(ROOT), str(variants)],
            capture_output=True,
        )
        if cloned.returncode != 0:
            # A checkout git will not clone (a shallow one, say): an empty repository,
            # whose first save has no parent.
            subprocess.run(["git", "init", "-q", "--bare", str(variants)], check=True)
        # Its own identity, so a save is made whoever runs the suite (CI has none),
        # and nothing of the person's configuration signs or hooks it.
        for key, value in (
            ("user.name", "Apothecary browser test"),
            ("user.email", "browser-test@apothecary.invalid"),
            ("commit.gpgsign", "false"),
        ):
            subprocess.run(["git", "config", key, value], cwd=variants, check=True)
        env = os.environ.copy()
        env.update(
            {
                "ARDUINO_CLI": str(write_fake_arduino_cli(tmp / "arduino-cli")),
                "ESPTOOL": "none",
                # No slicer of the person's own: the page's Slice step brings a fake.
                "APOTHECARY_ORCASLICER": "none",
                # Rust's tools: none, unless a test names the scripted ones (the
                # firmware loop); never a person's own on PATH.
                "CARGO": "none",
                "ESPFLASH": "none",
                "APOTHECARY_TOOLS_DIR": str(tmp / "tools"),
                "APOTHECARY_STATE_DIR": str(tmp / "state"),
                # Node renders and part variants in a cache of the server's own,
                # never the checkout's, and none left from an earlier run.
                "APOTHECARY_CACHE_DIR": str(tmp / "cache"),
                "APOTHECARY_PICTURE_ROOT": str(tmp / "pictures"),
                "APOTHECARY_SERIAL_ENGINE": "simulated",
                "APOTHECARY_SIMULATED_PRINTER": "printing",
                "APOTHECARY_VARIANTS_REPO": str(variants),
                **(env_overrides or {}),
            }
        )
        if port is None:
            port = _free_port()
        elif os.environ.get("PYTEST_XDIST_WORKER"):
            # Under -n every worker starts its own server: one named port cannot hold them all.
            pytest.exit(
                "--server-port names one port; with -n, leave it out so each worker takes a free one",
                1,
            )
        else:
            refuse_a_held_port(port)
        url = f"http://127.0.0.1:{port}"
        every_stl_built()  # none to build in the background while pictures are taken
        proc = subprocess.Popen(
            [sys.executable, "-c", SERVE, str(port), str(tmp / "builds")],
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
    """The picture folder, or None if nobody said which one.

    Separate from `picture_folder` because the server must not depend on a fixture
    that can skip: every browser test is downstream of it.
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
    """The one folder the test server reads pictures from; skips if nobody said which."""
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
        # A plain `pytest` is the unit run. A server that happens to be listening is
        # never taken: the browser tests reset sites, add and remove cameras and
        # forget pictures, and a person's own server holds their state and their
        # pinned boards. Only a scripted server, or one named on purpose, is used.
        pytest.skip(
            "browser tests need a server of their own: pass --start-server, "
            "or --base-url URL for a server you started for them"
        )
    try:
        response = httpx.get(f"{url}/health", timeout=2.0)
    except (httpx.ConnectError, httpx.TimeoutException):
        pytest.exit(f"--base-url {url} does not answer /health", returncode=1)
    if response.status_code != 200:
        pytest.exit(f"Server at {url} returned status {response.status_code}.", returncode=1)
    return url


@pytest.fixture(scope="session")
def docs_enabled(request) -> bool:
    return request.config.getoption("--generate-docs")


@pytest.fixture
def browser_context_args(browser_context_args, docs_enabled, request):
    """With --generate-docs, record each test's video into a directory named for the test."""
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
def doc_recorder(page, docs_enabled, request, every_stl_built):
    """Factory: doc_recorder(workflow, title, intro) -> DocRecorder.

    Every DocRecorder created through this fixture is finalized (manifest
    written) at teardown. With --generate-docs it also writes a marker naming
    the test's workflows into its video directory: the video is only written
    when the context closes, after this teardown, and `apothecary docs generate`
    matches each .webm to its workflows by that marker.
    """
    recorders = []

    def _make(workflow: str, title: str, intro: str) -> DocRecorder:
        recorder = DocRecorder(
            page=page,
            workflow=workflow,
            title=title,
            intro=intro,
            enabled=docs_enabled,
            stls=every_stl_built()["said"] if docs_enabled else None,
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


@pytest.fixture(scope="session")
def launch_browser(launch_browser):
    """pytest-playwright's, which `browser` and so `page` launch through, saying in one
    line when Chromium is not installed."""
    return lambda **options: launched(lambda: launch_browser(**options))


@pytest.fixture(scope="session")
def _camera_browser(browser_type):
    browser = launch(browser_type, args=FAKE_CAMERA)
    yield browser
    browser.close()


@pytest.fixture
def camera_page(_camera_browser, base_url):
    """A page in the fake-camera browser, in a context of its own with the camera allowed."""
    context = _camera_browser.new_context(
        viewport={"width": 1280, "height": 800}, base_url=base_url
    )
    context.grant_permissions(["camera"], origin=base_url)
    yield context.new_page()
    context.close()


# The first time: full Chromium (the `chromium` channel, which `playwright
# install chromium` puts beside the headless shell the other fixtures run) in its
# new headless mode, with the fake camera and no fake UI. The browser's own
# permission prompt stands, and headless there is nobody at it, so a page is
# refused until its context is granted the camera -- the person's yes, given as
# the address bar would give it. The headless shell has no prompt to stand.
UNASKED_CAMERA = ["--use-fake-device-for-media-stream"]


@pytest.fixture(scope="session")
def _unasked_browser(browser_type):
    try:
        browser = browser_type.launch(channel="chromium", args=UNASKED_CAMERA)
    except PlaywrightError as exc:
        pytest.skip(
            "full Chromium (Playwright's `chromium` channel) is not installed here; "
            "`uv run playwright install chromium` installs it beside the headless shell: "
            + str(exc).splitlines()[0]
        )
    yield browser
    browser.close()


@pytest.fixture
def unasked_page(_unasked_browser, base_url):
    """A page in full Chromium with a fake camera the page has no permission for yet.

    ``page.context.grant_permissions(["camera"], origin=base_url)`` is the person's yes.
    """
    context = _unasked_browser.new_context(
        viewport={"width": 1280, "height": 800}, base_url=base_url
    )
    yield context.new_page()
    context.close()


@pytest.fixture(scope="module")
def drawing_camera_browser(browser_type):
    """Chromium with its fake camera playing garage.py's drawing, from ``garage.DRAWING``.
    Written whole and moved into place, so a run beside this one never reads half."""
    garage.DRAWING.parent.mkdir(parents=True, exist_ok=True)
    fd, part = tempfile.mkstemp(dir=garage.DRAWING.parent, suffix=".y4m")
    os.close(fd)
    garage.y4m(part)
    os.replace(part, garage.DRAWING)
    browser = launch(
        browser_type,
        args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
            f"--use-file-for-fake-video-capture={garage.DRAWING}",
        ],
    )
    yield browser
    browser.close()


@pytest.fixture
def fixture_picture(picture_folder):
    """The stated picture (tests/views_helpers.py) in the server's picture folder, as
    garage.NAME, its shapes stated beside it; its file name. Taken away after."""
    (picture_folder / f"{garage.NAME}.png").write_bytes(garage.picture())
    (picture_folder / f"{garage.NAME}.shapes.json").write_text(
        json.dumps(
            {"name": garage.NAME, "pixel_width": WIDE, "pixel_height": HIGH, "shapes": SHAPES}
        ),
        encoding="utf-8",
    )
    yield f"{garage.NAME}.png"
    (picture_folder / f"{garage.NAME}.png").unlink(missing_ok=True)
    (picture_folder / f"{garage.NAME}.shapes.json").unlink(missing_ok=True)


@pytest.fixture
def leaves_garage_as_found(page, base_url: str):
    """After the test: garage's views, cameras and kept pictures it added are taken
    back, and its layout is the code's again. ``page`` is the test module's own,
    where it has one."""
    api = page.request
    attached = api.get(f"{base_url}/sites/garage/attached").json()
    views = {vw["id"] for vw in attached["views"]}
    cameras = {c["name"] for c in attached["cameras"]}
    pictures = {p["path"] for p in api.get(f"{base_url}/photos/pictures").json()}
    yield
    attached = api.get(f"{base_url}/sites/garage/attached").json()
    for view in attached["views"]:
        if view["id"] not in views:
            api.delete(f"{base_url}/sites/garage/views/{view['id']}")
    for camera in attached["cameras"]:
        if camera["name"] not in cameras:
            api.delete(f"{base_url}/sites/garage/cameras/{camera['name']}")
    for picture in api.get(f"{base_url}/photos/pictures").json():
        if picture["path"] not in pictures and picture["kept"]:
            api.delete(f"{base_url}/photos/pictures/{picture['path']}")
    api.post(f"{base_url}/sites/garage/reset")


@pytest.fixture
def walkthrough(page, request, every_stl_built):
    """The walkthrough's recorder, written out however the test ends.

    Not gated on --generate-docs: every run of a walkthrough test writes its page.
    A page the quick `apothecary test run` writes is the run of a test marked
    `walkthrough`; a page only the browser suite writes passes
    ``browser_suite_only=True`` and is unmarked. The two are held together here,
    since the page's header and footer say which it is.
    """
    made: list[Walkthrough] = []

    def _make(
        ordinal, slug, title, intro, runtime, does_not_show, page=page, browser_suite_only=False
    ):
        # `page` may be another browser's -- the one launched with a fake
        # camera, for the page that places one -- and its screenshots are then
        # of that browser.
        marked = request.node.get_closest_marker("walkthrough") is not None
        if marked == browser_suite_only:
            pytest.fail(
                f"walkthrough page {ordinal}: a page the quick `apothecary test run` writes "
                "is the run of a test marked `walkthrough`; a page only the browser suite "
                "writes passes browser_suite_only=True and is not marked. This run is "
                f"{'' if marked else 'not '}marked and passes "
                f"browser_suite_only={browser_suite_only}."
            )
        recorder = Walkthrough(
            page=page,
            ordinal=ordinal,
            slug=slug,
            title=title,
            intro=intro,
            runtime=runtime,
            does_not_show=does_not_show,
            browser_suite_only=browser_suite_only,
            module=request.node.path.relative_to(ROOT).as_posix(),
            stls=every_stl_built()["said"],
        )
        made.append(recorder)
        return recorder

    yield _make

    for recorder in made:
        recorder.write()
