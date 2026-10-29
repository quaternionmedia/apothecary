# The bench as a rig carlos can draw: a plan

*Slice 1 is built on `explore/qm-family` (`apothecary/wiring/`). Slices 2 to 4
are not.*

## What this plans

Apothecary knows what is on its bench in pieces: a port and what answered on
it, the sketch last flashed there, the scene node a board is pinned to, a
picture of the bench. Carlos, in the instruments family
([quaternionmedia/carlos](https://github.com/quaternionmedia/carlos)), draws a
rig from real gear, patched on the face its sockets are on, and writes the whole
rig as one versioned JSON document, `carlos.patch`.

The plan joins them into one loop: a picture names a device, the wiring and the
IO configuration say what it is joined to, and a pipeline keeps the rig as
written beside the rig as observed, so that where they disagree is something
both pages show.

## The two sides as they stand

Apothecary (`irl`):

- `firmware/devices.py` holds five views of a board on a port: detected,
  probed, expected, observed (its hello) and, for a G-code firmware, identified
  (`M115`). A board's identity is its MAC, else its USB bridge's serial number,
  else the port.
- `firmware/bindings.py`: `bindings_for_site` gives one row per scene node
  that names firmware or has a device pinned to it, with the board on it now.
- `parts/boards/` draws five boards from their makers' drawings; a
  described board's `part.json` carries its bounds in millimetres.
- `vision/`: the finders (`stated`, `plain`) find shapes and do not name them.
  `FoundShape.label` is read only by `ScaleReference.known_shape`. A local model
  behind the finder is [its own plan](photo-finders-local-models-2026-09-21.md).
- `lighting.py` already uses *rig* and *patch*, for a theatre's fixtures and
  their DMX addresses. This work is called *wiring* so the two stay apart.

Carlos (`instruments`; default branch `they`, read at a5540e7, and
`feat/family-control` at 91678af):

- A catalogue: one JSON file per device, addressed `<maker>.<model>`; each
  socket says its signal, its carrier, its connector and the side it is on;
  `layout.box` is the device's size in millimetres. The connector and category
  vocabularies are closed.
- `carlos.patch` version 3: modules, connections (output end first), groups,
  display, MIDI bindings. Unknown fields are refused. `POST
  /api/patch/validate` checks a document; the browser additionally refuses a
  type or a jack its build does not have.
- `POST /family/cue` and `GET /family/state`, on `feat/family-control` only:
  a hub loads one of carlos's shipped examples or turns the rack. Nothing
  loads a posted document, and persistence waits on carlos's datastore
  decision.
- Outbound calls are planned, never sent.

## The seam

Connect, not merge (the draft record *a family is bordered by what it
drives*). Apothecary writes `carlos.patch` documents and catalogue entries in
carlos's own device-file format, and reaches carlos over REST; neither imports
the other's source. The replaceability test holds: anything that reads a
`carlos.patch` could stand where carlos stands.

Carlos refuses unknown fields, so how apothecary knows each module (the port,
the identity, the binding, the firmware) travels beside the document, never
inside it.

## The loop

1. **Declared**: a `carlos.patch`, the rig as somebody wrote it.
2. **Observed**: what apothecary sees: ports, probes, hellos, bindings,
   pictures.
3. **Reconciled**: the rig as it is, as a `carlos.patch`, with the evidence for
   each module and every disagreement with the declared one.
4. **Shown**: on apothecary's Bench, and in carlos's rack once carlos loads a
   posted document.
5. **Acted on**: a board plugged in, a sketch flashed, a lead moved, or the
   declared rig edited. Then observed again.

The disagreements are of five kinds:

| Kind | Means |
|---|---|
| missing | declared, and nothing observed answers for it |
| unexpected | observed, and not declared |
| wrong firmware | running other than what was flashed, or flashed from an older source (`ExpectedFirmware`) |
| unplaced | a node whose part has no catalogue entry, so it has no type to be |
| unobserved lead | declared, and invisible to apothecary (a 3.5 mm lead is): kept, marked, never *missing* |

## Slices

1. **The bench as a patch** (built). `apothecary/wiring/` writes a site's
   bindings as a `carlos.patch`: a module per node whose part has a catalogue
   entry, the computer apothecary runs on as `apothecary.host`, and a USB lead
   from each connected board to it. The evidence and the unplaced nodes come
   beside it. `GET /sites/{s}/wiring` answers all three; `GET
   /sites/{s}/wiring/patch` answers the document alone, for carlos's Import.
   The entries are in `apothecary/wiring/catalogue/`, in carlos's file format.
2. **A picture names a device.** An identification is a ranked list that may
   decline. First by footprint: the plain finder's rectangle and a stated
   scale give millimetres, compared with each board's bounds. The ratio alone
   cannot tell a Teensy 4.0 from an ESP32 devkit (both about 2:1) or an Uno
   from the Creality board (about 1.3), so without a scale it declines between
   them, and what USB says is plugged in breaks the tie. The name goes into
   `FoundShape.label`, which `known_shape` already reads. Then a tag engraved
   on a printed case, and a local model as the finders plan has it. Measured
   with a bench like `vision/bench.py` before any number is quoted.
3. **IO configuration.** `firmware.json` gains an `io` block (pin, role,
   direction, signal) that becomes jacks on the board's entry (header pins on
   its top face) and connections at pin level: the footpedal's switches, the
   blink sketch's LED. A sketch can say its own in its hello, so the declared
   pins and the running ones compare.
4. **The loop closed.** A diff of a declared document against a site, then a
   Bench window showing it, then the reconciled document sent to carlos once
   carlos loads one.

## What carlos needs

Each is carlos's own change, in its repository:

- Categories for a circuit board and a computer.
- The connector `micro-USB`, and a lead from `USB-A` to `micro-USB` carrying
  data.
- A cue action that loads a posted document, beside `patch` and `turn`.
- `feat/family-control` merged into `they`, or this work aimed at it.

Until then, a document from slice 1 is what carlos's own docs call a valid
patch this build cannot render: its server's validator accepts it, and its
browser refuses the types it has no entry for.

Checked on 2026-10-29 with carlos's own `patch_format.load` and
`catalogue.load_device`, from a clone, on the garage with its mainboard
pinned: both branches accept the document. On `feat/family-control` the
footpedal's entry loads as it is, and the others are refused only for the
categories and `micro-USB` above. On `they` every entry is refused, since its
sockets have no `carrier` and no `data` signal: the entries follow
`feat/family-control`'s socket model. A USB socket's carrier is written out,
because carlos's loader refuses the default `direct` for a USB connector
rather than inferring it.

## To decide

- Where the catalogue entries live: in apothecary, beside the boards they
  draw, and offered to carlos; or only in carlos, read from its API. Slice 1
  keeps them in apothecary, where the drawing and the sockets come from the
  same maker's drawing and a test holds each entry's box to its part's bounds.
- Which carlos branch is the target: `they`, or `feat/family-control`, whose
  socket model the entries already need.
- Where a declared rig is kept: per site in apothecary, or in carlos once it
  persists patches.

## After carlos

The family record names more members that meet apothecary's bench: `stomp`
(in both `irl` and `instruments`, beside the footpedal), `datum`, and the
show-control hub whose cues carlos's `/family/cue` answers. None of them has
been read for this plan.
