"""``apothecary airgap``: the Airgap panel's metrics document from the command line."""

from __future__ import annotations

import json
from pathlib import Path

import click
from pydantic import ValidationError

from ..airgap_metrics import AirgapMetrics, load_metrics, render_markdown


@click.group()
def airgap():
    """The Airgap panel's documents: its metrics validated and rendered."""


@airgap.group()
def metrics():
    """Validate and render ``airgap/metrics/1`` documents the panel copied."""


@metrics.command("validate")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--format", "fmt", type=click.Choice(["summary", "json", "md"]), default="summary")
def validate_cmd(path: Path, fmt: str):
    """Read a metrics document back: a summary, the document normalized, or Markdown."""
    try:
        doc = load_metrics(path)
    except ValidationError as exc:
        click.echo(f"Invalid metrics document: {path}", err=True)
        for err in exc.errors():
            loc = ".".join(str(x) for x in err.get("loc", ()))
            click.echo(f"  {loc}: {err.get('msg')}", err=True)
        raise SystemExit(1) from exc
    except json.JSONDecodeError as exc:
        click.echo(f"Not JSON: {path} ({exc})", err=True)
        raise SystemExit(1) from exc
    if fmt == "json":
        click.echo(json.dumps(doc.model_dump(by_alias=True), indent=2))
    elif fmt == "md":
        click.echo(render_markdown(doc), nl=False)
    else:
        n = sum(len(g.metrics) for g in doc.groups)
        groups = ", ".join(f"{g.id} ({len(g.metrics)})" for g in doc.groups)
        click.echo(f"OK {doc.schema_} · {n} metrics in {len(doc.groups)} groups: {groups}")


@metrics.command("schema")
def schema_cmd():
    """Print the JSON Schema of the metrics document."""
    click.echo(json.dumps(AirgapMetrics.model_json_schema(by_alias=True), indent=2))
