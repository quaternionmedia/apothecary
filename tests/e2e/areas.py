"""Which browser tests a change reaches: the suite in areas, each named for what a
person does with the page, with the sources it stands on and the files that hold it.

`apothecary test changed` runs the walkthrough and the unit files of the groups a change
reaches (tests/groups.py), then the browser files of the areas it touches: every file
when it touches shared ground -- the page itself, the server's app, the conftests, the
dependencies -- a browser file itself when it changes, none when it reaches no area. A
helper, a module in tests/e2e/ or tests/ that is no test file, reaches the browser files
that import it, directly or through other helpers, with the areas whose sources name it;
every browser file when a conftest imports it, and none when no browser file does. A
data file of tests/ outside tests/e2e/ -- a table of cases, a conformance vector --
reaches the browser files that name it, as a helper reaches those that import it. The
whole suite (`apothecary test all`) runs once, on the head of a stack, before it is
pulled.

    python tests/e2e/areas.py FILE...   # the browser files a change to FILE... reaches, or ALL

Who imports a helper is read from the suite's import statements, by tests/groups.py's
`importers`. tests/test_areas.py holds that every browser file is in one area and that
every pattern names something this checkout tracks.
"""

from __future__ import annotations

import fnmatch
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
E2E = "tests/e2e"
ALL = "ALL"

_spec = importlib.util.spec_from_file_location("groups", ROOT / "tests/groups.py")
groups = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(groups)

# The conftests every browser file runs under.
CONFTESTS = ("conftest.py", "tests/conftest.py", "tests/e2e/conftest.py")

# Ground every area stands on: a change here runs every browser file.
SHARED = (
    "conftest.py",
    "templates/fractal_viewer.html.j2",
    "apothecary/api.py",
    "apothecary/site_store.py",
    "apothecary/sites.py",
    "apothecary/picture_root.py",
    "apothecary/stays_local.py",
    "apothecary/viewer.py",
    "apothecary/static/vendor/*",
    "apothecary/models/*",
    "apothecary/hierarchy.py",
    "apothecary/objects.py",
    "apothecary/scene.py",
    "apothecary/transforms.py",
    "tests/conftest.py",
    "tests/e2e/conftest.py",
    "pyproject.toml",
    "uv.lock",
)

