"""Which unit tests a change reaches: the unit suite in groups, each named for a part of
the package, with the sources it stands on and the files that hold it.

`apothecary test changed` runs the unit files of the groups a change reaches, and the
walkthrough's pages, then the browser files of the areas it reaches
(tests/e2e/areas.py): every unit file when it touches shared ground -- the package's
core, the app, the suite's own conftest, the dependencies -- a unit file itself when
it changes, none when it reaches no group. `apothecary test group NAME...` runs named
groups. The run before a merge is `apothecary test all` on the stack's head, the whole
suite.

    python tests/groups.py FILE...   # the unit files a change to FILE... reaches, or ALL

tests/test_groups.py holds that every unit file is in one group and that every pattern
names something this checkout tracks.
"""

from __future__ import annotations

import fnmatch
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = "tests"
ALL = "ALL"

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
            "apothecary/demo.py",
            "apothecary/routes/jobs.py",
            "apothecary/routes/machines.py",
            "apothecary/cli/firmware.py",
            "apothecary/state_folder.py",
            "parts/esp32_blink/*",
            "parts/footpedal/*",
            "parts/boards/*",
            "parts/ender3/*",
            "parts/anolex_4060_evo_ultra_2/*",
            "tests/firmware_helpers.py",
            "walkthrough/19-*",
        ),
        "tests": (
            "test_board_by_part.py",
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
            "test_machine_plans.py",
            "test_machine_words.py",
            "test_rust_installer.py",
            "test_state_folder.py",
            "test_stream_deck_part.py",
            "test_demo.py",
        ),
    },
    "making": {
        "sources": (
            "apothecary/slicer/*",
            "apothecary/cam/*",
            "apothecary/preview/*",
            "apothecary/cli/slicer.py",
            "parts/router_coupon/*",
            "parts/ender3/*",
            "tests/slicer_helpers.py",
            "walkthrough/20-*",
            "walkthrough/21-*",
        ),
        "tests": (
            "test_slicer.py",
            "test_slicer_api.py",
            "test_slicer_installer.py",
            "test_cam.py",
            "test_preview.py",
        ),
    },
    "parts": {
        "sources": (
            "apothecary/projects/*",
            "apothecary/meshes.py",
            "apothecary/spaces.py",
            "apothecary/airgap_metrics.py",
            "apothecary/datum_core_site.py",
            "apothecary/openscad_installer.py",
            "apothecary/routes/part_edits.py",
            "apothecary/routes/airgap.py",
            "apothecary/cli/parts.py",
            "apothecary/cli/airgap.py",
            "apothecary/cli/openscad.py",
            "apothecary/cli/spaces.py",
            "parts/*",
            "tests/scripted_openscad.py",
            "tests/rendered_parts.py",
            "tests/assignment_cases.json",
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
            "test_failed_renders.py",
            "test_following_a_variant.py",
            "test_geometry_from_elsewhere.py",
            "test_gridfinity.py",
            "test_lighter_and_faster.py",
            "test_openscad_installer.py",
            "test_openscad_messages.py",
            "test_param_controls.py",
            "test_parameter_coverage.py",
            "test_params_contract.py",
            "test_part_drafts.py",
            "test_part_json_parity.py",
            "test_part_loader.py",
            "test_part_variants.py",
            "test_parts_parameters.py",
            "test_parts_stl_generation.py",
            "test_parts_wrappers.py",
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
            "apothecary/site_names.py",
            "apothecary/cli/render.py",
            "apothecary/cli/kernels.py",
            "templates/*",
            "examples/scenes/*",
            "examples/scripts/*",
        ),
        "tests": (
            "test_catalog_geometry.py",
            "test_datum_assembly.py",
            "test_examples.py",
            "test_garage_workbench.py",
            "test_hierarchy.py",
            "test_jscad_renderer.py",
            "test_kernel_comparison.py",
            "test_models.py",
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
            "apothecary/gathering/*",
            "apothecary/finders/*",
            "apothecary/vocabulary/*",
            "apothecary/routes/pictures.py",
            "apothecary/routes/views.py",
            "apothecary/routes/cameras.py",
            "apothecary/routes/vision.py",
            "apothecary/cli/photo.py",
            "apothecary/cli/vision.py",
            "examples/pictures/*",
            "examples/llms_own/*",
            "tests/views_helpers.py",
        ),
        "tests": (
            "test_again.py",
            "test_finder_accuracy.py",
            "test_finder_geometry.py",
            "test_free_space.py",
            "test_gathering.py",
            "test_gathering_accuracy.py",
            "test_made_part.py",
            "test_made_piece_geometry.py",
            "test_marks.py",
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
            "test_vision_through_qmcp.py",
            "test_working_together.py",
        ),
    },
    "family": {
        "sources": (
            "apothecary/family/*",
            "apothecary/wiring/*",
            "apothecary/rig/*",
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
            "test_former_site_names.py",
            "test_frames_cost.py",
            "test_rig.py",
            "test_wiring.py",
        ),
    },
    "viewer": {
        "sources": (
            "apothecary/viewer.py",
            "apothecary/menu.py",
            "apothecary/systems.py",
            "apothecary/census.py",
            "apothecary/docs_site.py",
            "apothecary/lighting.py",
            "apothecary/console_feedback.py",
            "apothecary/theatre_site.py",
            "apothecary/routes/menu.py",
            "apothecary/routes/lighting.py",
            "apothecary/routes/readme.py",
            "apothecary/static/*",
            "apothecary/cli/census.py",
            "apothecary/cli/server.py",
            "templates/fractal_viewer.html.j2",
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
            "test_menu_routes.py",
            "test_readiness.py",
            "test_stays_local.py",
            "test_group_colours.py",
            "test_systems.py",
            "test_theatre_site.py",
            "test_viewer_assets.py",
        ),
    },
    "cli": {
        "sources": (
            "apothecary/cli/*",
            "apothecary/__main__.py",
            "apothecary/version.py",
            "apothecary/stamped.py",
            "apothecary/release.py",
            "apothecary/preflight.py",
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
}


def _matches(path: str, patterns) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def files(names) -> list[str]:
    """The unit files of the groups ``names``, in the order the map holds them."""
    unknown = sorted(set(names) - set(GROUPS))
    if unknown:
        raise KeyError(f"no group named {', '.join(unknown)}: {', '.join(GROUPS)}")
    return [f"{TESTS}/{name}" for group in names for name in GROUPS[group]["tests"]]


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
        groups = [group for group in GROUPS.values() if _matches(path, group["sources"])]
        if directory == TESTS and name.endswith(".py") and not groups:
            return ALL  # a helper any unit file may import
        for group in groups:
            found.update(group["tests"])
    held = [name for group in GROUPS.values() for name in group["tests"]]
    return [f"{TESTS}/{name}" for name in held if name in found] + sorted(
        f"{TESTS}/{name}" for name in found - set(held)
    )


def main(argv=None) -> int:
    changed = sys.argv[1:] if argv is None else argv
    found = reached(changed)
    print(found if found == ALL else " ".join(found))
    return 0


if __name__ == "__main__":
    sys.exit(main())
