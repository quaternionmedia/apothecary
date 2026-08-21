"""What is unresolved here, and what exists to resolve it.

Two indexes over things this repository already knows, so a reader does not
have to run five commands and hold the answers in their head.

**The problem space** is every open question the repository can state: a
dimension its sources disagree about, a part whose declared size its geometry
does not have, an envelope nobody has measured, a layout that does not close.
Each carries who can close it, which is the interesting field — a problem
nobody owns is how a project accumulates them.

**The solution space** is what is here to close them with: the parts, the
assemblies, the providers behind the black-box seam, and the commands that
check each class.

Neither index invents anything. Every entry is derived from a model that
already exists, so this cannot drift from the repository the way a
hand-maintained issue list does.

**Scope, stated so its absence is not mistaken for silence.** These are open
*questions*, not failing checks. An assembly that has drifted from the parts it
models is a failing test, not an entry here — `tests/test_datum_core_site.py`
is that gate, and the suite is where it reports. The index answers "what is
unresolved", never "is the build green".

Ownership is the boundary between the two repositories, made machine-readable:

``apothecary``  geometry, its realization, and the tooling around it. Closable
                here, by a commit in this repository.
``datum``       the board, the firmware, and what the product must do. Closable
                only by the consuming project.
``human``       a decision between defensible alternatives. No commit closes
                it; somebody has to choose.
``measurement`` waits on a physical artifact or a real file. No amount of
                code closes it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

APOTHECARY = "apothecary"
DATUM = "datum"
HUMAN = "human"
MEASUREMENT = "measurement"

# Problem kinds, and who is able to close each by construction.
KIND_OWNER = {
    "contested": HUMAN,
    "drift": APOTHECARY,
    "unbounded": APOTHECARY,
    "unmeasured": MEASUREMENT,
    "unprintable": APOTHECARY,
    "violation": APOTHECARY,
}


@dataclass
class Problem:
    """One open question, with who can close it and what would."""

    id: str
    kind: str
    subject: str
    summary: str
    owner: str
    closes_with: str
    detail: str = ""
    sources: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class Capability:
    """One thing this repository offers, and the problems it can close."""

    name: str
    kind: str
    summary: str
    addresses: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


# --------------------------------------------------------------- problems --


def _contested_problems(part) -> List[Problem]:
    """Dimensions the project's own sources state differently.

    Owned by a human by construction: each candidate has a document behind it,
    so this is a choice between defensible alternatives rather than a bug.
    """
    problems = []
    for name, candidates in (getattr(part, "contested", {}) or {}).items():
        values = ", ".join(str(c.value) for c in candidates)
        problems.append(
            Problem(
                id=f"contested:{part.name}:{name}",
                kind="contested",
                subject=part.name,
                summary=f"{part.name}.{name} has {len(candidates)} candidate values",
                # From the table, not typed again here. Two places declaring
                # one fact is the duplication this whole index exists to avoid,
                # and an adversarial pass caught this one lying dormant.
                owner=KIND_OWNER["contested"],
                closes_with=(
                    "choose one in the viewer — the panel lists each candidate "
                    "with its source and what choosing it costs"
                ),
                detail=f"candidates: {values}",
                sources=[c.source for c in candidates],
            )
        )
    return problems


def _readiness_problems(part, report) -> List[Problem]:
    """Whatever the build-readiness assessment could not tick."""
    problems = []
    for check in report.checks:
        if check.state == "pass":
            continue

        if check.name == "Declared bounds match geometry":
            kind = "unbounded" if "declares no bounds" in check.detail else "drift"
        elif check.name == "Fitted to measured artifacts":
            kind = "unmeasured"
        elif check.name in ("Print settings declared", "Fits the printer", "Geometry renders"):
            kind = "unprintable"
        else:
            continue  # contested is reported from the part, with its provenance

        owner = KIND_OWNER[kind]
        # An unmeasured board is the consuming project's to supply -- WP-4
        # produces the schematic. An unmeasured mounting surface is not.
        if kind == "unmeasured" and "board" in check.detail:
            owner = DATUM

        problems.append(
            Problem(
                id=f"{kind}:{part.name}:{check.name.lower().replace(' ', '-')}",
                kind=kind,
                subject=part.name,
                summary=f"{part.name}: {check.name.lower()}",
                owner=owner,
                closes_with=check.fix or "see the checklist",
                detail=check.detail,
            )
        )
    return problems


def _site_problems(name: str, report) -> List[Problem]:
    """Layouts that do not close."""
    return [
        Problem(
            id=f"violation:{name}:{index}",
            kind="violation",
            subject=name,
            summary=f"{name}: {violation.kind}",
            owner=APOTHECARY,
            closes_with="move the pieces, or correct the validator if it is wrong",
            detail=violation.message,
            sources=list(getattr(violation, "structures", []) or []),
        )
        for index, violation in enumerate(report.violations)
    ]


def problems(build_volume: Optional[tuple] = None) -> List[Problem]:
    """Every open question this repository can state, worst-owned first."""
    from .projects.parts.readiness import assess
    from .projects.parts.skeleton import ROOT
    from .projects.registry import scan_projects

    found: List[Problem] = []

    for entry in sorted(
        {p.name: p for p in scan_projects(ROOT) if p.kind == "part" and p.wrapper}.values(),
        key=lambda p: p.name,
    ):
        try:
            module = __import__(entry.wrapper, fromlist=["DEFAULT"])
            part = module.DEFAULT
        except Exception:  # pragma: no cover - a broken wrapper is its own problem
            continue
        found.extend(_contested_problems(part))
        found.extend(_readiness_problems(part, assess(part, build_volume=build_volume)))

    # Sites carry layout constraints that parts do not.
    from .api import _site_store

    for name in _site_store.names():
        try:
            site = _site_store.get(name)
            found.extend(_site_problems(name, _site_store.validator(name)(site)))
        except Exception:  # pragma: no cover - defensive
            continue

    order = {HUMAN: 0, MEASUREMENT: 1, APOTHECARY: 2, DATUM: 3}
    return sorted(found, key=lambda p: (order.get(p.owner, 9), p.kind, p.subject))


# -------------------------------------------------------------- solutions --


def capabilities() -> List[Capability]:
    """What this repository offers against those problems."""
    from .projects.parts.skeleton import ROOT
    from .projects.registry import scan_projects

    found: List[Capability] = []

    for entry in sorted(
        {p.name: p for p in scan_projects(ROOT) if p.kind == "part" and p.wrapper}.values(),
        key=lambda p: p.name,
    ):
        try:
            module = __import__(entry.wrapper, fromlist=["DEFAULT"])
            part = module.DEFAULT
        except Exception:  # pragma: no cover
            continue
        found.append(
            Capability(
                name=part.name,
                kind="part",
                summary=part.description or "a printable part",
                addresses=["unbounded", "unprintable"],
            )
        )

    from .api import _site_store

    found.extend(
        Capability(
            name=name,
            kind="assembly",
            summary="a navigable assembly with a layout validator",
            addresses=["violation"],
        )
        for name in _site_store.names()
    )

    # The black-box seam: how an unmeasured envelope stops being one.
    found.append(
        Capability(
            name="StubProvider",
            kind="provider",
            summary="hand-entered envelopes, good enough to scaffold against",
            addresses=[],
        )
    )
    found.append(
        Capability(
            name="KiCadProvider",
            kind="provider",
            summary="the same interface, reading a real board outline",
            addresses=["unmeasured"],
        )
    )

    found.extend(
        [
            Capability(
                name="apothecary parts verify",
                kind="gate",
                summary="declared bounds against real geometry; exits non-zero on drift",
                addresses=["drift"],
            ),
            Capability(
                name="apothecary parts checklist",
                kind="gate",
                summary="whether a part can be printed and then checked against a real one",
                addresses=["unbounded", "unprintable", "unmeasured", "contested"],
            ),
            Capability(
                name="the viewer's part panel",
                kind="tool",
                summary="turn a contested value and see what it costs",
                addresses=["contested"],
            ),
        ]
    )
    return found


def summary(build_volume: Optional[tuple] = None) -> Dict:
    """Both spaces, and what is unaddressed.

    A problem kind with no capability against it is the one worth naming: it
    means nothing here can close it, whoever owns it.
    """
    open_problems = problems(build_volume=build_volume)
    offered = capabilities()

    addressable = {kind for c in offered for kind in c.addresses}
    by_kind: Dict[str, int] = {}
    by_owner: Dict[str, int] = {}
    for problem in open_problems:
        by_kind[problem.kind] = by_kind.get(problem.kind, 0) + 1
        by_owner[problem.owner] = by_owner.get(problem.owner, 0) + 1

    return {
        "problems": len(open_problems),
        "by_kind": by_kind,
        "by_owner": by_owner,
        "capabilities": len(offered),
        "unaddressed_kinds": sorted(set(by_kind) - addressable),
    }
