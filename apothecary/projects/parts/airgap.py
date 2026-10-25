"""
Airgap - a rotor/stator pair of any base form, with the conductors that wind it.

The part is its SCAD: ``parts/airgap/airgap.scad`` computes every surface from its own
top-level assignments, so the rotor, the stator and the windings are edited as text in the
page (Part > Edit) and a saved variant carries its values. This module is the Python mirror
of that pipeline, in the same degrees and the same order, for what Python has to know
without running OpenSCAD: the envelope a set of values renders to, the conductor stations
a winding reduces to, and a check that the two agree (``tests/test_airgap_part.py`` runs the
SCAD with ``-D echo_surfaces=true`` and compares).

Each surface starts from a base curve (circle, ellipse, superellipse, rounded polygon or a
constant-width support curve), is scaled in its own frame by
``spiral(psi) * (1 + ribbon(psi)) * (1 + teeth(psi))`` -- a nautilus step, a Mobius ribbon's
reach, fractal gearing -- then rotated and offset from the machine axis and re-sampled as a
polar profile about that axis. The bore scale ``s0`` is solved so the closest approach over
every rotor angle equals the nominal air gap. Windings reduce to conductor stations (a
signed turn count at a stator angle): tooth coils, lap coils, wave windings, toroidal belts,
an ideal sinusoidal sheet, or explicit stations.

The model's groups (``rotor``, ``stator``, ``windings``) hold fields named as the SCAD names
them (``rotor_base_form``), so a control writes its own line of the text; the flat form the
analysis panel exports (``{"rotor_base_form": ...}``) is accepted and ``flat()`` gives it back.

Units: mm and degrees. Ratios are of r0.

Tools: drafted with Claude Code (Anthropic); a human ratifies before merge.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, Tuple, Type

from pydantic import BaseModel, Field, create_model, model_validator

from apothecary.models import BoundingBox3D, Color, Vector3D

from .base import BasePart
from .skeleton import ROOT

MM = {"unit": "mm"}
DEG = {"unit": "deg"}
PHASES = "ABCDEF"

BaseForm = Literal["circle", "ellipse", "superellipse", "polygon", "constwidth"]
RibbonMode = Literal["single", "envelope", "woven"]
ToothForm = Literal["trap", "sine", "tri", "saw"]
OuterForm = Literal["concentric", "round", "square", "hex"]
Topology = Literal["tooth", "lap", "wave", "toroidal", "sinusoidal", "custom"]
Pattern = Literal["diametral", "sequential", "paired", "custom"]

# One side's fields: (name, type, default, Field keywords). The SCAD's literals are these
# defaults; ``tests/test_defaults_are_the_scad.py`` holds the two together.
SIDE_FIELDS: List[Tuple[str, Any, Any, Dict[str, Any]]] = [
    ("base_form", BaseForm, "circle", dict(description="base curve")),
    ("base_ratio", float, 0.8, dict(ge=0.2, le=1, description="minor/major axis of an ellipse")),
    ("base_exp", float, 4.0, dict(ge=1, le=12, description="superellipse exponent")),
    ("base_sides", int, 4, dict(ge=3, le=16, description="polygon sides")),
    ("base_round", float, 0.3, dict(ge=0, le=1, description="polygon rounding, 1 is a circle")),
    ("base_width_k", int, 3, dict(ge=3, le=15, description="constant-width lobes (odd)")),
    ("base_width_a", float, 0.08, dict(ge=0, le=0.3, description="constant-width lobe depth")),
    (
        "rot",
        float,
        0.0,
        dict(ge=-180, le=180, description="rotation about its own centre", json_schema_extra=DEG),
    ),
    ("off_x", float, 0.0, dict(ge=-0.4, le=0.4, description="offset from the axis, x r0")),
    ("off_y", float, 0.0, dict(ge=-0.4, le=0.4, description="offset from the axis, x r0")),
    ("spiral_b", float, 0.0, dict(ge=0, le=2, description="nautilus growth per turn, 0 is none")),
    ("spiral_k", int, 2, dict(ge=1, le=16, description="nautilus steps per revolution")),
    ("spiral_s", float, 0.8, dict(ge=0, le=1, description="step sharpness")),
    ("rib_k", int, 0, dict(ge=0, le=32, description="Mobius ribbon lobes, 0 is none")),
    ("rib_w", float, 0.1, dict(ge=0, le=0.5, description="ribbon reach")),
    ("rib_p", float, 1.0, dict(ge=0.1, le=6, description="ribbon lobe sharpness")),
    ("rib_mode", RibbonMode, "envelope", dict(description="how the ribbon's two lobes combine")),
    ("teeth_n", int, 0, dict(ge=0, le=256, description="teeth, 0 is none")),
    ("teeth_h", float, 0.08, dict(ge=0, le=0.5, description="tooth height")),
    ("teeth_l", int, 0, dict(ge=0, le=6, description="fractal levels under each tooth")),
    ("teeth_m", int, 3, dict(ge=2, le=8, description="teeth per tooth, each level down")),
    ("teeth_rho", float, 0.5, dict(ge=0, le=0.99, description="height ratio, each level down")),
    ("teeth_shape", ToothForm, "trap", dict(description="tooth profile")),
]
ROTOR_DEFAULTS = {"spiral_b": 0.35, "spiral_s": 0.85, "rib_k": 3, "rib_w": 0.12}
STATOR_DEFAULTS = {"teeth_n": 12, "teeth_l": 3}
STATOR_EXTRA: List[Tuple[str, Any, Any, Dict[str, Any]]] = [
    ("cov_segs", int, 1, dict(ge=1, le=24, description="stator segments")),
    (
        "cov_arc",
        float,
        1.0,
        dict(ge=0.05, le=1, description="fraction of the ring the segments cover"),
    ),
    (
        "cov_rot",
        float,
        0.0,
        dict(
            ge=-180, le=180, description="where the first segment is centred", json_schema_extra=DEG
        ),
    ),
    ("outer_form", OuterForm, "concentric", dict(description="frame behind the yoke")),
    (
        "yoke",
        float,
        6.0,
        dict(ge=1, le=60, description="yoke thickness behind the teeth", json_schema_extra=MM),
    ),
]


def _side_model(prefix: str, overrides: Mapping[str, Any], extra=()) -> Type[BaseModel]:
    fields: Dict[str, Any] = {}
    for name, kind, default, kw in list(SIDE_FIELDS) + list(extra):
        fields[f"{prefix}_{name}"] = (kind, Field(overrides.get(name, default), **kw))
    return create_model(f"{prefix.capitalize()}Side", **fields)


RotorSide = _side_model("rotor", ROTOR_DEFAULTS)
StatorSide = _side_model("stator", STATOR_DEFAULTS, STATOR_EXTRA)


class Windings(BaseModel):
    """The conductor arrangement, as the SCAD's ``[Windings]`` section names it."""

    topology: Topology = Field("tooth", description="how the conductors are arranged")
    phases: int = Field(3, ge=0, le=6)
    pattern: Pattern = Field("diametral", description="which phase and sense each slot gets")
    layout: str = Field("", description="slot string when pattern is custom: A+ A+ C- C- B+ B+ ...")
    custom_stations: str = Field(
        "", description="when topology is custom: A: 0:50 90:-50; B: 30:50 (deg:turns)"
    )
    turns: int = Field(50, ge=1, le=1000, description="turns per coil")
    span: float = Field(0.6, ge=0.05, le=1, description="tooth coil span, in slot pitches")
    pitch: int = Field(1, ge=1, le=48, description="lap coil pitch, in slots")
    slots: int = Field(0, ge=0, le=256, description="slots; 0 is one per stator tooth")
    skew_deg: float = Field(
        0.0, ge=0, le=90, description="conductor skew over the stack", json_schema_extra=DEG
    )
    wire_d: float = Field(
        1.2, ge=0.2, le=20, description="conductor bundle diameter", json_schema_extra=MM
    )
    pole_pairs: int = Field(4, ge=1, le=32, description="of a sinusoidal sheet")


