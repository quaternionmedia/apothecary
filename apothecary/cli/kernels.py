"""Print the reference's numbers for the kernel-comparison corpus."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Tuple

import click


@click.command("kernel-reference")
@click.option(
    "--case",
    "names",
    multiple=True,
    help="A case of the corpus (repeatable); the whole corpus by default.",
)
@click.option(
    "--openscad",
    "openscad",
    default=None,
    help="An OpenSCAD with Manifold to use, instead of the one found.",
)
@click.option("--json", "as_json", is_flag=True, help="One JSON object per case, not a table.")
@click.option("--list", "list_only", is_flag=True, help="Name the cases and stop.")
def kernel_reference(names: Tuple[str, ...], openscad: str | None, as_json: bool, list_only: bool):
    """Render the corpus with OpenSCAD's Manifold backend and print what it measures.

    The reference a geometry kernel is compared with (see
    docs/plans/rust-geometry-kernels-2026-10-09.md and
    tests/test_kernel_comparison.py): per case, triangles, volume, surface
    area, bounding box, watertightness, manifoldness and render seconds.
    Exits 1, saying why, when this machine has no OpenSCAD with Manifold.
    """
    from .. import kernel_compare as kc

    if list_only:
        for case in kc.CASES:
            click.echo(f"{case.name:<24}{case.group:<11}{case.why}")
        return
    try:
        cases = [kc.case_named(n) for n in names] or list(kc.CASES)
        executable = kc.reference_openscad(openscad)
    except (KeyError, kc.ReferenceUnavailable) as refusal:
        click.echo(str(refusal.args[0]), err=True)
        sys.exit(1)
    with tempfile.TemporaryDirectory(prefix="apothecary-kernels-") as scratch:
        try:
            references = kc.run_reference(cases, Path(scratch), executable)
        except RuntimeError as failure:
            click.echo(str(failure), err=True)
            sys.exit(1)
        click.echo(f"# reference: {executable} --backend=manifold", err=True)
        click.echo(kc.reference_table(references, as_json=as_json), nl=False)
