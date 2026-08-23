# Being depended on

**Hermetic.**

This repository has consumers that pin it. That is easy to forget from inside,
because nothing in the parts knows about them — clause 2 of the enclosure
record requires exactly that, and `datum_core` renders as a sensible 40 mm tray
for someone who has never heard of the project it was drawn for.

But the same record has a clause pointing the other way:

> 5. **This project depends on a released apothecary version**, pinned, and
>    consumes parts through apothecary's CLI or API rather than by path.
>    Geometry changes land upstream and arrive here by version bump.

Read from this side, that is an obligation on *this* repository: **a geometry
change reaches a consumer by being published.** Until it is published, the
consumer either does without it or pins a commit — and a commit on an unmerged
branch is a state nobody else can obtain.

That obligation was documented only in the consumer's repository. A contributor
here had no way to find out it existed, which is how a one-directional
boundary becomes a one-directional surprise.

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

## The state today

Nothing here has ever been released. No tags, no GitHub releases, and the
version has stood at 0.1.0. So the downstream pins a commit by necessity rather
than by choice, and clause 5 is unmet for a reason that lives in this
repository rather than in that one.

The consumer's side of this is already automatic: it reports the deviation
while nothing is published and fails the moment something is. Nobody has to
remember to tighten it later — which matters, because "we will fix this when X
happens" depends on somebody re-reading the note at the moment X happens, and
nobody does.

Closing it needs two acts here, in order: merge to `main`, and tag a version.
