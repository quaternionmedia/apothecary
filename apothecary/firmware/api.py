"""``/firmware`` routes: toolchain status, boards, sketches, and compile/upload/flash tasks.

Every endpoint that runs an engine returns a task id immediately; the
viewer's Bench and a board's Machine poll ``GET /firmware/tasks/{id}?since=N``
for new log lines. ``/firmware`` and ``/firmware/monitor`` are not this
router's: they redirect to the Bench and a board's Machine in front of the
world (``apothecary/api.py``). The server
binds to localhost by default and this router does nothing to change that:
these endpoints run binaries and write to serial ports on the machine
hosting the server, so they are a local workbench control, not a service to
expose.

Every route answers the seam's exceptions the same way (``FirmwareRoute``):
something else has the port, the latch is down or a task runs (409); the
engine is missing or failed (503); the request cannot be done as asked (422).
"""

from __future__ import annotations

import asyncio
import queue
import threading
from typing import List, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.routing import APIRoute

from .. import control_loops, loop_document
from . import can, devices, gcode, loops, service
from .installer import InstallSpec, env_for_arduino
from .models import (
    CompileRequest,
    CoreInstallRequest,
    EsptoolFlashRequest,
    InstallRequest,
    LevelingRequest,
    LibraryInstallRequest,
    ListenRequest,
    LoopDocumentRequest,
    LoopExperimentRequest,
    LoopGainsRequest,
    LoopPlanRequest,
    LoopSaveRequest,
    ModuleInstallRequest,
    PlateRequest,
    Port,
    PrinterControlArmRequest,
    PrinterControlRequest,
    PrinterIdentifyRequest,
    PrinterJogRequest,
    PrinterQueryRequest,
    PrintRequest,
    ProbeRequest,
    UploadRequest,
)
from .modules import Plan, get_module
from .sketches import discover_sketches, find_sketch
from .tasks import TaskBusy, get_task_runner
from .toolchains import PortHeld, ToolchainError, get_arduino_cli, get_esptool


class FirmwareRoute(APIRoute):
    """Maps the seam's exceptions to one status each, for every route on the router."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def answer(request: Request):
            try:
                return await handler(request)
            except (PortHeld, gcode.ControlNotArmed, TaskBusy) as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except ToolchainError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

        return answer


router = APIRouter(prefix="/firmware", tags=["firmware"], route_class=FirmwareRoute)

# A port filter: one port, or "" for every port.
PortOrAll = Port | Literal[""]


def _sketch_or_404(name: str):
    sketch = find_sketch(name)
    if sketch is None:
        raise HTTPException(status_code=404, detail=f"Sketch '{name}' not found")
    return sketch


def _start(kind: str, title: str, steps: List[List[str]] | Plan, on_done=None, port=None):
    """Run ``steps`` -- argv lists in arduino-cli's environment, or a module's
    ``Plan`` in its own environment and folder -- as the one task."""
    devices.get_streams().stop_all()  # a devkit's Machine listening must not hold the port
    if port:
        # Only the port being written to: releasing every printer link would
        # reset every printer (DTR) the next time it is polled.
        gcode.get_printer_links().close(port)
    plan = steps if isinstance(steps, Plan) else Plan(steps, env=env_for_arduino())
    task = get_task_runner().run(
        kind,
        title,
        plan.steps,
        env=plan.env,
        cwd=str(plan.cwd) if plan.cwd else None,
        on_done=on_done,
        port=port,
    )
    return task.snapshot()


# -- status / catalogue ----------------------------------------------------------
# These shell out to arduino-cli / esptool (tens of seconds worst case), so they
# are plain ``def``: FastAPI runs them in its threadpool instead of on the event
# loop, which keeps task polling, SSE streams and the viewer responsive.


@router.get("/status")
def firmware_status():
    """Where the tools live and every toolchain module's status, with the task
    running now."""
    data = service.toolchain_status().model_dump()
    active = get_task_runner().active
    data["active_task"] = active.snapshot() if active else None
    return data


@router.get("/toolchains")
def firmware_toolchains():
    """Every toolchain module: what it builds, its tools as found, its problems."""
    return [t.model_dump() for t in service.toolchain_status().toolchains]


@router.get("/boards")
def firmware_boards():
    return [b.model_dump() for b in get_arduino_cli().board_list()]


@router.get("/boards/all")
def firmware_boards_all():
    return [b.model_dump() for b in get_arduino_cli().board_listall()]


@router.get("/cores")
def firmware_cores():
    return [c.model_dump() for c in get_arduino_cli().core_list()]


@router.get("/sketches")
async def firmware_sketches():
    return [s.to_json() for s in discover_sketches()]


# -- long-running actions → tasks ------------------------------------------------


@router.post("/install", status_code=202)
async def firmware_install(body: InstallRequest):
    spec = InstallSpec(
        version=body.version, force=body.force, cores=body.cores, libraries=body.libraries
    )
    task = get_task_runner().run_callable(
        "install", "Install arduino-cli", lambda log: service.install(spec, log)
    )
    return task.snapshot()


@router.post("/toolchains/{module_id}/install", status_code=202)
async def firmware_module_install(module_id: str, body: ModuleInstallRequest):
    """Install one toolchain module's tools (``arduino``, ``rust-esp32``), as a task."""
    try:
        module = get_module(module_id)
    except ToolchainError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    task = get_task_runner().run_callable(
        "install",
        f"Install {module.label}" if module.id != "arduino" else "Install arduino-cli",
        lambda log: service.install_module(module.id, log, force=body.force),
    )
    return task.snapshot()


