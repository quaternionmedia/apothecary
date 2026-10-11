"""A slice: a part or a made piece, its G-code for a printer, kept where the Print card keeps a file.

**What is sliced** is a ``Target``: a registered part (by its name), or a node
of a site -- a part standing there, or a piece made from a picture -- which
the site layer answers (``TARGETS``, filled by apothecary/api.py; this module
imports nothing from the site layer). A part's STL is its own build
(``build_stl``, as ``/parts/{name}/stl/generate`` builds it); a piece's is its
node's render (as ``/sites/{name}/nodes/{path}/stl`` renders it).

**The printer** is a part that keeps a slicer profile (``profiles.py``): the
one a port's pin stands under, or a site's printer node, both answered by the
site layer (``PRINTERS``), or named by its part.

**A slice** chooses its module (``modules.chosen_id``), resolves its values
(``SlicerModule.settings``: the part's declared print settings, the printer's
profile filling the rest -- before anything is built, so a refusal costs
nothing), builds the STL, runs the module's steps in a folder of the slice's
own under the state folder, and reads what the slicer wrote.

**Where it is kept, and how long.** The G-code goes where the Print card's file
box keeps a file (``firmware/devices.save_print_file``: the state folder's
``prints/``, checked as an upload is), so Print follows Slice: the kept file is
in the Print card's list at once. Its slice record -- what was sliced, for
which printer, with which slicer, each value and where it came from, the
slicer's estimate, its errors and warnings, where the moves reach -- is the
state folder's ``slices/<file id>.json``, beside the file and kept as long as
the file is: a record whose file the Print card has forgotten is forgotten on
the next read. The slice's own folder is removed when it ends, whatever
happened (OrcaSlicer's whole configuration is in the G-code it wrote).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Protocol

from ..firmware import devices
from .models import Bounds, Estimate, Made, Setting, SlicedFor, SliceRecord, SlicerMessage
from .modules import Log, NotInstalled, SlicerError, chosen_id, get_module
from .profiles import Declared, PrinterProfile, load_part, load_profile, printers

FILE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,119}$")


class Runner(Protocol):
    """Where a slice runs: a task's (``firmware.tasks.Running``) or the CLI's
    (``Here``). ``run`` logs each line a process prints, and hands it to ``hear``."""

    def log(self, line: str) -> None: ...

    def run(
        self,
        argv: List[str],
        env: Optional[dict] = None,
        cwd: Optional[str] = None,
        hear: Optional[Callable[[str], None]] = None,
    ) -> int: ...


class Here:
    """A slice run in this process, as the CLI runs one: each line to ``log``."""

    def __init__(self, log: Log):
        self.log = log

    def run(self, argv, env=None, cwd=None, hear=None) -> int:
        from ..firmware.tasks import stream

        said = []

        def both(line: str) -> None:
            if said and hear is not None:  # the first line is the command, which stream logs
                hear(line)
            said.append(line)
            self.log(line)

        return stream(argv, both, env=env, cwd=cwd)


class SliceFailed(SlicerError):
    """A slice that ran and failed: what the slicer said, and the values it was given."""

    def __init__(self, message: str, messages: List[SlicerMessage], settings: List[Setting]):
        super().__init__(message)
        self.messages = messages
        self.settings = settings


@dataclass
class Target:
    """What is sliced: what it is, what it declares, and how its STL is had."""

    made: Made
    declared: Declared
    stl: Callable[[Log], bytes]  # its STL's bytes, built if need be


@dataclass
class Printer:
    """The printer a slice is for: where it stands, and the profile its part keeps."""

    at: SlicedFor
    profile: PrinterProfile


# The site layer answers these (apothecary/api.py registers each); the first
# answer wins. A target: a node of a site, by its path. A printer: the printer a
# port's pin stands under (port), or a site's printer node (site, path).
TARGETS: List[Callable[[str, str], Optional[Target]]] = []
PRINTERS: List[Callable[[Optional[str], Optional[str], Optional[str]], Optional[SlicedFor]]] = []


# --- what is sliced, and for which printer ---------------------------------------------


def part_target(name: str, site: Optional[str] = None, path: Optional[str] = None) -> Target:
    """A registered part, built at its defaults as its own STL is."""
    part = load_part(name)

    def stl(log: Log) -> bytes:
        from ..projects.parts.stl_renderer import build_stl

        result = build_stl(part)
        if not result.success or result.stl_path is None:
            raise SlicerError(f"the part {name}'s STL could not be built: {result.error_message}")
        log(f"STL: {result.stl_path}" + (" (up to date)" if result.skipped == "fresh" else ""))
        return Path(result.stl_path).read_bytes()

    return Target(
        made=Made(kind="part", name=name, site=site, path=path),
        declared=Declared.of(getattr(part, "print_settings", None), f"part {name}"),
        stl=stl,
    )


def printer_named(part_name: Optional[str] = None) -> Printer:
    """A printer by its part's name; with none named, the one part that keeps a
    profile, when there is one."""
    if not part_name:
        found = printers()
        if len(found) != 1:
            raise SlicerError(
                "name the printer: "
                + (", ".join(found) if found else "no part keeps a slicer profile")
            )
        part_name = found[0]
    return Printer(at=SlicedFor(part=part_name, name=part_name), profile=load_profile(part_name))


def resolve(
    part: str,
    port: Optional[str] = None,
    site: Optional[str] = None,
    printer: Optional[str] = None,
) -> tuple[Target, Printer]:
    """What ``part`` names, and the printer: the one ``port``'s pin stands under,
    else ``site``'s printer node at ``printer`` -- with none named, the site's one
    printer that keeps a profile -- else the printer part ``printer``. In a
    printer's site, ``part`` is a node's path there first (a part standing in it,
    or a piece made from a picture), else a registered part's name."""
    at: Optional[SlicedFor] = None
    if port or site:
        for answer in PRINTERS:
            at = answer(port, site, printer)
            if at is not None:
                break
        if at is None:
            where = f"the port {port}" if port else (f"{printer} in {site}" if printer else site)
            raise SlicerError(f"{where}: no printer that keeps a slicer profile")
        chosen = Printer(at=at, profile=load_profile(at.part))
    else:
        chosen = printer_named(printer)
    target = None
    if chosen.at.site:
        for answer in TARGETS:
            target = answer(chosen.at.site, part)
            if target is not None:
                break
    if target is None:
        try:
            target = part_target(part)
        except SlicerError:
            if not chosen.at.site:
                raise
            raise SlicerError(
                f"{part!r} is no part or piece of {chosen.at.site}, and no part's name"
            ) from None
    return target, chosen


