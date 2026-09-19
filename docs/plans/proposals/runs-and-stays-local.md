# Proposed rule — it runs on your machine and the data stays there

**Status:** proposed, nobody has agreed to it yet
**Applies to:** at minimum this photo work; probably every project
**Where it has to move to:** the shared rulebook, at the top level

## The rule

**Two halves.**

The software keeps everything it produces on the machine it runs on. Nothing is
written anywhere else — no outside storage, no outside database, no usage
reporting, no error reporting.

Everything needed to use it runs on that same machine. With the network switched
off, it still works.

If a capability cannot be built that way, it is not built yet. It waits, and the
reason it is waiting is written down.

## Why

Slow and yours can be made fast later. Fast and someone else's cannot be made
yours later — that is a rebuild, and it happens at the worst possible moment,
which is whenever the other party changes their mind.

So performance is not the thing being protected here. A slow, clumsy, obviously
imperfect result that runs on your own machine is the acceptable outcome. A fast
excellent result that stops working when an account is closed is not.

This also settles a question that was open. The photo work needs something that
recognises shapes in an image, and the plan so far deliberately refused to choose
one. Under this rule the field narrows on its own: whatever gets chosen has to
run locally. Nothing that sends a photograph anywhere is a candidate, so no
separate decision about photographs leaving is needed. The general rule covers
it.

## What this rules out, plainly

- Sending a photograph, or anything derived from it, to an outside service.
- Storing results in outside storage, even storage the organisation owns
  elsewhere on its own network — see the open question below.
- Anything that reports back how the software was used, or that a fault occurred.
- Anything that checks a licence, a version, or an update over the network while
  running.
- Loading part of the interface from a public website while someone is using it.
  The current viewer does exactly this for its drawing library. Under this rule
  that stops being a known untidiness and becomes a break of the rule.

## How it gets checked

Run the tests with the network switched off. If anything reaches for it, the
tests fail.

**This check now exists and has been watched failing.** It lives in
`tests/test_stays_local.py`. Every way Python has of opening a connection is
replaced with one that refuses, and then the whole picture path runs. To confirm
it works rather than merely passes, a deliberate outside call was put inside the
shape finder: four tests went red, naming the call. The call was removed and they
went green again.

The file also carries a test of the guard itself, so a green run cannot be a
green run of nothing.

It does not catch everything. It catches the common case, which is a library
quietly fetching something at the moment it is first used.

## The gap this fills

There is no rule anywhere in the current rulebook that says a project must run
locally. The closest is the first principle — if a provider vanished tomorrow,
the response must be a settings change rather than a rebuild. That rules out
*depending* on an outside party. It does not rule out *using* one, and the
difference is exactly where this work would otherwise drift.

There is also no rule about what information may leave a machine, only about
whether the party receiving it could be swapped for another. That gap was found
by the photo work and is the more serious of the two.

## What would make us drop or change this

- A capability that matters is impossible locally and stays impossible for a
  year. Then the rule is costing more than it protects and the trade should be
  re-argued in the open rather than quietly ignored.
- The tests-with-no-network check turns out to pass while something still reaches
  out. Then the check is theatre and needs replacing before the rule is trusted
  again.
- Someone needs to use this on a machine that cannot run it at all — a phone, a
  very old computer. That is a real conflict between this rule and being useful,
  and it deserves its own decision rather than an exception bolted on here.
