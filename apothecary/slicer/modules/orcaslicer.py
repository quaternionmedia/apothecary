"""OrcaSlicer's command line, the first slicer module.

**What it slices**: an STL, for an FFF printer, into G-code -- one plate,
arranged on the bed (``--arrange 1``), as the part is turned (``--orient 0``:
a part is authored the way up it prints), lifted onto the bed if it reaches
below it (``--ensure-on-bed``).

**Its program** is ``APOTHECARY_ORCASLICER`` (``none`` means none), else the
release ``apothecary slicer install`` put in the tools dir, else
``orca-slicer`` or ``OrcaSlicer`` on ``PATH``. OrcaSlicer reads its own
printer profiles from the ``resources`` folder beside it -- one level up from
the program, as OrcaSlicer itself looks (``Contents/Resources`` in a macOS
app) -- or, for an installed AppImage, the profiles its install extracted.

**The printer's profile** (``profiles.py``) names, for this module, three of
OrcaSlicer's own profiles of the printer's vendor -- a machine, a process and a
filament -- and the values the printer holds over them (``set``). At each slice
each is read from the installed release and flattened along its ``inherits``
chain, as OrcaSlicer flattens a system profile, because its command line takes
a profile whole and does not look its parents up; the printer's values go on
top, then the part's declared print settings:

- ``nozzle_diameter`` must be the printer's: a slice cannot change the nozzle,
  so a part that asks for another is refused, saying so.
- ``layer_height`` is the process's ``layer_height``, inside the machine's
  ``min_layer_height`` and ``max_layer_height``.
- ``wall_thickness`` is the process's ``wall_loops``: as many lines as reach it,
  a line as wide as the nozzle (the model's own reckoning, "usually 3x nozzle").
- ``tolerance`` is not passed: it is what the part's geometry already allows
  for a fit, and a slicer compensating as well would take it twice.

The three are written as user profiles of the system ones they start from
(``"from": "user"``, ``inherits``), so OrcaSlicer's own check that the process
is for the machine still holds. ``--datadir`` is a folder of the slice's own,
so nothing of a person's OrcaSlicer configuration is read or written.

**What it wrote**: ``plate_1.gcode`` in the output folder, whose comments carry
OrcaSlicer's estimate (``; estimated printing time (normal mode) = ...``,
``; filament used [g] = ...``), and on Linux ``result.json``, its return code
and error string. Its errors and warnings are the lines it printed that say so.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ...stays_local import subprocess_env
from .. import orcaslicer_installer as installer
from ..models import Setting, SlicerStatus, SlicerTool
from ..profiles import Declared, PrinterProfile
from . import Log, NotInstalled, Output, Plan, Resolved, SlicerError, SlicerModule, Tool

TOOL = Tool(
    name="OrcaSlicer",
    env="APOTHECARY_ORCASLICER",
    managed=installer.current_executable,
    commands=("orca-slicer", "OrcaSlicer"),
)

KINDS = ("machine", "process", "filament")
SECTION_KEYS = {"machine": "machine_list", "process": "process_list", "filament": "filament_list"}
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 @()._+-]{0,119}$")

# The values a slice's answer shows, beside every value the printer's profile
# sets and every value the part declares: what a person reads to know what the
# printer will do. (OrcaSlicer's full configuration is in the G-code's own
# CONFIG_BLOCK.)
SHOWN: Dict[str, Tuple[str, ...]] = {
    "machine": (
        "nozzle_diameter",
        "printable_area",
        "printable_height",
        "gcode_flavor",
        "z_offset",
    ),
    "process": (
        "layer_height",
        "initial_layer_print_height",
        "wall_loops",
        "top_shell_layers",
        "bottom_shell_layers",
        "sparse_infill_density",
        "enable_support",
    ),
    "filament": (
        "filament_type",
        "nozzle_temperature_initial_layer",
        "nozzle_temperature",
        "cool_plate_temp_initial_layer",
        "cool_plate_temp",
    ),
}

# What OrcaSlicer itself fills when a profile leaves a value out (PrintConfig.cpp).
ORCA_DEFAULTS = {"z_offset": "0"}

_SAID_ERROR = re.compile(r"\berror\b|\bfailed\b|\bcan ?not\b", re.I)
_SAID_WARNING = re.compile(r"\bwarning\b", re.I)


def _first(value):
    """A profile's value as one: the first of a list (one extruder), else itself."""
    return value[0] if isinstance(value, list) and value else value


