"""``apothecary tuning``: a printer's settings tuned from what its prints measure.

A turn is a piece printed from a kept slice and read with calipers: ``tuning plan``
says what to read of a part, ``tuning turn`` keeps the readings as the printer's next
turn and says what they imply, ``tuning apply`` takes the last turn's changes into the
printer's next slices, ``tuning undo`` drops the last turn, and ``tuning history`` says
whether each setting's error shrinks. Everything here reads and writes the state
folder's tuning documents (``apothecary/slicer/tuning.py``): no browser, no server, and
nothing is sent to a printer.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click
from pydantic import ValidationError

from .. import print_tuning as pt
from ..slicer import tuning as tn


@click.group()
def tuning():
    """A printer tuned from what its prints measure: plan, turn, apply, undo, history."""


def _pairs(given: Tuple[str, ...], what: str) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = defaultdict(list)
    for item in given:
        name, sep, values = item.partition("=")
        if not sep or not name.strip():
            raise click.UsageError(f"{what} is NAME=VALUE[,VALUE...]: not {item!r}")
        try:
            out[name.strip()] += [float(v) for v in values.split(",") if v.strip()]
        except ValueError as exc:
            raise click.UsageError(f"{what} {item!r}: {exc}") from exc
    return dict(out)


def _read_csv(path: Path) -> Dict[str, List[float]]:
    """Readings from a CSV whose columns are ``feature`` and ``value``: a row per reading,
    a feature's repeats its rows."""
    out: Dict[str, List[float]] = defaultdict(list)
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                out[row["feature"].strip()].append(float(row["value"]))
            except (KeyError, ValueError, AttributeError) as exc:
                raise click.UsageError(
                    f"{path}: a reading is a row of feature and value ({exc})"
                ) from exc
    return dict(out)


def _applies(site: str, printer: str, filament: Optional[str], process: Optional[str]):
    """What a command names, else the one document the printer has."""
    if filament and process:
        return tn.AppliesTo(filament=filament, process=process)
    found = [
        d.applies_to
        for d in tn.documents(site, printer)
        if (not filament or d.applies_to.filament == filament)
        and (not process or d.applies_to.process == process)
    ]
    if len(found) != 1:
        kept = ", ".join(f"{a.filament} / {a.process}" for a in found) or "none"
        raise click.UsageError(
            f"name the filament and the process: {site}'s {printer} keeps {kept}"
        )
    return found[0]


where = [
    click.option("--site", required=True, help="The site the printer stands in."),
    click.option("--printer", required=True, help="The printer's node in the site."),
    click.option("--filament", default=None, help="Its filament profile; with one kept, that one."),
    click.option("--process", default=None, help="Its process profile; with one kept, that one."),
]


def _with(options):
    def wrap(f):
        for o in reversed(options):
            f = o(f)
        return f

    return wrap


def _say(doc: tn.TuningDocument, fmt: str, explain: bool) -> None:
    if fmt == "json":
        click.echo(json.dumps(doc.model_dump(mode="json", by_alias=True), indent=2))
    else:
        click.echo(tn.render_markdown(doc, explain=explain), nl=False)


@tuning.command("plan")
@click.argument("part")
@click.option("-p", "--param", "params", multiple=True, metavar="NAME=VALUE")
def plan_cmd(part: str, params: Tuple[str, ...]):
    """What to read of PART printed: each feature in order, its jaws and its nominal, and
    which terms the plan separates. A part that names no plan is read by its box."""
    from ..models.measures import box_plan
    from ..slicer.profiles import load_part

    found = load_part(part)
    overrides = found.validate_overrides(dict(p.split("=", 1) for p in params)) if params else {}
    plan = found.measures(overrides or None)
    if plan is None:
        b = found.get_bounds(overrides or None)
        if b is None:
            raise click.UsageError(f"{part} names no plan and declares no bounds")
        plan = box_plan((b.size.x, b.size.y, b.size.z))
        click.echo(f"{part} names no plan: read by its box")
    for i, f in enumerate(plan.features, 1):
        where = f"{f.kind} {f.axis}" + (f", {f.level}" if f.axis != "z" else "")
        click.echo(f"{i:>2}. {f.name:<12} {f.nominal:>8g} mm  {f.jaw} jaws  ({where}): {f.words}")
    found_terms = plan.check()
    ok = [t for t, v in found_terms.items() if v]
    loose = [t for t, v in found_terms.items() if not v]
    click.echo(f"separates: {', '.join(ok) or 'nothing'}")
    if loose:
        click.echo(f"cannot separate: {', '.join(loose)}")


@tuning.command("start")
@click.option("--site", required=True)
@click.option("--printer", required=True)
@click.option(
    "--part", default=None, help="The printer's part; with one keeping a profile, that one."
)
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md", show_default=True)
def start_cmd(site: str, printer: str, part: Optional[str], fmt: str):
    """The printer's tuning document for the filament and process its profile names: the
    one kept (a correction of the older shape read into it), or a new one."""
    from ..slicer.profiles import load_profile, printers

    if not part:
        found = printers()
        if len(found) != 1:
            raise click.UsageError("name the printer's part: " + ", ".join(found))
        part = found[0]
    section = load_profile(part).sections.get(tn.MODULE) or {}
    applies = tn.AppliesTo(filament=section["filament"], process=section["process"])
    _say(tn.start(site, printer, part, applies), fmt, False)


@tuning.command("show")
@_with(where)
@click.option("--explain", is_flag=True, help="Each turn's design matrix and residuals too.")
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md", show_default=True)
def show_cmd(site, printer, filament, process, explain, fmt):
    """A printer's tuning document: what its next slices take, each turn, and the trend."""
    applies = _applies(site, printer, filament, process)
    _say(tn.load(site, printer, applies), fmt, explain)


