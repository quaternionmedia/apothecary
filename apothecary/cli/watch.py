"""``apothecary watch``: a running server watched while a person drives its page, one line
per thing that changed.

Two sources. The server's output, when ``--log`` names the file it is written to, with the
page's polling taken out: every request that is not a GET, every 4xx and 5xx, every line
that is not an access line (a traceback folded to one line, a warning, a restart). And the
server's state, read every few seconds over HTTP and compared with the read before: slices
kept, cuts, a printer's tuning turns and what they applied, jobs, and each board's serial
log (its state, its temperature targets, the commands sent by hand and every error).

It only reads. Each board is read from its serial log and the armed list, never through a
status call, which would poll the board itself on top of what the page already sends it.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import click

from .server import port_option

Event = Tuple[str, str]
Getter = Callable[..., object]

# The page's polling, and its other reads: the state's diff says what they changed.
QUIET_GET = re.compile(r'"GET ')
# What a page posts to draw itself: the world's meshes, its menus, its layout, the tour.
QUIET_POST = re.compile(
    r'"POST (/parts/[^ ]*/(validate|draft/check)|/parts/[^ ]*/stl/generate|/menu/resolve'
    r"|/sites/[^ ]*/layout|/tour/)"
)
# Lines a served log carries at every start and while a family member is away, which say
# nothing about what a person did.
KNOWN_NOISE = (
    "Duplicate Operation ID",
    "warnings.warn(message",
    "carlos answered None",
    "carlos did not answer",
)
SERVER_LINES = ("Started server", "Shutting down", "Finished server")
# The ports the test suite's simulated boards are given: a job on one was written by a test
# run, not at the bench.
TEST_PORT = re.compile(r"/dev/tty(POLL|FAKE)")
# The settings a slice line names, where its record has them.
TUNED = (
    "xy_contour_compensation",
    "xy_hole_compensation",
    "elefant_foot_compensation",
    "filament_shrink",
    "filament_shrinkage_compensation_z",
    "z_offset",
    "filament profile",
    "process profile",
    "nozzle_temperature",
    "hot_plate_temp",
    "filament_flow_ratio",
    "pressure_advance",
    "retraction_length",
)
BAD_SERIAL = re.compile(
    r"error|Error|!!|Unknown command|halted|kill|THERMAL|MINTEMP|MAXTEMP|ALARM|busy:"
)
STREAMED = ("print", "stream", "job", "cut")
JOB_LIMIT = 30


def http_getter(base: str, timeout: float = 8.0) -> Getter:
    """A read of ``base``'s JSON: the answer, or the exception that stopped it."""

    def get(path: str, **query):
        url = base + path + ("?" + urllib.parse.urlencode(query) if query else "")
        try:
            with urllib.request.urlopen(url, timeout=timeout) as answer:
                return json.load(answer)
        except Exception as exc:  # a restart, a board gone: the caller says it once
            return exc

    return get


def serial_ports(by_id: Path = Path("/dev/serial/by-id")) -> Dict[str, str]:
    """Each serial device this machine names by id: its device path and that name."""
    if not by_id.is_dir():
        return {}
    return {str(p.resolve()): p.name for p in by_id.iterdir()}


# ---- the server's output ------------------------------------------------------------------


def fold(lines: List[str]) -> str:
    """A traceback in one line: its last frame in apothecary's own code, and the error."""
    frames = [
        line.strip()
        for line in lines
        if line.strip().startswith('File "')
        and "/apothecary/" in line
        and "site-packages" not in line
    ]
    last = lines[-1].strip() if lines else ""
    where = frames[-1].split("apothecary/", 1)[-1] if frames else "?"
    return f"traceback at {where}: {last[:300]}"