# Each area: the sources a change to which reaches it, and the browser files that hold it.
AREAS = {
    "windows": {
        "sources": (
            "apothecary/static/panels.js",
            "apothecary/static/systems.js",
            "apothecary/static/ring.js",
            "apothecary/static/keys.js",
            "apothecary/static/anchors.js",
            "apothecary/static/twice.js",
            "apothecary/static/widgets/settings.js",
            "apothecary/static/widgets/layers.js",
            "apothecary/static/pick_scope.js",
            "apothecary/systems.py",
            "apothecary/journeys.py",
            "apothecary/menu.py",
            "apothecary/routes/menu.py",
            "apothecary/docs_site.py",
            "apothecary/universe.py",
        ),
        "tests": (
            "test_window_manager.py",
            "test_windows_over_a_reload.py",
            "test_focused_systems.py",
            "test_ring.py",
            "test_site_panel.py",
            "test_nothing_covers_a_control.py",
            "test_less_on_screen.py",
            "test_the_pointer_and_the_keys.py",
            "test_viewer.py",
            "test_viewer_regressions.py",
            "test_world_resize.py",
            "test_render_on_demand.py",
            "test_the_page_keeps_up.py",
            "test_docs_fractal_viewer.py",
            "test_the_universe.py",
            "test_layers.py",
            "test_view_banner.py",
            "test_journeys.py",
        ),
    },
    "pictures": {
        "sources": (
            "apothecary/vision/*",
            "apothecary/gathering/*",
            "apothecary/routes/pictures.py",
            "apothecary/routes/views.py",
            "apothecary/routes/cameras.py",
            "apothecary/static/pictures.js",
            "apothecary/static/picture_marks.js",
            "apothecary/static/widgets/picture_list.js",
            "apothecary/static/widgets/pinned.js",
            "examples/pictures/*",
            "walkthrough/01-*",
            "walkthrough/screenshots/01-*",
            "walkthrough/03-*",
            "walkthrough/screenshots/03-*",
        ),
        "tests": (
            "test_camera.py",
            "test_first_camera.py",
            "test_the_loop.py",
            "test_picture_in_the_world.py",
            "test_pictures_panel.py",
            "test_gathering_map_in_a_browser.py",
            "test_edit_a_made_piece.py",
            "test_picture_to_print.py",
            "test_paths_people_take.py",
            "test_docs_photo_walkthrough.py",
            "test_steps_a_picture_to_a_print.py",
        ),
    },
    "machine": {
        "sources": (
            "apothecary/firmware/*",
            "apothecary/slicer/*",
            "apothecary/cam/*",
            "apothecary/preview/*",
            "parts/router_coupon/*",
            "parts/router_emoji/*",
            "apothecary/jobs.py",
            "apothecary/routes/jobs.py",
            "apothecary/static/boards.js",
            "apothecary/static/can.js",
            "apothecary/static/board_text.js",
            "apothecary/static/machine_words.js",
            "apothecary/static/tokens.css",
            "apothecary/static/machine_marks.js",
            "apothecary/static/frames.js",
            "apothecary/static/widgets/machine.js",
            "apothecary/static/widgets/sketches.js",
            "apothecary/static/widgets/tasks.js",
            "apothecary/static/widgets/toolchain.js",
            "parts/esp32_blink/*",
            "parts/footpedal/*",
            "apothecary/static/widgets/deck.*",
            "apothecary/static/deck_knobs.js",
            "walkthrough/26-*",
            "walkthrough/screenshots/26-*",
            "walkthrough/27-*",
            "walkthrough/screenshots/27-*",
            "walkthrough/02-*",
            "walkthrough/screenshots/02-*",
            "walkthrough/05-*",
            "walkthrough/screenshots/05-*",
            "walkthrough/20-*",
            "walkthrough/21-*",
            "walkthrough/24-*",
            "walkthrough/screenshots/24-*",
        ),
        "tests": (
            "test_one_machine.py",
            "test_printer_ui.py",
            "test_machine_stops.py",
            "test_buttons_say_why.py",
            "test_router_ui.py",
            "test_router_needs.py",
            "test_router_table_map.py",
            "test_toolpath_preview.py",
            "test_machine_plans.py",
            "test_make.py",
            "test_bench.py",
            "test_deck.py",
            "test_deck_jog.py",
            "test_the_firmware_loop.py",
            "test_the_made_thing.py",
            "test_onboarding.py",
            "test_docs_printer_monitor.py",
            "test_docs_bench_walkthrough.py",
            "test_steps_firmware.py",
            "test_steps_one_machine.py",
        ),
    },
    "parts": {
        "sources": (
            "apothecary/projects/*",
            "apothecary/airgap_metrics.py",
            "apothecary/routes/part_edits.py",
            "apothecary/routes/airgap.py",
            "apothecary/static/widgets/scad_editor.js",
            "apothecary/static/widgets/part_controls.js",
            "apothecary/static/widgets/assignments.js",
            "apothecary/static/widgets/airgap.js",
            "parts/*",
            "walkthrough/04-*",
            "walkthrough/screenshots/04-*",
            "walkthrough/06-*",
            "walkthrough/screenshots/06-*",
        ),
        "tests": (
            "test_part_loop.py",
            "test_part_iteration.py",
            "test_part_iteration_answers.py",
            "test_scad_loop.py",
            "test_text_tied.py",
            "test_assignments_in_the_page.py",
            "test_airgap.py",
        ),
    },
    "lighting": {
        "sources": (
            "apothecary/lighting.py",
            "apothecary/console_feedback.py",
            "apothecary/theatre_site.py",
            "apothecary/routes/lighting.py",
            "apothecary/static/lighting.js",
            "examples/theatre-rig/*",
        ),
        "tests": ("test_lighting_overlay.py",),
    },
    "simulated": {
        "sources": ("apothecary/simulated.py", "apothecary/cli/server.py"),
        "tests": ("test_simulated_machines.py",),
    },
    "carlos": {
        "sources": (
            "apothecary/rig/*",
            "apothecary/wiring/*",
            "apothecary/routes/wiring.py",
            "apothecary/cli/rig.py",
            "tests/e2e/carlos_app.py",
        ),
        "tests": ("test_carlos_concert.py", "test_carlos_bench.py"),
    },
    "working space": {
        "sources": (
            "apothecary/evidence/*",
            "apothecary/routes/evidence.py",
            "apothecary/cli/evidence.py",
            "apothecary/static/widgets/working_space.*",
        ),
        "tests": ("test_working_space.py",),
    },
    "procedure": {
        "sources": (
            "apothecary/family/*",
            "apothecary/routes/procedures.py",
            "apothecary/static/widgets/procedure.*",
            "apothecary/static/widgets/family.js",
            "walkthrough/25-*",
            "walkthrough/screenshots/25-*",
        ),
        "tests": ("test_procedure_doors.py", "test_procedure_window.py"),
    },
    "marks": {
        "sources": (
            "apothecary/vision/marks.py",
            "apothecary/vision/notes.py",
            "apothecary/vision/outline.py",
            "apothecary/routes/marks.py",
            "apothecary/routes/whiteboards.py",
            "apothecary/vision/history.py",
            "apothecary/vision/whiteboard.py",
            "apothecary/static/widgets/marks.*",
            "walkthrough/screenshots/30-*",
        ),
        "tests": ("test_marks_window.py", "test_whiteboard_round_twice.py"),
    },
    "models": {
        "sources": (
            "apothecary/finders/*",
            "apothecary/routes/vision.py",
            "apothecary/cli/vision.py",
            "apothecary/static/widgets/models.*",
        ),
        "tests": ("test_models_window.py",),
    },
    "tour": {
        "sources": (
            "apothecary/tour.py",
            "apothecary/routes/tour.py",
            "apothecary/static/widgets/tour_popover.*",
            "apothecary/journeys.py",
            "apothecary/simulated.py",
        ),
        "tests": ("test_tour.py", "test_tour_from_anywhere.py", "test_the_chain.py"),
    },
}


