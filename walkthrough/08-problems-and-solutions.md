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
today's. What this page does assert is the part that must hold everywhere:
every kind is drawn from the one table, and every open kind has something that
can close it.

Nothing here is entered by hand. Each problem is derived from a model that
exists — a part's contested values, the build checklist, a layout validator,
the black-box seam — so the index cannot go stale the way an issue list does.

## Ownership is the boundary, made executable

The interesting field is who can close it:

    >>> from apothecary.spaces import KIND_OWNER
    >>> KIND_OWNER["contested"], KIND_OWNER["drift"]
    ('human', 'apothecary')

Four owners, and each means something different about what happens next.
`apothecary` is a commit here. `datum` is the consuming project's to supply —
the board outline is its fact, and no amount of work here produces one.
`human` is a decision between defensible alternatives. `measurement` waits on a
physical artifact.

    >>> from apothecary.spaces import APOTHECARY, DATUM, HUMAN, MEASUREMENT
    >>> set(summary()["by_owner"]) <= {APOTHECARY, DATUM, HUMAN, MEASUREMENT}
    True

Every problem carries one, and one that carries none would mean the boundary
has a hole:

    >>> all(p.owner and p.closes_with for p in problems())
    True

`docs/boundaries.md` is the prose; this is the part a machine can check.

## The owner comes from one table

It did not always. An adversarial pass changed `KIND_OWNER["contested"]` to
`apothecary` and the index reported exactly the same thing, because the
contested branch typed the owner again instead of reading the table. Two places
declaring one fact is the duplication this index exists to avoid.

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
| Over HTTP | `/problems`, `/problems?owner=human`, `/solutions`, `/spaces` |

A build volume changes the answer, because "fits the printer" cannot be
answered without one:

    >>> summary(build_volume=(220.0, 220.0, 250.0))["problems"] < summary()["problems"]
    True