# --- one slice -------------------------------------------------------------------------


def slices_dir() -> Path:
    return devices.state_dir() / "slices"


def _work_dir() -> Path:
    folder = devices.private_folder(slices_dir() / "work")
    return Path(tempfile.mkdtemp(prefix=f"{uuid.uuid4().hex[:8]}.", dir=folder))


def slice_into(
    target: Target, printer: Printer, runner: Runner, slicer: Optional[str] = None
) -> SliceRecord:
    """Slice ``target`` for ``printer`` with the module chosen, keep the G-code
    where the Print card keeps a file, and record the slice beside it."""
    module = get_module(chosen_id(slicer, printer.profile))
    status = module.status()
    if not status.ok:
        raise NotInstalled(f"{module.label}: " + "; ".join(status.problems))
    for note in status.notes:
        runner.log(note)
    runner.log(
        f"Slicing {target.made.kind} {target.made.name} for {printer.at.name} "
        f"({printer.profile.file}) with {module.label} {status.tool.version}"
    )
    resolved = module.settings(printer.profile, target.declared)
    if target.declared.note:
        resolved.settings.insert(
            0,
            Setting(
                name="print settings",
                value="none declared",
                origin="printer",
                source=target.declared.by,
                note=target.declared.note,
            ),
        )
    for setting in resolved.settings:
        runner.log(f"  {setting.name} = {setting.value!r}  [{setting.origin}: {setting.source}]")
    stl = target.stl(runner.log)
    work = _work_dir()
    try:
        model = work / "model.stl"
        model.write_bytes(stl)
        plan = module.slice(model, resolved, work)
        said: List[str] = []  # what the slicer printed: its errors and warnings are read from it
        cwd = str(plan.cwd) if plan.cwd else None
        code = 0
        for argv in plan.steps:
            code = runner.run(argv, plan.env, cwd, hear=said.append)
            if code != 0:
                break
        output = module.result(work, said)
        messages = [SlicerMessage(**m) for m in output.messages]
        if code != 0 or output.gcode is None:
            errors = "; ".join(m.text for m in messages if m.level == "error")
            what = f"failed (exit {code})" if code != 0 else "wrote no G-code"
            raise SliceFailed(
                f"{module.label} {what}" + (f": {errors}" if errors else ""),
                messages,
                resolved.settings,
            )
        data = output.gcode.read_bytes()
        kept = devices.save_print_file(f"{target.made.name}.gcode", data)
        runner.log(f"Kept {kept.name} ({kept.lines} lines) for the Print card: {kept.id}")
        for problem in kept.problems:
            runner.log(f"  the Print card would refuse it: {problem}")
        record = SliceRecord(
            file_id=kept.id,
            name=kept.name,
            at=datetime.now(timezone.utc),
            slicer=module.id,
            slicer_label=module.label,
            slicer_version=status.tool.version,
            made=target.made,
            printer=printer.at,
            settings=resolved.settings,
            estimate=Estimate(**output.estimate) if output.estimate else None,
            messages=messages,
            bounds=gcode_bounds(output.gcode),
            lines=kept.lines,
            problems=kept.problems,
        )
        _write_record(record)
        if record.estimate and record.estimate.time:
            runner.log(
                f"{module.label} estimates {record.estimate.time}, "
                f"{record.estimate.filament_g or '?'} g of filament"
            )
        return record
    finally:
        shutil.rmtree(work, ignore_errors=True)


