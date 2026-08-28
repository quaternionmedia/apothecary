# Handoff — photographs into pieces

**Stamped 2026-08-28.** apothecary at `00dbf99` (one commit on
`evolve/photo-shapes-and-light-language`, base `f1c1543`), governance pinned at
`20e00bd`, read against qm `main` at `a5072a3`. **Every figure below was true at
those commits and nowhere else.** Re-derive before quoting one — the commands are
given beside each.

**This is not the entry point.** `README.md` in this folder is the way in;
`HIL-REVIEW.md` is what a person deciding about this work should read.

---

## The one-paragraph version

The picture path is built, measured, and has survived four adversarial reviews.
Nothing is ratified, nothing is pushed, and **the interface work has not
started** — that is the whole of what is left of the original plan, and it is the
larger half. The two things blocking anybody else picking this up are neither
technical: a person has to open the pull request, and a person has to answer six
questions that no check can answer. Everything else on this page is detail.

## State

| | |
|---|---|
| apothecary | `00dbf99`, working tree clean, **never pushed** |
| Base | `f1c1543` on `main` |
| Governance pin | `20e00bd` — this project's own branch tip, moved forward 124 changes this session |
| Governance not yet passed down | **233 changes** on qm `main`; five new principles among them |
| Tests | **712 passing, 2 skipped** — `APOTHECARY_PICTURE_ROOT=/tmp/pics uv run pytest tests walkthrough -q --doctest-glob='*.md'` |
| Records this project has ratified | **none.** Two drafts, both `Proposed` |
| rad | `evolve/rad-unification-principle` at `30b3b6d`, also never pushed |

## Before your first command

A plain checkout **cannot run its own tests**, and each of the three failures
reads like broken code rather than missing setup. One of them was already
failing in the starting point.

    git submodule update --init --recursive     # part of the parts library lives elsewhere
    apt-get install -y openscad                 # turns a design into a printable file
    uv sync

Then, everything in one go:

    mkdir -p /tmp/pics
    APOTHECARY_PICTURE_ROOT=/tmp/pics uv run apothecary serve --port 8765 &
    APOTHECARY_PICTURE_ROOT=/tmp/pics uv run pytest tests walkthrough -q --doctest-glob='*.md'

**712 and 2 skipped.** A smaller number means something is switched off rather
than passing — that has happened here, twice, and both times the run was green.

## What exists

**The picture path.** A photograph is read into flat shapes, each shape gets a
name from a five-word vocabulary, the pieces are placed with or without a
real-world size, and the whole thing is an ordinary arrangement the existing
viewer already knows how to show. Two finders behind one seam. A harness that
measures a finder against known answers.

**Sorting many photographs at once** — `apothecary/gathering/`, 11 modules. Which
are of the same thing, which are neighbouring parts of one larger thing, which
stand alone, which could not be read, and which pairs it cannot decide. Measured:
about **a fifth of the groups that are there, and never one built out of
photographs that did not belong together**, across 32 folders of 27 drawn
pictures, 17 of which were never used while choosing the thresholds.

**Working with a person** — `judgement.py`, `questions.py`. Five plain sentences
a person types; their word wins outright, carries to everything that follows,
and scores the machine. The machine's half is arithmetic: no model, no service,
no network, no randomness, and four tests read the source and refuse it if that
changes.

**Two meters.** `apothecary census` counts the controls the viewer puts on screen
(**20**, and unifying takes that to nothing) and the steps a person types per
named job (**10 across 8 jobs, 7 of them carried by nothing but typing**).

**One walkthrough that runs** — `walkthrough/01-photographs-into-pieces.md`,
executed by the suite, named on the command line with a guard for that.

## What does not exist

Any change to the viewer. Links between arrangements (`links.py` was planned and
never written). The ring itself. Any pushed branch, any ratified record, any
selected detector. Anything that survives a restart.

---

## Traps, in the order you will hit them

**1. Delivery is a pull request a person opens.** The branch cannot be pushed
from an assistant session — the proxy returns `403, not in this session's
authorized repository set`, verified by dry run. And `handbook/async-contract.md`
§7 says local-only is a standing state that overrides delivery. A stop hook will
tell you to push four times; it is wrong four times.

**2. Git will stamp the committer with a vendor address.** Human-only
contributorship forbids it. Every commit here sets both author and committer
explicitly. `git config user.email` for this repo fixes it once.

**3. This project's records are not in this project.** They live on qm's
`project/apothecary` branch. A pull request into that branch may touch `adr/` and
nothing else, and a `project/*` branch is never the *head* of a PR.

**4. There is no namespace for the branch you are on.** The rulebook names five;
none is "a project's work in progress heading toward a record". This branch uses
the organisation's own namespace because there is nothing better. Practice has
invented two answers and blessed neither. **Ask; do not guess.**