@router.post("/cores/install", status_code=202)
async def firmware_core_install(body: CoreInstallRequest):
    cli = get_arduino_cli()
    steps = [cli.core_update_index_argv([body.id]), cli.core_install_argv(body.id)]
    return _start("core-install", f"Install core {body.id}", steps)


@router.post("/libraries/install", status_code=202)
async def firmware_library_install(body: LibraryInstallRequest):
    steps = [get_arduino_cli().lib_install_argv(body.names)]
    return _start("lib-install", "Install libraries " + ", ".join(body.names), steps)


def _board(sketch, given):
    """An Arduino sketch's FQBN, as the request names it (required); None for a
    module's sketch that builds for what its project names."""
    if get_module(sketch.toolchain).needs_board and not given:
        raise ValueError(f"fqbn: {sketch.name} is an Arduino sketch; name the board to build for")
    return service.resolve_board(sketch, given)


def upload_sketch(sketch, board: str | None, port: str, replace: bool = False):
    """Flash a sketch to ``port`` as the one task, recorded once it has succeeded. A
    machine's controller is flashed only when ``replace`` asks for it
    (``devices.not_a_machines_controller``)."""
    devices.not_a_machines_controller(port, replace)
    plan = service.flash_plan(sketch, board, port)

    def remember(task, status):
        if status.value == "succeeded":
            service.record_upload(port, sketch, board, task_id=task.id)

    return _start("upload", service.upload_title(sketch, port), plan, on_done=remember, port=port)


@router.post("/sketches/{name}/compile", status_code=202)
async def firmware_compile(name: str, body: CompileRequest):
    """Build a sketch with its toolchain module. ``name`` is a sketch's id: an
    Arduino sketch's name, or ``<name>@<module>`` (``esp32_blink@rust-esp32``)."""
    sketch = _sketch_or_404(name)
    board = _board(sketch, body.fqbn)
    plan = service.build_plan(sketch, board)
    return _start("compile", service.compile_title(sketch, board), plan)


@router.post("/sketches/{name}/upload", status_code=202)
async def firmware_upload(name: str, body: UploadRequest):
    sketch = _sketch_or_404(name)
    return upload_sketch(
        sketch, _board(sketch, body.fqbn), body.port, replace=body.replace_machine_firmware
    )


