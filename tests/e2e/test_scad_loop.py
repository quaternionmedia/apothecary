"""Loop 2, editing a part's SCAD, gone round in the page: the part's editor opened from
its ring (Part › Edit), its SCAD edited in Selected's editor, an assertion that fails
checked once typing stops and marked on its line with nothing rendered, then a real
change rendered soon after its check passes and drawn as an applied variant, taller than
its envelope and said so; saved from the ring (Part › Save) as a variant in git and
listed in both places, with what it changes; the editor floated over the world
(Part › View › Float) and made fullscreen (its own button, then Esc). Round two in the
floated editor: a name typed, another change, saved with Ctrl+S; then the first variant
drawn from the ring (Part › Variants › its name › Draw), and the editor docked back.
Round three: the name box letting go of the variant once the text moves on and taking it
back on Ctrl+Z, Save asking before it replaces a variant, F5 checking and drawing at
once a change that reaches under the floor; then a draft that does not read kept over a
reload and restored, and the editor's undo kept while another part is edited. It writes
walkthrough/06-editing-a-parts-scad.md and its pictures as it goes.

The server is this module's own, with this machine's OpenSCAD and a variant cache
of its own; it saves variants into a clone of the checkout (tests/e2e/conftest.py),
never this checkout's refs, which the run checks are as they were. Opening the part
draws its own STL, which a fresh clone does not have, so ``parts/calibration_cube/``
is put back as it was found. Pictures of the editor docked, floated and fullscreen
at both widths the page is laid out for, each checked to overlap nothing it must
not, are written under pytest's temp folder (``scad-loop-shots``).
"""

from __future__ import annotations

import re
import subprocess

import pytest
from doc_capture import all_words
from playwright.sync_api import Page, expect
from viewer_ready import (
    MARKED_LINE_FIRST,
    STAGE_BAR_AT_THE_TOP,
    UNDER_THE_STAGE_BAR,
    by_hand,
    settled,
    site_folded,
)

from apothecary.projects.parts.calibration_cube import DEFAULT as CUBE
from apothecary.projects.parts.skeleton import ROOT
from apothecary.projects.parts.stl_renderer import params_sidecar_path

PART = "calibration_cube"
RING_MS = 15000
WIDTHS = ((1280, 800), (1024, 768))
# Where this run's server keeps its variants: a folder of the run's own, which the
# server's words name and a page written from them must not -- another run, CI's among
# them, names another (tests/e2e/conftest.py's start_server).
RUN_CLONE = re.compile(r"/[^\s`'\"]*?/server\d*/variants\.git")
# What differs on every run whatever the page does, blanked in the pictures: when each
# variant was saved, a grey of one width whatever the time, and the run's own folder
# where the status line names it.
BLANK = (*all_words(".saved-when"), ("#status", RUN_CLONE.pattern))

# How long after a check that passes the page renders a SCAD edit, read from the page.
RENDER_AFTER_CHECK_MS = int(
    re.search(
        r"const SCAD_RENDER_AFTER_CHECK_MS = (\d+);",
        (ROOT / "templates" / "fractal_viewer.html.j2").read_text(encoding="utf-8"),
    ).group(1)
)

REFUSED = 'assert(size < 5, "too big to keep");'
SMALL_TOP = "translate([0, 0, size]) cube(size / 2);"
BIG_TOP = "translate([0, 0, size]) cube(size);"
UNDER = "translate([0, 0, -12]) cube(4);"

WEDGES = (
    "() => Object.fromEntries([...document.querySelectorAll('#ring-overlay .wedge')]"
    ".filter((w) => !w.classList.contains('empty'))"
    ".map((w) => [w.dataset.cell, w.getAttribute('aria-label')]))"
)

# The boxes a floated or fullscreen editor is checked against, in the page's pixels.
LAYOUT = """() => {
    const box = (el) => {
        if (!el || el.hidden) return null;
        const r = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        if (!r.width || !r.height || style.visibility === 'hidden' || parseFloat(style.opacity) < 0.05) return null;
        return { l: r.left, t: r.top, r: r.right, b: r.bottom };
    };
    const v = window.fractalViewer;
    return {
        floated: box(document.querySelector(".panel[data-panel='scad-editor']")),
        editor: box(document.querySelector('.scad-editor')),
        buttons: ['#scad-save', '#scad-float', '#scad-fullscreen', '#scad-name'].map((s) => box(document.querySelector(s))),
        rail: box(document.querySelector('.panel-rail')),
        keep: {
            header: box(document.querySelector('.toolbar')),
            hint: box(v.hintEl),
            ladder: box(v.minimapEl),
            tabs: box(document.querySelector('.panel-tabs')),
            rail: box(document.querySelector('.panel-rail')),
            status: box(document.getElementById('status')),
        },
        world: box(v.canvas),
        viewport: { r: innerWidth, b: innerHeight },
    };
}"""


