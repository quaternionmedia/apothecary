"""Parts-related CLI commands: parts group and subcommands."""

import json
import os
import shutil
import tempfile
from datetime import date
from importlib import import_module
from pathlib import Path

import click
from pydantic import ValidationError

from ..meshes import UNIT_SCALES, MeshError, bounds, read_mesh, transform, write_stl
from ..projects.parts.base import BasePart
from ..projects.parts.skeleton import ROOT
from ..projects.parts.stl_renderer import read_params_sidecar
from ..projects.registry import ProjectInfo, _sanitize_module_name, scan_projects
from ..templates import TemplateRenderer
from . import status
from .utils import (
    _load_part_wrapper,
    _parse_param_overrides,
    _safe_echo,
)


def _part_of(item: ProjectInfo) -> BasePart:
    """The part a registry entry names: its wrapper's DEFAULT, or a bare part
    for a SCAD that has no wrapper."""
    if item.wrapper:
        return import_module(item.wrapper).DEFAULT
    return BasePart(name=item.name, source_file=item.path)


def _stl_bounds(stl_path: Path):
    """An STL's (min, max) corners, or None when it is missing or unreadable."""
    try:
        return bounds(read_mesh(stl_path))
    except (OSError, MeshError):
        return None


@click.group()
def parts():
    """Commands for part wrappers."""


@parts.command("list")
@click.option("--json-out/--text", default=False)
def parts_list(json_out: bool):
    items = [p for p in scan_projects(ROOT) if p.kind == "part"]
    if json_out:
        click.echo(json.dumps([p.to_json() for p in items], indent=2))
        return
    for p in items:
        click.echo(f"{p.name} (wrapper={p.wrapper})")


FIELD_OF_USE = ("-NC", "-ND", "NonCommercial", "NoDerivatives", "personal")


