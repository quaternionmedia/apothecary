"""``/firmware`` routes: toolchain status, boards, sketches, and compile/upload/flash tasks.

Every endpoint that runs an engine returns a task id immediately; the GUI
polls ``GET /firmware/tasks/{id}?since=N`` for new log lines. The server
binds to localhost by default and this router does nothing to change that:
these endpoints run binaries and write to serial ports on the machine
hosting the server, so they are a local workbench control, not a service to
expose.
"""

from __future__ import annotations

import asyncio
import queue
import threading
from typing import List

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from jinja2 import Environment, FileSystemLoader

from ..projects.parts.skeleton import ROOT
from . import devices, service
from .installer import InstallSpec, env_for_arduino
from .models import (
    CompileRequest,
    CoreInstallRequest,
    EsptoolFlashRequest,
    InstallRequest,
    LibraryInstallRequest,
    ListenRequest,
    ProbeRequest,
    UploadRequest,
    validate_port,
)
from .sketches import discover_sketches, find_sketch
from .tasks import TaskBusy, get_task_runner
from .toolchains import SUGGESTED_CORES, ToolchainError, get_arduino_cli, get_esptool

router = APIRouter(prefix="/firmware", tags=["firmware"])

_env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=False)


def _sketch_or_404(name: str):
    sketch = find_sketch(name)
    if sketch is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{name}' not found")
    return sketch


def _start(kind: str, title: str, steps: List[List[str]], on_done=None):
    devices.get_streams().stop_all()  # a live serial overlay must not hold the port
    try:
        task = get_task_runner().run(kind, title, steps, env=env_for_arduino(), on_done=on_done)
    except TaskBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return task.snapshot()


def _start_callable(kind: str, title: str, fn):
    try:
        task = get_task_runner().run_callable(kind, title, fn)
    except TaskBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return task.snapshot()


def _engine(fn):
    try:
        return fn()
    except ToolchainError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# -- page ----------------------------------------------------------------------


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def firmware_page(request: Request):
    base_url = str(request.base_url).rstrip("/")
    template = _env.get_template("firmware.html.j2")
    return HTMLResponse(
        template.render(
            base_url=base_url,
            suggested_cores=SUGGESTED_CORES,
        )
    )


# -- status / catalogue ----------------------------------------------------------


@router.get("/status")
async def firmware_status():
    status = service.toolchain_status()
    data = status.model_dump()
    data["ok"] = status.ok
    data["suggested_cores"] = [{"id": cid, "label": label} for cid, label in SUGGESTED_CORES]
    active = get_task_runner().active
    data["active_task"] = active.snapshot() if active else None
    return data


@router.get("/boards")
async def firmware_boards():
    return [b.model_dump() for b in _engine(lambda: get_arduino_cli().board_list())]


@router.get("/boards/all")
async def firmware_boards_all():
    return [b.model_dump() for b in _engine(lambda: get_arduino_cli().board_listall())]


@router.get("/cores")
async def firmware_cores():
    return [c.model_dump() for c in _engine(lambda: get_arduino_cli().core_list())]


@router.get("/sketches")
async def firmware_sketches():
    return [s.to_json() for s in discover_sketches()]


# -- long-running actions → tasks ------------------------------------------------


@router.post("/install", status_code=202)
async def firmware_install(body: InstallRequest):
    spec = InstallSpec(
        version=body.version, force=body.force, cores=body.cores, libraries=body.libraries
    )
    return _start_callable("install", "Install arduino-cli", lambda log: service.install(spec, log))


@router.post("/cores/install", status_code=202)
async def firmware_core_install(body: CoreInstallRequest):
    cli = get_arduino_cli()
    steps = _engine(lambda: [cli.core_update_index_argv([body.id]), cli.core_install_argv(body.id)])
    return _start("core-install", f"Install core {body.id}", steps)


@router.post("/libraries/install", status_code=202)
async def firmware_library_install(body: LibraryInstallRequest):
    steps = _engine(lambda: [get_arduino_cli().lib_install_argv(body.names)])
    return _start("lib-install", "Install libraries " + ", ".join(body.names), steps)


@router.post("/sketches/{name}/compile", status_code=202)
async def firmware_compile(name: str, body: CompileRequest):
    sketch = _sketch_or_404(name)
    steps = _engine(lambda: service.compile_steps(sketch, body.fqbn))
    return _start("compile", f"Compile {sketch.name} ({body.fqbn})", steps)


