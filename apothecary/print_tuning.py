"""What a printed piece's measurements say about the printer, from calipers alone.

A person prints a piece made to be measured, measures some of its features with
calipers, and this module says what those readings imply: which errors of the printer
they determine, how sure that is, and which they cannot tell apart. It knows no slicer,
no printer and no file; ``apothecary/slicer/tuning.py`` maps its terms onto a slicer's
settings and keeps the turns. Standard library only.

**The error model.** A feature is one size a caliper reads: across two outer faces
(``outside``), across a hole or a slot (``inside``), a top's height over the bed face
(``height``), or a single-wall fin's thickness (``wall``). Along X or Y a feature is
read at the base -- the jaws take in the first layer, the widest of an outer face and
the narrowest of a hole -- or above it, on faces that begin above the first layers.
Its error, measured less nominal, is taken to be a sum of terms (``TERMS``):

=============  ======  =============================================================
term           unit    what it is, and the reading it moves
=============  ======  =============================================================
``scale_x``    1       a share every size along X is off by: ``+N`` per unit
``scale_y``    1       the same along Y
``scale_z``    1       the same along Z: a height ``H`` moves by ``H`` per unit
``contour``    mm      how far each outer face stands out of where it was drawn:
                       ``+2`` on an outside size, nothing on a hole
``hole``       mm      how far each face of a hole stands into it: ``-2`` on an
                       inside size, nothing on an outer one
``foot``       mm      how far the first layer spreads past the faces above it, on
                       each side: ``+2`` on an outside size at the base, ``-2`` on an
                       inside one at the base, nothing above
``first``      mm      how much higher every top stands because the first layer
                       printed thicker than it was sliced: ``+1`` on a height
=============  ======  =============================================================

so an outside size ``N`` along X at the base errs by ``N scale_x + 2 contour + 2
foot``, and a hole ``N`` across along X above the base by ``N scale_x - 2 hole``. An
outside and an inside size err in opposite directions for a face's offset and in the
same direction for a scale, and two sizes of one kind tell a scale from an offset by
their difference: that is how the terms separate (``separable``). The model is linear,
and the terms are taken as independent: what a scale does to an offset, a product of
two small errors, is left out.

A ``wall`` reading is not in the model. A single wall's thickness says how wide the
line was that printed it, and so the flow, only through the slicer's own model of a
line and the width it chose for that wall; both are slicer's, so a wall's error is
kept and said (``wall_errors``) and moves no term here.

**Measurement quality** (``Reading.uncertainty``). A caliper reads to its resolution
``q``, a step of its display: a reading is anywhere in a step, a standard uncertainty
of ``q / sqrt(12)``, and readings of a part that stays the same round the same way, so
it does not shrink with repeats. A person's repeatability -- stated, or the spread of
repeated readings -- does: ``s / sqrt(n)``. The two add in quadrature. A height off
the slice's layer boundaries carries a layer's quantization too, ``h / sqrt(12)``
(``layer_quantum``). A single reading with no repeatability stated carries the
resolution's alone, which understates it, and is said to.

**Solving** (``solve``). Weighted least squares over the terms the readings touch,
each column scaled to unit length, by the eigen-decomposition of the normal matrix
(``symmetric_eigen``, Jacobi's rotations). A direction of the terms the readings cannot
see -- an eigenvalue under ``RANK_TOLERANCE`` of the largest -- is a combination they
read the same: the terms in it are not separable and are given no value, and what is
said names them and how they trade. A term outside every such direction is determined,
whatever else is not. Each determined term's standard error is the larger of what the
readings' uncertainties give and what the residuals give, where there are more
readings than terms; with none to spare there is no residual to check the model
against, and that is said.

**A step** (``step``, ``RELATIONS``). From a term to a setting's change by a named
relation with its sign convention: an offset taken out (``take_out``: new = used -
term), an offset put back (``put_back``: new = used + term), or a percentage a part is
divided by (``percent``: new = used x (1 + term)). A turn takes ``damping`` of the
whole change (a half: never the whole error at once), never more than the setting's
``most_step``, and never past its limits. A term within ``RESOLVE`` standard errors of
zero is within what the readings resolve, and gets no step.

**Convergence** (``trend``). Over the turns kept, each term's error after a step
against before it: shrinking; oscillating (the sign turned and it is still resolved:
halve the step); not responding (it moved less than the readings resolve though the
step was larger -- the setting does not govern this error, stop); growing (the
relation is wrong for this printer, stop); or within what the readings resolve (done).

Units are millimetres, and a scale a share (0.01 is one percent).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Literal, Mapping, Optional, Sequence, Tuple

Kind = Literal["outside", "inside", "height", "wall"]
Axis = Literal["x", "y", "z"]
Level = Literal["base", "above"]

KINDS: Tuple[str, ...] = ("outside", "inside", "height", "wall")
AXES: Tuple[str, ...] = ("x", "y", "z")
LEVELS: Tuple[str, ...] = ("base", "above")


@dataclass(frozen=True)
class Term:
    """One error of the printer the readings may determine."""

    name: str
    unit: str  # "mm", or "" for a share
    means: str
    # A step of it a person reads easily: what is said when two terms trade.
    shown: float


TERMS: Tuple[Term, ...] = (
    Term("scale_x", "", "the share every size along X is off by", 0.001),
    Term("scale_y", "", "the share every size along Y is off by", 0.001),
    Term("scale_z", "", "the share every height is off by", 0.001),
    Term("contour", "mm", "how far each outer face stands out of where it was drawn", 0.01),
    Term("hole", "mm", "how far each face of a hole stands into it", 0.01),
    Term("foot", "mm", "how far the first layer spreads past the faces above it, each side", 0.01),
    Term("first", "mm", "how much higher every top stands for a first layer printed thick", 0.01),
)
TERM_NAMES: Tuple[str, ...] = tuple(t.name for t in TERMS)
_TERM = {t.name: t for t in TERMS}

# An eigenvalue of the scaled normal matrix under this share of the largest is a
# direction the readings cannot see.
RANK_TOLERANCE = 1e-9
# A term within this many standard errors of zero is within what the readings resolve.
RESOLVE = 2.0
# The share of the whole change a turn takes, unless halved by an oscillation.
DAMPING = 0.5
# The least share a step is halved to.
LEAST_DAMPING = 0.125


def term(name: str) -> Term:
    try:
        return _TERM[name]
    except KeyError:
        raise ValueError(f"no term {name!r} (there are: {', '.join(TERM_NAMES)})") from None


# ---- features and their rows ---------------------------------------------------------------


@dataclass(frozen=True)
class Feature:
    """One size a caliper reads of a piece, as designed."""

    name: str
    kind: Kind
    axis: Axis
    nominal: float  # mm
    level: Level = "above"  # x and y only: whether the jaws take in the first layer

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"{self.name}: no kind {self.kind!r} (there are: {', '.join(KINDS)})")
        if self.axis not in AXES:
            raise ValueError(f"{self.name}: no axis {self.axis!r}")
        if self.level not in LEVELS:
            raise ValueError(f"{self.name}: no level {self.level!r}")
        if (self.kind == "height") != (self.axis == "z"):
            raise ValueError(f"{self.name}: a height is along Z, and only a height is")
        if not (math.isfinite(self.nominal) and self.nominal > 0):
            raise ValueError(f"{self.name}: a nominal size is a length over zero")


def row(feature: Feature) -> Dict[str, float]:
    """What each term adds to ``feature``'s error per unit of it: the error model."""
    k, a, n = feature.kind, feature.axis, feature.nominal
    base = feature.level == "base"
    if k == "outside":
        out = {f"scale_{a}": n, "contour": 2.0}
        if base:
            out["foot"] = 2.0
        return out
    if k == "inside":
        out = {f"scale_{a}": n, "hole": -2.0}
        if base:
            out["foot"] = -2.0
        return out
    if k == "height":
        return {"scale_z": n, "first": 1.0}
    return {}  # a wall: its thickness is kept and said, and moves no term


