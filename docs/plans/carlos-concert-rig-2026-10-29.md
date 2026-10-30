# A synth rig photographed through a concert, held in carlos: a plan

*Slice 1 is built, on `explore/qm-family` (`apothecary/rig/`, `apothecary
rig`); it is not pushed. Slices 2 to 6 are not built.*

## What this plans

A camera looks down on a rig of a few synths. From each picture, apothecary
reads where every knob, fader, drawbar and switch stands, and which sockets
have a plug in them. It reads them against carlos's own drawing of each
device. Carlos holds the rig with those values and draws it. So, through a
concert, the rack in carlos is the rig on stage, and the readings kept along
the way are the concert's record: they can be sent to carlos again, in order,
afterwards.

This plan turns the family lane toward carlos's rigs. The
[bench plan](qm-family-carlos-2026-10-29.md) was the other way round: carlos
drawing apothecary's bench. Its slices 2 and 3 wait.

The same pipeline comes back to apothecary afterwards, one rig at a time: the
airgap's test rig, then a server room (*After the concert*).

## The two sides

The rule is the one the bench plan records: carlos holds and draws the rig,
and apothecary does everything else. Turned toward carlos's rigs, that splits
as follows.

**Carlos knows what the devices are.** Its catalogue entry for each device
says what it has and where each thing is:

- each parameter's range;
- each control's place on the panel, as fractions of the face, with its kind
  (`knob`, `fader`, `drawbar`, `encoder`, `switch`), its size, and a fader's
  orientation and travel;
- each socket's place and side;
- the device's real size, as a box in millimetres.

The rig itself is a `carlos.patch`: its devices, the leads between them, and
each module's parameter values. Carlos derives a knob's turn from its value
(−135° to +135° over the range), slides a fader to its value's fraction
("up is more"), and draws panels in its `irl` mode.

**Apothecary looks.** It owns:

- the camera, and the picture;
- where each device's face is in the picture;
- reading each control and each socket off the picture;
- following the frames through a concert;
- keeping the record.

Carlos's catalogue entries, and the rig, are read from carlos over the loopback,
or from a carlos checkout's `catalogue` folder. Apothecary keeps no copy of
them, apart from the copy a setup takes when its faces are pinned (below).

## The seam

The seam does not change: it is carlos's `hold` action on `POST /family/cue`,
from the bench plan. A reading is held as a `carlos.patch` and a state for each
module and lead:

- **The patch:** the rig's modules, each with the `parameters` it was read at,
  its leads, and `display.mode` `irl`. Carlos gets values, never rotations,
  which is what its format allows.
- **A module's state:** how many of its controls were read, and each one that
  was not, with the reason. Examples: an encoder turns without end; there was
  no pointer to see; the knob points past its sweep; the face is not in the
  picture.
- **A lead's state:** whether a plug was seen at both ends, at one end, or at
  neither, or whether an end is on a face the camera does not see. A plug seen
  in a socket that no lead names is a line on its module.

Slice 1 needs nothing new from carlos.

## The setup

A setup document, `apothecary.rig-setup` version 1, says what a picture shows:

- the rig, as a `carlos.patch`;
- the catalogue entries of the devices in it, as carlos had them when the setup
  was made;
- for each module the camera sees, its face: the side, and the face's four
  corners in the picture, as fractions across and down.

The corners go top left, top right, bottom right, bottom left, the order
`apothecary/vision/projection.py` writes a picture's own corners in. Four
corners make the one mapping from a point on the face to a point in the
picture, a homography, so a face seen at a slant reads as well as one seen
straight on.

The entries are copied into the setup on purpose. The faces were pinned against
one drawing of each device, and the reading has to use that same drawing. If
carlos's layout changes later, the setup is made again; it is not quietly read
against the new layout.

## Reading a control

Every reading is made in face coordinates and sampled from the picture through
the face's mapping. The picture is Pillow's, in grey, as the plain finder reads
it, with nothing else installed. Sizes are carlos's drawing sizes read as
millimetres: at size 1, a knob is 18 mm across, a socket 11 mm, and a fader's
cap 10 mm by 5 mm. That holds until real photographs measure them (slice 4).

