"""Devices: what is plugged in, what it is, what should be running, and what it says.

Three views of one board, kept deliberately separate so the GUI can show
where they disagree:

* **Detected** -- ``arduino-cli board list``: the serial port and USB bridge.
* **Probed** -- ``esptool flash_id``: chip model, revision, MAC, flash size.
  Resets the board afterwards, which is what makes the boot banner appear.
* **Expected** -- the ``FlashRecord`` Apothecary wrote when it last uploaded
  to that MAC (or port), compared against the sketch as it is *now*.
* **Observed** -- serial output via ``arduino-cli monitor``; a sketch that
  prints ``apothecary <name>: hello`` at boot identifies itself.
* **Identified** -- for a board running a G-code firmware (a printer
  mainboard), ``M115`` over a held-open link (``gcode.py``): firmware name,
  machine type, capabilities. Cached like a probe; polled for temperatures
  and progress afterwards.

Records live in ``~/.apothecary/firmware-state.json`` (``APOTHECARY_STATE_DIR``
overrides): machine state, not repository state, so it is never committed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional

from ..projects.parts.skeleton import ROOT
from . import gcode
from .models import (
    DeviceInfo,
    ExpectedFirmware,
    FlashRecord,
    LevelingRecord,
    ListenResult,
    ManualBinding,
    PrinterQueryResult,
    PrintFile,
    PrintRecord,
    SketchInfo,
)
from .sketches import find_sketch
from .toolchains import ArduinoCli, Esptool, ToolchainError, get_arduino_cli, get_esptool

BANNER_RE = re.compile(r"apothecary\s+([A-Za-z0-9_.\-]+):\s*hello")
CHIP_LINE_RE = re.compile(r"^chip:\s+(.+)$")
ESP_VENDORS = ("esp32", "esp8266")  # arduino-cli vendor prefixes esptool can talk to


def is_espressif_fqbn(fqbn: str) -> bool:
    return fqbn.split(":", 1)[0] in ESP_VENDORS


# --- persistent state -------------------------------------------------------------


def state_dir() -> Path:
    override = os.environ.get("APOTHECARY_STATE_DIR", "").strip()
    return Path(override).expanduser() if override else Path.home() / ".apothecary"


def state_file() -> Path:
    return state_dir() / "firmware-state.json"


class FirmwareState:
    """Flash records, cached probes and node bindings: one JSON file, read fresh on every use."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or state_file()
        self._lock = threading.Lock()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"flashes": [], "devices": {}, "bindings": []}
        data.setdefault("flashes", [])
        data.setdefault("devices", {})
        data.setdefault("bindings", [])
        return data

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        tmp.replace(self.path)

    def record_flash(self, record: FlashRecord) -> None:
        with self._lock:
            data = self._load()
            data["flashes"].append(record.model_dump(mode="json"))
            data["flashes"] = data["flashes"][-200:]
            self._save(data)

    def flashes(self) -> List[FlashRecord]:
        return [FlashRecord(**f) for f in self._load()["flashes"]]

    def last_flash(self, identity: str, port: Optional[str] = None) -> Optional[FlashRecord]:
        """Newest record for a MAC; falls back to the port for never-probed boards."""
        newest: Optional[FlashRecord] = None
        for rec in self.flashes():
            if rec.identity == identity or (port and rec.mac is None and rec.port == port):
                if newest is None or rec.flashed_at >= newest.flashed_at:
                    newest = rec
        return newest

    def remember_device(self, device: DeviceInfo) -> None:
        with self._lock:
            data = self._load()
            data["devices"][device.port] = device.model_dump(mode="json")
            self._save(data)

    def cached_device(self, port: str) -> Optional[DeviceInfo]:
        raw = self._load()["devices"].get(port)
        return DeviceInfo(**raw) if raw else None

    # -- node bindings: a device the user pinned to a (site, node path) ----------

    def set_binding(self, site: str, path: str, identity: str) -> ManualBinding:
        """Pin ``identity`` to the node; replaces any earlier pin for that node."""
        binding = ManualBinding(
            site=site, path=path, identity=identity, bound_at=datetime.now(timezone.utc)
        )
        with self._lock:
            data = self._load()
            data["bindings"] = [
                b for b in data["bindings"] if not (b["site"] == site and b["path"] == path)
            ]
            data["bindings"].append(binding.model_dump(mode="json"))
            self._save(data)
        return binding

    def clear_binding(self, site: str, path: str) -> bool:
        """Drop the pin for the node; ``False`` if there was none."""
        with self._lock:
            data = self._load()
            before = len(data["bindings"])
            data["bindings"] = [
                b for b in data["bindings"] if not (b["site"] == site and b["path"] == path)
            ]
            if len(data["bindings"]) == before:
                return False
            self._save(data)
            return True

    def bindings(self, site: Optional[str] = None) -> List[ManualBinding]:
        rows = [ManualBinding(**b) for b in self._load()["bindings"]]
        return [b for b in rows if site is None or b.site == site]

    def binding_for(self, site: str, path: str) -> Optional[ManualBinding]:
        return next((b for b in self.bindings(site) if b.path == path), None)


_STATE: Optional[FirmwareState] = None


def get_state() -> FirmwareState:
    global _STATE
    if _STATE is None:
        _STATE = FirmwareState()
    return _STATE


# --- hashes: what was built, what is in the tree ------------------------------------