@router.post("/sketches/{name}/upload", status_code=202)
async def firmware_upload(name: str, body: UploadRequest):
    sketch = _sketch_or_404(name)
    steps = _engine(lambda: service.upload_steps(sketch, body.fqbn, body.port))

    def remember(task):
        if task.status.value == "succeeded":
            service.record_upload(body.port, sketch, body.fqbn, task_id=task.id)

    return _start("upload", f"Upload {sketch.name} → {body.port}", steps, on_done=remember)


@router.post("/esptool/flash", status_code=202)
async def firmware_esptool_flash(body: EsptoolFlashRequest):
    esptool = get_esptool()

    def build():
        images = [(img.offset, service.resolve_image_path(img.path)) for img in body.images]
        steps = []
        if body.erase:
            steps.append(esptool.erase_argv(body.port, body.chip))
        steps.append(esptool.write_flash_argv(body.port, images, body.chip, body.baud))
        return steps

    def remember(task):
        if task.status.value == "succeeded":
            service.record_raw_flash(
                body.port, [f"{i.offset}:{i.path}" for i in body.images], task_id=task.id
            )

    return _start("esptool-flash", f"esptool flash → {body.port}", _engine(build), on_done=remember)


# -- devices: detected / probed / expected / observed -----------------------------


def _busy_guard():
    active = get_task_runner().active
    if active is not None:
        raise HTTPException(
            status_code=409, detail=f"task {active.id} ({active.title}) holds the port"
        )


def _device_view(d):
    expected = devices.expected_firmware(d, service.BUILD_ROOT)
    return {"device": d.model_dump(mode="json"), "expected": expected.model_dump(mode="json")}


@router.get("/devices")
async def firmware_devices():
    """Every detected port, with its cached chip identity and what should be running on it."""
    found = _engine(devices.detected_devices)
    return {
        "devices": [_device_view(d) for d in found],
        "streaming": devices.get_streams().open_ports,
    }


@router.post("/devices/probe")
def firmware_probe(body: ProbeRequest):
    """Identify the chip with esptool (resets the board); cached for later views."""
    _busy_guard()
    devices.get_streams().close(body.port)
    return _device_view(_engine(lambda: devices.probe_device(body.port)))


@router.post("/devices/listen")
def firmware_listen(body: ListenRequest):
    """Capture a few seconds of serial output; with ``reset`` the boot banner is included."""
    _busy_guard()
    if body.reset:
        _engine(lambda: devices.probe_device(body.port))
    result = _engine(lambda: devices.listen(body.port, body.seconds, body.baud))
    return result.model_dump(mode="json")


@router.get("/devices/stream")
async def firmware_stream(
    request: Request, port: str, baud: int = Query(115200, ge=300, le=2000000)
):
    """Server-sent events: live serial lines until the client leaves or a task takes the port."""
    try:
        validate_port(port)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _busy_guard()
    cli = get_arduino_cli()
    if not cli.is_available:
        raise HTTPException(status_code=503, detail="arduino-cli is not installed")

    q: queue.Queue = queue.Queue()
    stop = threading.Event()
    eof = object()

    def reader():
        try:
            for item in devices.stream_lines(port, baud, cli, stop=stop):
                q.put(item)
        finally:
            q.put(eof)

    threading.Thread(target=reader, daemon=True, name=f"serial-{port}").start()
    loop = asyncio.get_running_loop()

    async def events():
        yield f"event: open\ndata: {port} @ {baud}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await loop.run_in_executor(None, q.get, True, 1.0)
                except queue.Empty:
                    continue
                if item is eof:
                    yield "event: close\ndata: monitor stopped\n\n"
                    break
                if item is None:
                    yield ": keepalive\n\n"
                else:
                    yield "data: " + item.replace("\n", " ") + "\n\n"
        finally:
            stop.set()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# -- tasks ------------------------------------------------------------------------


@router.get("/tasks")
async def firmware_tasks():
    return [t.snapshot(since=len(t.lines)) for t in get_task_runner().list()]


@router.get("/tasks/{task_id}")
async def firmware_task(task_id: str, since: int = Query(0, ge=0)):
    task = get_task_runner().get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.snapshot(since=since)


@router.post("/tasks/{task_id}/cancel")
async def firmware_task_cancel(task_id: str):
    if not get_task_runner().cancel(task_id):
        raise HTTPException(status_code=409, detail="Task is not running")
    return get_task_runner().get(task_id).snapshot()
