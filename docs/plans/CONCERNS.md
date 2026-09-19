# Concerns for review

Everything the two new proposed rules leave unresolved, plus the older gaps they
touch. Each item is a decision for a person, not a task. Nothing here is settled.

Ordered by how much damage getting it wrong would do.

---

## About keeping everything on one machine

### 1. What counts as "your machine"?

The rule says data stays on the machine the software runs on. There is also a
small cluster of machines on a home network, owned outright, which already runs
several things.

Three readings, and they lead to different software:

- **Strictly the one machine.** Simplest to check, hardest to live with — no
  shared storage between a laptop and a workshop computer.
- **Any machine you own on your own network.** Matches how the cluster is already
  used. Harder to check, because "your own network" is a judgement.
- **The one machine for anything derived from a photograph; the network for
  everything else.** Splits the difference at the point where the risk actually
  is.

**Nothing can be built for storage until this is answered.** Recommend the
second, with photographs pinned to the first.

### 2. Is a one-time download allowed?

Almost anything that recognises shapes well is a trained model that has to be
fetched once, then runs locally forever after. Fetching it is a network use.
Running it is not.

If one-time fetching is not allowed, the practical ceiling on quality is a
hand-written detector — noticeably worse, and possibly good enough given that
poor performance is explicitly acceptable here.

**Recommend allowing it**, on the same terms as installing the software itself
(item 3), with the fetched thing openly licensed and kept.

### 3. Installing the software needs the network. Is that an exception?

Getting the program onto the machine in the first place requires downloading it
and the libraries it uses. Almost certainly an exception, but it should be stated
rather than assumed, because "with the network off it still works" is otherwise
false on a fresh machine and the rule looks broken on day one.

**Recommend:** the rule covers *using* the software, not *installing* it. Say so
in one sentence.

**Live example.** The shape finding needs a picture library, which is now listed
as something the software requires. Installing it needs the network once.
Everything after that runs with the network off, and there is a test proving it.

**Second live example, and a harder one.** Two further things had to be fetched
before the tests could all be run: one part of the parts library, which is kept
somewhere else and pulled down once, and the program that turns a design into a
printable file, which is installed from the operating system's own catalogue.
Both are one-time fetches and both run with the network off afterwards, so both
fit the recommendation above. What they show is that the recommendation is not a
corner case — a plain checkout on a plain machine cannot run its own tests until
three separate fetches have happened. Whatever is written should be written
knowing that.

### 4. Backups

If data only ever lives on one machine, one failed disk destroys the work. Any
backup is by definition a copy somewhere else.

**Recommend:** backups are the user's business, not the software's — the software
never sends anything anywhere, and where the user chooses to copy their own files
is not the software's decision. But this needs saying out loud, because "we keep
your data safe on one machine" is a promise that sounds better than it is.

### 5. The viewer loaded part of itself from a public website — **done**

Fixed, and it turned out to be far worse than untidy. **With no way out to the
internet, the viewer did not work at all**: the page loaded, the drawing code
never arrived, and it sat on "Loading site…" for ever. Nobody had noticed because
nobody had ever opened it on a machine without a route out. A browser test
running in a sandbox with no such route found it on its first run.

The four files the viewer imports are now kept beside the software and served
from it. About 1.3 MB, MIT licensed, with a note saying where they came from and
how to update them.

That leaves the general question open, though: the same decision arrives again
for the ring, and for anything else with a front end. The answer looks settled —
keep a copy — but it should be written down once rather than argued each time.

### 6. What happens when local-only makes something impossible?

The rule says it waits and the reason is written down. In practice someone will
be under pressure with a half-working local version and a working outside
service one click away.

**Recommend** deciding now, calmly, what the answer is: build it badly and
honestly, or do not build it. Both are defensible. Deciding under pressure is not.

### 7. Talking to the video editor breaks the rule

One of the planned connections has the parts tool asking the video editor for a
single frame of video. Two programs on one machine talking to each other is
arguably still local. Two programs on two machines is not.

**Needs a line drawn**, and it is the same line as item 1.

### 8. Running anything on the cluster is now questionable

There was a plan describing how a shape recogniser would be deployed to the home
cluster if one were ever chosen. Under the strictest reading of the rule, that
plan is dead. Under the second reading of item 1 it survives.

Marked as blocked on item 1 rather than deleted.

---

## About plain language

### 9. There is nobody to read aloud to

The real check for the plain-language rule is reading the page to someone who
does not do this work. With one person on the project, that person is not always
available.

**Options:** accept that the check happens in batches when someone is around;
find one willing outsider and treat their attention as a scarce resource; or
weaken the rule to self-review and admit it is weaker.

The rulebook elsewhere refuses to fake a check that needs a second person, so the
honest options are the first two.

