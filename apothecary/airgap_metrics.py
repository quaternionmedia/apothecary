"""The Airgap panel's metrics document: its schema, its groups, and a view of it.

The panel (``apothecary/static/widgets/airgap.js``) says its figures as one document,
``airgap/metrics/1``, grouped by what produced them: the geometry, the windings, the static
field and torque tables, and the run. The panel is the only thing that computes a figure;
this module validates the document it emits and renders it. A view reads a document and
nothing else -- the split the org's monitoring-seam record draws between a collector and a
view -- so a Markdown table rendered here is a claim about the document it was given, never
a recomputation. ``GET /airgap/metrics/schema`` publishes the schema, ``POST
/airgap/metrics/validate`` and ``apothecary airgap metrics validate`` read a document back.

Groups are a contract: the four ids below are the only ones accepted, so ``geometry.bore_s0``
means the same thing in every document. Metrics inside a group are open: a new figure is a
new key, not a new schema.

Tools: drafted with Claude Code (Anthropic); a human ratifies before merge.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

SCHEMA = "airgap/metrics/1"

GroupId = Literal["geometry", "windings", "field", "dynamics"]

GROUP_TITLES: Dict[str, str] = {
    "geometry": "Geometry",
    "windings": "Windings",
    "field": "Field and torque (static)",
    "dynamics": "Dynamics",
}

MetricValue = Union[float, int, bool, str, None]


class Metric(BaseModel):
    """One reported figure: a stable key, a human label, a value with its unit, an optional note."""

    key: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$")
    label: str
    value: MetricValue = None
    unit: str = ""
    note: str = ""

    @field_validator("value")
    @classmethod
    def _finite(cls, v: MetricValue) -> MetricValue:
        if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
            raise ValueError("metric values must be finite; use null for unavailable")
        return v


class MetricGroup(BaseModel):
    id: GroupId
    title: str = ""
    metrics: List[Metric] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_keys(self) -> "MetricGroup":
        keys = [m.key for m in self.metrics]
        dup = {k for k in keys if keys.count(k) > 1}
        if dup:
            raise ValueError(f"duplicate metric keys in group {self.id}: {sorted(dup)}")
        if not self.title:
            self.title = GROUP_TITLES[self.id]
        return self


class AirgapMetrics(BaseModel):
    """The metrics document the panel emits (Panels › Airgap › Copy metrics)."""

    schema_: Literal["airgap/metrics/1"] = Field(SCHEMA, alias="schema")
    generated_at: str = Field(..., description="ISO 8601 timestamp written by the tool")
    units: str = ""
    preset: Optional[str] = None
    groups: List[MetricGroup] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _unique_groups(self) -> "AirgapMetrics":
        ids = [g.id for g in self.groups]
        dup = {g for g in ids if ids.count(g) > 1}
        if dup:
            raise ValueError(f"duplicate groups: {sorted(dup)}")
        return self

    def get(self, path: str) -> Metric:
        """``group.key`` lookup, e.g. ``field.mean_torque``."""
        gid, _, key = path.partition(".")
        for g in self.groups:
            if g.id == gid:
                for m in g.metrics:
                    if m.key == key:
                        return m
        raise KeyError(path)

    def flat(self) -> Dict[str, MetricValue]:
        return {f"{g.id}.{m.key}": m.value for g in self.groups for m in g.metrics}


def load_metrics(path: Union[str, Path]) -> AirgapMetrics:
    with open(path, encoding="utf-8") as fh:
        return AirgapMetrics.model_validate(json.load(fh))


def format_value(m: Metric) -> str:
    v = m.value
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, str):
        return v
    if isinstance(v, float):
        a = abs(v)
        if a != 0 and (a < 1e-3 or a >= 1e6):
            s = f"{v:.3e}"
        elif a >= 100:
            s = f"{v:.0f}"
        elif a >= 10:
            s = f"{v:.1f}"
        else:
            s = f"{v:.3f}".rstrip("0").rstrip(".")
    else:
        s = str(v)
    return f"{s} {m.unit}".strip()


def render_markdown(doc: AirgapMetrics) -> str:
    """One table per group, in the document's group order. A view, not a computation."""
    out = ["# Airgap metrics", ""]
    head = f"Schema `{doc.schema_}` · generated {doc.generated_at}"
    if doc.preset:
        head += f" · preset `{doc.preset}`"
    out.append(head)
    if doc.units:
        out.append(f"Units: {doc.units}")
    out.append("")
    for g in doc.groups:
        out.append(f"## {g.title or GROUP_TITLES[g.id]}")
        out.append("")
        out.append("| Metric | Value | Note |")
        out.append("|---|---|---|")
        for m in g.metrics:
            out.append(f"| {m.label} (`{g.id}.{m.key}`) | {format_value(m)} | {m.note} |")
        out.append("")
    return "\n".join(out).rstrip() + "\n"