GROUPS = ("rotor", "stator", "windings")


class Params(BaseModel):
    """The airgap's parameters: the SCAD's top-level assignments, grouped as its sections are."""

    r0: float = Field(30.0, ge=5, le=200, description="rotor base radius", json_schema_extra=MM)
    stack: float = Field(20.0, ge=2, le=200, description="axial stack length", json_schema_extra=MM)
    gap: float = Field(1.5, ge=0.1, le=10, description="nominal air gap", json_schema_extra=MM)
    phi: float = Field(0.0, ge=0, le=360, description="rotor angle", json_schema_extra=DEG)
    resolution: int = Field(360, ge=72, le=1440, description="polar samples about the axis")
    show_rotor: bool = True
    show_stator: bool = True
    show_windings: bool = True
    rotor: RotorSide = Field(default_factory=RotorSide)  # type: ignore[valid-type]
    stator: StatorSide = Field(default_factory=StatorSide)  # type: ignore[valid-type]
    windings: Windings = Field(default_factory=Windings)

    @model_validator(mode="before")
    @classmethod
    def _gather_flat(cls, data: Any) -> Any:
        """The flat form (``rotor_base_form`` beside ``r0``) folds into its groups."""
        if not isinstance(data, Mapping):
            return data
        data = dict(data)
        groups = {g: dict(data.pop(g, None) or {}) for g in GROUPS}
        for key in list(data):
            for g in GROUPS:
                names = _group_names(g)
                if key in names:
                    groups[g][key] = data.pop(key)
                    break
        for g in GROUPS:
            if groups[g]:
                data[g] = groups[g]
        return data

    def flat(self) -> Dict[str, Any]:
        """Every SCAD assignment name with its value, in the file's order."""
        out: Dict[str, Any] = {}
        for name in (
            "r0",
            "stack",
            "gap",
            "phi",
            "resolution",
            "show_rotor",
            "show_stator",
            "show_windings",
        ):
            out[name] = getattr(self, name)
        for g in GROUPS:
            out.update(getattr(self, g).model_dump())
        return out

    def side(self, prefix: str) -> "Side":
        group = getattr(self, prefix)
        return Side(**{n: getattr(group, f"{prefix}_{n}") for n, *_ in SIDE_FIELDS})


