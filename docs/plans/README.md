# Plans

This folder holds the thinking for a piece of work that has not been built yet.

**Start here. This page is written for anyone.** The pages further down are
written for people building the thing, and you get to them through this one, not
around it.

## What the work is

Apothecary is a tool for designing parts you can print on a 3D printer. The idea
being planned: take a photograph of something, have the tool pick out the basic
shapes in it, place those shapes in space, give each shape a name so it can be
used again, and let named shapes be assembled into arrangements that connect to
one another.

Alongside that, a second idea that turned out to matter more. The organisation
has a ring of options that appears under your finger or your cursor — one gesture
to reach any command. It has been described as a menu. Everything measured about
it only makes sense if its real job is to *replace* an application's scattered
buttons, dropdowns and checkboxes with a single way in. That was believed and
never written down. It is now written down, and it now has a number that a
machine takes rather than a person:

    apothecary census

**Twenty controls of its own**, counted one at a time from the page itself:
buttons, drop-downs, tick-boxes, typing boxes, a form and a link. Beside them,
four things done to the scene, six places in the lists, and taking hold of a
piece and moving it. Unifying means the twenty reaches nothing — not a smaller
pile, nothing, because a ring that leaves five buttons behind has not replaced
them.

**An earlier version of this page said twelve, and twelve was wrong.** It was a
hand tally, and the first counter written was built until it agreed with the
tally. A reviewer took that counter apart: it counted names rather than controls,
so two buttons side by side came to one; it could not see a drop-down that
nothing listens to; and its own rule, applied evenly, gave nine or sixteen but
never twelve. The counter was rebuilt against a rule written down first, and
twenty is what that rule says.

## What state it is in

**The first part is built and runs.** You can point it at a picture and get back
named pieces with real sizes. It is deliberately crude — see below.

Nothing is agreed. Every rule and every decision here is still a proposal waiting
on a person.

Four related projects could not be reached from where this was written, so their
existence is genuinely unknown rather than assumed either way.

## Two new rules, and one withdrawn

| Proposal | In one sentence |
|---|---|
| [Light Language](proposals/light-language.md) | Every set of documents has a plain page at the front, written first, and everything else is reached through it |
| [It runs on your machine and the data stays there](proposals/runs-and-stays-local.md) | The software stores nothing anywhere else and needs no outside service to work; slow and yours beats fast and borrowed |
| [People and machines, here](proposals/people-and-machines.md) | **Withdrawn as a new rule** — the organisation has one now. Kept as three narrower additions: your word carries, the machine works out what is worth asking, and every answer marks the machine |

[**Concerns for review**](CONCERNS.md) lists everything those two leave
unresolved — twenty items, six of which block further building.

## Trying it

    apothecary photo gather ~/pictures --ask questions.txt
    apothecary photo gather ~/pictures --answers questions.txt --map-to went.html --view
    apothecary photo look  picture.png
    apothecary photo build picture.png --width-mm 800 --out bench.scad
    apothecary photo view  picture.png --width-mm 800
    apothecary photo words

