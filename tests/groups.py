"""Which unit tests a change reaches: the unit suite in groups, each named for a part of
the package, with the sources it stands on and the files that hold it.

`apothecary test changed` runs the unit files of the groups a change reaches, and the
walkthrough's pages, then the browser files of the areas it reaches
(tests/e2e/areas.py): every unit file when it touches shared ground -- the package's
core, the app, the suite's own conftest, the dependencies -- a unit file itself when
it changes, none when it reaches no group. A helper of the suite, a module in tests/
or tests/e2e/ that is no test file, reaches the unit files that import it, directly or
through other helpers, with the groups whose sources name it; every unit file when a
conftest imports it, since a fixture any file asks for may stand on it.
`apothecary test group NAME...` runs named groups. The run before a merge is
`apothecary test all` on the stack's head, the whole suite.

    python tests/groups.py FILE...   # the unit files a change to FILE... reaches, or ALL

Who imports a helper is read from the import statements of the suite's modules, one
inside a function too; a helper a test loads by path or runs in a script of its own is
named in its group's sources instead. tests/e2e/areas.py reads the browser files'
imports through `importers` too. tests/test_groups.py holds that every unit file is in
one group and that every pattern names something this checkout tracks.
"""

from __future__ import annotations

import ast
import fnmatch
import functools
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
TESTS = "tests"
ALL = "ALL"

# The directories whose modules import one another by name: the browser suite puts
# tests/ on its path and a unit file may put tests/e2e/ on its own.
SUITE = ("tests", "tests/e2e")

# The conftests every unit file runs under.
CONFTESTS = ("conftest.py", "tests/conftest.py")

# Ground every group stands on: a change here runs every unit file.
SHARED = (
    "apothecary/__init__.py",
    "apothecary/api.py",
    "apothecary/core.py",
    "apothecary/models/*",
    "apothecary/hierarchy.py",
    "apothecary/objects.py",
    "apothecary/scene.py",
    "apothecary/transforms.py",
    "apothecary/primitives.py",
    "apothecary/example_hierarchy.py",
    "apothecary/site_store.py",
    "apothecary/sites.py",
    "apothecary/picture_root.py",
    "apothecary/stays_local.py",
    "apothecary/routes/__init__.py",
    "conftest.py",
    "tests/conftest.py",
    "pyproject.toml",
    "uv.lock",
)