def _overlaps(a, b) -> bool:
    return a["l"] < b["r"] and b["l"] < a["r"] and a["t"] < b["b"] and b["t"] < a["b"]


def _inside(a, b, slack: float = 0.5) -> bool:
    return (
        a["l"] >= b["l"] - slack
        and a["t"] >= b["t"] - slack
        and a["r"] <= b["r"] + slack
        and a["b"] <= b["b"] + slack
    )


@pytest.fixture(scope="module")
def scad_url(start_server, every_stl_built, tmp_path_factory):
    """A server of this module's own, rendering with the OpenSCAD every server runs."""
    real = every_stl_built()["path"]
    if not real:
        pytest.skip("OpenSCAD not installed")
    folder = tmp_path_factory.mktemp("scad-loop")
    return start_server(
        {
            "APOTHECARY_OPENSCAD": real,
            "APOTHECARY_CACHE_DIR": str(folder / "cache"),
        }
    )


@pytest.fixture(scope="module")
def shots(tmp_path_factory):
    folder = tmp_path_factory.getbasetemp() / "scad-loop-shots"
    folder.mkdir(exist_ok=True)
    return folder


@pytest.fixture
def cube_as_it_was():
    """Opening the part draws its own STL, built if a fresh clone lacks it; put back."""
    stl = CUBE.get_stl_output_path()
    files = (stl, params_sidecar_path(stl))
    kept = {path: path.read_bytes() for path in files if path.exists()}
    yield
    for path in files:
        if path in kept:
            path.write_bytes(kept[path])
        else:
            path.unlink(missing_ok=True)


