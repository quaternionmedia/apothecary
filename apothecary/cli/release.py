"""`apothecary release`: what a downstream may pin, and what stands in the way.

This repository is consumed by pinned downstreams, and the enclosure record
asks them to depend on a *released* version rather than a commit. That is an
obligation on this side too: geometry reaches a consumer by publishing, and a
contributor here had no way to learn that until it was written down somewhere
the code could point at.
"""

from __future__ import annotations

import click

from ..release import consumers_waiting, published_versions, readiness
from . import status


@click.command()
@click.option(
    "--check",
    "check_only",
    is_flag=True,
    help="Exit non-zero unless this commit could legitimately be released.",
)
def release(check_only: bool) -> None:
    """Whether this commit is something a downstream project may depend on.

    Publishing is a human act and this command does none of it. It reports
    whether the act would be legitimate right now, and names what is missing
    if not.
    """
    report = readiness()

    status.heading("what downstream sees")
    status.detail(f"declared version: {report.version or 'none'}")
    status.detail(f"published tags:   {', '.join(report.published) or 'none yet'}")
    status.detail(f"pinned by:        {', '.join(consumers_waiting())}")
    click.echo("")

    if report.releasable:
        status.verdict(True, f"this commit could be released as {report.version}")
    else:
        status.heading("not releasable")
        for reason in report.reasons:
            status.line("blocked", reason)
        click.echo("")
        # The consumer's side of this is already automated: it reports the
        # deviation while nothing is published and fails once something is, so
        # nobody has to remember to go and tighten it.
        status.verdict(
            False,
            "downstream is pinned to a commit until this repository publishes",
            warn=True,
        )

    if not published_versions():
        click.echo("")
        status.detail(
            "Nothing has ever been released here, so every consumer is pinned to a "
            "commit by necessity rather than by choice."
        )

    if check_only and not report.releasable:
        raise SystemExit(1)