# --- the records ---------------------------------------------------------------------


def _write_record(record: SliceRecord) -> None:
    folder = devices.private_folder(slices_dir())
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(record.model_dump_json(indent=2))
        os.replace(tmp, folder / f"{record.file_id}.json")
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def get_record(file_id: str) -> Optional[SliceRecord]:
    """The slice that made the kept file ``file_id``, while the file is kept."""
    if not FILE_ID_RE.match(file_id or ""):
        return None
    path = slices_dir() / f"{file_id}.json"
    if devices.print_file(file_id) is None:
        path.unlink(missing_ok=True)  # the Print card forgot the file: the slice goes with it
        return None
    try:
        return SliceRecord(**json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None


def records() -> List[SliceRecord]:
    """Every slice whose file is still kept, newest first."""
    folder = slices_dir()
    found = []
    if folder.is_dir():
        for path in folder.glob("*.json"):
            record = get_record(path.stem)
            if record is not None:
                found.append(record)
    return sorted(found, key=lambda r: r.at, reverse=True)


# --- where the moves reach ------------------------------------------------------------

_WORD = re.compile(r"([A-Z])\s*(-?\d*\.?\d+)")


def gcode_bounds(path: Path) -> Optional[Bounds]:
    """Where the extruding moves reach (both ends of each), in the printer's own
    coordinates: absolute or relative moves (G90/G91), absolute or relative
    extrusion (M82/M83), and ``G92`` setting where it stands. None for a file
    that extrudes nothing."""
    pos = {"X": 0.0, "Y": 0.0, "Z": 0.0, "E": 0.0}
    relative = relative_e = False
    low = [float("inf")] * 3
    high = [float("-inf")] * 3
    seen = False
    try:
        handle = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return None
    with handle:
        for raw in handle:
            line = raw.split(";", 1)[0].strip().upper()
            if not line:
                continue
            code = line.split(None, 1)[0]
            if code == "G90":
                relative = relative_e = False
            elif code == "G91":
                relative = relative_e = True
            elif code == "M82":
                relative_e = False
            elif code == "M83":
                relative_e = True
            elif code == "G92":
                for axis, value in _WORD.findall(line[3:]):
                    if axis in pos:
                        pos[axis] = float(value)
            elif code in ("G0", "G1", "G00", "G01"):
                words = dict(_WORD.findall(line[len(code) :]))
                start = (pos["X"], pos["Y"], pos["Z"])
                for axis in "XYZ":
                    if axis in words:
                        value = float(words[axis])
                        pos[axis] = pos[axis] + value if relative else value
                extruded = False
                if "E" in words:
                    e = float(words["E"])
                    extruded = e > 0 if relative_e else e > pos["E"]
                    pos["E"] = pos["E"] + e if relative_e else e
                moved = start != (pos["X"], pos["Y"], pos["Z"])
                if extruded and moved:
                    seen = True
                    for point in (start, (pos["X"], pos["Y"], pos["Z"])):
                        for i in range(3):
                            low[i] = min(low[i], point[i])
                            high[i] = max(high[i], point[i])
    if not seen:
        return None
    return Bounds(min=[round(v, 3) for v in low], max=[round(v, 3) for v in high])


# --- answers kept for a task -----------------------------------------------------------

ANSWERS_KEPT = 50
_ANSWERS: Dict[str, dict] = {}


def remember(task_id: str, answer: dict) -> None:
    _ANSWERS[task_id] = answer
    while len(_ANSWERS) > ANSWERS_KEPT:
        _ANSWERS.pop(next(iter(_ANSWERS)))


def answer_of(task_id: str) -> Optional[dict]:
    return _ANSWERS.get(task_id)
