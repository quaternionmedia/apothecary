"""Shims that level a bed on its solid mounts: one for each levelling screw whose corner
stands low, as thick as lifts that corner to the highest.

A bed reading (``firmware.devices.leveling_records``) is a grid of heights over the
area the probe reaches. A plane fitted to it by least squares is the bed's tilt, which
the mounts set. What the plane leaves is the plate's own shape (a bow or a twist), which
no shim changes. The plane is taken where each screw stands. That is outside the grid,
since the probe is offset from the nozzle and the screws sit near the plate's corners.

The rule is the least that levels the bed. The corner the plane puts highest gets no
shim. Each other corner gets the highest's height less its own, rounded to a printed
layer. A shim stacks on its corner's mount, between the mount and the bed or the
carriage, and raises that corner by its thickness. A corner gets none when its shim
would be thinner than one layer, since no print makes it, or thinner than the
repeatability floor, since no probe tells it from noise.

The readings are the mean of those given: two heated probes taken one after the other,
as the bench takes them. Their spread at each point of the grid is the floor. A
reading's bed temperature says whether it was heated (``HEATED_C``). The bed is levelled
at the temperature it prints at, since the plate and the probe both move as they warm.
Shims already fitted are said by label (``fitted``), and the new set is a whole set to
fit in their place. What a shim fits on the machine, the hole its bed screw passes and its
mounts' outer diameter, is kept per machine in the state folder once a person has measured
it (``keep_mount``, ``bed/mounts.json``); until then the part's defaults stand, and are said
to be defaults.

The printer's profile says where its screws are (``measured.bed_screws`` in
``parts/<printer>/slicer.json``): as many as it has, each named, with the label its shim
carries and where the nozzle stands over it in the reading's bed coordinates. Marlin
prints a mesh without its positions. A reading that carries them (a router's ``area``)
is placed by them. A printer's is placed by its profile's ``measured.mesh_area`` when it
holds one, else by the estimate the viewer draws it by (``grid_area_estimate``,
``static/machine_marks.js`` ``meshBounds``), and the result says which.

Nothing here opens a port or sends a line. ``apothecary bed shims`` reads the state
folder's readings and the printer's profile, and the part ``bed_shims`` draws what it
computes.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from .state_folder import state_dir, write_whole

Mesh = Sequence[Sequence[float]]

MESH_INSET = 10.0
"""Marlin's default ``MESH_INSET``, mm in from the probeable edge: the viewer's
``MESH_INSET`` in ``static/machine_marks.js``, which ``tests/test_bed_shims.py`` holds
equal to this."""

HEATED_C = 40.0
"""A bed reading at this bed temperature or above was heated; below it, cold. A line
chosen between a room's temperature and the lowest a bed prints at."""

STEP = 0.1
"""What a shim's thickness is rounded to: the part's layer height, over its first
layer, so each top lands on a layer."""

FIRST_LAYER = 0.2
"""One layer: the thinnest shim printed."""


class ShimError(ValueError):
    """What stops shims being computed: no screws said, no reading, grids that differ."""


class NotAMount(ShimError):
    """A mount no shim fits, or nothing said of one to keep: the person's figures, not
    the printer's or its readings'."""


@dataclass(frozen=True)
class Screw:
    """A levelling screw: its name, the label its shim carries, and where the nozzle
    stands over it, in the reading's bed coordinates (mm from the volume's front-left)."""

    name: str
    label: str
    x: float
    y: float