# Each group: the sources a change to which reaches it, and the unit files that hold it.
GROUPS = {
    "machines": {
        "sources": (
            "apothecary/firmware/*",
            "apothecary/jobs.py",
            "apothecary/machine_plans.py",
            "apothecary/projector.py",
            "apothecary/homography.py",
            "apothecary/surfaces.py",
            "apothecary/routes/surfaces.py",
            "apothecary/simulated.py",
            "apothecary/routes/jobs.py",
            "apothecary/routes/machines.py",
            "apothecary/routes/projector.py",
            "apothecary/cli/firmware.py",
            "apothecary/state_folder.py",
            "parts/esp32_blink/*",
            "parts/footpedal/*",
            "parts/boards/*",
            "parts/ender3/*",
            "parts/anolex_4060_evo_ultra_2/*",
            "tests/firmware_helpers.py",
            "apothecary/static/can.js",
            "walkthrough/19-*",
        ),
        "tests": (
            "test_board_by_part.py",
            "test_can_js.py",
            "test_can_now.py",
            "test_deck_screens.py",
            "test_firmware_api.py",
            "test_firmware_deck.py",
            "test_firmware_deck_control.py",
            "test_firmware_devices.py",
            "test_firmware_files_by_kind.py",
            "test_firmware_gcode.py",
            "test_firmware_grbl.py",
            "test_firmware_modules.py",
            "test_firmware_ports.py",
            "test_firmware_ports_move.py",
            "test_firmware_seam.py",
            "test_firmware_table_map.py",
            "test_jobs.py",
            "test_job_api.py",
            "test_machine_frame.py",
            "test_machine_plans.py",
            "test_machine_words.py",
            "test_projector.py",
            "test_rust_installer.py",
            "test_state_folder.py",
            "test_stream_deck_part.py",
            "test_surfaces.py",
            "test_whiteboard_part.py",
            "test_simulated.py",
        ),
    },
    "making": {
        "sources": (
            "apothecary/slicer/*",
            "apothecary/cam/*",
            "apothecary/preview/*",
            "apothecary/cli/slicer.py",
            "parts/router_coupon/*",
            "parts/router_emoji/*",
            "parts/ender3/*",
            "tests/slicer_helpers.py",
            "walkthrough/20-*",
            "walkthrough/21-*",
        ),
        "tests": (
            "test_slicer.py",
            "test_slicer_api.py",
            "test_slicer_measured.py",
            "test_slicer_installer.py",
            "test_cam.py",
            "test_cam_measured.py",
            "test_preview.py",
        ),
    },
    "parts": {
        "sources": (
            "apothecary/projects/*",
            "apothecary/meshes.py",
            "apothecary/fittings.py",
            "apothecary/spaces.py",
            "apothecary/airgap_metrics.py",
            "apothecary/gap_geometry.py",
            "apothecary/datum_core_site.py",
            "apothecary/openscad_installer.py",
            "apothecary/routes/part_edits.py",
            "apothecary/routes/interfaces.py",
            "apothecary/routes/airgap.py",
            "apothecary/cli/parts.py",
            "apothecary/cli/airgap.py",
            "apothecary/cli/openscad.py",
            "apothecary/cli/spaces.py",
            "parts/*",
            "tests/scripted_openscad.py",
            "tests/rendered_parts.py",
            "tests/assignment_cases.json",
            "walkthrough/43-*",
        ),
        "tests": (
            "test_airgap_metrics.py",
            "test_airgap_part.py",
            "test_assignment_cases.py",
            "test_assignments.py",
            "test_calibration_cube.py",
            "test_camera_parts.py",
            "test_contested_values.py",
            "test_customizer_params.py",
            "test_datum_core_site.py",
            "test_defaults_are_the_scad.py",
            "test_dust_parts.py",
            "test_failed_renders.py",
            "test_fittings.py",
            "test_following_a_variant.py",
            "test_gap_geometry.py",
            "test_geometry_from_elsewhere.py",
            "test_gridfinity.py",
            "test_interfaces.py",
            "test_lighter_and_faster.py",
            "test_openscad_installer.py",
            "test_openscad_messages.py",
            "test_param_controls.py",
            "test_parameter_coverage.py",
            "test_params_contract.py",
            "test_part_drafts.py",
            "test_part_interfaces.py",
            "test_part_json_parity.py",
            "test_part_loader.py",
            "test_part_variants.py",
            "test_parts_fit.py",
            "test_parts_parameters.py",
            "test_parts_stl_generation.py",
            "test_parts_wrappers.py",
            "test_rolling_rotor_part.py",
            "test_registry.py",
            "test_render_queue.py",
            "test_saved_variants.py",
            "test_snowplow_part.py",
            "test_spaces.py",
            "test_stl_renderer.py",
            "test_text_is_the_truth.py",
        ),
    },
    "scene": {
        "sources": (
            "apothecary/booleans.py",
            "apothecary/jscad.py",
            "apothecary/templates.py",
            "apothecary/example.py",
            "apothecary/kernel_compare.py",
            "apothecary/universe.py",
            "apothecary/orbitals.py",
            "apothecary/composition.py",
            "apothecary/connections.py",
            "apothecary/site_names.py",
            "apothecary/cli/render.py",
            "apothecary/cli/kernels.py",
            "templates/*",
            "examples/scenes/*",
            "examples/scripts/*",
        ),
        "tests": (
            "test_catalog_geometry.py",
            "test_composition.py",
            "test_connections.py",
            "test_datum_assembly.py",
            "test_examples.py",
            "test_garage_workbench.py",
            "test_hierarchy.py",
            "test_jscad_renderer.py",
            "test_kernel_comparison.py",
            "test_models.py",
            "test_orbitals.py",
            "test_primitives_transforms.py",
            "test_scene_labels.py",
            "test_scene_render.py",
            "test_site_api.py",
            "test_site_store.py",
            "test_staging.py",
            "test_templates.py",
            "test_universe.py",
        ),
    },
    "vision": {
        "sources": (
            "apothecary/vision/*",
            "apothecary/homography.py",
            "apothecary/surfaces.py",
            "apothecary/gathering/*",
            "apothecary/finders/*",
            "apothecary/vocabulary/*",
            "apothecary/routes/pictures.py",
            "apothecary/routes/views.py",
            "apothecary/routes/marks.py",
            "apothecary/routes/whiteboards.py",
            "apothecary/routes/cameras.py",
            "apothecary/routes/vision.py",
            "apothecary/cli/photo.py",
            "apothecary/cli/vision.py",
            "examples/pictures/*",
            "examples/llms_own/*",
            "tests/views_helpers.py",
            "tests/whiteboards_helpers.py",
        ),
        "tests": (
            "test_again.py",
            "test_finder_accuracy.py",
            "test_finder_geometry.py",
            "test_free_space.py",
            "test_gathering.py",
            "test_gathering_accuracy.py",
            "test_homography.py",
            "test_made_part.py",
            "test_made_piece_geometry.py",
            "test_marks.py",
            "test_marks_api.py",
            "test_notes.py",
            "test_outline_finder.py",
            "test_photo_hard_cases.py",
            "test_photo_in_the_viewer.py",
            "test_photo_shapes.py",
            "test_pictures_api.py",
            "test_projection.py",
            "test_switches.py",
            "test_views_api.py",
            "test_whiteboard.py",
            "test_whiteboard_history.py",
            "test_whiteboard_views.py",
            "test_vision_through_qmcp.py",
            "test_working_together.py",
        ),
    },
    "family": {
        "sources": (
            "apothecary/family/*",
            "apothecary/wiring/*",
            "apothecary/rig/*",
            "apothecary/homography.py",
            "apothecary/surfaces.py",
            "apothecary/evidence/*",
            "apothecary/routes/procedures.py",
            "apothecary/routes/wiring.py",
            "apothecary/routes/evidence.py",
            "apothecary/cli/rig.py",
            "apothecary/cli/evidence.py",
            "examples/rigs/*",
            "tests/rig_catalogue.json",
            "walkthrough/22-*",
            "walkthrough/23-*",
        ),
        "tests": (
            "test_evidence.py",
            "test_family_beside.py",
            "test_family_hub.py",
            "test_family_members.py",
            "test_family_procedures.py",
            "test_frames_cost.py",
            "test_rig.py",
            "test_site_names.py",
            "test_wiring.py",
        ),
    },
    "viewer": {
        "sources": (
            "apothecary/viewer.py",
            "apothecary/menu.py",
            "apothecary/layer_colours.py",
            "apothecary/systems.py",
            "apothecary/census.py",
            "apothecary/docs_site.py",
            "apothecary/lighting.py",
            "apothecary/console_feedback.py",
            "apothecary/theatre_site.py",
            "apothecary/routes/menu.py",
            "apothecary/routes/lighting.py",
            "apothecary/surfaces.py",
            "apothecary/routes/readme.py",
            "apothecary/static/*",
            "apothecary/cli/census.py",
            "apothecary/cli/server.py",
            "templates/fractal_viewer.html.j2",
            "templates/projector.html.j2",
            "apothecary/routes/projector.py",
            "examples/theatre-rig/*",
            "tests/conformance/*",
            "tests/ring_helpers.py",
        ),
        "tests": (
            "test_api.py",
            "test_census.py",
            "test_console_feedback.py",
            "test_lighting.py",
            "test_lighting_routes.py",
            "test_menu.py",
            "test_measure.py",
            "test_menu_routes.py",
            "test_orbits_drawn.py",
            "test_pick_scope.py",
            "test_projector_page.py",
            "test_readiness.py",
            "test_stays_local.py",
            "test_group_colours.py",
            "test_layer_colours.py",
            "test_systems.py",
            "test_journeys.py",
            "test_theatre_site.py",
            "test_viewer_assets.py",
        ),
    },
    # The tour: the journeys' stages, each with what it names to try -- a walkthrough
    # page read back as its steps -- and a person's word on each kept; a page changed
    # is what there is to try changed.
    "tour": {
        "sources": (
            "apothecary/tour.py",
            "apothecary/routes/tour.py",
            "apothecary/docs_site.py",
            "apothecary/journeys.py",
            "walkthrough/*",
        ),
        "tests": ("test_tour.py",),
    },
    "cli": {
        "sources": (
            "apothecary/cli/*",
            "apothecary/__main__.py",
            "apothecary/version.py",
            "apothecary/stamped.py",
            "apothecary/release.py",
            "apothecary/preflight.py",
            # test_cli_testing.py runs these by path or in a script of its own, which no
            # import statement shows: the suite's maps, the browser's launch.
            "tests/groups.py",
            "tests/e2e/areas.py",
            "tests/e2e/browsers.py",
        ),
        "tests": (
            "test_cli.py",
            "test_cli_extended.py",
            "test_cli_guidance.py",
            "test_cli_render_jscad.py",
            "test_cli_testing.py",
            "test_coverage_summary.py",
            "test_docs_generate.py",
            "test_every_command.py",
            "test_first_commands.py",
            "test_lighting_cli.py",
            "test_parts_cli.py",
            "test_preflight_staging.py",
            "test_stamped.py",
            "test_the_port.py",
            "test_unchanged_since_green.py",
        ),
    },
    "repository": {
        "sources": (
            "README.md",
            "CONTRIBUTING.md",
            "AGENTS.md",
            "CHANGELOG.md",
            "todo.md",
            "docs/*",
            ".github/*",
            "walkthrough/*",
            "tests/groups.py",
            "tests/e2e/*",
        ),
        "tests": (
            "test_areas.py",
            "test_groups.py",
            "test_browser_suite_is_not_gated.py",
            "test_check_integrates.py",
            "test_ci_workflows.py",
            "test_declared_dependencies.py",
            "test_docs_site.py",
            "test_e2e_helpers.py",
            "test_e2e_shards.py",
            "test_picture_blanks.py",
            "test_picture_drift.py",
            "test_readme_map.py",
            "test_readme_page.py",
            "test_the_walkthrough_is_named.py",
            "test_time_bounds.py",
        ),
    },
    # The borders docs/boundaries.md states: any module of the package can move one.
    "borders": {
        "sources": (
            "apothecary/*",
            "docs/boundaries.md",
        ),
        "tests": ("test_boundaries.py",),
    },
}