def _group_names(group: str) -> set:
    model = {"rotor": RotorSide, "stator": StatorSide, "windings": Windings}[group]
    return set(model.model_fields)


@dataclass(frozen=True)
class Side:
    """One side's feature stack, unprefixed, for the functions below."""

    base_form: str
    base_ratio: float
    base_exp: float
    base_sides: int
    base_round: float
    base_width_k: int
    base_width_a: float
    rot: float
    off_x: float
    off_y: float
    spiral_b: float
    spiral_k: int
    spiral_s: float
    rib_k: int
    rib_w: float
    rib_p: float
    rib_mode: str
    teeth_n: int
    teeth_h: float
    teeth_l: int
    teeth_m: int
    teeth_rho: float
    teeth_shape: str


# ---- small helpers, as the SCAD has them (degrees) ---------------------------------------------


def frac(x: float) -> float:
    return x - math.floor(x)


def mod360(a: float) -> float:
    return a - 360 * math.floor(a / 360)


def _cos(d: float) -> float:
    return math.cos(math.radians(d))


def _sin(d: float) -> float:
    return math.sin(math.radians(d))


def _atan2(y: float, x: float) -> float:
    return math.degrees(math.atan2(y, x))


def spow(x: float, e: float) -> float:
    return math.copysign(abs(x) ** e, x) if x != 0 else 0.0


def bsearch(u: Sequence[float], t: float, lo: int, hi: int) -> int:
    """Largest k in [lo, hi) with u[k] <= t, for u ascending and u[lo] <= t."""
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if u[mid] <= t:
            lo = mid
        else:
            hi = mid
    return lo


def interp(arr: Sequence[float], x: float) -> float:
    n = len(arr)
    i0 = math.floor(x)
    f = x - i0
    a = i0 % n
    b = (a + 1) % n
    return arr[a] * (1 - f) + arr[b] * f


# ---- feature stack of one side, psi in degrees of its own frame --------------------------------


def wave(x: float, form: str) -> float:
    if form == "sine":
        return 0.5 + 0.5 * _sin(x)
    if form == "trap":
        return 0.5 + 0.5 * max(-1.0, min(1.0, 2.5 * _sin(x)))
    if form == "tri":
        u = frac(x / 360) * 2
        return 1 - abs(u - 1)
    return frac(x / 360 + 1e-9)  # a saw's drop nudged off the sample grid, as the SCAD does


def peak(form: str) -> float:
    return 180.0 if form == "tri" else 360 * 0.999 if form == "saw" else 90.0


def spiral(s: Side, th: float) -> float:
    if s.spiral_b <= 0:
        return 1.0
    b = s.spiral_b
    d = max(0.02, 0.5 * (1 - s.spiral_s))
    u = frac(s.spiral_k * th / 360)
    eb = math.exp(-b)
    if u < 1 - d:
        return math.exp(b * (u / (1 - d) - 1))
    t = (u - (1 - d)) / d
    return eb + (1 - eb) * (1 + _cos(180 * t)) / 2


def ribbon(s: Side, th: float) -> float:
    if s.rib_k <= 0 or s.rib_w <= 0:
        return 0.0
    a = s.rib_w * abs(_cos(s.rib_k * th / 2)) ** s.rib_p
    if s.rib_mode == "single":
        return a
    b = s.rib_w * abs(_sin(s.rib_k * th / 2)) ** s.rib_p
    if s.rib_mode == "envelope":
        return max(a, b)
    return (a + b) / max(1.0, 2 ** (1 - s.rib_p / 2))


def teeth(s: Side, th: float) -> float:
    if s.teeth_n <= 0 or s.teeth_h <= 0:
        return 0.0
    acc = sum(
        s.teeth_rho**j * wave(s.teeth_n * s.teeth_m**j * th, s.teeth_shape)
        for j in range(s.teeth_l + 1)
    )
    norm = sum(s.teeth_rho**j for j in range(s.teeth_l + 1))
    return s.teeth_h * acc / norm


def f_full(s: Side, th: float) -> float:
    return spiral(s, th) * (1 + ribbon(s, th)) * (1 + teeth(s, th))


