# 01 — Photographs into pieces you could print

If you want to see what this tool actually does, rather than read about it,
start here.

**This page runs.** Every example below is executed by `uv run apothecary test
walkthrough`, and the output shown is the output that ran. If a behaviour
changes, this page fails the build rather than quietly describing something that
stopped being true.

**Runtime-bound.** It draws its own photographs into a temporary folder and
reads them back. It needs no network, no server and no browser. It does not
render a printable model, because that needs a program this page does not
install.

It walks the whole chain end to end: a photograph, the shapes in it, the names
those shapes get, several photographs at once, what a person tells it, and what
the whole thing costs a person to use.

---

## 1. A photograph becomes shapes

The finder is deliberately plain: it shrinks the picture, splits light from
dark, gathers touching pixels, and guesses each blob from how much of its box it
fills. Here is one drawn to order, so the answer is known.

    >>> from apothecary.gathering import bench
    >>> from pathlib import Path
    >>> import tempfile
    >>> folder = Path(tempfile.mkdtemp())
    >>> occasions = bench.draw_occasions(folder, each=1, seed=17)
    >>> picture_path = folder / "same0_a.png"
    >>> picture_path.exists()
    True

    >>> from apothecary.vision.plain import PlainFinder
    >>> picture = PlainFinder().look(picture_path)
    >>> picture.name
    'same0_a'
    >>> len(picture.shapes) >= 3
    True

Nothing there is a measurement. A photograph on its own cannot say how big
anything is, and every position comes back as a fraction of the picture:

    >>> first = picture.shapes[0]
    >>> 0.0 <= first.min_point.x <= 1.0 and 0.0 <= first.max_point.y <= 1.0
    True

## 2. Each shape gets a name, and says how sure it is

    >>> from apothecary.vocabulary import word_for
    >>> choice = word_for(first)
    >>> choice.word in {"plate", "disc", "post", "slot", "wedge"}
    True

The confidence is never rounded up. It is measurably lower when the finder is
wrong, which is what makes it worth reporting at all:

    >>> 0.0 < first.confidence < 1.0
    True

## 3. Placed, and honest about not being measured

Give it no real-world size and the pieces are still placed — marked as having no
size rather than being quietly made up.

    >>> from apothecary.vision import build
    >>> made = build(picture, picture_path=picture_path)
    >>> len(made.site.children) == len(picture.shapes)
    True
    >>> made.album.sized
    False
    >>> all(piece.status == "unsized" for piece in made.site.children)
    True

Every piece carries where it came from:

    >>> about = made.album.provenance[made.site.children[0].name]
    >>> about.finder
    'plain'
    >>> about.thickness_guessed
    True

## 4. Several photographs at once, and which are of the same thing

This is the part that is hard. Some of these are of one thing, some are
neighbouring parts of something bigger, and some are of nothing in particular.

    >>> paths = sorted(folder.glob("*.png"))
    >>> len(paths)
    11
    >>> finder = PlainFinder()
    >>> pictures = [finder.look(path) for path in paths]

    >>> from apothecary.gathering import gather
    >>> found = gather(pictures, paths=paths)
    >>> len(found.readings)
    11

One of those photographs has nothing in it. It is set aside with a reason
rather than quietly dropped:

    >>> "blankset_empty" in found.set_aside
    True
    >>> print(found.set_aside["blankset_empty"])
    only 0 shape(s) were found, and 2 is the fewest that makes an arrangement

The sorting is conservative on purpose. It finds about a fifth of the groups
that are there, and on eight hundred and thirty drawn photographs it has never
built one out of photographs that did not belong together:

    >>> groups = [c for c in found.clusters if c.kind != "on its own"]
    >>> len(groups) >= 1
    True

**Every answer says why**, including the ones against it:

    >>> said = found.between("same0_a", "same0_b")
    >>> said.verdict
    'the same thing'
    >>> len(said.because) >= 1
    True

And a pair it cannot decide is a real answer, not a gap:

    >>> undecided = found.undecided()
    >>> all(k.verdict == "cannot tell" for k in undecided)
    True

## 5. You are better at this than it is, so it asks

The machine works out which questions are worth a minute — best first, with what
each one is worth — and a person answers in plain sentences.

    >>> from apothecary.gathering.questions import worth_asking
    >>> questions = worth_asking(found, most=3)
    >>> len(questions) >= 1
    True
    >>> print(questions[0].sentence())        # doctest: +ELLIPSIS
    Are ... and ... photographs of the same thing?

The whole language a person writes is five sentences:

    >>> from apothecary.gathering.judgement import read_answers
    >>> answers = read_answers('''
    ... parts0_left and parts0_right are parts of one thing
    ... blankset_empty is not worth using   # that one is a blank wall
    ... ''')
    >>> [one.verdict for one in answers]
    ['parts of one thing', 'not worth using']

**Their word wins**, and it says who decided:

    >>> told = gather(pictures, paths=paths, answers=answers)
    >>> joined = told.between("parts0_left", "parts0_right")
    >>> joined.verdict
    'parts of one thing'
    >>> joined.said_by
    'you'
    >>> joined.strength
    1.0

**Their word carries** — the group it makes is built out of that one sentence:

    >>> holding = told.cluster_holding("parts0_left")
    >>> sorted(holding.pictures)
    ['parts0_left', 'parts0_right']

**And their word marks the machine**, because an answer is a case where the
answer is known:

    >>> card = told.scorecard()
    >>> card["you answered"]
    2
    >>> card["agreed"] + card["overruled"] + card["silent"] == card["about a pair"]
    True

Two answers that contradict each other are refused rather than averaged:

    >>> from apothecary.gathering.judgement import PeopleDisagree, settle
    >>> both_ways = """
    ... a and b are the same thing
    ... b and a are not related
    ... """
    >>> try:
    ...     settle(read_answers(both_ways))
    ... except PeopleDisagree as refused:
    ...     print("refused, and it names both lines")
    ...     print(str(refused).count("line ") >= 2)
    refused, and it names both lines
    True

## 6. What the whole thing costs a person

Two meters, because a tool that is pleasant to demonstrate and expensive to use
is neither.

    >>> from apothecary import census, workflows
    >>> controls = census.take()
    >>> len(controls.controls_of_its_own())
    20

Twenty controls of its own in the viewer. Unifying means that reaches nothing —
not a smaller pile, nothing.

    >>> typed = workflows.take()
    >>> typed.typed
    10
    >>> len(typed.only_typed()) >= 1
    True

Ten typed steps across eight named jobs, most of them carried by nothing but
typing. Each of those is an open item about where the interface stops.

## What this page does not show

- **A real photograph.** Everything here is drawn to order, which is how the
  answers are known. Shadow, texture, blur and clutter are all absent, so a good
  showing here means "handles the easy case".
- **A printable model.** Turning an arrangement into a solid needs a program
  this page does not install. Nothing below the arrangement is exercised.
- **The viewer.** The pieces above can be walked into in a browser, and that is
  driven by `apothecary docs generate` rather than here, because it needs a
  server and a browser.
- **Anything about how long it takes.** No timing is asserted anywhere on this
  page.

Run it yourself:

```sh
uv run apothecary test walkthrough
```