@parts.command("import")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--name", "name", default=None, help="The part's name (default: the file's stem)")
@click.option(
    "--units",
    type=click.Choice(sorted(UNIT_SCALES)),
    default="mm",
    show_default=True,
    help="The units the file is in; it is stored in millimetres.",
)
@click.option(
    "--up",
    type=click.Choice(["z", "y"]),
    default="z",
    show_default=True,
    help="Which axis is up in the file; it is stored Z-up.",
)
@click.option("--title", default=None, help="What the thing is called where it came from")
@click.option("--author", default=None, help="Who made it")
@click.option("--url", default=None, help="Where it came from (recorded, never fetched)")
@click.option("--license", "license_id", default=None, help="Its licence, as an SPDX id")
@click.option("--note", default=None, help="Anything else worth recording")
@click.option("--category", default="imported", show_default=True)
@click.option("--tag", "tags", multiple=True, help="A tag (repeatable)")
@click.option("--force", is_flag=True, help="Replace a part of the same name")
def parts_import(
    file: Path,
    name: str | None,
    units: str,
    up: str,
    title: str | None,
    author: str | None,
    url: str | None,
    license_id: str | None,
    note: str | None,
    category: str,
    tags: tuple[str, ...],
    force: bool,
):
    """Bring a mesh made elsewhere (STL or OBJ) into parts/ as a part.

    The file is read, turned into millimetres and Z-up, and written beside a
    one-line SCAD that imports it and a part.json that records where it came
    from -- so the part lists, renders, sits in a site by its measured
    bounds, and is drawn in the world like any other. Nothing is fetched:
    the file is one the person already has.
    """
    from ..projects.parts.described import SIDECAR

    part_name = _sanitize_module_name(name or file.stem)
    folder = ROOT / "parts" / part_name
    if folder.exists() and not force:
        raise click.ClickException(f"{folder} exists; --force replaces it")
    if license_id and any(mark.lower() in license_id.lower() for mark in FIELD_OF_USE):
        # The open-license record takes no field-of-use restriction. The file
        # stays on this machine either way (STLs are ignored by git); it is
        # the repository it cannot join.
        _safe_echo(
            f"! {license_id}: a licence with a field-of-use restriction cannot be committed "
            "to this repository (the open-license record, §1). Kept here for your own use.",
            fg="yellow",
        )
    try:
        triangles = read_mesh(file)
    except MeshError as exc:
        raise click.ClickException(str(exc)) from None
    placed = transform(triangles, scale=UNIT_SCALES[units], up=up)
    lo, hi = bounds(placed)
    folder.mkdir(parents=True, exist_ok=True)
    kept = folder / f"{part_name}.mesh.stl"
    write_stl(placed, kept, name=part_name)
    # The STL a part serves is its render; for a mesh in millimetres and Z-up
    # that is the file itself, so the viewer needs no OpenSCAD to draw it.
    shutil.copyfile(kept, folder / f"{part_name}.stl")
    (folder / f"{part_name}.scad").write_text(
        f"// {part_name}: a mesh made elsewhere, brought in with `apothecary parts import`.\n"
        f"// Source: {title or file.name}"
        + (f" by {author}" if author else "")
        + (f" ({license_id})" if license_id else "")
        + "\n"
        + (f"// {url}\n" if url else "")
        + f"// The mesh is stored in millimetres, Z-up (it was {units}, {up}-up).\n"
        f'import("{kept.name}", convexity=10);\n',
        encoding="utf-8",
    )
    sidecar = {
        "name": part_name,
        "description": title or f"{file.name}, brought in from elsewhere",
        "category": category,
        "tags": list(tags) or ["imported", "mesh"],
        "bounds": {"min": [round(v, 3) for v in lo], "max": [round(v, 3) for v in hi]},
        "source": {
            "title": title,
            "author": author,
            "url": url,
            "license": license_id,
            "obtained": date.today().isoformat(),
            "note": note,
            "file": file.name,
            "units": units,
            "up": up,
        },
    }
    (folder / SIDECAR).write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    # REUSE reads a .license file beside a file that cannot carry a header.
    # (The tag names are spelled in halves so that REUSE, which reads a tag
    # anywhere in a file as that file's own declaration, does not read this
    # module as licensed under whatever the person typed.)
    if license_id or author:
        (folder / f"{kept.name}.license").write_text(
            (f"SPDX-FileCopyright{'Text'}: {author}\n" if author else "")
            + (f"SPDX-License-{'Identifier'}: {license_id}\n" if license_id else ""),
            encoding="utf-8",
        )
    size = [round(hi[i] - lo[i], 1) for i in range(3)]
    _safe_echo(
        f"✓ {part_name}: {len(placed)} triangles, {size[0]} x {size[1]} x {size[2]} mm", fg="green"
    )
    click.echo(f"  {folder.relative_to(ROOT)}/: {kept.name}, {part_name}.scad, {SIDECAR}")
    click.echo(
        "  STL files are ignored by git (.gitignore: *.stl); to share this one, un-ignore it"
    )
    click.echo("  and give it a licence the open-license record accepts.")
    click.echo(
        f"  Place it: Assembly(name=..., part_ref={part_name!r}, "
        f"footprint=BoundingBox3D(min_point=Vector3D(x={lo[0]:.1f}, y={lo[1]:.1f}, z={lo[2]:.1f}), "
        f"max_point=Vector3D(x={hi[0]:.1f}, y={hi[1]:.1f}, z={hi[2]:.1f})))"
    )


@parts.command("info")
@click.argument("name")
@click.option("--json-out/--text", default=False)
def parts_info(name: str, json_out: bool):
    mod = _load_part_wrapper(name)
    part = mod.DEFAULT
    # A consumer sizing an assembly around this part needs the envelope, not
    # just the file path. Parts that neither override get_bounds nor set
    # default_bounds report null rather than a guess.
    bounds = part.get_bounds()
    data = {
        "name": part.name,
        "source_file": str(part.source_file),
        "exists": part.exists,
        "category": part.category,
        "tags": part.tags,
        "description": part.description,
        "readme": str(part.readme_path) if part.readme_path and part.readme_path.exists() else None,
        "params_model": list(part.params_model.model_fields.keys()) if part.params_model else [],
        "bounds": bounds.model_dump(mode="json") if bounds else None,
        "stl_params": read_params_sidecar(part.get_stl_output_path()),
    }
    if json_out:
        click.echo(json.dumps(data, indent=2))
    else:
        for k, v in data.items():
            click.echo(f"{k}: {v}")