@dataclass(frozen=True)
class BedScrews:
    """A machine's levelling screws, and where they were found."""

    screws: Tuple[Screw, ...]
    source: str

    def __post_init__(self) -> None:
        if len(self.screws) < 3:
            raise ShimError(
                f"a bed stands on three screws or more, and {len(self.screws)} are said"
            )
        labels = [s.label for s in self.screws]
        if len(set(labels)) != len(labels) or any(not lbl or " " in lbl for lbl in labels):
            raise ShimError(f"each screw's label is one word of its own: {labels}")

    @classmethod
    def of(cls, value: Mapping, source: str) -> "BedScrews":
        """From a profile's ``measured.bed_screws`` value: ``screws``, each ``name``,
        ``label``, ``x`` and ``y``."""
        try:
            screws = tuple(
                Screw(str(s["name"]), str(s["label"]), float(s["x"]), float(s["y"]))
                for s in value["screws"]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ShimError(
                f"bed_screws is {{screws: [{{name, label, x, y}}, ...]}}: {exc}"
            ) from exc
        return cls(screws=screws, source=source)


@dataclass(frozen=True)
class Area:
    """Where a grid's first and last points lie, in the reading's bed coordinates, and
    what says so."""

    x0: float
    y0: float
    x1: float
    y1: float
    source: str


def grid_area_estimate(
    volume: Sequence[float], probe_offset: Optional[Mapping], inset: float = MESH_INSET
) -> Area:
    """Where a printer's grid is taken to lie when nothing says: the volume less what
    the probe's offset from the nozzle puts out of reach, ``inset`` inside that. The
    viewer places the Bed mesh layer by the same estimate (``meshBounds``)."""
    sx, sy = float(volume[0]), float(volume[1])
    ox = float((probe_offset or {}).get("x") or 0.0)
    oy = float((probe_offset or {}).get("y") or 0.0)
    return Area(
        x0=max(0.0, ox) + inset,
        y0=max(0.0, oy) + inset,
        x1=min(sx, sx + ox) - inset,
        y1=min(sy, sy + oy) - inset,
        source=(
            f"an estimate: the {sx:g} x {sy:g} volume less the probe's offset "
            f"(X{ox:+g} Y{oy:+g}), {inset:g} mm inside it"
        ),
    )


def _shape(mesh: Mesh) -> Tuple[int, int]:
    rows = len(mesh)
    cols = len(mesh[0]) if rows else 0
    if rows < 2 or cols < 2 or any(len(r) != cols for r in mesh):
        raise ShimError(f"a plane needs a grid of two by two or more, not {rows} x {cols}")
    return rows, cols


def grid_points(mesh: Mesh, area: Area) -> List[Tuple[float, float, float]]:
    """Each point of ``mesh`` as (x, y, height): rows from the front, each left to
    right, spread evenly over ``area``."""
    rows, cols = _shape(mesh)
    dx = (area.x1 - area.x0) / (cols - 1)
    dy = (area.y1 - area.y0) / (rows - 1)
    return [
        (area.x0 + i * dx, area.y0 + j * dy, float(mesh[j][i]))
        for j in range(rows)
        for i in range(cols)
    ]


def _same_grid(meshes: Sequence[Mesh]) -> Tuple[int, int]:
    if not meshes:
        raise ShimError("no reading to level the bed by")
    shapes = {_shape(m) for m in meshes}
    if len(shapes) != 1:
        raise ShimError(f"the readings' grids differ ({sorted(shapes)}): one grid only")
    return shapes.pop()


def mean_mesh(meshes: Sequence[Mesh]) -> List[List[float]]:
    """The readings' mean, point by point."""
    rows, cols = _same_grid(meshes)
    n = len(meshes)
    return [[sum(float(m[j][i]) for m in meshes) / n for i in range(cols)] for j in range(rows)]


def difference(before: Sequence[Mesh], after: Sequence[Mesh]) -> List[List[float]]:
    """``after``'s mean less ``before``'s, point by point: what changed between them.
    Two probes one after the other are the repeatability; a probe before shims and one
    after are what the shims did, with that repeatability in it."""
    a, b = mean_mesh(before), mean_mesh(after)
    if (len(a), len(a[0])) != (len(b), len(b[0])):
        raise ShimError("the readings before and after are of different grids")
    return [[b[j][i] - a[j][i] for i in range(len(a[0]))] for j in range(len(a))]


def spread(meshes: Sequence[Mesh]) -> Optional[float]:
    """The repeatability floor: the most the readings differ at any one point of the
    grid. None for a single reading, which has no floor."""
    if len(meshes) < 2:
        return None
    rows, cols = _same_grid(meshes)
    return max(
        max(float(m[j][i]) for m in meshes) - min(float(m[j][i]) for m in meshes)
        for j in range(rows)
        for i in range(cols)
    )


@dataclass(frozen=True)
class Plane:
    """``height = a·x + b·y + c``: mm of rise per mm along X (``a``) and Y (``b``)."""

    a: float
    b: float
    c: float

    def at(self, x: float, y: float) -> float:
        return self.a * x + self.b * y + self.c


def fit_plane(points: Sequence[Tuple[float, float, float]]) -> Plane:
    """The least-squares plane through ``points``, from its normal equations."""
    n = len(points)
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    mz = sum(p[2] for p in points) / n
    sxx = sum((p[0] - mx) ** 2 for p in points)
    syy = sum((p[1] - my) ** 2 for p in points)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in points)
    sxz = sum((p[0] - mx) * (p[2] - mz) for p in points)
    syz = sum((p[1] - my) * (p[2] - mz) for p in points)
    det = sxx * syy - sxy * sxy
    if abs(det) < 1e-12:
        raise ShimError("the grid's points lie on a line: no plane through them")
    a = (sxz * syy - syz * sxy) / det
    b = (syz * sxx - sxz * sxy) / det
    return Plane(a=a, b=b, c=mz - a * mx - b * my)


