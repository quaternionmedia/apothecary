# Being depended on

**Hermetic.**

This repository has consumers that pin it, and nothing in the parts knows
about them. `datum`'s enclosure record, *Enclosure Parts Live in Apothecary*,
requires that in its clause 2, and `datum_core` renders as a sensible 40 mm
tray for someone who has never heard of the project it was drawn for. The
record is `adr/DRAFT-enclosure-parts-live-in-apothecary.md` on the governance
corpus's `project/datum` branch, which `datum` pins as its `governance/qm`.

But the same record has a clause pointing the other way:

> 5. **This project depends on a released apothecary version**, pinned, and
>    consumes parts through apothecary's CLI or API rather than by path.
>    Geometry changes land upstream and arrive here by version bump.

Read from this side, that is an obligation on *this* repository: **a geometry
change reaches a consumer by being published.** Until it is published, the
consumer either does without it or pins a commit — and a commit on an unmerged
branch is a state nobody else can obtain.

## Who is watching

    >>> from apothecary.release import consumers_waiting
    >>> consumers_waiting()
    ['quaternionmedia/datum']

This is not a dependency. Nothing here imports it, no part is shaped by it, and
the list existing does not entitle a consumer to influence a part. It records
who is affected when this repository publishes, so that publishing is a
decision made with the consequence visible.

## What a downstream may pin

    >>> from apothecary.release import declared_version, published_versions
    >>> declared_version()
    '0.1.0'
    >>> isinstance(published_versions(), list)
    True

`apothecary release` answers whether this commit could legitimately become
something a consumer depends on, and `--check` exits non-zero when it could
not. It publishes nothing: tagging is a human act, and the corpus is explicit
that assistants draft and humans decide.

The questions it asks are ones this repository can answer from its own state —
is there a version, has it already been used, is this commit on a branch anyone
else can obtain, is the tree clean. It does not try to judge whether the change
is any good; that is what review is for.

## Until a release is tagged

`apothecary release` says what is published. Until a first release is tagged,
a consumer pins a commit, and clause 5 is unmet for a reason that lives in this
repository rather than in that one. `datum`'s side needs no reminder:
`datum apothecary --check` reports the deviation while nothing is published,
and fails once something is.

Closing it needs two acts here, in order: merge to `main`, and tag a version.
