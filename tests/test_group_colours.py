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