@dataclass(frozen=True)
class Run:
    """One reading as the shims say it: its id, when, how, the bed's temperature and
    the note it was kept with."""

    id: str
    at: Optional[datetime] = None
    method: Optional[str] = None
    bed_c: Optional[float] = None
    note: Optional[str] = None

    @property
    def heated(self) -> Optional[bool]:
        """Whether the bed was heated when it was read; None when no temperature was."""
        return None if self.bed_c is None else self.bed_c >= HEATED_C

    def said(self) -> str:
        when = self.at.strftime("%Y-%m-%d %H:%M UTC") if self.at else "no time"
        bed = (
            "bed temperature not read"
            if self.bed_c is None
            else f"bed {self.bed_c:g} °C, {'heated' if self.heated else 'cold'}"
        )
        note = f", {self.note!r}" if self.note else ""
        return f"{self.id} ({self.method or 'unknown method'}, {when}, {bed}{note})"


NONE_HIGHEST = "the highest"
NONE_LAYER = "under one layer"
NONE_FLOOR = "under the floor"


@dataclass(frozen=True)
class Shim:
    """One screw's shim: the plane's height at the screw, the shim fitted there now,
    the thickness that levels its corner, and that thickness as printed -- or none, and
    why (``NONE_HIGHEST``, ``NONE_LAYER``, ``NONE_FLOOR``)."""

    screw: Screw
    height: float
    fitted: float
    thickness: float
    printed: Optional[float]
    none: Optional[str] = None


@dataclass(frozen=True)
class Mount:
    """What a machine's shims fit: the hole its bed screw passes and the ring across, at
    least its mounts' face. Each is kept per machine once a person has measured it
    (``keep_mount``); until then it is the part's own default, and said as one."""

    hole_d: float
    outer_d: float
    hole_kept: bool = False
    outer_kept: bool = False
    screw: Optional[str] = None  # the bed screw a kept hole was set by, "M3" or "M4"
    at: Optional[str] = None  # when it was last kept

    def params(self) -> Dict[str, float]:
        """The part's parameters a person has measured: none of its defaults."""
        out: Dict[str, float] = {}
        if self.hole_kept:
            out["hole_d"] = self.hole_d
        if self.outer_kept:
            out["outer_d"] = self.outer_d
        return out

    def said(self) -> str:
        screw = f" ({self.screw})" if self.hole_kept and self.screw else ""
        hole = f"screw hole {self.hole_d:g} mm{screw}" + ("" if self.hole_kept else " (a default)")
        ring = f"ring {self.outer_d:g} mm across" + ("" if self.outer_kept else " (a default)")
        if self.hole_kept and self.outer_kept:
            return f"{hole}, {ring}: kept {self.at}"
        return (
            f"{hole}, {ring}: a default stands until the bed screw and the mount's outer "
            "diameter, read with calipers, are kept (`apothecary bed mount`)"
        )