def predicted(feature: Feature, terms: Mapping[str, float]) -> float:
    """``feature``'s error the model gives for ``terms``: what a reading less its
    nominal would be if the terms were the printer's whole error."""
    return sum(c * terms.get(name, 0.0) for name, c in row(feature).items())


# ---- readings and their uncertainty --------------------------------------------------------


@dataclass(frozen=True)
class Reading:
    """A feature read: each value a person read, in mm, and the instrument's resolution
    and the person's repeatability as stated (standard deviations, mm; None where not
    stated). ``extra`` is a further standard uncertainty, a height's layer quantization."""

    feature: Feature
    values: Tuple[float, ...]
    resolution: float = 0.01
    repeatability: Optional[float] = None
    extra: float = 0.0

    def __post_init__(self) -> None:
        if not self.values:
            raise ValueError(f"{self.feature.name}: a reading has one value or more")
        for v in self.values:
            if not (math.isfinite(v) and v > 0):
                raise ValueError(f"{self.feature.name}: {v} mm is no size")
        if not (self.resolution > 0 and math.isfinite(self.resolution)):
            raise ValueError("a caliper's resolution is a length over zero")
        if self.repeatability is not None and not self.repeatability >= 0:
            raise ValueError("a repeatability is a length, zero or more")

    @property
    def mean(self) -> float:
        return sum(self.values) / len(self.values)

    @property
    def error(self) -> float:
        return self.mean - self.feature.nominal

    @property
    def spread(self) -> Optional[float]:
        """The repeated readings' standard deviation; None for one reading."""
        n = len(self.values)
        if n < 2:
            return None
        m = self.mean
        return math.sqrt(sum((v - m) ** 2 for v in self.values) / (n - 1))

    @property
    def uncertainty(self) -> float:
        """The mean's standard uncertainty: the resolution's, a step's uniform spread,
        which repeats do not shrink; the person's, the larger of the stated
        repeatability and the readings' spread, over the square root of their number;
        and ``extra``; in quadrature."""
        n = len(self.values)
        person = max(self.repeatability or 0.0, self.spread or 0.0)
        return math.sqrt(self.resolution**2 / 12 + person**2 / n + self.extra**2)

    @property
    def understated(self) -> bool:
        """One reading, and no repeatability stated: the resolution's uncertainty alone."""
        return len(self.values) == 1 and self.repeatability is None