@tuning.command("turn")
@click.argument("file_id")
@click.option(
    "--read",
    "reads",
    multiple=True,
    metavar="NAME=VALUE[,VALUE...]",
    help="A feature read, its repeats comma-separated.",
)
@click.option(
    "--csv",
    "csv_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Readings: columns feature and value.",
)
@click.option(
    "--resolution",
    type=float,
    default=tn.RESOLUTION,
    show_default=True,
    help="The caliper's step, mm.",
)
@click.option(
    "--repeatability", type=float, default=None, help="Your repeatability, mm, as you know it."
)
@click.option(
    "--assume",
    "assumes",
    multiple=True,
    metavar="TERM=VALUE",
    help="Hold a term at a value: said as assumed.",
)
@click.option(
    "--explain",
    is_flag=True,
    help="The design matrix, the terms, their errors and why each setting moves or not.",
)
def turn_cmd(file_id, reads, csv_path, resolution, repeatability, assumes, explain):
    """Keep what the piece printed from the kept slice FILE_ID reads as its printer's next
    turn, and say what it implies. Nothing is applied: `tuning apply` does that."""
    from ..slicer import service

    record = service.get_record(file_id)
    if record is None:
        raise click.UsageError(f"no slice made {file_id!r}, or its file is not kept")
    values = _read_csv(csv_path) if csv_path else {}
    for name, read in _pairs(reads, "--read").items():
        values.setdefault(name, []).extend(read)
    assumed = {k: v[0] for k, v in _pairs(assumes, "--assume").items()}
    try:
        doc, turn = tn.add_turn(
            record,
            values,
            tn.Instrument(resolution=resolution, repeatability=repeatability),
            assumed,
        )
    except (tn.Refused, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"{turn.id}: {tn.said(turn)}")
    for p in turn.proposed:
        click.echo(f"  {p.setting}: {p.why}")
    if explain:
        single = doc.model_copy(update={"turns": [turn]})
        click.echo("")
        click.echo(_explain(single), nl=False)


def _explain(doc: tn.TuningDocument) -> str:
    text = tn.render_markdown(doc, explain=True)
    return text[text.index("## turn-") :] if "## turn-" in text else text


@tuning.command("apply")
@_with(where)
def apply_cmd(site, printer, filament, process):
    """Take the last turn's proposed changes into the printer's next slices."""
    applies = _applies(site, printer, filament, process)
    try:
        doc, changes = tn.apply(site, printer, applies)
    except tn.Refused as exc:
        raise click.ClickException(str(exc)) from exc
    for c in changes:
        before = "the profile's" if c.before is None else f"{c.before:g}"
        click.echo(f"{c.setting}: {before} -> {c.after:g}{'%' if c.unit == '%' else ' mm'}")
    click.echo(f"{printer}'s next slices for {applies.filament} take them ({doc.turns[-1].id})")


@tuning.command("undo")
@_with(where)
def undo_cmd(site, printer, filament, process):
    """Drop the last turn, and what it applied."""
    applies = _applies(site, printer, filament, process)
    try:
        doc, gone = tn.undo(site, printer, applies)
    except tn.Refused as exc:
        raise click.ClickException(str(exc)) from exc
    held = ", ".join(f"{k} {h.value:g}" for k, h in doc.settings.items()) or "nothing"
    click.echo(f"{gone.id} undone; the next slices take {held}")


@tuning.command("history")
@_with(where)
def history_cmd(site, printer, filament, process):
    """Each setting's term over the turns kept, and whether its error is shrinking,
    oscillating, not responding or growing."""
    applies = _applies(site, printer, filament, process)
    doc = tn.load(site, printer, applies)
    if doc is None or not doc.turns:
        raise click.ClickException(f"{printer} has no turn for {applies.filament}")
    for setting in tn.SETTINGS:
        points = tn.points(doc.turns, setting)
        if not points:
            continue
        trend = pt.trend(setting.term, points)
        unit = pt.term(setting.term).unit if setting.term in pt.TERM_NAMES else ""
        line = ", ".join(
            f"{p.turn} "
            + ("-" if p.value is None else _term(p.value, unit))
            + (" *" if p.stepped else "")
            for p in points
        )
        click.echo(f"{setting.key} ({setting.term}): {line}")
        click.echo(f"  {trend.state}: {trend.said}")
    click.echo("* a change for it was applied after that turn")


def _term(v: float, unit: str) -> str:
    return f"{v:+.3f} mm" if unit == "mm" else f"{v:+.3%}"


@tuning.command("schema")
def schema_cmd():
    """Print the JSON Schema of print/tuning/1."""
    click.echo(json.dumps(tn.TuningDocument.model_json_schema(by_alias=True), indent=2))


@tuning.command("validate")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--format", "fmt", type=click.Choice(["summary", "json", "md"]), default="summary")
def validate_cmd(path: Path, fmt: str):
    """Read a tuning document back: a summary, the document normalized, or Markdown."""
    try:
        doc = tn.TuningDocument.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        click.echo(f"Invalid tuning document: {path}", err=True)
        for err in exc.errors():
            loc = ".".join(str(x) for x in err.get("loc", ()))
            click.echo(f"  {loc}: {err.get('msg')}", err=True)
        raise SystemExit(1) from exc
    if fmt == "json":
        click.echo(json.dumps(doc.model_dump(mode="json", by_alias=True), indent=2))
    elif fmt == "md":
        click.echo(tn.render_markdown(doc), nl=False)
    else:
        click.echo(
            f"OK {doc.schema_} · {doc.printer.site}'s {doc.printer.node} · "
            f"{doc.applies_to.filament} · {len(doc.turns)} turns, {len(doc.settings)} settings held"
        )