### 10. Most existing documents have no plain front page

The rule says existing work gets one when it is next touched, rather than in a
sweep. That is realistic and it means the rule is mostly aspirational for a
while. Worth knowing rather than discovering later.

### 11. The word list will be misused

It is written as advisory and unable to pass or fail anything. Word lists get
turned into gates anyway, because a number is easier to act on than a judgement.

**Recommend** the list carry the warning in its own first line rather than only
in the rule that created it.

---

## Older gaps these two rules touch

### 12. There is still no rule about what information may leave

The local-only rule makes the question moot for this work, because nothing
leaves. It does not answer the question for any project that does send data
somewhere. That gap is still open at the top level.

### 13. The process has no name for the most ordinary act in it

Proposing a new decision to a project has no category in the list of five that
the rulebook says is complete. This has been worked around every time.

### 14. An automated check wanted credit given to an address no human reads

Declined, because the rulebook forbids it. It will recur on every future piece of
work until the check is changed or an exception is written.

### 15. "Show it by running it" has no answer for a run that ran nothing

The rulebook says a claim is shown by running it. It says nothing about a run
that goes green because the tests were switched off rather than because they
passed. That happened here: one fixture skipped, twenty-six browser tests skipped
behind it, and the run reported success. Nothing failed. It was found by reading,
not by any check.

The general shape of the problem is that a passing run reports what passed and
never what is missing. Three cheap answers exist and none is written down
anywhere:

- Record the expected number of tests and fail when the number drops.
- Refuse to call a run successful if anything skipped without a stated reason.
- Make skipping something only an individual test may do, never a fixture that
  others are built on — which is what was done here, in one project, by hand.

**Recommend** the third as a rule and the first as a check. Worth deciding at the
top level rather than once per project, because every project will meet it.

### 16. A fresh machine cannot run the tests

Three separate things must be fetched before a plain checkout can run its own
tests, and none of the three announces itself: the run just fails in ways that
read as broken code. One of those failures had been sitting in this project's
starting point already.

This is not a rule question, it is a missing sentence in the setup instructions,
and it is listed here because it cost real time to work out and will cost the
next person the same.

---

### 17. A green suite is not evidence that anything was checked

Concern 15 said a run can go green because the checks were switched off. This is
the sharper version of the same thing, and it was measured rather than feared: an
independent reviewer put twenty-seven deliberate faults into working code and
**twenty-four of them broke nothing**. The suite passed every time. One of the
survivors was the test named after the single most important refusal in the
module — it never called the function it was named after.

Nothing in the rulebook asks for this to be checked, and there is a cheap way to:
break the code on purpose and see which tests notice. It costs one run per fault
and it is the only thing that measures whether a suite is doing its job.

**Recommend** it as a rule for anything carrying a number that a decision rests
on, rather than for everything.

### 18. Nobody has decided whether guessing is the right default — **half done**

Sorting photographs into groups is guessing, carefully. It currently guesses and
tells you what it did. It could instead propose and wait to be told.

**The half that is settled and built:** a person's word now always wins, carries
through everything that follows from it, and is never overruled or averaged
with a machine's guess. There is a way to say things in plain sentences, a
scorecard showing how the machine did against what you said, and a list of the
questions worth your minute. That is the proposed rule
[people and machines](proposals/people-and-machines.md).

**The half still open:** whether it should guess *before* being asked. Both are
defensible. Guessing first and being told is faster when it is right; proposing
and waiting is calmer when it is wrong. It currently guesses.

### 19. There is nowhere to keep what a person said

Answers live in a file the person hands back each time. That is honest — nothing
is stored anywhere they did not choose — and slightly tiresome, and it means
nothing they said survives on its own.

It also means an answer never expires. If the photographs change, something said
about them may stop being true and nothing notices.

**Recommend** deciding this together with item 1, since where the answers live is
the same question as where anything lives.

### 20. Nobody has checked that the questions are worth answering

The machine ranks its questions by how many other pairs an answer would settle.
That is arithmetic and it is repeatable. Whether it is the *right* arithmetic —
whether those are the questions a person actually finds worth a minute — is an
argument and not a finding, and it needs somebody sitting down with a real folder
of photographs, which has not happened.

This is the sort of claim the rulebook says has to name its checker. Its checker
is a person with a folder, and there is no substitute.

## Questions worth answering before more is built

1. Item 1 — what counts as your machine? Everything about storage waits on it.
2. Item 2 — is a one-time download of an openly-licensed recogniser allowed?
3. Item 6 — what do we do when local-only makes something impossible?
4. Item 9 — who reads the plain pages aloud?
5. Item 18 — should sorting photographs guess, or propose and wait?
6. Item 19 — where should the things a person has said be kept?
