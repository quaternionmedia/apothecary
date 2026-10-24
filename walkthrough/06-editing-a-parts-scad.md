# 06 — Editing a part's SCAD

Written by `tests/e2e/test_scad_loop.py`, and
rewritten by every run of the browser suite (`uv run apothecary test
all`), though not by the quicker `apothecary test run`.
Each numbered step is written as the run reaches it, after the assertions
before it pass, and what a step shows is what the run had then. The
opening, the notes under it and the list of what the page does not show
are the test's fixed words. Editing the page by hand is editing the output
of a program: the next run puts it back.

A part's SCAD edited in the page: the part laid out by the Part view, its SCAD in a window beside the world, a failing line checked once typing stops and marked where it is, a change rendered soon after its check passes and drawn as an applied variant, kept as a variant in git and listed with what it changes, the editor made fullscreen; then round again, and the first variant drawn once more; then the name a save keeps, OpenSCAD's own keys, a draft kept over a reload and the editor's undo kept while another part is edited. Every step is the page's own: a cell of a ring, a key or a button, and every step's words name the next one.

**Runtime-bound.** It drives a real browser against a real server of its own, with the OpenSCAD every test server runs and a temporary cache of variants. A variant is saved into a clone of the checkout the server was given, never the checkout's own refs, which the run checks are as it found them. It needs no network, and refuses one.

Its pictures draw every part that OpenSCAD version 2021.01, the OpenSCAD its server runs, can build from an STL it built; a part it cannot build is drawn from an STL already there, or as its box.

---

## 1. Part › Edit, and the Part view lays the part out

calibration_cube's ring, Part › Edit, then Panels › Windows › Part view: Selected with the staged changes' bar, its Parameters under it with Variants, History and Readiness as tabs behind them, and its SCAD in an editor in a window of its own beside the world. Typing in it is the next step.

![Part › Edit, and the Part view lays the part out](screenshots/06-01-part-edit-and-the-part-view-lays-the-part-out.png)

## 2. A failing line is checked once typing stops, and marked where it is

An assertion typed at the end that this part fails. One check, once typing stops: OpenSCAD evaluates the edited SCAD beside the part and renders nothing, and its error is marked on line 125, listed under the stage bar in Selected and said above the code. Nothing is rendered while it does not read; changing the line is the next step.

![A failing line is checked once typing stops, and marked where it is](screenshots/06-02-a-failing-line-is-checked-once-typing-stops-and-ma.png)

## 3. A change that reads is rendered soon after its check

The line replaced with a smaller cube on top. Checked once typing stops, and 300 ms after the check passes rendered as Apply renders, from the edited SCAD written beside the part, and drawn in this tab, 15 mm tall now: an applied variant, not saved, the view brought to it by hand, Shift+drag and the wheel. Taller than the envelope its numbers declare, the envelope's line turns amber and says by how much. The part's own SCAD is not touched. Part › Save is the next step.

![A change that reads is rendered soon after its check](screenshots/06-03-a-change-that-reads-is-rendered-soon-after-its-che.png)

```
calibration_cube regenerated from its edited SCAD: an applied variant, not saved; Part › Save keeps it in git
```

## 4. Part › Save keeps it as a variant in git

calibration_cube's ring, Part › Save: the edited SCAD, its values in it, committed to refs/apothecary/variants/calibration_cube/variant-1, the name the editor offered. Nothing in the checkout changes; a merge would bring it, its values with it, and merging is yours to do. It is listed in the part's Variants and, in the editor, with what it changes against the part's SCAD and that HEAD does not hold it. Fullscreen is the next step.

![Part › Save keeps it as a variant in git](screenshots/06-04-part-save-keeps-it-as-a-variant-in-git.png)

