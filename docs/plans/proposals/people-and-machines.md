# People and machines each do what they are good at — this project's instance

**Start here. This page is for anyone.**

## Withdrawn as a new rule, kept as a narrower one

This began as a proposal for a rule the organisation did not have. **It has one
now**, and it is sharper than this was: *a model is a black box with no halting
guarantee, so it is never the check — it drafts the check, and a person authors
it.* Said plainly in its own words: **work yourself out of the jobs you are not
good at, playing to your strengths.**

So the general claim here is withdrawn. Offering the organisation a rule it
already holds, under a different name, is duplication of exactly the kind its
own rules exist to prevent.

**What is left is worth keeping**, and it is narrower: what that rule looks like
when the undecidable judgement is *"are these two photographs of the same
thing"*. A project may be stricter than the rulebook and never looser, so this
stands as a tightening — it adds three obligations the general rule does not
state, and it is those three that are being proposed:

1. **A person's word carries.** The general rule says the person authors the
   check. This adds that one answer settles everything that follows from it, and
   that a person is never asked twice for the same fact.
2. **The machine works out what is worth asking.** Not merely "the tool drafts";
   the tool also computes, for each question, how much of the remaining doubt an
   answer would settle, and asks in that order.
3. **Every answer scores the machine.** An answer is a case where the truth is
   known, so helping and checking are the same act, and the scorecard is shown
   without being asked for.

The rest of this page is that instance, and where it says "the machine" it means
the arithmetic in `apothecary/gathering/`, which is not a model and is checked
not to become one.

## The rule, in one paragraph

Where a machine and a person are both able to judge something, the software does
not choose between them. It gives each the part they are better at: the machine
counts, compares, remembers and works out **which question is worth asking**; the
person answers. A person's answer is taken as it stands — never overruled, never
averaged with a machine's guess, never quietly downgraded to a suggestion. And
because a person's answer is a case where the answer is known, every one of them
also scores the machine, so helping and checking are the same act.

## Why this rule and not "check the machine's work"

Checking is what you do to a thing that is mostly right. This machine is not
mostly right. On its own it finds about a fifth of the groups of photographs that
are actually there. A person glancing at two photographs gets nearly all of them,
in about a second, and could not tell you how.

But a person will not look at nineteen thousand pairs, and the machine will,
without getting bored or changing its mind. Neither of them can do this alone.
Calling it "review" gets the relationship backwards and makes the person a rubber
stamp for arithmetic they cannot see.

## What each is better at

| A person is better at | The machine is better at |
|---|---|
| Knowing at a glance that two photographs are of one thing | Comparing every pair of two hundred photographs |
| Knowing a photograph is useless — a thumb, a floor, a blur | Giving the same answer today as last week |
| Saying how big something really is | Saying how sure it is, and never rounding that up |
| Saying what a thing is called | Remembering what it was told and following it through |
| Being right without being able to say why | Working out which single question is worth asking next |
| Judgement | Arithmetic |

The right-hand column is not the impressive one and that is rather the point. The
machine's job here is to be tireless, consistent and honest about its own doubt —
and then to get out of the way.

## The machine's half is arithmetic, deliberately

There is a tempting shortcut here: hand the two photographs to something that has
seen a great many photographs and ask it what it thinks. That is not what this
does, and the rule says so, because the shortcut breaks every promise the rule
makes.

- **A person's word has to win, so the other side has to be a thing you can
  overrule.** Overruling arithmetic is a fact. Overruling something that answers
  differently on two Tuesdays is an argument you cannot win or lose.
- **A question has to be worth asking, and worth is a number.** "How many other
  pairs would this settle" is counted. Asked of something that guesses, it
  becomes a guess about a guess, and the number on the page stops meaning
  anything.
- **Every answer scores the machine.** That only works if the machine gives the
  same answer to the same question. Score something that drifts and you have
  measured the weather.
- **It has to say why.** Not a sentence that sounds like a reason — the actual
  reason, with the numbers that produced it, so a person can disagree with a
  step rather than with a verdict.
- **The photographs stay on the machine they are on.** Asking anything else
  means sending them somewhere, which the
  [local-only rule](runs-and-stays-local.md) forbids outright.