@parts.command("verify")
@click.argument("name", required=False)
@click.option("--all", "verify_all", is_flag=True, help="Verify every part that declares bounds")
@click.option(
    "--param",
    "-p",
    "param_pairs",
    multiple=True,
    metavar="NAME=VALUE",
    help="Override a part parameter before measuring. Repeatable.",
)
@click.option(
    "--tolerance",
    default=0.5,
    show_default=True,
    help="Permitted difference per axis, in mm.",
)
@click.option("--timeout", default=120, help="Timeout per part in seconds")
def parts_verify(
    name: str | None,
    verify_all: bool,
    param_pairs: tuple[str, ...],
    tolerance: float,
    timeout: int,
):
    """Check a part's declared bounds against the geometry OpenSCAD produces.

    A wrapper's ``get_bounds`` is hand-written Python beside hand-written
    OpenSCAD, and nothing has been keeping the two honest. Anything consuming
    the declared envelope -- catalog layout, an assembly sizing itself around
    the part -- is wrong by exactly the amount they have drifted apart.

    Renders to a temporary file, so the STL you are iterating on is untouched.
    """
    from ..projects.parts.stl_renderer import get_renderer

    renderer = get_renderer()
    if not renderer.is_available:
        raise click.ClickException("OpenSCAD not found; cannot measure geometry.")

    if verify_all:
        names = sorted({p.name for p in scan_projects(ROOT) if p.kind == "part" and p.wrapper})
    elif name:
        names = [name]
    else:
        raise click.ClickException("Specify a part name or use --all")

    drifted, checked, skipped = [], 0, []

    for part_name in status.iterate(names, "Verifying"):
        try:
            part = _load_part_wrapper(part_name).DEFAULT
        except click.ClickException:
            skipped.append((part_name, "no wrapper"))
            continue

        if not part.source_file.exists():
            skipped.append((part_name, "no source file"))
            continue

        params = _parse_param_overrides(part, param_pairs)
        declared = part.get_bounds(params or None)
        if declared is None:
            skipped.append((part_name, "declares no bounds"))
            continue

        with tempfile.TemporaryDirectory() as tmp:
            measured_stl = Path(tmp) / f"{part_name}.stl"
            result = renderer.render_stl(
                part.source_file, measured_stl, timeout=timeout, params=params or None
            )
            if not result.success:
                skipped.append((part_name, f"render failed: {result.error_message}"))
                continue
            box = _stl_bounds(measured_stl)

        if box is None:
            skipped.append((part_name, "could not measure STL"))
            continue

        lo, hi = box
        actual = tuple(hi[axis] - lo[axis] for axis in range(3))
        want = (declared.size.x, declared.size.y, declared.size.z)
        deltas = [abs(a - w) for a, w in zip(actual, want, strict=False)]
        ok = all(d <= tolerance for d in deltas)
        checked += 1

        if ok:
            status.line("pass", part_name, indent=0)
        else:
            drifted.append(part_name)
            status.line("fail", part_name, indent=0)

        if not ok or verify_all is False:
            click.echo(f"    {'axis':<6}{'declared':>12}{'measured':>12}{'delta':>10}")
            for axis, w, a, d in zip("xyz", want, actual, deltas, strict=False):
                flag = "" if d <= tolerance else "   <-- drift"
                click.echo(f"    {axis:<6}{w:>12.2f}{a:>12.2f}{d:>10.2f}{flag}")

    click.echo("")
    for part_name, reason in skipped:
        status.line("skip", f"{part_name}: {reason}", indent=0)
    status.verdict(
        not drifted,
        f"{checked} verified, {len(drifted)} drifted, {len(skipped)} skipped",
        warn=not drifted and bool(skipped),
    )

    if drifted:
        raise SystemExit(1)


