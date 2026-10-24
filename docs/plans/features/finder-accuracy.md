# How well the plain finder actually does

| | |
|---|---|
| **Kind** | feature |
| **Repo** | quaternionmedia/apothecary |
| **State** | measured; the numbers below are the current reading |
| **Depends on** | Photo → shapes → words → placed scenes → links |
| **Graduates to** | a paragraph in the shape provider seam record |
| **Verified** | **Executed.** `apothecary photo check` draws pictures whose answers are known and scores a finder against them. Every number below came out of a run; none was estimated. |

## What

Run it yourself:

```
apothecary photo check
```

Measured on 20 generated pictures per row, at the tip of this work:

| condition | found | named right | made up | less sure when wrong |
|---|---|---|---|---|
| clear shapes | 100% | 100% | 0 | — |
| turned and speckled | 100% | 100% | 0 | — |
| softly blurred | 100% | 100% | 0 | — |
| heavily blurred | 100% | 71% | 0 | +0.39 |
| faint against the background | 100% | 100% | 0 | — |
| small (5–10% of the picture) | 100% | 88% | 0 | +0.19 |
| very small (3–6%) | 100% | 51% | 0 | +0.15 |
| crowded (up to 8 shapes) | 100% | 100% | 0 | — |

**found** — of the shapes drawn, how many came back in about the right place.
**named right** — of those, how many were called the right family.
**made up** — shapes reported that were never drawn. Zero everywhere, which
matters more than the other columns: an invented shape is worse than a missed
one, because nothing downstream can tell it is not real.
**less sure when wrong** — how much lower the confidence runs on the ones it got
wrong. Positive in every hard row, so the confidence can be trusted to flag its
own bad guesses.

## Why now

Because the alternative was a document saying the finder "works". Two things
came out of measuring that would not have come out of asserting.

**Turned shapes were being named wrongly**, and nobody would have guessed which
ones. A square turned 45° fills half of its upright box, which is exactly what a
triangle does, so turned squares were coming back as triangles. Judging by the
*tightest* box at any angle instead fixed it, and handed back the angle as a
bonus — so a bar lying at 35° in a photograph now becomes a bar lying at 35° in
the thing you build, at its true size rather than the size of the upright box
around it, which was four times too big.

**Small shapes were being thrown away.** The speckle filter measured a blob
against the size of the whole picture, so a small shape in a large picture was
discarded for being small relative to a frame it had nothing to do with. Found
rate at 3–6% was 33%. An absolute floor in pixels took it to 100% while still
rejecting every speckle.

## What an independent review found that this did not

The table above was green in every row that mattered while three faults sat in
the code that would have ruined the first real photograph. They were found by
someone reviewing the code with no knowledge of why it was written that way, who
was asked to break it rather than check it. Worth recording, because the harness
did not catch any of them and could not have.

- **Every photograph that is not square was stretched by a third.** Positions
  across the picture and down it are fractions of different edges, and both were
  being multiplied by the width. Pieces ended up outside the picture they came
  from. All the generated test pictures happened to be handled consistently, so
  nothing showed.
- **One object filling the frame came back as the background.** The finder called
  whichever colour was rarer the subject. Fill more than half the frame — which
  is how anybody photographs one thing on purpose — and it reported a single
  shape covering the whole picture, at *higher* confidence than the correct
  answer got. The harness draws small shapes on a large background and so can
  never produce this. The rule is now "the background is whatever runs round the
  outside".
- **Anything saved with a see-through background found nothing at all**, because
  transparency is stored as black underneath, and **a phone photograph came out a
  quarter turn round**, because the note saying which way up it goes was ignored.

Two more worth naming: a ruler photographed at an angle was measured by its
upright box and scaled the whole build a third too big, and a picture smaller
than the working size had its shapes thrown away as speckle. Both are fixed and
both have tests in `tests/test_photo_hard_cases.py`, which exists because these
were not the sort of fault the friendly tests were ever going to find.

The lesson is in the second one: **the harness scores what the harness draws.**
Rows reading 100% were evidence about a world where subjects are small and
backgrounds are plain.

## Seam

`apothecary/vision/bench.py` draws the pictures and scores a finder through the
same connection everything else uses, so any future finder is measured the same
way with no changes. `tests/test_finder_accuracy.py` holds the floors, marked
slow. `apothecary/vision/geometry.py` has the tightest-box work, tested as
properties — turning a shape must not change its tightest box — rather than as
remembered examples.

## Open questions

- **These are drawings, not photographs.** Clean edges, flat background, no
  shadow, no texture, nothing overlapping. A good score here means the easy case
  is handled. The first real photograph will be worse and should be measured
  rather than argued about.
- **Naming small and blurred shapes stays poor**, and probably always will from
  one crude number. Counting corners on the outline would help and has not been
  tried. The confidence already says when to distrust the answer, which is the
  cheaper half of the fix.
- **Nothing here overlaps.** Two touching shapes merge into one blob and will be
  reported as one strange shape. Not measured, because the generator refuses to
  place shapes that touch — which is itself a limit of the harness worth naming.
- The floors in the test are set a little under what was measured, so ordinary
  wobble does not turn the suite red. If one fails, the finder got worse — go and
  look rather than lowering the number.
