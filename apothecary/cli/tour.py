"""What a person said of the tour's stops, from the command line (apothecary/tour.py)."""

from __future__ import annotations

import click

from .. import tour as the_tour


@click.command("tour")
@click.option("--off", is_flag=True, help="Only the stops a person said are off.")
def tour(off: bool) -> None:
    """What a person said of each stop of the tour (Tour, in the viewer's header).

    The roadmap's lines in their order (docs/ROADMAP.md), each with its stops -- a
    journey's stages, a walkthrough page -- and each stop's latest answer: as shown, or
    off with what is off, and the commit the server ran when it was said. A line that
    names nothing is shown by nothing. The answers are kept under the state folder, in
    tour/answers.jsonl.
    """
    doc = the_tour.document()
    group = None
    for line in doc["lines"]:
        stops = line["stops"]
        given = [s["answer"] for s in stops]
        counts = {
            v: sum(1 for a in given if a and a["verdict"] == v) for v in the_tour.VERDICTS
        }
        if off and not counts["off"]:
            continue
        if line["group"] != group:
            group = line["group"]
            click.echo(group)
        if line["shown_by_nothing"]:
            click.echo(f"  {line['text']} shown by nothing")
            continue
        waiting = sum(1 for a in given if a is None)
        click.echo(
            f"  {line['text']} {counts['as shown']} as shown, {counts['off']} off, "
            f"{waiting} not yet"
        )
        for s in stops:
            record = s["answer"]
            if record is None or (off and record["verdict"] != "off"):
                continue
            mark = "✓" if record["verdict"] == "as shown" else "✗"
            name = s["title"] if s["kind"] == "stage" else f"{s['number']} {s['title']}"
            note = f": {record['note']}" if record.get("note") else ""
            against = record.get("commit") or "an unknown commit"
            changed = ", changed" if record.get("changed") else ""
            click.echo(f"    {mark} {name}{note} ({against}{changed}, {record['at']})")
    for page in doc["not_on_the_roadmap"]:
        click.echo(f"Not on the roadmap: {page}")
    click.echo(f"Kept in {the_tour.answers_path()}")