@parts.command("checklist")
@click.argument("name", required=False)
@click.option("--all", "check_all", is_flag=True, help="Every part with a wrapper")
@click.option(
    "--build-volume",
    default=None,
    metavar="X,Y,Z",
    help="Printer build volume in mm, to check the part fits it.",
)
@click.option(
    "--tolerance", default=0.5, show_default=True, help="Permitted bounds difference, in mm."
)
def parts_checklist(name, check_all, build_volume, tolerance):
    """Is this part ready to print and check against a real one?

    Answers from what this repository already knows: the geometry, the bounds
    against the real mesh, the print settings, the dimensions its sources
    disagree about, and the black boxes it is fitted around.

    A question that could not be asked is reported as `????`, never as a tick.
    Exits non-zero if anything is blocked, so it can gate a build.
    """
    from ..projects.parts.readiness import PASS, assess

    volume = None
    if build_volume:
        try:
            volume = tuple(float(v) for v in build_volume.split(","))
            if len(volume) != 3:
                raise ValueError
        except ValueError:
            raise click.ClickException("--build-volume wants three numbers: X,Y,Z") from None

    if check_all:
        names = sorted({p.name for p in scan_projects(ROOT) if p.kind == "part" and p.wrapper})
    elif name:
        names = [name]
    else:
        raise click.ClickException("Specify a part name or use --all")

    any_blocked = False
    reports = []

    # Assessing renders and measures, so it is slow enough to watch.
    with status.progress(names, "Assessing") as bar:
        for part_name in bar:
            part = _load_part_wrapper(part_name).DEFAULT
            reports.append((part_name, assess(part, build_volume=volume, tolerance=tolerance)))

    for part_name, report in reports:
        click.echo("")
        status.heading(part_name)
        for check in report.checks:
            status.line(check.state, check.name)
            if check.detail:
                status.detail(check.detail)
            if check.fix and check.state != PASS:
                status.fix(check.fix)

        if report.ready:
            status.verdict(True, "ready to build")
        else:
            any_blocked = any_blocked or bool(report.blocked)
            summary = []
            if report.blocked:
                summary.append(f"{len(report.blocked)} blocking")
            if report.unknown:
                summary.append(f"{len(report.unknown)} unanswered")
            status.verdict(False, "not ready: " + ", ".join(summary), warn=not report.blocked)

    if len(reports) > 1:
        ready = sum(1 for _, r in reports if r.ready)
        click.echo("")
        status.verdict(
            ready == len(reports),
            f"{ready} of {len(reports)} ready to build",
            warn=ready < len(reports) and not any_blocked,
        )

    click.echo("")
    if any_blocked:
        raise SystemExit(1)


@parts.command("render")
@click.argument("name")
@click.option("--params-json", type=str, help="JSON string of parameter overrides")
@click.option(
    "--template",
    type=click.Path(exists=True, dir_okay=False),
    help="Jinja2 template file for include",
)
@click.option("--output", "-o", type=click.Path(dir_okay=False), default="part.scad")
def parts_render(name: str, params_json: str | None, template: str | None, output: str):
    mod = _load_part_wrapper(name)
    part = mod.DEFAULT
    params_data = {}
    if params_json:
        try:
            params_data = json.loads(params_json)
        except Exception as e:
            raise click.ClickException(f"Invalid JSON for --params-json: {e}") from e
    params = None
    if part.params_model:
        try:
            params = part.params_model(**params_data)
        except ValidationError as e:
            raise click.ClickException(f"Invalid parameters for '{part.name}': {e}") from e
    params_json_out = params.model_dump_json() if params else "{}"
    output_path = Path(output)

    # Special case: rc.snowplow is a Python parametric part, generate SCAD from Python
    if part.name == "rc.snowplow":
        from ..projects.parts.rc.snowplow import snowplow_assembly

        code = snowplow_assembly(**(params.model_dump() if params else {})).render()
        output_path.write_text(code, encoding="utf-8")
        click.echo(f"Rendered parametric part '{part.name}' -> {output_path}")
        return

    # Otherwise, use template rendering (legacy/generic). The stub includes the
    # source file, so writing it over that file would destroy the part.
    if output_path.resolve() == part.source_file.resolve():
        raise click.ClickException(
            f"Refusing to overwrite the part's own source file {part.source_file}; "
            "pass a different --output path."
        )
    if template:
        tpl_str = Path(template).read_text(encoding="utf-8")
    else:
        default_tpl = ROOT / "templates" / "part.include.scad.j2"
        tpl_str = (
            default_tpl.read_text(encoding="utf-8")
            if default_tpl.exists()
            else "// {{ part.name }}\ninclude <{{ source_posix }}>"
        )
    renderer = TemplateRenderer()
    ctx = {
        "part": part,
        "params_json": params_json_out,
        "source_posix": part.source_file.as_posix(),
    }
    code = renderer.render_template(tpl_str, ctx)
    output_path.write_text(code, encoding="utf-8")
    click.echo(f"Rendered part '{part.name}' -> {output_path}")


