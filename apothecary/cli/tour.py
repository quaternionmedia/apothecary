"""What a person said of the tour's steps, from the command line (apothecary/tour.py)."""

from __future__ import annotations

import click

from .. import tour as the_tour


@click.command("tour")
@click.option("--off", is_flag=True, help="Only the steps a person said are off.")
@click.option("--page", default=None, help="Only this walkthrough page (its file name or number).")
def tour(off: bool, page: str | None) -> None:
    """What a person said of each step of the tour (⊞ Windows › Tour in the viewer).

    A page a step at a time, each step's latest verdict -- as shown, or off with what
    is off -- and the commit the server ran when it was said. The verdicts are kept
    under the state folder, in tour/verdicts.jsonl.
    """
    given = the_tour.answers()
    shown = [
        s
        for s in the_tour.stops()
        if page is None or page in (s.page, s.number, s.page.removesuffix(".md"))
    ]
    if page is not None and not shown:
        raise click.ClickException(f"no walkthrough page {page}")
    for stop in shown:
        steps = [(st.index, st.heading) for st in stop.steps] or [(0, "the page, read whole")]
        mine = [(i, heading, given.get((stop.page, i))) for i, heading in steps]
        counts = {v: sum(1 for *_, r in mine if r and r["verdict"] == v) for v in the_tour.VERDICTS}
        waiting = sum(1 for *_, r in mine if r is None)
        if off and not counts["off"]:
            continue
        click.echo(
            f"{stop.number} {stop.title}: {counts['as shown']} as shown, "
            f"{counts['off']} off, {waiting} not yet"
        )
        for i, heading, record in mine:
            if record is None or (off and record["verdict"] != "off"):
                continue
            mark = "✓" if record["verdict"] == "as shown" else "✗"
            note = f": {record['note']}" if record.get("note") else ""
            against = record.get("commit") or "an unknown commit"
            changed = ", changed" if record.get("changed") else ""
            click.echo(f"  {mark} {i}. {heading}{note} ({against}{changed}, {record['at']})")
    click.echo(f"Kept in {the_tour.verdicts_path()}")