def f_no_teeth(s: Side, th: float) -> float:
    return spiral(s, th) * (1 + ribbon(s, th))


def f_core(s: Side, th: float) -> float:
    return spiral(s, th) * (1 + teeth(s, th))


# ---- base forms, placement, re-sampling (unit: r0) -----------------------------------------


def base_point(s: Side, t: float) -> Tuple[float, float]:
    c, sn = _cos(t), _sin(t)
    if s.base_form == "ellipse":
        return c, s.base_ratio * sn
    if s.base_form == "superellipse":
        e = 2 / s.base_exp
        return spow(c, e), s.base_ratio * spow(sn, e)
    if s.base_form == "polygon":
        k = s.base_sides
        sec = 360 / k
        u = t - sec * math.floor(t / sec)
        rp = _cos(180 / k) / _cos(u - 180 / k)
        r = (1 - s.base_round) * rp + s.base_round
        return r * c, r * sn
    if s.base_form == "constwidth":
        k = s.base_width_k
        a = min(s.base_width_a, 0.95 / (k * k - 1))
        h = 1 + a * _cos(k * t)
        hp = -a * k * _sin(k * t)
        return h * c - hp * sn, h * sn + hp * c
    return c, sn


def own_curve(s: Side, is_stator: bool, m: int) -> List[Tuple[float, float, float, float, float]]:
    """Own-frame curve scaled by the feature stack: (x, y, x_root, y_root, psi) per sample."""
    out = []
    for i in range(m):
        t = i * 360 / m
        bx, by = base_point(s, t)
        psi = mod360(_atan2(by, bx))
        fac = (2 - f_full(s, psi)) if is_stator else f_full(s, psi)
        fac_r = (2 - f_no_teeth(s, psi)) if is_stator else f_core(s, psi)
        out.append((bx * fac, by * fac, bx * fac_r, by * fac_r, psi))
    return out


def placed(pts, scale: float, s: Side, ix: int = 0, iy: int = 1) -> List[Tuple[float, float]]:
    c, sn = _cos(s.rot), _sin(s.rot)
    out = []
    for p in pts:
        x, y = p[ix] * scale, p[iy] * scale
        out.append((x * c - y * sn + s.off_x, x * sn + y * c + s.off_y))
    return out


def resample(P, psis: Optional[Sequence[float]], nt: int) -> List[Tuple[float, float]]:
    """Polar re-sample about the axis: (r, psi) at each of nt axis angles."""
    m = len(P)
    ang = [mod360(_atan2(p[1], p[0])) for p in P]
    rad = [math.hypot(p[0], p[1]) for p in P]
    a0 = ang[0]
    u = [mod360(a - a0) for a in ang]
    out = []
    for j in range(nt):
        th = mod360(j * 360 / nt - a0)
        k = bsearch(u, th, 0, m)
        k1 = (k + 1) % m
        t0 = u[k]
        t1 = u[0] + 360 if k == m - 1 else u[k1]
        f = (th - t0) / (t1 - t0) if t1 > t0 else 0.0
        r = rad[k] * (1 - f) + rad[k1] * f
        psi = 0.0
        if psis is not None:
            d0 = psis[k1] - psis[k]
            d = d0 - 360 if d0 > 180 else d0 + 360 if d0 < -180 else d0
            psi = mod360(psis[k] + d * f)
        out.append((r, psi))
    return out


def covered(psi: float, segs: int, arc: float, rot: float) -> bool:
    if arc >= 1:
        return True
    half = min(1.0, arc) * 180 / segs
    for k in range(segs):
        d0 = mod360(abs(psi - rot - 360 * k / segs))
        d = 360 - d0 if d0 > 180 else d0
        if d <= half + 1e-9:
            return True
    return False


def outer_own(own, s0: float, form: str, yk: float) -> List[Tuple[float, float]]:
    m = len(own)
    rmax = max(math.hypot(p[2], p[3]) * s0 for p in own)
    out = []
    for i in range(m):
        t = i * 360 / m
        p = own[i]
        if form == "concentric":
            rr = math.hypot(p[2], p[3]) * s0
            f = (rr + yk) / rr
            out.append((p[2] * s0 * f, p[3] * s0 * f))
        elif form == "round":
            out.append(((rmax + yk) * _cos(t), (rmax + yk) * _sin(t)))
        else:
            k = 4 if form == "square" else 6
            sec = 360 / k
            off = 45.0 if k == 4 else 0.0
            u = (t - off) - sec * math.floor((t - off) / sec)
            rr = (rmax + yk) / _cos(u - sec / 2)
            out.append((rr * _cos(t), rr * _sin(t)))
    return out


# ---- the surfaces, solved once --------------------------------------------------------------


