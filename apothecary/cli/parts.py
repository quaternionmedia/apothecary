"""Parts-related CLI commands: parts group and subcommands."""

import json
import tempfile
from pathlib import Path

import click

from ..projects.parts.skeleton import ROOT
from ..projects.parts.stl_renderer import read_params_sidecar, write_params_sidecar
from ..projects.registry import scan_projects
from ..templates import TemplateRenderer
from . import status
from .utils import (
    _get_stl_bounding_box,
    _load_part_wrapper,
    _parse_param_overrides,
    _safe_echo,
)


@click.group()
def parts():
    """Commands for part wrappers."""


@parts.command("list")
@click.option("--json-out/--text", default=False)
def parts_list(json_out: bool):
    items = [p for p in scan_projects(Path(".").resolve()) if p.kind == "part"]
    if json_out:
        click.echo(json.dumps([p.to_json() for p in items], indent=2))
        return
    for p in items:
        click.echo(f"{p.name} (wrapper={p.wrapper})")


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
            box = _get_stl_bounding_box(measured_stl)

        if box is None:
            skipped.append((part_name, "could not measure STL"))
            continue

        min_x, max_x, min_y, max_y, min_z, max_z = box
        actual = (max_x - min_x, max_y - min_y, max_z - min_z)
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
    if part.params_model:
        params = part.params_model(**params_data)
        params_json_out = params.model_dump_json()
    else:
        params_json_out = "{}"
    # Choose template
    if template:
        tpl_str = Path(template).read_text(encoding="utf-8")
    else:
        default_tpl = Path("templates/part.include.scad.j2")
        tpl_str = (
            default_tpl.read_text(encoding="utf-8")
            if default_tpl.exists()
            else "// {{ part.name }}\ninclude <{{ source_posix }}>"
        )
    # Render
    renderer = TemplateRenderer()
    ctx = {
        "part": part,
        "params_json": params_json_out,
        "source_posix": part.source_file.as_posix(),
    }
    code = renderer.render_template(tpl_str, ctx)
    Path(output).write_text(code, encoding="utf-8")
    click.echo(f"Rendered part '{part.name}' -> {output}")