@dataclass(frozen=True)
class Shims:
    """Readings turned into shims, with what they cannot fix."""

    runs: Tuple[Run, ...]
    screws_from: str
    area: Area
    plane: Plane
    shims: Tuple[Shim, ...]
    residual: Tuple[float, float, float]  # what the plane leaves: least, most, rms
    floor: Optional[float]  # the readings' repeatability floor; None for one reading
    outside: float  # how far the furthest screw stands outside the grid, mm
    bound: Optional[float] = None  # the profile's measured.mesh_range_bound, mm
    mesh: List[List[float]] = field(default_factory=list)  # the readings' mean
    mount: Optional[Mount] = None  # what the shims fit; None, the part's defaults unsaid

    @property
    def printed(self) -> Tuple[Shim, ...]:
        """The shims to print: the corners that get one."""
        return tuple(s for s in self.shims if s.printed is not None)

    @property
    def bow(self) -> float:
        """How far apart the plane leaves the bed's highest and lowest points: the range
        no shim takes out, and the least a level bed's reading spans."""
        return self.residual[1] - self.residual[0]

    def bow_mesh(self) -> List[List[float]]:
        """What the plane leaves at each point of the grid: the readings' mean less the
        plane, rows from the front."""
        if not self.mesh:
            return []
        points = grid_points(self.mesh, self.area)
        cols = len(self.mesh[0])
        flat = [round(z - self.plane.at(x, y), 4) for x, y, z in points]
        return [flat[j * cols : (j + 1) * cols] for j in range(len(self.mesh))]

    @property
    def left(self) -> float:
        """The tilt the shims leave between corners, by rounding to a layer and by the
        corners that get none."""
        errs = [(s.printed or 0.0) - s.thickness for s in self.shims]
        return max(errs) - min(errs)

    def params(self) -> Optional[Dict[str, object]]:
        """The part ``bed_shims``'s parameters that draw the shims to print; None when
        no corner gets one."""
        if not self.printed:
            return None
        return {
            "thicknesses": [s.printed for s in self.printed],
            "labels": " ".join(s.screw.label for s in self.printed),
            **(self.mount.params() if self.mount else {}),
        }

    def slice_command(self, part: str = "bed_shims") -> Optional[str]:
        """The command that slices them for the printer, as the shell takes it."""
        p = self.params()
        if p is None:
            return None
        return (
            f"apothecary slicer slice {part} -p thicknesses="
            + ",".join(f"{t:.1f}" for t in p["thicknesses"])
            + f" -p 'labels={p['labels']}'"
            + "".join(f" -p {k}={p[k]:g}" for k in ("hole_d", "outer_d") if k in p)
        )

    def said(self) -> List[str]:
        """What a person reads: the readings, the tilt at each screw, each shim, and
        what is left for the plate's shape and for rounding."""
        least, most, rms = self.residual
        lines = [f"reading {r.said()}" for r in self.runs]
        if any(r.heated is False for r in self.runs):
            lines.append(
                "a cold reading: the bed is levelled at the temperature it prints at, so heat "
                "it, let it soak, and probe it there"
            )
        lines += [
            f"grid placed by {self.area.source}: x {self.area.x0:g}..{self.area.x1:g}, "
            f"y {self.area.y0:g}..{self.area.y1:g} mm",
            f"screws from {self.screws_from}",
            f"tilt: {self.plane.a * 100:+.3f} mm per 100 mm along X, "
            f"{self.plane.b * 100:+.3f} along Y",
            (
                f"repeatability floor: {self.floor:.3f} mm, the most the readings differ at "
                "one point"
                if self.floor is not None
                else "repeatability floor: not known from one reading; probe twice, one after "
                "the other"
            ),
        ]
        for s in self.shims:
            now = f", fitted {s.fitted:.1f}" if s.fitted else ""
            shim = f"shim {s.printed:.1f} mm" if s.printed is not None else f"none ({s.none})"
            lines.append(
                f"  {s.screw.label:>3} {s.screw.name:<12} at ({s.screw.x:g}, {s.screw.y:g}): "
                f"plane {s.height:+.3f} mm{now}, needs {s.thickness:.3f} -> {shim}"
            )
        lines += [
            f"left by the plane, which shims cannot fix: {least:+.3f}..{most:+.3f} mm "
            f"(a range of {self.bow:.3f}), rms {rms:.3f}",
            f"left by rounding to {STEP:g} mm layers and the corners that get none: up to "
            f"{self.left:.3f} mm between corners",
            f"the furthest screw stands {self.outside:.1f} mm outside the probed grid, where "
            "the plane is carried beyond its points",
        ]
        if self.mount is not None:
            lines.append(f"each shim fits a {self.mount.said()}")
        if self.bound is not None:
            lines.append(
                f"the profile's bound for a stored mesh is {self.bound:g} mm "
                "(measured.mesh_range_bound): "
                + (
                    f"the plane alone leaves {self.bow:.3f}, over it, so no shim brings a "
                    "reading under it"
                    if self.bow >= self.bound
                    else f"the plane leaves {self.bow:.3f}, under it, once the bed is level"
                )
            )
        return lines