```
calibration_cube saved as the variant variant-1, a commit on refs/apothecary/variants/calibration_cube/variant-1; nothing in the checkout changed. The ref is in <the test server's variants repository>, not this checkout: `git fetch <the test server's variants repository> refs/apothecary/variants/calibration_cube/variant-1:refs/apothecary/variants/calibration_cube/variant-1` there brings it, then `git merge refs/apothecary/variants/calibration_cube/variant-1` makes the variant's SCAD the part's, its values with it: they are its assignments, so the part is drawn with them. (⌗39)
```

## 5. Fullscreen covers the page

Its Fullscreen button: the editor over the whole page, the code as tall as it can be. Esc, the same button or Part › View › Fullscreen puts it back.

![Fullscreen covers the page](screenshots/06-05-fullscreen-covers-the-page.png)

## 6. Round two: a name, a change and Save

In the SCAD window: a name typed, taller, and the top made as big as the cube, rendered once it reads, 20 mm tall; then Ctrl+S in the editor, OpenSCAD's key, which saves as its Save does. Both variants are listed in Variants, brought in front of Parameters, newest first. Drawing the first again is the next step.

![Round two: a name, a change and Save](screenshots/06-06-round-two-a-name-a-change-and-save.png)

```
calibration_cube saved as the variant taller, a commit on refs/apothecary/variants/calibration_cube/taller; nothing in the checkout changed. The ref is in <the test server's variants repository>, not this checkout: `git fetch <the test server's variants repository> refs/apothecary/variants/calibration_cube/taller:refs/apothecary/variants/calibration_cube/taller` there brings it, then `git merge refs/apothecary/variants/calibration_cube/taller` makes the variant's SCAD the part's, its values with it: they are its assignments, so the part is drawn with them.
```

## 7. Part › Variants draws the first again

calibration_cube's ring, Part › Variants › variant-1 › Draw: its SCAD back in the editor, its values in it and the controls on them, drawn, 15 mm tall again, the name it saves under its own.

![Part › Variants draws the first again](screenshots/06-07-part-variants-draws-the-first-again.png)

## 8. The name box lets go of a variant once the text moves on

A comment typed after variant-1's last line: the name box clears, variant-2 greyed in it, so Save would keep the edit under a name of its own and never over variant-1 unasked. Ctrl+Z in the editor: variant-1's text, and its name, back.

## 9. Save asks before it replaces a variant

taller typed in the name box, the text variant-1's, and Ctrl+S: the name is taken, so Save asks first -- Save again would replace it. Another name, short-top, and Ctrl+S keeps it beside the others.

```
calibration_cube: a variant named taller is saved already. Save again to replace it, or give this one another name
```

## 10. F5 checks and draws at once, and a part under the floor is flagged

The last line made a small cube 12 mm under the part, and F5 in the editor, OpenSCAD's key: checked at once and drawn as soon as it reads, the page not reloaded. Drawn where it stands, it reaches under the floor, and the envelope's line says by how far beside what it measures against what it declares. F6 or Ctrl+Enter would render it as Apply does.

![F5 checks and draws at once, and a part under the floor is flagged](screenshots/06-10-f5-checks-and-draws-at-once-and-a-part-under-the-f.png)

```
calibration_cube regenerated from its edited SCAD: an applied variant, not saved; Part › Save keeps it in git
```

## 11. A draft is kept over a reload, and offered back

A line that does not read typed at the end, and the page reloaded: the browser asks before leaving, the status line names the part with work kept in this tab, and Part › Edit draws what the address names and offers the draft back. Restore is the next step.

![A draft is kept over a reload, and offered back](screenshots/06-11-a-draft-is-kept-over-a-reload-and-offered-back.png)

```
Kept in this tab from before it was reloaded: its SCAD edited from short-top. Restore puts it back; Discard lets it go.
```

## 12. Restore puts the draft back, and the editor keeps its undo while another part is edited

Restore: the draft back in the editor, checked, its refusal marked. Then v_slot's editor, and calibration_cube's again: its text as it was left, and Ctrl+Z undoes the restore, as it would have before v_slot was opened.

## What this page does not show

- **Making a variant the part's source.** That is a merge you do (`git merge refs/apothecary/variants/<part>/<name>`); no control in the page writes the checkout.
- **A part without a model.** Its controls come from what its SCAD declares, where the OpenSCAD in use lists them; calibration_cube has a model.
- **When a variant was saved, and where the server keeps it.** Both differ on every run: the lists' times are blanked in the pictures, and the server's clone of the checkout is named as the test server's variants repository in the words and blanked where the status line shows it.
- **The way back to the saved part.** Part › Defaults, then Apply, draws the part's own SCAD and numbers again, as walkthrough 04 does for its numbers.

Run it yourself:

```sh
uv run pytest tests/e2e/test_scad_loop.py --start-server   # this page alone
uv run apothecary test all                                 # with every browser test
```
