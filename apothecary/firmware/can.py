"""What a machine's port would refuse right now, as one answer per command.

Each refusal the seam makes is a predicate here that returns the reason (or None).
The routes and ``devices`` raise from the same predicates, and ``can_now`` reads
them to say, before a person presses anything, which commands would be refused and
why. A page greys a button from this answer, so what it greys and what the server
refuses cannot drift: ``tests/test_can_now.py`` runs each condition through both.

A verdict is ``{"ok": bool, "why": str | None, "kind": str | None}``. ``kind`` names
what stands in the way: ``armed`` (the control latch is down), ``held`` (a job or a
task holds the port), ``homed`` (a home the port has not shown its switch for),
``placed`` (a cut with the tool's place unknown), ``busy`` (another task runs),
``idle`` (nothing to act on), ``offline`` (no link, and the last poll said so),
``alarm`` (the controller is in alarm), ``kind`` (the wrong kind of machine) and
``file`` (the file does not fit the machine).

The emergency stop has no predicate: it is always ok.
"""

from __future__ import annotations

from typing import Any, Dict, NamedTuple, Optional

from . import gcode, grbl
from .toolchains import PortHeld, ToolchainError


class Refusal(NamedTuple):
    kind: str
    why: str

    def error(self) -> Exception:
        """The exception the seam raises for this refusal."""
        if self.kind == "armed":
            return gcode.ControlNotArmed(self.why)
        if self.kind in ("held", "busy"):
            return PortHeld(self.why)
        if self.kind == "offline":
            return ToolchainError(self.why)
        return ValueError(self.why)


def raise_for(why: Optional[str], kind: str) -> None:
    if why:
        raise Refusal(kind, why).error()


# -- the predicates: a reason, or None ----------------------------------------------


def task_holds(port: str, active: Any) -> Optional[str]:
    """A running task (an upload, a flash) writes to ``port``. A compile or an install
    holds no port."""
    if active is not None and active.port == port:
        return f"task {active.id} ({active.title}) holds {port}"
    return None


def print_holds(port: str, job: Any) -> Optional[str]:
    """A host print is running on ``port``."""
    if job is not None and job.finished is None:
        return f"{port}: a print holds the port -- cancel it first"
    return None


def query_held(port: str, job: Optional[dict]) -> Optional[str]:
    """A report-only query waits behind a job that is not streamed (a bed reading); a
    streamed print or cut leaves the link to it."""
    from . import devices

    if job is not None and job.get("kind") not in devices.STREAMED:
        return f"{port}: {devices.what_holds(job)} holds the port ({job['stage']})"
    return None


def not_armed(port: str, armed: bool, saying: str = "control is not armed -- arm it first"):
    return None if armed else f"{port}: {saying}"


def job_refusal(job: Optional[dict], cmd: str) -> Optional[str]:
    """What a job holding the port leaves a person to send: the stop always; while a
    streamed job runs, what its dialect allows; a probe keeps only the stop."""
    from .. import jobs
    from . import devices, dialects

    if not job or cmd in dialects.STOPS:
        return None
    op = jobs.operation(job.get("kind", ""))
    if op is not None and op.kind in devices.STREAMED:
        if dialects.BY_MACHINE[op.machine].job_allows.match(cmd):
            return None
    return f"{devices.port_of(job)}: {devices.what_holds(job)} holds the port ({job.get('stage')})"


def misfit(file: Any, port: str, kind: Optional[str]) -> Optional[str]:
    """A kept file is for one kind of machine; ``kind`` is the one on ``port``."""
    if kind is None:
        return (
            f"{port}: the board there has not said what kind of machine it drives -- "
            f"{file.name} is sent to the kind it was kept for alone"
        )
    if file.machine != kind:
        return (
            f"{file.name} was kept for a {file.machine}, and {port} holds a {kind}: "
            f"it is never sent to a {kind}"
        )
    return None


def file_problem(file: Any, file_id: str) -> Optional[str]:
    """A file that may not be sent at all, on any machine."""
    if file is None:
        return f"no such print file: {file_id}"
    if file.problems:
        return f"{file.name} may not be sent: " + "; ".join(file.problems[:3])
    if file.lines == 0:
        return f"{file.name} has nothing to send"
    return None


def print_start_blocked(port: str, printing: Any, leveling: Any) -> Optional[str]:
    """A job already has the machine: a print, or a bed reading."""
    for running in (printing, leveling):
        if running and running.finished is None:
            what = running.op.kind if running is printing else "bed reading"
            return f"{port}: a {what} already holds the port ({running.stage})"
    return None


def level_start_blocked(port: str, leveling: Any, printing: Any) -> Optional[str]:
    running = leveling
    if running and running.finished is None:
        return f"{port}: {running.what} is already {running.stage}"
    if printing and printing.finished is None:
        return f"{port}: a print holds the port ({printing.stage})"
    return None


def card_printing(port: str, last: Any) -> Optional[str]:
    if last is not None and last.sd_printing:
        return f"{port}: the card is printing -- pause or abort that first"
    return None