def _layers(thickness: float) -> float:
    steps = round((thickness - FIRST_LAYER) / STEP)
    return round(FIRST_LAYER + max(0, steps) * STEP, 4)


def _outside(area: Area, screw: Screw) -> float:
    dx = max(area.x0 - screw.x, 0.0, screw.x - area.x1)
    dy = max(area.y0 - screw.y, 0.0, screw.y - area.y1)
    return math.hypot(dx, dy)


def compute(
    meshes: Sequence[Mesh],
    bed: BedScrews,
    area: Area,
    *,
    runs: Sequence[Run] = (),
    fitted: Optional[Mapping[str, float]] = None,
    bound: Optional[float] = None,
    mount: Optional[Mount] = None,
) -> Shims:
    """The least shims that level the mean of ``meshes`` on ``bed``'s screws.

    The plane's height at screw i is ``h_i``, and ``f_i`` is the shim fitted there now
    (``fitted``, by label or name; none is 0). Every corner is raised to the one that
    stands highest with its shim taken out: the new shim is ``f_i - h_i`` less the
    least of those, so one corner gets none. A shim under one layer
    (``FIRST_LAYER``) or under the repeatability floor is none; each other is rounded to
    a layer (``STEP``).
    """
    fitted = dict(fitted or {})
    given = {s.label for s in bed.screws} | {s.name for s in bed.screws}
    unknown = sorted(set(fitted) - given)
    if unknown:
        raise ShimError(
            f"no screw is called {', '.join(unknown)}: the screws are "
            + ", ".join(f"{s.label} ({s.name})" for s in bed.screws)
        )
    if any(v < 0 for v in fitted.values()):
        raise ShimError("a fitted shim is 0 mm or more")
    mesh = mean_mesh(meshes)
    floor = spread(meshes)
    points = grid_points(mesh, area)
    plane = fit_plane(points)
    residuals = [z - plane.at(x, y) for x, y, z in points]
    rms = math.sqrt(sum(r * r for r in residuals) / len(residuals))
    heights = [plane.at(s.x, s.y) for s in bed.screws]
    now = [float(fitted.get(s.label, fitted.get(s.name, 0.0))) for s in bed.screws]
    want = [n - h for n, h in zip(now, heights, strict=True)]
    least = min(want)
    shims = []
    for s, h, n, w in zip(bed.screws, heights, now, want, strict=True):
        t = w - least
        if t < 1e-9:
            printed, none = None, NONE_HIGHEST
        elif floor is not None and t < floor:
            printed, none = None, NONE_FLOOR
        elif t < FIRST_LAYER:
            printed, none = None, NONE_LAYER
        else:
            printed, none = _layers(t), None
        shims.append(
            Shim(
                screw=s,
                height=round(h, 4),
                fitted=n,
                thickness=round(t, 4),
                printed=printed,
                none=none,
            )
        )
    return Shims(
        runs=tuple(runs),
        screws_from=bed.source,
        area=area,
        plane=plane,
        shims=tuple(shims),
        residual=(round(min(residuals), 4), round(max(residuals), 4), round(rms, 4)),
        floor=None if floor is None else round(floor, 4),
        outside=max(_outside(area, s) for s in bed.screws),
        bound=bound,
        mesh=mesh,
        mount=mount,
    )


# --- a printer's own: its profile, its pinned board, its readings ----------------------


def bed_screws(profile) -> BedScrews:
    """The screws a printer's profile (``slicer.profiles.PrinterProfile``) holds."""
    held = profile.measured.get("bed_screws")
    if held is None:
        raise ShimError(
            f"{profile.file} holds no bed screws (measured.bed_screws): where each levelling "
            "screw stands and the label its shim carries"
        )
    return BedScrews.of(held.value, f"{profile.file} (measured.bed_screws)")