@dataclass
class Surfaces:
    """Polar profiles about the axis in units of r0, the coverage mask, the own-angle map."""

    rotor_r: List[float]
    bore_r: List[float]
    outer_r: List[float]
    mask: List[int]
    psi_s: List[float]
    s0: float

    @property
    def nt(self) -> int:
        return len(self.rotor_r)


def build_surfaces(p: Params, nt: Optional[int] = None, m: int = 2880) -> Surfaces:
    """As the SCAD's ``surfaces(resolution, own_samples)``."""
    nt = nt or p.resolution
    rs, ss = p.side("rotor"), p.side("stator")
    g0 = p.gap / p.r0
    rown = own_curve(rs, False, m)
    sown = own_curve(ss, True, m)
    R = [q[0] for q in resample(placed(rown, 1.0, rs), [q[4] for q in rown], nt)]
    target = max(R) + g0

    def min_bore(s0: float) -> float:
        return min(q[0] for q in resample(placed(sown, s0, ss), None, nt))

    sa, ma = 1.0, min_bore(1.0)
    sb = 1 + (target - ma)
    mb = min_bore(sb)
    it = 0
    while not (it >= 6 or abs(mb - target) <= 1e-9):
        sn = (
            sb + (target - mb) * (sb - sa) / (mb - ma)
            if abs(mb - ma) > 1e-12
            else sb + (target - mb)
        )
        sa, ma, sb = sb, mb, sn
        mb = min_bore(sb)
        it += 1
    s0 = sb
    sres = resample(placed(sown, s0, ss), [q[4] for q in sown], nt)
    S = [q[0] for q in sres]
    psi_s = [q[1] for q in sres]
    st = p.stator
    mask = [
        1 if covered(v, st.stator_cov_segs, st.stator_cov_arc, st.stator_cov_rot) else 0
        for v in psi_s
    ]
    oown = outer_own(sown, s0, st.stator_outer_form, st.stator_yoke / p.r0)
    outer = [q[0] for q in resample(placed(oown, 1.0, ss), None, nt)]
    return Surfaces(R, S, outer, mask, psi_s, s0)


# ---- windings: everything becomes conductor stations ------------------------------------------


def _phase_of(c: str) -> Optional[int]:
    u = c.upper()
    return PHASES.index(u) if u in PHASES else None


def _slot_token(t: str) -> Optional[Tuple[int, int, float]]:
    mt = re.match(r"^([A-Fa-f])([+\-−]?)(?:[x×]?([+\-−]?\d*(?:\.\d+)?))?$", t)
    if not mt:
        return None
    ph = _phase_of(mt.group(1))
    sg = -1 if mt.group(2) in ("-", "−") else 1
    mult = float(mt.group(3).replace("−", "-")) if mt.group(3) else 1.0
    return (ph, sg, mult)  # type: ignore[return-value]


def parse_layout(s: str) -> List[Tuple[int, int, float]]:
    out = []
    for t in re.split(r"[ ,;\n\t]+", s):
        if not t:
            continue
        c = _slot_token(t)
        if c is not None:
            out.append(c)
    return out