| Kind | Read as | Unread when |
|---|---|---|
| `knob` | The angle round a ring inside the knob where it differs most from the ring's middle value: the pointer. The angle sets the value over carlos's 270° | The ring has no pointer to see, or it points into the gap at the bottom |
| `fader`, `drawbar` | The point along the travel, averaged across the slot, where it differs most from the travel's middle value: the cap. Up, or right, is more | Nothing along the travel stands out |
| `switch` | Whichever half of the body is lighter: the lever. Up is the top of the range | The halves are alike |
| `encoder` | Never | Always: it turns without end, so a picture shows no position |
| socket | A plug, unless the centre is darker than the ring round it by enough to be an empty hole | The face is not in the picture |

Every result carries a confidence: the contrast it was read on.

## The path

1. **A picture read against carlos's panels.** *Built.* What it includes:
   - the setup document;
   - the reader above;
   - pictures of a rig drawn at known values through a pinhole camera, so
     every answer is known;
   - `apothecary rig check`, which measures the reader on those pictures;
   - `apothecary rig read`, which reads one picture;
   - `apothecary rig follow`, which reads a folder of frames in order, holds
     each reading in carlos, and keeps the record beside the frames;
   - `apothecary rig simulate`, which draws a concert: songs that move a few
     controls each and pull or push a plug between them.

   Drawn pictures prove the plumbing, not the eyes: the same drawing rules
   both draw them and read them.
2. **Carlos turns in place.** When a hold keeps the same rig with new values,
   carlos turns the knobs and slides the faders where they stand, rather than
   drawing the rack again. A control apothecary could not read is drawn as
   unread. This is carlos's side, and it only draws.
3. **Faces pinned on a real photograph.** A window in apothecary's viewer shows
   the camera's picture, and a person drags each device's four corners onto
   it. The first guess comes from the site's camera pose, where the rig stands
   in a site. The setup is kept in the state folder, like a camera's record.
4. **Real photographs measured.** The owner's rig is photographed at positions
   set by hand and written down, and `rig check` is run on those photographs.
   The thresholds are recorded in `docs/validation/`. The setup picture then
   teaches each control its own look: which way the pointer is lighter, the
   knob's real sweep, and what an empty socket looks like.
5. **A concert, live.** During a show, the camera keeps a frame every few
   seconds in `captures/`. `rig follow` reads the newest frame as it arrives,
   and each reading is tied to the hub's cue, the one carlos already holds. The
   record is the show's.
6. **Printed for the rig.** From the parts library: a camera mount for a mic
   stand or a desk edge, and a corner tab for each synth, so the setup comes
   back the same at the next gig.

## Taken as the start

These defaults were chosen when slice 1 was built. Each one is a default, not a
decision the owner has made yet.

- **The rig:** carlos's `moog.subharmonicon.complex` example. The Subharmonicon
  clocks the DFAM, and the DFAM returns through its VCA to a Qu-24 seen from
  the back. Two synths face the camera, and the desk is behind them.
- **What a concert is:** a folder of frames, in time order by name. The record
  is `readings.jsonl` beside them.
- **Where the frames come from:** anything that writes pictures into a folder,
  whether the viewer's camera, a phone's time-lapse or ffmpeg. The follower
  reads a folder; it does not drive a camera.

## Open

- Which synths the owner's real rig has, and whether it can be photographed at
  known positions. This is slice 4, and nothing about the eyes is known until
  it is done.

## After the concert

Each one follows in turn, once the one before it reads real pictures:

- **The airgap's test rig.** The airgap part, built and on a test rig, with its
  dials and gauges read as this reads a synth's controls. The readings stand
  beside what the Airgap panel predicts for the same settings.
- **A server room.** Racks are faces, patch panels are sockets, and a camera
  looks along each row. The readings say which ports have a lead in them,
  against the room as drawn.

## The demo

Carlos runs from its `feat/hold-the-rig` clone, on 4186, as in the bench
plan's demo. Then:

```bash
uv run apothecary rig simulate --carlos http://127.0.0.1:4186 --out .cache/concert
uv run apothecary rig follow .cache/concert --carlos http://127.0.0.1:4186 --pace 1
```

The first command draws the concert's frames, with its setup and the truth of
each frame. The second sends them to carlos one a second, as a replay of the
concert. Carlos's rack draws the Subharmonicon and the DFAM in `irl` with every
knob and fader where the frame shows it. A lead whose plug was pulled is drawn
as a fault until it goes back in.