@router.post("/esptool/flash", status_code=202)
async def firmware_esptool_flash(body: EsptoolFlashRequest):
    esptool = get_esptool()
    devices.not_a_machines_controller(body.port, body.replace_machine_firmware)
    images = [(img.offset, service.resolve_image_path(img.path)) for img in body.images]
    steps = []
    if body.erase:
        steps.append(esptool.erase_argv(body.port, body.chip))
    steps.append(esptool.write_flash_argv(body.port, images, body.chip, body.baud))

    def remember(task, status):
        if status.value == "succeeded":
            service.record_raw_flash(
                body.port, [f"{i.offset}:{i.path}" for i in body.images], task_id=task.id
            )

    return _start(
        "esptool-flash", f"esptool flash → {body.port}", steps, on_done=remember, port=body.port
    )


# -- devices: detected / probed / expected / observed -----------------------------


def _no_print(port: str) -> None:
    can.raise_for(can.print_holds(port, devices.print_job(port)), "held")


def _busy_guard(port: str):
    """Refused while a running task writes to ``port`` (an upload, a flash). A
    compile or an install holds no port, so a printer's poll and its emergency
    stop still go while a sketch compiles."""
    can.raise_for(can.task_holds(port, get_task_runner().active), "held")


def device_view(d):
    expected = devices.expected_firmware(d, service.BUILD_ROOT)
    return {"device": d.model_dump(mode="json"), "expected": expected.model_dump(mode="json")}


@router.get("/devices")
def firmware_devices(fresh: bool = False):
    """Every detected port, with its cached chip identity and what should be running on it.

    The port scan is cached for a couple of seconds; ``fresh`` forces one.
    """
    found = devices.detected_devices(fresh=fresh)
    return {
        "devices": [device_view(d) for d in found],
        "streaming": devices.get_streams().open_ports,
        "printers": gcode.get_printer_links().open_ports,
    }


@router.post("/devices/probe")
def firmware_probe(body: ProbeRequest):
    """Identify the chip with esptool (resets the board); cached for later views."""
    _busy_guard(body.port)
    devices.get_streams().close(body.port)
    return device_view(devices.probe_device(body.port))


@router.post("/devices/listen")
def firmware_listen(body: ListenRequest):
    """Capture a few seconds of serial output; with ``reset`` the boot banner is included."""
    _busy_guard(body.port)
    if body.reset:
        devices.probe_device(body.port)
    return devices.listen(body.port, body.seconds, body.baud).model_dump(mode="json")


@router.post("/devices/identify")
def firmware_identify(body: PrinterIdentifyRequest):
    """Ask what the board is: a printer's ``M115``, then a router's ``$I``, and which
    firmware answered. ``reset`` reboots it
    first. ``if_idle`` asks only a board nothing here knows to be printing -- a print
    from here, a running job, or its last poll -- and refuses one that may be busy
    (409, saying why) without sending anything: a printer's Pin asks this way."""
    try:
        _busy_guard(body.port)
    except PortHeld as held:
        if body.if_idle:
            raise PortHeld(f"not asked: {held}") from None
        raise
    if body.if_idle:
        busy = devices.known_printing(body.port)
        if busy is not None:
            raise PortHeld(f"not asked: {busy}")
    return device_view(devices.identify_printer(body.port, body.baud, reset=body.reset))


@router.get("/printers/status")
def firmware_printer_status(port: Port, baud: int = Query(None, ge=300, le=2000000)):
    """One poll of a printer over its held-open link (opened on first use)."""
    _busy_guard(port)
    status = devices.printer_status(port, baud)
    data = status.model_dump(mode="json")
    data["heating"] = status.heating
    # A failed poll drops the link (and with it the control latch): say so, so
    # a page polling on a schedule learns it without a second request.
    data["held"] = gcode.get_printer_links().get(port) is not None
    data["control"] = _control_state(port)
    data["can"] = can.can_now(port)
    return data


