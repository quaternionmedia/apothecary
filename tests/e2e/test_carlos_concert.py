"""A concert followed into carlos, frame by frame, and what carlos's rack draws of it.

Carlos runs from a checkout of its own (``CARLOS_CHECKOUT``), as
``carlos_app.py`` starts it. The rig is carlos's Subharmonicon example, asked
of that carlos; ``rig.simulated`` draws its concert, and each frame is read and
held in carlos as ``apothecary rig follow`` holds it. An open rack tab is then held to the frame's truth:

- every knob and fader carlos draws stands where the frame was drawn, within
  what the reader is measured to;
- the rack is turned in place from frame to frame, its devices the same elements
  (carlos's ``feat/hold-the-rig``), not drawn again;
- the stray plug's song draws the DFAM's state as a warning, and the pulled
  lead's song draws that lead as a fault.

Without ``CARLOS_CHECKOUT`` it skips, saying so: carlos is another repository.
"""

from __future__ import annotations

import json

import pytest

# The fixtures these tests stand on: carlos itself, and a page of its.
from carlos_app import (  # noqa: F401
    _chromium_here,
    _verify_url,
    browser_context_args,
    carlos_server,  # the fixture `carlos`
)
from playwright.sync_api import Page

from apothecary.rig import concert, reading, simulated

# A browser test, deselected where nothing can serve it.
pytestmark = pytest.mark.e2e

EXAMPLE = "moog.subharmonicon.complex"
# The reader on drawn pictures is measured at under 2% of a range at worst
# (`apothecary rig check`); carlos is held to a little more.
WITHIN = 0.03


def _drawn_values(page: Page, modules) -> dict:
    return page.evaluate(
        """(ids) => Object.fromEntries(ids.map(id => {
            const module = system.modules.get(id);
            return [id, Object.fromEntries([...module.parameters].map(([n, p]) => [n, p.value]))];
        }))""",
        list(modules),
    )


def test_a_concert_followed_into_carlos_is_drawn_frame_by_frame(carlos, page: Page, tmp_path):
    rig_doc, devices = reading.rig_from_carlos(carlos, EXAMPLE)
    setup = simulated.scene(rig_doc, devices)
    folder = tmp_path / "concert"
    simulated.write_concert(setup, folder, songs=4, frames=3, every=5.0, seed=7)
    truth = [json.loads(line) for line in (folder / "truth.jsonl").read_text().splitlines()]
    ranges = {
        (module["id"], c.name): (c.minimum, c.maximum)
        for module, panel in simulated._laid(setup)
        for c in panel.controls
    }

    page.goto(f"{carlos}/rack")
    page.wait_for_function("() => typeof hub !== 'undefined' && hub.revision !== null")
    following = concert.Concert(folder, url=carlos, say=lambda line: None)
    (folder / concert.RECORD).write_text("", encoding="utf-8")
    elements = None
    seen = {"held": 0, "stray": 0, "pulled": 0}

    for frame, shown in zip(concert.frames(folder), truth, strict=True):
        following.take(frame)
        held = json.loads((folder / concert.RECORD).read_text().splitlines()[-1])["held"]
        if held:
            page.wait_for_function(
                "(name) => (document.querySelector('#status')?.textContent || '').includes(name)",
                arg=frame.name,
            )
        drawn = _drawn_values(page, shown["values"])
        for module, values in shown["values"].items():
            for name, value in values.items():
                low, high = ranges[(module, name)]
                assert abs(drawn[module][name] - value) <= WITHIN * (high - low), (
                    f"{frame.name}: {module}'s {name} drawn at {drawn[module][name]}, drawn in the frame at {value}"
                )

        # The rack is the same elements from the first frame on: turned in place.
        if elements is None:
            elements = page.evaluate(
                "() => { document.querySelectorAll('.module').forEach(m => { m.__fromTheFirstFrame = true; });"
                " return document.querySelectorAll('.module').length; }"
            )
        assert page.evaluate(
            "() => [...document.querySelectorAll('.module')].every(m => m.__fromTheFirstFrame)"
        ), f"{frame.name}: the rack was drawn again"
        assert page.locator(".module").count() == elements

        # What the song did to the plugs is drawn as each device's and lead's state.
        dfam = page.locator('.module[data-module-id="dfam"]')
        stray = [
            module
            for module, sockets in shown["plugged"].items()
            for name, on in sockets.items()
            if on and not _named(rig_doc, module, name)
        ]
        for module in stray:
            assert (
                page.locator(f'.module[data-module-id="{module}"]').get_attribute("data-held")
                == "warn"
            )
        if not stray:
            assert dfam.get_attribute("data-held") == "ok", frame.name
        pulled = any(
            not shown["plugged"][end["module"]][end["jack"]]
            for lead in rig_doc["connections"]
            for end in (lead["source"], lead["target"])
            if end["jack"] in shown["plugged"].get(end["module"], {})
        )
        faults = page.locator("path.cable.is-held-fault").count()
        assert (faults > 0) == pulled, (
            f"{frame.name}: pulled {pulled}, {faults} cables drawn as a fault"
        )
        seen["held"] += bool(held)
        seen["stray"] += bool(stray)
        seen["pulled"] += pulled

    # The concert went through what it is drawn to: frames held, a song with a
    # stray plug in, and one with a lead's plug pulled.
    assert seen["held"] > 1 and seen["stray"] and seen["pulled"], seen


def _named(rig_doc, module: str, jack: str) -> bool:
    return any(
        end["module"] == module and end["jack"] == jack
        for lead in rig_doc["connections"]
        for end in (lead["source"], lead["target"])
    )
