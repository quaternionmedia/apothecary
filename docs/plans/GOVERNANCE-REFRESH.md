# What changed in the rules, and what it costs this work

**Written for anyone.** The organisation's rulebook moved a long way while this
work was being built. This page says what moved, what it means for the work, what
has been done about it, and what is left. Nothing here is a decision — it is the
list of them.

**Read against:** qm `main` at `a5072a3` (2026-08-26) and qm `project/apothecary`
at `20e00bd` (2026-08-12), fetched and read in full.

## The shape of the gap, in three numbers

| | |
|---|---|
| What this project had pinned | `a6c7afb`, 2026-07-21 |
| What its own branch had already moved to | `20e00bd` — **124 changes ahead**, already agreed, never picked up |
| What the rulebook itself has become | `a5072a3` — **233 further changes**, not yet passed down to this project |

**Two separate things, and only one of them is ours.** Picking up the 124 costs
nothing and decides nothing: it is agreed work this project simply had not
collected. **That has been done.** Passing down the 233 is a job on the
organisation's side and a person's to start; nobody here can do it.

**So the five new rules below are not binding on this project yet.** They will
be. A project may be stricter than the rulebook and never looser, so the work has
been brought into line with them anyway, ahead of the pass-down. Where that was
not possible it is said so.

## Five new rules, and what each one costs

### The tool is never the check. It drafts the check; a person authors it.

This is the big one, and it very nearly says outright what this work had been
drafting as its own proposal. **So that proposal is withdrawn as a new rule** and
rewritten as a narrower thing: what the general rule looks like when the
undecidable judgement is *"are these two photographs of the same thing"*. Getting
that the wrong way round — offering the organisation a rule it already has,
under a different name — is exactly the kind of duplication the rulebook exists
to stop.

Three obligations come with it, and two of them found real faults here:

- **Every check terminates and returns a value.** Checked; they do.
- **A limit that fires is reported, never swallowed.** *It was not.* The sorting
  stops after the best sixty possible pairings between two crowded photographs,
  and said nothing when it did — so "did not look past sixty" and "there is no
  match" came out as the same sentence. The answer now carries a mark, and the
  report names it. This is the fault the rule is written to catch, found by
  reading the rule.
- **What cannot be decided is metered at one seam.** Nothing here calls a model
  or a service at all, and two checks read the source and refuse it if that ever
  changes.

### A check is evidence only after it has been seen to fail

Also very close to something this work had been arguing, and now settled at the
top. Two obligations:

- **Write the mutation down beside the guard.** Partly done — the breaking has
  been happening all along, but it was recorded in one central place rather than
  beside each guard. The newest files now carry the note where the guard is.
  Older ones do not yet.
- **A skip is not a pass, and a skip is about the machine, never the subject.**
  *Four skips here were about the subject* — "these two were not judged to be of
  the same thing, so never mind". Every one is now an assertion, which is what it
  should always have been: the sorting is repeatable, so either it holds or the
  test has stopped testing what it is named for.

### A person is interrupted only by a decision

The teeth are a count: each named job records how many things a person must type
to finish it, and **a rise without a reason is a regression**.

Built. `apothecary census` now reports both meters — the controls the viewer puts
on screen, and the steps a person types. **Eight named jobs, ten typed steps, and
seven of the eight carried by nothing but typing.**

### A change that can only be typed schedules interface work

The other half of the same rule: doing a needed thing by typing is a diagnosis,
not a delivery, and the act writes down an item naming the job.

Built, and it is uncomfortable reading — which is the point. Seven of eight jobs
here are carried by nothing but typing, and each is now listed as an open item.
The worst is answering the sorting's questions: three steps, of which the middle
one is a person reading and deciding and *should* exist, while the two around it
exist only because there is nowhere to be asked a question and answer it in the
same place.

### Every repository carries one walkthrough, and it runs

Built: `walkthrough/11-photographs-into-pieces.md`. Every example in it is
executed by the test runner and the output shown is the output that ran, so a
behaviour that changes fails the build rather than quietly leaving a page
describing something that stopped being true. It is named on the command line
rather than left to configuration, because a page nobody names does not run — and
there is a guard for that, watched failing.

This project is **named in the rulebook as a counter-example** for having inlined
a shared check instead of calling it, and for sitting seven revisions behind the
starting kit. That is a separate repair and is not done.

## What this work now owes, that it did not before

| Owed | State |
|---|---|
| Pick up the 124 agreed changes | **done** |
| Report the limit when it fires | **done** |
| Skips about the machine, never the subject | **done** |
| A typed-step count per job | **done** — `apothecary census` |
| An open item per job that only typing carries | **done** — seven of them |
| One walkthrough, executed | **done** |
| Withdraw the proposal the rulebook now covers | **done** — rewritten as a narrower rule |
| Mutation notes beside every guard, not only the new ones | part done |
| Say what this project's `v0.0.2` asserts | **not done** — see below |
| Pass the 233 changes down to this project | **not ours** — a person's, on the organisation's side |
| Stop inlining the shared check; catch up the starting kit | **not done** |

## The one the rulebook names this project for

The phase ladder says every rung above the first is defined by the project, in
the project's own records, and that a project which has not written that
definition "has not got a v0.0.2; it has a word". **This project claims v0.0.2
and has written no such definition.** It is named, by name, in that record's
consequences.

That is a record a person ratifies, not something to be settled here. What can be
said is what this work would put in it, and that is in the review checklist.

## What was checked, and what was not

**Checked by reading the rulebook in full**, both branches: the five new
principles, the new records, the branch namespaces, the walkthrough record, the
phase ladders, and the status documents.

**Not checked:** whether any of this passes the organisation's own gates. Those
run on the organisation's side, against its own repository, and nothing here can
run them. **Not checked either:** that the pass-down of the 233 changes would
apply cleanly — that is a real job with its own surprises, and guessing at it
from here would be worth nothing.

**Still open and unchanged:** the rulebook still has no name for the kind of
branch this work is on. The five it names are for the organisation's own work, a
project's records, a pass-down, a perspective, and a research dead end. Work in
progress inside a project heading toward a record is none of those. Practice has
invented two answers and blessed neither.