def grid_area(profile, reading) -> Area:
    """Where ``reading``'s grid lies: its own ``area`` (a router's), else the profile's
    ``measured.mesh_area``, else the estimate from the profile's volume and the
    reading's probe offset."""
    if reading.area:
        a = reading.area
        return Area(a["min"]["x"], a["min"]["y"], a["max"]["x"], a["max"]["y"], "the reading")
    held = profile.measured.get("mesh_area")
    if held is not None:
        v = held.value
        return Area(
            float(v["min"]["x"]),
            float(v["min"]["y"]),
            float(v["max"]["x"]),
            float(v["max"]["y"]),
            f"{profile.file} (measured.mesh_area)",
        )
    volume = profile.measured.get("build_volume")
    if volume is None:
        raise ShimError(
            f"{profile.file}: a printer's grid is placed by its volume (measured.build_volume) "
            "when nothing says where it lies (measured.mesh_area)"
        )
    offset = reading.probe_offset
    if offset is None and profile.measured.get("probe_offset") is not None:
        offset = profile.measured["probe_offset"].value
    return grid_area_estimate(volume.value, offset)


def range_bound(profile) -> Optional[float]:
    """The profile's ``measured.mesh_range_bound``, mm, when it holds a number."""
    held = profile.measured.get("mesh_range_bound")
    value = held.value if held is not None else None
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def pinned_board(site: str, printer: str, state=None) -> str:
    """The key of the board pinned at ``printer``'s node in ``site``, or beneath it (a
    printer's pin is its mainboard's): what its readings are kept under."""
    from .firmware import devices

    # The state file as it is now, read: never the server's cached one, which names the
    # folder it was first asked in.
    state = state or devices.FirmwareState()
    keys = sorted(
        {
            b.identity
            for b in state.bindings(site)
            if (b.path == printer or b.path.startswith(printer + "."))
            and b.kind in (None, "printer")
        }
    )
    if not keys:
        raise ShimError(
            f"no board is pinned at {printer} in {site}: a reading is kept under its board, "
            "so pin the printer's board first (its node's ring, Device › Pin)"
        )
    if len(keys) > 1:
        raise ShimError(f"{printer} in {site} has boards {', '.join(keys)} pinned: one only")
    return keys[0]


def readings(board: str):
    """The printer readings kept under ``board``'s key, newest first: read from the state
    folder, whichever port the board is on, and with no port touched."""
    from .firmware import devices

    return [
        r
        for r in devices.leveling_records()
        if r.machine == "printer" and r.board.lower() == board.lower()
    ]


def run_of(record) -> Run:
    """A kept reading (``LevelingRecord``) as a run."""
    return Run(
        id=record.id, at=record.at, method=record.method, bed_c=record.bed_c, note=record.note
    )


def heated_pair(found) -> list:
    """The readings shims are computed from when none is named: the newest probe, and
    the probe before it too when both are heated -- the pair the bench takes one after
    the other. A read of the mesh the board stores (``M420 V``) is not known to be the
    bed, and is never chosen unnamed."""
    probes = [r for r in found if r.method == "probe"]
    pair = probes[:2]
    if len(pair) == 2 and all(run_of(r).heated for r in pair):
        return pair
    return probes[:1]


def mounts_file() -> Path:
    """Where each machine's mount is kept: the state folder's ``bed/mounts.json``, a
    machine's ``site/printer`` its key. Machine state: never committed."""
    return state_dir() / "bed" / "mounts.json"