def _control_state(port: str) -> dict:
    latch = gcode.get_printer_links().control
    return {
        "port": port,
        "armed": latch.armed(port),
        "seconds_left": round(latch.seconds_left(port)),
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
async def firmware_printer_control_state(port: Port):
    return _control_state(port)


@router.get("/printers/can-start")
def firmware_printer_can_start(port: Port, file_id: str = Query(..., min_length=1)):
    """Whether the kept file ``file_id`` would be started on ``port`` now, and if not
    why: what ``POST /printers/print`` would refuse, answered without sending it."""
    return can.can_start(port, file_id)


@router.get("/printers/armed")
async def firmware_printers_armed():
    """Every port whose control is armed now, and its seconds left, however it was armed:
    its Machine, the deck's long presses, another browser. A page follows it to show a
    machine armed when its Machine is not open."""
    return {"armed": gcode.get_printer_links().control.armed_ports()}


@router.get("/busy")
def firmware_busy():
    """What a restart of this server would cut into, each in a line; ``busy`` is empty
    when it would cut into nothing. A job streaming, a bed reading or a table map
    under way, a port whose control is armed, a task writing to a board (a flash cut
    off part way leaves a board with half a firmware), and work a member of the
    family was handed and has not ended. For whatever restarts the server for a
    reason of its own: it asks here, and a server that does not answer has not said
    it is idle."""
    from ..family import members

    said = devices.at_work()
    active = get_task_runner().active
    if active is not None:
        said.append(f"task {active.id} ({active.title}) is running")
    for name in ("machine", "board"):
        member = members.hosted(name)
        for piece in member.state()["working"] if member is not None else []:
            said.append(f"{name}: {piece.get('verb')} for step {piece['cue'].get('number')}")
    return {"busy": said}


@router.post("/printers/command")
def firmware_printer_command(body: PrinterControlRequest):
    """Send one allowlisted control line -- a printer's heaters, fan, homing, bounded
    jogs and SD pause/resume/abort; a router's homing, unlock, jogs, spindle, work zero,
    probe, hold and resume -- while the latch is armed. The stop (``M112``; a router's
    ``RESET``) always goes, as the stop of whatever is on the port."""
    if not devices.is_emergency_stop(body.command):
        _busy_guard(body.port)
    data = devices.printer_control(body.port, body.command).model_dump(mode="json")
    data["control"] = _control_state(body.port)
    return data


@router.post("/printers/jog")
def firmware_printer_jog(body: PrinterJogRequest):
    """One relative move of one axis, as one act on the port (latch required): a
    router's jog line, or a printer's relative move with absolute positioning put
    back whatever became of it, the link held from first line to last. What the
    page's pad and the deck's knobs both send."""
    _busy_guard(body.port)
    data = devices.printer_jog(body.port, body.axis, body.mm, body.feed).model_dump(mode="json")
    data["control"] = _control_state(body.port)
    return data


# -- the touch plate ---------------------------------------------------------------


@router.get("/printers/plate")
def firmware_printer_plate(port: Port):
    """The touch plate of the router on ``port``: its thickness as measured and kept for
    that board, else the maker's nominal figure, and where the figure is from."""
    return devices.plate(port)


@router.put("/printers/plate")
def firmware_printer_plate_set(body: PlateRequest):
    """Keep the plate's thickness as measured, for the board on ``port``: what Probe Z to
    plate calls the touch."""
    try:
        return devices.set_plate(body.port, body.thickness_mm)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# -- bed leveling ------------------------------------------------------------------


@router.post("/printers/level", status_code=202)
def firmware_printer_level(body: LevelingRequest):
    """Start a bed reading in the port's dialect: a printer's -- home, probe (``G29``,
    latch required) and read, or just read the stored mesh; a router's table map --
    home, then probe down at each point of ``grid`` (latch required)."""
    _busy_guard(body.port)
    return devices.start_leveling(
        body.port, probe=body.probe, note=body.note, grid=body.grid
    ).snapshot()


@router.get("/printers/level")
async def firmware_printer_level_status(port: Port):
    """The current (or last) bed-reading job on ``port``, if any."""
    job = devices.leveling_job(port)
    return job.snapshot() if job else {"port": port, "running": False, "stage": None}


@router.get("/printers/leveling")
async def firmware_printer_leveling(port: PortOrAll = ""):
    """Saved bed readings, newest first (all ports when ``port`` is empty); no raw lines."""
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
    request: Request,
    name: str = Query(..., min_length=1, max_length=200),
    machine: str = Query(
        ..., pattern="^(printer|router)$", description="the kind of machine it is kept for"
    ),
):
    """Keep a G-code file (the request body, as text) under ``name``, for a kind of
    machine; it is checked in that machine's terms, not sent."""
    data = await request.body()
    if not data:
        raise HTTPException(status_code=422, detail="an empty file")
    if len(data) > PRINT_FILE_MAX:
        raise HTTPException(
            status_code=413, detail=f"larger than {PRINT_FILE_MAX // (1024 * 1024)} MB"
        )
    # Checking and writing 60 MB takes seconds: off the event loop, so polls keep going.
    kept = await run_in_threadpool(devices.save_print_file, name, data, machine)
    return kept.model_dump(mode="json")


