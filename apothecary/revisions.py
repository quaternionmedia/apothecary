"""First-slice versioning building blocks over the fractal Assembly tree.

PROTOTYPE — not ratified, and not wired into the API or viewer yet. This
module lays the pieces a "plan and composite design iterations" feature would
need — commit, branch, checkout, and a path-addressed structural diff — as
generic operations on :class:`apothecary.hierarchy.Assembly`. Because
``Assembly`` is one recursive class reachable at any depth, these operations
already reach a single ``Feature`` the same way they reach a whole ``Site``;
no per-level versioning code is needed as the tree grows deeper.

Branching, not linear or flat: a :class:`Revision` names its parent(s)
(``parent_ids``), so history is a tree — ``branch()`` forks a new line from
any existing revision without disturbing the one it forked from, and two
branches can diverge and be compared independently.

**Not included, and deliberately so:** mix-and-match compositing (building a
new revision by picking, per node path, which prior revision's subtree wins).
That stays a documented roadmap step once this shape is proven, not built
here — the dotted paths ``diff_assemblies`` already keys by are exactly what
that merge would key off of.

Same explicit prototype caveat as ``site_store.SiteStore``/
``example_hierarchy.JobStore``: in-memory, one graph per site name, lost on
restart, not shared across worker processes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .hierarchy import Assembly


def _new_id() -> str:
    return uuid.uuid4().hex


class Revision(BaseModel):
    """One immutable snapshot of an Assembly tree, plus where it came from.

    ``parent_ids`` is empty for a root revision, one entry for an ordinary
    commit or branch, and (in principle, for a future merge) more than one --
    the field already carries that shape even though nothing here creates a
    multi-parent revision yet.
    """

    id: str = Field(default_factory=_new_id)
    parent_ids: List[str] = Field(default_factory=list)
    label: str
    rationale: Optional[str] = None
    tree: Assembly
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AssemblyDiff(BaseModel):
    """One concrete difference between two Assembly trees, at one dotted path.

    Same shape convention as ``hierarchy.LayoutViolation``: a ``kind``, a
    human ``message``, and the identifying path rather than a generic object
    dump.
    """

    path: str
    kind: str
    message: str


def diff_assemblies(
    a: Optional[Assembly], b: Optional[Assembly], *, path: str = ""
) -> List[AssemblyDiff]:
    """Recursive, path-addressed structural diff between two Assembly trees.

    Paths follow the dotted addressing the ADR already names
    (``enclosure.mounting_system.m3_boss_fl``), built from ``name`` at each
    level rather than list position -- so reordering a node's children is not
    itself a diff, but renaming, moving, or removing one is.
    """
    if a is None and b is None:
        return []
    if a is None:
        node_path = path or b.name  # type: ignore[union-attr]
        return [AssemblyDiff(path=node_path, kind="added", message=f"{node_path} added")]
    if b is None:
        node_path = path or a.name
        return [AssemblyDiff(path=node_path, kind="removed", message=f"{node_path} removed")]

    node_path = path or a.name
    diffs: List[AssemblyDiff] = []

    if a.position != b.position:
        diffs.append(
            AssemblyDiff(
                path=node_path,
                kind="position_changed",
                message=f"{node_path} moved from {a.position} to {b.position}",
            )
        )
    if a.status != b.status:
        diffs.append(
            AssemblyDiff(
                path=node_path,
                kind="status_changed",
                message=f"{node_path} status changed from {a.status!r} to {b.status!r}",
            )
        )
    if a.material != b.material:
        diffs.append(
            AssemblyDiff(
                path=node_path,
                kind="material_changed",
                message=f"{node_path} material changed from {a.material!r} to {b.material!r}",
            )
        )
    if a.build_volume != b.build_volume:
        diffs.append(
            AssemblyDiff(
                path=node_path,
                kind="build_volume_changed",
                message=(
                    f"{node_path} build_volume changed from "
                    f"{a.build_volume} to {b.build_volume}"
                ),
            )
        )

    a_children = {child.name: child for child in a.children}
    b_children = {child.name: child for child in b.children}
    for name in sorted(set(a_children) | set(b_children)):
        diffs.extend(
            diff_assemblies(a_children.get(name), b_children.get(name), path=f"{node_path}.{name}")
        )

    return diffs


class RevisionGraph:
    """Branching history of Assembly-tree snapshots, one graph per site name."""

    def __init__(self) -> None:
        self._revisions: Dict[str, Dict[str, Revision]] = {}

    def commit(
        self,
        site_name: str,
        tree: Assembly,
        *,
        label: str,
        rationale: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> Revision:
        """Snapshot ``tree`` as a new revision, optionally forking from ``parent_id``."""
        if parent_id is not None:
            self.get(site_name, parent_id)  # raises KeyError if it doesn't exist
        revision = Revision(
            parent_ids=[parent_id] if parent_id else [],
            label=label,
            rationale=rationale,
            tree=tree,
        )
        self._revisions.setdefault(site_name, {})[revision.id] = revision
        return revision

    def branch(
        self, site_name: str, from_revision_id: str, *, label: str, rationale: Optional[str] = None
    ) -> Revision:
        """Fork a new line from an existing revision, starting as an exact copy of its tree.

        The two lines are independent from this point on: committing further
        against the new revision never mutates ``from_revision_id`` or any
        other revision already recorded.
        """
        parent = self.get(site_name, from_revision_id)
        return self.commit(
            site_name,
            parent.tree.model_copy(deep=True),
            label=label,
            rationale=rationale,
            parent_id=from_revision_id,
        )

    def get(self, site_name: str, revision_id: str) -> Revision:
        try:
            return self._revisions[site_name][revision_id]
        except KeyError:
            raise KeyError(revision_id) from None

    def history(self, site_name: str, revision_id: str) -> List[Revision]:
        """Walk the first-parent chain back to the root, oldest first."""
        chain = [self.get(site_name, revision_id)]
        while chain[-1].parent_ids:
            chain.append(self.get(site_name, chain[-1].parent_ids[0]))
        return list(reversed(chain))

    def children_of(self, site_name: str, revision_id: str) -> List[Revision]:
        """Every revision that named ``revision_id`` as a parent -- the branch points."""
        return [
            revision
            for revision in self._revisions.get(site_name, {}).values()
            if revision_id in revision.parent_ids
        ]

    def checkout(self, site_name: str, revision_id: str) -> Assembly:
        """A deep copy of the revision's tree -- safe to mutate without corrupting history."""
        return self.get(site_name, revision_id).tree.model_copy(deep=True)