class LogReader:
    """The server's output read a line at a time; ``feed`` and ``idle`` say what to show."""

    def __init__(self) -> None:
        self.held: List[str] = []

    def idle(self) -> List[Event]:
        """Nothing more came: a traceback being held is whole."""
        if not self.held:
            return []
        out = [("error", fold(self.held))]
        self.held = []
        return out

    def feed(self, line: str) -> List[Event]:
        line = line.rstrip()
        out: List[Event] = []
        if self.held and line.startswith("INFO:"):
            out += self.idle()
        if line.startswith(("ERROR:", "Traceback")) or (self.held and not line.startswith("INFO:")):
            if not any(n in line for n in KNOWN_NOISE):
                self.held.append(line)
            return out
        if not line or any(n in line for n in KNOWN_NOISE):
            return out
        if line.startswith("INFO:") and '" ' in line and "HTTP/1.1" in line:
            status = line.rsplit('" ', 1)[-1]
            code = int(status.split()[0]) if status[:1].isdigit() else 0
            request = line.split(" - ", 1)[-1]
            if code >= 400:
                if "/favicon" not in line:
                    out.append(("http", request))
            elif not (QUIET_GET.search(line) or QUIET_POST.search(line)):
                out.append(("http", request))
        elif line.startswith("INFO:"):
            if any(w in line for w in SERVER_LINES):
                out.append(("server", line[5:].strip()))
        else:
            out.append(("log", line[:400]))
        return out


def follow(
    path: Path, emit: Callable[[str, str], None], stop: threading.Event, pause: float = 0.3
) -> None:
    """Read what is written to ``path`` from now on, through a rotation or a truncation."""
    reader = LogReader()
    handle, inode = None, None
    quiet_since = time.monotonic()
    while not stop.is_set():
        try:
            st = path.stat()
            if handle is None or st.st_ino != inode or handle.tell() > st.st_size:
                if handle is not None:
                    handle.close()
                    emit("server", f"{path.name} reopened (rotated or truncated)")
                handle = path.open("r", errors="replace")
                inode = st.st_ino
                handle.seek(0, os.SEEK_END)
        except FileNotFoundError:
            stop.wait(1.0)
            continue
        line = handle.readline()
        if not line:
            if time.monotonic() - quiet_since > 1.0:
                for kind, text in reader.idle():
                    emit(kind, text)
            stop.wait(pause)
            continue
        quiet_since = time.monotonic()
        for kind, text in reader.feed(line):
            emit(kind, text)
    if handle is not None:
        handle.close()


# ---- the server's state -------------------------------------------------------------------


def slice_line(record: dict) -> str:
    """A slice in one line: what was made, for which printer, its plan and its tuned settings."""
    named = {s["name"]: s for s in record.get("settings", [])}
    tuned = []
    for key in TUNED:
        setting = named.get(key)
        if setting is not None:
            value = setting["value"]
            value = value[0] if isinstance(value, list) and len(value) == 1 else value
            tuned.append(f"{key}={value}({setting.get('origin')})")
    plan = record.get("plan")
    features = [f["name"] for f in plan.get("features", [])] if plan else "box"
    estimate = record.get("estimate") or {}
    return (
        f"{record.get('file_id')} made={(record.get('made') or {}).get('name')} "
        f"for={(record.get('printer') or {}).get('path')} size={record.get('size')} "
        f"plan={features} est={ {k: estimate[k] for k in list(estimate)[:3]} } "
        f"problems={record.get('problems') or []} messages={len(record.get('messages') or [])}"
        + (" | " + " ".join(tuned) if tuned else "")
    )