def _matches(path: str, patterns) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _naming(name: str) -> set:
    """The browser files whose text names a file: a data file of tests/, read by path."""
    return {
        test.name
        for test in (ROOT / E2E).glob("test_*.py")
        if name in test.read_text(encoding="utf-8")
    }


def reached(changed) -> list | str:
    """The browser files a change reaches, in the order the suite holds them, or ALL."""
    files = set()
    for path in changed:
        if _matches(path, SHARED):
            return ALL
        name = path.rpartition("/")[2]
        if path.startswith(f"{E2E}/") and name.startswith("test_") and name.endswith(".py"):
            if (ROOT / path).exists():  # a file the change deletes runs nothing
                files.add(name)
            continue
        if groups.is_helper(path):
            importing = groups.importers(path, ROOT)
            if importing & set(CONFTESTS):
                return ALL
            files.update(groups.tests_among(importing, E2E))
        elif (
            path.startswith("tests/")
            and not path.startswith(f"{E2E}/")
            and not name.endswith(".py")
        ):
            files.update(_naming(name))
        for area in AREAS.values():
            if _matches(path, area["sources"]):
                files.update(area["tests"])
    held = [name for area in AREAS.values() for name in area["tests"]]
    return [f"{E2E}/{name}" for name in held if name in files] + sorted(
        f"{E2E}/{name}" for name in files - set(held)
    )


def main(argv=None) -> int:
    changed = sys.argv[1:] if argv is None else argv
    files = reached(changed)
    print(files if files == ALL else " ".join(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