**Or from the browser.** `apothecary serve`, open the viewer, and the ring's
Panels › Camera (or `Camera` on the canvas ring) opens the **Camera &
pictures** panel: allow the browser's cameras, pick one and see it live,
**Capture** a frame -- it is kept on this machine, under `captures/` in the
picture folder (`APOTHECARY_PICTURE_ROOT`, else the folder the server was
started in), and nowhere else -- and **Look** captures, looks and opens what
the finder made of it in the world. That is a camera's first sanity check:
record its own surroundings and see what comes back (a room is crude
pieces: plates, wedges, discs, most of them overlapping; a drawn picture is
not). **Place at selected** stands the camera at the chosen piece, and the
world draws it there from then on -- a badge and a small frustum -- in
every browser. Below, the pictures on this machine: tick some, **Gather**
for the groups and the questions worth your word (answer with a button; the
sentence goes into the answers box, and your word wins), **Open as one**
for the whole gathering in the world. What the browser put on this machine
it takes back from the same panel: **add** is a file picker whose pictures
are kept under `uploads/` as they were named, each kept picture (captured
or added) has a ✕ that forgets it, **Purge kept** forgets them all after
asking (never the folder's own pictures), and the cameras placed in the
world and the boards pinned to pieces are listed -- every site's, a pin
whose site or piece is gone marked as such -- each with the button that
takes it back. `GET/POST/DELETE /photos/pictures`, `POST /photos/gather`,
`/cameras` and `GET/DELETE /firmware/pins` are the routes underneath
(`apothecary/routes/pictures.py`, `apothecary/api.py`); the CLI below does
the same from a terminal.

`view` opens the existing viewer on what was built, where the pieces can be
walked into at any depth and filtered by the word each came from. Beside it sits
what is known about every piece — which finder saw it, how sure it was, whether
anything was measured — and the picture it came from.

`gather` takes in a whole folder at once and works out which photographs are of
the same thing, which are neighbouring parts of something bigger, which stand
alone, which could not be read at all, and which pairs it could not decide about.
Pictures of one thing become one set of pieces, and a piece two photographs agree
on says so. It gives you three things from the one command: a report in plain
sentences, a one-page picture of what went with what, and the whole lot in the
viewer.

On its own it finds about a fifth of the groups that are there, and on eight
hundred and thirty drawn pictures it has never made one out of photographs that
did not belong together. That trade is on purpose.

**And it is not meant to work on its own.** You are far better at this than it
is — you can see two photographs are of one bench in about a second, and could
not say how. It cannot, but it will compare nineteen thousand pairs without
getting bored, and it can work out which handful of questions are worth your
minute. So `--ask` writes those questions out, best first, saying what each one
is worth; you answer them in plain sentences; `--answers` hands them back. Your
word wins outright, it carries — one answer settles every pair that follows from
it — and because you were right, each answer also marks the machine's homework.
See [many photographs at once](features/gathering.md) and the proposed rule
[people and machines](proposals/people-and-machines.md).

`look` reports the flat shapes it found and what each would become. Nothing it
prints is a measurement — a picture on its own cannot say how big anything is.
`build` places the pieces; give it a real width and you get millimetres, leave it
out and every piece is marked as having no real size rather than being quietly
made up.

Four independent reviewers have been asked in turn to break it rather than
confirm it, and all four did. The first found three faults that would have ruined
the first real photograph — see
[how well the finder does](features/finder-accuracy.md). The second found
seventeen more, two of which let a person reach files the software was meant to
refuse. The third showed that the number this work's whole argument rests on had
been arrived at backwards. The fourth showed that three of the promises made
about sorting photographs were false as written, and that most of the tests
guarding it would have passed with the code broken. Everything they found is
fixed, each with a test that fails without the fix, and every corrected claim is
written down beside the one it replaced rather than quietly swapped.

The shape finding is plain and openly imperfect: it shrinks the picture, splits
light from dark, gathers touching pixels, and guesses each blob from how much of
its box it fills. It will be beaten by anything trained on real pictures. It also
runs on your own machine with the network switched off, which is the trade being
made on purpose.

## Seeing it work

    uv run apothecary test run        # the walkthrough runs as part of the suite
    apothecary docs generate

`walkthrough/11-photographs-into-pieces.md` is the page to read first, and every
example in it is executed by the suite — the output shown is the output that
ran, so a behaviour that changes fails the build rather than leaving a page
describing something that stopped being true.

`docs generate` runs the whole path in a real browser and writes a walkthrough
from what happened: nine steps, nine screenshots, and the recording of the run
itself. If the run goes red nothing is published. The picture of which
photographs went together is written the same way — out of the same run as the
assertions beside it, never by a separate demonstration harness.

Everything checks out together — the ordinary checks and the browser ones in one
run, 697 of them, none failing. Getting there needed three things fetched onto
the machine first, and a fault of our own making: one piece of setup could switch
the entire browser half off while the run still reported success. Both are
written up in [Evidence](EVIDENCE.md), and there is now a check that refuses to
let it happen again.

## Reading further

| Page | Who it is for |
|---|---|
| [Review for a person](HIL-REVIEW.md) | **You, deciding what to do with this.** What to look at, what only you can settle, and what to distrust |
| [What changed in the rules](GOVERNANCE-REFRESH.md) | Anyone. The rulebook moved a long way; what that cost this work and what is left |
| [Orientation](ORIENTATION.md) | Anyone. What the organisation's rules are and where this work touches them |
| [Handoff](HANDOFF.md) | Whoever picks the work up next. How to start, what will trip you, what to do first |
| [Evidence](EVIDENCE.md) | Anyone checking rather than trusting. Every claim, marked as run, read, or guessed, with how to re-check it |

Below those, one short page per change, per postponed idea, and per connection
between projects. Each says what it is, why now or why not yet, what it attaches
to, and what is still undecided.

| Page | Kind | State | Waits on |
|---|---|---|---|
| [Video frames into the same provider seam](edits/alfred.md) | change | stub | Photo → shapes → words → placed scenes → links |
| [Photo → shapes → words → placed scenes → links](edits/apothecary-model.md) | change | stub | nothing |
| [Twenty controls of its own become none](edits/apothecary-surface.md) | change | stub | rad is a unification engine — the foundational principle; Photo → shapes → words → placed scenes → links |
| [looksatphotos, looksatvideos, and what unknown means](edits/looksat-family.md) | change | stub | nothing |
| [Where a detector would run, if one is ever selected](edits/moat.md) | change | stub | Selecting a real detector |
| [Four org-level gaps this work exposes](edits/qm-main.md) | change | stub | The records this work eventually owes |
| [The records this work eventually owes](edits/qm-project-apothecary.md) | change | stub | Photo → shapes → words → placed scenes → links; Twenty controls of its own become none |
| [rad-android inherits the principle](edits/rad-android.md) | change | stub | rad is a unification engine — the foundational principle |
| [rad-menu carries the principle at its foundation](edits/rad-menu.md) | change | stub | rad is a unification engine — the foundational principle |
| [rad is a unification engine — the foundational principle](edits/rad-unification-principle.md) | change | drafted | nothing |
| [rad's conformance learns the nine cells](edits/rad-nine-cells-conformance.md) | change | drafted | rad's *The menu addresses nine cells* |
| [Many photographs at once, and which are of the same thing](features/gathering.md) | feature | built | Photo → shapes → words → placed scenes → links |
| [What can and cannot be chorded](features/chord-vocabulary.md) | postponed | stub | Twenty controls of its own become none |
| [Selecting a real detector](features/detector-selection.md) | postponed | stub | Photo → shapes → words → placed scenes → links |
| [Nothing survives a restart](features/persistence.md) | postponed | stub | Photo → shapes → words → placed scenes → links |
| [What a photograph contains that a scene does not](features/photo-privacy.md) | postponed | stub | nothing |
| [Wiring the revision graph to something](features/revision-graph-wiring.md) | postponed | stub | Twenty controls of its own become none |
| [Giving photo-derived geometry a scale](features/scale-references.md) | postponed | stub | Photo → shapes → words → placed scenes → links |
| [Externally authored scene documents are validated, never inferred](features/scene-document-validation.md) | postponed | stub | nothing |
| [Counting the controls, repeatably](features/surface-census-tooling.md) | feature | built | rad is a unification engine — the foundational principle |
| [Words that carry composition rules](features/word-grammar.md) | postponed | stub | Photo → shapes → words → placed scenes → links |
| [Fitting a word's parameters to a detected shape](features/word-parameters.md) | postponed | stub | Photo → shapes → words → placed scenes → links |
| [alfred frames as a Detection source](integration/alfred-frames.md) | connection | stub | Video frames into the same provider seam |
| [A looksat service as the third provider](integration/looksat-provider.md) | connection | stub | looksatphotos, looksatvideos, and what unknown means |
| [Deploying anything to the cluster](integration/moat-deployment.md) | connection | stub | Selecting a real detector |
| [The integration standard, host side](integration/rad-host-standard.md) | connection | stub | rad is a unification engine — the foundational principle; Twenty controls of its own become none |
