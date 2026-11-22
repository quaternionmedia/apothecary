"""``apothecary bed``: what a printer's bed readings say, and the shims that level it.

``bed runs`` lists the readings of a printer's pinned board, each heated or cold.
``bed shims`` turns the newest heated pair, or the readings named, into the least shims
that level the bed on its solid mounts (``apothecary/bed_shims.py``), and says the command
that slices them. ``bed compare`` sets readings taken after fitting them beside those
taken before. Each reads the state folder's readings and the printer's profile: no port
is opened and nothing is sent to a printer. Heating the bed and probing it are done on
the bench, from the printer's Machine.
"""

from __future__ import annotations

import json
from typing import Dict, Tuple

import click

from .. import bed_shims as bs

where = [
    click.option("--site", required=True, help="The site the printer stands in."),
    click.option("--printer", required=True, help="The printer's node in the site."),
]


def _where(fn):
    for option in reversed(where):
        fn = option(fn)
    return fn


@click.group()
def bed():
    """What a printer's bed readings say, and the shims that level it: runs, shims, compare."""


def _fitted(given: Tuple[str, ...]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for item in given:
        name, sep, value = item.partition("=")
        if not sep or not name.strip():
            raise click.UsageError(f"--fitted is LABEL=MM: not {item!r}")
        try:
            out[name.strip()] = float(value)
        except ValueError:
            raise click.UsageError(f"--fitted is LABEL=MM: not {item!r}") from None
    return out


def _or_die(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except bs.ShimError as exc:
        raise click.ClickException(str(exc)) from exc


@bed.command("runs")
@_where
@click.option("--json-out/--text", default=False)
def bed_runs(site: str, printer: str, json_out: bool):
    """The bed readings of a printer's pinned board, newest first: each one's bed
    temperature, heated or cold, its range and its note."""
    board = _or_die(bs.pinned_board, site, printer)
    found = bs.readings(board)
    rows = [
        {
            **_run_json(bs.run_of(r)),
            "range": r.stats.get("range"),
            "rows": len(r.mesh),
            "cols": len(r.mesh[0]) if r.mesh else 0,
        }
        for r in found
    ]
    if json_out:
        click.echo(json.dumps({"board": board, "runs": rows}, indent=2))
        return
    if not rows:
        click.echo(f"{board}: no bed reading yet")
        return
    for r, row in zip(found, rows, strict=True):
        span = f"range {row['range']:.3f} mm" if row["range"] is not None else "no range"
        click.echo(f"{bs.run_of(r).said()}: {row['rows']} x {row['cols']}, {span}")


@bed.command("shims")
@_where
@click.option(
    "--reading",
    "reading_ids",
    multiple=True,
    help="A reading of the printer's board by its id; repeatable, and their mean is used "
    "(default: the newest, with the one before it when both are heated probes).",
)
@click.option(
    "--fitted",
    multiple=True,
    metavar="LABEL=MM",
    help="A shim on that screw now, by its label: the new set is computed to replace "
    "it. Repeatable; a screw not named has none.",
)
@click.option("--json-out/--text", default=False)
def bed_shims(
    site: str, printer: str, reading_ids: Tuple[str, ...], fitted: Tuple[str, ...], json_out: bool
):
    """The least shims that level a printer's bed on its solid mounts, from its newest
    heated pair of readings.

    \b
    The plane through the readings' mean is taken at each screw the printer's
    profile holds (measured.bed_screws). The highest corner gets no shim; each
    other gets what lifts it to the highest, rounded to a layer, unless that is
    under one layer or under the readings' repeatability floor. What the plane
    leaves is the plate's own shape, which shims cannot fix, and is said against
    the profile's bound for a stored mesh. The command that slices them for the
    printer is printed last. Nothing is sent to the printer.
    """
    found = _or_die(bs.for_printer, site, printer, reading_ids=reading_ids, fitted=_fitted(fitted))
    if json_out:
        click.echo(json.dumps(shims_json(found), indent=2))
        return
    for line in found.said():
        click.echo(line)
    click.echo("")
    command = found.slice_command()
    if command is None:
        click.echo("no corner needs a shim: the bed is as level as shims make it")
        return
    click.echo(f"slice them: uv run {command}")
    click.echo(
        "then: print them, fit each on the mount its label names, heat the bed and let it soak, "
        "probe it twice, and compare (apothecary bed compare)"
    )


@bed.command("compare")
@_where
@click.option(
    "--before", "before_ids", multiple=True, required=True, help="A reading before; repeatable."
)
@click.option(
    "--after", "after_ids", multiple=True, required=True, help="A reading after; repeatable."
)
@click.option("--json-out/--text", default=False)
def bed_compare(
    site: str, printer: str, before_ids: Tuple[str, ...], after_ids: Tuple[str, ...], json_out: bool
):
    """Readings taken after fitting shims beside those taken before: what each corner
    needs in each, and how far the mean moved at any point."""
    before = _or_die(bs.for_printer, site, printer, reading_ids=before_ids)
    after = _or_die(bs.for_printer, site, printer, reading_ids=after_ids)
    moved = _or_die(bs.difference, [before.mesh], [after.mesh])
    flat = [v for row in moved for v in row]
    if json_out:
        click.echo(
            json.dumps(
                {
                    "before": shims_json(before),
                    "after": shims_json(after),
                    "difference": {"mesh": moved, "min": min(flat), "max": max(flat)},
                },
                indent=2,
            )
        )
        return
    for word, found in (("before", before), ("after", after)):
        click.echo(f"{word}: " + "; ".join(r.id for r in found.runs))
        click.echo(
            f"  range {_range(found.mesh):.3f} mm, the plane leaving {found.bow:.3f}; tilt "
            f"{found.plane.a * 100:+.3f} / {found.plane.b * 100:+.3f} mm per 100 mm along X / Y"
        )
    for b, a in zip(before.shims, after.shims, strict=True):
        click.echo(
            f"  {b.screw.label:>3} needed {b.thickness:.3f} mm before, {a.thickness:.3f} after"
        )
    click.echo(f"after less before: {min(flat):+.3f}..{max(flat):+.3f} mm at any point")


def _range(mesh) -> float:
    flat = [v for row in mesh for v in row]
    return max(flat) - min(flat)


def _run_json(run: bs.Run) -> dict:
    return {
        "id": run.id,
        "at": run.at.isoformat() if run.at else None,
        "method": run.method,
        "bed_c": run.bed_c,
        "heated": run.heated,
        "note": run.note,
    }


def shims_json(found: bs.Shims) -> dict:
    """What ``bed shims --json-out`` says, and the page draws."""
    least, most, rms = found.residual
    return {
        "runs": [_run_json(r) for r in found.runs],
        "screws_from": found.screws_from,
        "grid": {
            "x": [found.area.x0, found.area.x1],
            "y": [found.area.y0, found.area.y1],
            "from": found.area.source,
        },
        "mesh": found.mesh,
        "range": _range(found.mesh),
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
        "bound": found.bound,
        "left": round(found.left, 4),
        "outside": round(found.outside, 2),
        "params": found.params(),
        "slice": found.slice_command(),
    }