def source_sha256(sketch: SketchInfo) -> str:
    """Hash of every source file in the sketch folder (not the sidecar)."""
    h = hashlib.sha256()
    for f in sorted(p for p in sketch.path.rglob("*") if p.is_file()):
        if f.name == "firmware.json" or f.suffix in {".bin", ".elf", ".map"}:
            continue
        h.update(str(f.relative_to(sketch.path)).encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def build_binary(sketch: SketchInfo, build_dir: Path) -> Optional[Path]:
    candidate = build_dir / f"{sketch.name}.ino.bin"
    if candidate.is_file():
        return candidate
    hexfile = build_dir / f"{sketch.name}.ino.hex"  # AVR
    return hexfile if hexfile.is_file() else None


def file_sha256(path: Optional[Path]) -> Optional[str]:
    if not path or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_flash_record(
    port: str,
    sketch: Optional[SketchInfo],
    fqbn: Optional[str],
    build_dir: Optional[Path] = None,
    images: Optional[List[str]] = None,
    task_id: Optional[str] = None,
    state: Optional[FirmwareState] = None,
) -> FlashRecord:
    state = state or get_state()
    cached = state.cached_device(port)
    mac = cached.mac if cached else None
    return FlashRecord(
        identity=mac or port,
        port=port,
        mac=mac,
        sketch=sketch.name if sketch else None,
        fqbn=fqbn,
        images=images or [],
        build_sha256=file_sha256(build_binary(sketch, build_dir)) if sketch and build_dir else None,
        source_sha256=source_sha256(sketch) if sketch else None,
        flashed_at=datetime.now(timezone.utc),
        task_id=task_id,
    )


def expected_firmware(
    device: DeviceInfo, build_root: Path, state: Optional[FirmwareState] = None
) -> ExpectedFirmware:
    state = state or get_state()
    record = state.last_flash(device.identity, device.port)
    if record is None:
        return ExpectedFirmware()
    out = ExpectedFirmware(record=record)
    if record.sketch:
        sketch = find_sketch(record.sketch, ROOT)
        if sketch is None:
            out.sketch_missing = True
        else:
            if record.source_sha256 and source_sha256(sketch) != record.source_sha256:
                out.source_changed = True
            current = file_sha256(build_binary(sketch, build_root / sketch.name))
            if current and record.build_sha256 and current != record.build_sha256:
                out.build_changed = True
    return out


# --- detected + probed -------------------------------------------------------------


# ``arduino-cli board list`` takes ~2 s; the viewer's panel, its serial
# overlay and the firmware page each ask for it, often within a second of
# one another. A short-lived cache of the raw scan (cached probes are merged
# afresh each call) turns those into one scan. Long enough to coalesce a
# page's requests, short enough that a replug shows on the next click.
SCAN_TTL = 2.0
_SCAN: Optional[tuple] = None  # (monotonic time, cli, boards)


def scan_ports(cli: Optional[ArduinoCli] = None, fresh: bool = False):
    global _SCAN
    cli = cli or get_arduino_cli()
    now = time.monotonic()
    if not fresh and _SCAN and _SCAN[1] is cli and now - _SCAN[0] < SCAN_TTL:
        return _SCAN[2]
    boards = cli.board_list()
    _SCAN = (now, cli, boards)
    return boards


def detected_devices(
    cli: Optional[ArduinoCli] = None, state: Optional[FirmwareState] = None, fresh: bool = False
) -> List[DeviceInfo]:
    """Every serial port arduino-cli sees, merged with any cached probe for it.

    ``fresh`` bypasses the short scan cache (an explicit rescan button).
    """
    cli = cli or get_arduino_cli()
    state = state or get_state()
    devices: List[DeviceInfo] = []
    for b in scan_ports(cli, fresh):
        info = DeviceInfo(
            port=b.port,
            label=b.label,
            vid=b.vid,
            pid=b.pid,
            board_name=b.board_name,
            fqbn=b.fqbn,
            serial_number=b.serial_number,
        )
        cached = state.cached_device(b.port)
        if cached and (cached.vid, cached.pid) == (b.vid, b.pid):
            info = info.model_copy(
                update={
                    k: getattr(cached, k)
                    for k in (
                        "chip",
                        "revision",
                        "features",
                        "crystal",
                        "mac",
                        "flash_size",
                        "flash_manufacturer",
                        "probed_at",
                        "printer",
                    )
                }
            )
        devices.append(info)
    return devices


def probe_device(
    port: str,
    cli: Optional[ArduinoCli] = None,
    esptool: Optional[Esptool] = None,
    state: Optional[FirmwareState] = None,
) -> DeviceInfo:
    """Identify the chip on ``port`` with esptool and cache the answer.

    A board arduino-cli already matched to a non-Espressif core is returned
    as-is: esptool would only confuse an AVR by talking to it.
    """
    cli = cli or get_arduino_cli()
    esptool = esptool or get_esptool()
    state = state or get_state()
    base = next((d for d in detected_devices(cli, state) if d.port == port), None)
    if base is None:
        raise ToolchainError(f"no board detected on {port}")
    if base.fqbn and not is_espressif_fqbn(base.fqbn):
        return base
    if base.printer is not None:
        return base  # a printer mainboard; esptool would only reset it
    if not esptool.is_available:
        raise ToolchainError(
            "esptool is not available; install the esp32 core to get its bundled copy"
        )
    fields = esptool.probe(port)
    fields.pop("raw", None)
    device = base.model_copy(update={**fields, "probed_at": datetime.now(timezone.utc)})
    state.remember_device(device)
    return device


# --- identified: a G-code firmware ----------------------------------------------------


def identify_printer(
    port: str,
    baud: int = 115200,
    cli: Optional[ArduinoCli] = None,
    state: Optional[FirmwareState] = None,
    links: Optional[gcode.PrinterLinks] = None,
    reset: bool = False,
) -> DeviceInfo:
    """Ask ``M115`` on ``port`` and cache the answer on the device.

    Opens (and keeps) the printer link; the serial overlay's monitor on that
    port is closed first so only one process reads it. ``reset`` reboots the
    board deliberately to capture its boot banner -- never do that mid-print.
    Raises ``ToolchainError`` when nothing G-code answers.
    """
    cli = cli or get_arduino_cli()
    state = state or get_state()
    links = links or gcode.get_printer_links()
    base = next((d for d in detected_devices(cli, state) if d.port == port), None)
    if base is None:
        raise ToolchainError(f"no board detected on {port}")
    get_streams().close(port)
    link = links.open(port, baud)
    try:
        info = gcode.identify_printer(link, reset=reset)
    except ToolchainError:
        links.close(port)
        raise
    device = base.model_copy(update={"printer": info})
    state.remember_device(device)
    return device


# Who wants to know a printer's state after each poll: api.py registers the
# site sync here, so this package never imports the site layer. A listener
# returns the nodes it touched; they ride along on ``PrinterStatus.synced``.
StatusListener = Callable[[gcode.PrinterStatus], List[dict]]
STATUS_LISTENERS: List[StatusListener] = []
_LAST_STATUS: Dict[str, gcode.PrinterStatus] = {}


def last_statuses() -> Dict[str, gcode.PrinterStatus]:
    """The newest poll per port, for views that must not touch the port themselves."""
    return dict(_LAST_STATUS)


def notify_status(status: gcode.PrinterStatus) -> gcode.PrinterStatus:
    _LAST_STATUS[status.port] = status
    for listener in STATUS_LISTENERS:
        status.synced.extend(listener(status) or [])
    return status


def printer_status(
    port: str,
    baud: Optional[int] = None,
    state: Optional[FirmwareState] = None,
    links: Optional[gcode.PrinterLinks] = None,
) -> gcode.PrinterStatus:
    """One poll over the held link; opens it if it is not yet open.

    ``baud`` defaults to what the cached identification used. A port never
    identified is identified first, so a viewer can poll straight away.
    Every poll is handed to ``STATUS_LISTENERS`` (the site sync).
    """
    state = state or get_state()
    links = links or gcode.get_printer_links()
    link = links.get(port)
    if link is None:
        cached = state.cached_device(port)
        rate = baud or (cached.printer.baud if cached and cached.printer else 115200)
        if not (cached and cached.printer):
            identify_printer(port, rate, state=state, links=links)
            link = links.get(port)
        else:
            get_streams().close(port)
            link = links.open(port, rate)
    assert link is not None
    job = _live_job(port, link.job)
    if job is not None and job.get("kind") != "print":
        # A probe holds the firmware for minutes; a poll now would only queue
        # behind it. Say what is happening instead.
        return _last_status_with(port, job)
    try:
        # Between two streamed lines is where a host polls; a line the
        # firmware is slow to answer (heating) is not worth queueing behind.
        status = gcode.poll_printer(link, wait=0.5 if job else None)
    except gcode.LinkBusy:
        return _last_status_with(port, _live_job(port, link.job) or job)
    except ToolchainError as exc:
        links.close(port, force=True)  # a wedged link is worse than a reopen on the next poll
        status = gcode.offline_status(port, str(exc))
    job = _live_job(port, link.job)
    if job is not None and job.get("kind") == "print":
        status.job = job
        if status.state == "idle":
            status.state = "printing"  # the card is idle; the host is not
    return notify_status(status)


def _live_job(port: str, job: Optional[dict]) -> Optional[dict]:
    """The link's announced job, fresh from the print when one is streaming."""
    if job is not None and job.get("kind") == "print":
        running = _PRINTS.get(port)
        if running is not None and running.finished is None:
            return running.snapshot()
    return job


def _last_status_with(port: str, job: dict) -> gcode.PrinterStatus:
    last = _LAST_STATUS.get(port)
    status = (
        last.model_copy(update={"polled_at": datetime.now(timezone.utc), "raw": []})
        if last
        else gcode.PrinterStatus(port=port, polled_at=datetime.now(timezone.utc))
    )
    status.job = dict(job)
    status.synced = []
    if job.get("kind") == "print" and status.state == "idle":
        status.state = "printing"
    return status


def printer_reconnect(
    port: str,
    baud: Optional[int] = None,
    state: Optional[FirmwareState] = None,
    links: Optional[gcode.PrinterLinks] = None,
) -> gcode.PrinterStatus:
    """Drop the held link and open a fresh one (no reset), then poll.

    The remedy for a wedged port or a board that was replugged: the comms
    log is kept across the reopen so the monitor shows the whole story.
    """
    state = state or get_state()
    links = links or gcode.get_printer_links()
    links.close(port)
    return printer_status(port, baud, state=state, links=links)


def printer_reset(
    port: str,
    state: Optional[FirmwareState] = None,
    links: Optional[gcode.PrinterLinks] = None,
) -> List[str]:
    """Reboot the board on purpose (DTR pulse) and return its boot banner.

    Never do this mid-print; the API and pages ask before calling it.
    """
    state = state or get_state()
    links = links or gcode.get_printer_links()
    if links.get(port) is None:
        printer_status(port, state=state, links=links)
    link = links.get(port)
    if link is None:
        raise ToolchainError(f"{port}: no printer link (is it a G-code printer?)")
    if link.job is not None:
        raise ToolchainError(f"{port}: a {link.job.get('kind')} holds the port -- not resetting")
    return link.reset()


def printer_control(
    port: str,
    command: str,
    state: Optional[FirmwareState] = None,
    links: Optional[gcode.PrinterLinks] = None,
) -> PrinterQueryResult:
    """One allowlisted control line, only while the port's latch is armed (M112 always).

    Renews the latch on success. The link is opened (and the port
    identified) on first use like a poll would.
    """
    state = state or get_state()
    links = links or gcode.get_printer_links()
    cmd = gcode.normalise_control(command)  # ValueError when not allowed / out of bounds
    if cmd != gcode.EMERGENCY_STOP and not links.control.armed(port):
        raise gcode.ControlNotArmed(f"{port}: control is not armed -- arm it first")
    held = links.get(port)
    if held is not None and held.job is not None:
        _job_allows(held.job, cmd)
    if links.get(port) is None:
        printer_status(port, state=state, links=links)
    link = links.get(port)
    if link is None:
        raise ToolchainError(f"{port}: no printer link (is it a G-code printer?)")
    if cmd == gcode.EMERGENCY_STOP:
        running = _PRINTS.get(port)
        if running and running.finished is None:
            running.cancel(quiet=True)  # the board halts; nothing more is sent
    lines = gcode.control_printer(link, cmd)
    links.control.renew(port)
    return PrinterQueryResult(
        port=port, command=cmd, lines=lines, queried_at=datetime.now(timezone.utc)
    )


# What a person may still send while a job holds the port. A print keeps the
# heaters, the fan and the break-wait in reach (a hotend a few degrees off is
# fixed mid-print); motion and the SD card are the job's. A probe keeps only
# the stop.
PRINT_ALLOWS = re.compile(r"^(M104|M140|M106|M107|M108)\b")


def _job_allows(job: dict, cmd: str) -> None:
    if cmd == gcode.EMERGENCY_STOP:
        return
    if job.get("kind") == "print" and PRINT_ALLOWS.match(cmd):
        return
    what = "a print" if job.get("kind") == "print" else "a bed reading"
    raise ToolchainError(f"{port_of(job)}: {what} holds the port ({job.get('stage')})")


def port_of(job: dict) -> str:
    return str(job.get("port", "?"))


# --- bed leveling: a job that holds the port for minutes, and its records ---------------

LEVELING_PROBE_TIMEOUT_S = 900.0  # a five-by-five probe on a slow bed


def leveling_dir() -> Path:
    return state_dir() / "leveling"


def leveling_records(port: Optional[str] = None) -> List[LevelingRecord]:
    """Every saved reading, newest first; for one port when given."""
    folder = leveling_dir()
    if not folder.is_dir():
        return []
    records: List[LevelingRecord] = []
    for path in folder.glob("*.json"):
        try:
            rec = LevelingRecord(**json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
        if port is None or rec.port == port:
            records.append(rec)
    return sorted(records, key=lambda r: r.at, reverse=True)


def leveling_record(record_id: str) -> Optional[LevelingRecord]:
    return next((r for r in leveling_records() if r.id == record_id), None)


def _save_leveling(record: LevelingRecord) -> Path:
    folder = leveling_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{record.id}.json"
    path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    return path


def read_bed(link: gcode.GcodeLink, port: str, method: str, note: Optional[str]) -> LevelingRecord:
    """The reading itself: mesh, state, probe offset and temperatures, from an open link."""
    lines: List[str] = []
    mesh_lines = link.command("M420 V", timeout=15.0, origin="query")
    lines += mesh_lines
    offset_lines = link.command("M851", timeout=10.0, origin="query")
    lines += offset_lines
    temp_lines = link.command("M105", timeout=10.0, origin="query")
    lines += temp_lines
    grids = gcode.parse_meshes(mesh_lines)
    temps = gcode.parse_m105(next((ln for ln in temp_lines if gcode.is_temperature_line(ln)), ""))
    cached = get_state().cached_device(port)
    at = datetime.now(timezone.utc)
    slug = re.sub(r"[^A-Za-z0-9]+", "_", port).strip("_")
    record = LevelingRecord(
        id=f"{at:%Y%m%dT%H%M%S}.{at.microsecond // 1000:03d}-{slug}",
        port=port,
        at=at,
        method=method,
        mesh=grids[0] if grids else [],
        subdivided=grids[1] if len(grids) > 1 else None,
        stats=gcode.mesh_stats(grids[0]) if grids else {},
        leveling_on=gcode.parse_leveling_state(mesh_lines),
        probe_offset=gcode.parse_probe_offset(offset_lines),
        hotend_c=temps["hotends"][0].actual if temps["hotends"] else None,
        bed_c=temps["bed"].actual if temps["bed"] else None,
        firmware=cached.printer.firmware_name if cached and cached.printer else None,
        note=note,
        lines=lines[-400:],
    )
    return record


class LevelingJob:
    """Home, probe, read, save -- on a thread, announcing its stage on the link."""

    def __init__(self, port: str, probe: bool, note: Optional[str], links: gcode.PrinterLinks):
        self.port, self.probe, self.note, self.links = port, probe, note, links
        self.stage = "starting"
        self.started = datetime.now(timezone.utc)
        self.finished: Optional[datetime] = None
        self.error: Optional[str] = None
        self.record: Optional[LevelingRecord] = None
        self.thread = threading.Thread(target=self._run, daemon=True, name=f"leveling-{port}")

    def snapshot(self) -> dict:
        return {
            "kind": "leveling",
            "port": self.port,
            "probe": self.probe,
            "stage": self.stage,
            "since": self.started.isoformat(),
            "finished": self.finished.isoformat() if self.finished else None,
            "error": self.error,
            "record_id": self.record.id if self.record else None,
            "running": self.finished is None,
        }

    def _run(self) -> None:
        link = self.links.get(self.port)
        if link is None:
            self.error, self.finished = "no link", datetime.now(timezone.utc)
            return
        link.job = self.snapshot()
        try:
            if self.probe:
                self.stage = "homing"
                link.job = self.snapshot()
                link.command("G28", timeout=120.0, origin="control")
                self.stage = "probing"
                link.job = self.snapshot()
                link.command("G29", timeout=LEVELING_PROBE_TIMEOUT_S, origin="control")
            self.stage = "reading"
            link.job = self.snapshot()
            self.record = read_bed(link, self.port, "probe" if self.probe else "read", self.note)
            _save_leveling(self.record)
            link.log.add("sys", f"bed reading saved: {self.record.id}", "control")
            self.stage = "saved"
        except (ToolchainError, ValueError) as exc:
            self.error = str(exc)
            self.stage = "failed"
            link.log.add("sys", f"bed reading failed: {exc}", "control")
        finally:
            self.finished = datetime.now(timezone.utc)
            link.job = None


_LEVELING: Dict[str, LevelingJob] = {}


def leveling_job(port: str) -> Optional[LevelingJob]:
    return _LEVELING.get(port)


def start_leveling(
    port: str,
    probe: bool = True,
    note: Optional[str] = None,
    state: Optional[FirmwareState] = None,
    links: Optional[gcode.PrinterLinks] = None,
) -> LevelingJob:
    """Begin a bed reading on ``port``; a probe needs the control latch armed.

    Raises ``ControlNotArmed`` for a probe with the latch down, ``ToolchainError``
    when the port is not a printer or a job already holds it.
    """
    state = state or get_state()
    links = links or gcode.get_printer_links()
    running = _LEVELING.get(port)
    if running and running.finished is None:
        raise ToolchainError(f"{port}: a bed reading is already {running.stage}")
    printing = _PRINTS.get(port)
    if printing and printing.finished is None:
        raise ToolchainError(f"{port}: a print holds the port ({printing.stage})")
    if probe and not links.control.armed(port):
        raise gcode.ControlNotArmed(f"{port}: probing moves the machine -- arm control first")
    if links.get(port) is None:
        printer_status(port, state=state, links=links)
    if links.get(port) is None:
        raise ToolchainError(f"{port}: no printer link (is it a G-code printer?)")
    job = LevelingJob(port, probe, note, links)
    _LEVELING[port] = job
    job.thread.start()
    return job


# --- host printing: a file streamed over the held link, one line per ok --------------


def prints_dir() -> Path:
    return state_dir() / "prints"


def _print_meta_path(file_id: str) -> Path:
    return prints_dir() / f"{file_id}.json"


def _print_file_path(file_id: str) -> Path:
    return prints_dir() / f"{file_id}.gcode"


def save_print_file(name: str, data: bytes) -> PrintFile:
    """Keep an uploaded file and say what it holds; ``problems`` says why it may not be sent."""
    text = data.decode("utf-8", "replace")
    total, problems = gcode.check_gcode(text)
    at = datetime.now(timezone.utc)
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(name).name).strip("_.") or "print"
    stem = re.sub(r"\.(gcode|gco|g|txt)$", "", stem, flags=re.IGNORECASE)[:60]
    file_id = f"{at:%Y%m%dT%H%M%S}.{at.microsecond // 1000:03d}-{stem}"
    folder = prints_dir()
    folder.mkdir(parents=True, exist_ok=True)
    _print_file_path(file_id).write_text(text, encoding="utf-8")
    meta = PrintFile(
        id=file_id,
        name=Path(name).name[:120] or file_id,
        size=len(data),
        lines=total,
        uploaded_at=at,
        problems=problems,
    )
    _print_meta_path(file_id).write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    return meta


def print_files() -> List[PrintFile]:
    """Every kept file, newest first."""
    folder = prints_dir()
    if not folder.is_dir():
        return []
    files: List[PrintFile] = []
    for path in folder.glob("*.json"):
        try:
            meta = PrintFile(**json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
        if _print_file_path(meta.id).is_file():
            files.append(meta)
    return sorted(files, key=lambda f: f.uploaded_at, reverse=True)


def print_file(file_id: str) -> Optional[PrintFile]:
    path = _print_meta_path(file_id)
    if not path.is_file() or not _print_file_path(file_id).is_file():
        return None
    try:
        return PrintFile(**json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def delete_print_file(file_id: str) -> bool:
    """Forget a kept file; refused while a print streams it."""
    for job in _PRINTS.values():
        if job.file.id == file_id and job.finished is None:
            raise ToolchainError(f"{file_id}: a print is streaming it")
    found = False
    for path in (_print_meta_path(file_id), _print_file_path(file_id)):
        if path.is_file():
            path.unlink()
            found = True
    return found


def print_records_dir() -> Path:
    return prints_dir() / "records"


def print_records(port: Optional[str] = None) -> List[PrintRecord]:
    """Every print streamed from here, newest first; for one port when given."""
    folder = print_records_dir()
    if not folder.is_dir():
        return []
    records: List[PrintRecord] = []
    for path in folder.glob("*.json"):
        try:
            rec = PrintRecord(**json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
        if port is None or rec.port == port:
            records.append(rec)
    return sorted(records, key=lambda r: r.at, reverse=True)


def print_record(record_id: str) -> Optional[PrintRecord]:
    return next((r for r in print_records() if r.id == record_id), None)


def _save_print_record(record: PrintRecord) -> Path:
    folder = print_records_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{record.id}.json"
    path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    return path


# What is sent when a print stops short, in this order, each on its own and
# none of them fatal: the heaters off, the fan off, the motors free. No move
# -- a nozzle parked blind is worse than one left where it stopped.
PRINT_SAFE_OFF = ("M104 S0", "M140 S0", "M107", "M84")
PRINT_PROGRESS_EVERY = 20  # lines between announcements on the link
PRINT_LOG_EVERY = 500  # lines between progress notes in the comms log


class PrintJob:
    """Stream a kept file over the link, one line per ``ok``, on a thread.

    ``ok`` is the flow control: the firmware answers it when it has queued
    the line, so its planner stays fed and the host never runs ahead of it.
    Pausing stops the feed (the firmware finishes what it has queued);
    cancelling stops it and sends ``PRINT_SAFE_OFF``. Between two lines
    the link is free, which is where polls and a temperature change go.
    """

    def __init__(self, port: str, file: PrintFile, links: gcode.PrinterLinks):
        self.port, self.file, self.links = port, file, links
        self.stage = "starting"
        self.sent = 0
        self.total = file.lines
        self.current: Optional[str] = None
        self.started = datetime.now(timezone.utc)
        self.finished: Optional[datetime] = None
        self.error: Optional[str] = None
        self.record: Optional[PrintRecord] = None
        self._go = threading.Event()
        self._go.set()
        self._stop = threading.Event()
        self._quiet = False
        self.thread = threading.Thread(target=self._run, daemon=True, name=f"print-{port}")

    def snapshot(self) -> dict:
        elapsed = ((self.finished or datetime.now(timezone.utc)) - self.started).total_seconds()
        return {
            "kind": "print",
            "port": self.port,
            "file_id": self.file.id,
            "name": self.file.name,
            "stage": self.stage,
            "sent": self.sent,
            "total": self.total,
            "progress": (self.sent / self.total) if self.total else 0.0,
            "current": self.current,
            "since": self.started.isoformat(),
            "finished": self.finished.isoformat() if self.finished else None,
            "elapsed_s": round(elapsed, 1),
            "error": self.error,
            "record_id": self.record.id if self.record else None,
            "running": self.finished is None,
        }

    def pause(self) -> None:
        if self.finished is None and self.stage == "printing":
            self._go.clear()
            self.stage = "paused"
            self._announce()

    def resume(self) -> None:
        if self.finished is None and self.stage == "paused":
            self.stage = "printing"
            self._go.set()
            self._announce()

    def cancel(self, quiet: bool = False) -> None:
        """Stop feeding; ``quiet`` skips the safe-off (the board is already halted)."""
        if self.finished is None:
            self._quiet = quiet
            self.stage = "cancelling"
            self._stop.set()
            self._go.set()  # a paused print must wake to notice
            self._announce()

    def _announce(self) -> None:
        link = self.links.get(self.port)
        if link is not None and (self.finished is None):
            link.job = self.snapshot()

    def _run(self) -> None:
        link = self.links.get(self.port)
        if link is None:
            self.error, self.finished = "no link", datetime.now(timezone.utc)
            return
        tail: List[str] = []
        outcome = "done"
        try:
            text = _print_file_path(self.file.id).read_text(encoding="utf-8")
            link.log.add("sys", f"print started: {self.file.name} ({self.total} lines)", "print")
            self.stage = "printing"
            self._announce()
            for raw in text.splitlines():
                cmd = gcode.strip_gcode(raw)
                if not cmd:
                    continue
                while not self._go.wait(0.2):
                    if self._stop.is_set():
                        break
                if self._stop.is_set():
                    outcome = "cancelled"
                    break
                self.current = cmd
                lines = link.command(
                    cmd, timeout=gcode.line_timeout(cmd), origin="print", quiet=True
                )
                tail = (tail + [f"> {cmd}", *lines])[-200:]
                self.sent += 1
                if self.sent % PRINT_PROGRESS_EVERY == 0 or self.sent == self.total:
                    self._announce()
                if self.sent % PRINT_LOG_EVERY == 0:
                    link.log.add("sys", f"print: {self.sent}/{self.total} lines sent", "print")
                time.sleep(0.001)  # let a poll take the lock between lines
            else:
                self.stage = "done"
            if outcome == "cancelled":
                self.stage = "cancelled"
        except (ToolchainError, ValueError, OSError) as exc:
            outcome = "failed"
            self.error = str(exc)
            self.stage = "failed"
        if outcome != "done" and not self._quiet:
            for cmd in PRINT_SAFE_OFF:
                try:
                    tail = (tail + link.command(cmd, timeout=10.0, origin="print"))[-200:]
                except ToolchainError as exc:  # a halted or vanished board: nothing more to do
                    tail.append(f"({cmd} not answered: {exc})")
                    break
        ended = datetime.now(timezone.utc)
        cached = get_state().cached_device(self.port)
        self.record = PrintRecord(
            id=f"{self.started:%Y%m%dT%H%M%S}.{self.started.microsecond // 1000:03d}-"
            + re.sub(r"[^A-Za-z0-9]+", "_", self.port).strip("_"),
            port=self.port,
            file_id=self.file.id,
            name=self.file.name,
            at=self.started,
            finished=ended,
            outcome=outcome,
            sent=self.sent,
            total=self.total,
            error=self.error,
            firmware=cached.printer.firmware_name if cached and cached.printer else None,
            lines=tail,
        )
        _save_print_record(self.record)
        link.log.add(
            "sys",
            f"print {outcome}: {self.file.name}, {self.sent}/{self.total} lines"
            + (f" -- {self.error}" if self.error else ""),
            "print",
        )
        link.job = None
        self.finished = ended  # last: a snapshot that says "not running" names the record


_PRINTS: Dict[str, PrintJob] = {}


def print_job(port: str) -> Optional[PrintJob]:
    return _PRINTS.get(port)


def start_print(
    port: str,
    file_id: str,
    state: Optional[FirmwareState] = None,
    links: Optional[gcode.PrinterLinks] = None,
) -> PrintJob:
    """Begin streaming a kept file to ``port``; needs the control latch armed.

    Raises ``ControlNotArmed`` with the latch down, ``ToolchainError`` when
    the file is unknown or refused, the port is not a printer, or a job
    (a print, a bed reading) already holds it.
    """
    state = state or get_state()
    links = links or gcode.get_printer_links()
    file = print_file(file_id)
    if file is None:
        raise ToolchainError(f"no such print file: {file_id}")
    if file.problems:
        raise ToolchainError(f"{file.name} may not be sent: " + "; ".join(file.problems[:3]))
    if file.lines == 0:
        raise ToolchainError(f"{file.name} has nothing to send")
    if not links.control.armed(port):
        raise gcode.ControlNotArmed(
            f"{port}: a print heats and moves the machine -- arm control first"
        )
    for running in (_PRINTS.get(port), _LEVELING.get(port)):
        if running and running.finished is None:
            what = "print" if isinstance(running, PrintJob) else "bed reading"
            raise ToolchainError(f"{port}: a {what} already holds the port ({running.stage})")
    if links.get(port) is None:
        printer_status(port, state=state, links=links)
    link = links.get(port)
    if link is None:
        raise ToolchainError(f"{port}: no printer link (is it a G-code printer?)")
    last = _LAST_STATUS.get(port)
    if last is not None and last.sd_printing:
        raise ToolchainError(f"{port}: the card is printing -- pause or abort that first")
    job = PrintJob(port, file, links)
    _PRINTS[port] = job
    link.job = job.snapshot()
    job.thread.start()
    return job


def printer_query(
    port: str,
    command: str,
    state: Optional[FirmwareState] = None,
    links: Optional[gcode.PrinterLinks] = None,
) -> PrinterQueryResult:
    """One allowlisted report code over the held link (opened and identified on first use)."""
    state = state or get_state()
    links = links or gcode.get_printer_links()
    cmd = gcode.normalise_query(command)  # ValueError for anything that is not a report
    held = links.get(port)
    if held is not None and held.job is not None and held.job.get("kind") != "print":
        raise ToolchainError(f"{port}: a bed reading holds the port ({held.job['stage']})")
    if links.get(port) is None:
        printer_status(port, state=state, links=links)  # identifies + opens; offline if it cannot
    link = links.get(port)
    if link is None:
        raise ToolchainError(f"{port}: no printer link (is it a G-code printer?)")
    lines = gcode.query_printer(link, cmd)
    return PrinterQueryResult(
        port=port, command=cmd, lines=lines, queried_at=datetime.now(timezone.utc)
    )


# --- observed: serial -------------------------------------------------------------


class SerialStreams:
    """Open ``arduino-cli monitor`` processes, one per port, stoppable as a group.

    Uploads and probes need the port; ``stop_all()`` is called before any
    task starts so a live overlay never blocks a flash -- the overlay
    reconnects when the task ends.
    """

    def __init__(self):
        self._procs: Dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()

    def open(self, port: str, baud: int, cli: Optional[ArduinoCli] = None) -> subprocess.Popen:
        cli = cli or get_arduino_cli()
        with self._lock:
            self._kill(port)
            proc = subprocess.Popen(
                cli.monitor_argv(port, baud),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",  # ROM bootloaders chatter at other baud rates: garbage, not fatal
                bufsize=1,
            )
            self._procs[port] = proc
            return proc

    def close(self, port: str) -> None:
        with self._lock:
            self._kill(port)

    def stop_all(self) -> None:
        with self._lock:
            for port in list(self._procs):
                self._kill(port)

    def _kill(self, port: str) -> None:
        proc = self._procs.pop(port, None)
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

    @property
    def open_ports(self) -> List[str]:
        with self._lock:
            return [p for p, proc in self._procs.items() if proc.poll() is None]


_STREAMS: Optional[SerialStreams] = None


def get_streams() -> SerialStreams:
    global _STREAMS
    if _STREAMS is None:
        _STREAMS = SerialStreams()
    return _STREAMS


def classify_lines(lines: List[str]) -> dict:
    running = None
    chip_line = None
    for line in lines:
        m = BANNER_RE.search(line)
        if m:
            running = m.group(1)
        m = CHIP_LINE_RE.match(line.strip())
        if m:
            chip_line = m.group(1).strip()
    return {"running_sketch": running, "chip_line": chip_line}


def listen(
    port: str,
    seconds: float = 3.0,
    baud: int = 115200,
    cli: Optional[ArduinoCli] = None,
    streams: Optional[SerialStreams] = None,
) -> ListenResult:
    """Capture ``seconds`` of serial output and say which sketch announced itself."""
    streams = streams or get_streams()
    # The window is counted from the first line received, not from process
    # start: arduino-cli spends a second or two on port discovery first.
    stop = threading.Event()
    lines: List[str] = []
    started = time.time()
    first_line_at: Optional[float] = None
    for item in stream_lines(port, baud, cli, streams, keepalive=0.5, stop=stop):
        now = time.time()
        if item is not None:
            lines.append(item)
            if not item.startswith("[apothecary:"):
                first_line_at = first_line_at or now
        origin = first_line_at or started
        if now - origin >= seconds or now - started >= seconds + 5:
            stop.set()
    tail = [ln for ln in lines if ln.strip()][-200:]
    return ListenResult(port=port, baud=baud, seconds=seconds, lines=tail, **classify_lines(tail))


REPLAY_MARKER = "[apothecary: serial replay detected -- reopening port]"


def _pump(fd: int, port: str):
    """Read ``fd`` in 4 KB chunks on a thread and hand them over a queue.

    ``select()`` only works on sockets on Windows, so the portable way to wait
    on a pipe with a timeout is a blocking reader thread; it ends when the
    monitor process closes its end (EOF or error puts ``b""`` on the queue).
    """
    import queue

    q: "queue.Queue[bytes]" = queue.Queue()

    def reader():
        try:
            while True:
                raw = os.read(fd, 4096)
                q.put(raw)
                if not raw:
                    return
        except OSError:
            q.put(b"")

    threading.Thread(target=reader, daemon=True, name=f"serial-pump-{port}").start()
    return q


def stream_lines(
    port: str,
    baud: int = 115200,
    cli: Optional[ArduinoCli] = None,
    streams: Optional[SerialStreams] = None,
    keepalive: float = 5.0,
    stop: Optional[threading.Event] = None,
    max_reopens: int = 3,
) -> Iterator[Optional[str]]:
    """Yield serial lines until ``stop`` is set or the monitor exits (a task took the port).

    Yields ``None`` after ``keepalive`` seconds of silence so an SSE writer can
    send a comment and notice a vanished client even when the board is quiet.

    Replay guard: some USB-UART bridges (seen on a CP2102 under a realtime
    kernel) occasionally hand back bytes they already delivered -- a few
    lines, or the same buffer thousands of times a second, with bytes lost in
    between. Genuine output cannot outrun the wire, so a token bucket refilled
    at the baud rate arbitrates: a chunk that overdraws the bucket is a
    replay and is dropped; a run of them means the port is wedged and the
    monitor is reopened (which clears it), with a marker line so the reader
    knows what happened. Real bursts fit comfortably -- the bucket holds the
    bridge's whole buffer several times over.
    """
    import queue

    streams = streams or get_streams()
    wire_rate = baud / 10.0  # bytes/s: 8 data bits + start + stop
    bucket_cap = (
        1024.0  # about twice a CP210x buffer; refills at wire rate, so legit output never waits
    )
    reopens = 0
    while True:
        proc = streams.open(port, baud, cli)
        assert proc.stdout is not None
        chunks = _pump(proc.stdout.fileno(), port)
        buf = ""
        quiet_since = time.time()
        tokens, refilled_at = bucket_cap, time.time()
        dropped_since, dropped = time.time(), 0
        recent = b""  # last few KB delivered, for spotting small verbatim replays
        replay = False
        try:
            while proc.poll() is None and not (stop and stop.is_set()):
                try:
                    raw = chunks.get(timeout=0.5)
                except queue.Empty:
                    if time.time() - quiet_since >= keepalive:
                        quiet_since = time.time()
                        yield None
                    continue
                if not raw:
                    break
                now = time.time()
                elapsed = now - refilled_at
                tokens = min(bucket_cap, tokens + elapsed * wire_rate)
                refilled_at = now
                # A small replay fits the bucket, but it is a verbatim repeat of
                # bytes just delivered, arriving in less time than the wire needs
                # to carry it. A sketch genuinely repeating itself at full wire
                # speed would take at least len(raw)/wire_rate seconds to do so.
                verbatim = len(raw) >= 8 and raw in recent and elapsed * wire_rate < len(raw) * 0.5
                recent = (recent + raw)[-4096:]
                if verbatim or len(raw) > tokens:
                    # Replayed bytes. Drop them; a run of drops means the port is wedged.
                    if now - dropped_since > 2.0:
                        dropped_since, dropped = now, 0
                    dropped += 1
                    if dropped >= 3:
                        replay = True
                        break
                    continue
                tokens -= len(raw)
                quiet_since = now
                buf += raw.decode("utf-8", "replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    yield line.rstrip("\r")
        finally:
            if streams._procs.get(port) is proc:
                streams.close(port)
        if not replay or (stop and stop.is_set()):
            return
        reopens += 1
        yield REPLAY_MARKER
        if reopens > max_reopens:
            yield "[apothecary: giving up -- replug the board or check the USB-UART bridge]"
            return
        time.sleep(0.5)