@parts.command("generate-stl")
@click.argument("name", required=False)
@click.option("--all", "generate_all", is_flag=True, help="Generate STL for all parts")
@click.option("--force", is_flag=True, help="Regenerate even if STL exists")
@click.option(
    "--param",
    "-p",
    "param_pairs",
    multiple=True,
    metavar="NAME=VALUE",
    help="Override a part parameter. Repeatable. Implies --force.",
)
@click.option("--timeout", default=120, type=int, help="Timeout per part in seconds")
def parts_generate_stl(
    name: str | None,
    generate_all: bool,
    force: bool,
    timeout: int,
    param_pairs: tuple[str, ...] = (),
):
    """Generate STL files from SCAD sources.

    STL files are not committed to git (they're in .gitignore).
    This command regenerates them from the source SCAD files.

    Examples:
        apothecary parts generate-stl calibration_cube
        apothecary parts generate-stl --all
        apothecary parts generate-stl --all --force
    """
    from ..projects.parts.stl_renderer import get_renderer

    renderer = get_renderer()

    if not renderer.is_available:
        raise click.ClickException(
            "OpenSCAD not found. Please install OpenSCAD to generate STL files.\n"
            "Download from: https://openscad.org/downloads.html"
        )

    click.echo(f"Using OpenSCAD: {renderer.openscad_path}")
    click.echo("")

    if generate_all:
        # Generate for all parts
        items = [p for p in scan_projects(ROOT) if p.kind == "part"]
        click.echo(f"Generating STL for {len(items)} parts...")
        click.echo("")

        success_count = 0
        fail_count = 0
        skip_count = 0

        for item in status.iterate(items, "Rendering"):
            scad_path = item.path
            stl_path = scad_path.with_suffix(".stl")

            # Try to load part wrapper for display_rotation and custom STL path
            rotation = None
            can_generate = True
            skip_reason = None
            custom_openscad = None
            part = None
            try:
                mod = _load_part_wrapper(item.name)
                if hasattr(mod, "DEFAULT"):
                    part = mod.DEFAULT
                    # Use custom STL output path if available
                    if hasattr(part, "get_stl_output_path"):
                        stl_path = part.get_stl_output_path()
                    # Check if part can generate STL
                    if hasattr(part, "can_generate_stl"):
                        can_gen, reason = part.can_generate_stl()
                        if not can_gen:
                            can_generate = False
                            skip_reason = reason
                    # Get custom OpenSCAD path (e.g., nightly build)
                    if hasattr(part, "get_openscad_path"):
                        custom_openscad = part.get_openscad_path()
                    # Get display rotation
                    if hasattr(part, "display_rotation"):
                        rot = part.display_rotation
                        if rot and rot.to_list() != [0, 0, 0]:
                            rotation = rot.to_list()
            except Exception:
                pass  # Fall back to defaults

            # Skip parts that can't generate STL
            if not can_generate:
                _safe_echo(f"  • {item.name}: Cannot generate ({skip_reason})")
                skip_count += 1
                continue

            # Check if we should skip
            if stl_path.exists() and not force:
                _safe_echo(f"  • {item.name}: STL exists (use --force to regenerate)")
                skip_count += 1
                continue

            click.echo(f"  Generating {item.name}...", nl=False)

            # Use custom OpenSCAD path if needed
            part_renderer = renderer
            if custom_openscad and custom_openscad != renderer.openscad_path:
                from ..projects.parts.stl_renderer import OpenSCADRenderer

                part_renderer = OpenSCADRenderer(openscad_path=str(custom_openscad))
                click.echo(f" (using {custom_openscad.name})", nl=False)

            if rotation:
                result = part_renderer.render_stl_with_rotation(
                    scad_path, stl_path, rotation=rotation, timeout=timeout
                )
            else:
                result = part_renderer.render_stl(scad_path, stl_path, timeout=timeout)

            if result.success:
                _safe_echo(click.style(f" OK ({result.render_time_seconds:.1f}s)", fg="green"))
                success_count += 1
            else:
                _safe_echo(click.style(f" FAIL {result.error_message}", fg="red"))
                fail_count += 1

        click.echo("")
        click.echo(f"Results: {success_count} generated, {skip_count} skipped, {fail_count} failed")

        if fail_count > 0:
            raise SystemExit(1)

    elif name:
        # Generate for a single part
        mod = _load_part_wrapper(name)
        part = mod.DEFAULT

        if not part.source_file.exists():
            raise click.ClickException(f"Source file not found: {part.source_file}")

        # Check if this part has special requirements
        if hasattr(part, "can_generate_stl"):
            can_gen, reason = part.can_generate_stl()
            if not can_gen:
                raise click.ClickException(f"Cannot generate STL for '{name}': {reason}")

        # Use part-specific OpenSCAD path if available (e.g., nightly build)
        part_renderer = renderer
        if hasattr(part, "get_openscad_path"):
            custom_path = part.get_openscad_path()
            if custom_path and custom_path != renderer.openscad_path:
                from ..projects.parts.stl_renderer import OpenSCADRenderer

                part_renderer = OpenSCADRenderer(openscad_path=str(custom_path))
                click.echo(f"Using OpenSCAD: {custom_path} (required by {name})")

        stl_path = part.get_stl_output_path()

        # Validate before rendering: OpenSCAD accepts any -D name, defined or
        # not, so a typo would render the defaults and look like a success.
        params = _parse_param_overrides(part, param_pairs)

        if stl_path.exists() and not force and not params:
            click.echo(f"STL already exists: {stl_path}")
            click.echo("Use --force to regenerate")
            return

        click.echo(f"Generating STL for {part.name}...")
        if params:
            click.echo(f"  Parameters: {params}")

        # Apply display rotation if defined
        rotation = part.display_rotation.to_list() if part.display_rotation else None
        if rotation and rotation != [0, 0, 0]:
            click.echo(f"  Applying display rotation: {rotation}")
            result = part_renderer.render_stl_with_rotation(
                part.source_file, stl_path, rotation=rotation, timeout=timeout, params=params
            )
        else:
            result = part_renderer.render_stl(
                part.source_file, stl_path, timeout=timeout, params=params
            )

        if result.success:
            write_params_sidecar(stl_path, params)
            status.line(
                "pass",
                f"Generated {stl_path.name} in {result.render_time_seconds:.1f}s",
                indent=0,
            )
        else:
            raise click.ClickException(f"Generation failed: {result.error_message}")

    else:
        raise click.ClickException("Specify a part name or use --all")


