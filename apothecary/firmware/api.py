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
import json
import queue
import threading
from typing import List

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from jinja2 import Environment, FileSystemLoader

from ..projects.parts.skeleton import ROOT
from . import devices, gcode, service
from .installer import InstallSpec, env_for_arduino
from .models import (
    CompileRequest,
    CoreInstallRequest,
    EsptoolFlashRequest,
    InstallRequest,
    LevelingRequest,
    LibraryInstallRequest,
    ListenRequest,
    PrinterControlArmRequest,
    PrinterControlRequest,
    PrinterIdentifyRequest,
    PrinterQueryRequest,
    PrintRequest,
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


def _start(kind: str, title: str, steps: List[List[str]], on_done=None, port=None):
    devices.get_streams().stop_all()  # a live serial overlay must not hold the port
    if port:
        # Only the port being written to: releasing every printer link would
        # reset every printer (DTR) the next time it is polled.
        _release_or_409(port)
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


@router.get("/monitor", response_class=HTMLResponse, include_in_schema=False)
async def monitor_page(request: Request, port: str = ""):
    """The focused printer monitor: one port, its status, comms log and controls.

    ``port`` is validated by shape and emitted as JSON: the template runs with
    autoescape off, so a raw query string must never reach a script literal.
    """
    try:
        validate_port(port) if port else None
    except ValueError:
        port = ""
    base_url = str(request.base_url).rstrip("/")
    template = _env.get_template("monitor.html.j2")
    return HTMLResponse(template.render(base_url=base_url, port_json=json.dumps(port)))


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
# These shell out to arduino-cli / esptool (tens of seconds worst case), so they
# are plain ``def``: FastAPI runs them in its threadpool instead of on the event
# loop, which keeps task polling, SSE streams and the viewer responsive.


@router.get("/status")
def firmware_status():
    status = service.toolchain_status()
    data = status.model_dump()
    data["ok"] = status.ok
    data["suggested_cores"] = [{"id": cid, "label": label} for cid, label in SUGGESTED_CORES]
    active = get_task_runner().active
    data["active_task"] = active.snapshot() if active else None
    return data


@router.get("/boards")
def firmware_boards():
    return [b.model_dump() for b in _engine(lambda: get_arduino_cli().board_list())]


@router.get("/boards/all")
def firmware_boards_all():
    return [b.model_dump() for b in _engine(lambda: get_arduino_cli().board_listall())]


@router.get("/cores")
def firmware_cores():
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

    def remember(task, status):
        if status.value == "succeeded":
            service.record_upload(body.port, sketch, body.fqbn, task_id=task.id)

    return _start(
        "upload", f"Upload {sketch.name} → {body.port}", steps, on_done=remember, port=body.port
    )


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

    def remember(task, status):
        if status.value == "succeeded":
            service.record_raw_flash(
                body.port, [f"{i.offset}:{i.path}" for i in body.images], task_id=task.id
            )

    return _start(
        "esptool-flash",
        f"esptool flash → {body.port}",
        _engine(build),
        on_done=remember,
        port=body.port,
    )


# -- devices: detected / probed / expected / observed -----------------------------


def _release_or_409(port: str) -> bool:
    try:
        return gcode.get_printer_links().close(port)
    except ToolchainError as exc:  # a print streams over it
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _no_print_or_409(port: str) -> None:
    job = devices.print_job(port)
    if job is not None and job.finished is None:
        raise HTTPException(
            status_code=409, detail=f"{port}: a print holds the port -- cancel it first"
        )


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
def firmware_devices(fresh: bool = False):
    """Every detected port, with its cached chip identity and what should be running on it.

    The port scan is cached for a couple of seconds; ``fresh`` forces one.
    """
    found = _engine(lambda: devices.detected_devices(fresh=fresh))
    return {
        "devices": [_device_view(d) for d in found],
        "streaming": devices.get_streams().open_ports,
        "printers": gcode.get_printer_links().open_ports,
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


@router.post("/devices/identify")
def firmware_identify(body: PrinterIdentifyRequest):
    """Ask ``M115``: is this a printer mainboard, and which firmware? ``reset`` reboots it first."""
    _busy_guard()
    return _device_view(
        _engine(lambda: devices.identify_printer(body.port, body.baud, reset=body.reset))
    )


@router.get("/printers/status")
def firmware_printer_status(port: str, baud: int = Query(None, ge=300, le=2000000)):
    """One poll of a printer over its held-open link (opened on first use)."""
    try:
        validate_port(port)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _busy_guard()
    status = _engine(lambda: devices.printer_status(port, baud))
    data = status.model_dump(mode="json")
    data["heating"] = status.heating
    # A failed poll drops the link (and with it the control latch): say so, so
    # a page polling on a schedule learns it without a second request.
    data["held"] = gcode.get_printer_links().get(port) is not None
    data["control"] = _control_state(port)
    return data


def _control_state(port: str) -> dict:
    latch = gcode.get_printer_links().control
    return {
        "port": port,
        "armed": latch.armed(port),
        "seconds_left": round(latch.seconds_left(port)),
    }


@router.get("/printers/controls")
async def firmware_printer_controls():
    """The control lines the command route accepts (regex + purpose) and their bounds."""
    return {
        "codes": [{"pattern": p.pattern, "does": what} for p, what in gcode.CONTROL_CODES],
        "emergency_stop": gcode.EMERGENCY_STOP,
        "bounds": {
            "hotend_max_c": gcode.HOTEND_MAX_C,
            "bed_max_c": gcode.BED_MAX_C,
            "jog_max_mm": gcode.JOG_MAX_MM,
            "feed_max": gcode.FEED_MAX,
            "latch_ttl_s": gcode.CONTROL_TTL_S,
        },
    }


@router.post("/printers/control")
async def firmware_printer_control_arm(body: PrinterControlArmRequest):
    """Arm (or disarm) the port's control latch; armed lapses after ``ttl_s`` of silence."""
    latch = gcode.get_printer_links().control
    if body.armed:
        latch.arm(body.port, body.ttl_s)
        gcode.get_printer_links().log_for(body.port).add(
            "sys", f"control armed for {body.ttl_s:.0f}s", "control"
        )
    else:
        latch.disarm(body.port)
        gcode.get_printer_links().log_for(body.port).add("sys", "control disarmed", "control")
    return _control_state(body.port)


@router.get("/printers/control")
async def firmware_printer_control_state(port: str):
    try:
        validate_port(port)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _control_state(port)


@router.post("/printers/command")
def firmware_printer_command(body: PrinterControlRequest):
    """Send one allowlisted control line -- heaters, fan, homing, bounded jogs, SD
    pause/resume/abort -- while the latch is armed. ``M112`` (emergency stop) always goes."""
    try:
        gcode.normalise_control(body.command)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _busy_guard()
    try:
        result = devices.printer_control(body.port, body.command)
    except gcode.ControlNotArmed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ToolchainError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    data = result.model_dump(mode="json")
    data["control"] = _control_state(body.port)
    return data


# -- bed leveling ------------------------------------------------------------------


@router.post("/printers/level", status_code=202)
def firmware_printer_level(body: LevelingRequest):
    """Start a bed reading: home, probe (``G29``, latch required) and read, or just read."""
    _busy_guard()
    try:
        job = devices.start_leveling(body.port, probe=body.probe, note=body.note)
    except gcode.ControlNotArmed as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ToolchainError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return job.snapshot()


@router.get("/printers/level")
async def firmware_printer_level_status(port: str):
    """The current (or last) bed-reading job on ``port``, if any."""
    try:
        validate_port(port)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    job = devices.leveling_job(port)
    return job.snapshot() if job else {"port": port, "running": False, "stage": None}


@router.get("/printers/leveling")
async def firmware_printer_leveling(port: str = ""):
    """Saved bed readings, newest first (all ports when ``port`` is empty); no raw lines."""
    if port:
        try:
            validate_port(port)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [
        r.model_dump(mode="json", exclude={"lines", "subdivided"})
        for r in devices.leveling_records(port or None)
    ]


@router.get("/printers/leveling/{record_id}")
async def firmware_printer_leveling_record(record_id: str):
    """One saved reading in full: mesh, subdivided mesh, and every line the firmware said."""
    record = devices.leveling_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="no such bed reading")
    return record.model_dump(mode="json")


# -- host printing ------------------------------------------------------------------

PRINT_FILE_MAX = 64 * 1024 * 1024


@router.get("/printers/prints")
async def firmware_print_files():
    """The G-code files kept on the host, newest first, each with its line count and problems."""
    return [f.model_dump(mode="json") for f in devices.print_files()]


@router.post("/printers/prints", status_code=201)
async def firmware_print_upload(
    request: Request, name: str = Query(..., min_length=1, max_length=200)
):
    """Keep a G-code file (the request body, as text) under ``name``; it is checked, not sent."""
    data = await request.body()
    if not data:
        raise HTTPException(status_code=422, detail="an empty file")
    if len(data) > PRINT_FILE_MAX:
        raise HTTPException(
            status_code=413, detail=f"larger than {PRINT_FILE_MAX // (1024 * 1024)} MB"
        )
    return devices.save_print_file(name, data).model_dump(mode="json")


@router.delete("/printers/prints/{file_id}")
async def firmware_print_delete(file_id: str):
    try:
        found = devices.delete_print_file(file_id)
    except ToolchainError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not found:
        raise HTTPException(status_code=404, detail="no such print file")
    return {"id": file_id, "deleted": True}


@router.post("/printers/print", status_code=202)
def firmware_print_start(body: PrintRequest):
    """Stream a kept file to the printer (latch required); the job's first snapshot."""
    _busy_guard()
    try:
        job = devices.start_print(body.port, body.file_id)
    except (gcode.ControlNotArmed, ToolchainError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return job.snapshot()


@router.get("/printers/print")
async def firmware_print_status(port: str):
    """The current (or last) host print on ``port``, if any."""
    try:
        validate_port(port)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    job = devices.print_job(port)
    return job.snapshot() if job else {"port": port, "running": False, "stage": None}


def _print_verb(port: str, verb: str) -> dict:
    job = devices.print_job(port)
    if job is None or job.finished is not None:
        raise HTTPException(status_code=409, detail=f"{port}: no print is running")
    if verb == "resume" and not gcode.get_printer_links().control.armed(port):
        raise HTTPException(
            status_code=409, detail=f"{port}: resuming moves the machine -- arm control first"
        )
    getattr(job, verb)()
    if verb != "cancel":
        gcode.get_printer_links().control.renew(port)
    return job.snapshot()


@router.post("/printers/print/pause")
def firmware_print_pause(body: ProbeRequest):
    """Stop feeding lines; the firmware finishes what it has queued. No latch needed."""
    return _print_verb(body.port, "pause")


@router.post("/printers/print/resume")
def firmware_print_resume(body: ProbeRequest):
    """Feed lines again (latch required: it moves the machine)."""
    return _print_verb(body.port, "resume")


@router.post("/printers/print/cancel")
def firmware_print_cancel(body: ProbeRequest):
    """Stop feeding and send the safe-off (heaters and fan off, motors free). No latch needed."""
    return _print_verb(body.port, "cancel")


@router.get("/printers/print/records")
async def firmware_print_records(port: str = ""):
    """Prints streamed from here, newest first (all ports when ``port`` is empty)."""
    if port:
        try:
            validate_port(port)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [
        r.model_dump(mode="json", exclude={"lines"}) for r in devices.print_records(port or None)
    ]


@router.get("/printers/print/records/{record_id}")
async def firmware_print_record(record_id: str):
    record = devices.print_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="no such print")
    return record.model_dump(mode="json")


@router.get("/printers/queries")
async def firmware_printer_queries():
    """The report-only G-code the query route accepts, with what each reports."""
    return [{"command": c, "reports": what} for c, what in gcode.QUERY_CODES.items()]


@router.post("/printers/query")
def firmware_printer_query(body: PrinterQueryRequest):
    """Send one allowlisted report code (``M503``, ``M119``, ``M20`` ...) over the held link."""
    try:
        gcode.normalise_query(body.command)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _busy_guard()
    result = _engine(lambda: devices.printer_query(body.port, body.command))
    return result.model_dump(mode="json")


@router.get("/printers/info")
def firmware_printer_info(port: str):
    """Everything the monitor page needs at once: device, held link, last poll."""
    try:
        validate_port(port)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    found = _engine(devices.detected_devices)
    device = next((d for d in found if d.port == port), None)
    link = gcode.get_printer_links().get(port)
    last = devices.last_statuses().get(port)
    return {
        "port": port,
        "detected": device is not None,
        "device": _device_view(device) if device else None,
        "link": link.info() if link else None,
        "engine": gcode.serial_engine(),
        "last_status": last.model_dump(mode="json") if last else None,
        "active_task": (get_task_runner().active or None) and get_task_runner().active.snapshot(),
        "control": _control_state(port),
    }


@router.get("/printers/log")
async def firmware_printer_log(port: str, since: int = Query(0, ge=0)):
    """The port's comms log from index ``since`` on (tx/rx/boot/sys entries)."""
    try:
        validate_port(port)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    links = gcode.get_printer_links()
    data = links.log_for(port).since(since)
    data["port"] = port
    data["held"] = links.get(port) is not None
    return data


@router.post("/printers/reconnect")
def firmware_printer_reconnect(body: PrinterIdentifyRequest):
    """Release and reopen the link (no reset), then poll."""
    _busy_guard()
    _no_print_or_409(body.port)
    status = _engine(lambda: devices.printer_reconnect(body.port, body.baud))
    data = status.model_dump(mode="json")
    data["heating"] = status.heating
    return data


@router.post("/printers/reset")
def firmware_printer_reset(body: ProbeRequest):
    """Reboot the board deliberately (DTR pulse); returns its boot banner."""
    _busy_guard()
    _no_print_or_409(body.port)
    return {"port": body.port, "boot_lines": _engine(lambda: devices.printer_reset(body.port))}


@router.post("/printers/release")
def firmware_printer_release(body: ProbeRequest):
    """Drop the held link so another tool (a slicer, OctoPrint) can open the port."""
    return {"port": body.port, "released": _release_or_409(body.port)}


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
    _release_or_409(port)  # one holder per port (the monitor resets it anyway)

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
