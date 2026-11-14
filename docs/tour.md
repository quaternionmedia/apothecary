# The tour

What apothecary claims is built, a stop at a time, in a box over the page: the way a
person finds their way through the app, and the way a person says whether it does what
it claims. [Walkthrough 34](../walkthrough/34-the-tour.md) goes through it, written by
the browser test that does it.

## What it takes, and in what order

[The roadmap](ROADMAP.md) orders it. Each of the roadmap's lines is a claim, and names
what shows it:

- **a journey** (`journey:<id>`, [the viewer's journeys](viewer.md#journeys)): its
  stages are the tour's stops, and the page is put on each;
- **walkthrough pages**, by their links: each page is one stop, read and not put on.

The tour takes the lines in the roadmap's order, a part designed before a thing made
and photographs last. A line that names neither a journey nor a page is *shown by
nothing*, and the box and `apothecary tour` say so in those words.

The box has no words of its own. A stage's line is the one its journey's rail shows; a
page's are its own first words; and under either are the steps the page's test
recorded, each a link to the picture the run took after the step's assertions passed
([one executable walkthrough](../governance/qm/records/DRAFT-one-executable-walkthrough.md)).
A stage names the recorded steps that check it (`shown_by`, in
`apothecary/journeys.py`): they are what to try there.

## Opening it

**Tour**, in the header, or the canvas ring's **Panels › Windows › Tour › Tour**. The box
opens above the windows, so a view or a journey laid out moves them and not it. It is
dragged by its head, folded to its head by a double-click there, and closed by its ✕
or by Tour again. Where it stands, whether it is open and the stop it shows are this
browser's (`apothecary.tour` in its local storage), so a reload opens it where it was.

Opened in a browser that has not taken it before, it starts at the first stop of a
ticked line nobody has said anything of.

## A stage, put on

On a stage the box has **Put the page here**, and going to a stage -- by its number
among the line's stops, Next, Back, or a word said on the one before -- presses it.
The page then does what a person would do to get there:

- the machine the journey is staged on is opened, and its piece chosen
  (`staged_on`, in `apothecary/journeys.py`: for Make a thing, printer_1 and the
  footpedal);
- the journey is entered at the stage, its windows laid out and its rail in the
  header;
- where the stage needs the work of the one before it, that is done first: See draws
  a file's path, so with no file kept the piece is sliced for the machine, as Slice
  does.

The box says what it did, then what the page said of the stage. The stage is there to
explore.

**Only on the demo.** Putting a stage on acts on machines and state, so it happens only
where the server says it is `apothecary serve --demo`. Anywhere else the box shows the
stage and says to do what it says in the page.

**Nothing is armed or started.** Print's stage brings the Machine and Jobs forward;
arming control and starting a print are a person's, on the demo too.

Moving the rail in the page moves the box to that stage, and puts nothing on.

## A page, shown

A page's stop gives its first words, its recorded steps where a test writes it, and
**its page**, the page whole in a tab. It is shown only: a page's states are reached
by its test, some by answers the test fakes, and the box does not put the page on
them.

## Saying how a stop is

- **✓ As shown**: the page here does what the stop shows.
- **✗ Off**: it does not, with what is off typed in the field above the buttons. Off
  with the field empty is refused, the box saying so and staying on the stop.

Either is kept on the server, and the box goes to the next stop. A stop answered wears
its answer among the line's stops, and the box says what was said of it, when, and
against which commit.

An answer is a line of `tour/answers.jsonl` under the state folder
(`APOTHECARY_STATE_DIR`, [configuration](configuration.md#apothecary_-variables)): the
stop (`journey:make/slice`, `page:31-what-the-router-needs.md`), the answer, what is
off, the moment, and the commit the server ran, with whether its tree had changes
beside it. A line is never rewritten; the latest for a stop is its answer. Answers are
kept beside the roadmap and never written into it: a ticked line is the claim, and
what a person said is what was found.

## Reading it back

```sh
uv run apothecary tour            # every line of the roadmap: its stops as shown, off, and not yet
uv run apothecary tour --off      # only what is off, with what was said
```

`GET /tour` is the whole tour as the box reads it: the roadmap's lines in order, each
with its stops and each stop's answer, and any walkthrough page no line names.
`POST /tour/answers` keeps one word (`{stop, verdict, note}`), refusing a stop the
roadmap does not have (404), and a verdict that is neither or Off with nothing said
(422).

## The ring

Panels › Windows › Tour is the box, then its buttons: Tour (open or closed), Back, As
shown, Off (with what the box's field says), Next, Its page and Put here. It is seated
after the views, so no cell before it moves.

## What it does not do

- It does not put the page on a page's stop, only on a journey's stage; and Make a
  thing is the one journey there is.
- It does not arm, start or spend anything.
- An answer is said against the commit the server runs. A page's pictures are of the
  run that last wrote them, rewritten by the browser suite (`apothecary test all`).
- Nothing leaves the machine: the answers are under the state folder, and the server
  answers this machine only.