@parts.command("generate-stl")
@click.argument("name", required=False)
@click.option("--all", "generate_all", is_flag=True, help="Generate STL for all parts")
@click.option("--force", is_flag=True, help="Rebuild even an STL that is up to date")
@click.option(
    "--param",
    "-p",
    "param_pairs",
    multiple=True,
    metavar="NAME=VALUE",
    help="Override a part parameter. Repeatable. Implies --force.",
)
@click.option("--timeout", default=120, type=int, help="Timeout per part in seconds")
@click.option(
    "--openscad-path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to OpenSCAD executable",
)
def parts_generate_stl(
    name: str | None,
    generate_all: bool,
    force: bool,
    timeout: int,
    param_pairs: tuple[str, ...] = (),
    openscad_path: str | None = None,
):
    """Generate STL files from SCAD sources.

    STL files are not committed to git (they're in .gitignore); this builds
    them. An STL newer than its SCAD and wrapper, rendered with the same
    parameters, is kept unless --force is given.

    Examples:
        apothecary parts generate-stl calibration_cube
        apothecary parts generate-stl --all
        apothecary parts generate-stl --all --force
    """
    from ..projects.parts.stl_renderer import OpenSCADRenderer, build_stl, get_renderer

    # Without --openscad-path each part picks its own (get_openscad_path).
    chosen = OpenSCADRenderer(openscad_path=openscad_path) if openscad_path else None
    renderer = chosen or get_renderer()
    if not renderer.is_available:
        raise click.ClickException(
            "OpenSCAD not found. Please install OpenSCAD to generate STL files.\n"
            "Download from: https://openscad.org/downloads.html"
        )

    if generate_all and param_pairs:
        raise click.ClickException("--param overrides one part's parameters; name the part")
    if generate_all:
        to_build = [_part_of(item) for item in scan_projects(ROOT) if item.kind == "part"]
    elif name:
        to_build = [_load_part_wrapper(name).DEFAULT]
    else:
        raise click.ClickException("Specify a part name or use --all")

    click.echo(f"Using OpenSCAD: {renderer.openscad_path}")
    built = skipped = failed = 0
    for part in status.iterate(to_build, "Rendering"):
        # Validated here, before a render: OpenSCAD accepts any -D name.
        params = _parse_param_overrides(part, param_pairs)
        if params:
            click.echo(f"  {part.name} parameters: {params}")
        result = build_stl(
            part, params, force=force or bool(params), timeout=timeout, renderer=chosen
        )
        if result.skipped == "fresh":
            status.line("skip", f"{part.name}: up to date (--force rebuilds it)", indent=0)
            skipped += 1
        elif result.skipped == "refused" and generate_all:
            status.line(
                "skip", f"{part.name}: cannot build here ({result.error_message})", indent=0
            )
            skipped += 1
        elif result.success:
            took = f"{result.render_time_seconds:.1f}s"
            status.line("pass", f"{part.name}: {result.stl_path.name} in {took}", indent=0)
            for line in result.dropped:
                status.line("warn", f"OpenSCAD dropped part of it: {line}", indent=1)
            built += 1
        else:
            status.line("fail", f"{part.name}: {result.error_message}", indent=0)
            failed += 1

    if generate_all:
        click.echo(f"\nResults: {built} generated, {skipped} skipped, {failed} failed")
    if failed:
        raise SystemExit(1)


