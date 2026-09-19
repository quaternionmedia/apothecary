# Many photographs at once, and which are of the same thing

| | |
|---|---|
| **Kind** | feature |
| **Repo** | quaternionmedia/apothecary |
| **State** | built — `apothecary photo gather`, `apothecary/gathering/`, 134 tests plus a meter |
| **Depends on** | Photo → shapes → words → placed scenes → links |
| **Graduates to** | a record on qm `project/apothecary`, once someone decides whether guessing at all is the right default |
| **Verified** | Measured on drawn pictures whose answers are known, over thirty-two folders of twenty-seven pictures each. Numbers below. Broken twice by independent reviewers; both rounds are recorded. |

## What

One picture at a time was the easy case and was already built. The real case is a
handful of photographs taken at different moments, from different distances, in
different light — some of the same object, some of neighbouring parts of one
larger thing, and some of nothing in particular.

    apothecary photo gather ~/pictures --map-to went-together.html --view

Three questions, kept firmly apart, because "resolved" means all three in
ordinary speech and they need different answers:

1. **Did this picture resolve on its own?** Was enough found in it, clearly
   enough, to be worth placing? A photograph of a blank wall did not.
2. **Do these two resolve to the same thing?** The same object from a different
   angle, distance or light. Their pieces become *one* set of pieces, and a piece
   seen in both says so.
3. **Do these two resolve into one larger thing?** Neighbouring parts sharing an
   edge. Their pieces sit side by side. They are **not** merged.

And a fourth answer that matters as much as the three: **cannot tell**. It is a
real answer, it is written down with a reason, and nothing is joined on it.

Three ways to look at the result, all from the one command: a report in plain
sentences, a one-page picture of which photographs went with which, and the whole
lot as an ordinary arrangement in the viewer that was already there.

## It is not meant to work on its own

The most important thing on this page is not a number. It is that **you are far
better at this than it is**, and the software is built around that rather than
around pretending otherwise.

    apothecary photo gather ~/pictures --ask questions.txt
    # answer them in the file, in plain sentences
    apothecary photo gather ~/pictures --answers questions.txt --view

You can see that two photographs are of one bench in about a second and could not
say how. The machine cannot do that at all. What it can do is compare nineteen
thousand pairs without getting bored, give the same answer next week, be honest
about its own doubt, and — the useful part — **work out which handful of
questions are worth your minute**, best first, with what each one is worth
written beside it.

Three promises about what you tell it:

- **Your word wins.** Outright. No weighting, no "the machine is fairly sure so
  we will keep its answer". Everything downstream says who decided.
- **Your word carries.** Saying two photographs are of one thing joins everything
  already joined to either of them. One sentence can settle a dozen pairs. You
  are never asked for something that follows from what you already said.
- **Your word marks the machine.** An answer is a case where the answer is known,
  so every one of them scores it — agreed, overruled, or had nothing to say. The
  report shows that without being asked. Helping and checking are the same act
  here.

And one about people: **two answers that contradict each other are refused, not
averaged.** A machine deciding which person was right is the thing this must
never do.

The whole language is five sentences, chosen so they can be read aloud:

    bench_from_the_left and bench_from_the_right are the same thing
    wall_left and wall_right are parts of one thing
    shed_door and kitchen_wall are not related
    my_thumb is not worth using
    very_dark_one is worth using anyway

**What it does, measured.** On the same nineteen drawn photographs, the machine
alone found 2 groups. Five sentences typed by hand took it to 5, and the map
draws the joins a person made heavier than the ones it worked out.

## The machine's half is arithmetic, on purpose

There is no model in any of this, nothing is asked of anything over a network,
and there is no randomness in the deciding path. That is deliberate, and it is
what makes the three promises above mean anything: you can overrule arithmetic,
you cannot overrule something that answers differently on two Tuesdays; a
question's worth is a number, and a number about a guess is a guess; an answer
only marks the machine if the machine would say the same thing tomorrow.

Checked rather than claimed — tests read this package's own source and refuse it
if it ever reaches for a model, a service, a network, or chance, and two more
hand the same photographs in twice and compare the results exactly. See
[people and machines](../proposals/people-and-machines.md).

## The trade being made, in one line

**On its own it finds about a fifth of the groups that are there. It has never
built one out of photographs that did not belong together.**

That is the deliberate choice. A tool that quietly makes an object out of two
unrelated photographs is worse than a tool that shrugs, because nothing further
down can tell the difference — the arrangement looks the same either way, and the
mistake only surfaces when something is printed and does not fit.

## How it decides

No trained model, nothing fetched, nothing sent. It compares what a photograph
looks like in ways that survive moving the camera:

- **What shapes are in it and what proportions they have.** Stepping back halves
  every size and leaves every proportion alone.
