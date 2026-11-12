# The tour

The walkthrough a step at a time inside the viewer, beside the live page: the help a
person takes through the app, and the way a person says whether the app does what
each step shows. [Walkthrough 34](../walkthrough/34-the-tour.md) goes through it,
written by the browser test that does it.

## Opening it

**⊞ Windows › Tour**, under Tools, or the canvas ring's **Panels › Windows › Tour**,
opens it: a stack of its own beside the world, closed until asked for, and open again
after a reload where it was, as any window a person opened is
([the viewer's windows](viewer.md#the-windows)).

Its first line, under the page's drop-down, says which step it shows and what to do
with it. Opened in a browser that has not taken it before, it starts at the first
step nobody has answered; after that, where this browser left it.

## What a step is

Each page under `walkthrough/` is a stop, in their order. A page a test writes --
its *Written by* line names the test -- is read back into its numbered steps: each
step's heading, its words, the picture the run took after the step's assertions
passed, and what it showed. The tour shows those and nothing written beside them, so
what a person checks is what a test asserted
([one executable walkthrough](../governance/qm/records/DRAFT-one-executable-walkthrough.md)).

The words say what a person does in the page beside the window; the picture is what
the page did when its test did it. A click on the picture opens it whole in a tab of
its own, and **its page**, at the window's foot, opens the walkthrough page.

A page written by hand, whose checks run with the ordinary test command, is one step:
its first words, and its link to read it whole.

## Saying what a step does

- **✓ As shown**: the page here does what the step shows.
- **✗ Off**: it does not, with what is off typed in the box above the buttons. Off
  with the box empty is refused, the window saying so and staying on the step.

Either is kept on the server, and the window goes to the next step. **‹ Back** and
**Next ›** move without saying anything; a step answered shows what was said of it,
when, and against which commit.

A word is a line of `tour/verdicts.jsonl` under the state folder
(`APOTHECARY_STATE_DIR`, [configuration](configuration.md#apothecary_-variables)): the
page, the step (0 for a page read whole), the verdict, what is off, the moment, and the
commit the server ran, with whether its tree had changes beside it. A line is never rewritten; the latest for a step is its answer.
Where a person is in the tour is this browser's alone (`apothecary.tour` in its local
storage); what they said is the server's.

## Reading it back

```sh
uv run apothecary tour            # every page: its steps as shown, off, and not yet
uv run apothecary tour --off      # only what is off, with what was said
uv run apothecary tour --page 31  # one page, by its number or its file name
```

`GET /tour` is the whole tour as the window reads it, each step's answer beside it;
`POST /tour/verdicts` keeps one word (`{page, step, verdict, note}`), refusing a page
that is not there (404), and a step it does not have, a verdict that is neither, or
Off with nothing said (422).

## The ring

Panels › Windows › Tour is the window, then its buttons: Back, As shown, Off (with
what the window's box says), Next, Its page and Its picture. It is seated after the
views, so no cell before it moves.

## What it does not do

- It does not set the page up for a step. The words say what to do; each page's own
  test is what does it, against a server of its own.
- A word is said against the commit the server runs. A page's pictures are of the run
  that last wrote them, rewritten by the browser suite (`apothecary test all`); a step
  said off against a commit whose pictures are older is checked against the page's
  run again before it is fixed.
- Nothing leaves the machine: the verdicts are under the state folder, and the server
  answers this machine only.