def _matches(path: str, patterns) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def files(names) -> list[str]:
    """The unit files of the groups ``names``, in the order the map holds them."""
    unknown = sorted(set(names) - set(GROUPS))
    if unknown:
        raise KeyError(f"no group named {', '.join(unknown)}: {', '.join(GROUPS)}")
    return [f"{TESTS}/{name}" for group in names for name in GROUPS[group]["tests"]]


@functools.cache
def _source(root: Path, path: str) -> str:
    return (root / path).read_text(encoding="utf-8")


@functools.cache
def _imported(root: Path, path: str) -> frozenset[str] | None:
    """The files the import statements of ``path`` may name, as paths from the root:
    each name resolved from the root and from each of the suite's directories (a
    relative one from the file's own), whether or not a file stands there. None for a
    file that does not parse, which is taken to import every name it spells."""
    try:
        tree = ast.parse(_source(root, path), filename=path)
    except SyntaxError:
        return None
    named = set()
    suite = [PurePosixPath(), *map(PurePosixPath, SUITE)]
    for node in ast.walk(tree):
        bases = suite
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            # `from x import y` may name a module x/y as well as x's attribute y.
            prefix = f"{node.module}." if node.module else ""
            modules = [node.module] if node.module else []
            modules += [prefix + alias.name for alias in node.names]
            if node.level:  # `from .x import y`, `from . import x`: the file's own package
                base = PurePosixPath(path).parent
                for _ in range(node.level - 1):
                    base = base.parent
                bases = [base]
        else:
            continue
        named.update(
            f"{(base / module.replace('.', '/')).as_posix()}.py"
            for base in bases
            for module in modules
        )
    return frozenset(named)