@parts.command("elephant-walk")
@click.option("--output", "-o", type=click.Path(dir_okay=False), default=None)
@click.option("--gap", default=10, type=int, help="Gap between parts in mm")
@click.option("--ensure-stl/--no-ensure-stl", default=True, help="Generate missing STLs first")
def parts_elephant_walk(output: str, gap: int, ensure_stl: bool):
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
    # Default output to parts/elephant_walk.scad
    if output is None:
        output = str(ROOT / "parts" / "elephant_walk.scad")

    # Per-part rotation overrides (rotate before calculating bounds)
    # Format: name -> (rx, ry, rz) rotation in degrees

    # Filter out elephant_walk itself and only include parts in subdirs
    items = [
        p for p in scan_projects(ROOT) if p.kind == "part" and "elephant" not in p.name.lower()
    ]

    if not items:
        raise click.ClickException("No parts found")

    # Ensure STL files exist
    if ensure_stl:
        from ..projects.parts.stl_renderer import get_renderer

        renderer = get_renderer()

        if renderer.is_available:
            missing = []
            for item in items:
                stl_path = item.path.with_suffix(".stl")
                if not stl_path.exists():
                    missing.append(item)

            if missing:
                click.echo(f"Generating {len(missing)} missing STL files...")
                for item in missing:
                    stl_path = item.path.with_suffix(".stl")
                    click.echo(f"  {item.name}...", nl=False)
                    result = renderer.render_stl(item.path, stl_path, timeout=120)
                    if result.success:
                        _safe_echo(" ✓", fg="green")
                    else:
                        _safe_echo(f" ✗ {result.error_message}", fg="red")
                click.echo("")

    # Calculate bounding boxes and positions
    click.echo("Calculating bounding boxes...")
    part_data = []
    for item in items:
        stl_path = item.path.with_suffix(".stl")
        bbox = _get_stl_bounding_box(stl_path)
        if bbox:
            min_x, max_x, min_y, max_y, min_z, max_z = bbox
            width = max_x - min_x
            depth = max_y - min_y
            height = max_z - min_z
            # Center offset to place part's center at origin
            center_x = (min_x + max_x) / 2
            center_y = (min_y + max_y) / 2
            part_data.append(
                {
                    "item": item,
                    "width": width,
                    "depth": depth,
                    "height": height,
                    "center_x": center_x,
                    "center_y": center_y,
                    "min_y": min_y,
                    "max_y": max_y,
                }
            )
            click.echo(f"  {item.name}: {width:.1f} x {depth:.1f} x {height:.1f} mm")
        else:
            # Fallback for parts without valid STL
            part_data.append(
                {
                    "item": item,
                    "width": 50,
                    "depth": 50,
                    "height": 50,
                    "center_x": 0,
                    "center_y": 0,
                    "min_y": -25,
                    "max_y": 25,
                }
            )
            click.echo(f"  {item.name}: (using default size)")

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
        f"// Parts: {len(items)}, Gap: {gap}mm",
        "",
        "// Import STL files - positioned to avoid collisions",
    ]

    # Generate import statements with calculated positions
    for _i, (data, x_pos) in enumerate(zip(part_data, x_positions, strict=False)):
        item = data["item"]
        rel_path = item.path.relative_to(ROOT / "parts").with_suffix(".stl")
        # Translate to center the part at x_pos, and center Y at 0
        translate_x = x_pos - data["center_x"]
        translate_y = -data["center_y"]
        lines.append(
            f"// {item.name} ({data['width']:.1f} x {data['depth']:.1f} x {data['height']:.1f} mm)"
        )
        lines.append(f"translate([{translate_x:.2f}, {translate_y:.2f}, 0])")
        lines.append(f'    import("{rel_path.as_posix()}");')
        lines.append("")

    content = "\n".join(lines)
    Path(output).write_text(content, encoding="utf-8")
    total_width = x_positions[-1] + part_data[-1]["width"] / 2 if x_positions else 0
    click.echo(
        f"Generated elephant walk: {len(items)} parts, {total_width:.1f}mm total width -> {output}"
    )