**5. Drafts have no memory.** Before ratification, rewrite a record whole as
though you always thought that. The change history is the record of how the
thinking moved.

**6. A skip is not a pass, and a skip is about the machine — never the subject.**
Four skips here were about the subject and are now assertions. If you write
`pytest.skip("it did not happen to do the thing")`, you have written a green
test that checks nothing.

**7. A check is evidence only after it has been seen to fail.** Break the thing
it protects, watch it go red, put it back, and **write the mutation down beside
the guard**. The newest files here do; older ones record it centrally in
`EVIDENCE.md` instead. That gap is real and small.

**8. A bound that fires must be reported.** One here was silent — the sorting
stops after the best sixty pairings and said nothing, so "did not look that far"
and "no match" were one sentence. Fixed. Look for the others.

**9. Nothing is ratified anywhere, including upstream.** Ratification needs a
second code owner and there is one person. Do not wait for it and do not fake it.

---

## What to do next, in priority order

**1. Open the pull request.** Everything else waits on it. `git am` the patch
onto `f1c1543`, check the governance pin says `20e00bd`, open it into `main`.

**2. Answer the six questions in `HIL-REVIEW.md` §2.** Four of them block
building anything about storage. No check will ever answer them.

**3. Write what this project's `v0.0.2` asserts.** The phase ladder names this
project, by name, for claiming a rung it has never defined — "has not got a
v0.0.2; it has a word". One record on `project/apothecary` settles it. An
assistant drafts; a person ratifies.

**4. Start the interface work, or say it is not happening.** Seven of eight jobs
are carried by nothing but typing, and each is an open item under the rule that
a change which can only be typed schedules interface work. The most valuable one
is answering the sorting's questions: today a file is carried out and back by
hand because there is nowhere to be asked a question and answer it in the same
place.

**5. Propagate the 233 changes.** Org-side, a person's, and until it happens the
five new principles bind this project only by its own choice.

**6. The rest of the original plan.** `links.py`, the migration that deletes the
old viewer controls, the `unification` topic entry in rad's tests, and the six
records owed on `project/apothecary`. All described in the stubs under
`edits/` and `features/`.

---

## Hard stops

- **Do not push.** See trap 1.
- **Do not add a co-author trailer naming an address no human reads**, and check
  the committer as well as the author.
- **Do not ratify anything.** A human ratifies; you draft.
- **Do not create a repository to fill a gap.** An empty repo reads as an adopted
  project to the org's own status tooling.
- **Do not put a model, a service, or a network call anywhere in
  `apothecary/gathering/`, `vision/` or `vocabulary/`.** Four tests refuse it,
  and the reason is in `proposals/people-and-machines.md` — the promises made
  about a person's word only mean something against something repeatable.
- **Do not quote a number from these pages without re-deriving it.** Four
  reviewers found four wrong ones, including the number the whole unification
  argument rested on.

## What was corrected, and what that should tell you

Across this session, four independent reviewers were asked to break the work.
Everything below was written down as fact and was false:

| Claimed | Actually |
|---|---|
| Twelve ways into the viewer | Twenty. The hand tally was wrong and the counter was built until it agreed with it |
| Fourteen browser tests fail from a shared server | Three unrelated causes, one of them a fixture that switched the whole browser suite off |
| No group ever mixed unrelated photographs | True of three seeds, false on thirteen of twenty-five |
| A person's word wins | A machine's guess could destroy a group a person built |
| The same gathering always gives the same answer | Handing one folder in nine orders gave five answers |

And twice, most of the tests would have passed with the code broken —
twenty-four of twenty-seven injected faults caught by nothing.

**The pattern is the finding.** Reading produces claims about shape and misses
claims about behaviour. Everything in `EVIDENCE.md` is graded run, read, or
guessed for that reason. Anything not re-derived by somebody else is worth
distrusting.

## Where the reasoning lives

| Page | What it is for |
|---|---|
| [`README.md`](README.md) | The way in. Plain, for anyone |
| [`HIL-REVIEW.md`](HIL-REVIEW.md) | A person deciding what to do with this |
| [`GOVERNANCE-REFRESH.md`](GOVERNANCE-REFRESH.md) | What the rulebook's 233 changes cost this work |
| [`EVIDENCE.md`](EVIDENCE.md) | Every claim, graded, with how to re-check it |
| [`CONCERNS.md`](CONCERNS.md) | Twenty items needing a person; six block building |
| [`ORIENTATION.md`](ORIENTATION.md) | The organisation's rules, in plain language |
| `features/`, `edits/`, `integration/` | One short page per change, postponed idea, and connection |
| `walkthrough/01-photographs-into-pieces.md` | The demonstration. It runs |
