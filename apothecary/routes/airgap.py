"""``/airgap``: the Airgap panel's metrics document, its schema published and a document read back.

The panel computes; these routes validate. ``GET /airgap/metrics/schema`` is the JSON Schema
of ``airgap/metrics/1``, the published contract; ``POST /airgap/metrics/validate`` takes a
document the panel copied and answers it normalized, or as Markdown with ``?format=md``,
or 422 naming what is wrong with it. Nothing here runs the model.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from ..airgap_metrics import AirgapMetrics, render_markdown

router = APIRouter(prefix="/airgap", tags=["airgap"])


@router.get("/metrics/schema")
def metrics_schema() -> Dict[str, Any]:
    """The JSON Schema of the metrics document the Airgap panel emits."""
    return AirgapMetrics.model_json_schema(by_alias=True)


@router.post("/metrics/validate")
def metrics_validate(
    doc: AirgapMetrics,
    fmt: str = Query("json", alias="format", pattern="^(json|md)$"),
):
    """A metrics document read back: normalized, or rendered as Markdown (``?format=md``)."""
    if fmt == "md":
        return PlainTextResponse(render_markdown(doc), media_type="text/markdown")
    return doc.model_dump(by_alias=True)
