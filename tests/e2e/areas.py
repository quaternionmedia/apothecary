"""Which browser tests a change reaches: the suite in areas, each named for what a
person does with the page, with the sources it stands on and the files that hold it.

`apothecary test changed` runs the unit tests and the walkthrough, then the browser
files of the areas a change touches: every file when it touches shared ground -- the
page itself, the server's app, this suite's own helpers and conftest, the
dependencies -- a browser file itself when it changes, none when it reaches no area.
The whole suite (`apothecary test all`) runs before a pull request is ready.

    python tests/e2e/areas.py FILE...   # the browser files a change to FILE... reaches, or ALL

tests/test_areas.py holds that every browser file is in one area and that every
pattern names something this checkout tracks.
"""

from __future__ import annotations

import fnmatch
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
E2E = "tests/e2e"
ALL = "ALL"

# Ground every area stands on: a change here runs every browser file.
SHARED = (
    "templates/fractal_viewer.html.j2",
    "apothecary/api.py",
    "apothecary/site_store.py",
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
            "apothecary/systems.py",
            "apothecary/menu.py",
            "apothecary/routes/menu.py",
            "apothecary/docs_site.py",
        ),
        "tests": (
            "test_window_manager.py",
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
            "test_docs_fractal_viewer.py",
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
            "apothecary/jobs.py",
            "apothecary/routes/jobs.py",
            "apothecary/static/boards.js",
            "apothecary/static/board_text.js",
            "apothecary/static/machine_marks.js",
            "apothecary/static/widgets/machine.js",
            "apothecary/static/widgets/sketches.js",
            "apothecary/static/widgets/tasks.js",
            "apothecary/static/widgets/toolchain.js",
            "parts/esp32_blink/*",
            "walkthrough/02-*",
            "walkthrough/screenshots/02-*",
            "walkthrough/05-*",
            "walkthrough/screenshots/05-*",
        ),
        "tests": (
            "test_one_machine.py",
            "test_printer_ui.py",
            "test_bench.py",
            "test_the_firmware_loop.py",
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
    "demo": {
        "sources": ("apothecary/demo.py", "apothecary/cli/server.py"),
        "tests": ("test_the_demo.py",),
    },
}


def _matches(path: str, patterns) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def reached(changed) -> list | str:
    """The browser files a change reaches, in the order the suite holds them, or ALL."""
    files = set()
    for path in changed:
        if _matches(path, SHARED):
            return ALL
        if path.startswith(f"{E2E}/") and path.endswith(".py"):
            name = path.rsplit("/", 1)[1]
            if not name.startswith("test_"):
                return ALL  # a helper every browser file may import
            if (ROOT / path).exists():  # a file the change deletes runs nothing
                files.add(name)
            continue
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
