# Review for a person — photographs into pieces

**Transient.** Written to be deleted when its work lands. Nothing here is a
decision; it is a list of the decisions waiting for one.

| | |
|---|---|
| **What this covers** | one branch in apothecary, one squashed commit, and the governance refresh that preceded it |
| **What it is for** | a person deciding what to do with it |
| **What it is not** | a claim that the work is correct. **Every item names what to look at, not what to conclude** |

---

## 0. Read this first

**Nothing here has been ratified, and nothing has been pushed.** The branch
cannot be pushed from the session that wrote it — the credential is not issued
for this repository — and under the async contract delivery is a pull request a
person opens. So the deliverable is a patch, and applying it is the first
decision.

**No organisation-side check has been run against any of this.** Those gates run
in the organisation's own repository. Every green reported below is this
project's own suite, run on this machine.

**The rules this work was brought into line with are not binding on this project
yet.** They live on the organisation's `main`; this project's branch is 233
changes behind them. Complying early is allowed — stricter is always allowed —
but do not read the compliance below as *required* compliance. See
`GOVERNANCE-REFRESH.md`.

---

## 1. The five minutes that are worth more than the rest of this page

- [ ] **Run it on your own photographs.** Nothing below replaces this. Twenty
      pictures of one workbench from different angles is the case it was built
      for and the case it has never seen.

      ```
      apothecary photo gather ~/pictures --ask questions.txt
      # answer some of them
      apothecary photo gather ~/pictures --answers questions.txt --map-to went.html --view
      ```

- [ ] **Answer three of its questions and see whether they were worth
      answering.** This is the one claim nothing here can check. The machine
      ranks its questions by how many other pairs an answer would settle; that
      the ranking is *arithmetically* right is tested, and that it is the *right
      arithmetic* is an argument. Its checker is you with a real folder.

- [ ] **Look at what it declines.** It refuses about seven pairs in ten. Decide
      whether that is a tool being careful or a tool being useless — the numbers
      cannot tell you, because they were measured on pictures it drew itself.

---

## 2. The checklist

Tick what you have actually done. **An unticked line is not a failure; it is a
known gap, which is the only kind worth having.**

### The work itself

- [ ] **Apply the patch and run everything.** `git am` onto `f1c1543`, then the
      three fetches named in `HANDOFF.md` §3, then the suite. It should say 697
      passing and two skipped. **A smaller number means something was switched
      off rather than passing.**

- [ ] **Read `walkthrough/11-photographs-into-pieces.md` as a stranger would.**
      It is the demonstration, it executes, and it is the page a newcomer meets.
      If it does not survive being read aloud, that is a finding.

- [ ] **Look at the screenshot in `docs/generated/gathering/`.** It came out of
      the same run as the assertions beside it. Check that what it shows matches
      what the report says — that is the only comparison anybody makes of it,
      and it is deliberately not automated.

- [ ] **Decide whether "a fifth of the groups, and never a wrong one" is the
      right trade.** It is the load-bearing choice in the whole feature and it
      was made without you. The other trade — more groups found, each confirmed
      by a person — is equally defensible and was not built.

- [ ] **Run `apothecary census` and look at the second half.** Seven of eight
      jobs are carried by nothing but typing. Each is an open item about where
      the interface stops. Decide which, if any, is worth building.

### What only you can settle

- [ ] **What counts as "your machine"?** Everything about storage waits on it.
      Concerns 1, 7 and 8 all resolve the moment this does, and none of them
      before. **No check will ever answer this.**

- [ ] **Is a one-time download of an openly-licensed recogniser allowed?** The
      practical ceiling on how good the shape-finding gets is on the other side
      of this question.

- [ ] **Should the sorting guess before being asked, or propose and wait?**
      Concern 18. It currently guesses and says so.

- [ ] **Where should the things you have told it live?** Concern 19. Today they
      live in a file you hand back each time, which is honest, tiresome, and
      means nothing survives a restart.

- [ ] **Who reads the plain pages aloud?** Concern 9. The rulebook refuses to
      fake a check that needs a second person, and this is one.

### The governance refresh

- [ ] **Bump the submodule pin, or decide not to.** The patch moves it 124
      changes forward, to this project's own branch tip. That work was already
      agreed; the project had simply not collected it. **Check the pin is what
      you expect** — `git -C governance/qm log --oneline -1` should say
      `20e00bd`.

- [ ] **Decide who opens the pass-down.** 233 changes sit on the organisation's
      `main` and have not reached this project. Nothing in this session can do
      it, and until somebody does, the five new principles bind this project
      only by its own choice.

- [ ] **Write what this project's `v0.0.2` asserts, or drop the claim.** The
      phase ladder names this project, by name, as claiming a rung it has never
      defined — "has not got a v0.0.2; it has a word". One record settles it.
      **This is a record a person ratifies. An assistant may draft it and does
      not ratify it.**

- [ ] **Decide what namespace this branch should have been on.** It is on
      `evolve/*`, which the rulebook defines as the *organisation's* work in
      progress. There is no defined namespace for a project's work in progress,
      practice has invented two, and neither is blessed. This is the same gap
      that was reported the first time and is still open.

---

## 3. What went wrong, so you know what to distrust

Four reviewers were asked to break this work and all four did. In order of how
much it should change your reading:

1. **Two of the three promises made about working with a person were false when
   written.** "Your word wins" did not — a machine's guess was allowed to destroy
   a group a person had built, while the report said "your word was taken as it
   stands" in the same breath. Both fixed, both with a test watched failing.

2. **The number the whole unification argument rests on was arrived at
   backwards.** It said twelve; twelve was a hand tally, and the counter written
   to make it repeatable had been built until it agreed. Rebuilt against a rule
   written first, it says twenty.

3. **A claim that no group had ever mixed unrelated photographs was true of the
   three seeds the test used and false on thirteen of twenty-five.** The tests
   now separate the seeds used for tuning from the seeds used as evidence.

4. **Most of the tests would have passed with the code broken.** Twenty-four of
   twenty-seven injected faults were caught by nothing, including a test named
   after the central refusal that never called the function it was named for.

**What that pattern should tell you:** every number in these documents that has
not been re-derived by somebody else is a number to distrust. The ones that have
been are marked in `EVIDENCE.md`, graded as run, read, or guessed.

---

## 4. What a check found that nobody was looking for

- **The viewer did not work at all without a route to the internet.** It fetched
  its drawing library from a public website; on a machine with no way out it sat
  on "Loading site…" for ever. Recorded as untidiness for a long time. A browser
  test found it on its first run.

- **A limit was firing silently.** The sorting stops after the best sixty
  pairings between two crowded photographs and said nothing when it did, so "did
  not look that far" and "there is no match" came out identical. Found by reading
  a rule, not by any test.

- **Three separate things must be fetched before a plain checkout can run its own
  tests**, and one of those failures was already present in the starting point.

---

## 5. Two things nobody has looked at

- **Fourteen browser tests that used to fail together.** They pass now, and the
  explanation given for the old failure was wrong twice before it was right. The
  current explanation — a missing program and a fixture of mine — is consistent
  with everything observed, and has not been challenged by anybody but me.

- **Whether any of this survives a real photograph.** Every number was measured
  on pictures the tool drew itself: no shadow, no texture, no blur, nothing
  overlapping. A good showing there means "handles the easy case", and that is
  the whole of what has been established.