So the machine's half is counting, comparing and sorting, and nothing else. It is
worse at judging than the alternative would be. It is repeatable, cheap,
explainable, offline, and possible to be right about — and the judging is not its
job anyway. That is the trade, and it is the whole reason the arrangement works.

**Checked, not claimed.** Two tests read the source of the whole path from
photograph to group and refuse it if it reaches for a model, a service, or
anything over a network — and a third refuses it if it reaches for chance at
all. Two more hand the same photographs and the same answers in twice, and in
the other order, and compare the results exactly.

**And the general rule adds three obligations this page did not have**, all of
which found something:

- *Every check terminates and returns a value.* They do.
- *A limit that fires is reported, never swallowed.* **It was not.** The sorting
  stops after the best sixty possible pairings between two crowded photographs
  and said nothing when it did, so "did not look past sixty" and "there is no
  match" were the same sentence. Fixed: the answer carries a mark and the report
  names it.
- *What cannot be decided is metered at one seam.* Nothing here calls anything
  of the sort, which is the strongest form of compliance available and the one
  the tests enforce.

## The four parts of the rule

**1. A person's word wins.** Outright. No weighting, no confidence, no "the
machine is 94% sure so we will keep its answer". If somebody says two photographs
are of the same thing, they are, and everything downstream says who decided.

**2. A person's word carries.** One answer settles every pair that follows from
it. Saying two photographs are of one thing joins everything already joined to
either of them. A person should never be asked twice for the same fact, or asked
for something that follows from what they already said.

**3. The machine asks well, or does not ask.** A question put to a person costs
attention, which is the scarcest thing here. So the machine works out what each
question is worth — how many other pairs its answer would settle — and asks the
handful that are worth a minute, best first. Questions the machine could answer
itself are not asked. Questions with nothing to look at are not asked.

**4. Two people who disagree are refused, not averaged.** If the answers
contradict each other, nothing is merged and both are named. A machine deciding
which person was right is the one thing this rule exists to prevent.

## How you would know it was being followed

Not by reading the code. By these, which are things you can look at:

- **The output says who decided what.** Every group, every judgement, every piece
  says whether a person or the machine decided it. On the picture of what went
  with what, a join somebody made is drawn heavier than one the machine worked
  out.
- **There is a way to tell it something**, in sentences a person can type, that
  does not require knowing anything about how it works.
- **There is a scorecard**, and it is shown without being asked for: how many
  answers you have given, how often the machine had agreed, how often it had been
  wrong, how often it had had nothing to say.
- **Nothing a person wrote is ever rewritten.** The software adds to their file;
  it never tidies their words.

## What this costs

**It is slower.** Fully automatic is faster right up until it is confidently
wrong, and this whole approach is a bet that being confidently wrong is more
expensive than being slow.

**It only works if the questions are good.** Eight worthwhile questions is
cooperation. Two hundred questions is a machine offloading its job onto a person,
and it will be ignored by the second day. The number that each question is worth
is not decoration — it is what makes the difference visible.

**It needs somewhere to keep the answers.** Right now they live in a file the
person passes back each time, which is honest and slightly tiresome. Nothing
survives a restart on its own.

## Where it already applies

Sorting photographs into groups, which is where it was worked out —
see [many photographs at once](../features/gathering.md).

Three more places it obviously belongs, none of them built:

- **What something is called.** The tool guesses a name for each shape from a
  table. A person knows.
- **How big something is.** A photograph cannot say. A person can say "that beam
  is two and a half metres" and everything else follows from it.
- **Which photograph is the good one.** When several show the same thing, the
  machine picks the one with the most shapes in it. A person would pick the one
  in focus.

## What is not decided

- **Whether the machine should guess at all before being asked.** It currently
  guesses and says so. It could instead propose and wait. Both are defensible;
  this is [concern 18](../CONCERNS.md).
- **Whether this is a project record at all, or a note under the org's rule.**
  The three additions above may be general enough to belong upstairs, in which
  case this becomes a perspective arguing for them rather than a record. That is
  the organisation's call, not this project's.
- **Whether an answer should ever expire.** If the photographs change, an answer
  about them may stop being true, and nothing notices.
- **Whether one person's answers should carry to another person's folder.** Right
  now they do not, and nothing pretends otherwise.