def layer_quantum(height: float, first_layer: float, layer: float) -> float:
    """The standard uncertainty a top at ``height`` takes from the slice's layers: none
    where it falls on a layer's top (``first_layer`` and then ``layer`` each), a whole
    layer's uniform spread, ``layer / sqrt(12)``, where it falls between, since the top
    is printed at one boundary or the next."""
    if not (first_layer > 0 and layer > 0):
        raise ValueError("layer heights are over zero")
    k = (height - first_layer) / layer
    if height >= first_layer - 1e-9 and abs(k - round(k)) < 1e-6:
        return 0.0
    return layer / math.sqrt(12)


# ---- linear algebra, by hand -------------------------------------------------------------


def symmetric_eigen(
    matrix: Sequence[Sequence[float]], sweeps: int = 100
) -> Tuple[List[float], List[List[float]]]:
    """The eigenvalues of a symmetric matrix and its eigenvectors (each a column of the
    second), by Jacobi's rotations: each rotation zeroes one off-diagonal entry, and
    the sweeps go on until what is off the diagonal is nothing beside what is on it."""
    n = len(matrix)
    a = [[float(x) for x in r] for r in matrix]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(sweeps):
        off = sum(a[i][j] ** 2 for i in range(n) for j in range(i + 1, n))
        on = sum(a[i][i] ** 2 for i in range(n))
        if off <= 1e-30 * max(on, 1e-300):
            break
        for p in range(n):
            for q in range(p + 1, n):
                if abs(a[p][q]) <= 1e-300:
                    continue
                theta = (a[q][q] - a[p][p]) / (2 * a[p][q])
                t = (1.0 if theta >= 0 else -1.0) / (abs(theta) + math.sqrt(theta * theta + 1))
                c = 1 / math.sqrt(t * t + 1)
                s = t * c
                for k in range(n):
                    akp, akq = a[k][p], a[k][q]
                    a[k][p], a[k][q] = c * akp - s * akq, s * akp + c * akq
                for k in range(n):
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k], a[q][k] = c * apk - s * aqk, s * apk + c * aqk
                for k in range(n):
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p], v[k][q] = c * vkp - s * vkq, s * vkp + c * vkq
    return [a[i][i] for i in range(n)], v