def controller_flash(port: str, kind: Optional[str], firmware: Optional[str], replace: bool):
    """A flash would replace the firmware that runs a machine."""
    from .devices import REPLACE_FLAG

    if kind is None or replace:
        return None
    return (
        f"{port} holds a {kind}'s controller ({firmware or 'its firmware'}): a flash replaces "
        f"the firmware that runs the {kind}. Not flashed. To replace it on purpose, ask for it "
        f"by name ({REPLACE_FLAG})"
    )


# -- the answer ------------------------------------------------------------------------

OK: Dict[str, Any] = {"ok": True, "why": None, "kind": None}


def _no(kind: str, why: str) -> Dict[str, Any]:
    return {"ok": False, "why": why, "kind": kind}


def _verdict(refusal: Optional[Refusal]) -> Dict[str, Any]:
    return dict(OK) if refusal is None else _no(*refusal)


# A line of each kind of command, in each dialect, to put to ``job_refusal``: a job
# lets some through (a heater, a spindle) and not others.
LINES = {
    "jog": {"printer": "G91", "router": "$J=G91 G21 X1 F1000"},
    "home": {"printer": "G28", "router": "$H"},
    "off": {"printer": "M104 S0", "router": "M5"},
    "heat": {"printer": "M104 S200"},
    "spindle": {"router": "M3 S1000"},
    "unlock": {"router": "$X"},
    "control": {"printer": "M84", "router": "G0 X0 Y0"},
}
AXES = "XYZ"


class Facts(NamedTuple):
    """What the answer is read from, gathered once."""

    port: str
    task: Any  # the task running now, or None
    armed: bool
    link: Any
    job: Optional[dict]  # the job holding the link
    printing: Any
    leveling: Any
    last: Any  # the last poll
    kind: Optional[str]  # "printer" / "router" / None
    firmware: Optional[str]


def facts_of(port: str, state=None, links=None, runner=None) -> Facts:
    from . import devices
    from .tasks import get_task_runner

    state = state or devices.get_state()
    links = links or gcode.get_printer_links()
    link = links.get(port)
    cached = state.cached_device(port)
    return Facts(
        port=port,
        task=(runner or get_task_runner()).active,
        armed=links.control.armed(port),
        link=link,
        job=link.job if link is not None else None,
        printing=devices.print_job(port),
        leveling=devices.leveling_job(port),
        last=devices.last_statuses().get(port),
        kind=devices.machine_kind(cached),
        firmware=cached.printer.firmware_name if cached and cached.printer else None,
    )


def _offline(f: Facts) -> Optional[Refusal]:
    if f.link is None and f.last is not None and f.last.state == "offline":
        return Refusal("offline", f"{f.port}: no printer link -- the last poll said it is offline")
    return None


def _kind_has(f: Facts, verb: str) -> Optional[Refusal]:
    """A verb a dialect has no line for: a hotend's on a router, a spindle's on a printer."""
    lines = LINES[verb]
    if f.kind is not None and f.kind not in lines:
        return Refusal("kind", f"{f.port}: a {f.kind} has no {verb}")
    return None


def _line(f: Facts, verb: str) -> str:
    lines = LINES[verb]
    return lines.get(f.kind or "") or next(iter(lines.values()))


def line_refusal(f: Facts, verb: str, off: bool = False) -> Optional[Refusal]:
    """What stands between a person and a control line of ``verb``, in the order the
    seam asks: a task on the port, the latch, a job, the link."""
    why = task_holds(f.port, f.task)
    if why:
        return Refusal("held", why)
    why = _kind_has(f, verb)
    if why:
        return why
    if not off:
        why = not_armed(f.port, f.armed)
        if why:
            return Refusal("armed", why)
    why = job_refusal(f.job, _line(f, verb))
    if why:
        return Refusal("held", why)
    return _offline(f)


def home_refusal(f: Facts, axes: str = "") -> Optional[Refusal]:
    why = line_refusal(f, "home")
    if why:
        return why
    if f.kind == grbl.MACHINE and f.link is not None:
        said = grbl.home_problem(f.link, "$H" + axes, read=False)
        if said:
            return Refusal("homed", said)
    return None


def jog_refusal(f: Facts) -> Optional[Refusal]:
    why = line_refusal(f, "jog")
    if why:
        return why
    if f.last is not None and f.last.dialect == grbl.DIALECT and f.last.machine_state == "Alarm":
        # The controller's own refusal, not the server's: nothing moves, a jog included.
        return Refusal("alarm", f"{f.port}: in alarm -- nothing moves until Unlock or a home")
    return None