def _variant_refs_here() -> str:
    return subprocess.run(
        ["git", "for-each-ref", "--format=%(refname) %(objectname)", "refs/apothecary/"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout


# --- what a person does ---------------------------------------------------------


def _open(page: Page, url: str) -> None:
    page.goto(url)
    expect(page.locator("#status")).to_contain_text("Loaded", timeout=20000)
    page.evaluate("() => localStorage.removeItem('apothecary.panels')")
    settled(page)
    page.wait_for_function(
        f"() => {{ const m = window.fractalViewer.meshByName['{PART}'];"
        " return m && !m.userData.isPlaceholder; }",
        timeout=60000,
    )
    settled(page)


def _press(page: Page, *labels: str) -> None:
    for label in labels:
        page.wait_for_function(
            f"() => [...document.querySelectorAll('#ring-overlay .wedge')]"
            f".some((w) => w.getAttribute('aria-label') === {label!r})",
            timeout=RING_MS,
        )
        cell = next(c for c, got in page.evaluate(WEDGES).items() if got == label)
        page.keyboard.press(cell)


def _ring(page: Page, *labels: str) -> None:
    """The part's ring, from its row in Site, and the cells ``labels`` name."""
    page.locator(f"#contents-list .contents-item[data-path='{PART}']").click(
        button="right", modifiers=["Control"]
    )
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=RING_MS)
    _press(page, *labels)


def _said_on_the_page(page: Page) -> str:
    """The status line, as the walkthrough shows it: the run's own folder named as such."""
    return RUN_CLONE.sub("<the test server's variants repository>", _status(page).inner_text())


def _status(page: Page):
    return page.locator("#status")


def _said(page: Page):
    return page.locator(".scad-said")


def _code(page: Page):
    return page.locator(".scad-editor .cm-content")


def _into_code(page: Page) -> None:
    """Into the editor, its text taking the keys that follow, the view of it left as it
    is: a click lands where the code happens to be scrolled -- its middle below what
    Selected shows of it, a line's start under its gutter or out past the rail's left
    edge, a line's middle past its right -- and scrolls it, run by run otherwise."""
    page.locator(".scad-editor .cm-content").focus()


def _text(page: Page) -> str:
    return page.evaluate("() => window.fractalViewer.scadEditor.text()")


def _height(page: Page) -> float:
    """What the part drawn measures, up: the editor's measured bounds."""
    text = page.locator("#part-envelope .measured").inner_text()
    found = re.search(r"measured ([\d.]+) × ([\d.]+) × ([\d.]+) mm", text)
    assert found, text
    return float(found.group(3))


def _replace_last_line(page: Page, text: str) -> None:
    """The cursor to the SCAD's last line, that line selected, and ``text`` put over it
    in one go, as a paste does: however loaded the machine, one pause in typing."""
    _into_code(page)
    page.keyboard.press("Control+End")
    page.keyboard.press("Shift+Home")
    page.keyboard.insert_text(text)


def _counting(page: Page):
    """Every check and render the page asks for from now, by route."""
    asked = {"check": 0, "render": 0}

    def count(request):
        if "/draft/check" in request.url:
            asked["check"] += 1
        elif "/draft/render" in request.url:
            asked["render"] += 1

    page.on("request", count)
    return asked, lambda: page.remove_listener("request", count)


def _rendered(page: Page, height: float) -> None:
    said = f"{PART} regenerated from its edited SCAD: an applied variant, not saved"
    expect(_status(page)).to_contain_text(said, timeout=60000)
    settled(page)
    assert _height(page) == pytest.approx(height, abs=0.05)
    expect(page.locator(".part-editor")).to_have_class(re.compile(r"\bdrawn-from-variant\b"))


def _settled_render(page: Page) -> None:
    """Whatever check and render the last edit brought has answered."""
    page.wait_for_function(
        "() => { const s = window.fractalViewer.scadStages['part:calibration_cube'];"
        " return !s || s.text === s.drawnText || (s.check && !s.check.valid); }",
        timeout=60000,
    )
    expect(_status(page)).not_to_contain_text("Applying", timeout=60000)
    settled(page)


def _saved(page: Page, name: str) -> None:
    expect(_status(page)).to_contain_text(f"{PART} saved as the variant {name}", timeout=20000)
    expect(page.locator(f"#part-saved .saved-variant[data-variant='{name}']")).to_be_visible()
    expect(
        page.locator(f".scad-saved .saved-row[data-variant='{name}'] .not-in-head")
    ).to_be_attached()


def _laid_out(page: Page, width: int, shots, how: str) -> None:
    """At ``width``, the editor ``how`` it stands -- docked, floated, fullscreen --
    overlaps nothing it must not, its buttons in view; and a picture of it."""
    layout = page.evaluate(LAYOUT)
    view = {"l": 0, "t": 0, **layout["viewport"]}
    for button in layout["buttons"]:
        assert button and _inside(button, view), (how, width, layout["buttons"])
    if how == "docked":
        for button in layout["buttons"]:
            assert _inside(button, layout["rail"]), (how, width, button, layout["rail"])
    elif how == "floated":
        floated = layout["floated"]
        assert floated and _inside(floated, layout["world"]), (width, floated, layout["world"])
        for name, box in layout["keep"].items():
            if box is not None and name != "status":
                assert not _overlaps(floated, box), (width, name, floated, box)
        for button in layout["buttons"]:
            assert _inside(button, floated), (width, button, floated)
    else:
        assert _inside(view, layout["editor"], slack=1), (width, layout["editor"])
    page.screenshot(path=str(shots / f"{how}-{width}.png"))


def _at_both_widths(page: Page, shots, how: str) -> None:
    for width, height in WIDTHS:
        page.set_viewport_size({"width": width, "height": height})
        settled(page)
        if how == "floated":
            # Floated afresh at this width, as a person would after resizing: docked
            # first when it floats already.
            floated = page.locator(".panel[data-panel='scad-editor']")
            if floated.count():
                _ring(page, "Part", "View", "Float")
                expect(floated).to_have_count(0)
            _ring(page, "Part", "View", "Float")
            expect(page.locator(".panel[data-panel='scad-editor'].free")).to_be_visible()
        elif how == "docked":
            page.locator(".scad-editor .scad-bar").scroll_into_view_if_needed()
        page.evaluate("() => window.fractalViewer.scadEditor.measure()")
        settled(page)
        _laid_out(page, width, shots, how)
    page.set_viewport_size({"width": WIDTHS[0][0], "height": WIDTHS[0][1]})
    settled(page)


# --- the loop ---------------------------------------------------------------------


@pytest.mark.e2e
def test_editing_a_parts_scad_twice_round(
    page: Page, scad_url: str, cube_as_it_was, shots, walkthrough
):
    """The loop, twice round, and walkthrough page 16 written from it. Marked e2e and
    not walkthrough: a loop's page is written by the browser suite only."""
    story = walkthrough(
        ordinal="06",
        slug="editing-a-parts-scad",
        title="Editing a part's SCAD",
        browser_suite_only=True,
        intro=(
            "A part's SCAD edited in the page: the editor where its source stood in "
            "Selected, a failing line checked once typing stops and marked where it is, a "
            "change rendered soon after its check passes and drawn as an applied variant, "
            "kept as a variant in git and listed with what it changes, the editor floated "
            "and made fullscreen; then round again, and the first variant drawn once more; "
            "then the name a save keeps, OpenSCAD's own keys, a draft kept over a reload "
            "and the editor's undo kept while another part is edited. Every step is the "
            "page's own: a cell of a ring, a key or a button, and every step's words name "
            "the next one."
        ),
        runtime=(
            "It drives a real browser against a real server of its own, with the "
            "OpenSCAD every test server runs and a temporary cache of variants. A variant is saved into "
            "a clone of the checkout the server was given, never the checkout's own refs, "
            "which the run checks are as it found them. It needs no network, and refuses one."
        ),
        does_not_show=[
            "**Making a variant the part's source.** That is a merge you do "
            "(`git merge refs/apothecary/variants/<part>/<name>`); no control in the page "
            "writes the checkout.",
            "**A part without a model.** Its controls come from what its SCAD declares, "
            "where the OpenSCAD in use lists them; calibration_cube has a model.",
            "**When a variant was saved, and where the server keeps it.** Both differ on "
            "every run: the lists' times are blanked in the pictures, and the server's clone "
            "of the checkout is named as the test server's variants repository in the "
            "words and blanked where the status line shows it.",
            "**The way back to the saved part.** Part › Defaults, then Apply, draws the "
            "part's own SCAD and numbers again, as walkthrough 14 does for its numbers.",
        ],
    )
    refs_before = _variant_refs_here()
    page.set_viewport_size({"width": WIDTHS[0][0], "height": WIDTHS[0][1]})
    site = f"{scad_url}/viewer/sites/parts_library"
    assert page.request.post(f"{scad_url}/parts/{PART}/stl/generate").ok
    _open(page, site)

    # Part › Edit: the SCAD in its editor.
    _ring(page, "Part", "Edit")
    expect(_code(page)).to_be_visible(timeout=20000)
    expect(_said(page)).to_contain_text("The part's own SCAD: edit it here")
    expect(page.locator("#part-saved")).to_contain_text("no variants saved yet")
    # The name Save keeps it under, greyed in the box until one is typed.
    expect(page.locator("#scad-name")).to_have_value("")
    expect(page.locator("#scad-name")).to_have_attribute("placeholder", "variant-1")
    own = _text(page)
    assert own == CUBE.source_file.read_text()
    with site_folded(page):
        page.evaluate(STAGE_BAR_AT_THE_TOP)
        story.shows(
            "Part › Edit opens the SCAD where its source stood",
            f"{PART}'s ring, Part › Edit: its parameters in Selected and, below them and "
            "the short list of its saved variants (none yet), its SCAD in an editor -- "
            "Site folded to its title by its ▾ here, so Selected has the rail. Typing in "
            "it is the next step.",
        )

    # Round one: a line OpenSCAD refuses, checked once typing stops, marked, not rendered.
    asked, stop = _counting(page)
    _into_code(page)
    page.keyboard.press("Control+End")
    ends_a_line = own.endswith("\n")
    page.keyboard.insert_text(REFUSED if ends_a_line else "\n" + REFUSED)
    refused_line = own.count("\n") + (1 if ends_a_line else 2)
    page.wait_for_function(
        "(line) => (window.fractalViewer.scadEditor?.marked ?? [])"
        ".some((m) => m.severity === 'error' && m.line === line)",
        arg=refused_line,
        timeout=15000,
    )
    expect(_said(page)).to_contain_text("Not rendered until it reads", timeout=10000)
    page.wait_for_timeout(1500)  # past when a check that passed would render: nothing
    assert asked == {"check": 1, "render": 0}, asked
    marked = page.locator(".scad-editor .cm-line:has(.cm-lintRange-error)")
    expect(marked).to_have_count(1)
    expect(marked).to_contain_text("too big to keep")
    # The error listed in the stage bar, which stays at the top of Selected; what the
    # editor says of it just under the bar; and the code below that, scrolled so the
    # marked line is its first.
    with site_folded(page):
        page.evaluate(STAGE_BAR_AT_THE_TOP)
        marked.evaluate(MARKED_LINE_FIRST)
        story.shows(
            "A failing line is checked once typing stops, and marked where it is",
            f"An assertion typed at the end that this part fails. One check, once typing "
            f"stops: OpenSCAD evaluates the edited SCAD beside the part and renders nothing, "
            f"and its error is marked on line {refused_line}, listed under the stage bar and "
            "said above the code -- Site folded to its title by its ▾ here, so Selected has "
            "the rail. Nothing is rendered while it does not read; changing the line is the "
            "next step.",
            blank=BLANK,
        )

    # A change that reads: rendered soon after its check, drawn as an applied variant.
    asked["check"] = asked["render"] = 0
    _replace_last_line(page, SMALL_TOP)
    _rendered(page, 15)
    assert asked == {"check": 1, "render": 1}, asked
    stop()
    expect(page.locator(".cm-lintRange-error")).to_have_count(0)
    # Taller than the envelope its numbers declare: the line amber, by how much.
    envelope = page.locator("#part-envelope")
    expect(envelope).to_have_class(re.compile(r"\bdiffers\b"))
    expect(envelope).to_contain_text("measured against the envelope +0.00 × +0.00 × +5.00 mm")
    by_hand(page, PART, distance=110)
    story.shows(
        "A change that reads is rendered soon after its check",
        "The line replaced with a smaller cube on top. Checked once typing stops, and "
        f"{RENDER_AFTER_CHECK_MS} ms after the check passes rendered as Apply renders, "
        "from the edited SCAD "
        "written beside the part, and drawn in this tab, 15 mm tall now: an applied "
        "variant, not saved, the view brought to it by hand, Shift+drag and the wheel. "
        "Taller than the envelope its numbers declare, the envelope's line turns amber and "
        "says by how much. The part's own SCAD is not touched. Part › Save is the next "
        "step.",
        shown=_said_on_the_page(page),
        blank=BLANK,
    )

    # Saved from the ring: a variant in git, listed in both places with what it changes.
    _ring(page, "Part", "Save")
    _saved(page, "variant-1")
    diff = page.locator(".scad-saved .saved-row[data-variant='variant-1'] .variant-diff")
    diff.locator("summary").click()
    expect(diff.locator("pre")).to_contain_text(f"+{SMALL_TOP}")
    page.locator(".scad-saved").scroll_into_view_if_needed()
    story.shows(
        "Part › Save keeps it as a variant in git",
        f"{PART}'s ring, Part › Save: the edited SCAD, its values in it, committed "
        f"to refs/apothecary/variants/{PART}/variant-1, the name the editor offered. "
        "Nothing in the checkout changes; a merge would bring it, its values with it, and "
        "merging is yours to do. It is listed under the "
        "part's parameters and, in the editor, with what it changes against the part's "
        "SCAD and that HEAD does not hold it. Floating the editor is the next step.",
        shown=_said_on_the_page(page),
        blank=BLANK,
    )

    # Docked, at both widths, nothing overlaps.
    _at_both_widths(page, shots, "docked")

    # Part › View › Float: the editor over the world, clear of what it must be clear of.
    _at_both_widths(page, shots, "floated")
    expect(page.locator(".scad-away")).to_be_attached()
    story.shows(
        "Part › View › Float puts the editor over the world",
        "Part › View › Float: the editor out of Selected, a panel of its own over the "
        "world, clear of the header, the hint bar, the depth ladder and the closed "
        "panels' tabs; where it stood, Selected says where it is. Its Fullscreen is the "
        "next step.",
        blank=BLANK,
    )

    # Fullscreen, from its own button; Esc puts it back.
    page.locator("#scad-fullscreen").click()
    expect(page.locator(".scad-editor.fullscreen")).to_be_visible()
    for width, height in WIDTHS:
        page.set_viewport_size({"width": width, "height": height})
        settled(page)
        _laid_out(page, width, shots, "fullscreen")
    page.set_viewport_size({"width": WIDTHS[0][0], "height": WIDTHS[0][1]})
    settled(page)
    story.shows(
        "Fullscreen covers the page",
        "Its Fullscreen button: the editor over the whole page, the code as tall as it "
        "can be. Esc, the same button or Part › View › Fullscreen puts it back.",
        blank=BLANK,
    )
    page.keyboard.press("Escape")
    expect(page.locator(".scad-editor.fullscreen")).to_have_count(0)
    expect(page.locator(".panel[data-panel='scad-editor'].free")).to_be_visible()

    # Round two, in the floated editor: a name typed, a bigger top, Ctrl+S in the editor.
    page.locator("#scad-name").fill("taller")
    _replace_last_line(page, BIG_TOP)
    _rendered(page, 20)
    _into_code(page)
    page.keyboard.press("Control+s")
    _saved(page, "taller")
    rows = page.locator("#part-saved .saved-variant")
    expect(rows).to_have_count(2)
    assert rows.evaluate_all("(rs) => rs.map((r) => r.dataset.variant)") == ["taller", "variant-1"]
    page.locator("#part-saved").evaluate(UNDER_THE_STAGE_BAR)
    story.shows(
        "Round two: a name, a change and Save",
        "In the floated editor: a name typed, taller, and the top made as big as the "
        "cube, rendered once it reads, 20 mm tall; then Ctrl+S in the editor, OpenSCAD's "
        "key, which saves as its Save does. Both variants are listed, newest first. "
        "Drawing the first again is the next step.",
        shown=_said_on_the_page(page),
        blank=BLANK,
    )

    # The first variant chosen from the ring, drawn again; the editor docked back.
    _ring(page, "Part", "Variants", "variant-1", "Draw")
    expect(_status(page)).to_contain_text("the variant variant-1 is drawn", timeout=60000)
    settled(page)
    assert _height(page) == pytest.approx(15, abs=0.05)
    assert _text(page).endswith(SMALL_TOP)
    expect(page.locator("#scad-name")).to_have_value("variant-1")
    _ring(page, "Part", "View", "Float")
    expect(page.locator(".panel[data-panel='scad-editor']")).to_have_count(0)
    expect(page.locator(".part-editor .scad-editor")).to_be_visible()
    page.locator(".scad-editor .scad-bar").scroll_into_view_if_needed()
    by_hand(page, PART, distance=110)
    story.shows(
        "Part › Variants draws the first again, and Part › View › Float docks it",
        f"{PART}'s ring, Part › Variants › variant-1 › Draw: its SCAD back in the editor, its "
        "values in it and the controls on them, drawn, 15 mm tall again, the name it saves "
        "under its own. "
        "Part › View › Float again puts the editor back in Selected.",
        blank=BLANK,
    )

    # Round three. The text moved on from variant-1: its name let go of, the next free
    # one greyed in its place; Ctrl+Z, the text back, and the name with it.
    name = page.locator("#scad-name")
    _into_code(page)
    page.keyboard.press("Control+End")
    page.keyboard.insert_text(" // round three")
    expect(name).to_have_value("")
    expect(name).to_have_attribute("placeholder", "variant-2")
    page.keyboard.press("Control+z")
    expect(name).to_have_value("variant-1")
    assert _text(page).endswith(SMALL_TOP)
    _settled_render(page)
    story.says(
        "The name box lets go of a variant once the text moves on",
        "A comment typed after variant-1's last line: the name box clears, variant-2 "
        "greyed in it, so Save would keep the edit under a name of its own and never "
        "over variant-1 unasked. Ctrl+Z in the editor: variant-1's text, and its name, "
        "back.",
    )

    # A name already saved: Save asks first, and another name keeps both.
    name.fill("taller")
    _into_code(page)
    page.keyboard.press("Control+s")
    expect(_status(page)).to_contain_text(
        "a variant named taller is saved already. Save again to replace it", timeout=10000
    )
    expect(_said(page)).to_contain_text("Save again to replace it")
    asked_first = _status(page).inner_text()
    name.fill("short-top")
    _into_code(page)
    page.keyboard.press("Control+s")
    _saved(page, "short-top")
    story.says(
        "Save asks before it replaces a variant",
        "taller typed in the name box, the text variant-1's, and Ctrl+S: the name is "
        "taken, so Save asks first -- Save again would replace it. Another name, "
        "short-top, and Ctrl+S keeps it beside the others.",
        shown=asked_first,
    )

    # F5: checked and drawn at once, without the quiet typing waits for. Under the floor.
    _replace_last_line(page, UNDER)
    page.keyboard.press("F5")
    expect(_status(page)).to_contain_text(f"{PART} regenerated from its edited SCAD", timeout=60000)
    settled(page)
    assert "/viewer/sites/parts_library" in page.url  # F5 reloaded nothing
    assert _height(page) == pytest.approx(22, abs=0.05)
    expect(page.locator("#part-envelope .floor")).to_have_text(" · 12.00 mm below the floor")
    expect(envelope).to_have_class(re.compile(r"\bdiffers\b"))
    page.locator("#part-envelope").evaluate("(el) => el.scrollIntoView({ block: 'center' })")
    by_hand(page, PART, distance=140)
    story.shows(
        "F5 checks and draws at once, and a part under the floor is flagged",
        "The last line made a small cube 12 mm under the part, and F5 in the editor, "
        "OpenSCAD's key: checked at once and drawn as soon as it reads, the page not "
        "reloaded. Drawn where it stands, it reaches under the floor, and the envelope's "
        "line says by how far beside what it measures against what it declares. F6 or "
        "Ctrl+Enter would render it as Apply does.",
        shown=_said_on_the_page(page),
        blank=BLANK,
    )

    # A draft that does not read, kept over a reload: leaving asks first, the page names
    # the part, and its editor offers the draft back.
    drawn = _text(page)
    _into_code(page)
    page.keyboard.press("Control+End")
    page.keyboard.insert_text("\n" + REFUSED)
    expect(_said(page)).to_contain_text("Not rendered until it reads", timeout=15000)
    asked = []

    def leave(dialog):
        asked.append(dialog.type)
        dialog.accept()

    page.on("dialog", leave)
    page.reload()
    expect(_status(page)).to_contain_text("Loaded", timeout=20000)
    page.remove_listener("dialog", leave)
    assert asked == ["beforeunload"], asked
    expect(_status(page)).to_contain_text(f"{PART} has work kept from before the reload")
    _ring(page, "Part", "Edit")
    expect(_code(page)).to_be_visible(timeout=20000)
    offer = page.locator("#kept-offer")
    expect(offer).to_be_visible(timeout=10000)
    expect(offer).to_contain_text("its SCAD edited")
    assert _text(page) == drawn  # what the address draws, until it is restored
    offer.evaluate(UNDER_THE_STAGE_BAR)
    story.shows(
        "A draft is kept over a reload, and offered back",
        "A line that does not read typed at the end, and the page reloaded: the browser "
        "asks before leaving, the status line names the part with work kept in this tab, "
        "and Part › Edit draws what the address names and offers the draft back. Restore "
        "is the next step.",
        shown=offer.locator(".kept-said").inner_text(),
        blank=BLANK,
    )
    page.locator("#kept-restore").click()
    expect(offer).to_be_hidden()
    assert _text(page).endswith(REFUSED)
    expect(_said(page)).to_contain_text("Not rendered until it reads", timeout=15000)

    # Another part edited, and back: the editor as it was left, its undo with it.
    page.locator("#contents-list .contents-item[data-path='v_slot']").click(
        button="right", modifiers=["Control"]
    )
    expect(page.locator("#ring-overlay")).to_be_visible(timeout=RING_MS)
    _press(page, "Part", "Edit")
    expect(page.locator(".part-editor[data-target='part:v_slot']")).to_be_attached(timeout=10000)
    _ring(page, "Part", "Edit")
    expect(_code(page)).to_be_visible(timeout=20000)
    assert _text(page).endswith(REFUSED)
    _into_code(page)
    page.keyboard.press("Control+z")
    assert _text(page) == drawn
    story.says(
        "Restore puts the draft back, and the editor keeps its undo while another part is edited",
        "Restore: the draft back in the editor, checked, its refusal marked. Then v_slot's "
        "editor, and calibration_cube's again: its text as it was left, and Ctrl+Z undoes "
        "the restore, as it would have before v_slot was opened.",
    )
    _settled_render(page)

    # Every variant is a ref of the clone the server saves into; none of this checkout's.
    listed = page.request.get(f"{scad_url}/parts/{PART}/saved").json()
    assert [(v["name"], v["merged"]) for v in listed] == [
        ("short-top", False),
        ("taller", False),
        ("variant-1", False),
    ]
    assert _variant_refs_here() == refs_before
    assert CUBE.source_file.read_text() == own


@pytest.mark.e2e
def test_after_a_scad_edit_defaults_then_apply_draws_the_saved_part(
    page: Page, scad_url: str, cube_as_it_was
):
    """The way back after a SCAD edit: the text is the one draft, so the edit drawn is
    what is drawn and nothing is staged. Defaults puts the part's own SCAD back -- its
    defaults are its SCAD as saved -- and Apply, saying it draws the saved part, draws
    it, the mark and the address's variant gone: from the ring, and with the editor's
    own Defaults and Apply."""
    quarter = "translate([0, 0, size]) cube(size / 4);"  # 12.5 mm tall, this test's own
    assert page.request.post(f"{scad_url}/parts/{PART}/stl/generate").ok
    _open(page, f"{scad_url}/viewer/sites/parts_library")
    _ring(page, "Part", "Edit")
    expect(_code(page)).to_be_visible(timeout=20000)
    own = _text(page)

    for from_the_ring in (True, False):
        _into_code(page)
        page.keyboard.press("Control+End")
        page.keyboard.insert_text(quarter if own.endswith("\n") else "\n" + quarter)
        expect(_status(page)).to_contain_text(
            "from its edited SCAD: an applied variant, not saved", timeout=60000
        )
        settled(page)
        assert _height(page) == pytest.approx(12.5, abs=0.05)
        assert re.search(rf"[?&]variant={PART}", page.url), page.url
        expect(page.locator(".part-editor")).to_have_class(re.compile(r"\bdrawn-from-variant\b"))
        # The edit is what is drawn: nothing is staged, and nothing to apply.
        expect(page.locator("#stage-summary")).to_have_text("No staged changes")
        expect(page.locator("#apply-btn")).to_be_disabled()
        if from_the_ring:
            _ring(page, "Part", "Defaults")
            expect(_status(page)).to_contain_text(
                "the part's own SCAD is back in its editor", timeout=10000
            )
        else:
            page.locator("#defaults-btn").click()
        # The part's own text, and still the saved part to go to.
        assert _text(page) == own
        expect(page.locator("#stage-summary")).to_contain_text("Apply draws the saved part")
        expect(page.locator("#apply-btn")).to_have_text("Apply: the saved part")
        expect(page.locator("#apply-btn")).to_be_enabled()
        if from_the_ring:
            _ring(page, "Part", "Apply")
        else:
            page.locator("#apply-btn").click()
        expect(_status(page)).to_contain_text(f"{PART} from the cache", timeout=30000)
        expect(_status(page)).to_contain_text("drawn as saved")
        settled(page)
        assert _height(page) == pytest.approx(10, abs=0.05)  # the saved cube, its own size
        assert "variant=" not in page.url, page.url
        expect(page.locator(".part-editor")).not_to_have_class(
            re.compile(r"\bdrawn-from-variant\b")
        )
        assert _text(page) == own
        expect(page.locator("#stage-summary")).to_have_text("No staged changes")
        expect(page.locator("#apply-btn")).to_be_disabled()


@pytest.mark.e2e
def test_the_code_taken_before_the_controls_are_built_keeps_the_keys(
    page: Page, scad_url: str, cube_as_it_was
):
    """Part › Edit puts the cursor in the part's first control once its controls are
    built, and the code can be shown before them. Taken first, the code keeps the focus
    when they arrive, and the keys pressed in it are its own: not the size slider's,
    where Ctrl+End is the largest size and the text typed lands at the code's start.
    The part's parameters are held back here until the code has the focus, as a slow
    machine holds them."""
    quarter = "translate([0, 0, size]) cube(size / 4);"
    _open(page, f"{scad_url}/viewer/sites/parts_library")
    page.evaluate(
        """(part) => { const real = window.fetch;
            const held = new Promise((go) => { window.releaseParams = go; });
            window.fetch = async (url, init) => {
                if (String(url).includes(`/parts/${part}/params`)) await held;
                return real(url, init);
            }; }""",
        PART,
    )
    _ring(page, "Part", "Edit")
    expect(_code(page)).to_be_visible(timeout=20000)
    size = page.locator("#part-params .param[data-field='size']")
    expect(size).to_have_count(0)
    own = _text(page)
    _code(page).focus()
    page.evaluate("() => window.releaseParams()")
    expect(size).to_be_visible(timeout=15000)
    assert page.evaluate("() => document.activeElement.classList.contains('cm-content')")
    page.keyboard.press("Control+End")
    typed = quarter if own.endswith("\n") else "\n" + quarter
    page.keyboard.insert_text(typed)
    page.wait_for_function(
        "(want) => window.fractalViewer.scadEditor.text() === want", arg=own + typed
    )
    assert page.evaluate("() => window.fractalViewer.partParams.size") == 10