# ---- solving ------------------------------------------------------------------------------


@dataclass
class Solved:
    """One term as the readings determine it, or why they do not."""

    name: str
    value: Optional[float]  # None where it is not determined
    error: Optional[float]  # its standard error
    determined: bool
    # The terms it cannot be told from, where it is not determined.
    with_: Tuple[str, ...] = ()
    resolved: bool = False  # further from zero than RESOLVE standard errors
    assumed: bool = False  # not solved: taken as a value a person stated


@dataclass
class Trade:
    """Terms the readings cannot tell apart. Where one direction of them is all the
    readings miss, ``changes`` is it: adding them to the terms moves no reading."""

    terms: Tuple[str, ...]
    changes: Optional[Dict[str, float]] = None

    def said(self) -> str:
        names = ", ".join(self.terms[:-1]) + f" and {self.terms[-1]}"
        out = f"these readings cannot tell {names} apart"
        if self.changes:
            parts = []
            for name in self.terms:
                v = self.changes[name]
                shown = f"{v:+.4g} mm" if term(name).unit == "mm" else f"{v:+.2%}"
                parts.append(f"{name} {shown}")
            out += ": " + ", ".join(parts) + " together move none of them"
        return out


@dataclass
class Solution:
    """What a set of readings says: each term touched, the trades it cannot settle, and
    the fit's own figures."""

    terms: Dict[str, Solved]
    trades: List[Trade]
    readings: int
    rank: int
    unknowns: int
    dof: int  # readings less the terms determined: what the residuals rest on
    # The weighted residuals' mean square per degree of freedom: about 1 where the model
    # and the stated uncertainties explain the readings; None with no degree of freedom.
    chi2: Optional[float]
    residuals: Dict[str, float]  # each reading's, mm: measured less what the solution gives
    standardized: Dict[str, float]  # each residual over its reading's uncertainty
    matrix: List[List[float]]  # the design matrix: a row per reading, a column per unknown
    columns: List[str]
    rows: List[str]
    said: List[str] = field(default_factory=list)

    def value(self, name: str) -> Optional[float]:
        t = self.terms.get(name)
        return t.value if t is not None else None