@router.get("/printers/prints/{file_id}/preview")
def firmware_print_preview(file_id: str, machine: str = Query("printer", max_length=20)):
    """A kept file's toolpath as a kind of machine would run it, to draw and scrub through
    (docs/toolpath-preview.md). Plain ``def``: reading a long file takes seconds."""
    try:
        found = devices.print_preview(file_id, machine)
    except KeyError:
        raise HTTPException(status_code=422, detail=f"no way to preview a {machine!r}") from None
    if found is None:
        raise HTTPException(status_code=404, detail="no such print file")
    return found.model_dump(mode="json")


@router.delete("/printers/prints/{file_id}")
async def firmware_print_delete(file_id: str):
    if not devices.delete_print_file(file_id):
        raise HTTPException(status_code=404, detail="no such print file")
    return {"id": file_id, "deleted": True}


@router.post("/printers/print", status_code=202)
def firmware_print_start(body: PrintRequest):
    """Stream a kept file to the printer (latch required), as a print job naming the
    part it makes, if one is named; the print's first snapshot, with its ``job_id``.
    The printer's jobs are ``GET /jobs?machine=``."""
    _busy_guard(body.port)
    return devices.start_print(body.port, body.file_id, part=body.part).snapshot()


@router.get("/printers/print")
async def firmware_print_status(port: Port):
    """The current (or last) host print on ``port``, if any."""
    job = devices.print_job(port)
    return job.snapshot() if job else {"port": port, "running": False, "stage": None}


