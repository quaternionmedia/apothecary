# Four org-level gaps this work exposes

| | |
|---|---|
| **Kind** | repo-edit |
| **Repo** | quaternionmedia/qm, branch `main` |
| **State** | stub |
| **Depends on** | The records this work eventually owes |
| **Graduates to** | one perspective, then possibly two org records |
| **Verified** | `records/` and `PRINCIPLES.md` read in full at tip of `main`. No privacy, PII, personal-data or biometric record exists anywhere in the corpus — searched by filename and by content. |

## What
Three gaps, none of which a project record can close:

**1. Personal data has no record.** The open-license record's §6 governs whether
a *provider* is replaceable and says nothing about what *data* crosses the seam.
The narrow, enforceable version: personal-data-bearing inputs are a named class,
and any record selecting a service that receives one answers an **egress test**
alongside §6's ownability test. One decision, falsifiable, enforced by the same
reviewed-inventory mechanism §6 already uses.

**2. The branch-namespace table is incomplete.** Five namespaces, none of which
describes a branch heading toward `project/<name>` — the same class of gap the
README already admits about `propagate/*`.

**3. The unification principle may belong at org level.** rad and apothecary are
the two data points the org's own second-data-point rule asks for.

**4. Two new proposals are drafted and need a home at the top level.** The
plain-language rule (`../proposals/light-language.md`) and the local-only rule
(`../proposals/runs-and-stays-local.md`) are both written and both bind more than
one project. Neither can live on a project's own branch. The local-only one
partly subsumes gap 1 above — worth deciding whether it replaces that proposal or
sits beside it.

**5. "Show it by running it" has no answer for a run that ran nothing.** The
rulebook says a claim is shown by running it, and says nothing about a run that
reports success because the checks were switched off rather than because they
passed. This happened here — one fixture skipped and twenty-six browser tests
skipped silently behind it, with a green result. It was found by reading, not by
any check. The enforceable version is one sentence: *a check that can decide the
tests cannot run must be one an individual test asks for, never one others are
built on*, plus a recorded expected count that fails when it drops. Both are
mechanisms, not motherhood. See `../CONCERNS.md` item 15.

## Why now
Gap 1 now, because photographs of a workshop, a garage or a home contain people,
addresses, licence plates and equipment inventories, and this is the first
feature line in the corpus to ingest them. Gap 2 now, because it blocks the very
next push. Gap 3 not yet — one host is an anecdote. Gap 5 now, because it is the
cheapest of the five to write and it has already cost this project a false green
run once.

## Seam
The corpus's own path from gap to record is a perspective: attributed, dated,
non-binding, indexed in `perspectives/README.md`. Several existing `DRAFT-*`
records began that way.

Slot cost, verified: an org record on `evolve/<slug>` and a perspective both base
`main` and therefore share slot `""`. They cannot both be open at once. Open the
perspective first — it is cheaper, it binds nothing, and it is the artifact that
makes the case for the record.

## Open questions
- A record called "QM privacy policy" would be the motherhood statement
  `PRINCIPLES.md` explicitly warns against. The version with teeth extends a
  mechanism that already exists. Getting that framing right is the whole job.
- Whether gap 3 waits for benchmark to be a second data point, or whether rad
  plus apothecary already counts. The second-data-point rule suggests it counts
  only once both have *shipped*, not once both have planned.
