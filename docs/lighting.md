# Lighting: a theatre, its rig, and a console's levels

A site can carry a lighting rig: fixture types, a patch (channel, universe and
address, position, orientation), and live levels from a console. The viewer draws
each placed fixture in the colour its levels give it, with a beam, and lists the
patches that have no position, with the console's own words, in its Lighting
window, a tab beside Pictures while the site has a rig. `apothecary/lighting.py` is the model
and is tied to no one theatre; `apothecary/theatre_site.py` is the example that
uses it, the `theatre` site.

## The theatre

The shell is the `theatre` part (`parts/theatre/theatre.scad`): the stage floor,
its side and upstage walls, the proscenium wall with its opening, the pit below
the stage, and the side walls running downstage into the house. Each size is a
slider: on `/viewer/sites/theatre`, the shell's ring, Part › Edit -- stage width
and depth, wall height, how far the house runs downstage, the proscenium opening's
width and height, and the pit's width, length and depth -- and Apply draws the
resized shell. Every default is a measurement of one real stage house, traced from
its plan: a few boxes, not the outline, with the house's seating, its back wall
and the fly tower not drawn.

The frame: millimetres; the origin is the plaster line's centre on the stage
floor; +x is to the right as the house sees the stage, +y upstage, +z up. The rig's
positions are metres in the same frame.

## The rig, and another in its place

A rig is a folder of a console's two exports: `patches.csv` (channel, fixture
type, address, label, position, orientation) and `fixture-parameters.csv` (each
type's parameters). The site reads the folder `APOTHECARY_THEATRE_RIG` names,
else `examples/theatre-rig/`: a made-up rig of front of house, three electrics, a
cyc groundrow, house lights and two scenic elements, hung for the shell at its
defaults. Any console's exports, saved under those two names in a folder, stand in
for it:

    APOTHECARY_THEATRE_RIG=/path/to/a/rig uv run apothecary serve

A beam starts pointing straight down; the patch's ORIENTATION is Euler degrees in
the site's frame, X tilting it towards upstage. The site's check names a fixture
the shell at its defaults does not hold, an unknown fixture type, a DMX map that
does not fit its address span, and two patches on one address.

The rig hangs where its exports place it, so a shell resized by its sliders does
not move it. A rig that follows the shell -- electrics at fractions of the stage
depth, fixtures spread across the opening -- needs the site rebuilt from the
part's applied numbers, which the server does not know today (an applied variant
is the page's tab's); that is the next step.

## Getting levels in

- `apothecary serve --console-sacn` listens on UDP 5568 for a console's sACN
  (E1.31), multicast or unicast to this machine, for the universes the rig
  patches. Point the console's (or Eos Visualizer's) sACN output at this machine.
  Only addressed fixtures carry DMX; the DMX channel order of each fixture type
  is in `lighting.DMX_MAPS`.
- `apothecary serve --console-osc` listens on UDP 8001 for an Eos console's OSC
  output and shows its status (command line, active channels) beside the lighting.
  In Eos, Setup > System > Show Control, set OSC to UDP, the TX IP to this
  machine's address and the TX port to 8001. It keeps the latest arguments of each
  `/eos/out/...` message (`status` in the state). It carries no levels: Eos sends
  per-channel levels only to a program that has subscribed, and a subscription is a
  message sent to the console, which the guard refuses.
- `PUT /sites/{site}/lighting/state` takes levels by channel number
  (`{"levels": {"1": {"Intens": 0.5}}}`) or a universe's slots as base64. This is
  how a bridge feeds what has no address: movers, virtual layers and servers,
  scenic elements.
- `apothecary lighting simulate` sweeps every fixture, for a demo with no console.
- `GET /sites/{site}/lighting` is the rig and its checks; `GET .../lighting/state`
  is the latest levels, their age, and each channel's colour.

## What the guard allows

`apothecary/stays_local.py` still refuses every connect and send beyond this
machine. The one change is `console_listener()`: a UDP socket on a console port
that may bind beyond loopback, on 5568 (sACN) or 8001 (OSC) alone, and receives
only. A test holds it to the two receivers.

Not built: asking the console for anything (OSC subscribe or get).