def _number(value) -> Optional[float]:
    try:
        return float(str(_first(value)).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None


def _plain(value: float) -> str:
    """A number as a profile writes one: ``0.2``, ``8``."""
    return f"{value:g}"


# --- finding it ------------------------------------------------------------------------


def resources_beside(program: Path) -> Optional[Path]:
    """The ``resources`` folder OrcaSlicer reads for ``program``: the installed
    release's, as its install recorded it; else where OrcaSlicer itself looks,
    one level up from the program (``Contents/Resources`` in a macOS app)."""
    version = installer.current_version()
    if version is not None and installer.executable_for(version) == program:
        found = installer.resources_for(version)
        return found if found is not None and (found / "profiles").is_dir() else None
    try:
        real = program.resolve()
    except OSError:
        return None
    for candidate in (
        real.parent / "resources",
        real.parent.parent / "resources",
        real.parent.parent / "Resources",
        real.parent.parent.parent / "resources",
    ):
        if (candidate / "profiles").is_dir():
            return candidate
    return None


_REPORTED: Dict[Tuple[str, int], Optional[str]] = {}


def reported_version(program: Path) -> Optional[str]:
    """The version ``program --help`` names (OrcaSlicer prints it first), remembered
    for as long as the file is the same file. It is asked in a folder of its own:
    OrcaSlicer writes a ``result.json`` wherever it is run, even for ``--help``."""
    try:
        key = (str(program), program.stat().st_mtime_ns)
    except OSError:
        return None
    if key not in _REPORTED:
        try:
            with tempfile.TemporaryDirectory(prefix="apothecary-orcaslicer-") as aside:
                done = subprocess.run(
                    [str(program), "--help"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=120,
                    env=subprocess_env(),
                    cwd=aside,
                    check=False,
                )
            said = (done.stdout or "") + (done.stderr or "")
        except (OSError, subprocess.SubprocessError):
            said = ""
        _REPORTED[key] = installer.reported_version(said)
    return _REPORTED[key]


# --- its profiles ----------------------------------------------------------------------


def _check_name(name: object, what: str) -> str:
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise SlicerError(f"not an OrcaSlicer {what} profile name: {name!r}")
    return name


def vendor_index(resources: Path, vendor: str) -> Dict[str, Path]:
    """Every profile of ``vendor`` OrcaSlicer ships, by name: its vendor file lists
    each with the path of its file under the vendor's folder."""
    vendor = _check_name(vendor, "vendor")
    profiles = resources / "profiles"
    try:
        index = json.loads((profiles / f"{vendor}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SlicerError(f"OrcaSlicer has no profiles of the vendor {vendor!r} ({exc})") from exc
    found: Dict[str, Path] = {}
    folder = (profiles / vendor).resolve()
    for key in SECTION_KEYS.values():
        for entry in index.get(key) or []:
            name, sub = entry.get("name"), entry.get("sub_path")
            if not isinstance(name, str) or not isinstance(sub, str):
                continue
            path = (folder / sub).resolve()
            if folder in path.parents:  # a sub_path that leaves the folder is not a profile
                found[name] = path
    return found


def flatten(index: Dict[str, Path], name: str, kind: str) -> Tuple[dict, List[str]]:
    """The profile ``name`` with what it inherits filled in, nearest first, as
    OrcaSlicer flattens a system profile; and the chain, ``name`` first."""
    chain: List[str] = []
    layers: List[dict] = []
    current: Optional[str] = name
    while current:
        if current in chain:
            raise SlicerError(f"OrcaSlicer's {kind} profile {name!r} inherits itself")
        path = index.get(current)
        if path is None:
            raise SlicerError(f"OrcaSlicer has no {kind} profile {current!r}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SlicerError(f"OrcaSlicer's {kind} profile {current!r}: {exc}") from exc
        if data.get("type") != kind:
            raise SlicerError(
                f"OrcaSlicer's {current!r} is a {data.get('type')} profile, not a {kind}"
            )
        chain.append(current)
        layers.append(data)
        current = data.get("inherits") or None
    flat: dict = {}
    for layer in reversed(layers):
        flat.update(layer)
    return flat, chain


# --- the module ------------------------------------------------------------------------


class OrcaSlicerModule(SlicerModule):
    id = "orcaslicer"
    label = "OrcaSlicer"
    technology = "FFF"
    inputs = (".stl",)
    writes = (".gcode",)
    install_command = "apothecary slicer install"
    pinned = installer.ORCASLICER_VERSION

    # -- the program --------------------------------------------------------------------

    def program(self) -> Tuple[Optional[Path], Optional[str]]:
        return TOOL.find()

    def status(self) -> SlicerStatus:
        path, found_by = self.program()
        tool = SlicerTool(name=TOOL.name, path=str(path) if path else None, found_by=found_by)
        out = SlicerStatus(
            id=self.id,
            label=self.label,
            technology=self.technology,
            inputs=list(self.inputs),
            writes=list(self.writes),
            install=self.install_command,
            pinned=self.pinned,
            tool=tool,
            installed=installer.current_version(),
        )
        if path is None:
            out.problems.append(f"OrcaSlicer is not installed: {self.install_command}")
            return out
        tool.version = reported_version(path)
        tool.ok = tool.version is not None
        if not tool.ok:
            out.problems.append(f"{path} does not run, or does not say it is OrcaSlicer")
        elif tool.version != self.pinned:
            out.notes.append(
                f"OrcaSlicer {tool.version} ({found_by}), not the pinned {self.pinned}: "
                "its profiles and its G-code may differ from what was tested"
            )
        resources = resources_beside(path)
        if resources is None:
            out.problems.append(f"no printer profiles beside {path}")
        else:
            out.profiles = str(resources / "profiles")
        return out

    def install(self, log: Log, force: bool = False) -> SlicerStatus:
        try:
            installer.OrcaSlicerInstaller(force=force, log=log).install()
        except (installer.InstallError, OSError) as exc:
            raise SlicerError(str(exc)) from exc
        return self.status()

    def _resources(self) -> Path:
        path, _found_by = self.program()
        if path is None:
            raise NotInstalled(f"OrcaSlicer is not installed: {self.install_command}")
        resources = resources_beside(path)
        if resources is None:
            raise NotInstalled(f"no printer profiles beside {path}")
        return resources

    # -- a slice's values ---------------------------------------------------------------

    def settings(self, profile: PrinterProfile, declared: Declared) -> Resolved:
        section = profile.section(self.id)
        path, _found_by = self.program()
        version = reported_version(path) if path else None
        index = vendor_index(self._resources(), section.get("vendor"))
        base = f"OrcaSlicer {version or '?'}"
        configs: Dict[str, dict] = {}
        origins: Dict[Tuple[str, str], Setting] = {}
        shown: List[Setting] = []

        for kind in KINDS:
            name = _check_name(section.get(kind), kind)
            flat, chain = flatten(index, name, kind)
            configs[kind] = flat
            shown.append(
                Setting(
                    name=f"{kind} profile",
                    value=name,
                    origin="printer",
                    source=f"{profile.file}: {base}'s {section.get('vendor')} {kind} profile",
                    note=" < ".join(chain) if len(chain) > 1 else None,
                )
            )
            for key in SHOWN[kind]:
                origins[(kind, key)] = Setting(
                    name=key,
                    value=flat.get(key, ORCA_DEFAULTS.get(key)),
                    origin="printer",
                    source=f"{base}'s {name}"
                    if key in flat
                    else f"{base}'s own default ({name} leaves it out)",
                )

        held = section.get("set") or {}
        for kind in KINDS:
            for key, entry in (held.get(kind) or {}).items():
                if not isinstance(entry, dict) or "value" not in entry or "source" not in entry:
                    raise SlicerError(f"{profile.file}: {kind} {key} wants a value and a source")
                before = configs[kind].get(key, ORCA_DEFAULTS.get(key))
                configs[kind][key] = entry["value"]
                agrees = before == entry["value"]
                origins[(kind, key)] = Setting(
                    name=key,
                    value=entry["value"],
                    origin="printer",
                    source=f"{profile.file}: {entry['source']}",
                    note=entry.get("note")
                    or (f"{base}'s profile agrees" if agrees else f"over {base}'s {before!r}"),
                )

        self._declare(configs, origins, declared, profile)
        settings = shown + list(origins.values())
        return Resolved(settings=settings, configs=configs)

    def _declare(self, configs, origins, declared: Declared, profile: PrinterProfile) -> None:
        machine, process = configs["machine"], configs["process"]
        values = declared.values
        nozzle = _number(machine.get("nozzle_diameter"))
        if "nozzle_diameter" in values:
            wanted = float(values["nozzle_diameter"])
            if nozzle is None or abs(wanted - nozzle) > 1e-6:
                has = f"{nozzle:g} mm" if nozzle is not None else "no nozzle named"
                raise SlicerError(
                    f"{declared.by} declares a {wanted:g} mm nozzle; the printer {profile.part} "
                    f"has {has} (its profile), and a slice cannot change a nozzle"
                )
            origins[("machine", "nozzle_diameter")] = Setting(
                name="nozzle_diameter",
                value=machine.get("nozzle_diameter"),
                origin="declared",
                source=declared.by,
                note="the printer's, as the part asks",
            )
        if "layer_height" in values:
            wanted = float(values["layer_height"])
            low = _number(machine.get("min_layer_height"))
            high = _number(machine.get("max_layer_height"))
            if (low is not None and wanted < low - 1e-9) or (
                high is not None and wanted > high + 1e-9
            ):
                raise SlicerError(
                    f"{declared.by} declares {wanted:g} mm layers; the printer {profile.part} "
                    f"prints {low or 0:g} to {high or 0:g} mm"
                )
            process["layer_height"] = _plain(wanted)
            origins[("process", "layer_height")] = Setting(
                name="layer_height", value=_plain(wanted), origin="declared", source=declared.by
            )
        if "wall_thickness" in values:
            thickness = float(values["wall_thickness"])
            line = nozzle or 0.4
            loops = max(1, math.ceil(thickness / line - 1e-9))
            process["wall_loops"] = str(loops)
            origins[("process", "wall_loops")] = Setting(
                name="wall_loops",
                value=str(loops),
                origin="declared",
                source=declared.by,
                note=f"wall_thickness {thickness:g} mm: {loops} lines of {line:g} mm reach it",
            )
        if "tolerance" in values:
            origins[("part", "tolerance")] = Setting(
                name="tolerance",
                value=values["tolerance"],
                origin="declared",
                source=declared.by,
                note="not passed to the slicer: the part's geometry already allows for it",
            )

    # -- the run ------------------------------------------------------------------------

    def slice(self, model: Path, resolved: Resolved, work: Path) -> Plan:
        path, _found_by = self.program()
        if path is None:
            raise NotInstalled(f"OrcaSlicer is not installed: {self.install_command}")
        written = {}
        for kind in KINDS:
            config = dict(resolved.configs[kind])
            config.update(
                type=kind,
                name=f"apothecary {kind}",
                # A user profile of the system one it starts from: OrcaSlicer checks
                # a process against its machine by the machine's system name.
                inherits=config.get("name"),
                **{"from": "user"},
            )
            target = work / f"{kind}.json"
            target.write_text(json.dumps(config, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            written[kind] = target
        out = work / "out"
        out.mkdir(parents=True, exist_ok=True)
        argv = [
            str(path),
            "--datadir",
            str(work / "datadir"),
            "--load-settings",
            f"{written['machine']};{written['process']}",
            "--load-filaments",
            str(written["filament"]),
            "--arrange",
            "1",
            "--orient",
            "0",
            "--ensure-on-bed",
            "--slice",
            "0",
            "--outputdir",
            str(out),
            str(model),
        ]
        return Plan(steps=[argv], env=subprocess_env(), cwd=work)

    def result(self, work: Path, said: List[str]) -> Output:
        out = work / "out"
        messages = _said(said)
        summary = _result_json(out / "result.json")
        if summary is not None:
            code, text = summary.get("return_code"), str(summary.get("error_string") or "")
            if code not in (0, None) and text:
                messages.append({"level": "error", "line": None, "text": f"{text} (code {code})"})
            for plate in summary.get("sliced_plates") or []:
                warning = str(plate.get("warning_message") or "").strip()
                if warning:
                    messages.append({"level": "warning", "line": None, "text": warning})
        found = sorted(out.glob("*.gcode"))
        if not found:
            return Output(gcode=None, messages=messages)
        return Output(gcode=found[0], estimate=read_estimate(found[0]), messages=messages)


def _result_json(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _said(lines: List[str]) -> List[dict]:
    """The errors and warnings among what OrcaSlicer printed, each with its line."""
    found = []
    for n, raw in enumerate(lines, 1):
        text = raw.strip()
        if not text or text.startswith("$ "):
            continue
        if _SAID_WARNING.search(text):
            found.append({"level": "warning", "line": n, "text": text})
        elif _SAID_ERROR.search(text):
            found.append({"level": "error", "line": n, "text": text})
    return found


_TIME_PART = re.compile(r"(\d+)\s*([dhms])")
_ESTIMATE = {
    "time": re.compile(r"^; estimated printing time \(normal mode\) = (.+)$"),
    "first_layer": re.compile(r"^; estimated first layer printing time \(normal mode\) = (.+)$"),
    "filament_mm": re.compile(r"^; filament used \[mm\] = (.+)$"),
    "filament_cm3": re.compile(r"^; filament used \[cm3\] = (.+)$"),
    "filament_g": re.compile(r"^; filament used \[g\] = (.+)$"),
    "layers": re.compile(r"^; total layer(?:s count| number)\s*[:=]\s*(\d+)$"),
}


def seconds_of(text: str) -> Optional[int]:
    """``1d 2h 3m 4s`` as seconds."""
    parts = _TIME_PART.findall(text or "")
    if not parts:
        return None
    scale = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    return sum(int(n) * scale[unit] for n, unit in parts)


def _sum(text: str) -> Optional[float]:
    """``263.81`` or ``263.81, 0.00`` (one per extruder) as one number."""
    try:
        return round(sum(float(v) for v in text.split(",") if v.strip()), 2)
    except ValueError:
        return None


def read_estimate(gcode: Path) -> dict:
    """OrcaSlicer's estimate, from the comments it writes into the G-code: the
    header's layer count, and the time and filament it writes after the moves."""
    found: dict = {}
    try:
        with open(gcode, "rb") as f:
            head = f.read(4096).decode("utf-8", "replace")
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 256 * 1024))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return found
    for line in (head + "\n" + tail).splitlines():
        for key, pattern in _ESTIMATE.items():
            match = pattern.match(line.strip())
            if match and key not in found:
                value = match.group(1).strip()
                if key in ("time", "first_layer"):
                    found[key] = value
                elif key == "layers":
                    found[key] = int(value)
                else:
                    found[key] = _sum(value)
    if "time" in found:
        found["seconds"] = seconds_of(found["time"])
    return found