@parts.command("elephant-walk")
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Where to write it (default: .cache/elephant_walk.scad)",
)
@click.option("--gap", default=10, type=int, help="Gap between parts in mm")
@click.option(
    "--ensure-stl/--no-ensure-stl", default=True, help="Build missing or stale STLs first"
)
def parts_elephant_walk(output: Path | None, gap: int, ensure_stl: bool):
    """Generate an 'elephant walk' file showing all parts in a line.

    Creates an OpenSCAD file that imports STL files and arranges them
    in a single row along the X axis, using bounding boxes to prevent
    parts from overlapping.

    Note: This imports STL files, not SCAD modules, for reliable rendering
    regardless of how individual parts define their modules.

    Example:
        apothecary parts elephant-walk -o preview.scad
        apothecary parts elephant-walk --gap 20
    """
    # Not parts/elephant_walk.scad: that file is tracked, and this is a build product.
    output = output or ROOT / ".cache" / "elephant_walk.scad"
    parts_in_line = [
        _part_of(p)
        for p in scan_projects(ROOT)
        if p.kind == "part" and "elephant" not in p.name.lower()
    ]
    if not parts_in_line:
        raise click.ClickException("No parts found")

    if ensure_stl:
        from ..projects.parts.stl_renderer import build_stl, get_renderer

        if get_renderer().is_available:
            for part in parts_in_line:
                result = build_stl(part)
                if result.skipped == "fresh":
                    continue
                if result.success:
                    _safe_echo(f"  {part.name} ✓", fg="green")
                else:
                    _safe_echo(f"  {part.name} ✗ {result.error_message}", fg="red")

    click.echo("Calculating bounding boxes...")
    part_data = []
    for part in parts_in_line:
        box = _stl_bounds(part.get_stl_output_path())
        if box:
            lo, hi = box
            width, depth, height = (hi[axis] - lo[axis] for axis in range(3))
            part_data.append(
                {
                    "part": part,
                    "width": width,
                    "depth": depth,
                    "height": height,
                    # Center offset to place part's center at origin
                    "center_x": (lo[0] + hi[0]) / 2,
                    "center_y": (lo[1] + hi[1]) / 2,
                }
            )
            click.echo(f"  {part.name}: {width:.1f} x {depth:.1f} x {height:.1f} mm")
        else:
            # Fallback for parts without valid STL
            part_data.append(
                {
                    "part": part,
                    "width": 50,
                    "depth": 50,
                    "height": 50,
                    "center_x": 0,
                    "center_y": 0,
                }
            )
            click.echo(f"  {part.name}: (using default size)")

    # Calculate cumulative X positions (no overlap)
    x_positions = []
    current_x = 0
    for i, data in enumerate(part_data):
        half_width = data["width"] / 2
        if i == 0:
            x_positions.append(half_width)
            current_x = half_width + data["width"] / 2
        else:
            # Position so left edge is gap away from previous right edge
            x_positions.append(current_x + gap + half_width)
            current_x = x_positions[-1] + half_width

    lines = [
        "// Elephant Walk - All parts laid out in a line",
        "// Auto-generated by: apothecary parts elephant-walk",
        "//",
        "// Parts are positioned using bounding boxes to prevent overlap.",
        f"// Parts: {len(parts_in_line)}, Gap: {gap}mm",
        "",
        "// Import STL files - positioned to avoid collisions",
    ]

    # Generate import statements with calculated positions
    for data, x_pos in zip(part_data, x_positions, strict=False):
        part = data["part"]
        # import() resolves against the file doing the importing.
        rel_path = Path(os.path.relpath(part.get_stl_output_path(), output.parent)).as_posix()
        # Translate to center the part at x_pos, and center Y at 0
        translate_x = x_pos - data["center_x"]
        translate_y = -data["center_y"]
        lines.append(
            f"// {part.name} ({data['width']:.1f} x {data['depth']:.1f} x {data['height']:.1f} mm)"
        )
        lines.append(f"translate([{translate_x:.2f}, {translate_y:.2f}, 0])")
        lines.append(f'    import("{rel_path}");')
        lines.append("")

    content = "\n".join(lines)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    total_width = x_positions[-1] + part_data[-1]["width"] / 2 if x_positions else 0
    click.echo(
        f"Generated elephant walk: {len(parts_in_line)} parts, "
        f"{total_width:.1f}mm total width -> {output}"
    )