class StateWatch:
    """The server's state read once per ``step``; each step says what changed since the last.

    The first step learns what is there and says only the boards it found."""

    def __init__(
        self,
        get: Getter,
        site: Optional[str] = None,
        printer: Optional[str] = None,
        ports: Callable[[], Dict[str, str]] = serial_ports,
    ) -> None:
        self.get, self.site, self.printer, self.ports = get, site, printer, ports
        self.slices: Optional[set] = None
        self.cuts: Optional[set] = None
        self.turns: Dict[str, int] = {}
        self.applied: Dict[str, dict] = {}
        self.jobs: Optional[Dict[str, tuple]] = None
        self.boards: Dict[str, dict] = {}
        self.log_next: Dict[str, object] = {}
        self.down = False

    def step(self) -> List[Event]:
        out: List[Event] = []
        slices = self.get("/slicer/slices")
        if isinstance(slices, Exception):
            if not self.down:
                out.append(("server", f"not answering: {slices}"))
            self.down = True
            return out
        if self.down:
            out.append(("server", "answering again"))
            self.down = False
        out += self._slices(slices)
        out += self._cuts()
        out += self._tuning()
        out += self._jobs()
        out += self._boards()
        return out

    def _slices(self, slices) -> List[Event]:
        out: List[Event] = []
        ids = {r["file_id"]: r for r in slices if isinstance(r, dict) and "file_id" in r}
        if self.slices is not None:
            for fid in sorted(ids.keys() - self.slices):
                full = self.get(f"/slicer/slices/{urllib.parse.quote(fid)}")
                out.append(("slice", slice_line(full if isinstance(full, dict) else ids[fid])))
        self.slices = set(ids)
        return out

    def _cuts(self) -> List[Event]:
        cuts = self.get("/cam/cuts")
        if not isinstance(cuts, list):
            return []
        out: List[Event] = []
        by_id = {c.get("file_id") or c.get("id"): c for c in cuts if isinstance(c, dict)}
        if self.cuts is not None:
            for cid in sorted(by_id.keys() - self.cuts, key=str):
                c = by_id[cid]
                said = {k: c.get(k) for k in ("file_id", "name", "made", "size")}
                out.append(("cut", json.dumps(said)[:400]))
        self.cuts = set(by_id)
        return out

    def _tuning(self) -> List[Event]:
        if not (self.site and self.printer):
            return []
        tuning = self.get("/slicer/tuning", site=self.site, printer=self.printer)
        if not isinstance(tuning, dict):
            return []
        out: List[Event] = []
        for entry in tuning.get("documents", []):
            doc = entry["document"]
            key = json.dumps(doc.get("applies_to", doc.get("appliesTo")), sort_keys=True)
            turns = doc.get("turns", [])
            before = self.turns.get(key)
            if before is not None and len(turns) > before:
                for turn in turns[before:]:
                    out.append(
                        (
                            "turn",
                            f"{turn.get('id')} on {key}: {len(turn.get('readings', []))} readings",
                        )
                    )
                trends = {k: v.get("said") for k, v in (entry.get("trends") or {}).items()}
                out.append(("turn", "trends " + json.dumps(trends)[:600]))
            elif before is not None and len(turns) < before:
                out.append(("turn", f"turns {before} -> {len(turns)} on {key} (undone)"))
            self.turns[key] = len(turns)
            settings = {
                k: (v.get("value"), v.get("source")) for k, v in (doc.get("settings") or {}).items()
            }
            if key in self.applied and settings != self.applied[key]:
                out.append(("applied", f"{key}: {settings}"))
            self.applied[key] = settings
        return out

    def _jobs(self) -> List[Event]:
        jobs = self.get("/jobs")
        if not isinstance(jobs, list):
            return []
        out: List[Event] = []
        first = self.jobs is None
        known = {} if first else self.jobs
        for job in jobs[:JOB_LIMIT]:
            port = str((job.get("machine") or {}).get("port") or "")
            if TEST_PORT.match(port):
                continue
            progress = job.get("progress")
            bucket = None if progress is None else int(progress * 10)
            state = (job.get("outcome"), (job.get("detail") or {}).get("stage"), bucket)
            if not first and job["id"] not in known:
                name = (job.get("input") or {}).get("name")
                out.append(("job", f"new {job.get('kind')} {job['id']} {name} on {port}"))
            elif not first and known[job["id"]] != state:
                shown = "" if progress is None else round(progress * 100)
                out.append(
                    (
                        "job",
                        f"{job['id']} outcome={state[0]} stage={state[1]} "
                        f"progress={shown}% reason={job.get('reason')}",
                    )
                )
            known[job["id"]] = state
        self.jobs = known
        return out

    def _page_to_end(self, port: str) -> None:
        """A board's log is read from its oldest page: page to its end, so only lines
        written from now on are said."""
        cursor = None
        for _ in range(500):
            query = {"port": port, **({"since": cursor} if cursor is not None else {})}
            page = self.get("/firmware/printers/log", **query)
            if (
                not isinstance(page, dict)
                or not page.get("entries")
                or page.get("next") in (None, cursor)
            ):
                break
            cursor = page.get("next")
        if cursor is not None:
            self.log_next[port] = cursor

    def _boards(self) -> List[Event]:
        out: List[Event] = []
        armed = self.get("/firmware/printers/armed")
        armed_ports = set((armed.get("armed") or {}).keys()) if isinstance(armed, dict) else set()
        for port, name in sorted(self.ports().items()):
            if port not in self.log_next:
                self._page_to_end(port)
            query = {
                "port": port,
                **({"since": self.log_next[port]} if port in self.log_next else {}),
            }
            log = self.get("/firmware/printers/log", **query)
            if not isinstance(log, dict):
                if self.boards.get(port, {}).get("err") is None:
                    out.append(("board", f"{name} ({port}): log refused: {log}"))
                self.boards.setdefault(port, {})["err"] = str(log)
                continue
            old = self.boards.get(port)
            snap = dict(old or {"targets": None, "state": None})
            snap["err"] = None
            snap["armed"] = port in armed_ports
            unpaged = port not in self.log_next
            for entry in log.get("entries", []):
                text, origin = entry.get("text", ""), entry.get("origin")
                temps = re.search(r"T:[-\d.]+ /([-\d.]+) B:[-\d.]+ /([-\d.]+)", text)
                if temps:
                    snap["targets"] = (float(temps.group(1)), float(temps.group(2)))
                grbl = re.match(r"<(\w+)[|:>]", text)
                if grbl:
                    snap["state"] = grbl.group(1)
                if unpaged:
                    continue
                bad = BAD_SERIAL.search(text)
                # A jog is G91, the move, G90, each answered ok: the move alone is said.
                if not bad and origin != "poll" and text.strip() in ("ok", "G90", "G91"):
                    continue
                if (
                    bad
                    or (origin != "poll" and origin not in STREAMED)
                    or entry.get("kind") == "sys"
                ):
                    out.append(("serial", f"{port} {entry.get('kind')}/{origin}: {text[:200]}"))
            self.log_next[port] = log.get("next", self.log_next.get(port))
            if old is None or old.get("err"):
                out.append(("board", f"{name} ({port}) {snap}"))
            else:
                diff = {k: f"{old.get(k)} -> {v}" for k, v in snap.items() if old.get(k) != v}
                if diff:
                    out.append(("board", f"{port} {diff}"))
            self.boards[port] = snap
        return out


