"""Every group of windows the page registers has a colour of its own in the palette
(apothecary/static/tokens.css), and what shows a window says whose it is."""

from __future__ import annotations

import re

from apothecary import systems
from apothecary.projects.parts.skeleton import ROOT

TOKENS = (ROOT / "apothecary" / "static" / "tokens.css").read_text(encoding="utf-8")
TEMPLATE = (ROOT / "templates" / "fractal_viewer.html.j2").read_text(encoding="utf-8")
PANELS = (ROOT / "apothecary" / "static" / "panels.js").read_text(encoding="utf-8")


def _registered() -> set[str]:
    """Each group a window is registered under: the template's sections, the page's
    own registrations, and every focused system's."""
    groups = set(re.findall(r'data-group="([^"]+)"', TEMPLATE))
    groups |= set(re.findall(r"\bgroup: '([^']+)'", TEMPLATE))
    groups |= {system.group for system in systems.SYSTEMS}
    return groups


def _coloured() -> dict[str, str]:
    """Group -> the palette variable its rule sets ``--group`` to."""
    return dict(
        re.findall(r'\[data-group="([^"]+)"\] \{ --group: var\((--group-[a-z]+)\); \}', TOKENS)
    )


def test_the_page_registers_the_groups_this_reads():
    """The reading itself: it finds the template's, the page's and a system's."""
    assert {"Site", "Selected", "Pictures", "Tools", "Machine", "Family"} <= _registered()


def test_every_group_has_a_colour():
    assert _registered() - set(_coloured()) == set()


def test_no_colour_is_left_for_a_group_that_is_gone():
    assert set(_coloured()) - _registered() == set()


def test_each_group_has_a_colour_of_its_own_and_none_means_a_state():
    values = dict(re.findall(r"(--[a-z0-9-]+): (#[0-9a-f]{6})", TOKENS))
    worn = {group: values[variable] for group, variable in _coloured().items()}
    assert len(set(worn.values())) == len(worn), worn
    states = {values[name] for name in ("--ok", "--warn", "--bad", "--tx", "--hotend", "--bed")}
    assert not states & set(worn.values())


def test_a_tab_a_window_and_each_list_wear_their_group():
    """Four places set data-group from a window's record, and the heading of each
    list from its group's name."""
    assert PANELS.count("wearGroup(tab.element, r.group)") == 1
    assert PANELS.count("wearGroup(container.element, r.group)") == 1
    assert PANELS.count("wearGroup(b, r.group)") == 1
    assert PANELS.count("wearGroup(head, group)") == 2
    for rule in (
        ".lm_header .lm_tab[data-group]",
        ".spawn-group[data-group]",
        ".panel-window[data-group]",
    ):
        assert rule in TEMPLATE, rule


def _panel_groups_on_the_page() -> dict[str, str]:
    """Panel id -> group, as the page registers each: each focused system's main
    window, then its markup's sections and its script's registrations, which a
    window the markup holds keeps."""
    found = {system.main: system.group for system in systems.SYSTEMS}
    found |= dict(re.findall(r'data-panel="([a-z-]+)"[^>]*?data-group="([^"]+)"', TEMPLATE))
    found |= dict(
        re.findall(r"register\('([a-z-]+)',\s*\{[^}]*?group: '([^']+)'", TEMPLATE, flags=re.S)
    )
    return found


def test_a_panels_cell_wears_the_group_its_window_is_registered_under():
    from apothecary.menu import PANEL_GROUPS, PANELS

    on_the_page = _panel_groups_on_the_page()
    assert {"site", "selected", "pictures", "bench", "procedure"} <= set(on_the_page)
    for panel, _ in PANELS:
        assert panel in PANEL_GROUPS, f"{panel} has a cell and no group"
        if panel in on_the_page:
            assert PANEL_GROUPS[panel] == on_the_page[panel], panel


def test_every_ring_cell_that_wears_a_group_wears_one_with_a_colour():
    from apothecary.menu import Option, _panels

    def groups(options):
        for option in options or []:
            if option.group:
                yield option.group
            yield from groups(option.children)

    worn = set(groups([_panels()]))
    assert {"Site", "Selected", "Pictures", "Machine", "Tools", "Family", "Airgap", "Part"} <= worn
    assert worn <= set(_coloured())
    assert Option(id="x", label="X", action="x").group is None


def test_the_ring_and_the_worlds_badges_draw_the_group():
    ring = (ROOT / "apothecary" / "static" / "ring.js").read_text(encoding="utf-8")
    anchors = (ROOT / "apothecary" / "static" / "anchors.js").read_text(encoding="utf-8")
    assert 'class="rim" data-group="${esc(option.group)}"' in ring
    assert ".apothecary-ring .wedge[data-group] { fill: color-mix(" in ring
    assert ".apothecary-ring .wedge[data-group].hot { fill: color-mix(" in ring
    assert "if (group) el.dataset.group = group;" in anchors
    assert ".world-badge[data-group]" in TEMPLATE
    marks = (ROOT / "apothecary" / "static" / "machine_marks.js").read_text(encoding="utf-8")
    pictures = (ROOT / "apothecary" / "static" / "picture_marks.js").read_text(encoding="utf-8")
    assert 'group: "Machine"' in marks and pictures.count('group: "Pictures"') == 2