def layout_for(w: Windings, n: int) -> List[Tuple[int, int, float]]:
    m = max(1, w.phases)
    if w.pattern == "custom":
        toks = parse_layout(w.layout)
        return [toks[i % len(toks)] for i in range(n)] if toks else []
    out = []
    for i in range(n):
        if w.pattern == "sequential":
            out.append((i % m, 1, 1.0))
        elif w.pattern == "paired":
            out.append(((i // 2) % m, 1 if i % 2 == 0 else -1, 1.0))
        else:
            out.append((i % m, 1 if i < n / 2 else -1, 1.0))
    return out


def parse_custom(s: str) -> List[Tuple[int, float, float]]:
    """``A: 0:50 90:-50; B: 30:50`` -> [(phase, theta, turns), ...], as the SCAD reads it."""
    out = []
    for line in re.split(r"[;\n]+", s):
        toks = [t for t in re.split(r"[ ,\t]+", line) if t]
        if not toks:
            continue
        ph = _phase_of(toks[0][0])
        if ph is None:
            continue
        for t in toks[1:]:
            mt = re.match(r"^([+\-−]?\d*(?:\.\d+)?):([+\-−]?\d*(?:\.\d+)?)$", t)
            if mt and mt.group(1).strip("+-−") and mt.group(2).strip("+-−"):
                a = float(mt.group(1).replace("−", "-"))
                b = float(mt.group(2).replace("−", "-"))
                out.append((ph, mod360(a), b))
    return out


Station = Tuple[float, float, int, str]  # theta, turns, phase, kind
Coil = Tuple[int, int, float, float, float, float, float, float, str]


@dataclass
class Winding:
    stations: List[Station]
    coils: List[Coil]
    phases: int


def build_winding(p: Params, sf: Surfaces) -> Winding:
    """As the SCAD's ``winding()``: stations [theta, turns, phase, kind] and tooth/lap coils."""
    w, st = p.windings, p.stator
    nt = sf.nt
    psi0 = sf.psi_s[0]
    psi_u = [mod360(v - psi0) for v in sf.psi_s]

    def theta_of_psi(psi: float) -> float:
        v = mod360(psi - psi0)
        k = bsearch(psi_u, v, 0, nt)
        k1 = (k + 1) % nt
        t0 = psi_u[k]
        t1 = psi_u[0] + 360 if k == nt - 1 else psi_u[k1]
        f = (v - t0) / (t1 - t0) if t1 > t0 else 0.0
        return mod360((k + f) * 360 / nt)

    def cov(psi: float) -> bool:
        return covered(psi, st.stator_cov_segs, st.stator_cov_arc, st.stator_cov_rot)

    if w.topology == "sinusoidal":
        return Winding([], [], max(1, w.phases))
    if w.topology == "custom":
        sts = parse_custom(w.custom_stations)
        return Winding(
            [(s[1], s[2], s[0], "bar") for s in sts], [], max([s[0] + 1 for s in sts], default=0)
        )
    n = w.slots if w.slots > 0 else st.stator_teeth_n
    if n <= 0:
        return Winding([], [], 0)
    lay = layout_for(w, n)
    if not lay:
        return Winding([], [], 0)
    m = max(c[0] + 1 for c in lay)
    pitch = 360 / n

    def tooth_psi(i: int) -> float:
        if st.stator_teeth_n > 0 and w.slots == 0:
            return (peak(st.stator_teeth_shape) + 360 * i) / st.stator_teeth_n
        return 360 * (i + 0.5) / n

    stations: List[Station] = []
    coils: List[Coil] = []
    if w.topology == "tooth":
        sp = min(360.0, w.span * pitch)
        for i in range(n):
            c = lay[i]
            psi = tooth_psi(i)
            if not cov(psi):
                continue
            nT = c[2] * w.turns * c[1]
            a, b = theta_of_psi(psi - sp / 2), theta_of_psi(psi + sp / 2)
            stations += [(a, nT, c[0], "coil"), (b, -nT, c[0], "coil")]
            coils.append((c[0], c[1], abs(nT), a, b, theta_of_psi(psi), psi, sp, "tooth"))
    elif w.topology == "lap":
        y = max(1, min(n - 1, w.pitch))
        for i in range(n):
            c = lay[i]
            p1, p2 = tooth_psi(i) + pitch / 2, tooth_psi((i + y) % n) + pitch / 2
            if not (cov(p1) and cov(p2)):
                continue
            nT = c[2] * w.turns * c[1]
            a, b = theta_of_psi(p1), theta_of_psi(p2)
            stations += [(a, nT, c[0], "coil"), (b, -nT, c[0], "coil")]
            coils.append(
                (c[0], c[1], abs(nT), a, b, theta_of_psi(p1 + y * pitch / 2), p1, y * pitch, "lap")
            )
    else:
        for i in range(n):
            c = lay[i]
            ps = tooth_psi(i) + pitch / 2
            if not cov(ps):
                continue
            stations.append(
                (
                    theta_of_psi(ps),
                    c[2] * w.turns * c[1],
                    c[0],
                    "toroid" if w.topology == "toroidal" else "bar",
                )
            )
    return Winding(stations, coils, m)


# ---- conductor paths: (phase, diameter, closed, [(x, y, z), ...]) -----------------------------

Path3 = Tuple[int, float, bool, List[Tuple[float, float, float]]]


def conductor_paths(p: Params, sf: Surfaces, wd: Winding) -> List[Path3]:
    """As the SCAD's ``conductor_paths()``, in mm."""
    w, r0, nt = p.windings, p.r0, sf.nt
    wire = w.wire_d
    hz = p.stack / 2 + wire
    ss = p.side("stator")

    def bore_at(th: float) -> float:
        return interp(sf.bore_r, th / 360 * nt) * r0

    def outer_at(th: float) -> float:
        return interp(sf.outer_r, th / 360 * nt) * r0

    def root_at(th: float) -> float:
        return sf.s0 * (2 - f_no_teeth(ss, interp(sf.psi_s, th / 360 * nt))) * r0

    def p3(th, r, z):
        return (r * _cos(th), r * _sin(th), z)

    def bar(th, r, z0, z1):
        k = 4 if w.skew_deg > 0 else 1
        out = []
        for s in range(k + 1):
            u = s / k
            a = th + w.skew_deg * (u - 0.5) * (1 if z1 > z0 else -1)
            out.append(p3(a, r, z0 + (z1 - z0) * u))
        return out

    def arc(t0, t1, r, z, fwd):
        d0 = t1 - t0
        d = mod360(d0) if fwd else mod360(d0 + 180) - 180
        n = max(3, math.ceil(abs(d) / 12))
        return [p3(t0 + d * s / n, r, z) for s in range(1, n)]

    paths: List[Path3] = []
    if w.topology == "sinusoidal":
        nb, m = 48, wd.phases
        for ph in range(m):
            for b in range(nb):
                th = 360 * (b + 0.5) / nb
                v = _cos(w.pole_pairs * th - 360 * ph / m)
                if sf.mask[round(th / 360 * nt) % nt] != 1 or abs(v) < 0.08:
                    continue
                paths.append(
                    (
                        ph,
                        wire * math.sqrt(abs(v)),
                        False,
                        bar(th, bore_at(th) + wire * 0.9 + ph * wire * 1.1, -hz, hz),
                    )
                )
        return paths
    if w.topology == "tooth":
        for c in wd.coils:
            centre, span = c[5], c[7]
            tip, root = bore_at(centre), root_at(centre)
            rm = min(outer_at(centre) - wire, (tip + root) / 2)
            hw = max(wire, rm * math.tan(math.radians(min(68.75, span / 2))))
            ca, sa = _cos(centre), _sin(centre)
            pts = [
                (rm * ca - t * sa, rm * sa + t * ca, z)
                for t, z in ((-hw, -hz), (hw, -hz), (hw, hz), (-hw, hz))
            ]
            paths.append((c[0], wire, True, pts))
        return paths
    if w.topology == "lap":
        for c in wd.coils:
            a, b = c[3], c[4]
            ra, rb = bore_at(a) + wire * 0.9, bore_at(b) + wire * 0.9
            ro = max(ra, rb) + wire
            pts = (
                bar(a, ra, hz, -hz)
                + arc(a, b, ro, -hz - wire * 1.5, True)
                + bar(b, rb, -hz, hz)
                + arc(b, a, ro, hz + wire * 1.5, False)
            )
            paths.append((c[0], wire, True, pts))
        return paths
    if w.topology == "wave":
        for ph in range(wd.phases):
            sts = sorted((s for s in wd.stations if s[2] == ph), key=lambda s: s[0])
            n = len(sts)
            if n < 2:
                continue
            closes = n % 2 == 0
            pts = []
            for k in range(n):
                s = sts[k]
                r = bore_at(s[0]) + wire * 0.9
                down = k % 2 == 0
                pts += bar(s[0], r, hz if down else -hz, -hz if down else hz)
                if k < n - 1 or closes:
                    nx = sts[(k + 1) % n]
                    pts += arc(
                        s[0],
                        nx[0],
                        max(r, bore_at(nx[0]) + wire * 0.9) + wire,
                        -hz - wire * 1.5 if down else hz + wire * 1.5,
                        True,
                    )
            paths.append((ph, wire, closes, pts))
        return paths
    if w.topology == "toroidal":
        for s in wd.stations:
            rin, rout = bore_at(s[0]) + wire * 0.9, outer_at(s[0]) + wire * 0.9
            nl = max(2, min(8, round(abs(s[1]) / 10)))
            dth = wire * 1.3 / rin * 180 / math.pi
            for q in range(nl):
                th = s[0] + (q - (nl - 1) / 2) * dth
                leg = [
                    p3(th, rin, -hz),
                    p3(th, rin, hz),
                    p3(th + dth * 0.5, rout, hz),
                    p3(th + dth * 0.5, rout, -hz),
                ]
                paths.append((s[2], wire, True, leg))
        return paths
    for s in wd.stations:
        paths.append(
            (
                s[2],
                wire * min(2.0, math.sqrt(abs(s[1]) / w.turns)),
                False,
                bar(s[0], bore_at(s[0]) + wire * 0.9, -hz, hz),
            )
        )
    return paths


# ---- the swept bundle, as the SCAD's tube() places its vertices -------------------------------


def _unit(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (0.0, 0.0, 0.0) if n < 1e-12 else (v[0] / n, v[1] / n, v[2] / n)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(v, k):
    return (v[0] * k, v[1] * k, v[2] * k)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(v):
    return math.sqrt(_dot(v, v))


def _first_normal(t):
    return _unit(_cross(t, (0, 0, 1) if abs(t[2]) < 0.9 else (1, 0, 0)))


def tube_points(pts: Sequence[Tuple[float, float, float]], d: float, closed: bool, sides: int = 8):
    """The ring of ``sides`` vertices the SCAD places at every point of a bundle's path: each
    ring's frame carried from the last (no twist), a corner's ring widened by its mitre."""
    n = len(pts)
    tangents, mitres = [], []
    for i in range(n):
        prev = pts[(i - 1) % n] if closed else pts[max(i - 1, 0)]
        nxt = pts[(i + 1) % n] if closed else pts[min(i + 1, n - 1)]
        a, b = _unit(_sub(pts[i], prev)), _unit(_sub(nxt, pts[i]))
        t = _unit(_add(a, b))
        tangents.append((b if _norm(b) > 0 else a) if _norm(t) < 1e-6 else t)
        c = 1.0 if (_norm(a) < 1e-6 or _norm(b) < 1e-6) else max(-1.0, min(1.0, _dot(a, b)))
        mitres.append(min(1.5, 1 / max(0.5, math.sqrt((1 + c) / 2))))
    frames = []
    normal = None
    for t in tangents:
        proj = _first_normal(t) if normal is None else _sub(normal, _mul(t, _dot(normal, t)))
        normal = _first_normal(t) if _norm(proj) < 1e-6 else _unit(proj)
        frames.append((normal, _cross(t, normal)))
    out = []
    for i in range(n):
        f0, f1 = frames[i]
        for j in range(sides):
            a = 360 * j / sides
            out.append(
                _add(pts[i], _mul(_add(_mul(f0, _cos(a)), _mul(f1, _sin(a))), d / 2 * mitres[i]))
            )
    return out


def build_paths(p: Params, sf: Optional[Surfaces] = None) -> List[Path3]:
    sf = sf or build_surfaces(p)
    if p.windings.phases <= 0 and p.windings.topology != "custom":
        return []
    return conductor_paths(p, sf, build_winding(p, sf))


# ---- the part ------------------------------------------------------------------------------


class AirgapPart(BasePart):
    """A rotor/stator pair whose envelope follows the frame and the end-turns."""

    def validate_overrides(
        self, params: Optional[Mapping[str, Any]], scad_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """A group's field is accepted by its own SCAD name (``-p rotor_rib_k=5``) as well as
        inside its group; each comes back as the model coerced it, keyed as it was given."""
        if not params:
            return {}
        groups = {name: g for g in GROUPS for name in _group_names(g)}
        known = set(Params.model_fields) | set(groups)
        unknown = sorted(set(params) - known)
        if unknown:
            raise ValueError(
                f"unknown parameter(s): {', '.join(unknown)}. "
                f"{self.name} declares: {', '.join(sorted(known))}"
            )
        validated = Params(**params)
        out: Dict[str, Any] = {}
        for name in params:
            if name in groups:
                out[name] = getattr(getattr(validated, groups[name]), name)
            else:
                out[name] = getattr(validated, name)
        return out

    def scad_overrides(self, params: Mapping[str, Any]) -> Dict[str, Any]:
        """A group's fields are SCAD assignments of their own: ``rotor`` becomes ``rotor_*``."""
        out: Dict[str, Any] = {}
        for name, value in params.items():
            if isinstance(value, BaseModel):
                out.update(value.model_dump())
            elif isinstance(value, Mapping) and name in GROUPS:
                out.update(value)
            else:
                out[name] = value
        return out

    def get_bounds(self, params: Optional[Dict] = None) -> BoundingBox3D:
        p = self.params_model(**params) if params else self.params_model()
        sf = build_surfaces(p, nt=min(p.resolution, 360), m=1440)
        xs: List[float] = []
        ys: List[float] = []
        zs: List[float] = [p.stack / 2]
        if p.show_stator:
            for i, v in enumerate(sf.outer_r):
                a = i * 360 / sf.nt
                xs.append(v * p.r0 * _cos(a))
                ys.append(v * p.r0 * _sin(a))
        if p.show_rotor:
            for i, v in enumerate(sf.rotor_r):
                a = i * 360 / sf.nt + p.phi
                xs.append(v * p.r0 * _cos(a))
                ys.append(v * p.r0 * _sin(a))
        if p.show_windings:
            for _, d, closed, pts in build_paths(p, sf):
                for x, y, z in tube_points(pts, d, closed):
                    xs.append(x)
                    ys.append(y)
                    zs.append(abs(z))
        if not xs:
            xs = ys = [0.0]
        half_z = max(zs)
        return BoundingBox3D(
            min_point=Vector3D(x=min(xs), y=min(ys), z=-half_z),
            max_point=Vector3D(x=max(xs), y=max(ys), z=half_z),
        )


def create(metadata_root: Path) -> AirgapPart:
    return AirgapPart(
        name="airgap",
        source_file=metadata_root / "parts" / "airgap" / "airgap.scad",
        description=(
            "A rotor/stator pair of any base form - nautilus, Mobius and fractal features, "
            "segmented stators, explicit conductor arrangements - computed from its own SCAD"
        ),
        params_model=Params,
        category="electromechanical",
        tags=[
            "motor",
            "reluctance",
            "rotor",
            "stator",
            "winding",
            "parametric",
            "mobius",
            "fractal",
        ],
        readme_path=metadata_root / "parts" / "airgap" / "README.md",
        preview_color=Color.from_hex("#D9925A"),  # copper
    )


DEFAULT = create(ROOT)