@functools.cache
def _modules(root: Path) -> tuple[str, ...]:
    """The suite's modules, as paths from the root, the root's conftest with them."""
    found = [root / "conftest.py", *(p for d in SUITE for p in sorted((root / d).glob("*.py")))]
    return tuple(p.relative_to(root).as_posix() for p in found if p.is_file())


@functools.cache
def _importing(root: Path, target: str) -> frozenset[str]:
    """The suite's modules whose import statements may name ``target``."""
    stem = target.rpartition("/")[2].removesuffix(".py")
    found = set()
    for module in _modules(root):
        if stem not in _source(root, module):
            continue  # a file that never spells the name imports nothing by it
        imported = _imported(root, module)
        if imported is None or target in imported:
            found.add(module)
    return frozenset(found)


def importers(path: str, root: Path = ROOT) -> set[str]:
    """The suite's modules that import ``path``, a module of the suite as a path from the
    root, directly or through other modules of the suite."""
    found, todo = set(), [path]
    while todo:
        for module in _importing(root, todo.pop()):
            if module not in found:
                found.add(module)
                todo.append(module)
    return found - {path}


def is_helper(path: str) -> bool:
    """A module of the suite that is no test file."""
    directory, _, name = path.rpartition("/")
    return directory in SUITE and name.endswith(".py") and not name.startswith("test_")