def _mounts() -> Dict[str, dict]:
    try:
        held = json.loads(mounts_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return held if isinstance(held, dict) else {}


def _defaults() -> Tuple[float, float]:
    from .projects.parts.bed_shims import Params

    at = Params()
    return float(at.hole), float(at.outer_d)


def mount(site: str, printer: str) -> Mount:
    """What ``printer``'s shims fit: what is kept for it, else the part's defaults."""
    hole, outer = _defaults()
    held = _mounts().get(f"{site}/{printer}") or {}
    return Mount(
        hole_d=float(held.get("hole_d", hole)),
        outer_d=float(held.get("outer_d", outer)),
        hole_kept="hole_d" in held,
        outer_kept="outer_d" in held,
        screw=held.get("screw"),
        at=held.get("at"),
    )


def keep_mount(
    site: str,
    printer: str,
    *,
    screw: Optional[str] = None,
    hole_d: Optional[float] = None,
    outer_d: Optional[float] = None,
) -> Mount:
    """Keep what a person measured of ``printer``'s mounts: the bed screw (``screw``,
    which sets the hole as the part's ``screw`` does), the hole typed over it (``hole_d``) and the
    mount's outer diameter (``outer_d``). What is not given stays as it was kept, or the
    part's default. Checked as the part checks its parameters; ShimError says why not."""
    from pydantic import ValidationError

    from .projects.parts.bed_shims import SCREW_HOLES, Params

    printer_part(site, printer)  # a printer of the site, or ShimError
    if screw is not None and screw not in SCREW_HOLES:
        raise NotAMount(f"a bed screw is {' or '.join(SCREW_HOLES)}, not {screw!r}")
    if screw is None and hole_d is None and outer_d is None:
        raise NotAMount("nothing to keep: the bed screw, the hole or the mount's outer diameter")
    held = _mounts()
    now = dict(held.get(f"{site}/{printer}") or {})
    if screw is not None:
        now["screw"] = screw
        now["hole_d"] = SCREW_HOLES[screw]
    if hole_d is not None:
        now["hole_d"] = float(hole_d)
        if screw is None:
            now.pop("screw", None)  # a hole typed alone is no longer the screw's own
    if outer_d is not None:
        now["outer_d"] = float(outer_d)
    hole, outer = _defaults()
    try:
        Params(hole_d=now.get("hole_d", hole), outer_d=now.get("outer_d", outer))
    except ValidationError as exc:
        raise NotAMount(f"not a mount a shim fits: {exc.errors()[0]['msg']}") from None
    now["at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    held[f"{site}/{printer}"] = now
    write_whole(mounts_file(), json.dumps(held, indent=2) + "\n")
    return mount(site, printer)


def printer_part(site: str, printer: str) -> str:
    """The part ``printer``'s node in ``site`` is built from: the one whose profile it
    keeps."""
    from . import sites
    from .hierarchy import find_node_by_path

    try:
        node = find_node_by_path(sites.store.get(site), printer)
    except KeyError as exc:
        raise ShimError(f"no site called {site!r}") from exc
    if node is None or not node.part_ref:
        raise ShimError(f"{site} has no printer at {printer}")
    return node.part_ref


def printer_profile(site: str, printer: str):
    from .slicer.modules import SlicerError
    from .slicer.profiles import load_profile

    try:
        return load_profile(printer_part(site, printer))
    except SlicerError as exc:
        raise ShimError(str(exc)) from exc


def for_printer(
    site: str,
    printer: str,
    *,
    reading_ids: Sequence[str] = (),
    fitted: Optional[Mapping[str, float]] = None,
) -> Shims:
    """The shims for ``printer`` in ``site`` from the readings of its pinned board named
    by ``reading_ids``, else its newest heated pair (``heated_pair``)."""
    profile = printer_profile(site, printer)
    bed = bed_screws(profile)
    board = pinned_board(site, printer)
    found = readings(board)
    if reading_ids:
        by_id = {r.id: r for r in found}
        missing = [i for i in reading_ids if i not in by_id]
        if missing:
            raise ShimError(f"{board} has no reading {', '.join(missing)}")
        chosen = [by_id[i] for i in reading_ids]
    else:
        chosen = heated_pair(found)
    if not chosen:
        raise ShimError(
            f"{board}, pinned at {printer} in {site}, has no probe of its bed: Probe bed first "
            "(its Machine's Bed level)"
        )
    empty = [r.id for r in chosen if not r.mesh]
    if empty:
        raise ShimError(f"no mesh in the reading {', '.join(empty)}")
    return compute(
        [r.mesh for r in chosen],
        bed,
        grid_area(profile, chosen[0]),
        runs=[run_of(r) for r in chosen],
        fitted=fitted,
        bound=range_bound(profile),
        mount=mount(site, printer),
    )


# --- as JSON: what `bed shims --json-out` says, and the page draws ----------------------


def mesh_range(mesh) -> float:
    flat = [v for row in mesh for v in row]
    return max(flat) - min(flat)


def run_json(run: Run) -> dict:
    return {
        "id": run.id,
        "at": run.at.isoformat() if run.at else None,
        "method": run.method,
        "bed_c": run.bed_c,
        "heated": run.heated,
        "note": run.note,
    }


def mount_json(found: Mount) -> dict:
    return {
        "hole_d": found.hole_d,
        "outer_d": found.outer_d,
        "hole_kept": found.hole_kept,
        "outer_kept": found.outer_kept,
        "screw": found.screw,
        "at": found.at,
        "said": found.said(),
    }


def as_json(found: Shims) -> dict:
    """What ``bed shims --json-out`` says, and the page draws."""
    least, most, rms = found.residual
    return {
        "runs": [run_json(r) for r in found.runs],
        "screws_from": found.screws_from,
        "grid": {
            "x": [found.area.x0, found.area.x1],
            "y": [found.area.y0, found.area.y1],
            "from": found.area.source,
        },
        "mesh": found.mesh,
        "range": mesh_range(found.mesh),
        "tilt": {"x_per_100mm": found.plane.a * 100, "y_per_100mm": found.plane.b * 100},
        "floor": found.floor,
        "shims": [
            {
                "name": s.screw.name,
                "label": s.screw.label,
                "x": s.screw.x,
                "y": s.screw.y,
                "plane": s.height,
                "fitted": s.fitted,
                "thickness": s.thickness,
                "printed": s.printed,
                "none": s.none,
            }
            for s in found.shims
        ],
        "residual": {"min": least, "max": most, "rms": rms, "range": round(found.bow, 4)},
        "bow": found.bow_mesh(),
        "bound": found.bound,
        "left": round(found.left, 4),
        "outside": round(found.outside, 2),
        "mount": mount_json(found.mount) if found.mount else None,
        "params": found.params(),
        "slice": found.slice_command(),
    }


# --- what the page draws: a printer's readings, their differences, its shims ----------


def heated_pairs(found) -> list:
    """The heated pairs among a board's probes, newest first: two heated probes one after
    the other, of one grid. A probe that is cold, or heated beside a cold one, is in
    none."""
    probes = [r for r in found if r.method == "probe" and r.mesh]
    out, i = [], 0
    while i + 1 < len(probes):
        a, b = probes[i], probes[i + 1]
        if run_of(a).heated and run_of(b).heated and _shape(a.mesh) == _shape(b.mesh):
            out.append((a, b))
            i += 2
        else:
            i += 1
    return out


def story(site: str, printer: str) -> dict:
    """A printer's readings, their differences and its shims, as the page's windows draw
    them: every reading of its pinned board, newest first; the shims from the newest
    heated pair (else the newest probe); that pair's newer less its older, the floor; the
    newest pair less the pair before it, what was done between them; and the bow."""
    profile = printer_profile(site, printer)
    bed = bed_screws(profile)
    board = pinned_board(site, printer)
    found = readings(board)
    pairs = heated_pairs(found)
    runs = [
        {
            **run_json(run_of(r)),
            "range": r.stats.get("range") if r.mesh else None,
            "mesh": r.mesh,
            "machine": r.machine,
            "port": r.port,
            "probe_offset": r.probe_offset,
            "area": r.area,
        }
        for r in found
    ]
    try:
        shims = as_json(for_printer(site, printer))
    except ShimError as exc:
        shims = {"error": str(exc)}
    differences: dict = {}
    if pairs:
        newer, older = pairs[0]
        moved = difference([older.mesh], [newer.mesh])
        differences["repeatability"] = {
            "of": [older.id, newer.id],
            "mesh": moved,
            "floor": spread([older.mesh, newer.mesh]),
        }
    if len(pairs) >= 2:
        differences["after"] = {
            "before": [r.id for r in reversed(pairs[1])],
            "after": [r.id for r in reversed(pairs[0])],
            "mesh": difference([r.mesh for r in pairs[1]], [r.mesh for r in pairs[0]]),
        }
    if "error" not in shims:
        differences["bow"] = {
            "mesh": shims["bow"],
            "range": shims["residual"]["range"],
            "bound": shims["bound"],
        }
    volume = profile.measured.get("build_volume")
    return {
        "site": site,
        "printer": printer,
        "board": board,
        "runs": runs,
        "pairs": [[r.id for r in reversed(p)] for p in pairs],
        "shims": shims,
        "differences": differences,
        "bound": range_bound(profile),
        "volume": list(volume.value[:2]) if volume is not None else None,
        "screws": [{"name": s.name, "label": s.label, "x": s.x, "y": s.y} for s in bed.screws],
        "mount": mount_json(mount(site, printer)),
    }