def solve(readings: Sequence[Reading], assumed: Optional[Mapping[str, float]] = None) -> Solution:
    """The terms ``readings`` determine, by weighted least squares; ``assumed`` holds
    terms at values a person stated, said as assumed, and solves for the rest."""
    assumed = dict(assumed or {})
    for name in assumed:
        term(name)
    used = [r for r in readings if row(r.feature)]
    names = [r.feature.name for r in used]
    if len(set(names)) != len(names):
        raise ValueError("a feature is read once: its repeats are values of one reading")
    touched = [t for t in TERM_NAMES if any(t in row(r.feature) for r in used)]
    unknowns = [t for t in touched if t not in assumed]
    said: List[str] = []
    a = [[row(r.feature).get(t, 0.0) for t in unknowns] for r in used]
    y = [r.error - sum(c * assumed.get(t, 0.0) for t, c in row(r.feature).items()) for r in used]
    sigma = [r.uncertainty for r in used]
    m, p = len(used), len(unknowns)
    # Weighted, and each column scaled to unit length: the eigenvalues compare.
    aw = [[a[i][j] / sigma[i] for j in range(p)] for i in range(m)]
    yw = [y[i] / sigma[i] for i in range(m)]
    norm = [math.sqrt(sum(aw[i][j] ** 2 for i in range(m))) or 1.0 for j in range(p)]
    an = [[aw[i][j] / norm[j] for j in range(p)] for i in range(m)]
    normal = [[sum(an[i][j] * an[i][k] for i in range(m)) for k in range(p)] for j in range(p)]
    if p:
        lam, vec = symmetric_eigen(normal)
    else:
        lam, vec = [], []
    top = max(lam) if lam else 0.0
    keep = [i for i in range(p) if top > 0 and lam[i] > RANK_TOLERANCE * top]
    null = [i for i in range(p) if i not in keep]
    rank = len(keep)
    aty = [sum(an[i][j] * yw[i] for i in range(m)) for j in range(p)]
    beta_n = [0.0] * p
    cov_n = [[0.0] * p for _ in range(p)]
    for k in keep:
        proj = sum(vec[j][k] * aty[j] for j in range(p)) / lam[k]
        for j in range(p):
            beta_n[j] += vec[j][k] * proj
            for jj in range(p):
                cov_n[j][jj] += vec[j][k] * vec[jj][k] / lam[k]
    beta = [beta_n[j] / norm[j] for j in range(p)]
    # Which terms stand in a direction the readings cannot see.
    loose: Dict[int, float] = {j: sum(vec[j][k] ** 2 for k in null) for j in range(p)}
    directions: List[Dict[str, float]] = []
    for k in null:
        members = [j for j in range(p) if abs(vec[j][k]) > 1e-6]
        if not members:
            continue
        first = members[0]
        unit = term(unknowns[first]).shown
        factor = unit / (vec[first][k] / norm[first])
        directions.append({unknowns[j]: vec[j][k] / norm[j] * factor for j in members})
    trades = _grouped(directions)
    fit = {unknowns[j]: beta[j] for j in range(p) if loose[j] < 1e-12}
    terms_given = {**{t: 0.0 for t in unknowns}, **fit, **assumed}
    residuals = {r.feature.name: r.error - predicted(r.feature, terms_given) for r in used}
    standardized = {r.feature.name: residuals[r.feature.name] / r.uncertainty for r in used}
    dof = m - rank
    chi2 = (sum(v * v for v in standardized.values()) / dof) if dof > 0 else None
    out: Dict[str, Solved] = {}
    for j, name in enumerate(unknowns):
        if loose[j] >= 1e-12:
            with_ = tuple(
                sorted({t for tr in trades if name in tr.terms for t in tr.terms} - {name})
            )
            out[name] = Solved(name, None, None, False, with_=with_)
            continue
        var = cov_n[j][j] / (norm[j] ** 2)
        if chi2 is not None and chi2 > 1:
            var *= chi2  # the residuals say more than the stated uncertainties do
        err = math.sqrt(max(var, 0.0))
        out[name] = Solved(name, beta[j], err, True, resolved=abs(beta[j]) > RESOLVE * err)
    for name, v in assumed.items():
        if name in touched:
            out[name] = Solved(name, v, None, True, assumed=True)
    for tr in trades:
        said.append(tr.said())
    if m and dof <= 0:
        said.append(
            "no reading is left over once the terms are fitted: no residual checks the "
            "model, and each error rests on the stated uncertainties alone"
        )
    if any(r.understated for r in used):
        said.append(
            "a feature read once with no repeatability stated carries its caliper's "
            "resolution alone, which understates it: read each twice or more"
        )
    if chi2 is not None and chi2 > 4 and dof >= 2:
        worst = max(standardized, key=lambda k: abs(standardized[k]))
        said.append(
            f"the readings disagree with the model {math.sqrt(chi2):.1f} times more than "
            f"their uncertainties allow, {worst} the most ({standardized[worst]:+.1f}): a "
            "feature misread, or an error the model leaves out"
        )
    return Solution(
        terms=out,
        trades=trades,
        readings=m,
        rank=rank,
        unknowns=p,
        dof=dof,
        chi2=chi2,
        residuals=residuals,
        standardized=standardized,
        matrix=a,
        columns=list(unknowns),
        rows=names,
        said=said,
    )