def tests_among(paths, directory: str) -> set[str]:
    """The names of the test files among ``paths`` that stand in ``directory``."""
    split = (path.rpartition("/") for path in paths)
    return {name for held, _, name in split if held == directory and name.startswith("test_")}


def reached(changed) -> list | str:
    """The unit files a change reaches, in the order the map holds them, or ALL."""
    found = set()
    for path in changed:
        if _matches(path, SHARED):
            return ALL
        directory, _, name = path.rpartition("/")
        if directory == TESTS and name.startswith("test_") and name.endswith(".py"):
            if (ROOT / path).exists():  # a file the change deletes runs nothing
                found.add(name)
            continue
        if is_helper(path):
            importing = importers(path, ROOT)
            if importing & set(CONFTESTS):
                return ALL
            found.update(tests_among(importing, TESTS))
        for group in GROUPS.values():
            if _matches(path, group["sources"]):
                found.update(group["tests"])
    held = [name for group in GROUPS.values() for name in group["tests"]]
    return [f"{TESTS}/{name}" for name in held if name in found] + sorted(
        f"{TESTS}/{name}" for name in found - set(held)
    )


def reaching(paths) -> tuple[set[str], dict[str, set[str]]]:
    """``reached`` turned round: of ``paths``, those a change to which reaches every unit
    file, and for each unit file the others a change to which reaches it. What a unit
    file stands on, by the same rules that choose what a change runs."""
    shared, each = set(), {}
    for path in paths:
        found = reached([path])
        if found == ALL:
            shared.add(path)
            continue
        for test in found:
            each.setdefault(test, set()).add(path)
    return shared, each


def main(argv=None) -> int:
    changed = sys.argv[1:] if argv is None else argv
    found = reached(changed)
    print(found if found == ALL else " ".join(found))
    return 0


if __name__ == "__main__":
    sys.exit(main())
