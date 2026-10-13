# Problems and solutions

**Hermetic.**

Two indexes over what this repository already knows, so a reader does not have
to run five commands and hold the answers in their head.

    >>> from apothecary.spaces import problems, capabilities, summary, KIND_OWNER
    >>> set(summary()["by_kind"]) <= set(KIND_OWNER)
    True
    >>> summary()["unaddressed_kinds"]
    []

Which kinds are open is deliberately not pinned here. It depends on what has
been rendered on this machine — a part whose STL exists has been measured, one
whose STL does not has not — so a page that asserted the census would fail on a
fresh checkout for a reason that is not a defect. `apothecary problems` prints
the kinds open on this machine. What this page asserts is what holds everywhere:
every kind is drawn from the one table, and every open kind has something that
can close it.

Nothing here is entered by hand. Each problem is derived from a model that
exists — a part's contested values, the build checklist, a layout validator,
the black-box seam — so the index cannot go stale the way an issue list does.

## Each problem has an owner

Each problem names who can close it:

    >>> from apothecary.spaces import KIND_OWNER
    >>> KIND_OWNER["contested"], KIND_OWNER["drift"]
    ('human', 'apothecary')

There are four owners, and [where a problem is
owned](../docs/fitting-a-part.md#where-a-problem-is-owned) says what each means
for what happens next:

    >>> from apothecary.spaces import APOTHECARY, DATUM, HUMAN, MEASUREMENT
    >>> set(summary()["by_owner"]) <= {APOTHECARY, DATUM, HUMAN, MEASUREMENT}
    True

Every problem carries one, and what closes it:

    >>> all(p.owner and p.closes_with for p in problems())
    True

## The owner comes from one table

A problem's owner is its kind's in `KIND_OWNER`. The one exception is an
unmeasured board, which only the consuming project can supply:

    >>> all(p.owner == KIND_OWNER[p.kind] or (p.kind, p.owner) == ("unmeasured", DATUM)
    ...     for p in problems())
    True
    >>> {p.owner for p in problems() if p.kind == "contested"}
    {'human'}

## What the index is not

Open *questions*, not failing checks. An assembly that has drifted from the
parts it models is a failing test — `tests/test_datum_core_site.py` is that
gate, and the suite is where it reports. This answers "what is unresolved",
never "is the build green".

## Recipes

| | |
|---|---|
| Everything open | `apothecary problems` |
| Only what needs deciding | `apothecary problems --owner human --detail` |
| Only what datum owes | `apothecary problems --owner datum` |
| What can close them | `apothecary solutions` |

A build volume changes the answer, because "fits the printer" cannot be
answered without one:

    >>> summary(build_volume=(220.0, 220.0, 250.0))["problems"] < summary()["problems"]
    True
