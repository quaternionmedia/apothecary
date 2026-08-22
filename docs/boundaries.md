# The boundary between datum and apothecary

Which repository owns what, why the line falls there, and what happens at the
crossing. Written from the records that already decide it, and from the code
that already implements it — not proposed here.

## The line

> **datum designs a product and integrates a system. Apothecary carries the
> shared design tooling and the index of what has been designed.**

`datum` owns the thing being built: the event schema, the firmware, the board,
what the product must do. Apothecary owns the means of making and finding
geometry: the parts library, the OpenSCAD seam, the assembly model, the viewer,
the checks. Apothecary has other consumers; `datum` is one of them.

That is not an invention. `governance/qm/adr/DRAFT-enclosure-parts-live-in-apothecary.md`
decides it, and its clause 2 supplies the test: **a part must render something
coherent with no knowledge of the consuming project.** A part that only makes
sense as `datum`'s accessory belongs in `datum`.

## What each side owns

| | datum | apothecary |
|---|---|---|
| The event envelope, topics, firmware | ✓ | |
| The board: outline, connector position, contact pitch | ✓ | |
| Which enclosure it uses, and pinned to which version | ✓ | |
| Whether the product's behaviour is right | ✓ | |
| Geometry, and how a requirement becomes a shape | | ✓ |
| Manufacturability: wall, tolerance, print settings | | ✓ |
| Whether a layout closes, whether bounds are true | | ✓ |
| Indexing: what parts exist, what is unresolved | | ✓ |

The test for a single number: **would it change if you printed the same object
on a different machine?** Then it is manufacturing, and apothecary's. Would it
change if the board changed? Then it is interface, and the consumer's.

## What happens at the crossing

Three mechanisms, all built:

**The black-box seam.** `models/blackbox.py` describes an artifact apothecary
places but does not author — its envelope, its mounts, its keepouts — and
`BlackBoxProvider` is a Protocol. `StubProvider` returns hand-entered numbers;
`KiCadProvider` reads a real board outline through the same interface. Swapping
one for the other changes no geometry code. `source` on each box is what lets a
reader tell a measured envelope from a guessed one.

**A pin, not a path.** `datum.hil.APOTHECARY_PIN` names the apothecary commit
`datum` was verified against, and `datum`'s own CI checks that pin out and
renders every part it depends on. Geometry changes land here and arrive there
by a reviewed bump. (The enclosure record's clause 5 asks for a *released
version* consumed through the CLI or API; a commit pin consumed by path is
where that stands today, and the gap is deliberate rather than forgotten.)

**Parts are useful to strangers.** Clause 2 again. `datum_core` renders as a
sensible 40 mm tray for someone who has never heard of `datum`, and only the
consumer's black box makes it that project's enclosure.

## Where a problem is owned

`apothecary/spaces.py` makes this line executable. Every open problem the
repository can state carries an owner, and the owner is derived rather than
typed:

| Owner | Means | Example |
|---|---|---|
| `apothecary` | a commit here closes it | a wrapper whose declared bounds its geometry does not have |
| `datum` | only the consuming project can close it | the board envelope is still a stub; WP-4 produces the schematic |
| `human` | a decision between defensible alternatives | `walls`: the record says 3, another part says 2.4 |
| `measurement` | waits on a physical artifact | a mounting surface nobody has measured |

    apothecary problems --owner human
    apothecary problems --owner datum
    apothecary solutions

A problem with no owner would be the interesting failure — it would mean the
boundary has a hole. The index reports the count per owner precisely so that
shows up rather than hiding.

## Where this line is currently blurred

Stated because an unstated exception becomes the rule.

- **`parts/datum` and `parts/datum_core` both describe one object.** The first
  is what `projects/assemblies/datum_bench.py` drives through the black-box
  seam; the second is the detailed enclosure with the navigable assembly and
  the contested values. Neither is a superset. They should meet — `datum_core`
  taking its board envelope from a `BlackBox` rather than its own defaults —
  and that is a design step nobody has taken.
- **`datum_core_site.py` lives here and models `datum`'s enclosure.** It is
  apothecary geometry by the test above, but its existence is entirely due to
  one consumer. If a second consumer never appears, it is a candidate for
  moving.
- **Clause 5 is half met**, as noted above.

## What the line is not

It is not a division of labour between people, and it is not about which
repository a change is easier to make in. It is about which repository can
*answer* for a fact afterwards. Apothecary cannot answer for where the
connector is; `datum` cannot answer for whether 3 mm of PETG prints.
