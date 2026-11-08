# Integrating the local stacks

*Dated 2026-11-07. How every local stack of apothecary's, cut from `main` at
1e12ec58, is finished, merged into one tree, tested once as a whole by
[the integration checklist](../integration-checklist.md), and landed on `main`.
Nothing here is pushed until the owner says so. Each fact below was read from
the branches that evening; each phase runs its command again before relying on
it. Plans are dated and exempt from the durable-text rule.*

## The stacks

Each is a line of branches, each cut from the one beneath, every commit signed:

```
main 1e12ec58
├─ testing      build/test-groups ─ build/stack-head-checks ─ build/picture-sheets
│               ─ build/integration-checklist ─ build/integration-plan (this plan)
├─ fixes        fix/identify-names-both
│               fix/vanished-port-lets-go
│               fix/ring-one-scan ─ fix/ring-reads-the-last-scan
├─ standardize  build/standardization-plan ─ build/state-folder-leaf ─ build/one-tool
│               ─ build/file-check-per-dialect ─ build/objection-per-dialect
│               ─ build/board-by-part ─ build/kind-from-dialect ─ build/retired-names-gone
│               ─ build/shims-gone ─ build/kept-file-kind ─ build/one-key-per-board
├─ homing       build/home-each-axis (not yet built)
├─ family       the plan ─ build/family-less-text ─ build/family-card-surfaces
│               ─ build/family-step-doors ─ the Procedure beside the world (open)
│               ─ the family as a focused system (open)
└─ streamdeck   build/stream-deck-plan ─ build/stream-deck-part ─ build/stream-deck-module
                ─ build/stream-deck-window ─ build/stream-deck-jogs (its fixups open)
                ─ the two classes of stop key (open)
```

What each makes true:

| Stack | Makes true |
|---|---|
| testing | the unit suite in groups, so the loop runs what a change reaches; CI on a pull request into `main`, a stack checked at its head; walkthrough pictures judged beside their commit; [the integration checklist](../integration-checklist.md); this plan |
| fixes | a board answering neither a printer's `M115` nor a router's `$I` is refused naming both; a board unplugged lets go of its link; the ring opens without waiting on a port scan |
| standardize | one way of doing each thing, the shims and the retired names gone (its plan, `docs/plans/standardization-2026-11-07.md` on its stack); one key per board |
| homing | each axis of each machine homed alone, from the pad and the ring |
| family | the viewer's family journeys: less text, controls that surface as they can act, a step and a member as doors, the Procedure beside the world, the family as a focused system (its plan, `docs/plans/family-journeys-2026-11-07.md` on its stack) |
| streamdeck | the Stream Deck + as a part on the bench, programmed from here, and a controller of the machines through the control latch (its plan, `docs/plans/stream-deck-2026-11-07.md` on its stack) |

The governance side is one commit in qm on qm#197's branch,
`adr/apothecary-stack-head`: the integrated-whole draft tests a stack once at its
head, CI follows, and its second decision names the integration checklist.

## Phase 0: finish what is open

Each stack's own session finishes its open slices on the stack, each a signed
commit whose test fails on the code beneath it:

- **family**: the Procedure beside the world (the owner: "Yes, beside the world");
  the family as a focused system, Members and Deliveries windows of their own (the
  owner: "Windows of their own").
- **streamdeck**: its fixups folded into the commits they fix; the two classes of
  stop key (the owner: "Two classes of estop. One for everything, one per machine").
- **homing**: built off `main` as its own stack (the owner: "Please ensure each axis
  on each machine can be homed independently").
- **fixes**: the integration checklist on the four branches merged together.
- **standardize**: the checklist on its top; the wheel step's failure, which failed
  alone, compared on the base and the top.
- **testing**: the two browser failures of its run named:
  `test_the_wheel_steps_within_a_site_and_never_to_another` and
  `test_one_poller_per_board_whatever_draws_it`.

The gate: every slice committed and signed, no working-tree change left in any
stack, each stack's own checklist recorded in its handoff.

## Phase 1: one integrated tree

The stacks merge in landing order into `scratch/integration-2026-11-07`, cut from
`main` at 1e12ec58, its merges unsigned, never pushed:

1. **testing**, first, so the stacks above it run under its triggers;
2. **fixes**, small, and what production needs soonest;
3. **standardize**, which the later stacks' firmware changes sit on;
4. **homing**;
5. **family**;
6. **streamdeck**, the newest and the most new page.

The conflicts `git merge-tree` found between the stacks' tops that evening:

| Where | Between | Resolution |
|---|---|---|
| `CHANGELOG.md`, `docs/README.md`, `README.md` | most pairs | the lines of both, in their sections and the map's order |
| `tests/test_census.py` | family and streamdeck | the counts recomputed as [the census](../census.md) says, never a bound loosened |
| `apothecary/firmware/gcode.py` | standardize and streamdeck | streamdeck's bounded extrude line where standardize puts Marlin's rules |
| `tests/groups.py` | testing and every stack adding a test file | each new test file named in its group |

A resolution is owed to the later stack in landing order, which takes it in Phase 3.

## Phase 2: the checklist on the tree

[The integration checklist](../integration-checklist.md), box by box, on the
integrated tree: the tests that list the repository's files; the unit tests and
the walkthrough; the browser suite as two shards run at once; each walkthrough
picture judged, its change named for the stack that made it; the docs every
stack touches read against each other; `apothecary census`; `apothecary
preflight`; each branch's signatures. A failure is owned by the stack whose top
fails it alone, and a timing failure is named with its run alone.

What only a person sees, gathered from the stacks, for the bench checklist:

- the router pinned by its bridge's make, found after a replug on another port;
- each axis homed alone on the Ender, and `$HX`, `$HY`, `$HZ` on the router, Z first;
- the Stream Deck + found, drawn, and its knobs jogging, its fourth knob extruding
  within its bound, its stop keys, arming by two long presses;
- Query on a board that answers neither, and the ring's opening, on production.

## Phase 3: owed fixes go home

Each stack rebases onto the top of the one before it in landing order, taking
what it owes, re-signing its commits, and rerunning the files its change reaches.
The tree is then one line: the last stack's top. `git diff` between it and the
integrated tree shows only what the merges resolved and the stacks took, and the
whole checklist runs once more on that top: a stack is tested at its head.

## Phase 4: landing, on the owner's word

The push is priced before it is made. With the testing stack's triggers, opening
the line as stacked pull requests costs the bottom's full set of runs and three
runs for each level above it; landing it as one merge of the top costs two runs
for each level retargeted, the head's set as it is marked ready, and the merge's
push to `main`: about two hundred runs, about seventy recorded job-minutes,
recomputed from the triggers and the recorded medians when asked. The qm commit
goes onto qm#197's branch, qm#211 takes it, and the pin moves in a level of its
own on the testing stack.

## Phase 5: after landing

Production moves to the new `main` on the owner's word, as it did for #136 to
#146. The bench checklist's rows from Phase 2 are the owner's to walk; a version
tag waits for that walk.