def _print_verb(port: str, verb: str) -> dict:
    job = devices.print_job(port)
    if job is None or job.finished is not None:
        raise HTTPException(status_code=409, detail=f"{port}: no print is running")
    if verb == "resume":
        can.raise_for(
            can.not_armed(
                port,
                gcode.get_printer_links().control.armed(port),
                "resuming moves the machine -- arm control first",
            ),
            "armed",
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


# -- a heater's loop (firmware/loops.py) --------------------------------------------------


@router.post("/printers/loops/read")
def firmware_loops_read(body: ProbeRequest):
    """The gains the board holds, as ``M503`` says them (report-only), by loop."""
    _busy_guard(body.port)
    can.raise_for_refusal(can.read_refusal(can.facts_of(body.port)))
    return loops.read_gains(body.port)


@router.post("/printers/loops/start", status_code=202)
def firmware_loops_start(body: LoopExperimentRequest):
    """Start an experiment on a loop -- a step of the target, the firmware's autotune, or a
    square wave of the target about an operating temperature -- as a job that holds the
    port (latch required), with the ceiling and the longest time the request states."""
    _busy_guard(body.port)
    params = body.model_dump(exclude={"port", "heater", "index", "kind", "ceiling_c", "max_duration_s", "sample_period_s"})
    plan = loops.plan(
        body.heater, body.index, body.kind, body.ceiling_c, body.max_duration_s, body.sample_period_s, **params
    )
    return loops.start(body.port, plan).snapshot()


@router.post("/printers/loops/can-start")
def firmware_loops_can_start(body: LoopPlanRequest):
    """Whether an experiment of these figures would be started on ``port`` now: the
    machine's verdict (``tune.start``), then the plan's -- a ceiling and a longest time
    stated, every target under the ceiling, the schedule within the longest time -- as
    ``{ok, why, kind, plan}``, with the plan (the targets and when, or the autotune line)
    when it would. Nothing is sent."""
    return can.can_tune(body.port, body.model_dump(exclude={"port"}))


@router.get("/printers/loops/job")
async def firmware_loops_job(port: Port, series: bool = False):
    """The current (or last) experiment on ``port``, with its samples so far when
    ``series`` asks for them."""
    job = loops.tuning_job(port)
    return job.snapshot(samples=series) if job else {"port": port, "running": False, "stage": None}


@router.post("/printers/loops/cancel")
def firmware_loops_cancel(body: ProbeRequest):
    """End the running experiment: the heater off and read back, as at every end. No latch."""
    can.raise_for_refusal(can.tune_cancel_refusal(can.facts_of(body.port)))
    job = loops.tuning_job(body.port)
    job.cancel()
    return job.snapshot()


@router.post("/printers/loops/set")
def firmware_loops_set(body: LoopGainsRequest):
    """Set a loop's gains (``M301``/``M304``, latch required), read back and compared. Set,
    not saved."""
    _busy_guard(body.port)
    return loops.set_gains(body.port, body.heater, body.index, body.kp, body.ki, body.kd)


@router.post("/printers/loops/save")
def firmware_loops_save(body: LoopSaveRequest):
    """``M500``, the board's memory written: refused unless ``write_board_memory`` is true."""
    _busy_guard(body.port)
    return loops.save_settings(body.port, body.write_board_memory)


@router.get("/printers/loops/experiments")
async def firmware_loops_experiments(port: PortOrAll = ""):
    """The kept experiments, newest first, without their samples."""
    return loops.experiments(port or None)


@router.get("/printers/loops/experiments/{experiment_id}")
async def firmware_loops_experiment(experiment_id: str):
    """One kept experiment, its samples and what the firmware said."""
    body = loops.experiment(experiment_id)
    if body is None:
        raise HTTPException(status_code=404, detail="no such experiment")
    return body


@router.post("/printers/loops/document")
def firmware_loops_document(body: LoopDocumentRequest, format: Literal["json", "md"] = "json"):
    """The ``control/loop/1`` document of a kept experiment: its plant identified, a
    controller designed by ``rule``, the margins and the measures; with ``read_board`` the
    gains the board holds read now."""
    doc = loops.document(
        body.experiment_id, body.rule, body.kind, body.closed_loop_time, body.read_board
    )
    if format == "md":
        return PlainTextResponse(loop_document.render_markdown(doc))
    return doc.model_dump(mode="json", by_alias=True)


@router.post("/printers/loops/curves")
def firmware_loops_curves(body: LoopDocumentRequest):
    """What a page draws of a kept experiment's loop, computed here: the open loop over
    frequency with each controller, and the measured temperature beside the model's
    step through the same targets."""
    doc = loops.document(
        body.experiment_id, body.rule, body.kind, body.closed_loop_time, body.read_board
    )
    return loop_document.curves(doc)


@router.get("/loops/rules")
async def firmware_loops_rules():
    """The rules a controller is designed by (``control_loops.RULES``): each one's name,
    title, source, what it takes, the kinds of controller it gives, what it assumes and
    its relation; the rule and the kind a document is designed by when none is named;
    and the rules left out, with why."""
    fields = LoopDocumentRequest.model_fields
    return {
        "rules": [
            {
                "name": r.name,
                "title": r.title,
                "source": r.source,
                "takes": r.takes,
                "kinds": list(r.kinds),
                "assumes": r.assumes,
                "relation": r.relation,
            }
            for r in control_loops.RULES.values()
        ],
        "default": {"rule": fields["rule"].default, "kind": fields["kind"].default},
        "left_out": control_loops.LEFT_OUT,
    }


@router.get("/loops/kinds")
async def firmware_loops_kinds():
    """The experiments a loop is run through and what each takes beside its ceiling and
    its longest time (``loops.KINDS``), each figure with a value to start from for a
    hotend and for the bed; the caps the ceiling stands under; the longest time any
    experiment may be given; the sample period when none is said. The ceiling and the
    longest time have no value to start from: the caller states them."""
    return {
        "kinds": [
            {
                "kind": k.name,
                "label": k.label,
                "parameters": [
                    {"name": p.name, "label": p.label, "unit": p.unit, "start": p.start}
                    for p in k.parameters
                ],
            }
            for k in loops.KINDS
        ],
        "caps": {"hotend": gcode.HOTEND_MAX_C, "bed": gcode.BED_MAX_C},
        "max_duration_s": loops.MAX_DURATION_S,
        "sample_period_s": LoopExperimentRequest.model_fields["sample_period_s"].default,
    }


@router.get("/loops/schema")
async def firmware_loops_schema():
    """The JSON Schema of ``control/loop/1``, the published contract."""
    return loop_document.LoopDocument.model_json_schema(by_alias=True)


@router.post("/loops/validate")
async def firmware_loops_validate(doc: loop_document.LoopDocument, format: Literal["json", "md"] = "json"):
    """A loop document read back normalized, or as Markdown; 422 names what is wrong."""
    if format == "md":
        return PlainTextResponse(loop_document.render_markdown(doc))
    return doc.model_dump(mode="json", by_alias=True)


@router.get("/printers/queries")
async def firmware_printer_queries(port: PortOrAll = ""):
    """The report-only G-code the query route accepts, with what each reports: the
    dialect of the board on ``port`` (a router's ``$$``, ``$G``, ``?``), Marlin's for none."""
    return [
        {"command": c, "reports": what} for c, what in devices.query_codes(port or None).items()
    ]


@router.post("/printers/query")
def firmware_printer_query(body: PrinterQueryRequest):
    """Send one allowlisted report code (``M503``, ``M119``, ``M20`` ...) over the held link."""
    _busy_guard(body.port)
    return devices.printer_query(body.port, body.command).model_dump(mode="json")


@router.get("/printers/info")
def firmware_printer_info(port: Port):
    """Everything a board's Machine needs at once: device, held link, last poll."""
    found = devices.detected_devices()
    device = next((d for d in found if d.port == port), None)
    link = gcode.get_printer_links().get(port)
    last = devices.last_statuses().get(port)
    return {
        "port": port,
        "detected": device is not None,
        "device": device_view(device) if device else None,
        "link": link.info() if link else None,
        "engine": gcode.serial_engine(),
        "last_status": last.model_dump(mode="json") if last else None,
        "active_task": (get_task_runner().active or None) and get_task_runner().active.snapshot(),
        "control": _control_state(port),
        "can": can.can_now(port),
    }


@router.get("/printers/log")
async def firmware_printer_log(port: Port, since: int = Query(0, ge=0)):
    """The port's comms log from index ``since`` on (tx/rx/boot/sys entries)."""
    links = gcode.get_printer_links()
    data = links.log_for(port).since(since)
    data["port"] = port
    data["held"] = links.get(port) is not None
    return data


@router.post("/printers/reconnect")
def firmware_printer_reconnect(body: PrinterIdentifyRequest):
    """Release and reopen the link (no reset), then poll."""
    _busy_guard(body.port)
    _no_print(body.port)
    status = devices.printer_reconnect(body.port, body.baud)
    data = status.model_dump(mode="json")
    data["heating"] = status.heating
    return data


@router.post("/printers/reset")
def firmware_printer_reset(body: ProbeRequest):
    """Reboot the board deliberately (DTR pulse); returns its boot banner."""
    _busy_guard(body.port)
    _no_print(body.port)
    return {"port": body.port, "boot_lines": devices.printer_reset(body.port)}


@router.post("/printers/release")
def firmware_printer_release(body: ProbeRequest):
    """Drop the held link so another tool (a slicer, OctoPrint) can open the port."""
    return {"port": body.port, "released": gcode.get_printer_links().close(body.port)}


@router.get("/devices/stream")
async def firmware_stream(
    request: Request, port: Port, baud: int = Query(115200, ge=300, le=2000000)
):
    """Server-sent events: live serial lines until the client leaves or a task takes the port."""
    _busy_guard(port)
    # The module that found the port listens to it: arduino-cli's monitor, or the
    # Rust module's own (pyserial); refused here when nothing can.
    devices.listener_argv(port, baud)
    gcode.get_printer_links().close(port)  # one holder per port (the monitor resets it anyway)

    q: queue.Queue = queue.Queue()
    stop = threading.Event()
    eof = object()

    def reader():
        try:
            for item in devices.stream_lines(port, baud, stop=stop):
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