def _grouped(directions: List[Dict[str, float]]) -> List[Trade]:
    """The directions the readings cannot see, as groups of the terms they join: a
    group that is one direction says how its terms trade; several directions through
    the same terms are any mix of them, and only the group is said."""
    groups: List[Tuple[set, List[Dict[str, float]]]] = []
    for d in directions:
        joined = [g for g in groups if g[0] & set(d)]
        names = set(d).union(*(g[0] for g in joined))
        found = [d] + [x for g in joined for x in g[1]]
        groups = [g for g in groups if all(g is not j for j in joined)] + [(names, found)]
    return [
        Trade(
            tuple(t for t in TERM_NAMES if t in names),
            found[0] if len(found) == 1 else None,
        )
        for names, found in groups
    ]


def separable(features: Iterable[Feature], assumed: Iterable[str] = ()) -> Dict[str, bool]:
    """Which terms a set of features determines, read once each: the design matrix's
    answer alone, before anything is printed (a plan's check)."""
    readings = [Reading(f, (f.nominal,)) for f in features]
    found = solve(readings, {t: 0.0 for t in assumed})
    return {name: s.determined for name, s in found.terms.items() if not s.assumed}


def wall_errors(readings: Sequence[Reading]) -> Dict[str, Tuple[float, float]]:
    """Each wall's thickness error and its uncertainty: kept and said, solved for nothing."""
    return {r.feature.name: (r.error, r.uncertainty) for r in readings if r.feature.kind == "wall"}


# ---- a step --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Relation:
    """How a setting moves to take out a term: ``whole`` the value that leaves none of
    it, ``after`` what is left of it once the setting moves from ``used`` to ``new``."""

    name: str
    says: str

    def whole(self, value: float, used: float) -> float:
        if self.name == "take_out":
            return used - value
        if self.name == "put_back":
            return used + value
        if self.name == "percent":
            return used * (1 + value)
        raise ValueError(self.name)

    def after(self, value: float, used: float, new: float) -> float:
        if self.name == "take_out":
            return value + (new - used)
        if self.name == "put_back":
            return value - (new - used)
        if self.name == "percent":
            return (1 + value) * used / new - 1
        raise ValueError(self.name)


RELATIONS: Dict[str, Relation] = {
    "take_out": Relation(
        "take_out",
        "new = used - term: the setting moves the faces the way the term does, a "
        "positive value outward, so the term is taken back out of it",
    ),
    "put_back": Relation(
        "put_back",
        "new = used + term: the setting moves the faces against the term, a positive "
        "value opening a hole or shrinking the first layer, so the term is added to it",
    ),
    "percent": Relation(
        "percent",
        "new = used x (1 + term): the setting is the size a part comes out at, in "
        "percent of its drawing, and the slicer scales the part by 100 over it",
    ),
}


@dataclass(frozen=True)
class Limits:
    """A setting's bounds: the least and the most it may be, and the most one turn moves it."""

    least: float
    most: float
    most_step: float


@dataclass
class Step:
    """A setting's change for one term, or why there is none."""

    term: str
    used: float
    whole: Optional[float]  # the value that would leave none of the term
    new: Optional[float]  # what the turn proposes; None: nothing
    damping: float
    expected: Optional[float]  # the term left once the setting is ``new``
    why: str


