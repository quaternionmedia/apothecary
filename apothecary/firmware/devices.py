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
from typing import Dict, Iterator, List, Optional

from ..projects.parts.skeleton import ROOT
from .models import DeviceInfo, ExpectedFirmware, FlashRecord, ListenResult, SketchInfo
from .sketches import find_sketch
from .toolchains import ArduinoCli, Esptool, ToolchainError, get_arduino_cli, get_esptool

BANNER_RE = re.compile(r"apothecary\s+([A-Za-z0-9_.\-]+):\s*hello")
CHIP_LINE_RE = re.compile(r"^chip:\s+(.+)$")
ESP_VENDOR = "esp32"


# --- persistent state -------------------------------------------------------------


def state_dir() -> Path:
    override = os.environ.get("APOTHECARY_STATE_DIR", "").strip()
    return Path(override).expanduser() if override else Path.home() / ".apothecary"


def state_file() -> Path:
    return state_dir() / "firmware-state.json"


class FirmwareState:
    """Flash records and cached probes, one JSON file, read fresh on every use."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or state_file()
        self._lock = threading.Lock()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"flashes": [], "devices": {}}
        data.setdefault("flashes", [])
        data.setdefault("devices", {})
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


def detected_devices(
    cli: Optional[ArduinoCli] = None, state: Optional[FirmwareState] = None
) -> List[DeviceInfo]:
    """Every serial port arduino-cli sees, merged with any cached probe for it."""
    cli = cli or get_arduino_cli()
    state = state or get_state()
    devices: List[DeviceInfo] = []
    for b in cli.board_list():
        info = DeviceInfo(
            port=b.port, label=b.label, vid=b.vid, pid=b.pid, board_name=b.board_name, fqbn=b.fqbn
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
    if base.fqbn and not base.fqbn.startswith(ESP_VENDOR + ":"):
        return base
    if not esptool.is_available:
        raise ToolchainError(
            "esptool is not available; install the esp32 core to get its bundled copy"
        )
    fields = esptool.probe(port)
    fields.pop("raw", None)
    device = base.model_copy(update={**fields, "probed_at": datetime.now(timezone.utc)})
    state.remember_device(device)
    return device


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
    import select

    streams = streams or get_streams()
    wire_rate = baud / 10.0  # bytes/s: 8 data bits + start + stop
    bucket_cap = (
        1024.0  # about twice a CP210x buffer; refills at wire rate, so legit output never waits
    )
    reopens = 0
    while True:
        proc = streams.open(port, baud, cli)
        assert proc.stdout is not None
        fd = proc.stdout.fileno()
        buf = ""
        quiet_since = time.time()
        tokens, refilled_at = bucket_cap, time.time()
        dropped_since, dropped = time.time(), 0
        recent = b""  # last few KB delivered, for spotting small verbatim replays
        replay = False
        try:
            while proc.poll() is None and not (stop and stop.is_set()):
                ready, _, _ = select.select([fd], [], [], 0.5)
                if not ready:
                    if time.time() - quiet_since >= keepalive:
                        quiet_since = time.time()
                        yield None
                    continue
                raw = os.read(fd, 4096)
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