def start_refusal(f: Facts, file: Any = None, file_id: Optional[str] = None):
    """The checks of ``devices.start_print``; the file's too when one is named."""
    if file_id is not None:
        why = file_problem(file, file_id)
        if why:
            return Refusal("file", why)
    why = task_holds(f.port, f.task)
    if why:
        return Refusal("held", why)
    why = not_armed(
        f.port, f.armed, "a job heats, turns and moves the machine -- arm control first"
    )
    if why:
        return Refusal("armed", why)
    why = print_start_blocked(f.port, f.printing, f.leveling)
    if why:
        return Refusal("held", why)
    why = _offline(f)
    if why:
        return why
    why = card_printing(f.port, f.last)
    if why:
        return Refusal("held", why)
    if file is not None:
        why = misfit(file, f.port, f.kind)
        if why:
            return Refusal("file", why)
    if f.kind == grbl.MACHINE and f.link is not None:
        why = grbl.not_placed(f.link)
        if why:
            return Refusal("placed", f"{f.port}: {why}")
    return None


def _running(f: Facts) -> Optional[Refusal]:
    if f.printing is None or f.printing.finished is not None:
        return Refusal("idle", f"{f.port}: no print is running")
    return None


def _resume_refusal(f: Facts) -> Optional[Refusal]:
    running = _running(f)
    if running:
        return running
    why = not_armed(f.port, f.armed, "resuming moves the machine -- arm control first")
    return Refusal("armed", why) if why else None


def level_refusal(f: Facts, probe: bool) -> Optional[Refusal]:
    why = task_holds(f.port, f.task)
    if why:
        return Refusal("held", why)
    why = level_start_blocked(f.port, f.leveling, f.printing)
    if why:
        return Refusal("held", why)
    if probe:
        why = not_armed(f.port, f.armed, "probing moves the machine -- arm control first")
        if why:
            return Refusal("armed", why)
    why = _offline(f)
    if why:
        return why
    if not probe and f.kind == grbl.MACHINE:
        return Refusal(
            "kind",
            f"{f.port}: a stored mesh is a printer's to read, and {f.port} holds a router, "
            "whose reading probes the table",
        )
    return None


def _port_free(f: Facts, also_print: bool = False) -> Optional[Refusal]:
    why = task_holds(f.port, f.task)
    if why:
        return Refusal("held", why)
    if also_print:
        why = print_holds(f.port, f.printing)
        if why:
            return Refusal("held", why)
        why = gcode.job_holds_link(f.port, f.job)
        if why:
            return Refusal("held", why)
    return None


def _release(f: Facts) -> Optional[Refusal]:
    why = gcode.job_holds_link(f.port, f.job)
    return Refusal("held", why) if why else None


def _query(f: Facts) -> Optional[Refusal]:
    why = task_holds(f.port, f.task)
    if why:
        return Refusal("held", why)
    why = query_held(f.port, f.job)
    return Refusal("held", why) if why else None


def can_now(port: str, state=None, links=None, runner=None) -> Dict[str, Dict[str, Any]]:
    """Per command, whether the server would take it from ``port`` right now."""
    f = facts_of(port, state, links, runner)
    answer = {
        "estop": dict(OK),
        "release": _verdict(_release(f)),
        "jog": _verdict(jog_refusal(f)),
        "home": _verdict(home_refusal(f)),
        "off": _verdict(line_refusal(f, "off", off=True)),
        "heat": _verdict(line_refusal(f, "heat")),
        "spindle": _verdict(line_refusal(f, "spindle")),
        "unlock": _verdict(line_refusal(f, "unlock")),
        "control": _verdict(line_refusal(f, "control")),
        "print.start": _verdict(start_refusal(f)),
        "print.pause": _verdict(_running(f)),
        "print.cancel": _verdict(_running(f)),
        "print.resume": _verdict(_resume_refusal(f)),
        "level.probe": _verdict(level_refusal(f, probe=True)),
        "level.read": _verdict(level_refusal(f, probe=False)),
        "reconnect": _verdict(_port_free(f, also_print=True)),
        "reset": _verdict(_port_free(f, also_print=True)),
        "identify": _verdict(_port_free(f)),
        "listen": _verdict(_port_free(f)),
        "probe": _verdict(_port_free(f)),
        "query": _verdict(_query(f)),
        "flash": _verdict(flash_refusal(f)),
    }
    if f.kind == grbl.MACHINE:
        for axis in AXES:
            answer[f"home.{axis}"] = _verdict(home_refusal(f, axis))
    return answer


def flash_refusal(f: Facts, replace: bool = False) -> Optional[Refusal]:
    """A flash: no task running anywhere, no job holding the port's link, and not
    over a machine's controller."""
    if f.task is not None:
        return Refusal("busy", f"task {f.task.id} ({f.task.title}) is still running")
    why = gcode.job_holds_link(f.port, f.job)
    if why:
        return Refusal("held", why)
    why = controller_flash(f.port, f.kind, f.firmware, replace)
    return Refusal("kind", why) if why else None


def can_start(port: str, file_id: str, state=None, links=None, runner=None) -> Dict[str, Any]:
    """Whether the kept file ``file_id`` could be started on ``port`` now."""
    from . import devices

    f = facts_of(port, state, links, runner)
    return _verdict(start_refusal(f, devices.print_file(file_id), file_id))