def step(
    solved: Solved,
    relation: Relation,
    used: float,
    limits: Limits,
    damping: float = DAMPING,
) -> Step:
    """The change one turn makes to a setting for ``solved``: ``damping`` of the whole
    change, no more than ``limits.most_step``, never past the limits; none for a term
    not determined, or within what the readings resolve."""
    if solved.assumed or not solved.determined or solved.value is None:
        why = (
            "assumed, not measured"
            if solved.assumed
            else "not determined: " + (", ".join(solved.with_) or "nothing") + " read the same"
        )
        return Step(solved.name, used, None, None, damping, None, why)
    whole = relation.whole(solved.value, used)
    if not solved.resolved:
        return Step(
            solved.name,
            used,
            whole,
            None,
            damping,
            None,
            f"{solved.value:+.4g} is within {RESOLVE:g} standard errors "
            f"({solved.error:.2g}) of none: smaller than the readings resolve",
        )
    change = damping * (whole - used)
    why = f"{damping:g} of the whole change"
    if abs(change) > limits.most_step:
        change = math.copysign(limits.most_step, change)
        why = f"the most one turn moves it, {limits.most_step:g}"
    new = used + change
    if new > limits.most or new < limits.least:
        new = min(limits.most, max(limits.least, new))
        why = f"held at its limit, {limits.least:g} to {limits.most:g}"
        if abs(new - used) < 1e-12:
            return Step(solved.name, used, whole, None, damping, None, why + ": it is there")
    return Step(
        solved.name, used, whole, new, damping, relation.after(solved.value, used, new), why
    )


# ---- convergence ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Point:
    """A term as one turn found it, and the setting's change made after it."""

    turn: str
    value: Optional[float]
    error: Optional[float]
    stepped: bool  # whether a change for it was applied after this turn
    expected: Optional[float] = None  # what was expected of it at the next turn
    damping: float = DAMPING


@dataclass
class Trend:
    term: str
    state: Literal[
        "one turn",
        "not determined",
        "not stepped",
        "within resolution",
        "shrinking",
        "oscillating",
        "not responding",
        "growing",
    ]
    damping: float  # what the next step takes
    stop: bool
    said: str


def trend(term_name: str, points: Sequence[Point]) -> Trend:
    """What the last two turns say of a term: is its error shrinking, oscillating (halve
    the step), not responding (stop: the setting does not govern it) or growing (stop:
    the relation is wrong here)?"""
    found = [p for p in points if p.value is not None and p.error is not None]
    damping = found[-1].damping if found else DAMPING
    if not found:
        return Trend(term_name, "not determined", damping, False, "no turn determined it")
    last = found[-1]
    if abs(last.value) <= RESOLVE * last.error:
        return Trend(
            term_name,
            "within resolution",
            damping,
            False,
            f"{last.value:+.4g} at {last.turn}, within what its readings resolve: nothing to take out",
        )
    if len(found) < 2:
        return Trend(term_name, "one turn", damping, False, f"{last.value:+.4g} at {last.turn}")
    before = found[-2]
    if not before.stepped:
        return Trend(
            term_name,
            "not stepped",
            damping,
            False,
            f"{before.value:+.4g} at {before.turn}, {last.value:+.4g} at {last.turn}, with no "
            "step between",
        )
    noise = RESOLVE * math.hypot(before.error, last.error)
    moved = before.value - last.value
    meant = before.value - (before.expected if before.expected is not None else 0.0)
    said = f"{before.value:+.4g} at {before.turn}, {last.value:+.4g} at {last.turn}"
    if abs(moved) <= noise and abs(meant) > noise:
        return Trend(
            term_name,
            "not responding",
            damping,
            True,
            said + f": it did not move though the step meant {meant:+.4g}; the setting does "
            "not govern this error here: stop",
        )
    if (last.value > 0) != (before.value > 0):
        half = max(LEAST_DAMPING, damping / 2)
        return Trend(
            term_name,
            "oscillating",
            half,
            False,
            said + f": it turned past none; the next step takes {half:g} of the change",
        )
    if abs(last.value) > abs(before.value) + noise:
        return Trend(
            term_name,
            "growing",
            damping,
            True,
            said + ": it grew after a step meant to shrink it; the relation does not hold "
            "for this printer: stop",
        )
    return Trend(term_name, "shrinking", damping, False, said)