- **How the shapes sit relative to each other.** This is the one that does the
  work. If two photographs are of one thing, then one step-and-zoom should put
  every shared shape on top of its partner at once. A coincidence never does.
- **How light and dark the whole picture is.** Weak on its own — two pictures of
  different things in one room look alike this way — so it is only ever used to
  support an answer, never to reach one.
- **How distinctive the shared shapes are.** Three matching squares out of a pile
  of squares is not evidence. A picture where nearly every shape could stand in
  for nearly every shape in the other is refused rather than guessed at.

Every threshold is a named number with the measurement that chose it written
beside it, so each can be argued with.

## What was measured

Pictures are drawn into a made-up scene and then *photographed*: a camera window
is chosen inside the scene, so two pictures of one scene really differ by where
the camera stood, how close it was, and how bright the light was.

**Thirty-two folders, twenty-seven pictures each — eight hundred and thirty
pictures, near enough five thousand pairs.**

| | Groups found | Groups mixing unrelated pictures |
|---|---|---|
| Fifteen folders used while choosing the thresholds | 41 of 195 there to find | **0** |
| Seventeen folders never used for anything | 41 of 221 | **0** |

Pair by pair: never wrong on any seed tried, and 18% to 41% of pairs given an
answer rather than a shrug.

**How it got there**, because the numbers on their own read as though it worked
first time:

| | Groups found | Mixed |
|---|---|---|
| Matching shapes one at a time | — | joined 10 unrelated pairs in one folder |
| Adding the arrangement check | 67 | 9 |
| Requiring three shapes, not two | 62 | 5 |
| Refusing shapes too alike to tell apart | 41 | **0** |

## What it cannot do

- **Turning the camera is not covered.** A photograph taken with the camera on
  its side will be judged unrelated to the same scene taken upright.
- **Real photographs are not what any of this was measured on.** Everything drawn
  is clean: no shadow, no texture, no blur, nothing overlapping. A good score
  here means "handles the easy case".
- **It will be beaten by anything trained on real pictures.** It also runs on
  your own machine with the network off, which is the trade being made on
  purpose.
- **Two pictures of the same thing in very different light** are still judged on
  their shapes, so the light disagreeing is recorded as an argument against
  rather than a veto. That is a judgement call and it could be wrong.

## Seeing a piece twice does not make it certain

A piece two pictures agree on is better evidence than a piece one picture saw,
and nowhere near twice as good: the same finder, with the same weaknesses,
looking at one object twice makes the same mistake twice. So agreement closes
part of the gap to certainty and can never close all of it, and the sum is
written out where it can be argued with rather than buried.

## What two reviewers broke

Both were asked to break it rather than confirm it, and both did.

**The first round** found the whole idea was missing a signal: shapes matched one
at a time made two photographs of entirely different things look identical,
because both happened to hold a square, a disc and a triangle of about the same
proportions. That is where the arrangement check came from.

**The second round** found three claims that were plainly false:

- *"Nothing is merged on a maybe."* There was an exception in the rule for the
  case where every shape in both pictures was accounted for — and two pictures
  with one shape each meet it on a single match, with no arrangement to check.
  Two unrelated photographs came back as the same thing at full confidence.
- *"No group has ever mixed unrelated photographs."* True of the three seeds
  the test happened to use. On twenty-five, thirteen produced a mixed group. The
  table above is the corrected version.
- *"The same gathering always gives the same picture."* The fit measured its
  error in the second picture's frame, so it was stricter one way round than the
  other. One folder handed in nine different orders gave five different answers.

Plus: a report that said "held together at 100%" and "nothing was built" about
the same pictures in one run; parts laid side by side that all sat on top of each
other; two pieces silently sharing a name so one replaced the other; and a
picture's typical confidence being the upper of two rather than the middle, so
one certainty and one blank guess read as "typically completely sure".

All fixed, each with a test that fails without the fix — checked by putting each
fault back and watching the test go red.

The reviewer also found that **twenty-four of twenty-seven faults injected into
the code were caught by no test at all**, including the test named for the
module's central refusal, which never called the function it was named after.
That is fixed too, and it is the more useful finding: a passing suite says
nothing until somebody has tried to break it.

## Open questions

- Is guessing the right default at all? It currently guesses and says so; it
  could instead propose and wait for you. Both are defensible — concern 18.
- Nothing you say survives a restart on its own. The answers live in a file you
  hand back each time, which is honest and slightly tiresome.
- An answer never expires. If the photographs change, something you said about
  them may stop being true and nothing notices.
- A fifth is a lot to leave on the floor *before* you have said anything. The
  obvious way to lift it without your help is a trained model, which is concern
  2 and not decided — and would cost the explainability the whole arrangement
  above is built on.
