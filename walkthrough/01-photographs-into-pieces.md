# 01 — Photographs into pieces you could print

Written by `tests/e2e/test_docs_photo_walkthrough.py`, and
rewritten by the ordinary test command (`uv run apothecary test run`).
Each numbered step is written as the run reaches it, after the assertions
before it pass, and what a step shows is what the run had then. The
opening, the notes under it and the list of what the page does not show
are the test's fixed words. Editing the page by hand is editing the output
of a program: the next run puts it back.

Point the tool at a photograph. It finds the flat shapes in it, matches each one to a named, reusable word, places them in space, sorts a folder of them into what belongs with what, asks you the questions it cannot settle, and shows the result in the viewer. Nothing claims to be measured unless somebody said how wide the picture is.

**Runtime-bound.** It draws its own photographs and reads them back, then walks the same pieces in a real browser against a real server. It needs no network. Its second half needs a browser and a running server.

Its pictures draw every part that OpenSCAD version 2021.01, the OpenSCAD its server runs, can build from an STL it built; a part it cannot build is drawn from an STL already there, or as its box.

---

## 1. A photograph becomes shapes

The finder is deliberately plain: it shrinks the picture, splits light from dark, gathers touching pixels, and guesses each blob from how much of its box it fills. This one was drawn to order, so the answer is known.

```
4 shapes found in same0_a
```

## 2. Nothing there is a measurement

A photograph on its own cannot say how big anything is, so every position comes back as a fraction of the picture.

```
x from 0.754 to 0.918, y from 0.141 to 0.362
```

## 3. Each shape gets a name, and says how sure it is

A word is a recipe that builds an ordinary piece, so a named shape is something the rest of the tool already knows how to handle. The confidence is the finder's own, and the plain finder never gives more than 0.8: how much of its box a blob fills is a guess at its shape, never a certainty.

```
plate, 0.64 sure
```

## 4. Placed, and honest about not being measured

Give it no real-world size and the pieces are still placed, marked as having no size rather than quietly given one. Every piece carries where it came from.

```
4 pieces, sized=False
first piece seen by the 'plain' finder, thickness guessed: True
```

## 5. Several photographs at once, and which are of the same thing

Some of these are of one thing, some are neighbouring parts of something bigger, and some are of nothing in particular. A photograph with nothing in it is set aside with a reason rather than quietly dropped.

```
11 photographs read
blankset_empty set aside: only 0 shape(s) were found, and 2 is the fewest that makes an arrangement
```

## 6. Every answer says why, and 'cannot tell' is an answer

The sorting is conservative on purpose: it would rather decline a pair than guess at it. A pair it cannot decide comes back as a real answer with a reason attached, not as a gap in the output.

```
2 group(s) built, 29 pair(s) declined
same0_a and same0_b: the same thing, because 4 matching shapes line up under one step and zoom (1.00×, 0% out); 2 other match(es) do not fit and were dropped
```

## 7. You are better at this than it is, so it asks

It works out which questions are worth a minute, best first, by how many other pairs an answer would settle. A person answers in plain sentences, each ending in one of the verdicts: 'the same thing', 'parts of one thing', 'not related', 'not worth using', 'worth using anyway'.

```
Are apart0_a and blankset_a photographs of the same thing?
```

## 8. Their word wins, carries, and marks the machine

A person's answer beats the machine's outright, builds the group that follows from it, and says who decided. It also scores the machine, because an answered pair is a pair where the answer is known.

```
parts0_left and parts0_right: parts of one thing, said by you
the group it makes: ['parts0_left', 'parts0_right']
scorecard: {'you answered': 2, 'about a pair': 1, 'about one picture': 1, 'agreed': 0, 'overruled': 0, 'silent': 1}
```

## 9. Two answers that contradict each other are refused

Not averaged, and not last-one-wins. The refusal names both lines, because the person who wrote them is the only one who can settle it.

```
line 2 says 'a and b are the same thing' and line 3 says 'b and a are not related'. Both cannot be true, and picking one would mean a machine deciding which person was right. Nothing was merged. Delete or correct one of the two.
```

## 10. The same path, now against a real server

This is the picture the rest of the page is about: 800 by 600 pixels, 4 shapes found by the 'plain' finder. Everything above ran in this process. Everything below runs through the server and a browser.

![The same path, now against a real server](screenshots/01-10-the-same-path-now-against-a-real-server.png)

## 11. Told how wide it is, the pieces get real sizes

Nine hundred millimetres across, so the pieces have sizes rather than fractions. That a machine picked every one of these shapes is recorded separately from whether they have a size, because they are different claims.

```
words: disc, plate, slot, wedge
sized: True
```

## 12. The arrangement opens in the viewer

An arrangement built from a photograph is an ordinary arrangement, drawn as any site is, each piece as its word builds it: a wedge is a triangle in the world, as the picture's was.

![The arrangement opens in the viewer](screenshots/01-12-the-arrangement-opens-in-the-viewer.png)

## 13. Every piece is listed, named for the word it was matched to

Site, beside the world in the picture above, lists the pieces by name, and the names are the words from the top of this page. One vocabulary runs the whole length of the path.

```
plate_1 (word)
disc_2 (word)
wedge_3 (word)
slot_4 (word)
```

## 14. Each word is a chip above the list, and 'disc' is chosen

The chips are the viewer's own, one per word the pieces carry. A chip expands every piece of its word, at any depth; these pieces are flat shapes with nothing inside, so choosing one marks the chip and leaves the list and the world as they were.

![Each word is a chip above the list, and 'disc' is chosen](screenshots/01-14-each-word-is-a-chip-above-the-list-and-disc-is-cho.png)

## 15. Choosing a piece shows where it came from

Its word and why, the finder that saw it ('plain'), how sure it was (0.67), and that its thickness is a guess: the same provenance the model half printed, in Selected, beside its place.

![Choosing a piece shows where it came from](screenshots/01-15-choosing-a-piece-shows-where-it-came-from.png)

## 16. And it forgets on request

The picture it was all built from is served beside the arrangement while the arrangement exists, and both go when the arrangement is forgotten.

## What this page does not show

- **A real photograph.** Everything here is drawn to order, which is how the answers are known. Shadow, texture, blur and clutter are all absent, so a good showing here means it handles the easy case.
- **A printable model.** These pieces stay an arrangement here; a piece made from a camera's picture is sliced and printed in walkthrough 03.
- **Anything about how long it takes.** No timing is asserted anywhere in this run.
- **Anything surviving a restart.** Nothing here is stored. The run builds what it needs and forgets it.

Run it yourself:

```sh
uv run apothecary test run
```