# ---- the command --------------------------------------------------------------------------


class _Say:
    """Each event as one timed line, to the terminal and, when named, to a file."""

    def __init__(self, events: Optional[Path]) -> None:
        self.events = events
        self.lock = threading.Lock()

    def __call__(self, kind: str, text: str) -> None:
        line = f"{datetime.now():%H:%M:%S} {kind:7} {text}"
        with self.lock:
            click.echo(line)
            if self.events is not None:
                with self.events.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")


@click.command("watch")
@port_option("Port of the running server to watch")
@click.option(
    "--log",
    "log_path",
    type=click.Path(dir_okay=False, path_type=Path),
    help="The file the server's output is written to: its requests, errors and restarts are followed too.",
)
@click.option(
    "--events",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Also append each line to this file.",
)
@click.option("--site", help="The site whose printer's tuning is followed (with --printer).")
@click.option(
    "--printer", help="The printer, a node path in --site, whose tuning turns are followed."
)
@click.option(
    "--every",
    type=float,
    default=3.0,
    show_default=True,
    help="Seconds between reads of the state.",
)
@click.option(
    "--rounds",
    type=int,
    default=0,
    show_default=True,
    help="Stop after this many reads of the state; 0 runs until stopped.",
)
def watch(
    port: int,
    log_path: Optional[Path],
    events: Optional[Path],
    site: Optional[str],
    printer: Optional[str],
    every: float,
    rounds: int,
):
    """Watch a running server while its page is used: one line per thing that changed.

    The state (slices, cuts, tuning turns, jobs, each board's serial log) is read over
    HTTP and compared with the read before; with --log, the server's output is followed
    too, the page's polling taken out. It only reads: no board is polled by it. Stop it
    with Ctrl-C."""
    if (site is None) != (printer is None):
        raise click.UsageError(
            "--site and --printer go together: the tuning of one printer in one site"
        )
    base = f"http://127.0.0.1:{port}"
    say = _Say(events)
    stop = threading.Event()
    follower = None
    if log_path is not None:
        follower = threading.Thread(target=follow, args=(log_path, say, stop), daemon=True)
        follower.start()
    state = StateWatch(http_getter(base), site=site, printer=printer, ports=serial_ports)
    say("watch", f"watching {base}" + (f" and {log_path}" if log_path else ""))
    done = 0
    try:
        while True:
            for kind, text in state.step():
                say(kind, text)
            done += 1
            if rounds and done >= rounds:
                break
            time.sleep(every)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if follower is not None:
            follower.join(timeout=2.0)
